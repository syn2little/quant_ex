from argparse import Namespace
from pathlib import Path

import pandas as pd

import run_walk_forward_validation as wfv


def _args(tmp_path: Path, export: bool) -> Namespace:
    return Namespace(
        python="python",
        eval_market="csi300",
        topk="15",
        n_drop="3",
        hold_thresh="8",
        grid_workers=1,
        seeds=False,
        with_extra_factors=True,
        train_config=None,
        _train_config_dict=None,
        export_attribution_inputs=export,
    )


def _patch_fold_boundaries(monkeypatch, tmp_path):
    commands = []

    monkeypatch.setattr(wfv, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(wfv, "newest_model_for_tag", lambda tag, before_ts: tmp_path / "models" / f"lgbm_{tag}.pkl")

    def fake_run_command(command, log_path):
        commands.append(command)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ok", encoding="utf-8")
        if "run_backtest.py" in command:
            dest = Path(command[command.index("--output-csv") + 1])
            dest.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {
                        "market": "csi300",
                        "topk": 15,
                        "n_drop": 3,
                        "hold_thresh": 8,
                        "annual_return": 0.1,
                        "sharpe": 1.0,
                        "max_drawdown": -0.1,
                        "rank_ic": 0.03,
                        "rank_icir": 0.2,
                    }
                ]
            ).to_csv(dest, index=False)

    monkeypatch.setattr(wfv, "run_command", fake_run_command)
    return commands


def test_wfv_fold_backtest_command_exports_attribution_inputs_when_enabled(tmp_path, monkeypatch):
    commands = _patch_fold_boundaries(monkeypatch, tmp_path)
    fold = wfv.Fold("test_2022", "2015-01-01", "2020-12-31", "2021-01-01", "2021-12-31", "2022-01-01", "2022-12-31")

    wfv._run_one_fold_universe(fold, "csi1000", _args(tmp_path, export=True), tmp_path / "wf", "unit")

    backtest_cmd = next(command for command in commands if "run_backtest.py" in command)
    assert "--export-attribution-inputs" in backtest_cmd
    assert "--run-id" in backtest_cmd
    assert backtest_cmd[backtest_cmd.index("--run-id") + 1] == "wf_csi1000_test_2022_unit"


def test_wfv_fold_backtest_command_does_not_export_attribution_inputs_by_default(tmp_path, monkeypatch):
    commands = _patch_fold_boundaries(monkeypatch, tmp_path)
    fold = wfv.Fold("test_2022", "2015-01-01", "2020-12-31", "2021-01-01", "2021-12-31", "2022-01-01", "2022-12-31")

    wfv._run_one_fold_universe(fold, "csi1000", _args(tmp_path, export=False), tmp_path / "wf", "unit")

    backtest_cmd = next(command for command in commands if "run_backtest.py" in command)
    assert "--export-attribution-inputs" not in backtest_cmd
    assert "--run-id" not in backtest_cmd
