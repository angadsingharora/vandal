"""R1: the business-day sim clock. The only source of time outside api/.

A SimDay is an index of business days (Mon-Fri) from the profile's start date. Day 0 is the start
date (rolled forward to a weekday); negative days are history.
"""

from __future__ import annotations

from datetime import date, timedelta

from vandal.contracts.entities import SimDay


class BusinessClock:
    def __init__(self, start: date) -> None:
        while start.weekday() >= 5:
            start += timedelta(days=1)
        self.start = start

    def date_of(self, day: SimDay) -> date:
        weeks, rem = divmod(day, 5)
        d = self.start + timedelta(weeks=weeks)
        for _ in range(rem):
            d += timedelta(days=1)
            while d.weekday() >= 5:
                d += timedelta(days=1)
        return d

    def day_of(self, d: date) -> SimDay:
        """Business-day index of `d`. A weekend date maps to the following Monday."""
        while d.weekday() >= 5:
            d += timedelta(days=1)
        weeks = (d - self.start).days // 7
        day = weeks * 5
        cursor = self.start + timedelta(weeks=weeks)
        while cursor < d:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5:
                day += 1
        return day
