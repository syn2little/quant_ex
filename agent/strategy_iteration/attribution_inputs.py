from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


REQUIREMENTS = {
    "portfolio_returns": {
        "description": "Daily portfolio and benchmark returns for residual attribution.",
        "patterns": [
            "backtest_results/**/*portfolio*return*.csv",
            "backtest_results/**/*returns*.csv",
            "optimization_results/**/*portfolio*return*.csv",
        ],
        "required_columns": {"date", "portfolio_return", "benchmark_return"},
        "optional_columns": {"position_count", "turnover", "strategy_return"},
        "required": True,
    },
    "risk_exposures": {
        "description": "Date-level risk exposures or risk model inputs for transient factor diagnostics.",
        "patterns": [
            "backtest_results/**/*risk*exposure*.csv",
            "backtest_results/**/*exposure*.csv",
            "optimization_results/**/*risk*exposure*.csv",
        ],
        "required_columns": {"date", "portfolio_return", "benchmark_return"},
        "optional_columns": {"market_exposure", "size_exposure", "value_exposure", "industry_exposure"},
        "required": True,
    },
    "candidate_events": {
        "description": "Generated/accepted/rejected candidate events for missed-winner and avoided-loser attribution.",
        "patterns": [
            "backtest_results/**/*candidate*event*.csv",
            "backtest_results/**/*rejected*.csv",
            "optimization_results/**/*candidate*event*.csv",
            "docs/strategy_log/**/*candidate*event*.csv",
        ],
        "required_columns": {"date", "instrument", "decision", "forward_return"},
        "optional_columns": {"rejection_reason", "score", "rank", "weight"},
        "required": False,
    },
    "risk_cap_counterfactual": {
        "description": "Diagnostic-only risk-cap counterfactual rows generated from lagged portfolio risk inputs.",
        "patterns": [
            "backtest_results/**/*risk*cap*counterfactual*.csv",
            "optimization_results/**/*risk*cap*counterfactual*.csv",
        ],
        "required_columns": {"date", "state", "multiplier", "pre_cap_return", "post_cap_return", "decision_label"},
        "optional_columns": {"lagged_vol", "lagged_drawdown", "pre_cap_nav", "post_cap_nav"},
        "required": False,
    },
    "risk_cap_summary": {
        "description": "One-row diagnostic-only summary for a risk-cap counterfactual export.",
        "patterns": [
            "backtest_results/**/*risk*cap*summary*.csv",
            "optimization_results/**/*risk*cap*summary*.csv",
        ],
        "required_columns": {"fold_id", "candidate_id", "decision_label", "baseline_max_drawdown", "capped_max_drawdown"},
        "optional_columns": {"tail_loss_delta", "positive_return_capture_delta", "cap_active_days", "avg_cap_multiplier"},
        "required": False,
    },
}


def assess_attribution_input_contract(root: str | Path) -> dict[str, Any]:
    """Inspect local artifacts needed before transient-factor attribution can run."""

    root = Path(root)
    requirements = {
        name: _assess_requirement(root, name, spec)
        for name, spec in REQUIREMENTS.items()
    }
    primary_ready = all(requirements[name]["status"] == "ready" for name in ("portfolio_returns", "risk_exposures"))
    events_ready = requirements["candidate_events"]["status"] == "ready"
    risk_cap_schema_ready = all(
        requirements[name]["status"] == "ready"
        for name in ("risk_cap_counterfactual", "risk_cap_summary")
    )
    risk_cap_decision_label_valid = risk_cap_schema_ready and all(
        _csv_column_values(root / requirements[name]["path"], "decision_label") == {"diagnostic_only"}
        for name in ("risk_cap_counterfactual", "risk_cap_summary")
    )
    risk_cap_ready = risk_cap_schema_ready and risk_cap_decision_label_valid
    if primary_ready:
        overall = "ready_for_transient_diagnostic" if events_ready else "ready_for_transient_only"
        next_action = "implement_risk_transient_factor_attribution_v0"
    else:
        overall = "blocked_missing_contract"
        next_action = "define_or_generate_attribution_inputs"
    if primary_ready and risk_cap_ready:
        next_action = "review_risk_cap_counterfactual_diagnostic"
    return {
        "overall_status": overall,
        "next_action": next_action,
        "requirements": requirements,
        "optional_capabilities": {
            "risk_cap_counterfactual": {
                "status": _risk_cap_optional_status(risk_cap_schema_ready, risk_cap_decision_label_valid),
                "decision_label": "diagnostic_only",
                "promotion_evidence": False,
            }
        },
        "guardrails": [
            "Use only local artifacts; do not refresh market data automatically.",
            "Do not run full WFV, live notifications, or trading-like actions from this diagnostic.",
            "Transient factors and risk-cap counterfactuals are attribution evidence, not trading signals.",
        ],
    }


def contract_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Attribution Input Contract Report",
        "",
        f"- Overall status: {report.get('overall_status')}",
        f"- Next action: {report.get('next_action')}",
        "",
        "## Requirements",
    ]
    for name, item in (report.get("requirements") or {}).items():
        lines.extend([
            f"### {name}",
            f"- Status: {item.get('status')}",
            f"- Description: {item.get('description')}",
            f"- Candidate path: `{item.get('path', '')}`" if item.get("path") else "- Candidate path: none",
            "- Missing columns: " + ", ".join(item.get("missing_columns") or []),
            "- Available columns: " + ", ".join((item.get("columns") or [])[:30]),
            "",
        ])
    lines.append("## Optional capabilities")
    for name, item in (report.get("optional_capabilities") or {}).items():
        lines.extend([
            f"### {name}",
            f"- Status: {item.get('status')}",
            f"- Decision label: {item.get('decision_label')}",
            f"- Promotion evidence: {item.get('promotion_evidence')}",
            "",
        ])
    lines.append("## Guardrails")
    lines.extend(f"- {item}" for item in report.get("guardrails") or [])
    return "\n".join(lines) + "\n"


def _assess_requirement(root: Path, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    candidates = _candidate_files(root, spec["patterns"])
    required = set(spec["required_columns"])
    best = None
    for path in candidates:
        columns = _csv_columns(path)
        missing = sorted(required - set(columns))
        current = {
            "description": spec["description"],
            "status": "ready" if not missing else "missing_columns",
            "path": str(path.relative_to(root)),
            "columns": columns,
            "required_columns": sorted(required),
            "missing_columns": missing,
        }
        if not missing:
            return current
        if best is None or len(missing) < len(best.get("missing_columns", [])):
            best = current
    if best:
        return best
    return {
        "description": spec["description"],
        "status": "missing_artifact",
        "path": "",
        "columns": [],
        "required_columns": sorted(required),
        "missing_columns": sorted(required),
    }


def _candidate_files(root: Path, patterns: list[str]) -> list[Path]:
    seen = set()
    files = []
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                files.append(path)
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def _csv_columns(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle).fieldnames or [])
    except Exception:
        return []


def _csv_column_values(path: Path, column: str) -> set[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return {str(row.get(column, "")).strip() for row in reader if row.get(column, "") != ""}
    except Exception:
        return set()


def _risk_cap_optional_status(schema_ready: bool, decision_label_valid: bool) -> str:
    if not schema_ready:
        return "missing_optional_artifact"
    if not decision_label_valid:
        return "invalid_decision_label"
    return "ready"
