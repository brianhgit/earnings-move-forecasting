"""Price inputs at a cutoff.

Exact definitions (LOCKED, they are in the prereg). All use adjusted closes on
sessions up to and including cutoff_date, nothing after:

  r_t        = ln(adj_close_t / adj_close_{t-1})
  vol_21d    = std(r over the last 21 sessions ending at cutoff, ddof=1) * sqrt(252) * 100
  vol_63d    = same over 63 sessions
  ret_21d    = 100 * ln(adj_close_cutoff / adj_close_{cutoff - 21 sessions})
  absret_21d = |ret_21d|
  vix        = ^VIX close on cutoff_date (raw close; VIX has no adjustment)

Never use a price LEVEL as a feature: adjusted levels are rewritten every time a
dividend is paid, so a level would quietly carry future information. Ratios are safe.

Leakage check L1 (tests/test_leakage.py): scrambling every price after the cutoff
must not change any output of price_features.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

PRICE_FEATURES = ["vol_21d", "vol_63d", "ret_21d", "absret_21d", "vix"]


def price_features(prices: pd.DataFrame, ticker: str, cutoff: dt.date) -> dict[str, float]:
    """prices: long table (schema "prices"). Returns {name: value} for PRICE_FEATURES.

    Raise btb.dataset.windows.Excluded("price_gap") if fewer than 64 sessions are available.
    """
    raise NotImplementedError
