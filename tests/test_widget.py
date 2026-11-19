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


SCFG = {"labels": [], "system_label": "System", "storage_paths": [], "storage_labels": ["RAID"],
        "show_storage": True, "net_interfaces": [], "system_path": ""}


class ServerLogicTests(unittest.TestCase):
    def setUp(self):
        import server
        self.server = server

    def test_raid_status(self):
        s = self.server.raid_status
        ok = {"ok": True, "arrays": [{"name": "md0", "level": "raid5", "devices": 4, "working": 4, "health": "ok"}]}
        self.assertEqual(s(ok, True), ("raid5 · 4/4 disks · healthy", "ok"))
        bad = {"ok": True, "arrays": [{"name": "md0", "level": "raid5", "devices": 4, "working": 3, "health": "degraded"}]}
        text, cls = s(bad, True)
        self.assertEqual(cls, "bad")
        self.assertIn("degraded", text)
        rebuilding = {"ok": True, "arrays": [{"name": "md0", "level": "raid5", "devices": 4, "working": 3,
                                              "health": "degraded", "progress": 12.6}]}
        self.assertIn("rebuilding 12.6%", s(rebuilding, True)[0])
        self.assertEqual(s({"ok": False, "error": "x", "arrays": []}, False), ("Not reachable", "bad"))
        self.assertEqual(s({"ok": True, "arrays": []}, True), ("Online", "ok"))

    def test_old_v2_payload_still_works(self):
        old = {"cpu": 10, "temp": 40, "ram_u": 4, "ram_t": 16, "ram_p": 25, "raid_u": 100, "raid_t": 1000,
               "raid_p": 10, "ssd_u": 1, "ssd_t": 2, "ssd_p": 50, "net_rx": "1", "net_tx": "1"}
        out = self.server.build(old, "Home", "h", (1.0, 2.0), SCFG)
        self.assertEqual([r["val"] for r in out["storage"]], ["100 / 1000 GB"])
        self.assertEqual(out["storage"][0]["name"], "RAID:")          # the migrated v0.3 label
        self.assertEqual(out["down"], "1.00 Mbps")
        self.assertEqual(out["clock"], "N/A")                          # old server: no cpu_mhz
        new = dict(old, host="rayaz", uptime=90061, raid={"ok": False, "error": "nope", "arrays": []})
        out = self.server.build(new, "Home", "h", (0, 0), SCFG)
        self.assertEqual(out["storage"][0]["val"], "N/A")
        self.assertEqual(out["storage"][0]["cls"], "bad")
        self.assertEqual(out["title"], "rayaz · Home")
        self.assertEqual(out["uptime"], "1d 1h 1m")

    def test_no_separate_pool_hides_storage_rows(self):
        data = {"cpu": 1, "ram_t": 8, "cpu_name": "Intel Core i3-6100", "raid_u": 0, "raid_t": 0, "raid_p": 0,
                "raid": {"present": False, "ok": False, "error": "same disk", "arrays": []}}
        out = self.server.build(data, "Home", "h", (0, 0), SCFG)
        self.assertEqual(out["storage"], [])
        self.assertEqual(out["cpu_name"], "Intel Core i3-6100")

    def test_load_average_is_gone_and_cpu_clock_is_there(self):
        out = self.server.build({"ram_t": 8, "load": [1, 2, 3], "cpu_mhz": 2840, "cpu_mhz_max": 4600}, "H", "h", (0, 0), SCFG)
        self.assertNotIn("load", out)
        self.assertEqual(out["clock"], "2.84 / 4.60 GHz")

    def test_two_pools_with_names_and_health(self):
        data = {"ram_t": 8, "storage": [
            {"path": "/raids", "kind": "raid", "ok": True, "used": 6840, "total": 10900, "percent": 62.8,
             "md": {"name": "md0", "level": "raid5", "devices": 4, "working": 3, "health": "degraded"}},
            {"path": "/mnt/media", "kind": "disk", "ok": True, "used": 50, "total": 500, "percent": 10, "md": None},
            {"path": "/gone", "kind": "disk", "ok": False, "error": "x", "used": 0, "total": 0, "percent": 0, "md": None}]}
        cfg = dict(SCFG, storage_paths=["/raids", "/mnt/media", "/gone"], storage_labels=["Main RAID", "", "Backup"])
        rows = self.server.build(data, "H", "h", (0, 0), cfg)["storage"]
        self.assertEqual([r["name"] for r in rows], ["Main RAID:", "media:", "Backup:"])
        self.assertEqual((rows[0]["cls"], rows[1]["status"], rows[2]["status"]), ("bad", "", "Not reachable"))
        # only as many rows as paths were listed (the layout was sized for that)
        one = self.server.build(data, "H", "h", (0, 0), dict(cfg, storage_paths=["/raids"], storage_labels=[]))["storage"]
        self.assertEqual(len(one), 1)

    def test_storage_can_be_switched_off(self):
        data = {"ram_t": 8, "raid_t": 100, "raid_u": 1, "raid_p": 1}
        out = self.server.build(data, "H", "h", (0, 0), dict(SCFG, show_storage=False, show_swap=False))
        self.assertEqual(out["storage"], [])
        self.assertFalse(out["show_swap"])
        self.assertTrue(out["show_uptime"])

    def test_params_sent_to_the_server(self):
        self.assertEqual(self.server.server_params(SCFG), {})        # nothing configured -> server decides
        p = self.server.server_params(dict(SCFG, storage_paths=["/a", "/b c"], system_path="/", net_interfaces=["eth0"]))
        self.assertEqual(p, {"paths[]": ["/a", "/b c"], "system": "/", "nic[]": ["eth0"]})


class ConfigFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["STATS_WIDGET_CONFIG"] = str(Path(self.tmp.name) / "config.toml")

    def tearDown(self):
        self.tmp.cleanup()

    def test_v03_raid_label_is_migrated(self):
        common.config_path().write_text('[server]\nraid_label = "Tank"\n', encoding="utf-8")
        self.assertEqual(common.load_config()["server"]["storage_labels"], ["Tank"])

    def test_new_settings_roundtrip_both_parsers(self):
        cfg = copy.deepcopy(common.DEFAULTS)
        cfg["general"].update(week_start="mon", weekend=["sat", "sun"])
        cfg["server"].update(storage_paths=["/raids", "/mnt/media"], storage_labels=["RAID", ""], show_swap=False,
                             net_interfaces=["enp3s0"], system_path="/", system_label="Root")
        common.save_config(cfg)
        a = common.load_config()
        saved = common.tomllib
        common.tomllib = None
        try:
            b = common.load_config()
        finally:
            common.tomllib = saved
        self.assertEqual(a, b)
        self.assertEqual(a["server"]["storage_paths"], ["/raids", "/mnt/media"])
        self.assertIs(a["server"]["show_swap"], False)
        self.assertEqual(common.weekend_days(a), {5, 6})
        self.assertEqual(common.week_start(a), 0)

    def test_weekend_parsing_is_forgiving(self):
        self.assertEqual(common.weekend_days({"general": {"weekend": ["Friday", "SAT", "nonsense"]}}), {4, 5})
        self.assertEqual(common.weekend_days({"general": {"weekend": []}}), set())
        self.assertEqual(common.weekend_days({"general": {"weekend": "fri, sat"}}), {4, 5})
        self.assertEqual(common.week_start({"general": {"week_start": "bogus"}}), 6)

    def test_design_height(self):
        d = copy.deepcopy(common.DEFAULTS)
        self.assertEqual(common.design_height(d), 475)                      # default layout is untouched
        d["server"]["storage_paths"] = ["/a", "/b"]
        self.assertGreater(common.design_height(d), 475)                    # an extra pool needs room
        d["server"].update(show_swap=False, show_network=False, show_temp=False)
        self.assertEqual(common.design_height(d), 475)                      # hiding rows gives it back

    def test_clock_format(self):
        self.assertEqual(common.clock_pair(2840, 4600), "2.84 / 4.60 GHz")
        self.assertEqual(common.clock_pair(800), "800 MHz")
        self.assertEqual(common.clock_pair(0), "N/A")
        self.assertEqual(common.clock_pair(3000, 2900), "3.00 GHz")        # never "current / smaller max"


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
        self.assertEqual([h["n"] for h in data["heads"]], ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"])
        self.assertEqual([h["n"] for h in data["heads"] if h["c"]], ["FRI", "SAT"])

    def test_calendar_other_weekend_and_week_start(self):
        import calendar_grid
        data = calendar_grid.build(date(2026, 11, 15), 0, {5, 6})          # Monday first, Sat + Sun weekend
        self.assertEqual([h["n"] for h in data["heads"]], ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"])
        self.assertEqual([h["n"] for h in data["heads"] if h["c"]], ["SAT", "SUN"])
        days = {c["d"]: c["c"] for w in data["weeks"] for c in w if "out" not in c["c"]}
        self.assertEqual(days["1"], "wk")                                  # Sun 1 Nov
        self.assertEqual(days["6"], "")                                    # Fri 6 Nov is a working day now
        self.assertEqual(days["7"], "wk")
        none = calendar_grid.build(date(2026, 11, 15), 6, set())
        self.assertFalse(any("wk" in c["c"] for w in none["weeks"] for c in w))

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

    def test_extra_storage_rows_shrink_the_layout_instead_of_overflowing(self):
        cfg = copy.deepcopy(common.DEFAULTS)
        cfg["server"]["storage_paths"] = ["/a", "/b"]
        design_h = common.design_height(cfg)
        self.assertGreater(design_h, 475)
        sx, sy, sf = self.ac.factors(795, 475, design_h)
        self.assertEqual(sx, 1.0)
        self.assertLess(sy, 1.0)
        self.assertEqual(sf, sy)                                   # text follows, so nothing is cut off
        self.assertEqual(self.ac.factors(795, 475), (1.0, 1.0, 1.0))
        self.assertNotIn("{{", self.ac.render_layout(self.tpl, 795, 475, design_h))

    def test_layout_has_no_load_average_and_has_dynamic_calendar_header(self):
        self.assertNotIn("Load average", self.tpl)
        self.assertIn("server.clock", self.tpl)
        self.assertIn("{cal.heads}", self.tpl)

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


class PcToggleTests(unittest.TestCase):
    """The PC Stats column: one switch per row, saved in [pc], applied by pcstats.py and the layout."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["STATS_WIDGET_CONFIG"] = str(Path(self.tmp.name) / "config.toml")
        self.saved_toml = common.tomllib

    def tearDown(self):
        common.tomllib = self.saved_toml
        self.tmp.cleanup()

    def test_every_row_has_a_switch_and_defaults_to_on(self):
        import pcstats
        flags = pcstats.pc_flags(common.load_config()["pc"])
        self.assertEqual(set(flags), {f"show_{k}" for k in common.PC_SHOW_KEYS})
        self.assertTrue(all(flags.values()))

    def test_switches_survive_save_and_both_parsers(self):
        cfg = copy.deepcopy(common.DEFAULTS)
        cfg["pc"].update(show_gpu_temp=False, show_uptime=False, show_battery=False)
        common.save_config(cfg)
        for parser in (common.tomllib, None):                 # tomllib and the built-in fallback
            common.tomllib = parser
            pc = common.load_config()["pc"]
            self.assertFalse(pc["show_gpu_temp"] or pc["show_uptime"] or pc["show_battery"])
            self.assertTrue(pc["show_cpu"] and pc["show_network"])

    def test_missing_section_means_everything_shown(self):
        Path(os.environ["STATS_WIDGET_CONFIG"]).write_text("[general]\nuse_24h = true\n")
        self.assertTrue(all(common.load_config()["pc"].values()))

    def test_layout_knows_every_pc_switch(self):
        template = (common.ROOT / "eww.yuck.in").read_text()
        for key in common.PC_SHOW_KEYS:
            self.assertIn(f"pc.show_{key}", template, key)
            self.assertIn(f'"show_{key}":true', template.split("(deflisten pc")[1].split("scripts/pcstats.py")[0], key)

    def test_vram_and_battery_switches_only_matter_when_the_hardware_exists(self):
        template = (common.ROOT / "eww.yuck.in").read_text()
        self.assertIn("pc.show_vram && pc.has_vram", template)
        self.assertIn("pc.show_battery && pc.has_battery", template)


class ServerToggleTests(unittest.TestCase):
    def setUp(self):
        import server
        self.server = server
        self.scfg = copy.deepcopy(common.DEFAULTS["server"])
        self.data = {"host": "rayaz", "cpu": 10, "ram_u": 4, "ram_t": 16, "ram_p": 25, "ssd_u": 1, "ssd_t": 2,
                     "ssd_p": 50, "net_rx": 1, "net_tx": 1}

    def test_custom_server_name_replaces_the_hostname(self):
        self.assertIn("rayaz", self.server.build(self.data, "Home", "h", (1.0, 1.0), self.scfg)["title"])
        self.scfg["name"] = " Homelab "
        self.assertEqual(self.server.build(self.data, "Home", "h", (1.0, 1.0), self.scfg)["title"], "Homelab · Home")

    def test_cpu_and_ram_can_be_hidden(self):
        self.scfg.update(show_cpu=False, show_ram=False)
        out = self.server.build(self.data, "Home", "h", (1.0, 1.0), self.scfg)
        self.assertFalse(out["show_cpu"] or out["show_ram"])
        self.assertTrue(out["show_temp"])

    def test_hidden_rows_give_the_height_back(self):
        full = common.design_height(common.DEFAULTS)
        cfg = copy.deepcopy(common.DEFAULTS)
        cfg["server"].update(show_cpu=False, show_ram=False, show_temp=False, show_swap=False)
        self.assertLessEqual(common.design_height(cfg), full)

    def test_draft_key_names_are_migrated(self):
        tmp = tempfile.TemporaryDirectory()
        os.environ["STATS_WIDGET_CONFIG"] = str(Path(tmp.name) / "config.toml")
        Path(os.environ["STATS_WIDGET_CONFIG"]).write_text(
            "[server]\nshow_clock = false\nshow_temperature = false\nshow_system_disk = false\n")
        s = common.load_config()["server"]
        self.assertFalse(s["show_cpu_clock"] or s["show_temp"] or s["show_system"])
        tmp.cleanup()

    def test_label_follows_the_position_when_the_server_picked_other_paths(self):
        self.scfg.update(storage_paths=["/mnt/media"], storage_labels=["Media"], show_storage=True)
        data = dict(self.data, storage=[{"path": "/raids", "kind": "raid", "ok": True, "used": 1, "total": 2,
                                         "percent": 50, "md": None}])
        rows = self.server.build(data, "Home", "h", (1.0, 1.0), self.scfg)["storage"]
        self.assertEqual(rows[0]["name"], "Media:")


class WeekendFallbackTests(unittest.TestCase):
    def test_unreadable_weekend_keeps_friday_saturday_but_empty_means_none(self):
        self.assertEqual(common.weekend_days({"general": {"weekend": ["xyz"]}}), {4, 5})
        self.assertEqual(common.weekend_days({"general": {"weekend": []}}), set())
        self.assertEqual(common.weekend_days({"general": {"weekend": ["Sun", "monday"]}}), {6, 0})


class GpuDetectionTests(unittest.TestCase):
    def test_apu_without_own_memory_has_no_vram_row_but_a_discrete_card_does(self):
        import pcstats
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "mem_info_vram_total").write_text(str(512 * 1024 ** 2))
            self.assertFalse(pcstats.GPU.amd_has_dedicated_vram(d))               # APU: 512 MB carve-out of the RAM
            (Path(d) / "mem_info_vram_total").write_text(str(8 * 1024 ** 3))
            self.assertTrue(pcstats.GPU.amd_has_dedicated_vram(d))                # real card
            (Path(d) / "mem_info_vram_vendor").write_text("samsung")
            (Path(d) / "mem_info_vram_total").write_text(str(512 * 1024 ** 2))
            self.assertTrue(pcstats.GPU.amd_has_dedicated_vram(d))                # memory maker named: dedicated

    def test_cpu_clock_reads_cpufreq_then_cpuinfo(self):
        import pcstats
        with tempfile.TemporaryDirectory() as d:
            cpu = Path(d) / "sys" / "devices" / "system" / "cpu" / "cpu0" / "cpufreq"
            cpu.mkdir(parents=True)
            (cpu / "scaling_cur_freq").write_text("2400000")
            (cpu / "cpuinfo_max_freq").write_text("4600000")
            self.assertEqual(pcstats.cpu_clock(str(Path(d) / "sys"), str(Path(d) / "nope")), (2400.0, 4600.0))
            proc = Path(d) / "proc"
            proc.mkdir()
            (proc / "cpuinfo").write_text("cpu MHz\t\t: 1000.0\ncpu MHz\t\t: 3000.0\n")
            self.assertEqual(pcstats.cpu_clock(str(Path(d) / "none"), str(proc)), (2000.0, 0.0))


if __name__ == "__main__":
    unittest.main()
