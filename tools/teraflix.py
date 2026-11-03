#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inspect a machine against the teraflix device table.

This command does not write GPU registers. The kernel module does that, and
only when the kernel command line opts in.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from .catalog import PROFESSIONAL, RTX_4070, by_device, load_cards
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from catalog import PROFESSIONAL, RTX_4070, by_device, load_cards

STATUS = Path("/sys/kernel/gpu_unlock/status")
PCI_RE = re.compile(r"\[10de:([0-9a-fA-F]{4})\]", re.I)
STATUS_CARD = re.compile(
    r"pci=(\S+) device=([0-9a-fA-F]+) confidence=(\S+) family=(\S+) "
    r"disposition=(\S+) result=(-?\d+) name=(.*)"
)


def lspci_nvidia() -> list[str]:
    binary = shutil.which("lspci")
    if not binary:
        return []
    result = subprocess.run([binary, "-nn", "-d", "10de:"], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def virtualization() -> dict:
    info = {"hypervisor_flag": False, "dmi": {}}
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists() and "hypervisor" in cpuinfo.read_text(errors="replace"):
        info["hypervisor_flag"] = True
    for key in ("sys_vendor", "product_name", "product_version"):
        path = Path("/sys/class/dmi/id") / key
        if path.exists():
            info["dmi"][key] = path.read_text(errors="replace").strip()
    detect = shutil.which("systemd-detect-virt")
    if detect:
        result = subprocess.run([detect], check=False, capture_output=True, text=True)
        info["systemd_detect_virt"] = result.stdout.strip() or "none"
    return info


def cmdline() -> str:
    path = Path("/proc/cmdline")
    return path.read_text(errors="replace").strip() if path.exists() else ""


def cmd_list() -> int:
    cards = load_cards()
    for card in cards:
        mark = ""
        if card["device"] in RTX_4070:
            mark = "  4070"
        print(f"{card['device']}  {card['chip']}  {card['confidence']:13}  {card['name']}{mark}")
    print(f"{len(cards)} device ids")
    return 0


def cmd_explain(token: str) -> int:
    cards = by_device()
    needle = token.lower().removeprefix("0x").removeprefix("10de:")
    if needle in PROFESSIONAL:
        print(f"{needle}: {PROFESSIONAL[needle]}")
        print("Not a teraflix target. Professional cards already run the full tensor rate.")
        print("The module does not bind this id, and it will not pretend the card is a GeForce.")
        return 0
    if needle in cards:
        card = cards[needle]
        print(f"{card['device']}: {card['name']}")
        print(f"chip check: PMC_BOOT_0 architecture+implementation {card['chip']}")
        print(f"confidence: {card['confidence']}")
        if needle in RTX_4070:
            print(RTX_4070[needle])
        if card["confidence"] == "experimental":
            print("Skipped when the kernel command line sets gpu_unlock.experimental=0.")
        elif card["confidence"] == "family":
            print("Same chip recipe as a validated SKU. This exact board still needs a local run.")
        else:
            print("Upstream published a stability claim or a BF16 result for this SKU.")
        return 0
    matches = [card for card in cards.values() if needle in card["name"].lower()]
    if not matches:
        print(f"no teraflix entry for {token!r}")
        return 1
    for card in matches:
        print(f"{card['device']}  {card['confidence']:13}  {card['name']}")
    return 0


def parse_status(text: str) -> list[dict]:
    found = []
    for line in text.splitlines():
        match = STATUS_CARD.match(line.strip())
        if match:
            found.append({
                "pci": match.group(1),
                "device": match.group(2).lower(),
                "confidence": match.group(3),
                "family": match.group(4),
                "disposition": match.group(5),
                "result": int(match.group(6)),
                "name": match.group(7),
            })
    return found


def cmd_status() -> int:
    if not STATUS.exists():
        print("gpu_unlock is not loaded, or it was loaded without gpu_unlock.targets=.")
        print("The module does nothing until that command-line option is set.")
        return cmd_check(require=None)
    text = STATUS.read_text(errors="replace")
    print(text, end="" if text.endswith("\n") else "\n")
    return 0


def cmd_check(require: str | None) -> int:
    cards = by_device()
    virt = virtualization()
    print(f"hypervisor flag: {virt['hypervisor_flag']}")
    if virt["dmi"]:
        print("dmi: {sys_vendor} {product_name}".format(
            sys_vendor=virt["dmi"].get("sys_vendor", ""),
            product_name=virt["dmi"].get("product_name", ""),
        ).rstrip())
    if "systemd_detect_virt" in virt:
        print(f"systemd-detect-virt: {virt['systemd_detect_virt']}")
    boot = cmdline()
    if boot:
        opted = "gpu_unlock.targets=" in boot
        print(f"kernel command line opts in: {opted}")
        if "gpu_unlock.dry_run=" in boot:
            print("dry_run is set: this boot will not write selectors")
    lines = lspci_nvidia()
    if not lines:
        print("no NVIDIA PCI device visible to lspci (or lspci is not installed)")
    required = require.lower().removeprefix("0x") if require else None
    saw_required = False
    for line in lines:
        match = PCI_RE.search(line)
        device = match.group(1).lower() if match else ""
        print(line)
        if device in PROFESSIONAL:
            print(f"  {PROFESSIONAL[device]}: already full-rate, teraflix will not touch it")
        elif device in cards:
            card = cards[device]
            print(f"  teraflix: {card['confidence']} — {card['name']}")
            if device in RTX_4070:
                print(f"  {RTX_4070[device]}")
        elif device:
            print("  not in the teraflix table")
        if required and device == required:
            saw_required = True
    if required and not saw_required:
        print(f"required device 10de:{required} was not found")
        return 1
    if any(PCI_RE.search(line) and PCI_RE.search(line).group(1).lower() in ("2786", "2709") for line in lines):
        print("4070 guest command line, after a dry run looks right:")
        print("  gpu_unlock.targets=all gpu_unlock.rate=full")
        print("Family-supported 4070 IDs stay enabled when gpu_unlock.experimental=0.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="print the device table")
    explain = sub.add_parser("explain", help="explain one device id or name")
    explain.add_argument("token")
    sub.add_parser("status", help="print /sys/kernel/gpu_unlock/status if the module published it")
    check = sub.add_parser("check", help="report PCI ids, virtualization, and the kernel command line")
    check.add_argument("--require", help="exit 1 unless this NVIDIA device id is present")
    args = parser.parse_args(argv)
    if args.command == "list":
        return cmd_list()
    if args.command == "explain":
        return cmd_explain(args.token)
    if args.command == "status":
        return cmd_status()
    return cmd_check(args.require)


if __name__ == "__main__":
    sys.exit(main())
