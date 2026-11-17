# Installation

## The short way
```bash
curl -fsSL https://raw.githubusercontent.com/TechZeeLand/Stats-Widget/main/install.sh | bash -s -- --autostart --start
```
Run as your **normal user** (not root). It will:

1. detect your distribution family (`/etc/os-release`),
2. install the build and runtime packages with your package manager (`sudo` asks once),
3. install Rust with rustup if there is no Rust ≥ 1.81, then **build eww** (10-20 min, only the first time),
4. install the widget to `~/.local/share/stats-widget`, the fonts to `~/.local/share/fonts/stats-widget`,
   the `stats-widget` command to `~/.local/bin`, and create `~/.config/stats-widget/config.toml`.

### Options (after `bash -s --`)
| Option | Meaning |
|---|---|
| `--autostart` | start the widget at every login |
| `--start` | start it right after installing |
| `--widget-only` | update only the widget (skip packages and eww) - this is what `stats-widget update` does |
| `--no-eww` | install packages and widget, do not build eww |
| `--no-deps` | skip system packages |

Environment variables: `STATS_WIDGET_DISTRO=debian` forces a family, `EWW_FEATURES=x11` builds eww without Wayland support,
`STATS_WIDGET_REF=<branch>` installs another branch.

## From a clone
```bash
git clone https://github.com/TechZeeLand/Stats-Widget && cd Stats-Widget
./install.sh --autostart --start
# or a specific family:  ./distros/arch/install.sh
```

## Supported systems
| Family (`distros/…`) | Package manager | Notes |
|---|---|---|
| `fedora` | dnf | Fedora Workstation/KDE/spins, Nobara. Not Silverblue/Kinoite/Bazzite (immutable: install in a toolbox/distrobox) |
| `rhel` | dnf + EPEL + CRB | RHEL/Alma/Rocky/Oracle/CentOS Stream 9-10. Without `gtk-layer-shell` an X11-only eww is built (XWayland) |
| `debian` | apt | Debian 12+, Ubuntu 22.04+, Mint, Pop!_OS, elementary, Zorin |
| `arch` | pacman | Arch, Manjaro, EndeavourOS, Garuda, CachyOS |
| `suse` | zypper | Tumbleweed, Leap, SLE (+PackageHub) |
| `generic` | none | you install the packages listed in `distros/generic/install.sh` |

**RHEL itself** (not Alma/Rocky): enable EPEL and CodeReady Builder first:
`sudo dnf install https://dl.fedoraproject.org/pub/epel/epel-release-latest-$(rpm -E %rhel).noarch.rpm` and
`sudo subscription-manager repos --enable codeready-builder-for-rhel-$(rpm -E %rhel)-$(arch)-rpms`.

**NixOS:** use `generic` inside `nix-shell -p gtk3 gtk-layer-shell pango gdk-pixbuf cairo glib libdbusmenu-gtk3 pkg-config openssl python3Packages.pygobject3 rustup` or the eww module of home-manager and copy `widget/` yourself.

## Desktops
* **KDE Plasma (Wayland or X11)**, Sway, Hyprland, river, labwc: works (layer-shell). The default layer `bottom` sits above the wallpaper and below windows.
* **GNOME on Wayland** has no layer-shell. eww then runs through XWayland; if the widget does not appear, log into the *GNOME on Xorg* session.
* **XFCE, Cinnamon, MATE, i3 (X11)**: works through the X11 backend.

## Requirements the installer sets up
git, C compiler, pkg-config, curl, fontconfig, pciutils (GPU name), GTK 3 + gtk-layer-shell + pango + gdk-pixbuf2 + cairo + glib + libdbusmenu-gtk3 (headers for the build),
Python ≥ 3.8 with PyGObject and pycairo (settings window and move mode), Rust ≥ 1.81 (build only).

## Update / uninstall
Stats Widget is not a distro package, so `sudo dnf/apt/pacman update` will not update it. It updates itself:
```bash
stats-widget update          # latest widget, keeps your settings (restarts it if it was running)
stats-widget update --full   # also re-run the package/eww step (only when the release notes say so)
stats-widget uninstall       # removes the widget; add --purge to delete your settings too
```
eww itself (`~/.local/bin/eww`) is left in place because other widgets may use it.

## Manual install (no script)
1. Install the dependencies above, build eww: `git clone https://github.com/elkowar/eww && cd eww && cargo build --release` and copy `target/release/eww` to `~/.local/bin/`.
2. Copy `widget/` to `~/.local/share/stats-widget/`, the files of `widget/fonts/` to `~/.local/share/fonts/` and run `fc-cache -f`.
3. `python3 ~/.local/share/stats-widget/scripts/apply_config.py && eww --config ~/.local/share/stats-widget daemon && eww --config ~/.local/share/stats-widget open stats`

## Replacing an older version (before the one-line installer)
The installer now looks for the first eww port in `~/.config/eww`; if it is recognisably Stats Widget it is stopped and **moved**
(not deleted) to `~/.config/eww.stats-widget-old-<date>`. Other eww widgets are left alone. Then just run the one-line install.
Manual check: `pgrep -a eww`, `ls ~/.config/eww ~/.config/autostart`; stop the old one with `eww kill` and remove its autostart entry.
