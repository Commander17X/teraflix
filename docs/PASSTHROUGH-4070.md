# RTX 4070 in a Linux guest

This is the path for an AD104 GeForce RTX 4070 passed through to a KVM guest
(Proxmox, libvirt, or plain QEMU). The card this was written for is
`10de:2786`. A few 4070 boards are AD103 `10de:2709` instead; that id is in
the same family table and uses the same command line. The laptop parts
`2820` and `2860` are AD106M and stay experimental. They are not this guide.

An RTX A4000 (`10de:24b0`) is the wrong card for this test. It is already
full-rate, and the module has no entry for it.

Nothing in this guide was executed on a 4070. The build and unit tests run
without one. The steps below are what to verify on the guest, and what
failure looks like in the log.

## How passthrough interacts with the unlock

The sequence runs in the **guest**, from the initramfs, before `nvidia`
binds. The host only assigns the PCI device.

Selectors survive the FLR the module performs. That is intentional: the
driver must still see them. They reset when the GPU loses power. A guest
reboot is usually just another FLR, issued by QEMU, so:

- Every guest boot must load `gpu_unlock` again before `nvidia`. The packages
  do that via initramfs.
- A guest reboot does not relock the card.
- Stopping the VM often resets the device with FLR as well. Assume the
  selectors are still there until you have evidence they are not.
- Host runtime D3cold does clear them. On the host, keep vfio from suspending
  the GPU: `options vfio-pci disable_idle_d3=1`.

The module logs `hypervisor guest` when the CPUID hypervisor bit is set, and
`/sys/kernel/gpu_unlock/status` shows `guest=1` plus the DMI product string
(often `QEMU` or `Standard PC`). Virtual functions are refused. Do not add a
mediated vGPU device to this VM.

`pcie_flr()` inside the guest is the step most likely to misbehave under
QEMU. If the log reaches the selector write and then fails the post-FLR
check, the hypervisor reset cleared the selectors or the card did not come
back. Do not paper over that by ignoring the check. Record the `stage=flr`
line and the QEMU version.

## Host

1. Confirm the function you will pass through:

   ```sh
   lspci -nn -d 10de:
   ```

   You want `10de:2786` (AD104 RTX 4070) or, less often, `10de:2709`.
   Pass through the VGA/3D function and its audio function. Leave the rest
   of the host's NVIDIA devices alone.

2. Enable the IOMMU and bind those functions to vfio-pci. Proxmox's PCI
   device dialog does this when the GPU is marked as a PCIe passthrough
   device. The equivalent libvirt device is `hostdev` with `managed="yes"`.

3. Machine type `q35`, OVMF, CPU model `host`. Leave the option ROM enabled
   the first time. Do not add a vGPU mdev, and do not hide the hypervisor
   unless you already know you need that for something else. teraflix uses
   the hypervisor bit only as a log line.

4. Install the vfio idle setting and rebuild the host initramfs if the GPU
   disappears or the guest finds it powered down:

   ```
   options vfio-pci disable_idle_d3=1
   ```

5. Start the guest only after the host shows the device owned by vfio-pci.

## Guest

1. Install a normal distribution kernel, headers, and the NVIDIA driver
   packages, but do not let `nouveau` bind:

   ```
   # /etc/modprobe.d/blacklist-nouveau.conf
   blacklist nouveau
   options nouveau modeset=0
   ```

2. Build teraflix from this tree (`make install`, or `make install-deb` /
   `make install-rpm` / `make install-arch`). The packages install the DKMS
   module, the generated firmware, and the initramfs drop-in.

3. First boot, dry run. Add this to the guest kernel command line and reboot:

   ```
   gpu_unlock.targets=all gpu_unlock.dry_run=1
   ```

   Then:

   ```sh
   python3 tools/teraflix.py check
   python3 tools/teraflix.py status
   journalctl -k -b | grep gpu_unlock
   ```

   A matching 4070 prints `AD104 GeForce RTX 4070 [family] dry-run` (or the
   AD103 line for `2709`). `check` should show the hypervisor flag. If the
   line says the device is not in the table, stop. If it says
   `skipped-vgpu`, the VM was given a virtual function.

4. Second boot, real preset. Replace the dry-run tokens with:

   ```
   gpu_unlock.targets=all gpu_unlock.rate=full
   ```

   `gpu_unlock.experimental=0` is optional. The 4070 ids `2786` and `2709`
   are family-supported, so they still run. Add `nvidia-drm.modeset=1` when
   the guest should drive a display.

5. Confirm the handoff:

   ```sh
   journalctl -k -b | grep gpu_unlock
   cat /sys/kernel/gpu_unlock/status
   ```

   You want `disposition=unlocked` and a `stage=flr` line whose `ss0` is
   `0x88888888` and `ss1` is `0x8`. `lspci -nnk` should show `nvidia` on the
   device after that. `disposition=failed` with `-ENODEV` on the chip check
   means PMC_BOOT_0 was not `0x194` (AD104) or `0x193` (AD103). Do not force
   past that.

6. Measure. Install PyTorch with CUDA, then:

   ```sh
   python3 tools/benchmark.py --save after.json
   ```

   A stock number needs a separate boot at the power-on selectors. Set
   `gpu_unlock.rate=stock`, **shut the VM down**, and reset the GPU from the
   host so it loses power (a guest reboot is not enough if the log still
   shows `0x88888888` on the next dry read). Boot, confirm status says
   `stock`, load the driver, and `--save before.json`. Compare:

   ```sh
   python3 tools/benchmark.py --compare before.json after.json
   ```

   The upstream 4070 Ti row went from 81 to 150 BF16 TFLOPS. A 4070 has
   fewer tensor cores, so the absolute numbers will be lower. The ratio is
   the thing to keep. Clocks and the power limit have to be comparable
   between the two boots or the ratio is not the cap.

## Relock

1. Set `gpu_unlock.rate=stock` and remove `rewrite` if it is set.
2. Shut the guest down and power-cycle the GPU from the host.
3. Boot and read `/sys/kernel/gpu_unlock/status`. Disposition should be
   `stock`. A benchmark on that boot is the locked rate only if the card
   really lost power. If `ss` values in a later full attempt still show the
   old pair before any write, the reset was an FLR.
4. To store the documented power-on pair through the sequence itself, one
   boot with `gpu_unlock.rate=stock gpu_unlock.rewrite=1` is the explicit
   path. It is the same firmware transaction as an unlock, with `0x1` / `0x1`
   instead of the full-rate pair. Remove `rewrite` afterwards.

## What this environment could not check

- The guest `lspci` id and the PMC_BOOT_0 value on the owner's 4070.
- Whether this QEMU builds an FLR that leaves `SS0` intact. The module fails
  the boot if the post-FLR readback does not match the preset.
- Temperature and the achieved BF16 ratio at the card's stock power limit.
- Laptop 4070s (`2820`, `2860`). They are a different die and are experimental.
- Suspend inside the guest. The module's resume hook is the upstream one and
  has not been run here.
- Secure Boot signing of the DKMS module. If the guest enforces Secure Boot,
  the module must be signed with a key the firmware trusts or it will not
  load from the initramfs. That is a distribution signing step, not a
  different recipe.
