# Project brief (maintainer notes)

**Origin:** Rainmeter skin "Stats Widget" (Windows, by TechZeeLand) → ported to eww for Linux (v0.1) → open-source project (v0.2).

**Decisions**
- Default size 795 × 475 px and the original black/white theme (Alata font) are kept; the size is user-adjustable (50-300 %), layout rendered from `eww.yuck.in`.
- Data scripts are plain Python (stdlib only) printing JSON; eww `deflisten` consumes them. Server side is one PHP file.
- Config is a single TOML file in `~/.config/stats-widget`; position/opacity are turned into `window.yuck` / `theme.scss` at start (eww cannot read config files itself).
- Server failover = ordered URL list; preferred address re-probed periodically.
- eww cannot drag windows → "move mode" (ghost window) places the real one; right-click triggers it.
- eww is built from a pinned upstream revision by the installer (reproducible; no distro ships it).
- Installers: one bootstrap (`install.sh`) → per-family script in `distros/` → shared `lib/common.sh`.
- License AGPL-3.0-or-later. Bundled fonts/icons keep their own licenses (`THIRD_PARTY.md`).

**Open items**
- rhel / arch / suse installers need a real-machine test; Fedora-on-KDE-Wayland needs a real-desktop test of layer `bottom` and move mode.
- Optional later: prebuilt eww binaries per distro, GPU busy % for Intel, Flatpak-friendly layout.
