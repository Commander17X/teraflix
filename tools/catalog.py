# SPDX-License-Identifier: GPL-2.0-only
"""Read the kernel device table. recipes.c is the source of truth."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "kernel" / "gpu_unlock" / "recipes.c"

CARD_RE = re.compile(
    r'GU_CARD\(0x([0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+),\s*&\w+,\s*(GU_\w+),\s*"([^"]*)"\)'
)

# Professional and data-center IDs this tree deliberately does not unlock.
# They already run full-rate tensor paths, or they are not GeForce parts.
PROFESSIONAL = {
    "24b0": "GA104GL RTX A4000",
    "24b1": "GA104GL RTX A4000H",
    "2230": "GA102GL RTX A6000",
    "2231": "GA102GL RTX A5000",
    "25b6": "GA107GL A2 / A16",
    "25b8": "GA107GLM RTX A2000 Mobile",
    "25b9": "GA107GLM RTX A1000 Laptop GPU",
}

# Desktop RTX 4070 SKUs. 2786 is the common AD104 card.
RTX_4070 = {
    "2786": "AD104 desktop RTX 4070, family-supported",
    "2709": "AD103 desktop RTX 4070, family-supported",
    "2783": "AD104 RTX 4070 SUPER, family-supported",
    "2782": "AD104 RTX 4070 Ti, validated in the upstream BF16 table",
    "2820": "AD106M RTX 4070 Laptop, experimental",
    "2860": "AD106M RTX 4070 Laptop, experimental",
}

CONFIDENCE = {
    "GU_VALIDATED": "validated",
    "GU_FAMILY": "family",
    "GU_EXPERIMENTAL": "experimental",
}


def selector_ok(value: int, nibbles: int) -> bool:
    """Match kernel/gpu_unlock/policy.c. Confirmed encodings only."""
    if nibbles < 8 and (value >> (nibbles * 4)):
        return False
    for i in range(nibbles):
        nibble = (value >> (i * 4)) & 0xF
        if nibble not in (0x0, 0x1, 0x8, 0x9):
            return False
    return True


def load_cards(path: Path = RECIPES) -> list[dict]:
    text = path.read_text()
    cards = []
    seen = set()
    for device, chip, level, name in CARD_RE.findall(text):
        device = device.lower()
        if device in seen:
            raise ValueError(f"duplicate device id {device}")
        seen.add(device)
        if level not in CONFIDENCE:
            raise ValueError(f"unknown confidence {level} for {device}")
        cards.append({
            "device": device,
            "chip": chip.lower(),
            "level": level,
            "confidence": CONFIDENCE[level],
            "name": name,
        })
    if not cards:
        raise ValueError(f"no GU_CARD entries in {path}")
    return cards


def by_device(cards: list[dict] | None = None) -> dict[str, dict]:
    return {card["device"]: card for card in (cards if cards is not None else load_cards())}
