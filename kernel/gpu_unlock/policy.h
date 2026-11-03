/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GPU_UNLOCK_POLICY_H
#define GPU_UNLOCK_POLICY_H

#include <linux/types.h>

/* Selector preset chosen at module load. apply is false for rate=stock,
 * which leaves the card alone unless rewrite is also set. dry_run never
 * writes. ss0/ss1 are the values a transaction will store and then require
 * to survive FLR. */
struct gu_policy {
	u32 ss0;
	u32 ss1;
	bool apply;
	bool rewrite;
	bool dry_run;
	bool allow_experimental;
};

int gu_policy_parse(const char *rate, const char *ss0, const char *ss1,
		    bool rewrite, bool dry_run, bool allow_experimental);
const struct gu_policy *gu_policy(void);

#endif
