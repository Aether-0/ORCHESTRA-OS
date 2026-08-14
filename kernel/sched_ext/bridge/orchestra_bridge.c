/* SPDX-License-Identifier: GPL-2.0 */
/*
 * ORCHESTRA-OS privileged sched_ext bridge, ABI v2.
 *
 * The bridge uses raw bpf(2) operations so its safety checks do not depend on
 * a particular libbpf helper version.  Writers serialize with flock(2), map
 * values are published/read with BPF_F_LOCK, and map IDs are pinned only when
 * the operator supplies every exact ID.  There is no global prefix scan.
 */
#define _GNU_SOURCE
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <linux/bpf.h>
#include <sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#include "orchestra_bridge_v1.h"

#define BRIDGE_PIN_DIR       "/sys/fs/bpf/orchestra"
#define BRIDGE_CTL_PATH      BRIDGE_PIN_DIR "/" BRIDGE_CTL_MAP_NAME
#define BRIDGE_DIR_PATH      BRIDGE_PIN_DIR "/" BRIDGE_DIR_MAP_NAME
#define BRIDGE_ID_PATH       BRIDGE_PIN_DIR "/" BRIDGE_ID_MAP_NAME
#define BRIDGE_TASK_PATH     BRIDGE_PIN_DIR "/" BRIDGE_TASK_MAP_NAME
#define BRIDGE_TASK_TEL_PATH BRIDGE_PIN_DIR "/" BRIDGE_TASK_TEL_MAP_NAME
#define BRIDGE_TEL_PATH      BRIDGE_PIN_DIR "/" BRIDGE_TEL_MAP_NAME
#define BRIDGE_DEFER_PATH    BRIDGE_PIN_DIR "/" BRIDGE_DEFER_MAP_NAME
#define BRIDGE_LOCK_PATH     "/run/lock/orchestra_bridge.lock"
#define BRIDGE_OPS_NAME      "orchestra_scx_stage7"
#define DEFAULT_EXPIRY_NS    UINT64_C(30000000000)
#define DEFAULT_LEASE_NS     UINT64_C(30000000000)

enum exit_code {
    EXIT_OK = 0,
    EXIT_ARGS = 1,
    EXIT_NO_SCHED = 2,
    EXIT_MAP_MISSING = 3,
    EXIT_SCHEMA = 4,
    EXIT_POLICY = 5,
    EXIT_TASK = 6,
    EXIT_ACTION = 7,
    EXIT_PUB_FAIL = 8,
    EXIT_PERM = 9,
    EXIT_GEN_OVERFLOW = 10
};

enum map_role {
    MAP_CONTROL,
    MAP_DIRECTIVE,
    MAP_IDENTITY,
    MAP_TASK_STATE,
    MAP_TASK_TELEMETRY,
    MAP_TELEMETRY,
    MAP_DEFER_TIMER,
    MAP_ROLE_COUNT
};

struct map_spec {
    const char *name;
    const char *path;
    enum bpf_map_type type;
    uint32_t key_size;
    uint32_t value_size;
    uint32_t max_entries;
};

static const struct map_spec map_specs[MAP_ROLE_COUNT] = {
    [MAP_CONTROL] = { BRIDGE_CTL_MAP_NAME, BRIDGE_CTL_PATH,
        BPF_MAP_TYPE_ARRAY, sizeof(uint32_t), sizeof(struct bridge_control), 1 },
    [MAP_DIRECTIVE] = { BRIDGE_DIR_MAP_NAME, BRIDGE_DIR_PATH,
        BPF_MAP_TYPE_HASH, sizeof(struct orchestra_task_identity),
        sizeof(struct bridge_directive), BRIDGE_MAX_TASKS },
    [MAP_IDENTITY] = { BRIDGE_ID_MAP_NAME, BRIDGE_ID_PATH,
        BPF_MAP_TYPE_HASH, sizeof(struct orchestra_pid_key),
        sizeof(struct bridge_identity_record), BRIDGE_MAX_TASKS },
    [MAP_TASK_STATE] = { BRIDGE_TASK_MAP_NAME, BRIDGE_TASK_PATH,
        BPF_MAP_TYPE_HASH, sizeof(struct orchestra_task_identity),
        sizeof(struct bridge_task_state), BRIDGE_MAX_TASKS },
    [MAP_TASK_TELEMETRY] = { BRIDGE_TASK_TEL_MAP_NAME, BRIDGE_TASK_TEL_PATH,
        BPF_MAP_TYPE_HASH, sizeof(struct orchestra_task_identity),
        sizeof(struct bridge_task_telemetry), BRIDGE_MAX_TASKS },
    [MAP_TELEMETRY] = { BRIDGE_TEL_MAP_NAME, BRIDGE_TEL_PATH,
        BPF_MAP_TYPE_ARRAY, sizeof(uint32_t),
        sizeof(struct bridge_telemetry), 1 },
    [MAP_DEFER_TIMER] = { BRIDGE_DEFER_MAP_NAME, BRIDGE_DEFER_PATH,
        BPF_MAP_TYPE_ARRAY, sizeof(uint32_t),
        sizeof(struct bridge_defer_timer), 1 }
};

struct map_set {
    int fd[MAP_ROLE_COUNT];
};

struct task_proc_info {
    uint32_t tgid;
    uint64_t start_ticks;
};

struct options {
    bool status;
    bool publish;
    bool clear;
    bool opt_in;
    bool pin_maps;
    bool stream;
    bool dry_run;
    bool quiet;
    bool target_set;
    enum orchestra_action_id action;
    bool action_set;
    uint32_t target_tid;
    uint32_t target_cpu;
    uint64_t slice_ns;
    uint64_t not_before_ns;
    uint64_t throttle_period_ns;
    uint64_t throttle_budget_ns;
    uint64_t expiry_duration_ns;
    uint64_t lease_ns;
    uint32_t controller_state;
    uint32_t policy_mode;
    uint64_t policy_generation;
    uint32_t map_ids[MAP_ROLE_COUNT];
};

static const char *const action_names[ORCHESTRA_ACTION_COUNT] = {
    [ORCHESTRA_ACTION_RUN] = "RUN",
    [ORCHESTRA_ACTION_SLEEP] = "SLEEP",
    [ORCHESTRA_ACTION_MIGRATE] = "MIGRATE",
    [ORCHESTRA_ACTION_THROTTLE] = "THROTTLE",
    [ORCHESTRA_ACTION_YIELD] = "YIELD"
};

static const char *const controller_names[ORCHESTRA_CTRL_COUNT] = {
    "NORMAL", "DEGRADED", "SATURATED", "DISABLED", "ROLLBACK", "RECOVERY"
};

static int bpf_call(enum bpf_cmd cmd, union bpf_attr *attr)
{
    return (int)syscall(__NR_bpf, cmd, attr, sizeof(*attr));
}

