"""Pick the rows for the timing hand check and write the sheets.

    python -m btb.audit_sample                 (after the full build)
    python -m btb.audit_sample --checkers 6    (default: 6 people)

Reads the events table and exclusions from data/processed/ (dev side only, never the
lockbox) and draws, with the locked seed (cfg project.seed):
  precision     60 kept reports            -> audit/precision_audit.csv
  recall        30 company-quarters        -> audit/recall_audit.csv
  market hours  10 "during_market_hours"   -> audit/market_hours_audit.csv
                exclusions

Only reports up to dev_end (2024) are drawn, so nobody looks at the locked test years.
Rows are split evenly across checkers c1, c2, ... (10 precision + 5 recall each with 6
checkers); the market-hours rows all go to c1. Names stay out of the repo: the c-number
to person list lives in Notion. Each checker also gets their own files in
audit/sheets/ (c1_precision.csv, c1_recall.csv, ...) to fill in; paste the answers back
into the combined files when they come back.

Columns match the *_template.csv files in audit/, so btb.eval.data_report reads them.
Refuses to overwrite existing audit files, so the draw happens once.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from btb.config import PROCESSED, ROOT, load

AUDIT = ROOT / "audit"
N_PRECISION, N_RECALL, N_MARKET_HOURS = 60, 30, 10

PRECISION_COLS = list(pd.read_csv(AUDIT / "precision_audit_template.csv", nrows=0).columns)
RECALL_COLS = list(pd.read_csv(AUDIT / "recall_audit_template.csv", nrows=0).columns)


def _quarter(ts) -> str:
    ts = pd.Timestamp(ts)
    return f"{ts.year}Q{ts.quarter}"


def draw(events: pd.DataFrame, exclusions: pd.DataFrame, universe: pd.DataFrame,
         seed: int, dev_end, checkers: int = 6) -> dict[str, pd.DataFrame]:
    """Return {"precision", "recall", "market_hours"} frames, already assigned to checkers."""
    rng = np.random.default_rng(seed)
    dev_end = pd.Timestamp(dev_end)
    ev = events[pd.to_datetime(events["report_date"]) <= dev_end].reset_index(drop=True)
    ex = exclusions[pd.to_datetime(exclusions["accept_ts_et"]) <= dev_end + pd.Timedelta(days=1)]

    # Precision: kept reports.
    pick = ev.iloc[rng.choice(len(ev), size=min(N_PRECISION, len(ev)), replace=False)]
    prec = pd.DataFrame({
        "event_id": pick["event_id"].values,
        "ticker": pick["ticker"].values,
        "accept_ts_et": pd.to_datetime(pick["accept_ts_et"]).dt.strftime("%Y-%m-%d %H:%M").values,
        "our_timing": pick["timing"].values,
        "our_before_date": pd.to_datetime(pick["before_date"]).dt.date.astype(str).values,
        "our_after_date": pd.to_datetime(pick["after_date"]).dt.date.astype(str).values,
    })

    # Recall: company-quarters from the first scored year through dev_end.
    cfg_start = pd.Timestamp(load()["dates"]["events_start"])
    quarters = pd.period_range(cfg_start, dev_end, freq="Q")
    ciks = np.sort(universe["cik"].astype(int).unique())
    n_pairs = len(ciks) * len(quarters)
    flat = rng.choice(n_pairs, size=min(N_RECALL, n_pairs), replace=False)
    rows = []
    ev_q = ev.assign(q=pd.to_datetime(ev["report_date"]).map(_quarter))
    tick = universe.drop_duplicates("cik").set_index("cik")["yahoo_ticker"]
    for i in flat:
        cik, q = int(ciks[i // len(quarters)]), str(quarters[i % len(quarters)])
        hit = ev_q[(ev_q["cik"] == cik) & (ev_q["q"] == q)]
        note = "" if hit.empty else "ours: " + "; ".join(
            f"{r.event_id} before={pd.Timestamp(r.before_date).date()} after={pd.Timestamp(r.after_date).date()}"
            for r in hit.itertuples())
        rows.append({"ticker": tick.get(cik, ""), "cik": cik, "fiscal_quarter_checked": q,
                     "our_event_id": "" if hit.empty else hit["event_id"].iloc[0], "notes": note})
    rec = pd.DataFrame(rows)

    # Market hours: exclusions we dropped for being filed while the market was open.
    mh_all = ex[ex["reason"] == "during_market_hours"].reset_index(drop=True)
    mh_pick = mh_all.iloc[rng.choice(len(mh_all), size=min(N_MARKET_HOURS, len(mh_all)), replace=False)] \
        if len(mh_all) else mh_all
    mh = pd.DataFrame({
        "cik": mh_pick["cik"].values,
        "ticker": mh_pick["ticker"].values,
        "accession": mh_pick["accession"].values,
        "accept_ts_et": pd.to_datetime(mh_pick["accept_ts_et"]).dt.strftime("%Y-%m-%d %H:%M").values,
        "press_release_url": "", "press_release_time_et": "",
        "released_before_open_yes_no": "", "notes": "",
    })

    def assign(df, per):
        df = df.copy()
        df.insert(0, "checker", [f"c{min(i // per, checkers - 1) + 1}" for i in range(len(df))])
        return df

    prec = assign(prec, max(1, N_PRECISION // checkers)).reindex(columns=PRECISION_COLS).fillna("")
    rec = assign(rec, max(1, N_RECALL // checkers)).reindex(columns=RECALL_COLS).fillna("")
    mh.insert(0, "checker", "c1")
    return {"precision": prec, "recall": rec, "market_hours": mh}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkers", type=int, default=6)
    a = ap.parse_args(argv)
    cfg = load()

    out = {"precision": AUDIT / "precision_audit.csv", "recall": AUDIT / "recall_audit.csv",
           "market_hours": AUDIT / "market_hours_audit.csv"}
    if any(p.exists() for p in out.values()):
        raise SystemExit("Audit files already exist. The draw happens once; delete them only if the draw was wrong.")

    from btb.config import INTERIM
    events = pd.read_parquet(PROCESSED / "events_dev.parquet")       # never the lockbox file
    exclusions = pd.read_csv(PROCESSED / "exclusions.csv")
    universe = pd.read_parquet(INTERIM / "universe.parquet")
    sheets = draw(events, exclusions, universe, int(cfg["project"]["seed"]), cfg["dates"]["dev_end"], a.checkers)

    for name, df in sheets.items():
        df.to_csv(out[name], index=False, lineterminator="\n")
    per = AUDIT / "sheets"
    per.mkdir(exist_ok=True)
    for name, df in sheets.items():
        for c, part in df.groupby("checker"):
            part.to_csv(per / f"{c}_{name}.csv", index=False, lineterminator="\n")
    print({k: len(v) for k, v in sheets.items()}, "->", AUDIT)


if __name__ == "__main__":
    main()
