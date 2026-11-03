# Controls

Every control here is a boot-time module parameter or a host setting that can
be removed. None of them flash a VBIOS, patch the proprietary driver, or
change a license check. The kernel command line is read when `gpu_unlock`
loads from the initramfs. Changing a parameter later does not rewrite a card
the driver already owns.

The CLI (`python3 tools/teraflix.py`) only reads sysfs, lspci, and the device
table. It never maps BAR0.

## Parameters

| Parameter | Default | What it does | Risk | Revert |
| --- | --- | --- | --- | --- |
| `gpu_unlock.targets` | unset | Opt-in. `all`, or comma-separated PCI addresses as `lspci -D` prints them (`0000:21:00.0`). With this unset the module returns immediately. | None until a later parameter asks for a write. | Delete the parameter and reboot. |
| `gpu_unlock.rate` | `full` | `full` stores `SS0=0x88888888` and `SS1=0x8`, the pair upstream has always written. `stock` stores nothing unless `rewrite=1`. | `full` raises tensor throughput and can raise temperature. Power and thermal limits stay the driver's. | `rate=stock` plus a real power-off of the GPU, or one boot with `rewrite=1`. |
| `gpu_unlock.ss0`, `gpu_unlock.ss1` | the full pair | Optional replacement pair used only with `rate=full`. Each SS0 nibble, and the one SS1 nibble, must be `0x0`, `0x1`, `0x8`, or `0x9`. | The field *encoding* is documented (bit 3 enables the override, bits 2:0 select full or half). Which nibble is FP16, TF32, or FP64 is not. Mixed nibbles are therefore a guess. Quarter-rate and eighth-rate encodings are unconfirmed and rejected. | Boot again with the parameters removed (`full`) or with `rate=stock` and `rewrite=1`. Power-off also returns the selectors to the power-on default. |
| `gpu_unlock.rewrite` | off | With `rate=stock`, run the same pre-driver sequence and store the documented power-on values `SS0=0x1`, `SS1=0x1`. | Same class of risk as an unlock boot: a firmware transaction and an FLR. Use it when FLR has preserved an old full-rate pair and you cannot cut GPU power. | Boot with `rate=full`, or power-cycle and leave `rewrite` unset. |
| `gpu_unlock.dry_run` | off | Log the matched card, confidence, and preset. Do not write. | None. | Remove the parameter. |
| `gpu_unlock.experimental` | on | When `0`, skip experimental ids (Turing, GA107, unsettled laptops, engineering samples, CMP). Family-supported ids, including the RTX 4070 `2786`, still run. | Leaving it on tries recipes that have not been measured on that SKU. A chip-id mismatch aborts with `-ENODEV` before FWSEC starts. | Set `0`, or remove the parameter to restore the default. |
| `gpu_unlock.resume` | on | After suspend-to-RAM, re-apply the preset before `nvidia` resumes the card. Writable at `/sys/module/gpu_unlock/parameters/resume`. | Adds about a second to resume. Hibernation is not covered. | `gpu_unlock.resume=0` or write `0` to that sysfs parameter. |

`/sys/kernel/gpu_unlock/status` appears after a boot that set `targets`. It
reports whether the kernel thinks it is a guest, the DMI vendor and product,
the preset, and one line per matched card (`disposition` is `dry-run`,
`stock`, `unlocked`, `failed`, `skipped-experimental`, `skipped-vgpu`,
`not-cold`, or `busy`).

## What "reversible" means

The selectors survive the module's FLR. That is how the stock driver still
sees them. They go back to the power-on default when the GPU loses power.
A guest reboot, and many hypervisor resets, are only an FLR, so they do not
relock the card by themselves.

Practical revert, in order:

1. Set `gpu_unlock.rate=stock` and **power off the GPU** (host shutdown, or a
   passthrough stop that actually removes power). The next boot writes nothing.
2. If the selectors are still full after that, because the reset was only an
   FLR, boot once with `gpu_unlock.rate=stock gpu_unlock.rewrite=1`. That
   stores `0x1` / `0x1` and checks that the FLR kept them.
3. Removing the packages removes the module from later initramfs images. It
   does not by itself clear selectors that are already sticky.

`disposition=not-cold` means the feature privilege mask was already fully
open, so the module refused to start another sequence. Power-cycle the GPU
before changing presets.

## Laptop power

Upstream already re-applies the preset after suspend-to-RAM. The remaining
laptop failure is runtime D3cold: the embedded controller powers the dGPU off
when idle, which clears the selectors, and the desktop module is not in a
position to run the sequence again under the live driver.

The reversible workaround is the driver's own parameter, not a new register
write:

```
# /etc/modprobe.d/nvidia-power.conf
options nvidia NVreg_DynamicPowerManagement=0x00
```

Delete that file and regenerate the initramfs to restore runtime power
management. Results on laptops stay mixed; those device ids are marked
experimental unless they are Ampere ids whose recipe is the validated
desktop one (those are `family`, with this caveat).

A 460-line runtime-PM patch (unya, gpu-unlock PR #251) was not merged. It
rewrites the coordinator and was still a draft.

## Investigated and not included

These came up in forks, related projects, or the register map. They are not
controls in teraflix.

| Idea | Why it is not here |
| --- | --- |
| NVENC session cap | Enforced in the proprietary encode library, not in SS0/SS1. Removing it is a license restriction bypass. |
| vGPU / GRID license | Out of scope. The module also refuses PCI virtual functions, so it will not bind a vGPU. |
| Spoofing a Quadro / RTX A device id | Misrepresents the card to the driver. License-adjacent, and it can make the driver mis-program the board. |
| ECC, NVLink, GPC/TPC geometry, CMP memory-size unlocks | The GA100 PLM list in the source opens extra apertures for a different product. The GeForce recipes do not. Changing geometry or memory size is not a reversible speed preset. |
| Power, clocks, fans, voltage | `nvidia-smi` already exposes the supported limits. Hidden power tables can damage the card. |
| Resizable BAR | A platform firmware setting. Forcing it from the module can hang the bus. |
| VBIOS flash or strap changes | Excluded. The sequence does not write the EEPROM. |
| Per-instruction names on the eight SS0 nibbles | The public note lists the fields (DP, FFMA, FMLA16, FMLA32, IMLA0–3, and SS1 as IMLA4) and does not say which nibble is which. Naming them would be a guess. Raw nibbles are accepted only inside the confirmed encoding set. |
| Userspace BAR0 poking | A root process with `/dev/mem` is a worse place to do this than the module that already owns the sequence. The read-only diagnostic PR (#116) was not merged for that reason. Status comes from the module's own sysfs file. |
| Turing two-write payload | PR #294 (RakkiPoni, `9422be4c7920`) and PierreLepagnol `5df16fff8269` change the Falcon path and, in the latter, skip FLR. Both say hardware throughput is still unconfirmed, or they were unmerged. A bad payload can leave firmware running until power-off. The upstream Turing payload is unchanged and the ids stay experimental. |
| DMA capture / Falcon probe | PR #276 adds firmware-analysis capture. It does not unlock a card. Not merged. |
