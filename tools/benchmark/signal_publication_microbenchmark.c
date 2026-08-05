/*
 * Bounded ORCHESTRA signal-publication microbenchmark.
 *
 * This is an isolated measurement harness, not a scheduler benchmark and not
 * part of the canonical userspace experiment output.  It compiles the
 * canonical publication implementation in either reference legacy mode or
 * generation-stamped mode, then exercises one publisher and bounded reader
 * threads through the same authenticated publish/read APIs.
 */

#define main orchestra_demo_main
#include "../../orchestra_paper_cpu_demo/orchestra_paper_cpu.c"
#undef main

#include <pthread.h>

#define MICROBENCH_SCHEMA_ID "orchestra.signal_publication.microbenchmark/v1"
#define MICROBENCH_MAX_READERS 16
#define MICROBENCH_MAX_ITERATIONS UINT64_C(200000)
#define MICROBENCH_MAX_WARMUP UINT64_C(10000)
#define MICROBENCH_MAX_RUNTIME_MS UINT64_C(10000)
#define MICROBENCH_MAX_STARTUP_TIMEOUT_MS UINT64_C(5000)
#define MICROBENCH_MAX_DRAIN_READS UINT64_C(128)
#define MICROBENCH_JOIN_TIMEOUT_MS UINT64_C(1000)

#if ORCHESTRA_SIGNAL_PUBLICATION_LEGACY
#define MICROBENCH_PUBLICATION_MODE "legacy"
#else
#define MICROBENCH_PUBLICATION_MODE "generation_stamped"
#endif

typedef struct {
    int readers;
    uint64_t iterations;
    uint64_t warmup_iterations;
    uint64_t seed;
    uint64_t startup_timeout_ms;
    uint64_t max_runtime_ms;
    uint64_t drain_reads;
} microbench_config_t;

typedef struct {
    uint64_t snapshot_copy_attempts;
    uint64_t snapshot_copy_successes;
    uint64_t snapshot_copy_empty;
    uint64_t snapshot_copy_unstable;
    uint64_t snapshot_copy_latency_sum_ns;
    uint64_t snapshot_copy_latency_max_ns;
    uint64_t api_calls;
    uint64_t valid_reads;
    uint64_t no_new_reads;
    uint64_t unstable_reads;
    uint64_t invalid_reads;
    uint64_t api_latency_sum_ns;
    uint64_t api_latency_max_ns;
    uint64_t verified_frame_latency_sum_ns;
    uint64_t verified_frame_latency_max_ns;
    uint64_t elapsed_ns;
    bool deadline_exit;
    signal_reader_diagnostics_t diagnostics;
} reader_measurement_t;

typedef struct {
    signal_bus_t bus;
    signal_reader_gates_t gates;
    uint8_t master_key[MASTER_KEY_SIZE];
    _Atomic bool start_readers;
    _Atomic bool writer_done;
    _Atomic bool abort_requested;
    _Atomic bool clock_failed;
    _Atomic unsigned int readers_ready;
    uint64_t startup_deadline_ns;
    uint64_t measurement_deadline_ns;
    uint64_t drain_reads;
    reader_measurement_t readers[MICROBENCH_MAX_READERS];
} microbench_state_t;

typedef struct {
    microbench_state_t *state;
    int reader_index;
} reader_thread_arg_t;

typedef struct {
    uint64_t attempts;
    uint64_t successes;
    uint64_t contended;
    uint64_t generation_exhausted;
    uint64_t latency_sum_ns;
    uint64_t latency_max_ns;
    uint64_t elapsed_ns;
    bool deadline_exhausted;
} publisher_measurement_t;

typedef struct {
    uint64_t snapshot_copy_attempts;
    uint64_t snapshot_copy_successes;
    uint64_t snapshot_copy_empty;
    uint64_t snapshot_copy_unstable;
    uint64_t snapshot_copy_latency_sum_ns;
    uint64_t snapshot_copy_latency_max_ns;
    uint64_t api_calls;
    uint64_t valid_reads;
    uint64_t no_new_reads;
    uint64_t unstable_reads;
    uint64_t invalid_reads;
    uint64_t api_latency_sum_ns;
    uint64_t api_latency_max_ns;
    uint64_t verified_frame_latency_sum_ns;
    uint64_t verified_frame_latency_max_ns;
    uint64_t elapsed_sum_ns;
    uint64_t elapsed_max_ns;
    uint64_t deadline_exits;
    uint64_t diagnostic_read_attempts;
    uint64_t diagnostic_verified_reads;
    uint64_t diagnostic_retries;
    uint64_t diagnostic_retry_exhaustions;
    uint64_t diagnostic_unstable_slots;
    uint64_t diagnostic_hmac_failures;
    uint64_t diagnostic_invalid_fields;
    uint64_t diagnostic_invalid_schema;
    uint64_t diagnostic_invalid_tier;
    uint64_t diagnostic_invalid_source;
    uint64_t diagnostic_invalid_directive;
    uint64_t diagnostic_invalid_sequence;
    uint64_t diagnostic_stale_frames;
    uint64_t diagnostic_invalid_key_epochs;
} aggregate_reader_measurement_t;

