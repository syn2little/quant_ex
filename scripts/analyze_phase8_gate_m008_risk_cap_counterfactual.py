"""Report-only risk-cap counterfactual for Phase 8 gate_m008 2022 fold."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections.abc import Sequence
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from agent.strategy_iteration.risk_cap import (
    RiskCapPolicy,
    compute_drawdown,
    compute_risk_cap_counterfactual_series,
    compute_rolling_vol,
    summarize_risk_cap_counterfactual,
)

DEFAULT_RUN_ID = "wf_csi1000_test_2022_phase8_gate_m008_single_fold_2022_attr_20260519"
DEFAULT_AGENT_RUNS_DIR = Path("backtest_results/agent_runs")
DEFAULT_OUTPUT = Path("docs/strategy_log/phase8_gate_m008_2022_risk_cap_counterfactual_2026-05-21.md")


def _load_returns(agent_runs_dir: Path, run_id: str) -> pd.DataFrame:
    path = agent_runs_dir / f"{run_id}_portfolio_returns.csv"
    frame = pd.read_csv(path)
    required = {"date", "portfolio_return", "benchmark_return"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{path} missing required columns: {', '.join(missing)}")
    frame = frame.sort_values("date").reset_index(drop=True)
    return frame


def _lagged(values: Sequence[float | None]) -> list[float | None]:
    return [None, *values[:-1]] if values else []


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def build_report(frame: pd.DataFrame, run_id: str, vol_window: int, policy: RiskCapPolicy) -> tuple[dict[str, Any], str]:
    returns = [float(value) for value in frame["portfolio_return"]]
    benchmark_returns = [float(value) for value in frame["benchmark_return"]]
    nav = []
    current_nav = 1.0
    for value in returns:
        current_nav *= 1.0 + value
        nav.append(current_nav)

    lagged_vol = _lagged(compute_rolling_vol(returns, window=vol_window))
    lagged_drawdown = _lagged(compute_drawdown(nav))
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=returns,
        lagged_vol=lagged_vol,
        lagged_drawdown=lagged_drawdown,
        policy=policy,
    )
    summary = cast(
        dict[str, Any],
        summarize_risk_cap_counterfactual(
            rows,
            fold_id="2022",
            candidate_id="gate_m008_risk_cap_v0",
            decision_label="diagnostic_only",
            benchmark_returns=benchmark_returns,
        ),
    )
    summary["run_id"] = run_id
    summary["vol_window"] = vol_window
    summary["policy"] = {
        "watch_vol": policy.watch_vol,
        "cut_vol": policy.cut_vol,
        "watch_drawdown": policy.watch_drawdown,
        "cut_drawdown": policy.cut_drawdown,
        "recover_vol": policy.recover_vol,
        "recover_drawdown": policy.recover_drawdown,
        "cut_multiplier": policy.cut_multiplier,
        "recover_multiplier": policy.recover_multiplier,
        "missing_input_state": policy.missing_input_state,
    }

    state_counts: dict[str, int] = {}
    for row in rows:
        state = str(row["state"])
        state_counts[state] = state_counts.get(state, 0) + 1
    summary["state_counts"] = state_counts

    metric_order = [
        "baseline_total_return",
        "capped_total_return",
        "total_return_delta",
        "baseline_annualized_return",
        "capped_annualized_return",
        "baseline_max_drawdown",
        "capped_max_drawdown",
        "max_drawdown_delta",
        "baseline_vol",
        "capped_vol",
        "baseline_ir",
        "capped_ir",
        "worst_5_day_pre_cap",
        "worst_5_day_post_cap",
        "tail_loss_delta",
        "baseline_positive_return_capture",
        "capped_positive_return_capture",
        "positive_return_capture_delta",
        "baseline_negative_return_capture",
        "capped_negative_return_capture",
        "negative_return_capture_delta",
        "cap_active_days",
        "cap_cut_days",
        "cap_recover_days",
        "cap_blocked_days",
        "avg_cap_multiplier",
    ]

    lines = [
        "# Phase8 gate_m008 2022 risk-cap counterfactual",
        "",
        "Status: `diagnostic_only_not_trading_signal`.",
        "",
        "This report keeps the fixed `gate_m008` signal path and applies only a lagged portfolio-level exposure cap to realized daily returns. It does not change ranking, topk, n_drop, hold threshold, data, WFV, or any daily rebalance/live configuration.",
        "",
        "## Inputs",
        f"- run_id: `{run_id}`",
        f"- rows: {len(frame)}",
        f"- date_range: {frame['date'].iloc[0]} to {frame['date'].iloc[-1]}",
        f"- vol_window: {vol_window}",
        f"- policy: `{json.dumps(summary['policy'], sort_keys=True)}`",
        "",
        "## Summary metrics",
    ]
    for key in metric_order:
        lines.append(f"- {key}: {_format_value(summary[key])}")
    lines.extend(
        [
            "",
            "## State counts",
        ]
    )
    for state, count in sorted(state_counts.items()):
        lines.append(f"- {state}: {count}")

    if summary["max_drawdown_delta"] > 0 and summary["tail_loss_delta"] > 0 and summary["total_return_delta"] >= 0:
        next_action = "compare_next: risk cap deserves a fixed-parameter replay on adjacent folds before any promotion discussion."
    elif summary["max_drawdown_delta"] > 0 and summary["tail_loss_delta"] > 0:
        next_action = "diagnostic_refine: risk survival improves, but upside capture loss is too large for replay readiness."
    else:
        next_action = "not_promotable: this cap variant does not improve the intended risk survival metrics."
    lines.extend(
        [
            "",
            "## Interpretation",
            f"- decision: `{summary['decision_label']}`",
            f"- next_action: `{next_action}`",
            "- guardrail: improvement here is post-hoc diagnostic evidence only; it is not WFV evidence and not a trading signal.",
            "",
        ]
    )
    return summary, "\n".join(lines)


def build_sensitivity(frame: pd.DataFrame, run_id: str, vol_window: int) -> list[dict[str, Any]]:
    presets = {
        "default_v0": RiskCapPolicy(),
        "drawdown_15_cut": RiskCapPolicy(
            watch_vol=0.30,
            cut_vol=0.40,
            watch_drawdown=-0.10,
            cut_drawdown=-0.15,
            recover_vol=0.24,
            recover_drawdown=-0.06,
        ),
        "drawdown_20_cut": RiskCapPolicy(
            watch_vol=0.35,
            cut_vol=0.50,
            watch_drawdown=-0.12,
            cut_drawdown=-0.20,
            recover_vol=0.28,
            recover_drawdown=-0.08,
        ),
        "soft_dd15": RiskCapPolicy(
            watch_vol=0.30,
            cut_vol=0.40,
            watch_drawdown=-0.10,
            cut_drawdown=-0.15,
            recover_vol=0.24,
            recover_drawdown=-0.06,
            cut_multiplier=0.70,
            recover_multiplier=0.85,
        ),
        "vol_only_high": RiskCapPolicy(
            watch_vol=0.28,
            cut_vol=0.35,
            watch_drawdown=-0.99,
            cut_drawdown=-0.99,
            recover_vol=0.20,
            recover_drawdown=-0.99,
        ),
    }
    rows: list[dict[str, Any]] = []
    for name, preset_policy in presets.items():
        summary, _ = build_report(frame, run_id, vol_window, preset_policy)
        rows.append(
            {
                "preset": name,
                "capped_total_return": summary["capped_total_return"],
                "total_return_delta": summary["total_return_delta"],
                "capped_max_drawdown": summary["capped_max_drawdown"],
                "max_drawdown_delta": summary["max_drawdown_delta"],
                "capped_ir": summary["capped_ir"],
                "tail_loss_delta": summary["tail_loss_delta"],
                "positive_return_capture_delta": summary["positive_return_capture_delta"],
                "negative_return_capture_delta": summary["negative_return_capture_delta"],
                "cap_active_days": summary["cap_active_days"],
                "avg_cap_multiplier": summary["avg_cap_multiplier"],
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-runs-dir", type=Path, default=DEFAULT_AGENT_RUNS_DIR)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--vol-window", type=int, default=20)
    args = parser.parse_args()

    frame = _load_returns(args.agent_runs_dir, args.run_id)
    summary, markdown = build_report(frame, args.run_id, args.vol_window, RiskCapPolicy())
    sensitivity = build_sensitivity(frame, args.run_id, args.vol_window)
    markdown = markdown.rstrip() + "\n\n## Coarse sensitivity\n"
    for row in sensitivity:
        markdown += "- " + ", ".join(f"{key}: {_format_value(value)}" for key, value in row.items()) + "\n"
    markdown += (
        "\nSensitivity is coarse diagnostic triage, not parameter tuning evidence. "
        "The dominant finding is whether fixed risk-budget families are worth a follow-up replay, "
        "not which threshold is best.\n"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    print(f"wrote {args.output}")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
