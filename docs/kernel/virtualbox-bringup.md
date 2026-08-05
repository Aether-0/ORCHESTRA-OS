# ORCHESTRA-OS sched_ext VirtualBox Bring-Up Guide

**Stage 6 — sched_ext MVP**

## 1. VirtualBox Guest Configuration

Create a VM with:

| Setting | Recommended |
|---------|-------------|
| OS Type | Linux (64-bit) |
| vCPUs | 4 |
| RAM | 8 GB |
| Disk | 40 GB dynamically allocated VDI |
| Chipset | I/O APIC enabled |
| EFI | Disabled (BIOS boot) |
| Network | NAT or host-only |
| Serial | COM1 enabled, port mode: Raw File at `/tmp/vm-serial.log` |

Host: [VirtualBox 7.0+](https://www.virtualbox.org/)

## 2. Guest OS Installation

Recommended: Ubuntu 24.04 LTS (or Debian 12) minimal server.

After guest install:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential clang llvm libelf-dev \
    libbpf-dev bpftool dwarves flex bison libssl-dev \
    bc rsync git curl wget pahole

# Verify tool versions
clang --version | head -1
bpftool version
```

Record exact versions in evidence.

## 3. Kernel Source

```bash
export ORCHESTRA_KERNEL_SRC="$HOME/linux"

# Clone the latest stable kernel (6.12+ required)
git clone --depth 1 --branch v6.12 \
    https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git \
    "$ORCHESTRA_KERNEL_SRC"

cd "$ORCHESTRA_KERNEL_SRC"
git rev-parse HEAD  # record this commit
```

## 4. Kernel Configuration

```bash
cd "$ORCHESTRA_KERNEL_SRC"

# Verify required config options
/path/to/orchestra-os/kernel/sched_ext/scripts/check_kernel_config.sh "$ORCHESTRA_KERNEL_SRC"

# If not present, start from distro config and enable:
cp /boot/config-$(uname -r) .config
make olddefconfig

# Enable sched_ext requirements
scripts/config -e CONFIG_BPF
scripts/config -e CONFIG_BPF_SYSCALL
scripts/config -e CONFIG_BPF_JIT
scripts/config -e CONFIG_DEBUG_INFO_BTF
scripts/config -e CONFIG_SCHED_CLASS_EXT
scripts/config -e CONFIG_BPF_EVENTS

make olddefconfig
```

## 5. Kernel Build

```bash
cd "$ORCHESTRA_KERNEL_SRC"
make -j$(nproc)
make modules -j$(nproc)
sudo make modules_install
sudo make install

# Update bootloader (GRUB)
sudo update-grub

# Verify the new kernel is in the boot menu
grep menuentry /boot/grub/grub.cfg | head -5
```

## 6. Boot Custom Kernel

```bash
# Reboot and select the new kernel in GRUB
sudo reboot

# After boot, verify
uname -r
cat /sys/kernel/sched_ext/state
# Should show nothing (no sched_ext scheduler loaded yet)
```

## 7. Build ORCHESTRA Scheduler

On the guest VM:

```bash
cd $ORCHESTRA_KERNEL_SRC/tools/bpf/bpftool
make

export ORCHESTRA_OS="/path/to/orchestra-os"

cd "$ORCHESTRA_OS/kernel/sched_ext"

# Build the BPF program
clang -O2 -target bpf -g \
    -I "$ORCHESTRA_KERNEL_SRC/tools/lib" \
    -I "$ORCHESTRA_OS/kernel/sched_ext/include" \
    -I "$ORCHESTRA_KERNEL_SRC/include" \
    -I "$ORCHESTRA_KERNEL_SRC/include/uapi" \
    -c orchestra_scx.bpf.c -o orchestra_scx.bpf.o

# Verify BPF verifier accepts it
sudo bpftool prog load orchestra_scx.bpf.o \
    /sys/fs/bpf/orchestra_scx type sched_ext 2>&1

# Generate skeleton and build loader
bpftool gen skeleton orchestra_scx.bpf.o > orchestra_scx.skel.h

cc -O2 -Wall -Wextra -Werror \
    orchestra_scx.c -o orchestra_scx -lbpf -lelf -lz
```

## 8. Test Load/Unload

```bash
# Load (requires root)
sudo ./orchestra_scx &
SCX_PID=$!

# Check status
cat /sys/kernel/sched_ext/state
# Should show "orchestra_scx_stage6"

# Run test workload
sleep 5

# Unload
sudo kill $SCX_PID
wait $SCX_PID

# Verify clean return
cat /sys/kernel/sched_ext/state
# Should be empty
```

## 9. Safety: Known-Good Kernel Fallback

Before loading the ORCHESTRA scheduler, **create a VirtualBox snapshot**:

```
Machine → Take Snapshot → "Pre-ORCHESTRA kernel"
```

If the custom kernel fails to boot:
1. Force power-off the VM
2. Restore the snapshot
3. Boot into the original distribution kernel
4. Fix the configuration and rebuild

If the scheduler causes a panic/stall:
1. Use the serial console to observe logs
2. If stuck, power-cycle and boot the known-good kernel
3. Restore from snapshot and re-test

## 10. Serial Console Logging

To capture boot and scheduler logs:

```bash
# In guest, add to /etc/default/grub:
GRUB_CMDLINE_LINUX="console=tty0 console=ttyS0,115200n8"
sudo update-grub

# On host, access:
cat /tmp/vm-serial.log
```

## 11. Evidence Collection

After each successful run, collect:

```bash
mkdir -p artifacts/test-results/$(date +%Y-%m-%d)/sched-ext-vbox-mvp/

cd "$ORCHESTRA_OS"
git rev-parse HEAD > artifacts/test-results/DATE/sched-ext-vbox-mvp/repo-commit.txt
cd "$ORCHESTRA_KERNEL_SRC"
git rev-parse HEAD > "$ORCHESTRA_OS"/artifacts/test-results/DATE/sched-ext-vbox-mvp/kernel-commit.txt
uname -r > "$ORCHESTRA_OS"/artifacts/test-results/DATE/sched-ext-vbox-mvp/kernel-release.txt
cp .config "$ORCHESTRA_OS"/artifacts/test-results/DATE/sched-ext-vbox-mvp/kernel-config.txt
```

## 12. Recovery Procedure

| Problem | Action |
|---------|--------|
| Custom kernel won't boot | GRUB → select previous kernel → remove bad entry |
| Scheduler load fails | Check `dmesg`, verify BTF, rebuild BPF program |
| Scheduler stalls | Ctrl+C the loader → if stuck, `echo 1 > /proc/sys/kernel/sysrq` then `echo b > /proc/sysrq-trigger` |
| VM frozen | Force power-off, restore snapshot |
| All else fails | Delete VM, recreate from ISO + snapshot |
