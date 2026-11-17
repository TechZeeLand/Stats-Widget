#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Column 2 (top) - prints the time once per second, exactly on the second."""
import time
from datetime import datetime

from common import emit, load_config


def main():
    use_24h = load_config()["general"]["use_24h"]
    pattern = "%H:%M" if use_24h else "%-I:%M"      # 15:07  /  3:07
    while True:
        now = datetime.now()
        emit({"time": now.strftime(pattern), "sec": now.strftime("%S"),
              "date": now.strftime("%A · %-d %B").upper()})
        time.sleep(1.0 - (time.time() % 1.0) + 0.003)


if __name__ == "__main__":
    main()
