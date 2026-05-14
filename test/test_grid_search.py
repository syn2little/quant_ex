import pandas as pd

from quant_ex.backtest.grid_search import GridSearchBacktest


class RecordingEngine:
    def __init__(self):
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        index = pd.date_range("2024-01-01", periods=2, freq="D")
        report = pd.DataFrame(
            {
                "return": [0.01, 0.02],
                "bench": [0.0, 0.0],
                "cost": [0.0, 0.0],
            },
            index=index,
        )
        return report, {}


def test_grid_search_sorts_by_configured_rank_metric():
    searcher = GridSearchBacktest(
        engine=None,
        pred=pd.Series(dtype=float),
        config={"backtest": {"rank_metric": "information_ratio"}},
    )
    df = pd.DataFrame(
        [
            {"topk": 5, "sharpe": 2.0, "information_ratio": 0.1},
            {"topk": 10, "sharpe": 1.0, "information_ratio": 0.5},
        ]
    )

    sorted_df = searcher._sort_results(df)

    assert sorted_df.iloc[0]["topk"] == 10


def test_grid_search_passes_backtest_overrides_to_engine():
    engine = RecordingEngine()
    searcher = GridSearchBacktest(
        engine=engine,
        pred=pd.Series(dtype=float),
        config={"backtest": {"rank_metric": "information_ratio"}},
    )

    searcher.run(
        param_grid={"topk": [5], "n_drop": [1], "hold_thresh": [5]},
        n_jobs=1,
        benchmark="SH000905",
        deal_price="open",
        open_cost=0.0007,
        close_cost=0.0017,
        min_cost=3.5,
    )

    assert len(engine.calls) == 1
    call = engine.calls[0]
    assert call["benchmark"] == "SH000905"
    assert call["deal_price"] == "open"
    assert call["open_cost"] == 0.0007
    assert call["close_cost"] == 0.0017
    assert call["min_cost"] == 3.5
