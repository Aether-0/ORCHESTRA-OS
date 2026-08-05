/*
 * Bounded contention stress coverage for the selected generation-stamped
 * signal publication path.  It is a test-only executable: Linux remains the
 * scheduler, and the assertions concern coherent authenticated frame reads,
 * not kernel dispatch behavior.
 */
#define ORCHESTRA_UNIT_TEST 1
#define main orchestra_demo_main
#include "../../orchestra_paper_cpu_demo/orchestra_paper_cpu.c"
#undef main

#include <pthread.h>

enum {
    STRESS_READER_COUNT = 4,
    STRESS_PUBLICATION_COUNT = 2000,
    STRESS_PUBLISH_RETRY_LIMIT = 2048,
    STRESS_READER_ATTEMPT_LIMIT = 200000,
    STRESS_START_WAIT_LIMIT = 200000,
};

typedef struct {
    uint64_t valid_reads;
    uint64_t no_new_reads;
    uint64_t unstable_reads;
    uint64_t invalid_reads;
    uint64_t sequence_regressions;
    uint64_t accepted_duplicates;
    uint64_t final_sequence;
    signal_reader_diagnostics_t diagnostics;
} stress_reader_result_t;

typedef struct {
    signal_bus_t bus;
    signal_reader_gates_t gates;
    uint8_t key[MASTER_KEY_SIZE];
    _Atomic unsigned int ready_threads;
    _Atomic int start;
    _Atomic int publisher_done;
    _Atomic int abort_requested;
    _Atomic int errors;
    _Atomic unsigned int reader_completed;
    _Atomic uint64_t successful_publications;
    _Atomic uint64_t publisher_contentions;
    _Atomic uint64_t hook_calls;
    _Atomic uint64_t hook_yields;
    stress_reader_result_t reader[STRESS_READER_COUNT];
} publication_stress_context_t;

typedef struct {
    publication_stress_context_t *context;
    unsigned int reader_index;
} reader_thread_arg_t;

static publication_stress_context_t *g_stress_context = NULL;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "check failed at %s:%d: %s\n",                  \
                    __FILE__, __LINE__, #condition);                            \
            return false;                                                       \
        }                                                                       \
    } while (0)

static uint64_t stress_deadline_after_ns(uint64_t duration_ns) {
    uint64_t now = monotonic_ns();
    return now > UINT64_MAX - duration_ns ? UINT64_MAX : now + duration_ns;
}

static void stress_note_error(publication_stress_context_t *context) {
    (void)atomic_fetch_add_explicit(&context->errors, 1, memory_order_relaxed);
}

static void stress_publication_hook(signal_publication_hook_stage_t stage) {
    if (g_stress_context == NULL) return;
    if (stage != SIGNAL_HOOK_WRITER_WORD && stage != SIGNAL_HOOK_READER_TOKEN
        && stage != SIGNAL_HOOK_READER_SEQUENCE && stage != SIGNAL_HOOK_READER_WORD) {
        return;
    }
    uint64_t call = atomic_fetch_add_explicit(&g_stress_context->hook_calls,
                                               UINT64_C(1), memory_order_relaxed);
    /* The permutation is deterministic but distributes bounded yields across
     * token, sequence, and word-copy phases instead of synchronizing every
     * reader at one fixed iteration.  Unsigned wrap is intentional here. */
    uint64_t mixed = (call * UINT64_C(0x9e3779b97f4a7c15))
                   ^ ((uint64_t)stage * UINT64_C(0xbf58476d1ce4e5b9));
    if ((mixed >> 58u) == 0u) {
        (void)sched_yield();
        (void)atomic_fetch_add_explicit(&g_stress_context->hook_yields,
                                         UINT64_C(1), memory_order_relaxed);
    }
}

static void stress_fill_key(uint8_t key[MASTER_KEY_SIZE]) {
    for (size_t index = 0; index < MASTER_KEY_SIZE; ++index)
        key[index] = (uint8_t)(UINT8_C(0x70) + (uint8_t)index);
}

