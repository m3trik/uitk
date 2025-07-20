# !/usr/bin/python
# coding=utf-8
from qtpy import QtGui, QtCore
import importlib.resources
from pathlib import Path


class IconManager:
    _cache = {}
    _icon_dirs = []  # List of extra Path objects to search before defaults

    @classmethod
    def register_icon_dir(cls, path):
        """Register an additional icon directory (searched first)."""
        path = Path(path)
        if path not in cls._icon_dirs:
            cls._icon_dirs.insert(0, path)  # Insert at front for precedence

    @classmethod
    def get(cls, name: str, size=(16, 16)) -> QtGui.QIcon:
        icon_key = (name, size)
        if icon_key in cls._cache:
            return cls._cache[icon_key]

        icon = None

        # 1. Check any registered custom icon directories
        for icon_dir in cls._icon_dirs:
            file_path = icon_dir / f"{name}.svg"
            if file_path.exists():
                icon = QtGui.QIcon(str(file_path))
                break

        # 2. Package resources
        if icon is None:
            try:
                icon_path = importlib.resources.files("uitk.icons") / f"{name}.svg"
                with importlib.resources.as_file(icon_path) as file_path:
                    icon = QtGui.QIcon(str(file_path))
            except Exception:
                pass

        # 3. Fallback: local dev path
        if icon is None:
            icon_dir = Path(__file__).parent.parent.parent / "icons"
            file_path = icon_dir / f"{name}.svg"
            if file_path.exists():
                icon = QtGui.QIcon(str(file_path))

        if icon is None:
            icon = QtGui.QIcon()  # Return empty icon

        cls._cache[icon_key] = icon
        return icon

    @classmethod
    def set_icon(cls, widget, name: str, size=(16, 16)):
        icon = cls.get(name, size)
        widget.setIcon(icon)
        widget.setIconSize(QtCore.QSize(*size))


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------
