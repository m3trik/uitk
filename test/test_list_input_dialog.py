# !/usr/bin/python
# coding=utf-8
"""Unit tests for ``SwitchboardUtilsMixin.list_input_dialog``.

The list twin of ``input_dialog``: panels that need a "pick some of these"
prompt were hand-rolling a ``QDialog``, which meant each copy re-lost the
three things the house helper gets right — parenting, host-theme stylesheet
inheritance, and busy-cursor suspension.

Run standalone: python -m test.test_list_input_dialog
"""

import unittest
from unittest.mock import patch

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets

from uitk.switchboard.utils import SwitchboardUtilsMixin


def _accept(dlg):
    """Stand in for the modal ``exec_`` with an OK click."""
    return QtWidgets.QDialog.Accepted


def _reject(dlg):
    return QtWidgets.QDialog.Rejected


class TestListInputDialog(QtBaseTestCase):
    MATERIALS = ["lambert1", "wood_oak", "metal_steel"]

    def _show(self, items, exec_result=_accept, select=None, **kwargs):
        """Run the dialog with ``exec_`` stubbed, optionally selecting rows."""
        captured = {}

        def fake_exec(self_dlg):
            captured["dialog"] = self_dlg
            listing = self_dlg.findChild(QtWidgets.QListWidget)
            for row in select or []:
                listing.item(row).setSelected(True)
            return exec_result(self_dlg)

        with patch.object(QtWidgets.QDialog, "exec_", fake_exec):
            result = SwitchboardUtilsMixin.list_input_dialog(items, **kwargs)
        return result, captured.get("dialog")

    def test_returns_selected_entries(self):
        result, _ = self._show(self.MATERIALS, select=[0, 2])
        self.assertEqual(result, ["lambert1", "metal_steel"])

    def test_cancel_returns_empty(self):
        result, _ = self._show(self.MATERIALS, exec_result=_reject, select=[0, 1])
        self.assertEqual(result, [])

    def test_accept_with_nothing_selected_returns_empty(self):
        result, _ = self._show(self.MATERIALS)
        self.assertEqual(result, [])

    def test_empty_items_is_handled(self):
        result, dialog = self._show([])
        self.assertEqual(result, [])
        self.assertEqual(dialog.findChild(QtWidgets.QListWidget).count(), 0)

    def test_non_string_items_are_rendered(self):
        """Maya/Blender hand back node objects, not strs."""
        result, _ = self._show([1, 2, 3], select=[1])
        self.assertEqual(result, ["2"])

    def test_multi_false_restricts_to_single_selection(self):
        _, dialog = self._show(self.MATERIALS, multi=False)
        listing = dialog.findChild(QtWidgets.QListWidget)
        self.assertEqual(
            listing.selectionMode(), QtWidgets.QAbstractItemView.SingleSelection
        )

    def test_multi_is_the_default(self):
        _, dialog = self._show(self.MATERIALS)
        listing = dialog.findChild(QtWidgets.QListWidget)
        self.assertEqual(
            listing.selectionMode(), QtWidgets.QAbstractItemView.ExtendedSelection
        )

    def test_preselection_is_applied(self):
        result, _ = self._show(self.MATERIALS, selected=["wood_oak"])
        self.assertEqual(result, ["wood_oak"])

    def test_preselection_ignores_unknown_entries(self):
        result, _ = self._show(self.MATERIALS, selected=["not_in_scene"])
        self.assertEqual(result, [])

    def test_inherits_the_parent_stylesheet(self):
        """A dialog that ignores the host theme is the reason this helper exists."""
        parent = QtWidgets.QWidget()
        parent.setStyleSheet("QDialog { color: #abcdef; }")

        _, dialog = self._show(self.MATERIALS, parent=parent)

        self.assertEqual(dialog.styleSheet(), "QDialog { color: #abcdef; }")
        self.assertIs(dialog.parent(), parent)
        parent.deleteLater()

    def test_title_and_label_are_shown(self):
        _, dialog = self._show(
            self.MATERIALS, title="Choose Materials", label="Pick some:"
        )
        self.assertEqual(dialog.windowTitle(), "Choose Materials")
        labels = [w.text() for w in dialog.findChildren(QtWidgets.QLabel)]
        self.assertIn("Pick some:", labels)

    def test_suspends_the_busy_cursor(self):
        """Opened from inside a slot, the hourglass would otherwise stick."""
        with patch.object(
            SwitchboardUtilsMixin, "_suspend_override_cursor"
        ) as mock_suspend:
            self._show(self.MATERIALS)
        mock_suspend.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
