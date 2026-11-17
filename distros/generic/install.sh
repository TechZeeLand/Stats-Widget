#!/usr/bin/env bash
# shellcheck disable=SC2034,SC1091
# SPDX-License-Identifier: AGPL-3.0-or-later
# Any other distribution: installs NO system packages - install these yourself first (names differ per distro):
#   git, a C compiler, pkg-config, curl, fontconfig, pciutils
#   GTK3, gtk-layer-shell, pango, gdk-pixbuf2, cairo, glib2, libdbusmenu-gtk3  (with the -dev/-devel headers)
#   python3 (3.8+) with PyGObject + pycairo
. "$(dirname "$(readlink -f "$0")")/../../lib/common.sh"
DISPLAY_NAME="${DISPLAY_NAME:-generic Linux}"
install_packages() { warn "generic installer: skipping system packages (install them yourself, see docs/INSTALL.md)"; }
run_installer "$@"
