#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Removes the Stats Widget. Your settings (~/.config/stats-widget) are kept unless you pass --purge.
# eww itself (~/.local/bin/eww) is left alone because other widgets may use it.
set -u
APP="${STATS_WIDGET_HOME:-$HOME/.local/share/stats-widget}"
export PATH="$HOME/.local/bin:$PATH"
command -v eww >/dev/null && { eww --config "$APP" close stats; eww --config "$APP" kill; } 2>/dev/null
rm -f "$HOME/.config/autostart/stats-widget.desktop" "$HOME/.local/bin/stats-widget"
rm -rf "$HOME/.local/share/fonts/stats-widget" "$HOME/.cache/stats-widget"
command -v fc-cache >/dev/null && fc-cache -f "$HOME/.local/share/fonts" 2>/dev/null
if [ "${1:-}" = "--purge" ]; then rm -rf "$HOME/.config/stats-widget"; echo "Settings removed."; else echo "Settings kept in ~/.config/stats-widget (use --purge to delete)."; fi
rm -rf "$APP"
echo "Stats Widget removed."
