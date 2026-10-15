"""Make a forecast drop for EVERY company in the universe.
(main() is plumbing and done; the two functions below are yours.)
Until lgbm/shrinkage are implemented, the tests use stand-ins for them (src/btb/standins.py),
so call them as lgbm.fit(...) / shrinkage.fit(...), through the module.

    python -m btb.live.forecast --drop drop1            (make forecast DROP=drop1)

Why every company and not just the ones we expect to report: then nobody (us
included) chooses which reports get scored. Whoever actually files an earnings
8-K inside the drop's window after we posted gets scored. Date changes, surprise
reports and companies we forgot about are all handled without any judgment calls.

Order of operations this script enforces:
  1. The lockbox must already be opened (results/lockbox/OPENED.json exists).
  2. Train the live model ONCE per drop on every event whose move finished by the cutoff.
  3. Compute every company's inputs as of the drop's cutoff (Friday close).
  4. Write live/drops/<drop>/forecasts.csv, sorted, rounded, so the hash is stable.
Then run btb.live.freeze before the post_by deadline.
"""

from __future__ import annotations

import argparse

import pandas as pd

from btb.config import INTERIM, LOCKBOX_DIR, config_hash, features, load  # noqa: F401
from btb.eval import backtest  # noqa: F401
from btb.live.drops import drop_cfg, drop_dir  # noqa: F401
from btb.models import lgbm, shrinkage  # noqa: F401

FORECAST_COLS = ["drop_id", "ticker", "cik", "cutoff_date", "n_prior", *features(),
                 "pred_baseline", "pred_model", "pred_shrunk", "model_fp", "config_hash"]


def features_asof(events_all: pd.DataFrame, prices: pd.DataFrame, universe: pd.DataFrame,
                  cutoff: pd.Timestamp, k: int = 8) -> pd.DataFrame:
    """The 9 inputs for EVERY universe company as of `cutoff`, using the SAME rules as
    the backtest (that's leakage check L5: live code on an old week must match the
    backtest's inputs for that week).
      - history inputs: that company's events (by cik) with after_date <= cutoff,
        last k moves -> hist_median8, hist_mean8, hist_max8, hist_last, plus n_prior
      - price inputs: btb.features.price.price_features(prices, yahoo_ticker, cutoff)
    One row per company: ticker (yahoo_ticker), cik, n_prior, and the 9 inputs.
    If a company has no counted history, leave its hist_ columns NaN. If price_features
    raises Excluded (price gap), leave its price inputs NaN. Either way the company stays
    in the table, and make_forecasts puts it in not_forecast.csv.
    """
    raise NotImplementedError


def make_forecasts(drop_id: str, data_source: str = "real", inputs: pd.DataFrame | None = None) -> pd.DataFrame:
    """1. If data_source == "real" and results/lockbox/OPENED.json doesn't exist: SystemExit
       (live forecasts only come after the locked test is opened).
    2. Load history with backtest.load_events(data_source, "lockbox") (that's every event up to
       the end of the locked test, and it's also the events_all you pass to features_asof
       when inputs is None); train ONE LightGBM and
       ONE shrinkage diagnostic on rows with after_date <= the drop's cutoff.
    3. inputs: use the given frame (tests pass a slice of the events table with extra
       columns; just use the columns you need), or build it with features_asof from
       data/interim/prices.parquet and data/interim/universe.parquet.
    4. Forecast only companies with n_prior >= cfg event.min_prior_events and no missing input.
       Fill drop_id, cutoff_date (ISO date), pred_baseline (= hist_median8), pred_model,
       pred_shrunk, model_fp, config_hash (btb.config.config_hash(cfg)). Round floats
       (not cik or n_prior) to 4 decimals, keep FORECAST_COLS
       in that order, sort by ticker. (Stable formatting = stable SHA-256 fingerprint.)
    5. Write to drop_dir(drop_id, data_source): forecasts.csv (lineterminator="\n", no index),
       not_forecast.csv (ticker, cik, n_prior of skipped companies), model.pkl (lgbm.save).
    Return the forecasts frame.
    Done when tests/test_live.py passes.
    """
    raise NotImplementedError


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", required=True)
    ap.add_argument("--data", choices=["synthetic", "real"], default="real")
    a = ap.parse_args(argv)
    fc = make_forecasts(a.drop, a.data)
    print(f"{a.drop}: {len(fc)} companies forecast. Next: python -m btb.live.freeze --drop {a.drop}")


if __name__ == "__main__":
    main()
