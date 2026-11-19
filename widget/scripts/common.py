# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared helpers for every Stats Widget script: config loading/saving and small utilities."""
import copy
import json
import os
import sys
from pathlib import Path

try:                                  # Python 3.11+
    import tomllib
except ModuleNotFoundError:           # older Python (RHEL 9, Ubuntu 22.04): tiny built-in fallback
    tomllib = None

ROOT = Path(__file__).resolve().parent.parent            # the widget folder (has eww.yuck)
CACHE = Path.home() / ".cache" / "stats-widget"

DEFAULTS = {
    "general": {"use_24h": False, "weekend": ["fri", "sat"], "week_start": "sunday"},
    "server": {
        "urls": ["http://192.168.0.123/stats.php", "http://rayaz.netbird.cloud/stats.php"],
        "labels": ["Home network", "Remote (NetBird)"],
        "token": "",
        "interval": 1.0,
        "timeout": 1.5,
        "retry_primary": 20,
        "name": "",                  # shown instead of the server's own hostname
        "show_uptime": True,
        "show_cpu": True,
        "show_clock": True,
        "show_temperature": True,
        "show_ram": True,
        "show_swap": True,
        "show_network": True,
        "show_system_disk": True,
        "system_label": "System",
        "system_path": "",           # "" = whatever the server treats as its system disk
        "storage_paths": [],         # [] = automatic: every disk / pool that is not the system disk
        "storage_labels": [],
        "max_storage_rows": 3,       # automatic mode only
        "raid_label": "RAID",        # automatic mode: name of mdadm / ZFS / btrfs / mergerfs rows
        "net_interfaces": [],        # [] = all physical network cards on the server
    },
    "weather": {
        "display_name": "Dhaka, Bangladesh",
        "latitude": 23.7643863,
        "longitude": 90.3890144,
        "units": "metric",
        "refresh_minutes": 10,
    },
    "position": {"anchor": "top left", "x": 40, "y": 40, "monitor": 0, "layer": "bottom"},
    "appearance": {"background_opacity": 100, "width": 795, "height": 475},
}

# The widget was designed at 795 x 475 px. Any other size scales the whole layout from that design.
DEFAULT_W, DEFAULT_H = 795, 475
MIN_SCALE, MAX_SCALE = 0.5, 3.0

ANCHORS = ["top left", "top center", "top right", "center left", "center", "center right",
           "bottom left", "bottom center", "bottom right"]
LAYERS = ["bottom", "bg", "fg", "overlay"]


def rnd(x):
    """Round half up - the same rule Sass round() uses, so yuck and scss agree on every pixel."""
    return int(x + 0.5)


def widget_size(cfg):
    """(width, height) in px, clamped to 50 %..300 % of the design size. Bad values -> the default."""
    a = cfg.get("appearance", {})
    out = []
    for key, default in (("width", DEFAULT_W), ("height", DEFAULT_H)):
        try:
            v = int(float(a.get(key, default)))
        except (TypeError, ValueError):
            v = default
        out.append(max(rnd(default * MIN_SCALE), min(rnd(default * MAX_SCALE), v)))
    return tuple(out)


# ───────────────────────── calendar week ─────────────────────────
DAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]        # index 0 = Monday (like datetime.weekday())
DEFAULT_WEEKEND = [4, 5]                                              # Friday + Saturday
DEFAULT_WEEK_START = 6                                                # Sunday


def _day_index(value):
    """'Fri' / 'friday' / ' FRI ' -> 4.  Anything else -> None."""
    text = str(value).strip().lower()[:3]
    return DAY_CODES.index(text) if text in DAY_CODES else None


def weekend_days(cfg):
    """Set of weekday numbers (Monday = 0) that are the weekend.
    [] = no highlighted weekend. A list with no valid day names at all falls back to Friday + Saturday."""
    raw = cfg.get("general", {}).get("weekend", DEFAULT_WEEKEND_NAMES)
    if not isinstance(raw, (list, tuple)):
        return set(DEFAULT_WEEKEND)
    days = {i for i in (_day_index(v) for v in raw) if i is not None}
    return days if days or not raw else set(DEFAULT_WEEKEND)


