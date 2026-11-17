#!/usr/bin/env bash
# shellcheck disable=SC2034,SC1091
# SPDX-License-Identifier: AGPL-3.0-or-later
# Fedora Workstation / KDE / Spins and Nobara. (Immutable variants such as Silverblue/Kinoite are not supported.)
. "$(dirname "$(readlink -f "$0")")/../../lib/common.sh"
DISPLAY_NAME="${DISPLAY_NAME:-Fedora}"
install_packages() {
  $SUDO dnf install -y git gcc pkgconf-pkg-config curl fontconfig pciutils \
    gtk3-devel gtk-layer-shell-devel pango-devel gdk-pixbuf2-devel cairo-devel glib2-devel \
    libdbusmenu-gtk3-devel openssl-devel \
    python3 python3-gobject python3-cairo gtk3 gtk-layer-shell
}
run_installer "$@"
