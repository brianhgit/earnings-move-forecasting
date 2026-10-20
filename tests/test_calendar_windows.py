"""Contract tests for btb.dataset.calendar and btb.dataset.windows 

These skip until the functions exist, then they must all pass. Every date here
was checked by hand against the NYSE calendar. Add cases, don't edit these.
"""

import datetime as dt

import pytest

from btb.dataset import calendar as cal
from btb.dataset import windows as W
from conftest import call_or_skip

D = dt.date
T = dt.datetime


# ---- calendar ----
@pytest.mark.contract
@pytest.mark.parametrize("day,expected", [
    (D(2024, 7, 4), False),   # Independence Day
    (D(2024, 3, 29), False),  # Good Friday
    (D(2024, 6, 19), False),  # Juneteenth
    (D(2024, 7, 27), False),  # Saturday
    (D(2024, 7, 23), True),
])
def test_is_session(day, expected):
    assert call_or_skip(cal.is_session, day) is expected


@pytest.mark.contract
def test_early_close():
    assert call_or_skip(cal.close_time_et, D(2024, 7, 3)) == dt.time(13, 0)
    assert call_or_skip(cal.close_time_et, D(2024, 7, 2)) == dt.time(16, 0)


@pytest.mark.contract
def test_next_prev_skip_holidays():
    assert call_or_skip(cal.next_session, D(2024, 7, 3)) == D(2024, 7, 5)
    assert call_or_skip(cal.prev_session, D(2024, 4, 1)) == D(2024, 3, 28)


# ---- windows, plan A ----
CASES_A = [
    # accept time ET,                 timing, report,            before,            after
    (T(2024, 7, 23, 16, 5),  "AMC", D(2024, 7, 23), D(2024, 7, 23), D(2024, 7, 24)),
    (T(2024, 7, 23, 7, 0),   "BMO", D(2024, 7, 23), D(2024, 7, 22), D(2024, 7, 23)),
    (T(2024, 7, 23, 16, 0),  "AMC", D(2024, 7, 23), D(2024, 7, 23), D(2024, 7, 24)),  # exactly at close
    (T(2024, 7, 27, 10, 0),  "BMO", D(2024, 7, 29), D(2024, 7, 26), D(2024, 7, 29)),  # Saturday
    (T(2024, 7, 4, 8, 0),    "BMO", D(2024, 7, 5),  D(2024, 7, 3),  D(2024, 7, 5)),   # holiday
    (T(2024, 7, 3, 13, 30),  "AMC", D(2024, 7, 3),  D(2024, 7, 3),  D(2024, 7, 5)),   # after a 1pm early close
    (T(2024, 7, 26, 16, 10), "AMC", D(2024, 7, 26), D(2024, 7, 26), D(2024, 7, 29)),  # Friday after close
    (T(2024, 7, 22, 23, 50), "AMC", D(2024, 7, 22), D(2024, 7, 22), D(2024, 7, 23)),  # late night
]


@pytest.mark.contract
@pytest.mark.parametrize("ts,timing,report,before,after", CASES_A)
def test_plan_a(ts, timing, report, before, after):
    w = call_or_skip(W.assign_window, ts, "A")
    assert (w.timing, w.report_date, w.before_date, w.after_date) == (timing, report, before, after)


@pytest.mark.contract
@pytest.mark.parametrize("ts", [T(2024, 7, 23, 9, 30), T(2024, 7, 23, 11, 0), T(2024, 7, 23, 15, 59)])
def test_plan_a_excludes_market_hours(ts):
    try:
        W.assign_window(ts, "A")
    except NotImplementedError:
        pytest.skip("not implemented yet")
    except W.Excluded as e:
        assert e.reason == "during_market_hours"
    else:
        pytest.fail("market-hours filing should be excluded under plan A")


@pytest.mark.contract
def test_plan_b_two_day_window():
    w = call_or_skip(W.assign_window, T(2024, 7, 23, 11, 0), "B")
    assert (w.before_date, w.after_date) == (D(2024, 7, 22), D(2024, 7, 24))


@pytest.mark.contract
@pytest.mark.parametrize("report,cutoff", [
    (D(2024, 7, 23), D(2024, 7, 19)),
    (D(2024, 7, 29), D(2024, 7, 26)),  # Monday report: cutoff is the Friday just before
    (D(2024, 4, 2), D(2024, 3, 28)),   # Good Friday closed -> Thursday
])
def test_cutoff(report, cutoff):
    assert call_or_skip(W.cutoff_for, report) == cutoff
