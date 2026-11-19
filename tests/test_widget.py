# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests - run:  python3 -m unittest discover -s tests -v"""
import copy
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "widget" / "scripts"))
import common  # noqa: E402


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["STATS_WIDGET_CONFIG"] = str(Path(self.tmp.name) / "config.toml")
        self.saved_toml = common.tomllib

    def tearDown(self):
        common.tomllib = self.saved_toml
        self.tmp.cleanup()

    def test_defaults_when_missing(self):
        self.assertEqual(common.load_config(), common.DEFAULTS)

    def test_failover_defaults_are_the_agreed_addresses(self):
        urls = common.DEFAULTS["server"]["urls"]
        self.assertEqual(urls, ["http://192.168.0.123/stats.php", "http://rayaz.netbird.cloud/stats.php"])

    def test_roundtrip_both_parsers(self):
        cfg = copy.deepcopy(common.DEFAULTS)
        cfg["weather"]["display_name"] = 'Sylhet "City"'
        cfg["position"].update(x=321, y=12, anchor="bottom right", monitor="DP-1")
        cfg["server"]["urls"] = ["http://a/x.php", "http://b/y.php", "http://c/z.php"]
        cfg["general"]["use_24h"] = True
        common.save_config(cfg)
        with_tomllib = common.load_config()
        common.tomllib = None                 # force the built-in fallback parser (old Python)
        fallback = common.load_config()
        self.assertEqual(with_tomllib, fallback)
        self.assertEqual(fallback["weather"]["display_name"], 'Sylhet "City"')
        self.assertEqual(fallback["position"]["monitor"], "DP-1")
        self.assertEqual(len(fallback["server"]["urls"]), 3)

    def test_broken_file_falls_back(self):
        common.config_path().write_text("this is [not valid", encoding="utf-8")
        self.assertEqual(common.load_config(), common.DEFAULTS)

    def test_apply_config_writes_window_and_theme(self):
        import apply_config
        cfg = copy.deepcopy(common.DEFAULTS)
        cfg["position"].update(x=5, y=6, anchor="top right", monitor=1, layer="bg")
        cfg["appearance"]["background_opacity"] = 50
        common.save_config(cfg)
        apply_config.apply()
        window = (common.ROOT / "window.yuck").read_text()
        self.assertIn(':x "5px" :y "6px"', window)
        self.assertIn(':anchor "top right"', window)
        self.assertIn(":monitor 1", window)
        self.assertIn(":stacking \"bg\"", window)
        self.assertIn("$bg-opacity: 0.5;", (common.ROOT / "theme.scss").read_text())
        common.save_config(common.DEFAULTS)   # restore generated files to defaults
        apply_config.apply()


class FormatTests(unittest.TestCase):
    def test_size_pair(self):
        self.assertEqual(common.size_pair(120, 500), "120 / 500 GB")
        self.assertEqual(common.size_pair(2.14, 10.9), "2.1 / 10.9 GB")
        self.assertEqual(common.size_pair(6840, 10900), "6.7 / 10.6 TB")

    def test_duration(self):
        self.assertEqual(common.duration(59), "0m")
        self.assertEqual(common.duration(3 * 3600 + 120), "3h 2m")
        self.assertEqual(common.duration(14 * 86400 + 6 * 3600 + 56 * 60), "14d 6h 56m")

    def test_fmt(self):
        self.assertEqual(common.fmt(12.0), "12")
        self.assertEqual(common.fmt(12.35, 1), "12.3" if f"{12.35:.1f}" == "12.3" else "12.4")


