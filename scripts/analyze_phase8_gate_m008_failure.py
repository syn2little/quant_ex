#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WFV_DIR = ROOT / "optimization_results" / "walk_forward_phase8_regime_gate_grid_m008_full_wfv_20260519"
OUT = ROOT / "docs" / "strategy_log" / "phase8_gate_m008_failure_attribution_v0_2026-05-19.md"


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def fmt(value: float) -> str:
    return f"{value:.4f}"


def read_fold_rows() -> pd.DataFrame:
    return pd.read_csv(WFV_DIR / "walk_forward_all_results.csv")


def main() -> None:
    rows = read_fold_rows()
    summary = pd.read_csv(WFV_DIR / "walk_forward_summary.csv").iloc[0]
    fold_rows = rows.assign(year=rows["fold"].str.replace("test_", "", regex=False))
    weakest = fold_rows.sort_values("sharpe").iloc[0]
    # Benchmark-relative diagnostics from persisted fold metrics.
    fold_rows["alpha_minus_return"] = fold_rows["alpha"] - fold_rows["annual_return"]
    fold_rows["tracking_to_vol"] = fold_rows["tracking_error"] / fold_rows["annual_vol"]
    y2022 = fold_rows[fold_rows["year"] == "2022"].iloc[0]
    y2023 = fold_rows[fold_rows["year"] == "2023"].iloc[0]
    problem = fold_rows[fold_rows["year"].isin(["2022", "2023"])]
    stable = fold_rows[~fold_rows["year"].isin(["2022", "2023"])]

    lines = [
        "# Phase 8 gate_m008 failure attribution v0 — 2026-05-19",
        "",
        "## Scope",
        "- Read-only diagnostic from existing WFV fold artifacts.",
        "- No new backtest, no data refresh, no parameter search, no rebalance.",
        "- Candidate: `gate_m008`, `drawdown_threshold: -0.08`.",
        "- Limitation: WFV artifacts contain fold-level metrics only; daily portfolio returns, positions, trades, and candidate events were not exported for each WFV fold.",
        "",
        "## Aggregate read",
        f"- mean Sharpe: {fmt(float(summary['mean_sharpe']))}",
        f"- min Sharpe: {fmt(float(summary['min_sharpe']))}",
        f"- worst max drawdown: {pct(float(summary['worst_max_drawdown']))}",
        f"- positive Sharpe folds: {int(summary['positive_sharpe_folds'])}/{int(summary['folds'])}",
        f"- Sharpe p-value: {fmt(float(summary['sharpe_ttest_pvalue']))}",
        "",
        "## Failure localization",
        f"- Weakest fold: {weakest['year']} with Sharpe {fmt(float(weakest['sharpe']))}, annual return {pct(float(weakest['annual_return']))}, max drawdown {pct(float(weakest['max_drawdown']))}.",
        f"- 2022: Sharpe {fmt(float(y2022['sharpe']))}, annual return {pct(float(y2022['annual_return']))}, annual vol {pct(float(y2022['annual_vol']))}, max drawdown {pct(float(y2022['max_drawdown']))}, IR {fmt(float(y2022['information_ratio']))}, alpha {pct(float(y2022['alpha']))}.",
        f"- 2023: Sharpe {fmt(float(y2023['sharpe']))}, annual return {pct(float(y2023['annual_return']))}, annual vol {pct(float(y2023['annual_vol']))}, max drawdown {pct(float(y2023['max_drawdown']))}, IR {fmt(float(y2023['information_ratio']))}, alpha {pct(float(y2023['alpha']))}.",
        "",
        "## Benchmark-relative diagnosis",
        f"- Problem years average annual return: {pct(problem['annual_return'].mean())}; average alpha: {pct(problem['alpha'].mean())}; average IR: {fmt(problem['information_ratio'].mean())}.",
        f"- Non-problem years average annual return: {pct(stable['annual_return'].mean())}; average alpha: {pct(stable['alpha'].mean())}; average IR: {fmt(stable['information_ratio'].mean())}.",
        "- 2022 is not a pure stock-selection failure: annual return is slightly negative, but alpha and IR are strongly positive.",
        "- The blocker is absolute-risk survival: high beta/tracking volatility and deep drawdown keep Sharpe slightly below zero despite positive excess performance.",
        "- 2023 is repaired directionally versus soft_no_gate, becoming positive annual return and positive Sharpe, so the residual blocker is concentrated in 2022.",
        "",
        "## Drawdown diagnosis",
        "- Daily WFV returns were not persisted, so this report intentionally avoids synthetic daily-path reconstruction.",
        f"- The persisted 2022 fold max drawdown is {pct(float(y2022['max_drawdown']))}, with annual vol {pct(float(y2022['annual_vol']))} and beta {fmt(float(y2022['beta']))}.",
        f"- Tracking error is {pct(float(y2022['tracking_error']))}, about {fmt(float(y2022['tracking_to_vol']))}x annual vol, so active risk is material but not the only risk source.",
        "- This supports a portfolio-risk interpretation: the fold does not need more alpha threshold fitting; it needs a drawdown/volatility budget if this line continues.",
        "",
        "## What not to do",
        "- Do not continue threshold fitting around -0.08 just to flip 2022 Sharpe from -0.0424 to positive.",
        "- Do not promote `gate_m008` from these results.",
        "- Do not change daily rebalance/default configs.",
        "",
        "## Recommended next design",
        "`portfolio_risk_cap_over_signal_tuning`",
        "",
        "Keep `gate_m008` as the fixed signal candidate, and if continuing, test a portfolio-layer cap rather than another signal threshold:",
        "- volatility or drawdown regime risk budget,",
        "- lower gross exposure or per-position cap during gated regimes,",
        "- optional turnover cap to reduce whipsaw during high-volatility periods.",
        "",
        "Before any such run, modify WFV export plumbing to persist fold-level attribution inputs so future failure attribution can use real daily returns/candidate events instead of fold-level approximations.",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
