"""How sure are we? A cluster bootstrap over report weeks.

Reports in the same week share one market mood, so they aren't independent. If
we resampled single reports, the 95% range would come out too narrow and we
could mistake luck for a signal. So we resample whole report WEEKS:

  1. Group the predictions by `cluster` (week_id by default).
  2. Draw that many clusters at random WITH replacement (some weeks twice, some never).
  3. Recompute 1 - (total model error / total baseline error) on the drawn weeks.
  4. Repeat n times. The 95% range is the 2.5th to 97.5th percentile of those values.

Use numpy.random.default_rng(seed) so the same inputs give the same range every time.

To match the numbers in fixtures/demo_results exactly, do it this way:
  codes, _ = pd.factorize(pred[cluster])        # clusters in order of first appearance
  sum the model and baseline absolute errors per cluster (np.bincount with weights)
  draws = rng.integers(0, k, size=(n, k))       # k = number of clusters
  boot = 1 - sum_model[draws].sum(axis=1) / sum_base[draws].sum(axis=1)
  ci_low, ci_high = np.quantile(boot, [(1 - ci) / 2, 1 - (1 - ci) / 2])
The config says cluster: week, which means the "week_id" column.

Done when tests/test_eval.py::test_bootstrap_* and test_week_clusters_* pass.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def cluster_bootstrap(pred: pd.DataFrame, cluster: str = "week_id", n: int = 2000, seed: int = 2026,
                      ci: float = 0.95, model_col: str = "pred_model", base_col: str = "pred_baseline") -> dict:
    """Return a dict with:
      point             1 - sum|y - model| / sum|y - base| on the real data
      ci_low, ci_high   the percentile range
      ci_level          ci
      cluster           the column used
      n_clusters        number of distinct clusters
      n_resamples       n
      share_above_zero  fraction of resampled values > 0
      draws             numpy array of the n resampled values
    """
    """Calculate a cluster bootstrap confidence interval for relative improvement."""
    y = pred["y_true"].to_numpy()
    p_model = pred[model_col].to_numpy()
    p_base = pred[base_col].to_numpy()

    model_error = np.abs(y - p_model)
    base_error = np.abs(y - p_base)

    codes, _ = pd.factorize(pred[cluster])
    k = int(codes.max() + 1) if len(codes) else 0

    sum_model = np.bincount(codes, weights=model_error, minlength=k)
    sum_base = np.bincount(codes, weights=base_error, minlength=k)

    total_base = sum_base.sum()
    point = (
        float(1 - sum_model.sum() / total_base)
        if total_base != 0
        else 0.0
    )

    rng = np.random.default_rng(seed)
    draws_idx = rng.integers(0, k, size=(n, k))

    boot_model = sum_model[draws_idx].sum(axis=1)
    boot_base = sum_base[draws_idx].sum(axis=1)

    draws = np.divide(
        boot_model,
        boot_base,
        out=np.zeros_like(boot_model, dtype=float),
        where=boot_base != 0,
    )
    draws = 1 - draws

    alpha = (1 - ci) / 2
    ci_low, ci_high = np.quantile(draws, [alpha, 1 - alpha])

    return {
        "point": float(point),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "ci_level": float(ci),
        "cluster": cluster,
        "n_clusters": k,
        "n_resamples": n,
        "share_above_zero": float(np.mean(draws > 0)),
        "draws": draws,
    }
