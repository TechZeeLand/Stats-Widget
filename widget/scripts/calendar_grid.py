#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Column 2 (bottom) - builds the month grid: 6 rows x 7 columns, weeks start on Sunday.
Fri + Sat are the weekend (red), days of other months are grey, today gets a box."""
import time
from calendar import Calendar
from datetime import date, timedelta

from common import emit


def build(today):
    days = list(Calendar(firstweekday=6).itermonthdates(today.year, today.month))
    while len(days) < 42:                       # always 6 rows so the widget never changes height
        days.append(days[-1] + timedelta(days=1))
    weeks = []
    for w in range(6):
        row = []
        for col, d in enumerate(days[w * 7:(w + 1) * 7]):
            classes = []
            if d.month != today.month:
                classes.append("out")
            elif col in (5, 6):                 # Friday, Saturday
                classes.append("wk")
            if d == today:
                classes.append("today")
            row.append({"d": str(d.day), "c": " ".join(classes)})
        weeks.append(row)
    return {"title": today.strftime("%B, %Y").upper(), "weeks": weeks}


def main():
    shown = None
    while True:
        today = date.today()
        if today != shown:                      # first run, and again after midnight
            emit(build(today))
            shown = today
        time.sleep(20)


if __name__ == "__main__":
    main()
