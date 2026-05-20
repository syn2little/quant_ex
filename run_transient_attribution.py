#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quant_ex.agent.strategy_iteration.transient_attribution import (
    build_risk_transient_factor_attribution,
    transient_attribution_to_markdown,
)


def main(
    *,
    run_id: str,
    portfolio_returns_csv: str | Path,
    risk_exposures_csv: str | Path,
    candidate_events_csv: str | Path | None = None,
    output_md: str | Path | None = None,
) -> dict:
    report = build_risk_transient_factor_attribution(
        run_id=run_id,
        portfolio_returns_csv=portfolio_returns_csv,
        risk_exposures_csv=risk_exposures_csv,
        candidate_events_csv=candidate_events_csv,
    )
    markdown = transient_attribution_to_markdown(report)
    if output_md:
        output_path = Path(output_md)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        print(output_path)
    else:
        print(markdown)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build diagnostic-only risk transient attribution from local artifacts.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--portfolio-returns-csv", required=True)
    parser.add_argument("--risk-exposures-csv", required=True)
    parser.add_argument("--candidate-events-csv", default=None)
    parser.add_argument("--output-md", default=None)
    args = parser.parse_args()
    main(
        run_id=args.run_id,
        portfolio_returns_csv=args.portfolio_returns_csv,
        risk_exposures_csv=args.risk_exposures_csv,
        candidate_events_csv=args.candidate_events_csv,
        output_md=args.output_md,
    )