static signal_payload_t stress_payload(uint64_t sequence) {
    return (signal_payload_t) {
        .magic = SIGNAL_MAGIC,
        .schema_version = SIGNAL_SCHEMA_VERSION,
        .tier = SIGNAL_TIER_CORE_LOCAL,
        .source_id = SIGNAL_SOURCE_LOCAL,
        .sequence = sequence,
        .monotonic_ns = monotonic_ns(),
        .max_age_ns = MAX_FRAME_AGE_NS,
        .key_epoch = (uint32_t)(sequence / (uint64_t)KEY_EPOCH_TICKS),
        .directive = ACT_RUN,
        .state_schema_version = STATE_SCHEMA_VERSION,
        .prediction_used = 1u,
        .cpu_now = 0.45,
        .cpu_pred = 0.46,
        .decision_cpu = 0.46,
        .memory_pressure = 0.20,
        .thermal_proxy = 0.25,
        .confidence = 0.90,
        .jitter_sigma = 0.02,
        .switch_penalty = 0.01,
        .consensus_blend = 0.01,
    };
}

static void stress_initialize(publication_stress_context_t *context) {
    memset(context, 0, sizeof(*context));
    initialize_selected_signal_publication(&context->bus.publication);
    initialize_signal_reader_gates(&context->gates);
    initialize_signal_publisher_diagnostics(&context->bus.diagnostics);
    atomic_init(&context->bus.consensus_lock, 0);
    atomic_init(&context->bus.stop, 0);
    atomic_init(&context->ready_threads, 0u);
    atomic_init(&context->start, 0);
    atomic_init(&context->publisher_done, 0);
    atomic_init(&context->abort_requested, 0);
    atomic_init(&context->errors, 0);
    atomic_init(&context->reader_completed, 0u);
    atomic_init(&context->successful_publications, 0);
    atomic_init(&context->publisher_contentions, 0);
    atomic_init(&context->hook_calls, 0);
    atomic_init(&context->hook_yields, 0);
    for (unsigned int index = 0; index < STRESS_READER_COUNT; ++index)
        initialize_signal_reader_diagnostics(&context->reader[index].diagnostics);
    stress_fill_key(context->key);
}

static bool stress_wait_for_start(publication_stress_context_t *context) {
    (void)atomic_fetch_add_explicit(&context->ready_threads, 1u, memory_order_release);
    for (unsigned int attempt = 0; attempt < STRESS_START_WAIT_LIMIT; ++attempt) {
        if (atomic_load_explicit(&context->start, memory_order_acquire) != 0)
            return true;
        if (atomic_load_explicit(&context->abort_requested, memory_order_acquire) != 0)
            return false;
        (void)sched_yield();
    }
    stress_note_error(context);
    return false;
}

static void *stress_publisher_thread(void *opaque) {
    publication_stress_context_t *context = opaque;
    if (!stress_wait_for_start(context)) {
        atomic_store_explicit(&context->publisher_done, 1, memory_order_release);
        return NULL;
    }

    for (uint64_t sequence = 1; sequence <= (uint64_t)STRESS_PUBLICATION_COUNT;
         ++sequence) {
        if (atomic_load_explicit(&context->abort_requested, memory_order_acquire) != 0)
            break;
        signal_payload_t payload = stress_payload(sequence);
        bool published = false;
        for (unsigned int attempt = 0; attempt < STRESS_PUBLISH_RETRY_LIMIT; ++attempt) {
            if (atomic_load_explicit(&context->abort_requested, memory_order_acquire) != 0)
                break;
            signal_publish_result_t result = publish_frame(&context->bus, &context->gates,
                                                            &payload, context->key, false);
            if (result == SIGNAL_PUBLISH_OK) {
                (void)atomic_fetch_add_explicit(&context->successful_publications,
                                                 UINT64_C(1), memory_order_relaxed);
                published = true;
                break;
            }
            if (result == SIGNAL_PUBLISH_CONTENDED) {
                (void)atomic_fetch_add_explicit(&context->publisher_contentions,
                                                 UINT64_C(1), memory_order_relaxed);
                (void)sched_yield();
                continue;
            }
            stress_note_error(context);
            break;
        }
        if (!published) {
            if (atomic_load_explicit(&context->abort_requested, memory_order_acquire) == 0)
                stress_note_error(context);
            break;
        }
    }
    atomic_store_explicit(&context->publisher_done, 1, memory_order_release);
    return NULL;
}

