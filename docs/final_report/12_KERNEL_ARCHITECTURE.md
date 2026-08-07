# 12. Kernel Architecture

## Custom Kernel Build

ORCHESTRA Stage 8 achieved exact same-revision kernel alignment by building Linux v6.12.96 from source.

### Build Configuration
| Option | Value |
|--------|-------|
| Base config | `x86_64_defconfig` |
| SCHED_CLASS_EXT | y |
| DEBUG_INFO_BTF | y |
| DEBUG_INFO_DWARF5 | y |
| XFS_FS | y (root filesystem) |
| SATA_AHCI | y (disk controller) |
| E1000, E1000E | y (network) |
| BLK_DEV_SD | y |
| MODULE_SIG | n (disabled) |
| DEVTMPFS | y |
| BPF, BPF_SYSCALL, BPF_JIT | y |

### Build Command
```bash
export KSRC="$HOME/src/linux-v6.12.96"
export KBUILD="$HOME/build/linux-v6.12.96-stage8"
make -C "$KSRC" O="$KBUILD" x86_64_defconfig
# Enable options via scripts/config + direct append
make -C "$KSRC" O="$KBUILD" -j4
```

### Build Artifacts
- bzImage: 15 MB, SHA-256 `d3d50d26b3d1a91196318a2c99d1c71a859c3171b69276bd26414ae6dfa9e912`
- BTF: 6.4 MB, SHA-256 `7af6be54b981c04e7e57c2043f3cb0247e05e564ff65271138197fd8a91ca458`
- vmlinux.h: 166,619 lines

### Boot Configuration
- **BLS entry:** `/boot/loader/entries/<machine-id>-6.12.96.conf`
- **Critical fix:** `linux /boot/vmlinuz-6.12.96` (not `/vmlinuz-6.12.96`)
- **Root:** `root=UUID=...` (explicit, not `$kernelopts`)

### Attempt History
| Attempt | Config | bzImage | Boot | Root Cause |
|---------|--------|---------|------|------------|
| 1 | Fedora stock | Failed | — | Certificate signing |
| 2 | defconfig+sched_ext | 14 MB | ✗ | Missing XFS |
| 3 | +XFS/E1000/SATA | 15 MB | ✗ | Missing DEBUG_INFO (drops SCHED_CLASS_EXT) |
| 4 | localmodconfig | Failed | — | Build errors |
| 5 | **defconfig+all** | **15 MB** | **✓** | **All drivers present** |

### BLS Entry (Working)
```
title Fedora Linux (6.12.96 ORCHESTRA) 40 (Forty)
version 6.12.96
linux /boot/vmlinuz-6.12.96
initrd /boot/initramfs-6.12.96.img
options root=UUID=99ee1fbf-8f21-4e11-b06d-eff8ca27e837 ro net.ifnames=0 biosdevname=0
```
