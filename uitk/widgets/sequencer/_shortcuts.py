# !/usr/bin/python
# coding=utf-8
"""A :class:`~uitk.widgets.sequencer._sequencer.SequencerWidget`'s keys and
their legend: the shortcut table and the dispatch that keeps a matched key
from the host, and the corner overlay that explains the gestures -- parts the
widget holds and publishes (``_sequencer.py``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from qtpy import QtCore, QtGui, QtWidgets

from uitk.managers.shortcut_manager import ShortcutManager
from uitk.widgets.sequencer._editor import SequencerEditor
from uitk.widgets.sequencer._timeline import _ALT_MOD, _CTRL_MOD, _SHIFT_MOD

if TYPE_CHECKING:
    from uitk.widgets.sequencer._sequencer import SequencerWidget

#: What "On Modifier" answers to -- the three the legend is about.  As plain
#: ints, the form the timeline banks a chord in.
_LEGEND_MODIFIERS = _ALT_MOD | _CTRL_MOD | _SHIFT_MOD


class _ShortcutLegend:
    """The corner legend (:class:`ShortcutOverlay`): the rows registered with
    the shortcut table -- the active editor's, as the layers edit them --
    when it shows (:attr:`SequencerWidget.shortcut_overlay_mode`), and the
    gesture group under the pointer it brightens."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        #: The legend rows registered with the manager now
        #: (:meth:`apply`): the active editor's, as the layers edit them.
        self.rows: tuple = ()
        self.overlay = None  # built on first show (shortcut_overlay_visible)
        #: off / on / modifier -- see :attr:`SequencerWidget.shortcut_overlay_mode`.
        self.mode: str = "off"
        # The gesture group under the pointer, remembered so a legend that
        # rises later opens on the right page.
        self.gesture_context: Optional[str] = None

    def editor_rows(self, editor: SequencerEditor) -> tuple:
        """*editor*'s legend rows, as each layer edits them in turn."""
        rows = tuple(editor.gestures)
        for layer in self._sequencer._layers.values():
            legend = getattr(layer, "legend", None)
            if legend is not None:
                rows = tuple(legend(editor.name, rows))
        return rows

    def apply(self, editor: Optional[SequencerEditor]) -> None:
        sq = self._sequencer
        rows = self.editor_rows(editor or sq.active_editor)
        for group in dict.fromkeys(g for g, _k, _d in self.rows):
            sq._shortcut_mgr.remove_gesture_group(group)
        for group, keys, description in rows:
            sq._shortcut_mgr.add_gesture(group, keys, description)
        self.rows = rows

    def visible(self) -> bool:
        return self.overlay is not None and self.overlay.isVisible()

    def set_mode(self, value) -> None:
        if isinstance(value, bool):
            value = "on" if value else "off"
        value = str(value).lower()
        modes = self._sequencer.SHORTCUT_OVERLAY_MODES
        if value not in modes:
            raise ValueError(f"shortcut_overlay_mode: {value!r} is not one of {modes}")
        if value == self.mode:
            return
        self.mode = value
        self.refresh()

    def tracking(self) -> bool:
        return self._sequencer.shortcut_overlay_visible or self.mode == "modifier"

    def refresh(self) -> None:
        """Put the legend on screen, or take it off, per the current mode."""
        sq = self._sequencer
        wanted = self.mode == "on" or (
            self.mode == "modifier" and bool(sq.modifiers_held & _LEGEND_MODIFIERS)
        )
        if wanted and self.overlay is None:
            self.overlay = sq._shortcut_mgr.overlay(sq._timeline)
            self.overlay.set_context(self.gesture_context)
        overlay = self.overlay
        if overlay is None or overlay.isVisible() == wanted:
            return
        overlay.setVisible(wanted)
        if wanted:
            overlay.refresh()

    def set_gesture_context(self, group: Optional[str]) -> None:
        self.gesture_context = group
        if self.overlay is not None:
            self.overlay.set_context(group)


