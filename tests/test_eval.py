import numpy as np
import pandas as pd
import pytest

from btb.config import load
from btb.eval import backtest, bootstrap, metrics, splits
from btb.models import shrinkage
from btb.schema import validate


def _pred(n_weeks=40, per_week=20, edge=0.0, seed=0):
    rng = np.random.default_rng(seed)
    n = n_weeks * per_week
    y = np.abs(rng.standard_t(4, n)) * 4
    base = y + rng.normal(0, 3, n)
    model = y + rng.normal(0, 3 * (1 - edge), n)
    return pd.DataFrame({"event_id": [f"e{i}" for i in range(n)], "ticker": [f"T{i % 50}" for i in range(n)],
                         "sector": "X", "report_date": pd.Timestamp("2023-01-02"), "fold": "2023Q1",
                         "week_id": np.repeat([f"w{i}" for i in range(n_weeks)], per_week),
                         "y_true": y, "pred_baseline": base, "pred_model": model, "vix": 18.0})


def test_metrics_basics():
    p = _pred()
    assert metrics.mae([1, 2], [2, 2]) == 0.5
    assert metrics.rel_improvement(p["y_true"], p["pred_baseline"], p["pred_baseline"]) == 0
    assert metrics.win_rate([0], [1], [1]) == 0.5


def test_bootstrap_brackets_point_and_is_reproducible():
    p = _pred(edge=0.2)
    a = bootstrap.cluster_bootstrap(p, n=500, seed=1)
    b = bootstrap.cluster_bootstrap(p, n=500, seed=1)
    assert a["ci_low"] <= a["point"] <= a["ci_high"]
    assert a["ci_low"] == b["ci_low"]
    assert a["n_clusters"] == 40


def test_week_clusters_are_wider_than_single_events_when_weeks_share_shocks():
    p = _pred(edge=0.1)
    rng = np.random.default_rng(5)
    shock = pd.Series(rng.normal(0, 4, 40), index=[f"w{i}" for i in range(40)])
    p["pred_model"] = p["pred_model"] + p["week_id"].map(shock)   # whole weeks go right or wrong together
    by_week = bootstrap.cluster_bootstrap(p, "week_id", n=1000)
    by_event = bootstrap.cluster_bootstrap(p, "event_id", n=1000)
    assert (by_week["ci_high"] - by_week["ci_low"]) > (by_event["ci_high"] - by_event["ci_low"])


def test_shrinkage_fit_on_train_only(dev_events):
    params = shrinkage.fit(dev_events)
    assert 0 <= params["w"] <= 1


def test_backtest_end_to_end_on_synthetic(dev_events):
    """Folds + predictions only. (Scoring is tested separately.)"""
    cfg = load()
    folds = splits.walk_forward(dev_events, "dev", cfg)
    pred = backtest.predict_folds(dev_events, folds, cfg)
    validate(pred, "predictions")
    assert pred["fold"].nunique() == 12
    assert {"pred_shrunk", "n_train", "model_fp"} <= set(pred.columns)
    assert set(pred["event_id"]) == set(dev_events.loc[dev_events["split"] == "dev", "event_id"])


def test_evaluate_has_every_key(fake_pred):
    """Runs on fake predictions, no model needed."""
    met = metrics.evaluate(fake_pred, load())
    assert {"overall", "bootstrap_week", "bootstrap_company", "bootstrap_draws_week", "shrinkage", "by_fold",
            "by_sector", "by_vix", "point_in_time_members_only", "success", "tripwire"} <= set(met)
    assert "draws" not in met["bootstrap_week"]
    assert met["overall"]["n_events"] == len(fake_pred)
    assert met["bootstrap_week"]["ci_low"] <= met["bootstrap_week"]["point"] <= met["bootstrap_week"]["ci_high"]


def test_backtest_is_deterministic(dev_events):
    cfg = load()
    folds = splits.walk_forward(dev_events, "dev", cfg)[:2]
    a = backtest.predict_folds(dev_events, folds, cfg)
    b = backtest.predict_folds(dev_events, folds, cfg)
    pd.testing.assert_series_equal(a["pred_model"], b["pred_model"])


def test_schema_catches_leaky_rows(events):
    bad = events.copy()
    bad.loc[bad.index[0], "cutoff_date"] = bad.loc[bad.index[0], "after_date"]
    with pytest.raises(ValueError, match="cutoff_date"):
        validate(bad, "events")


def test_synthetic_matches_schema(events):
    validate(events, "events")
    assert set(events["split"]) <= {"train_only", "dev", "lockbox", "live"}
