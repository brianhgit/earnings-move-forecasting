"""Leakage checks L1 to L5 from the plan. These guard the headline number."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from btb.config import load
from btb.eval import backtest, splits
from btb.features.history import add_history_features
from btb.features.price import price_features
from conftest import call_or_skip


def test_L2_poisoned_future_does_not_change_features(events):
    base = events[["cik", "report_date", "after_date", "cutoff_date", "move_adj"]].copy()
    a = add_history_features(base)
    cut = pd.Timestamp("2023-06-30")
    poisoned = base.copy()
    poisoned.loc[poisoned["after_date"] > cut, "move_adj"] = 999.0
    b = add_history_features(poisoned)
    m = a["cutoff_date"] < cut
    pd.testing.assert_frame_equal(a.loc[m, ["hist_median8", "hist_max8", "n_prior"]],
                                  b.loc[m, ["hist_median8", "hist_max8", "n_prior"]])


def test_L3_split_rule(dev_events):
    folds = splits.walk_forward(dev_events, "dev")
    assert len(folds) == 12
    splits.check_no_leak(dev_events, folds)
    for f in folds:
        assert dev_events.loc[f.train_idx, "after_date"].max() <= dev_events.loc[f.test_idx, "cutoff_date"].min()


def test_L3_dev_refuses_lockbox_rows(events):
    with pytest.raises(RuntimeError):
        splits.walk_forward(events, "dev")


def test_L4_shuffled_answers_cannot_beat_baseline(dev_events):
    """Train on scrambled targets: if this 'wins', scoring or splitting is broken."""
    cfg = load()
    ev = dev_events.copy()
    rng = np.random.default_rng(0)
    folds = splits.walk_forward(ev, "dev", cfg)
    shuffled = ev.copy()
    shuffled["move_adj"] = rng.permutation(ev["move_adj"].to_numpy())
    pred = backtest.predict_folds(shuffled, folds, cfg)
    pred["y_true"] = ev.set_index("event_id").loc[pred["event_id"], "move_adj"].to_numpy()  # score on the REAL moves
    err_m = np.abs(pred["y_true"] - pred["pred_model"]).sum()
    err_b = np.abs(pred["y_true"] - pred["pred_baseline"]).sum()
    assert 1 - err_m / err_b < 0.03, "a model trained on scrambled answers should not clear the success bar"


def test_L1_price_features_ignore_the_future():
    """Scramble every price after the cutoff; features must not move."""
    days = pd.bdate_range("2023-01-02", "2023-12-29")
    rng = np.random.default_rng(3)
    px = pd.DataFrame({"date": days.date, "ticker": "AAA",
                       "adj_close": 100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(days)))),
                       "close": 0.0, "volume": 1.0})
    vix = px.assign(ticker="^VIX", adj_close=20 + rng.normal(0, 1, len(days)))
    prices = pd.concat([px, vix], ignore_index=True)
    prices["close"] = prices["adj_close"]
    cutoff = dt.date(2023, 9, 15)
    a = call_or_skip(price_features, prices, "AAA", cutoff)
    scrambled = prices.copy()
    after = pd.to_datetime(scrambled["date"]) > pd.Timestamp(cutoff)
    scrambled.loc[after, ["adj_close", "close"]] *= rng.uniform(0.5, 2.0, after.sum())[:, None]
    b = price_features(scrambled, "AAA", cutoff)
    assert a == pytest.approx(b)
