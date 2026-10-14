"""Frozen fake data with the exact real schema (fixtures/*.parquet).

    from btb import synthetic
    ev = synthetic.events("test")      # the "events" table: what build.py will produce
    ms = synthetic.measured("test")    # every measured report before history inputs and filtering

Raw inputs for the table build: synthetic.raw("tiny") -> (universe, filings, prices, planted).

Three event sets: "demo" (150 fake companies, used by make demo and the app),
"test" (60 companies, used by tests), and "null" (60 companies where the inputs
carry no real information beyond history; used by leakage test L4).

Uses:
  - Build and test your piece before the real table exists.
  - CI never downloads anything; every test runs on these.
  - The app shows these (with a DEMO banner) until real results exist.

Tickers are SYN000, SYN001, ... Nothing here is real. Never quote a number from it.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def events(name: str = "demo") -> pd.DataFrame:
    return pd.read_parquet(FIXTURE_DIR / f"{name}_events.parquet")


def measured(name: str = "demo") -> pd.DataFrame:
    return pd.read_parquet(FIXTURE_DIR / f"{name}_measured.parquet")


def raw(name: str = "tiny"):
    """Fake RAW inputs for the table build: (universe, filings, prices, planted).

    20 fake companies plus SPY and ^VIX, 2016-07 to 2026-10, quarterly earnings filings.
    `planted` maps a few deliberately tricky cases to their event_id: an 8-K/A amendment,
    a non-earnings 8-K, a duplicate filing, a market-hours filing, a weekend filing, a
    company with no prices, and one known after-close report (2024-07-23).
    """
    import json

    return (pd.read_parquet(FIXTURE_DIR / f"{name}_universe.parquet"),
            pd.read_parquet(FIXTURE_DIR / f"{name}_filings.parquet"),
            pd.read_parquet(FIXTURE_DIR / f"{name}_prices.parquet"),
            json.loads((FIXTURE_DIR / f"{name}_planted.json").read_text()))
