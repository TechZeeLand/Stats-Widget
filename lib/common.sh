#!/usr/bin/env bash
# shellcheck disable=SC2034
# SPDX-License-Identifier: AGPL-3.0-or-later
# Shared installer logic. Each distros/<family>/install.sh defines:
#   DISTRO_NAME, install_packages()   and then calls:  run_installer "$@"

REPO_URL="${STATS_WIDGET_REPO:-https://github.com/TechZeeLand/Stats-Widget}"
EWW_REPO="https://github.com/elkowar/eww.git"
EWW_REF="${EWW_REF:-48f5aa8b379adf29da0b0bb9ca04164f65d8bdaa}"   # eww revision this widget was tested with
EWW_FEATURES="${EWW_FEATURES:-x11,wayland}"
APP_DIR="${STATS_WIDGET_HOME:-$HOME/.local/share/stats-widget}"
BIN_DIR="$HOME/.local/bin"
FONT_DIR="$HOME/.local/share/fonts/stats-widget"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -t 1 ]; then C1=$'\033[1;36m'; C2=$'\033[1;31m'; C3=$'\033[1;33m'; C0=$'\033[0m'; else C1=; C2=; C3=; C0=; fi
say()  { printf '%s→%s %s\n' "$C1" "$C0" "$*"; }
warn() { printf '%s!%s %s\n' "$C3" "$C0" "$*" >&2; }
die()  { printf '%s✗%s %s\n' "$C2" "$C0" "$*" >&2; exit 1; }

SUDO=""
need_root() {
  if [ "$(id -u)" -eq 0 ]; then SUDO=""; return; fi
  command -v sudo >/dev/null || die "sudo is required to install system packages (or run this as root)."
  SUDO="sudo"
  say "Installing system packages needs administrator rights (sudo will ask for your password)."
}