static int bpf_obj_get_raw(const char *path)
{
    union bpf_attr attr;

    memset(&attr, 0, sizeof(attr));
    attr.pathname = (uint64_t)(uintptr_t)path;
    return bpf_call(BPF_OBJ_GET, &attr);
}

static int bpf_map_fd_by_id(uint32_t id)
{
    union bpf_attr attr;

    memset(&attr, 0, sizeof(attr));
    attr.map_id = id;
    return bpf_call(BPF_MAP_GET_FD_BY_ID, &attr);
}

static int bpf_obj_pin_raw(int fd, const char *path)
{
    union bpf_attr attr;

    memset(&attr, 0, sizeof(attr));
    attr.pathname = (uint64_t)(uintptr_t)path;
    attr.bpf_fd = (uint32_t)fd;
    return bpf_call(BPF_OBJ_PIN, &attr);
}

static int bpf_info_raw(int fd, struct bpf_map_info *info)
{
    union bpf_attr attr;
    uint32_t len = sizeof(*info);

    memset(info, 0, sizeof(*info));
    memset(&attr, 0, sizeof(attr));
    attr.info.bpf_fd = (uint32_t)fd;
    attr.info.info_len = len;
    attr.info.info = (uint64_t)(uintptr_t)info;
    return bpf_call(BPF_OBJ_GET_INFO_BY_FD, &attr);
}

static int bpf_lookup_raw(int fd, const void *key, void *value, uint64_t flags)
{
    union bpf_attr attr;

    memset(&attr, 0, sizeof(attr));
    attr.map_fd = (uint32_t)fd;
    attr.key = (uint64_t)(uintptr_t)key;
    attr.value = (uint64_t)(uintptr_t)value;
    attr.flags = flags;
    return bpf_call(BPF_MAP_LOOKUP_ELEM, &attr);
}

static int bpf_update_raw(int fd, const void *key, const void *value,
                          uint64_t flags)
{
    union bpf_attr attr;

    memset(&attr, 0, sizeof(attr));
    attr.map_fd = (uint32_t)fd;
    attr.key = (uint64_t)(uintptr_t)key;
    attr.value = (uint64_t)(uintptr_t)value;
    attr.flags = flags;
    return bpf_call(BPF_MAP_UPDATE_ELEM, &attr);
}

static int bpf_delete_raw(int fd, const void *key)
{
    union bpf_attr attr;

    memset(&attr, 0, sizeof(attr));
    attr.map_fd = (uint32_t)fd;
    attr.key = (uint64_t)(uintptr_t)key;
    return bpf_call(BPF_MAP_DELETE_ELEM, &attr);
}

static int bpf_next_key_raw(int fd, const void *key, void *next_key)
{
    union bpf_attr attr;

    memset(&attr, 0, sizeof(attr));
    attr.map_fd = (uint32_t)fd;
    attr.key = (uint64_t)(uintptr_t)key;
    attr.next_key = (uint64_t)(uintptr_t)next_key;
    return bpf_call(BPF_MAP_GET_NEXT_KEY, &attr);
}

static bool checked_add_u64(uint64_t a, uint64_t b, uint64_t *out)
{
    if (UINT64_MAX - a < b)
        return false;
    *out = a + b;
    return true;
}

static bool monotonic_ns(uint64_t *out)
{
    struct timespec ts;

    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0 || ts.tv_sec < 0)
        return false;
    if ((uint64_t)ts.tv_sec > UINT64_MAX / UINT64_C(1000000000))
        return false;
    return checked_add_u64((uint64_t)ts.tv_sec * UINT64_C(1000000000),
                           (uint64_t)ts.tv_nsec, out);
}

