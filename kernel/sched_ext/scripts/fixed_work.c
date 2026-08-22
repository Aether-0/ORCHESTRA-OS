/*
 * Fixed-iteration CPU work for completion-time benches.
 * Wall time varies with scheduler; unlike a timed busy-loop.
 */
#include <stdlib.h>

int main(int argc, char **argv)
{
    unsigned long n = 80000000UL;
    volatile unsigned long x = 1;
    unsigned long i;

    if (argc > 1)
        n = strtoul(argv[1], NULL, 10);
    for (i = 0; i < n; i++)
        x = x * 3UL + 1UL;

    /*
     * The result is deliberately not part of the benchmark contract.  The
     * volatile accumulator keeps the fixed work observable, while returning
     * success lets harnesses distinguish completed work from an execution
     * failure using the normal process-status convention.
     */
    (void)x;
    return 0;
}
