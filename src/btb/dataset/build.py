"""Build the events table.

    python -m btb.dataset.build        (make dataset)

Two functions:
  build_events(universe, filings, prices, ...) -> (events, exclusions)
      All the logic, on DataFrames, no files. This is what the tests check, using the
      fake raw inputs in fixtures/ (btb.synthetic.raw("tiny")).
  build()
      Reads the real inputs from data/, calls build_events, writes the outputs.

Steps inside build_events, in this order:
  1. Keep filings with form == "8-K" (not "8-K/A") whose items include "2.02", for CIKs
     in the universe. Anything else is simply ignored (not an exclusion).
  2. Per company, in time order: a 2.02 filing within 45 days (cfg event.dedupe_days) of the
     last KEPT one -> exclusions, reason "duplicate_filing".
  3. windows.assign_window(accept_ts_et, plan). Excluded -> exclusions with its reason.
  4. Adjusted closes for the stock (by yahoo_ticker) and SPY on before_date and after_date.
     Any missing -> "missing_price".
  5. ret_stock = ln(P_after / P_before), ret_spy = ln(SPY_after / SPY_before),
     move_adj = 100 * |ret_stock - ret_spy|, move_raw = 100 * |ret_stock|,
     cutoff_date = windows.cutoff_for(report_date), week_id = ISO week of report_date ("2024-W30").
  6. history.add_history_features on ALL measured reports (2017 on), before any filtering.
  7. price.price_features(prices, yahoo_ticker, cutoff_date) for each report.
     Excluded("price_gap") -> exclusions.
  8. in_index_at_cutoff from the membership table if given, else True (sensitivity column only).
  9. Keep report_date >= 2019-01-01. Of those, n_prior < 8 -> "insufficient_history".
     split: before 2022 "train_only", through 2024 "dev", through Sep 30 2026 "lockbox", after "live".
 10. Return (events, exclusions) passing validate(..., "events") and validate(..., "exclusions").
     event_id = f"{cik}-{accession}".

Call dependencies through their module (history.add_history_features(...),
price.price_features(...)), so the test's stand-ins can fill in until theirs is built.

Outputs of build():
  data/processed/events_dev.parquet       split in {train_only, dev}        <- everyone uses this
  data/processed/events_lockbox.parquet   split == lockbox                  <- only btb.eval.lockbox reads it
  data/processed/events_live.parquet      split == live                     <- live scoring
  data/processed/exclusions.csv           every dropped report and why
  results/build_report.json               counts by reason and by year (committed; no prices in it)

Rule: never open events_lockbox.parquet in a notebook. Automated checks on it are fine;
looking at its moves is not.

Done when tests/test_build.py passes.
"""

from __future__ import annotations

import pandas as pd

from btb.config import INTERIM, PROCESSED, RESULTS, load  # noqa: F401
from btb.dataset import windows  # noqa: F401
from btb.features import history, price  # noqa: F401  (call them as history.add_history_features / price.price_features)
from btb.schema import validate  # noqa: F401


def build_events(universe: pd.DataFrame, filings: pd.DataFrame, prices: pd.DataFrame,
                 membership: pd.DataFrame | None = None, plan: str | None = None,
                 cfg: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Steps 1 to 10 above. plan defaults to cfg["event"]["timing_plan"].
    Returns (events, exclusions). Exclusion columns: cik, ticker, accession, accept_ts_et, reason, detail."""
    raise NotImplementedError


def build() -> None:
    """Read data/interim/{universe,filings,prices}.parquet, call build_events, write the outputs listed above."""
    raise NotImplementedError


if __name__ == "__main__":
    build()
