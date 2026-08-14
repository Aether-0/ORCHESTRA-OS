CC ?= gcc

.PHONY: all check test test-unit test-integration clean

all:
	$(MAKE) -C orchestra_paper_cpu_demo

check:
	$(MAKE) -C orchestra_paper_cpu_demo check
	@if command -v clang >/dev/null 2>&1; then \
		clang -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow \
			-Wformat=2 -Werror -fsyntax-only \
			orchestra_paper_cpu_demo/orchestra_paper_cpu.c; \
		for publication_mode in 0 1; do \
			clang -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow \
				-Wformat=2 -Werror -pthread \
				-DORCHESTRA_SIGNAL_PUBLICATION_LEGACY=$$publication_mode \
				-fsyntax-only tools/benchmark/signal_publication_microbenchmark.c; \
		done; \
		clang -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow \
			-Wformat=2 -Werror -fsyntax-only \
			tests/integration/test_signal_publication_integration.c; \
	fi
	@for publication_mode in 0 1; do \
		$(CC) -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow \
			-Wformat=2 -Werror -pthread \
			-DORCHESTRA_SIGNAL_PUBLICATION_LEGACY=$$publication_mode \
			-fsyntax-only tools/benchmark/signal_publication_microbenchmark.c; \
	done
	@$(CC) -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow \
		-Wformat=2 -Werror -fsyntax-only \
		tests/integration/test_signal_publication_integration.c
	@$(CC) -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow \
		-Wformat=2 -Werror -Ikernel/sched_ext/include -fsyntax-only \
		kernel/sched_ext/bridge/orchestra_bridge.c
	@if printf '#include <bpf/libbpf.h>\n' | $(CC) -E - >/dev/null 2>&1; then \
		$(CC) -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow \
			-Wformat=2 -Werror -Ikernel/sched_ext/include -fsyntax-only \
			kernel/sched_ext/bridge/orchestra_loader.c; \
	fi
	@$(CC) -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow \
		-Wformat=2 -Werror -fsyntax-only kernel/sched_ext/orchestra_scx.c
	@PYTHONPYCACHEPREFIX=/tmp/orchestra-os-check-pyc \
		python3 -m py_compile \
		tools/benchmark/run_paper_cpu_benchmark.py \
		tools/benchmark/run_signal_publication_microbenchmark.py \
		tools/plotting/plot_paper_cpu_smoke.py \
		tools/plotting/plot_release_readiness.py \
		tools/reporting/build_release_readiness_docx.py \
		tools/testing/capture_test_run.py \
		tools/testing/index_test_artifacts.py \
		tests/integration/validate_paper_cpu_csv.py \
		tests/integration/test_validate_paper_cpu_csv.py \
		tests/unit/test_benchmark_validator.py \
		tests/unit/test_signal_publication_microbenchmark_runner.py
	@python3 -m json.tool experiments/manifests/paper_cpu_smoke_v1.json >/dev/null
	@python3 -m json.tool experiments/schemas/paper_cpu_metrics_v2.json >/dev/null
	@python3 -m json.tool experiments/schemas/paper_cpu_metrics_v3.json >/dev/null
	@python3 -m json.tool experiments/schemas/paper_cpu_metrics_v4.json >/dev/null
	@python3 -m json.tool experiments/schemas/paper_cpu_metrics_v7.json >/dev/null
	@python3 -m json.tool experiments/manifests/paper_cpu_exploratory_v3.json >/dev/null
	@python3 -m json.tool experiments/manifests/paper_cpu_exploratory_v4.json >/dev/null
	@bash -n tests/unit/run.sh tests/integration/run.sh
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck tests/unit/run.sh tests/integration/run.sh; \
	fi

test-unit:
	./tests/unit/run.sh

test-integration:
	./tests/integration/run.sh

test: check test-unit test-integration

clean:
	$(MAKE) -C orchestra_paper_cpu_demo clean
