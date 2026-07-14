# !/usr/bin/python
# coding=utf-8
import logging
import re
import importlib.resources
from typing import Union
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk
from uitk.widgets.mixins.settings_manager import SettingsManager

_logger = logging.getLogger(__name__)


def repolish_tree(root: QtWidgets.QWidget) -> None:
    """Force re-evaluation of property-selector QSS for *root* and children.

    Dynamic-property rules (``[class="..."]``) are only re-matched on an
    ``unpolish``/``polish`` cycle — a property stamped after a widget's first
    polish leaves stale metrics until then (show performs the cycle
    implicitly, which is why post-show measurements differ from pre-show
    ones: the init-flash mechanism). Call this after stamping style-bearing
    properties and BEFORE measuring size hints, so first measurements are
    final. ``QStyle.polish`` is per-widget, so the tree is walked explicitly;
    cheap for row/menu-scale trees.
    """
    for w in [root] + root.findChildren(QtWidgets.QWidget):
        try:
            # NOT w.style(): uitk widgets attach a StyleSheet manager as the
            # instance attribute ``style`` (e.g. Menu.__init__), shadowing
            # QWidget.style() — the unbound base-class call bypasses that.
            style = QtWidgets.QWidget.style(w)
            style.unpolish(w)
            style.polish(w)
        except RuntimeError:
            pass  # C++ side died mid-walk


class _ThemeSignalBus(QtCore.QObject):
    """Process-wide emitter backing :attr:`StyleSheet.theme_changed`.

    ``theme_changed`` is connected per-instance (``ui.style.theme_changed``),
    but the classmethod paths (``reload`` / ``set_theme`` / ``set_variable``)
    emit from a throwaway ``StyleSheet()`` instance. Routing every instance's
    signal to one shared bus makes those class-level emits reach subscribers
    connected via any instance.
    """

    # Signal emitted when theme changes: (widget, theme_name, theme_vars)
    theme_changed = QtCore.Signal(object, str, dict)


