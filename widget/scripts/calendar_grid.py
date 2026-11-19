#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Column 2 (bottom) - builds the month grid: 6 rows x 7 columns.

Which day the week starts on and which days are the weekend (drawn red) come from config.toml
([general] week_start / weekend), because countries differ. Days of other months are grey, today gets a box."""
import time
from calendar import Calendar
from datetime import date, timedelta

from common import WEEKDAYS, emit, load_config, week_start, weekend_days


def build(today, first=6, weekend=frozenset({4, 5})):
    """first = weekday the week starts on (Mon = 0 ... Sun = 6); weekend = set of weekday numbers."""
    days = list(Calendar(firstweekday=first).itermonthdates(today.year, today.month))
    while len(days) < 42:                       # always 6 rows so the widget never changes height
        days.append(days[-1] + timedelta(days=1))
    order = [(first + i) % 7 for i in range(7)]
    heads = [{"n": WEEKDAYS[d].upper(), "c": "wd-red" if d in weekend else ""} for d in order]
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
    return {"title": today.strftime("%B, %Y").upper(), "heads": heads, "weeks": weeks}


def main():
    cfg = load_config()
    first, weekend = week_start(cfg), weekend_days(cfg)
    shown = None
    while True:
        today = date.today()
        if today != shown:                      # first run, and again after midnight
            emit(build(today, first, weekend))
            shown = today
        time.sleep(20)


if __name__ == "__main__":
    main()
