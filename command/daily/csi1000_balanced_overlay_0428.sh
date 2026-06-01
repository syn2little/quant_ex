#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

./.venv/bin/python run_scheduled_rebalance.py \
    --config config/csi1000_balanced_overlay.yaml \
    --model-path models/lgbm_sector_csi1000_balanced_20260428_235851.pkl \
    --start-date 2026-04-30 \
    --positions SH600489:900:2026-04-30,SH600900:900:2026-04-30,SH601021:500:2026-04-30,SH603259:200:2026-04-30,SH603993:1300:2026-04-30 \
    --replay-from-initial-positions \
    --min-action-value 1000 \
    --skip-update \
    "$@"
