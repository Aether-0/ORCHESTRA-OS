/*
 * Integration coverage for the generation-stamped userspace signal transport.
 *
 * This intentionally includes the canonical implementation under its unit-test
 * visibility switch, but keeps the bus and reader-gate mappings separate and
 * MAP_SHARED.  A worker normally makes only the bus mapping read-only; the
 * separate gate mapping must remain writable for bounded reader pin/unpin.
 */
#define ORCHESTRA_UNIT_TEST 1
#define main orchestra_demo_main
#include "../../orchestra_paper_cpu_demo/orchestra_paper_cpu.c"
#undef main

typedef struct {
    int frame_result;
    int child_errno;
    uint64_t sequence;
} child_reader_report_t;

typedef enum {
    SAFE_DISPOSITION_ACCEPT = 0,
    SAFE_DISPOSITION_RETAIN_LKG,
    SAFE_DISPOSITION_OBSERVED_FALLBACK
} safe_disposition_t;

enum {
    INTEGRATION_PROCESS_READER_COUNT = 4,
    INTEGRATION_PROCESS_PUBLICATION_COUNT = 2000,
    INTEGRATION_PROCESS_PUBLISH_RETRY_LIMIT = 2048,
    INTEGRATION_PROCESS_READER_ATTEMPT_LIMIT = 200000,
    INTEGRATION_PROCESS_START_WAIT_LIMIT = 200000,
};

typedef enum {
    INTEGRATION_PROCESS_READER_OK = 0,
    INTEGRATION_PROCESS_READER_MPROTECT_FAILED,
    INTEGRATION_PROCESS_READER_START_ABORTED,
    INTEGRATION_PROCESS_READER_START_TIMEOUT,
    INTEGRATION_PROCESS_READER_INVALID_FRAME,
    INTEGRATION_PROCESS_READER_SEQUENCE_ERROR,
    INTEGRATION_PROCESS_READER_INCOMPLETE
} integration_process_reader_status_t;

/* This is intentionally a third mapping.  Children make only the canonical
 * bus read-only; gates and this bounded test-control state remain writable. */
typedef struct {
    _Atomic unsigned int readers_ready;
    _Atomic int start;
    _Atomic int publisher_done;
    _Atomic int abort_requested;
    _Atomic uint64_t hook_calls;
    _Atomic uint64_t hook_yields;
} integration_process_stress_control_t;

typedef struct {
    int status;
    int child_errno;
    uint64_t read_attempts;
    uint64_t verified_reads;
    uint64_t retries;
    uint64_t retry_exhaustions;
    uint64_t unstable_reads;
    uint64_t invalid_reads;
    uint64_t hmac_failures;
    uint64_t invalid_fields;
    uint64_t invalid_schema;
    uint64_t invalid_tier;
    uint64_t invalid_source;
    uint64_t invalid_directive;
    uint64_t invalid_sequence;
    uint64_t invalid_key_epochs;
    uint64_t stale_frames;
    uint64_t valid_reads;
    uint64_t no_new_reads;
    uint64_t sequence_regressions;
    uint64_t accepted_duplicates;
    uint64_t final_sequence;
} integration_process_reader_report_t;

static volatile sig_atomic_t g_integration_reader_stop_once = 0;
static integration_process_stress_control_t *g_integration_process_stress_control = NULL;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "check failed at %s:%d: %s\n",                  \
                    __FILE__, __LINE__, #condition);                            \
            return false;                                                       \
        }                                                                       \
    } while (0)

static uint64_t integration_deadline_after_ns(uint64_t duration_ns) {
    uint64_t now = monotonic_ns();
    return now > UINT64_MAX - duration_ns ? UINT64_MAX : now + duration_ns;
}

static bool integration_wait_child_until(pid_t pid, uint64_t deadline_ns,
                                         int *status_out) {
    while (monotonic_ns() < deadline_ns) {
        pid_t result = waitpid(pid, status_out, WNOHANG);
        if (result == pid) return true;
        if (result < 0 && errno != EINTR) return false;
        struct timespec pause = { .tv_sec = 0, .tv_nsec = 1000000L };
        (void)nanosleep(&pause, NULL);
    }
    return false;
}

static bool integration_wait_child_bounded(pid_t pid, int *status_out) {
    if (integration_wait_child_until(pid, integration_deadline_after_ns(
            UINT64_C(2000000000)), status_out)) {
        return true;
    }
    if (kill(pid, SIGKILL) != 0 && errno != ESRCH) return false;
    return integration_wait_child_until(pid, integration_deadline_after_ns(
        UINT64_C(1000000000)), status_out);
}

static bool integration_wait_child_stopped_bounded(pid_t pid, int *status_out) {
    uint64_t deadline = integration_deadline_after_ns(UINT64_C(2000000000));
    while (monotonic_ns() < deadline) {
        pid_t result = waitpid(pid, status_out, WNOHANG | WUNTRACED);
        if (result == pid) return WIFSTOPPED(*status_out);
        if (result < 0 && errno != EINTR) return false;
        struct timespec pause = { .tv_sec = 0, .tv_nsec = 1000000L };
        (void)nanosleep(&pause, NULL);
    }
    return false;
}

static void integration_fill_key(uint8_t key[MASTER_KEY_SIZE]) {
    for (size_t index = 0; index < MASTER_KEY_SIZE; ++index)
        key[index] = (uint8_t)(UINT8_C(0x40) + (uint8_t)index);
}

static signal_payload_t integration_valid_payload(uint64_t sequence) {
    return (signal_payload_t) {
        .magic = SIGNAL_MAGIC,
        .schema_version = SIGNAL_SCHEMA_VERSION,
        .tier = SIGNAL_TIER_CORE_LOCAL,
        .source_id = SIGNAL_SOURCE_LOCAL,
        .sequence = sequence,
        .monotonic_ns = monotonic_ns(),
        .max_age_ns = UINT64_C(5000000000),
        .key_epoch = (uint32_t)(sequence / (uint64_t)KEY_EPOCH_TICKS),
        .directive = ACT_RUN,
        .state_schema_version = STATE_SCHEMA_VERSION,
        .prediction_used = 1u,
        .cpu_now = 0.40,
        .cpu_pred = 0.42,
        .decision_cpu = 0.42,
        .memory_pressure = 0.20,
        .thermal_proxy = 0.25,
        .confidence = 0.90,
        .jitter_sigma = 0.02,
        .switch_penalty = 0.01,
        .consensus_blend = 0.01,
    };
}

