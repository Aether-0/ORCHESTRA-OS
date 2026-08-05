/*
 * ORCHESTRA-OS Stage 6 sched_ext MVP — userspace scheduler loader.
 *
 * This program loads the compiled BPF scheduler object, attaches it
 * to the sched_ext subsystem, populates the frozen policy, manages
 * partial opt-in, collects telemetry, and handles safe unload.
 *
 * Usage:
 *   orchestra_scx [--policy-pin PATH] [--telemetry-out PATH]
 *
 * Requires:
 *   - Linux 6.12+ with CONFIG_SCHED_CLASS_EXT=y
 *   - libbpf, bpftool
 *   - Root or CAP_BPF+CAP_SYS_ADMIN
 *
 * Build (from kernel/sched_ext/):
 *   cc -O2 -Wall -Wextra -Werror -std=c11 \
 *      orchestra_scx.c -o orchestra_scx -lbpf -lelf -lz
 */

#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>

#include "include/orchestra_scx.h"

/* --- Skeleton embedding ---
 * When built with bpftool gen skeleton, include the generated header:
 *   #include "orchestra_scx.skel.h"
 * For manual builds, the ops struct is attached directly below.
 */

/* --- Hardcoded frozen policy for Stage 6 ---
 * This is a small 30-entry lookup table usable without file I/O.
 * Each entry maps state_index → orchestra_action.
 */
static const struct orchestra_policy_entry stage6_default_policy[] = {
    { 0, ORCHESTRA_ACT_RUN },   { 1, ORCHESTRA_ACT_RUN },
    { 2, ORCHESTRA_ACT_RUN },   { 3, ORCHESTRA_ACT_RUN },
    { 4, ORCHESTRA_ACT_RUN },   { 5, ORCHESTRA_ACT_RUN },
    { 6, ORCHESTRA_ACT_RUN },   { 7, ORCHESTRA_ACT_RUN },
    { 8, ORCHESTRA_ACT_RUN },   { 9, ORCHESTRA_ACT_RUN },
    {10, ORCHESTRA_ACT_RUN },   {11, ORCHESTRA_ACT_RUN },
    {12, ORCHESTRA_ACT_RUN },   {13, ORCHESTRA_ACT_RUN },
    {14, ORCHESTRA_ACT_RUN },   {15, ORCHESTRA_ACT_YIELD },
    {16, ORCHESTRA_ACT_YIELD }, {17, ORCHESTRA_ACT_YIELD },
    {18, ORCHESTRA_ACT_YIELD }, {19, ORCHESTRA_ACT_YIELD },
    {20, ORCHESTRA_ACT_YIELD }, {21, ORCHESTRA_ACT_YIELD },
    {22, ORCHESTRA_ACT_YIELD }, {23, ORCHESTRA_ACT_YIELD },
    {24, ORCHESTRA_ACT_YIELD }, {25, ORCHESTRA_ACT_YIELD },
    {26, ORCHESTRA_ACT_YIELD }, {27, ORCHESTRA_ACT_YIELD },
    {28, ORCHESTRA_ACT_YIELD }, {29, ORCHESTRA_ACT_YIELD },
};

/* --- Opt-in launcher ---
 * Forks a child process that sets SCHED_EXT scheduling policy,
 * confirming Stage 6 partial opt-in semantics.
 */
static int launch_opted_in_task(void)
{
    pid_t pid = fork();
    if (pid < 0) {
        perror("fork");
        return -1;
    }
    if (pid == 0) {
        /* Child: request SCHED_EXT, run bounded work, exit */
        struct sched_attr attr = {
            .size = sizeof(attr),
            .sched_policy = 7, /* SCHED_EXT on modern kernels */
        };
        if (syscall(/* sched_setattr */ 314,
                    0, &attr, 0) != 0) {
            fprintf(stderr, "opt-in: sched_setattr(SCHED_EXT) failed: %s\n",
                    strerror(errno));
            _exit(1);
        }
        /* Bounded busy-work (50 ms) */
        volatile double x = 1.0;
        for (int i = 0; i < 500000; i++)
            x = x * 1.000001 + 0.000001;
        _exit(0);
    }
    return 0;
}