static void microbench_usage(const char *program) {
    fprintf(stderr,
            "Usage: %s [options]\n"
            "  --readers N             reader threads, 1..%d (default 1)\n"
            "  --iterations N          measured publisher attempts, 100..%llu (default 5000)\n"
            "  --warmup N              unmeasured publications, 0..%llu (default 100)\n"
            "  --seed N                deterministic payload/key seed (default 1)\n"
            "  --startup-timeout-ms N  bounded thread-start wait, 10..%llu (default 1000)\n"
            "  --max-runtime-ms N      bounded measured window, 100..%llu (default 3000)\n"
            "  --drain-reads N         bounded reads after writer completion, 0..%llu (default 4)\n",
            program, MICROBENCH_MAX_READERS,
            (unsigned long long)MICROBENCH_MAX_ITERATIONS,
            (unsigned long long)MICROBENCH_MAX_WARMUP,
            (unsigned long long)MICROBENCH_MAX_STARTUP_TIMEOUT_MS,
            (unsigned long long)MICROBENCH_MAX_RUNTIME_MS,
            (unsigned long long)MICROBENCH_MAX_DRAIN_READS);
}

static bool microbench_parse_u64(const char *text, uint64_t minimum,
                                 uint64_t maximum, uint64_t *out) {
    if (text == NULL || *text == '\0' || *text == '-') return false;
    errno = 0;
    char *end = NULL;
    unsigned long long parsed = strtoull(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0') return false;
    uint64_t value = (uint64_t)parsed;
    if (value < minimum || value > maximum) return false;
    *out = value;
    return true;
}

static bool microbench_now_ns(uint64_t *out) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0 || now.tv_sec < 0) return false;
    uint64_t seconds = (uint64_t)now.tv_sec;
    if (seconds > UINT64_MAX / UINT64_C(1000000000)) return false;
    *out = seconds * UINT64_C(1000000000) + (uint64_t)now.tv_nsec;
    return true;
}

static bool microbench_deadline_after(uint64_t start_ns, uint64_t duration_ms,
                                      uint64_t *deadline_ns) {
    if (duration_ms > UINT64_MAX / UINT64_C(1000000)) return false;
    uint64_t duration_ns = duration_ms * UINT64_C(1000000);
    if (start_ns > UINT64_MAX - duration_ns) return false;
    *deadline_ns = start_ns + duration_ns;
    return true;
}

static uint64_t microbench_elapsed_ns(uint64_t before_ns, uint64_t after_ns) {
    return after_ns >= before_ns ? after_ns - before_ns : 0;
}

static uint64_t microbench_saturating_add(uint64_t left, uint64_t right) {
    return left > UINT64_MAX - right ? UINT64_MAX : left + right;
}

static void microbench_record_latency(uint64_t elapsed_ns, uint64_t *sum_ns,
                                      uint64_t *max_ns) {
    *sum_ns = microbench_saturating_add(*sum_ns, elapsed_ns);
    if (elapsed_ns > *max_ns) *max_ns = elapsed_ns;
}

static void microbench_make_key(uint64_t seed, uint8_t key[MASTER_KEY_SIZE]) {
    for (size_t index = 0; index < MASTER_KEY_SIZE; ++index) {
        unsigned int shift = (unsigned int)((index % 8u) * 8u);
        uint64_t lane = seed >> shift;
        key[index] = (uint8_t)(lane ^ (uint64_t)(UINT8_C(0x5a) + (uint8_t)index));
    }
}

static bool microbench_make_payload(uint64_t sequence, uint64_t seed,
                                    signal_payload_t *payload) {
    uint64_t now_ns = 0;
    if (!microbench_now_ns(&now_ns)) return false;
    uint64_t sequence_component = (sequence + (seed % UINT64_C(1000))) % UINT64_C(1000);
    double utilization = (double)sequence_component / 1000.0;
    *payload = (signal_payload_t){
        .magic = SIGNAL_MAGIC,
        .schema_version = SIGNAL_SCHEMA_VERSION,
        .tier = SIGNAL_TIER_CORE_LOCAL,
        .source_id = SIGNAL_SOURCE_LOCAL,
        .sequence = sequence,
        .monotonic_ns = now_ns,
        .max_age_ns = UINT64_C(5000000000),
        .key_epoch = (uint32_t)(sequence / KEY_EPOCH_TICKS),
        .directive = ACT_RUN,
        .state_schema_version = STATE_SCHEMA_VERSION,
        .prediction_used = 1u,
        .cpu_now = utilization,
        .cpu_pred = utilization,
        .decision_cpu = utilization,
        .memory_pressure = 0.20,
        .thermal_proxy = 0.10,
        .confidence = 1.0,
        .jitter_sigma = 0.02,
        .switch_penalty = 0.0,
        .consensus_blend = 0.0,
    };
    return true;
}

static void microbench_initialize_state(microbench_state_t *state,
                                        const microbench_config_t *config) {
    memset(state, 0, sizeof(*state));
    initialize_selected_signal_publication(&state->bus.publication);
    initialize_signal_publisher_diagnostics(&state->bus.diagnostics);
    initialize_signal_reader_gates(&state->gates);
    atomic_init(&state->bus.consensus_lock, 0);
    atomic_init(&state->bus.stop, 0);
    atomic_init(&state->start_readers, false);
    atomic_init(&state->writer_done, false);
    atomic_init(&state->abort_requested, false);
    atomic_init(&state->clock_failed, false);
    atomic_init(&state->readers_ready, 0u);
    state->drain_reads = config->drain_reads;
    microbench_make_key(config->seed, state->master_key);
    for (int reader = 0; reader < config->readers; ++reader)
        initialize_signal_reader_diagnostics(&state->readers[reader].diagnostics);
}

