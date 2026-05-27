import csv
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "agent/strategy_iteration/factor_crowding_diagnostic.py"
SPEC = importlib.util.spec_from_file_location("factor_crowding_diagnostic", MODULE_PATH)
factor_crowding_diagnostic = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(factor_crowding_diagnostic)

build_factor_crowding_diagnostic = factor_crowding_diagnostic.build_factor_crowding_diagnostic
render_factor_crowding_markdown = factor_crowding_diagnostic.render_factor_crowding_markdown


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_cluster_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    portfolio = _write_csv(
        tmp_path / "portfolio_returns.csv",
        [
            {"date": "2022-01-03", "portfolio_return": 0.01, "benchmark_return": 0.002, "cost": 0.0, "excess_return": 0.008},
            {"date": "2022-01-04", "portfolio_return": -0.02, "benchmark_return": -0.005, "cost": 0.0, "excess_return": -0.015},
            {"date": "2022-01-05", "portfolio_return": -0.06, "benchmark_return": -0.015, "cost": 0.0, "excess_return": -0.045},
            {"date": "2022-01-06", "portfolio_return": -0.05, "benchmark_return": -0.012, "cost": 0.0, "excess_return": -0.038},
        ],
    )
    risk = _write_csv(
        tmp_path / "risk_exposures.csv",
        [
            {"date": "2022-01-03", "portfolio_return": 0.01, "benchmark_return": 0.002, "residual_return": 0.008, "drawdown": 0.0, "abs_residual_return": 0.008},
            {"date": "2022-01-04", "portfolio_return": -0.02, "benchmark_return": -0.005, "residual_return": -0.015, "drawdown": -0.02, "abs_residual_return": 0.015},
            {"date": "2022-01-05", "portfolio_return": -0.06, "benchmark_return": -0.015, "residual_return": -0.045, "drawdown": -0.08, "abs_residual_return": 0.045},
            {"date": "2022-01-06", "portfolio_return": -0.05, "benchmark_return": -0.012, "residual_return": -0.038, "drawdown": -0.12, "abs_residual_return": 0.038},
        ],
    )
    events = _write_csv(
        tmp_path / "candidate_events.csv",
        [
            {"date": "2022-01-03", "instrument": "AAA", "decision": "accepted", "rejection_reason": "", "score": 0.9, "rank": 1, "forward_return": 0.02},
            {"date": "2022-01-05", "instrument": "BBB", "decision": "accepted", "rejection_reason": "", "score": 0.8, "rank": 1, "forward_return": -0.04},
            {"date": "2022-01-05", "instrument": "CCC", "decision": "accepted", "rejection_reason": "", "score": 0.7, "rank": 2, "forward_return": -0.03},
            {"date": "2022-01-05", "instrument": "DDD", "decision": "accepted", "rejection_reason": "", "score": 0.6, "rank": 3, "forward_return": -0.02},
            {"date": "2022-01-05", "instrument": "EEE", "decision": "accepted", "rejection_reason": "", "score": 0.5, "rank": 4, "forward_return": -0.01},
            {"date": "2022-01-05", "instrument": "FFF", "decision": "rejected", "rejection_reason": "rank_filter", "score": 0.4, "rank": 5, "forward_return": 0.04},
            {"date": "2022-01-05", "instrument": "GGG", "decision": "rejected", "rejection_reason": "rank_filter", "score": 0.3, "rank": 6, "forward_return": 0.03},
            {"date": "2022-01-06", "instrument": "HHH", "decision": "accepted", "rejection_reason": "", "score": 0.7, "rank": 1, "forward_return": -0.03},
            {"date": "2022-01-06", "instrument": "III", "decision": "accepted", "rejection_reason": "", "score": 0.6, "rank": 2, "forward_return": -0.02},
            {"date": "2022-01-06", "instrument": "JJJ", "decision": "accepted", "rejection_reason": "", "score": 0.5, "rank": 3, "forward_return": -0.01},
            {"date": "2022-01-06", "instrument": "KKK", "decision": "rejected", "rejection_reason": "rank_filter", "score": 0.4, "rank": 4, "forward_return": 0.05},
            {"date": "2022-01-06", "instrument": "LLL", "decision": "rejected", "rejection_reason": "rank_filter", "score": 0.3, "rank": 5, "forward_return": 0.04},
            {"date": "2022-01-06", "instrument": "MMM", "decision": "rejected", "rejection_reason": "rank_filter", "score": 0.2, "rank": 6, "forward_return": 0.03},
        ],
    )
    return portfolio, risk, events