static void *stress_reader_thread(void *opaque) {
    reader_thread_arg_t *argument = opaque;
    publication_stress_context_t *context = argument->context;
    stress_reader_result_t *result = &context->reader[argument->reader_index];
    if (!stress_wait_for_start(context)) {
        (void)atomic_fetch_add_explicit(&context->reader_completed, 1u,
                                         memory_order_release);
        return NULL;
    }

    uint64_t last_sequence = 0;
    for (unsigned int attempt = 0; attempt < STRESS_READER_ATTEMPT_LIMIT; ++attempt) {
        if (atomic_load_explicit(&context->abort_requested, memory_order_acquire) != 0)
            break;
        signal_payload_t frame = {0};
        frame_read_result_t read_result = read_verified_frame_with_diagnostics(
            &context->bus, &context->gates, context->key, last_sequence, &frame,
            &result->diagnostics);
        if (read_result == FRAME_VALID) {
            if (frame.sequence < last_sequence) {
                result->sequence_regressions++;
                stress_note_error(context);
                break;
            }
            if (frame.sequence == last_sequence) {
                result->accepted_duplicates++;
                stress_note_error(context);
                break;
            }
            if (frame.sequence > (uint64_t)STRESS_PUBLICATION_COUNT) {
                stress_note_error(context);
                break;
            }
            last_sequence = frame.sequence;
            result->valid_reads++;
        } else if (read_result == FRAME_NO_NEW) {
            result->no_new_reads++;
        } else if (read_result == FRAME_UNSTABLE) {
            result->unstable_reads++;
        } else {
            /* Every writer payload is fresh and HMAC-valid.  A torn snapshot
             * must become FRAME_UNSTABLE, never an accepted or invalid frame. */
            result->invalid_reads++;
            stress_note_error(context);
            break;
        }
        if (atomic_load_explicit(&context->publisher_done, memory_order_acquire) != 0
            && last_sequence == (uint64_t)STRESS_PUBLICATION_COUNT) {
            break;
        }
        if ((attempt & 31u) == 0u) (void)sched_yield();
    }
    result->final_sequence = last_sequence;
    if (last_sequence != (uint64_t)STRESS_PUBLICATION_COUNT
        && atomic_load_explicit(&context->abort_requested, memory_order_acquire) == 0) {
        stress_note_error(context);
    }
    (void)atomic_fetch_add_explicit(&context->reader_completed, 1u,
                                     memory_order_release);
    return NULL;
}

static bool stress_wait_for_ready(publication_stress_context_t *context,
                                  unsigned int expected) {
    uint64_t deadline = stress_deadline_after_ns(UINT64_C(2000000000));
    while (monotonic_ns() < deadline) {
        if (atomic_load_explicit(&context->ready_threads, memory_order_acquire) == expected)
            return true;
        (void)sched_yield();
    }
    return false;
}

static bool stress_join_thread_bounded(pthread_t thread) {
    uint64_t deadline = stress_deadline_after_ns(UINT64_C(5000000000));
    while (monotonic_ns() < deadline) {
        int result = pthread_tryjoin_np(thread, NULL);
        if (result == 0) return true;
        if (result != EBUSY) return false;
        struct timespec pause = { .tv_sec = 0, .tv_nsec = 1000000L };
        (void)nanosleep(&pause, NULL);
    }
    return false;
}

/* Keep all test-only reference helpers live under -Werror.  The stress itself
 * exercises the selected transport only; this compact smoke check retains the
 * existing byte-wise reference symbols intentionally exposed by the include. */
