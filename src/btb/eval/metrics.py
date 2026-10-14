"""Scoring.

Everything is mean absolute error (MAE) in percentage points.

    rel_improvement = 1 - MAE_model / MAE_baseline
    0.05 means the model's average miss is 5% smaller than the simple guess's.

`evaluate()` is THE scoring function for backtest, lockbox and live. Everything
anyone ever reports comes out of it, so there is exactly one copy. Its output is
written to metrics.json and read by the charts and the app; the exact keys are
listed in docs/RESULTS_FORMAT.md and checked by tests/test_eval.py.

Done when tests/test_eval.py passes (the metric and evaluate tests).
"""

from __future__ import annotations

import pandas as pd

from btb.config import load  # noqa: F401
from btb.eval.bootstrap import cluster_bootstrap  # noqa: F401


def mae(y, p) -> float:
    raise NotImplementedError


def rel_improvement(y, p_model, p_base) -> float:
    raise NotImplementedError


def win_rate(y, p_model, p_base) -> float:
    """Share of events where the model was strictly closer. Ties count as half."""
    raise NotImplementedError


def summarize(pred: pd.DataFrame, model_col: str = "pred_model", base_col: str = "pred_baseline") -> dict:
    """pred is the "predictions" table. Return:
    n_events, n_weeks (unique week_id), n_companies (unique ticker),
    mae_baseline, mae_model, rel_improvement, win_rate, median_actual (median y_true).
    """
    raise NotImplementedError


def by_group(pred: pd.DataFrame, col: str) -> pd.DataFrame:
    """One row per value of `col`, columns:
    col, n_events, mae_baseline, mae_model, rel_improvement, win_rate."""
    raise NotImplementedError


def vix_bucket(vix: pd.Series) -> pd.Series:
    """Categorical buckets: "calm <15", "normal 15-20", "nervous 20-30", "panic 30+"
    (edges 0, 15, 20, 30, infinity; right-inclusive like pandas.cut's default)."""
    raise NotImplementedError


def evaluate(pred: pd.DataFrame, cfg: dict | None = None) -> dict:
    """Build the full metrics dict. Settings come from cfg["eval"] and cfg["project"]["seed"].

    Keys (see docs/RESULTS_FORMAT.md for meanings):
      overall                      summarize(pred)
      bootstrap_week               cluster_bootstrap on week_id, WITHOUT the "draws" key   <- the headline
      bootstrap_company            same but clustered on ticker                            <- sensitivity
      bootstrap_draws_week         the week bootstrap's draws as a list (rounded to 5 dp)
      shrinkage                    only if pred has pred_shrunk: {mae_shrunk, rel_improvement_vs_shrunk,
                                   ci_low, ci_high, model_beats_shrunk (ci_low > 0)}, week clusters,
                                   comparing pred_model against pred_shrunk
      by_fold, by_sector, by_vix   by_group(...) as a list of dicts (by_vix uses vix_bucket as strings)
      point_in_time_members_only   only if pred has in_index_at_cutoff: summarize() of those rows
      success                      week point >= eval.success.min_point_improvement AND
                                   week ci_low > eval.success.ci_lower_above
      tripwire                     week point > eval.tripwire_improvement
    """
    raise NotImplementedError
