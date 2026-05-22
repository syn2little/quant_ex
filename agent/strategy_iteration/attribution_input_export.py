from __future__ import annotations

from pathlib import Path
from typing import Any

from .risk_cap import (
    RiskCapPolicy,
    compute_drawdown,
    compute_risk_cap_counterfactual_series,
    compute_rolling_vol,
    summarize_risk_cap_counterfactual,
)

import pandas as pd


def build_portfolio_returns(report: pd.DataFrame) -> pd.DataFrame:
    """Normalize a qlib-style backtest report into the attribution return contract."""

    if report is None or report.empty:
        return pd.DataFrame(columns=["date", "portfolio_return", "benchmark_return"])
    frame = report.copy()
    frame.index = pd.to_datetime(frame.index)
    returns = _series_or_first(frame, "return")
    cost = frame["cost"].fillna(0.0) if "cost" in frame.columns else pd.Series(0.0, index=frame.index)
    portfolio = (returns - cost).astype(float)
    benchmark = (
        frame["bench"].astype(float)
        if "bench" in frame.columns
        else pd.Series(0.0, index=frame.index, dtype="float64")
    )
    output = pd.DataFrame(
        {
            "date": frame.index.strftime("%Y-%m-%d"),
            "portfolio_return": portfolio.round(10).values,
            "benchmark_return": benchmark.round(10).values,
        }
    )
    if "cost" in frame.columns:
        output["cost"] = cost.astype(float).round(10).values
    output["excess_return"] = (output["portfolio_return"] - output["benchmark_return"]).round(10)
    return output


def build_risk_exposures(portfolio_returns: pd.DataFrame) -> pd.DataFrame:
    """Build a minimal residual-return risk exposure contract from portfolio returns."""

    required = ["date", "portfolio_return", "benchmark_return"]
    if portfolio_returns is None or portfolio_returns.empty:
        return pd.DataFrame(columns=required + ["residual_return", "drawdown"])
    missing = [col for col in required if col not in portfolio_returns.columns]
    if missing:
        raise ValueError(f"portfolio_returns missing required columns: {missing}")
    output = portfolio_returns[required].copy()
    output["portfolio_return"] = output["portfolio_return"].astype(float)
    output["benchmark_return"] = output["benchmark_return"].astype(float)
    output["residual_return"] = (output["portfolio_return"] - output["benchmark_return"]).round(10)
    nav = (1.0 + output["portfolio_return"]).cumprod()
    output["drawdown"] = ((nav - nav.cummax()) / nav.cummax()).round(10)
    output["abs_residual_return"] = output["residual_return"].abs().round(10)
    return output