class _KeyRouting:
    """The widget's keys: the shortcut table (a :class:`ShortcutManager`) and
    the active editor's own keys answered before it, and the dispatch that
    keeps a matched key from leaking to the host -- at the widget, or at its
    top-level window while :attr:`SequencerWidget.window_shortcuts` is on."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        #: Keys the active editor answers before the shortcut table.
        self.editor_keys: Dict[str, dict] = {}
        self.manager: Optional[ShortcutManager] = None  # install_shortcuts()
        self.window_shortcuts: bool = False  # shortcuts active at window level
        # Top-level window the ShortcutOverride filter is installed on.
        # Tracked by identity (not a bool) so a reparent — e.g. Maya
        # dock/undock — moves the filter instead of leaving it dangling
        # on the old window.
        self.filtered_window = None
        # (key, modifiers) dispatched by filter_window_event, awaiting its
        # follow-up KeyPress; 0 when nothing is pending.
        self.filter_pending_key = 0
        # (key, modifiers) dispatched by shortcut_override, awaiting the
        # KeyPress Qt delivers next so key_press consumes it once instead
        # of re-dispatching; 0 when nothing is pending.
        self.override_pending_key = 0

    def install_shortcuts(self) -> None:
        """Build the shortcut table: the widget's own keys."""
        sq = self._sequencer
        _shortcut_defs = [
            ("Ctrl+Z", sq.undo, "Undo last clip edit"),
            ("Ctrl+Shift+Z", sq.redo, "Redo last undone edit"),
            ("Left", sq.go_to_prev_key, "Jump to previous key"),
            ("Right", sq.go_to_next_key, "Jump to next key"),
            ("Shift+Left", sq.step_backward, "Step playhead backward"),
            ("Shift+Right", sq.step_forward, "Step playhead forward"),
            ("Home", sq.go_to_start, "Jump playhead to start"),
            ("End", sq.go_to_end, "Jump playhead to last clip end"),
            ("M", sq.add_marker_at_playhead, "Add marker at playhead"),
            ("F", sq.frame_shot, "Frame the active shot range"),
            ("Delete", sq._delete_selected_keys, "Delete selected keyframes"),
            ("Escape", sq._cancel_active_drag, "Cancel the active drag"),
        ]
        self.manager = ShortcutManager(sq)
        _ctx = QtCore.Qt.WidgetWithChildrenShortcut
        self.manager.add_shortcuts_batch(
            [(k, fn, desc, _ctx) for k, fn, desc in _shortcut_defs]
        )

    def sync_sequences(self) -> None:
        keys = list(self.editor_keys)
        keys += [
            k
            for k, v in self.manager.shortcuts.items()
            if not v.get("read_only") and k not in self.editor_keys
        ]
        self._sequencer._timeline._shortcut_sequences = [
            QtGui.QKeySequence(k) for k in keys
        ]

    def set_window_shortcuts(self, enabled: bool) -> None:
        if enabled == self.window_shortcuts:
            return
        self.window_shortcuts = enabled
        ctx = (
            QtCore.Qt.WindowShortcut
            if enabled
            else QtCore.Qt.WidgetWithChildrenShortcut
        )
        for entry in self.manager.shortcuts.values():
            if entry["shortcut"] is not None:
                entry["shortcut"].setContext(ctx)
        if not enabled:
            self.uninstall_window_filter()
        elif self._sequencer.isVisible():
            # Enabled at runtime on an already-visible widget — there
            # may be no further showEvent, so install immediately or
            # keys leak to the host until the panel is hidden/reshown.
            self.install_window_filter()
        # Otherwise defer to showEvent: self.window() may not return
        # the actual top-level until the widget is shown (parented).

    def on_show(self) -> None:
        if self.window_shortcuts:
            # Self-guards on same-window; after a reparent (Maya
            # dock/undock) this moves the filter to the new top-level.
            self.install_window_filter()

    def install_window_filter(self) -> None:
        sq = self._sequencer
        win = sq.window()
        if win is None or win is self.filtered_window:
            return
        if self.filtered_window is not None:
            try:
                self.filtered_window.removeEventFilter(sq)
            except RuntimeError:
                pass  # old top-level already destroyed
        win.installEventFilter(sq)
        self.filtered_window = win

    def uninstall_window_filter(self) -> None:
        if self.filtered_window is not None:
            try:
                self.filtered_window.removeEventFilter(self._sequencer)
            except RuntimeError:
                pass  # top-level already destroyed
            self.filtered_window = None

    def match(self, event):
        mods = event.modifiers()
        mod_int = mods.value if hasattr(mods, "value") else int(mods)
        key = QtGui.QKeySequence(event.key() | mod_int)
        for seq in self._sequencer._timeline._shortcut_sequences:
            if key.matches(seq) == QtGui.QKeySequence.ExactMatch:
                name = seq.toString()
                # The active editor answers its own keys first: a graph
                # editor's Delete is not the track rows' Delete.
                entry = self.editor_keys.get(name)
                return seq, entry or self.manager.shortcuts.get(name)
        return None

    def filter_window_event(self, event) -> bool:
        """True: *event*, on the top-level window, was a shortcut and is
        consumed (``SequencerWidget.eventFilter``)."""
        if not self.window_shortcuts:
            return False
        if event.type() == QtCore.QEvent.ShortcutOverride:
            # Don't intercept keystrokes while a text-editing widget has focus
            focused = QtWidgets.QApplication.focusWidget()
            if isinstance(
                focused,
                (
                    QtWidgets.QLineEdit,
                    QtWidgets.QTextEdit,
                    QtWidgets.QPlainTextEdit,
                ),
            ):
                return False
            match = self._sequencer._match_shortcut(event)
            if match is not None:
                event.accept()
                # Dispatch the action directly — the QShortcut won't
                # fire because we accepted the override.
                _seq, entry = match
                if entry and entry.get("action"):
                    entry["action"]()
                mods = event.modifiers()
                self.filter_pending_key = (
                    event.key(),
                    mods.value if hasattr(mods, "value") else int(mods),
                )
                return True
        elif event.type() == QtCore.QEvent.KeyPress and self.filter_pending_key:
            # Consume the KeyPress that Qt delivers after the accepted
            # ShortcutOverride so the host app doesn't also act on it.
            # A pending key that never arrived (the press was accepted
            # elsewhere) must not linger and eat a later press — clear
            # on ANY KeyPress, consume only an exact key+mods match.
            pending_key, pending_mods = self.filter_pending_key
            self.filter_pending_key = 0
            mods = event.modifiers()
            mod_int = mods.value if hasattr(mods, "value") else int(mods)
            if event.key() == pending_key and mod_int == pending_mods:
                return True
        return False

    def shortcut_override(self, event) -> bool:
        """True: the widget's ``ShortcutOverride`` *event* matched a shortcut,
        which ran (``SequencerWidget.event``)."""
        match = self._sequencer._match_shortcut(event)
        if match is None:
            return False
        event.accept()
        # Dispatch here instead of relying on the follow-up KeyPress
        # bubbling back to keyPressEvent: accepting the override
        # suppresses the QShortcut, and any intermediate focused
        # child (e.g. a clicked track label) can swallow the KeyPress
        # so it never reaches keyPressEvent — leaving the shortcut
        # dead.  override_pending_key gates the follow-up press so
        # the action can't fire twice.
        _seq, entry = match
        if entry and entry.get("action"):
            entry["action"]()
        mods = event.modifiers()
        self.override_pending_key = (
            event.key(),
            mods.value if hasattr(mods, "value") else int(mods),
        )
        return True

    def key_press(self, event) -> bool:
        """True: the key press was a shortcut's, or the one that follows an
        override already dispatched (``SequencerWidget.keyPressEvent``)."""
        # Consume (once) the KeyPress that follows an override we already
        # dispatched in shortcut_override().  Clear on ANY press so a stale
        # pending key — whose press never arrived because a child ate it —
        # can't eat a later, unrelated press.
        pending = self.override_pending_key
        if pending:
            self.override_pending_key = 0
            mods = event.modifiers()
            mod_int = mods.value if hasattr(mods, "value") else int(mods)
            if event.key() == pending[0] and mod_int == pending[1]:
                event.accept()
                return True
        match = self._sequencer._match_shortcut(event)
        if match is not None:
            _seq, entry = match
            if entry and entry.get("action"):
                entry["action"]()
            event.accept()
            return True
        return False
