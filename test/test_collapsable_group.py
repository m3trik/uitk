# !/usr/bin/python
# coding=utf-8
"""Unit tests for the CollapsableGroup widget.

CollapsableGroup is a checkable QGroupBox whose title doubles as an
expand/collapse toggle. The checkbox indicator the style draws to the left of
the title is unwanted: it indents the title relative to a plain QGroupBox, and
the QSS ``::indicator { width:0; height:0 }`` rule doesn't fully remove it
(under QStyleSheetStyle it leaves a residual indent — the offset seen in
Blender). These tests pin the style-independent contract:

- the checkable indicator subcontrol is suppressed for painting, and
- the title aligns with a plain (non-checkable) QGroupBox,

while collapse-via-toggle keeps working.

Run standalone: python -m test.test_collapsable_group
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtGui  # noqa: E402

from uitk.widgets.collapsableGroup import CollapsableGroup  # noqa: E402


class TestCollapsableGroupIndicatorHidden(QtBaseTestCase):
    """The checkbox indicator is hidden and its reserved space reclaimed, so the
    title aligns with a plain QGroupBox regardless of the active Qt style."""

    def test_group_is_checkable_with_indicator_subcontrol(self):
        """Precondition: it IS a checkable group box, so the style reserves a
        ``SC_GroupBoxCheckBox`` subcontrol — there is something to hide."""
        g = self.track_widget(CollapsableGroup("My Group"))
        self.assertTrue(g.isCheckable())
        opt = QtWidgets.QStyleOptionGroupBox()
        g.initStyleOption(opt)
        self.assertTrue(
            bool(opt.subControls & QtWidgets.QStyle.SC_GroupBoxCheckBox),
            "A checkable QGroupBox must carry SC_GroupBoxCheckBox by default.",
        )

    def test_paint_option_drops_checkbox_subcontrol(self):
        """The option used for painting must not include the checkbox subcontrol
        — that is what stops the indicator from being drawn."""
        g = self.track_widget(CollapsableGroup("My Group"))
        self.assertFalse(
            bool(
                g._checkbox_suppressed_option().subControls
                & QtWidgets.QStyle.SC_GroupBoxCheckBox
            ),
            "paintEvent must drop SC_GroupBoxCheckBox so the indicator isn't drawn.",
        )

    def test_title_aligns_with_plain_groupbox(self):
        """With the checkbox suppressed, the title's left edge matches a plain
        QGroupBox's title (the checkbox no longer reserves space)."""
        g = self.track_widget(CollapsableGroup("My Group"))
        g.resize(200, 80)
        plain = self.track_widget(QtWidgets.QGroupBox("My Group"))
        plain.resize(200, 80)

        cc = QtWidgets.QStyle.CC_GroupBox
        sc_label = QtWidgets.QStyle.SC_GroupBoxLabel

        g_label = g.style().subControlRect(
            cc, g._checkbox_suppressed_option(), sc_label, g
        )
        p_opt = QtWidgets.QStyleOptionGroupBox()
        plain.initStyleOption(p_opt)
        p_label = plain.style().subControlRect(cc, p_opt, sc_label, plain)

        self.assertEqual(
            g_label.x(),
            p_label.x(),
            "CollapsableGroup title must align with a plain QGroupBox title.",
        )

    def test_paints_without_error(self):
        """The paintEvent override is a valid replacement (renders cleanly)."""
        g = self.track_widget(CollapsableGroup("My Group"))
        g.resize(200, 80)
        pixmap = QtGui.QPixmap(g.size())
        g.render(pixmap)  # drives paintEvent through the override

    def test_hiding_checkbox_keeps_collapse_working(self):
        """Suppressing the indicator is cosmetic — toggling still collapses and
        expands the content (the title remains the toggle)."""
        g = self.track_widget(CollapsableGroup("My Group"))
        child = QtWidgets.QLabel("content")
        g.addWidget(child)

        g.setChecked(False)  # collapse
        self.assertTrue(child.isHidden())
        g.setChecked(True)  # expand
        self.assertFalse(child.isHidden())


if __name__ == "__main__":
    unittest.main()