static void integration_initialize_shared_bus(signal_bus_t *bus,
                                              signal_reader_gates_t *gates) {
    memset(bus, 0, sizeof(*bus));
    memset(gates, 0, sizeof(*gates));
    initialize_selected_signal_publication(&bus->publication);
    initialize_signal_reader_gates(gates);
    initialize_signal_publisher_diagnostics(&bus->diagnostics);
    atomic_init(&bus->consensus_lock, 0);
    atomic_init(&bus->stop, 0);
}

static size_t integration_active_slot(const signal_bus_t *bus) {
    uint64_t token = atomic_load_explicit(&bus->publication.publication_token.value,
                                          memory_order_acquire);
    return (size_t)(token & SIGNAL_TOKEN_SLOT_MASK);
}

static size_t integration_next_slot(const signal_bus_t *bus) {
    uint64_t token = atomic_load_explicit(&bus->publication.publication_token.value,
                                          memory_order_acquire);
    return token == 0u ? 0u
                       : (size_t)(UINT64_C(1) - (token & SIGNAL_TOKEN_SLOT_MASK));
}

static safe_disposition_t integration_classify_read(frame_read_result_t result,
                                                     bool have_lkg) {
    if (result == FRAME_VALID) return SAFE_DISPOSITION_ACCEPT;
    if (have_lkg && (result == FRAME_UNSTABLE || result == FRAME_NO_NEW))
        return SAFE_DISPOSITION_RETAIN_LKG;
    return SAFE_DISPOSITION_OBSERVED_FALLBACK;
}

static safe_disposition_t integration_classify_publication(signal_publish_result_t result,
                                                            bool have_lkg) {
    if (result == SIGNAL_PUBLISH_OK) return SAFE_DISPOSITION_ACCEPT;
    return have_lkg ? SAFE_DISPOSITION_RETAIN_LKG
                    : SAFE_DISPOSITION_OBSERVED_FALLBACK;
}

static void integration_stop_reader_between_token_and_words(
    signal_publication_hook_stage_t stage) {
    if (stage == SIGNAL_HOOK_READER_TOKEN && g_integration_reader_stop_once == 0) {
        g_integration_reader_stop_once = 1;
        (void)raise(SIGSTOP);
    }
}

static void integration_stop_reader_while_pinned(signal_publication_hook_stage_t stage) {
    if (stage == SIGNAL_HOOK_READER_PINNED && g_integration_reader_stop_once == 0) {
        g_integration_reader_stop_once = 1;
        (void)raise(SIGSTOP);
    }
}

static void integration_initialize_process_stress_control(
    integration_process_stress_control_t *control) {
    memset(control, 0, sizeof(*control));
    atomic_init(&control->readers_ready, 0u);
    atomic_init(&control->start, 0);
    atomic_init(&control->publisher_done, 0);
    atomic_init(&control->abort_requested, 0);
    atomic_init(&control->hook_calls, 0);
    atomic_init(&control->hook_yields, 0);
}

static void integration_process_stress_hook(signal_publication_hook_stage_t stage) {
    integration_process_stress_control_t *control =
        g_integration_process_stress_control;
    if (control == NULL
        || (stage != SIGNAL_HOOK_WRITER_WORD && stage != SIGNAL_HOOK_READER_TOKEN
            && stage != SIGNAL_HOOK_READER_SEQUENCE
            && stage != SIGNAL_HOOK_READER_WORD)) {
        return;
    }
    uint64_t call = atomic_fetch_add_explicit(&control->hook_calls, UINT64_C(1),
                                               memory_order_relaxed);
    /* This deterministic unsigned permutation injects occasional bounded
     * yields at writer and reader copy phases without synchronizing every
     * process at one predictable iteration. */
    uint64_t mixed = (call * UINT64_C(0x9e3779b97f4a7c15))
                   ^ ((uint64_t)stage * UINT64_C(0xbf58476d1ce4e5b9));
    if ((mixed >> 58u) == 0u) {
        (void)sched_yield();
        (void)atomic_fetch_add_explicit(&control->hook_yields, UINT64_C(1),
                                         memory_order_relaxed);
    }
}

static void integration_snapshot_process_reader_diagnostics(
    integration_process_reader_report_t *report,
    const signal_reader_diagnostics_t *diagnostics) {
    report->read_attempts = atomic_load_explicit(&diagnostics->read_attempts,
                                                 memory_order_relaxed);
    report->verified_reads = atomic_load_explicit(&diagnostics->verified_reads,
                                                  memory_order_relaxed);
    report->retries = atomic_load_explicit(&diagnostics->retries,
                                           memory_order_relaxed);
    report->retry_exhaustions = atomic_load_explicit(&diagnostics->retry_exhaustions,
                                                     memory_order_relaxed);
    report->hmac_failures = atomic_load_explicit(&diagnostics->hmac_failures,
                                                 memory_order_relaxed);
    report->invalid_fields = atomic_load_explicit(&diagnostics->invalid_fields,
                                                  memory_order_relaxed);
    report->invalid_schema = atomic_load_explicit(&diagnostics->invalid_schema,
                                                  memory_order_relaxed);
    report->invalid_tier = atomic_load_explicit(&diagnostics->invalid_tier,
                                                memory_order_relaxed);
    report->invalid_source = atomic_load_explicit(&diagnostics->invalid_source,
                                                  memory_order_relaxed);
    report->invalid_directive = atomic_load_explicit(&diagnostics->invalid_directive,
                                                     memory_order_relaxed);
    report->invalid_sequence = atomic_load_explicit(&diagnostics->invalid_sequence,
                                                    memory_order_relaxed);
    report->invalid_key_epochs = atomic_load_explicit(&diagnostics->invalid_key_epochs,
                                                      memory_order_relaxed);
    report->stale_frames = atomic_load_explicit(&diagnostics->stale_frames,
                                                memory_order_relaxed);
}