static void microbench_reset_publisher_diagnostics(signal_bus_t *bus) {
    atomic_store_explicit(&bus->diagnostics.publication_attempts, 0, memory_order_relaxed);
    atomic_store_explicit(&bus->diagnostics.publications, 0, memory_order_relaxed);
    atomic_store_explicit(&bus->diagnostics.publication_contention, 0, memory_order_relaxed);
    atomic_store_explicit(&bus->diagnostics.generation_exhaustions, 0,
                          memory_order_relaxed);
}

static bool microbench_publish_warmup(microbench_state_t *state,
                                      const microbench_config_t *config,
                                      uint64_t *next_sequence) {
    for (uint64_t iteration = 0; iteration < config->warmup_iterations; ++iteration) {
        signal_payload_t payload;
        if (!microbench_make_payload(*next_sequence, config->seed, &payload)) return false;
        signal_publish_result_t result = publish_frame(&state->bus, &state->gates,
                                                       &payload, state->master_key, false);
        if (result != SIGNAL_PUBLISH_OK) return false;
        if (*next_sequence == UINT64_MAX) return false;
        *next_sequence += UINT64_C(1);
    }
    microbench_reset_publisher_diagnostics(&state->bus);
    return true;
}

/* This separately measures only a coherent immutable-byte snapshot.  It does
 * not deserialize or authenticate the bytes, so its timing is deliberately
 * not reported as complete frame verification time. */
static bool microbench_snapshot_copy_once(microbench_state_t *state,
                                          reader_measurement_t *measurement) {
    uint8_t bytes[SIGNAL_FRAME_SIZE];
    uint64_t before_ns = 0;
    uint64_t after_ns = 0;
    if (!microbench_now_ns(&before_ns)) return false;
    signal_snapshot_result_t result = selected_copy_canonical_frame(
        &state->bus, &state->gates, bytes, NULL);
    if (!microbench_now_ns(&after_ns)) return false;
    measurement->snapshot_copy_attempts = microbench_saturating_add(
        measurement->snapshot_copy_attempts, 1);
    if (result == SIGNAL_SNAPSHOT_COPIED) {
        measurement->snapshot_copy_successes = microbench_saturating_add(
            measurement->snapshot_copy_successes, 1);
        microbench_record_latency(microbench_elapsed_ns(before_ns, after_ns),
                                  &measurement->snapshot_copy_latency_sum_ns,
                                  &measurement->snapshot_copy_latency_max_ns);
    } else if (result == SIGNAL_SNAPSHOT_EMPTY) {
        measurement->snapshot_copy_empty = microbench_saturating_add(
            measurement->snapshot_copy_empty, 1);
    } else {
        measurement->snapshot_copy_unstable = microbench_saturating_add(
            measurement->snapshot_copy_unstable, 1);
    }
    return true;
}

/* A completed verified-frame timing is recorded only for FRAME_VALID.  The
 * full API timing below remains useful for retry/no-new overhead, but
 * FRAME_NO_NEW deliberately returns before HMAC verification. */
static bool microbench_reader_once(microbench_state_t *state,
                                   reader_measurement_t *measurement,
                                   uint64_t *last_sequence) {
    uint64_t before_ns = 0;
    uint64_t after_ns = 0;
    if (!microbench_now_ns(&before_ns)) return false;
    signal_payload_t frame;
    frame_read_result_t result = read_verified_frame_with_diagnostics(
        &state->bus, &state->gates, state->master_key, *last_sequence, &frame,
        &measurement->diagnostics);
    if (!microbench_now_ns(&after_ns)) return false;
    measurement->api_calls = microbench_saturating_add(measurement->api_calls, 1);
    microbench_record_latency(microbench_elapsed_ns(before_ns, after_ns),
                              &measurement->api_latency_sum_ns,
                              &measurement->api_latency_max_ns);
    switch (result) {
        case FRAME_VALID:
            measurement->valid_reads = microbench_saturating_add(measurement->valid_reads, 1);
            microbench_record_latency(microbench_elapsed_ns(before_ns, after_ns),
                                      &measurement->verified_frame_latency_sum_ns,
                                      &measurement->verified_frame_latency_max_ns);
            *last_sequence = frame.sequence;
            break;
        case FRAME_NO_NEW:
            measurement->no_new_reads = microbench_saturating_add(measurement->no_new_reads, 1);
            break;
        case FRAME_UNSTABLE:
            measurement->unstable_reads = microbench_saturating_add(measurement->unstable_reads, 1);
            break;
        case FRAME_INVALID:
            measurement->invalid_reads = microbench_saturating_add(measurement->invalid_reads, 1);
            break;
        default:
            measurement->invalid_reads = microbench_saturating_add(measurement->invalid_reads, 1);
            break;
    }
    return true;
}

static bool microbench_reader_cycle(microbench_state_t *state,
                                    reader_measurement_t *measurement,
                                    uint64_t *last_sequence) {
    return microbench_snapshot_copy_once(state, measurement)
        && microbench_reader_once(state, measurement, last_sequence);
}

