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
  2. Per company (group by cik), walking back from the newest filing: filings fewer than 45
     days (cfg event.dedupe_days) before it share one report window. Inside a window, filings
     fewer than 3 days apart (cfg event.burst_days) form a burst, and a press release plus
     next-morning slides is one burst, so its FIRST filing stands for it. If the window has
     several bursts, first drop any burst filed after the company's next 10-Q or 10-K (the
     first one filed on or after the window's first filing, if it comes within 60 days of the
     window's last filing): an earnings release always comes before or with the quarterly
     report, so later Item 2.02 filings are side news (a subsidiary's results, a later update).
     Then keep the last remaining burst: side news before the report (delivery numbers,
     guidance) is older. Every other filing in the window -> exclusions, reason
     "duplicate_filing". Only filing dates are used, never prices. Measure with .days < 45,
     so exactly 45 days apart is NOT a duplicate. "Kept" means kept at this step, even if a
     later step excludes it. Periodic report dates come from the periodic argument
     (data/interim/periodic.parquet, written by btb.data.edgar); without it, the last burst.
  3. windows.assign_window(accept_ts_et, plan). Excluded -> exclusions with its reason.
  4. Adjusted closes for the stock (by yahoo_ticker) and SPY on before_date and after_date.
     Any missing -> "missing_price".
  5. ret_stock = ln(P_after / P_before), ret_spy = ln(SPY_after / SPY_before),
     move_adj = 100 * |ret_stock - ret_spy|, move_raw = 100 * |ret_stock|,
     cutoff_date = windows.cutoff_for(report_date), week_id = ISO week of report_date ("2024-W30").
  6. history.add_history_features on every report that survived steps 1 to 5 (2017 on),
     before the price_gap and date filters below, so pre-2019 reports still count as history.
  7. price.price_features(prices, yahoo_ticker, cutoff_date) for each of those reports
     (all years). Excluded("price_gap") -> exclusions. It returns a dict of the 5 price
     columns; add them as columns.
  8. in_index_at_cutoff from the membership table if given, else True (sensitivity column only).
     membership has columns ticker, start, end (end NaT = still in the index). A report is
     in the index if some row has the same ticker, start <= cutoff_date, and end is NaT or
     end >= cutoff_date. The tests pass membership=None.
  9. Keep report_date >= 2019-01-01. Earlier reports are dropped silently (they were only
     needed as history, so they are NOT exclusions). Of the rest, n_prior < 8 ->
     "insufficient_history".
     split: before 2022 "train_only", through 2024 "dev", through Sep 30 2026 "lockbox", after "live".
 10. Return (events, exclusions) passing validate(..., "events") and validate(..., "exclusions").
     event_id = f"{cik}-{accession}".
     Column types: match fixtures/test_events.parquet (dates as datetime64, n_prior int).
     Sort by report_date, then ticker.

Exclusions rows have columns cik, ticker, accession, accept_ts_et, reason, detail. detail is
free text for humans (e.g. "12 days after previous", "AAPL 2024-01-02..2024-01-03").

The fake raw inputs plant these cases (see fixtures/tiny_planted.json and tests/test_build.py):
an 8-K/A amendment, a filing that isn't earnings (no 2.02), a duplicate filing, a
market-hours filing, a weekend filing, a known after-close report with a hand-checked move,
and a company with no prices.
Call dependencies through their module (history.add_history_features(...),
price.price_features(...)), so the test's stand-ins can fill in until theirs is built.

Outputs of build():
  data/processed/events_dev.parquet       split in {train_only, dev}        <- everyone uses this
  data/processed/events_lockbox.parquet   split == lockbox                  <- only btb.eval.lockbox reads it
  data/processed/events_live.parquet      split == live                     <- live scoring
  data/processed/exclusions.csv           every dropped report and why
  results/build_report.json               counts, no prices (committed). Keys:
      kept_by_split            {"train_only": n, "dev": n, "lockbox": n, "live": n}
      kept_by_year             {"2019": n, ...}
      dropped_by_reason        {"duplicate_filing": n, ...}
      dropped_by_reason_year   [{"reason": ..., "year": ..., "n": ...}, ...]

Rule: never open events_lockbox.parquet in a notebook. Automated checks on it are fine;
looking at its moves is not.

Done when tests/test_build.py passes.
"""


from __future__ import annotations
 
import datetime as dt
import json
 
import numpy as np
import pandas as pd
 
from btb import schema
from btb.config import INTERIM, PROCESSED, RESULTS, load
from btb.features import price, history
from btb.dataset import windows
 
#constants                         
SPLITS = ("train_only", "dev", "lockbox", "live")
 
EXCLUSION_COLS = ["cik", "ticker", "accession", "accept_ts_et", "reason", "detail"]
 
 
#helpers
def _has_item_202(items) -> bool:
    """True if the filing's items include exactly "2.02" (string or list-like)."""
    if items is None:
        return False
    if isinstance(items, float) and pd.isna(items):
        return False
    if isinstance(items, str):
        parts = items.replace(";", ",").replace(" ", ",").split(",")
    else:
        parts = [str(i) for i in items]
    return "2.02" in [p.strip() for p in parts]
 
 
def _price_lookup(prices: pd.DataFrame) -> dict:
    """{(ticker, date): adj_close}. ADAPT if the real prices table is shaped differently."""
    days = pd.to_datetime(prices["date"]).dt.date
    return dict(zip(zip(prices["ticker"], days), prices["adj_close"]))
 
 
def _get_price(lookup: dict, ticker: str, day: dt.date):
    v = lookup.get((ticker, day))
    return None if v is None or pd.isna(v) else float(v)
 
 
def _week_id(day: dt.date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"
 
 
def _in_index(membership: pd.DataFrame, ticker: str, cutoff: pd.Timestamp) -> bool:
    m = membership[membership["ticker"] == ticker]
    ok = (m["start"] <= cutoff) & (m["end"].isna() | (m["end"] >= cutoff))
    return bool(ok.any())
 
 
def _bursts(window: list[dict], burst_days: int) -> list[list[dict]]:
    """Split one window (oldest -> newest) into bursts, oldest first. Walking back from the
    newest filing, filings fewer than burst_days before a burst's newest filing join it."""
    bursts: list[list[dict]] = []
    i = len(window) - 1
    while i >= 0:
        anchor = window[i]["accept_ts_et"]
        j = i
        while j - 1 >= 0 and (anchor - window[j - 1]["accept_ts_et"]).days < burst_days:
            j -= 1
        bursts.insert(0, window[j:i + 1])
        i = j - 1
    return bursts


def _split_for(day: pd.Timestamp, cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else load()
    dates = cfg["dates"]

    day = pd.Timestamp(day)

    if day < pd.Timestamp(dates["dev_folds_start"]):
        return "train_only"
    if day <= pd.Timestamp(dates["dev_end"]):
        return "dev"
    if day <= pd.Timestamp(dates["lockbox_end"]):
        return "lockbox"
    return "live"
 
 
#logic
def build_events(
    universe: pd.DataFrame,
    filings: pd.DataFrame,
    prices: pd.DataFrame,
    membership: pd.DataFrame | None = None,
    plan: str | None = None,
    cfg: dict | None = None,
    periodic: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Steps 1 to 10 above. plan defaults to cfg["event"]["timing_plan"].
    Returns (events, exclusions). Exclusion columns: cik, ticker, accession, accept_ts_et, reason, detail."""
    cfg = cfg if cfg is not None else load()
    plan = plan if plan is not None else cfg["event"]["timing_plan"]
    dedupe_days = cfg["event"]["dedupe_days"]
    burst_days = cfg["event"]["burst_days"]
    min_prior = cfg["event"]["min_prior_events"]
    exclusions: list[dict] = []
 
    def exclude(row, reason: str, detail: str = "") -> None:
        exclusions.append(
            {
                "cik": row["cik"],
                "ticker": row["ticker"],
                "accession": row["accession"],
                "accept_ts_et": row["accept_ts_et"],
                "reason": reason,
                "detail": detail,
            }
        )
 
    # STEP 1: 8-K (not 8-K/A) with item 2.02, CIK in the universe. Else: ignored silently.
    uni = universe[["cik", "ticker", "yahoo_ticker", "sector"]].drop_duplicates("cik")
    f = filings[filings["form"] == "8-K"]
    f = f[f["items"].map(_has_item_202)]
    f = f.drop(columns=["ticker", "yahoo_ticker", "sector"], errors="ignore")
    f = f.merge(uni, on="cik", how="inner")
    f["accept_ts_et"] = pd.to_datetime(f["accept_ts_et"])
    f = f.sort_values(["cik", "accept_ts_et", "accession"], kind="stable")
 
    # STEP 2: duplicates (rule in the module docstring). Periodic reports (10-Q, 10-K) mark
    # where a quarter's earnings news ends.
    report_dates: dict[int, list] = {}
    if periodic is not None and len(periodic):
        pr = periodic.assign(filing_date=pd.to_datetime(periodic["filing_date"]))
        report_dates = {int(c): sorted(g["filing_date"]) for c, g in pr.groupby("cik")}
    reach = pd.Timedelta(days=60)
    kept_rows: list[dict] = []
    for cik, grp in f.groupby("cik", sort=False):
        rows = grp.to_dict("records")              # oldest -> newest
        dates = report_dates.get(int(cik), [])
        i = len(rows) - 1
        while i >= 0:
            newest = rows[i]["accept_ts_et"]
            j = i
            while j - 1 >= 0 and (newest - rows[j - 1]["accept_ts_et"]).days < dedupe_days:
                j -= 1                             # rows[j..i] share one window
            window = rows[j:i + 1]
            bursts = _bursts(window, burst_days)
            if len(bursts) > 1 and dates:
                first_day = window[0]["accept_ts_et"].normalize()
                last_day = window[-1]["accept_ts_et"].normalize()
                report = next((d for d in dates if first_day <= d <= last_day + reach), None)
                if report is not None:
                    before = [b for b in bursts if b[0]["accept_ts_et"].normalize() <= report]
                    bursts = before or bursts
            keep = bursts[-1][0]                   # first filing of the last remaining burst
            for r in window:
                if r is keep:
                    continue
                if r["accept_ts_et"] < keep["accept_ts_et"]:
                    days = (keep["accept_ts_et"] - r["accept_ts_et"]).days
                    exclude(r, "duplicate_filing", f"{days} days before the kept filing")
                else:
                    days = (r["accept_ts_et"] - keep["accept_ts_et"]).days
                    exclude(r, "duplicate_filing", f"{days} days after the kept filing")
            kept_rows.append(keep)                 # kept here, even if a later step drops it
            i = j - 1
    kept_rows.sort(key=lambda r: (r["cik"], r["accept_ts_et"]))
 
    # STEPS 3-5: window, prices, returns
    lookup = _price_lookup(prices)
    events_rows: list[dict] = []
    for row in kept_rows:
        # STEP 3
        try:
            w = windows.assign_window(row["accept_ts_et"], plan)
        except windows.Excluded as e:
            exclude(row, e.reason, e.detail)
            continue
 
        # STEP 4
        t = row["yahoo_ticker"]
        p_b = _get_price(lookup, t, w.before_date)
        p_a = _get_price(lookup, t, w.after_date)
        s_b = _get_price(lookup, "SPY", w.before_date)
        s_a = _get_price(lookup, "SPY", w.after_date)
        if None in (p_b, p_a, s_b, s_a):
            exclude(row, "missing_price", f"{t} {w.before_date}..{w.after_date}")
            continue
 
        # STEP 5
        ret_stock = float(np.log(p_a / p_b))
        ret_spy = float(np.log(s_a / s_b))
        events_rows.append(
            {
                **row,
                "timing": w.timing,
                "report_date": w.report_date,
                "before_date": w.before_date,
                "after_date": w.after_date,
                "ret_stock": ret_stock,
                "ret_spy": ret_spy,
                "move_adj": 100 * abs(ret_stock - ret_spy),
                "move_raw": 100 * abs(ret_stock),
                "cutoff_date": windows.cutoff_for(w.report_date),
                "week_id": _week_id(w.report_date),
            }
        )
 
    df = pd.DataFrame(events_rows)
    if not df.empty:
        for c in ("report_date", "before_date", "after_date", "cutoff_date"):
            df[c] = pd.to_datetime(df[c])
 
        # STEP 6: history features on every survivor (2017 on), before any date filter.
        df = history.add_history_features(df)
 
        # STEP 7: price features, all years. Excluded("price_gap") -> exclusions.
        # Split prices by ticker once (plus ^VIX), so each call scans ~2,500 rows, not ~1.3M.
        prices_dt = prices.assign(date=pd.to_datetime(prices["date"]))
        vix = prices_dt[prices_dt["ticker"] == "^VIX"]
        by_ticker = {t: pd.concat([g, vix]) for t, g in prices_dt.groupby("ticker", sort=False)}
        keep_idx, feats = [], []
        for idx, row in df.iterrows():
            try:
                feats.append(
                    price.price_features(
                        by_ticker.get(row["yahoo_ticker"], vix),
                        row["yahoo_ticker"],
                        row["cutoff_date"].date(),
                    )
                )
                keep_idx.append(idx)
            except windows.Excluded as e:
                exclude(row, e.reason, e.detail)
        df = df.loc[keep_idx].copy()
        if not df.empty:
            df = df.join(pd.DataFrame(feats, index=keep_idx))
 
    if not df.empty:
        # STEP 8: in_index_at_cutoff (sensitivity column only)
        if membership is None:
            df["in_index_at_cutoff"] = True
        else:
            mem = membership.copy()
            mem["start"] = pd.to_datetime(mem["start"])
            mem["end"] = pd.to_datetime(mem["end"])
            df["in_index_at_cutoff"] = [
                _in_index(mem, tk, co) for tk, co in zip(df["ticker"], df["cutoff_date"])
            ]
 
        # STEP 9: silent drop before 2019, then insufficient history, then split.
        df = df[df["report_date"] >= cfg["dates"]["events_start"]].copy()
        short = df["n_prior"] < min_prior
        for _, row in df[short].iterrows():
            exclude(row, "insufficient_history", f"n_prior={int(row['n_prior'])}")
        df = df[~short].copy()
        df["split"] = df["report_date"].map(lambda d: _split_for(d, cfg))
 
        # STEP 10: final columns, types, order
        df["event_id"] = df["cik"].astype(str) + "-" + df["accession"].astype(str)
        df["n_prior"] = df["n_prior"].astype(int)
        df = df.sort_values(["report_date", "ticker"], kind="stable").reset_index(drop=True)
 
    # Keep exactly the schema's columns, in the schema's order (drops accession, form,
    # items, yahoo_ticker; also gives an empty frame the right columns).
    df = df.reindex(columns=list(schema.TABLES["events"]))
    exclusions_df = pd.DataFrame(exclusions, columns=EXCLUSION_COLS)
    schema.validate(df, "events")
    schema.validate(exclusions_df, "exclusions")
    return df, exclusions_df
 
 
# ---------------------------------------------------------------- report + files
def _build_report(events: pd.DataFrame, exclusions: pd.DataFrame) -> dict:
    kept_by_split = {s: 0 for s in SPLITS}
    kept_by_year: dict = {}
    if not events.empty:
        for s, n in events["split"].value_counts().items():
            kept_by_split[s] = int(n)
        for y, n in events["report_date"].dt.year.value_counts().sort_index().items():
            kept_by_year[str(int(y))] = int(n)
 
    dropped_by_reason: dict = {}
    by_reason_year: list = []
    if not exclusions.empty:
        for r, n in exclusions["reason"].value_counts().items():
            dropped_by_reason[r] = int(n)
        years = pd.to_datetime(exclusions["accept_ts_et"], utc=True).dt.year
        g = exclusions.assign(year=years).groupby(["reason", "year"]).size()
        by_reason_year = [
            {"reason": r, "year": int(y), "n": int(n)} for (r, y), n in g.items()
        ]
 
    return {
        "kept_by_split": kept_by_split,
        "kept_by_year": kept_by_year,
        "dropped_by_reason": dropped_by_reason,
        "dropped_by_reason_year": by_reason_year,
    }
 
 
def build() -> None:
    """Read data/interim/{universe,filings,prices}.parquet, call build_events, write the outputs listed above."""

    cfg = load()
    universe = pd.read_parquet(INTERIM / "universe.parquet")
    filings = pd.read_parquet(INTERIM / "filings.parquet")
    prices = pd.read_parquet(INTERIM / "prices.parquet")
    mem_path = INTERIM / "membership.parquet"
    membership = pd.read_parquet(mem_path) if mem_path.exists() else None
    per_path = INTERIM / "periodic.parquet"
    if not per_path.exists():
        raise FileNotFoundError(f"{per_path} is missing; run python -m btb.data.edgar --accept-times <snapshot>")
    periodic = pd.read_parquet(per_path)

    events, exclusions = build_events(universe, filings, prices, membership, cfg=cfg, periodic=periodic)
 
    PROCESSED.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    events[events["split"].isin(["train_only", "dev"])].to_parquet(
        PROCESSED / "events_dev.parquet", index=False
    )
    events[events["split"] == "lockbox"].to_parquet(
        PROCESSED / "events_lockbox.parquet", index=False
    )
    events[events["split"] == "live"].to_parquet(
        PROCESSED / "events_live.parquet", index=False
    )
    exclusions.to_csv(PROCESSED / "exclusions.csv", index=False)
    (RESULTS / "build_report.json").write_text(
        json.dumps(_build_report(events, exclusions), indent=2), newline="\n"
    )
    print(f"kept {len(events)} reports, dropped {len(exclusions)}")
 
if __name__ == "__main__":
    build()
