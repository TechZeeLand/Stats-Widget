#!/usr/bin/env bash
# shellcheck disable=SC2034,SC1091
# SPDX-License-Identifier: AGPL-3.0-or-later
# Debian 12+, Ubuntu 22.04+, Linux Mint, Pop!_OS, elementary, Zorin, Kali ...
. "$(dirname "$(readlink -f "$0")")/../../lib/common.sh"
DISPLAY_NAME="${DISPLAY_NAME:-Debian / Ubuntu family}"
install_packages() {
  export DEBIAN_FRONTEND=noninteractive
  $SUDO apt-get update
  $SUDO apt-get install -y git build-essential pkg-config curl ca-certificates fontconfig pciutils \
    libgtk-3-dev libpango1.0-dev libgdk-pixbuf-2.0-dev libcairo2-dev libglib2.0-dev libdbusmenu-gtk3-dev libssl-dev \
    python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 || return 1
  # layer-shell (Wayland) packages are missing in very old releases
  if ! $SUDO apt-get install -y libgtk-layer-shell-dev gir1.2-gtklayershell-0.1; then
    warn "libgtk-layer-shell not available - building eww with X11 support only (runs through XWayland on Wayland sessions)."
    EWW_FEATURES="x11"
  fi
}
run_installer "$@"