static void *microbench_reader_main(void *opaque) {
    reader_thread_arg_t *argument = opaque;
    microbench_state_t *state = argument->state;
    reader_measurement_t *measurement = &state->readers[argument->reader_index];
    atomic_fetch_add_explicit(&state->readers_ready, 1u, memory_order_release);

    for (;;) {
        if (atomic_load_explicit(&state->abort_requested, memory_order_acquire)) return NULL;
        if (atomic_load_explicit(&state->start_readers, memory_order_acquire)) break;
        uint64_t now_ns = 0;
        if (!microbench_now_ns(&now_ns)) {
            atomic_store_explicit(&state->clock_failed, true, memory_order_release);
            return NULL;
        }
        if (now_ns >= state->startup_deadline_ns) {
            measurement->deadline_exit = true;
            return NULL;
        }
        (void)sched_yield();
    }

    uint64_t start_ns = 0;
    if (!microbench_now_ns(&start_ns)) {
        atomic_store_explicit(&state->clock_failed, true, memory_order_release);
        return NULL;
    }
    uint64_t last_sequence = 0;
    while (!atomic_load_explicit(&state->writer_done, memory_order_acquire)
           && !atomic_load_explicit(&state->abort_requested, memory_order_acquire)) {
        uint64_t now_ns = 0;
        if (!microbench_now_ns(&now_ns)) {
            atomic_store_explicit(&state->clock_failed, true, memory_order_release);
            break;
        }
        if (now_ns >= state->measurement_deadline_ns) {
            measurement->deadline_exit = true;
            break;
        }
        if (!microbench_reader_cycle(state, measurement, &last_sequence)) {
            atomic_store_explicit(&state->clock_failed, true, memory_order_release);
            break;
        }
    }
    for (uint64_t drain = 0; drain < state->drain_reads
                          && !atomic_load_explicit(&state->abort_requested,
                                                   memory_order_acquire);
         ++drain) {
        uint64_t now_ns = 0;
        if (!microbench_now_ns(&now_ns)) {
            atomic_store_explicit(&state->clock_failed, true, memory_order_release);
            break;
        }
        if (now_ns >= state->measurement_deadline_ns) break;
        if (!microbench_reader_cycle(state, measurement, &last_sequence)) {
            atomic_store_explicit(&state->clock_failed, true, memory_order_release);
            break;
        }
    }
    uint64_t end_ns = 0;
    if (!microbench_now_ns(&end_ns)) {
        atomic_store_explicit(&state->clock_failed, true, memory_order_release);
        return NULL;
    }
    measurement->elapsed_ns = microbench_elapsed_ns(start_ns, end_ns);
    return NULL;
}

static bool microbench_wait_for_readers(microbench_state_t *state, int readers) {
    for (;;) {
        unsigned int ready = atomic_load_explicit(&state->readers_ready, memory_order_acquire);
        if (ready == (unsigned int)readers) return true;
        uint64_t now_ns = 0;
        if (!microbench_now_ns(&now_ns)) {
            atomic_store_explicit(&state->clock_failed, true, memory_order_release);
            return false;
        }
        if (now_ns >= state->startup_deadline_ns) return false;
        (void)sched_yield();
    }
}

/* The harness never relies on an unbounded pthread_join.  Reader loops check
 * writer_done/abort_requested and are internally deadline-bounded; if a host
 * nevertheless fails to release one, process exit leaves the runner's raw
 * stderr artifact rather than racing stack-backed benchmark state. */
static bool microbench_join_readers_until(pthread_t threads[], int created,
                                          bool joined[MICROBENCH_MAX_READERS],
                                          uint64_t deadline_ns) {
    for (;;) {
        bool complete = true;
        for (int reader = 0; reader < created; ++reader) {
            if (joined[reader]) continue;
            int result = pthread_tryjoin_np(threads[reader], NULL);
            if (result == 0) {
                joined[reader] = true;
            } else if (result == EBUSY) {
                complete = false;
            } else {
                return false;
            }
        }
        if (complete) return true;
        uint64_t now_ns = 0;
        if (!microbench_now_ns(&now_ns) || now_ns >= deadline_ns) return false;
        const struct timespec pause = { .tv_sec = 0, .tv_nsec = 1000000L };
        (void)nanosleep(&pause, NULL);
    }
}

static void microbench_join_readers_bounded_or_exit(microbench_state_t *state,
                                                     pthread_t threads[], int created,
                                                     const char *phase) {
    bool joined[MICROBENCH_MAX_READERS] = {false};
    uint64_t start_ns = 0;
    uint64_t deadline_ns = 0;
    bool complete = microbench_now_ns(&start_ns)
        && microbench_deadline_after(start_ns, MICROBENCH_JOIN_TIMEOUT_MS, &deadline_ns)
        && microbench_join_readers_until(threads, created, joined, deadline_ns);
    if (complete) return;

    atomic_store_explicit(&state->abort_requested, true, memory_order_release);
    atomic_store_explicit(&state->start_readers, true, memory_order_release);
    atomic_store_explicit(&state->writer_done, true, memory_order_release);
    complete = microbench_now_ns(&start_ns)
        && microbench_deadline_after(start_ns, MICROBENCH_JOIN_TIMEOUT_MS, &deadline_ns)
        && microbench_join_readers_until(threads, created, joined, deadline_ns);
    if (complete) return;

    fprintf(stderr, "bounded reader join failed during %s; abandoning measurement\n", phase);
    fflush(stderr);
    _Exit(3);
}