class ServerLogicTests(unittest.TestCase):
    def setUp(self):
        import server
        self.server = server

    def test_raid_status(self):
        s = self.server.raid_status
        ok = {"ok": True, "arrays": [{"name": "md0", "level": "raid5", "devices": 4, "working": 4, "health": "ok"}]}
        self.assertEqual(s(ok, True)[1], "ok")
        bad = {"ok": True, "arrays": [{"name": "md0", "level": "raid5", "devices": 4, "working": 3, "health": "degraded"}]}
        text, cls = s(bad, True)
        self.assertEqual(cls, "bad")
        self.assertIn("degraded", text)
        rebuilding = {"ok": True, "arrays": [{"name": "md0", "level": "raid5", "devices": 4, "working": 3,
                                              "health": "degraded", "progress": 12.6}]}
        self.assertIn("rebuilding 12.6%", s(rebuilding, True)[0])
        self.assertEqual(s({"ok": False, "error": "x", "arrays": []}, False), ("Not reachable", "bad"))
        self.assertEqual(s({"ok": True, "arrays": []}, True), ("Online", "ok"))

    def test_build_handles_old_and_new_payloads(self):
        cfg = common.DEFAULTS["server"]
        old = {"cpu": 10, "temp": 40, "ram_u": 4, "ram_t": 16, "ram_p": 25, "raid_u": 100, "raid_t": 1000,
               "raid_p": 10, "ssd_u": 1, "ssd_t": 2, "ssd_p": 50, "net_rx": "1", "net_tx": "1"}
        out = self.server.build(old, "Home", "h", (1.0, 2.0), cfg)
        rows = {r["n"]: r for sec in out["sections"] for r in sec["rows"]}
        self.assertEqual(rows["RAID:"]["v"], "100 / 1000 GB")             # old server: single legacy RAID pool
        self.assertEqual(rows["Download:"]["v"], "1.00 Mbps")
        self.assertEqual(rows["Clock:"]["v"], "N/A")                      # old server has no clock
        new = dict(old, host="rayaz", uptime=90061, load=[0.1, 0.2, 0.3],
                   raid={"ok": False, "error": "nope", "arrays": []})
        out = self.server.build(new, "Home", "h", (0, 0), cfg)
        rows = {r["n"]: r for sec in out["sections"] for r in sec["rows"]}
        self.assertEqual(rows["RAID:"]["v"], "N/A")
        self.assertEqual(rows["Status:"]["c"], "bad")
        self.assertEqual(out["title"], "rayaz · Home")
        self.assertEqual(out["head"][0]["v"], "1d 1h 1m")

    def test_load_average_is_gone_and_clock_is_there(self):
        data = {"cpu": 5, "cpu_mhz": 3412, "load": [1, 2, 3], "ram_t": 8, "uptime": 5}
        out = self.server.build(data, "Home", "h", (0, 0), common.DEFAULTS["server"])
        names = [r["n"] for r in out["head"]] + [r["n"] for sec in out["sections"] for r in sec["rows"]]
        self.assertNotIn("Load average:", names)
        self.assertIn("3.41 GHz", [r["v"] for sec in out["sections"] for r in sec["rows"]])

    def test_every_row_can_be_switched_off(self):
        cfg = dict(common.DEFAULTS["server"], **{k: False for k in (
            "show_uptime", "show_cpu", "show_clock", "show_temperature", "show_ram", "show_swap",
            "show_network", "show_system_disk")})
        out = self.server.build({"cpu": 5, "ram_t": 8}, "Home", "h", (0, 0), cfg)
        self.assertEqual(out["head"], [])
        self.assertEqual(out["sections"], [])                  # sections without rows disappear
        cfg["show_network"] = True
        out = self.server.build({"cpu": 5, "ram_t": 8}, "Home", "h", (0, 0), cfg)
        self.assertEqual([s["t"] for s in out["sections"]], ["Network"])

    def test_offline_reads_na_everywhere(self):
        out = self.server.build(None, "", "", None, common.DEFAULTS["server"])
        self.assertFalse(out["ok"])
        for row in out["head"] + [r for sec in out["sections"] for r in sec["rows"]]:
            self.assertEqual(row["v"], "N/A", row)

    def test_custom_server_name(self):
        cfg = dict(common.DEFAULTS["server"], name="Homelab")
        out = self.server.build({"host": "rayaz", "ram_t": 8}, "Home", "h", (0, 0), cfg)
        self.assertEqual(out["title"], "Homelab · Home")

    def test_request_params(self):
        self.assertEqual(self.server.request_params({"system_path": " /data ", "net_interfaces": ["a", " b ", ""]}),
                         {"system": "/data", "net": "a,b"})
        self.assertEqual(self.server.request_params(common.DEFAULTS["server"]), {"system": "", "net": ""})