static void integration_process_reader_exit(
    int report_fd, integration_process_reader_report_t *report) {
    ssize_t written = write(report_fd, report, sizeof(*report));
    (void)close(report_fd);
    _exit(written == (ssize_t)sizeof(*report)
          && report->status == INTEGRATION_PROCESS_READER_OK
          ? EXIT_SUCCESS : EXIT_FAILURE);
}

static void integration_process_reader(
    signal_bus_t *bus, signal_reader_gates_t *gates,
    integration_process_stress_control_t *control,
    const uint8_t key[MASTER_KEY_SIZE], int report_fd) {
    integration_process_reader_report_t report = {0};
    signal_reader_diagnostics_t diagnostics;
    initialize_signal_reader_diagnostics(&diagnostics);
    if (mprotect(bus, sizeof(*bus), PROT_READ) != 0) {
        report.status = INTEGRATION_PROCESS_READER_MPROTECT_FAILED;
        report.child_errno = errno;
        integration_snapshot_process_reader_diagnostics(&report, &diagnostics);
        integration_process_reader_exit(report_fd, &report);
    }

    (void)atomic_fetch_add_explicit(&control->readers_ready, 1u, memory_order_release);
    bool started = false;
    for (unsigned int attempt = 0; attempt < INTEGRATION_PROCESS_START_WAIT_LIMIT;
         ++attempt) {
        if (atomic_load_explicit(&control->abort_requested, memory_order_acquire) != 0) {
            report.status = INTEGRATION_PROCESS_READER_START_ABORTED;
            integration_snapshot_process_reader_diagnostics(&report, &diagnostics);
            integration_process_reader_exit(report_fd, &report);
        }
        if (atomic_load_explicit(&control->start, memory_order_acquire) != 0) {
            started = true;
            break;
        }
        (void)sched_yield();
    }
    if (!started) {
        report.status = INTEGRATION_PROCESS_READER_START_TIMEOUT;
        integration_snapshot_process_reader_diagnostics(&report, &diagnostics);
        integration_process_reader_exit(report_fd, &report);
    }

    uint64_t last_sequence = 0;
    for (unsigned int attempt = 0; attempt < INTEGRATION_PROCESS_READER_ATTEMPT_LIMIT;
         ++attempt) {
        if (atomic_load_explicit(&control->abort_requested, memory_order_acquire) != 0) {
            report.status = INTEGRATION_PROCESS_READER_START_ABORTED;
            break;
        }
        signal_payload_t frame = {0};
        frame_read_result_t outcome = read_verified_frame_with_diagnostics(
            bus, gates, key, last_sequence, &frame, &diagnostics);
        if (outcome == FRAME_VALID) {
            if (frame.sequence < last_sequence) {
                report.sequence_regressions++;
                report.status = INTEGRATION_PROCESS_READER_SEQUENCE_ERROR;
                break;
            }
            if (frame.sequence == last_sequence) {
                report.accepted_duplicates++;
                report.status = INTEGRATION_PROCESS_READER_SEQUENCE_ERROR;
                break;
            }
            if (frame.sequence > (uint64_t)INTEGRATION_PROCESS_PUBLICATION_COUNT) {
                report.invalid_reads++;
                report.status = INTEGRATION_PROCESS_READER_SEQUENCE_ERROR;
                break;
            }
            last_sequence = frame.sequence;
            report.valid_reads++;
        } else if (outcome == FRAME_NO_NEW) {
            report.no_new_reads++;
        } else if (outcome == FRAME_UNSTABLE) {
            report.unstable_reads++;
        } else {
            /* A valid writer never emits a malformed/HMAC-invalid frame.  A
             * concurrent copy must be bounded as FRAME_UNSTABLE instead. */
            report.invalid_reads++;
            report.status = INTEGRATION_PROCESS_READER_INVALID_FRAME;
            break;
        }
        if (atomic_load_explicit(&control->publisher_done, memory_order_acquire) != 0
            && last_sequence == (uint64_t)INTEGRATION_PROCESS_PUBLICATION_COUNT) {
            break;
        }
        if ((attempt & 31u) == 0u) (void)sched_yield();
    }
    report.final_sequence = last_sequence;
    if (report.status == INTEGRATION_PROCESS_READER_OK
        && last_sequence != (uint64_t)INTEGRATION_PROCESS_PUBLICATION_COUNT) {
        report.status = INTEGRATION_PROCESS_READER_INCOMPLETE;
    }
    integration_snapshot_process_reader_diagnostics(&report, &diagnostics);
    integration_process_reader_exit(report_fd, &report);
}

static bool integration_wait_for_process_readers(
    const integration_process_stress_control_t *control, unsigned int expected) {
    uint64_t deadline = integration_deadline_after_ns(UINT64_C(2000000000));
    while (monotonic_ns() < deadline) {
        if (atomic_load_explicit(&control->readers_ready, memory_order_acquire) == expected)
            return true;
        if (atomic_load_explicit(&control->abort_requested, memory_order_acquire) != 0)
            return false;
        struct timespec pause = { .tv_sec = 0, .tv_nsec = 1000000L };
        (void)nanosleep(&pause, NULL);
    }
    return false;
}

static size_t integration_reap_process_children_until(
    const pid_t children[INTEGRATION_PROCESS_READER_COUNT],
    bool reaped[INTEGRATION_PROCESS_READER_COUNT],
    int statuses[INTEGRATION_PROCESS_READER_COUNT], uint64_t deadline_ns,
    bool *ok) {
    size_t remaining = 0;
    for (size_t index = 0; index < INTEGRATION_PROCESS_READER_COUNT; ++index)
        if (children[index] > 0 && !reaped[index]) remaining++;
    while (remaining > 0u && monotonic_ns() < deadline_ns) {
        bool made_progress = false;
        for (size_t index = 0; index < INTEGRATION_PROCESS_READER_COUNT; ++index) {
            if (children[index] <= 0 || reaped[index]) continue;
            pid_t result = waitpid(children[index], &statuses[index], WNOHANG);
            if (result == children[index]) {
                reaped[index] = true;
                remaining--;
                made_progress = true;
            } else if (result < 0 && errno != EINTR) {
                reaped[index] = true;
                remaining--;
                *ok = false;
                made_progress = true;
            }
        }
        if (remaining > 0u && !made_progress) {
            struct timespec pause = { .tv_sec = 0, .tv_nsec = 1000000L };
            (void)nanosleep(&pause, NULL);
        }
    }
    return remaining;
}

