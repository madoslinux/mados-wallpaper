"""Workspace card widget for mados-wallpaper."""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GdkPixbuf


class WorkspaceCard(Gtk.Box):
    def __init__(self, workspace: int, wallpaper: dict | None, on_click=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.workspace = workspace
        self.wallpaper = wallpaper
        self.on_click = on_click
        self.set_css_classes(["workspace-card"])
        self.set_size_request(170, 150)

        label = Gtk.Label(label=f"Workspace {workspace}")
        label.set_css_classes(["workspace-label"])
        self.append(label)

        if wallpaper and os.path.exists(wallpaper["path"]):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(wallpaper["path"], 150, 90, True)
                image = Gtk.Picture.new_for_pixbuf(pixbuf)
            except Exception:
                image = Gtk.Image.new_from_icon_name("image-x-generic")
        else:
            image = Gtk.Image.new_from_icon_name("image-missing")
            image.set_pixel_size(40)

        image.set_css_classes(["wallpaper-thumb"])
        self.append(image)

        filename = wallpaper["filename"] if wallpaper else "No wallpaper"
        name_label = Gtk.Label(label=filename[:20])
        name_label.set_css_classes(["wallpaper-name"])
        self.append(name_label)

        event = Gtk.EventControllerMotion.new()
        event.connect("enter", self._on_enter)
        event.connect("leave", self._on_leave)
        self.add_controller(event)

        click = Gtk.GestureClick.new()
        click.connect("pressed", self._on_click_gesture)
        self.add_controller(click)

    def _on_enter(self, controller, x, y):
        self.set_css_classes(["workspace-card", "hovered"])

    def _on_leave(self, controller):
        self.set_css_classes(["workspace-card"])

    def _on_click_gesture(self, gesture, n_press, x, y):
        if self.on_click:
            self.on_click(self.workspace)