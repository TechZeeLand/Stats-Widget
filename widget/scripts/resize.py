#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""stats-widget size            show the current size
stats-widget size 120%          scale (keeps proportions)
stats-widget size 1000x600      exact width x height in pixels
stats-widget size reset         back to the default design size"""
import re
import sys

from apply_config import apply
from common import (DEFAULT_H, DEFAULT_W, MAX_SCALE, MIN_SCALE, load_config, reload_widget, rnd,
                    save_config, widget_size)


def parse(arg):
    arg = arg.strip().lower().replace(" ", "")
    if arg in ("reset", "default"):
        return DEFAULT_W, DEFAULT_H
    m = re.fullmatch(r"(\d+(?:\.\d+)?)%", arg)
    if m:
        f = float(m.group(1)) / 100
        return rnd(DEFAULT_W * f), rnd(DEFAULT_H * f)
    m = re.fullmatch(r"(\d+)[x×](\d+)", arg)
    if m:
        return int(m.group(1)), int(m.group(2))
    raise ValueError(f"cannot read size '{arg}' - use e.g. 120%, 1000x600 or reset")


def main(argv):
    cfg = load_config()
    if not argv:
        w, h = widget_size(cfg)
        print(f"{w} x {h} px  ({round(100 * w / DEFAULT_W)} % x {round(100 * h / DEFAULT_H)} % of {DEFAULT_W} x {DEFAULT_H})")
        return 0
    try:
        w, h = parse(argv[0])
    except ValueError as exc:
        print(f"stats-widget: {exc}", file=sys.stderr)
        return 2
    lo_w, hi_w = rnd(DEFAULT_W * MIN_SCALE), rnd(DEFAULT_W * MAX_SCALE)
    lo_h, hi_h = rnd(DEFAULT_H * MIN_SCALE), rnd(DEFAULT_H * MAX_SCALE)
    cw, ch = max(lo_w, min(hi_w, w)), max(lo_h, min(hi_h, h))
    if (cw, ch) != (w, h):
        print(f"limited to {lo_w}-{hi_w} x {lo_h}-{hi_h} px (50 % - 300 %)")
    cfg["appearance"].update(width=cw, height=ch)
    save_config(cfg)
    apply()
    reload_widget()
    print(f"Widget size: {cw} x {ch} px")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
