#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"

ARMS = [
    ("m005", "config/csi1000_transient_repair_regime_gated_svs_m005.yaml"),
    ("m008", "config/csi1000_transient_repair_regime_gated_svs_m008.yaml"),
    ("m012", "config/csi1000_transient_repair_regime_gated_svs_m012.yaml"),
]


def main() -> int:
    for label, config in ARMS:
        run_id = f"phase8_regime_gate_grid_{label}_full_wfv_20260519"
        cmd = [
            str(PYTHON),
            "run_walk_forward_validation.py",
            "--train-universes", "csi1000",
            "--eval-market", "csi300",
            "--topk", "15",
            "--n-drop", "3",
            "--hold-thresh", "8",
            "--workers", "1",
            "--grid-workers", "1",
            "--train-config", config,
            "--with-extra-factors",
            "--run-id", run_id,
        ]
        print(f"\n=== Running {label}: {config} ===", flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
