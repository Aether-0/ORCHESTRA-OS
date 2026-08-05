CC ?= gcc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Wpedantic
LDLIBS ?= -lm

all: orchestra_real_cpu

orchestra_real_cpu: orchestra_real_cpu.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

clean:
	rm -f orchestra_real_cpu results.csv

.PHONY: all clean
