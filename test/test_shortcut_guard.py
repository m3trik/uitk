# !/usr/bin/python
# coding=utf-8
"""Tests for ShortcutGuardMixin and who owns Ctrl+C when the console is app-wide.

Regression (live-Maya verified): with a uitk LineEdit focused, Ctrl+C copied the
*script console's* text instead of the field's, so the field could only be copied
from via its context menu. The cause was not Maya — the only Ctrl+C binding in the
session was uitk's own ScriptOutput, which used to back ``app_wide_copy`` with an
event filter installed on the QApplication. Such a filter sees key presses before
their target widget, bypassing the ShortcutOverride protocol that lets a focused
editor keep its own chords, so a stale console selection hijacked Copy app-wide.

The filter is gone; the ``ApplicationShortcut`` alone gives the console the same
reach *through* that protocol. These tests pin both halves: a focused editor (and
a focused read-only view, which needs the mixin to speak up at all) keeps its own
Ctrl+C, while the console still copies when nothing else claims the chord.

Second regression, same saga and the commoner symptom: that shortcut was always
enabled, so it consumed Ctrl+C from every read-only pane (they decline the
override) and then copied **nothing** — the clipboard was left untouched and the
pane could only be copied from via its context menu. Pinned here by
``TestConsoleShortcutIsGatedOnSelection`` (the shortcut is inert without a
selection) and ``TestRegisteredPaneKeepsCopy`` (a ``.ui``-declared plain
``QTextBrowser`` claims Copy once ``MainWindow`` registration installs the filter
form of the guard, so even a *stale* console selection can't take it).

Run standalone: python -m test.test_shortcut_guard
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets, QtGui, QtTest  # noqa: E402

from uitk.widgets.lineEdit import LineEdit  # noqa: E402
from uitk.widgets.mainWindow import MainWindow  # noqa: E402
from uitk.widgets.scriptOutput import ScriptOutput  # noqa: E402
from uitk.widgets.textEdit import TextEdit  # noqa: E402
from uitk.widgets.textViewBox import _ViewerTextEdit  # noqa: E402
from uitk.widgets.mixins.shortcut_guard import ShortcutGuardFilter  # noqa: E402


class _BareSwitchboard:
    """Minimal stand-in so MainWindow can register a widget without uitk.Switchboard."""

    default_signals = {}

    def convert_to_legal_name(self, name):
        return name

    def get_base_name(self, name):
        return name

    def has_tags(self, *_a, **_k):
        return False

    def get_slots_instance(self, *_a, **_k):
        return None

    def center_widget(self, *_a, **_k):
        return None

    def init_slot(self, *_a, **_k):
        return None

    def connect_slot(self, *_a, **_k):
        return None

SEQUENCE_KEYS = {
    QtGui.QKeySequence.Copy: QtCore.Qt.Key_C,
    QtGui.QKeySequence.Cut: QtCore.Qt.Key_X,
    QtGui.QKeySequence.Paste: QtCore.Qt.Key_V,
    QtGui.QKeySequence.Undo: QtCore.Qt.Key_Z,
    QtGui.QKeySequence.SelectAll: QtCore.Qt.Key_A,
}


def _override_event(sequence):
    event = QtGui.QKeyEvent(
        QtCore.QEvent.ShortcutOverride,
        SEQUENCE_KEYS[sequence],
        QtCore.Qt.ControlModifier,
    )
    event.ignore()
    return event


def _claims(widget, sequence):
    """Whether *widget* takes *sequence* for itself instead of letting it resolve.

    Puts Qt's own question to the widget — a ``ShortcutOverride`` it may accept.
    Test-only: some widgets *act* on this event (``SequencerWidget`` dispatches
    its bound command from ``event``), so asking is safe to do about a known
    widget under test and not safe to do about an arbitrary focus widget.
    """
    event = _override_event(sequence)
    widget.event(event)
    return event.isAccepted()


def _claims_through_filters(widget, sequence):
    """Like :func:`_claims`, but routed so installed event filters get their say.

    ``widget.event`` is called directly and so skips them — which is the whole
    mechanism behind :class:`ShortcutGuardFilter`, the form used for widgets uitk
    doesn't define.
    """
    event = _override_event(sequence)
    QtWidgets.QApplication.sendEvent(widget, event)
    return event.isAccepted()


def _key_click(widget, key, modifier):
    """``QTest.keyClick`` that puts the global modifier state back.

    ``keyboardModifiers()`` is a cache of the last processed key event, and QTest's
    events maintain it — an unreleased Ctrl leaks into every later test in the
    process (it has broken test_sequencer's snapping before).
    """
    QtTest.QTest.keyClick(widget, key, modifier)
    for mod, mod_key in (
        (QtCore.Qt.ControlModifier, QtCore.Qt.Key_Control),
        (QtCore.Qt.ShiftModifier, QtCore.Qt.Key_Shift),
        (QtCore.Qt.AltModifier, QtCore.Qt.Key_Alt),
    ):
        if modifier & mod:
            QtTest.QTest.keyRelease(widget, mod_key, QtCore.Qt.NoModifier)


class TestWidgetClaims(QtBaseTestCase):
    """Which widgets keep an editing chord for themselves, and which hand it on."""

    def test_editable_field_owns_the_editing_family(self):
        le = self.track_widget(LineEdit())
        le.setText("abc")
        for sequence in (
            QtGui.QKeySequence.Copy,
            QtGui.QKeySequence.Cut,
            QtGui.QKeySequence.Paste,
            QtGui.QKeySequence.Undo,
            QtGui.QKeySequence.SelectAll,
        ):
            with self.subTest(sequence=sequence):
                self.assertTrue(_claims(le, sequence))

    def test_read_only_field_keeps_copy_and_releases_the_writes(self):
        le = self.track_widget(LineEdit())
        le.setText("abc")
        le.setReadOnly(True)
        self.assertTrue(_claims(le, QtGui.QKeySequence.Copy))
        self.assertFalse(_claims(le, QtGui.QKeySequence.Paste))

    def test_plain_read_only_browser_claims_nothing(self):
        """Why the mixin exists: bare Qt hands Copy to whatever is bound app-wide."""
        browser = self.track_widget(QtWidgets.QTextBrowser())
        browser.setPlainText("abc")
        self.assertFalse(_claims(browser, QtGui.QKeySequence.Copy))

    def test_guarded_viewer_claims_copy(self):
        viewer = self.track_widget(_ViewerTextEdit())
        viewer.setPlainText("abc")
        viewer.selectAll()  # Copy is only claimed when there is something to copy
        self.assertTrue(_claims(viewer, QtGui.QKeySequence.Copy))
        self.assertTrue(_claims(viewer, QtGui.QKeySequence.SelectAll))

    def test_guarded_viewer_releases_writes_it_cannot_perform(self):
        viewer = self.track_widget(_ViewerTextEdit())
        viewer.setPlainText("abc")
        self.assertFalse(_claims(viewer, QtGui.QKeySequence.Paste))
        self.assertFalse(_claims(viewer, QtGui.QKeySequence.Undo))

    def test_unrelated_chord_is_never_claimed(self):
        viewer = self.track_widget(_ViewerTextEdit())
        event = QtGui.QKeyEvent(
            QtCore.QEvent.ShortcutOverride, QtCore.Qt.Key_B, QtCore.Qt.ControlModifier
        )
        self.assertFalse(viewer.claims_shortcut(event))

    def test_copy_with_nothing_selected_is_left_to_others(self):
        """A view with no selection has nothing to put on the clipboard, so it must
        not swallow the chord from an app-wide copy that does."""
        viewer = self.track_widget(_ViewerTextEdit())
        viewer.setPlainText("abc")
        self.assertFalse(_claims(viewer, QtGui.QKeySequence.Copy))
        viewer.selectAll()
        self.assertTrue(_claims(viewer, QtGui.QKeySequence.Copy))

    def test_read_only_uitk_text_edit_keeps_copy(self):
        """uitk's own TextEdit in read-only mode — bare Qt claims nothing there."""
        te = self.track_widget(TextEdit())
        te.setPlainText("abc")
        te.setReadOnly(True)
        te.selectAll()
        self.assertTrue(_claims(te, QtGui.QKeySequence.Copy))
        self.assertTrue(_claims(te, QtGui.QKeySequence.SelectAll))
        self.assertFalse(_claims(te, QtGui.QKeySequence.Paste))

    def test_subclass_can_narrow_the_claimed_set(self):
        """``guarded_shortcuts`` is documented as overridable, and both entry points
        must read the *widget's* class — a shared helper that hard-bound the base
        class would silently ignore the override (and the filter, which runs first,
        would mask the widget's own answer)."""

        class CopyOnlyViewer(_ViewerTextEdit):
            guarded_shortcuts = (QtGui.QKeySequence.Copy,)

        viewer = self.track_widget(CopyOnlyViewer())
        viewer.setPlainText("abc")
        viewer.selectAll()
        self.assertTrue(_claims(viewer, QtGui.QKeySequence.Copy))
        self.assertFalse(_claims(viewer, QtGui.QKeySequence.SelectAll))

        # Same answer once the filter form is also installed on it.
        viewer.installEventFilter(ShortcutGuardFilter(viewer))
        self.assertTrue(_claims_through_filters(viewer, QtGui.QKeySequence.Copy))
        self.assertFalse(_claims_through_filters(viewer, QtGui.QKeySequence.SelectAll))

    def test_probe_leaves_the_widget_untouched(self):
        """``widget_claims`` is a query — it must not edit, select, or clear."""
        le = self.track_widget(LineEdit())
        le.setText("abc")
        le.setCursorPosition(1)
        _claims(le, QtGui.QKeySequence.Cut)
        _claims(le, QtGui.QKeySequence.Paste)
        self.assertEqual(le.text(), "abc")
        self.assertFalse(le.hasSelectedText())


class TestConsoleDoesNotStealCopy(QtBaseTestCase):
    """The reported bug, reproduced in-process."""

    def _console_with_selection(self):
        console = self.track_widget(ScriptOutput(app_wide_copy=True))
        console.setPlainText("CONSOLE TEXT")
        console.selectAll()
        # Qt deactivates a QShortcut owned by a hidden widget even at
        # ApplicationShortcut scope, so the console must be shown for the
        # app-wide path to be under test at all.
        console.show()
        QtWidgets.QApplication.processEvents()
        return console

    def _copy_from(self, widget):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.clear()
        _key_click(widget, QtCore.Qt.Key_C, QtCore.Qt.ControlModifier)
        QtWidgets.QApplication.processEvents()
        return clipboard.text()

    def _require_clipboard(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText("sentinel")
        if clipboard.text() != "sentinel":
            self.skipTest("environment cannot round-trip the clipboard")

    def test_focused_field_keeps_its_own_ctrl_c(self):
        self._require_clipboard()
        console = self._console_with_selection()
        window = self.track_widget(QtWidgets.QWidget())
        QtWidgets.QVBoxLayout(window).addWidget(console)
        field = LineEdit()
        window.layout().addWidget(field)
        window.show()
        window.activateWindow()
        QtWidgets.QApplication.processEvents()

        field.setText("field text")
        field.setFocus(QtCore.Qt.MouseFocusReason)
        field.selectAll()
        QtWidgets.QApplication.processEvents()
        self.assertIs(QtWidgets.QApplication.focusWidget(), field)

        self.assertEqual(self._copy_from(field), "field text")

    def test_focused_read_only_view_keeps_its_own_ctrl_c(self):
        """The second victim of the same grab, and the case that needs the mixin:
        a read-only view claims nothing from Qt on its own, so it can only hold
        Ctrl+C against an app-wide binding once ``ShortcutGuardMixin`` speaks up.
        """
        self._require_clipboard()
        console = self._console_with_selection()
        window = self.track_widget(QtWidgets.QWidget())
        QtWidgets.QVBoxLayout(window).addWidget(console)
        viewer = _ViewerTextEdit()
        viewer.setPlainText("VIEWER TEXT")
        window.layout().addWidget(viewer)
        window.show()
        window.activateWindow()
        QtWidgets.QApplication.processEvents()

        viewer.selectAll()
        viewer.setFocus(QtCore.Qt.MouseFocusReason)
        QtWidgets.QApplication.processEvents()
        self.assertIs(QtWidgets.QApplication.focusWidget(), viewer)

        self.assertEqual(self._copy_from(viewer), "VIEWER TEXT")

    def test_console_copies_when_it_holds_focus(self):
        """The deference must not cost the console its own hover-focus copy."""
        self._require_clipboard()
        console = self._console_with_selection()
        console.activateWindow()
        console.setFocus(QtCore.Qt.MouseFocusReason)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self._copy_from(console), "CONSOLE TEXT")

    def test_console_copies_when_focus_cannot_handle_copy(self):
        """``app_wide_copy``'s reason to exist: a focus widget with no Copy of its
        own (a button, the host's viewport) leaves the chord to the console."""
        self._require_clipboard()
        console = self._console_with_selection()
        button = self.track_widget(QtWidgets.QPushButton("x"))
        button.show()
        button.activateWindow()
        button.setFocus()
        QtWidgets.QApplication.processEvents()
        self.assertIs(QtWidgets.QApplication.focusWidget(), button)
        self.assertEqual(self._copy_from(button), "CONSOLE TEXT")

    def test_widget_scoped_console_never_reaches_outside_itself(self):
        """``app_wide_copy=False`` (Blender / standalone) must stay local even to a
        focus widget that has no Copy of its own."""
        self._require_clipboard()
        console = self.track_widget(ScriptOutput(app_wide_copy=False))
        console.setPlainText("CONSOLE TEXT")
        console.selectAll()
        console.show()
        button = self.track_widget(QtWidgets.QPushButton("x"))
        button.show()
        button.activateWindow()
        button.setFocus()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self._copy_from(button), "")


