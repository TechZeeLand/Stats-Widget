#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Stats Widget - one-line installer
#
#   curl -fsSL https://raw.githubusercontent.com/TechZeeLand/Stats-Widget/main/install.sh | bash
#
# Options go after "bash -s --":   ... | bash -s -- --autostart --start
# Detects your distribution family, installs the dependencies, builds eww if needed and installs the widget.
set -euo pipefail

REPO="${STATS_WIDGET_REPO:-https://github.com/TechZeeLand/Stats-Widget}"
REF="${STATS_WIDGET_REF:-main}"

say() { printf '\033[1;36m→\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Linux" ] || die "Stats Widget runs on Linux only."

# ── 1. detect the distribution family ───────────────────────────────────
family_of() {
  local id="" like=""
  # shellcheck disable=SC1091
  [ -r /etc/os-release ] && . /etc/os-release && id="${ID:-}" && like="${ID_LIKE:-}"
  for token in $id $like; do
    case "$token" in
      fedora)                                   echo fedora; return ;;
      rhel|centos|almalinux|rocky|ol|scientific) echo rhel;   return ;;
      debian|ubuntu|linuxmint|pop|elementary|zorin|kali|raspbian) echo debian; return ;;
      arch|manjaro|endeavouros|garuda|cachyos|artix) echo arch; return ;;
      suse|opensuse*|sles|sled)                 echo suse;    return ;;
    esac
  done
  echo generic
}
FAMILY="${STATS_WIDGET_DISTRO:-$(family_of)}"
# shellcheck disable=SC1091
PRETTY="$( (. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-$ID}") || echo Linux)"
say "Detected $PRETTY  →  installer family: $FAMILY"
export DISPLAY_NAME="$PRETTY"

# ── 2. run from a local checkout, or download one ───────────────────────
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$HERE" ] && [ -f "$HERE/distros/$FAMILY/install.sh" ]; then
  SRC="$HERE"
else
  command -v curl >/dev/null || die "curl is required (install it with your package manager and retry)."
  command -v tar  >/dev/null || die "tar is required."
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  say "Downloading Stats Widget ($REF)"
  curl -fsSL "$REPO/archive/refs/heads/$REF.tar.gz" | tar -xz -C "$TMP" --strip-components=1 \
    || die "Download failed. Check your internet connection or $REPO"
  SRC="$TMP"
fi

exec bash "$SRC/distros/$FAMILY/install.sh" "$@"
