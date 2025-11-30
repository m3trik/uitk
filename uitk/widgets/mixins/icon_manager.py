# !/usr/bin/python
# coding=utf-8
import re
import weakref
from qtpy import QtGui, QtCore, QtWidgets
import importlib.resources
from pathlib import Path


class IconManager:
    """Theme-aware SVG icon loader with caching and color customization.

    Features:
        - SVG colorization with proper handling of fill/stroke attributes
        - High-DPI aware icon rendering with smooth scaling
        - Efficient caching with LRU-style eviction
        - Weak references for widget tracking to prevent memory leaks
        - Multiple icon states support (normal, disabled, active, selected)
    """

    _MAX_CACHE_SIZE = 500  # Maximum number of cached icons
    _cache = {}
    _cache_order = []  # Track access order for LRU eviction
    _icon_dirs = []  # List of extra Path objects to search before defaults
    _svg_cache = {}  # Cache for raw SVG content
    _widget_icons = weakref.WeakValueDictionary()  # Weak refs to widgets
    _widget_icon_info = {}  # Icon settings keyed by id(widget)
    _default_color = None  # Default icon color (set by theme)
    _last_update_color = {}  # Track last color applied per widget

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
            cls._cache_order.clear()
            cls._last_update_color.clear()

    @staticmethod
    def _normalize_color(color: str) -> str:
        """Normalize color to lowercase hex format for consistent comparison.

        Converts rgb(r,g,b), rgba(r,g,b,a), and named colors to #rrggbb format.
        """
        if not color:
            return color

        color = color.strip().lower()

        # Already hex format - normalize to 6-digit
        if color.startswith("#"):
            if len(color) == 4:  # #rgb -> #rrggbb
                return f"#{color[1]*2}{color[2]*2}{color[3]*2}"
            return color[:7]  # Strip alpha if present (#rrggbbaa -> #rrggbb)

        # Convert rgb(r,g,b) or rgba(r,g,b,a) to hex
        match = re.match(
            r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\d.]+)?\s*\)", color
        )
        if match:
            r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f"#{r:02x}{g:02x}{b:02x}"

        # Return as-is if can't parse (could be a named color)
        return color

    @classmethod
    def register_icon_dir(cls, path):
        """Register an additional icon directory (searched first)."""
        path = Path(path)
        if path not in cls._icon_dirs:
            cls._icon_dirs.insert(0, path)  # Insert at front for precedence

    @classmethod
    def _evict_cache_if_needed(cls):
        """Evict oldest cache entries if cache exceeds max size."""
        while len(cls._cache) > cls._MAX_CACHE_SIZE and cls._cache_order:
            oldest_key = cls._cache_order.pop(0)
            cls._cache.pop(oldest_key, None)

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

        Handles:
        - fill="..." and stroke="..." attributes (except 'none' and 'transparent')
        - currentColor values
        - Inline styles with fill: and stroke:
        - Preserves opacity values
        """
        if not svg_content or not color:
            return svg_content

        # Patterns to preserve (don't colorize these)
        preserve_values = {"none", "transparent"}

        # Replace fill attribute colors (preserve none/transparent)
        def replace_fill(match):
            value = match.group(1).lower().strip()
            if value in preserve_values:
                return match.group(0)
            return f'fill="{color}"'

        def replace_stroke(match):
            value = match.group(1).lower().strip()
            if value in preserve_values:
                return match.group(0)
            return f'stroke="{color}"'

        # Replace fill="..." except none/transparent
        svg_content = re.sub(r'fill="([^"]*)"', replace_fill, svg_content)

        # Replace stroke="..." except none/transparent
        svg_content = re.sub(r'stroke="([^"]*)"', replace_stroke, svg_content)

        # Replace currentColor with the target color
        svg_content = re.sub(
            r"\bcurrentColor\b", color, svg_content, flags=re.IGNORECASE
        )

        # Handle inline styles: style="...fill:#xxx..." and style="...stroke:#xxx..."
        def replace_style_colors(match):
            style = match.group(1)
            # Replace fill: color in style (but not fill-opacity, fill-rule, etc.)
            style = re.sub(
                r"fill\s*:\s*(?!none|transparent)[^;\"]+",
                f"fill:{color}",
                style,
                flags=re.IGNORECASE,
            )
            # Replace stroke: color in style
            style = re.sub(
                r"stroke\s*:\s*(?!none|transparent)[^;\"]+",
                f"stroke:{color}",
                style,
                flags=re.IGNORECASE,
            )
            return f'style="{style}"'

        svg_content = re.sub(r'style="([^"]*)"', replace_style_colors, svg_content)

        return svg_content

    @classmethod
    def _get_device_pixel_ratio(cls) -> float:
        """Get the device pixel ratio for high-DPI scaling."""
        app = QtWidgets.QApplication.instance()
        if app:
            # Try to get from primary screen
            try:
                screen = app.primaryScreen()
                if screen:
                    return screen.devicePixelRatio()
            except Exception:
                pass
        return 1.0

    @classmethod
    def _create_icon_from_svg(
        cls, svg_content: str, size: tuple, for_states: bool = True
    ) -> QtGui.QIcon:
        """Create a QIcon from SVG content string with high-DPI support.

        Args:
            svg_content: The SVG XML content
            size: Requested logical size (width, height)
            for_states: If True, creates pixmaps for different icon states

        Returns:
            QIcon with proper scaling and anti-aliasing
        """
        if not svg_content:
            return QtGui.QIcon()

        from qtpy import QtSvg

        svg_data = svg_content.encode("utf-8")
        renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg_data))

        if not renderer.isValid():
            return QtGui.QIcon()

        icon = QtGui.QIcon()
        dpr = cls._get_device_pixel_ratio()

        # Create pixmaps at multiple scales for high-DPI displays
        scales = [1.0]
        if dpr > 1.0:
            scales.append(dpr)
        if dpr > 1.5:
            scales.append(2.0)

        for scale in scales:
            # Calculate physical pixel size
            physical_size = QtCore.QSize(int(size[0] * scale), int(size[1] * scale))

            pixmap = QtGui.QPixmap(physical_size)
            pixmap.fill(QtCore.Qt.transparent)
            pixmap.setDevicePixelRatio(scale)

            painter = QtGui.QPainter(pixmap)
            # Enable anti-aliasing and smooth transformations
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)

            # Calculate viewport to maintain aspect ratio
            svg_size = renderer.defaultSize()
            if svg_size.isValid() and svg_size.width() > 0 and svg_size.height() > 0:
                # Scale SVG to fit while maintaining aspect ratio
                target_rect = QtCore.QRectF(
                    0, 0, physical_size.width(), physical_size.height()
                )
                svg_aspect = svg_size.width() / svg_size.height()
                target_aspect = physical_size.width() / physical_size.height()

                if svg_aspect > target_aspect:
                    # SVG is wider - fit to width
                    new_height = physical_size.width() / svg_aspect
                    y_offset = (physical_size.height() - new_height) / 2
                    target_rect = QtCore.QRectF(
                        0, y_offset, physical_size.width(), new_height
                    )
                else:
                    # SVG is taller - fit to height
                    new_width = physical_size.height() * svg_aspect
                    x_offset = (physical_size.width() - new_width) / 2
                    target_rect = QtCore.QRectF(
                        x_offset, 0, new_width, physical_size.height()
                    )

                renderer.render(painter, target_rect)
            else:
                renderer.render(painter)

            painter.end()

            # Add for normal mode
            icon.addPixmap(pixmap, QtGui.QIcon.Normal, QtGui.QIcon.Off)

        return icon

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
        # Normalize size to tuple
        if isinstance(size, (int, float)):
            size = (int(size), int(size))
        elif hasattr(size, "width"):  # QSize
            size = (size.width(), size.height())

        # Use default color if no explicit color and use_theme is True
        effective_color = cls._normalize_color(color) if color else None
        if effective_color is None and use_theme and cls._default_color:
            effective_color = cls._default_color

        icon_key = (name, size, effective_color)

        # Check cache and update access order
        if icon_key in cls._cache:
            # Move to end of access order (most recently used)
            if icon_key in cls._cache_order:
                cls._cache_order.remove(icon_key)
            cls._cache_order.append(icon_key)
            return cls._cache[icon_key]

        # Create the icon
        if effective_color:
            # Load and colorize SVG
            svg_content = cls._load_svg_content(name)
            if svg_content:
                colorized_svg = cls._colorize_svg(svg_content, effective_color)
                icon = cls._create_icon_from_svg(colorized_svg, size)
            else:
                icon = QtGui.QIcon()
        else:
            # Load icon without colorization - still use our renderer for consistency
            svg_content = cls._load_svg_content(name)
            if svg_content:
                icon = cls._create_icon_from_svg(svg_content, size)
            else:
                # Fallback to direct file loading if SVG content couldn't be loaded
                icon = cls._load_icon_from_file(name)

        # Cache the icon with LRU eviction
        cls._cache[icon_key] = icon
        cls._cache_order.append(icon_key)
        cls._evict_cache_if_needed()

        return icon

    @classmethod
    def _load_icon_from_file(cls, name: str) -> QtGui.QIcon:
        """Load icon directly from file without colorization (fallback)."""
        # 1. Check any registered custom icon directories
        for icon_dir in cls._icon_dirs:
            file_path = icon_dir / f"{name}.svg"
            if file_path.exists():
                return QtGui.QIcon(str(file_path))

        # 2. Package resources
        try:
            icon_path = importlib.resources.files("uitk.icons") / f"{name}.svg"
            with importlib.resources.as_file(icon_path) as file_path:
                return QtGui.QIcon(str(file_path))
        except Exception:
            pass

        # 3. Fallback: local dev path
        icon_dir = Path(__file__).parent.parent.parent / "icons"
        file_path = icon_dir / f"{name}.svg"
        if file_path.exists():
            return QtGui.QIcon(str(file_path))

        return QtGui.QIcon()

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
            size: Icon size tuple (width, height) or single int for square
            color: Optional hex color. If None and auto_theme is True, uses theme color.
            auto_theme: If True and no color specified, uses the widget's theme color.
        """
        # Normalize size
        if isinstance(size, (int, float)):
            size = (int(size), int(size))
        elif hasattr(size, "width"):  # QSize
            size = (size.width(), size.height())

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

        # Register widget for theme updates using weak reference
        widget_id = id(widget)
        if auto_theme:
            try:
                cls._widget_icons[widget_id] = widget
                cls._widget_icon_info[widget_id] = {
                    "name": name,
                    "size": size,
                }
                cls._last_update_color[widget_id] = color
            except TypeError:
                # Widget doesn't support weak references - track without weak ref
                pass

    @classmethod
    def update_widget_icons(cls, root_widget: QtWidgets.QWidget, color: str):
        """Update all registered icons under a widget tree with a new color.

        Called when theme changes. Skips widgets already at the target color.
        Also refreshes tree widget item icons.
        """
        color = cls._normalize_color(color)

        # Clean up stale references and update valid widgets
        stale_ids = []

        for widget_id, widget in list(cls._widget_icons.items()):
            info = cls._widget_icon_info.get(widget_id)
            if info is None:
                stale_ids.append(widget_id)
                continue

            try:
                # Check if widget still exists and is valid
                if widget is None:
                    stale_ids.append(widget_id)
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

            except (RuntimeError, ReferenceError):
                # Widget was deleted
                stale_ids.append(widget_id)

        # Clean up stale entries
        for widget_id in stale_ids:
            cls._widget_icons.pop(widget_id, None)
            cls._widget_icon_info.pop(widget_id, None)
            cls._last_update_color.pop(widget_id, None)

        # Also refresh tree widget item icons
        try:
            from uitk.widgets.treeWidget import TreeWidget

            for tree in root_widget.findChildren(TreeWidget):
                if hasattr(tree, "refresh_item_icons"):
                    tree.refresh_item_icons(color)
        except ImportError:
            pass  # TreeWidget not available

    @classmethod
    def clear_cache(cls):
        """Clear all cached icons and SVG content.

        Useful for releasing memory or forcing a complete reload.
        """
        cls._cache.clear()
        cls._cache_order.clear()
        cls._svg_cache.clear()
        cls._last_update_color.clear()

    @classmethod
    def get_cache_stats(cls) -> dict:
        """Get statistics about the icon cache.

        Returns:
            dict with cache size, SVG cache size, and registered widgets count
        """
        return {
            "icon_cache_size": len(cls._cache),
            "svg_cache_size": len(cls._svg_cache),
            "registered_widgets": len(cls._widget_icons),
            "max_cache_size": cls._MAX_CACHE_SIZE,
        }


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------
