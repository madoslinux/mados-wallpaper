"""Workspace card widget for mados-wallpaper."""

import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf


class WorkspaceCard(Gtk.Box):
    def __init__(
        self, workspace: int, wallpaper: dict | None, on_click=None, on_mode_click=None
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.workspace = workspace
        self.wallpaper = wallpaper
        self.on_click = on_click
        self.on_mode_click = on_mode_click
        self.set_size_request(170, 150)
        self.get_style_context().add_class("workspace-card")

        label = Gtk.Label(label=f"Workspace {workspace}")
        label.get_style_context().add_class("workspace-label")
        self.pack_start(label, False, False, 0)

        if wallpaper and os.path.exists(wallpaper["path"]):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    wallpaper["path"], 150, 90, True
                )
                image = Gtk.Image.new_from_pixbuf(pixbuf)
            except Exception:
                image = Gtk.Image.new_from_icon_name(
                    "image-x-generic", Gtk.IconSize.DIALOG
                )
        else:
            image = Gtk.Image.new_from_icon_name("image-missing", Gtk.IconSize.DIALOG)
            image.set_pixel_size(40)

        image.get_style_context().add_class("wallpaper-thumb")

        image_event = Gtk.EventBox()
        image_event.add(image)
        image_event.connect("button_press_event", self._on_image_click)
        self.pack_start(image_event, False, False, 0)

        filename = wallpaper["filename"] if wallpaper else "No wallpaper"
        name_label = Gtk.Label(label=filename[:20])
        name_label.get_style_context().add_class("wallpaper-name")
        self.pack_start(name_label, False, False, 0)

        mode_text = f"Mode: {wallpaper.get('mode', 'fill')}" if wallpaper else ""
        mode_btn = Gtk.Button(label=mode_text)
        mode_btn.set_size_request(100, 24)
        mode_btn.get_style_context().add_class("mode-button")
        mode_btn.connect("clicked", self._on_mode_btn_click)

        mode_btn_event = Gtk.EventBox()
        mode_btn_event.add(mode_btn)
        mode_btn_event.connect("enter_notify_event", self._on_mode_enter)
        mode_btn_event.connect("leave_notify_event", self._on_mode_leave)
        mode_btn_event.connect("button_press_event", self._on_mode_click_gesture)
        self.pack_start(mode_btn_event, False, False, 0)

        self.connect("enter_notify_event", self._on_enter)
        self.connect("leave_notify_event", self._on_leave)

    def _on_enter(self, widget, event):
        self.get_style_context().add_class("hovered")

    def _on_leave(self, widget, event):
        self.get_style_context().remove_class("hovered")

    def _on_mode_enter(self, widget, event):
        self.get_style_context().add_class("mode-hovered")

    def _on_mode_leave(self, widget, event):
        self.get_style_context().remove_class("mode-hovered")

    def _on_mode_click_gesture(self, gesture, event):
        if self.on_mode_click:
            self.on_mode_click(self.workspace, self.wallpaper)

    def _on_mode_btn_click(self, button):
        if self.on_mode_click:
            self.on_mode_click(self.workspace, self.wallpaper)

    def _on_image_click(self, widget, event):
        if self.on_click:
            self.on_click(self.workspace)