def week_start(cfg):
    """First column of the calendar as a weekday number (Monday = 0). Bad value -> Sunday."""
    i = _day_index(cfg.get("general", {}).get("week_start", "sunday"))
    return DEFAULT_WEEK_START if i is None else i


DEFAULT_WEEKEND_NAMES = [DAY_CODES[i] for i in DEFAULT_WEEKEND]


def clock_text(mhz):
    """2412.7 -> '2.41 GHz', 800 -> '800 MHz', anything unusable -> 'N/A'."""
    try:
        mhz = float(mhz)
    except (TypeError, ValueError):
        return "N/A"
    if mhz <= 0:
        return "N/A"
    return f"{mhz / 1000:.2f} GHz" if mhz >= 1000 else f"{mhz:.0f} MHz"


# ───────────────────────── config file ─────────────────────────
def config_path():
    env = os.environ.get("STATS_WIDGET_CONFIG")
    if env:
        return Path(env)
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "stats-widget" / "config.toml"


def _parse_toml_subset(text):
    """Just enough TOML for our own file: [sections], key = "str" | number | bool | ["a", "b"]."""
    data, section = {}, None
    for raw in text.splitlines():
        line, in_str, cut = raw.strip(), False, None
        for i, ch in enumerate(line):                 # strip trailing "# comment" outside strings
            if ch == '"' and (i == 0 or line[i - 1] != "\\"):
                in_str = not in_str
            elif ch == "#" and not in_str:
                cut = i
                break
        line = (line[:cut] if cut is not None else line).strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]") and "=" not in line:
            section = line[1:-1].strip()
            data.setdefault(section, {})
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value in ("true", "false"):
            parsed = value == "true"
        elif value.startswith(('"', "[")):
            parsed = json.loads(value)
        else:
            parsed = float(value) if any(c in value for c in ".eE") else int(value)
        (data.setdefault(section, {}) if section else data)[key] = parsed
    return data


def load_config():
    """Defaults + whatever is in config.toml. Never raises: a broken file falls back to defaults."""
    cfg = copy.deepcopy(DEFAULTS)
    path = config_path()
    try:
        raw = path.read_bytes()
        user = tomllib.loads(raw.decode("utf-8")) if tomllib else _parse_toml_subset(raw.decode("utf-8"))
        for section, values in user.items():
            if isinstance(values, dict):
                cfg.setdefault(section, {}).update(values)
    except FileNotFoundError:
        pass
    except Exception as exc:                          # syntax error etc.
        print(f"config.toml problem ({path}): {exc} - using defaults", file=sys.stderr)
    return cfg


def _val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)


