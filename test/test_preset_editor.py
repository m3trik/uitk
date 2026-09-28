# !/usr/bin/python
# coding=utf-8
"""Tests for PresetEditor — every tool's presets in one window.

Each test gets its own presets root under ``test/temp_tests/`` (set as
``UITK_PRESETS_ROOT``) seeded with stores the way the tools write them, and drives
the window through its real widgets: tree selection, the filter field and its
facet buttons, the collections box and its menu, table cells (including a click
on a Collection cell), the row menu, the header menu's buttons, the New / Edit
collection form, the import review page.
"""

import json
import os
import shutil
import sys
import time
import uuid
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from conftest import QtBaseTestCase, QtWait, setup_qt_application

app = setup_qt_application()

import pythontk as ptk  # noqa: E402
from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402
from qtpy.QtTest import QTest  # noqa: E402
from uitk.managers.icon_manager import IconManager  # noqa: E402
from uitk.managers.preset_manager import PresetManager  # noqa: E402
from uitk.managers.settings_manager import SettingsManager  # noqa: E402
from uitk.widgets.context_menu import ContextMenu  # noqa: E402
from uitk.widgets.formPanel import FormPanel  # noqa: E402
from uitk.widgets.editors.preset_editor import PresetEditor  # noqa: E402
from uitk.widgets.optionBox.options.choice import ChoiceOption  # noqa: E402

TEMP_ROOT = Path(__file__).parent / "temp_tests"


