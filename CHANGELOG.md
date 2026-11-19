# Changelog
All notable changes are documented here. Format: [Keep a Changelog](https://keepachangelog.com), versioning: [SemVer](https://semver.org).

## [Unreleased]
### Added
- **PC Stats rows can be switched off** (`[pc] show_*` in `config.toml`, *PC data* tab in `stats-widget config`): CPU usage / clock / temperature, uptime, GPU usage / temperature, VRAM, RAM, disk, battery, network. A block with no row left disappears with its heading, and a hidden GPU block is not read at all (no `nvidia-smi` calls, a sleeping laptop GPU is left alone).
- Server column: `name` (shown instead of the hostname) and switches for **CPU usage** and **RAM** (`show_cpu`, `show_ram`). Hidden rows give their height back to the layout. Key names from an earlier draft (`show_clock`, `show_temperature`, `show_system_disk`) are migrated.
- **Everything on the server column is configurable from the widget** (`stats-widget config` → *Server data*): any number of storage pools (RAID, ZFS, data disks) with names, the system-disk path and name, which network cards to count, and a switch for every row. The paths are sent to `stats.php`, which validates them (`allow_client_config = false` turns this off); nothing has to be edited on the server. *Find on server…* lists the disks it sees. Old `raid_label` settings are migrated.
- **Calendar**: first day of the week and the weekend days are settings (*Look & Size*), no longer hard-coded Sunday-first / Fri+Sat.
- **CPU clock** (current / maximum) in the PC column and, replacing *Load average*, in the Server column (`stats.php` returns `cpu_mhz`, `cpu_mhz_max`).
- GPU clock is shown next to the utilisation. The **VRAM row only appears for cards with their own memory** (NVIDIA, AMD); integrated GPUs show no VRAM row.
- `stats.php` v3: `storage` list (kind, md array per mount, status per pool), `net_t` timestamp, `client_config`.
- Server column shows the **server CPU name** (e.g. "Intel Core i3-6100") as the title of the *CPU & Memory* bar, like the PC column; `stats.php` returns `cpu_name`.
### Fixed
- AMD APUs no longer get a VRAM row (they borrow system RAM); NVIDIA cards keep it and show *N/A* if `nvidia-smi` cannot read it.
- NVIDIA: one unreadable value (`[N/A]` from `nvidia-smi`) blanked the whole GPU block; each value is now read on its own (and cached for 2 s).
- `stats.php`: CPU core count is a single clean `/proc/cpuinfo` read again (it had gone back to a fragile newline test).
- A weekend list with only unreadable day names no longer removes the weekend colouring (`[]` still means "no weekend").
- Storage names follow the list order when the server chose other paths than the widget asked for (`allow_client_config` off).
- Settings *Test* and `stats-widget doctor` printed "(RAID: …)" for servers that simply have no RAID; they now report storage found/missing.
- Network speed uses the moment the server read its counters (less jitter than timing the request).
- RAID health is matched to the right pool by its `/dev/mdN` device (it used to be one global line).
- The Docker image runs several PHP workers so a second widget no longer waits on CPU sampling; `nvidia-smi` is queried at most every 2 s.
- Portainer *Pull and redeploy* failed with "pull access denied for stats-widget-server": the compose file no longer names a pullable image (`pull_policy: build`).
- The RAID row no longer repeats the system disk. `stats.php` compares the candidate pool with the system path (device id, mount source device, identical size and free space - the last one catches Docker bind mounts) and reports `raid.present: false`; the widget then shows no RAID row. Real `/dev/mdN` arrays are never treated as the system disk.
- Debug page (`?debug=1`) says when a configured RAID path is the same disk as the system path.

## [0.3.0] - 2026-11-17
### Added
- **Resizable widget**: size (50 %-300 %) in `stats-widget config` → *Look & Size*, or `stats-widget size 120%` / `1000x600` / `reset`. The default stays 795 × 475; all text, icons and spacing scale with it.
- `stats-widget update --full`; `stats-widget update` now restarts a running widget by itself.
- The installer backs up a recognisable pre-0.2 installation in `~/.config/eww` and warns about old autostart entries.
### Changed
- Server: Docker setup is built from GitHub (`docker-compose.yml` + `server/Dockerfile`) so Portainer's *Repository* option works; `stats.php` reads `STATS_*` environment variables.
- Sunrise/sunset and humidity/rain/wind strip: no white background, centred in the weather block.
- Weather, sunrise/sunset, humidity, rain and wind pictures are Material Icons glyphs (Apache-2.0). Wind arrow now shows where the wind blows **to**.
- `eww.yuck` is generated from `eww.yuck.in`.
### Removed
- JDWI icon fonts and weather PNGs (license unknown).

## [0.2.0] - 2026-11-15
### Added
- Server **failover**: ordered list of stats.php addresses (home → NetBird), automatic switch-back, status shown in the widget.
- Redesigned Server and PC columns with usage bars, uptime, load, swap, system disk, RAID health, battery.
- **RAID** support in `stats.php`: mdadm state (healthy / degraded / rebuilding), auto-detected arrays, per-disk list, `?debug=1`.
- Graphical settings window (`stats-widget config`) and drag-to-place move mode (right-click the widget).
- `stats-widget` command (start/stop/config/move/doctor/autostart/update/uninstall).
- One-line installer with per-family scripts: Fedora, RHEL family, Debian/Ubuntu, Arch, openSUSE, generic.
- Optional token for `stats.php`, Docker guidance, background-opacity setting, date under the clock.

### Changed
- Settings moved to `~/.config/stats-widget/config.toml`; widget installs to `~/.local/share/stats-widget`.
- License: AGPL-3.0-or-later.

### Removed
- Minecraft server section.

## [0.1.0] - 2026-11-14
- First eww port of the Rainmeter "Stats Widget" skin (fixed network-speed, calendar-highlight and data-parsing bugs).
