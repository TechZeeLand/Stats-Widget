#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Column 1 - polls stats.php on your server and prints one JSON line per update.

Address failover: the first URL (home network) is preferred. If it does not answer, the next one
(e.g. NetBird / VPN) is used, and the first is re-tested every few seconds so the widget switches
back by itself when you get home.

What the column shows (system disk, storage pools, network cards, which rows) comes from config.toml.
The paths are sent to stats.php with every request, so they can be changed without touching the server."""
import json
import os
import re
import time
import urllib.parse
import urllib.request

from common import (SHOW_KEYS, clean_list, clock_pair, duration, emit, fmt, load_config, num, size_pair,
                    storage_pairs, storage_slots)

KIND_LABEL = {"raid": "RAID", "zfs": "ZFS", "btrfs": "Btrfs", "mergerfs": "Pool"}


def flatten(obj, out=None):
    """Top-level scalars of the JSON (nested values are ignored, first key wins)."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(value, (dict, list)):
                out.setdefault(key, value)
    return out


def server_params(scfg):
    """Query parameters that tell stats.php what to report. Only what the user filled in is sent; an old
    stats.php (or one with allow_client_config = false) simply ignores them."""
    params = {}
    pairs = storage_pairs({"server": scfg})
    if pairs:
        params["paths[]"] = [p for _label, p in pairs]
    system = str(scfg.get("system_path") or "").strip()
    if system:
        params["system"] = system
    nics = [str(n).strip() for n in (scfg.get("net_interfaces") or []) if str(n).strip()]
    if nics:
        params["nic[]"] = nics
    return params


def fetch(url, token, timeout, params=None):
    query = dict(params or {})
    if token:
        query["key"] = token
    if query:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": "stats-widget"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", "replace")
    try:
        full = json.loads(text)
        if isinstance(full, dict) and "error" in full:
            raise ValueError(full["error"])
        return full
    except ValueError:
        if '"cpu"' not in text:
            raise
        # Very old stats.php that printed broken JSON: pull  "key": 123  pairs out of the text.
        return dict(re.findall(r'"(\w+)"\s*:\s*"?(-?[\d.]+)"?', text))


# ───────────────────────── storage / RAID health ─────────────────────────
def array_status(a):
    """One mdadm array (as reported by stats.php) -> (text, css-class)."""
    health = a.get("health")
    disks = f"{a.get('working')}/{a.get('devices')} disks" if a.get("devices") is not None else ""
    if health == "degraded":
        if a.get("progress") is not None:
            return f"{a['name']} rebuilding {fmt(a['progress'])}%", "bad"
        return f"{a['name']} degraded · {disks}".strip(" ·"), "bad"
    if health in ("syncing", "checking"):
        return f"{a['name']} {health} {fmt(a.get('progress') or 0)}%", "warn"
    if health == "inactive":
        return f"{a['name']} inactive", "bad"
    return " · ".join(x for x in (a.get("level"), disks, "healthy") if x), "ok"


def raid_status(raid, ok):
    """All arrays of a (legacy) raid object -> (text, css-class); the worst array wins."""
    if isinstance(raid, dict) and raid.get("present") is False and not raid.get("arrays"):
        return "No RAID", "ok"                      # server says: nothing separate from the system disk
    if not isinstance(raid, dict) or not ok:
        err = raid.get("error") if isinstance(raid, dict) else None
        return ("Not reachable" if err else "No data"), "bad"
    arrays = raid.get("arrays") or []
    if not arrays:
        return "Online", "ok"
    worst, text = "ok", ""
    for a in arrays:
        msg, cls = array_status(a)
        if cls == "bad":
            return msg, "bad"
        if cls == "warn" and worst != "warn":
            worst, text = "warn", msg
        elif worst == "ok" and not text:
            text = msg
    return text or "Healthy", worst


def pools_from(data):
    """The storage pools of a stats.php answer. Servers older than v3 only know one 'raid' pool."""
    if not isinstance(data, dict):
        return []
    pools = data.get("storage")
    if isinstance(pools, list):
        return [p for p in pools if isinstance(p, dict)]
    f = flatten(data)
    raid = data.get("raid")
    if isinstance(raid, dict) and raid.get("present") is False and not raid.get("arrays"):
        return []                                   # nothing separate from the system disk: no row
    ok = bool(raid.get("ok")) if isinstance(raid, dict) else num(f.get("raid_t")) > 0
    return [{"path": raid.get("path") if isinstance(raid, dict) else None, "kind": "raid", "ok": ok,
             "error": raid.get("error") if isinstance(raid, dict) else None,
             "used": num(f.get("raid_u")), "total": num(f.get("raid_t")), "percent": num(f.get("raid_p")),
             "md": None}]


def _norm(path):
    return str(path or "").rstrip("/") or "/"


def pool_label(pool, custom):
    if custom and custom.strip():
        return custom.strip()
    if pool.get("kind") in KIND_LABEL:
        return KIND_LABEL[pool["kind"]]
    base = os.path.basename(str(pool.get("path") or "").rstrip("/"))
    return base or "Storage"


def pool_status(pool, index, arrays):
    """-> (text, css-class). Empty text = no status line (a plain disk has no health to report)."""
    if not pool.get("ok"):
        return ("Not reachable" if pool.get("error") else "No data"), "bad"
    md = pool.get("md")
    if isinstance(md, dict):
        return array_status(md)
    if index == 0 and arrays and pool.get("kind") in ("raid", None):
        # mount table does not name the array (Docker, LVM, ...): fall back to all arrays like v0.3 did
        return raid_status({"ok": True, "arrays": arrays}, True)
    return "", ""


