# !/usr/bin/python
# coding=utf-8
import importlib.resources
from typing import Union
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk
from uitk.widgets.mixins.settings_manager import SettingsManager


class StyleSheet(QtCore.QObject, ptk.LoggingMixin):
    """Theme and stylesheet manager with light/dark theme support."""

    # Signal emitted when theme changes: (widget, theme_name, theme_vars)
    theme_changed = QtCore.Signal(object, str, dict)

    themes = {
        "light": {
            "PANEL_BACKGROUND": "rgb(70,70,70)",
            "WINDOW_FOREGROUND": "rgb(127,127,127)",
            "WINDOW_BACKGROUND": "rgba(80,80,80,170)",
            "WIDGET_BACKGROUND": "rgb(125,125,125)",
            "BUTTON_PRESSED": "rgb(120,120,120)",
            "BUTTON_HOVER": "rgb(100,130,150)",  # Desaturated blue
            "BUTTON_CHECKED": "rgb(165,135,110)",  # Further desaturated orange
            "TEXT_COLOR": "rgb(255,255,255)",
            "TEXT_CHECKED": "rgb(255,255,255)",
            "TEXT_DISABLED": "rgba(150,150,150,175)",
            "TEXT_HOVER": "rgb(255,255,255)",
            "TEXT_BACKGROUND": "rgba(70,70,70,100)",
            "BORDER_COLOR": "rgb(40,40,40)",
            "HIGHLIGHT_COLOR": "rgb(255,255,190)",
            "DISABLED_BACKGROUND": "rgb(85,85,85)",
            "PROGRESS_BAR_COLOR": "rgb(0,160,208)",
            "ICON_COLOR": "rgb(220,220,220)",
        },
        "dark": {
            "PANEL_BACKGROUND": "rgb(115,115,115)",
            "WINDOW_FOREGROUND": "rgb(127,127,127)",
            "WINDOW_BACKGROUND": "rgba(100,100,100,170)",
            "WIDGET_BACKGROUND": "rgb(60,60,60)",
            "BUTTON_PRESSED": "rgb(120,120,120)",
            "BUTTON_HOVER": "rgba(100,130,150,225)",  # Desaturated blue
            "BUTTON_CHECKED": "rgba(165,135,100,225)",  # Further desaturated orange
            "TEXT_COLOR": "rgb(220,220,220)",
            "TEXT_CHECKED": "rgb(255,255,255)",
            "TEXT_DISABLED": "rgb(150,150,150)",
            "TEXT_HOVER": "rgb(255,255,255)",
            "TEXT_BACKGROUND": "rgba(80,80,80,100)",
            "BORDER_COLOR": "rgb(40,40,40)",
            "HIGHLIGHT_COLOR": "rgb(255,255,190)",
            "DISABLED_BACKGROUND": "rgb(85,85,85)",
            "PROGRESS_BAR_COLOR": "rgb(0,160,208)",
            "ICON_COLOR": "rgb(220,220,220)",
        },
    }

    _qss_cache: dict[str, str] = {}
    # Track current theme per widget for icon color lookups
    _widget_themes: dict = {}
    # Track configuration for reloading
    _widget_configs: dict = {}
    # Track custom overrides
    _global_overrides: dict = {}
    _widget_overrides: dict = {}
    _settings = SettingsManager(
        org="uitk", app="GlobalStyle", namespace="overrides_v2"
    )  # Bumped namespace to avoid conflicts with old structure
    _settings_loaded = False

    @classmethod
    def _ensure_settings_loaded(cls):
        """Lazy load settings from persistent storage."""
        if not cls._settings_loaded:
            stored_overrides = cls._settings.value("global", {})
            if stored_overrides and isinstance(stored_overrides, dict):
                cls._global_overrides.update(stored_overrides)
            # Initialize structure for known themes if missing
            for theme_name in cls.themes:
                if theme_name not in cls._global_overrides:
                    cls._global_overrides[theme_name] = {}
            cls._settings_loaded = True

    def __init__(
        self, parent: Union[QtWidgets.QWidget, None] = None, log_level: str = "WARNING"
    ):
        StyleSheet._ensure_settings_loaded()
        super().__init__(parent)
        self.logger.setLevel(log_level)
        self.set = self._set_style

    @classmethod
    def get_icon_color(cls, widget: QtWidgets.QWidget = None) -> str:
        """Get the icon color for a widget based on its current theme.

        Args:
            widget: The widget to get icon color for. If None, returns default.

        Returns:
            Hex color string for icons (e.g., "#ffffff")
        """
        if widget is not None:
            # Walk up the widget hierarchy to find a themed ancestor
            w = widget
            while w is not None:
                if w in cls._widget_themes:
                    theme_name = cls._widget_themes[w]
                    return cls.themes.get(theme_name, {}).get("ICON_COLOR", "#888888")
                w = w.parent() if hasattr(w, "parent") else None

        # Default fallback
        return "#888888"

    @classmethod
    def set_theme(cls, theme: str, widget: QtWidgets.QWidget = None):
        """Set a new theme for a specific widget or all registered widgets.

        Args:
            theme: Name of the theme to apply (e.g. "light", "dark")
            widget: Specific widget to update. If None, updates all registered widgets.
        """
        targets = [widget] if widget else list(cls._widget_configs.keys())

        for w in targets:
            if w in cls._widget_configs:
                cls._widget_configs[w]["theme"] = theme
                cls.reload(w)

    @classmethod
    def reload(cls, widget: QtWidgets.QWidget = None):
        """Reload the style for a specific widget or all registered widgets.

        Args:
            widget: Specific widget to reload. If None, reloads all registered widgets.
        """
        targets = [widget] if widget else list(cls._widget_configs.keys())

        # Use a temporary instance to apply styles since _set_style is an instance method
        styler = cls()

        for w in targets:
            if w in cls._widget_configs:
                config = cls._widget_configs[w].copy()
                kwargs = config.pop("kwargs", {})
                try:
                    styler.set(w, **config, **kwargs)
                except RuntimeError:
                    # Widget likely deleted
                    if w in cls._widget_configs:
                        del cls._widget_configs[w]

    @classmethod
    def set_variable(
        cls,
        name: str,
        value: Union[str, QtGui.QColor, None],
        theme: str = "light",
        widget: QtWidgets.QWidget = None,
    ):
        """Set a theme variable override.

        Args:
            name: The variable name (e.g. "BUTTON_HOVER").
            value: The value. If None, the override is removed.
            theme: The theme to modify (e.g. "light"). Defaults to "light" for global fallback.
            widget: If provided, override only for this widget. Otherwise global for the theme.
        """
        cls._ensure_settings_loaded()
        if value is None:
            if widget:
                if (
                    widget in cls._widget_overrides
                    and name in cls._widget_overrides[widget]
                ):
                    del cls._widget_overrides[widget][name]
                    cls.reload(widget)
            else:
                if (
                    theme in cls._global_overrides
                    and name in cls._global_overrides[theme]
                ):
                    del cls._global_overrides[theme][name]
                    # Update settings
                    cls._settings.setValue("global", cls._global_overrides)
                    cls.reload()
            return

        val_str = value
        if hasattr(value, "name"):  # Handle QColor
            if value.alpha() == 255:
                # Use hex for opaque colors to keep strings short/readable
                val_str = value.name()
            else:
                val_str = f"rgba({value.red()},{value.green()},{value.blue()},{value.alpha()})"
        elif hasattr(value, "toRgb"):  # Handle other Qt color objects
            c = value.toRgb()
            if c.alpha() == 255:
                val_str = c.name()
            else:
                val_str = f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"
        elif not isinstance(value, str):
            val_str = str(value)

        if widget:
            if widget not in cls._widget_overrides:
                cls._widget_overrides[widget] = {}
                # Ensure cleanup
                try:
                    widget.destroyed.connect(
                        lambda obj: cls._widget_overrides.pop(obj, None)
                    )
                except (AttributeError, RuntimeError):
                    pass
            cls._widget_overrides[widget][name] = val_str
            cls.reload(widget)
        else:
            if theme not in cls._global_overrides:
                cls._global_overrides[theme] = {}
            cls._global_overrides[theme][name] = val_str
            # Update settings
            cls._settings.setValue("global", cls._global_overrides)
            cls.reload()

    @classmethod
    def get_variable(
        cls, name: str, theme: str = "light", widget: QtWidgets.QWidget = None
    ) -> str:
        """Get a theme variable value, resolving overrides.

        Args:
            name: Variable name.
            theme: Base theme name.
            widget: Context widget for checking overrides.
        """
        cls._ensure_settings_loaded()
        # Check widget override
        if widget and widget in cls._widget_overrides:
            if name in cls._widget_overrides[widget]:
                return cls._widget_overrides[widget][name]

        # Check global override for specific theme
        if theme in cls._global_overrides and name in cls._global_overrides[theme]:
            return cls._global_overrides[theme][name]

        # Check base theme
        return cls.themes.get(theme, {}).get(name, "")

    @classmethod
    def get_variables(cls, theme: str = "light") -> list[str]:
        """Get list of available theme variables."""
        return list(cls.themes.get(theme, {}).keys())

    @classmethod
    def reset_overrides(cls, widget: QtWidgets.QWidget = None):
        """Clear overrides.

        Args:
            widget: If provided, clear only this widget's overrides.
                    If None, clear ALL overrides (global and all widgets).
        """
        cls._ensure_settings_loaded()
        if widget:
            if widget in cls._widget_overrides:
                del cls._widget_overrides[widget]
                cls.reload(widget)
        else:
            cls._widget_overrides.clear()
            cls._global_overrides.clear()
            # Clear settings
            cls._settings.clear("global")
            cls.reload()

    def _load_qss_file(
        self, resource: str = "style.qss", package: str = "uitk.widgets.mixins"
    ) -> str:
        cache_key = f"{package}:{resource}"
        if cache_key not in self._qss_cache:
            try:
                with (
                    importlib.resources.files(package)
                    .joinpath(resource)
                    .open("r", encoding="utf-8") as f
                ):
                    self._qss_cache[cache_key] = f.read()
                self.logger.info(f"Loaded QSS from package: {package}/{resource}")
            except Exception as e:
                self.logger.error(f"Failed to load QSS from {package}/{resource} ({e})")
                raise
        else:
            self.logger.debug(f"Using cached QSS for: {package}/{resource}")
        return self._qss_cache[cache_key]

    @staticmethod
    def _apply_theme_variables(qss: str, theme_vars: dict) -> str:
        for k, v in theme_vars.items():
            qss = qss.replace("{" + k + "}", v)
        return qss

    @staticmethod
    def _set_class_property(widget: QtWidgets.QWidget, style_class: str):
        widget.setProperty("class", style_class)
        if isinstance(widget, QtWidgets.QMainWindow) and widget.centralWidget():
            widget.centralWidget().setProperty("class", style_class)

    @ptk.listify
    def _set_style(
        self,
        widget: Union[QtWidgets.QWidget, None] = None,
        theme: str = "light",
        style_class: str = "",
        recursive: bool = False,
        resource: str = "style.qss",
        package: str = "uitk.widgets.mixins",
        **kwargs,
    ):
        if widget is None:
            if isinstance(self.parent(), QtWidgets.QWidget):
                widget = self.parent()
            else:
                raise ValueError(
                    f"No valid QWidget found for styling (self={self}, parent={self.parent()})"
                )

        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.error(f"Invalid datatype for widget: {type(widget)}")
            raise ValueError(f"Expected QWidget, got {type(widget)}.")

        if not style_class:
            default_class = getattr(widget, "_default_style_class", "")
            if default_class:
                style_class = default_class

        if style_class:
            self._set_class_property(widget, style_class)
            self.logger.debug(
                f"Set style class '{style_class}' on widget: {widget.objectName()}"
            )

        try:
            # Prepare theme variables with overrides
            theme_vars = self.themes.get(theme, {}).copy()
            # Apply global overrides for this theme
            if theme in self._global_overrides:
                theme_vars.update(self._global_overrides[theme])

            # Apply widget-specific overrides
            if widget in self._widget_overrides:
                theme_vars.update(self._widget_overrides[widget])
            # Apply kwargs overrides (if any match theme keys)
            for k, v in kwargs.items():
                if k in theme_vars:  # treat kwargs as overrides if they match keys
                    theme_vars[k] = str(v)

            qss = self._load_qss_file(resource, package)
            qss_final = self._apply_theme_variables(qss, theme_vars)
            self.logger.debug(
                f"Applying QSS to widget '{widget.objectName()}':\n---BEGIN QSS---\n{qss_final}\n---END QSS---"
            )
            widget.setStyleSheet("")  # Optional clear
            widget.setStyleSheet(qss_final)
            self.logger.info(
                f"Applied QSS style to widget: {widget.objectName()} (theme='{theme}', class='{style_class}')"
            )

            # Track theme for this widget
            StyleSheet._widget_themes[widget] = theme

            # Track configuration for reloading
            if widget not in StyleSheet._widget_configs:
                try:
                    widget.destroyed.connect(
                        lambda obj: StyleSheet._widget_themes.pop(obj, None)
                    )
                    widget.destroyed.connect(
                        lambda obj: StyleSheet._widget_configs.pop(obj, None)
                    )
                except (AttributeError, RuntimeError):
                    pass

            StyleSheet._widget_configs[widget] = {
                "theme": theme,
                "style_class": style_class,
                "recursive": recursive,
                "resource": resource,
                "package": package,
                "kwargs": kwargs,
            }

            # Update default icon color and refresh icons for this widget tree
            # Use resolved color from theme_vars to ensure overrides are respected
            icon_color = theme_vars.get("ICON_COLOR", "#888888")
            from uitk.widgets.mixins.icon_manager import IconManager

            IconManager.set_default_color(icon_color)
            IconManager.update_widget_icons(widget, icon_color)

            # Emit signal for any custom handlers
            self.theme_changed.emit(widget, theme, theme_vars)

        except Exception as e:
            self.logger.error(
                f"Failed to apply QSS style to {widget.objectName()}: {e}"
            )
            raise

        if recursive:
            for child in widget.findChildren(QtWidgets.QWidget):
                self.logger.debug(
                    f"Recursively setting style on: {child.objectName()} ({type(child).__name__})"
                )
                self._set_style(
                    child,
                    theme=theme,
                    recursive=False,
                    resource=resource,
                    package=package,
                    **kwargs,
                )


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    ...

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