static publisher_measurement_t microbench_run_publisher(
    microbench_state_t *state, const microbench_config_t *config,
    uint64_t next_sequence) {
    publisher_measurement_t measurement = {0};
    uint64_t start_ns = 0;
    if (!microbench_now_ns(&start_ns)) {
        atomic_store_explicit(&state->clock_failed, true, memory_order_release);
        atomic_store_explicit(&state->writer_done, true, memory_order_release);
        return measurement;
    }
    for (uint64_t iteration = 0; iteration < config->iterations; ++iteration) {
        uint64_t now_ns = 0;
        if (!microbench_now_ns(&now_ns)) {
            atomic_store_explicit(&state->clock_failed, true, memory_order_release);
            break;
        }
        if (now_ns >= state->measurement_deadline_ns) {
            measurement.deadline_exhausted = true;
            break;
        }
        signal_payload_t payload;
        if (!microbench_make_payload(next_sequence, config->seed, &payload)) {
            atomic_store_explicit(&state->clock_failed, true, memory_order_release);
            break;
        }
        uint64_t before_ns = 0;
        uint64_t after_ns = 0;
        if (!microbench_now_ns(&before_ns)) {
            atomic_store_explicit(&state->clock_failed, true, memory_order_release);
            break;
        }
        signal_publish_result_t result = publish_frame(&state->bus, &state->gates,
                                                       &payload, state->master_key, false);
        if (!microbench_now_ns(&after_ns)) {
            atomic_store_explicit(&state->clock_failed, true, memory_order_release);
            break;
        }
        measurement.attempts = microbench_saturating_add(measurement.attempts, 1);
        microbench_record_latency(microbench_elapsed_ns(before_ns, after_ns),
                                  &measurement.latency_sum_ns,
                                  &measurement.latency_max_ns);
        if (result == SIGNAL_PUBLISH_OK) {
            measurement.successes = microbench_saturating_add(measurement.successes, 1);
            if (next_sequence == UINT64_MAX) {
                measurement.generation_exhausted = microbench_saturating_add(
                    measurement.generation_exhausted, 1);
                break;
            }
            next_sequence += UINT64_C(1);
        } else if (result == SIGNAL_PUBLISH_CONTENDED) {
            measurement.contended = microbench_saturating_add(measurement.contended, 1);
        } else {
            measurement.generation_exhausted = microbench_saturating_add(
                measurement.generation_exhausted, 1);
            break;
        }
    }
    uint64_t end_ns = 0;
    if (!microbench_now_ns(&end_ns)) {
        atomic_store_explicit(&state->clock_failed, true, memory_order_release);
    } else {
        measurement.elapsed_ns = microbench_elapsed_ns(start_ns, end_ns);
    }
    atomic_store_explicit(&state->writer_done, true, memory_order_release);
    return measurement;
}