def test_factor_crowding_diagnostic_identifies_stress_and_event_clusters(tmp_path):
    portfolio, risk, events = _write_cluster_inputs(tmp_path)

    report = build_factor_crowding_diagnostic(
        run_id="unit_factor_crowding",
        portfolio_returns_csv=portfolio,
        risk_exposures_csv=risk,
        candidate_events_csv=events,
        stress_drawdown_threshold=-0.05,
        event_cluster_min_count=3,
    )

    assert report["run_id"] == "unit_factor_crowding"
    assert report["guardrail"] == "diagnostic_only_not_trading_signal"
    assert report["summary"]["days"] == 4
    assert report["summary"]["accepted_loser_count"] == 7
    assert report["summary"]["missed_winner_count"] == 5
    assert report["summary"]["stress_cluster_days"] == 2
    assert report["crowding_buckets"]["stress_cluster_days"][0]["date"] == "2022-01-06"
    assert report["crowding_buckets"]["event_concentration_days"][0]["accepted_loser_count"] == 4
    assert "factor_crowding_proxy_stress_cluster" in report["diagnostic_flags"]
    assert "event_concentration_cluster" in report["diagnostic_flags"]
    assert report["next_action"] == "review_crowding_proxy_with_risk_memory_without_signal_promotion"

    markdown = render_factor_crowding_markdown(report)
    assert "## Factor Crowding / Co-movement Diagnostic" in markdown
    assert "diagnostic_only_not_trading_signal" in markdown
    assert "factor_crowding_proxy_stress_cluster" in markdown


def test_factor_crowding_diagnostic_excludes_event_only_dates(tmp_path):
    portfolio = _write_csv(
        tmp_path / "portfolio_returns.csv",
        [
            {"date": "2022-02-07", "portfolio_return": 0.01, "benchmark_return": 0.005},
        ],
    )
    risk = _write_csv(
        tmp_path / "risk_exposures.csv",
        [
            {"date": "2022-02-07", "portfolio_return": 0.01, "benchmark_return": 0.005, "residual_return": 0.005, "drawdown": 0.0, "abs_residual_return": 0.005},
        ],
    )
    events = _write_csv(
        tmp_path / "candidate_events.csv",
        [
            {"date": "2022-02-08", "instrument": "AAA", "decision": "accepted", "rejection_reason": "", "score": 0.9, "rank": 1, "forward_return": -0.10},
            {"date": "2022-02-08", "instrument": "BBB", "decision": "accepted", "rejection_reason": "", "score": 0.8, "rank": 2, "forward_return": -0.08},
        ],
    )

    report = build_factor_crowding_diagnostic(
        run_id="unit_orphan_event_dates",
        portfolio_returns_csv=portfolio,
        risk_exposures_csv=risk,
        candidate_events_csv=events,
        event_cluster_min_count=2,
    )

    assert report["summary"]["days"] == 1
    assert report["summary"]["events"] == 0
    assert report["orphan_event_dates"] == ["2022-02-08"]
    assert report["crowding_buckets"]["event_concentration_days"] == []
    assert report["diagnostic_flags"] == ["no_primary_crowding_proxy_detected"]
    assert "Excluded Event-Only Dates" in render_factor_crowding_markdown(report)


def test_factor_crowding_diagnostic_clamps_negative_top_days(tmp_path):
    portfolio, risk, events = _write_cluster_inputs(tmp_path)

    report = build_factor_crowding_diagnostic(
        run_id="unit_negative_top_days",
        portfolio_returns_csv=portfolio,
        risk_exposures_csv=risk,
        candidate_events_csv=events,
        stress_drawdown_threshold=-0.05,
        event_cluster_min_count=3,
        top_days=-1,
    )

    assert report["summary"]["stress_cluster_days"] == 2
    assert report["crowding_buckets"]["stress_cluster_days"] == []
    assert report["crowding_buckets"]["event_concentration_days"] == []
    assert report["crowding_buckets"]["missed_winner_cluster_days"] == []
    assert report["diagnostic_flags"] == ["no_primary_crowding_proxy_detected"]


def test_factor_crowding_diagnostic_uses_no_primary_flag_when_clusters_absent(tmp_path):
    portfolio = _write_csv(
        tmp_path / "portfolio_returns.csv",
        [
            {"date": "2022-02-07", "portfolio_return": 0.01, "benchmark_return": 0.005},
            {"date": "2022-02-08", "portfolio_return": 0.005, "benchmark_return": 0.002},
        ],
    )
    risk = _write_csv(
        tmp_path / "risk_exposures.csv",
        [
            {"date": "2022-02-07", "portfolio_return": 0.01, "benchmark_return": 0.005, "residual_return": 0.005, "drawdown": 0.0, "abs_residual_return": 0.005},
            {"date": "2022-02-08", "portfolio_return": 0.005, "benchmark_return": 0.002, "residual_return": 0.003, "drawdown": 0.0, "abs_residual_return": 0.003},
        ],
    )
    events = _write_csv(
        tmp_path / "candidate_events.csv",
        [
            {"date": "2022-02-07", "instrument": "AAA", "decision": "accepted", "rejection_reason": "", "score": 0.9, "rank": 1, "forward_return": 0.01},
            {"date": "2022-02-08", "instrument": "BBB", "decision": "rejected", "rejection_reason": "rank_filter", "score": 0.4, "rank": 2, "forward_return": -0.01},
        ],
    )

    report = build_factor_crowding_diagnostic(
        run_id="unit_no_crowding",
        portfolio_returns_csv=portfolio,
        risk_exposures_csv=risk,
        candidate_events_csv=events,
        stress_drawdown_threshold=-0.05,
        event_cluster_min_count=3,
    )

    assert report["crowding_buckets"]["stress_cluster_days"] == []
    assert report["crowding_buckets"]["event_concentration_days"] == []
    assert report["diagnostic_flags"] == ["no_primary_crowding_proxy_detected"]