def build_candidate_events(
    signal: pd.Series,
    price_data: pd.DataFrame,
    *,
    topk: int,
    horizon: int = 1,
) -> pd.DataFrame:
    """Create accepted/rejected candidate events from a signal and forward returns."""

    columns = ["date", "instrument", "decision", "rejection_reason", "score", "rank", "forward_return"]
    if signal is None or signal.empty or price_data is None or price_data.empty:
        return pd.DataFrame(columns=columns)
    price_col = "real_close" if "real_close" in price_data.columns else "$close"
    if price_col not in price_data.columns:
        return pd.DataFrame(columns=columns)
    scores = signal.rename("score").sort_index()
    close = price_data[price_col].sort_index()
    if (
        isinstance(scores.index, pd.MultiIndex)
        and isinstance(close.index, pd.MultiIndex)
        and set(scores.index.names) == set(close.index.names)
        and scores.index.names != close.index.names
    ):
        close = close.reorder_levels(scores.index.names)
    forward = close.groupby(level="instrument").shift(-horizon) / close - 1
    aligned = pd.concat([scores, forward.rename("forward_return")], axis=1, join="inner").dropna()
    if aligned.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    instrument_level = aligned.index.names.index("instrument") if isinstance(aligned.index, pd.MultiIndex) else None
    for dt, day_df in aligned.groupby(level="datetime"):
        day = day_df.sort_values("score", ascending=False).copy()
        day["rank"] = range(1, len(day) + 1)
        for idx, row in day.iterrows():
            instrument = idx[instrument_level] if instrument_level is not None else idx
            accepted = int(row["rank"]) <= topk
            rows.append(
                {
                    "date": pd.to_datetime(dt).strftime("%Y-%m-%d"),
                    "instrument": str(instrument),
                    "decision": "accepted" if accepted else "rejected",
                    "rejection_reason": "" if accepted else "score_threshold",
                    "score": round(float(row["score"]), 10),
                    "rank": int(row["rank"]),
                    "forward_return": round(float(row["forward_return"]), 10),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def build_risk_cap_diagnostics(
    portfolio_returns: pd.DataFrame,
    *,
    run_id: str,
    rolling_window: int = 20,
    policy: RiskCapPolicy | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build diagnostic-only risk-cap counterfactual rows and one-row summary."""

    required = ["date", "portfolio_return", "benchmark_return"]
    if portfolio_returns is None or portfolio_returns.empty:
        return pd.DataFrame(), pd.DataFrame()
    missing = [col for col in required if col not in portfolio_returns.columns]
    if missing:
        raise ValueError(f"portfolio_returns missing required columns: {missing}")
    if rolling_window < 2:
        raise ValueError("rolling_window must be at least 2")

    frame = portfolio_returns[required].copy()
    returns = frame["portfolio_return"].astype(float).tolist()
    benchmark_returns = frame["benchmark_return"].astype(float).tolist()
    nav = (1.0 + frame["portfolio_return"].astype(float)).cumprod().tolist()
    trailing_vol = compute_rolling_vol(returns, window=rolling_window)
    trailing_drawdown = compute_drawdown(nav)
    lagged_vol = [None] + trailing_vol[:-1]
    lagged_drawdown = [None] + trailing_drawdown[:-1]
    rows = compute_risk_cap_counterfactual_series(
        pre_cap_returns=returns,
        lagged_vol=lagged_vol,
        lagged_drawdown=lagged_drawdown,
        policy=policy,
    )
    row_frame = pd.DataFrame(rows)
    row_frame.insert(0, "date", frame["date"].astype(str).values)
    row_frame["decision_label"] = "diagnostic_only"
    summary = summarize_risk_cap_counterfactual(
        rows,
        fold_id=run_id,
        candidate_id=run_id,
        decision_label="diagnostic_only",
        benchmark_returns=benchmark_returns,
    )
    summary_frame = pd.DataFrame([summary])
    return row_frame, summary_frame


def export_attribution_inputs(
    *,
    run_id: str,
    output_dir: str | Path,
    report: pd.DataFrame,
    signal: pd.Series | None = None,
    price_data: pd.DataFrame | None = None,
    topk: int | None = None,
    horizon: int = 1,
    export_risk_cap_diagnostics: bool = False,
    risk_cap_rolling_window: int = 20,
) -> dict[str, Path]:
    """Write disabled-by-default attribution input artifacts for a completed local run."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    portfolio = build_portfolio_returns(report)
    portfolio_path = output_dir / f"{run_id}_portfolio_returns.csv"
    portfolio.to_csv(portfolio_path, index=False)
    written["portfolio_returns"] = portfolio_path

    exposures = build_risk_exposures(portfolio)
    exposure_path = output_dir / f"{run_id}_risk_exposures.csv"
    exposures.to_csv(exposure_path, index=False)
    written["risk_exposures"] = exposure_path

    if export_risk_cap_diagnostics:
        rows, summary = build_risk_cap_diagnostics(
            portfolio,
            run_id=run_id,
            rolling_window=risk_cap_rolling_window,
        )
        if not rows.empty:
            rows_path = output_dir / f"{run_id}_risk_cap_counterfactual.csv"
            rows.to_csv(rows_path, index=False)
            written["risk_cap_counterfactual"] = rows_path
        if not summary.empty:
            summary_path = output_dir / f"{run_id}_risk_cap_summary.csv"
            summary.to_csv(summary_path, index=False)
            written["risk_cap_summary"] = summary_path

    if signal is not None and price_data is not None and topk is not None:
        events = build_candidate_events(signal, price_data, topk=topk, horizon=horizon)
        if not events.empty:
            events_path = output_dir / f"{run_id}_candidate_events.csv"
            events.to_csv(events_path, index=False)
            written["candidate_events"] = events_path
    return written


def _series_or_first(frame: pd.DataFrame, name: str) -> pd.Series:
    if name in frame.columns:
        return frame[name].fillna(0.0).astype(float)
    return frame.iloc[:, 0].fillna(0.0).astype(float)