static void microbench_aggregate_readers(const microbench_state_t *state,
                                         int readers,
                                         aggregate_reader_measurement_t *aggregate) {
    memset(aggregate, 0, sizeof(*aggregate));
    for (int reader = 0; reader < readers; ++reader) {
        const reader_measurement_t *measurement = &state->readers[reader];
        aggregate->snapshot_copy_attempts = microbench_saturating_add(
            aggregate->snapshot_copy_attempts, measurement->snapshot_copy_attempts);
        aggregate->snapshot_copy_successes = microbench_saturating_add(
            aggregate->snapshot_copy_successes, measurement->snapshot_copy_successes);
        aggregate->snapshot_copy_empty = microbench_saturating_add(
            aggregate->snapshot_copy_empty, measurement->snapshot_copy_empty);
        aggregate->snapshot_copy_unstable = microbench_saturating_add(
            aggregate->snapshot_copy_unstable, measurement->snapshot_copy_unstable);
        aggregate->snapshot_copy_latency_sum_ns = microbench_saturating_add(
            aggregate->snapshot_copy_latency_sum_ns,
            measurement->snapshot_copy_latency_sum_ns);
        if (measurement->snapshot_copy_latency_max_ns
            > aggregate->snapshot_copy_latency_max_ns) {
            aggregate->snapshot_copy_latency_max_ns =
                measurement->snapshot_copy_latency_max_ns;
        }
        aggregate->api_calls = microbench_saturating_add(aggregate->api_calls,
                                                          measurement->api_calls);
        aggregate->valid_reads = microbench_saturating_add(aggregate->valid_reads,
                                                            measurement->valid_reads);
        aggregate->no_new_reads = microbench_saturating_add(aggregate->no_new_reads,
                                                             measurement->no_new_reads);
        aggregate->unstable_reads = microbench_saturating_add(aggregate->unstable_reads,
                                                               measurement->unstable_reads);
        aggregate->invalid_reads = microbench_saturating_add(aggregate->invalid_reads,
                                                              measurement->invalid_reads);
        aggregate->api_latency_sum_ns = microbench_saturating_add(
            aggregate->api_latency_sum_ns, measurement->api_latency_sum_ns);
        aggregate->verified_frame_latency_sum_ns = microbench_saturating_add(
            aggregate->verified_frame_latency_sum_ns,
            measurement->verified_frame_latency_sum_ns);
        aggregate->elapsed_sum_ns = microbench_saturating_add(
            aggregate->elapsed_sum_ns, measurement->elapsed_ns);
        if (measurement->api_latency_max_ns > aggregate->api_latency_max_ns)
            aggregate->api_latency_max_ns = measurement->api_latency_max_ns;
        if (measurement->verified_frame_latency_max_ns
            > aggregate->verified_frame_latency_max_ns) {
            aggregate->verified_frame_latency_max_ns =
                measurement->verified_frame_latency_max_ns;
        }
        if (measurement->elapsed_ns > aggregate->elapsed_max_ns)
            aggregate->elapsed_max_ns = measurement->elapsed_ns;
        if (measurement->deadline_exit)
            aggregate->deadline_exits = microbench_saturating_add(
                aggregate->deadline_exits, 1);

        const signal_reader_diagnostics_t *diagnostics = &measurement->diagnostics;
        aggregate->diagnostic_read_attempts = microbench_saturating_add(
            aggregate->diagnostic_read_attempts,
            atomic_load_explicit(&diagnostics->read_attempts, memory_order_relaxed));
        aggregate->diagnostic_verified_reads = microbench_saturating_add(
            aggregate->diagnostic_verified_reads,
            atomic_load_explicit(&diagnostics->verified_reads, memory_order_relaxed));
        aggregate->diagnostic_retries = microbench_saturating_add(
            aggregate->diagnostic_retries,
            atomic_load_explicit(&diagnostics->retries, memory_order_relaxed));
        aggregate->diagnostic_retry_exhaustions = microbench_saturating_add(
            aggregate->diagnostic_retry_exhaustions,
            atomic_load_explicit(&diagnostics->retry_exhaustions, memory_order_relaxed));
        aggregate->diagnostic_unstable_slots = microbench_saturating_add(
            aggregate->diagnostic_unstable_slots,
            atomic_load_explicit(&diagnostics->unstable_slot_observations,
                                 memory_order_relaxed));
        aggregate->diagnostic_hmac_failures = microbench_saturating_add(
            aggregate->diagnostic_hmac_failures,
            atomic_load_explicit(&diagnostics->hmac_failures, memory_order_relaxed));
        aggregate->diagnostic_invalid_fields = microbench_saturating_add(
            aggregate->diagnostic_invalid_fields,
            atomic_load_explicit(&diagnostics->invalid_fields, memory_order_relaxed));
        aggregate->diagnostic_invalid_schema = microbench_saturating_add(
            aggregate->diagnostic_invalid_schema,
            atomic_load_explicit(&diagnostics->invalid_schema, memory_order_relaxed));
        aggregate->diagnostic_invalid_tier = microbench_saturating_add(
            aggregate->diagnostic_invalid_tier,
            atomic_load_explicit(&diagnostics->invalid_tier, memory_order_relaxed));
        aggregate->diagnostic_invalid_source = microbench_saturating_add(
            aggregate->diagnostic_invalid_source,
            atomic_load_explicit(&diagnostics->invalid_source, memory_order_relaxed));
        aggregate->diagnostic_invalid_directive = microbench_saturating_add(
            aggregate->diagnostic_invalid_directive,
            atomic_load_explicit(&diagnostics->invalid_directive, memory_order_relaxed));
        aggregate->diagnostic_invalid_sequence = microbench_saturating_add(
            aggregate->diagnostic_invalid_sequence,
            atomic_load_explicit(&diagnostics->invalid_sequence, memory_order_relaxed));
        aggregate->diagnostic_stale_frames = microbench_saturating_add(
            aggregate->diagnostic_stale_frames,
            atomic_load_explicit(&diagnostics->stale_frames, memory_order_relaxed));
        aggregate->diagnostic_invalid_key_epochs = microbench_saturating_add(
            aggregate->diagnostic_invalid_key_epochs,
            atomic_load_explicit(&diagnostics->invalid_key_epochs, memory_order_relaxed));
    }
}

