// SPDX-License-Identifier: GPL-2.0-only
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/string.h>

#include "policy.h"
#include "registers.h"

static struct gu_policy policy = {
	.ss0 = GU_SS0_UNLOCK,
	.ss1 = GU_SS1_UNLOCK,
	.apply = true,
	.allow_experimental = true,
};

const struct gu_policy *gu_policy(void)
{
	return &policy;
}

/* Documented SS field encodings. 0x2/0x3 (quarter and eighth) are unconfirmed
 * in docs/How Ampere was unlocked.md and are rejected. 0x4..0x7 and 0xa..0xf
 * set reserved selector bits. */
static bool nibble_allowed(u32 nibble)
{
	switch (nibble) {
	case 0x0:
	case 0x1:
	case 0x8:
	case 0x9:
		return true;
	default:
		return false;
	}
}

static bool selector_ok(u32 value, unsigned int nibbles)
{
	unsigned int i;

	if (nibbles < 8 && (value >> (nibbles * 4)))
		return false;
	for (i = 0; i < nibbles; i++) {
		if (!nibble_allowed((value >> (i * 4)) & 0xfu))
			return false;
	}
	return true;
}

static int parse_selector(const char *text, u32 *out, unsigned int nibbles,
			  const char *which)
{
	u32 value;
	int ret;

	ret = kstrtou32(text, 0, &value);
	if (ret) {
		pr_err("gpu_unlock: %s is not a hex value\n", which);
		return ret;
	}
	if (!selector_ok(value, nibbles)) {
		pr_err("gpu_unlock: %s=%#x uses an unconfirmed selector encoding\n",
		       which, value);
		return -EINVAL;
	}
	*out = value;
	return 0;
}

int gu_policy_parse(const char *rate, const char *ss0, const char *ss1,
		    bool rewrite, bool dry_run, bool allow_experimental)
{
	bool custom = ss0 || ss1;
	int ret;

	if (!rate || !*rate)
		rate = "full";
	policy.rewrite = rewrite;
	policy.dry_run = dry_run;
	policy.allow_experimental = allow_experimental;

	if (!strcmp(rate, "full")) {
		policy.apply = true;
		policy.ss0 = GU_SS0_UNLOCK;
		policy.ss1 = GU_SS1_UNLOCK;
	} else if (!strcmp(rate, "stock")) {
		if (custom) {
			pr_err("gpu_unlock: ss0/ss1 overrides require rate=full\n");
			return -EINVAL;
		}
		policy.apply = false;
		policy.ss0 = GU_SS0_STOCK;
		policy.ss1 = GU_SS1_STOCK;
	} else {
		pr_err("gpu_unlock: rate=%s is not full or stock\n", rate);
		return -EINVAL;
	}

	if (custom) {
		if (!ss0 || !ss1) {
			pr_err("gpu_unlock: set both ss0 and ss1, or neither\n");
			return -EINVAL;
		}
		ret = parse_selector(ss0, &policy.ss0, 8, "ss0");
		if (ret)
			return ret;
		ret = parse_selector(ss1, &policy.ss1, 1, "ss1");
		if (ret)
			return ret;
	}
	return 0;
}