static bool stress_reference_visibility(void) {
    legacy_signal_publication_t legacy;
    signal_bus_t selected;
    signal_reader_gates_t gates;
    signal_reader_diagnostics_t diagnostics;
    uint8_t bytes[SIGNAL_FRAME_SIZE] = {0};
    uint8_t copied[SIGNAL_FRAME_SIZE] = {0};
    uint8_t key[MASTER_KEY_SIZE] = {0};
    action_t actions[MAX_WORKERS] = {ACT_RUN};
    action_t previous[MAX_WORKERS] = {ACT_RUN};
    signal_payload_t output = {0};
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

    memset(&selected, 0, sizeof(selected));
    memset(&gates, 0, sizeof(gates));
    initialize_selected_signal_publication(&selected.publication);
    initialize_signal_reader_gates(&gates);
    initialize_signal_publisher_diagnostics(&selected.diagnostics);
    atomic_init(&selected.consensus_lock, 0);
    atomic_init(&selected.stop, 0);
    CHECK(read_verified_frame(&selected, &gates, key, 0, &output) == FRAME_NO_NEW);
    return true;
}

int main(void) {
#if ORCHESTRA_SIGNAL_PUBLICATION_LEGACY
#error "the stress test requires the selected generation-stamped transport"
#endif
    publication_stress_context_t context;
    pthread_t publisher;
    pthread_t readers[STRESS_READER_COUNT];
    reader_thread_arg_t arguments[STRESS_READER_COUNT];
    stress_initialize(&context);
    CHECK(selected_signal_publication_atomics_are_lock_free(&context.bus.publication));
    for (size_t slot = 0; slot < SIGNAL_PUBLICATION_SLOT_COUNT; ++slot)
        CHECK(atomic_is_lock_free(&context.gates.access_state[slot].value));
    CHECK(stress_reference_visibility());

    g_stress_context = &context;
    g_signal_publication_test_hook = stress_publication_hook;
    unsigned int created_readers = 0;
    bool publisher_created = false;
    for (unsigned int index = 0; index < STRESS_READER_COUNT; ++index) {
        arguments[index] = (reader_thread_arg_t) {
            .context = &context,
            .reader_index = index,
        };
        if (pthread_create(&readers[index], NULL, stress_reader_thread, &arguments[index])
            != 0) {
            stress_note_error(&context);
            break;
        }
        created_readers++;
    }
    if (created_readers == STRESS_READER_COUNT
        && pthread_create(&publisher, NULL, stress_publisher_thread, &context) == 0) {
        publisher_created = true;
    } else {
        stress_note_error(&context);
    }

    bool ready = publisher_created && stress_wait_for_ready(
        &context, STRESS_READER_COUNT + 1u);
    if (!ready) stress_note_error(&context);
    atomic_store_explicit(&context.start, 1, memory_order_release);

    bool publisher_joined = !publisher_created;
    bool reader_joined[STRESS_READER_COUNT] = {false};
    unsigned int reader_hangs = 0;
    if (publisher_created) publisher_joined = stress_join_thread_bounded(publisher);
    for (unsigned int index = 0; index < created_readers; ++index) {
        reader_joined[index] = stress_join_thread_bounded(readers[index]);
        if (!reader_joined[index]) reader_hangs++;
    }
    if (!publisher_joined || reader_hangs != 0u) {
        atomic_store_explicit(&context.abort_requested, 1, memory_order_release);
        if (!publisher_joined && publisher_created)
            publisher_joined = stress_join_thread_bounded(publisher);
        for (unsigned int index = 0; index < created_readers; ++index) {
            if (!reader_joined[index])
                reader_joined[index] = stress_join_thread_bounded(readers[index]);
        }
    }
    bool joined = publisher_joined;
    for (unsigned int index = 0; index < created_readers; ++index)
        joined = reader_joined[index] && joined;
    if (!joined) {
        /* Do not clear a hook or inspect shared test state while an unjoined
         * reader can still access it.  The process exits, and the enclosing
         * timeout remains a final external bound. */
        fprintf(stderr, "FAIL publication stress: bounded thread join failure\n");
        _Exit(EXIT_FAILURE);
    }
    g_signal_publication_test_hook = NULL;
    g_stress_context = NULL;

    uint64_t total_read_attempts = 0;
    uint64_t total_verified_reads = 0;
    uint64_t total_retries = 0;
    uint64_t total_retry_exhaustions = 0;
    uint64_t total_unstable_reads = 0;
    uint64_t total_hmac_failures = 0;
    uint64_t total_invalid_fields = 0;
    uint64_t total_invalid_schema = 0;
    uint64_t total_invalid_tier = 0;
    uint64_t total_invalid_source = 0;
    uint64_t total_invalid_directive = 0;
    uint64_t total_invalid_sequence = 0;
    uint64_t total_invalid_key_epochs = 0;
    uint64_t total_stale_frames = 0;
    uint64_t total_invalid_frame_reads = 0;
    uint64_t total_sequence_regressions = 0;
    uint64_t total_accepted_duplicates = 0;
    bool ok = joined
           && atomic_load_explicit(&context.errors, memory_order_relaxed) == 0
           && atomic_load_explicit(&context.successful_publications,
                                   memory_order_relaxed)
              == (uint64_t)STRESS_PUBLICATION_COUNT
           && atomic_load_explicit(&context.hook_yields, memory_order_relaxed) > 0u;
    for (unsigned int index = 0; index < STRESS_READER_COUNT; ++index) {
        const stress_reader_result_t *reader = &context.reader[index];
        uint64_t read_attempts = atomic_load_explicit(&reader->diagnostics.read_attempts,
                                                      memory_order_relaxed);
        uint64_t hmac_failures = atomic_load_explicit(&reader->diagnostics.hmac_failures,
                                                       memory_order_relaxed);
        uint64_t verified_reads = atomic_load_explicit(&reader->diagnostics.verified_reads,
                                                        memory_order_relaxed);
        uint64_t retries = atomic_load_explicit(&reader->diagnostics.retries,
                                                memory_order_relaxed);
        uint64_t retry_exhaustions = atomic_load_explicit(
            &reader->diagnostics.retry_exhaustions, memory_order_relaxed);
        uint64_t invalid_fields = atomic_load_explicit(&reader->diagnostics.invalid_fields,
                                                       memory_order_relaxed);
        uint64_t invalid_schema = atomic_load_explicit(&reader->diagnostics.invalid_schema,
                                                       memory_order_relaxed);
        uint64_t invalid_tier = atomic_load_explicit(&reader->diagnostics.invalid_tier,
                                                     memory_order_relaxed);
        uint64_t invalid_source = atomic_load_explicit(&reader->diagnostics.invalid_source,
                                                       memory_order_relaxed);
        uint64_t invalid_directive = atomic_load_explicit(
            &reader->diagnostics.invalid_directive, memory_order_relaxed);
        uint64_t invalid_sequence = atomic_load_explicit(
            &reader->diagnostics.invalid_sequence, memory_order_relaxed);
        uint64_t invalid_key_epochs = atomic_load_explicit(
            &reader->diagnostics.invalid_key_epochs, memory_order_relaxed);
        uint64_t stale_frames = atomic_load_explicit(&reader->diagnostics.stale_frames,
                                                     memory_order_relaxed);
        total_read_attempts += read_attempts;
        total_verified_reads += verified_reads;
        total_retries += retries;
        total_retry_exhaustions += retry_exhaustions;
        total_unstable_reads += reader->unstable_reads;
        total_hmac_failures += hmac_failures;
        total_invalid_fields += invalid_fields;
        total_invalid_schema += invalid_schema;
        total_invalid_tier += invalid_tier;
        total_invalid_source += invalid_source;
        total_invalid_directive += invalid_directive;
        total_invalid_sequence += invalid_sequence;
        total_invalid_key_epochs += invalid_key_epochs;
        total_stale_frames += stale_frames;
        total_invalid_frame_reads += reader->invalid_reads;
        total_sequence_regressions += reader->sequence_regressions;
        total_accepted_duplicates += reader->accepted_duplicates;
        printf("reader=%u attempts=%" PRIu64 " verified=%" PRIu64
               " valid=%" PRIu64 " no-new=%" PRIu64 " unstable=%" PRIu64
               " retries=%" PRIu64 " retry-exhaustions=%" PRIu64
               " invalid-frame-reads=%" PRIu64 " regressions=%" PRIu64
               " duplicates=%" PRIu64 " final=%" PRIu64 "\n",
               index, read_attempts, verified_reads, reader->valid_reads,
               reader->no_new_reads, reader->unstable_reads, retries,
               retry_exhaustions, reader->invalid_reads, reader->sequence_regressions,
               reader->accepted_duplicates, reader->final_sequence);
        ok = ok && reader->invalid_reads == 0u
             && reader->final_sequence == (uint64_t)STRESS_PUBLICATION_COUNT
             && reader->valid_reads > 0u
             && verified_reads == reader->valid_reads
             && hmac_failures == 0u && invalid_fields == 0u
             && invalid_schema == 0u && invalid_tier == 0u && invalid_source == 0u
             && invalid_directive == 0u && invalid_sequence == 0u
             && invalid_key_epochs == 0u && stale_frames == 0u
             && reader->sequence_regressions == 0u
             && reader->accepted_duplicates == 0u;
    }
    uint64_t publisher_attempts = atomic_load_explicit(&context.bus.diagnostics.publication_attempts,
                                                        memory_order_relaxed);
    uint64_t publisher_successes = atomic_load_explicit(&context.successful_publications,
                                                         memory_order_relaxed);
    unsigned int reader_completed = atomic_load_explicit(&context.reader_completed,
                                                         memory_order_acquire);
    uint64_t reader_crashes = reader_completed >= STRESS_READER_COUNT ? 0u
        : (uint64_t)(STRESS_READER_COUNT - reader_completed);
    printf("stress-summary publisher-success=%" PRIu64 " publisher-attempts=%" PRIu64
           " publisher-contention=%" PRIu64 " read-attempts=%" PRIu64
           " verified=%" PRIu64 " retries=%" PRIu64
           " retry-exhaustions=%" PRIu64 " unstable=%" PRIu64
           " hmac=%" PRIu64 " invalid-fields=%" PRIu64
           " invalid-schema=%" PRIu64 " invalid-tier=%" PRIu64
           " invalid-source=%" PRIu64 " invalid-directive=%" PRIu64
           " invalid-sequence=%" PRIu64
           " invalid-key-epoch=%" PRIu64 " stale=%" PRIu64
           " torn-frame-detections=%" PRIu64 " regressions=%" PRIu64
           " accepted-duplicates=%" PRIu64 " reader-crashes=%" PRIu64
           " reader-hangs=%u hook-yields=%" PRIu64 "\n",
           publisher_successes, publisher_attempts,
           atomic_load_explicit(&context.publisher_contentions, memory_order_relaxed),
           total_read_attempts, total_verified_reads, total_retries,
           total_retry_exhaustions, total_unstable_reads, total_hmac_failures,
           total_invalid_fields, total_invalid_schema, total_invalid_tier,
           total_invalid_source, total_invalid_directive, total_invalid_sequence,
           total_invalid_key_epochs, total_stale_frames, total_invalid_frame_reads,
           total_sequence_regressions, total_accepted_duplicates, reader_crashes,
           reader_hangs,
           atomic_load_explicit(&context.hook_yields, memory_order_relaxed));
    ok = ok && publisher_attempts >= publisher_successes
         && total_hmac_failures == 0u && total_invalid_fields == 0u
         && total_invalid_schema == 0u && total_invalid_tier == 0u
         && total_invalid_source == 0u && total_invalid_directive == 0u
         && total_invalid_sequence == 0u
         && total_invalid_key_epochs == 0u && total_stale_frames == 0u
         && total_invalid_frame_reads == 0u && total_sequence_regressions == 0u
         && total_accepted_duplicates == 0u && reader_crashes == 0u
         && reader_hangs == 0u && reader_completed == STRESS_READER_COUNT;
    explicit_bzero(context.key, sizeof(context.key));
    if (!ok) return EXIT_FAILURE;
    printf("PASS generation publication thread stress\n");
    return EXIT_SUCCESS;
}
