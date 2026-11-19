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
from common import (ANCHORS, DAY_CODES, DEFAULT_H, DEFAULT_W, LAYERS, MAX_SCALE, MIN_SCALE, config_path,  # noqa: E402
                    load_config, reload_widget, rnd, save_config, week_start, weekend_days, widget_size)
from server import fetch, request_params  # noqa: E402

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

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
        self.set_default_size(680, 580)
        self.set_border_width(0)
        self.cfg = load_config()
        c = self.cfg
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(box)
        nb = Gtk.Notebook()
        box.pack_start(nb, True, True, 0)
        nb.append_page(scrolled(self.server_page(c)), Gtk.Label(label="Server"))
        nb.append_page(scrolled(self.server_show_page(c)), Gtk.Label(label="Server rows"))
        nb.append_page(scrolled(self.weather_page(c)), Gtk.Label(label="Weather"))
        nb.append_page(scrolled(self.calendar_page(c)), Gtk.Label(label="Calendar"))
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

    # ───────────── Server rows (what the Server column shows) ─────────────
    def server_show_page(self, c):
        s = c["server"]
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=18)
        outer.pack_start(Gtk.Label(xalign=0, wrap=True, label=(
            "Choose what the Server column shows. This is decided here in the widget - nothing needs to be "
            "changed on the server. Disks, RAID arrays and pools are listed by the server; pick the ones you want.")),
            False, False, 0)

        def switch(key):
            return Gtk.Switch(active=bool(s.get(key, True)), halign=Gtk.Align.START)
        self.show = {k: switch(k) for k in ("show_uptime", "show_cpu", "show_clock", "show_temperature",
                                            "show_ram", "show_swap", "show_network", "show_system_disk")}
        self.srv_name = Gtk.Entry(text=s.get("name", ""), placeholder_text="(the server's own hostname)")
        self.sys_label = Gtk.Entry(text=s.get("system_label", "System"))
        self.sys_path = Gtk.Entry(text=s.get("system_path", ""), placeholder_text="(server default)")
        self.nics = Gtk.Entry(text=", ".join(s.get("net_interfaces", [])), placeholder_text="(all physical network cards)")
        self.max_rows = spin(int(s.get("max_storage_rows", 3)), 0, 8)
        self.raid_label = Gtk.Entry(text=s.get("raid_label", "RAID"))
        outer.pack_start(page([
            ("Server name", self.srv_name, "Shown in the first title bar instead of the hostname."),
            ("Uptime", self.show["show_uptime"], None),
            ("CPU usage", self.show["show_cpu"], None),
            ("CPU clock speed", self.show["show_clock"], "Current speed, averaged over all cores."),
            ("Temperature", self.show["show_temperature"], None),
            ("RAM", self.show["show_ram"], None),
            ("Swap", self.show["show_swap"], None),
            ("Network speed", self.show["show_network"], None),
            ("Network cards", self.nics, "Comma separated, e.g. enp3s0, enp4s0. Empty = all physical cards."),
        ]), False, False, 0)

        outer.pack_start(Gtk.Label(xalign=0, use_markup=True, label="<b>Storage</b>"), False, False, 0)
        outer.pack_start(page([
            ("System disk", self.show["show_system_disk"], None),
            ("System disk name", self.sys_label, None),
            ("System disk path", self.sys_path, "A mount point on the server, e.g. /. Empty = the server's default."),
        ]), False, False, 0)
        outer.pack_start(Gtk.Label(xalign=0, wrap=True, label=(
            "Extra storage rows. Leave the list EMPTY for automatic: every separate disk, RAID array or pool "
            "the server reports is shown (nothing if it only has its system disk). Or add the mount points "
            "you want, exactly as the SERVER sees them (inside Docker: the path inside the container).")),
            False, False, 0)
        self.disk_store = Gtk.ListStore(str, str)           # name, mount point
        labels = list(s.get("storage_labels", [])) + [""] * len(s.get("storage_paths", []))
        for i, path in enumerate(s.get("storage_paths", [])):
            self.disk_store.append([labels[i], path])
        self.disk_tree = Gtk.TreeView(model=self.disk_store)
        for idx, title, expand in ((0, "Name", False), (1, "Mount point on the server", True)):
            r = Gtk.CellRendererText(editable=True)
            r.connect("edited", self.on_disk_edited, idx)
            col = Gtk.TreeViewColumn(title, r, text=idx)
            col.set_expand(expand)
            col.set_resizable(True)
            self.disk_tree.append_column(col)
        sc = Gtk.ScrolledWindow(min_content_height=90)
        sc.add(self.disk_tree)
        sc.set_shadow_type(Gtk.ShadowType.IN)
        outer.pack_start(sc, True, True, 0)
        btns = Gtk.Box(spacing=6)
        for text, cb in (("Add", self.on_disk_add), ("Remove", self.on_disk_remove)):
            b = Gtk.Button(label=text)
            b.connect("clicked", cb)
            btns.pack_start(b, False, False, 0)
        outer.pack_start(btns, False, False, 0)
        outer.pack_start(page([
            ("Automatic mode: at most", self.max_rows, "Extra disks shown when the list above is empty. Each one needs about 25-50 px of height."),
            ("Automatic mode: RAID name", self.raid_label, "Name of RAID / ZFS / btrfs / mergerfs rows, e.g. “RAID:”."),
        ]), False, False, 0)
        return outer

    def on_disk_edited(self, _r, path, text, idx):
        self.disk_store[path][idx] = text.strip()

    def on_disk_add(self, _b):
        it = self.disk_store.append(["", "/"])
        self.disk_tree.set_cursor(self.disk_store.get_path(it), self.disk_tree.get_column(1), True)

    def on_disk_remove(self, _b):
        model, it = self.disk_tree.get_selection().get_selected()
        if it:
            model.remove(it)

    # ───────────── Calendar ─────────────
    def calendar_page(self, c):
        weekend, first = weekend_days(c), week_start(c)
        self.weekend_checks = []
        box = Gtk.Box(spacing=10)
        for i, name in enumerate(DAY_NAMES):
            chk = Gtk.CheckButton(label=name[:3], active=i in weekend)
            self.weekend_checks.append(chk)
            box.pack_start(chk, False, False, 0)
        self.week_first = combo(DAY_NAMES, DAY_NAMES[first])
        return page([
            ("Weekend days", box, "Drawn in red in the calendar. Not every country has the same weekend."),
            ("Week starts on", self.week_first, "The first column of the calendar."),
        ])

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
        params = request_params({"system_path": self.sys_path.get_text(), "net_interfaces": self.nics.get_text().split(",")})
        for row in self.store:
            row[2] = "…"
        for i, row in enumerate(self.store):
            threading.Thread(target=self._test_one, args=(i, row[1], token, timeout, params), daemon=True).start()

    def _test_one(self, i, url, token, timeout, params):
        try:
            d = fetch(url, token, timeout, params)
            disks = d.get("disks") if isinstance(d, dict) else None
            msg = f"✓ {d.get('host', 'ok')}" + (f" · {len(disks)} disk(s)" if isinstance(disks, list) else " · old stats.php")
        except Exception as exc:
            msg = "✗ " + str(getattr(exc, "reason", exc))[:40]
        GLib.idle_add(lambda: self.store[i].__setitem__(2, msg) if i < len(self.store) else None)

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
        return page([
            ("24-hour clock", self.h24, "Off: 3:07    On: 15:07"),
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
            retry_primary=int(self.retry.get_value()), raid_label=self.raid_label.get_text() or "RAID",
            name=self.srv_name.get_text().strip(), system_label=self.sys_label.get_text().strip() or "System",
            system_path=self.sys_path.get_text().strip(),
            storage_paths=[r[1] for r in self.disk_store if r[1].strip()],
            storage_labels=[r[0] for r in self.disk_store if r[1].strip()],
            max_storage_rows=int(self.max_rows.get_value()),
            net_interfaces=[n.strip() for n in self.nics.get_text().split(",") if n.strip()],
            **{k: sw.get_active() for k, sw in self.show.items()})
        c["weather"].update(
            display_name=self.w_name.get_text(), latitude=self.w_lat.get_value(), longitude=self.w_lon.get_value(),
            units=self.w_units.get_active_text(), refresh_minutes=int(self.w_refresh.get_value()))
        c["general"]["use_24h"] = self.h24.get_active()
        c["general"]["weekend"] = [DAY_CODES[i] for i, chk in enumerate(self.weekend_checks) if chk.get_active()]
        c["general"]["week_start"] = DAY_NAMES[self.week_first.get_active()].lower()
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
