# Comparison ownership gate

The comparison used the same `fixed_work` binary, 600,000,000 iterations, CPU affinity, and three repetitions for worker counts 1, 2, and 4. An ORCHESTRA timing row is valid only when every target PID has an exact status line with positive accepted and dispatched counters.

The nine ORCHESTRA rows are preserved in `orchestra_matrix.csv`: 2/9 passed the all-target ownership gate and 7/9 failed it. Rows with failed ownership remain in the raw dataset, but their elapsed values are not treated as ORCHESTRA performance measurements. CFS completed all 9 matched rows and is the only valid performance baseline in this continuation.
