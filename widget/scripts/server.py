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

from common import clock_text, duration, emit, fmt, load_config, num, size_pair


def flatten(obj, out=None):
    """Top-level scalars of the JSON (nested values are ignored, first key wins)."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(value, (dict, list)):
                out.setdefault(key, value)
    return out


def fetch(url, token, timeout, params=None):
    query = {k: v for k, v in (params or {}).items() if v}
    if token:
        query["key"] = token
    if query:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)
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


NA = "N/A"


def request_params(cfg):
    """Settings the widget asks the server to apply (stats.php only accepts known mount points / NIC names)."""
    nics = [str(n).strip() for n in cfg.get("net_interfaces", []) if str(n).strip()]
    return {"system": str(cfg.get("system_path", "")).strip(), "net": ",".join(nics)}


def row(name, val, pct=-1, cls=""):
    """One line of the Server column. pct >= 0 draws a usage bar under it; cls colours the value (ok / warn / bad)."""
    return {"n": name, "v": val, "p": pct, "c": cls}


def disk_for(path, disks):
    """The reported disk whose mount point is `path`, or else the one that contains it (longest match).
    "/" only matches exactly: a mistyped path must say "Not found" instead of silently showing the system disk."""
    want, best = path.rstrip("/") or "/", None
    for d in disks:
        mount = str(d.get("mount", "")).rstrip("/") or "/"
        if mount == want:
            return d
        if mount != "/" and (want + "/").startswith(mount + "/") and (best is None or len(mount) > len(best[0])):
            best = (mount, d)
    return best[1] if best else None


def storage_rows(data, f, cfg):
    """The rows of the Storage section."""
    rows = []
    if cfg.get("show_system_disk", True):
        rows.append(row(f"{cfg.get('system_label') or 'System'}:",
                        size_pair(num(f.get("ssd_u")), num(f.get("ssd_t"))) if f.get("ssd_t") is not None else NA,
                        num(f.get("ssd_p")) if f.get("ssd_t") is not None else 0))
    disks = data.get("disks") if isinstance(data, dict) else None
    raid = data.get("raid") if isinstance(data, dict) else None
    if not isinstance(disks, list):
        # an old stats.php without the disk list: all it knows is one "RAID" pool (and says if there is none)
        no_pool = isinstance(raid, dict) and raid.get("present") is False and not raid.get("arrays")
        if f.get("raid_t") is not None and not no_pool:
            ok = bool(raid.get("ok")) if isinstance(raid, dict) else num(f.get("raid_t")) > 0
            text, cls = raid_status(raid, ok)
            rows.append(row(f"{cfg.get('raid_label') or 'RAID'}:",
                            size_pair(num(f.get("raid_u")), num(f.get("raid_t"))) if ok else NA,
                            num(f.get("raid_p")) if ok else 0))
            rows.append(row("Status:", text, -1, cls))
        return rows

    arrays = {a.get("name"): a for a in (raid.get("arrays") or [])} if isinstance(raid, dict) else {}

    def disk_row(label, d):
        out = [row(f"{label}:", size_pair(num(d.get("used")), num(d.get("total"))), num(d.get("percent")))]
        array = arrays.get(d.get("md"))
        if array:                               # mdadm array: add its health line
            text, cls = raid_status({"ok": True, "arrays": [array]}, True)
            out.append(row("Status:", text, -1, cls))
        return out

    paths = [str(p).strip() for p in cfg.get("storage_paths", []) if str(p).strip()]
    if paths:                                   # the user listed exactly what to show
        labels = list(cfg.get("storage_labels", [])) + [""] * len(paths)
        for path, label in zip(paths, labels):
            label = (label or "").strip() or (path.rstrip("/").rsplit("/", 1)[-1] or "Root")
            d = disk_for(path, disks)
            rows += disk_row(label, d) if d else [row(f"{label}:", "Not found", 0, "bad")]
        return rows

    extra = [d for d in disks if not d.get("system")]          # automatic: everything that is not the system disk
    extra.sort(key=lambda d: not d.get("array"))               # arrays / pools first
    extra = extra[:max(0, int(cfg.get("max_storage_rows", 3)))]
    n_arrays = sum(1 for d in extra if d.get("array"))
    for d in extra:
        base = str(d.get("mount", "")).rstrip("/").rsplit("/", 1)[-1] or str(d.get("mount", "?"))
        if d.get("array"):
            label = cfg.get("raid_label") or "RAID"
            label = label if n_arrays == 1 else f"{label} {base}"
        else:
            label = base
        rows += disk_row(label, d)
    return rows


def build(data, via, host_addr, speed, cfg):
    """One JSON object for eww. `data` = stats.php's answer, or None when the server can't be reached
    (every value then reads N/A). The Server column is a list of sections of rows, so what is shown
    follows the [server] settings in config.toml."""
    online = isinstance(data, dict)
    f = flatten(data) if online else {}
    has = lambda key: f.get(key) is not None                      # noqa: E731
    show = lambda key: bool(cfg.get(key, True))                   # noqa: E731

    ram_t = num(f.get("ram_t"))
    swap_t = num(f.get("swap_t"))
    cpu_temp = num(f.get("temp"))
    cpu_name = str(f.get("cpu_name") or "")[:60]

    head = []
    if show("show_uptime"):
        head.append(row("Uptime:", duration(num(f.get("uptime"))) if has("uptime") else NA))

    cpu = []
    if show("show_cpu"):
        cpu.append(row("CPU:", f"{fmt(num(f.get('cpu')))}%" if has("cpu") else NA, num(f.get("cpu"))))
    if show("show_clock"):
        cpu.append(row("Clock:", clock_text(f.get("cpu_mhz"))))
    if show("show_temperature"):
        cpu.append(row("Temperature:", f"{fmt(cpu_temp)}°C" if cpu_temp > 0 else NA))
    if show("show_ram"):
        cpu.append(row("RAM:", size_pair(num(f.get("ram_u")), ram_t) if ram_t > 0 else NA, num(f.get("ram_p"))))
    if show("show_swap"):
        cpu.append(row("Swap:", (size_pair(num(f.get("swap_u")), swap_t) if swap_t > 0 else "None") if has("swap_t") else NA))

    net = []
    if show("show_network"):
        net = [row("Download:", f"{speed[0]:.2f} Mbps" if online and speed else NA),
               row("Upload:", f"{speed[1]:.2f} Mbps" if online and speed else NA)]

    name = (cfg.get("name") or "").strip() or str(f.get("host") or host_addr)
    sections = [{"t": cpu_name if cpu_name else "CPU & Memory", "rows": cpu},
                {"t": "Storage", "rows": storage_rows(data, f, cfg)},
                {"t": "Network", "rows": net}]
    return {
        "ok": online,
        "title": f"{name} · {via}" if online else "Server offline",
        "head": head,
        "sections": [sec for sec in sections if sec["rows"]],      # a section with nothing to show disappears
    }


def main():
    cfg = load_config()["server"]
    params = request_params(cfg)
    urls = [u for u in cfg["urls"] if u] or ["http://127.0.0.1/stats.php"]
    labels = list(cfg["labels"]) + [""] * len(urls)
    timeout, interval = float(cfg["timeout"]), max(0.5, float(cfg["interval"]))
    retry = max(5, int(cfg["retry_primary"]))
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
                result = (i, fetch(urls[i], cfg["token"], timeout if i == active or active is None else min(timeout, 1.0), params))
                break
            except Exception:
                continue

        if result is None:
            active, prev = None, None
            emit(build(None, "", "", None, cfg))
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
            emit(build(data, labels[i] or host, host, (down, up), cfg))
        time.sleep(max(0.2, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