DISKS = [
    {"mount": "/", "dev": "/dev/nvme0n1p2", "fs": "ext4", "used": 212, "total": 466, "percent": 45.5, "array": False, "system": True, "md": None},
    {"mount": "/raids", "dev": "/dev/md0", "fs": "ext4", "used": 6700, "total": 10900, "percent": 61.5, "array": True, "system": False, "md": "md0"},
    {"mount": "/mnt/media", "dev": "/dev/sdf1", "fs": "ext4", "used": 100, "total": 2000, "percent": 5, "array": False, "system": False, "md": None},
]
ARRAYS = [{"name": "md0", "level": "raid1", "devices": 2, "working": 2, "health": "ok"}]


class StorageRowTests(unittest.TestCase):
    def setUp(self):
        import server
        self.server = server

    def rows(self, disks, **over):
        data = {"ram_t": 8, "ssd_u": 212, "ssd_t": 466, "ssd_p": 45.5, "disks": disks,
                "raid": {"present": True, "ok": True, "arrays": ARRAYS}}
        cfg = dict(common.DEFAULTS["server"], **over)
        out = self.server.build(data, "Home", "h", (0, 0), cfg)
        return [r for sec in out["sections"] if sec["t"] == "Storage" for r in sec["rows"]]

    def test_automatic_shows_system_then_every_other_disk(self):
        rows = self.rows(DISKS)
        self.assertEqual([r["n"] for r in rows], ["System:", "RAID:", "Status:", "media:"])
        self.assertEqual(rows[2]["c"], "ok")                       # the mdadm health line

    def test_no_raid_and_no_other_disk_means_only_the_system_row(self):
        self.assertEqual([r["n"] for r in self.rows(DISKS[:1])], ["System:"])

    def test_disk_on_the_system_disk_is_not_repeated(self):
        same = dict(DISKS[1], dev="/dev/nvme0n1p2", array=False, md=None, system=True)   # Docker bind mount of the system disk
        self.assertEqual([r["n"] for r in self.rows([DISKS[0], same])], ["System:"])

    def test_custom_list_with_labels_and_missing_path(self):
        rows = self.rows(DISKS, storage_paths=["/mnt/media", "/nope"], storage_labels=["Media"], raid_label="X")
        self.assertEqual([(r["n"], r["v"]) for r in rows[1:]], [("Media:", "0.1 / 2 TB"), ("nope:", "Not found")])
        self.assertEqual(rows[2]["c"], "bad")

    def test_custom_path_inside_a_mount_uses_that_mount(self):
        rows = self.rows(DISKS, storage_paths=["/raids/photos"], storage_labels=["Photos"])
        self.assertEqual(rows[1]["n"], "Photos:")
        self.assertEqual(rows[1]["p"], 61.5)

    def test_names_and_limits(self):
        rows = self.rows(DISKS, raid_label="Pool", system_label="OS", max_storage_rows=1)
        self.assertEqual([r["n"] for r in rows], ["OS:", "Pool:", "Status:"])     # arrays first, only 1 extra disk
        self.assertEqual([r["n"] for r in self.rows(DISKS, show_system_disk=False, max_storage_rows=0)], [])

    def test_raid_status_row_for_degraded_array(self):
        bad = [dict(ARRAYS[0], working=1, health="degraded")]
        data = {"ram_t": 8, "disks": DISKS, "raid": {"present": True, "ok": True, "arrays": bad}}
        out = self.server.build(data, "Home", "h", (0, 0), common.DEFAULTS["server"])
        status = [r for sec in out["sections"] for r in sec["rows"] if r["n"] == "Status:"][0]
        self.assertEqual(status["c"], "bad")