static void microbench_print_json(const microbench_config_t *config,
                                  const microbench_state_t *state,
                                  const publisher_measurement_t *publisher,
                                  const aggregate_reader_measurement_t *readers,
                                  bool completed) {
    const signal_publisher_diagnostics_t *diagnostics = &state->bus.diagnostics;
    unsigned int ready = atomic_load_explicit(&state->readers_ready, memory_order_relaxed);
    bool clock_failed = atomic_load_explicit(&state->clock_failed, memory_order_relaxed);
    printf("{\"schema_id\":\"%s\",\"publication_mode\":\"%s\","
           "\"readers\":%d,\"requested_iterations\":%" PRIu64 ","
           "\"warmup_iterations\":%" PRIu64 ",\"seed\":%" PRIu64 ","
           "\"reader_threads_ready\":%u,\"completed\":%s,"
           "\"clock_failed\":%s,\"publisher_deadline_exhausted\":%s,"
           "\"publisher_attempts\":%" PRIu64 ",\"publisher_successes\":%" PRIu64 ","
           "\"publisher_contended\":%" PRIu64 ","
           "\"publisher_generation_exhausted\":%" PRIu64 ","
           "\"publisher_latency_sum_ns\":%" PRIu64 ","
           "\"publisher_latency_max_ns\":%" PRIu64 ","
           "\"publisher_elapsed_ns\":%" PRIu64 ","
           "\"publisher_diagnostic_attempts\":%" PRIu64 ","
           "\"publisher_diagnostic_publications\":%" PRIu64 ","
           "\"publisher_diagnostic_contention\":%" PRIu64 ","
           "\"publisher_diagnostic_generation_exhaustions\":%" PRIu64 ","
           "\"reader_snapshot_copy_attempts\":%" PRIu64 ","
           "\"reader_snapshot_copy_successes\":%" PRIu64 ","
           "\"reader_snapshot_copy_empty\":%" PRIu64 ","
           "\"reader_snapshot_copy_unstable\":%" PRIu64 ","
           "\"reader_snapshot_copy_latency_sum_ns\":%" PRIu64 ","
           "\"reader_snapshot_copy_latency_max_ns\":%" PRIu64 ","
           "\"reader_api_calls\":%" PRIu64 ",\"reader_valid_reads\":%" PRIu64 ","
           "\"reader_no_new_reads\":%" PRIu64 ",\"reader_unstable_reads\":%" PRIu64 ","
           "\"reader_invalid_reads\":%" PRIu64 ","
           "\"reader_api_latency_sum_ns\":%" PRIu64 ","
           "\"reader_api_latency_max_ns\":%" PRIu64 ","
           "\"reader_verified_frame_latency_sum_ns\":%" PRIu64 ","
           "\"reader_verified_frame_latency_max_ns\":%" PRIu64 ","
           "\"reader_elapsed_sum_ns\":%" PRIu64 ","
           "\"reader_elapsed_max_ns\":%" PRIu64 ","
           "\"reader_deadline_exits\":%" PRIu64 ","
           "\"reader_diagnostic_attempts\":%" PRIu64 ","
           "\"reader_diagnostic_verified_reads\":%" PRIu64 ","
           "\"reader_diagnostic_retries\":%" PRIu64 ","
           "\"reader_diagnostic_retry_exhaustions\":%" PRIu64 ","
           "\"reader_diagnostic_unstable_slots\":%" PRIu64 ","
           "\"reader_diagnostic_hmac_failures\":%" PRIu64 ","
           "\"reader_diagnostic_invalid_fields\":%" PRIu64 ","
           "\"reader_diagnostic_invalid_schema\":%" PRIu64 ","
           "\"reader_diagnostic_invalid_tier\":%" PRIu64 ","
           "\"reader_diagnostic_invalid_source\":%" PRIu64 ","
           "\"reader_diagnostic_invalid_directive\":%" PRIu64 ","
           "\"reader_diagnostic_invalid_sequence\":%" PRIu64 ","
           "\"reader_diagnostic_stale_frames\":%" PRIu64 ","
           "\"reader_diagnostic_invalid_key_epochs\":%" PRIu64 "}\n",
           MICROBENCH_SCHEMA_ID, MICROBENCH_PUBLICATION_MODE,
           config->readers, config->iterations, config->warmup_iterations, config->seed,
           ready, completed ? "true" : "false", clock_failed ? "true" : "false",
           publisher->deadline_exhausted ? "true" : "false",
           publisher->attempts, publisher->successes, publisher->contended,
           publisher->generation_exhausted, publisher->latency_sum_ns,
           publisher->latency_max_ns, publisher->elapsed_ns,
           atomic_load_explicit(&diagnostics->publication_attempts, memory_order_relaxed),
           atomic_load_explicit(&diagnostics->publications, memory_order_relaxed),
           atomic_load_explicit(&diagnostics->publication_contention, memory_order_relaxed),
           atomic_load_explicit(&diagnostics->generation_exhaustions, memory_order_relaxed),
           readers->snapshot_copy_attempts, readers->snapshot_copy_successes,
           readers->snapshot_copy_empty, readers->snapshot_copy_unstable,
           readers->snapshot_copy_latency_sum_ns,
           readers->snapshot_copy_latency_max_ns,
           readers->api_calls, readers->valid_reads, readers->no_new_reads,
           readers->unstable_reads, readers->invalid_reads, readers->api_latency_sum_ns,
           readers->api_latency_max_ns, readers->verified_frame_latency_sum_ns,
           readers->verified_frame_latency_max_ns,
           readers->elapsed_sum_ns, readers->elapsed_max_ns,
           readers->deadline_exits, readers->diagnostic_read_attempts,
           readers->diagnostic_verified_reads, readers->diagnostic_retries,
           readers->diagnostic_retry_exhaustions, readers->diagnostic_unstable_slots,
           readers->diagnostic_hmac_failures, readers->diagnostic_invalid_fields,
           readers->diagnostic_invalid_schema, readers->diagnostic_invalid_tier,
           readers->diagnostic_invalid_source, readers->diagnostic_invalid_directive,
           readers->diagnostic_invalid_sequence,
           readers->diagnostic_stale_frames, readers->diagnostic_invalid_key_epochs);
}

