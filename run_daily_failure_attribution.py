#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant_ex.agent.strategy_iteration.daily_failure_attribution import (  # noqa: E402
    build_daily_failure_attribution,
    render_daily_failure_attribution_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build diagnostic-only daily failure attribution from local CSV artifacts")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--portfolio-returns-csv", required=True)
    parser.add_argument("--risk-exposures-csv", required=True)
    parser.add_argument("--candidate-events-csv", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--stress-drawdown-threshold", type=float, default=-0.05)
    parser.add_argument("--top-loss-days", type=int, default=10)
    args = parser.parse_args()

    report = build_daily_failure_attribution(
        run_id=args.run_id,
        portfolio_returns_csv=args.portfolio_returns_csv,
        risk_exposures_csv=args.risk_exposures_csv,
        candidate_events_csv=args.candidate_events_csv,
        stress_drawdown_threshold=args.stress_drawdown_threshold,
        top_loss_days=args.top_loss_days,
    )
    output = Path(args.output_md)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_daily_failure_attribution_markdown(report), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
