# Executive summary

Next Kali real-machine testing is prepared at the userspace and tool level.

Ready now:

- repository commit recorded;
- kernel capability gate passed;
- userspace build and regression evidence captured;
- target-specific BTF header generated;
- existing bridge, loader, and fixed workload built.

Still required on the physical target:

- exact matching full kernel source for the running kernel;
- libbpf/libelf development inputs;
- target-side BPF compilation and hashing;
- root BPF inventory;
- safe loader-only attach, ownership, action, unload, and baseline gates.

The BPF scheduler was deliberately not built from the available 7.2.0-rc6
source against the 7.0.12 running kernel. The prior intermittent userspace
signal-stop teardown failure is preserved; a later complete captured run passed
and three direct integration reruns passed.
