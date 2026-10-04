# !/usr/bin/python
# coding=utf-8
"""Tests for ChoiceOption — a filter facet: an icon button picking one value.

Each test acts the way a user does: open the popup (``build_menu``), click a
row, and read what the field shows back -- the value, the persisted key, the
icon's tint and the tooltip.

Run standalone: python -m test.test_choice_option
"""

import unittest

from conftest import QtBaseTestCase, QtWait, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets  # noqa: E402

from uitk.managers.icon_manager import IconManager  # noqa: E402
from uitk.widgets.lineEdit import LineEdit  # noqa: E402
from uitk.widgets.optionBox.options.choice import ChoiceOption  # noqa: E402
from uitk.widgets.optionBox.options.filter import FilterOption  # noqa: E402


class _DictSettings:
    """Minimal ``QSettings``-like store (value/setValue)."""

    def __init__(self, initial=None):
        self._d = dict(initial or {})

    def value(self, key, default=None):
        return self._d.get(key, default)

    def setValue(self, key, value):
        self._d[key] = value


class ChoiceOptionTest(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.window = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(self.window)
        self.field = LineEdit()
        self.field.setObjectName("le_filter")
        layout.addWidget(self.field)
        self.settings = _DictSettings()
        self.picked = []
        self.items = [
            ("Any status", "any"),
            None,
            ("Locked", "locked", "Can't be saved over"),
        ]
        self.choice = self.field.option_box.add_choice(
            icon="lock",
            label="Status",
            choices=lambda: self.items,
            default="any",
            on_changed=self.picked.append,
            settings=self.settings,
            settings_key="filter.status",
        )
        layout.addWidget(self.field.option_box.container)
        self.window.show()

    # --- acting helpers -------------------------------------------------
    def rows(self, menu=None):
        menu = menu or self.choice.build_menu()
        self.addCleanup(menu.dispose)
        return [
            w for w in menu.list._row_widgets() if isinstance(w, QtWidgets.QPushButton)
        ]

    def pick(self, text):
        [row] = [r for r in self.rows() if r.text() == text]
        row.click()

    def tint(self):
        return (IconManager.registered_info(self.choice.widget) or {}).get("color")

    # --- tests ----------------------------------------------------------
    def test_picking_a_row_sets_persists_and_announces_the_value(self):
        self.pick("Locked")
        self.assertEqual(self.choice.value, "locked")
        self.assertEqual(self.settings.value("filter.status"), "locked")
        self.assertEqual(self.picked, ["locked"])
        self.assertEqual(self.choice.widget.toolTip(), "Status: Locked")

    def test_the_icon_is_tinted_only_while_the_list_is_narrowed(self):
        self.assertIsNone(self.tint(), "the default reads as the theme glyph")
        self.pick("Locked")
        self.assertEqual(
            self.tint(), IconManager._normalize_color(ChoiceOption.ACTIVE_COLOR)
        )
        self.pick("Any status")
        self.assertIsNone(self.tint())

    def test_the_popup_marks_the_value_in_effect_and_keeps_separators(self):
        self.pick("Locked")
        rows = {r.text(): r for r in self.rows()}
        self.assertEqual(set(rows), {"Any status", "Locked"})
        self.assertTrue(rows["Locked"].property("marked"), "the current row is marked")
        self.assertFalse(rows["Any status"].property("marked"))
        self.assertEqual(rows["Locked"].toolTip(), "Can't be saved over")
        menu = self.choice.build_menu()
        self.addCleanup(menu.dispose)
        kinds = [type(w).__name__ for w in menu.list._row_widgets()]
        self.assertIn("Separator", kinds)

    def test_choices_are_read_each_time_the_popup_opens(self):
        self.items.append(("Built-in", "builtin"))
        self.pick("Built-in")
        self.assertEqual(self.choice.value, "builtin")

    def test_a_value_no_longer_offered_falls_back_on_refresh(self):
        self.pick("Locked")
        del self.items[2]
        self.choice.refresh()
        self.assertEqual(self.choice.value, "any")
        self.assertEqual(self.picked, ["locked", "any"])
        self.assertIsNone(self.tint())

    def test_restore_default_is_a_field_reset(self):
        self.pick("Locked")
        self.choice.restore_default()
        self.assertEqual(self.choice.value, "any")
        self.assertEqual(self.settings.value("filter.status"), "any")

    def test_the_persisted_value_is_restored_on_construction(self):
        field = LineEdit()
        self.track_widget(field)
        again = field.option_box.add_choice(
            icon="lock",
            label="Status",
            choices=self.items,
            default="any",
            settings=_DictSettings({"filter.status": "locked"}),
            settings_key="filter.status",
        )
        self.assertEqual(again.value, "locked")
        self.assertTrue(again.is_active)

    def test_a_bare_value_is_its_own_label(self):
        self.items.append("hero")
        self.pick("hero")
        self.assertEqual(self.choice.value, "hero")
        self.assertEqual(self.choice.widget.toolTip(), "Status: hero")

    def test_set_value_is_silent_unless_asked(self):
        self.choice.set_value("locked")
        self.assertEqual(self.picked, [])
        self.choice.set_value("any", notify=True)
        self.assertEqual(self.picked, ["any"])

    def test_facets_stack_after_the_filter_toggle(self):
        field = LineEdit()
        self.track_widget(field)
        box = field.option_box
        box.set_filter(settings=_DictSettings(), text_key="t", on_changed=lambda: None)
        first = box.add_choice(icon="stack", label="A", choices=["a"])
        second = box.add_choice(icon="tag", label="B", choices=["b"])
        order = box.container._option_box._sort_options()
        self.assertIsInstance(order[0], FilterOption)
        self.assertEqual(order[1:], [first, second])


class MultiChoiceOptionTest(QtBaseTestCase):
    """``multi=True``: toggles in a popup that stays open; ANY-of picks."""

    def setUp(self):
        super().setUp()
        self.window = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(self.window)
        self.field = LineEdit()
        layout.addWidget(self.field)
        self.settings = _DictSettings()
        self.picked = []
        self.items = [
            ("Any status", "any"),
            None,
            ("Locked", "locked"),
            ("Editable", "unlocked"),
            ("Built-in", "builtin"),
        ]
        self.choice = self.field.option_box.add_choice(
            icon="lock",
            label="Status",
            choices=lambda: self.items,
            default="any",
            multi=True,
            on_changed=self.picked.append,
            settings=self.settings,
            settings_key="filter.status",
        )
        layout.addWidget(self.field.option_box.container)
        self.window.show()

    def open_menu(self):
        menu = self.choice.build_menu()
        self.addCleanup(menu.dispose)
        menu.popup(self.window.mapToGlobal(QtCore.QPoint(10, 10)))
        QtWait.until(lambda: menu.isVisible(), "popup never showed")
        rows = {
            w.text(): w
            for w in menu.list._row_widgets()
            if isinstance(w, QtWidgets.QPushButton)
        }
        return menu, rows

    def interact(self, menu, row):
        """What a click on the row does: the list reports it to the menu."""
        menu.list.on_item_interacted.emit(row)

    def test_several_rows_are_picked_in_one_visit(self):
        menu, rows = self.open_menu()
        self.interact(menu, rows["Locked"])
        self.interact(menu, rows["Built-in"])
        self.assertTrue(menu.isVisible(), "the popup stays open for the next pick")
        self.assertEqual(self.choice.value, ("locked", "builtin"))
        self.assertEqual(self.picked, [("locked",), ("locked", "builtin")])
        marked = {t for t, r in rows.items() if r.property("marked")}
        self.assertEqual(marked, {"Locked", "Built-in"})
        self.assertEqual(self.choice.widget.toolTip(), "Status: Locked, Built-in")
        self.assertEqual(
            (IconManager.registered_info(self.choice.widget) or {}).get("color"),
            IconManager._normalize_color(ChoiceOption.ACTIVE_COLOR),
        )

    def test_a_second_click_unpicks_and_the_any_row_clears(self):
        menu, rows = self.open_menu()
        self.assertTrue(rows["Any status"].property("marked"), "nothing picked yet")
        self.interact(menu, rows["Locked"])
        self.interact(menu, rows["Editable"])
        self.interact(menu, rows["Locked"])
        self.assertEqual(self.choice.value, ("unlocked",))
        self.interact(menu, rows["Any status"])
        self.assertEqual(self.choice.value, ())
        self.assertFalse(self.choice.is_active)
        self.assertTrue(rows["Any status"].property("marked"))
        self.assertEqual(self.choice.widget.toolTip(), "Status: Any status")

    def test_picks_persist_as_a_list_and_come_back(self):
        self.choice.set_value(["locked", "builtin"])
        self.assertEqual(self.settings.value("filter.status"), ["locked", "builtin"])
        for stored in (["locked", "builtin"], '["locked", "builtin"]'):
            field = self.track_widget(LineEdit())
            again = field.option_box.add_choice(
                label="Status",
                choices=self.items,
                default="any",
                multi=True,
                settings=_DictSettings({"filter.status": stored}),
                settings_key="filter.status",
            )
            self.assertEqual(again.value, ("locked", "builtin"))

    def test_a_single_pick_saved_before_multi_comes_back_as_one_pick(self):
        for stored, expected in (
            ("locked", ("locked",)),
            ("any", ()),
            ("5", ("5",)),  # a string that happens to parse as JSON stays one
            ("", ()),  # what a raw QSettings may hand back for []
        ):
            field = self.track_widget(LineEdit())
            again = field.option_box.add_choice(
                label="Status",
                choices=self.items,
                default="any",
                multi=True,
                settings=_DictSettings({"filter.status": stored}),
                settings_key="filter.status",
            )
            self.assertEqual(again.value, expected)

    def test_refresh_drops_only_the_picks_no_longer_offered(self):
        self.choice.set_value(("locked", "builtin"))
        del self.items[-1]
        self.choice.refresh()
        self.assertEqual(self.choice.value, ("locked",))
        self.assertEqual(self.picked, [("locked",)])

    def test_restore_default_clears_every_pick(self):
        self.choice.set_value(("locked", "builtin"))
        self.choice.restore_default()
        self.assertEqual(self.choice.value, ())


class ExcludeChoiceOptionTest(MultiChoiceOptionTest):
    """``exclude=True``: a show list -- ticked rows are shown, the value is
    what is left out."""

    def setUp(self):
        QtBaseTestCase.setUp(self)
        self.window = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(self.window)
        self.field = LineEdit()
        layout.addWidget(self.field)
        self.settings = _DictSettings()
        self.picked = []
        self.items = [
            ("Show all", "all"),
            ChoiceOption.Section("Kind"),
            ("Locked", "locked"),
            ("Built-in", "builtin"),
            ChoiceOption.Section("Tags"),
            "hero",
        ]
        self.choice = self.field.option_box.add_choice(
            icon="eye",
            label="Show",
            choices=lambda: self.items,
            default="all",
            exclude=True,
            on_changed=self.picked.append,
            settings=self.settings,
            settings_key="filter.show",
        )
        layout.addWidget(self.field.option_box.container)
        self.window.show()

    # The inherited ANY-of tests read picks as ticks; a show list reads the
    # other way, so they are replaced here.
    test_several_rows_are_picked_in_one_visit = None
    test_a_second_click_unpicks_and_the_any_row_clears = None
    test_picks_persist_as_a_list_and_come_back = None
    test_a_single_pick_saved_before_multi_comes_back_as_one_pick = None

    def test_everything_is_ticked_until_a_row_is_left_out(self):
        menu, rows = self.open_menu()
        marked = {t for t, r in rows.items() if r.property("marked")}
        self.assertEqual(marked, {"Show all", "Locked", "Built-in", "hero"})
        self.interact(menu, rows["Built-in"])
        self.interact(menu, rows["hero"])
        self.assertTrue(menu.isVisible(), "the popup stays open for the next flip")
        self.assertEqual(self.choice.value, ("builtin", "hero"))
        marked = {t for t, r in rows.items() if r.property("marked")}
        self.assertEqual(marked, {"Locked"})
        self.assertEqual(self.choice.widget.toolTip(), "Show: all but Built-in, hero")
        self.assertTrue(self.choice.is_active)
        self.assertEqual(self.settings.value("filter.show"), ["builtin", "hero"])

    def test_show_all_brings_every_row_back(self):
        menu, rows = self.open_menu()
        self.interact(menu, rows["Locked"])
        self.interact(menu, rows["Locked"])
        self.assertEqual(self.choice.value, ())
        self.interact(menu, rows["Built-in"])
        self.interact(menu, rows["Show all"])
        self.assertEqual(self.choice.value, ())
        self.assertFalse(self.choice.is_active)
        self.assertEqual(self.choice.widget.toolTip(), "Show: Show all")

    def test_refresh_drops_only_the_picks_no_longer_offered(self):
        self.choice.set_value(("locked", "hero"))
        del self.items[-1]  # the tag went: its row is gone, so is its exclusion
        self.choice.refresh()
        self.assertEqual(self.choice.value, ("locked",))
        self.assertEqual(self.picked, [("locked",)])

    def test_sections_caption_their_rows_and_are_not_choices(self):
        menu, _rows = self.open_menu()
        captions = [
            w.getTitle()
            for w in menu.list._row_widgets()
            if type(w).__name__ == "Separator"
        ]
        self.assertEqual(captions, ["Show", "Kind", "Tags"])
        self.assertEqual(
            self.choice.choice_values(), ["all", "locked", "builtin", "hero"]
        )


if __name__ == "__main__":
    unittest.main()
