# !/usr/bin/python
# coding=utf-8
"""Tests for RowTags -- per-row colour tags, a strip down a view's left edge.

Run standalone: python -m test.test_row_tags
"""

import unittest
from unittest import mock

from conftest import QtBaseTestCase, QtWait, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtTest import QTest

import pythontk as ptk
from uitk.managers.settings_manager import SettingsManager
from uitk.widgets.delegates.row_selection import RowSelectionBorderDelegate
from uitk.widgets.editors.color_editor import ColorEditorPopup
from uitk.widgets.menu import Menu
from uitk.widgets.row_tags import RowTags
from uitk.widgets.tableWidget import TableWidget
from uitk.widgets.treeWidget import TreeWidget


class _Case(QtBaseTestCase):
    """A shown tree (two parents, one with a child) and a shown table, each
    with a sandboxed palette branch, and a way to see what the strip paints."""

    def _settings(self):
        settings = SettingsManager(org="uitk", app="RowTagsTest")
        settings.clear()
        self.addCleanup(settings.clear)
        return settings

    def _tree(self):
        tree = self.track_widget(TreeWidget())
        tree.setColumnCount(2)
        a = QtWidgets.QTreeWidgetItem(tree, ["A", "x"])
        a1 = QtWidgets.QTreeWidgetItem(a, ["a1", ""])
        b = QtWidgets.QTreeWidgetItem(tree, ["B", "y"])
        tree.expandAll()
        tree.resize(240, 200)
        tree.show()
        QtWait.pump()
        tags = tree.enable_row_tags(settings=self._settings(), settings_key="tree")
        return tree, tags, (a, a1, b)

    def _table(self):
        table = self.track_widget(TableWidget())
        table.setColumnCount(2)
        table.setRowCount(3)
        for row in range(3):
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(f"r{row}"))
        table.resize(240, 200)
        table.show()
        QtWait.pump()
        tags = table.enable_row_tags(settings=self._settings(), settings_key="table")
        return table, tags

    @staticmethod
    def _rendered(overlay):
        """The strip's own paint over nothing: alpha 0 wherever it draws
        nothing (``grab()`` fills opaque, so it cannot tell)."""
        img = QtGui.QImage(overlay.size(), QtGui.QImage.Format_ARGB32)
        img.fill(QtCore.Qt.transparent)
        overlay.render(
            img, QtCore.QPoint(), QtGui.QRegion(), QtWidgets.QWidget.DrawChildren
        )
        return img

    def _strip_at(self, tags, rect):
        """The strip's colour beside the row at viewport *rect*."""
        return self._rendered(tags).pixelColor(1, rect.center().y())


class TestAttach(_Case):
    def test_attach_returns_the_one_overlay(self):
        tree, tags, _ = self._tree()
        self.assertIs(RowTags.of(tree), tags)
        self.assertIs(tree.enable_row_tags(), tags, "attach is idempotent")
        self.assertIs(tags.view, tree)

    def test_the_strip_sits_down_the_viewports_left_edge_above_it(self):
        """A sibling of the viewport, so ``viewport().scroll()`` never drags
        it along with the rows."""
        tree, tags, _ = self._tree()
        self.assertIs(tags.parent(), tree)
        viewport = tree.viewport().geometry()
        self.assertEqual(
            tags.geometry(),
            QtCore.QRect(
                viewport.x(), viewport.y(), RowTags.STRIP_WIDTH, viewport.height()
            ),
        )
        self.assertTrue(tags.testAttribute(QtCore.Qt.WA_TransparentForMouseEvents))