static int microbench_run(const microbench_config_t *config) {
    microbench_state_t state;
    microbench_initialize_state(&state, config);

    uint64_t next_sequence = 1;
    if (!microbench_publish_warmup(&state, config, &next_sequence)) {
        fprintf(stderr, "warm-up publication failed\n");
        return 3;
    }

    uint64_t setup_start_ns = 0;
    if (!microbench_now_ns(&setup_start_ns)
        || !microbench_deadline_after(setup_start_ns, config->startup_timeout_ms,
                                      &state.startup_deadline_ns)) {
        fprintf(stderr, "could not establish bounded startup deadline\n");
        return 3;
    }

    pthread_t threads[MICROBENCH_MAX_READERS];
    reader_thread_arg_t arguments[MICROBENCH_MAX_READERS];
    int created = 0;
    for (int reader = 0; reader < config->readers; ++reader) {
        arguments[reader] = (reader_thread_arg_t){ .state = &state, .reader_index = reader };
        int create_result = pthread_create(&threads[reader], NULL, microbench_reader_main,
                                           &arguments[reader]);
        if (create_result != 0) {
            fprintf(stderr, "pthread_create(reader=%d) failed: %s\n", reader,
                    strerror(create_result));
            break;
        }
        created++;
    }
    if (created != config->readers || !microbench_wait_for_readers(&state, config->readers)) {
        atomic_store_explicit(&state.abort_requested, true, memory_order_release);
        atomic_store_explicit(&state.start_readers, true, memory_order_release);
        atomic_store_explicit(&state.writer_done, true, memory_order_release);
        microbench_join_readers_bounded_or_exit(&state, threads, created, "startup");
        fprintf(stderr, "reader startup did not complete within the bounded interval\n");
        return 3;
    }

    uint64_t measurement_start_ns = 0;
    if (!microbench_now_ns(&measurement_start_ns)
        || !microbench_deadline_after(measurement_start_ns, config->max_runtime_ms,
                                      &state.measurement_deadline_ns)) {
        atomic_store_explicit(&state.abort_requested, true, memory_order_release);
        atomic_store_explicit(&state.start_readers, true, memory_order_release);
        atomic_store_explicit(&state.writer_done, true, memory_order_release);
        microbench_join_readers_bounded_or_exit(&state, threads, created,
                                                "measurement setup");
        fprintf(stderr, "could not establish bounded measurement deadline\n");
        return 3;
    }
    atomic_store_explicit(&state.start_readers, true, memory_order_release);
    publisher_measurement_t publisher = microbench_run_publisher(&state, config, next_sequence);
    microbench_join_readers_bounded_or_exit(&state, threads, created, "measurement");

    aggregate_reader_measurement_t readers;
    microbench_aggregate_readers(&state, config->readers, &readers);
    bool clock_failed = atomic_load_explicit(&state.clock_failed, memory_order_acquire);
    bool completed = !clock_failed && !publisher.deadline_exhausted
        && publisher.attempts == config->iterations;
    microbench_print_json(config, &state, &publisher, &readers, completed);
    fflush(stdout);
    return completed ? 0 : 4;
}

int main(int argc, char **argv) {
    microbench_config_t config = {
        .readers = 1,
        .iterations = UINT64_C(5000),
        .warmup_iterations = UINT64_C(100),
        .seed = UINT64_C(1),
        .startup_timeout_ms = UINT64_C(1000),
        .max_runtime_ms = UINT64_C(3000),
        .drain_reads = UINT64_C(4),
    };
    for (int index = 1; index < argc; ++index) {
        const char *argument = argv[index];
        if (strcmp(argument, "--help") == 0) {
            microbench_usage(argv[0]);
            return 0;
        }
        if (index + 1 >= argc) {
            microbench_usage(argv[0]);
            return 2;
        }
        const char *value = argv[++index];
        uint64_t parsed = 0;
        if (strcmp(argument, "--readers") == 0) {
            if (!microbench_parse_u64(value, 1, MICROBENCH_MAX_READERS, &parsed)) {
                microbench_usage(argv[0]);
                return 2;
            }
            config.readers = (int)parsed;
        } else if (strcmp(argument, "--iterations") == 0) {
            if (!microbench_parse_u64(value, 100, MICROBENCH_MAX_ITERATIONS, &parsed)) {
                microbench_usage(argv[0]);
                return 2;
            }
            config.iterations = parsed;
        } else if (strcmp(argument, "--warmup") == 0) {
            if (!microbench_parse_u64(value, 0, MICROBENCH_MAX_WARMUP, &parsed)) {
                microbench_usage(argv[0]);
                return 2;
            }
            config.warmup_iterations = parsed;
        } else if (strcmp(argument, "--seed") == 0) {
            if (!microbench_parse_u64(value, 1, INT64_MAX, &parsed)) {
                microbench_usage(argv[0]);
                return 2;
            }
            config.seed = parsed;
        } else if (strcmp(argument, "--startup-timeout-ms") == 0) {
            if (!microbench_parse_u64(value, 10, MICROBENCH_MAX_STARTUP_TIMEOUT_MS,
                                      &parsed)) {
                microbench_usage(argv[0]);
                return 2;
            }
            config.startup_timeout_ms = parsed;
        } else if (strcmp(argument, "--max-runtime-ms") == 0) {
            if (!microbench_parse_u64(value, 100, MICROBENCH_MAX_RUNTIME_MS, &parsed)) {
                microbench_usage(argv[0]);
                return 2;
            }
            config.max_runtime_ms = parsed;
        } else if (strcmp(argument, "--drain-reads") == 0) {
            if (!microbench_parse_u64(value, 0, MICROBENCH_MAX_DRAIN_READS, &parsed)) {
                microbench_usage(argv[0]);
                return 2;
            }
            config.drain_reads = parsed;
        } else {
            microbench_usage(argv[0]);
            return 2;
        }
    }
    return microbench_run(&config);
}
