// SPDX-License-Identifier: GPL-2.0-only
#include <linux/async.h>
#include <linux/dmi.h>
#include <linux/init.h>
#include <linux/kobject.h>
#include <linux/list.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/pci.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/suspend.h>
#include <linux/sysfs.h>

#if defined(CONFIG_X86)
#include <asm/cpufeature.h>
#endif

#include "policy.h"
#include "recipes.h"
#include "unlock_610.h"

static char *targets;
module_param(targets, charp, 0444);
MODULE_PARM_DESC(targets, "\"all\" or comma-separated PCI addresses to unlock");

static char *rate = "full";
module_param(rate, charp, 0444);
MODULE_PARM_DESC(rate, "full (default) or stock. stock does not write unless rewrite=1");

static char *ss0;
module_param(ss0, charp, 0444);
MODULE_PARM_DESC(ss0, "Optional SS0 value used with rate=full. Each nibble must be 0x0, 0x1, 0x8 or 0x9");

static char *ss1;
module_param(ss1, charp, 0444);
MODULE_PARM_DESC(ss1, "Optional SS1 value used with rate=full. Low nibble must be 0x0, 0x1, 0x8 or 0x9");

static bool rewrite;
module_param(rewrite, bool, 0444);
MODULE_PARM_DESC(rewrite, "With rate=stock, run the pre-driver sequence to store the documented power-on selectors");

static bool dry_run;
module_param(dry_run, bool, 0444);
MODULE_PARM_DESC(dry_run, "Identify cards and publish status, but do not write");

static bool experimental = true;
module_param(experimental, bool, 0444);
MODULE_PARM_DESC(experimental, "Allow experimental device IDs (default: on)");

static bool resume = true;
module_param(resume, bool, 0644);
MODULE_PARM_DESC(resume, "Re-apply after resume from suspend, which powers the cards off (default: on)");

/* A target card. Those actually unlocked stay listed so resume can find them.
 * Skipped and failed cards stay too, for the status file. */
struct card {
	struct list_head node;
	struct gu_device device;
	const char *disposition;
	int result;
};

static LIST_HEAD(cards);
static DEFINE_MUTEX(cards_lock);
static ASYNC_DOMAIN_EXCLUSIVE(unlock_domain);
static struct gpu_unlock_610_shared shared;
static struct kobject *gu_kobj;
static bool in_guest;
static bool pm_registered;
static char guest_dmi[96] = "unknown";

static bool running_in_guest(void)
{
#if defined(CONFIG_X86)
	return boot_cpu_has(X86_FEATURE_HYPERVISOR);
#else
	return false;
#endif
}

static void note_guest(void)
{
	const char *vendor = NULL, *product = NULL;
	size_t i;

	in_guest = running_in_guest();
#ifdef CONFIG_DMI
	vendor = dmi_get_system_info(DMI_SYS_VENDOR);
	product = dmi_get_system_info(DMI_PRODUCT_NAME);
#endif
	scnprintf(guest_dmi, sizeof(guest_dmi), "%s %s",
		  vendor && *vendor ? vendor : "unknown",
		  product && *product ? product : "");
	for (i = 0; guest_dmi[i]; i++) {
		if (guest_dmi[i] == '\n' || guest_dmi[i] == '=')
			guest_dmi[i] = ' ';
	}
	if (!in_guest)
		return;
	pr_info("gpu_unlock: hypervisor guest (%s). The sequence runs in the guest, before nvidia binds, on every boot. Selectors survive the module's own FLR and are cleared when the GPU actually loses power. Virtual functions are refused.\n",
		guest_dmi);
}

/* The next supported NVIDIA card after from, like pci_get_device(). */
static struct pci_dev *next_supported(struct pci_dev *from, const struct gu_card **recipe)
{
	struct pci_dev *pdev = from;

	while ((pdev = pci_get_device(PCI_VENDOR_ID_NVIDIA, PCI_ANY_ID, pdev)))
		if ((*recipe = gu_card_find(pdev->device)))
			return pdev;
	return NULL;
}

static bool transaction_wanted(void)
{
	const struct gu_policy *p = gu_policy();

	if (p->dry_run)
		return false;
	return p->apply || p->rewrite;
}

static void set_disposition(struct card *card, const char *disposition, int result)
{
	mutex_lock(&cards_lock);
	card->disposition = disposition;
	card->result = result;
	mutex_unlock(&cards_lock);
}

/* At boot, before nvidia binds the card. Runs concurrently for each card. */
static void unlock_one(void *data, async_cookie_t cookie)
{
	struct card *card = data;
	struct pci_dev *pdev = card->device.pdev;
	int ret;

	pci_dev_lock(pdev);
	ret = pdev->driver ? -EBUSY : gpu_unlock_610_unlock(&card->device, &shared, false);
	pci_dev_unlock(pdev);
	if (!ret) {
		set_disposition(card, "unlocked", 0);
		pci_info(pdev, "gpu_unlock: unlocked %s\n", card->device.recipe->name);
	} else if (ret == -EBUSY) {
		set_disposition(card, "busy", ret);
		pci_info(pdev, "gpu_unlock: left as is, driver already bound\n");
	} else if (ret == -EALREADY) {
		set_disposition(card, "not-cold", ret);
		pci_info(pdev, "gpu_unlock: feature PLM already open; power-cycle the GPU before changing the preset\n");
	} else {
		set_disposition(card, "failed", ret);
		pci_err(pdev, "gpu_unlock: unlock failed (%d)\n", ret);
	}
}