class TestTags(_Case):
    def test_set_and_read_a_tag(self):
        tree, tags, (a, a1, b) = self._tree()
        tags.set_tag([a, b], "tag3")
        self.assertEqual(tags.tag(a), "tag3")
        self.assertEqual(tags.tag(tree.indexFromItem(b, 1)), "tag3", "any column")
        tags.set_tag([b], None)
        self.assertIsNone(tags.tag(b))

    def test_the_users_tag_shows_over_the_automatic_one(self):
        """Clearing the user's tag shows the host's automatic one again."""
        tree, tags, (a, a1, b) = self._tree()
        tags.set_tag([a], "tag2", auto=True)
        self.assertEqual(tags.shown_tag(a), "tag2")
        tags.set_tag([a], "tag5")
        self.assertEqual(tags.shown_tag(a), "tag5")
        self.assertEqual(tags.auto_tag(a), "tag2")
        tags.set_tag([a], None)
        self.assertEqual(tags.shown_tag(a), "tag2")

    def test_a_child_shows_its_ancestors_tag_unless_it_has_its_own(self):
        tree, tags, (a, a1, b) = self._tree()
        tags.set_tag([a], "tag1")
        self.assertEqual(tags.shown_tag(a1), "tag1")
        tags.set_tag([a1], "tag4")
        self.assertEqual(tags.shown_tag(a1), "tag4")
        tags.set_tag([a1], None)
        tags.inherit = False
        self.assertIsNone(tags.shown_tag(a1))

    def test_a_tag_is_never_heard_as_an_edit(self):
        """A host treats ``itemChanged`` on column 0 as a user's edit (the
        Shot Manifest renames the step); a tag must not look like one."""
        tree, tags, (a, a1, b) = self._tree()
        heard = []
        tree.itemChanged.connect(lambda *args: heard.append(args))
        tree.model().dataChanged.connect(lambda *args: heard.append(args))
        tags.set_tag([a, b], "tag1")
        tags.set_tag([a], None)
        self.assertEqual(heard, [])

    def test_set_tag_does_not_announce_a_pick(self):
        """A host restoring its saved tags must not hear them back."""
        tree, tags, (a, a1, b) = self._tree()
        picks = []
        tags.assigned.connect(lambda *args: picks.append(args))
        tags.set_tag([a], "tag1")
        self.assertEqual(picks, [])

    def test_tagging_a_sorted_table_never_reorders_or_fills_it(self):
        """Bug: a tag was written into the model with its signals blocked. On
        a row whose column-0 cell held no item, Qt made one, and in a table
        sorted on column 0 it moved rows while the view, muted, never heard:
        the rows on screen no longer matched the model. Tags now live beside
        the model.
        Fixed: 2026-10-09"""
        table = self.track_widget(TableWidget())
        table.setColumnCount(2)
        table.setRowCount(3)
        table.setItem(0, 0, QtWidgets.QTableWidgetItem("b"))
        table.setItem(2, 0, QtWidgets.QTableWidgetItem("a"))
        for row in range(3):
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"r{row}"))
        table.setSortingEnabled(True)
        table.sortItems(0)
        order = [table.item(r, 1).text() for r in range(3)]
        empty = next(r for r in range(3) if table.item(r, 0) is None)
        tags = table.enable_row_tags(settings=self._settings(), settings_key="t")
        tags.set_tag([empty], "tag2")
        self.assertIsNone(table.item(empty, 0), "no item made for a tag")
        self.assertEqual([table.item(r, 1).text() for r in range(3)], order)
        self.assertEqual(tags.tag(empty), "tag2")

    def test_a_tag_follows_its_row_through_a_sort(self):
        table, tags = self._table()
        table.setItem(0, 0, QtWidgets.QTableWidgetItem("z"))
        tags.set_tag([0], "tag7")
        table.sortItems(0)
        row = next(r for r in range(3) if table.item(r, 0).text() == "z")
        self.assertEqual(row, 2)
        self.assertEqual(tags.tag(row), "tag7")
        self.assertIsNone(tags.tag(0))

    def test_a_removed_rows_tag_never_lands_on_its_successor(self):
        tree, tags, (a, a1, b) = self._tree()
        tags.set_tag([a], "tag1")
        tree.takeTopLevelItem(0)
        self.assertIsNone(tags.tag(b), "b slid into row 0, untagged")
        self.assertEqual(tags._user, {}, "the removed row's tag was dropped")

    def test_a_table_row_by_number_item_or_index(self):
        table, tags = self._table()
        tags.set_tag([0, table.item(1, 0), table.model().index(2, 1)], "tag6")
        self.assertEqual([tags.tag(r) for r in range(3)], ["tag6"] * 3)


