# !/usr/bin/python
# coding=utf-8
"""Mixin: transient HUD-style feedback for any QWidget.

Adds a ``show_feedback(html)`` method that flashes a short rich-text
message near the host widget via :class:`uitk.widgets.messageBox.MessageBox`.
The popup is themed by uitk's :class:`StyleSheet` engine so it matches
the rest of the ecosystem chrome.

Use cases inside uitk:

* :class:`WheelStepMixin` calls it to show the step amount when the
  user scrolls a spin-box with a modifier.
* :class:`SpinBox` / :class:`DoubleSpinBox` inherit it directly to surface
  the feedback without each widget owning its own MessageBox instance.

Switchboard's :meth:`Slots.message_box` (the slot-side convenience that
spawns the same popup for slot-emitted text) is unaffected — it uses
:class:`MessageBox` directly via the registered widgets registry. Both
paths share the same widget + styling.
"""
from typing import Optional

from qtpy import QtWidgets


class FeedbackMixin:
    """Adds a lazily-instantiated, theme-styled HUD popup.

    The host widget gets:

    * :meth:`show_feedback(html)` — flash a transient rich-text message.

    The popup is created on first call (so widgets that never call it
    pay zero cost) and reused for subsequent calls. It is parented to
    the host, so Qt destroys it with the host automatically.

    Hosts may override :attr:`_feedback_timeout` to change the auto-dismiss
    interval, or :attr:`_feedback_theme` to pick a non-default StyleSheet
    theme. Both are class-level so subclasses can set them without an
    ``__init__`` override.
    """

    #: Auto-dismiss timeout for the popup, in seconds.
    _feedback_timeout: int = 1

    #: StyleSheet theme name. Falls back to whichever theme is active on
    #: the host's ancestry if available; explicit ``None`` skips theme
    #: registration entirely (popup falls back to its inline defaults).
    _feedback_theme: Optional[str] = "dark"

    def show_feedback(self, html_text: str) -> None:
        """Flash *html_text* near the host. Rich-text body."""
        box = self._ensure_feedback_box()
        box.setText(html_text)
        box.show()

    def _ensure_feedback_box(self) -> QtWidgets.QWidget:
        """Lazy-create the popup on first use; reuse thereafter."""
        box = getattr(self, "_feedback_box", None)
        if box is not None:
            return box

        # Local import to avoid a hard import cycle: ``feedback`` is loaded
        # alongside other mixins very early, before the widgets package
        # has finished registering.
        from uitk.widgets.messageBox import MessageBox

        box = MessageBox(self, timeout=self._feedback_timeout)
        self._register_feedback_theme(box)
        self._feedback_box = box
        return box

    def _register_feedback_theme(self, box: QtWidgets.QWidget) -> None:
        """Register *box* with the StyleSheet engine so it picks up uitk theme tokens."""
        theme = self._feedback_theme
        if theme is None:
            return
        # Import locally so the mixin can be used in environments where
        # the full style engine isn't desired (e.g. minimal headless setups).
        try:
            from uitk.widgets.mixins.style_sheet import StyleSheet
        except Exception:  # noqa: BLE001 — style engine optional at this layer.
            return
        StyleSheet(box).set(theme=theme)