/* After resume, before nvidia resumes the card it suspended. Losing power in
 * suspend to RAM reset the selectors. Runs concurrently for each card. */
static void unlock_again(void *data, async_cookie_t cookie)
{
	struct card *card = data;
	struct pci_dev *pdev = card->device.pdev;
	bool nvidia;
	int ret = 0;

	pci_dev_lock(pdev);
	nvidia = pdev->driver && !strcmp(pdev->driver->name, "nvidia");
	if (nvidia)
		ret = gpu_unlock_610_unlock(&card->device, &shared, true);
	pci_dev_unlock(pdev);
	if (!nvidia)
		pci_info(pdev, "gpu_unlock: not bound to nvidia, left as is after resume\n");
	else if (ret == -EALREADY)
		pci_info(pdev, "gpu_unlock: selectors still match the preset after resume\n");
	else if (ret) {
		set_disposition(card, "resume-failed", ret);
		pci_err(pdev, "gpu_unlock: unlock after resume failed (%d)\n", ret);
	} else
		pci_info(pdev, "gpu_unlock: preset applied again after resume\n");
}

static bool scheduled(const struct card *card, bool resume_pass)
{
	if (resume_pass)
		return card->disposition && !strcmp(card->disposition, "unlocked");
	return card->disposition && !strcmp(card->disposition, "pending");
}

/* Prepare all selected firmware families, then run the ready cards concurrently. */
static void unlock_cards(async_func_t unlock, bool resume_pass)
{
	struct card *card;
	int ret;

	list_for_each_entry(card, &cards, node) {
		if (!scheduled(card, resume_pass))
			continue;
		ret = gpu_unlock_610_load_shared(&card->device, &shared);
		card->result = ret;
		if (ret) {
			set_disposition(card, "firmware", ret);
			pci_err(card->device.pdev, "gpu_unlock: firmware load failed (%d)\n", ret);
		}
	}
	/* Publish the completed cache only after every selected family is prepared.
	 * A firmware failure leaves result set and disposition "firmware", so the
	 * card is not scheduled. */
	list_for_each_entry(card, &cards, node) {
		if (scheduled(card, resume_pass) && !card->result)
			async_schedule_domain(unlock, card, &unlock_domain);
	}
	async_synchronize_full_domain(&unlock_domain);
	gpu_unlock_610_release_shared(&shared);
}

static void drop_card(struct card *card)
{
	list_del(&card->node);
	pci_dev_put(card->device.pdev);
	kfree(card);
}

/* nvidia resumes its cards from its own notifier, at the default priority 0,
 * once this returns: every card must be finished by then. */
static int gpu_unlock_pm_notify(struct notifier_block *nb, unsigned long event, void *unused)
{
	if (event == PM_POST_SUSPEND && resume && transaction_wanted())
		unlock_cards(unlock_again, true);
	return NOTIFY_DONE;
}

static struct notifier_block pm_nb = {
	.notifier_call = gpu_unlock_pm_notify,
	.priority = 1,
};

/* True when the comma-separated targets list names this PCI device. */
static bool listed(const char *name)
{
	const char *entry, *end;

	for (entry = targets; *entry; entry = *end ? end + 1 : end) {
		end = strchrnul(entry, ',');
		if (strlen(name) == end - entry && !strncasecmp(name, entry, end - entry))
			return true;
	}
	return false;
}

static void report_unmatched(void)
{
	const char *entry, *end;
	struct card *card;
	bool matched;

	for (entry = targets; *entry; entry = *end ? end + 1 : end) {
		end = strchrnul(entry, ',');
		matched = false;
		list_for_each_entry(card, &cards, node) {
			const char *name = pci_name(card->device.pdev);

			if (strlen(name) == end - entry && !strncasecmp(name, entry, end - entry)) {
				matched = true;
				break;
			}
		}
		if (!matched)
			pr_err("gpu_unlock: no supported card at \"%.*s\"\n",
			       (int)(end - entry), entry);
	}
}

static bool any_unlocked(void)
{
	struct card *card;

	list_for_each_entry(card, &cards, node)
		if (card->disposition && !strcmp(card->disposition, "unlocked"))
			return true;
	return false;
}