class TestPaint(_Case):
    def test_a_tagged_row_paints_its_colour_and_an_untagged_one_nothing(self):
        tree, tags, (a, a1, b) = self._tree()
        tags.set_tag([b], "tag6")
        painted = self._strip_at(tags, tree.visualItemRect(b))
        self.assertEqual(painted.name().upper(), tags.color("tag6"))
        self.assertEqual(painted.alpha(), 255)
        self.assertEqual(self._strip_at(tags, tree.visualItemRect(a)).alpha(), 0)

    def test_an_inherited_colour_is_fainter(self):
        tree, tags, (a, a1, b) = self._tree()
        tags.set_tag([a], "tag1")
        child = self._strip_at(tags, tree.visualItemRect(a1))
        self.assertEqual(child.alpha(), RowTags.INHERITED_ALPHA)

    def test_recolouring_a_slot_recolours_every_row_holding_it(self):
        tree, tags, (a, a1, b) = self._tree()
        tags.set_tag([a, b], "tag2")
        tags.set_color("tag2", "#102030")
        for item in (a, b):
            painted = self._strip_at(tags, tree.visualItemRect(item))
            self.assertEqual(painted.name().upper(), "#102030")

    def test_a_table_keeps_its_strip_when_the_host_swaps_the_delegate(self):
        """Why the strip is an overlay and not a delegate: hosts routinely
        replace a table's delegate (colour-coded cells keep theirs visible
        under ``RowSelectionBorderDelegate``)."""
        table, tags = self._table()
        table.setItemDelegate(RowSelectionBorderDelegate(table))
        tags.set_tag([1], "tag4")
        rect = table.visualRect(table.model().index(1, 0))
        self.assertEqual(self._strip_at(tags, rect).name().upper(), tags.color("tag4"))
        rect0 = table.visualRect(table.model().index(0, 0))
        self.assertEqual(self._strip_at(tags, rect0).alpha(), 0)


class TestPalette(_Case):
    def test_the_default_palette_is_ptk_palette_tags(self):
        tree, tags, _ = self._tree()
        self.assertEqual(tags.slots, list(ptk.Palette.tags()))
        self.assertEqual(
            tags.colors(),
            {s: c.hex.upper() for s, c in ptk.Palette.tags().items()},
        )

    def test_a_recoloured_slot_persists_across_sessions(self):
        settings = self._settings()
        first = self.track_widget(QtWidgets.QTreeWidget())
        RowTags.attach(first, settings=settings, settings_key="k").set_color(
            "tag3", QtGui.QColor("#AABBCC")
        )
        second = self.track_widget(QtWidgets.QTreeWidget())
        reloaded = RowTags.attach(second, settings=settings, settings_key="k")
        self.assertEqual(reloaded.color("tag3"), "#AABBCC")
        reloaded.reset_colors()
        third = self.track_widget(QtWidgets.QTreeWidget())
        fresh = RowTags.attach(third, settings=settings, settings_key="k")
        self.assertEqual(fresh.color("tag3"), ptk.Palette.tags()["tag3"].hex.upper())

    def test_only_changed_slots_are_saved_and_a_corrupt_one_is_ignored(self):
        settings = self._settings()
        view = self.track_widget(QtWidgets.QTreeWidget())
        tags = RowTags.attach(view, settings=settings, settings_key="k")
        tags.set_color("tag1", "#010203")
        self.assertEqual(settings.branch("k").value("colors"), {"tag1": "#010203"})
        settings.branch("k").setValue("colors", {"tag2": "not a colour", "zz": "#FFF"})
        tags.configure(view, settings=settings, settings_key="k")
        self.assertEqual(
            tags.colors(), {s: c.hex.upper() for s, c in ptk.Palette.tags().items()}
        )

    def test_bad_slots_and_colours_raise(self):
        tree, tags, _ = self._tree()
        with self.assertRaises(KeyError):
            tags.set_color("tag99", "#FFFFFF")
        with self.assertRaises(ValueError):
            tags.set_color("tag1", "not a colour")