# ── Rust (eww is written in Rust) ───────────────────────────────────────
rust_ok() {
  command -v cargo >/dev/null && command -v rustc >/dev/null || return 1
  local v; v="$(rustc --version | sed -E 's/rustc ([0-9]+)\.([0-9]+).*/\1 \2/')"
  # shellcheck disable=SC2086   # splitting "major minor" into two arguments is intended
  set -- $v
  [ "$1" -gt 1 ] || [ "$2" -ge 81 ]
}
ensure_rust() {
  # shellcheck disable=SC1091
  [ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
  rust_ok && return
  say "Installing Rust (rustup, minimal profile) - needed once to build eww"
  curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable \
    || die "Could not install Rust. Install it from https://rustup.rs and run this installer again."
  # shellcheck disable=SC1091
  . "$HOME/.cargo/env"
}

# ── eww ─────────────────────────────────────────────────────────────────
ensure_eww() {
  export PATH="$BIN_DIR:$HOME/.cargo/bin:$PATH"
  if command -v eww >/dev/null && [ -z "${FORCE_EWW:-}" ]; then
    say "eww already installed: $(eww --version 2>/dev/null | head -1)"; return
  fi
  ensure_rust
  local tmp; tmp="$(mktemp -d)"
  say "Downloading eww source (revision ${EWW_REF:0:8})"
  ( cd "$tmp" && git init -q eww && cd eww && git remote add origin "$EWW_REPO" \
      && git fetch -q --depth 1 origin "$EWW_REF" && git checkout -q FETCH_HEAD ) \
    || die "Could not download eww from GitHub."
  say "Building eww (features: $EWW_FEATURES). This takes 10-20 minutes the first time - fans will spin, that is normal."
  ( cd "$tmp/eww" && cargo build --release -p eww --no-default-features --features "$EWW_FEATURES" ) \
    || die "Building eww failed. Scroll up for the error, or open an issue: $REPO_URL/issues"
  mkdir -p "$BIN_DIR"
  install -m 755 "$tmp/eww/target/release/eww" "$BIN_DIR/eww"
  rm -rf "$tmp"
  say "eww installed to $BIN_DIR/eww"
}

# ── an older, hand-installed version (before the one-line installer) ─────
# Looks for the first eww port in the default eww folder (~/.config/eww). It is only touched when it
# is recognisably this widget; it is MOVED to a backup folder, never deleted, and any other eww
# widgets are left alone.
cleanup_legacy() {
  local old="$HOME/.config/eww" stamp; stamp="$(date +%Y%m%d-%H%M%S)"
  export PATH="$BIN_DIR:$HOME/.cargo/bin:$PATH"
  if [ -f "$old/eww.yuck" ] && grep -q -E 'defwindow +stats|Server Stats' "$old/eww.yuck" 2>/dev/null; then
    say "Found the old Stats Widget in $old - backing it up"
    if command -v eww >/dev/null; then { eww --config "$old" close stats; eww --config "$old" kill; } 2>/dev/null || true; fi
    mv "$old" "$old.stats-widget-old-$stamp" && say "Old files kept in $old.stats-widget-old-$stamp (delete it when you are happy)"
  fi
  local f
  for f in "$HOME"/.config/autostart/*.desktop; do
    [ -f "$f" ] || continue
    [ "$(basename "$f")" = "stats-widget.desktop" ] && continue
    if grep -q -E 'eww.* open +stats|stats-widget' "$f" 2>/dev/null; then
      warn "Old autostart entry found: $f - remove it if it starts the old version (the new one uses stats-widget.desktop)."
    fi
  done
}

# ── the widget itself ───────────────────────────────────────────────────
install_widget() {
  local src="$ROOT_DIR/widget"
  [ -f "$src/eww.yuck.in" ] || die "widget files not found next to the installer ($src)."
  say "Installing widget to $APP_DIR"
  mkdir -p "$APP_DIR" "$BIN_DIR" "$FONT_DIR"
  # replace program files, never touch the user's config (it lives in ~/.config/stats-widget)
  rm -rf "${APP_DIR:?}/scripts" "${APP_DIR:?}/images" "${APP_DIR:?}/bin" "${APP_DIR:?}/fonts"
  rm -f "$APP_DIR/eww.yuck"          # generated again below from eww.yuck.in
  cp -r "$src/." "$APP_DIR/"
  cp "$ROOT_DIR/uninstall.sh" "$APP_DIR/uninstall.sh"
  chmod +x "$APP_DIR"/scripts/*.py "$APP_DIR/bin/stats-widget" "$APP_DIR/uninstall.sh"
  ln -sf "$APP_DIR/bin/stats-widget" "$BIN_DIR/stats-widget"
  rm -f "$FONT_DIR"/*                # drop fonts of older versions (e.g. the retired JDWI icon fonts)
  cp "$src"/fonts/* "$FONT_DIR/"
  command -v fc-cache >/dev/null && fc-cache -f "$HOME/.local/share/fonts"
  python3 "$APP_DIR/scripts/apply_config.py" || warn "could not generate the default config (is python3 installed?)"
}

python_check() {
  command -v python3 >/dev/null || die "python3 is missing."
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || die "Python 3.8 or newer is required."
  python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk; import cairo" 2>/dev/null \
    || warn "Python GTK bindings not found - the settings window (stats-widget config) and move mode need them."
}

# ── entry point ─────────────────────────────────────────────────────────
usage() {
  cat <<USAGE
Stats Widget installer ($DISTRO_NAME)
  --widget-only   only (re)install the widget; skip system packages and eww
  --no-eww        install packages + widget but do not build eww
  --no-deps       skip system packages (you installed them yourself)
  --autostart     start the widget automatically when you log in
  --start         start the widget when the install finishes
  -h, --help      this text
USAGE
}

run_installer() {
  local deps=1 eww=1 autostart=0 start=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --widget-only) deps=0; eww=0 ;;
      --no-eww) eww=0 ;;
      --no-deps) deps=0 ;;
      --autostart) autostart=1 ;;
      --start) start=1 ;;
      -h|--help) usage; exit 0 ;;
      *) warn "unknown option: $1" ;;
    esac; shift
  done
  [ "$(id -u)" -ne 0 ] || [ -n "${STATS_WIDGET_ALLOW_ROOT:-}" ] || die "Run this as your normal user, not as root (it asks for sudo when needed)."
  say "Detected: $DISPLAY_NAME"
  if [ $deps -eq 1 ]; then need_root; install_packages || die "Package installation failed."; fi
  if [ $eww -eq 1 ]; then ensure_eww; fi
  python_check
  cleanup_legacy
  install_widget
  [ $autostart -eq 1 ] && "$BIN_DIR/stats-widget" autostart on
  echo
  say "Done!  Start the widget with:   stats-widget start"
  echo "   Settings window:  stats-widget config      Move it:  right-click the widget"
  case ":$PATH:" in *":$BIN_DIR:"*) ;; *) warn "$BIN_DIR is not in your PATH yet - log out and back in (or run: export PATH=\"$BIN_DIR:\$PATH\")." ;; esac
  [ $start -eq 1 ] && "$BIN_DIR/stats-widget" start
  return 0
}
