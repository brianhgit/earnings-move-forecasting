"""Score a frozen drop against what actually happened.
(main() is plumbing and done; eligible() and score() are yours.)

    python -m btb.live.score --drop drop1        (make score DROP=drop1)

Eligibility rule (pre-registered, applied by code, no judgment calls):
  An event is scored if ALL hold:
    - its company has a row in the frozen forecasts.csv
    - its EDGAR acceptance time is AFTER the drop was frozen
    - its report_date falls inside the drop's window
    - it passes the same build rules as the backtest (timing plan, prices present)
  Anything else goes to unscored.csv with a reason. A void (late) drop scores nothing.

The live numbers are a sanity check, not the headline. ~150-250 reports in two weeks
of one market can't prove much, so the 95% range here resamples trading days and
is labeled "descriptive" everywhere it appears.
"""

from __future__ import annotations

import argparse
import json  # noqa: F401

import pandas as pd

from btb.eval import backtest, metrics, runs
from btb.live.drops import drop_cfg, drop_dir  # noqa: F401
from btb.live.freeze import verify
from btb.schema import validate


def eligible(drop_id: str, measured: pd.DataFrame, data_source: str = "real") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the eligibility rule above, by code only.

    measured: events built by the normal pipeline for the live window (event_id, ticker, cik,
    sector, accept_ts_et (Eastern, may be naive), report_date, move_adj, vix, ...).

    1. If freeze.verify(...) fails: SystemExit (the file changed after we posted its hash).
    2. If FREEZE.json says on_time is false: nothing is scored, every row unscored with
       reason "drop_void_late".
    3. Otherwise give each row a reason, checked in this order:
         "outside_window"          report_date not inside the drop's window
         "reported_before_freeze"  acceptance time <= frozen_utc. frozen_utc in FREEZE.json is
                                   an ISO string with an offset; accept_ts_et is Eastern and
                                   may be naive, so tz_localize("America/New_York") first,
                                   then tz_convert("UTC") and compare
         "no_forecast_row"         cik not in forecasts.csv
       Rows with no reason are scored: merge in pred_baseline, pred_model, pred_shrunk by cik.
    Return (scored, unscored) where unscored has a "reason" column.
    """
    try:
        frozen_ok = verify(drop_id, data_source)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{drop_id} has no valid freeze record; forecasts cannot be scored.") from exc
    if not frozen_ok:
        raise SystemExit(f"{drop_id} freeze verification failed; forecasts cannot be scored.")

    out_dir = drop_dir(drop_id, data_source)
    with (out_dir / "FREEZE.json").open() as file:
        freeze_record = json.load(file)
    forecasts = pd.read_csv(out_dir / "forecasts.csv")
    drop = drop_cfg(drop_id)
    window_start, window_end = (pd.Timestamp(value).date() for value in drop["window"])
    frozen_utc = pd.Timestamp(freeze_record["frozen_utc"])
    if frozen_utc.tzinfo is None:
        raise ValueError("FREEZE.json frozen_utc must include a timezone offset.")
    frozen_utc = frozen_utc.tz_convert("UTC")

    work = measured.copy().reset_index(drop=True)
    # A missed deadline voids the whole drop; do not selectively score its reports.
    if not freeze_record["on_time"]:
        unscored = work.copy()
        unscored["reason"] = "drop_void_late"
        return work.iloc[0:0].copy(), unscored

    report_dates = pd.to_datetime(work["report_date"]).dt.date
    reasons = pd.Series(pd.NA, index=work.index, dtype="string")
    outside = (report_dates < window_start) | (report_dates > window_end)
    reasons.loc[outside] = "outside_window"

    # Acceptance timestamps may be naive Eastern time or already timezone-aware.
    accept_utc = []
    for value in work["accept_ts_et"]:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            raise ValueError("accept_ts_et contains a missing timestamp.")
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("America/New_York")
        accept_utc.append(timestamp.tz_convert("UTC"))
    before_freeze = pd.Series(accept_utc, index=work.index) <= frozen_utc
    # Preserve the documented reason priority: window, posting time, then forecast coverage.
    reasons.loc[reasons.isna() & before_freeze] = "reported_before_freeze"

    forecast_ciks = pd.to_numeric(forecasts["cik"], errors="raise").astype("Int64")
    measured_ciks = pd.to_numeric(work["cik"], errors="raise").astype("Int64")
    has_forecast = measured_ciks.isin(forecast_ciks)
    reasons.loc[reasons.isna() & ~has_forecast] = "no_forecast_row"

    unscored = work.loc[reasons.notna()].copy()
    unscored["reason"] = reasons.loc[reasons.notna()].to_numpy()
    scored = work.loc[reasons.isna()].copy()
    if not scored.empty:
        # Join predictions by stable company identity, not ticker, which can change.
        forecast_values = forecasts[["cik", "pred_baseline", "pred_model", "pred_shrunk"]].copy()
        forecast_values["_cik_key"] = pd.to_numeric(forecast_values["cik"], errors="raise").astype("Int64")
        scored["_cik_key"] = measured_ciks.loc[reasons.isna()].to_numpy()
        scored = scored.merge(
            forecast_values.drop(columns="cik"),
            on="_cik_key",
            how="left",
            validate="many_to_one",
        ).drop(columns="_cik_key")
    return scored, unscored


def score(drop_id: str, measured: pd.DataFrame, data_source: str = "real") -> dict | None:
    """eligible() -> write unscored.csv -> if anything scored, build the "predictions" table
    (fold = drop_id, week_id = the report_date as YYYY-MM-DD so the bootstrap resamples
    trading days, not weeks), write scores.csv, run metrics.evaluate, add
    met["note"] saying the result is descriptive, and
    runs.write_run(name=f"live_{drop_id}", kind="live", data_source=data_source,
                   predictions=pred, metrics=met, data_hash=backtest.data_hash(scored),
                   note=met["note"]).
    Return the metrics dict, or None if nothing was scored.
    """
    scored, unscored = eligible(drop_id, measured, data_source)
    out_dir = drop_dir(drop_id, data_source)
    unscored.to_csv(out_dir / "unscored.csv", index=False, lineterminator="\n")
    if scored.empty:
        return None

    report_dates = pd.to_datetime(scored["report_date"])
    # Use report day as the cluster so the descriptive bootstrap resamples trading days.
    pred = pd.DataFrame({
        "event_id": scored["event_id"],
        "ticker": scored["ticker"],
        "sector": scored["sector"],
        "report_date": report_dates,
        "week_id": report_dates.dt.strftime("%Y-%m-%d"),
        "fold": drop_id,
        "y_true": scored["move_adj"],
        "pred_baseline": scored["pred_baseline"],
        "pred_model": scored["pred_model"],
        "pred_shrunk": scored["pred_shrunk"],
        "vix": scored["vix"],
    })
    validate(pred, "predictions")
    pred.to_csv(out_dir / "scores.csv", index=False, lineterminator="\n")
    met = metrics.evaluate(pred)
    met["note"] = "Descriptive live result; this short, single-market sample is a sanity check."
    runs.write_run(
        name=f"live_{drop_id}",
        kind="live",
        data_source=data_source,
        predictions=pred,
        metrics=met,
        data_hash=backtest.data_hash(scored),
        note=met["note"],
    )
    return met


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", required=True)
    ap.add_argument("--data", choices=["synthetic", "real"], default="real")
    a = ap.parse_args(argv)
    if a.data == "synthetic":
        from btb import synthetic

        ev = synthetic.events("demo")
        measured = ev[ev["split"] == "live"].reset_index(drop=True)
    else:
        from btb.config import PROCESSED

        measured = pd.read_parquet(PROCESSED / "events_live.parquet")
    met = score(a.drop, measured, a.data)
    if met:
        o = met["overall"]
        print(f"{a.drop}: {o['n_events']} scored. Baseline miss {o['mae_baseline']:.2f}, model {o['mae_model']:.2f}, "
              f"model closer {o['win_rate']:.0%} of the time")


if __name__ == "__main__":
    main()
