"""Diagnostic, never the headline: is the model just shrinking the baseline?

A model can "beat" the per-stock median by pulling every guess toward the overall
median: wild stocks get guessed a bit lower, calm stocks a bit higher. That's
real, but boring, and it isn't what we want to claim. So we build that boring
version and check the model beats it too:

    pred = w * hist_median8 + (1 - w) * global_median

  - global_median = median of move_adj in the TRAINING rows
  - w = the value in {0, 0.05, 0.10, ..., 1.0} that gives the lowest mean absolute
    error on the TRAINING rows. Build the grid as np.round(np.linspace(0, 1, 21), 2)
    so float steps don't drift. On a tie keep the first (smallest) w, which is what
    np.argmin does.
  - global_median is a plain np.median of training move_adj.
  - predict(params, events) returns the formula above as a Series aligned to events.

Both are learned from training rows only. Using test rows to pick w would be leakage.

Done when tests/test_models.py::test_shrinkage_* passes.
"""

from __future__ import annotations

import pandas as pd


def fit(train: pd.DataFrame) -> dict:
    """Return {"w": float, "global_median": float}."""
    raise NotImplementedError


def predict(params: dict, events: pd.DataFrame) -> pd.Series:
    raise NotImplementedError
