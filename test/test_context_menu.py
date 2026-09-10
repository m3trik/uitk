# !/usr/bin/python
# coding=utf-8
"""Tests for ``uitk.widgets.context_menu`` (ContextMenu / MenuRow).

Pins the contract the shot sequencer's shot menu is built on: rows are
actions, categories, or both; an action row hides the menu BEFORE it runs;
a category row never dismisses; sub-rows live in the parent row's flyout;
``exec_`` blocks until dismissal and then disposes; a row can carry an
option box without falling out of the list's bookkeeping.
"""

import unittest

from conftest import QtBaseTestCase, QtWait, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtCore, QtGui

from uitk.widgets.context_menu import ContextMenu, MenuRow
from uitk.widgets.separator import Separator
from uitk.themes.style_sheet import StyleSheet


class _Host(QtWidgets.QWidget):
    """A shown parent, so the menu has a window to belong to."""


class TestContextMenuRows(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.host = self.track_widget(_Host())
        self.host.resize(300, 200)
        self.host.show()
        self.menu = ContextMenu(parent=self.host)
        self.addCleanup(self.menu.dispose)

    def test_a_label_becomes_a_menu_row(self):
        row = self.menu.add("Trim Empty Space")
        self.assertIsInstance(row, MenuRow)
        self.assertEqual(row.text(), "Trim Empty Space")
        self.assertIn(row, self.menu.list.get_items())
        self.assertFalse(row.property("contextAction"), "no callback: not an action")

    def test_a_callback_row_is_an_action(self):
        row = self.menu.add("Refresh", callback=lambda: None)
        self.assertTrue(row.property("contextAction"))

    def test_sub_rows_go_into_the_parents_flyout(self):
        trim = self.menu.add("Trim Empty Space", callback=lambda: None)
        self.assertFalse(trim.has_flyout)
        lead = self.menu.add("Trim Leading Space", parent=trim, callback=lambda: None)
        self.assertIn(lead, trim.sublist.get_items())
        self.assertNotIn(lead, self.menu.list._row_widgets(), "not a root row")
        self.assertTrue(trim.has_flyout)
        self.assertIn(lead, self.menu.list.get_items(), "get_items recurses")

    def test_a_registered_widget_name_makes_that_widget(self):
        row = self.menu.add("CheckBox", setText="Show Gaps", setChecked=True)
        self.assertIsInstance(row, QtWidgets.QCheckBox)
        self.assertTrue(row.isChecked())

    def test_add_separator_is_not_an_action(self):
        sep = self.menu.add_separator("Display")
        self.assertIsInstance(sep, Separator)
        self.assertEqual(sep.title, "Display")
        self.assertFalse(sep.property("contextAction"))

    def test_rejects_non_widget_input(self):
        with self.assertRaises(TypeError):
            self.menu.add(42)

    def test_has_flyout_reads_only_its_own_level(self):
        """It is asked on every paint and sizeHint, so it must not walk the
        whole tree the way ``get_items()`` does."""
        row = self.menu.add("Keys")
        self.assertFalse(row.has_flyout)
        sub = self.menu.add("Snap", parent=row, callback=lambda: None)
        self.assertTrue(row.has_flyout)
        self.assertFalse(sub.has_flyout, "a leaf owns an EMPTY flyout")
        self.menu.add("Nested", parent=sub, callback=lambda: None)
        self.assertTrue(sub.has_flyout)

    def test_add_entries_renders_a_widgets_own_context_entries(self):
        state = {"gaps": True}
        entries = [
            {
                "label": "Add Marker\u2026",
                "callback": lambda: state.update(marked=True),
                "checkable": False,
                "checked": False,
            },
            None,
            {
                "label": "Show Gaps",
                "callback": lambda checked: state.update(gaps=checked),
                "checkable": True,
                "checked": True,
            },
        ]
        host_row = self.menu.add("Timeline")
        rows = self.menu.add_entries(entries, parent=host_row)
        self.assertEqual(len(rows), 3)
        self.assertIsInstance(rows[0], MenuRow)
        self.assertIsInstance(rows[1], Separator)
        self.assertIsInstance(rows[2], QtWidgets.QCheckBox)
        self.assertTrue(rows[2].isChecked())
        self.assertEqual(
            host_row.sublist._row_widgets(), rows, "in entry order, separator included"
        )
        rows[0].click()
        self.assertTrue(state["marked"])
        rows[2].click()
        self.assertFalse(state["gaps"], "a checkable entry gets the NEW state")

    def test_a_splitter_host_does_not_adopt_the_menu_as_a_pane(self):
        """A QSplitter takes any plain child widget as a pane, and the menu
        is a plain child until it is shown as a popup -- so it is parented
        to the host's window instead (the sequencer widget IS a splitter)."""
        splitter = QtWidgets.QSplitter(self.host)
        splitter.addWidget(QtWidgets.QLabel("pane", splitter))
        menu = ContextMenu(parent=splitter)
        self.addCleanup(menu.dispose)
        self.assertEqual(splitter.count(), 1)
        self.assertIs(menu.parent(), self.host.window())


class TestContextMenuActivation(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.host = self.track_widget(_Host())
        self.host.resize(300, 200)
        self.host.show()
        self.menu = ContextMenu(parent=self.host)
        self.addCleanup(self.menu.dispose)
        self.calls = []

    def _show(self):
        self.menu.popup(self.host.mapToGlobal(QtCore.QPoint(20, 20)))
        QtWait.until(lambda: self.menu.isVisible(), "menu never showed")

    def test_an_action_row_hides_the_menu_then_runs(self):
        seen = []
        row = self.menu.add("Run", callback=lambda: seen.append(self.menu.isVisible()))
        self._show()
        self.menu.list.on_item_interacted.emit(row)
        self.assertEqual(seen, [False], "hidden BEFORE the callback ran")
        self.assertFalse(self.menu.isVisible())

    def test_a_category_row_does_not_dismiss(self):
        cat = self.menu.add("Keys")
        self.menu.add("Snap Keys", parent=cat, callback=lambda: self.calls.append(1))
        self._show()
        self.menu.list.on_item_interacted.emit(cat)
        self.assertTrue(self.menu.isVisible(), "navigation only")
        self.assertEqual(self.calls, [])

    def test_an_action_row_with_a_flyout_runs_its_own_action(self):
        trim = self.menu.add("Trim", callback=lambda: self.calls.append("both"))
        self.menu.add(
            "Trim Head", parent=trim, callback=lambda: self.calls.append("head")
        )
        self._show()
        self.menu.list.on_item_interacted.emit(trim)
        self.assertEqual(self.calls, ["both"])
        self.assertFalse(self.menu.isVisible())

    def test_a_sub_row_runs_and_dismisses(self):
        trim = self.menu.add("Trim", callback=lambda: self.calls.append("both"))
        head = self.menu.add(
            "Trim Head", parent=trim, callback=lambda: self.calls.append("head")
        )
        self._show()
        self.menu.list.on_item_interacted.emit(head)
        self.assertEqual(self.calls, ["head"])
        self.assertFalse(self.menu.isVisible())

    def test_a_checkable_row_reports_its_new_state(self):
        row = self.menu.add(
            "CheckBox",
            setText="Show Gaps",
            setChecked=True,
            toggled=lambda checked: self.calls.append(checked),
        )
        self._show()
        self.menu.list.on_item_interacted.emit(row)
        self.assertEqual(self.calls, [False], "click() toggled it off")
        self.assertFalse(row.isChecked())

    def test_escape_hides(self):
        self.menu.add("Run", callback=lambda: None)
        self._show()
        QtWidgets.QApplication.sendEvent(self.menu, _key_press(QtCore.Qt.Key_Escape))
        self.assertFalse(self.menu.isVisible())


def _key_press(key):
    from qtpy import QtGui

    return QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, QtCore.Qt.NoModifier)


class TestContextMenuExec(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.host = self.track_widget(_Host())
        self.host.resize(300, 200)
        self.host.show()

    def test_exec_returns_after_an_action_and_disposes(self):
        menu = ContextMenu(parent=self.host)
        calls = []
        row = menu.add("Run", callback=lambda: calls.append(1))
        QtCore.QTimer.singleShot(50, lambda: menu.list.on_item_interacted.emit(row))
        menu.exec_(self.host.mapToGlobal(QtCore.QPoint(10, 10)))
        self.assertEqual(calls, [1])
        self.assertTrue(menu._disposed)
        QtWait.pump()

    def test_exec_returns_when_dismissed_without_a_choice(self):
        menu = ContextMenu(parent=self.host)
        menu.add("Run", callback=lambda: None)
        QtCore.QTimer.singleShot(50, menu.hide)
        menu.exec_(self.host.mapToGlobal(QtCore.QPoint(10, 10)), dispose=False)
        self.assertFalse(menu.isVisible())
        self.assertFalse(menu._disposed)
        menu.dispose()
        QtWait.pump()


class TestContextMenuOptionBoxRow(QtBaseTestCase):
    """A row wearing an option box is wrapped in a container inside the
    list's layout; the list must keep seeing the ROW as its item."""

    def setUp(self):
        super().setUp()
        self.host = self.track_widget(_Host())
        self.host.resize(300, 200)
        self.host.show()
        self.menu = ContextMenu(parent=self.host)
        self.addCleanup(self.menu.dispose)

    def test_a_wrapped_row_is_still_an_item(self):
        row = self.menu.add("Extend to Keys", callback=lambda: None)
        sub = self.menu.add("Extend Head", parent=row, callback=lambda: None)
        row.option_box.enable_option_menu(items=[("Max distance", lambda: None)])
        container = row.option_box.container  # forces the wrap
        self.assertIsNotNone(container)
        self.assertIs(row.parent(), container)
        items = self.menu.list.get_items()
        self.assertIn(row, items, "seen through the wrap")
        self.assertIn(sub, items, "its flyout is still reached")
        self.assertNotIn(container, items)
        self.assertIn(row, self.menu.list._row_widgets())

    def test_clear_tears_down_a_wrapped_rows_flyout(self):
        row = self.menu.add("Extend to Keys", callback=lambda: None)
        self.menu.add("Extend Head", parent=row, callback=lambda: None)
        row.option_box.enable_option_menu(items=[("Max distance", lambda: None)])
        row.option_box.container
        sub = row.sublist
        self.menu.list.clear()
        self.assertEqual(self.menu.list.get_items(), [])
        self.assertIsNone(sub.parent(), "detached from the window with its row")
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        with self.assertRaises(RuntimeError):
            sub.objectName()  # deleted with its row


class TestMenuRowOptionMenu(QtBaseTestCase):
    """A row's settings box is laid OVER the row, inside the arrow.

    Appended beside the row (the option-box container) it landed exactly
    where the row's flyout opens, so on a row that both acts and expands the
    box was under the flyout and could not be clicked at all.
    """

    def setUp(self):
        super().setUp()
        self.host = self.track_widget(_Host())
        self.host.resize(300, 200)
        self.host.show()
        self.menu = ContextMenu(parent=self.host)
        self.addCleanup(self.menu.dispose)

    def test_the_button_is_a_child_of_the_row_not_a_sibling(self):
        row = self.menu.add("Extend to Keys", callback=lambda: None)
        menu = row.add_option_menu()
        self.assertIsNotNone(menu)
        self.assertIs(row.option_menu, menu)
        self.assertIs(row._option_button.parent(), row)
        self.assertIn(row, self.menu.list._row_widgets(), "no container in the way")

    def test_the_button_sits_left_of_the_arrow(self):
        row = self.menu.add("Extend to Keys", callback=lambda: None)
        self.menu.add("Extend Head", parent=row, callback=lambda: None)
        row.add_option_menu()
        row.resize(200, 20)
        row.setAttribute(QtCore.Qt.WA_WState_Hidden, False)
        arrow_left = row.width() - row._ARROW_INSET - row._arrow_width()
        self.assertGreater(row._arrow_width(), 0, "the row owns a flyout")
        self.assertLessEqual(
            row._option_button.geometry().right(), arrow_left, "inside the arrow"
        )
        self.assertGreaterEqual(row._option_button.geometry().left(), 0)

    def test_the_button_makes_room_when_a_flyout_appears_later(self):
        """The arrow slot only exists once the flyout has a row in it, which
        is usually AFTER the option menu was attached."""

        def _inset(r):
            # Measured from the RIGHT EDGE: the list re-lays its rows out as
            # they are added, so an absolute x says nothing.
            return r.width() - 1 - r._option_button.geometry().right()

        row = self.menu.add("Extend", callback=lambda: None)
        row.add_option_menu()
        self.assertEqual(row._arrow_width(), 0, "no flyout yet")
        before = _inset(row)
        self.menu.add("Extend Head", parent=row, callback=lambda: None)
        self.assertGreater(row._arrow_width(), 0)
        self.assertEqual(
            _inset(row) - before,
            row._arrow_width() + row._OPTION_GAP,
            "the button stepped aside by exactly the arrow's slot",
        )

    def test_the_row_reserves_width_for_the_button(self):
        plain = self.menu.add("Trim", callback=lambda: None)
        boxed = self.menu.add("Extend", callback=lambda: None)
        before = boxed.sizeHint().width()
        boxed.add_option_menu()
        self.assertGreater(boxed.sizeHint().width(), before)
        self.assertIsNone(plain._option_button, "untouched")


class TestRowCallbackArity(QtBaseTestCase):
    """``callback`` runs with NO arguments, whatever the button emits.

    A row captures its subject in a default -- ``lambda e=edge: ...`` is how
    every menu in the tree is written -- and `QAbstractButton.clicked`
    carries `checked`, which PySide hands to any slot that will take an
    argument. It landed in exactly that default, so a Trim Leading row
    trimmed edge ``False`` and a Merge row reached for ``False.shot_id``.
    """

    def setUp(self):
        super().setUp()
        self.host = self.track_widget(_Host())
        self.host.resize(300, 200)
        self.host.show()
        self.menu = ContextMenu(parent=self.host)
        self.addCleanup(self.menu.dispose)

    def _click(self, row):
        row.click()
        QtWidgets.QApplication.processEvents()

    def test_a_captured_default_survives_the_click(self):
        seen = []
        for edge in ("leading", "trailing"):
            self.menu.add(edge, callback=lambda e=edge: seen.append(e))
        for row in [w for w in self.menu.list._row_widgets() if hasattr(w, "text")]:
            self._click(row)
        self.assertEqual(seen, ["leading", "trailing"])

    def test_a_zero_argument_callback_still_runs(self):
        ran = []
        row = self.menu.add("Refresh", callback=lambda: ran.append(True))
        self._click(row)
        self.assertEqual(ran, [True])

    def test_a_falsy_default_is_not_mistaken_for_the_checked_bool(self):
        """0 and False are the values the bug was indistinguishable from."""
        seen = []
        row = self.menu.add("zero", callback=lambda p=0: seen.append(p))
        self._click(row)
        self.assertEqual(seen, [0])

    def test_clicked_still_receives_the_state_for_a_caller_that_wants_it(self):
        """``clicked=`` is the raw signal; only ``callback=`` drops the bool."""
        seen = []
        row = self.menu.add("raw", clicked=lambda checked: seen.append(checked))
        self._click(row)
        self.assertEqual(seen, [False], "the button's own checked state")

    def test_a_checkable_entry_still_gets_its_new_state(self):
        """``add_entries`` routes checkable rows through ``toggled``."""
        seen = []
        rows = self.menu.add_entries(
            [
                {
                    "label": "Show Gaps",
                    "callback": lambda checked: seen.append(checked),
                    "checkable": True,
                    "checked": False,
                }
            ]
        )
        rows[0].setChecked(True)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(seen, [True])


class TestContextMenuSurface(QtBaseTestCase):
    """The flyouts paint the same ground as the menu they fan out of."""

    def setUp(self):
        super().setUp()
        self.host = self.track_widget(_Host())
        self.host.resize(300, 200)
        # The rules under test live in the theme, so it has to be applied:
        # without it every assertion here would pass on an unstyled widget.
        StyleSheet().set(self.host, theme="dark")
        self.host.show()
        self.menu = ContextMenu(parent=self.host)
        self.addCleanup(self.menu.dispose)

    def test_the_root_list_is_a_menu_surface(self):
        self.assertTrue(self.menu.list.menu_surface)
        self.assertTrue(self.menu.list.property("menuSurface"))
        self.assertTrue(
            self.menu.list.testAttribute(QtCore.Qt.WA_StyledBackground),
            "a plain QWidget honours background-color only with this set",
        )

    def test_a_flyout_inherits_the_surface(self):
        row = self.menu.add("Trim", callback=lambda: None)
        self.menu.add("Trim Leading", parent=row, callback=lambda: None)
        sub = row.sublist
        self.assertTrue(sub.menu_surface, "the flyout is its own top-level window")
        self.assertTrue(sub.property("menuSurface"))
        self.assertTrue(sub.testAttribute(QtCore.Qt.WA_StyledBackground))

    def _opaque_fill(self, widget):
        """``(ground, leaked)`` for *widget* rendered over magenta.

        Anything still magenta was never painted, so a flyout that shows the
        desktop through fails on ``leaked`` rather than on a colour anyone
        has to eyeball.  The ground is the most common colour rather than the
        centre pixel: a one-row flyout is mostly text through the middle.
        """
        magenta = QtGui.QColor(255, 0, 255)
        img = QtGui.QImage(widget.size(), QtGui.QImage.Format_ARGB32)
        img.fill(magenta)
        widget.render(img, QtCore.QPoint(), QtGui.QRegion(widget.rect()))
        tally = {}
        leaked = 0
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                if c == magenta:
                    leaked += 1
                tally[c.rgba()] = tally.get(c.rgba(), 0) + 1
        return QtGui.QColor.fromRgba(max(tally, key=tally.get)), leaked

    def test_the_menu_ground_is_opaque_not_the_translucent_window_fill(self):
        """WINDOW_BACKGROUND composites over a window BODY; a menu has none.

        A popup composites over the desktop, so the theme's rgba(...,125)
        window fill reads as see-through there.  MENU_BACKGROUND is opaque
        for that reason, and the dark theme's value is the #333 the QMenus
        this replaced hardcode.
        """
        self.menu.add("Trim", callback=lambda: None)
        self.menu.show()
        QtWidgets.QApplication.processEvents()
        colour, leaked = self._opaque_fill(self.menu.list)
        self.assertEqual(leaked, 0, "the menu ground let the backdrop through")
        self.assertEqual(colour.alpha(), 255, "a menu ground must be opaque")
        self.assertEqual(
            (colour.red(), colour.green(), colour.blue()),
            (51, 51, 51),
            "the dark theme's MENU_BACKGROUND is #333",
        )

    def test_a_promoted_flyout_paints_the_same_opaque_ground(self):
        """A flyout is its own Tool window, so it inherits no background.

        Promoting it used to also set WA_TranslucentBackground, which is what
        made a fanned-out list read as fully transparent.
        """
        row = self.menu.add("Trim", callback=lambda: None)
        self.menu.add("Trim Leading", parent=row, callback=lambda: None)
        sub = row.sublist
        self.menu.list._ensure_popup_flags(sub)
        self.assertFalse(
            sub.testAttribute(QtCore.Qt.WA_TranslucentBackground),
            "translucency is what let the desktop through",
        )
        sub.show()
        QtWidgets.QApplication.processEvents()
        colour, leaked = self._opaque_fill(sub)
        self.assertEqual(leaked, 0, "the flyout let the backdrop through")
        self.assertEqual(colour.alpha(), 255)
        root, _ = self._opaque_fill(self.menu.list)
        self.assertEqual(
            colour.name(), root.name(), "one surface, whatever level it is drawn at"
        )

    def test_the_surface_reaches_a_nested_flyout(self):
        row = self.menu.add("Keys", callback=lambda: None)
        deep = self.menu.add("Tangents", parent=row)
        self.menu.add("Auto", parent=deep, callback=lambda: None)
        self.assertTrue(deep.sublist.menu_surface)


if __name__ == "__main__":
    unittest.main()
