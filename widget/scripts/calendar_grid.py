#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Column 2 (bottom) - builds the month grid: 6 rows x 7 columns.
Which day the week starts on and which days are the weekend (red) come from config.toml
([general] week_start / weekend). Days of other months are grey, today gets a box."""
import time
from calendar import Calendar
from datetime import date, timedelta

from common import DAY_CODES, DEFAULT_WEEK_START, DEFAULT_WEEKEND, emit, load_config, week_start, weekend_days


def build(today, weekend=None, first=None):
    """weekend = set of weekday numbers (Monday = 0), first = weekday number of the first column."""
    weekend = set(DEFAULT_WEEKEND) if weekend is None else set(weekend)
    first = DEFAULT_WEEK_START if first is None else first
    days = list(Calendar(firstweekday=first).itermonthdates(today.year, today.month))
    while len(days) < 42:                       # always 6 rows so the widget never changes height
        days.append(days[-1] + timedelta(days=1))
    weeks = []
    for w in range(6):
        row = []
        for d in days[w * 7:(w + 1) * 7]:
            classes = []
            if d.month != today.month:
                classes.append("out")
            elif d.weekday() in weekend:
                classes.append("wk")
            if d == today:
                classes.append("today")
            row.append({"d": str(d.day), "c": " ".join(classes)})
        weeks.append(row)
    heads = []
    for i in range(7):
        wd = (first + i) % 7
        heads.append({"t": DAY_CODES[wd].upper(), "c": "wd-red" if wd in weekend else ""})
    return {"title": today.strftime("%B, %Y").upper(), "heads": heads, "weeks": weeks}


def main():
    cfg = load_config()
    weekend, first = weekend_days(cfg), week_start(cfg)
    shown = None
    while True:
        today = date.today()
        if today != shown:                      # first run, and again after midnight
            emit(build(today, weekend, first))
            shown = today
        time.sleep(20)


if __name__ == "__main__":
    main()
