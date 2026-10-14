"""dataset/build.py, on the fake raw inputs in fixtures/.

Uses stand-ins for the history and price inputs until those are implemented, so
these tests check the build logic itself (filtering, dedupe, windows, moves, splits).
"""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from btb import synthetic
from btb.dataset import build
from btb.schema import validate


@pytest.fixture(scope="module")
def raw():
    return synthetic.raw("tiny")


@pytest.fixture(scope="module")
def built(raw):
    from btb import standins as s

    u, f, p, _ = raw
    s.enable()
    try:
        return build.build_events(u, f, p, plan="A")
    finally:
        s.disable()


def test_outputs_match_the_contracts(built):
    events, excl = built
    validate(events, "events")
    validate(excl, "exclusions")
    assert events["event_id"].is_unique
    assert (events["report_date"] >= "2019-01-01").all()


def test_ignored_filings_never_appear(raw, built):
    *_, planted = raw
    events, excl = built
    for key in ("amendment", "not_earnings"):
        acc = planted[key].split("-", 1)[1]
        assert acc not in set(events["event_id"].str.split("-", n=1).str[1])
        assert acc not in set(excl["accession"])


@pytest.mark.parametrize("key,reason", [("duplicate", "duplicate_filing"),
                                        ("during_market_hours", "during_market_hours"),
                                        ("missing_price", "missing_price")])
def test_planted_exclusions(raw, built, key, reason):
    *_, planted = raw
    _, excl = built
    acc = planted[key].split("-", 1)[1]
    assert excl.loc[excl["accession"] == acc, "reason"].tolist() == [reason]


def test_weekend_filing_is_before_open_monday(raw, built):
    *_, planted = raw
    events, _ = built
    r = events.set_index("event_id").loc[planted["weekend"]]
    assert r["timing"] == "BMO"
    assert r["report_date"].date() == dt.date(2022, 10, 24)
    assert r["before_date"].date() == dt.date(2022, 10, 21)


def test_known_after_close_move_is_market_adjusted(raw, built):
    u, f, p, planted = raw
    events, _ = built
    r = events.set_index("event_id").loc[planted["known_amc"]]
    assert (r["before_date"].date(), r["after_date"].date()) == (dt.date(2024, 7, 23), dt.date(2024, 7, 24))
    assert r["cutoff_date"].date() == dt.date(2024, 7, 19)
    px = p.assign(date=pd.to_datetime(p["date"])).set_index(["ticker", "date"])["adj_close"]
    s = np.log(px[("SYN100", pd.Timestamp("2024-07-24"))] / px[("SYN100", pd.Timestamp("2024-07-23"))])
    m = np.log(px[("SPY", pd.Timestamp("2024-07-24"))] / px[("SPY", pd.Timestamp("2024-07-23"))])
    assert r["move_adj"] == pytest.approx(100 * abs(s - m))
    assert r["move_raw"] == pytest.approx(100 * abs(s))


def test_splits_by_date(built):
    events, _ = built
    for split, lo, hi in [("train_only", "2019-01-01", "2021-12-31"), ("dev", "2022-01-01", "2024-12-31"),
                          ("lockbox", "2025-01-01", "2026-09-30")]:
        part = events[events["split"] == split]
        assert len(part) and part["report_date"].between(lo, hi).all()


def test_plan_b_keeps_market_hours(raw, standins):
    u, f, p, planted = raw
    events, excl = build.build_events(u, f, p, plan="B")
    assert planted["during_market_hours"] in set(events["event_id"])
    assert (events["timing"] == "ANY").all()
