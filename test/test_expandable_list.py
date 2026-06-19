# !/usr/bin/python
# coding=utf-8
"""Tests for ExpandableList widget.

Covers stylesheet propagation to reparented sublists, sublist positioning
before show, and _logical_ancestor integration for marking menu hit-testing.
"""
import sys
from pathlib import Path

# Add package root to path
PACKAGE_ROOT = Path(__file__).parent.parent.absolute()
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from conftest import QtBaseTestCase
from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.expandableList import ExpandableList


class TestExpandableList(QtBaseTestCase):
    """Tests for ExpandableList core behavior."""

    def setUp(self):
        super().setUp()
        self.window = QtWidgets.QMainWindow()
        self.track_widget(self.window)

    def test_sublist_inherits_stylesheet(self):
        """Verify sublists inherit stylesheet when reparented to window.

        Bug: Sublists parented to self.window() didn't inherit the UI's
        stylesheet, causing items to appear transparent/unstyled.
        Fixed: 2026-03-11
        """
        # Apply a stylesheet to the window (simulates what _init_ui does)
        test_qss = "QPushButton { background-color: rgb(50, 50, 50); }"
        self.window.setStyleSheet(test_qss)

        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        w1 = lw.add("Button 1")

        # The sublist is parented to self.window(), not to lw directly
        sublist = w1.sublist
        self.assertIsNotNone(sublist)

        # Sublist should have the stylesheet even though it's reparented
        sublist_ss = sublist.styleSheet()
        self.assertTrue(
            len(sublist_ss) > 0,
            "Sublist should have an inherited stylesheet applied",
        )
        self.assertIn("background-color", sublist_ss)

    def test_nested_sublist_inherits_stylesheet(self):
        """Verify deeply nested sublists also get stylesheet propagation."""
        test_qss = "QLabel { background-color: rgb(40, 40, 40); }"
        self.window.setStyleSheet(test_qss)

        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        w1 = lw.add("Item 1")
        w2 = w1.sublist.add("Sub Item")
        w3 = w2.sublist.add("Deep Item")

        # Each level of sublist should have a stylesheet
        self.assertTrue(len(w1.sublist.styleSheet()) > 0)
        self.assertTrue(len(w2.sublist.styleSheet()) > 0)

    def test_logical_ancestor_set_on_sublist(self):
        """Verify _logical_ancestor is set so MarkingMenu can detect sublist items.

        Bug: MarkingMenu.mouseReleaseEvent couldn't recognize sublist items
        as belonging to the current UI, causing mouse grab to persist.
        Fixed: 2026-03-11
        """
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        w1 = lw.add("Button 1")

        sublist = w1.sublist
        self.assertTrue(
            hasattr(sublist, "_logical_ancestor"),
            "Sublist should have _logical_ancestor attribute set",
        )
        self.assertIs(
            sublist._logical_ancestor,
            lw,
            "_logical_ancestor should point to the root ExpandableList",
        )

    def test_nested_logical_ancestor_points_to_root(self):
        """Verify nested sublists' _logical_ancestor always points to root list."""
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        w1 = lw.add("Item 1")
        w2 = w1.sublist.add("Sub Item")

        # Both levels should point back to the root (lw)
        self.assertIs(w1.sublist._logical_ancestor, lw)
        self.assertIs(w2.sublist._logical_ancestor, lw)

    def test_sublist_positioned_before_show(self):
        """Verify sublists are moved to correct position before becoming visible.

        Bug: show() was called before move(), causing a flash at position (0,0).
        Fixed: 2026-03-11
        """
        self.window.resize(400, 300)
        self.window.show()

        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.move(100, 100)
        lw.show()

        w1 = lw.add("QPushButton", setText="Button 1")
        sub_item = w1.sublist.add("Sub Label")

        # Trigger the enter event on w1 to show the sublist
        lw._handle_widget_enter_event(w1)

        # After the handler, the sublist should be visible and NOT at (0, 0)
        self.assertTrue(w1.sublist.isVisible())
        sublist_pos = w1.sublist.pos()
        # The sublist shouldn't be at the parent widget's origin
        self.assertFalse(
            sublist_pos.x() == 0 and sublist_pos.y() == 0,
            f"Sublist should be positioned away from origin, got {sublist_pos}",
        )

    def test_sublist_has_correct_size_before_show(self):
        """Verify sublist has correct dimensions when shown."""
        lw = ExpandableList(self.window, fixed_item_height=25)
        self.track_widget(lw)
        w1 = lw.add("QPushButton", setText="Parent")
        w1.sublist.add(["Child A", "Child B", "Child C"])

        # Before showing, sublist should have non-zero size from sizeHint
        size = w1.sublist.sizeHint()
        self.assertGreater(size.width(), 0, "Sublist width should be > 0")
        self.assertGreater(size.height(), 0, "Sublist height should be > 0")

    def test_force_hide_collapses_sublist_shown_under_hidden_ancestor(self):
        """A sublist open at hide-time must reopen collapsed.

        Bug: sublists are reparented to the window, so when an ancestor is
        hidden they get a spontaneous hide (``isVisible()`` → False) but keep
        their explicit-visible flag. ``_force_hide_all``'s old ``isVisible()``
        guard then skipped them, the flag survived, and Qt's ``showChildren``
        restored them on the next show — the list "reshown in the previously
        open state". The collapse must clear the flag unconditionally.

        Reproduced deterministically by showing a sublist while its window is
        not visible: ``isVisible()`` is False yet ``isHidden()`` is False (the
        exact mid-hide condition). The fix asserts ``isHidden()`` afterward —
        the flag ``showChildren`` actually consults — not an OS-dependent
        visibility outcome.
        """
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        w1 = lw.add("Parent")
        w1.sublist.add("Child")  # non-empty so it is a real, showable sublist

        # Window is not shown → ancestor not visible. Explicitly show the
        # sublist: not visible (ancestor hidden) but not explicitly hidden.
        w1.sublist.show()
        self.assertFalse(w1.sublist.isVisible())
        self.assertFalse(w1.sublist.isHidden())

        # Hiding the list (what hideEvent does) must collapse it unconditionally.
        lw._force_hide_all()
        self.assertTrue(
            w1.sublist.isHidden(),
            "sublist must be explicitly hidden so a later show won't restore it",
        )

    def test_root_list_attribute(self):
        """Verify root_list always points to the topmost ExpandableList."""
        lw = ExpandableList(self.window)
        self.track_widget(lw)
        w1 = lw.add("A")
        w2 = w1.sublist.add("B")
        w3 = w2.sublist.add("C")

        self.assertIs(w1.sublist.root_list, lw)
        self.assertIs(w2.sublist.root_list, lw)
        self.assertIs(w3.sublist.root_list, lw)

    def test_explicit_hide_collapses_open_sublists(self):
        """Calling hide() on a list must tear down its open sublists.

        Bug: hide() used to early-return while any sublist was visible. Since
        sublists are reparented to the window (not Qt children of the list),
        an explicit dismiss then closed *nothing* — neither the list nor the
        sublist. hide() now force-collapses the hierarchy, then hides.
        """
        lw = ExpandableList(fixed_item_height=21)  # top-level: sublists parent to lw
        self.track_widget(lw)
        w1 = lw.add("Parent")
        c1 = w1.sublist.add("Child")
        c1.sublist.add("Grandchild")
        lw.show()
        lw._handle_widget_enter_event(w1)
        w1.sublist._handle_widget_enter_event(c1)
        self.assertTrue(w1.sublist.isVisible())
        self.assertTrue(c1.sublist.isVisible())

        lw.hide()

        self.assertFalse(lw.isVisible(), "the list itself must hide")
        self.assertTrue(w1.sublist.isHidden(), "sublist must collapse on hide")
        self.assertTrue(c1.sublist.isHidden(), "nested sublist must collapse on hide")

    def test_sublist_stays_collapsed_after_window_reshow(self):
        """A sublist open at hide-time must not reopen on the next show.

        Bug: after ``_force_hide_all`` correctly collapses sublists on hide,
        Qt delivers a synthetic ``Enter`` to the item under the stationary
        cursor when the window reappears. That Enter ran the normal
        hover-to-expand path, silently reopening the previously-expanded
        sublist — the list "reshown in its previously open state".
        Fixed: gate the Enter-driven open behind a show-time latch that
        clears only once the cursor actually moves.
        """
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.show()
        w1 = lw.add("Parent")
        w1.sublist.add("Child")  # non-empty so it is a real, showable sublist

        # Open the sublist (direct call mirrors a genuine hover).
        lw._handle_widget_enter_event(w1)
        self.assertTrue(w1.sublist.isVisible())

        # Window hides — hideEvent/_force_hide_all collapse the sublist.
        self.window.hide()
        self.assertTrue(w1.sublist.isHidden())

        # Reshow re-arms the latch (showEvent records the cursor position).
        self.window.show()
        self.assertIsNotNone(
            lw._suppress_open_pos, "showEvent must arm the auto-open latch on reshow"
        )

        # Pin the latch to the current cursor so the "stationary cursor"
        # condition is deterministic — the suite runs under the native QPA
        # locally (real, moving pointer) and offscreen only in CI.
        lw._suppress_open_pos = QtGui.QCursor.pos()

        # The synthetic Enter Qt fires at the unchanged cursor position must
        # NOT reopen the sublist.
        QtWidgets.QApplication.sendEvent(w1, QtCore.QEvent(QtCore.QEvent.Enter))
        self.assertFalse(
            w1.sublist.isVisible(),
            "sublist must stay collapsed on reshow until the cursor moves",
        )

    def test_auto_open_resumes_after_cursor_moves(self):
        """Once the cursor moves off the show position, hover-to-expand resumes.

        Guards against the reshow latch over-suppressing: a genuine Enter at a
        position different from the recorded show position must open the
        sublist and clear the latch.
        """
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.show()
        w1 = lw.add("Parent")
        w1.sublist.add("Child")

        # Latch armed at a position the cursor is no longer at (it has moved).
        lw._suppress_open_pos = QtCore.QPoint(-9999, -9999)
        QtWidgets.QApplication.sendEvent(w1, QtCore.QEvent(QtCore.QEvent.Enter))

        self.assertTrue(
            w1.sublist.isVisible(), "sublist should open on a genuine hover Enter"
        )
        self.assertIsNone(
            lw._suppress_open_pos, "latch should clear once the cursor has moved"
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