class _EditorCase(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        # Unique per run: a folder a sync client kept from being deleted, or a
        # concurrent run of the same test (routine with several sessions), must
        # never be this run's root -- both surfaced as FileExistsError here.
        run = uuid.uuid4().hex[:6]
        self.root = TEMP_ROOT / f"preset_editor_{self._testMethodName}_{run}"
        self.other = Path(str(self.root) + "_other")
        for d in (self.root, self.other):
            d.mkdir(parents=True)
            self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        patcher = mock.patch.dict(os.environ, {"UITK_PRESETS_ROOT": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        # The filter row persists; every test starts from an unfiltered window.
        settings = SettingsManager(namespace="preset_editor")
        settings.clear()
        self.addCleanup(settings.clear)

        exporter = ptk.PresetStore("scene_exporter", "mayatk")
        exporter.save("Unity", {"_meta": {"version": 1}, "a": 1})
        exporter.save("WebXR", {"_meta": {"version": 1}, "a": 2})
        ptk.PresetStore("fbx_presets", "blendertk").save("Game (FBX)", {"axis": "Y"})

        self.editor = self.make_editor()

    def make_editor(self, library=None, **kwargs):
        editor = PresetEditor(library=library, **kwargs)
        self.addCleanup(editor.deleteLater)
        return editor

    # --- acting helpers -------------------------------------------------
    def rows(self, editor=None):
        editor = editor or self.editor
        table = editor._table
        return [
            table.item(r, PresetEditor.COL_NAME).text() for r in range(table.rowCount())
        ]

    def row_of(self, name, editor=None):
        return self.rows(editor).index(name)

    def cell(self, name, col, editor=None):
        editor = editor or self.editor
        return editor._table.item(self.row_of(name, editor), col)

    def select(self, *names):
        self.editor.select_entries(
            [ptk.PresetStore.sanitize_preset_name(n) for n in names]
        )

    def menu_rows(self, menu, parent=None):
        """``{text: row}`` of a ContextMenu level (the root, or *parent*'s flyout)."""
        self.addCleanup(menu.dispose)
        level = menu.list if parent is None else parent.sublist
        return {
            w.text(): w
            for w in level._row_widgets()
            if isinstance(w, QtWidgets.QAbstractButton)
        }

    def click(self, menu, *path):
        """Click the row at *path* (``"Move to", "Studio"`` walks a flyout)."""
        parent = None
        for label in path:
            row = self.menu_rows(menu, parent)[label]
            parent = row
        self.assertTrue(row.isEnabled(), f"{path[-1]!r} is disabled")
        row.click()

    def trigger(self, label):
        """Click row-menu entry *label* for the selection."""
        menu = self.editor.build_context_menu()
        self.assertIsNotNone(menu, "no row menu for the selection")
        self.click(menu, label)

    def header_button(self, name, editor=None):
        editor = editor or self.editor
        btn = editor._header.menu.findChild(QtWidgets.QAbstractButton, name)
        self.assertIsNotNone(btn, f"no header-menu button {name!r}")
        return btn

    def answer_form(self, **values):
        """Patch the New / Edit collection form to be answered with *values*."""
        seen = []

        def exec_panel(panel):
            panel.opened_with = panel.values()  # what the user saw first
            panel.set_values(values)
            seen.append(panel)
            return not panel.revalidate()

        patcher = mock.patch.object(FormPanel, "exec_panel", new=exec_panel)
        patcher.start()
        self.addCleanup(patcher.stop)
        return seen

    def create(self, name, **extra):
        """Create collection *name* through the ＋ button; returns its id.

        Nothing goes in unless *add_selected* says so (the form ticks it)."""
        extra.setdefault("add_selected", False)
        self.answer_form(name=name, **extra)
        self.editor.prompt_new_collection()
        return self.editor.picked_collection()

    def answer_open_dialog(self, path):
        """Patch the open-file dialog to pick *path*; returns the folders it
        opened in."""
        opened_in = []

        def pick(_parent, _caption, folder, *_filter):
            opened_in.append(Path(folder))
            return str(path), ""

        patcher = mock.patch.object(QtWidgets.QFileDialog, "getOpenFileName", new=pick)
        patcher.start()
        self.addCleanup(patcher.stop)
        return opened_in

    def captured_menus(self):
        """Record every ContextMenu shown instead of blocking on it."""
        shown = []
        patcher = mock.patch.object(
            ContextMenu,
            "exec_",
            new=lambda menu, pos=None, dispose=True: shown.append(menu),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return shown

    def click_cell(self, name, col, modifier=QtCore.Qt.NoModifier):
        table = self.editor._table
        rect = table.visualRect(table.model().index(self.row_of(name), col))
        QTest.mouseClick(
            table.viewport(), QtCore.Qt.LeftButton, modifier, rect.center()
        )
        QtWidgets.QApplication.processEvents()

    def click_header(self, col, editor=None):
        """Left-click column *col*'s header section."""
        header = (editor or self.editor)._table.horizontalHeader()
        x = header.sectionViewportPosition(col) + header.sectionSize(col) // 2
        QTest.mouseClick(
            header.viewport(),
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            QtCore.QPoint(x, header.height() // 2),
        )
        QtWidgets.QApplication.processEvents()

    def column_menu(self, act=None, editor=None):
        """Right-click the table header; while its menu is up, ``act(rows)``
        with the menu's list of column rows.

        Returns:
            The row labels, top to bottom, as the menu opened.
        """
        seen, errors = [], []

        def exec_(menu, pos):
            try:
                return run(menu, pos)
            except BaseException as e:  # a slot's exception is only printed
                errors.append(e)

        def run(menu, pos):
            menu.popup(pos)
            QtWait.until(menu.isVisible, "the column menu never showed")
            rows = menu.findChild(QtWidgets.QListWidget)
            seen.extend(rows.item(i).text() for i in range(rows.count()))
            if act is not None:
                act(rows)
            menu.hide()
            return None

        header = (editor or self.editor)._table.horizontalHeader()
        with mock.patch.object(QtWidgets.QMenu, "exec_", exec_):
            header.customContextMenuRequested.emit(QtCore.QPoint(4, 4))
        if errors:
            raise errors[0]
        return seen

    @staticmethod
    def _row_point(rows, label):
        [item] = rows.findItems(label, QtCore.Qt.MatchExactly)
        return rows.visualItemRect(item).center()

    def pick_column(self, label, editor=None):
        """Click *label*'s row in the header's column menu; the menu's rows."""

        def click(rows):
            QTest.mouseClick(
                rows.viewport(),
                QtCore.Qt.LeftButton,
                QtCore.Qt.NoModifier,
                self._row_point(rows, label),
            )

        return self.column_menu(click, editor)

    def drag_column(self, label, onto, editor=None):
        """Drag *label*'s row in the header's column menu onto *onto*'s."""

        def drag(rows):
            viewport = rows.viewport()
            start, end = self._row_point(rows, label), self._row_point(rows, onto)
            left, none = QtCore.Qt.LeftButton, QtCore.Qt.NoModifier
            QTest.mousePress(viewport, left, none, start)
            QTest.mouseMove(viewport, start + QtCore.QPoint(0, 1))
            QTest.mouseMove(viewport, end)
            QTest.mouseRelease(viewport, left, none, end)

        return self.column_menu(drag, editor)

    def shown_columns(self, editor=None):
        """The shown column headers, left to right."""
        header = (editor or self.editor)._table.horizontalHeader()
        return [
            PresetEditor.HEADERS[header.logicalIndex(v)]
            for v in range(header.count())
            if not header.isSectionHidden(header.logicalIndex(v))
        ]

    def tree_menu(self, prefix, editor=None):
        """Right-click the tree node for *prefix*; the menu it opened."""
        editor = editor or self.editor
        [item] = [
            i
            for i in editor._iter_tree_items()
            if i.data(0, QtCore.Qt.UserRole) == prefix
        ]
        shown = self.captured_menus()
        tree = editor._tree
        tree.customContextMenuRequested.emit(tree.visualItemRect(item).center())
        self.assertEqual(len(shown), 1, f"no menu for {prefix!r}")
        return shown[0]

    def ship(self, **payloads):
        """A tool shipping built-in presets (``name=payload``), as a tool writes
        its store on first use; the window rescans."""
        shipped = self.other / "shipped"
        shipped.mkdir()
        for name, data in payloads.items():
            (shipped / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
        store = ptk.PresetStore("stock_tool", "uitk_test", builtin_dir=shipped)
        store.user_dir.mkdir(parents=True)
        store.list()  # the .domain marker: how the library finds the built-ins
        self.editor.refresh()
        return store

    def open_panel(self, key="mayatk/scene_exporter"):
        """An open panel selector over store *key*; returns its combo."""
        from uitk.widgets.comboBox import ComboBox

        chk = QtWidgets.QCheckBox()
        chk.setObjectName("a")
        self.addCleanup(chk.deleteLater)
        mgr = PresetManager.from_widgets(preset_dir=key, widgets=[chk])
        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        mgr.wire_combo(combo)
        return combo


class TreeAndFilterTest(_EditorCase):
    def setUp(self):
        # As the hosts do at startup: uitk itself names no app.
        labels = mock.patch.dict(PresetEditor.APP_LABELS)
        labels.start()
        self.addCleanup(labels.stop)
        PresetEditor.register_app_label("mayatk", "Maya")
        PresetEditor.register_app_label("blendertk", "Blender")
        super().setUp()

    def test_an_unregistered_app_folder_is_title_cased(self):
        PresetEditor.APP_LABELS.pop("mayatk")
        self.assertEqual(
            self.editor.tool_label("mayatk/scene_exporter"), "Mayatk › Scene Exporter"
        )

    def top_level(self):
        tree = self.editor._tree
        return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]

    def test_tree_groups_stores_by_app_with_counts(self):
        self.assertEqual(
            self.top_level(), ["All presets (3)", "Blender (1)", "Maya (2)"]
        )

    def test_picking_a_tool_filters_the_table(self):
        self.assertEqual(len(self.rows()), 3)
        self.assertTrue(self.editor.select_prefix("mayatk/scene_exporter"))
        self.assertEqual(self.rows(), ["Unity", "WebXR"])
        tool = self.cell("Unity", PresetEditor.COL_TOOL).text()
        self.assertEqual(tool, "Maya › Scene Exporter")

    def test_filter_text_matches_name_tool_and_tags(self):
        search = self.editor._search
        search.setText("blender")  # a tool folder's label, ignoring case
        self.assertEqual(self.rows(), ["Game (FBX)"])  # the label keeps its parens
        search.setText("*web*")
        self.assertEqual(self.rows(), ["WebXR"])
        search.setText("maya, !unity")
        self.assertEqual(self.rows(), ["WebXR"])
        search.setText("")
        self.cell("Unity", PresetEditor.COL_TAGS).setText("hero, web")
        search.setText("hero")
        self.assertEqual(self.rows(), ["Unity"])

    def test_the_filter_toggle_silences_the_text_without_clearing_it(self):
        self.editor._search.setText("unity")
        self.assertEqual(self.rows(), ["Unity"])
        self.editor._text_filter.set_on(False)
        self.assertEqual(len(self.rows()), 3)
        self.assertEqual(self.editor._search.text(), "unity")

    def test_the_status_facet_shows_every_status_picked(self):
        self.select("Unity")
        self.trigger("Lock")
        facet = self.editor._status_filter
        menu = facet.build_menu()  # one visit: the popup stays open
        self.click(menu, "Locked")
        self.assertEqual(self.rows(), ["Unity"])
        tint = IconManager.registered_info(facet.widget).get("color")
        self.assertEqual(tint, IconManager._normalize_color(ChoiceOption.ACTIVE_COLOR))
        self.click(menu, "Editable")
        self.assertEqual(len(self.rows()), 3, "locked OR editable")
        self.click(menu, "Locked")
        self.assertEqual(sorted(self.rows()), ["Game (FBX)", "WebXR"])
        self.click(menu, "Any status")
        self.assertEqual(len(self.rows()), 3)
        self.assertFalse(facet.is_active)

    def test_edited_since_export_finds_changed_collection_members(self):
        self.select("Unity", "WebXR")
        cid = self.create("Studio", add_selected=True)
        self.editor.export_collection(cid, self.other / "studio.zip")
        ptk.PresetStore("scene_exporter", "mayatk").save(
            "WebXR", {"_meta": {"version": 1}, "a": 99}
        )
        self.editor.refresh()
        self.click(
            self.editor._status_filter.build_menu(), "Edited since export or install"
        )
        self.assertEqual(self.rows(), ["WebXR"])

    def test_the_tag_facet_offers_the_tags_in_use(self):
        self.cell("Unity", PresetEditor.COL_TAGS).setText("hero")
        facet = self.editor._tag_filter
        self.assertIn("hero", self.menu_rows(facet.build_menu()))
        self.click(facet.build_menu(), "hero")
        self.assertEqual(self.rows(), ["Unity"])
        self.click(facet.build_menu(), "Untagged")
        self.assertEqual(sorted(self.rows()), ["Game (FBX)", "WebXR"])

    def test_a_vanished_tag_drops_its_facet_back_to_any(self):
        self.cell("Unity", PresetEditor.COL_TAGS).setText("hero")
        self.click(self.editor._tag_filter.build_menu(), "hero")
        self.cell("Unity", PresetEditor.COL_TAGS).setText("")
        self.assertEqual(self.editor._tag_filter.value, PresetEditor.TAG_ANY)
        self.assertEqual(len(self.rows()), 3)

    def test_the_filter_row_comes_back_with_the_window(self):
        self.editor._search.setText("*web*")
        self.click(self.editor._status_filter.build_menu(), "Editable")
        again = self.make_editor()
        self.assertEqual(again._search.text(), "*web*")
        self.assertEqual(again._status_filter.value, ("unlocked",))
        self.assertEqual(self.rows(again), ["WebXR"])


class FocusTest(_EditorCase):
    def test_a_focused_window_lists_only_its_packages(self):
        focused = self.make_editor(inc="mayatk")
        self.assertEqual(self.rows(focused), ["Unity", "WebXR"])
        tree = focused._tree
        labels = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
        self.assertEqual(labels, ["All presets (2)", "Mayatk (2)"])

    def test_the_focus_can_change_and_clear(self):
        self.editor.set_entry_filter(exc="mayatk")
        self.assertEqual(self.rows(), ["Game (FBX)"])
        self.editor.set_entry_filter()
        self.assertEqual(len(self.rows()), 3)

    def test_collections_stay_root_wide_with_the_count_in_view(self):
        self.select("Unity", "WebXR")
        cid = self.create("Studio", add_selected=True)
        focused = self.make_editor(exc="mayatk")
        cmb = focused._cmb_collection
        cells = cmb.item_cells(cmb.findData(cid))
        self.assertEqual(cells["count"], "0 presets")


class ShowTest(_EditorCase):
    def test_a_reshown_window_lists_what_was_saved_while_it_was_hidden(self):
        self.editor.show()
        self.editor.hide()
        ptk.PresetStore("scene_exporter", "mayatk").save("Late", {"_meta": {}})
        self.assertNotIn("Late", self.rows())
        self.editor.show()
        self.assertIn("Late", self.rows())


class RowActionTest(_EditorCase):
    def test_lock_from_the_row_menu_marks_the_row_and_the_open_panel(self):
        # A panel selector for the same store is open: locking in the editor
        # must reach it without a manual Refresh.
        from uitk.widgets.comboBox import ComboBox

        chk = QtWidgets.QCheckBox()
        chk.setObjectName("a")
        mgr = PresetManager.from_widgets(
            preset_dir="mayatk/scene_exporter", widgets=[chk]
        )
        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        mgr.wire_combo(combo)

        self.select("Unity")
        self.trigger("Lock")
        self.assertEqual(self.cell("Unity", PresetEditor.COL_LOCK).text(), "Locked")
        self.assertTrue(
            ptk.PresetStore("scene_exporter", "mayatk").is_read_only("Unity")
        )
        item = combo.model().item(combo.findText("Unity"))
        self.assertTrue(item.font().italic())

        self.select("Unity")
        self.trigger("Unlock")
        self.assertEqual(self.cell("Unity", PresetEditor.COL_LOCK).text(), "")

    def test_a_mixed_selection_can_be_unlocked_without_locking_it_first(self):
        self.select("Unity")
        self.trigger("Lock")
        self.select("Unity", "WebXR")
        self.assertLessEqual(
            {"Lock", "Unlock"}, set(self.menu_rows(self.editor.build_context_menu()))
        )
        self.trigger("Unlock")
        self.assertEqual(self.cell("Unity", PresetEditor.COL_LOCK).text(), "")
        self.assertEqual(self.cell("WebXR", PresetEditor.COL_LOCK).text(), "")

    def test_a_locked_name_cell_is_not_editable_and_cannot_be_deleted(self):
        self.select("Unity")
        self.trigger("Lock")
        flags = self.cell("Unity", PresetEditor.COL_NAME).flags()
        self.assertFalse(flags & QtCore.Qt.ItemIsEditable)
        self.select("Unity")
        self.assertNotIn("Delete", self.menu_rows(self.editor.build_context_menu()))

    def test_the_row_menu_leaves_collections_to_the_collection_cell(self):
        self.select("Unity")
        rows = self.menu_rows(self.editor.build_context_menu())
        self.assertFalse([r for r in rows if "ollection" in r], rows)

    def test_editing_the_name_cell_renames_the_preset(self):
        self.cell("WebXR", PresetEditor.COL_NAME).setText("WebXR (preview)")
        store = ptk.PresetStore("scene_exporter", "mayatk")
        self.assertTrue(store.exists("WebXR (preview)"))
        self.assertFalse(store.exists("WebXR"))
        self.assertIn("WebXR (preview)", self.rows())

    def test_renaming_a_panels_active_preset_keeps_the_panel_on_it(self):
        # The open selector is refreshed by notify(); under the file name the
        # new label gets ("WebXR _preview_") it must still show the preset it
        # had active, not fall to its placeholder.
        from uitk.widgets.comboBox import ComboBox

        chk = QtWidgets.QCheckBox()
        chk.setObjectName("a")
        mgr = PresetManager.from_widgets(
            preset_dir="mayatk/scene_exporter", widgets=[chk]
        )
        combo = ComboBox()
        self.addCleanup(combo.deleteLater)
        mgr.wire_combo(combo)
        mgr.active_preset = "WebXR"
        mgr.refresh_combo()
        self.assertEqual(combo.currentText(), "WebXR")

        self.cell("WebXR", PresetEditor.COL_NAME).setText("WebXR (preview)")
        self.assertEqual(combo.currentText(), "WebXR _preview_")
        self.assertEqual(mgr.active_preset, "WebXR _preview_")

    def test_duplicate_makes_an_unlocked_copy(self):
        self.select("Unity")
        self.trigger("Lock")
        self.select("Unity")
        self.trigger("Duplicate")
        self.assertIn("Unity copy", self.rows())
        self.assertEqual(self.cell("Unity copy", PresetEditor.COL_LOCK).text(), "")

    def test_delete_backs_up_first_and_keeps_locked_presets(self):
        self.select("Unity")
        self.trigger("Lock")
        self.select("Unity", "WebXR")
        self.trigger("Delete")
        self.assertEqual(sorted(self.rows()), ["Game (FBX)", "Unity"])
        backups = ptk.PresetLibrary().backups()
        self.assertEqual(len(backups), 1)
        self.assertIn("Deleted 1 preset", self.editor.footer.statusText())


class SortTest(_EditorCase):
    """A header click sorts the presets by that column; a second reverses it.

    The DATA is sorted, never the view: every edit maps a row to its preset by
    position, so the list and the rows must stay in one order.
    """

    def setUp(self):
        super().setUp()
        self.exporter = ptk.PresetStore("scene_exporter", "mayatk")
        self.exporter.save("Alpha", {"_meta": {"version": 1}, "a": 0})
        self.editor.refresh()
        # Default order: by tool, then name.
        self.assertEqual(self.rows(), ["Game (FBX)", "Alpha", "Unity", "WebXR"])

    def test_a_click_sorts_by_name_and_a_second_reverses_it(self):
        header = self.editor._table.horizontalHeader()
        self.assertFalse(header.isSortIndicatorShown())
        self.click_header(PresetEditor.COL_NAME)
        self.assertEqual(self.rows(), ["Alpha", "Game (FBX)", "Unity", "WebXR"])
        self.assertTrue(header.isSortIndicatorShown())
        self.click_header(PresetEditor.COL_NAME)
        self.assertEqual(self.rows(), ["WebXR", "Unity", "Game (FBX)", "Alpha"])
        self.assertEqual(
            (header.sortIndicatorSection(), header.sortIndicatorOrder()),
            (PresetEditor.COL_NAME, QtCore.Qt.DescendingOrder),
        )

    def test_after_sorting_each_rows_edits_hit_the_preset_it_shows(self):
        self.click_header(PresetEditor.COL_NAME)
        self.click_header(PresetEditor.COL_NAME)
        self.cell("Unity", PresetEditor.COL_NAME).setText("Unity 6")
        self.cell("Alpha", PresetEditor.COL_TAGS).setText("first")
        self.click_cell("WebXR", PresetEditor.COL_NAME)  # select it by its row
        self.trigger("Delete")
        self.assertEqual(self.exporter.list(), ["Alpha", "Unity 6"])
        self.assertEqual(self.exporter.info("Alpha")["tags"], ["first"])
        self.assertEqual(self.rows(), ["Unity 6", "Game (FBX)", "Alpha"])

    def test_names_sort_naturally_ignoring_case(self):
        takes = ptk.PresetStore("takes", "uitk_test")
        for name in ("Take 10", "take 2", "Take 1"):
            takes.save(name, {})
        self.editor.refresh()
        self.editor.select_prefix("uitk_test/takes")
        self.assertEqual(self.rows(), ["Take 1", "Take 10", "take 2"])
        self.click_header(PresetEditor.COL_NAME)
        self.assertEqual(self.rows(), ["Take 1", "take 2", "Take 10"])

    def test_text_columns_sort_case_blind_with_empty_cells_first(self):
        self.cell("WebXR", PresetEditor.COL_TAGS).setText("alpha")
        self.cell("Unity", PresetEditor.COL_TAGS).setText("Beta")
        self.click_header(PresetEditor.COL_TAGS)
        self.assertEqual(self.rows(), ["Game (FBX)", "Alpha", "WebXR", "Unity"])

    def test_modified_sorts_by_time_even_within_one_shown_minute(self):
        # Four saves in one minute read the same; their order is still known.
        minute = (int(time.time()) // 60) * 60 - 3600
        paths = [
            self.exporter.path("WebXR"),
            self.exporter.path("Unity"),
            self.exporter.path("Alpha"),
            ptk.PresetStore("fbx_presets", "blendertk").path("Game (FBX)"),
        ]
        for second, path in enumerate(paths):
            os.utime(path, (minute + 10 * second, minute + 10 * second))
        self.editor.refresh()
        shown = {self.cell(n, PresetEditor.COL_MODIFIED).text() for n in self.rows()}
        self.assertEqual(len(shown), 1, shown)
        self.click_header(PresetEditor.COL_MODIFIED)
        self.assertEqual(self.rows(), ["WebXR", "Unity", "Alpha", "Game (FBX)"])

    def test_the_sort_outlives_filters_and_rescans_and_keeps_the_selection(self):
        self.select("Unity")
        self.click_header(PresetEditor.COL_NAME)
        self.click_header(PresetEditor.COL_NAME)
        self.assertEqual([e.name for e in self.editor.selected_entries()], ["Unity"])
        self.editor._search.setText("!game*")
        self.assertEqual(self.rows(), ["WebXR", "Unity", "Alpha"])
        self.editor.refresh()
        self.assertEqual(self.rows(), ["WebXR", "Unity", "Alpha"])
        self.assertEqual([e.name for e in self.editor.selected_entries()], ["Unity"])


class HideTest(_EditorCase):
    """Hide a preset from its panel's dropdown; it stays here, dimmed."""

    def test_hide_from_the_row_menu_dims_the_row_and_drops_it_from_the_panel(self):
        combo = self.open_panel()
        self.select("Unity")
        self.trigger("Hide")
        self.assertEqual(combo.findText("Unity"), -1)
        self.assertIn("Unity", self.rows())
        self.assertTrue(ptk.PresetStore("scene_exporter", "mayatk").is_hidden("Unity"))
        dim = self.editor._table.palette().color(
            QtGui.QPalette.Disabled, QtGui.QPalette.Text
        )
        self.assertEqual(
            self.cell("Unity", PresetEditor.COL_NAME).foreground().color(), dim
        )
        self.assertNotEqual(
            self.cell("WebXR", PresetEditor.COL_NAME).foreground().color(), dim
        )
        self.select("Unity")
        rows = self.menu_rows(self.editor.build_context_menu())
        self.assertIn("Show", rows)
        self.assertNotIn("Hide", rows)
        self.trigger("Show")
        self.assertNotEqual(combo.findText("Unity"), -1)

    def test_a_mixed_selection_offers_hide_and_show(self):
        self.select("Unity")
        self.trigger("Hide")
        self.select("Unity", "WebXR")
        rows = self.menu_rows(self.editor.build_context_menu())
        self.assertLessEqual({"Hide", "Show"}, set(rows))

    def test_the_hidden_status_facet_lists_the_hidden_ones(self):
        self.select("WebXR")
        self.trigger("Hide")
        self.click(self.editor._status_filter.build_menu(), "Hidden")
        self.assertEqual(self.rows(), ["WebXR"])

    def test_a_builtin_can_be_hidden_and_shown(self):
        store = self.ship(Stock={"x": 0})
        self.select("Stock")
        self.trigger("Hide")
        self.assertTrue(store.is_hidden("Stock"))
        self.assertEqual(self.cell("Stock", PresetEditor.COL_LOCK).text(), "Built-in")
        self.select("Stock")
        self.trigger("Show")
        self.assertFalse(store.is_hidden("Stock"))


class DescriptionTest(_EditorCase):
    def test_typing_a_description_saves_it_and_the_filter_finds_it(self):
        self.cell("Unity", PresetEditor.COL_DESCRIPTION).setText("For the Unity export")
        info = ptk.PresetStore("scene_exporter", "mayatk").info("Unity")
        self.assertEqual(info["description"], "For the Unity export")
        cell = self.cell("Unity", PresetEditor.COL_DESCRIPTION)
        self.assertEqual(cell.toolTip(), "For the Unity export")
        self.editor._search.setText("*unity export*")
        self.assertEqual(self.rows(), ["Unity"])

    def test_a_builtins_shipped_description_is_shown_read_only(self):
        self.ship(Stock={"_meta": {"description": "The shipped look."}})
        cell = self.cell("Stock", PresetEditor.COL_DESCRIPTION)
        self.assertEqual(cell.text(), "The shipped look.")
        self.assertFalse(cell.flags() & QtCore.Qt.ItemIsEditable)
        self.assertTrue(cell.font().italic())
        mine = self.cell("Unity", PresetEditor.COL_DESCRIPTION)
        self.assertTrue(mine.flags() & QtCore.Qt.ItemIsEditable)


class ColumnMenuTest(_EditorCase):
    """Right-click the header: a column per row, ticked while shown."""

    def test_unticking_a_column_hides_it_and_the_next_window_keeps_it_hidden(self):
        rows = self.pick_column("Tags")
        self.assertEqual(list(rows), list(PresetEditor.HEADERS))
        self.assertTrue(self.editor._table.isColumnHidden(PresetEditor.COL_TAGS))
        again = self.make_editor()
        self.assertTrue(again._table.isColumnHidden(PresetEditor.COL_TAGS))
        self.pick_column("Tags", again)
        self.assertFalse(again._table.isColumnHidden(PresetEditor.COL_TAGS))

    def test_the_name_column_cannot_be_hidden(self):
        self.pick_column("Name")
        self.assertFalse(self.editor._table.isColumnHidden(PresetEditor.COL_NAME))

    def test_description_is_last_and_takes_the_spare_width(self):
        self.assertEqual(self.shown_columns()[-1], "Description")
        table = self.editor._table
        header = table.horizontalHeader()
        self.editor.resize(1400, 500)
        self.editor.show()
        QtWidgets.QApplication.processEvents()
        widths = [header.sectionSize(c) for c in range(header.count())]
        self.assertEqual(sum(widths), table.viewport().width(), "no gap, no overflow")
        before = header.sectionSize(PresetEditor.COL_DESCRIPTION)
        others = widths[: PresetEditor.COL_DESCRIPTION]
        self.editor.resize(1600, 500)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(
            header.sectionSize(PresetEditor.COL_DESCRIPTION) - before,
            table.viewport().width() - sum(widths),
            "the added width all goes to Description",
        )
        self.assertEqual(
            [header.sectionSize(c) for c in range(PresetEditor.COL_DESCRIPTION)],
            others,
            "the other columns keep their widths",
        )

    def test_columns_are_reordered_by_dragging_their_rows_and_kept(self):
        self.drag_column("Tool", "Name")
        self.assertEqual(self.shown_columns()[:2], ["Tool", "Name"])
        header = self.editor._table.horizontalHeader()
        self.assertFalse(header.sectionsMovable(), "a header click still sorts")
        again = self.make_editor()
        self.assertEqual(self.shown_columns(again)[:2], ["Tool", "Name"])
        self.assertEqual(
            again._table.horizontalHeader().sectionResizeMode(
                PresetEditor.COL_DESCRIPTION
            ),
            QtWidgets.QHeaderView.Stretch,
            "the spare width stays with Description",
        )

    def test_a_long_description_shows_whole_and_wrapped_in_its_tooltip(self):
        words = " ".join(f"word{i}" for i in range(400))  # ~3000 characters
        self.cell("Unity", PresetEditor.COL_DESCRIPTION).setText(words)
        table = self.editor._table
        self.editor.show()
        QtWidgets.QApplication.processEvents()
        rect = table.visualItemRect(self.cell("Unity", PresetEditor.COL_DESCRIPTION))
        shown = []
        with mock.patch.object(
            QtWidgets.QToolTip,
            "showText",
            new=lambda pos, text, *rest: shown.append(text),
        ):
            viewport = table.viewport()
            event = QtGui.QHelpEvent(
                QtCore.QEvent.ToolTip,
                rect.center(),
                viewport.mapToGlobal(rect.center()),
            )
            QtWidgets.QApplication.sendEvent(viewport, event)
        [tip] = shown
        lines = tip.splitlines()
        self.assertGreater(len(lines), 10, "wrapped into lines")
        self.assertLessEqual(max(map(len, lines)), 80, "each a readable width")
        self.assertTrue(tip.startswith("word0 word1"), "from the start")
        self.assertTrue(tip.endswith("…"), "a cut description says so")
        shown_text = tip[:-1].replace("\n", " ")
        cap = PresetEditor.DESCRIPTION_TIP_CHARS
        self.assertTrue(words.startswith(shown_text + " "), "cut at a word")
        self.assertLessEqual(len(shown_text), cap)
        self.assertGreater(len(shown_text), cap - len("word399 "), "all it can hold")

    def test_a_sort_by_a_column_that_gets_hidden_is_kept(self):
        self.cell("WebXR", PresetEditor.COL_TAGS).setText("a")
        self.cell("Unity", PresetEditor.COL_TAGS).setText("b")
        self.click_header(PresetEditor.COL_TAGS)
        self.click_header(PresetEditor.COL_TAGS)
        self.assertEqual(self.rows(), ["Unity", "WebXR", "Game (FBX)"])
        self.pick_column("Tags")
        self.editor.refresh()
        self.assertEqual(self.rows(), ["Unity", "WebXR", "Game (FBX)"])


class TreeMenuTest(_EditorCase):
    """Right-click a node of the left pane: act on every preset under it."""

    def test_lock_all_locks_the_nodes_presets_only_and_unlock_all_undoes_it(self):
        menu = self.tree_menu("mayatk")
        rows = self.menu_rows(menu)
        self.assertIn("Lock all", rows)
        self.assertNotIn("Unlock all", rows)
        self.click(menu, "Lock all")
        self.assertEqual(self.cell("Unity", PresetEditor.COL_LOCK).text(), "Locked")
        self.assertEqual(self.cell("WebXR", PresetEditor.COL_LOCK).text(), "Locked")
        self.assertEqual(self.cell("Game (FBX)", PresetEditor.COL_LOCK).text(), "")
        rows = self.menu_rows(self.tree_menu("mayatk"))
        self.assertNotIn("Lock all", rows)
        self.click(self.tree_menu("mayatk"), "Unlock all")
        self.assertEqual(self.cell("Unity", PresetEditor.COL_LOCK).text(), "")

    def test_hide_all_on_the_root_takes_every_preset(self):
        self.click(self.tree_menu(""), "Hide all")
        self.assertTrue(all(e.hidden for e in ptk.PresetLibrary().entries()))
        rows = self.menu_rows(self.tree_menu(""))
        self.assertIn("Show all", rows)
        self.assertNotIn("Hide all", rows)

    def test_open_folder_opens_the_nodes_folder(self):
        opened = []
        with mock.patch.object(
            QtGui.QDesktopServices,
            "openUrl",
            new=lambda url: opened.append(Path(url.toLocalFile())),
        ):
            self.click(self.tree_menu("mayatk/scene_exporter"), "Open folder")
        self.assertEqual(opened, [self.root / "mayatk" / "scene_exporter"])

    def test_back_up_these_presets_covers_the_nodes_stores_only(self):
        self.click(self.tree_menu("blendertk"), "Back up these presets")
        [backup] = ptk.PresetLibrary().backups()
        with zipfile.ZipFile(backup) as zf:
            payloads = [
                n
                for n in zf.namelist()
                if n.startswith("presets/") and not n.rsplit("/", 1)[-1].startswith(".")
            ]
        self.assertEqual(payloads, ["presets/blendertk/fbx_presets/Game _FBX_.json"])
        self.assertIn("Backed up", self.editor.footer.statusText())

    def test_a_node_of_built_ins_offers_what_applies_to_them(self):
        self.ship(Stock={"x": 0})
        rows = self.menu_rows(self.tree_menu("uitk_test"))
        self.assertIn("Hide all", rows)
        self.assertIn("Open folder", rows)
        self.assertNotIn("Lock all", rows)
        self.assertNotIn("Back up these presets", rows)


class StaleRowTest(_EditorCase):
    """A panel renames or deletes a preset while the window lists it: an action
    on the stale row rescans and says so, rather than raising out of the action
    (or, from a cell or a menu, out of the slot, where nobody sees it)."""

    def setUp(self):
        super().setUp()
        store = ptk.PresetStore("scene_exporter", "mayatk")
        store.rename("Unity", "Unity 2")  # behind the window's back
        store.delete("WebXR")
        self.unity, self.webxr = self.stale("Unity"), self.stale("WebXR")

    def stale(self, name):
        [entry] = [e for e in self.editor._rows if e.name == name]
        return entry

    def slot_errors(self):
        """What slots raise: it reaches ``sys.excepthook``, never the caller."""
        errors = []
        patcher = mock.patch.object(
            sys, "excepthook", new=lambda *exc: errors.append(exc[1])
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return errors

    def assert_refreshed(self):
        self.assertIn("Unity 2", self.rows())
        self.assertNotIn("WebXR", self.rows())
        self.assertIn("changed on disk", self.editor.footer.statusText())

    def test_lock(self):
        self.assertEqual(self.editor.lock([self.unity]), 0)
        self.assert_refreshed()

    def test_duplicate(self):
        self.assertIsNone(self.editor.duplicate(self.webxr))
        self.assert_refreshed()

    def test_assign(self):
        cid = ptk.PresetLibrary().create_collection("Studio")["id"]
        self.assertEqual(self.editor.assign(cid, [self.unity]), 0)
        self.assert_refreshed()

    def test_a_new_collection_is_not_left_behind_empty(self):
        self.assertIsNone(self.editor.create_collection("Studio", "", [self.unity]))
        self.assertEqual(ptk.PresetLibrary().collections(), [])
        self.assert_refreshed()

    def test_a_member_lost_after_the_check_takes_the_new_header_back(self):
        # The race the up-front check can't close: the file goes between the
        # check and the move, after the header is written.
        self.editor.refresh()
        fresh = self.stale("Unity 2")
        with mock.patch.object(
            self.editor.library, "assign", side_effect=KeyError("gone")
        ):
            self.assertIsNone(self.editor.create_collection("Studio", "", [fresh]))
        self.assertEqual(ptk.PresetLibrary().collections(), [])
        self.assertIn("changed on disk", self.editor.footer.statusText())

    def test_tags_typed_into_the_cell(self):
        errors = self.slot_errors()
        self.cell("Unity", PresetEditor.COL_TAGS).setText("web")
        self.assertEqual(errors, [])
        self.assert_refreshed()

    def test_copy_contents_from_the_row_menu(self):
        errors = self.slot_errors()
        self.select("WebXR")
        self.trigger("Copy contents")
        self.assertEqual(errors, [])
        self.assert_refreshed()


class CollectionBoxTest(_EditorCase):
    """The collections box: filter, ＋ new, double-click rename, ☰ menu."""

    def box_texts(self):
        cmb = self.editor._cmb_collection
        return [cmb.itemText(i) for i in range(cmb.count())]

    def test_new_collection_takes_the_selection_and_shows_it(self):
        self.select("Unity", "WebXR")
        seen = self.answer_form(name="Acme Standard", description="Studio")
        self.editor.prompt_new_collection()
        [form] = seen
        self.assertEqual(self.editor._cmb_collection.currentText(), "Acme Standard")
        self.assertEqual(sorted(self.rows()), ["Unity", "WebXR"])
        header = ptk.PresetLibrary().collection(self.editor.picked_collection())
        self.assertEqual(header["description"], "Studio")
        self.assertIn("Add the 2 selected presets", form.add_selected.text())

    def test_unticking_add_selected_makes_an_empty_collection(self):
        self.select("Unity")
        cid = self.create("Empty", add_selected=False)
        self.assertEqual(ptk.PresetLibrary().members(cid), [])

    def test_the_form_refuses_a_blank_or_taken_name(self):
        self.create("Studio")
        form = self.editor._collection_form()
        self.addCleanup(form.deleteLater)
        self.assertEqual(form.revalidate(), "Name the collection.")
        form.set_values({"name": "studio"})
        self.assertIn("already exists", form.revalidate())
        self.assertFalse(form._ok_btn.isEnabled())
        self.assertEqual(len(ptk.PresetLibrary().collections()), 1)

    def test_picking_in_the_box_filters_and_is_remembered(self):
        self.select("Unity")
        cid = self.create("Studio", add_selected=True)
        self.assertEqual(self.rows(), ["Unity"])
        self.editor.set_collection_filter(PresetEditor.NO_COLLECTION)
        self.assertEqual(sorted(self.rows()), ["Game (FBX)", "WebXR"])
        self.editor.set_collection_filter(cid)
        self.assertEqual(self.make_editor().picked_collection(), cid)

    def test_double_click_renames_a_collection_but_not_the_fixed_rows(self):
        cid = self.create("Studio")
        cmb = self.editor._cmb_collection
        self.assertTrue(cmb.rename_on_double_click)
        cmb.begin_rename()
        QtWidgets.QApplication.processEvents()
        editor = cmb._cell_editor
        self.assertIsNotNone(editor, "a collection row opens the cell editor")
        editor._fields["name"].setText("Studio Standard")
        editor.committed.emit(editor.values())
        self.assertEqual(ptk.PresetLibrary().collection(cid)["name"], "Studio Standard")
        self.assertEqual(cmb.currentText(), "Studio Standard")
        self.editor.set_collection_filter(PresetEditor.ALL_PRESETS)
        self.assertFalse(cmb.rename_on_double_click)

    def test_renaming_onto_a_taken_name_is_refused_and_undone(self):
        self.create("Studio")
        cid = self.create("Other")
        cmb = self.editor._cmb_collection
        cmb.begin_rename()
        QtWidgets.QApplication.processEvents()
        editor = cmb._cell_editor
        editor._fields["name"].setText("studio")
        editor.committed.emit(editor.values())
        self.assertEqual(ptk.PresetLibrary().collection(cid)["name"], "Other")
        self.assertEqual(cmb.currentText(), "Other")
        self.assertIn("already exists", self.editor.footer.statusText())

    def test_without_a_collection_the_menu_offers_only_import(self):
        rows = self.menu_rows(self.editor.build_collection_menu())
        enabled = [text for text, row in rows.items() if row.isEnabled()]
        self.assertEqual(enabled, ["Import…"])
        self.assertEqual(len(rows), 2, "and a hint to pick one for the rest")

    def test_lock_and_unlock_the_collection_from_the_box(self):
        self.select("Unity", "WebXR")
        self.create("Studio", add_selected=True)
        rows = self.menu_rows(self.editor.build_collection_menu())
        self.assertIn("Lock", rows)
        self.assertNotIn("Unlock", rows)
        self.click(self.editor.build_collection_menu(), "Lock")
        for name in ("Unity", "WebXR"):
            self.assertEqual(self.cell(name, PresetEditor.COL_LOCK).text(), "Locked")
        fbx = ptk.PresetStore("fbx_presets", "blendertk")
        self.assertFalse(
            any(fbx.is_read_only(n) for n in fbx.list()),
            "only the collection's presets",
        )
        rows = self.menu_rows(self.editor.build_collection_menu())
        self.assertNotIn("Lock", rows)
        # Mixed: either way is one click.
        self.editor.lock([self.editor._rows[self.row_of("WebXR")]], False)
        rows = self.menu_rows(self.editor.build_collection_menu())
        self.assertLessEqual({"Lock", "Unlock"}, set(rows))
        self.click(self.editor.build_collection_menu(), "Unlock")
        self.assertEqual(self.cell("Unity", PresetEditor.COL_LOCK).text(), "")

    def test_an_empty_collection_has_nothing_to_lock(self):
        self.create("Empty")
        rows = self.menu_rows(self.editor.build_collection_menu())
        self.assertFalse({"Lock", "Unlock"} & set(rows))

    def test_edit_changes_name_and_description(self):
        cid = self.create("Studio")
        self.editor.edit_collection(cid, description="Old")
        seen = self.answer_form(name="Studio Std", description="House style")
        self.click(self.editor.build_collection_menu(), "Edit…")
        [form] = seen
        self.assertEqual(form.opened_with, {"name": "Studio", "description": "Old"})
        self.assertEqual(ptk.PresetLibrary().collection(cid)["name"], "Studio Std")
        self.assertEqual(
            ptk.PresetLibrary().collection(cid)["description"], "House style"
        )

    def test_an_empty_collection_can_be_deleted_from_the_box(self):
        cid = self.create("Empty")
        self.click(self.editor.build_collection_menu(), "Delete")
        self.assertIsNone(ptk.PresetLibrary().collection(cid))
        self.assertEqual(self.editor.collection_filter(), PresetEditor.ALL_PRESETS)
        self.assertNotIn("Empty", self.box_texts())

    def test_delete_keeps_the_presets_untagged(self):
        self.select("Unity", "WebXR")
        self.create("Studio", add_selected=True)
        self.click(self.editor.build_collection_menu(), "Delete")
        self.assertEqual(len(self.rows()), 3)
        self.assertEqual(self.cell("Unity", PresetEditor.COL_COLLECTION).text(), "")

    def test_delete_with_its_presets_backs_up_and_keeps_edited_ones(self):
        self.select("Unity", "WebXR")
        cid = self.create("Studio", add_selected=True)
        self.editor.export_collection(cid, self.other / "studio.zip")
        ptk.PresetStore("scene_exporter", "mayatk").save(
            "WebXR", {"_meta": {"version": 1}, "a": 99}
        )
        self.editor.refresh()
        self.click(
            self.editor.build_collection_menu(), "Delete", "Delete with its presets"
        )
        self.assertEqual(sorted(self.rows()), ["Game (FBX)", "WebXR"])
        self.assertEqual(len(ptk.PresetLibrary().backups()), 1)

    def test_export_bumps_the_version_the_box_shows(self):
        self.select("Unity")
        cid = self.create("Studio", add_selected=True)
        bundle = self.other / "studio.zip"
        with mock.patch.object(
            QtWidgets.QFileDialog,
            "getSaveFileName",
            new=lambda *a, **k: (str(bundle), ""),
        ):
            self.click(self.editor.build_collection_menu(), "Export…")
        self.assertTrue(bundle.is_file())
        cmb = self.editor._cmb_collection
        self.assertEqual(cmb.item_cells(cmb.findData(cid))["version"], "v1")


class CollectionCellTest(_EditorCase):
    """A preset's Collection cell: click it to add, move or remove the preset."""

    def test_clicking_a_selected_rows_cell_keeps_the_selection(self):
        studio = self.create("Studio")
        self.editor.set_collection_filter(PresetEditor.ALL_PRESETS)
        shown = self.captured_menus()
        self.select("Unity", "WebXR")
        self.click_cell("WebXR", PresetEditor.COL_COLLECTION)
        self.assertEqual(
            sorted(e.name for e in self.editor.selected_entries()), ["Unity", "WebXR"]
        )
        [menu] = shown
        self.click(menu, "Add to", "Studio")
        members = sorted(e.name for e in ptk.PresetLibrary().members(studio))
        self.assertEqual(members, ["Unity", "WebXR"])

    def test_clicking_another_rows_cell_acts_on_that_row_alone(self):
        self.create("Studio")
        self.editor.set_collection_filter(PresetEditor.ALL_PRESETS)
        shown = self.captured_menus()
        self.select("Unity")
        self.click_cell("WebXR", PresetEditor.COL_COLLECTION)
        self.assertEqual([e.name for e in self.editor.selected_entries()], ["WebXR"])
        self.assertEqual(len(shown), 1)

    def test_ctrl_click_on_the_cell_still_extends_the_selection(self):
        shown = self.captured_menus()
        self.select("Unity")
        self.click_cell("WebXR", PresetEditor.COL_COLLECTION, QtCore.Qt.ControlModifier)
        self.assertEqual(len(self.editor.selected_entries()), 2)
        self.assertEqual(shown, [])

    def test_a_lost_release_does_not_eat_the_next_clicks(self):
        self.captured_menus()
        clicked = []
        table = self.editor._table
        table.clicked.connect(lambda index: clicked.append(index.row()))
        cell = table.visualRect(
            table.model().index(self.row_of("Unity"), PresetEditor.COL_COLLECTION)
        )
        # The popup took the release: the viewport saw only the press.
        QTest.mousePress(table.viewport(), QtCore.Qt.LeftButton, pos=cell.center())
        QtWidgets.QApplication.processEvents()
        self.click_cell("WebXR", PresetEditor.COL_NAME)
        self.assertEqual(clicked, [self.row_of("WebXR")])

    def test_move_between_collections_and_remove(self):
        self.select("Unity")
        self.create("Studio", add_selected=True)
        other = self.create("Other")
        self.editor.set_collection_filter(PresetEditor.ALL_PRESETS)
        row = self.row_of("Unity")
        self.click(self.editor.build_collection_cell_menu(row), "Move to", "Other")
        self.assertEqual(
            self.cell("Unity", PresetEditor.COL_COLLECTION).text(), "Other"
        )
        self.click(
            self.editor.build_collection_cell_menu(self.row_of("Unity")),
            "Remove from Other",
        )
        self.assertEqual(self.cell("Unity", PresetEditor.COL_COLLECTION).text(), "")
        self.assertEqual(ptk.PresetLibrary().members(other), [])

    def test_a_mixed_selection_can_join_the_collection_some_are_in(self):
        self.select("Unity")
        studio = self.create("Studio", add_selected=True)
        self.editor.set_collection_filter(PresetEditor.ALL_PRESETS)
        self.select("Unity", "WebXR")
        menu = self.editor.build_collection_cell_menu(self.row_of("WebXR"))
        self.click(menu, "Move to", "Studio")
        members = sorted(e.name for e in ptk.PresetLibrary().members(studio))
        self.assertEqual(members, ["Unity", "WebXR"])

    def test_show_only_picks_the_collection_in_the_box(self):
        self.select("Unity")
        cid = self.create("Studio", add_selected=True)
        self.editor.set_collection_filter(PresetEditor.ALL_PRESETS)
        menu = self.editor.build_collection_cell_menu(self.row_of("Unity"))
        self.click(menu, "Show only Studio")
        self.assertEqual(self.editor.picked_collection(), cid)

    def test_new_collection_from_the_cell_takes_the_clicked_presets(self):
        self.select("Unity", "WebXR")
        self.answer_form(name="Fresh", add_selected=True)
        self.click(
            self.editor.build_collection_cell_menu(self.row_of("Unity")),
            "New collection…",
        )
        self.assertEqual(sorted(self.rows()), ["Unity", "WebXR"])
        self.assertEqual(self.editor._cmb_collection.currentText(), "Fresh")

    def test_right_click_on_the_cell_opens_the_cell_menu_not_the_row_menu(self):
        shown = self.captured_menus()
        table = self.editor._table
        row = self.row_of("Unity")
        for col in (PresetEditor.COL_COLLECTION, PresetEditor.COL_NAME):
            pos = table.visualRect(table.model().index(row, col)).center()
            self.editor._on_context_menu(pos)
        cell_menu, row_menu = shown
        self.assertIn("New collection…", self.menu_rows(cell_menu))
        self.assertIn("Duplicate", self.menu_rows(row_menu))


class ImportFlowTest(_EditorCase):
    """Author builds and exports a collection; an artist reviews and installs it."""

    def export_studio(self, *names, lock=False):
        self.select(*names)
        cid = self.create("Acme Standard", add_selected=True)
        if lock:
            self.select(*names)
            self.trigger("Lock")
        bundle = self.other / "Acme Standard.presets.zip"
        self.editor.export_collection(cid, bundle)
        return bundle

    def test_export_review_and_install_in_another_root(self):
        bundle = self.export_studio("Unity", "WebXR", lock=True)
        self.assertTrue(bundle.is_file())

        artist = self.make_editor(ptk.PresetLibrary(self.other / "root"))
        artist.import_bundle(bundle)
        self.assertEqual(artist._stack.currentIndex(), PresetEditor.PAGE_IMPORT)
        self.assertEqual(artist._tbl_import.rowCount(), 2)
        statuses = {
            artist._tbl_import.item(r, 1).text(): artist._tbl_import.item(r, 2).text()
            for r in range(2)
        }
        self.assertEqual(statuses, {"Unity": "new", "WebXR": "new"})
        artist._btn_apply_import.click()
        self.assertEqual(artist._stack.currentIndex(), PresetEditor.PAGE_PRESETS)
        self.assertEqual(sorted(self.rows(artist)), ["Unity", "WebXR"])
        self.assertEqual(
            self.cell("Unity", PresetEditor.COL_LOCK, artist).text(), "Locked"
        )
        self.assertIn(
            "Acme Standard",
            [
                artist._cmb_collection.itemText(i)
                for i in range(artist._cmb_collection.count())
            ],
        )
        self.assertIn("Imported", artist.footer.statusText())

    def test_import_from_the_collections_box_then_shows_the_collection(self):
        bundle = self.export_studio("Unity", "WebXR")
        artist = self.make_editor(ptk.PresetLibrary(self.other / "root"))
        # The artist is looking at another tool's presets: what arrives must
        # show anyway, so the tree goes back to every tool.
        fbx = artist.library.domain("blendertk/fbx_presets").store()
        fbx.save("Mine", {"axis": "Z"})
        artist.refresh()
        self.assertTrue(artist.select_prefix("blendertk/fbx_presets"))
        self.assertEqual(self.rows(artist), ["Mine"])
        opened_in = self.answer_open_dialog(bundle)
        self.click(artist.build_collection_menu(), "Import…")
        self.assertEqual(opened_in, [Path.home()], "a shared bundle, not a backup")
        self.assertEqual(artist._stack.currentIndex(), PresetEditor.PAGE_IMPORT)
        artist.apply_import()
        [installed] = artist.library.collections()
        self.assertEqual(artist.collection_filter(), installed["id"])
        self.assertEqual(sorted(self.rows(artist)), ["Unity", "WebXR"])

    def test_changing_a_row_action_is_what_apply_does(self):
        bundle = self.export_studio("Unity")
        artist = self.make_editor(ptk.PresetLibrary(self.other / "root"))
        artist.import_bundle(bundle)
        combo = artist._tbl_import.cellWidget(0, 3)
        combo.setCurrentText("skip")
        self.assertFalse(artist._plan.pending())
        artist.apply_import()
        self.assertEqual(self.rows(artist), [])

    def test_cancel_leaves_everything_untouched(self):
        bundle = self.export_studio("Unity")
        artist = self.make_editor(ptk.PresetLibrary(self.other / "root"))
        artist.import_bundle(bundle)
        artist._btn_cancel_import.click()
        self.assertEqual(artist._stack.currentIndex(), PresetEditor.PAGE_PRESETS)
        self.assertFalse((self.other / "root").exists())

    def test_a_non_bundle_reports_instead_of_raising(self):
        junk = self.other / "junk.zip"
        junk.write_bytes(b"nope")
        self.assertIsNone(self.editor.import_bundle(junk))
        self.assertEqual(self.editor._stack.currentIndex(), PresetEditor.PAGE_PRESETS)
        self.assertIn("not a preset bundle", self.editor.footer.statusText())


class MaintenanceTest(_EditorCase):
    def test_back_up_all_writes_to_the_backups_folder(self):
        self.header_button("b_backup").click()
        [backup] = ptk.PresetLibrary().backups()
        self.assertEqual(backup.parent.name, ".backups")
        self.assertIn("Backed up", self.editor.footer.statusText())

    def test_restore_opens_in_the_backups_folder_and_reviews_the_backup(self):
        self.header_button("b_backup").click()
        [backup] = ptk.PresetLibrary().backups()
        opened_in = self.answer_open_dialog(backup)
        self.header_button("b_restore").click()
        self.assertEqual(opened_in, [backup.parent])
        self.assertEqual(self.editor._stack.currentIndex(), PresetEditor.PAGE_IMPORT)
        self.assertIn("Backup", self.editor._lbl_import.text())
        self.assertEqual(
            self.editor.collection_filter(),
            PresetEditor.ALL_PRESETS,
            "a backup is not a collection to show",
        )

    def test_clean_up_removes_stray_metadata(self):
        store = ptk.PresetStore("scene_exporter", "mayatk")
        store.path("WebXR").unlink()  # as an older install would delete it
        self.header_button("b_clean_up").click()
        self.assertFalse(store.info_path("WebXR").exists())
        self.assertIn("1 stray", self.editor.footer.statusText())


class RegistryTest(_EditorCase):
    def test_switchboard_exposes_the_editor_as_presets(self):
        from uitk.switchboard.editors import _EditorRegistry

        self.assertIn("presets", _EditorRegistry._EDITORS)
        module, cls_name, needs_sb = _EditorRegistry._EDITORS["presets"][:3]
        self.assertEqual(
            (module, cls_name, needs_sb),
            ("uitk.widgets.editors.preset_editor", "PresetEditor", False),
        )


if __name__ == "__main__":
    unittest.main()
