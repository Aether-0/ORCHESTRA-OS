#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <pthread.h>
#include <unistd.h>
#include <stdatomic.h>
#include <sys/resource.h>

typedef struct {
    int thread_id;
    volatile bool stop;
    _Atomic uint64_t ops_completed;
} worker_args_t;

void* worker_func(void* arg) {
    worker_args_t* w = (worker_args_t*)arg;
    double x = 1.000001;

    while (!w->stop) {
        for (int i = 0; i < 1000; i++) {
            x = x * 1.0000001 + 0.0000001;
        }
        atomic_fetch_add(&w->ops_completed, 1000);
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
    int num_threads = 4;
    uint64_t duration_s = 180; // 3 minutes = 180s

    if (argc >= 2) num_threads = atoi(argv[1]);
    if (argc >= 3) duration_s = strtoull(argv[2], NULL, 10);

    printf("==================================================\n");
    printf("ORCHESTRA-OS CPU Compute Benchmark (3 Minutes)\n");
    printf("Threads: %d | Target Duration: %lu seconds (%.1f minutes)\n", 
           num_threads, duration_s, (double)duration_s / 60.0);
    printf("==================================================\n\n");

    pthread_t threads[num_threads];
    worker_args_t args[num_threads];

    uint64_t ctx_before = get_ctx_switches();
    struct timespec start_time, end_time;
    clock_gettime(CLOCK_MONOTONIC, &start_time);

    for (int i = 0; i < num_threads; i++) {
        args[i].thread_id = i;
        args[i].stop = false;
        atomic_init(&args[i].ops_completed, 0);
        pthread_create(&threads[i], NULL, worker_func, &args[i]);
    }

    printf("Benchmark running... Progress updates every 15s:\n");
    fflush(stdout);

    uint64_t remaining = duration_s;
    uint64_t step = 15;
    uint64_t elapsed_total = 0;

    while (remaining > 0) {
        uint64_t sleep_time = (remaining < step) ? remaining : step;
        sleep(sleep_time);
        elapsed_total += sleep_time;
        remaining -= sleep_time;

        uint64_t current_ops = 0;
        for (int i = 0; i < num_threads; i++) {
            current_ops += atomic_load(&args[i].ops_completed);
        }

        double live_mops = (double)current_ops / (double)elapsed_total / 1e6;

        printf("[%3lus / %3lus] Progress: %5.1f%% | Completed: %7.2f Mops | Rate: %7.2f Mops/s\n", 
               elapsed_total, duration_s, (double)elapsed_total / duration_s * 100.0,
               (double)current_ops / 1e6, live_mops);
        fflush(stdout);
    }

    // Stop workers
    for (int i = 0; i < num_threads; i++) {
        args[i].stop = true;
    }

    for (int i = 0; i < num_threads; i++) {
        pthread_join(threads[i], NULL);
    }

    clock_gettime(CLOCK_MONOTONIC, &end_time);
    uint64_t ctx_after = get_ctx_switches();

    double elapsed_sec = (end_time.tv_sec - start_time.tv_sec) + 
                        (end_time.tv_nsec - start_time.tv_nsec) / 1e9;

    uint64_t total_ops = 0;
    for (int i = 0; i < num_threads; i++) {
        total_ops += atomic_load(&args[i].ops_completed);
    }

    double ops_per_sec = (double)total_ops / elapsed_sec;
    uint64_t total_ctx = (ctx_after >= ctx_before) ? (ctx_after - ctx_before) : 0;

    printf("\n==================== FINAL RESULTS ====================\n");
    printf("Target Duration:      %lu seconds (3.0 minutes)\n", duration_s);
    printf("Actual Duration:      %.4f seconds\n", elapsed_sec);
    printf("Total Compute Ops:    %lu floating-point ops\n", total_ops);
    printf("Compute Throughput:   %.2f Mops/sec (%.3f Gops total)\n", ops_per_sec / 1e6, (double)total_ops / 1e9);
    printf("Total Context Sw:     %lu switches (%.2f ctx/sec)\n", total_ctx, (double)total_ctx / elapsed_sec);
    printf("Per-Thread Average:   %.2f Mops/sec\n", (ops_per_sec / num_threads) / 1e6);
    printf("=======================================================\n");

    return 0;
}