class TestMenu(_Case):
    def _qmenu(self, tags, rows=None, parent=None):
        menu = self.track_widget(QtWidgets.QMenu(parent))
        row = tags.add_to_menu(menu, rows)
        menu.addAction("Other")
        menu.popup(QtCore.QPoint(100, 100))
        QtWait.pump()
        return menu, row

    def test_the_row_holds_the_clear_swatch_then_every_slot(self):
        tree, tags, (a, a1, b) = self._tree()
        menu, row = self._qmenu(tags, [a])
        self.assertEqual([s.slot for s in row.swatches], [None, *tags.slots])

    def test_a_click_tags_every_target_announces_it_and_closes_the_menu(self):
        tree, tags, (a, a1, b) = self._tree()
        picks = []
        tags.assigned.connect(lambda rows, slot: picks.append((rows, slot)))
        menu, row = self._qmenu(tags, [a, b])
        QTest.mouseClick(row.swatches[3], QtCore.Qt.LeftButton)
        QtWait.pump()
        self.assertEqual((tags.tag(a), tags.tag(b)), ("tag3", "tag3"))
        self.assertEqual(len(picks), 1)
        rows, slot = picks[0]
        self.assertEqual(slot, "tag3")
        self.assertEqual(
            [tree.itemFromIndex(i) for i in rows], [a, b], "column-0 indexes"
        )
        self.assertFalse(menu.isVisible())

    def test_the_clear_swatch_clears_and_announces_none(self):
        tree, tags, (a, a1, b) = self._tree()
        tags.set_tag([a], "tag1")
        picks = []
        tags.assigned.connect(lambda rows, slot: picks.append(slot))
        menu, row = self._qmenu(tags, [a])
        QTest.mouseClick(row.swatches[0], QtCore.Qt.LeftButton)
        self.assertIsNone(tags.tag(a))
        self.assertEqual(picks, [None])

    def test_no_rows_means_the_selection_at_the_moment_of_the_pick(self):
        """What a menu built once and kept wants: the row is made before
        anything is selected, the pick acts on what is selected then."""
        tree, tags, (a, a1, b) = self._tree()
        menu, row = self._qmenu(tags)
        b.setSelected(True)
        QTest.mouseClick(row.swatches[2], QtCore.Qt.LeftButton)
        self.assertEqual((tags.tag(a), tags.tag(b)), (None, "tag2"))

    def test_the_slot_every_target_shares_is_ringed(self):
        tree, tags, (a, a1, b) = self._tree()
        tags.set_tag([a, b], "tag5")
        menu, row = self._qmenu(tags, [a, b])
        self.assertEqual([s.slot for s in row.swatches if s.current], ["tag5"])
        tags.set_tag([b], "tag1")
        row.refresh()
        self.assertEqual([s.slot for s in row.swatches if s.current], [])

    def test_a_right_click_edits_that_slots_colour_after_the_menu_closes(self):
        tree, tags, (a, a1, b) = self._tree()
        seen = {}

        def pick(initial=None, parent=None, title="", pos=None, **_kwargs):
            seen["menu_open"] = menu.isVisible()
            seen["pos"] = pos
            return QtGui.QColor("#405060")

        menu, row = self._qmenu(tags, [a])
        with mock.patch.object(ColorEditorPopup, "get_color", new=pick):
            QTest.mouseClick(row.swatches[4], QtCore.Qt.RightButton)
            QtWait.until(lambda: "pos" in seen, "the colour popup never opened")
        self.assertFalse(seen["menu_open"], "the popup opens once the menu is gone")
        self.assertIsNotNone(seen["pos"])
        self.assertEqual(tags.color("tag4"), "#405060")
        self.assertIsNone(tags.tag(a), "an edit tags nothing")

    def test_a_uitk_menu_that_hides_on_triggers_hides_on_a_pick(self):
        """A pick is a trigger like any item's: the menu's own
        ``hide_on_trigger`` decides."""
        tree, tags, (a, a1, b) = self._tree()
        menu = self.track_widget(Menu(hide_on_trigger=True))
        row = tags.add_to_menu(menu, [a])
        menu.show()
        QtWait.pump()
        QTest.mouseClick(row.swatches[1], QtCore.Qt.LeftButton)
        QtWait.until(lambda: not menu.isVisible(), "the menu stayed up")
        self.assertEqual(tags.tag(a), "tag1")


if __name__ == "__main__":
    unittest.main()
