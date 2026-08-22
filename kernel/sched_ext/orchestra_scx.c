/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Retired compatibility entry point.
 *
 * The historical loader hard-coded a syscall number and changed a child to
 * SCHED_EXT while advertising an implementation it did not actually attach.
 * Privileged map publication is now exclusively implemented by
 * bridge/orchestra_bridge.c, which validates the ABI and exact map schema.
 */
#include <stdio.h>

int main(void)
{
    fputs("orchestra_scx: retired unsafe loader; use bridge/orchestra_bridge "
          "with the kernel-ABI-v8 scheduler object\n", stderr);
    return 2;
}