/* ORCHESTRA_UNIT_TEST intentionally retains the legacy reference functions
 * beside the selected generation transport.  Touch them here so this strict
 * integration build checks both canonical-frame encodings without weakening
 * -Werror for the included translation unit. */
static bool integration_test_reference_visibility(void) {
    legacy_signal_publication_t legacy;
    signal_reader_diagnostics_t diagnostics;
    uint8_t bytes[SIGNAL_FRAME_SIZE] = {0};
    uint8_t copied[SIGNAL_FRAME_SIZE] = {0};
    action_t actions[MAX_WORKERS] = {ACT_RUN};
    action_t previous[MAX_WORKERS] = {ACT_RUN};
    memset(&legacy, 0, sizeof(legacy));
    atomic_init(&legacy.publish_version, 0);
    for (size_t index = 0; index < SIGNAL_WIRE_SIZE; ++index)
        atomic_init(&legacy.wire[index], 0);
    for (size_t index = 0; index < HMAC_SIZE; ++index)
        atomic_init(&legacy.hmac[index], 0);
    initialize_signal_reader_diagnostics(&diagnostics);
    CHECK(legacy_publish_canonical_frame(&legacy, bytes) == SIGNAL_PUBLISH_OK);
    CHECK(legacy_copy_canonical_frame(&legacy, copied, &diagnostics)
          == SIGNAL_SNAPSHOT_COPIED);
    CHECK(memcmp(bytes, copied, sizeof(bytes)) == 0);
    CHECK(isfinite(population_utility_reference(actions, previous, 0, ACT_RUN)));
    return true;
}

static bool integration_readonly_fork_reader(signal_bus_t *bus,
                                              signal_reader_gates_t *gates,
                                              const uint8_t key[MASTER_KEY_SIZE],
                                              uint64_t expected_sequence) {
    int pipe_fds[2] = { -1, -1 };
    CHECK(pipe(pipe_fds) == 0);
    pid_t child = fork();
    CHECK(child >= 0);
    if (child == 0) {
        child_reader_report_t report = {
            .frame_result = FRAME_INVALID,
            .child_errno = 0,
            .sequence = 0,
        };
        (void)close(pipe_fds[0]);
        if (mprotect(bus, sizeof(*bus), PROT_READ) != 0) {
            report.child_errno = errno;
        } else {
            signal_payload_t out = {0};
            signal_reader_diagnostics_t diagnostics;
            initialize_signal_reader_diagnostics(&diagnostics);
            report.frame_result = read_verified_frame_with_diagnostics(
                bus, gates, key, 0, &out, &diagnostics);
            report.sequence = out.sequence;
        }
        ssize_t wrote = write(pipe_fds[1], &report, sizeof(report));
        (void)close(pipe_fds[1]);
        _exit(wrote == (ssize_t)sizeof(report) ? EXIT_SUCCESS : EXIT_FAILURE);
    }

    (void)close(pipe_fds[1]);
    int status = 0;
    bool reaped = integration_wait_child_bounded(child, &status);
    child_reader_report_t report = {0};
    ssize_t read_count = read(pipe_fds[0], &report, sizeof(report));
    (void)close(pipe_fds[0]);
    CHECK(reaped);
    CHECK(WIFEXITED(status));
    CHECK(WEXITSTATUS(status) == EXIT_SUCCESS);
    CHECK(read_count == (ssize_t)sizeof(report));
    CHECK(report.child_errno == 0);
    CHECK(report.frame_result == FRAME_VALID);
    CHECK(report.sequence == expected_sequence);
    return true;
}

static bool integration_test_readonly_mapping_and_contention(
    signal_bus_t *bus, signal_reader_gates_t *gates,
    const uint8_t key[MASTER_KEY_SIZE]) {
    integration_initialize_shared_bus(bus, gates);
    signal_payload_t first = integration_valid_payload(UINT64_C(100));
    signal_payload_t second = integration_valid_payload(UINT64_C(101));
    CHECK(publish_frame(bus, gates, &first, key, false) == SIGNAL_PUBLISH_OK);
    CHECK(integration_readonly_fork_reader(bus, gates, key, first.sequence));
    signal_payload_t direct_read = {0};
    CHECK(read_verified_frame(bus, gates, key, 0, &direct_read) == FRAME_VALID);
    CHECK(direct_read.sequence == first.sequence);

    size_t blocked_slot = integration_next_slot(bus);
    CHECK(signal_gate_try_lock_writer(gates, blocked_slot));
    CHECK(publish_frame(bus, gates, &second, key, false) == SIGNAL_PUBLISH_CONTENDED);
    CHECK(atomic_load_explicit(&bus->diagnostics.publication_contention,
                               memory_order_relaxed) == 1u);
    signal_gate_unlock_writer(gates, blocked_slot);
    return true;
}

