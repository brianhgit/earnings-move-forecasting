"""Turn an EDGAR acceptance time into the two closes we measure.

This file decides what "the earnings move" means, so it gets the most tests.

Plan A (default):
  BMO  accepted before 09:30 ET on a session      -> before = previous session, after = that session
  AMC  accepted at/after the close on a session   -> before = that session,     after = next session
       (the close is 13:00 on early-close days)
  non-session day (weekend/holiday), any time      -> treat as BMO of the next session
  DMH  accepted 09:30 <= t < close on a session   -> excluded, reason "during_market_hours"

Plan B (only if the timing hand check fails plan A):
  before = session before report_date, after = session after report_date (two days,
  catches the reaction whichever side it fell on, including DMH). This CHANGES what
  we measure (a 2-day move), so it is reported as a different estimand. See
  docs/PREREGISTRATION.md section 2. A weekend or holiday filing under plan B uses the
  next session as report_date, then the sessions before and after it.

report_date = the session the announcement belongs to (acceptance day, or the next
session if accepted on a non-session day). It decides which week (and which live
drop) the event belongs to.

cutoff_date = last session on or before the Friday before report_date's Mon-Sun week.
Every feature must use data from cutoff_date or earlier.
"""

from __future__ import annotations

import datetime as dt

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from btb.dataset.trading_calendar import (
    is_session,
    next_session,
    prev_session,
    session_on_or_before,
    close_time_et,
)

eastern = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Window:
    timing: str          # BMO, AMC, or ANY (plan B)
    report_date: dt.date
    before_date: dt.date
    after_date: dt.date


class Excluded(Exception):
    """Raise with a reason from btb.schema.EXCLUSION_REASONS."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason)
        self.reason, self.detail = reason, detail


def assign_window(accept_ts_et: dt.datetime, plan: str = "A") -> Window:
    if plan not in ("A", "B"):
        raise ValueError(f"Unknown plan: {plan!r}")

    if accept_ts_et.tzinfo is None:
        local = accept_ts_et.replace(tzinfo=eastern)
    else:
        local = accept_ts_et.astimezone(eastern)

    acceptance_date = local.date()

    if is_session(acceptance_date):
        report_date = acceptance_date
        non_session = False
    else:
        report_date = next_session(acceptance_date)
        non_session = True

    if plan == "B":
        return Window(
            timing="ANY",
            report_date=report_date,
            before_date=prev_session(report_date),
            after_date=next_session(report_date),
        )

    if non_session:
        return Window(
            timing="BMO",
            report_date=report_date,
            before_date=prev_session(report_date),
            after_date=report_date,
        )

    accepted_time = local.time().replace(tzinfo=None)
    market_open = dt.time(9, 30)
    market_close = close_time_et(report_date)

    if accepted_time < market_open:
        return Window(
            timing="BMO",
            report_date=report_date,
            before_date=prev_session(report_date),
            after_date=report_date,
        )

    if accepted_time >= market_close:
        return Window(
            timing="AMC",
            report_date=report_date,
            before_date=report_date,
            after_date=next_session(report_date),
        )

    raise Excluded(
        "during_market_hours",
        f"Acceptance at {local.isoformat()} occurred during market hours.",
    )


def cutoff_for(report_date: dt.date) -> dt.date:
    monday = report_date - dt.timedelta(days=report_date.weekday())
    prior_friday = monday - dt.timedelta(days=3)
    return session_on_or_before(prior_friday)
