import importlib
import sys
from pathlib import Path

import pandas as pd


class DummyModel:
    pass


class DummyDataLoader:
    def __init__(self, config):
        self.config = config

    def load_price_data(self, instruments, start_time=None, end_time=None):
        index = pd.MultiIndex.from_product(
            [[pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02")], ["SH600000", "SZ000001"]],
            names=["datetime", "instrument"],
        )
        return pd.DataFrame({"real_close": [10.0, 20.0, 11.0, 18.0]}, index=index)


class DummyUniverseFilter:
    def __init__(self, config):
        pass

    def requires_price_data(self):
        return False

    def filter(self, pred, price_data=None):
        return pred


class DummyEngine:
    def __init__(self, config):
        self.config = config
        self.calls = []

    def run(self, pred, strategy_params, **kwargs):
        self.calls.append((pred, strategy_params, kwargs))
        report = pd.DataFrame(
            {"return": [0.02, -0.01], "cost": [0.001, 0.0], "bench": [0.01, -0.005]},
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )
        return report, {}


class DummyGridSearchBacktest:
    def __init__(self, engine, pred, config):
        self.engine = engine
        self.pred = pred
        self.config = config

    def run(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "topk": 1,
                    "n_drop": 3,
                    "hold_thresh": 5,
                    "sharpe": 1.2,
                    "information_ratio": 0.4,
                }
            ]
        )

    @staticmethod
    def best_params(results_df):
        return {"topk": int(results_df.iloc[0]["topk"]), "n_drop": 3, "hold_thresh": 5}


def test_run_backtest_exports_attribution_inputs_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONHASHSEED", "42")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    run_backtest = importlib.import_module("quant_ex.run_backtest")

    config = {
        "paths": {"backtest_results_dir": str(tmp_path / "backtest_results")},
        "training": {"test_start": "2026-01-01"},
        "market": {"name": "csi300"},
        "backtest": {"rank_metric": "information_ratio"},
        "signal": {"diagnostics": {"enabled": False}},
    }
    signal_index = pd.MultiIndex.from_product(
        [[pd.Timestamp("2026-01-01")], ["SH600000", "SZ000001"]],
        names=["datetime", "instrument"],
    )
    signal = pd.Series([0.9, 0.1], index=signal_index, name="score")

    monkeypatch.setattr(run_backtest, "load_config", lambda path=None: config)
    monkeypatch.setattr(run_backtest, "_load_model", lambda config, model_path=None: DummyModel())
    monkeypatch.setattr(run_backtest, "DataLoader", DummyDataLoader)
    monkeypatch.setattr(run_backtest, "UniverseFilter", DummyUniverseFilter)
    monkeypatch.setattr(run_backtest, "SectorDataProvider", lambda config: None)
    monkeypatch.setattr(run_backtest, "BacktestEngine", DummyEngine)
    monkeypatch.setattr(run_backtest, "GridSearchBacktest", DummyGridSearchBacktest)
    monkeypatch.setattr(run_backtest, "_predict_for_market", lambda **kwargs: signal)
    monkeypatch.setattr(run_backtest, "_signal_diagnostics_for_market", lambda **kwargs: {})

    run_backtest.main(
        topk_vals=[1],
        n_drop_vals=[3],
        hold_thresh_vals=[5],
        grid_workers=1,
        export_attribution_inputs=True,
        run_id="unit_backtest",
    )

    output_dir = tmp_path / "backtest_results" / "agent_runs"
    assert (output_dir / "unit_backtest_portfolio_returns.csv").exists()
    assert (output_dir / "unit_backtest_risk_exposures.csv").exists()
    assert (output_dir / "unit_backtest_candidate_events.csv").exists()

    events = pd.read_csv(output_dir / "unit_backtest_candidate_events.csv")
    assert set(events["decision"]) == {"accepted", "rejected"}
