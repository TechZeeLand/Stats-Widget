#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stats Widget settings window  (run:  stats-widget config).
Edits the same config.toml you could edit by hand, then applies it to the running widget."""
import json
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from apply_config import apply  # noqa: E402
from common import (ANCHORS, DEFAULT_H, DEFAULT_W, LAYERS, MAX_SCALE, MAX_STORAGE, MIN_SCALE, PC_SHOW_KEYS,  # noqa: E402
                    SHOW_KEYS, WEEKDAYS, clean_list, config_path, load_config, reload_widget, rnd, save_config,
                    storage_pairs, week_start, weekend_days, widget_size)
from server import fetch, server_params  # noqa: E402

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SHOW_LABELS = {"uptime": "Uptime", "cpu_clock": "CPU clock", "cpu": "CPU usage", "temp": "Temperature",
               "ram": "RAM", "swap": "Swap", "system": "System disk", "storage": "Storage pools",
               "network": "Network speed"}
PC_SHOW_LABELS = {"cpu": "CPU usage", "cpu_clock": "CPU clock", "cpu_temp": "CPU temperature", "uptime": "Uptime",
                  "gpu_use": "GPU usage & clock", "gpu_temp": "GPU temperature", "vram": "VRAM (own-memory cards)",
                  "ram": "RAM", "disk": "Disk", "battery": "Battery (laptops)", "network": "Network speed"}

HERE = Path(__file__).resolve().parent


def spin(value, lo, hi, step=1, digits=0):
    s = Gtk.SpinButton.new_with_range(lo, hi, step)
    s.set_digits(digits)
    s.set_value(value)
    return s


def combo(options, current):
    c = Gtk.ComboBoxText()
    for o in options:
        c.append_text(o)
    c.set_active(options.index(current) if current in options else 0)
    return c


def scrolled(child):
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.add(child)
    return sw


def page(rows):
    """rows = [(label, widget, hint-or-None)] -> a tidy 2-column form."""
    grid = Gtk.Grid(column_spacing=14, row_spacing=10, margin=18)
    for r, (label, widget, hint) in enumerate(rows):
        lab = Gtk.Label(label=label, xalign=1)
        grid.attach(lab, 0, r * 2, 1, 1)
        widget.set_hexpand(True)
        grid.attach(widget, 1, r * 2, 1, 1)
        if hint:
            h = Gtk.Label(label=hint, xalign=0)
            h.get_style_context().add_class("dim-label")
            h.set_line_wrap(True)
            grid.attach(h, 1, r * 2 + 1, 1, 1)
    return grid


class Settings(Gtk.Window):
    def __init__(self):
        super().__init__(title="Stats Widget – Settings")
        self.set_default_size(660, 620)
        self.set_border_width(0)
        self.cfg = load_config()
        c = self.cfg
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(box)
        nb = Gtk.Notebook()
        box.pack_start(nb, True, True, 0)
        nb.append_page(scrolled(self.server_page(c)), Gtk.Label(label="Server"))
        nb.append_page(scrolled(self.server_data_page(c)), Gtk.Label(label="Server data"))
        nb.append_page(scrolled(self.pc_data_page(c)), Gtk.Label(label="PC data"))
        nb.append_page(scrolled(self.weather_page(c)), Gtk.Label(label="Weather"))
        nb.append_page(scrolled(self.look_page(c)), Gtk.Label(label="Look & Size"))
        nb.append_page(scrolled(self.position_page(c)), Gtk.Label(label="Position"))

        bar = Gtk.Box(spacing=8, margin=12)
        self.status = Gtk.Label(label=f"Config file: {config_path()}", xalign=0)
        self.status.get_style_context().add_class("dim-label")
        bar.pack_start(self.status, True, True, 0)
        for text, cb in (("Cancel", lambda *_: self.destroy()), ("Save && Apply", self.on_save)):
            b = Gtk.Button(label=text.replace("&&", "&"))
            b.connect("clicked", cb)
            if text.startswith("Save"):
                b.get_style_context().add_class("suggested-action")
            bar.pack_end(b, False, False, 0)
        box.pack_start(bar, False, False, 0)
        self.connect("destroy", Gtk.main_quit)

    # ───────────── Server ─────────────
    def server_page(self, c):
        s = c["server"]
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=18)
        intro = Gtk.Label(xalign=0, wrap=True, label=(
            "Addresses of your server's stats.php, in order of preference. The first that answers is used; "
            "while a later one is active, the first is re-checked regularly, so the widget switches back "
            "when you are home again."))
        outer.pack_start(intro, False, False, 0)

        self.store = Gtk.ListStore(str, str, str)       # label, url, test result
        labels = list(s["labels"]) + [""] * len(s["urls"])
        for i, url in enumerate(s["urls"]):
            self.store.append([labels[i], url, ""])
        tree = Gtk.TreeView(model=self.store)
        self.tree = tree
        for idx, title, expand in ((0, "Name", False), (1, "stats.php address", True), (2, "Test", False)):
            r = Gtk.CellRendererText(editable=(idx < 2))
            if idx < 2:
                r.connect("edited", self.on_cell_edited, idx)
            col = Gtk.TreeViewColumn(title, r, text=idx)
            col.set_expand(expand)
            col.set_resizable(True)
            tree.append_column(col)
        sc = Gtk.ScrolledWindow(min_content_height=100)
        sc.add(tree)
        sc.set_shadow_type(Gtk.ShadowType.IN)
        outer.pack_start(sc, True, True, 0)

        btns = Gtk.Box(spacing=6)
        for text, cb in (("Add", self.on_add), ("Remove", self.on_remove), ("Move up", lambda *_: self.on_move(-1)),
                         ("Move down", lambda *_: self.on_move(1)), ("Test all", self.on_test)):
            b = Gtk.Button(label=text)
            b.connect("clicked", cb)
            btns.pack_start(b, False, False, 0)
        outer.pack_start(btns, False, False, 0)

        self.token = Gtk.Entry(text=s["token"], visibility=False, placeholder_text="(none)")
        self.interval = spin(float(s["interval"]), 0.5, 60, 0.5, 1)
        self.timeout = spin(float(s["timeout"]), 0.5, 10, 0.5, 1)
        self.retry = spin(int(s["retry_primary"]), 5, 600, 5)
        outer.pack_start(page([
            ("Access key", self.token, "Only needed if you set 'token' in stats.config.php on the server."),
            ("Refresh every (s)", self.interval, None),
            ("Address timeout (s)", self.timeout, "How long to wait before an address counts as down."),
            ("Re-check home every (s)", self.retry, "While on a fallback address."),
        ]), False, False, 0)
        return outer

    def on_cell_edited(self, _r, path, text, idx):
        self.store[path][idx] = text.strip()

    def on_add(self, _b):
        it = self.store.append(["New", "http://", ""])
        self.tree.set_cursor(self.store.get_path(it), self.tree.get_column(1), True)

    def on_remove(self, _b):
        model, it = self.tree.get_selection().get_selected()
        if it:
            model.remove(it)

    def on_move(self, d):
        model, it = self.tree.get_selection().get_selected()
        if not it:
            return
        i = model.get_path(it)[0]
        j = i + d
        if 0 <= j < len(model):
            model.swap(it, model.get_iter(j))

    def on_test(self, _b):
        token, timeout = self.token.get_text(), float(self.timeout.get_value())
        for row in self.store:
            row[2] = "…"
        params = server_params(self.collect_server_data())
        for i, row in enumerate(self.store):
            threading.Thread(target=self._test_one, args=(i, row[1], token, timeout, params), daemon=True).start()

    def _test_one(self, i, url, token, timeout, params):
        try:
            d = fetch(url, token, timeout, params)
            d = d if isinstance(d, dict) else {}
            msg = f"✓ {d.get('host', 'ok')}"
            pools = d.get("storage") if isinstance(d.get("storage"), list) else None
            if params and d.get("client_config") is not True:
                msg += "  (server ignores the Server data settings)"
            elif pools is not None:
                missing = [p for p in pools if isinstance(p, dict) and not p.get("ok")]
                msg += f"  ({len(pools) - len(missing)} storage found" + (f", {len(missing)} missing)" if missing else ")")
            elif d.get("raid", {}).get("present", True) is not False and not d.get("raid", {}).get("ok", True):
                msg += "  (RAID: not found)"
        except Exception as exc:
            msg = "✗ " + str(getattr(exc, "reason", exc))[:40]
        GLib.idle_add(lambda: self.store[i].__setitem__(2, msg) if i < len(self.store) else None)

    # ───────────── Server data ─────────────
    def server_data_page(self, c):
        s = c["server"]
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=18)
        intro = Gtk.Label(xalign=0, wrap=True, label=(
            "What the Server column shows. The paths below are sent to stats.php with every request, so you do not "
            "have to edit anything on the server (unless its admin switched allow_client_config off). "
            "Leave a list empty to use whatever the server itself is set up for."))
        outer.pack_start(intro, False, False, 0)

        head = Gtk.Label(xalign=0, wrap=True, use_markup=True, label=(
            f"<b>Storage pools</b> - RAID arrays, ZFS pools, data disks … (up to {MAX_STORAGE}). "
            "Each row is a folder on the server (where the pool is mounted). Leave the list empty to let the server "
            "decide / detect. More than one row makes the widget shrink a little so everything still fits."))
        outer.pack_start(head, False, False, 0)
        self.sstore = Gtk.ListStore(str, str)           # name ("" = automatic), path on the server
        for label, path in storage_pairs(c):
            self.sstore.append([label, path])
        self.stree = Gtk.TreeView(model=self.sstore)
        for idx, title, expand in ((0, "Name (optional)", False), (1, "Path on the server", True)):
            r = Gtk.CellRendererText(editable=True)
            r.connect("edited", lambda _r, path, text, i=idx: self.sstore[path].__setitem__(i, text.strip()))
            col = Gtk.TreeViewColumn(title, r, text=idx)
            col.set_expand(expand)
            col.set_resizable(True)
            self.stree.append_column(col)
        sc = Gtk.ScrolledWindow(min_content_height=90)
        sc.add(self.stree)
        sc.set_shadow_type(Gtk.ShadowType.IN)
        outer.pack_start(sc, True, True, 0)
        btns = Gtk.Box(spacing=6)
        for text, cb in (("Add", self.on_s_add), ("Remove", self.on_s_remove), ("Move up", lambda *_: self.on_s_move(-1)),
                         ("Move down", lambda *_: self.on_s_move(1)), ("Find on server…", self.on_find)):
            b = Gtk.Button(label=text)
            b.connect("clicked", cb)
            btns.pack_start(b, False, False, 0)
        outer.pack_start(btns, False, False, 0)

        self.show_switches = {}
        outer.pack_start(Gtk.Label(xalign=0, use_markup=True, label="<b>Rows to show</b>"), False, False, 0)
        grid = Gtk.Grid(column_spacing=22, row_spacing=6, margin_start=6)
        for n, key in enumerate(SHOW_KEYS):
            box = Gtk.CheckButton(label=SHOW_LABELS[key], active=bool(s.get(f"show_{key}", True)))
            self.show_switches[key] = box
            grid.attach(box, n % 3, n // 3, 1, 1)
        outer.pack_start(grid, False, False, 0)

        self.srv_name = Gtk.Entry(text=str(s.get("name", "")), placeholder_text="the server's own hostname")
        self.sys_label = Gtk.Entry(text=s["system_label"])
        self.sys_path = Gtk.Entry(text=s["system_path"], placeholder_text="server default (normally /)")
        self.nics = Gtk.Entry(text=", ".join(clean_list(s["net_interfaces"])), placeholder_text="all physical network cards")
        outer.pack_start(page([
            ("Server name", self.srv_name, "Shown in the first title bar instead of the hostname."),
            ("System disk name", self.sys_label, "Shown as e.g. “System:”."),
            ("System disk path", self.sys_path, "Folder on the server whose disk is shown as the system disk."),
            ("Network cards", self.nics, "Comma separated, e.g. enp3s0, enp4s0. Speeds are summed."),
        ]), False, False, 0)

        return outer

    def on_s_add(self, _b):
        if len(self.sstore) >= MAX_STORAGE:
            self.status.set_text(f"At most {MAX_STORAGE} storage rows.")
            return
        it = self.sstore.append(["", "/"])
        self.stree.set_cursor(self.sstore.get_path(it), self.stree.get_column(1), True)

    def on_s_remove(self, _b):
        model, it = self.stree.get_selection().get_selected()
        if it:
            model.remove(it)

    def on_s_move(self, d):
        model, it = self.stree.get_selection().get_selected()
        if not it:
            return
        i = model.get_path(it)[0]
        j = i + d
        if 0 <= j < len(model):
            model.swap(it, model.get_iter(j))

    def collect_server_data(self):
        """The current (unsaved) Server data settings, as a [server] dict - used by Test and Find."""
        pairs = [(r[0].strip(), r[1].strip()) for r in self.sstore if r[1].strip()][:MAX_STORAGE]
        return {"storage_paths": [p for _l, p in pairs], "storage_labels": [l for l, _p in pairs],
                "system_path": self.sys_path.get_text().strip(),
                "net_interfaces": [n for n in clean_list(self.nics.get_text()) if n]}

    def on_find(self, _b):
        urls = [r[1] for r in self.store if r[1].strip()]
        token, timeout = self.token.get_text(), float(self.timeout.get_value())
        self.status.set_text("Asking the server which disks it can see…")

        def work():
            for url in urls:
                try:
                    data = fetch(url, token, timeout)          # no parameters: show what the server sees by itself
                    GLib.idle_add(self.show_disks, data.get("disks") if isinstance(data, dict) else None)
                    return
                except Exception:
                    continue
            GLib.idle_add(self.status.set_text, "No server address answered.")
        threading.Thread(target=work, daemon=True).start()

    def show_disks(self, disks):
        found = [d for d in (disks or []) if isinstance(d, dict) and not d.get("system") and d.get("mount")]
        if not found:
            self.status.set_text("The server reports no disk besides the system disk "
                                 "(with Docker: mount the pool into the container first).")
            return
        self.status.set_text(f"Config file: {config_path()}")
        dlg = Gtk.Dialog(title="Disks found on the server", transient_for=self, modal=True)
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dlg.add_button("Add selected", Gtk.ResponseType.OK)
        dlg.set_default_size(480, 320)
        have = {r[1] for r in self.sstore}
        store = Gtk.ListStore(bool, str, str)
        for d in found:
            kind = "RAID / pool" if d.get("array") else d.get("fs", "")
            size = f"{d.get('used', 0):.0f} / {d.get('total', 0):.0f} GB"
            store.append([False, d["mount"], f"{kind}  ·  {size}"])
        tree = Gtk.TreeView(model=store)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", lambda _r, path: store.__setitem__(path, [not store[path][0], store[path][1], store[path][2]]))
        tree.append_column(Gtk.TreeViewColumn("Show", toggle, active=0))
        tree.append_column(Gtk.TreeViewColumn("Mount point", Gtk.CellRendererText(), text=1))
        tree.append_column(Gtk.TreeViewColumn("Type · size", Gtk.CellRendererText(), text=2))
        dlg.get_content_area().pack_start(scrolled(tree), True, True, 6)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            for ticked, mount, _info in store:
                if ticked and mount not in have and len(self.sstore) < MAX_STORAGE:
                    self.sstore.append(["", mount])
        dlg.destroy()

    # ───────────── PC data ─────────────
    def pc_data_page(self, c):
        pc = c.get("pc", {})
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=18)
        outer.pack_start(Gtk.Label(xalign=0, wrap=True, label=(
            "Choose which rows the PC Stats column shows. A block whose rows are all switched off disappears "
            "together with its heading. A hidden GPU block is not read at all (no nvidia-smi calls, a sleeping "
            "laptop GPU is left alone). Rows that do not exist on this machine (VRAM, battery) stay hidden anyway.")),
            False, False, 0)
        self.pc_switches = {}
        grid = Gtk.Grid(column_spacing=22, row_spacing=6, margin_start=6)
        for n, key in enumerate(PC_SHOW_KEYS):
            box = Gtk.CheckButton(label=PC_SHOW_LABELS[key], active=bool(pc.get(f"show_{key}", True)))
            self.pc_switches[key] = box
            grid.attach(box, n % 2, n // 2, 1, 1)
        outer.pack_start(grid, False, False, 0)
        return outer

    # ───────────── Weather ─────────────
    def weather_page(self, c):
        w = c["weather"]
        self.w_name = Gtk.Entry(text=w["display_name"])
        self.w_lat = spin(float(w["latitude"]), -90, 90, 0.01, 6)
        self.w_lon = spin(float(w["longitude"]), -180, 180, 0.01, 6)
        self.w_units = combo(["metric", "imperial"], w["units"])
        self.w_refresh = spin(int(w["refresh_minutes"]), 1, 180)
        self.w_search = Gtk.Entry(placeholder_text="Type a city, e.g. Sylhet")
        self.w_results = Gtk.ComboBoxText()
        sbtn = Gtk.Button(label="Search")
        sbtn.connect("clicked", self.on_geocode)
        self.w_search.connect("activate", self.on_geocode)
        row = Gtk.Box(spacing=6)
        row.pack_start(self.w_search, True, True, 0)
        row.pack_start(sbtn, False, False, 0)
        self.w_results.connect("changed", self.on_geo_pick)
        self.geo = []
        return page([
            ("Find city", row, "Looks the coordinates up on Open-Meteo (the same free service that provides the weather)."),
            ("", self.w_results, None),
            ("Name shown", self.w_name, None),
            ("Latitude", self.w_lat, None),
            ("Longitude", self.w_lon, None),
            ("Units", self.w_units, "metric = °C and km/h,  imperial = °F and mph"),
            ("Refresh every (min)", self.w_refresh, None),
        ])

    def on_geocode(self, _w):
        q = self.w_search.get_text().strip()
        if not q:
            return
        self.status.set_text("Searching…")

        def work():
            try:
                url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({"name": q, "count": 6})
                with urllib.request.urlopen(url, timeout=10) as r:
                    res = json.load(r).get("results") or []
                GLib.idle_add(self.show_geo, res)
            except Exception as exc:
                GLib.idle_add(self.status.set_text, f"Search failed: {exc}")
        threading.Thread(target=work, daemon=True).start()

    def show_geo(self, results):
        self.geo = results
        self.w_results.remove_all()
        for r in results:
            self.w_results.append_text(", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x))
        self.status.set_text(f"{len(results)} result(s) - pick one" if results else "No match")
        if results:
            self.w_results.set_active(0)

    def on_geo_pick(self, combo_box):
        i = combo_box.get_active()
        if 0 <= i < len(self.geo):
            r = self.geo[i]
            self.w_lat.set_value(r["latitude"])
            self.w_lon.set_value(r["longitude"])
            self.w_name.set_text(", ".join(x for x in (r.get("name"), r.get("country")) if x))

    # ───────────── Look & Size ─────────────
    def look_page(self, c):
        self.h24 = Gtk.Switch(active=bool(c["general"]["use_24h"]), halign=Gtk.Align.START)
        self.opacity = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.opacity.set_value(int(c["appearance"]["background_opacity"]))
        self.opacity.set_value_pos(Gtk.PositionType.RIGHT)

        w, h = widget_size(c)
        self._sizing = False                        # guards the three linked controls against feedback loops
        self.keep = Gtk.Switch(active=True, halign=Gtk.Align.START)
        self.scale = spin(round(100 * w / DEFAULT_W), round(100 * MIN_SCALE), round(100 * MAX_SCALE), 5)
        self.width = spin(w, rnd(DEFAULT_W * MIN_SCALE), rnd(DEFAULT_W * MAX_SCALE), 5)
        self.height = spin(h, rnd(DEFAULT_H * MIN_SCALE), rnd(DEFAULT_H * MAX_SCALE), 5)
        self.keep.set_active(abs(w / DEFAULT_W - h / DEFAULT_H) < 0.01)
        self.scale.connect("value-changed", self.on_scale)
        self.width.connect("value-changed", lambda *_: self.on_dim("w"))
        self.height.connect("value-changed", lambda *_: self.on_dim("h"))
        reset = Gtk.Button(label=f"Reset to default ({DEFAULT_W} × {DEFAULT_H})", halign=Gtk.Align.START)
        reset.connect("clicked", self.on_size_reset)
        self.week_start = combo(DAY_NAMES, DAY_NAMES[week_start(c)])
        self.weekend = [Gtk.CheckButton(label=n[:3], active=i in weekend_days(c)) for i, n in enumerate(DAY_NAMES)]
        weekend_row = Gtk.Box(spacing=10)
        for b in self.weekend:
            weekend_row.pack_start(b, False, False, 0)
        return page([
            ("24-hour clock", self.h24, "Off: 3:07    On: 15:07"),
            ("Calendar starts on", self.week_start, "The first column of the month calendar."),
            ("Weekend days", weekend_row, "Drawn in red. Countries differ: tick your own weekend (none is fine too)."),
            ("Background opacity (%)", self.opacity, "100 = solid black, lower = see-through."),
            ("Size (%)", self.scale, f"100 % = {DEFAULT_W} × {DEFAULT_H} px. Everything inside grows or shrinks with it."),
            ("Width (px)", self.width, None),
            ("Height (px)", self.height, None),
            ("Keep proportions", self.keep, "On: width and height move together. Off: stretch the widget; text follows the smaller side."),
            ("", reset, None),
        ])

    def on_scale(self, _s):
        if self._sizing:
            return
        self._sizing = True
        f = self.scale.get_value() / 100
        self.width.set_value(rnd(DEFAULT_W * f))
        self.height.set_value(rnd(DEFAULT_H * f))
        self._sizing = False

    def on_dim(self, which):
        if self._sizing:
            return
        self._sizing = True
        w, h = self.width.get_value(), self.height.get_value()
        if self.keep.get_active():
            if which == "w":
                h = w * DEFAULT_H / DEFAULT_W
                self.height.set_value(rnd(h))
            else:
                w = h * DEFAULT_W / DEFAULT_H
                self.width.set_value(rnd(w))
        self.scale.set_value(round(100 * min(w / DEFAULT_W, h / DEFAULT_H)))
        self._sizing = False

    def on_size_reset(self, _b):
        self.keep.set_active(True)
        self.scale.set_value(100)
        self.on_scale(None)

    # ───────────── Position ─────────────
    def position_page(self, c):
        p = c["position"]
        self.anchor = combo(ANCHORS, p["anchor"])
        self.px = spin(int(p["x"]), -5000, 10000)
        self.py = spin(int(p["y"]), -5000, 10000)
        self.monitor = Gtk.Entry(text=str(p["monitor"]))
        self.layer = combo(LAYERS, p["layer"])
        drag = Gtk.Button(label="Drag to place…")
        drag.connect("clicked", self.on_drag)
        return page([
            ("Place by dragging", drag, "Opens a ghost of the widget - drag it, press Enter. Saves the position. "
                                       "(Tip: right-click the widget itself does the same.)"),
            ("Anchor", self.anchor, "Which screen corner/edge x and y are measured from."),
            ("X offset (px)", self.px, None),
            ("Y offset (px)", self.py, None),
            ("Monitor", self.monitor, "0 = first screen, 1 = second … or a name such as DP-1."),
            ("Layer (Wayland)", self.layer, "bottom = above the wallpaper, below windows. Try “bg” or “overlay” if it is hidden."),
        ])

    def on_drag(self, _b):
        self.collect()
        save_config(self.cfg)               # so the mover starts from the values shown here
        apply()
        proc = subprocess.Popen([sys.executable, str(HERE / "move.py")])
        self.hide()

        def wait():
            proc.wait()
            GLib.idle_add(self.reload_after_move)
        threading.Thread(target=wait, daemon=True).start()

    def reload_after_move(self):
        p = load_config()["position"]
        self.anchor.set_active(ANCHORS.index(p["anchor"]) if p["anchor"] in ANCHORS else 0)
        self.px.set_value(int(p["x"]))
        self.py.set_value(int(p["y"]))
        self.show_all()

    # ───────────── save ─────────────
    def collect(self):
        c = self.cfg
        c["server"].update(
            urls=[r[1] for r in self.store if r[1].strip()],
            labels=[r[0] for r in self.store if r[1].strip()],
            token=self.token.get_text(), interval=self.interval.get_value(), timeout=self.timeout.get_value(),
            retry_primary=int(self.retry.get_value()))
        pairs = [(r[0].strip(), r[1].strip()) for r in self.sstore if r[1].strip()][:MAX_STORAGE]
        c["server"].update(
            name=self.srv_name.get_text().strip(),
            system_label=self.sys_label.get_text().strip() or "System", system_path=self.sys_path.get_text().strip(),
            storage_paths=[p for _l, p in pairs], storage_labels=[l for l, _p in pairs],
            net_interfaces=[n for n in clean_list(self.nics.get_text()) if n],
            **{f"show_{k}": sw.get_active() for k, sw in self.show_switches.items()})
        c["general"].update(week_start=WEEKDAYS[max(0, self.week_start.get_active())],
                            weekend=[WEEKDAYS[i] for i, b in enumerate(self.weekend) if b.get_active()])
        c.setdefault("pc", {}).update({f"show_{k}": sw.get_active() for k, sw in self.pc_switches.items()})
        c["weather"].update(
            display_name=self.w_name.get_text(), latitude=self.w_lat.get_value(), longitude=self.w_lon.get_value(),
            units=self.w_units.get_active_text(), refresh_minutes=int(self.w_refresh.get_value()))
        c["general"]["use_24h"] = self.h24.get_active()
        c["appearance"]["background_opacity"] = int(self.opacity.get_value())
        c["appearance"].update(width=int(self.width.get_value()), height=int(self.height.get_value()))
        c["position"].update(
            anchor=self.anchor.get_active_text(), x=int(self.px.get_value()), y=int(self.py.get_value()),
            monitor=(lambda m: int(m) if m.lstrip("-").isdigit() else (m or 0))(self.monitor.get_text().strip()), layer=self.layer.get_active_text())

    def on_save(self, _b):
        self.collect()
        save_config(self.cfg)
        apply()
        reload_widget()
        self.status.set_text("Saved ✓  (the widget was reloaded)")
        GLib.timeout_add(900, self.destroy)


if __name__ == "__main__":
    win = Settings()
    win.show_all()
    Gtk.main()
