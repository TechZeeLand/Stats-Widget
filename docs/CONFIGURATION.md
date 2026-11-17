# Configuration

Easiest: **`stats-widget config`** (settings window). Everything below is what it edits:
`~/.config/stats-widget/config.toml` (created on first start). After hand-editing run `stats-widget restart`.

```toml
[general]
use_24h = false

[server]
urls   = ["http://192.168.0.123/stats.php", "http://rayaz.netbird.cloud/stats.php"]
labels = ["Home network", "Remote (NetBird)"]
token  = ""
interval = 1.0
timeout = 1.5
retry_primary = 20
raid_label = "RAID"

[weather]
display_name = "Dhaka, Bangladesh"
latitude = 23.7643863
longitude = 90.3890144
units = "metric"
refresh_minutes = 10

[position]
anchor = "top left"
x = 40
y = 40
monitor = 0
layer = "bottom"

[appearance]
background_opacity = 100
width  = 795
height = 475
```

| Key | Meaning |
|---|---|
| `server.urls` | stats.php addresses in order of preference. The first that answers is used. |
| `server.labels` | name shown for each address (`rayaz · Home network`). |
| `server.retry_primary` | while on a fallback address, how often (seconds) to test the first one again. |
| `server.timeout` | seconds before an address counts as down (probes of the preferred address use at most 1 s). |
| `server.token` | sent as `?key=…`; must match `token` in the server's `stats.config.php`. |
| `weather.*` | Open-Meteo, no key. `stats-widget config` → Weather has a city search that fills in the coordinates. |
| `position.anchor` | `top left`, `top center`, `top right`, `center left`, `center`, `center right`, `bottom left`, `bottom center`, `bottom right`. |
| `position.x / y` | pixels from the anchored edge. |
| `position.monitor` | `0` = first screen, `1` = second, or a name such as `"DP-1"`. |
| `position.layer` | Wayland only: `bottom` (above wallpaper, below windows), `bg`, `fg`, `overlay`. X11 ignores it. |
| `appearance.background_opacity` | 0-100 %. |
| `appearance.width / height` | Widget size in pixels (default 795 × 475, allowed 50-300 %). All text, icons and spacing scale with it. With different proportions the text follows the smaller side. Easiest: `stats-widget size 120%`. |

> Python < 3.11 uses a small built-in TOML reader: keep arrays on **one line**.

## Moving the widget
Right-click the widget → drag the ghost → **Enter** (or double-click) to save, **Esc** to cancel, arrow keys nudge (Shift = 10 px).
Same thing: `stats-widget move`, or *Position → Drag to place* in the settings window.
On Wayland the tool is a layer-shell surface so coordinates match your panels exactly; on X11 it is a full-screen window.

## Colours, fonts, sizes
`~/.local/share/stats-widget/eww.scss` (palette at the top) and the layout `eww.yuck.in`. Sizes in those files are written for 795 × 475
and scaled automatically (`sx() sy() sf()` in scss, `{{x:249}}` in the layout). Updating replaces these files - keep changes in a fork, or copy them elsewhere.

## Which files are generated
`window.yuck`, `theme.scss` and `eww.yuck` are written from `config.toml` every time the widget starts. Do not edit them.
