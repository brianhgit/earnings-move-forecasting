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

import numpy as np
import pandas as pd

from btb.config import INTERIM, LOCKBOX_DIR, config_hash, features, load
from btb.dataset.windows import Excluded
from btb.eval import backtest  # noqa: F401
from btb.features import price
from btb.live.drops import drop_cfg, drop_dir
from btb.models import lgbm, shrinkage

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
    cutoff_ts = pd.Timestamp(cutoff)
    feature_cols = features()
    history_cols = {"hist_median8", "hist_mean8", "hist_max8", "hist_last"}
    # Only prior reports whose price reaction had finished by cutoff are available history.
    completed = events_all.loc[pd.to_datetime(events_all["after_date"]) <= cutoff_ts]
    rows = []

    for company in universe.itertuples(index=False):
        cik = int(company.cik)
        ticker = str(company.yahoo_ticker)
        all_prior = completed.loc[completed["cik"] == cik]
        prior = all_prior.sort_values(["report_date", "after_date"]).tail(k)
        moves = prior["move_adj"].astype(float)
        row = {
            "ticker": ticker,
            "cik": cik,
            "n_prior": int(len(all_prior)),
            "hist_median8": float(moves.median()) if not moves.empty else float("nan"),
            "hist_mean8": float(moves.mean()) if not moves.empty else float("nan"),
            "hist_max8": float(moves.max()) if not moves.empty else float("nan"),
            "hist_last": float(moves.iloc[-1]) if not moves.empty else float("nan"),
        }
        try:
            row.update(price.price_features(prices, ticker, cutoff_ts))
        except Excluded as exc:
            if exc.reason != "price_gap":
                raise
            # Keep the company visible; missing inputs will route it to not_forecast.csv.
            row.update({name: float("nan") for name in feature_cols if name not in history_cols})
        rows.append(row)

    return pd.DataFrame(rows, columns=["ticker", "cik", "n_prior", *feature_cols])


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
    cfg = load()
    if data_source == "real" and not (LOCKBOX_DIR / "OPENED.json").exists():
        raise SystemExit("The lockbox must be opened before creating live forecasts.")

    drop = drop_cfg(drop_id, cfg)
    cutoff = pd.Timestamp(drop["cutoff"])
    events_all = backtest.load_events(data_source, "lockbox")
    # Train only on outcomes already fully observed by this drop's feature cutoff.
    training = events_all.loc[pd.to_datetime(events_all["after_date"]) <= cutoff].copy()
    if training.empty:
        raise ValueError(f"No completed training events are available by {cutoff.date()}.")
    model = lgbm.fit(training, cfg)
    shrinkage_params = shrinkage.fit(training)

    if inputs is None:
        prices = pd.read_parquet(INTERIM / "prices.parquet")
        universe = pd.read_parquet(INTERIM / "universe.parquet")
        inputs = features_asof(events_all, prices, universe, cutoff)

    feature_cols = features(cfg)
    required = {"ticker", "cik", "n_prior", *feature_cols}
    missing = sorted(required - set(inputs.columns))
    if missing:
        raise ValueError(f"Forecast inputs are missing required columns: {missing}")

    work = inputs.loc[:, ["ticker", "cik", "n_prior", *feature_cols]].copy()
    eligible = work["n_prior"].ge(int(cfg["event"]["min_prior_events"]))
    eligible &= work[feature_cols].notna().all(axis=1)
    forecast_inputs = work.loc[eligible].copy()
    skipped = work.loc[~eligible, ["ticker", "cik", "n_prior"]].copy()

    # Keep calls module-qualified so test stand-ins can replace unimplemented models.
    model_predictions = lgbm.predict(model, forecast_inputs, cfg)
    shrunk_predictions = shrinkage.predict(shrinkage_params, forecast_inputs)
    output = forecast_inputs.copy()
    output.insert(0, "drop_id", drop_id)
    output.insert(3, "cutoff_date", cutoff.date().isoformat())
    output["pred_baseline"] = output["hist_median8"]
    output["pred_model"] = np.asarray(model_predictions, dtype=float)
    output["pred_shrunk"] = np.asarray(shrunk_predictions, dtype=float)
    output["model_fp"] = lgbm.fingerprint(model)
    output["config_hash"] = config_hash(cfg)
    # Fixed column order, sorting, and rounding make the posted file hash reproducible.
    output = output.loc[:, FORECAST_COLS].sort_values("ticker").reset_index(drop=True)

    float_cols = [
        name for name in output.columns
        if name not in {"drop_id", "ticker", "cik", "cutoff_date", "n_prior", "model_fp", "config_hash"}
    ]
    output[float_cols] = output[float_cols].round(4)

    out_dir = drop_dir(drop_id, data_source)
    output.to_csv(out_dir / "forecasts.csv", index=False, lineterminator="\n", float_format="%.4f")
    skipped.to_csv(out_dir / "not_forecast.csv", index=False, lineterminator="\n")
    lgbm.save(model, out_dir / "model.pkl")
    return output


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", required=True)
    ap.add_argument("--data", choices=["synthetic", "real"], default="real")
    a = ap.parse_args(argv)
    fc = make_forecasts(a.drop, a.data)
    print(f"{a.drop}: {len(fc)} companies forecast. Next: python -m btb.live.freeze --drop {a.drop}")


if __name__ == "__main__":
    main()