static bool parse_u64(const char *text, uint64_t min, uint64_t max,
                      uint64_t *out)
{
    char *end = NULL;
    unsigned long long value;

    if (!text || !*text || isspace((unsigned char)text[0]) || text[0] == '-')
        return false;
    errno = 0;
    value = strtoull(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' || value < min || value > max)
        return false;
    *out = (uint64_t)value;
    return true;
}

static bool parse_u32(const char *text, uint32_t min, uint32_t max,
                      uint32_t *out)
{
    uint64_t value;

    if (!parse_u64(text, min, max, &value))
        return false;
    *out = (uint32_t)value;
    return true;
}

static bool canonical_to_wire(enum orchestra_action_id action, uint32_t *wire)
{
    switch (action) {
    case ORCHESTRA_ACTION_RUN:      *wire = ORCHESTRA_ACTION_RUN; return true;
    case ORCHESTRA_ACTION_SLEEP:    *wire = ORCHESTRA_ACTION_SLEEP; return true;
    case ORCHESTRA_ACTION_MIGRATE:  *wire = ORCHESTRA_ACTION_MIGRATE; return true;
    case ORCHESTRA_ACTION_THROTTLE: *wire = ORCHESTRA_ACTION_THROTTLE; return true;
    case ORCHESTRA_ACTION_YIELD:    *wire = ORCHESTRA_ACTION_YIELD; return true;
    default: return false;
    }
}

static bool parse_action(const char *text, enum orchestra_action_id *action)
{
    uint32_t i;

    for (i = 0; i < ORCHESTRA_ACTION_COUNT; i++) {
        if (action_names[i] && strcasecmp(text, action_names[i]) == 0) {
            *action = (enum orchestra_action_id)i;
            return true;
        }
    }
    return false;
}

static bool parse_controller(const char *text, uint32_t *state)
{
    uint32_t i;

    for (i = 0; i < ORCHESTRA_CTRL_COUNT; i++) {
        if (strcasecmp(text, controller_names[i]) == 0) {
            *state = i;
            return true;
        }
    }
    return false;
}

static void map_set_init(struct map_set *maps)
{
    size_t i;

    for (i = 0; i < MAP_ROLE_COUNT; i++)
        maps->fd[i] = -1;
}

static void map_set_close(struct map_set *maps)
{
    size_t i;

    for (i = 0; i < MAP_ROLE_COUNT; i++) {
        if (maps->fd[i] >= 0) {
            close(maps->fd[i]);
            maps->fd[i] = -1;
        }
    }
}

static bool map_matches(int fd, const struct map_spec *spec,
                        struct bpf_map_info *out)
{
    struct bpf_map_info info;

    if (bpf_info_raw(fd, &info) != 0)
        return false;
    if (strncmp((const char *)info.name, spec->name, BPF_OBJ_NAME_LEN) != 0 ||
        info.type != (uint32_t)spec->type || info.key_size != spec->key_size ||
        info.value_size != spec->value_size ||
        info.max_entries != spec->max_entries)
        return false;
    if (out)
        *out = info;
    return true;
}

static int open_checked(enum map_role role)
{
    int fd = bpf_obj_get_raw(map_specs[role].path);

    if (fd < 0)
        return -1;
    if (!map_matches(fd, &map_specs[role], NULL)) {
        close(fd);
        errno = EPROTO;
        return -1;
    }
    return fd;
}

static bool open_runtime_maps(struct map_set *maps, bool all)
{
    enum map_role last = all ? MAP_ROLE_COUNT : MAP_IDENTITY + 1;
    enum map_role role;

    map_set_init(maps);
    for (role = MAP_CONTROL; role < last; role++) {
        maps->fd[role] = open_checked(role);
        if (maps->fd[role] < 0) {
            map_set_close(maps);
            return false;
        }
    }
    return true;
}

static bool read_control(int fd, struct bridge_control *control)
{
    uint32_t key = 0;

    memset(control, 0, sizeof(*control));
    return bpf_lookup_raw(fd, &key, control, BPF_F_LOCK) == 0;
}

static bool write_control(int fd, const struct bridge_control *control)
{
    uint32_t key = 0;

    return bpf_update_raw(fd, &key, control, BPF_EXIST | BPF_F_LOCK) == 0;
}

static bool valid_control(const struct bridge_control *control)
{
    return control->magic == ORCHESTRA_ABI_MAGIC &&
           control->abi_version == ORCHESTRA_ABI_VERSION &&
           control->value_size == sizeof(*control) &&
           control->scx_api_version == ORCHESTRA_SCX_API_VERSION &&
           control->scheduler_epoch != 0 &&
           (control->capability_flags & BRIDGE_REQUIRED_CAPS) ==
               BRIDGE_REQUIRED_CAPS;
}

static bool read_text_file(const char *path, char *buf, size_t size)
{
    FILE *file;

    if (size == 0)
        return false;
    file = fopen(path, "re");
    if (!file)
        return false;
    if (!fgets(buf, (int)size, file)) {
        fclose(file);
        return false;
    }
    if (fclose(file) != 0)
        return false;
    buf[strcspn(buf, "\r\n")] = '\0';
    return true;
}

static bool scheduler_loaded(void)
{
    char state[32];
    char ops[64];

    return read_text_file("/sys/kernel/sched_ext/state", state, sizeof(state)) &&
           strcmp(state, "enabled") == 0 &&
           read_text_file("/sys/kernel/sched_ext/root/ops", ops, sizeof(ops)) &&
           strcmp(ops, BRIDGE_OPS_NAME) == 0;
}

/* Correctly parses field 22 after the final ')' which terminates comm. */
static bool parse_proc_stat_start(const char *line, uint64_t *start_ticks)
{
    const char *right = strrchr(line, ')');
    char copy[4096];
    char *save = NULL;
    char *token;
    unsigned int field = 3;

    if (!right || right[1] != ' ' || strlen(right + 2) >= sizeof(copy))
        return false;
    strcpy(copy, right + 2);
    for (token = strtok_r(copy, " ", &save); token;
         token = strtok_r(NULL, " ", &save), field++) {
        if (field == 22)
            return parse_u64(token, 1, UINT64_MAX, start_ticks);
    }
    return false;
}

static bool get_task_proc_info(uint32_t tid, struct task_proc_info *info)
{
    char path[64];
    char line[4096];
    FILE *file;
    uint32_t tgid = 0;

    if (snprintf(path, sizeof(path), "/proc/%" PRIu32 "/stat", tid) < 0)
        return false;
    file = fopen(path, "re");
    if (!file)
        return false;
    if (!fgets(line, sizeof(line), file) || !parse_proc_stat_start(line, &info->start_ticks)) {
        fclose(file);
        return false;
    }
    if (fclose(file) != 0)
        return false;

    if (snprintf(path, sizeof(path), "/proc/%" PRIu32 "/status", tid) < 0)
        return false;
    file = fopen(path, "re");
    if (!file)
        return false;
    while (fgets(line, sizeof(line), file)) {
        if (strncmp(line, "Tgid:", 5) == 0) {
            char *text = line + 5;
            char *end;
            unsigned long value;

            errno = 0;
            value = strtoul(text, &end, 10);
            while (*end && isspace((unsigned char)*end))
                end++;
            if (errno == 0 && value > 0 && value <= UINT32_MAX && *end == '\0')
                tgid = (uint32_t)value;
            break;
        }
    }
    if (fclose(file) != 0 || tgid == 0)
        return false;
    info->tgid = tgid;
    return true;
}

static bool proc_info_equal(const struct task_proc_info *a,
                            const struct task_proc_info *b)
{
    return a->tgid == b->tgid && a->start_ticks == b->start_ticks;
}

static bool start_ns_matches_proc_ticks(uint64_t start_ns,
                                        uint64_t proc_ticks)
{
    long clock_ticks = sysconf(_SC_CLK_TCK);
    uint64_t hz;
    uint64_t seconds;
    uint64_t remainder;
    uint64_t converted;

    if (start_ns == 0 || clock_ticks <= 0)
        return false;
    hz = (uint64_t)clock_ticks;
    seconds = start_ns / UINT64_C(1000000000);
    remainder = start_ns % UINT64_C(1000000000);
    if (seconds > UINT64_MAX / hz || remainder > UINT64_MAX / hz)
        return false;
    converted = seconds * hz +
        (remainder * hz) / UINT64_C(1000000000);
    return converted == proc_ticks;
}

static bool resolve_identity(const struct map_set *maps, uint32_t tid,
                             uint64_t scheduler_epoch,
                             struct orchestra_task_identity *identity)
{
    struct task_proc_info before, after;
    struct orchestra_pid_key key;
    struct bridge_identity_record record;

    if (!get_task_proc_info(tid, &before))
        return false;
    key.tgid = before.tgid;
    key.tid = tid;
    memset(&record, 0, sizeof(record));
    if (bpf_lookup_raw(maps->fd[MAP_IDENTITY], &key, &record, 0) != 0 ||
        record.start_boottime_ns == 0 || record.scheduler_epoch != scheduler_epoch ||
        !start_ns_matches_proc_ticks(record.start_boottime_ns,
                                    before.start_ticks))
        return false;
    if (!get_task_proc_info(tid, &after) || !proc_info_equal(&before, &after))
        return false;
    identity->tgid = before.tgid;
    identity->tid = tid;
    identity->start_boottime_ns = record.start_boottime_ns;
    return true;
}

static int acquire_writer_lock(void)
{
    int fd = open(BRIDGE_LOCK_PATH,
                  O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
    struct stat state;

    if (fd < 0)
        return -1;
    if (fstat(fd, &state) != 0 || !S_ISREG(state.st_mode) ||
        state.st_uid != geteuid() || (state.st_mode & 077u) != 0) {
        close(fd);
        errno = EPERM;
        return -1;
    }
    if (flock(fd, LOCK_EX) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

static bool cpu_allowed_for_task(uint32_t tid, uint32_t cpu)
{
    cpu_set_t allowed;

    if (cpu >= CPU_SETSIZE)
        return false;
    CPU_ZERO(&allowed);
    return sched_getaffinity((pid_t)tid, sizeof(allowed), &allowed) == 0 &&
           CPU_ISSET_S(cpu, sizeof(allowed), &allowed);
}

static bool directive_equal(const struct bridge_directive *a,
                            const struct bridge_directive *b)
{
    return a->abi_version == b->abi_version &&
           a->value_size == b->value_size && a->flags == b->flags &&
           a->scheduler_epoch == b->scheduler_epoch &&
           a->generation == b->generation &&
           memcmp(&a->identity, &b->identity, sizeof(a->identity)) == 0 &&
           a->action == b->action && a->target_cpu == b->target_cpu &&
           a->slice_ns == b->slice_ns &&
           a->not_before_ns == b->not_before_ns &&
           a->throttle_period_ns == b->throttle_period_ns &&
           a->throttle_budget_ns == b->throttle_budget_ns &&
           a->expiry_ns == b->expiry_ns &&
           a->controller_state == b->controller_state &&
           a->policy_mode == b->policy_mode &&
           a->policy_generation == b->policy_generation;
}

static uint32_t prune_expired_directives(int directive_fd, uint64_t epoch,
                                         uint64_t now)
{
    struct orchestra_task_identity key, next;
    bool have_key = false;
    uint32_t removed = 0;
    uint32_t scanned = 0;

    /* Deletion restarts hash iteration, so no entry is skipped. */
    while (scanned++ < BRIDGE_MAX_TASKS &&
           bpf_next_key_raw(directive_fd, have_key ? &key : NULL, &next) == 0) {
        struct bridge_directive directive;

        memset(&directive, 0, sizeof(directive));
        if (bpf_lookup_raw(directive_fd, &next, &directive, BPF_F_LOCK) != 0) {
            key = next;
            have_key = true;
            continue;
        }
        if (directive.abi_version == ORCHESTRA_ABI_VERSION &&
            directive.value_size == sizeof(directive) &&
            directive.scheduler_epoch == epoch && directive.expiry_ns > now) {
            key = next;
            have_key = true;
        } else if (bpf_delete_raw(directive_fd, &next) == 0) {
            removed++;
            have_key = false;
        } else {
            key = next;
            have_key = true;
        }
    }
    return removed;
}

static int publish_directive(const struct options *opts,
                             uint64_t *published_generation)
{
    struct map_set maps;
    struct bridge_control control, verify_control;
    struct bridge_directive directive, verify;
    struct orchestra_task_identity identity, identity_after;
    uint64_t now, expiry;
    uint32_t wire_action;
    int lock_fd = -1;
    int update_error = 0;
    int result = EXIT_PUB_FAIL;

    if (!scheduler_loaded()) {
        fprintf(stderr, "the active scheduler is not %s\n", BRIDGE_OPS_NAME);
        return EXIT_NO_SCHED;
    }
    if (!canonical_to_wire(opts->action, &wire_action))
        return EXIT_ACTION;
    if (!open_runtime_maps(&maps, false)) {
        fprintf(stderr, "missing or ABI-incompatible bridge maps: %s\n", strerror(errno));
        return errno == EPROTO ? EXIT_SCHEMA : EXIT_MAP_MISSING;
    }
    lock_fd = acquire_writer_lock();
    if (lock_fd < 0) {
        fprintf(stderr, "cannot serialize publisher: %s\n", strerror(errno));
        result = EXIT_PERM;
        goto out;
    }
    if (!read_control(maps.fd[MAP_CONTROL], &control) || !valid_control(&control)) {
        fprintf(stderr, "invalid control ABI\n");
        result = EXIT_SCHEMA;
        goto out;
    }
    if (!resolve_identity(&maps, opts->target_tid, control.scheduler_epoch,
                          &identity)) {
        fprintf(stderr, "TID %" PRIu32 " has no current kernel identity record\n",
                opts->target_tid);
        result = EXIT_TASK;
        goto out;
    }
    if (!monotonic_ns(&now) ||
        !checked_add_u64(now, opts->expiry_duration_ns, &expiry)) {
        fprintf(stderr, "monotonic time overflow\n");
        goto out;
    }
    if (opts->action == ORCHESTRA_ACTION_MIGRATE &&
        (opts->target_cpu == ORCHESTRA_CPU_ANY ||
         !cpu_allowed_for_task(opts->target_tid, opts->target_cpu))) {
        fprintf(stderr, "CPU %" PRIu32 " is not currently allowed for TID %" PRIu32 "\n",
                opts->target_cpu, opts->target_tid);
        result = EXIT_ACTION;
        goto out;
    }
    if (opts->action == ORCHESTRA_ACTION_SLEEP &&
        (opts->not_before_ns <= now || opts->not_before_ns - now > BRIDGE_SLEEP_MAX_NS)) {
        fprintf(stderr, "SLEEP not-before must be in the next five seconds\n");
        result = EXIT_ACTION;
        goto out;
    }
    if (opts->action == ORCHESTRA_ACTION_THROTTLE &&
        (opts->throttle_period_ns < BRIDGE_SLICE_MIN_NS ||
         opts->throttle_period_ns > BRIDGE_THROTTLE_MAX_NS ||
         opts->throttle_budget_ns < BRIDGE_SLICE_MIN_NS ||
         opts->throttle_budget_ns >= opts->throttle_period_ns)) {
        fprintf(stderr, "THROTTLE requires 100us <= budget < period <= 1s\n");
        result = EXIT_ACTION;
        goto out;
    }
    if (control.last_generation == UINT64_MAX) {
        fprintf(stderr, "generation exhausted for this scheduler epoch\n");
        result = EXIT_GEN_OVERFLOW;
        goto out;
    }

    memset(&directive, 0, sizeof(directive));
    directive.abi_version = ORCHESTRA_ABI_VERSION;
    directive.value_size = sizeof(directive);
    directive.scheduler_epoch = control.scheduler_epoch;
    directive.generation = control.last_generation + 1;
    directive.identity = identity;
    directive.action = wire_action;
    directive.target_cpu = opts->target_cpu;
    directive.slice_ns = opts->slice_ns;
    directive.not_before_ns = opts->not_before_ns;
    directive.throttle_period_ns = opts->throttle_period_ns;
    directive.throttle_budget_ns = opts->throttle_budget_ns;
    directive.expiry_ns = expiry;
    directive.controller_state = opts->controller_state;
    directive.policy_mode = opts->policy_mode;
    directive.policy_generation = opts->policy_generation;

    if (opts->dry_run) {
        if (!opts->quiet)
            printf("DRY-RUN identity=%" PRIu32 ":%" PRIu32 ":%" PRIu64
                   " action=%s generation=%" PRIu64 "\n",
                   identity.tgid, identity.tid, identity.start_boottime_ns,
                   action_names[opts->action], directive.generation);
        if (published_generation)
            *published_generation = directive.generation;
        result = EXIT_OK;
        goto out;
    }

    /* Reserve a never-reused generation before making the directive visible. */
    control.last_generation = directive.generation;
    control.publisher_heartbeat_ns = now;
    control.publisher_lease_ns = opts->lease_ns;
    control.controller_state = opts->controller_state;
    control.policy_mode = opts->policy_mode;
    control.policy_generation = opts->policy_generation;
    control.publication_status = BRIDGE_PUB_OK;
    if (!write_control(maps.fd[MAP_CONTROL], &control)) {
        fprintf(stderr, "control update failed: %s\n", strerror(errno));
        goto out;
    }
    if (bpf_update_raw(maps.fd[MAP_DIRECTIVE], &identity, &directive,
                       BPF_ANY | BPF_F_LOCK) != 0) {
        update_error = errno;
        if (update_error == ENOSPC &&
            prune_expired_directives(maps.fd[MAP_DIRECTIVE],
                                     control.scheduler_epoch, now) > 0) {
            if (bpf_update_raw(maps.fd[MAP_DIRECTIVE], &identity, &directive,
                               BPF_ANY | BPF_F_LOCK) == 0)
                update_error = 0;
            else
                update_error = errno;
        }
    }
    if (update_error != 0) {
        control.publication_status = update_error == ENOSPC ?
            BRIDGE_PUB_MAP_FULL : BRIDGE_PUB_MAP_ERROR;
        (void)write_control(maps.fd[MAP_CONTROL], &control);
        fprintf(stderr, "directive update failed: %s\n",
                strerror(update_error));
        goto out;
    }
    memset(&verify, 0, sizeof(verify));
    if (bpf_lookup_raw(maps.fd[MAP_DIRECTIVE], &identity, &verify,
                       BPF_F_LOCK) != 0 || !directive_equal(&directive, &verify) ||
        !read_control(maps.fd[MAP_CONTROL], &verify_control) ||
        !valid_control(&verify_control) ||
        verify_control.scheduler_epoch != control.scheduler_epoch ||
        verify_control.last_generation != directive.generation ||
        verify_control.publisher_heartbeat_ns != now ||
        !resolve_identity(&maps, opts->target_tid, control.scheduler_epoch,
                          &identity_after) ||
        memcmp(&identity, &identity_after, sizeof(identity)) != 0) {
        int saved = errno;
        (void)bpf_delete_raw(maps.fd[MAP_DIRECTIVE], &identity);
        control.publication_status = BRIDGE_PUB_READBACK_FAIL;
        (void)write_control(maps.fd[MAP_CONTROL], &control);
        errno = saved;
        fprintf(stderr, "full publication readback or identity revalidation failed\n");
        goto out;
    }
    if (!opts->quiet)
        printf("published generation=%" PRIu64 " identity=%" PRIu32 ":%" PRIu32
               ":%" PRIu64 " action=%s\n",
               directive.generation, identity.tgid, identity.tid,
               identity.start_boottime_ns, action_names[opts->action]);
    if (published_generation)
        *published_generation = directive.generation;
    result = EXIT_OK;

out:
    if (lock_fd >= 0)
        close(lock_fd);
    map_set_close(&maps);
    return result;
}

static int clear_directives(const struct options *opts)
{
    struct map_set maps;
    struct bridge_control control;
    struct orchestra_task_identity identity, next;
    int lock_fd;
    int result = EXIT_OK;

    if (!open_runtime_maps(&maps, false))
        return EXIT_MAP_MISSING;
    lock_fd = acquire_writer_lock();
    if (lock_fd < 0) {
        map_set_close(&maps);
        return EXIT_PERM;
    }
    if (!read_control(maps.fd[MAP_CONTROL], &control) || !valid_control(&control)) {
        result = EXIT_SCHEMA;
        goto out;
    }
    if (opts->target_set) {
        if (!resolve_identity(&maps, opts->target_tid, control.scheduler_epoch,
                              &identity) ||
            (bpf_delete_raw(maps.fd[MAP_DIRECTIVE], &identity) != 0 &&
             errno != ENOENT))
            result = EXIT_TASK;
    } else {
        bool have_key = false;

        while (bpf_next_key_raw(maps.fd[MAP_DIRECTIVE],
                                have_key ? &identity : NULL, &next) == 0) {
            if (bpf_delete_raw(maps.fd[MAP_DIRECTIVE], &next) != 0 && errno != ENOENT) {
                result = EXIT_PUB_FAIL;
                break;
            }
            /* Deletion restarts iteration; this cannot skip a hash entry. */
            have_key = false;
        }
    }
    /* Never reset last_generation: clear cannot create an ABA identity. */
    if (result == EXIT_OK)
        puts("cleared; scheduler epoch and generation were preserved");
out:
    close(lock_fd);
    map_set_close(&maps);
    return result;
}

static int status_command(void)
{
    struct map_set maps;
    struct bridge_control control;
    struct bridge_telemetry telemetry;
    struct orchestra_task_identity key, next;
    bool have_key = false;
    uint32_t zero = 0;

    printf("scheduler: %s\n", scheduler_loaded() ? BRIDGE_OPS_NAME : "not active");
    if (!open_runtime_maps(&maps, true)) {
        fprintf(stderr, "bridge maps missing or schema-invalid: %s\n", strerror(errno));
        return errno == EPROTO ? EXIT_SCHEMA : EXIT_MAP_MISSING;
    }
    if (!read_control(maps.fd[MAP_CONTROL], &control) || !valid_control(&control)) {
        map_set_close(&maps);
        return EXIT_SCHEMA;
    }
    printf("abi=%u scx_api=%u epoch=%" PRIu64 " generation=%" PRIu64
           " policy_generation=%" PRIu64 " controller=%s lease=%" PRIu64
           "ns\n",
           control.abi_version, control.scx_api_version,
           control.scheduler_epoch, control.last_generation,
           control.policy_generation,
           control.controller_state < ORCHESTRA_CTRL_COUNT ?
               controller_names[control.controller_state] : "INVALID",
           control.publisher_lease_ns);
    while (bpf_next_key_raw(maps.fd[MAP_DIRECTIVE],
                            have_key ? &key : NULL, &next) == 0) {
        struct bridge_directive directive;

        memset(&directive, 0, sizeof(directive));
        if (bpf_lookup_raw(maps.fd[MAP_DIRECTIVE], &next, &directive,
                           BPF_F_LOCK) == 0) {
            printf("directive identity=%" PRIu32 ":%" PRIu32 ":%" PRIu64
                   " generation=%" PRIu64 " action=%s cpu=%" PRIu32 "\n",
                   next.tgid, next.tid, next.start_boottime_ns,
                   directive.generation,
                   directive.action < ORCHESTRA_ACTION_COUNT ?
                       action_names[directive.action] : "INVALID",
                   directive.target_cpu);
        }
        key = next;
        have_key = true;
    }
    have_key = false;
    while (bpf_next_key_raw(maps.fd[MAP_TASK_TELEMETRY],
                            have_key ? &key : NULL, &next) == 0) {
        struct bridge_task_telemetry task;

        memset(&task, 0, sizeof(task));
        if (bpf_lookup_raw(maps.fd[MAP_TASK_TELEMETRY], &next, &task,
                           BPF_F_LOCK) == 0) {
            printf("task identity=%" PRIu32 ":%" PRIu32 ":%" PRIu64
                   " generation=%" PRIu64 " action=%s requested_cpu=%" PRIu32
                   " dispatched_cpu=%" PRId32 " actual_cpu=%" PRId32
                   " accepted=%" PRIu32 " dispatched=%" PRIu32
                   " running=%" PRIu32 " effective=%" PRIu32
                   " fallback=%" PRIu32 " errors=%" PRIu32 "\n",
                   next.tgid, next.tid, next.start_boottime_ns,
                   task.generation,
                   task.action < ORCHESTRA_ACTION_COUNT ?
                       action_names[task.action] : "INVALID",
                   task.requested_cpu, task.dispatched_cpu, task.actual_cpu,
                   task.accepted_count, task.dispatched_count,
                   task.running_count, task.effective_count,
                   task.fallback_count, task.error_count);
        }
        key = next;
        have_key = true;
    }
    memset(&telemetry, 0, sizeof(telemetry));
    if (bpf_lookup_raw(maps.fd[MAP_TELEMETRY], &zero, &telemetry, 0) == 0) {
        printf("telemetry accepted=%" PRIu64 " dispatched=%" PRIu64
               " running=%" PRIu64 " fallback=%" PRIu64
               " migrate_target=%" PRIu64 " migrate_other=%" PRIu64
               " timer_ticks=%" PRIu64 " deferred_scans=%" PRIu64
               " deferred_future=%" PRIu64 " deferred_release_fail=%" PRIu64
               " deferred_cpu_fail=%" PRIu64 "\n",
               telemetry.accepted_directive_count,
               telemetry.dispatched_action_count, telemetry.running_count,
               telemetry.fallback_count, telemetry.migrate_running_target_count,
               telemetry.migrate_running_other_count,
               telemetry.deferred_timer_tick_count,
               telemetry.deferred_timer_scanned_count,
               telemetry.deferred_timer_future_count,
               telemetry.deferred_release_failure_count,
               telemetry.deferred_cpu_failure_count);
    }
    map_set_close(&maps);
    return EXIT_OK;
}

static int opt_in_command(uint32_t tid)
{
    struct map_set maps;
    struct bridge_control control;
    struct orchestra_task_identity identity;
    int result = EXIT_TASK;

    if (!open_runtime_maps(&maps, false))
        return EXIT_MAP_MISSING;
    if (read_control(maps.fd[MAP_CONTROL], &control) && valid_control(&control) &&
        resolve_identity(&maps, tid, control.scheduler_epoch, &identity)) {
        printf("admitted exact TID identity=%" PRIu32 ":%" PRIu32 ":%" PRIu64
               "; full-switch mode does not change its Linux policy\n",
               identity.tgid, identity.tid, identity.start_boottime_ns);
        result = EXIT_OK;
    }
    map_set_close(&maps);
    return result;
}

static int pin_one(enum map_role role, uint32_t id, bool *created)
{
    struct bpf_map_info wanted, existing;
    int fd = bpf_map_fd_by_id(id);
    int old_fd;

    *created = false;
    if (fd < 0)
        return -1;
    if (!map_matches(fd, &map_specs[role], &wanted)) {
        close(fd);
        errno = EPROTO;
        return -1;
    }
    old_fd = bpf_obj_get_raw(map_specs[role].path);
    if (old_fd >= 0) {
        bool same = bpf_info_raw(old_fd, &existing) == 0 && existing.id == wanted.id;
        close(old_fd);
        close(fd);
        if (!same)
            errno = EEXIST;
        return same ? 0 : -1;
    }
    if (bpf_obj_pin_raw(fd, map_specs[role].path) != 0) {
        close(fd);
        return -1;
    }
    *created = true;
    close(fd);
    return 0;
}

static int pin_maps_command(const struct options *opts)
{
    enum map_role role;
    bool created[MAP_ROLE_COUNT] = {false};
    struct stat directory;
    struct bpf_map_info timer_info;
    uint32_t object_btf_id = 0;
    int timer_fd;

    if (!scheduler_loaded())
        return EXIT_NO_SCHED;
    /* A BPF timer is cancelled when its map loses all userspace references.
     * Pinning it after a generic loader exits cannot resurrect that timer.
     * Require a loader (or equivalent) to have pinned this exact map before
     * struct_ops attach; orchestra_loader implements the required order. */
    timer_fd = bpf_obj_get_raw(BRIDGE_DEFER_PATH);
    if (timer_fd < 0 ||
        !map_matches(timer_fd, &map_specs[MAP_DEFER_TIMER], &timer_info) ||
        timer_info.id != opts->map_ids[MAP_DEFER_TIMER]) {
        if (timer_fd >= 0)
            close(timer_fd);
        fprintf(stderr, "deferred timer map was not pinned before attach; use orchestra_loader\n");
        return EXIT_POLICY;
    }
    close(timer_fd);
    if (mkdir(BRIDGE_PIN_DIR, 0700) != 0 && errno != EEXIST)
        return EXIT_PERM;
    if (lstat(BRIDGE_PIN_DIR, &directory) != 0 ||
        !S_ISDIR(directory.st_mode) || directory.st_uid != geteuid() ||
        (directory.st_mode & (S_IWGRP | S_IWOTH)) != 0) {
        fprintf(stderr, "unsafe bridge pin directory ownership or mode\n");
        return EXIT_PERM;
    }
    for (role = MAP_CONTROL; role < MAP_ROLE_COUNT; role++) {
        struct bpf_map_info info;
        int fd;

        if (opts->map_ids[role] == 0) {
            fprintf(stderr, "every exact map ID is required; no global discovery is performed\n");
            return EXIT_ARGS;
        }
        fd = bpf_map_fd_by_id(opts->map_ids[role]);
        if (fd < 0 || !map_matches(fd, &map_specs[role], &info)) {
            if (fd >= 0) close(fd);
            return EXIT_SCHEMA;
        }
        close(fd);
        if (info.btf_id == 0 || (object_btf_id != 0 && info.btf_id != object_btf_id)) {
            fprintf(stderr, "map IDs do not share one BTF object identity\n");
            return EXIT_SCHEMA;
        }
        object_btf_id = info.btf_id;
    }
    for (role = MAP_CONTROL; role < MAP_ROLE_COUNT; role++) {
        if (pin_one(role, opts->map_ids[role], &created[role]) != 0) {
            int saved_errno = errno;
            fprintf(stderr, "cannot pin role %s ID %" PRIu32 ": %s\n",
                    map_specs[role].name, opts->map_ids[role],
                    strerror(saved_errno));
            for (enum map_role cleanup = MAP_CONTROL; cleanup < role; cleanup++) {
                if (created[cleanup] && unlink(map_specs[cleanup].path) != 0)
                    fprintf(stderr, "warning: cannot remove partial pin %s: %s\n",
                            map_specs[cleanup].path, strerror(errno));
            }
            return saved_errno == EPROTO ? EXIT_SCHEMA : EXIT_MAP_MISSING;
        }
    }
    return EXIT_OK;
}

/* 1=record, 0=clean EOF before a record, -1=error/truncated record. */
static int read_full_record(int fd, void *buffer, size_t size)
{
    uint8_t *cursor = buffer;
    size_t offset = 0;

    while (offset < size) {
        ssize_t count = read(fd, cursor + offset, size - offset);
        if (count < 0 && errno == EINTR)
            continue;
        if (count == 0)
            return offset == 0 ? 0 : -1;
        if (count < 0)
            return -1;
        offset += (size_t)count;
    }
    return 1;
}

static bool write_full(int fd, const void *buffer, size_t size)
{
    const uint8_t *cursor = buffer;
    size_t offset = 0;

    while (offset < size) {
        ssize_t count = write(fd, cursor + offset, size - offset);
        if (count < 0 && errno == EINTR)
            continue;
        if (count <= 0)
            return false;
        offset += (size_t)count;
    }
    return true;
}

static int stream_command(void)
{
    struct bridge_stream_request request;
    int read_status;
    uint64_t last_sequence = 0;

    while ((read_status = read_full_record(STDIN_FILENO, &request,
                                           sizeof(request))) == 1) {
        struct bridge_stream_response response = {
            .magic = BRIDGE_STREAM_MAGIC,
            .abi_version = ORCHESTRA_ABI_VERSION,
            .value_size = sizeof(response),
            .sequence = request.sequence
        };
        struct options opts;
        uint64_t generation = 0;

        memset(&opts, 0, sizeof(opts));
        opts.quiet = true;
        opts.publish = true;
        opts.action_set = true;
        opts.target_set = true;
        opts.target_cpu = ORCHESTRA_CPU_ANY;
        opts.expiry_duration_ns = DEFAULT_EXPIRY_NS;
        opts.lease_ns = DEFAULT_LEASE_NS;
        opts.controller_state = ORCHESTRA_CTRL_NORMAL;
        opts.policy_mode = ORCHESTRA_POLICY_EVALUATE;
        if (request.magic != BRIDGE_STREAM_MAGIC ||
            request.abi_version != ORCHESTRA_ABI_VERSION ||
            request.value_size != sizeof(request) ||
            request.sequence == 0 || request.sequence <= last_sequence ||
            request.action >= ORCHESTRA_ACTION_COUNT ||
            request.target_tid == 0 ||
            request.controller_state >= ORCHESTRA_CTRL_COUNT ||
            request.policy_mode >= ORCHESTRA_POLICY_COUNT ||
            request.expiry_duration_ns == 0 ||
            request.expiry_duration_ns > BRIDGE_EXPIRY_MAX_NS) {
            response.status = EXIT_ARGS;
        } else {
            last_sequence = request.sequence;
            opts.action = (enum orchestra_action_id)request.action;
            opts.target_tid = request.target_tid;
            opts.target_cpu = request.target_cpu;
            opts.slice_ns = request.slice_ns;
            opts.not_before_ns = request.not_before_ns;
            opts.throttle_period_ns = request.throttle_period_ns;
            opts.throttle_budget_ns = request.throttle_budget_ns;
            opts.expiry_duration_ns = request.expiry_duration_ns;
            opts.controller_state = request.controller_state;
            opts.policy_mode = request.policy_mode;
            opts.policy_generation = request.policy_generation;
            response.status = publish_directive(&opts, &generation);
            response.generation = generation;
        }
        if (!write_full(STDOUT_FILENO, &response, sizeof(response)))
            return EXIT_PUB_FAIL;
    }
    return read_status == 0 ? EXIT_OK : EXIT_PUB_FAIL;
}

static void usage(const char *program)
{
    fprintf(stderr,
        "Usage: %s COMMAND [OPTIONS]\n"
        "  --status\n"
        "  --stream   (binary canonical-engine request/response stream)\n"
        "  --publish --action RUN|SLEEP|MIGRATE|THROTTLE|YIELD --target-pid TID\n"
        "      [--target-cpu CPU] [--slice-ns NS] [--not-before-ns MONO_NS]\n"
        "      [--throttle-period-ns NS] [--throttle-budget-ns NS]\n"
        "      [--expiry-ns DURATION_NS] [--lease-ns NS] [--dry-run]\n"
        "      [--controller-state STATE] [--policy-mode ID] [--policy-generation N]\n"
        "  --clear [--target-pid TID]\n"
        "  --opt-in --target-pid TID   (identity admission only; exact TID)\n"
        "  --pin-maps --control-map-id ID --directive-map-id ID\n"
        "      --identity-map-id ID --task-map-id ID --task-telemetry-map-id ID\n"
        "      --telemetry-map-id ID --defer-timer-map-id ID\n"
        "      (timer map must already be pinned before attach; use orchestra_loader)\n",
        program);
}

static bool need_value(int argc, char **argv, int *index, const char **value)
{
    if (*index + 1 >= argc)
        return false;
    *value = argv[++*index];
    return true;
}

static bool parse_options(int argc, char **argv, struct options *opts)
{
    int i;
    unsigned int commands = 0;

    memset(opts, 0, sizeof(*opts));
    opts->action = ORCHESTRA_ACTION_RUN;
    opts->target_cpu = ORCHESTRA_CPU_ANY;
    opts->expiry_duration_ns = DEFAULT_EXPIRY_NS;
    opts->lease_ns = DEFAULT_LEASE_NS;
    opts->controller_state = ORCHESTRA_CTRL_NORMAL;
    opts->policy_mode = ORCHESTRA_POLICY_EVALUATE;

    for (i = 1; i < argc; i++) {
        const char *value = NULL;
        uint32_t parsed32;

        if (strcmp(argv[i], "--status") == 0) opts->status = true;
        else if (strcmp(argv[i], "--publish") == 0) opts->publish = true;
        else if (strcmp(argv[i], "--clear") == 0) opts->clear = true;
        else if (strcmp(argv[i], "--opt-in") == 0) opts->opt_in = true;
        else if (strcmp(argv[i], "--pin-maps") == 0) opts->pin_maps = true;
        else if (strcmp(argv[i], "--stream") == 0) opts->stream = true;
        else if (strcmp(argv[i], "--dry-run") == 0) opts->dry_run = true;
        else if (strcmp(argv[i], "--help") == 0) return false;
        else if (strcmp(argv[i], "--action") == 0) {
            if (!need_value(argc, argv, &i, &value) || !parse_action(value, &opts->action))
                return false;
            opts->action_set = true;
        } else if (strcmp(argv[i], "--target-pid") == 0) {
            if (!need_value(argc, argv, &i, &value) ||
                !parse_u32(value, 1, INT32_MAX, &opts->target_tid))
                return false;
            opts->target_set = true;
        } else if (strcmp(argv[i], "--target-cpu") == 0) {
            if (!need_value(argc, argv, &i, &value) ||
                !parse_u32(value, 0, UINT32_MAX - 1, &opts->target_cpu))
                return false;
        } else if (strcmp(argv[i], "--slice-ns") == 0) {
            if (!need_value(argc, argv, &i, &value) ||
                !parse_u64(value, 0, BRIDGE_SLICE_MAX_NS, &opts->slice_ns))
                return false;
        } else if (strcmp(argv[i], "--not-before-ns") == 0) {
            if (!need_value(argc, argv, &i, &value) ||
                !parse_u64(value, 1, UINT64_MAX, &opts->not_before_ns))
                return false;
        } else if (strcmp(argv[i], "--throttle-period-ns") == 0 ||
                   strcmp(argv[i], "--throttle-interval-ns") == 0) {
            if (!need_value(argc, argv, &i, &value) ||
                !parse_u64(value, 1, BRIDGE_THROTTLE_MAX_NS,
                           &opts->throttle_period_ns))
                return false;
        } else if (strcmp(argv[i], "--throttle-budget-ns") == 0) {
            if (!need_value(argc, argv, &i, &value) ||
                !parse_u64(value, 1, BRIDGE_THROTTLE_MAX_NS,
                           &opts->throttle_budget_ns))
                return false;
        } else if (strcmp(argv[i], "--expiry-ns") == 0) {
            if (!need_value(argc, argv, &i, &value) ||
                !parse_u64(value, 1, BRIDGE_EXPIRY_MAX_NS,
                           &opts->expiry_duration_ns))
                return false;
        } else if (strcmp(argv[i], "--lease-ns") == 0) {
            if (!need_value(argc, argv, &i, &value) ||
                !parse_u64(value, 1, BRIDGE_LEASE_MAX_NS, &opts->lease_ns))
                return false;
        } else if (strcmp(argv[i], "--controller-state") == 0) {
            if (!need_value(argc, argv, &i, &value) ||
                !parse_controller(value, &opts->controller_state))
                return false;
        } else if (strcmp(argv[i], "--policy-mode") == 0) {
            if (!need_value(argc, argv, &i, &value) ||
                !parse_u32(value, 0, ORCHESTRA_POLICY_COUNT - 1, &opts->policy_mode))
                return false;
        } else if (strcmp(argv[i], "--policy-generation") == 0) {
            if (!need_value(argc, argv, &i, &value) ||
                !parse_u64(value, 0, UINT64_MAX, &opts->policy_generation))
                return false;
        } else if (strcmp(argv[i], "--control-map-id") == 0 ||
                   strcmp(argv[i], "--directive-map-id") == 0 ||
                   strcmp(argv[i], "--identity-map-id") == 0 ||
                   strcmp(argv[i], "--task-map-id") == 0 ||
                   strcmp(argv[i], "--task-telemetry-map-id") == 0 ||
                   strcmp(argv[i], "--telemetry-map-id") == 0 ||
                   strcmp(argv[i], "--defer-timer-map-id") == 0) {
            enum map_role role = strcmp(argv[i], "--control-map-id") == 0 ? MAP_CONTROL :
                strcmp(argv[i], "--directive-map-id") == 0 ? MAP_DIRECTIVE :
                strcmp(argv[i], "--identity-map-id") == 0 ? MAP_IDENTITY :
                strcmp(argv[i], "--task-map-id") == 0 ? MAP_TASK_STATE :
                strcmp(argv[i], "--task-telemetry-map-id") == 0 ? MAP_TASK_TELEMETRY :
                strcmp(argv[i], "--telemetry-map-id") == 0 ? MAP_TELEMETRY :
                MAP_DEFER_TIMER;
            if (!need_value(argc, argv, &i, &value) ||
                !parse_u32(value, 1, UINT32_MAX, &parsed32))
                return false;
            opts->map_ids[role] = parsed32;
        } else {
            return false;
        }
    }

    commands = (unsigned int)opts->status + (unsigned int)opts->publish
             + (unsigned int)opts->clear + (unsigned int)opts->opt_in
             + (unsigned int)opts->pin_maps + (unsigned int)opts->stream;
    if (commands != 1)
        return false;
    if ((opts->publish && (!opts->action_set || !opts->target_set)) ||
        (opts->opt_in && !opts->target_set))
        return false;
    if (opts->action == ORCHESTRA_ACTION_SLEEP && opts->not_before_ns == 0) {
        uint64_t now;
        if (!monotonic_ns(&now) || !checked_add_u64(now, UINT64_C(20000000),
                                                    &opts->not_before_ns))
            return false;
    }
    if (opts->action == ORCHESTRA_ACTION_THROTTLE) {
        if (opts->throttle_period_ns == 0)
            opts->throttle_period_ns = UINT64_C(10000000);
        if (opts->throttle_budget_ns == 0)
            opts->throttle_budget_ns = UINT64_C(2000000);
    }
    return true;
}

#ifndef ORCHESTRA_BRIDGE_UNIT_TEST
int main(int argc, char **argv)
{
    struct options opts;

    if (!parse_options(argc, argv, &opts)) {
        usage(argv[0]);
        return EXIT_ARGS;
    }
    if (opts.status)
        return status_command();
    if (opts.stream)
        return stream_command();
    if (opts.publish)
        return publish_directive(&opts, NULL);
    if (opts.clear)
        return clear_directives(&opts);
    if (opts.opt_in)
        return opt_in_command(opts.target_tid);
    if (opts.pin_maps)
        return pin_maps_command(&opts);
    return EXIT_ARGS;
}
#endif
