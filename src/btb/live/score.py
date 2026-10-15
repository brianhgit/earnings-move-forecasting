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

from btb.eval import backtest, metrics, runs  # noqa: F401
from btb.live.drops import drop_cfg, drop_dir  # noqa: F401
from btb.live.freeze import verify  # noqa: F401


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
    raise NotImplementedError


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
    raise NotImplementedError


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", required=True)
    ap.add_argument("--data", choices=["synthetic", "real"], default="real")
    a = ap.parse_args(argv)
    from btb.config import PROCESSED

    measured = pd.read_parquet(PROCESSED / "events_live.parquet")
    met = score(a.drop, measured, a.data)
    if met:
        o = met["overall"]
        print(f"{a.drop}: {o['n_events']} scored. Baseline miss {o['mae_baseline']:.2f}, model {o['mae_model']:.2f}, "
              f"model closer {o['win_rate']:.0%} of the time")


if __name__ == "__main__":
    main()