class RaidAndCpuNameTests(unittest.TestCase):
    def setUp(self):
        import server
        self.server = server
        self.cfg = common.DEFAULTS["server"]

    def names(self, out):
        return [r["n"] for sec in out["sections"] for r in sec["rows"]]

    def test_no_separate_pool_hides_raid_row(self):
        data = {"cpu": 1, "ram_t": 8, "cpu_name": "Intel Core i3-6100", "raid_u": 0, "raid_t": 0, "raid_p": 0,
                "raid": {"present": False, "ok": False, "error": "same disk", "arrays": []}}
        out = self.server.build(data, "Home", "h", (0, 0), self.cfg)
        self.assertNotIn("RAID:", self.names(out))
        self.assertEqual(out["sections"][0]["t"], "Intel Core i3-6100")

    def test_old_server_keeps_raid_row(self):
        out = self.server.build({"cpu": 1, "ram_t": 8, "raid_t": 100, "raid_u": 1, "raid_p": 1}, "Home", "h", (0, 0), self.cfg)
        self.assertIn("RAID:", self.names(out))
        self.assertEqual(out["sections"][0]["t"], "CPU & Memory")

    def test_real_array_keeps_row(self):
        raid = {"present": True, "ok": True, "arrays": [{"name": "md0", "level": "raid1", "devices": 2, "working": 2, "health": "ok"}]}
        out = self.server.build({"ram_t": 8, "raid_t": 1000, "raid_u": 1, "raid": raid}, "Home", "h", (0, 0), self.cfg)
        self.assertIn("RAID:", self.names(out))


