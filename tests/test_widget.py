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
        old = {"cpu": 10, "temp": 40, "ram_u": 4, "ram_t": 16, "ram_p": 25, "raid_u": 100, "raid_t": 1000,
               "raid_p": 10, "ssd_u": 1, "ssd_t": 2, "ssd_p": 50, "net_rx": "1", "net_tx": "1"}
        out = self.server.build(old, "Home", "h", (1.0, 2.0), "RAID")
        self.assertEqual(out["raid"], "100 / 1000 GB")
        self.assertEqual(out["down"], "1.00 Mbps")
        new = dict(old, host="rayaz", uptime=90061, load=[0.1, 0.2, 0.3],
                   raid={"ok": False, "error": "nope", "arrays": []})
        out = self.server.build(new, "Home", "h", (0, 0), "RAID")
        self.assertEqual(out["raid"], "N/A")
        self.assertEqual(out["raid_cls"], "bad")
        self.assertEqual(out["title"], "rayaz · Home")
        self.assertEqual(out["uptime"], "1d 1h 1m")


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


class SizeTests(unittest.TestCase):
    def setUp(self):
        import apply_config
        self.ac = apply_config
        self.tpl = (common.ROOT / "eww.yuck.in").read_text(encoding="utf-8")

    def test_default_size_keeps_the_original_numbers(self):
        out = self.ac.render_layout(self.tpl, 795, 475)
        for expected in (":width 249", ":width 265", ":width 261", ":height 108", ":width 37 :height 22"):
            self.assertIn(expected, out)

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
