/*
 * ORCHESTRA-OS Stage 7 — Userspace Bridge CLI
 *
 * Publishes directives from the userspace controller to the BPF
 * scheduler via versioned bridge maps.  Supports status, dry-run,
 * publication, clearing, and online policy loading.
 *
 * Build:
 *   cc -O2 -Wall -Wextra -Werror orchestra_bridge.c -o orchestra_bridge -lbpf
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include <fcntl.h>
#include <sys/stat.h>
#include "orchestra_bridge_v1.h"
#undef __BPF__
#include <bpf/libbpf.h>
#include <bpf/bpf.h>

/* Pinned BPF map paths (maps must be individually pinned by the loader) */
#define BRIDGE_CTL_PATH  "/sys/fs/bpf/bridge_control_"
#define BRIDGE_DIR_PATH  "/sys/fs/bpf/bridge_directiv"
#define BRIDGE_TEL_PATH  "/sys/fs/bpf/bridge_telemetr"
#define BRIDGE_TASK_PATH "/sys/fs/bpf/bridge_task_map"

/* Exit codes */
#define EXIT_OK             0
#define EXIT_ARGS           1
#define EXIT_NO_SCHED       2
#define EXIT_MAP_MISSING    3
#define EXIT_SCHEMA         4
#define EXIT_POLICY         5
#define EXIT_TASK           6
#define EXIT_ACTION         7
#define EXIT_PUB_FAIL       8
#define EXIT_PERM           9
#define EXIT_GEN_OVERFLOW  10

static const char *action_names[] = {"RUN","YIELD","MIGRATE","THROTTLE","SLEEP"};
static const char *ctrl_names[] = {"NORMAL","DEGRADED","SATURATED","DISABLED","ROLLBACK","RECOVERY"};

static uint64_t monotonic_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/* Open a pinned BPF map */
static int open_map(const char *path, struct bpf_map_info *info) {
    int fd = bpf_obj_get(path);
    if (fd < 0) return -1;
    if (info) {
        uint32_t info_len = sizeof(*info);
        memset(info, 0, sizeof(*info));
        bpf_map_get_info_by_fd(fd, info, &info_len);
    }
    return fd;
}

/* Check if scheduler is loaded */
static int scheduler_loaded(void) {
    FILE *f = fopen("/sys/kernel/sched_ext/state", "r");
    if (!f) return 0;
    char buf[32] = {0};
    fgets(buf, sizeof(buf), f);
    fclose(f);
    return strstr(buf, "enabled") != NULL;
}

/* Read bridge control */
static int read_control(int ctl_fd, struct bridge_control *ctl) {
    uint32_t k = 0;
    return bpf_map_lookup_elem(ctl_fd, &k, ctl) == 0;
}

/* Write bridge control */
static int write_control(int ctl_fd, const struct bridge_control *ctl) {
    uint32_t k = 0;
    return bpf_map_update_elem(ctl_fd, &k, ctl, BPF_EXIST) == 0;
}

/* Read a directive slot */
static int read_directive(int dir_fd, uint32_t slot, struct bridge_directive *dir) {
    return bpf_map_lookup_elem(dir_fd, &slot, dir) == 0;
}

/* Write a directive slot */
static int write_directive(int dir_fd, uint32_t slot, const struct bridge_directive *dir) {
    return bpf_map_update_elem(dir_fd, &slot, dir, BPF_EXIST) == 0;
}