class TestRegisteredPaneKeepsCopy(QtBaseTestCase):
    """Panels declare log panes as plain ``QTextBrowser`` in their ``.ui`` (mayatk /
    blendertk scene_exporter ``txt003`` and ~20 siblings), so the mixin can't reach
    them — MainWindow registration installs the filter form instead."""

    def _window_with_pane(self, pane):
        pane.setObjectName("txt003")
        central = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(central).addWidget(pane)
        window = self.track_widget(
            MainWindow(
                name="test_shortcut_guard_window",
                switchboard_instance=_BareSwitchboard(),
                central_widget=central,
                restore_window_size=False,
                ensure_on_screen=False,
            )
        )
        window.register_widget(pane)
        return window

    def test_bare_browser_claims_copy_once_registered(self):
        pane = QtWidgets.QTextBrowser()
        pane.setPlainText("PANE TEXT")
        self._window_with_pane(pane)
        pane.selectAll()
        self.assertTrue(_claims_through_filters(pane, QtGui.QKeySequence.Copy))

    def test_registration_does_not_grant_writes_to_a_read_only_pane(self):
        pane = QtWidgets.QTextBrowser()
        pane.setPlainText("PANE TEXT")
        self._window_with_pane(pane)
        pane.selectAll()
        self.assertFalse(_claims_through_filters(pane, QtGui.QKeySequence.Paste))

    def test_guard_tracks_read_only_flipped_after_registration(self):
        """Installation is unconditional precisely so a later ``setReadOnly`` can't
        strip the guard — the filter re-reads state per event."""
        pane = QtWidgets.QTextEdit()
        pane.setPlainText("PANE TEXT")
        self._window_with_pane(pane)
        pane.selectAll()
        self.assertTrue(_claims_through_filters(pane, QtGui.QKeySequence.Paste))
        pane.setReadOnly(True)
        self.assertFalse(_claims_through_filters(pane, QtGui.QKeySequence.Paste))
        self.assertTrue(_claims_through_filters(pane, QtGui.QKeySequence.Copy))

    def test_non_text_widgets_are_left_alone(self):
        button = QtWidgets.QPushButton("x")
        window = self._window_with_pane(QtWidgets.QTextBrowser())
        button.setObjectName("b000")
        window.register_widget(button)
        self.assertFalse(_claims_through_filters(button, QtGui.QKeySequence.Copy))

    def test_one_filter_serves_every_pane(self):
        """Re-registration must not stack duplicate filters."""
        pane = QtWidgets.QTextBrowser()
        window = self._window_with_pane(pane)
        first = window._shortcut_guard
        other = QtWidgets.QTextBrowser()
        other.setObjectName("txt004")
        window.register_widget(other)
        self.assertIs(window._shortcut_guard, first)


