#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

try:
    from quant_ex.agent.strategy_iteration.factor_crowding_diagnostic import (  # noqa: E402
        build_factor_crowding_diagnostic,
        render_factor_crowding_markdown,
    )
except ModuleNotFoundError:
    module_path = ROOT / "agent/strategy_iteration/factor_crowding_diagnostic.py"
    spec = importlib.util.spec_from_file_location("factor_crowding_diagnostic", module_path)
    if spec is None or spec.loader is None:
        raise
    factor_crowding_diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(factor_crowding_diagnostic)
    build_factor_crowding_diagnostic = factor_crowding_diagnostic.build_factor_crowding_diagnostic
    render_factor_crowding_markdown = factor_crowding_diagnostic.render_factor_crowding_markdown


def main() -> dict:
    parser = argparse.ArgumentParser(
        description="Build a diagnostic-only factor crowding / co-movement report from local CSV artifacts"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--portfolio-returns-csv", required=True)
    parser.add_argument("--risk-exposures-csv", required=True)
    parser.add_argument("--candidate-events-csv", required=True)
    parser.add_argument("--output-md", default=None)
    parser.add_argument("--stress-drawdown-threshold", type=float, default=-0.05)
    parser.add_argument("--residual-quantile", type=float, default=0.75)
    parser.add_argument("--event-cluster-min-count", type=int, default=5)
    parser.add_argument("--top-days", type=int, default=10)
    args = parser.parse_args()

    report = build_factor_crowding_diagnostic(
        run_id=args.run_id,
        portfolio_returns_csv=args.portfolio_returns_csv,
        risk_exposures_csv=args.risk_exposures_csv,
        candidate_events_csv=args.candidate_events_csv,
        stress_drawdown_threshold=args.stress_drawdown_threshold,
        residual_quantile=args.residual_quantile,
        event_cluster_min_count=args.event_cluster_min_count,
        top_days=args.top_days,
    )
    markdown = render_factor_crowding_markdown(report)
    if args.output_md:
        output = Path(args.output_md)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
        print(output)
    else:
        print(markdown)
    return report


if __name__ == "__main__":
    main()
