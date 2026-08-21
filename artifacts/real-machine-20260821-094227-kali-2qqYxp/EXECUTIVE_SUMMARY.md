# Executive summary

The campaign tested commit 07c787c4eeac01a2f9d60916577806d00863b15f on physical host kali, running Linux 7.0.12+kali-amd64. The sched_ext host gate, BTF/eBPF prerequisites, userspace regression gate, fresh BPF/bridge/loader build, verifier/attach path, and repeated scheduler lifecycle all passed.

The existing stage7 scheduler was the active sched_ext scheduler during three controlled load phases. It returned to the normal scheduler after every phase. No ORCHESTRA oops, panic, lockup, RCU stall, scheduler error, or unreleased ORCHESTRA pin/link was observed.

Per-task evidence demonstrated effective RUN, YIELD, and MIGRATE behavior and exposed deferred SLEEP and budgeted THROTTLE telemetry. SLEEP was not fully validated because no-early execution was not independently proven and the one-shot directive produced later bad-parameter fallbacks. A finite positive worker did not complete within a 20-second timeout; its status showed the published identity but zero per-task accepted/dispatched records. A matched CFS run of the same 10-billion-iteration workload completed in 5,036 ms. This is an ownership/forward-progress gate failure or inconclusive protocol result, not proof of a specific BPF defect, and runtime escalation was stopped.

The native CFS baseline matrix completed 12/12 runs. The existing three-second CFS stress smoke completed CPU, memory, I/O, and mixed phases with zero workload errors. An ORCHESTRA performance comparison and ORCHESTRA stress run were not claimed: the available comparison scripts have hard-coded paths and broad BPF cleanup, the stress script does not opt tasks into ORCHESTRA, and scx_simple/perf are unavailable.

The checked-out kernel prototype does not expose executable kernel implementations of the research signal bus, predictor, kernel S1/S2/S3/S4/Q, feedback controller, full hybrid real-time safety layer, NUMA policy, or distributed tier. Userspace tests for those concepts remain userspace validation only.

Findings: P0=0, P1=1, P2=4, P3=1. Tracked source files remained unchanged; the working tree still contains pre-existing untracked artifacts plus this campaign directory.

The referenced DOCX checklist was audited item by item: 519 items total; 94 PASS, 39 INCONCLUSIVE, 178 BLOCKED, and 208 NOT IMPLEMENTED. Kernel installation/boot/reboot items were not performed because they require explicit host-change approval.