class TestConsoleShortcutIsGatedOnSelection(QtBaseTestCase):
    """The reported bug: with NO console selection, its app-scope shortcut still
    consumed Ctrl+C from a read-only pane and then copied nothing — so the pane
    could only be copied from via its context menu (live-Maya measured)."""

    def _console(self, text="CONSOLE TEXT"):
        console = self.track_widget(ScriptOutput(app_wide_copy=True))
        console.setPlainText(text)
        console.show()
        QtWidgets.QApplication.processEvents()
        return console

    def test_shortcut_is_inert_without_a_selection(self):
        console = self._console()
        self.assertFalse(console._copy_shortcut.isEnabled())

    def test_shortcut_arms_and_disarms_with_the_selection(self):
        console = self._console()
        console.selectAll()
        QtWidgets.QApplication.processEvents()
        self.assertTrue(console._copy_shortcut.isEnabled())

        cursor = console.textCursor()
        cursor.clearSelection()
        console.setTextCursor(cursor)
        QtWidgets.QApplication.processEvents()
        self.assertFalse(console._copy_shortcut.isEnabled())

    def test_unselected_console_leaves_a_bare_pane_its_own_copy(self):
        """End-to-end, and the exact user-visible symptom: the clipboard must get the
        pane's text, not stay untouched."""
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText("sentinel")
        if clipboard.text() != "sentinel":
            self.skipTest("environment cannot round-trip the clipboard")

        console = self._console()  # no selection — the everyday state
        pane = QtWidgets.QTextBrowser()  # deliberately unguarded: shortcut gating alone
        pane.setPlainText("PANE TEXT")
        window = self.track_widget(QtWidgets.QWidget())
        QtWidgets.QVBoxLayout(window).addWidget(pane)
        window.show()
        window.activateWindow()
        QtWidgets.QApplication.processEvents()

        pane.selectAll()
        pane.setFocus(QtCore.Qt.MouseFocusReason)
        QtWidgets.QApplication.processEvents()
        self.assertIs(QtWidgets.QApplication.focusWidget(), pane)

        clipboard.clear()
        _key_click(pane, QtCore.Qt.Key_C, QtCore.Qt.ControlModifier)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(clipboard.text(), "PANE TEXT")
        self.assertFalse(console._copy_shortcut.isEnabled())  # it never armed


if __name__ == "__main__":
    unittest.main()
