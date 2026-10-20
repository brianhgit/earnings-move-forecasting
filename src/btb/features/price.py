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

import numpy as np
import pandas as pd

from btb.dataset.windows import Excluded

PRICE_FEATURES = ["vol_21d", "vol_63d", "ret_21d", "absret_21d", "vix"]


def price_features(prices: pd.DataFrame, ticker: str, cutoff: dt.date) -> dict[str, float]:
    # Calculate price features using data available on or before cutoff.

    cutoff_ts = pd.Timestamp(cutoff)
    dates = pd.to_datetime(prices["date"])

    # Filter first so later price revisions or returns cannot leak into these features.
    stock = prices.loc[
        (prices["ticker"] == ticker) & (dates <= cutoff_ts)
    ].copy()

    stock["date"] = pd.to_datetime(stock["date"])
    stock = stock.sort_values("date")

    # 64 closes provide 63 returns; the final close must be exactly the requested cutoff.
    if len(stock) < 64 or stock["date"].iloc[-1] != cutoff_ts:
        raise Excluded(
            "price_gap",
            f"{ticker}: insufficient history or missing cutoff date",
        )

    adj_close = stock["adj_close"].astype(float)

    # Daily log returns.
    log_returns = np.log(adj_close / adj_close.shift(1)).dropna()

    # Annualized volatility over the last 21 and 63 returns.
    vol_21d = log_returns.tail(21).std(ddof=1) * np.sqrt(252) * 100
    vol_63d = log_returns.tail(63).std(ddof=1) * np.sqrt(252) * 100

    # Twenty-one intervals require the cutoff close and the close 21 rows earlier.
    ret_21d = 100 * np.log(adj_close.iloc[-1] / adj_close.iloc[-22])
    absret_21d = abs(ret_21d)

    # VIX closing price on the cutoff date.
    vix_rows = prices.loc[
        (prices["ticker"] == "^VIX") & (dates == cutoff_ts)
    ]
    vix = (
        float(vix_rows["close"].iloc[-1])
        if not vix_rows.empty
        else float("nan")
    )

    return {
        "vol_21d": float(vol_21d),
        "vol_63d": float(vol_63d),
        "ret_21d": float(ret_21d),
        "absret_21d": float(absret_21d),
        "vix": vix,
    }
