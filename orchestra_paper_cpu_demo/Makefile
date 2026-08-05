CC ?= gcc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Wformat=2 -Werror
CHECK_CFLAGS ?= -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Wformat=2 -Werror
LDLIBS ?= -lm

TARGET = orchestra_paper_cpu

all: $(TARGET)

$(TARGET): orchestra_paper_cpu.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

check:
	$(CC) $(CHECK_CFLAGS) -fsyntax-only orchestra_paper_cpu.c

clean:
	rm -f $(TARGET)

.PHONY: all check clean
