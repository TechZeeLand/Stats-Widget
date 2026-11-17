#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Column 2 - current weather from Open-Meteo (free, no API key). Prints ONE JSON object and exits;
eww re-runs it every few minutes. If the network is down, the last good answer is reused."""
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime

from common import CACHE, emit, load_config, num

# WMO weather code -> (text, condition)
WMO = {
    0: ("Clear sky", "clear"), 1: ("Mostly clear", "clear"), 2: ("Partly cloudy", "partly-cloudy"),
    3: ("Overcast", "cloudy"), 45: ("Fog", "fog"), 48: ("Rime fog", "fog"),
    51: ("Light drizzle", "rain"), 53: ("Drizzle", "rain"), 55: ("Heavy drizzle", "rain"),
    56: ("Freezing drizzle", "sleet"), 57: ("Freezing drizzle", "sleet"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "sleet"), 67: ("Freezing rain", "sleet"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow grains", "snow"),
    80: ("Light showers", "rain"), 81: ("Showers", "rain"), 82: ("Heavy showers", "rain"),
    85: ("Snow showers", "snow"), 86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "storm"), 96: ("Thunderstorm, hail", "storm"), 99: ("Thunderstorm, hail", "storm"),
}
# condition -> (day glyph, night glyph). Glyphs are ligature names of the bundled
# "Material Icons Outlined" font (Apache-2.0), drawn by eww as pictures.
GLYPHS = {
    "clear": ("wb_sunny", "nightlight"),
    "partly-cloudy": ("wb_cloudy", "nights_stay"),
    "cloudy": ("cloud", "cloud"),
    "fog": ("dehaze", "dehaze"),
    "rain": ("water_drop", "water_drop"),
    "sleet": ("grain", "grain"),
    "snow": ("ac_unit", "ac_unit"),
    "storm": ("thunderstorm", "thunderstorm"),
    "unknown": ("help_outline", "help_outline"),
}
# 8 compass arrows (Material Icons), index = 45-degree sector the wind blows TOWARDS
ARROWS = ["south", "south_west", "west", "north_west", "north", "north_east", "east", "south_east"]


def icon_name(condition, is_day):
    day, night = GLYPHS.get(condition, GLYPHS["unknown"])
    return day if is_day else night


def wind_arrow(degrees_from):
    """Meteorological wind direction is where the wind comes FROM; the arrow shows where it blows to."""
    return ARROWS[int(round(num(degrees_from) / 45.0)) % 8]


def clock(iso, use_24h):
    dt = datetime.fromisoformat(iso)
    return dt.strftime("%H:%M") if use_24h else dt.strftime("%-I:%M %p")


def fetch(cfg, use_24h):
    imperial = str(cfg["units"]).lower() == "imperial"
    query = urllib.parse.urlencode({
        "latitude": cfg["latitude"], "longitude": cfg["longitude"],
        "current": "temperature_2m,relative_humidity_2m,weather_code,is_day,wind_speed_10m,wind_direction_10m",
        "daily": "sunrise,sunset,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 1,
        "temperature_unit": "fahrenheit" if imperial else "celsius",
        "wind_speed_unit": "mph" if imperial else "kmh",
    })
    req = urllib.request.Request("https://api.open-meteo.com/v1/forecast?" + query,
                                 headers={"User-Agent": "eww-stats-widget"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    cur, daily = data["current"], data["daily"]
    text, icon = WMO.get(int(cur["weather_code"]), ("Unknown", "unknown"))
    return {
        "ok": True,
        "city": cfg["display_name"],
        "temp": f"{round(num(cur['temperature_2m']))}°",
        "phrase": text,
        "icon": icon_name(icon, int(cur.get("is_day", 1))),
        "sunrise": clock(daily["sunrise"][0], use_24h),
        "sunset": clock(daily["sunset"][0], use_24h),
        "humidity": f"{round(num(cur['relative_humidity_2m']))}%",
        "precip": f"{round(num(daily['precipitation_probability_max'][0]))}%",
        "wind": f"{round(num(cur['wind_speed_10m']))} {'mph' if imperial else 'km/h'}",
        "wind_icon": wind_arrow(cur["wind_direction_10m"]),
    }


def main():
    cfg = load_config()
    cache = CACHE / "weather.json"
    refresh = max(1, float(cfg["weather"]["refresh_minutes"])) * 60
    while True:
        wait = refresh
        try:
            result = fetch(cfg["weather"], cfg["general"]["use_24h"])
            CACHE.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(result, ensure_ascii=False))
        except Exception:
            wait = 60                       # network down? try again in a minute
            try:
                result = json.loads(cache.read_text())      # show the last good data meanwhile
            except Exception:
                result = {"ok": False, "city": cfg["weather"]["display_name"], "temp": "--°",
                          "phrase": "No data", "icon": "help_outline",
                          "sunrise": "--:--", "sunset": "--:--", "humidity": "--%",
                          "precip": "--%", "wind": "--", "wind_icon": "south"}
        emit(result)
        time.sleep(wait)


if __name__ == "__main__":
    main()
