#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

try:
    from quant_ex.agent.strategy_iteration.daily_failure_attribution import (  # noqa: E402
        build_daily_failure_attribution,
        render_daily_failure_attribution_markdown,
    )
except ModuleNotFoundError:
    module_path = ROOT / "agent/strategy_iteration/daily_failure_attribution.py"
    spec = importlib.util.spec_from_file_location("daily_failure_attribution", module_path)
    if spec is None or spec.loader is None:
        raise
    daily_failure_attribution = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(daily_failure_attribution)
    build_daily_failure_attribution = daily_failure_attribution.build_daily_failure_attribution
    render_daily_failure_attribution_markdown = daily_failure_attribution.render_daily_failure_attribution_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Build diagnostic-only daily failure attribution from local CSV artifacts")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--portfolio-returns-csv", required=True)
    parser.add_argument("--risk-exposures-csv", required=True)
    parser.add_argument("--candidate-events-csv", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--stress-drawdown-threshold", type=float, default=-0.05)
    parser.add_argument("--top-loss-days", type=int, default=10)
    parser.add_argument("--risk-memory-window", type=int, default=20)
    parser.add_argument("--roughness-window", type=int, default=10)
    parser.add_argument("--persistence-window", type=int, default=10)
    parser.add_argument("--diagnostic-high-quantile", type=float, default=0.75)
    args = parser.parse_args()

    report = build_daily_failure_attribution(
        run_id=args.run_id,
        portfolio_returns_csv=args.portfolio_returns_csv,
        risk_exposures_csv=args.risk_exposures_csv,
        candidate_events_csv=args.candidate_events_csv,
        stress_drawdown_threshold=args.stress_drawdown_threshold,
        top_loss_days=args.top_loss_days,
        risk_memory_window=args.risk_memory_window,
        roughness_window=args.roughness_window,
        persistence_window=args.persistence_window,
        diagnostic_high_quantile=args.diagnostic_high_quantile,
    )
    output = Path(args.output_md)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_daily_failure_attribution_markdown(report), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
