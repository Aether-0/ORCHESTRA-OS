/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Compatibility build name.
 *
 * There must be only one sched_ext implementation contract in the tree.  The
 * former Stage 6 body used partial switching, PID-only state, unchecked CPU
 * reuse, and a RUN/YIELD-only action subset.  Building this historical name
 * now compiles the canonical remediated scheduler instead.
 */
#include "orchestra_scx_stage7.bpf.c"