static ssize_t status_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
	const struct gu_policy *p = gu_policy();
	struct card *card;
	size_t len = PAGE_SIZE;
	size_t n = 0;

	mutex_lock(&cards_lock);
	n += scnprintf(buf + n, len - n, "guest=%u\n", in_guest ? 1 : 0);
	n += scnprintf(buf + n, len - n, "dmi=%s\n", guest_dmi);
	n += scnprintf(buf + n, len - n, "rate=%s\n", p->apply ? "full" : "stock");
	n += scnprintf(buf + n, len - n, "apply=%u\n", p->apply ? 1 : 0);
	n += scnprintf(buf + n, len - n, "rewrite=%u\n", p->rewrite ? 1 : 0);
	n += scnprintf(buf + n, len - n, "dry_run=%u\n", p->dry_run ? 1 : 0);
	n += scnprintf(buf + n, len - n, "experimental=%u\n", p->allow_experimental ? 1 : 0);
	n += scnprintf(buf + n, len - n, "resume=%u\n", resume ? 1 : 0);
	n += scnprintf(buf + n, len - n, "ss0=%#x\n", p->ss0);
	n += scnprintf(buf + n, len - n, "ss1=%#x\n", p->ss1);
	list_for_each_entry(card, &cards, node) {
		if (n >= len)
			break;
		n += scnprintf(buf + n, len - n,
			       "pci=%s device=%04x confidence=%s family=%s disposition=%s result=%d name=%s\n",
			       pci_name(card->device.pdev), card->device.recipe->device,
			       gu_confidence_name(card->device.recipe->confidence),
			       card->device.recipe->family->name,
			       card->disposition ? card->disposition : "unknown",
			       card->result, card->device.recipe->name);
	}
	mutex_unlock(&cards_lock);
	return n;
}
static struct kobj_attribute status_attr = __ATTR_RO(status);

static struct attribute *gu_attrs[] = {
	&status_attr.attr,
	NULL,
};
static const struct attribute_group gu_group = {
	.attrs = gu_attrs,
};

static void publish_status(void)
{
	int ret;

	gu_kobj = kobject_create_and_add("gpu_unlock", kernel_kobj);
	if (!gu_kobj) {
		pr_warn("gpu_unlock: status file was not created\n");
		return;
	}
	ret = sysfs_create_group(gu_kobj, &gu_group);
	if (ret) {
		kobject_put(gu_kobj);
		gu_kobj = NULL;
		pr_warn("gpu_unlock: status file was not created (%d)\n", ret);
	}
}

static int __init gpu_unlock_init(void)
{
	struct pci_dev *pdev = NULL;
	struct card *card;
	const struct gu_card *recipe;
	const struct gu_policy *policy;
	bool all, enumerated = true;
	int err;

	/* Loaded ahead of nvidia on every boot; the command line is the opt-in. */
	if (!targets || !*targets)
		return 0;
	err = gu_policy_parse(rate, ss0, ss1, rewrite, dry_run, experimental);
	if (err)
		return err;
	policy = gu_policy();
	note_guest();
	if (policy->dry_run)
		pr_info("gpu_unlock: dry run, no registers will be written\n");
	else if (!policy->apply && !policy->rewrite)
		pr_info("gpu_unlock: rate=stock, no registers will be written. A previous unlock survives FLR; power-cycle the GPU, or boot once with rewrite=1, to restore the power-on selectors.\n");
	else if (!policy->apply && policy->rewrite)
		pr_info("gpu_unlock: rate=stock rewrite=1, the pre-driver sequence will store the documented power-on selectors\n");

	all = !strcmp(targets, "all");
	while ((pdev = next_supported(pdev, &recipe))) {
		const char *why = "pending";

		if (!all && !listed(pci_name(pdev)))
			continue;
		card = kzalloc(sizeof(*card), GFP_KERNEL);
		if (!card) {
			pci_err(pdev, "gpu_unlock: card allocation failed\n");
			enumerated = false;
			pci_dev_put(pdev);
			break;
		}
		card->device.pdev = pci_dev_get(pdev);
		card->device.recipe = recipe;
		if (pdev->is_virtfn)
			why = "skipped-vgpu";
		else if (!policy->allow_experimental &&
			 recipe->confidence == GU_EXPERIMENTAL)
			why = "skipped-experimental";
		else if (policy->dry_run)
			why = "dry-run";
		else if (!policy->apply && !policy->rewrite)
			why = "stock";
		card->disposition = why;
		list_add_tail(&card->node, &cards);
		pci_info(pdev, "gpu_unlock: %s [%s] %s\n",
			 recipe->name, gu_confidence_name(recipe->confidence), why);
		if (!strcmp(why, "skipped-vgpu"))
			pci_info(pdev, "gpu_unlock: virtual function refused\n");
	}
	if (!all && enumerated)
		report_unmatched();
	/* nvidia loads once this returns: every card must be finished by then. */
	if (transaction_wanted())
		unlock_cards(unlock_one, false);
	if (any_unlocked()) {
		register_pm_notifier(&pm_nb);
		pm_registered = true;
	}
	publish_status();
	return 0;
}

static void __exit gpu_unlock_exit(void)
{
	struct card *card, *next;

	if (gu_kobj) {
		sysfs_remove_group(gu_kobj, &gu_group);
		kobject_put(gu_kobj);
		gu_kobj = NULL;
	}
	if (pm_registered)
		unregister_pm_notifier(&pm_nb);
	list_for_each_entry_safe(card, next, &cards, node)
		drop_card(card);
}

module_init(gpu_unlock_init);
module_exit(gpu_unlock_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Pre-driver GeForce tensor-rate unlock");
MODULE_VERSION("2.1.0");
