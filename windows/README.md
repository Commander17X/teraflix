# Windows

teraflix's tested component is the Linux kernel module. Windows support is a
separate pre-boot step, because the NVIDIA Windows driver claims the card
before a normal service can run the same sequence.

The maintained UEFI port is [impacifist/Windows-GPU-UNLOCK](https://github.com/impacifist/Windows-GPU-UNLOCK),
reviewed here at commit `fd8bbea5b1db991805ffcd7ba84e73fa7867bd8a` (1 November 2026).
It is GPL-2.0. It runs its own copy of the pre-driver transaction from the
firmware volume, before Windows loads `nvlddmkm`. Zagitta's FAQ points at that
port and warns that unrelated Windows installers are not part of the project.

This tree does not vendor that port. The upstream tree contains a prebuilt
`BOOTX64.EFI`, a large EDK2 snapshot, and NVIDIA firmware terms whose
redistribution upstream already declines to promise. Copying those in would
add a binary this repository cannot rebuild or inspect usefully, and it would
fork a second copy of the transaction that would drift from the Linux module.
Use the port from its own repository if you want the UEFI build. Read its
`SOURCE-MANIFEST.json` and license files before you trust a binary.

`status.ps1` in this directory only reads `Win32_PnPEntity` and prints device
ids. It does not unlock anything. On Windows, an RTX A4000 (`DEV_24B0`) is a
professional card and is already full-rate; the script says so and stops.

There is no Linux-style module parameter on Windows in this tree. Reverting a
UEFI unlock is a question for that port's own guide: remove its boot entry and
power-cycle the GPU so the selectors return to the power-on default. FLR alone
does not clear them.
