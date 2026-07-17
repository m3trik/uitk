# !/usr/bin/python
# coding=utf-8
"""Mixin that exposes the :class:`StyleSheet` class on the Switchboard.

Adds ``sb.style`` as a lazy class-proxy so callers can apply themes
globally, query theme variables, override colors, etc., without an
explicit ``from uitk.themes.style_sheet import StyleSheet`` and
without forcing the StyleSheet module (and its QSS files) to load until
the first access.

Usage::

    sb.style.set_theme("dark")         # global theme switch
    sb.style.set_variable("BG", ...)   # global override
    sb.style.get_variable("BG")        # query
    sb.style.reload()                  # refresh all styled widgets

The property returns the :class:`StyleSheet` class itself rather than an
instance because the methods callers most often want from the
switchboard scope are *classmethods* operating on the global registry of
styled widgets (set_theme, reload, set_variable, get_variable). For
applying a theme to a specific widget, callers still use the per-widget
``widget.style.set(theme=...)`` API.
"""


class SwitchboardStyleMixin:
    """Adds a lazy ``style`` property exposing the :class:`StyleSheet` class."""

    @property
    def style(self):
        """The :class:`StyleSheet` class (imported lazily on first access).

        Returns the class — not an instance — so the standard set of
        classmethods (``set_theme``, ``reload``, ``set_variable``,
        ``get_variable``, ``get_icon_color``) are reachable from a single
        ``sb.style.<method>`` call.
        """
        from uitk.themes.style_sheet import StyleSheet

        return StyleSheet