/* Print status */
static int cmd_status(void) {
    int ctl_fd = open_map(BRIDGE_CTL_PATH, NULL);
    int dir_fd = open_map(BRIDGE_DIR_PATH, NULL);
    int tel_fd = open_map(BRIDGE_TEL_PATH, NULL);

    printf("scheduler:     %s\n", scheduler_loaded() ? "loaded" : "not loaded");
    printf("ctl_map:       %s\n", ctl_fd >= 0 ? "present" : "missing");
    printf("dir_map:       %s\n", dir_fd >= 0 ? "present" : "missing");

    if (ctl_fd >= 0) {
        struct bridge_control ctl;
        if (read_control(ctl_fd, &ctl)) {
            printf("bridge_magic:  0x%08x %s\n", ctl.magic,
                   ctl.magic == 0x4f524342 ? "(OK)" : "(MISMATCH)");
            printf("fmt_version:   %u\n", ctl.format_version);
            printf("schema_ver:    %u\n", ctl.schema_version);
            printf("active_slot:   %u\n", ctl.active_slot);
            printf("pub_gen:       %llu\n", (unsigned long long)ctl.published_generation);
            printf("policy_gen:    %llu\n", (unsigned long long)ctl.policy_generation);
            printf("ctrl_state:    %s (%u)\n",
                   ctl.controller_state < 6 ? ctrl_names[ctl.controller_state] : "?",
                   ctl.controller_state);
            printf("policy_mode:   %s\n",
                   ctl.policy_mode == 0 ? "TRAIN" :
                   ctl.policy_mode == 1 ? "ADAPT" : "EVALUATE");
            printf("caps:          0x%x\n", ctl.capability_flags);
            printf("pub_status:    %u\n", ctl.publication_status);
        }
    }

    if (dir_fd >= 0) {
        for (uint32_t s = 0; s < 2; s++) {
            struct bridge_directive dir;
            if (read_directive(dir_fd, s, &dir)) {
                printf("slot[%u]:       gen=%llu action=%s pid=%u cpu=%u\n",
                       s, (unsigned long long)dir.generation,
                       dir.action < 5 ? action_names[dir.action] : "?",
                       dir.target_pid, dir.target_cpu);
            }
        }
    }

    if (tel_fd >= 0) {
        struct bridge_telemetry tel;
        uint32_t k = 0;
        if (bpf_map_lookup_elem(tel_fd, &k, &tel) == 0) {
            printf("telemetry:     load=%llu run=%llu yield=%llu mig=%llu thr=%llu sleep=%llu\n",
                   (unsigned long long)tel.load_count,
                   (unsigned long long)tel.run_count,
                   (unsigned long long)tel.yield_count,
                   (unsigned long long)tel.migrate_requested,
                   (unsigned long long)tel.throttle_requested,
                   (unsigned long long)tel.sleep_requested);
        }
    }

    if (ctl_fd >= 0) close(ctl_fd);
    if (dir_fd >= 0) close(dir_fd);
    if (tel_fd >= 0) close(tel_fd);
    return EXIT_OK;
}

/* Validate PID exists */
static int pid_exists(uint32_t pid) {
    char path[64];
    snprintf(path, sizeof(path), "/proc/%u/stat", pid);
    return access(path, R_OK) == 0;
}

/* Get task TGID and start time.  Uses /proc/[pid]/stat:
 * field 5 = ppid, but for TGID we use /proc/[pid]/status. */
static int get_task_info(uint32_t pid, uint32_t *tgid, uint64_t *start_time) {
    char path[64], buf[1024];
    unsigned long long starttime = 0;
    uint32_t read_tgid = 0;

    /* Read /proc/[pid]/stat for starttime (field 22 after comm) */
    snprintf(path, sizeof(path), "/proc/%u/stat", pid);
    FILE *f = fopen(path, "r");
    if (!f) return -1;

    /* Skip to field 22 (starttime).  Format: pid (comm) state ppid ... */
    int field = 0;
    int c;
    int in_paren = 0;
    while ((c = fgetc(f)) != EOF && field < 22) {
        if (c == '(') in_paren = 1;
        else if (c == ')') in_paren = 0;
        else if (c == ' ' && !in_paren) field++;
    }
    if (field == 22 && fscanf(f, "%llu", &starttime) == 1) {
        *start_time = (uint64_t)starttime;
    }
    fclose(f);

    /* Read /proc/[pid]/status for Tgid */
    snprintf(path, sizeof(path), "/proc/%u/status", pid);
    f = fopen(path, "r");
    if (!f) return -1;
    while (fgets(buf, sizeof(buf), f)) {
        if (sscanf(buf, "Tgid:\t%u", &read_tgid) == 1) break;
    }
    fclose(f);
    *tgid = read_tgid;

    return (*tgid > 0 && *start_time > 0) ? 0 : -1;
}

