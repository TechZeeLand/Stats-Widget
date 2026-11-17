#!/usr/bin/env bash
# shellcheck disable=SC2034,SC1091
# SPDX-License-Identifier: AGPL-3.0-or-later
# Arch Linux, Manjaro, EndeavourOS, Garuda, CachyOS, Artix ...
. "$(dirname "$(readlink -f "$0")")/../../lib/common.sh"
DISPLAY_NAME="${DISPLAY_NAME:-Arch family}"
install_packages() {
  $SUDO pacman -S --needed --noconfirm base-devel git curl fontconfig pciutils \
    gtk3 gtk-layer-shell pango gdk-pixbuf2 cairo glib2 libdbusmenu-gtk3 openssl \
    python python-gobject python-cairo
}
run_installer "$@"