class StyleSheet(QtCore.QObject, ptk.LoggingMixin):
    """Theme and stylesheet manager with light/dark theme support."""

    # Shared theme-change emitter (see _ThemeSignalBus). Lazily instantiated
    # on first access so importing this module never constructs a QObject.
    _signal_bus: "Union[_ThemeSignalBus, None]" = None

    @classmethod
    def _theme_signal_bus(cls) -> "_ThemeSignalBus":
        """Return the process-wide theme-change signal bus (creating it once)."""
        if StyleSheet._signal_bus is None:
            StyleSheet._signal_bus = _ThemeSignalBus()
        return StyleSheet._signal_bus

    @property
    def theme_changed(self):
        """Signal ``(widget, theme_name, theme_vars)`` emitted after a style applies.

        Backed by a shared bus so subscribers connected to *any* instance
        (``ui.style.theme_changed.connect(...)``) also receive the emits made
        from the classmethod paths (``reload`` / ``set_theme`` / ``set_variable``),
        which run on a throwaway instance.
        """
        return StyleSheet._theme_signal_bus().theme_changed

    themes = {
        "light": {
            # Surfaces
            "PANEL_BACKGROUND": "rgb(70,70,70)",
            "WINDOW_BACKGROUND": "rgba(80,80,80,170)",
            "WIDGET_BACKGROUND": "rgb(125,125,125)",
            "WIDGET_BACKGROUND_HOVER": "rgb(140,140,140)",
            "DISABLED_BACKGROUND": "rgb(85,85,85)",
            "ALTERNATE_BACKGROUND": "rgba(255,255,255,10)",
            "TREE_ALTERNATE_BG": "rgb(127,127,127)",
            # Text
            "TEXT_COLOR": "rgb(255,255,255)",
            "TEXT_HOVER": "rgb(255,255,255)",
            "TEXT_CHECKED": "rgb(255,255,255)",
            "TEXT_DISABLED": "rgba(150,150,150,175)",
            # Accents
            "BUTTON_HOVER": "rgb(100,130,150)",  # Desaturated blue
            "BUTTON_CHECKED": "rgb(165,135,110)",  # Further desaturated orange
            "PROGRESS_BAR_COLOR": "rgb(0,160,208)",
            # Borders + shape
            "BORDER_COLOR": "rgb(40,40,40)",
            "BORDER_HOVER": "rgba(255,255,255,110)",
            "BORDER_W": "1px",
            "RADIUS": "4px",
            # Metrics (layout, themeable)
            "COMBOBOX_ITEM_HEIGHT": "19px",  # min row height of popup items
            "TEXT_INSET": "2px",  # horizontal text inset shared by labels/inputs
            # Selection (text-selection inside inputs)
            "SELECTION_BG": "rgba(70,70,70,100)",
            "SELECTION_FG": "rgb(255,255,190)",
            # Status (input feedback)
            "ACTION_VALID_FG": "rgb(60,141,60)",
            "ACTION_VALID_BG": "rgb(230,244,234)",
            "ACTION_INVALID_FG": "rgb(185,122,122)",
            "ACTION_INVALID_BG": "rgb(251,234,234)",
            "ACTION_WARNING_FG": "rgb(180,155,92)",
            "ACTION_WARNING_BG": "rgb(255,246,220)",
            "ACTION_INFO_FG": "rgb(109,155,170)",
            "ACTION_INFO_BG": "rgb(226,243,249)",
            "ACTION_INACTIVE_FG": "rgb(170,170,170)",
            # Misc (Python-consumed)
            "ICON_COLOR": "rgb(220,220,220)",
            "LINK_COLOR": "rgb(130,170,210)",
            "LINK_VISITED_COLOR": "rgb(160,150,190)",
        },
        "dark": {
            # Surfaces
            "PANEL_BACKGROUND": "rgba(105,105,105,100)",
            "WINDOW_BACKGROUND": "rgba(100,100,100,200)",
            "WIDGET_BACKGROUND": "rgb(60,60,60)",
            "WIDGET_BACKGROUND_HOVER": "rgb(78,78,78)",
            "DISABLED_BACKGROUND": "rgb(85,85,85)",
            "ALTERNATE_BACKGROUND": "rgba(255,255,255,8)",
            "TREE_ALTERNATE_BG": "rgb(70,70,70)",
            # Text
            "TEXT_COLOR": "rgb(220,220,220)",
            "TEXT_HOVER": "rgb(255,255,255)",
            "TEXT_CHECKED": "rgb(255,255,255)",
            "TEXT_DISABLED": "rgb(150,150,150)",
            # Accents
            "BUTTON_HOVER": "rgba(100,130,150,225)",  # Desaturated blue
            "BUTTON_CHECKED": "rgba(165,135,100,225)",  # Further desaturated orange
            "PROGRESS_BAR_COLOR": "rgb(0,160,208)",
            # Borders + shape
            "BORDER_COLOR": "rgb(40,40,40)",
            "BORDER_HOVER": "rgba(255,255,255,110)",
            "BORDER_W": "0px",  # Dark theme defaults borderless for a softer look.
            "RADIUS": "1px",
            # Metrics (layout, themeable)
            "COMBOBOX_ITEM_HEIGHT": "19px",  # min row height of popup items
            "TEXT_INSET": "2px",  # horizontal text inset shared by labels/inputs
            # Selection (text-selection inside inputs)
            "SELECTION_BG": "rgba(80,80,80,100)",
            "SELECTION_FG": "rgb(255,255,190)",
            # Status (input feedback)
            "ACTION_VALID_FG": "rgb(168,213,162)",
            "ACTION_VALID_BG": "rgb(30,46,30)",
            "ACTION_INVALID_FG": "rgb(232,165,163)",
            "ACTION_INVALID_BG": "rgb(51,32,31)",
            "ACTION_WARNING_FG": "rgb(224,201,127)",
            "ACTION_WARNING_BG": "rgb(51,46,32)",
            "ACTION_INFO_FG": "rgb(163,203,224)",
            "ACTION_INFO_BG": "rgb(30,46,51)",
            "ACTION_INACTIVE_FG": "rgb(119,119,119)",
            # Misc (Python-consumed)
            "ICON_COLOR": "rgb(220,220,220)",
            "LINK_COLOR": "rgb(130,170,210)",
            "LINK_VISITED_COLOR": "rgb(160,150,190)",
        },
    }

    # Token substitution: ``{TOKEN_NAME}`` where TOKEN_NAME is UPPER_SNAKE.
    # Anchored so QSS rule-block braces ``{`` followed by whitespace/newline
    # never match.
    _token_pat = re.compile(r"\{([A-Z_][A-Z0-9_]*)\}")

    # Accent colors that get a derived ``<NAME>_TINT`` companion — consumed
    # by ``::selected:hover`` / ``::checked:hover`` rules so the hover state
    # of a highlighted item shifts subtly without losing the accent hue.
    # Internal: not exposed via ``themes`` / ``get_variables`` / ``set_variable``.
    # ``PANEL_BACKGROUND`` is also tinted: its ``_TINT`` is the slider handle's
    # resting color, a hair brighter than the panel so the knob reads as grabbable.
    _tint_sources = ("BUTTON_HOVER", "BUTTON_CHECKED", "PANEL_BACKGROUND")
    _derived_token_suffixes = ("_TINT",)
    # Derived tokens with explicit (non-suffix) names — kept separate because
    # their names share suffixes (``_BACKGROUND``) with real exposed tokens.
    _derived_token_names = ("DISABLED_CHECKED_BACKGROUND",)
    # Disabled-but-checked background: the disabled background nudged a little
    # toward the checked accent, so a checked toggle that's been disabled reads
    # as *disabled with a hint of checked* rather than fully active.
    _disabled_checked_mix = 0.22
    _color_pat = re.compile(
        r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)|"
        r"#([0-9A-Fa-f]{6})([0-9A-Fa-f]{2})?"
    )

    @classmethod
    def _is_derived_token(cls, name: str) -> bool:
        """True if ``name`` is a derived token managed by ``_derive_internal_vars``.

        Used to reject user overrides on internal tokens — those would be
        silently overwritten on the next assembly pass.
        """
        return name in cls._derived_token_names or any(
            name.endswith(s) for s in cls._derived_token_suffixes
        )

    @classmethod
    def _tint(cls, color_str: str, mix: float = 0.12) -> str:
        """Subtly lighten ``color_str`` by mixing toward white.

        ``mix`` is the white-blend ratio (0.0 = unchanged, 1.0 = white).
        Preserves the input format (``rgb``/``rgba``/``#hex``/``#hexa``)
        and the alpha channel. Returns ``color_str`` unchanged if the
        format isn't recognized.
        """
        return cls._blend(color_str, "rgb(255,255,255)", mix)

    @classmethod
    def _blend(cls, base_str: str, accent_str: str, mix: float = 0.5) -> str:
        """Mix ``base_str`` toward ``accent_str`` by ``mix`` (0=base, 1=accent).

        Linear RGB interpolation; the result keeps ``base``'s format and alpha.
        Returns ``base_str`` unchanged if either color can't be parsed.
        """

        def parse(s: str):
            m = cls._color_pat.fullmatch(s.strip())
            if not m:
                return None
            if m.group(1) is not None:
                return int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4), "rgb"
            h6, ha = m.group(5), m.group(6)
            return int(h6[0:2], 16), int(h6[2:4], 16), int(h6[4:6], 16), ha, "hex"

        base, accent = parse(base_str), parse(accent_str)
        if not base or not accent:
            return base_str
        r = round(base[0] + (accent[0] - base[0]) * mix)
        g = round(base[1] + (accent[1] - base[1]) * mix)
        b = round(base[2] + (accent[2] - base[2]) * mix)
        if base[4] == "rgb":
            return (
                f"rgba({r},{g},{b},{base[3]})"
                if base[3] is not None
                else f"rgb({r},{g},{b})"
            )
        return f"#{r:02x}{g:02x}{b:02x}{base[3] or ''}"

    @classmethod
    def _derive_internal_vars(cls, theme_vars: dict) -> None:
        """Inject derived-only tokens into ``theme_vars``.

        Called right before QSS template assembly so the derived values always
        track the resolved sources (base + global overrides + widget overrides
        + kwargs): the ``<NAME>_TINT`` hover companions, and
        ``DISABLED_CHECKED_BACKGROUND`` (disabled bg nudged toward the checked
        accent — see :attr:`_disabled_checked_mix`).
        """
        for name in cls._tint_sources:
            base = theme_vars.get(name)
            if base:
                theme_vars[f"{name}_TINT"] = cls._tint(base)
        disabled = theme_vars.get("DISABLED_BACKGROUND")
        checked = theme_vars.get("BUTTON_CHECKED")
        if disabled and checked:
            theme_vars["DISABLED_CHECKED_BACKGROUND"] = cls._blend(
                disabled, checked, cls._disabled_checked_mix
            )

    _qss_cache: dict[str, str] = {}
    # Parsed-template cache: cache_key -> [literal, TOKEN, literal, TOKEN, ...].
    # Built once per (package, resource) on first load; assembly is then a
    # single ``''.join`` of dict lookups, replacing N full-string ``str.replace``
    # passes (one per token) with one pass.
    _template_cache: dict[str, list[str]] = {}
    # Track current theme per widget for icon color lookups
    _widget_themes: dict = {}
    # Track configuration for reloading
    _widget_configs: dict = {}
    # Track custom overrides
    _global_overrides: dict = {}
    _widget_overrides: dict = {}
    _settings = SettingsManager(
        org="uitk", app="GlobalStyle", namespace="overrides_v3"
    )  # v3: token-set cleanup (drops + renames + adds). v2 left on disk.
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
                    # Resolve through get_variable so global/widget ICON_COLOR
                    # overrides win over the base theme value (icons created
                    # after an override must pick it up, not the un-overridden
                    # default).
                    return cls.get_variable("ICON_COLOR", theme_name, w) or "#888888"
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

        Widgets are grouped by ``(theme, resource, package, kwargs)`` so each
        unique configuration's QSS is assembled exactly once per call — large
        registries with a shared theme pay the template-apply cost once, not
        N times. Widgets with per-widget overrides take the slow path since
        their theme_vars dict is unique.

        Args:
            widget: Specific widget to reload. If None, reloads all registered widgets.
        """
        targets = [widget] if widget else list(cls._widget_configs.keys())
        styler = cls()
        # Per-call cache: (theme, resource, package, frozenset(kwargs.items())) -> qss_final
        assembled: dict = {}

        for w in targets:
            if w not in cls._widget_configs:
                continue
            config = cls._widget_configs[w].copy()
            kwargs = config.pop("kwargs", {})

            # Per-widget overrides break sharing — fall through to the slow path.
            if w in cls._widget_overrides:
                try:
                    styler.set(w, **config, **kwargs)
                except RuntimeError:
                    cls._widget_configs.pop(w, None)
                continue

            key = (
                config["theme"],
                config["resource"],
                config["package"],
                frozenset(kwargs.items()),
            )
            qss_final = assembled.get(key)
            if qss_final is None:
                theme_vars = cls.themes.get(config["theme"], {}).copy()
                if config["theme"] in cls._global_overrides:
                    theme_vars.update(cls._global_overrides[config["theme"]])
                for k, v in kwargs.items():
                    if k in theme_vars:
                        theme_vars[k] = str(v)
                # Derive into theme_vars here — it's not emitted from this
                # path (the slow path in ``set`` handles signal emission
                # with its own derivation-free dict).
                cls._derive_internal_vars(theme_vars)
                parts = cls._get_template(config["resource"], config["package"])
                qss_final = cls._apply_template(parts, theme_vars)
                assembled[key] = qss_final

            try:
                styler.set(w, **config, **kwargs, _qss_final=qss_final)
            except RuntimeError:
                cls._widget_configs.pop(w, None)

    @classmethod
    def clear_caches(cls) -> None:
        """Drop QSS + parsed-template caches.

        Call after editing ``style.qss`` during a dev session so the next
        ``reload()`` re-reads from disk and rebuilds its template.
        """
        cls._qss_cache.clear()
        cls._template_cache.clear()

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
        if cls._is_derived_token(name):
            raise ValueError(
                f"{name!r} is a derived token (auto-computed from a base "
                f"accent). Override the source token instead."
            )
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
    def get_variable_px(
        cls,
        name: str,
        theme: str = "light",
        widget: QtWidgets.QWidget = None,
        default: Union[int, None] = None,
    ) -> Union[int, None]:
        """Get a length token as an integer pixel value.

        Parses the leading integer of a length variable (e.g. ``"19px"`` →
        ``19``). Returns ``default`` if the variable is unset or non-numeric.
        Single source of truth for token → px conversion so consumers
        (popup delegates, the style editor's px spin boxes, …) don't each
        re-implement the parse.

        Args:
            name: Variable name (e.g. ``"COMBOBOX_ITEM_HEIGHT"``).
            theme: Base theme name.
            widget: Context widget for checking overrides.
            default: Returned when the value is missing/unparseable.
        """
        m = re.match(r"\s*(-?\d+)", cls.get_variable(name, theme, widget) or "")
        return int(m.group(1)) if m else default

    @classmethod
    def get_variables(cls, theme: str = "light") -> list[str]:
        """Get list of available theme variables."""
        return list(cls.themes.get(theme, {}).keys())

    @classmethod
    def export_overrides(cls) -> dict:
        """Export the current global overrides as a plain dict.

        Returns a deep copy of ``{theme_name: {var: value, ...}, ...}``
        suitable for JSON serialization.
        """
        cls._ensure_settings_loaded()
        import copy

        return copy.deepcopy(cls._global_overrides)

    @classmethod
    def import_overrides(cls, data: dict) -> None:
        """Bulk-replace global overrides from a dict and reload once.

        Args:
            data: A ``{theme_name: {var: value, ...}, ...}`` dict.
                  Keys not present in *data* are cleared.
        """
        cls._ensure_settings_loaded()
        cls._global_overrides.clear()
        for theme_name, overrides in data.items():
            if isinstance(overrides, dict):
                cls._global_overrides[theme_name] = dict(overrides)
        cls._settings.setValue("global", cls._global_overrides)
        cls.reload()

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

    @classmethod
    def _load_qss_file(
        cls, resource: str = "style.qss", package: str = "uitk.widgets.mixins"
    ) -> str:
        """Read a QSS resource from a package, caching the result.

        Classmethod (not instance method) so callers like ``_get_template``
        don't have to instantiate ``cls()`` — instance creation triggers
        ``_ensure_settings_loaded`` and QObject init for no benefit when
        all we need is the file contents.
        """
        cache_key = f"{package}:{resource}"
        if cache_key not in cls._qss_cache:
            try:
                with (
                    importlib.resources.files(package)
                    .joinpath(resource)
                    .open("r", encoding="utf-8") as f
                ):
                    cls._qss_cache[cache_key] = f.read()
            except Exception as e:
                _logger.error(f"Failed to load QSS from {package}/{resource} ({e})")
                raise
        return cls._qss_cache[cache_key]

    @classmethod
    def _get_template(
        cls, resource: str = "style.qss", package: str = "uitk.widgets.mixins"
    ) -> list[str]:
        """Return a parsed-template list for ``package/resource``.

        The list alternates literal chunks and token names:
        ``[literal, TOKEN, literal, TOKEN, ..., literal]``. Even indices are
        literals, odd indices are token names looked up against ``theme_vars``.
        """
        cache_key = f"{package}:{resource}"
        parts = cls._template_cache.get(cache_key)
        if parts is None:
            qss = cls._load_qss_file(resource, package)
            parts = cls._token_pat.split(qss)
            cls._template_cache[cache_key] = parts
        return parts

    @staticmethod
    def _apply_template(parts: list[str], theme_vars: dict) -> str:
        """Assemble a QSS string from a parsed template and a vars dict.

        Unknown tokens are left as ``{TOKEN}`` literals so missing vars are
        visible in the applied QSS rather than silently producing an empty
        substitution. Tokens inside commented-out QSS blocks are substituted
        too — harmless since the surrounding ``/* ... */`` still parses as
        a comment after substitution.
        """
        return "".join(
            p if i % 2 == 0 else theme_vars.get(p, "{" + p + "}")
            for i, p in enumerate(parts)
        )

    @staticmethod
    def _set_class_property(widget: QtWidgets.QWidget, style_class: str):
        widget.setProperty("class", style_class)
        if isinstance(widget, QtWidgets.QMainWindow) and widget.centralWidget():
            widget.centralWidget().setProperty("class", style_class)

    @ptk.listify
    def set(
        self,
        widget: Union[QtWidgets.QWidget, None] = None,
        theme: str = "light",
        style_class: str = "",
        recursive: bool = False,
        resource: str = "style.qss",
        package: str = "uitk.widgets.mixins",
        _qss_final: Union[str, None] = None,
        **kwargs,
    ):
        """Apply a themed stylesheet to ``widget`` and register it for reloads.

        Args:
            widget: Target. Defaults to ``self.parent()`` if a QWidget.
            theme: Theme name (key of :attr:`themes`).
            style_class: Optional ``class`` property to set on the widget.
            recursive: If True, apply to every QWidget descendant.
            resource, package: Locate the QSS file via importlib.resources.
            _qss_final: **Internal.** Precomputed QSS string from
                :meth:`reload`'s group-by-config fast path. When supplied,
                template assembly is skipped — the widget must NOT have
                per-widget overrides (caller is responsible for filtering),
                otherwise the precomputed QSS won't reflect them.
            **kwargs: Per-call token overrides; keys matching theme vars
                replace those vars for this widget only (not persisted).
        """
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

            # Reuse a precomputed QSS string if the caller (typically
            # ``reload()``) has already assembled it for our config group.
            # Derive internal tints into a scratch dict so the signal payload
            # below carries only user-facing tokens.
            if _qss_final is None:
                assembly_vars = theme_vars.copy()
                self._derive_internal_vars(assembly_vars)
                parts = self._get_template(resource, package)
                qss_final = self._apply_template(parts, assembly_vars)
            else:
                qss_final = _qss_final
            self.logger.debug(
                f"Applying QSS to widget '{widget.objectName()}':\n---BEGIN QSS---\n{qss_final}\n---END QSS---"
            )
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
                self.set(
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
