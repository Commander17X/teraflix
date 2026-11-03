# Fork audit

Base: [Zagitta/gpu-unlock](https://github.com/Zagitta/gpu-unlock) `main` at
`7eb51bccae0a0b7e599e084d971170e9a1e82d0c` (2.0.0, pushed 29 October 2026).
teraflix is that tree plus the changes below. The kernel module, firmware
extractor, and package layout are still that project, under GPL-2.0-only.

## How the forks were reviewed

The GitHub forks API listed on the order of 1,500 forks. Upstream was
rewritten in October 2026, so a fork `pushed_at` equal to upstream's does not
mean the fork has its own commits. Those trees were treated as unmodified
copies and not re-diffed.

What was diffed:

- Every open pull request against `Zagitta/gpu-unlock` at review time. That
  is the set of fork commits their authors had actually proposed.
- Compare API against `main` for forks whose description or push time said
  they had moved: linfei-mise, lgcorzo, beetlepig, PierreLepagnol,
  ThemeHackers, menotbobbybrown, Questing-VR, tk-shockwave. The last four
  were not ahead.
- [impacifist/Windows-GPU-UNLOCK](https://github.com/impacifist/Windows-GPU-UNLOCK)
  at `fd8bbea5b1db991805ffcd7ba84e73fa7867bd8a`.

Device names were checked against the pciutils `pci.ids` snapshot used during
the review (NVIDIA vendor `10de`). A fork id was added only when that file
names a GeForce product and the chip id follows the PMC_BOOT_0 encoding the
recipes already use (GA107 is `0x177`, the next implementation after GA106
`0x176`). Professional `GL` / `GLM` ids were not added.

## Merged

| Source | Commit / PR | What landed |
| --- | --- | --- |
| Zagitta/gpu-unlock | `7eb51bcca` | The whole 2.0.0 module, recipes, firmware tooling, packaging, and CI. |
| nklowns, merged upstream as PR #160, then dropped by the recipe refactor; restored from Cognizaunce PR #212 `a278a53ba0a9` and govwin PR #271 `e6bf184af7f3` | `2520`, `2560` | GA106M RTX 3060 Laptop / Max-Q. Also `2521` and `2561`, the other pci.ids names for that same laptop part. Confidence `family` (validated GA106 recipe). |
| Stradivario, PR #217 `93e751fb8137` | `2420` | GA103M RTX 3080 Ti Mobile. `2460` (the Laptop GPU name in pci.ids) added with it. Experimental. |
| LenaTDDS, PR #245 `cd017ead2463`, and the GeForce subset of qwecvw PR #231 `f8bc9936e184` | GA107 ids below | `2582`, `2583`, `2584`, `25a0`, `25a2`, `25a5`, `25ab`, `25ac`, `25e0`, `25e2`, `25e5`. Chip `0x177` on the existing GA10x recipe. Experimental. PR #222 (preethamb97, `3fd07c55bd9a`) is the same `25a5` id. |
| qwecvw PR #231, GeForce RTX 2050 rows only | `25a9`, `25ad` | pci.ids calls these GA107 GeForce RTX 2050. Experimental. Same recipe assumption as the 3050s. |
| rwinkelman, PR #277 `04533aa7ebaf` | `2717`, `28a1` | AD103M RTX 4090 Laptop sibling of the existing `2757`, and AD107M RTX 4050 Max-Q sibling of the existing `28e1`. Experimental. |
| PipelineDude, PR #282 `ff98096b01c0` | `2820`, `2860` | AD106M RTX 4070 Laptop. Experimental. Not the desktop 4070. |
| pci.ids, same desktop chips as ids already in 2.0.0 | `2703`, `2788`, `2808` | AD103 RTX 4080 SUPER, AD104 RTX 4060 Ti, AD106 RTX 4060. Confidence `family`. |
| pci.ids, AD104 mobile 4080 | `27a0`, `27e0` | Experimental laptop ids on the AD104 recipe. |
| TheDigitalEagle, PR #241 `d339e78787ed` | DMA mask | Streaming and coherent masks widened from 32 to 47 bits, matching the NVIDIA driver. Matters for hosts that map RAM above 4 GiB and for a guest IOMMU that issues high IOVAs. |
| lslowmotion, PR #289 `faf4da414946` | aperture header | Detect `linux/aperture.h` instead of assuming it appears at kernel 6.0. RHEL backports the helper. |
| lslowmotion, PR #288 `1b9b63aae134` | RPM macro | `%nv` renamed to `%nvver` so the macro is not a two-character name. |
| jpodivin, PR #291 `7a1e69c7b524` | SHA-256 | `fetch_artifacts.py` now checks the same two digests the RPM spec and PKGBUILD already pin. |
| linfei-mise `a35e82ec689b` | evidence only | Documents an RTX 4090 Laptop run on unmodified gpu-unlock 2.0.0. Not merged as code. It is why the 4090 Laptop ids stay in the table; they are still experimental because the power-management result is one machine and was not reproduced here. |

Desktop RTX 4070 `2786` and the AD103 variant `2709` were already in 2.0.0.
They were reclassified to `family` because they share the AD104 / AD103
recipe with the 4070 Ti (`2782`, published BF16 result) and the 4080
(`2704`). No new recipe was invented for them.

## Not merged

| Source | Why |
| --- | --- |
| RakkiPoni PR #294 `9422be4c7920`, and PierreLepagnol `5df16fff8269` | Turing loader changes. Pierre's message says hardware unlock and throughput are still pending, and the patch skips FLR on that path. Left the upstream Turing payload alone. Turing ids stay experimental. |
| unya PR #251 `4efe1321883a` (draft) | Runtime D3cold re-unlock. Large coordinator rewrite, not validated here. The documented workaround is `NVreg_DynamicPowerManagement=0x00`, which is reversible, plus the upstream suspend hook that is already in the tree. |
| RGlabs84 PR #276 | Falcon DMA capture for firmware analysis. Not a user-facing control. |
| qwecvw PR #231, the non-GeForce rows | `25a6`/`25a7`/`25aa` are MX570. `25af` is an engineering sample. `25b6` and the `25b8`–`25bd` range are RTX A-series / A2 professional parts. `25f9`–`25fb` are embedded A-series. `25be` and `25bf` are not in pci.ids. `25a4` has no product name. None of those were added. |
| joshuaswarren PR #116 | Userspace BAR0 reader. Status is published by the module instead. |
| tranzmatt PR #204 | A benchmark sketch. `tools/benchmark.py` is a new BF16 matmul recorder with an offline self-test, not that patch. |
| beetlepig `b20466924206` | akmod / rpm-ostree packaging. It rewrites the RPM and CI flow. Deferred until it can be built on Fedora Atomic; the existing RPM spec is intact. |
| lgcorzo (ahead 5, behind 5) | "Dark Gravity" install guide, a SECURITY.md, and action SHA pinning. No recipe change. The rebrand was not taken. Action pinning is reasonable and was not required to build the module. |
| linfei-mise diagnostics tree | Read-only CUDA benches and evidence for one Alienware m18 R2. Useful as a report, too large and too machine-specific to vendor. Their note that a stock boot which still shows full rate is not a valid control is repeated in the passthrough guide. |
| ThemeHackers, menotbobbybrown, Questing-VR, tk-shockwave | Compare against `main` showed zero commits ahead. |
| impacifist/Windows-GPU-UNLOCK `fd8bbea5` | Reviewed. Not vendored: the tree ships a prebuilt `BOOTX64.EFI`, an EDK2 snapshot, and NVIDIA firmware redistribution that upstream already refuses to promise. `windows/README.md` points at the port. `windows/status.ps1` is a new read-only reporter. |
| keylase/nvidia-patch and similar NVENC unlocks | Not a fork of this module. The session cap is a license check in the proprietary encode stack. Not implemented. |
| CMP memory-size unlocks (cmpunlocker beyond the V67 payload this tree already credits) | Different goal. The GeForce recipes do not retune framebuffer geometry. Existing CMP device ids that 2.0.0 already listed (`220d`, `248a`) were kept and marked experimental rather than deleted. |

## Confidence rules

Applied in `kernel/gpu_unlock/recipes.c` and printed by
`python3 tools/teraflix.py list`.

- `validated`: Ampere desktop GeForce ids that 2.0.0 already shipped, excluding unnamed ids, engineering samples, and CMP boards; plus Ada ids with a published BF16 row (`2684` RTX 4090, `2704` RTX 4080, `2782` RTX 4070 Ti).
- `family`: same chip and the same recipe as a validated SKU. Includes desktop RTX 4070 `2786` and `2709`, and the restored GA106M laptop ids.
- `experimental`: everything else that is still listed. `gpu_unlock.experimental=0` skips this tier.

Engineering samples, reserved ids, and CMP boards that were already in 2.0.0
were downgraded to experimental. They still run when `experimental` is left
at its default.
