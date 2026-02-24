# !/usr/bin/python
# coding=utf-8
"""Tests for the CollapsableGroup extra-space bug.

Bug: Each CollapsableGroup had forced 20px top margin in setLayout() override,
even though the stylesheet already handles title positioning. This wasted ~19px
of vertical space per group. Additionally, the collapsed height was inconsistent
between toggle_expand (title_height) and sizeHint (title_height + 5), and the
window resize used an indirect sizeHint comparison instead of direct delta.

Fixed: 2026-02-20
"""
import sys
import unittest

from qtpy import QtWidgets, QtCore

from uitk.widgets.collapsableGroup import CollapsableGroup


class TestCollapsableGroupSpacing(unittest.TestCase):
    """Verify toggling the CollapsableGroup doesn't leave extra space."""

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    def setUp(self):
        self.window = QtWidgets.QMainWindow()
        central = QtWidgets.QWidget()
        self.window.setCentralWidget(central)
        self.layout = QtWidgets.QVBoxLayout(central)

        self.group = CollapsableGroup("Test Group")
        self.group.restore_state = False  # Don't persist state in tests
        self.group.addWidget(QtWidgets.QLabel("Line 1"))
        self.group.addWidget(QtWidgets.QLabel("Line 2"))
        self.group.addWidget(QtWidgets.QPushButton("Button"))

        self.layout.addWidget(self.group)
        self.layout.addStretch()

        self.window.resize(300, 200)
        self.window.show()
        self._process()

    def tearDown(self):
        self.window.close()
        self._process()

    def _process(self):
        """Let Qt fully process layout updates including timers."""
        for _ in range(10):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)

    def test_setLayout_does_not_force_excessive_top_margin(self):
        """Verify setLayout doesn't override user-specified top margin to 20px.

        Bug: setLayout() forced topMargin=20 if caller set <15, wasting ~19px
        per group. The stylesheet already handles title positioning.
        Fixed: 2026-02-20
        """
        group = CollapsableGroup("Margin Test")
        group.restore_state = False
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        group.setLayout(layout)

        top_margin = group.layout().contentsMargins().top()
        self.assertLessEqual(
            top_margin,
            15,
            f"setLayout forced top margin to {top_margin}px — "
            f"should not override user-specified margins",
        )

    def test_toggle_cycle_does_not_accumulate_space(self):
        """Verify window height returns to original after collapse+expand cycle.

        Bug: _adjust_window_size used window.sizeHint() vs actual size,
        causing potential height drift each toggle cycle.
        Fixed: 2026-02-20
        """
        self._process()
        initial_height = self.window.height()

        # Collapse
        self.group.setChecked(False)
        self._process()
        collapsed_height = self.window.height()
        self.assertLess(
            collapsed_height,
            initial_height,
            "Window should shrink when group is collapsed",
        )

        # Expand
        self.group.setChecked(True)
        self._process()
        restored_height = self.window.height()

        drift = abs(restored_height - initial_height)
        self.assertLessEqual(
            drift,
            2,
            f"Window height drifted by {drift}px after one toggle cycle "
            f"(initial={initial_height}, restored={restored_height})",
        )

    def test_multiple_toggles_no_growth(self):
        """Verify repeated toggle cycles don't make the window grow.

        Bug: Each collapse/expand cycle could add extra pixels of space.
        Fixed: 2026-02-20
        """
        self._process()
        initial_height = self.window.height()

        for _ in range(5):
            self.group.setChecked(False)
            self._process()
            self.group.setChecked(True)
            self._process()

        final_height = self.window.height()
        drift = abs(final_height - initial_height)
        self.assertLessEqual(
            drift,
            2,
            f"Window grew by {drift}px after 5 toggle cycles "
            f"(initial={initial_height}, final={final_height})",
        )

    def test_collapsed_height_is_minimal(self):
        """Verify collapsed group doesn't take excessive vertical space.

        Fixed: 2026-02-20
        """
        self._process()

        self.group.setChecked(False)
        self._process()

        title_height = self.group.fontMetrics().height()
        actual_height = self.group.height()
        self.assertLessEqual(
            actual_height,
            title_height + 10,
            f"Collapsed group height ({actual_height}px) is too large "
            f"for title height ({title_height}px)",
        )

    def test_collapsed_sizehint_matches_maxheight(self):
        """Verify sizeHint and maxHeight use the same collapsed height.

        Bug: toggle_expand used title_height but sizeHint used title_height+5.
        Fixed: 2026-02-20
        """
        self.group.setChecked(False)
        self._process()

        hint_h = self.group.sizeHint().height()
        max_h = self.group.maximumHeight()
        diff = abs(hint_h - max_h)
        self.assertLessEqual(
            diff,
            2,
            f"sizeHint ({hint_h}) and maxHeight ({max_h}) differ by {diff}px "
            f"when collapsed — should be consistent",
        )


if __name__ == "__main__":
    unittest.main()
