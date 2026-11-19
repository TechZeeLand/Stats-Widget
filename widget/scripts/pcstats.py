#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Column 3 - local PC stats, read straight from /proc and /sys (no extra packages).

The Windows version read these numbers from HWiNFO's registry export.
Here: CPU/RAM/network from /proc, temperatures from hwmon, GPU from the DRM driver."""
import glob
import os
import re
import shlex
import shutil
import subprocess
import time

from common import clock_text, duration, emit, fmt, size_pair

NA = "N/A"
GIB = 1024 ** 3


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def read_int(path):
    try:
        return int(read(path))
    except (TypeError, ValueError):
        return None


# ───────────────────────────── CPU ─────────────────────────────
def cpu_title():
    model = ""
    for line in (read("/proc/cpuinfo", "") or "").splitlines():
        if line.startswith("model name"):
            model = line.split(":", 1)[1].strip()
            break
    model = re.sub(r"\((?:R|TM|r|tm)\)", "", model)
    model = re.sub(r"@.*$", "", model)
    model = re.sub(r"\b\d+(?:st|nd|rd|th) Gen\b", "", model)
    model = re.sub(r"\b(?:CPU|Processor|\d+-Core)\b", "", model)
    model = re.sub(r"\bwith Radeon.*$", "", model)
    model = re.sub(r"\s+", " ", model).strip(" ,") or "CPU"
    khz = read_int("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    return f"{model}, {khz / 1e6:.1f}GHz" if khz else model


def cpu_clock_mhz(sys_root="/sys", proc_root="/proc"):
    """Current CPU clock in MHz: the average over all cores (like HWiNFO's "average effective clock").
    Uses cpufreq when the kernel offers it, otherwise the "cpu MHz" lines of /proc/cpuinfo."""
    vals = []
    for path in glob.glob(f"{sys_root}/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq"):
        khz = read_int(path)
        if khz and khz > 0:
            vals.append(khz / 1000)
    if not vals:
        for line in (read(f"{proc_root}/cpuinfo", "") or "").splitlines():
            if line.startswith("cpu MHz"):
                try:
                    vals.append(float(line.split(":", 1)[1]))
                except ValueError:
                    pass
    vals = [v for v in vals if v > 0]
    return sum(vals) / len(vals) if vals else None


def cpu_times():
    parts = [int(x) for x in read("/proc/stat").splitlines()[0].split()[1:9]]
    idle = parts[3] + parts[4]          # idle + iowait
    return sum(parts), idle


def find_cpu_temp_input():
    best, best_rank = None, 99
    ranks = {"coretemp": 0, "k10temp": 0, "zenpower": 0, "cpu_thermal": 1, "acpitz": 2}
    for hw in glob.glob("/sys/class/hwmon/hwmon*"):
        rank = ranks.get(read(hw + "/name", ""), 99)
        if rank >= best_rank:
            continue
        chosen = None
        for label in sorted(glob.glob(hw + "/temp*_label")):
            text = (read(label, "") or "").lower()
            if any(k in text for k in ("package", "tctl", "tdie")):
                chosen = label.replace("_label", "_input")
                break
        best, best_rank = chosen or hw + "/temp1_input", rank
    return best


# ───────────────────────────── GPU ─────────────────────────────
def pick_gpu():
    """Prefer a discrete GPU (NVIDIA, then AMD) over an Intel iGPU."""
    order = {"0x10de": 0, "0x1002": 1, "0x8086": 2}
    cards = []
    for card in sorted(glob.glob("/sys/class/drm/card*")):
        if not re.fullmatch(r"card\d+", os.path.basename(card)):
            continue
        vendor = read(card + "/device/vendor")
        if vendor:
            cards.append((order.get(vendor, 3), card, vendor))
    cards.sort()
    return (cards[0][1], cards[0][2]) if cards else (None, None)


def gpu_title(card, vendor):
    fallback = {"0x10de": "NVIDIA Graphics", "0x1002": "AMD Graphics", "0x8086": "Intel Graphics"}
    if vendor == "0x10de" and shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
            if out:
                return out.splitlines()[0]
        except Exception:
            pass
    slot = os.path.basename(os.path.realpath(card + "/device"))
    if shutil.which("lspci"):
        try:
            out = subprocess.run(["lspci", "-s", slot, "-mm"], capture_output=True,
                                 text=True, timeout=5).stdout.strip()
            tok = shlex.split(out)
            vendor_name, device = tok[2], tok[3]
            short = ("AMD" if "Advanced Micro" in vendor_name else
                     "NVIDIA" if "NVIDIA" in vendor_name else
                     "Intel" if "Intel" in vendor_name else vendor_name)
            bracket = re.search(r"\[(.*)\]", device)
            return f"{short} {bracket.group(1) if bracket else device}"
        except Exception:
            pass
    return fallback.get(vendor, "GPU")


class GPU:
    def __init__(self):
        self.card, self.vendor = pick_gpu()
        self.title = gpu_title(self.card, self.vendor) if self.card else "No GPU found"
        self.last_rc6 = None  # (timestamp, residency_ms) for Intel utilisation

    def stats(self):
        # "vram" stays None for GPUs that have no memory of their own (Intel iGPU, AMD APU): the widget then hides the row
        out = {"use": NA, "temp": NA, "vram": None, "clock": NA}
        if not self.card:
            return out
        dev = self.card + "/device"
        if self.vendor == "0x1002":
            self._amd(dev, out)
        elif self.vendor == "0x10de":
            self._nvidia(dev, out)
        elif self.vendor == "0x8086":
            self._intel(out)
        return out

    @staticmethod
    def amd_has_dedicated_vram(dev):
        """True for a graphics card with its own memory, False for an APU that borrows system RAM.
        amdgpu names the memory maker only on real cards; as a fallback, 2 GB or more counts as dedicated."""
        total = read_int(dev + "/mem_info_vram_total") or 0
        maker = (read(dev + "/mem_info_vram_vendor", "") or "").strip().lower()
        if maker and maker != "unknown":
            return total > 0
        return total >= 2 * GIB

    @staticmethod
    def _amd(dev, out):
        busy = read_int(dev + "/gpu_busy_percent")
        if busy is not None:
            out["use"] = f"{busy}%"
        if GPU.amd_has_dedicated_vram(dev):
            used, total = read_int(dev + "/mem_info_vram_used"), read_int(dev + "/mem_info_vram_total")
            out["vram"] = f"{used / GIB:.2f} GB / {fmt(total / GIB, 0)} GB" if used is not None and total else NA
        for hw in glob.glob(dev + "/hwmon/hwmon*"):
            t = read_int(hw + "/temp1_input")
            if t is not None:
                out["temp"] = f"{t / 1000:.0f}°C"
                break
        m = re.search(r"(\d+)\s*[Mm][Hh]z\s*\*", read(dev + "/pp_dpm_sclk", "") or "")
        if m:
            out["clock"] = f"{m.group(1)} MHz"

    @staticmethod
    def _nvidia(dev, out):
        out["vram"] = NA                       # NVIDIA cards have their own memory
        # Don't poke a sleeping laptop dGPU - it would wake it up and drain the battery.
        if read(dev + "/power/runtime_status") == "suspended":
            out.update(use="Asleep", temp="Asleep", vram="Asleep", clock="Asleep")
            return
        if not shutil.which("nvidia-smi"):
            return
        try:
            line = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,clocks.gr",
                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3).stdout.strip()
            use, temp, used, total, clock = [x.strip() for x in line.splitlines()[0].split(",")]
        except Exception:
            return

        def number(text):                      # nvidia-smi prints "[N/A]" for what a card can't report
            try:
                return float(text)
            except ValueError:
                return None
        if number(use) is not None:
            out["use"] = f"{number(use):.0f}%"
        if number(temp) is not None:
            out["temp"] = f"{number(temp):.0f}°C"
        if number(used) is not None and number(total):
            out["vram"] = f"{number(used) / 1024:.2f} GB / {fmt(number(total) / 1024, 0)} GB"
        if number(clock) is not None:
            out["clock"] = f"{number(clock):.0f} MHz"

    def _intel(self, out):
        base = self.card
        for p in (base + "/gt_cur_freq_mhz", base + "/gt/gt0/rps_cur_freq_mhz",
                  base + "/device/tile0/gt0/freq0/cur_freq"):
            mhz = read_int(p)
            if mhz is not None:
                out["clock"] = f"{mhz} MHz"
                break
        # Intel exposes no "busy %" file. Time spent OUT of the RC6 sleep state is
        # a good approximation, so we show that (marked with ~).
        for p in (base + "/gt/gt0/rc6_residency_ms", base + "/power/rc6_residency_ms",
                  base + "/device/tile0/gt0/gtidle/idle_residency_ms"):
            rc6 = read_int(p)
            if rc6 is not None:
                now = time.monotonic()
                if self.last_rc6 and now > self.last_rc6[0]:
                    asleep = (rc6 - self.last_rc6[1]) / ((now - self.last_rc6[0]) * 1000)
                    out["use"] = f"~{max(0, min(100, round(100 * (1 - asleep))))}%"
                self.last_rc6 = (now, rc6)
                break


# ─────────────────────────── RAM / network ───────────────────────────
def ram_info():
    info = {}
    for line in (read("/proc/meminfo", "") or "").splitlines():
        key, _, rest = line.partition(":")
        info[key] = int(rest.split()[0])          # kB
    total, avail = info.get("MemTotal", 0), info.get("MemAvailable", 0)
    used = total - avail
    text = f"{used / 1048576:.1f} / {fmt(total / 1048576, 1)} GB"
    return text, (100 * used / total if total else 0)


def disk_info(path="/"):
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize / GIB
        used = total - st.f_bavail * st.f_frsize / GIB
        return size_pair(used, total), (100 * used / total if total else 0)
    except OSError:
        return NA, 0


def battery():
    for bat in sorted(glob.glob("/sys/class/power_supply/BAT*")):
        cap, status = read_int(bat + "/capacity"), read(bat + "/status", "")
        if cap is not None:
            icon = {"Charging": "charging", "Full": "full"}.get(status, "on battery")
            return f"{cap}% · {icon}", cap
    return "", 0


def net_totals():
    rx = tx = 0
    for iface in glob.glob("/sys/class/net/*"):
        if not os.path.exists(iface + "/device"):   # skips lo, docker, veth, VPNs, bridges...
            continue
        rx += read_int(iface + "/statistics/rx_bytes") or 0
        tx += read_int(iface + "/statistics/tx_bytes") or 0
    return rx, tx


def main():
    cpu_name, gpu = cpu_title(), GPU()
    temp_path = find_cpu_temp_input()
    prev_cpu, prev_net, prev_t = cpu_times(), net_totals(), time.monotonic()
    time.sleep(1)

    while True:
        started = time.monotonic()
        total, idle = cpu_times()
        d_total, d_idle = total - prev_cpu[0], idle - prev_cpu[1]
        usage = 100 * (1 - d_idle / d_total) if d_total > 0 else 0
        prev_cpu = (total, idle)

        temp_raw = read_int(temp_path) if temp_path else None
        rx, tx = net_totals()
        dt = max(started - prev_t, 0.001)
        down = max(0, rx - prev_net[0]) / 1048576 / dt
        up = max(0, tx - prev_net[1]) / 1048576 / dt
        prev_net, prev_t = (rx, tx), started

        g = gpu.stats()
        ram, ram_p = ram_info()
        disk, disk_p = disk_info("/")
        bat, _ = battery()
        uptime = duration(float((read("/proc/uptime", "0") or "0").split()[0]))
        emit({
            "cpu_title": cpu_name,
            "cpu_use": f"{usage:.0f}%", "cpu_p": round(usage),
            "cpu_clock": clock_text(cpu_clock_mhz()),
            "cpu_temp": f"{temp_raw / 1000:.0f}°C" if temp_raw is not None else NA,
            "uptime": uptime,
            "gpu_title": gpu.title,
            "gpu_use": g["use"], "gpu_temp": g["temp"],
            "gpu_clock": g["clock"],
            "has_vram": g["vram"] is not None, "gpu_vram": g["vram"] or "",
            "ram": ram, "ram_p": round(ram_p),
            "disk": disk, "disk_p": round(disk_p),
            "has_battery": bool(bat), "battery": bat,
            "down": f"{down:.2f} MB/s",
            "up": f"{up:.2f} MB/s",
        })
        time.sleep(max(0.2, 1 - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
