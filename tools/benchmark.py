#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Record and compare BF16 tensor throughput.

The unlock is applied before the NVIDIA driver loads, so a before/after pair
is two boots, not a live toggle. This script does not write GPU registers.

    python3 tools/benchmark.py --self-test
    python3 tools/benchmark.py --save before.json
    python3 tools/benchmark.py --save after.json
    python3 tools/benchmark.py --compare before.json after.json
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import time
from pathlib import Path


def nvidia_smi() -> dict:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return {"present": False}
    result = subprocess.run(
        [binary, "--query-gpu=name,pci.device_id,clocks.sm,clocks.mem,power.draw",
         "--format=csv,noheader"],
        check=False, capture_output=True, text=True,
    )
    return {
        "present": True,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def measure_torch() -> dict:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("PyTorch is installed and CUDA is not available")
    device = torch.device("cuda")
    name = torch.cuda.get_device_name(device)
    # Large square GEMM. 2*N^3 flops per matmul. BF16 uses tensor cores on
    # Ampere and Ada when the kernel the runtime picks is a tensor kernel.
    side = 8192
    left = torch.randn(side, side, device=device, dtype=torch.bfloat16)
    right = torch.randn(side, side, device=device, dtype=torch.bfloat16)
    for _ in range(4):
        torch.matmul(left, right)
    torch.cuda.synchronize()
    iterations = 20
    started = time.perf_counter()
    for _ in range(iterations):
        torch.matmul(left, right)
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    flops = iterations * 2 * side ** 3
    return {
        "method": "torch.matmul.bfloat16",
        "device": name,
        "side": side,
        "iterations": iterations,
        "seconds": elapsed,
        "bf16_tflops": flops / elapsed / 1e12,
    }


def measure() -> dict:
    record = {
        "platform": platform.platform(),
        "nvidia_smi": nvidia_smi(),
    }
    try:
        record.update(measure_torch())
    except ModuleNotFoundError:
        record["method"] = None
        record["error"] = "PyTorch is not installed. On the GPU guest: pip install torch, then rerun."
    except Exception as exc:  # noqa: BLE001 - report the environment, do not pretend.
        record["method"] = None
        record["error"] = str(exc)
    return record


def compare(before: dict, after: dict) -> dict:
    left = before.get("bf16_tflops")
    right = after.get("bf16_tflops")
    ratio = None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)) and left > 0:
        ratio = right / left
    return {
        "before_tflops": left,
        "after_tflops": right,
        "ratio": ratio,
        "before_method": before.get("method"),
        "after_method": after.get("method"),
        "before_device": before.get("device"),
        "after_device": after.get("device"),
    }


def self_test() -> None:
    before = {"bf16_tflops": 80.0, "method": "fixture", "device": "fixture"}
    after = {"bf16_tflops": 148.0, "method": "fixture", "device": "fixture"}
    result = compare(before, after)
    if abs(result["ratio"] - 1.85) > 1e-9:
        raise SystemExit(f"ratio math failed: {result}")
    if compare({"bf16_tflops": 0}, {"bf16_tflops": 1})["ratio"] is not None:
        raise SystemExit("zero baseline should not divide")
    print("benchmark self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--save", type=Path, help="measure and write a JSON record")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"))
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.compare:
        before = json.loads(args.compare[0].read_text())
        after = json.loads(args.compare[1].read_text())
        result = compare(before, after)
        print(json.dumps(result, indent=2))
        if result["ratio"] is None:
            raise SystemExit("one or both records have no bf16_tflops")
        return
    record = measure()
    text = json.dumps(record, indent=2)
    if args.save:
        args.save.write_text(text + "\n")
        print(f"wrote {args.save}")
    print(text)
    if record.get("bf16_tflops") is None:
        raise SystemExit(record.get("error") or "no measurement")


if __name__ == "__main__":
    main()
