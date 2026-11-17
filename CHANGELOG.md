# Changelog
All notable changes are documented here. Format: [Keep a Changelog](https://keepachangelog.com), versioning: [SemVer](https://semver.org).

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
