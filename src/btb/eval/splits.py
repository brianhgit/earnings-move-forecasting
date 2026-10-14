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

Test rows for a quarter: pool rows whose report_date falls inside that calendar
quarter. Skip quarters with no reports.

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
    raise NotImplementedError


def check_no_leak(events: pd.DataFrame, folds: list[Fold]) -> None:
    """Leakage check L3. Raise AssertionError if, in any fold:
      - an event is in both train and test, or
      - a training row's after_date is later than the earliest test cutoff_date.
    The backtest calls this on every run, not just in tests.
    """
    raise NotImplementedError
