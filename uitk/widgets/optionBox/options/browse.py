# !/usr/bin/python
# coding=utf-8
"""Browse option for OptionBox - provides file/folder browsing buttons."""

from qtpy import QtWidgets
from ._options import ButtonOption


class BrowseOption(ButtonOption):
    """A file/folder browse button option.

    Opens a native file or directory dialog and writes the selected
    path back to the wrapped widget. Optionally records the value
    to a paired ``RecentValuesOption`` when one is present.

    Example:
        browse = BrowseOption(
            file_types="Maya Files (*.ma *.mb);;All Files (*.*)",
            title="Select Scene",
            start_dir="/projects",
        )
        widget.option_box.add_option(browse)

        # Or via fluent API:
        widget.option_box.browse(
            file_types="Images (*.png *.jpg)",
            title="Select Texture",
        )
    """

    def __init__(
        self,
        wrapped_widget=None,
        file_types=None,
        title="Browse",
        start_dir=None,
        mode="file",
        icon="folder",
        tooltip="Browse...",
        callback=None,
        order=None,
    ):
        """Initialize the browse option.

        Args:
            wrapped_widget: The widget this option is attached to.
            file_types: File filter string for QFileDialog
                (e.g. ``"Images (*.png *.jpg);;All Files (*.*)"``).
                Ignored when *mode* is ``"directory"``.
            title: Dialog window title.
            start_dir: Initial directory for the dialog. When *None*,
                uses the current value of the wrapped widget (if it
                looks like a path) or the user's home directory.
            mode: ``"file"`` (default), ``"files"`` (multi-select),
                ``"save"``, or ``"directory"``.
            icon: Icon name for the button (default: ``"folder"``).
            tooltip: Tooltip text (default: ``"Browse..."``).
            callback: Optional callable invoked with the selected
                path(s) *after* the widget value has been set. Receives
                a single ``str`` for single-select modes or a ``list[str]``
                for ``"files"`` mode.
            order: Explicit sort position (int). See BaseOption.
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon=icon,
            tooltip=tooltip,
            callback=lambda: self.browse(),
            order=order,
        )
        self._file_types = file_types
        self._title = title
        self._start_dir = start_dir
        self._mode = mode
        self._user_callback = callback

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    @property
    def file_types(self):
        return self._file_types

    @file_types.setter
    def file_types(self, value):
        self._file_types = value

    @property
    def start_dir(self):
        return self._start_dir

    @start_dir.setter
    def start_dir(self, value):
        """Set start directory. Accepts a string or a callable returning a string."""
        self._start_dir = value

    def create_widget(self):
        """Create the browse button widget."""
        button = super().create_widget()
        if not button.objectName():
            button.setObjectName("browseButton")
        button.setProperty("class", "BrowseButton")
        return button

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def _resolve_start_dir(self):
        """Determine the starting directory for the dialog."""
        import os

        # Explicit start_dir takes priority (supports callables for lazy eval)
        raw = self._start_dir
        if callable(raw):
            raw = raw()
        if raw:
            return raw if os.path.isdir(raw) else os.path.dirname(raw)

        # Fall back to the current widget value (if it's a plausible path)
        current = self._get_widget_value()
        if current and isinstance(current, str):
            if os.path.isdir(current):
                return current
            parent = os.path.dirname(current)
            if os.path.isdir(parent):
                return parent

        return ""

    def browse(self):
        """Open the appropriate file dialog and apply the result."""
        start = self._resolve_start_dir()
        result = None

        if self._mode == "directory":
            path = QtWidgets.QFileDialog.getExistingDirectory(
                self._find_parent_window(),
                self._title,
                start,
            )
            if path:
                result = path

        elif self._mode == "save":
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self._find_parent_window(),
                self._title,
                start,
                self._file_types or "All Files (*.*)",
            )
            if path:
                result = path

        elif self._mode == "files":
            paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
                self._find_parent_window(),
                self._title,
                start,
                self._file_types or "All Files (*.*)",
            )
            if paths:
                result = paths

        else:  # "file" (default)
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self._find_parent_window(),
                self._title,
                start,
                self._file_types or "All Files (*.*)",
            )
            if path:
                result = path

        if result is None:
            return

        # Write value to wrapped widget
        display = result if isinstance(result, str) else result[0]
        self._set_widget_value(display)

        # Record to paired RecentValuesOption if one exists
        self._record_recent(display)

        # Fire user callback
        if self._user_callback:
            self._user_callback(result)

    def _record_recent(self, value):
        """Record *value* to a sibling RecentValuesOption, if present."""
        from .recent_values import RecentValuesOption

        widget = self.wrapped_widget
        if widget is None:
            return

        mgr = getattr(widget, "_option_box_manager", None)
        if mgr is None:
            return

        recent = mgr.find_option(RecentValuesOption)
        if recent is not None:
            recent.record(value)
