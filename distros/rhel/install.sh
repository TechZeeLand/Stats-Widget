#!/usr/bin/env bash
# shellcheck disable=SC2034,SC1091
# SPDX-License-Identifier: AGPL-3.0-or-later
# RHEL / AlmaLinux / Rocky / CentOS Stream / Oracle Linux 9 and 10  (needs EPEL + CRB)
. "$(dirname "$(readlink -f "$0")")/../../lib/common.sh"
DISPLAY_NAME="${DISPLAY_NAME:-RHEL family}"
install_packages() {
  $SUDO dnf install -y epel-release || warn "could not install epel-release (on RHEL itself see docs/INSTALL.md)"
  $SUDO dnf install -y dnf-plugins-core || true
  # CodeReady Builder / PowerTools holds most -devel packages
  { $SUDO /usr/bin/crb enable || $SUDO dnf config-manager --set-enabled crb || $SUDO dnf config-manager --set-enabled powertools; } 2>/dev/null || true
  $SUDO dnf install -y git gcc pkgconf-pkg-config curl fontconfig pciutils \
    gtk3-devel pango-devel gdk-pixbuf2-devel cairo-devel glib2-devel libdbusmenu-gtk3-devel openssl-devel \
    python3 python3-gobject python3-cairo gtk3 || return 1
  # Wayland layer-shell lives in EPEL; if missing we build the X11-only eww (runs through XWayland)
  if ! $SUDO dnf install -y gtk-layer-shell gtk-layer-shell-devel; then
    warn "gtk-layer-shell not available - building eww with X11 support only (runs through XWayland on Wayland sessions)."
    EWW_FEATURES="x11"
  fi
}
run_installer "$@"
