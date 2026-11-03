# teraflix

teraflix is a maintained consolidation of [Zagitta/gpu-unlock](https://github.com/Zagitta/gpu-unlock)
2.0.0 (`7eb51bccae0a0b7e599e084d971170e9a1e82d0c`). It is a Linux kernel module
that removes NVIDIA's half-rate FP16 / BF16 / TF32 tensor-core cap on GeForce
RTX 20, 30, and 40 cards before the stock driver binds. The module is still
named `gpu_unlock`, so the upstream command line and initramfs hooks keep
working. Packaging, firmware extraction, and the GPL-2.0-only license are
unchanged in structure.

The primary board for this tree is the **GeForce RTX 4070 (AD104, `10de:2786`)**,
including when that card is passed through to a Linux guest. The 4070 Ti
(`10de:2782`) is the same AD104 chip and the same recipe, and it has a
published BF16 result in the upstream table (81 to 150 TFLOPS). `2786` is
therefore **family-supported**: the recipe and the chip check are the ones
that already ran on the 4070 Ti, and this exact SKU still needs a measurement
on the machine that owns it. It is not lumped in with untested Turing or with
GA107.

An RTX A4000 (`10de:24b0`) is a professional card. It already runs the full
tensor rate. teraflix does not list it and will not touch it.

## License and credit

GPL-2.0-only. See `LICENSE`, `licenses/`, and `firmware/NOTICE.md`. NVIDIA
firmware is not stored in git. The build downloads the pinned 610.43.03
inputs over HTTPS, checks their SHA-256, and generates firmware locally.
Those inputs stay under NVIDIA's own terms.

The transaction, payload, and recipes come from Zagitta's gpu-unlock, which
itself credits the cmpunlocker V67 work and the public GA102/AD102 register
notes. Device IDs and small fixes taken from forks are listed with the source
commit in [docs/FORK-AUDIT.md](docs/FORK-AUDIT.md).

Nobody associated with this tree ships a coin, a website unlocker, or a
closed installer. Treat those as unrelated, the same way the upstream FAQ does.

## What it changes

GeForce cards ship with speed-selector registers that cap tensor issue rate.
The module runs before `nvidia` binds, opens the privilege mask that covers
those registers, writes the documented full-rate pair (`SS0=0x88888888`,
`SS1=0x8`), and function-level-resets the card so the stock driver starts
clean. Gaming and FP32 CUDA are outside that pair. INT8 / FP8 / INT4 paths
are not what this changes. A fuller account of the registers is in
[docs/How Ampere was unlocked.md](docs/How Ampere was unlocked.md).

The preset is chosen at boot, not by a live switch. [docs/CONTROLS.md](docs/CONTROLS.md)
lists every knob, what was investigated and left out, and how to put the
selectors back.

## Supported GPUs

`python3 tools/teraflix.py list` prints the table the module actually uses.
Confidence:

| Level | Meaning |
| --- | --- |
| validated | Upstream calls the Ampere desktop SKU stable, or the Ada SKU is in the published BF16 table (4070 Ti, 4080, 4090). |
| family | Same chip recipe as a validated SKU. The RTX 4070 `2786` is here, next to the 4070 Ti. |
| experimental | Turing, engineering samples, CMP boards, laptops whose power-off behaviour is unsettled, and GA107. `gpu_unlock.experimental=0` skips these. |

Blackwell (RTX 50) is not supported. vGPU / GRID virtual functions are refused.

## Install

The package flow is the upstream one:

```sh
git clone https://github.com/Commander17X/teraflix
cd teraflix
make install
```

`make install` picks Arch, Debian/Ubuntu, or Fedora/RHEL from `/etc/os-release`.
`make install-deb`, `make install-rpm`, and `make install-arch` force one.
The packages put `gpu_unlock` and its generated firmware in the initramfs so
it loads before `nvidia`.

Then add the opt-in to the kernel command line. Without it the module loads
and returns without touching a card.

```
gpu_unlock.targets=all
```

On a 4070 guest, do one dry boot first:

```
gpu_unlock.targets=all gpu_unlock.dry_run=1
```

`journalctl -k -b | grep gpu_unlock` should name `AD104 GeForce RTX 4070` and
say `dry-run`. Then drop `dry_run` and reboot with `gpu_unlock.rate=full`.
`experimental=0` still covers this 4070, because it is family-supported.

GRUB: add the tokens to `GRUB_CMDLINE_LINUX_DEFAULT` and run `update-grub`
(Debian/Ubuntu) or `grub-mkconfig -o /boot/grub/grub.cfg` (Arch). Fedora:
`sudo grubby --update-kernel=ALL --args="gpu_unlock.targets=all"`.
systemd-boot: the `options` line of the entry. UKI: `/etc/kernel/cmdline`,
then regenerate.

Check after a real boot:

```sh
python3 tools/teraflix.py status
python3 tools/teraflix.py check
journalctl -k -b | grep gpu_unlock
```

Status is also `/sys/kernel/gpu_unlock/status` once the module was loaded
with `targets=` set.

A passthrough guest has its own order of operations:
[docs/PASSTHROUGH-4070.md](docs/PASSTHROUGH-4070.md).

## Benchmark

Throughput changes only after a boot that actually wrote the selectors.
Record one boot at the power-on default and one boot at full rate:

```sh
python3 tools/benchmark.py --self-test
python3 tools/benchmark.py --save before.json   # stock boot, driver loaded
python3 tools/benchmark.py --save after.json    # full-rate boot, driver loaded
python3 tools/benchmark.py --compare before.json after.json
```

The measurement is a large BF16 `torch.matmul` when PyTorch with CUDA is
installed. It does not write GPU registers. `--self-test` checks the
comparison math and does not need a GPU.

## Windows

There is no Windows kernel driver in this tree. The UEFI port and the reason
it was not vendored are in [windows/README.md](windows/README.md).
`windows/status.ps1` only prints device ids.

## Build and test without a GPU

```sh
make test-unit
make -C kernel/gpu_unlock KDIR=/usr/src/linux-headers-$(uname -r) KCFLAGS=-Werror
```

GitHub Actions runs the unit tests and builds the module the way upstream CI
does. Firmware generation in the package jobs needs the pinned NVIDIA
downloads. Loading the module on real hardware, and any number it prints, is
not something CI can do.

## What still needs the 4070

This repository was prepared without the card in the build environment. Still
to confirm on the guest: `lspci` shows `10de:2786` (or `2709` for the rare
AD103 4070), the module's chip check reads `0x194` for AD104, the post-FLR
selector readback matches the preset under this hypervisor, and a BF16 matmul
moves. Details and the revert steps are in the passthrough guide.
