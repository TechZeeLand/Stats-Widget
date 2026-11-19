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
    "general": {"use_24h": False, "week_start": "sun", "weekend": ["fri", "sat"]},
    "server": {
        "urls": ["http://192.168.0.123/stats.php", "http://rayaz.netbird.cloud/stats.php"],
        "labels": ["Home network", "Remote (NetBird)"],
        "token": "",
        "interval": 1.0,
        "timeout": 1.5,
        "retry_primary": 20,
        "name": "",                  # shown instead of the server's own hostname ("" = hostname)
        # What the server column shows. Empty path lists mean "whatever the server itself is set up for".
        "system_label": "System",
        "system_path": "",
        "storage_paths": [],
        "storage_labels": [],
        "net_interfaces": [],
        "show_uptime": True,
        "show_cpu_clock": True,
        "show_cpu": True,
        "show_temp": True,
        "show_ram": True,
        "show_swap": True,
        "show_system": True,
        "show_storage": True,
        "show_network": True,
    },
    # What the PC Stats column shows: one switch per row (a block whose rows are all off disappears).
    "pc": {f"show_{k}": True for k in ("cpu", "cpu_clock", "cpu_temp", "uptime", "gpu_use", "gpu_temp", "vram",
                                       "ram", "disk", "battery", "network")},
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

# Python's weekday() order: Monday = 0 ... Sunday = 6
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SHOW_KEYS = ("uptime", "cpu_clock", "cpu", "temp", "ram", "swap", "system", "storage", "network")   # Server column
PC_SHOW_KEYS = ("cpu", "cpu_clock", "cpu_temp", "uptime", "gpu_use", "gpu_temp", "vram",
                "ram", "disk", "battery", "network")                                               # PC column
MAX_STORAGE = 4                                          # storage pools the server column can show


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


def _day_index(token):
    """'Fri', 'friday', 'FRI' -> 4.   Anything else -> None."""
    t = str(token).strip().lower()[:3]
    return WEEKDAYS.index(t) if t in WEEKDAYS else None


def weekend_days(cfg):
    """Set of weekday numbers (Mon = 0) drawn red in the calendar. Unknown names are ignored; [] = no weekend."""
    raw = cfg.get("general", {}).get("weekend", DEFAULTS["general"]["weekend"])
    if isinstance(raw, str):
        raw = [x for x in raw.replace(";", ",").split(",")]
    if not isinstance(raw, (list, tuple)):
        raw = DEFAULTS["general"]["weekend"]
    days = {i for i in map(_day_index, raw) if i is not None}
    if raw and not days:                                       # only unreadable names: do not silently drop the weekend
        days = {i for i in map(_day_index, DEFAULTS["general"]["weekend"]) if i is not None}
    return days


def week_start(cfg):
    """First column of the calendar as a weekday number (Mon = 0). Default Sunday."""
    i = _day_index(cfg.get("general", {}).get("week_start", "sun"))
    return 6 if i is None else i


def clean_list(value):
    """['a', ' b '] or 'a, b' -> ['a', 'b'] (blank entries are kept: they keep two parallel lists aligned)."""
    if isinstance(value, str):
        value = value.split(",")
    return [str(x).strip() for x in value] if isinstance(value, (list, tuple)) else []


def storage_pairs(cfg):
    """[(label, path)] of the storage pools the user listed (labels padded with ''), at most MAX_STORAGE."""
    s = cfg.get("server", {})
    paths, labels = clean_list(s.get("storage_paths")), clean_list(s.get("storage_labels"))
    pairs = [(labels[i] if i < len(labels) else "", p) for i, p in enumerate(paths) if p]
    return pairs[:MAX_STORAGE]


def storage_slots(cfg):
    """How many storage rows the layout has room for: one per listed path, at least one."""
    return max(1, len(storage_pairs(cfg)))


