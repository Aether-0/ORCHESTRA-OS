FINDING ID: F6  
TITLE: Stage-7 BPF compiles against 6.12 headers but cannot load on Linux 7.0.12 (missing scx_bpf_dispatch)  
SEVERITY: HIGH  
TEST ID: T-load-register  
STATUS: FAIL (load) / PASS (compile with 6.12 headers)

OBSERVATION:  
After installing bpftool and libbpf-dev, `orchestra_bridge` linked. `bpftool btf dump` produced `vmlinux.h`. Compile against linux-source-7.0 `common.bpf.h` failed with undeclared `scx_bpf_dispatch`. Compile against v6.12.96 `scx/common.bpf.h` plus this host’s `vmlinux.h` succeeded. `sudo bpftool struct_ops register` returned 255. libbpf: `extern (func ksym) 'scx_bpf_dispatch': not found in kernel or module BTFs`. sched_ext state stayed disabled. Kernel BTF lists `scx_bpf_dsq_insert`, `scx_bpf_dsq_insert_vtime`, not `scx_bpf_dispatch`.

EXPECTED:  
On a 6.12.x sched_ext kernel matching the source comments, struct_ops register enables the scheduler.

EVIDENCE:  
- `build/bpf_stage7b.stderr` (7.0 headers)  
- `build/bpf_612b.stderr` (compile PASS, 2 warnings)  
- `sched_ext/register.stderr`  
- `sched_ext/scx_kfuncs.txt`  
- `orchestra_scx_stage7.bpf.c` lines 5–8, 31–34  

REPRODUCIBILITY: 1/1 load attempt; compile against 7.0 headers 1/1 fail; compile against 6.12 headers 1/1 pass.

FIRST FAILURE POINT: libbpf ksym resolution of `scx_bpf_dispatch` against 7.0.12 BTF.

LIKELY COMPONENT: Kernel / BPF verifier / sched_ext API version.

MOST LIKELY CAUSE: Upstream rename of dispatch kfuncs to dsq_insert after 6.12. Object is built for 6.12 names.

ALTERNATIVE CAUSES: Wrong object; bpftool bug; missing BTF. Unlikely: same BTF dumped 137k-line vmlinux.h containing `scx_bpf_dsq_insert`.

EVIDENCE AGAINST ALTERNATIVES: Explicit kfunc list from this kernel.

CONFIDENCE: HIGH  

IMPACT: No physical KERNEL_PROTOTYPED attach on this Kali 7.0.12 host without an approved API port or a 6.12 kernel.

RECOMMENDATION: Do not mechanically rewrite dispatch→insert in this campaign. Developers should review 7.0 `compat.bpf.h` insert/move semantics and update wrappers + `ORCHESTRA_SCX_API_VERSION` after review, or boot 6.12.96.

IMPLEMENTATION MODIFIED: NO.
