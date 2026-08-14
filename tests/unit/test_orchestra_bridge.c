#define ORCHESTRA_BRIDGE_UNIT_TEST 1
#include "../../kernel/sched_ext/bridge/orchestra_bridge.c"

#include <assert.h>

static void test_checked_parsing(void)
{
    uint32_t u32;
    uint64_t u64;

    assert(parse_u32("1", 1, 100, &u32) && u32 == 1);
    assert(parse_u32("100", 1, 100, &u32) && u32 == 100);
    assert(!parse_u32("0", 1, 100, &u32));
    assert(!parse_u32("101", 1, 100, &u32));
    assert(!parse_u32("-1", 0, UINT32_MAX, &u32));
    assert(!parse_u32("7x", 0, UINT32_MAX, &u32));
    assert(!parse_u32(" 7", 0, UINT32_MAX, &u32));
    assert(parse_u64("18446744073709551615", 0, UINT64_MAX, &u64));
    assert(u64 == UINT64_MAX);
    assert(!parse_u64("18446744073709551616", 0, UINT64_MAX, &u64));
}

static void test_proc_stat_parser(void)
{
    const char *line =
        "123 (worker name with ) parens) R 1 2 3 4 5 6 7 8 9 10 11 12 13 "
        "14 15 16 17 18 987654 20 21\n";
    uint64_t ticks = 0;

    assert(parse_proc_stat_start(line, &ticks));
    assert(ticks == UINT64_C(987654));
    assert(!parse_proc_stat_start("123 malformed\n", &ticks));

    long hz = sysconf(_SC_CLK_TCK);
    assert(hz > 0);
    uint64_t expected_ticks = UINT64_C(12345);
    uint64_t start_ns = (expected_ticks / (uint64_t)hz) * UINT64_C(1000000000)
        + (expected_ticks % (uint64_t)hz) * UINT64_C(1000000000) /
          (uint64_t)hz;
    assert(start_ns_matches_proc_ticks(start_ns, expected_ticks));
    assert(!start_ns_matches_proc_ticks(start_ns, expected_ticks + 1));
    assert(!start_ns_matches_proc_ticks(0, expected_ticks));
}

static void test_action_translation(void)
{
    uint32_t wire = UINT32_MAX;
    enum orchestra_action_id parsed;

    for (uint32_t action = 0; action < ORCHESTRA_ACTION_COUNT; action++) {
        assert(canonical_to_wire((enum orchestra_action_id)action, &wire));
        assert(wire == action);
    }
    assert(!canonical_to_wire(ORCHESTRA_ACTION_COUNT, &wire));
    assert(parse_action("sleep", &parsed));
    assert(parsed == ORCHESTRA_ACTION_SLEEP);
}

static void test_abi_and_snapshot_comparison(void)
{
    struct bridge_control control = {
        .magic = ORCHESTRA_ABI_MAGIC,
        .abi_version = ORCHESTRA_ABI_VERSION,
        .value_size = sizeof(struct bridge_control),
        .capability_flags = BRIDGE_REQUIRED_CAPS,
        .scx_api_version = ORCHESTRA_SCX_API_VERSION,
        .scheduler_epoch = 42
    };
    struct bridge_directive first = {
        .abi_version = ORCHESTRA_ABI_VERSION,
        .value_size = sizeof(struct bridge_directive),
        .scheduler_epoch = 42,
        .generation = 1,
        .identity = { .tgid = 10, .tid = 11, .start_boottime_ns = 12 },
        .action = ORCHESTRA_ACTION_RUN,
        .target_cpu = ORCHESTRA_CPU_ANY,
        .expiry_ns = 99
    };
    struct bridge_directive second = first;

    assert(valid_control(&control));
    control.value_size--;
    assert(!valid_control(&control));
    assert(directive_equal(&first, &second));
    second.identity.start_boottime_ns++;
    assert(!directive_equal(&first, &second));

    assert(sizeof(struct bridge_stream_request) == 88);
    assert(sizeof(struct bridge_directive) == 112);
    assert(sizeof(struct bridge_telemetry) == 304);
}

static void test_exact_map_schema(void)
{
    assert(MAP_ROLE_COUNT == 7);
    for (int role = MAP_CONTROL; role < MAP_ROLE_COUNT; role++) {
        assert(map_specs[role].name != NULL);
        assert(strlen(map_specs[role].name) < BPF_OBJ_NAME_LEN);
        assert(map_specs[role].path != NULL);
        assert(map_specs[role].key_size > 0);
        assert(map_specs[role].value_size > 0);
        assert(map_specs[role].max_entries > 0);
    }
    assert(map_specs[MAP_DIRECTIVE].type == BPF_MAP_TYPE_HASH);
    assert(map_specs[MAP_DIRECTIVE].key_size ==
           sizeof(struct orchestra_task_identity));
    assert(map_specs[MAP_DIRECTIVE].value_size ==
           sizeof(struct bridge_directive));
    assert(map_specs[MAP_DIRECTIVE].max_entries == BRIDGE_MAX_TASKS);
    assert(map_specs[MAP_DEFER_TIMER].type == BPF_MAP_TYPE_ARRAY);
    assert(map_specs[MAP_DEFER_TIMER].value_size ==
           sizeof(struct bridge_defer_timer));
}

static void test_cli_validation(void)
{
    struct options options;
    char *valid[] = {
        "bridge", "--publish", "--action", "THROTTLE",
        "--target-pid", "123", "--throttle-period-ns", "10000000",
        "--throttle-budget-ns", "2000000", "--expiry-ns", "5000000",
        "--controller-state", "DEGRADED", "--policy-mode", "1",
        "--policy-generation", "18446744073709551615"
    };
    char *bad_pid[] = {
        "bridge", "--publish", "--action", "RUN", "--target-pid", "12x"
    };
    char *two_commands[] = { "bridge", "--status", "--clear" };

    assert(parse_options((int)(sizeof(valid) / sizeof(valid[0])), valid, &options));
    assert(options.action == ORCHESTRA_ACTION_THROTTLE);
    assert(options.target_tid == 123);
    assert(options.controller_state == ORCHESTRA_CTRL_DEGRADED);
    assert(options.policy_mode == ORCHESTRA_POLICY_ADAPT);
    assert(options.policy_generation == UINT64_MAX);
    assert(!parse_options((int)(sizeof(bad_pid) / sizeof(bad_pid[0])), bad_pid,
                          &options));
    assert(!parse_options((int)(sizeof(two_commands) / sizeof(two_commands[0])),
                          two_commands, &options));
}

int main(void)
{
    test_checked_parsing();
    test_proc_stat_parser();
    test_action_translation();
    test_abi_and_snapshot_comparison();
    test_exact_map_schema();
    test_cli_validation();
    puts("PASS bridge parser/ABI/publication-source tests");
    return 0;
}
