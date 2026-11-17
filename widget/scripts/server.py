#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Column 1 - polls stats.php on your server and prints one JSON line per update.

Address failover: the first URL (home network) is preferred. If it does not answer, the next one
(e.g. NetBird / VPN) is used, and the first is re-tested every few seconds so the widget switches
back by itself when you get home."""
import json
import re
import time
import urllib.parse
import urllib.request

from common import duration, emit, fmt, load_config, num, size_pair


def flatten(obj, out=None):
    """Top-level scalars of the JSON (nested values are ignored, first key wins)."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(value, (dict, list)):
                out.setdefault(key, value)
    return out


def fetch(url, token, timeout):
    if token:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode({"key": token})
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


def raid_status(raid, ok):
    """-> (text, css-class) for the RAID health line."""
    if not isinstance(raid, dict) or not ok:
        err = raid.get("error") if isinstance(raid, dict) else None
        return ("Not reachable" if err else "No data"), "bad"
    arrays = raid.get("arrays") or []
    if not arrays:
        return "Online", "ok"
    worst, text = "ok", ""
    for a in arrays:
        health = a.get("health")
        disks = f"{a.get('working')}/{a.get('devices')} disks" if a.get("devices") is not None else ""
        if health == "degraded":
            msg = f"{a['name']} degraded · {disks}"
            if a.get("progress") is not None:
                msg = f"{a['name']} rebuilding {fmt(a['progress'])}%"
            worst, text = "bad", msg
            break
        if health in ("syncing", "checking") and worst != "bad":
            worst, text = "warn", f"{a['name']} {health} {fmt(a.get('progress') or 0)}%"
        elif worst == "ok" and not text:
            text = f"{a['level']} · {disks} · healthy".replace("  ", " ")
    return text or "Healthy", worst


def build(data, via, host_addr, speed, raid_label):
    f = flatten(data)
    ram_t = num(f.get("ram_t")) or 1
    raid = data.get("raid") if isinstance(data, dict) else None
    raid_ok = bool(raid.get("ok")) if isinstance(raid, dict) else num(f.get("raid_t")) > 0
    rtext, rcls = raid_status(raid, raid_ok)
    load = data.get("load") if isinstance(data, dict) else None
    swap_t = num(f.get("swap_t"))
    return {
        "ok": True,
        "title": f"{f.get('host') or host_addr} · {via}",
        "uptime": duration(num(f.get("uptime"))) if f.get("uptime") is not None else "N/A",
        "load": " / ".join(f"{num(x):.2f}" for x in load) if isinstance(load, list) and load else "N/A",
        "cpu": f"{fmt(num(f.get('cpu')))}%", "cpu_p": num(f.get("cpu")),
        "temp": f"{fmt(num(f.get('temp')))}°C" if num(f.get("temp")) > 0 else "N/A",
        "ram": size_pair(num(f.get("ram_u")), ram_t), "ram_p": num(f.get("ram_p")),
        "swap": size_pair(num(f.get("swap_u")), swap_t) if swap_t > 0 else "None",
        "ssd": size_pair(num(f.get("ssd_u")), num(f.get("ssd_t"))), "ssd_p": num(f.get("ssd_p")),
        "raid_name": raid_label,
        "raid": size_pair(num(f.get("raid_u")), num(f.get("raid_t"))) if raid_ok else "N/A",
        "raid_p": num(f.get("raid_p")) if raid_ok else 0,
        "raid_status": rtext, "raid_cls": rcls,
        "down": f"{speed[0]:.2f} Mbps", "up": f"{speed[1]:.2f} Mbps",
    }


def main():
    cfg = load_config()["server"]
    urls = [u for u in cfg["urls"] if u] or ["http://127.0.0.1/stats.php"]
    labels = list(cfg["labels"]) + [""] * len(urls)
    timeout, interval = float(cfg["timeout"]), max(0.5, float(cfg["interval"]))
    retry = max(5, int(cfg["retry_primary"]))
    na = "N/A"
    offline = {"ok": False, "title": "Server offline", "uptime": na, "load": na, "cpu": na, "cpu_p": 0,
               "temp": na, "ram": na, "ram_p": 0, "swap": na, "ssd": na, "ssd_p": 0,
               "raid_name": cfg["raid_label"], "raid": na, "raid_p": 0, "raid_status": "Offline",
               "raid_cls": "bad", "down": na, "up": na}
    active, last_probe, prev = None, 0.0, None      # prev = (time, rx, tx)

    while True:
        started = time.monotonic()
        order = list(range(len(urls)))
        if active and started - last_probe < retry:
            order.remove(active)                  # on a fallback address: stay on it between probes
            order.insert(0, active)
        else:
            last_probe = started
        result = None
        for i in order:
            try:
                result = (i, fetch(urls[i], cfg["token"], timeout if i == active or active is None else min(timeout, 1.0)))
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
            rx, tx, now = num(f.get("net_rx")), num(f.get("net_tx")), time.monotonic()
            down = up = 0.0
            # speed = difference between two samples of the byte counters
            if prev and now > prev[0]:
                dt = now - prev[0]
                down = (rx - prev[1]) * 8 / 1e6 / dt if rx >= prev[1] else 0.0
                up = (tx - prev[2]) * 8 / 1e6 / dt if tx >= prev[2] else 0.0
            prev = (now, rx, tx)
            host = urllib.parse.urlparse(urls[i]).hostname or ""
            emit(build(data, labels[i] or host, host, (down, up), cfg["raid_label"]))
        time.sleep(max(0.2, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
