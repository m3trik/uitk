# !/usr/bin/python
# coding=utf-8
"""Regression tests for ConvertMixin.can_convert / to_qobject agreement.

``can_convert`` is a guard for ``to_qobject``: it must answer ``True`` only
when ``to_qobject`` would actually succeed. A prior version returned ``True``
for any value whose target type was in ``TYPES`` (ignoring arity), so a call
site guarded by ``can_convert`` could still hit a ``to_qobject`` exception --
e.g. a 3-tuple for ``QSize``.

Run standalone: python test/test_convert.py
"""
import unittest

from conftest import BaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtGui  # noqa: E402
from uitk.widgets.mixins.convert import ConvertMixin  # noqa: E402


class TestCanConvertAgreesWithToQobject(BaseTestCase):
    """The guard (can_convert) and the action (to_qobject) must never disagree."""

    def _converts(self, value, qtype) -> bool:
        try:
            ConvertMixin.to_qobject(value, qtype)
            return True
        except Exception:
            return False

    def _assert_agree(self, value, qtype) -> bool:
        can = ConvertMixin.can_convert(value, qtype)
        converts = self._converts(value, qtype)
        self.assertEqual(
            can,
            converts,
            f"can_convert({value!r}, {qtype}) = {can} but to_qobject "
            f"{'succeeded' if converts else 'failed'}",
        )
        return can

    def test_qsize_wrong_arity_now_consistent(self):
        # The headline regression: a 3-tuple is invalid for QSize. Previously
        # can_convert said True while to_qobject raised. Both must now say the
        # value cannot be converted.
        self.assertFalse(ConvertMixin.can_convert((30, 40, 50), QtCore.QSize))
        self.assertFalse(self._converts((30, 40, 50), QtCore.QSize))
        self._assert_agree((30, 40, 50), QtCore.QSize)

    def test_qpoint_wrong_arity_now_consistent(self):
        self.assertFalse(self._assert_agree((1, 2, 3), QtCore.QPoint))

    def test_valid_conversions_agree(self):
        for value, qtype in (
            ((30, 40), QtCore.QSize),
            ((10, 20), QtCore.QPoint),
            ((60, 70, 80, 90), QtCore.QRect),
            ((150.0, 160.0), QtCore.QPointF),
            ((170.0, 180.0, 190.0, 200.0), QtGui.QVector4D),
            ((90, 100, 110), QtGui.QColor),
            ("#ff0000", QtGui.QColor),
        ):
            self.assertTrue(self._assert_agree(value, qtype), (value, qtype))

    def test_already_correct_type_agrees(self):
        self.assertTrue(self._assert_agree(QtCore.QPoint(1, 2), QtCore.QPoint))

    def test_string_type_name_resolution_agrees(self):
        self.assertTrue(self._assert_agree((1, 2), "QPoint"))
        self.assertFalse(self._assert_agree((1, 2, 3), "QSize"))


if __name__ == "__main__":
    unittest.main()
