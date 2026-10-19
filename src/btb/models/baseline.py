"""The baseline: the median of the stock's last 8 earnings moves.

"This stock usually moves about this much": the median of the company's last 8
completed earnings moves. No fitting, no parameters. It's already sitting in the
table as the hist_median8 column, so the baseline and the model always see
exactly the same history.

Done when tests/test_models.py::test_baseline_is_the_median_of_last_8 passes.
"""

from __future__ import annotations

import pandas as pd


def predict(events: pd.DataFrame) -> pd.Series:
    """One prediction per row, same index as events.

    Raise ValueError if any hist_median8 is missing: those reports should have been
    excluded upstream (fewer than 8 prior reports), and silently filling them in
    would mean the two predictors get scored on different reports.
    """
  
    col = events["hist_median8"]
    
    if col.isna().any():
        raise ValueError("hist_median8 is missing for some reports; they should have been excluded upstream")
    return col

