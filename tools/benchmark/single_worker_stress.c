#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <pthread.h>
#include <unistd.h>
#include <stdatomic.h>
#include <sched.h>
#include <sys/resource.h>

typedef struct {
    int cpu_core;
    volatile bool stop;
    _Atomic uint64_t ops_completed;
    _Atomic uint64_t yield_calls;
} worker_args_t;

void* worker_func(void* arg) {
    worker_args_t* w = (worker_args_t*)arg;

    // Pin to CPU core
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(w->cpu_core, &cpuset);
    pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);

    double x = 1.000001;

    while (!w->stop) {
        for (int i = 0; i < 1000; i++) {
            x = x * 1.0000001 + 0.0000001;
        }
        atomic_fetch_add(&w->ops_completed, 1000);

        // Periodically perform yield to stress test context switching
        if ((atomic_load(&w->ops_completed) % 50000) == 0) {
            sched_yield();
            atomic_fetch_add(&w->yield_calls, 1);
        }
    }

    if (x == 0.123456789) {
        printf("impossible: %f\n", x);
    }

    return NULL;
}

uint64_t get_ctx_switches() {
    FILE* f = fopen("/proc/stat", "r");
    if (!f) return 0;
    char line[256];
    uint64_t ctxt = 0;
    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, "ctxt %lu", &ctxt) == 1) {
            break;
        }
    }
    fclose(f);
    return ctxt;
}

int main(int argc, char** argv) {
    uint64_t duration_s = 180; // Default 3 minutes
    int target_cpu = 0;

    if (argc >= 2) duration_s = strtoull(argv[1], NULL, 10);
    if (argc >= 3) target_cpu = atoi(argv[2]);

    printf("==============================================================\n");
    printf("ORCHESTRA-OS SINGLE WORKER FULL STRESS TEST\n");
    printf("Target CPU Core: %d | Duration: %lu seconds (%.1f minutes)\n", 
           target_cpu, duration_s, (double)duration_s / 60.0);
    printf("==============================================================\n\n");

    pthread_t thread;
    worker_args_t args;
    args.cpu_core = target_cpu;
    args.stop = false;
    atomic_init(&args.ops_completed, 0);
    atomic_init(&args.yield_calls, 0);

    uint64_t ctx_before = get_ctx_switches();
    struct timespec start_time, end_time;
    clock_gettime(CLOCK_MONOTONIC, &start_time);

    pthread_create(&thread, NULL, worker_func, &args);

    printf("Stress test running on CPU %d... Progress updates every 15s:\n\n", target_cpu);
    printf("%-10s | %-12s | %-14s | %-14s | %-14s\n", 
           "Elapsed", "Progress", "Total Ops", "Current Rate", "Yield Calls");
    printf("----------------------------------------------------------------------\n");
    fflush(stdout);

    uint64_t remaining = duration_s;
    uint64_t step = 15;
    uint64_t elapsed_total = 0;
    uint64_t last_ops = 0;

    while (remaining > 0) {
        uint64_t sleep_time = (remaining < step) ? remaining : step;
        sleep(sleep_time);
        elapsed_total += sleep_time;
        remaining -= sleep_time;

        uint64_t current_ops = atomic_load(&args.ops_completed);
        uint64_t yields = atomic_load(&args.yield_calls);
        
        uint64_t ops_in_step = current_ops - last_ops;
        double step_rate_mops = (double)ops_in_step / (double)sleep_time / 1e6;
        last_ops = current_ops;

        char time_buf[16];
        snprintf(time_buf, sizeof(time_buf), "%3lus/%3lus", elapsed_total, duration_s);

        printf("%-10s | %5.1f%%        | %8.2f Mops  | %7.2f Mops/s | %lu\n", 
               time_buf, (double)elapsed_total / duration_s * 100.0,
               (double)current_ops / 1e6, step_rate_mops, yields);
        fflush(stdout);
    }

    // Stop worker
    args.stop = true;
    pthread_join(thread, NULL);

    clock_gettime(CLOCK_MONOTONIC, &end_time);
    uint64_t ctx_after = get_ctx_switches();

    double elapsed_sec = (end_time.tv_sec - start_time.tv_sec) + 
                        (end_time.tv_nsec - start_time.tv_nsec) / 1e9;

    uint64_t total_ops = atomic_load(&args.ops_completed);
    uint64_t total_yields = atomic_load(&args.yield_calls);
    double ops_per_sec = (double)total_ops / elapsed_sec;
    uint64_t total_ctx = (ctx_after >= ctx_before) ? (ctx_after - ctx_before) : 0;

    printf("\n==================== FINAL STRESS TEST RESULTS ====================\n");
    printf("Pinned CPU Core:      CPU %d\n", target_cpu);
    printf("Actual Duration:      %.4f seconds\n", elapsed_sec);
    printf("Total Compute Ops:    %lu floating-point ops\n", total_ops);
    printf("Average Throughput:   %.2f Mops/sec (%.3f Gops total)\n", ops_per_sec / 1e6, (double)total_ops / 1e9);
    printf("Total Yield Calls:    %lu calls (%.2f yields/sec)\n", total_yields, (double)total_yields / elapsed_sec);
    printf("Total Context Sw:     %lu switches (%.2f ctx/sec)\n", total_ctx, (double)total_ctx / elapsed_sec);
    printf("===================================================================\n");

    return 0;
}