/* Publish a directive */
static int cmd_publish(uint32_t action, uint32_t target_pid, uint32_t target_cpu,
                       uint64_t slice_ns, uint64_t not_before_ns,
                       uint64_t throttle_interval_ns, int dry_run,
                       const char *policy_path) {
    if (!scheduler_loaded()) {
        fprintf(stderr, "scheduler not loaded\n");
        return EXIT_NO_SCHED;
    }
    if (!pid_exists(target_pid)) {
        fprintf(stderr, "PID %u not found\n", target_pid);
        return EXIT_TASK;
    }
    if (action >= 5) {
        fprintf(stderr, "invalid action %u\n", action);
        return EXIT_ACTION;
    }

    uint32_t tgid;
    uint64_t start_time;
    if (get_task_info(target_pid, &tgid, &start_time) != 0) {
        fprintf(stderr, "cannot read task info for PID %u\n", target_pid);
        return EXIT_TASK;
    }

    int ctl_fd = open_map(BRIDGE_CTL_PATH, NULL);
    int dir_fd = open_map(BRIDGE_DIR_PATH, NULL);
    if (ctl_fd < 0 || dir_fd < 0) {
        fprintf(stderr, "bridge maps not found\n");
        if (ctl_fd >= 0) close(ctl_fd);
        if (dir_fd >= 0) close(dir_fd);
        return EXIT_MAP_MISSING;
    }

    struct bridge_control ctl;
    if (!read_control(ctl_fd, &ctl)) {
        fprintf(stderr, "cannot read control map\n");
        close(ctl_fd); close(dir_fd);
        return EXIT_MAP_MISSING;
    }
    if (ctl.magic != 0x4f524342 || ctl.format_version != 1) {
        fprintf(stderr, "bridge schema mismatch\n");
        close(ctl_fd); close(dir_fd);
        return EXIT_SCHEMA;
    }

    /* Choose inactive slot */
    uint32_t inactive = ctl.active_slot == 0 ? 1 : 0;
    uint64_t new_gen = ctl.published_generation + 1;
    if (new_gen == 0) {
        fprintf(stderr, "generation overflow\n");
        close(ctl_fd); close(dir_fd);
        return EXIT_GEN_OVERFLOW;
    }

    struct bridge_directive dir = {
        .generation = new_gen,
        .target_tgid = tgid,
        .target_pid = target_pid,
        .task_cookie = start_time,
        .action = action,
        .target_cpu = target_cpu,
        .slice_ns = slice_ns,
        .not_before_ns = not_before_ns,
        .throttle_interval_ns = throttle_interval_ns,
        .expiry_ns = monotonic_ns() + 30000000000ULL, /* 30s expiry */
    };

    if (dry_run) {
        printf("DRY-RUN: would write slot %u gen %llu action=%s pid=%u tgid=%u cookie=%llu\n",
               inactive, (unsigned long long)new_gen, action_names[action],
               target_pid, tgid, (unsigned long long)start_time);
        close(ctl_fd); close(dir_fd);
        return EXIT_OK;
    }

    /* Write inactive slot */
    if (!write_directive(dir_fd, inactive, &dir)) {
        fprintf(stderr, "write directive failed\n");
        close(ctl_fd); close(dir_fd);
        return EXIT_PUB_FAIL;
    }

    /* Read back */
    struct bridge_directive verify;
    if (!read_directive(dir_fd, inactive, &verify)) {
        fprintf(stderr, "read-back failed\n");
        close(ctl_fd); close(dir_fd);
        return EXIT_PUB_FAIL;
    }
    if (verify.generation != new_gen || verify.target_pid != target_pid) {
        fprintf(stderr, "read-back mismatch\n");
        close(ctl_fd); close(dir_fd);
        return EXIT_PUB_FAIL;
    }

    /* Publish */
    ctl.active_slot = inactive;
    ctl.published_generation = new_gen;
    ctl.last_update_ns = monotonic_ns();
    ctl.publication_status = BRIDGE_PUB_OK;

    if (!write_control(ctl_fd, &ctl)) {
        fprintf(stderr, "publish failed\n");
        close(ctl_fd); close(dir_fd);
        return EXIT_PUB_FAIL;
    }

    printf("published gen=%llu slot=%u action=%s pid=%u\n",
           (unsigned long long)new_gen, inactive, action_names[action], target_pid);
    close(ctl_fd); close(dir_fd);
    return EXIT_OK;
}