static bool integration_test_retry_and_safe_outcomes(
    signal_bus_t *bus, signal_reader_gates_t *gates,
    const uint8_t key[MASTER_KEY_SIZE]) {
    integration_initialize_shared_bus(bus, gates);
    signal_payload_t payload = integration_valid_payload(UINT64_C(200));
    signal_payload_t accepted = {0};
    signal_reader_diagnostics_t diagnostics;
    initialize_signal_reader_diagnostics(&diagnostics);
    CHECK(publish_frame(bus, gates, &payload, key, false) == SIGNAL_PUBLISH_OK);
    CHECK(read_verified_frame_with_diagnostics(bus, gates, key, 0, &accepted,
                                               &diagnostics) == FRAME_VALID);
    CHECK(accepted.sequence == payload.sequence);

    size_t active_slot = integration_active_slot(bus);
    CHECK(signal_gate_try_lock_writer(gates, active_slot));
    signal_payload_t unstable = {0};
    CHECK(read_verified_frame_with_diagnostics(bus, gates, key, payload.sequence,
                                               &unstable, &diagnostics)
          == FRAME_UNSTABLE);
    CHECK(atomic_load_explicit(&diagnostics.retry_exhaustions, memory_order_relaxed)
          == 1u);
    CHECK(integration_classify_read(FRAME_UNSTABLE, true)
          == SAFE_DISPOSITION_RETAIN_LKG);
    CHECK(accepted.sequence == payload.sequence);
    CHECK(integration_classify_read(FRAME_UNSTABLE, false)
          == SAFE_DISPOSITION_OBSERVED_FALLBACK);
    signal_gate_unlock_writer(gates, active_slot);
    return true;
}

static bool integration_test_reader_death_during_copy(
    signal_bus_t *bus, signal_reader_gates_t *gates,
    const uint8_t key[MASTER_KEY_SIZE]) {
    integration_initialize_shared_bus(bus, gates);
    signal_payload_t payload = integration_valid_payload(UINT64_C(250));
    CHECK(publish_frame(bus, gates, &payload, key, false) == SIGNAL_PUBLISH_OK);
    g_integration_reader_stop_once = 0;
    g_signal_publication_test_hook = integration_stop_reader_between_token_and_words;
    pid_t child = fork();
    CHECK(child >= 0);
    if (child == 0) {
        if (mprotect(bus, sizeof(*bus), PROT_READ) != 0) _exit(EXIT_FAILURE);
        signal_payload_t partial = {0};
        /* The hook stops this child after token acquisition and before the
         * reader pin/word-copy path.  Reaching this line's return is failure. */
        (void)read_verified_frame_with_diagnostics(bus, gates, key, 0, &partial, NULL);
        _exit(EXIT_FAILURE);
    }

    int status = 0;
    bool stopped = integration_wait_child_stopped_bounded(child, &status);
    g_signal_publication_test_hook = NULL;
    CHECK(stopped);
    CHECK(WSTOPSIG(status) == SIGSTOP);
    CHECK(kill(child, SIGKILL) == 0);
    CHECK(integration_wait_child_bounded(child, &status));
    CHECK(WIFSIGNALED(status));
    CHECK(WTERMSIG(status) == SIGKILL);

    /* The child never pinned or copied a partial frame.  Its termination
     * leaves the active slot readable, and the parent accepts only a complete
     * canonical HMAC-protected frame. */
    size_t active_slot = integration_active_slot(bus);
    CHECK(atomic_load_explicit(&gates->access_state[active_slot].value,
                               memory_order_acquire) == 0u);
    signal_payload_t complete = {0};
    CHECK(read_verified_frame_with_diagnostics(bus, gates, key, 0, &complete, NULL)
          == FRAME_VALID);
    CHECK(complete.sequence == payload.sequence);
    return true;
}

static bool integration_test_reader_death_while_pinned(
    signal_bus_t *bus, signal_reader_gates_t *gates,
    const uint8_t key[MASTER_KEY_SIZE]) {
    integration_initialize_shared_bus(bus, gates);
    signal_payload_t first = integration_valid_payload(UINT64_C(260));
    signal_payload_t second = integration_valid_payload(UINT64_C(261));
    signal_payload_t third = integration_valid_payload(UINT64_C(262));
    signal_payload_t out = {0};
    CHECK(publish_frame(bus, gates, &first, key, false) == SIGNAL_PUBLISH_OK);
    CHECK(read_verified_frame_with_diagnostics(bus, gates, key, 0, &out, NULL)
          == FRAME_VALID);
    CHECK(out.sequence == first.sequence);

    g_integration_reader_stop_once = 0;
    g_signal_publication_test_hook = integration_stop_reader_while_pinned;
    pid_t child = fork();
    CHECK(child >= 0);
    if (child == 0) {
        if (mprotect(bus, sizeof(*bus), PROT_READ) != 0) _exit(EXIT_FAILURE);
        signal_payload_t child_out = {0};
        (void)read_verified_frame_with_diagnostics(bus, gates, key, 0, &child_out, NULL);
        _exit(EXIT_FAILURE);
    }

    int status = 0;
    bool stopped = integration_wait_child_stopped_bounded(child, &status);
    g_signal_publication_test_hook = NULL;
    CHECK(stopped);
    CHECK(WSTOPSIG(status) == SIGSTOP);
    CHECK(kill(child, SIGKILL) == 0);
    CHECK(integration_wait_child_bounded(child, &status));
    CHECK(WIFSIGNALED(status));
    CHECK(WTERMSIG(status) == SIGKILL);

    size_t pinned_slot = integration_active_slot(bus);
    CHECK(atomic_load_explicit(&gates->access_state[pinned_slot].value,
                               memory_order_acquire) == 1u);
    /* The first reuse goes to the alternate slot.  Reusing the leaked pinned
     * slot then fails within the publisher's bounded lock attempt. */
    CHECK(publish_frame(bus, gates, &second, key, false) == SIGNAL_PUBLISH_OK);
    CHECK(publish_frame(bus, gates, &third, key, false) == SIGNAL_PUBLISH_CONTENDED);
    CHECK(integration_classify_publication(SIGNAL_PUBLISH_CONTENDED, true)
          == SAFE_DISPOSITION_RETAIN_LKG);
    CHECK(integration_classify_publication(SIGNAL_PUBLISH_CONTENDED, false)
          == SAFE_DISPOSITION_OBSERVED_FALLBACK);
    CHECK(read_verified_frame_with_diagnostics(bus, gates, key, first.sequence, &out, NULL)
          == FRAME_VALID);
    CHECK(out.sequence == second.sequence);
    CHECK(read_verified_frame_with_diagnostics(bus, gates, key, second.sequence, &out, NULL)
          == FRAME_NO_NEW);
    CHECK(integration_classify_read(FRAME_NO_NEW, true)
          == SAFE_DISPOSITION_RETAIN_LKG);

    /* A cross-process reader death while pinned has no automatic lease
     * reclamation in this userspace prototype.  This explicit, test-only reset
     * documents that liveness limitation rather than treating it as recovery.
     * Production behavior remains bounded publication contention plus safe
     * last-known-good retention or observed-state fallback. */
    atomic_store_explicit(&gates->access_state[pinned_slot].value, 0,
                          memory_order_release);
    CHECK(publish_frame(bus, gates, &third, key, false) == SIGNAL_PUBLISH_OK);
    CHECK(read_verified_frame_with_diagnostics(bus, gates, key, second.sequence, &out, NULL)
          == FRAME_VALID);
    CHECK(out.sequence == third.sequence);
    return true;
}

