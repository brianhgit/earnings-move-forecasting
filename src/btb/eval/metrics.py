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
    y = pd.Series(y)
    p = pd.Series(p)
    return float((y - p).abs().mean())


def rel_improvement(y, p_model, p_base) -> float:
    model_mae = mae(y, p_model)
    base_mae = mae(y, p_base)
    if base_mae == 0:
        return 0.0 if model_mae == 0 else float("-inf")
    return float(1 - model_mae / base_mae)


def win_rate(y, p_model, p_base) -> float:
    """Share of events where the model was strictly closer. Ties count as half."""
    y = pd.Series(y)
    model_error = (y - pd.Series(p_model)).abs()
    base_error = (y - pd.Series(p_base)).abs()
    wins = (model_error < base_error).astype(float)
    ties = (model_error == base_error).astype(float)
    return float((wins + 0.5 * ties).mean())


def summarize(pred: pd.DataFrame, model_col: str = "pred_model", base_col: str = "pred_baseline") -> dict:
    """pred is the "predictions" table. Return:
    n_events, n_weeks (unique week_id), n_companies (unique ticker),
    mae_baseline, mae_model, rel_improvement, win_rate, median_actual (median y_true).
    """
    y = pred["y_true"]
    p_model = pred[model_col]
    p_base = pred[base_col]

    return {
        "n_events": int(len(pred)),
        "n_weeks": int(pred["week_id"].nunique()),
        "n_companies": int(pred["ticker"].nunique()),
        "mae_baseline": mae(y, p_base),
        "mae_model": mae(y, p_model),
        "rel_improvement": rel_improvement(y, p_model, p_base),
        "win_rate": win_rate(y, p_model, p_base),
        "median_actual": float(y.median()),
    }


def by_group(pred: pd.DataFrame, col: str) -> pd.DataFrame:
    """One row per value of `col` (groupby(col, observed=True), default sorted order), columns:
    col, n_events, mae_baseline, mae_model, rel_improvement, win_rate (from summarize)."""
    """Return event counts and model metrics for each group."""
    rows = []

    for value, group in pred.groupby(col, observed=True):
        stats = summarize(group)
        rows.append({
            col: value,
            "n_events": stats["n_events"],
            "mae_baseline": stats["mae_baseline"],
            "mae_model": stats["mae_model"],
            "rel_improvement": stats["rel_improvement"],
            "win_rate": stats["win_rate"],
        })

    columns = [
        col, "n_events", "mae_baseline", "mae_model",
        "rel_improvement", "win_rate",
    ]
    return pd.DataFrame(rows, columns=columns)


def vix_bucket(vix: pd.Series) -> pd.Series:
    """Categorical buckets: "calm <15", "normal 15-20", "nervous 20-30", "panic 30+"
    (edges 0, 15, 20, 30, infinity; right-inclusive like pandas.cut's default)."""
    """Assign VIX values to right-inclusive volatility buckets."""
    return pd.cut(
        vix,
        bins=[0, 15, 20, 30, float("inf")],
        labels=["calm <15", "normal 15-20", "nervous 20-30", "panic 30+"],
        right=True,
    )


def evaluate(pred: pd.DataFrame, cfg: dict | None = None) -> dict:
    """Build the full metrics dict. Settings come from cfg["eval"] and cfg["project"]["seed"].
    If cfg is None, load it with btb.config.load() (some callers pass only pred).

    Keys (see docs/RESULTS_FORMAT.md for meanings):
      overall                      summarize(pred)
      bootstrap_week               cluster_bootstrap on week_id, WITHOUT the "draws" key   <- the headline
      bootstrap_company            same but clustered on ticker                            <- sensitivity
      bootstrap_draws_week         the week bootstrap's draws as a list (rounded to 5 dp)
      shrinkage                    only if pred has pred_shrunk: {mae_shrunk, rel_improvement_vs_shrunk,
                                   ci_low, ci_high, model_beats_shrunk (ci_low > 0)}, week clusters,
                                   comparing pred_model against pred_shrunk
      by_fold, by_sector, by_vix   by_group(...) as a list of dicts (records). For by_vix, add a
                                   column vix_bucket(pred["vix"]).astype(str) and group on it, so
                                   rows come out in alphabetical order; that's expected
      point_in_time_members_only   only if pred has the in_index_at_cutoff column: summarize() of
                                   rows where it's True, or None if there are none
      success                      week point >= eval.success.min_point_improvement AND
                                   week ci_low > eval.success.ci_lower_above
      tripwire                     week point > eval.tripwire_improvement
    """
    """Build the complete metrics dictionary for a prediction table."""
    if cfg is None:
        cfg = load()

    eval_cfg = cfg["eval"]
    bootstrap_cfg = eval_cfg["bootstrap"]
    seed = int(cfg["project"]["seed"])
    n_resamples = int(bootstrap_cfg["n_resamples"])
    ci_level = float(bootstrap_cfg["ci_level"])

    overall = summarize(pred)

    week_result = cluster_bootstrap(
        pred,
        cluster="week_id",
        n=n_resamples,
        seed=seed,
        ci=ci_level,
    )
    company_result = cluster_bootstrap(
        pred,
        cluster="ticker",
        n=n_resamples,
        seed=seed,
        ci=ci_level,
    )

    week_draws = week_result["draws"]
    bootstrap_week = {
        key: value
        for key, value in week_result.items()
        if key != "draws"
    }
    bootstrap_company = {
        key: value
        for key, value in company_result.items()
        if key != "draws"
    }

    result = {
        "overall": overall,
        "bootstrap_week": bootstrap_week,
        "bootstrap_company": bootstrap_company,
        "bootstrap_draws_week": [
            round(float(value), 5) for value in week_draws
        ],
        "by_fold": by_group(pred, "fold").to_dict(orient="records"),
        "by_sector": by_group(pred, "sector").to_dict(orient="records"),
    }

    pred_vix = pred.copy()
    pred_vix["vix_bucket"] = vix_bucket(pred_vix["vix"]).astype(str)
    result["by_vix"] = by_group(pred_vix, "vix_bucket").to_dict(
        orient="records"
    )

    if "pred_shrunk" in pred.columns:
        shrink_result = cluster_bootstrap(
            pred,
            cluster="week_id",
            n=n_resamples,
            seed=seed,
            ci=ci_level,
            model_col="pred_model",
            base_col="pred_shrunk",
        )
        result["shrinkage"] = {
            "mae_shrunk": mae(pred["y_true"], pred["pred_shrunk"]),
            "rel_improvement_vs_shrunk": rel_improvement(
                pred["y_true"], pred["pred_model"], pred["pred_shrunk"]
            ),
            "ci_low": float(shrink_result["ci_low"]),
            "ci_high": float(shrink_result["ci_high"]),
            "model_beats_shrunk": bool(shrink_result["ci_low"] > 0),
        }

    if "in_index_at_cutoff" in pred.columns:
        members = pred.loc[pred["in_index_at_cutoff"].astype(bool)]
        result["point_in_time_members_only"] = (
            summarize(members) if not members.empty else None
        )

    success_cfg = eval_cfg["success"]
    result["success"] = bool(
        week_result["point"] >= float(success_cfg["min_point_improvement"])
        and week_result["ci_low"] > float(success_cfg["ci_lower_above"])
    )
    result["tripwire"] = bool(
        week_result["point"] > float(eval_cfg["tripwire_improvement"])
    )

    return result
