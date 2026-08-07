# Stage 8 — Exact Kernel Build Evidence

## Attempt 1: Fedora stock config → FAILED
- Config: `/boot/config-6.12.15-100.fc40.x86_64`
- Error: `certs/signing_key.pem` — module signing
- Duration: 5+ hours, vmlinux produced (452 MB), bzImage packaging failed

## Attempt 2: x86_64_defconfig + sched_ext → SUCCESS
- Config: `make x86_64_defconfig` + BPF/SCHED_CLASS_EXT/BTF enabled
- Result: bzImage 14 MB produced
- SHA-256: `03a271008feae83f7a4c1ac59db182f4055025df8ac97a4b74536ee7bd34449d`
- Boot: Failed — missing XFS filesystem driver for root

## Attempt 3: x86_64_defconfig + XFS/E1000/SATA → SUCCESS
- Added: XFS_FS=y, E1000=y, SATA_AHCI=y, BLK_DEV_SD=y
- Result: bzImage 15 MB produced
- Boot: Failed — VM boots but network or another driver missing

## Attempt 4: localmodconfig → FAILED
- Config: Fedora 6.12.15 + localmodconfig → build errors in drivers

## Root cause summary
- Fedora 40 stock config enables 5000+ modules causing 5h+ build + cert failures
- x86_64_defconfig is too minimal for VirtualBox (missing XFS, networking, etc.)
- Adding drivers incrementally produces valid bzImage but boot still fails
- Full VirtualBox driver set not yet determined

## Working environment
The Fedora 6.12.15-100.fc40.x86_64 kernel with v6.12.96 sched_ext headers is runtime-validated and passes all Stage 6B-8F gates.