static bool integration_test_multiprocess_high_frequency_stress(
    signal_bus_t *bus, signal_reader_gates_t *gates,
    const uint8_t key[MASTER_KEY_SIZE]) {
    integration_process_stress_control_t *control = mmap(
        NULL, sizeof(*control), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (control == MAP_FAILED) {
        perror("mmap process stress control");
        return false;
    }
    integration_initialize_shared_bus(bus, gates);
    integration_initialize_process_stress_control(control);
    int report_pipes[INTEGRATION_PROCESS_READER_COUNT][2];
    pid_t children[INTEGRATION_PROCESS_READER_COUNT];
    bool reaped[INTEGRATION_PROCESS_READER_COUNT] = {false};
    int statuses[INTEGRATION_PROCESS_READER_COUNT] = {0};
    for (size_t index = 0; index < INTEGRATION_PROCESS_READER_COUNT; ++index) {
        report_pipes[index][0] = -1;
        report_pipes[index][1] = -1;
        children[index] = -1;
    }

    bool ok = true;
    size_t child_count = 0;
    g_integration_process_stress_control = control;
    g_signal_publication_test_hook = integration_process_stress_hook;
    for (size_t index = 0; index < INTEGRATION_PROCESS_READER_COUNT; ++index) {
        if (pipe(report_pipes[index]) != 0) {
            ok = false;
            break;
        }
        pid_t child = fork();
        if (child < 0) {
            (void)close(report_pipes[index][0]);
            (void)close(report_pipes[index][1]);
            report_pipes[index][0] = -1;
            report_pipes[index][1] = -1;
            ok = false;
            break;
        }
        if (child == 0) {
            for (size_t prior = 0; prior <= index; ++prior) {
                if (report_pipes[prior][0] >= 0)
                    (void)close(report_pipes[prior][0]);
                if (prior != index && report_pipes[prior][1] >= 0)
                    (void)close(report_pipes[prior][1]);
            }
            integration_process_reader(bus, gates, control, key, report_pipes[index][1]);
        }
        children[index] = child;
        child_count++;
        (void)close(report_pipes[index][1]);
        report_pipes[index][1] = -1;
    }

    bool readers_ready = ok && child_count == INTEGRATION_PROCESS_READER_COUNT
                      && integration_wait_for_process_readers(
                          control, INTEGRATION_PROCESS_READER_COUNT);
    if (!readers_ready) {
        ok = false;
        atomic_store_explicit(&control->abort_requested, 1, memory_order_release);
    }
    /* Releasing all forked readers together gives the parent writer a
     * production-like multi-process reader population while every reader's
     * canonical bus mapping is already PROT_READ. */
    atomic_store_explicit(&control->start, 1, memory_order_release);

    uint64_t publisher_successes = 0;
    if (readers_ready) {
        for (uint64_t sequence = 1;
             sequence <= (uint64_t)INTEGRATION_PROCESS_PUBLICATION_COUNT; ++sequence) {
            signal_payload_t payload = integration_valid_payload(sequence);
            bool published = false;
            for (unsigned int attempt = 0;
                 attempt < INTEGRATION_PROCESS_PUBLISH_RETRY_LIMIT; ++attempt) {
                signal_publish_result_t outcome = publish_frame(bus, gates, &payload, key,
                                                                 false);
                if (outcome == SIGNAL_PUBLISH_OK) {
                    published = true;
                    publisher_successes++;
                    break;
                }
                if (outcome == SIGNAL_PUBLISH_CONTENDED) {
                    (void)sched_yield();
                    continue;
                }
                ok = false;
                break;
            }
            if (!published) {
                ok = false;
                atomic_store_explicit(&control->abort_requested, 1,
                                      memory_order_release);
                break;
            }
            /* This explicit bounded yield supplements the deterministic hook
             * yields and makes repeated alternating-slot reuse observable to
             * already-started reader processes on a lightly loaded host. */
            if ((sequence & UINT64_C(31)) == 0u) (void)sched_yield();
        }
    }
    atomic_store_explicit(&control->publisher_done, 1, memory_order_release);

    size_t remaining = integration_reap_process_children_until(
        children, reaped, statuses, integration_deadline_after_ns(UINT64_C(5000000000)), &ok);
    unsigned int reader_hangs = 0;
    if (remaining > 0u) {
        ok = false;
        reader_hangs = (unsigned int)remaining;
        atomic_store_explicit(&control->abort_requested, 1, memory_order_release);
        for (size_t index = 0; index < INTEGRATION_PROCESS_READER_COUNT; ++index) {
            if (children[index] > 0 && !reaped[index]
                && kill(children[index], SIGKILL) != 0 && errno != ESRCH) {
                ok = false;
            }
        }
        remaining = integration_reap_process_children_until(
            children, reaped, statuses,
            integration_deadline_after_ns(UINT64_C(1000000000)), &ok);
        if (remaining > 0u) {
            /* Do not continue to other integration cases while a child may
             * retain a shared gate.  The outer timeout remains a final bound. */
            fprintf(stderr, "FAIL process publication stress: child reap timeout\n");
            _Exit(EXIT_FAILURE);
        }
    }
    g_signal_publication_test_hook = NULL;
    g_integration_process_stress_control = NULL;

    uint64_t total_read_attempts = 0;
    uint64_t total_verified_reads = 0;
    uint64_t total_retries = 0;
    uint64_t total_retry_exhaustions = 0;
    uint64_t total_unstable_reads = 0;
    uint64_t total_invalid_reads = 0;
    uint64_t total_hmac_failures = 0;
    uint64_t total_invalid_fields = 0;
    uint64_t total_invalid_schema = 0;
    uint64_t total_invalid_tier = 0;
    uint64_t total_invalid_source = 0;
    uint64_t total_invalid_directive = 0;
    uint64_t total_invalid_sequence = 0;
    uint64_t total_invalid_key_epochs = 0;
    uint64_t total_stale_frames = 0;
    uint64_t total_regressions = 0;
    uint64_t total_duplicates = 0;
    unsigned int reader_crashes = 0;
    for (size_t index = 0; index < child_count; ++index) {
        integration_process_reader_report_t report = {0};
        ssize_t read_count = read(report_pipes[index][0], &report, sizeof(report));
        (void)close(report_pipes[index][0]);
        report_pipes[index][0] = -1;
        bool child_clean = reaped[index] && WIFEXITED(statuses[index])
                        && WEXITSTATUS(statuses[index]) == EXIT_SUCCESS
                        && read_count == (ssize_t)sizeof(report)
                        && report.status == INTEGRATION_PROCESS_READER_OK;
        if (!child_clean) reader_crashes++;
        total_read_attempts += report.read_attempts;
        total_verified_reads += report.verified_reads;
        total_retries += report.retries;
        total_retry_exhaustions += report.retry_exhaustions;
        total_unstable_reads += report.unstable_reads;
        total_invalid_reads += report.invalid_reads;
        total_hmac_failures += report.hmac_failures;
        total_invalid_fields += report.invalid_fields;
        total_invalid_schema += report.invalid_schema;
        total_invalid_tier += report.invalid_tier;
        total_invalid_source += report.invalid_source;
        total_invalid_directive += report.invalid_directive;
        total_invalid_sequence += report.invalid_sequence;
        total_invalid_key_epochs += report.invalid_key_epochs;
        total_stale_frames += report.stale_frames;
        total_regressions += report.sequence_regressions;
        total_duplicates += report.accepted_duplicates;
        printf("process-reader=%zu status=%d attempts=%" PRIu64
               " valid=%" PRIu64 " verified=%" PRIu64
               " retries=%" PRIu64 " retry-exhaustions=%" PRIu64
               " unstable=%" PRIu64 " invalid=%" PRIu64
               " hmac=%" PRIu64 " regressions=%" PRIu64
               " duplicates=%" PRIu64 " final=%" PRIu64 "\n",
               index, report.status, report.read_attempts, report.valid_reads,
               report.verified_reads, report.retries, report.retry_exhaustions,
               report.unstable_reads, report.invalid_reads, report.hmac_failures,
               report.sequence_regressions, report.accepted_duplicates,
               report.final_sequence);
        ok = ok && child_clean && report.valid_reads > 0u
             && report.final_sequence == (uint64_t)INTEGRATION_PROCESS_PUBLICATION_COUNT
             && report.invalid_reads == 0u && report.hmac_failures == 0u
             && report.invalid_fields == 0u && report.invalid_schema == 0u
             && report.invalid_tier == 0u && report.invalid_source == 0u
             && report.invalid_directive == 0u && report.invalid_sequence == 0u
             && report.invalid_key_epochs == 0u && report.stale_frames == 0u
             && report.sequence_regressions == 0u && report.accepted_duplicates == 0u;
    }
    for (size_t index = child_count; index < INTEGRATION_PROCESS_READER_COUNT; ++index) {
        if (report_pipes[index][0] >= 0) (void)close(report_pipes[index][0]);
        if (report_pipes[index][1] >= 0) (void)close(report_pipes[index][1]);
    }

    uint64_t publisher_attempts = atomic_load_explicit(
        &bus->diagnostics.publication_attempts, memory_order_relaxed);
    uint64_t publisher_contention = atomic_load_explicit(
        &bus->diagnostics.publication_contention, memory_order_relaxed);
    uint64_t recorded_publications = atomic_load_explicit(
        &bus->diagnostics.publications, memory_order_relaxed);
    uint64_t final_token = atomic_load_explicit(
        &bus->publication.publication_token.value, memory_order_acquire);
    uint64_t final_generation = final_token >> SIGNAL_TOKEN_GENERATION_SHIFT;
    size_t expected_slot = (INTEGRATION_PROCESS_PUBLICATION_COUNT & 1u) == 0u ? 1u : 0u;
    size_t final_slot = (size_t)(final_token & SIGNAL_TOKEN_SLOT_MASK);
    printf("process-stress-summary publisher-success=%" PRIu64
           " publisher-attempts=%" PRIu64 " publisher-contention=%" PRIu64
           " read-attempts=%" PRIu64 " verified=%" PRIu64
           " retries=%" PRIu64 " retry-exhaustions=%" PRIu64
           " unstable=%" PRIu64 " invalid=%" PRIu64 " hmac=%" PRIu64
           " invalid-fields=%" PRIu64 " invalid-schema=%" PRIu64
           " invalid-tier=%" PRIu64 " invalid-source=%" PRIu64
           " invalid-directive=%" PRIu64 " invalid-sequence=%" PRIu64
           " invalid-key-epoch=%" PRIu64 " stale=%" PRIu64
           " torn-frame-detections=%" PRIu64 " regressions=%" PRIu64
           " accepted-duplicates=%" PRIu64 " reader-crashes=%u reader-hangs=%u"
           " hook-yields=%" PRIu64 " final-generation=%" PRIu64
           " final-slot=%zu\n",
           publisher_successes, publisher_attempts, publisher_contention,
           total_read_attempts, total_verified_reads, total_retries,
           total_retry_exhaustions, total_unstable_reads, total_invalid_reads,
           total_hmac_failures, total_invalid_fields, total_invalid_schema,
           total_invalid_tier, total_invalid_source, total_invalid_directive,
           total_invalid_sequence, total_invalid_key_epochs, total_stale_frames,
           total_invalid_reads, total_regressions, total_duplicates, reader_crashes,
           reader_hangs, atomic_load_explicit(&control->hook_yields,
                                              memory_order_relaxed),
           final_generation, final_slot);
    ok = ok && child_count == INTEGRATION_PROCESS_READER_COUNT
         && publisher_successes == (uint64_t)INTEGRATION_PROCESS_PUBLICATION_COUNT
         && recorded_publications == publisher_successes
         && publisher_attempts >= publisher_successes
         && final_generation == (uint64_t)INTEGRATION_PROCESS_PUBLICATION_COUNT
         && final_slot == expected_slot
         && total_invalid_reads == 0u && total_hmac_failures == 0u
         && total_invalid_fields == 0u && total_invalid_schema == 0u
         && total_invalid_tier == 0u && total_invalid_source == 0u
         && total_invalid_directive == 0u && total_invalid_sequence == 0u
         && total_invalid_key_epochs == 0u && total_stale_frames == 0u
         && total_regressions == 0u && total_duplicates == 0u
         && reader_crashes == 0u && reader_hangs == 0u
         && atomic_load_explicit(&control->hook_yields, memory_order_relaxed) > 0u;
    if (munmap(control, sizeof(*control)) != 0) ok = false;
    return ok;
}

static bool integration_test_publisher_death_recovery(
    signal_bus_t *bus, signal_reader_gates_t *gates,
    const uint8_t key[MASTER_KEY_SIZE]) {
    integration_initialize_shared_bus(bus, gates);
    signal_payload_t first = integration_valid_payload(UINT64_C(300));
    signal_payload_t recovered = integration_valid_payload(UINT64_C(301));
    signal_payload_t out = {0};
    CHECK(publish_frame(bus, gates, &first, key, false) == SIGNAL_PUBLISH_OK);
    CHECK(read_verified_frame_with_diagnostics(bus, gates, key, 0, &out, NULL)
          == FRAME_VALID);
    CHECK(out.sequence == first.sequence);

    size_t target_slot = integration_next_slot(bus);
    pid_t child = fork();
    CHECK(child >= 0);
    if (child == 0) {
        if (!signal_gate_try_lock_writer(gates, target_slot)) _exit(EXIT_FAILURE);
        uint64_t token = atomic_load_explicit(&bus->publication.publication_token.value,
                                              memory_order_acquire);
        uint64_t next_generation = (token >> SIGNAL_TOKEN_GENERATION_SHIFT)
                                 + UINT64_C(1);
        uint64_t odd_sequence = (next_generation << SIGNAL_TOKEN_GENERATION_SHIFT)
                              | UINT64_C(1);
        atomic_store_explicit(&bus->publication.slot[target_slot].sequence.value,
                              odd_sequence, memory_order_release);
        /* Simulates publisher death after the writer lease/odd generation. */
        _exit(EXIT_SUCCESS);
    }

    int status = 0;
    CHECK(integration_wait_child_bounded(child, &status));
    CHECK(WIFEXITED(status));
    CHECK(WEXITSTATUS(status) == EXIT_SUCCESS);
    CHECK((atomic_load_explicit(&gates->access_state[target_slot].value,
                                memory_order_acquire) & SIGNAL_SLOT_WRITER_LOCK) != 0u);
    CHECK((atomic_load_explicit(&bus->publication.slot[target_slot].sequence.value,
                                memory_order_acquire) & UINT64_C(1)) != 0u);

    CHECK(publish_frame(bus, gates, &recovered, key, false) == SIGNAL_PUBLISH_CONTENDED);
    CHECK(read_verified_frame_with_diagnostics(bus, gates, key, first.sequence, &out, NULL)
          == FRAME_NO_NEW);
    CHECK(integration_classify_read(FRAME_NO_NEW, true)
          == SAFE_DISPOSITION_RETAIN_LKG);

    /* Test-only recovery releases an orphaned lease, then verifies a clean
     * publication and accepted HMAC-protected frame. */
    signal_gate_unlock_writer(gates, target_slot);
    CHECK(publish_frame(bus, gates, &recovered, key, false) == SIGNAL_PUBLISH_OK);
    CHECK(read_verified_frame_with_diagnostics(bus, gates, key, first.sequence, &out, NULL)
          == FRAME_VALID);
    CHECK(out.sequence == recovered.sequence);
    return true;
}

int main(void) {
#if ORCHESTRA_SIGNAL_PUBLICATION_LEGACY
#error "signal publication integration coverage requires the generation transport"
#endif
    signal_bus_t *bus = mmap(NULL, sizeof(*bus), PROT_READ | PROT_WRITE,
                             MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    signal_reader_gates_t *gates = mmap(NULL, sizeof(*gates), PROT_READ | PROT_WRITE,
                                        MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (bus == MAP_FAILED || gates == MAP_FAILED) {
        perror("mmap");
        if (bus != MAP_FAILED) (void)munmap(bus, sizeof(*bus));
        if (gates != MAP_FAILED) (void)munmap(gates, sizeof(*gates));
        return EXIT_FAILURE;
    }

    uint8_t key[MASTER_KEY_SIZE];
    integration_fill_key(key);
    integration_initialize_shared_bus(bus, gates);
    bool ok = selected_signal_publication_atomics_are_lock_free(&bus->publication)
           && atomic_is_lock_free(&gates->access_state[0].value)
           && atomic_is_lock_free(&gates->access_state[1].value)
           && integration_test_reference_visibility()
           && integration_test_readonly_mapping_and_contention(bus, gates, key)
           && integration_test_retry_and_safe_outcomes(bus, gates, key)
           && integration_test_reader_death_during_copy(bus, gates, key)
           && integration_test_reader_death_while_pinned(bus, gates, key)
           && integration_test_multiprocess_high_frequency_stress(bus, gates, key)
           && integration_test_publisher_death_recovery(bus, gates, key);
    explicit_bzero(key, sizeof(key));
    if (munmap(bus, sizeof(*bus)) != 0) ok = false;
    if (munmap(gates, sizeof(*gates)) != 0) ok = false;
    if (!ok) return EXIT_FAILURE;
    printf("PASS signal publication MAP_SHARED integration scenarios\n");
    return EXIT_SUCCESS;
}
