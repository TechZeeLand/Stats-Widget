# Troubleshooting

**First step, always:** `stats-widget doctor` - it checks eww, Python, GTK bindings, fonts, config and every server address.
Then `stats-widget logs` for eww's own messages.

| Problem | Fix |
|---|---|
| Nothing appears | `stats-widget logs`. On Wayland try `layer = "overlay"` in config.toml (Position tab → Layer) then `stats-widget restart`. On GNOME/Wayland use the Xorg session. |
| Appears in the wrong place / under the panel | Wayland respects panel space. Use *Drag to place* (it uses the same coordinates). |
| Icons show words (`wb_twilight`, `place`, `south_east`) | Fonts not cached: `fc-cache -f`, then `stats-widget restart`. `fc-list \| grep -E "Material\|Alata"` must list both fonts. |
| Server column says **Server offline** | `curl -v http://192.168.0.123/stats.php`. Does it return JSON? Is the address in the **Server** tab correct? A `token` set on the server must be set in the widget too. |
| It stays on "Remote" at home | The first address is probed every `retry_primary` seconds (default 20). Check that address with curl from this PC. |
| RAID row says N/A / Not reachable | Open `…/stats.php?debug=1` - see [SERVER_SETUP.md §3](SERVER_SETUP.md). Usually Docker without the mount, or permissions. |
| RAID health line says "Online" | Not an mdadm array (ZFS/btrfs/mergerfs): capacity only. |
| Weather "No data" | `python3 ~/.local/share/stats-widget/scripts/weather.py` shows the error; check internet / coordinates. |
| GPU shows N/A | AMD/NVIDIA: driver must expose it (`nvidia-smi` for NVIDIA). Intel shows an estimate (`~12%`), VRAM "Shared". |
| `stats-widget: command not found` | Log out/in, or `export PATH="$HOME/.local/bin:$PATH"`. |
| Settings window / move mode do not open | `python3 -c "import gi, cairo"` - install PyGObject and pycairo (`python3-gi-cairo` on Debian/Ubuntu). |
| eww build fails | Open an issue with the last 30 lines. You can retry with `EWW_FEATURES=x11` (no Wayland support). |
| Python < 3.11 and config error | Keep every array on one line in config.toml. |

Everything the widget writes: `~/.local/share/stats-widget` (program), `~/.config/stats-widget` (settings),
`~/.cache/stats-widget` (last weather), `~/.local/share/fonts/stats-widget`, `~/.local/bin/{stats-widget,eww}`,
`~/.config/autostart/stats-widget.desktop`.
