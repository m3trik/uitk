# !/usr/bin/python
# coding=utf-8
"""The menu's popup window: its window type, input grab, and screen clamp.

A menu is promoted from a hidden child widget to a frameless top-level window
on first show -- ``Qt.Tool`` normally, ``Qt.Popup`` when it opens inside
another popup's grab (a combo dropdown) -- and, on Qt 6.8+, takes the native
mouse grab from the popup beneath it for as long as it is shown. The mechanics
are the shared popup kit's (``uitk.widgets.popup``); this is the menu's use of
them.

One part of :class:`~uitk.widgets.menu.Menu` (see ``menu_parts``).
"""

import weakref
from typing import TYPE_CHECKING, Optional

from qtpy import QtCore, QtWidgets

from uitk.widgets.popup.dismissal import AncestorDismissal
from uitk.widgets.popup.placement import PopupPlacement
from uitk.widgets.popup.window import PopupWindow

if TYPE_CHECKING:
    from uitk.widgets.menu import Menu


class _MenuPopupWindow:
    """A :class:`Menu`'s popup window: its window type, input grab, and screen clamp.

    Owns whether (and as which window type) the menu was promoted, the popup
    whose native grab it took, and the dismiss-on-ancestor-move filter.
    """

    def __init__(self, menu: "Menu") -> None:
        self._menu = menu
        self.popup_configured = False  # Track if popup setup has been done
        # Window type the last ``setup_as_popup`` pass applied (Qt.Tool or
        # Qt.Popup). Re-checked on every show: a menu opened while another
        # popup holds the app-wide grab must itself be a Qt.Popup to get
        # any input at all. See ``resolve_popup_window_type``.
        self.popup_window_type: Optional[QtCore.Qt.WindowType] = None
        # The popup whose native mouse grab this menu stole on show (weakref),
        # to hand back on hide. See ensure_popup_input_grab.
        self.grab_stolen_from: Optional["weakref.ref"] = None
        self.dismiss_on_move_filter: Optional[AncestorDismissal] = None

    def install_dismiss_on_move_filter(self, anchor_widget) -> None:
        """Install (or replace) the dismiss-on-ancestor-move filter.

        Detaches any previous filter first so re-shows don't accumulate
        watchers.  Bound to ``anchor_widget``'s parent chain; safe to call
        with ``None`` (no-op) if the menu has no anchor.  A move of a window in
        that chain hides the menu while it is visible and not pinned
        (:class:`~uitk.widgets.popup.dismissal.AncestorDismissal`).
        """
        self.detach_dismiss_on_move_filter()
        if anchor_widget is None:
            return
        menu = self._menu
        # Resolved per event (lambdas, not bound methods) so an override or
        # instance patch of hide/is_pinned applies, as it did when the filter
        # called them on its target directly.
        self.dismiss_on_move_filter = AncestorDismissal(
            anchor_widget,
            dismiss=lambda: menu.hide(),
            when=lambda: menu.isVisible() and not menu.is_pinned,
            parent=menu,
        )

    def detach_dismiss_on_move_filter(self) -> None:
        existing = self.dismiss_on_move_filter
        if existing is not None:
            existing.detach()
            self.dismiss_on_move_filter = None

    def resolve_popup_window_type(self) -> QtCore.Qt.WindowType:
        """The window type this menu must use for the *current* show.

        ``Qt.Tool`` normally — a tool window floats above its parent, keeps
        the host window active, and does not steal input from the rest of
        the app.

        ``Qt.Popup`` when some *other* widget already holds Qt's app-wide
        popup grab.  While ``QApplication.activePopupWidget()`` is set, Qt
        routes every mouse event to that popup (or to a widget inside it) —
        a ``Qt.Tool`` window shown on top receives **nothing**, and the
        pointer appears to interact with whatever sits underneath.  That is
        the case for an option-box menu opened from a row embedded in a
        ``WidgetComboBox`` dropdown: the combo's native popup owns the grab,
        so the menu renders but is input-dead while the combo view below it
        keeps taking the hover.  Declaring ``Qt.Popup`` pushes this menu onto
        Qt's popup stack, so it becomes the active popup and gets the input;
        hiding it pops the stack and hands the grab back.
        """
        active = QtWidgets.QApplication.activePopupWidget()
        if active is self._menu:
            # A re-show while we already hold the grab: keep the type we have,
            # since re-declaring it would drop the grab mid-life.
            return self.popup_window_type or QtCore.Qt.Popup
        if active is not None:
            return QtCore.Qt.Popup
        return QtCore.Qt.Tool

    def ensure_popup_input_grab(self, prev_popup) -> None:
        """Route native mouse input here while this menu overlays another popup's grab.

        Qt 6.8 rewrote popup handling: ``QWidgetWindow`` no longer remaps a
        mouse event delivered to an OLDER popup into the active one. On
        Windows the older popup (e.g. a combo's native dropdown hosting this
        menu's option-box row) keeps the OS mouse capture, so every press is
        still delivered to ITS window and this menu is input-dead even while
        it is the active popup — measured live over Blender (PySide6 6.11):
        presses at the menu's own buttons routed into the combo view
        beneath. Do what pre-6.8 ``grabForPopup`` did internally: move the
        WINDOW-level grab (``QWindow.setMouseGrabEnabled`` → ``SetCapture``)
        to this menu. Window-level, not ``QWidget.grabMouse`` — a widget
        grab funnels events to the menu widget itself, bypassing its child
        buttons. The grab is handed back on hide
        (:meth:`release_popup_input_grab`) so the underlying popup's
        click-outside dismissal keeps working. No-op in the common
        single-popup case (*prev_popup* is None). Best-effort: a platform
        that refuses the grab leaves behavior unchanged.
        """
        menu = self._menu
        if prev_popup is None or prev_popup is menu or not menu.isVisible():
            return
        if self.popup_window_type != QtCore.Qt.Popup:
            return
        try:
            handle = menu.windowHandle()
            if handle is None:
                return
            handle.setMouseGrabEnabled(True)
            self.grab_stolen_from = weakref.ref(prev_popup.window())
        except Exception as e:  # pragma: no cover - platform-defensive
            menu.logger.debug(f"_ensure_popup_input_grab skipped: {e}")

    def release_popup_input_grab(self) -> None:
        """Hand a stolen native mouse grab back to the popup it came from.

        Runs on hide. Without the hand-back, the underlying popup (the combo
        dropdown this menu opened over) never sees another native mouse
        event over a non-Qt host, so it stops dismissing on outside clicks.
        Re-granting a grab Qt already restored itself (pre-6.8 hosts) is a
        harmless duplicate ``SetCapture``.
        """
        ref, self.grab_stolen_from = self.grab_stolen_from, None
        if ref is None:
            return
        menu = self._menu
        try:
            handle = menu.windowHandle()
            if handle is not None:
                handle.setMouseGrabEnabled(False)
            prev = ref()
            if prev is not None and prev.isVisible():
                prev_handle = prev.windowHandle()
                if prev_handle is not None:
                    prev_handle.setMouseGrabEnabled(True)
        except Exception as e:  # pragma: no cover - platform-defensive
            menu.logger.debug(f"_release_popup_input_grab skipped: {e}")

    def setup_as_popup(self):
        """Configure this menu as a popup window.

        Idempotent per window type: it re-runs only when
        :meth:`resolve_popup_window_type` returns something other than what
        is currently applied (Tool -> Popup when opened inside a foreign
        popup grab), since reparenting recreates the native handle.
        """
        window_type = self.resolve_popup_window_type()
        if self.popup_configured and window_type == self.popup_window_type:
            return

        self.popup_configured = True
        self.popup_window_type = window_type

        # One setParent(parent, flags) call (a single native recreation); a
        # parentless menu is owned by the active window. Translucent: a
        # Menu's ground is the translucent WINDOW_BACKGROUND.
        menu = self._menu
        had_parent = menu.parentWidget() is not None
        owner = PopupWindow.promote(
            menu,
            window_type | QtCore.Qt.FramelessWindowHint,
            parent_fallback=PopupWindow.active_window,
            translucent=True,
        )
        if not had_parent and owner is not None:
            menu.logger.debug(
                f"Menu._setup_as_popup: Parented to active window {owner}"
            )

    def ensure_on_screen(self) -> None:
        """Moves the menu to be fully visible on the screen if it is partially off-screen.

        See :meth:`PopupPlacement.clamp_to_screen
        <uitk.widgets.popup.placement.PopupPlacement.clamp_to_screen>`.
        """
        PopupPlacement.clamp_to_screen(self._menu)