def render_config(cfg):
    g, s, w, p, a = (cfg[k] for k in ("general", "server", "weather", "position", "appearance"))
    D = DEFAULTS["server"]
    sv = lambda key: s.get(key, D[key])                                       # noqa: E731
    gv = lambda key: g.get(key, DEFAULTS["general"][key])                     # noqa: E731
    return f"""\
# Stats Widget settings - https://github.com/TechZeeLand/Stats-Widget
# Easiest way to change these:   stats-widget config      (graphical settings window)
# After editing by hand run:     stats-widget restart

[general]
use_24h = {_val(g['use_24h'])}                  # false = 3:07   true = 15:07
weekend = {_val(gv('weekend'))}      # days drawn in red: any of "mon" "tue" "wed" "thu" "fri" "sat" "sun"  ([] = none)
week_start = {_val(gv('week_start'))}            # first column of the calendar: "sunday", "monday", "saturday" ...

[server]
# stats.php addresses, tried in this order. The first that answers is used; while a later one is
# active the first is re-checked every `retry_primary` seconds, so the widget switches back
# automatically when you get home.
urls   = {_val(s['urls'])}
labels = {_val(s['labels'])}   # text shown for each url (same order)
token  = {_val(s['token'])}                      # only if you set 'token' in stats.config.php
interval      = {_val(float(s['interval']))}     # seconds between requests
timeout       = {_val(float(s['timeout']))}      # seconds before an address is considered down
retry_primary = {_val(int(s['retry_primary']))}  # seconds between "is home reachable again?" checks

# What the Server column shows. Everything here is decided by the widget - nothing to edit on the server.
name = {_val(sv('name'))}                         # shown instead of the server's own hostname ("" = hostname)
show_uptime      = {_val(sv('show_uptime'))}
show_cpu         = {_val(sv('show_cpu'))}
show_clock       = {_val(sv('show_clock'))}                     # current CPU clock speed
show_temperature = {_val(sv('show_temperature'))}
show_ram         = {_val(sv('show_ram'))}
show_swap        = {_val(sv('show_swap'))}
show_network     = {_val(sv('show_network'))}
show_system_disk = {_val(sv('show_system_disk'))}
system_label     = {_val(sv('system_label'))}               # name of the system-disk row
system_path      = {_val(sv('system_path'))}                      # "" = the server's own choice, or a mount point such as "/"
# Extra storage rows. [] = automatic: every separate disk / RAID / pool the server reports (none if it has only
# its system disk). Or list mount points as the SERVER sees them, with a name for each (same order):
storage_paths  = {_val(sv('storage_paths'))}
storage_labels = {_val(sv('storage_labels'))}
max_storage_rows = {_val(int(sv('max_storage_rows')))}                  # automatic mode: how many extra disks to show at most
raid_label       = {_val(sv('raid_label'))}                  # automatic mode: name for mdadm / ZFS / btrfs / mergerfs rows
net_interfaces   = {_val(sv('net_interfaces'))}                       # [] = all physical network cards, or e.g. ["enp3s0"]

[weather]                                         # Open-Meteo, no API key needed
display_name    = {_val(w['display_name'])}
latitude        = {_val(float(w['latitude']))}
longitude       = {_val(float(w['longitude']))}
units           = {_val(w['units'])}              # "metric" (C, km/h)  or  "imperial" (F, mph)
refresh_minutes = {_val(int(w['refresh_minutes']))}

[position]
anchor  = {_val(p['anchor'])}                  # top left | top center | top right | center | bottom left ...
x       = {_val(int(p['x']))}                  # distance from the anchored edge, in pixels
y       = {_val(int(p['y']))}
monitor = {_val(p['monitor'])}                 # 0 = first screen, 1 = second ... (or a name like "DP-1")
layer   = {_val(p['layer'])}                   # Wayland: bottom (above wallpaper) | bg | fg | overlay

[appearance]
background_opacity = {_val(int(a['background_opacity']))}   # 0-100 (%), 100 = solid black
width  = {_val(widget_size(cfg)[0])}                  # widget size in pixels; the default design is 795 x 475.
height = {_val(widget_size(cfg)[1])}                  # Everything inside scales with it (50 % to 300 %).
"""


def save_config(cfg):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(render_config(cfg), encoding="utf-8")
    tmp.replace(path)
    return path


# ───────────────────────── small utilities ─────────────────────────
def emit(obj):
    """Print one JSON object on one line - this is what eww reads."""
    print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), flush=True)


def fmt(value, decimals=1):
    """12.0 -> '12', 12.345 -> '12.3'  (no trailing zeros)."""
    text = f"{value:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def size_pair(used, total):
    """GB numbers -> '120 / 500 GB' or '2.1 / 10.9 TB'."""
    if total >= 1024:
        tb = lambda v: fmt(v / 1024, 2 if v < 1024 else 1)      # noqa: E731
        return f"{tb(used)} / {tb(total)} TB"
    return f"{fmt(used, 0 if total >= 100 else 1)} / {fmt(total, 0 if total >= 100 else 1)} GB"


def duration(seconds):
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h {m}m"
    return f"{h}h {m}m" if h else f"{m}m"


# ───────────────────────── talking to eww ─────────────────────────
def eww_binary():
    import shutil
    return shutil.which("eww") or str(Path.home() / ".local" / "bin" / "eww")


def reload_widget():
    """Re-read config files and redraw. Silent no-op if the widget is not running."""
    import subprocess
    try:
        subprocess.run([eww_binary(), "--config", str(ROOT), "reload"], capture_output=True, timeout=15)
    except Exception:
        pass
