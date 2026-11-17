#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Move mode.  Right-click the widget (or `stats-widget move`) -> the screen dims and a ghost of the
widget appears. Drag it where you want it.
    Enter / double-click = save      Esc = cancel      arrow keys = nudge 1px (Shift = 10px)
eww windows cannot be dragged directly, so this places the real widget exactly where the ghost was."""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from common import load_config, reload_widget, save_config, widget_size  # noqa: E402
from apply_config import apply  # noqa: E402

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
except (ValueError, ImportError):
    GtkLayerShell = None

SNAP = 14
W, H = widget_size(load_config())          # the ghost has the same size as the widget


class Mover(Gtk.Window):
    def __init__(self):
        super().__init__(title="Move Stats Widget")
        self.cfg = load_config()
        p = self.cfg["position"]
        self.x, self.y = int(p["x"]), int(p["y"])
        self.grab = None
        self.guides = []
        self.set_app_paintable(True)
        self.set_decorated(False)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)

        monitor = str(p["monitor"])
        display = Gdk.Display.get_default()
        mon_index = int(monitor) if monitor.lstrip("-").isdigit() and int(monitor) < display.get_n_monitors() else 0
        use_layer = GtkLayerShell is not None and GtkLayerShell.is_supported()
        if use_layer:
            # Same coordinate origin as the real widget (respects your panels), so what you see is what you get.
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_namespace(self, "stats-widget-move")
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
            GtkLayerShell.set_monitor(self, display.get_monitor(mon_index))
            for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT, GtkLayerShell.Edge.BOTTOM):
                GtkLayerShell.set_anchor(self, edge, True)
        else:
            geo = display.get_monitor(mon_index).get_geometry()
            self.set_default_size(geo.width, geo.height)     # explicit size/position in case no WM honours fullscreen
            self.move(geo.x, geo.y)
            self.fullscreen_on_monitor(self.get_screen(), mon_index)
            self.set_keep_above(True)

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("draw", self.on_draw)
        self.connect("button-press-event", self.on_press)
        self.connect("button-release-event", self.on_release)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("key-press-event", self.on_key)
        self.connect("destroy", Gtk.main_quit)

    # -- geometry helpers --------------------------------------------------
    def clamp(self):
        sw, sh = self.get_allocated_width(), self.get_allocated_height()
        self.guides = []
        for edge_val, target, axis in ((self.x, 0, "x"), (self.x + W, sw, "x"), (self.x + W / 2, sw / 2, "x"),
                                       (self.y, 0, "y"), (self.y + H, sh, "y"), (self.y + H / 2, sh / 2, "y")):
            if abs(edge_val - target) <= SNAP:
                if axis == "x":
                    self.x += int(target - edge_val)
                else:
                    self.y += int(target - edge_val)
                self.guides.append((axis, target))
        self.x = max(0, min(self.x, max(0, sw - W)))
        self.y = max(0, min(self.y, max(0, sh - H)))

    def on_draw(self, widget, cr):
        sw, sh = self.get_allocated_width(), self.get_allocated_height()
        cr.set_operator(0)                     # CLEAR
        cr.paint()
        cr.set_operator(2)                     # OVER
        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.paint()
        # snap guides
        cr.set_source_rgba(1, 0.8, 0, 0.9)
        cr.set_line_width(1)
        for axis, pos in self.guides:
            if axis == "x":
                cr.move_to(pos + 0.5, 0); cr.line_to(pos + 0.5, sh)
            else:
                cr.move_to(0, pos + 0.5); cr.line_to(sw, pos + 0.5)
            cr.stroke()
        # ghost
        cr.rectangle(self.x, self.y, W, H)
        cr.set_source_rgba(0.1, 0.1, 0.1, 0.92)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 1)
        cr.set_line_width(4)
        cr.stroke()
        for cx in (self.x + W * 249 / 795, self.x + W * 514 / 795):   # the three columns
            cr.move_to(cx, self.y); cr.line_to(cx, self.y + H)
        cr.set_line_width(2); cr.stroke()
        cr.set_source_rgba(1, 1, 1, 1)
        cr.select_font_face("sans-serif", 0, 1)
        cr.set_font_size(22)
        label = f"x = {self.x}   y = {self.y}"
        cr.move_to(self.x + W / 2 - cr.text_extents(label).width / 2, self.y + H / 2)
        cr.show_text(label)
        cr.set_font_size(15)
        cr.select_font_face("sans-serif", 0, 0)
        hint = "Drag to move  ·  Enter / double-click = save  ·  Esc = cancel  ·  arrows = nudge"
        cr.move_to(self.x + W / 2 - cr.text_extents(hint).width / 2, self.y + H / 2 + 32)
        cr.show_text(hint)
        return False

    # -- events ------------------------------------------------------------
    def on_press(self, widget, ev):
        if ev.type == Gdk.EventType._2BUTTON_PRESS:
            return self.save()
        if self.x <= ev.x <= self.x + W and self.y <= ev.y <= self.y + H:
            self.grab = (ev.x - self.x, ev.y - self.y)
        else:                                   # click outside: jump the ghost there (centered)
            self.grab = (W / 2, H / 2)
            self.on_motion(widget, ev)

    def on_motion(self, widget, ev):
        if self.grab:
            self.x, self.y = int(ev.x - self.grab[0]), int(ev.y - self.grab[1])
            self.clamp()
            self.queue_draw()

    def on_release(self, widget, ev):
        self.grab = None
        self.guides = []
        self.queue_draw()

    def on_key(self, widget, ev):
        step = 10 if ev.state & Gdk.ModifierType.SHIFT_MASK else 1
        key = Gdk.keyval_name(ev.keyval)
        if key == "Escape":
            self.destroy()
        elif key in ("Return", "KP_Enter", "space"):
            self.save()
        elif key in ("Left", "Right", "Up", "Down"):
            self.x += {"Left": -step, "Right": step}.get(key, 0)
            self.y += {"Up": -step, "Down": step}.get(key, 0)
            self.clamp()
            self.queue_draw()

    def save(self):
        self.cfg["position"].update(anchor="top left", x=self.x, y=self.y)
        save_config(self.cfg)
        apply()
        reload_widget()
        self.destroy()


if __name__ == "__main__":
    win = Mover()
    win.show_all()
    win.present()
    Gtk.main()
