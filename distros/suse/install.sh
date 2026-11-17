#!/usr/bin/env bash
# shellcheck disable=SC2034,SC1091
# SPDX-License-Identifier: AGPL-3.0-or-later
# openSUSE Tumbleweed / Leap / Slowroll, SUSE Linux Enterprise (with PackageHub)
. "$(dirname "$(readlink -f "$0")")/../../lib/common.sh"
DISPLAY_NAME="${DISPLAY_NAME:-openSUSE / SUSE}"
install_packages() {
  $SUDO zypper --non-interactive install -y git gcc make pkg-config curl fontconfig pciutils \
    gtk3-devel pango-devel gdk-pixbuf-devel cairo-devel glib2-devel libdbusmenu-gtk3-devel libopenssl-devel \
    python3 python3-gobject python3-gobject-Gdk python3-cairo typelib-1_0-Gtk-3_0 || return 1
  if ! $SUDO zypper --non-interactive install -y gtk-layer-shell-devel typelib-1_0-GtkLayerShell-0_1; then
    warn "gtk-layer-shell not available - building eww with X11 support only (runs through XWayland on Wayland sessions)."
    EWW_FEATURES="x11"
  fi
}
run_installer "$@"