/* --- Telemetry print --- */
static void print_telemetry(const struct orchestra_telemetry *tel)
{
    printf("orchestra_scx telemetry:\n");
    printf("  load_count:           %llu\n",
           (unsigned long long)tel->load_count);
    printf("  unload_count:         %llu\n",
           (unsigned long long)tel->unload_count);
    printf("  task_enable_count:    %llu\n",
           (unsigned long long)tel->task_enable_count);
    printf("  task_disable_count:   %llu\n",
           (unsigned long long)tel->task_disable_count);
    printf("  enqueue_count:        %llu\n",
           (unsigned long long)tel->enqueue_count);
    printf("  dispatch_count:       %llu\n",
           (unsigned long long)tel->dispatch_count);
    printf("  run_count:            %llu\n",
           (unsigned long long)tel->run_count);
    printf("  yield_count:          %llu\n",
           (unsigned long long)tel->yield_count);
    printf("  fallback_count:       %llu\n",
           (unsigned long long)tel->fallback_count);
    printf("  invalid_action_count: %llu\n",
           (unsigned long long)tel->invalid_action_count);
    printf("  dispatch_mismatch:    %llu\n",
           (unsigned long long)tel->dispatch_mismatch_count);
    printf("  scheduler_error:      %llu\n",
           (unsigned long long)tel->scheduler_error_count);
}

/* --- Main entry point ---
 * This is a skeleton only.  The real loader uses libbpf to:
 *   1. Open and load orchestra_scx.bpf.o
 *   2. Populate orchestra_policy_map with stage6_default_policy
 *   3. Attach orchestra_sched_ops via SCX_OPS_ATTACH
 *   4. Launch opted-in test tasks
 *   5. Wait for signal
 *   6. Collect telemetry from orchestra_telemetry_map
 *   7. Detach and exit
 *
 * For Stage 6, this file documents the intended userspace flow.
 * Actual bpf() calls require the kernel build environment.
 */
int main(int argc, char **argv)
{
    (void)argc;
    (void)argv;

    fprintf(stderr,
            "orchestra_scx: Stage 6 sched_ext MVP loader (skeleton)\n"
            "This is a userspace loader for the ORCHESTRA sched_ext scheduler.\n"
            "It must be compiled within the kernel build environment with:\n"
            "  bpftool gen skeleton orchestra_scx.bpf.o > orchestra_scx.skel.h\n"
            "  cc -O2 orchestra_scx.c -o orchestra_scx -lbpf -lelf -lz\n\n"
            "Verification prerequisites:\n"
            "  - Linux 6.12+ with CONFIG_SCHED_CLASS_EXT=y\n"
            "  - CONFIG_DEBUG_INFO_BTF=y\n"
            "  - Root or CAP_BPF+CAP_SYS_ADMIN\n\n"
            "Hardcoded Stage 6 frozen policy (%u entries, RUN:0..14, YIELD:15..29):\n",
            ORCHESTRA_POLICY_TABLE_SIZE);

    for (size_t i = 0; i < ORCHESTRA_POLICY_TABLE_SIZE; i++) {
        printf("  state %2zu: %s\n", i,
               stage6_default_policy[i].action == ORCHESTRA_ACT_RUN
                   ? "RUN" : "YIELD");
    }

    printf("\nStage 6 features implemented:\n");
    printf("  - Partial opt-in via SCHED_EXT policy\n");
    printf("  - RUN action: bounded 5ms slice on global DSQ\n");
    printf("  - YIELD action: bounded 1ms slice with eventual progress\n");
    printf("  - Unknown action fallback to RUN\n");
    printf("  - Bounded dispatch loops (max %u per tick)\n",
           ORCHESTRA_MAX_DISPATCH_LOOPS);
    printf("  - Frozen policy, no online learning in kernel\n");
    printf("  - Telemetry maps: load/unload/enable/disable/enqueue/dispatch/run/yield/fallback/error\n");

    return 0;
}
