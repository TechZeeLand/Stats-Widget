# Configuration

Easiest: **`stats-widget config`** (settings window). Everything below is what it edits:
`~/.config/stats-widget/config.toml` (created on first start). After hand-editing run `stats-widget restart`.

```toml
[general]
use_24h = false
week_start = "sun"            # mon tue wed thu fri sat sun
weekend    = ["fri", "sat"]   # drawn red; any days, [] = none

[server]
urls   = ["http://192.168.0.123/stats.php", "http://rayaz.netbird.cloud/stats.php"]
labels = ["Home network", "Remote (NetBird)"]
token  = ""
interval = 1.0
timeout = 1.5
retry_primary = 20
name           = ""                 # shown instead of the server's hostname
system_label   = "System"
system_path    = ""                 # "" = the server's own setting (normally "/")
storage_paths  = []                 # e.g. ["/raids", "/mnt/media"]; [] = what the server is set up for / detects
storage_labels = []                 # names for those paths, same order ("" = automatic)
net_interfaces = []                 # e.g. ["enp3s0"]; [] = all physical network cards
show_uptime = true                  # also show_cpu_clock, show_cpu, show_temp, show_ram, show_swap, show_system, show_storage, show_network

[pc]                                # PC Stats column: true / false per row
show_cpu = true                     # CPU usage bar
show_cpu_clock = true
show_cpu_temp = true
show_uptime = true
show_gpu_use = true                 # GPU utilisation + clock
show_gpu_temp = true
show_vram = true                    # only cards with their own memory have this row anyway
show_ram = true
show_disk = true
show_battery = true                 # only laptops have this row anyway
show_network = true

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
| `general.week_start` / `general.weekend` | First calendar column and the red days. Countries differ: `["sat", "sun"]`, `["fri"]`, `[]` all work. |
| `server.storage_paths` | Folders on the **server** to show as storage bars (up to 4). Sent to `stats.php` with every request. Empty = the server's own `raid_paths` / auto-detect. An unreachable path is shown as *Not reachable*. |
| `server.storage_labels` | Names for those rows. Empty = automatic (*RAID*, *ZFS*, folder name). |
| `server.system_path` / `system_label` | Which disk the *System* row measures, and its name. |
| `server.net_interfaces` | Network cards whose traffic is summed. Empty = all physical cards. |
| `server.name` | Text shown in the first title bar instead of the server's hostname. |
| `server.show_*` | Hide any row you do not want: `uptime`, `cpu_clock`, `cpu`, `temp`, `ram`, `swap`, `system`, `storage`, `network`. A block with nothing left disappears with its heading. |
| `pc.show_*` | The same for the PC Stats column: `cpu`, `cpu_clock`, `cpu_temp`, `uptime`, `gpu_use`, `gpu_temp`, `vram`, `ram`, `disk`, `battery`, `network`. Also in `stats-widget config` → *PC data*. A hidden GPU block is not read at all (no `nvidia-smi` calls, a sleeping laptop GPU is left alone). |
| `weather.*` | Open-Meteo, no key. `stats-widget config` → Weather has a city search that fills in the coordinates. |
| `position.anchor` | `top left`, `top center`, `top right`, `center left`, `center`, `center right`, `bottom left`, `bottom center`, `bottom right`. |
| `position.x / y` | pixels from the anchored edge. |
| `position.monitor` | `0` = first screen, `1` = second, or a name such as `"DP-1"`. |
| `position.layer` | Wayland only: `bottom` (above wallpaper, below windows), `bg`, `fg`, `overlay`. X11 ignores it. |
| `appearance.background_opacity` | 0-100 %. |
| `appearance.width / height` | Widget size in pixels (default 795 × 475, allowed 50-300 %). All text, icons and spacing scale with it. With different proportions the text follows the smaller side. Easiest: `stats-widget size 120%`. |

> Python < 3.11 uses a small built-in TOML reader: keep arrays on **one line**.

> Extra storage rows need vertical room: with more than one the whole layout is shrunk a little so it still fits the window
> (raise *Size %* to compensate). Hidden rows give the room back.
> The server may refuse widget-chosen paths (`allow_client_config = false` in `stats.config.php`); then the server's own settings apply.

## Moving the widget
Right-click the widget → drag the ghost → **Enter** (or double-click) to save, **Esc** to cancel, arrow keys nudge (Shift = 10 px).
Same thing: `stats-widget move`, or *Position → Drag to place* in the settings window.
On Wayland the tool is a layer-shell surface so coordinates match your panels exactly; on X11 it is a full-screen window.

## Colours, fonts, sizes
`~/.local/share/stats-widget/eww.scss` (palette at the top) and the layout `eww.yuck.in`. Sizes in those files are written for 795 × 475
and scaled automatically (`sx() sy() sf()` in scss, `{{x:249}}` in the layout). Updating replaces these files - keep changes in a fork, or copy them elsewhere.

## Which files are generated
`window.yuck`, `theme.scss` and `eww.yuck` are written from `config.toml` every time the widget starts. Do not edit them.