def storage_rows(data, scfg):
    """What the Storage section draws below the system disk: [{name, val, pct, status, cls}]."""
    if not scfg.get("show_storage", True):
        return []
    pairs = storage_pairs({"server": scfg})
    by_path = {_norm(path): label for label, path in pairs}          # explicit paths: match the label by path
    positional = clean_list(scfg.get("storage_labels"))              # nothing listed: first label = first pool
    arrays = []
    if isinstance(data, dict) and isinstance(data.get("raid"), dict):
        arrays = [a for a in (data["raid"].get("arrays") or []) if isinstance(a, dict)]
    rows = []
    for i, pool in enumerate(pools_from(data)[:storage_slots({"server": scfg})]):
        text, cls = pool_status(pool, i, arrays)
        ok = bool(pool.get("ok"))
        if pairs:                                   # match by path; if the server chose other paths, by position
            custom = by_path.get(_norm(pool.get("path"))) or (pairs[i][0] if i < len(pairs) else "")
        else:
            custom = positional[i] if i < len(positional) else ""
        rows.append({
            "name": pool_label(pool, custom) + ":",
            "val": size_pair(num(pool.get("used")), num(pool.get("total"))) if ok else "N/A",
            "pct": num(pool.get("percent")) if ok else 0,
            "status": text, "cls": cls,
        })
    return rows


# ───────────────────────── one JSON line for eww ─────────────────────────
def flags(scfg):
    return {f"show_{k}": bool(scfg.get(f"show_{k}", True)) for k in SHOW_KEYS}


def first_label(scfg):
    pairs = storage_pairs({"server": scfg})
    labels = [label for label, _path in pairs] or clean_list(scfg.get("storage_labels"))
    return labels[0] if labels else ""


def blank(scfg, title="Server offline", note="Offline"):
    na = "N/A"
    return {"ok": False, "title": title, "uptime": na, "clock": na, "cpu": na, "cpu_p": 0, "temp": na, "cpu_name": "",
            "ram": na, "ram_p": 0, "swap": na, "system_name": (scfg.get("system_label") or "System") + ":",
            "ssd": na, "ssd_p": 0,
            "storage": [{"name": (first_label(scfg) or "Storage") + ":", "val": na, "pct": 0, "status": note, "cls": "bad"}]
            if scfg.get("show_storage", True) else [],
            "down": na, "up": na, **flags(scfg)}


def build(data, via, host_addr, speed, scfg):
    f = flatten(data)
    ram_t = num(f.get("ram_t")) or 1
    swap_t = num(f.get("swap_t"))
    return {
        "ok": True,
        "title": f"{(scfg.get('name') or '').strip() or f.get('host') or host_addr} · {via}",
        "uptime": duration(num(f.get("uptime"))) if f.get("uptime") is not None else "N/A",
        "clock": clock_pair(f.get("cpu_mhz"), f.get("cpu_mhz_max")),
        "cpu": f"{fmt(num(f.get('cpu')))}%", "cpu_p": num(f.get("cpu")),
        "temp": f"{fmt(num(f.get('temp')))}°C" if num(f.get("temp")) > 0 else "N/A",
        "ram": size_pair(num(f.get("ram_u")), ram_t), "ram_p": num(f.get("ram_p")),
        "swap": size_pair(num(f.get("swap_u")), swap_t) if swap_t > 0 else "None",
        "system_name": (scfg.get("system_label") or "System") + ":",
        "ssd": size_pair(num(f.get("ssd_u")), num(f.get("ssd_t"))), "ssd_p": num(f.get("ssd_p")),
        "cpu_name": str(f.get("cpu_name") or "")[:60],
        "storage": storage_rows(data, scfg),
        "down": f"{speed[0]:.2f} Mbps", "up": f"{speed[1]:.2f} Mbps",
        **flags(scfg),
    }


def main():
    cfg = load_config()["server"]
    urls = [u for u in cfg["urls"] if u] or ["http://127.0.0.1/stats.php"]
    labels = list(cfg["labels"]) + [""] * len(urls)
    timeout, interval = float(cfg["timeout"]), max(0.5, float(cfg["interval"]))
    retry = max(5, int(cfg["retry_primary"]))
    params = server_params(cfg)
    offline = blank(cfg)
    active, last_probe, prev = None, 0.0, None      # prev = (time, rx, tx)

    while True:
        started = time.monotonic()
        order = list(range(len(urls)))
        if active is not None and started - last_probe < retry:
            order.remove(active)                  # on a fallback address: stay on it between probes
            order.insert(0, active)
        else:
            last_probe = started
        result = None
        for i in order:
            try:
                result = (i, fetch(urls[i], cfg["token"], timeout if i == active or active is None else min(timeout, 1.0),
                                   params))
                break
            except Exception:
                continue

        if result is None:
            active, prev = None, None
            emit(offline)
        else:
            i, data = result
            if i != active:
                active, prev = i, None            # switched address -> restart the speed measurement
            f = flatten(data)
            rx, tx = num(f.get("net_rx")), num(f.get("net_tx"))
            # Speed = difference between two samples of the byte counters. Use the moment the SERVER read
            # them (net_t) when it says so - our own clock would include the request's travel time and jitter.
            now = num(f.get("net_t")) or time.monotonic()
            down = up = 0.0
            if prev and now > prev[0]:
                dt = now - prev[0]
                down = (rx - prev[1]) * 8 / 1e6 / dt if rx >= prev[1] else 0.0
                up = (tx - prev[2]) * 8 / 1e6 / dt if tx >= prev[2] else 0.0
            prev = (now, rx, tx)
            host = urllib.parse.urlparse(urls[i]).hostname or ""
            emit(build(data, labels[i] or host, host, (down, up), cfg))
        time.sleep(max(0.2, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
