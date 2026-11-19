# Changelog
All notable changes are documented here. Format: [Keep a Changelog](https://keepachangelog.com), versioning: [SemVer](https://semver.org).

## [Unreleased]
### Added
- **Everything in the Server column is configurable in `stats-widget config`** (new *Server rows* tab): show/hide uptime, CPU, clock, temperature, RAM, swap, network and system disk; server name, system-disk name/path, network cards; extra storage rows by mount point with your own names, or automatic (every separate disk / RAID / pool the server reports, up to a limit). No RAID, one RAID or several - nothing to edit on the server any more. `stats.php` now lists all disks (`disks`, with the mdadm array name) and accepts `?system=` / `?net=` from the widget (only known mount points / NIC names; `allow_client_settings` turns it off).
- **Configurable weekend and first day of the week** (`[general] weekend`, `week_start`, and *Calendar* tab). Default stays Fri + Sat, weeks start on Sunday. The weekday header follows.
- **CPU clock speed** (average over all cores) in the PC column and, from `stats.php` (`cpu_mhz`), in the Server column - it replaces *Load average*.
- PC column: **VRAM row only on graphics cards with their own memory** (NVIDIA, discrete AMD). Intel / APU graphics no longer show a VRAM or "Shared" line. The GPU *Clock* row is now always shown (before, VRAM replaced it).
### Changed
- *Load average* is gone from the widget (`stats.php` still reports `load` and `cores`).
- The Server column is built from a list of rows sent by `scripts/server.py`; the layout no longer hard-codes them.
### Fixed
- NVIDIA: one unreadable value (`[N/A]` from `nvidia-smi`) blanked the whole GPU block; each value is now read on its own.
- `stats.php`: CPU core count read `/proc/cpuinfo` twice and relied on a fragile newline test.
- Server column shows the **server CPU name** (e.g. "Intel Core i3-6100") as the title of the *CPU & Memory* bar, like the PC column; `stats.php` returns `cpu_name`.
### Fixed
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