class CalendarWeatherTests(unittest.TestCase):
    def test_calendar_shape_and_today(self):
        import calendar_grid
        data = calendar_grid.build(date(2026, 11, 15))
        self.assertEqual(len(data["weeks"]), 6)
        self.assertTrue(all(len(w) == 7 for w in data["weeks"]))
        self.assertEqual(data["title"], "NOVEMBER, 2026")
        today = [c for w in data["weeks"] for c in w if "today" in c["c"]]
        self.assertEqual(len(today), 1)
        self.assertEqual(today[0]["d"], "15")
        first = data["weeks"][0][0]                       # Nov 1 2026 is a Sunday
        self.assertEqual(first["d"], "1")
        self.assertEqual(data["weeks"][0][5]["c"], "wk")  # Friday = weekend
        self.assertEqual([h["t"] for h in data["heads"]], ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"])
        self.assertEqual([h["c"] for h in data["heads"]], ["", "", "", "", "", "wd-red", "wd-red"])

    def test_weekend_and_week_start_are_configurable(self):
        import calendar_grid
        cfg = {"general": {"weekend": ["Sat", "sun"], "week_start": "Monday"}}
        data = calendar_grid.build(date(2026, 11, 15), common.weekend_days(cfg), common.week_start(cfg))
        self.assertEqual([h["t"] for h in data["heads"]], ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"])
        self.assertEqual([h["c"] for h in data["heads"]].count("wd-red"), 2)
        self.assertEqual(data["heads"][5]["c"], "wd-red")
        row = data["weeks"][0]                                  # Mon 26 Oct ... Sun 1 Nov
        self.assertEqual(row[6]["d"], "1")
        self.assertEqual(row[5]["c"], "out")                    # other-month days stay grey, not red
        second = data["weeks"][1]                               # Mon 2 Nov ... Sun 8 Nov
        self.assertEqual([c["c"] for c in second], ["", "", "", "", "", "wk", "wk"])

    def test_weekend_setting_edge_cases(self):
        wk = lambda v: common.weekend_days({"general": {"weekend": v}})       # noqa: E731
        self.assertEqual(wk(["fri", "sat"]), {4, 5})
        self.assertEqual(wk(["Friday", " SAT "]), {4, 5})
        self.assertEqual(wk(["sun"]), {6})
        self.assertEqual(wk([]), set())                                       # no weekend at all
        self.assertEqual(wk(["nonsense"]), {4, 5})                            # unusable -> default
        self.assertEqual(wk("fri"), {4, 5})
        self.assertEqual(common.weekend_days({}), {4, 5})
        self.assertEqual(common.week_start({"general": {"week_start": "xyz"}}), 6)
        self.assertEqual(common.week_start({"general": {"week_start": "saturday"}}), 5)

    def test_weekend_survives_the_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STATS_WIDGET_CONFIG"] = str(Path(tmp) / "config.toml")
            cfg = copy.deepcopy(common.DEFAULTS)
            cfg["general"].update(weekend=["sat", "sun"], week_start="monday")
            cfg["server"].update(storage_paths=["/a", "/b"], storage_labels=["A", "B"], show_swap=False,
                                 net_interfaces=["eth0"], name="Lab")
            common.save_config(cfg)
            for parser_off in (False, True):
                if parser_off:
                    common.tomllib = None
                back = common.load_config()
                self.assertEqual(back["general"]["weekend"], ["sat", "sun"])
                self.assertEqual(back["server"]["storage_paths"], ["/a", "/b"])
                self.assertFalse(back["server"]["show_swap"])
                self.assertEqual(back["server"]["name"], "Lab")
            common.tomllib = __import__("tomllib")

    def test_every_weather_glyph_is_in_the_bundled_font(self):
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            self.skipTest("fontTools not installed")
        import weather
        font = TTFont(str(common.ROOT / "fonts" / "MaterialIconsOutlined-Regular.otf"))
        cmap, rev = font.getBestCmap(), {}
        for cp, name in cmap.items():
            rev.setdefault(name, chr(cp))
        ligatures = set()
        for lookup in font["GSUB"].table.LookupList.Lookup:
            for st in lookup.SubTable:
                st = getattr(st, "ExtSubTable", st)
                for first, ligs in getattr(st, "ligatures", {}).items():
                    for lig in ligs:
                        try:
                            ligatures.add(rev[first] + "".join(rev[c] for c in lig.Component))
                        except KeyError:
                            pass
        used = set(weather.ARROWS) | {g for pair in weather.GLYPHS.values() for g in pair}
        used |= {"wb_twilight", "arrow_upward", "arrow_downward", "water_drop", "umbrella", "place"}
        self.assertEqual(sorted(g for g in used if g not in ligatures), [])
        for _code, (_text, base) in weather.WMO.items():
            self.assertIn(base, weather.GLYPHS)

    def test_wind_arrow_points_downwind(self):
        import weather
        self.assertEqual(weather.wind_arrow(0), "south")        # north wind blows towards the south
        self.assertEqual(weather.wind_arrow(270), "east")       # west wind blows towards the east
        self.assertEqual(weather.wind_arrow(359), "south")


class PcStatsTests(unittest.TestCase):
    def fake_sys(self, tmp, khz_list):
        for i, khz in enumerate(khz_list):
            d = Path(tmp) / "devices" / "system" / "cpu" / f"cpu{i}" / "cpufreq"
            d.mkdir(parents=True)
            (d / "scaling_cur_freq").write_text(f"{khz}\n")

    def test_cpu_clock_is_the_average_of_all_cores(self):
        import pcstats
        with tempfile.TemporaryDirectory() as tmp:
            self.fake_sys(tmp, [800000, 3200000, 2000000, 2000000])
            self.assertEqual(pcstats.cpu_clock_mhz(tmp, tmp), 2000.0)

    def test_cpu_clock_falls_back_to_cpuinfo(self):
        import pcstats
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "cpuinfo").write_text("processor : 0\ncpu MHz\t\t: 1000.000\nprocessor : 1\ncpu MHz\t\t: 3000.000\n")
            self.assertEqual(pcstats.cpu_clock_mhz(tmp, tmp), 2000.0)
            self.assertIsNone(pcstats.cpu_clock_mhz("/nonexistent", "/nonexistent"))

    def test_clock_text(self):
        self.assertEqual(common.clock_text(2000), "2.00 GHz")
        self.assertEqual(common.clock_text(798.6), "799 MHz")
        self.assertEqual(common.clock_text(None), "N/A")

    def amd_card(self, tmp, total, maker=None):
        Path(tmp, "mem_info_vram_total").write_text(str(total))
        Path(tmp, "mem_info_vram_used").write_text(str(total // 4))
        if maker:
            Path(tmp, "mem_info_vram_vendor").write_text(maker)
        out = {"use": "N/A", "temp": "N/A", "vram": None, "clock": "N/A"}
        import pcstats
        pcstats.GPU._amd(tmp, out)
        return out

    def test_vram_only_for_cards_with_their_own_memory(self):
        gib = 1024 ** 3
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2, tempfile.TemporaryDirectory() as t3:
            self.assertEqual(self.amd_card(t1, 8 * gib, "samsung")["vram"], "2.00 GB / 8 GB")   # discrete card
            self.assertIsNone(self.amd_card(t2, 512 * 1024 ** 2, "unknown")["vram"])             # APU: shares system RAM
            self.assertIsNotNone(self.amd_card(t3, 4 * gib)["vram"])                             # no vendor file, 4 GB: card

    def test_intel_igpu_has_no_vram(self):
        import pcstats
        gpu = pcstats.GPU.__new__(pcstats.GPU)
        gpu.card, gpu.vendor, gpu.last_rc6 = "/nonexistent", "0x8086", None
        self.assertIsNone(gpu.stats()["vram"])
        gpu.vendor = "0x10de"                                    # NVIDIA: always has memory (shows N/A if unreadable)
        self.assertIsNotNone(gpu.stats()["vram"])


class SizeTests(unittest.TestCase):
    def setUp(self):
        import apply_config
        self.ac = apply_config
        self.tpl = (common.ROOT / "eww.yuck.in").read_text(encoding="utf-8")

    def test_default_size_keeps_the_original_numbers(self):
        out = self.ac.render_layout(self.tpl, 795, 475)
        for expected in (":width 249", ":width 265", ":width 261", ":height 108", ":width 37 :height 22"):
            self.assertIn(expected, out)

    def test_layout_is_data_driven(self):
        self.assertNotIn("Load average", self.tpl)
        self.assertNotIn('"FRI"', self.tpl)
        for needle in ("{server.sections}", "{cal.heads}", "{pc.cpu_clock}", "{pc.has_vram}"):
            self.assertIn(needle, self.tpl)

    def test_no_placeholder_left_and_parentheses_balance(self):
        for w, h in ((795, 475), (400, 238), (2385, 1425), (1000, 475)):
            out = self.ac.render_layout(self.tpl, w, h)
            self.assertNotIn("{{", out)
            depth, in_str, esc = 0, False, False
            for ch in out:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = not in_str
                elif not in_str:
                    depth += (ch == "(") - (ch == ")")
            self.assertEqual(depth, 0, (w, h))

    def test_columns_fill_the_window_exactly(self):
        import re
        for w, h in ((795, 475), (1000, 600), (643, 311), (400, 238)):
            out = self.ac.render_layout(self.tpl, w, h)
            cols = [int(x) for x in re.findall(r"space-evenly false :width (\d+)", out)[:3]]
            border = common.rnd(self.ac.BORDER * min(w / 795, h / 475))
            self.assertEqual(sum(cols) + 2 * border, w)

    def test_scaling_doubles_sizes(self):
        out = self.ac.render_layout(self.tpl, 1590, 950)
        self.assertIn(":width 110 :height 110", out)             # the seconds box, 55 x 55 by default

    def test_size_is_clamped(self):
        cfg = {"appearance": {"width": 10, "height": 99999}}
        self.assertEqual(common.widget_size(cfg), (398, 1425))
        self.assertEqual(common.widget_size({"appearance": {"width": "x"}}), (795, 475))
        self.assertEqual(common.widget_size(common.DEFAULTS), (795, 475))

    def test_size_roundtrips_and_reaches_the_generated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STATS_WIDGET_CONFIG"] = str(Path(tmp) / "config.toml")
            cfg = copy.deepcopy(common.DEFAULTS)
            cfg["appearance"].update(width=1000, height=597)
            common.save_config(cfg)
            self.assertEqual(common.widget_size(common.load_config()), (1000, 597))
            self.ac.apply()
            self.assertIn(':width "1000px" :height "597px"', (common.ROOT / "window.yuck").read_text())
            self.assertIn("$sx: 1.257862;", (common.ROOT / "theme.scss").read_text())
            common.save_config(common.DEFAULTS)                   # restore generated files
            self.ac.apply()


if __name__ == "__main__":
    unittest.main()