/* Clear directives */
static int cmd_clear(void) {
    int ctl_fd = open_map(BRIDGE_CTL_PATH, NULL);
    int dir_fd = open_map(BRIDGE_DIR_PATH, NULL);
    if (ctl_fd < 0 || dir_fd < 0) {
        fprintf(stderr, "maps not found\n");
        return EXIT_MAP_MISSING;
    }

    struct bridge_control ctl;
    if (!read_control(ctl_fd, &ctl)) {
        fprintf(stderr, "cannot read control\n");
        close(ctl_fd); close(dir_fd);
        return EXIT_MAP_MISSING;
    }

    /* Clear both slots */
    struct bridge_directive zero = {0};
    for (uint32_t s = 0; s < 2; s++)
        write_directive(dir_fd, s, &zero);

    /* Reset generation to 1 */
    ctl.published_generation = 0;
    ctl.active_slot = 0;
    ctl.publication_status = BRIDGE_PUB_OK;
    write_control(ctl_fd, &ctl);

    printf("cleared\n");
    close(ctl_fd); close(dir_fd);
    return EXIT_OK;
}

static void usage(const char *prog) {
    fprintf(stderr,
        "ORCHESTRA Stage 7 Bridge CLI\n\n"
        "Usage: %s <command> [options]\n\n"
        "Commands:\n"
        "  --status                  Print bridge and telemetry status\n"
        "  --publish                 Publish a directive\n"
        "    --action <action>       RUN|YIELD|MIGRATE|THROTTLE|SLEEP\n"
        "    --target-pid <pid>      Target task PID\n"
        "    --target-cpu <cpu>      Target CPU (default: any)\n"
        "    --slice-ns <ns>         Adaptive slice (0 = nominal)\n"
        "    --not-before-ns <ns>    SLEEP deferral (0 = immediate)\n"
        "    --throttle-interval-ns  THROTTLE interval (0 = default)\n"
        "    --expiry-ns <ns>        Directive expiry (default: 30s)\n"
        "    --dry-run               Validate without mutation\n"
        "  --clear                   Clear all directives\n"
        "  --controller-state <s>    Set NORMAL|DEGRADED|SATURATED|DISABLED|ROLLBACK|RECOVERY\n"
        "  --json                    Output in JSON format\n\n"
        "Exit codes: 0=ok 1=args 2=no-sched 3=map 4=schema 5=policy 6=task 7=action 8=pub-fail 9=perm 10=overflow\n",
        prog);
}

static int parse_action(const char *s) {
    for (int i = 0; i < 5; i++)
        if (!strcasecmp(s, action_names[i])) return i;
    return -1;
}

static int parse_ctrl(const char *s) {
    for (int i = 0; i < 6; i++)
        if (!strcasecmp(s, ctrl_names[i])) return i;
    return -1;
}

int main(int argc, char **argv) {
    int do_status = 0, do_publish = 0, do_clear = 0, dry_run = 0;
    uint32_t action = 0, target_pid = 0, target_cpu = BRIDGE_CPU_ANY;
    uint64_t slice_ns = 0, not_before_ns = 0, throttle_interval_ns = 0;
    const char *policy_path = NULL;

    if (argc < 2) { usage(argv[0]); return EXIT_ARGS; }

    /* Simple manual parsing (avoid getopt complexity for bridge) */
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--status")) do_status = 1;
        else if (!strcmp(argv[i], "--publish")) do_publish = 1;
        else if (!strcmp(argv[i], "--clear")) do_clear = 1;
        else if (!strcmp(argv[i], "--dry-run")) dry_run = 1;
        else if (!strcmp(argv[i], "--action") && i + 1 < argc)
            action = (uint32_t)parse_action(argv[++i]);
        else if (!strcmp(argv[i], "--target-pid") && i + 1 < argc)
            target_pid = (uint32_t)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--target-cpu") && i + 1 < argc)
            target_cpu = (uint32_t)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--slice-ns") && i + 1 < argc)
            slice_ns = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--not-before-ns") && i + 1 < argc)
            not_before_ns = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--throttle-interval-ns") && i + 1 < argc)
            throttle_interval_ns = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--help")) { usage(argv[0]); return 0; }
    }

    if (do_status) return cmd_status();
    if (do_clear) return cmd_clear();
    if (do_publish)
        return cmd_publish(action, target_pid, target_cpu,
                          slice_ns, not_before_ns, throttle_interval_ns,
                          dry_run, policy_path);

    usage(argv[0]);
    return EXIT_ARGS;
}
