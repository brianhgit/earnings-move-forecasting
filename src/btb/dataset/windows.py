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
    """accept_ts_et is a naive or tz-aware America/New_York timestamp."""
    raise NotImplementedError


def cutoff_for(report_date: dt.date) -> dt.date:
    raise NotImplementedError
