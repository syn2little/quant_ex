#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

# Emergency default switched from SVS overlay to the conservative baseline.
# Positions are the latest known real/cache holdings used as the previous
# trading day's portfolio; update this line when the brokerage account changes.
POSITIONS="SH601021:600:2026-05-29,SH601111:4400:2026-05-21,SZ000651:700:2026-05-13,SZ002050:600:2026-06-02,SZ300628:700:2026-05-28"

./.venv/bin/python run_scheduled_rebalance.py \
    --config config/daily_csi1000.yaml \
    --model-path models/lgbm_csi1000_balanced_20260429_002424.pkl \
    --start-date 2024-01-01 \
    --positions "$POSITIONS" \
    --account 150000 \
    --hold-thresh 0 \
    --min-action-value 1000 \
    --no-cache-roll-forward \
    --skip-update \
    "$@"