def design_height(cfg):
    """Height (design px) the layout needs. 475 normally; taller when the server column gets extra
    storage rows, so that apply_config can shrink everything a little instead of overflowing the window.
    Numbers measured from the default layout: content 430 px of 455 px usable."""
    s = cfg.get("server", {})
    on = lambda k: bool(s.get("show_" + k, True))                 # noqa: E731
    delta = 0
    delta -= 22 * sum(1 for k in ("uptime", "cpu_clock", "temp", "swap") if not on(k))
    delta -= 25 * sum(1 for k in ("cpu", "ram") if not on(k))
    if not any(on(k) for k in ("cpu", "temp", "ram", "swap")):
        delta -= 30                                               # the whole "CPU & Memory" heading goes
    pools = storage_slots(cfg) if on("storage") else 0
    delta += (pools - 1) * 47                                     # one bar (25) + one status line (22) each
    if not on("system"):
        delta -= 25
    if not on("system") and not on("storage"):
        delta -= 30                                               # the whole "Storage" heading goes
    if not on("network"):
        delta -= 74
    need = 430 + delta + 2 * 10 + 5                               # content + frame + a little air
    return max(DEFAULT_H, need)


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
        srv = user.get("server") if isinstance(user.get("server"), dict) else {}
        if "raid_label" in srv and "storage_labels" not in srv:      # settings written by v0.3
            cfg["server"]["storage_labels"] = [str(srv["raid_label"])]
        for old, new in (("show_clock", "show_cpu_clock"), ("show_temperature", "show_temp"),
                         ("show_system_disk", "show_system")):         # names used by an earlier draft of the Server rows
            if old in srv and new not in srv:
                cfg["server"][new] = srv[old]
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
    weekend = sorted(weekend_days(cfg))
    show = lambda k: _val(bool(s.get("show_" + k, True)))             # noqa: E731
    pc_show = lambda k: _val(bool(cfg.get("pc", {}).get("show_" + k, True)))   # noqa: E731
    return f"""\
# Stats Widget settings - https://github.com/TechZeeLand/Stats-Widget
# Easiest way to change these:   stats-widget config      (graphical settings window)
# After editing by hand run:     stats-widget restart

[general]
use_24h    = {_val(g['use_24h'])}                  # false = 3:07   true = 15:07
week_start = {_val(WEEKDAYS[week_start(cfg)])}                  # first day of the calendar week: mon tue wed thu fri sat sun
weekend    = {_val([WEEKDAYS[i] for i in weekend])}   # days drawn in red (any of the seven; [] = none)

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

# What the server column shows. The paths are sent to stats.php with every request, so you can change
# them here without touching the server (unless its admin set allow_client_config = false).
name           = {_val(str(s.get('name', '')))}                         # shown instead of the server's hostname ("" = hostname)
system_label   = {_val(s['system_label'])}                # name of the system-disk row
system_path    = {_val(s['system_path'])}                      # "" = the server's own setting (normally "/")
storage_paths  = {_val(clean_list(s['storage_paths']))}                   # e.g. ["/raids", "/mnt/media"]; [] = what the server is set up for / finds itself
storage_labels = {_val(clean_list(s['storage_labels']))}                   # names for those paths, same order ("" = automatic)
net_interfaces = {_val(clean_list(s['net_interfaces']))}                   # e.g. ["enp3s0"]; [] = all physical network cards
show_uptime    = {show('uptime')}
show_cpu_clock = {show('cpu_clock')}
show_cpu       = {show('cpu')}
show_temp      = {show('temp')}
show_ram       = {show('ram')}
show_swap      = {show('swap')}
show_system    = {show('system')}
show_storage   = {show('storage')}
show_network   = {show('network')}

[pc]                                              # which rows the PC Stats column shows (true / false)
show_cpu       = {pc_show('cpu')}                 # CPU usage bar
show_cpu_clock = {pc_show('cpu_clock')}
show_cpu_temp  = {pc_show('cpu_temp')}
show_uptime    = {pc_show('uptime')}
show_gpu_use   = {pc_show('gpu_use')}                 # GPU utilisation + clock
show_gpu_temp  = {pc_show('gpu_temp')}
show_vram      = {pc_show('vram')}                 # only exists on cards with their own memory
show_ram       = {pc_show('ram')}
show_disk      = {pc_show('disk')}
show_battery   = {pc_show('battery')}              # only exists on laptops
show_network   = {pc_show('network')}

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


def clock_pair(cur_mhz, max_mhz=0):
    """Current (and maximum) CPU clock -> '2.84 / 4.60 GHz', '2.84 GHz', '800 MHz' or 'N/A'."""
    cur, top = num(cur_mhz), num(max_mhz)
    if cur <= 0:
        return "N/A"
    if top >= cur:
        if top >= 1000:
            return f"{cur / 1000:.2f} / {top / 1000:.2f} GHz"
        return f"{cur:.0f} / {top:.0f} MHz"
    return f"{cur / 1000:.2f} GHz" if cur >= 1000 else f"{cur:.0f} MHz"


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
