# !/usr/bin/python
# coding=utf-8
"""Tests for in-cell shortcut capture (uitk.widgets.delegates.shortcut_capture).

Regression coverage for the PySide6 crash where ``key | modifiers``
(int | Qt.KeyboardModifier) routed through a deprecated ``__ror__`` and
raised ``TypeError: QKeyCombination.__init__ called with wrong argument
types``. The fix coerces both operands to int before the OR.
"""
import unittest

from qtpy import QtWidgets, QtCore, QtGui
from conftest import QtBaseTestCase, setup_qt_application
from uitk.widgets.delegates.shortcut_capture import (
    ShortcutCaptureEdit,
    install_shortcut_capture,
)

app = setup_qt_application()


def _press(widget, key, modifiers=QtCore.Qt.NoModifier):
    """Send a synthetic key-press through ``widget.keyPressEvent``.

    Mirrors the real event path: ``event.key()`` yields a plain int and
    ``event.modifiers()`` a ``Qt.KeyboardModifier`` enum — the exact mix
    that triggered the original crash.
    """
    event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, modifiers)
    widget.keyPressEvent(event)


class TestShortcutCaptureEdit(QtBaseTestCase):
    """The in-cell capture editor."""

    def test_modifier_chord_does_not_raise_and_captures(self):
        """Ctrl+K captures cleanly (regression: no QKeyCombination crash)."""
        editor = ShortcutCaptureEdit()
        fired = []
        editor.chordCaptured.connect(lambda: fired.append(editor.sequence()))

        _press(editor, QtCore.Qt.Key_K, QtCore.Qt.ControlModifier)

        self.assertEqual(len(fired), 1)
        self.assertIn("K", editor.sequence())
        self.assertIn("Ctrl", editor.sequence())

    def test_bare_key_captures(self):
        editor = ShortcutCaptureEdit()
        _press(editor, QtCore.Qt.Key_F5)
        self.assertEqual(editor.sequence(), "F5")

    def test_lone_modifier_is_ignored(self):
        """A modifier with no real key must not commit a sequence."""
        editor = ShortcutCaptureEdit()
        fired = []
        editor.chordCaptured.connect(lambda: fired.append(True))

        _press(editor, QtCore.Qt.Key_Control, QtCore.Qt.ControlModifier)

        self.assertEqual(fired, [])
        self.assertIsNone(editor.sequence())

    def test_backspace_clears(self):
        editor = ShortcutCaptureEdit()
        _press(editor, QtCore.Qt.Key_Backspace)
        self.assertEqual(editor.sequence(), "")

    def test_accepts_shortcut_override(self):
        """The editor swallows ShortcutOverride so a chord is captured, not fired.

        Qt sends a ShortcutOverride to the focus widget before triggering any
        QShortcut. Accepting it cancels the shortcut and delivers the key as a
        normal press — without this, an already-assigned application-scoped
        shortcut fires its slot instead of the key being captured (the
        re-assign-a-taken-key bug).
        """
        editor = ShortcutCaptureEdit()
        event = QtGui.QKeyEvent(
            QtCore.QEvent.ShortcutOverride,
            QtCore.Qt.Key_S,
            QtCore.Qt.ControlModifier,
        )
        handled = editor.event(event)
        self.assertTrue(handled, "ShortcutOverride should be handled")
        self.assertTrue(event.isAccepted(), "ShortcutOverride should be accepted")


class TestInstallShortcutCapture(QtBaseTestCase):
    """The turnkey ``install_shortcut_capture`` helper on a real table."""

    def _table(self):
        table = QtWidgets.QTableWidget(1, 2)
        table.setItem(0, 0, QtWidgets.QTableWidgetItem("Action"))
        item = QtWidgets.QTableWidgetItem("")
        # editItem requires the item to be editable.
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        table.setItem(0, 1, item)
        return table

    def test_capture_emits_row_col_sequence(self):
        table = self._table()
        captured = []
        install_shortcut_capture(
            table, 1, lambda r, c, s: captured.append((r, c, s))
        )

        table.editItem(table.item(0, 1))
        QtWidgets.QApplication.processEvents()
        editor = table.viewport().focusWidget()
        self.assertIsInstance(editor, ShortcutCaptureEdit)

        _press(editor, QtCore.Qt.Key_J, QtCore.Qt.ControlModifier)
        # captured signal is deferred one tick (singleShot) so a slot may
        # safely rebuild the table — drain the event loop to deliver it.
        QtWidgets.QApplication.processEvents()

        self.assertEqual(len(captured), 1)
        row, col, seq = captured[0]
        self.assertEqual((row, col), (0, 1))
        self.assertIn("J", seq)

    def test_bordered_delegate_captures(self):
        """bordered=True (composes RowSelectionBorderDelegate) still captures."""
        from uitk.widgets.delegates.shortcut_capture import (
            BorderedShortcutCaptureDelegate,
        )

        table = self._table()
        captured = []
        delegate = install_shortcut_capture(
            table, 1, lambda r, c, s: captured.append(s), bordered=True
        )
        self.assertIsInstance(delegate, BorderedShortcutCaptureDelegate)

        table.editItem(table.item(0, 1))
        QtWidgets.QApplication.processEvents()
        editor = table.viewport().focusWidget()
        _press(editor, QtCore.Qt.Key_M, QtCore.Qt.ShiftModifier)
        QtWidgets.QApplication.processEvents()

        self.assertEqual(len(captured), 1)
        self.assertIn("M", captured[0])

    def test_noedit_triggers_still_opens_via_edititem(self):
        """Helper works even when the table forbids implicit edit triggers."""
        table = self._table()
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        captured = []
        install_shortcut_capture(
            table, 1, lambda r, c, s: captured.append(s)
        )

        table.editItem(table.item(0, 1))
        QtWidgets.QApplication.processEvents()
        editor = table.viewport().focusWidget()
        self.assertIsInstance(editor, ShortcutCaptureEdit)

        _press(editor, QtCore.Qt.Key_G)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(captured, ["G"])

    def test_keystroke_does_not_open_editor_under_noedit_triggers(self):
        """A stray keypress on a selected cell must not silently rebind.

        Default QTableWidget triggers include AnyKeyPressed/EditKeyPressed;
        consumers set NoEditTriggers so only an explicit double-click opens
        the capture editor (guards the accidental-rebind footgun).
        """
        table = self._table()
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        captured = []
        install_shortcut_capture(table, 1, lambda r, c, s: captured.append(s))

        table.setCurrentCell(0, 1)
        # Route a letter key through the table the way a focused view would.
        table.keyPressEvent(
            QtGui.QKeyEvent(
                QtCore.QEvent.KeyPress, QtCore.Qt.Key_X, QtCore.Qt.NoModifier
            )
        )
        QtWidgets.QApplication.processEvents()

        self.assertNotEqual(
            table.state(), QtWidgets.QAbstractItemView.EditingState
        )
        self.assertNotIsInstance(
            table.viewport().focusWidget(), ShortcutCaptureEdit
        )
        self.assertEqual(captured, [])


if __name__ == "__main__":
    unittest.main()
