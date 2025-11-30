# !/usr/bin/python
# coding=utf-8
import re
from qtpy import QtGui, QtCore, QtWidgets
import importlib.resources
from pathlib import Path


class IconManager:
    """Theme-aware SVG icon loader with caching and color customization."""

    _cache = {}
    _icon_dirs = []  # List of extra Path objects to search before defaults
    _svg_cache = {}  # Cache for raw SVG content
    _widget_icons = {}  # Track widgets and their icon settings for theme updates
    _default_color = None  # Default icon color (set by theme)
    _last_update_color = (
        {}
    )  # Track last color applied per widget to avoid redundant updates

    @classmethod
    def set_default_color(cls, color: str):
        """Set the default icon color for icons created without explicit color.

        This is typically called when a theme is applied.
        """
        color = cls._normalize_color(color)
        if cls._default_color != color:
            cls._default_color = color
            # Clear caches to force re-creation with new color
            cls._cache.clear()
            cls._last_update_color.clear()

    @staticmethod
    def _normalize_color(color: str) -> str:
        """Normalize color to lowercase hex format for consistent comparison.

        Converts rgb(r,g,b) to #rrggbb format.
        """
        if not color:
            return color

        color = color.strip().lower()

        # Already hex format
        if color.startswith("#"):
            return color

        # Convert rgb(r,g,b) to hex
        import re

        match = re.match(r"rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", color)
        if match:
            r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f"#{r:02x}{g:02x}{b:02x}"

        # Return as-is if can't parse
        return color

    @classmethod
    def register_icon_dir(cls, path):
        """Register an additional icon directory (searched first)."""
        path = Path(path)
        if path not in cls._icon_dirs:
            cls._icon_dirs.insert(0, path)  # Insert at front for precedence

    @classmethod
    def _load_svg_content(cls, name: str) -> str:
        """Load raw SVG content from file."""
        if name in cls._svg_cache:
            return cls._svg_cache[name]

        svg_content = None

        # 1. Check any registered custom icon directories
        for icon_dir in cls._icon_dirs:
            file_path = icon_dir / f"{name}.svg"
            if file_path.exists():
                svg_content = file_path.read_text(encoding="utf-8")
                break

        # 2. Package resources
        if svg_content is None:
            try:
                icon_path = importlib.resources.files("uitk.icons") / f"{name}.svg"
                with importlib.resources.as_file(icon_path) as file_path:
                    svg_content = Path(file_path).read_text(encoding="utf-8")
            except Exception:
                pass

        # 3. Fallback: local dev path
        if svg_content is None:
            icon_dir = Path(__file__).parent.parent.parent / "icons"
            file_path = icon_dir / f"{name}.svg"
            if file_path.exists():
                svg_content = file_path.read_text(encoding="utf-8")

        if svg_content:
            cls._svg_cache[name] = svg_content

        return svg_content

    @classmethod
    def _colorize_svg(cls, svg_content: str, color: str) -> str:
        """Replace colors in SVG content with the specified color.

        Replaces fill and stroke colors (except 'none') with the new color.
        """
        if not svg_content or not color:
            return svg_content

        # Replace fill colors (but not fill="none")
        svg_content = re.sub(r'fill="(?!none)[^"]*"', f'fill="{color}"', svg_content)
        # Replace stroke colors (but not stroke="none")
        svg_content = re.sub(
            r'stroke="(?!none)[^"]*"', f'stroke="{color}"', svg_content
        )
        return svg_content

    @classmethod
    def _create_icon_from_svg(cls, svg_content: str, size: tuple) -> QtGui.QIcon:
        """Create a QIcon from SVG content string."""
        if not svg_content:
            return QtGui.QIcon()

        # Create icon from SVG data
        svg_data = svg_content.encode("utf-8")

        # Use QPixmap with SVG renderer for better quality
        from qtpy import QtSvg

        renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg_data))
        pixmap = QtGui.QPixmap(QtCore.QSize(*size))
        pixmap.fill(QtCore.Qt.transparent)

        painter = QtGui.QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        return QtGui.QIcon(pixmap)

    @classmethod
    def get(
        cls, name: str, size=(16, 16), color: str = None, use_theme: bool = True
    ) -> QtGui.QIcon:
        """Get an icon, optionally colorized.

        Args:
            name: Icon name (without .svg extension)
            size: Icon size tuple (width, height)
            color: Optional hex color to apply (e.g., "#ffffff").
            use_theme: If True and no color specified, uses the default theme color.

        Returns:
            QIcon instance
        """
        # Use default color if no explicit color and use_theme is True
        effective_color = cls._normalize_color(color) if color else None
        if effective_color is None and use_theme and cls._default_color:
            effective_color = cls._default_color

        icon_key = (name, size, effective_color)
        if icon_key in cls._cache:
            return cls._cache[icon_key]

        if effective_color:
            # Load and colorize SVG
            svg_content = cls._load_svg_content(name)
            if svg_content:
                colorized_svg = cls._colorize_svg(svg_content, effective_color)
                icon = cls._create_icon_from_svg(colorized_svg, size)
            else:
                icon = QtGui.QIcon()
        else:
            # Original behavior - load icon without colorization
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
    def set_icon(
        cls,
        widget,
        name: str,
        size=(16, 16),
        color: str = None,
        auto_theme: bool = True,
    ):
        """Set an icon on a widget.

        Args:
            widget: Widget to set icon on (must have setIcon method)
            name: Icon name (without .svg extension)
            size: Icon size tuple (width, height)
            color: Optional hex color. If None and auto_theme is True, uses theme color.
            auto_theme: If True and no color specified, uses the widget's theme color.
        """
        if color is None and auto_theme:
            # Get color from widget's theme (walks up hierarchy)
            from uitk.widgets.mixins.style_sheet import StyleSheet

            color = StyleSheet.get_icon_color(widget)

            # If we got the fallback color but have a default set, use the default
            # This handles widgets created before being parented to a themed window
            color = cls._normalize_color(color)
            if color == "#888888" and cls._default_color:
                color = cls._default_color
        else:
            color = cls._normalize_color(color)

        icon = cls.get(name, size, color)
        widget.setIcon(icon)
        widget.setIconSize(QtCore.QSize(*size))

        # Register widget for theme updates and track current color
        widget_id = id(widget)
        if auto_theme:
            cls._widget_icons[widget_id] = {
                "widget": widget,
                "name": name,
                "size": size,
            }
            cls._last_update_color[widget_id] = color

    @classmethod
    def update_widget_icons(cls, root_widget: QtWidgets.QWidget, color: str):
        """Update all registered icons under a widget tree with a new color.

        Called when theme changes. Skips widgets already at the target color.
        Also refreshes tree widget item icons.
        """
        color = cls._normalize_color(color)

        # Find all registered widgets that are children of root_widget
        to_remove = []
        for widget_id, info in cls._widget_icons.items():
            widget = info["widget"]
            try:
                # Check if widget still exists
                if widget is None:
                    to_remove.append(widget_id)
                    continue

                # Verify widget is still valid by accessing a property
                _ = widget.objectName()

                # Check if this widget is root or a descendant of root
                if widget is root_widget or root_widget.isAncestorOf(widget):
                    # Skip if already at this color (prevents redundant updates)
                    if cls._last_update_color.get(widget_id) == color:
                        continue

                    icon = cls.get(info["name"], info["size"], color)
                    widget.setIcon(icon)
                    widget.setIconSize(QtCore.QSize(*info["size"]))
                    cls._last_update_color[widget_id] = color
            except RuntimeError:
                # Widget was deleted
                to_remove.append(widget_id)

        # Clean up deleted widgets
        for widget_id in to_remove:
            del cls._widget_icons[widget_id]
            cls._last_update_color.pop(widget_id, None)

        # Also refresh tree widget item icons
        try:
            from uitk.widgets.treeWidget import TreeWidget

            for tree in root_widget.findChildren(TreeWidget):
                if hasattr(tree, "refresh_item_icons"):
                    tree.refresh_item_icons(color)
        except ImportError:
            pass  # TreeWidget not available


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------
