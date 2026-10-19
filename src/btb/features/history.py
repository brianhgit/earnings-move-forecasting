"""Last-8-moves inputs.

For every earnings report, look back at the SAME company's earlier reports and
summarize the moves that had fully played out by this report's cutoff.

Rule (leakage check L2): an earlier report counts only if its after_date is on or
before THIS report's cutoff_date. Example: a company reports after the close on
Fri Jan 5 (after_date Mon Jan 8). Its next report has cutoff Fri Jan 5. The Jan 5
report does NOT count yet, because its reaction happened Monday.

Outputs, using up to the last 8 counted moves (oldest to newest by report_date):
  hist_median8  median of those moves          (this IS the baseline's guess)
  hist_mean8    mean
  hist_max8     max
  hist_last     the most recent one
  n_prior       how many earlier reports counted in total (not capped at 8)
If nothing counts yet: the four hist_ columns are NaN and n_prior is 0.

Group by CIK, never ticker (tickers change: FB -> META).
Within a company, sort by report_date. The after_date rule alone decides what counts
(a report's own after_date is always after its cutoff, so it never counts itself).
Run it on ALL measured reports from 2017 on, before dropping early rows, or the
2019 reports won't see their 2017-2018 history.

Done when tests/test_history.py passes, especially
test_reproduces_the_synthetic_table: your function run on fixtures/test_measured
must reproduce the hist columns of fixtures/test_events exactly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HIST_COLS = ["hist_median8", "hist_mean8", "hist_max8", "hist_last", "n_prior"]


def add_history_features(df: pd.DataFrame, k: int = 8) -> pd.DataFrame:
    """df needs: cik, report_date, after_date, cutoff_date, move_adj.

    Returns a copy of df with the HIST_COLS columns added (n_prior as int).
    """
    out = df.copy()
    n = len(out)
    med, mean, mx, last = (np.full(n, np.nan) for _ in range(4))
    n_prior = np.zeros(n, dtype="int64")

    report = out["report_date"].to_numpy()
    after = out["after_date"].to_numpy()
    cutoff = out["cutoff_date"].to_numpy()
    move = out["move_adj"].to_numpy(dtype=float)

    # Work on row positions so the caller's index and row order come back unchanged.
    for pos in out.groupby("cik", sort=False).indices.values():
        pos = pos[np.argsort(report[pos], kind="stable")]   # oldest to newest
        for i in pos:
            counted = pos[after[pos] <= cutoff[i]]           # reaction finished by this cutoff
            n_prior[i] = len(counted)
            if len(counted):
                m = move[counted[-k:]]
                med[i], mean[i], mx[i], last[i] = np.median(m), m.mean(), m.max(), m[-1]

    out["hist_median8"], out["hist_mean8"], out["hist_max8"], out["hist_last"] = med, mean, mx, last
    out["n_prior"] = n_prior
    return out
