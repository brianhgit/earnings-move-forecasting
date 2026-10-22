"""NYSE trading calendar.

Build the calendar once at import time with
    xc.get_calendar("XNYS", start="2016-01-01")
(the default start is only ~20 years back, and we need 2016 on). Session labels come back
as pandas Timestamps; return plain datetime.date values. Close times come back in UTC, so
convert to America/New_York before comparing with 16:00 / 13:00.

Use exchange_calendars ("XNYS"), never pandas business days: BDay doesn't know
about holidays (Juneteenth, Good Friday) or 1 pm early closes (July 3, Black Friday,
Christmas Eve), and getting those wrong silently shifts a move by a day.

Done when tests/test_calendar_windows.py passes for these functions.
"""

from __future__ import annotations
from zoneinfo import ZoneInfo

import datetime as dt
import pandas as pd
import exchange_calendars as xc

XNYS = xc.get_calendar("XNYS", start="2016-01-01")
eastern = ZoneInfo("America/New_York")

def is_session(day: dt.date) -> bool:
    """True if NYSE is open that day."""
    return XNYS.is_session(pd.Timestamp(day))


def next_session(day: dt.date) -> dt.date:
    """First session strictly after `day`."""
    candidate = day + dt.timedelta(days=1)

    while not XNYS.is_session(pd.Timestamp(candidate)):
        candidate += dt.timedelta(days=1)

    return candidate


def prev_session(day: dt.date) -> dt.date:
    """Last session strictly before `day`."""
    candidate = day - dt.timedelta(days=1)

    while not XNYS.is_session(pd.Timestamp(candidate)):
        candidate -= dt.timedelta(days=1)

    return candidate


def session_on_or_after(day: dt.date) -> dt.date:
    return XNYS.date_to_session(pd.Timestamp(day), direction="next").date()


def session_on_or_before(day: dt.date) -> dt.date:
    return XNYS.date_to_session(pd.Timestamp(day), direction="previous").date()


def close_time_et(day: dt.date) -> dt.time:
    """16:00 normally, 13:00 on early-close days. day must be a session."""
    return XNYS.session_close(pd.Timestamp(day)).astimezone(eastern).time()


def sessions(start: dt.date, end: dt.date) -> pd.DatetimeIndex:
    return XNYS.sessions_in_range(start, end)
