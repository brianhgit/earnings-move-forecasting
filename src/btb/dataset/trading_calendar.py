from __future__ import annotations
from zoneinfo import ZoneInfo

import datetime as dt
import pandas as pd
import exchange_calendars as xc

XNYS = xc.get_calendar("XNYS", start="2016-01-01")
eastern = ZoneInfo("America/New_York")

def is_session(day: dt.date) -> bool:
    return XNYS.is_session(pd.Timestamp(day))


def next_session(day: dt.date) -> dt.date:
    candidate = day + dt.timedelta(days=1)

    while not XNYS.is_session(pd.Timestamp(candidate)):
        candidate += dt.timedelta(days=1)

    return candidate


def prev_session(day: dt.date) -> dt.date:
    candidate = day - dt.timedelta(days=1)

    while not XNYS.is_session(pd.Timestamp(candidate)):
        candidate -= dt.timedelta(days=1)

    return candidate


def session_on_or_after(day: dt.date) -> dt.date:
    return XNYS.date_to_session(pd.Timestamp(day), direction="next").date()


def session_on_or_before(day: dt.date) -> dt.date:
    return XNYS.date_to_session(pd.Timestamp(day), direction="previous").date()


def close_time_et(day: dt.date) -> dt.time:
    return XNYS.session_close(pd.Timestamp(day)).astimezone(eastern).time()


def sessions(start: dt.date, end: dt.date) -> pd.DatetimeIndex:
    return XNYS.sessions_in_range(start, end)
