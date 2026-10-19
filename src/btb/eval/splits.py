"""Walk-forward folds: train on the past, test on the next quarter, repeat.

The one rule that matters: a training row is allowed only if its move had fully
played out (after_date) by the EARLIEST cutoff_date among the test quarter's
reports. That is exactly what we could have known if we were forecasting that
quarter live.

mode="dev"
  test quarters: 2022Q1 .. 2024Q4 (cfg dates.dev_folds_start .. dates.dev_end), 12 folds
  training pool: rows with split in {train_only, dev}
  if ANY row in `events` has split == "lockbox": raise RuntimeError (dev code must
  never be handed the locked test set)
mode="lockbox"
  test quarters: 2025Q1 .. 2026Q3 (dates.lockbox_start .. dates.lockbox_end)
  training pool: train_only, dev and lockbox rows (earlier lockbox quarters are
  allowed by the time rule, the same way they'd be known live)

Rows with split == "live" are never in the pool, in either mode.

Test rows for a quarter: pool rows whose report_date falls inside that calendar
quarter (q_start = pd.date_range(start, end, freq="QS"), q_end = q_start +
pd.offsets.QuarterEnd(0)). Skip quarters with no reports.
Training rows: pool rows with after_date <= train_until, where train_until = the
earliest cutoff_date among that quarter's test rows. Nothing else is needed: the time
rule already keeps the test quarter itself out of training.
Any other mode -> raise ValueError.
Return Fold objects in date order; train_idx and test_idx are index LABELS of `events`
(use events.loc[...] with them, not .iloc).

Done when tests/test_leakage.py::test_L3_* pass.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from btb.config import load  # noqa: F401


@dataclass
class Fold:
    label: str                  # e.g. "2023Q2" (use quarter_label)
    train_idx: pd.Index         # index labels of training rows in `events`
    test_idx: pd.Index          # index labels of test rows
    train_until: pd.Timestamp   # the earliest test cutoff_date (latest after_date allowed)


def quarter_label(d: pd.Timestamp) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def walk_forward(events: pd.DataFrame, mode: str = "dev", cfg: dict | None = None) -> list[Fold]:
    cfg = cfg if cfg is not None else load()
    dates = cfg["dates"]

    if mode == "dev":
        if (events["split"] == "lockbox").any():
            raise RuntimeError("dev mode was handed lockbox rows")
        start, end = dates["dev_folds_start"], dates["dev_end"]
        pool_splits = ["train_only", "dev"]
    elif mode == "lockbox":
        start, end = dates["lockbox_start"], dates["lockbox_end"]
        pool_splits = ["train_only", "dev", "lockbox"]
    else:
        raise ValueError(f"unknown mode: {mode}")

    pool = events[events["split"].isin(pool_splits)]

    folds = []
    for q_start in pd.date_range(start, end, freq="QS"):
        q_end = q_start + pd.offsets.QuarterEnd(0)

        test = pool[(pool["report_date"] >= q_start) & (pool["report_date"] <= q_end)]
        if len(test) == 0:
            continue

        train_until = test["cutoff_date"].min()
        train = pool[pool["after_date"] <= train_until]

        folds.append(Fold(
            label=quarter_label(q_start),
            train_idx=train.index,
            test_idx=test.index,
            train_until=train_until,
        ))
    return folds


def check_no_leak(events: pd.DataFrame, folds: list[Fold]) -> None:
    """Leakage check L3. Raise AssertionError if, in any fold:
      - an index label is in both train_idx and test_idx, or
      - a training row's after_date is later than the earliest test cutoff_date.
    Skip the date check for a fold with no test rows. Return None if everything is fine.
    backtest.main() calls this on every run (you don't need to call it in predict_folds).
    """
    for f in folds:
        overlap = f.train_idx.intersection(f.test_idx)
        assert len(overlap) == 0, f"{f.label}: {len(overlap)} rows in both train and test"

        if len(f.test_idx) == 0:
            continue

        earliest_cutoff = events.loc[f.test_idx, "cutoff_date"].min()
        latest_train_after = events.loc[f.train_idx, "after_date"].max()
        ok = latest_train_after <= earliest_cutoff
        assert ok, f"{f.label}: training row's move ends after the test cutoff"
