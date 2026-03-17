#!/usr/bin/env python3
"""Main application for mados-wallpaper."""

import json
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from . import __app_id__, __app_name__, __version__
from .config import CONFIG_DIR, ICON_SIZE, STATE_FILE, WALLPAPER_DIRS, WINDOW_HEIGHT, WINDOW_WIDTH
from .theme import get_css
from .wallpaper_scanner import detect_compositor, scan_wallpaper_dirs, set_hyprland_wallpaper, set_sway_wallpaper


class WallpaperApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=__app_id__)
        self.connect("activate", self._on_activate)
        self._wallpapers = []
        self._selected_wallpaper = None
        self._compositor = detect_compositor()
        self._load_state()

    def _on_activate(self, _app: Gtk.Application) -> None:
        self._build_ui()
        self._scan_wallpapers()
        self._load_current_wallpaper()
        self._apply_css()
        self.window.show_all()

    def _apply_css(self) -> None:
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(get_css())
        screen = Gdk.Screen.get_default()
        if screen:
            context = Gtk.StyleContext()
            context.add_provider_for_screen(screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _build_ui(self) -> None:
        self.window = Gtk.ApplicationWindow(application=self, title=__app_name__)
        self.window.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.window.set_resizable(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Gtk.Label()
        header.set_markup(f"<span weight='bold' size='large'>{__app_name__}</span>")
        header.set_property("halign", Gtk.Align.START)
        header.set_property("margin", 12)
        header.set_property("margin-bottom", 8)
        header.set_name("header")
        vbox.pack_start(header, False, False, 0)

        self._scrolled = Gtk.ScrolledWindow()
        self._scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._scrolled.set_property("margin", 8)
        vbox.pack_start(self._scrolled, True, True, 0)

        self._flowbox = Gtk.FlowBox()
        self._flowbox.set_valign(Gtk.Align.START)
        self._flowbox.set_max_children_per_line(2)
        self._flowbox.set_property("margin", 4)
        self._scrolled.add(self._flowbox)

        button_box = Gtk.Box(spacing=8, homogeneous=True)
        button_box.set_property("margin", 12)

        self._apply_button = Gtk.Button(label="Apply Wallpaper")
        self._apply_button.connect("clicked", self._on_apply_clicked)
        self._apply_button.set_name("btn")
        button_box.pack_start(self._apply_button, True, True, 0)

        self._refresh_button = Gtk.Button(label="Refresh")
        self._refresh_button.connect("clicked", self._on_refresh_clicked)
        self._refresh_button.set_name("btn")
        button_box.pack_start(self._refresh_button, True, True, 0)

        vbox.pack_start(button_box, False, False, 0)

        self._status_label = Gtk.Label()
        self._status_label.set_property("margin", 8)
        self._status_label.set_property("halign", Gtk.Align.CENTER)
        if self._compositor:
            self._status_label.set_text(f"Detected compositor: {self._compositor}")
        else:
            self._status_label.set_text("No compositor detected (Sway/Hyprland)")
        vbox.pack_start(self._status_label, False, False, 0)

        self.window.add(vbox)

    def _scan_wallpapers(self) -> None:
        dirs = os.environ.get("WALLPAPER_DIRS", "").split(":") if "WALLPAPER_DIRS" in os.environ else WALLPAPER_DIRS
        self._wallpapers = scan_wallpaper_dirs(dirs)
        self._populate_grid()

    def _populate_grid(self) -> None:
        for child in self._flowbox.get_children():
            self._flowbox.remove(child)

        for wp in self._wallpapers:
            item = self._create_wallpaper_item(wp)
            self._flowbox.add(item)

    def _create_wallpaper_item(self, wp) -> Gtk.EventBox:
        event_box = Gtk.EventBox()
        event_box.set_property("width-request", 160)
        event_box.set_property("height-request", 140)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(wp.path, 140, 100, True)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            image.set_name("wallpaper-image")
        except Exception:
            image = Gtk.Image.new_from_icon_name("image-x-generic", Gtk.IconSize.DIALOG)
            image.set_name("wallpaper-image")

        image.set_property("margin", 4)
        vbox.pack_start(image, False, False, 0)

        label = Gtk.Label(label=wp.filename)
        label.set_name("wallpaper-name")
        label.set_ellipsize(3)
        label.set_property("max-width-chars", 18)
        label.set_property("margin", 4)
        vbox.pack_start(label, False, False, 0)

        event_box.add(vbox)
        event_box.connect("button-press-event", self._on_wallpaper_selected, wp)

        return event_box

    def _on_wallpaper_selected(self, widget: Gtk.Widget, event: Gdk.Event, wp) -> None:
        self._selected_wallpaper = wp
        self._status_label.set_text(f"Selected: {wp.filename}")

    def _on_apply_clicked(self, button: Gtk.Button) -> None:
        if not self._selected_wallpaper:
            self._status_label.set_text("Please select a wallpaper first")
            return

        if not self._compositor:
            self._status_label.set_text("No compositor detected")
            return

        success = False
        if self._compositor == "sway":
            success = set_sway_wallpaper(self._selected_wallpaper.path)
        elif self._compositor == "hyprland":
            success = set_hyprland_wallpaper(self._selected_wallpaper.path)

        if success:
            self._save_state()
            self._status_label.set_text(f"Applied: {self._selected_wallpaper.filename}")
        else:
            self._status_label.set_text("Failed to set wallpaper")

    def _on_refresh_clicked(self, button: Gtk.Button) -> None:
        self._scan_wallpapers()
        self._status_label.set_text(f"Found {len(self._wallpapers)} wallpapers")

    def _load_state(self) -> None:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
                    self._selected_path = state.get("last_wallpaper")
            except (json.JSONDecodeError, IOError):
                self._selected_path = None

    def _save_state(self) -> None:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        state = {
            "last_wallpaper": self._selected_wallpaper.path if self._selected_wallpaper else None,
            "compositor": self._compositor,
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)

    def _load_current_wallpaper(self) -> None:
        if hasattr(self, "_selected_path") and self._selected_path:
            for wp in self._wallpapers:
                if wp.path == self._selected_path:
                    self._selected_wallpaper = wp
                    break