"""Column contracts between the pipeline stages.

Each stage's output has to pass `validate(df, "<table>")` before it gets merged.
If you need a new column, add it here in your PR so everyone sees the change.
"""

from __future__ import annotations

import pandas as pd

from btb.config import features

TABLES: dict[str, dict[str, str]] = {
    # src/btb/data/universe.py
    "universe": {
        "ticker": "str",          # Wikipedia ticker, e.g. BRK.B
        "yahoo_ticker": "str",    # e.g. BRK-B
        "cik": "int",
        "name": "str",
        "sector": "str",          # GICS sector from the snapshot
    },
    # src/btb/data/edgar.py
    "filings": {
        "cik": "int",
        "accession": "str",
        "form": "str",            # 8-K only (8-K/A dropped upstream)
        "items": "str",           # e.g. "2.02,9.01"
        "accept_ts_et": "datetime",  # EDGAR acceptanceDateTime converted to America/New_York
    },
    # src/btb/data/prices.py. Long format, one row per ticker per day.
    "prices": {
        "date": "date",
        "ticker": "str",          # yahoo ticker, plus SPY and ^VIX
        "adj_close": "float",     # split and dividend adjusted
        "close": "float",         # raw close, only used for the split sanity check
        "volume": "float",
    },
    # src/btb/dataset/build.py. The modeling table.
    "events": {
        "event_id": "str",        # f"{cik}-{accession}"
        "ticker": "str",
        "cik": "int",
        "sector": "str",
        "accept_ts_et": "datetime",
        "timing": "str",          # BMO, AMC (plan A) or ANY (plan B)
        "report_date": "date",    # trading session the news first hits
        "before_date": "date",    # session whose close is P_before
        "after_date": "date",     # session whose close is P_after
        "cutoff_date": "date",    # last session on or before the Friday before report week
        "week_id": "str",         # ISO week of report_date, e.g. 2026-W43 (bootstrap cluster)
        "ret_stock": "float",     # ln(P_after / P_before)
        "ret_spy": "float",       # ln(SPY_after / SPY_before)
        "move_adj": "float",      # TARGET: 100 * |ret_stock - ret_spy|
        "move_raw": "float",      # 100 * |ret_stock|, reported as a side number only
        "n_prior": "int",         # completed prior events known at cutoff
        "in_index_at_cutoff": "bool",  # point-in-time membership (sensitivity analysis)
        "split": "str",           # train_only (2019-2021), dev (2022-2024), lockbox (2025-Sep 2026), live
        **{f: "float" for f in features()},
    },
    # Every report that got dropped, and why. Built alongside events.
    "exclusions": {
        "cik": "int",
        "ticker": "str",
        "accession": "str",
        "accept_ts_et": "datetime",
        "reason": "str",          # one of EXCLUSION_REASONS
        "detail": "str",
    },
    # results/runs/<run_id>/predictions.parquet, written by btb.eval.runs
    "predictions": {
        "event_id": "str",
        "ticker": "str",
        "sector": "str",
        "report_date": "date",
        "week_id": "str",
        "fold": "str",            # e.g. 2023Q2, or a live drop id
        "y_true": "float",
        "pred_baseline": "float",
        "pred_model": "float",
        "vix": "float",
    },
}

EXCLUSION_REASONS = {
    "during_market_hours",   # plan A only
    "duplicate_filing",      # second 2.02 within dedupe_days
    "insufficient_history",  # fewer than min_prior_events
    "missing_price",         # no close on before/after date
    "price_gap",             # missing sessions around the event
    "suspicious_jump",       # >40% non-event daily move with no split
    "not_in_universe",       # CIK not in the snapshot
    "duplicate_share_class",
    "outside_date_range",
}


def missing_columns(df: pd.DataFrame, table: str) -> list[str]:
    return [c for c in TABLES[table] if c not in df.columns]


def validate(df: pd.DataFrame, table: str) -> None:
    """Raise ValueError with every problem found, not just the first."""
    problems: list[str] = []
    miss = missing_columns(df, table)
    if miss:
        problems.append(f"{table}: missing columns {miss}")

    if table == "events" and not miss:
        if df["event_id"].duplicated().any():
            problems.append("events: duplicate event_id")
        if (df["before_date"] >= df["after_date"]).any():
            problems.append("events: before_date must be earlier than after_date")
        if (df["cutoff_date"] > df["before_date"]).any():
            problems.append("events: cutoff_date after before_date (feature window leaks into target)")
        if (df["move_adj"] < 0).any():
            problems.append("events: negative move_adj")
        scored = df[df["split"] != "train_only"]
        if scored[features()].isna().any().any():
            problems.append("events: missing feature values on scored rows")
        if (df["n_prior"] < 0).any():
            problems.append("events: negative n_prior")

    if table == "predictions" and not miss:
        if df[["y_true", "pred_baseline", "pred_model"]].isna().any().any():
            problems.append("predictions: NaN in y_true or predictions (both predictors must cover the same rows)")
        if df["event_id"].duplicated().any():
            problems.append("predictions: duplicate event_id")

    if table == "exclusions" and not miss:
        bad = set(df["reason"]) - EXCLUSION_REASONS
        if bad:
            problems.append(f"exclusions: unknown reasons {sorted(bad)}")

    if problems:
        raise ValueError("\n".join(problems))
