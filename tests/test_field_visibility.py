# !/usr/bin/python
# coding=utf-8
"""Which fields a container shows, per named mode."""

import unittest

from qtpy import QtWidgets

from conftest import QtBaseTestCase, setup_qt_application

setup_qt_application()


class _Host(QtWidgets.QWidget):
    """A panel with three rows in two sections, a divider each, and a group."""

    def __init__(self):
        super().__init__()
        box = QtWidgets.QVBoxLayout(self)
        self.group = QtWidgets.QWidget(self)
        inner = QtWidgets.QVBoxLayout(self.group)
        box.addWidget(self.group)
        self.rules = {}
        self.rows = {}
        for section, keys in (("timing", ("length", "period")), ("look", ("colour",))):
            rule = QtWidgets.QLabel(section, self.group)
            inner.addWidget(rule)
            self.rules[section] = rule
            for key in keys:
                row = QtWidgets.QLabel(key, self.group)
                inner.addWidget(row)
                self.rows[key] = row


class FieldVisibilityTestCase(QtBaseTestCase):
    def _fields(self, **kw):
        from uitk import FieldVisibility

        self.host = self.track_widget(_Host())
        fields = FieldVisibility(**kw)
        for section, keys in (("timing", ("length", "period")), ("look", ("colour",))):
            for key in keys:
                fields.register(key, self.host.rows[key], section=section)
            fields.divider(section, self.host.rules[section])
        fields.group(self.host.group)
        fields.define("create", ("length", "period", "colour"))
        fields.define("revise", ("colour",))
        self.host.show()
        return fields


class TestNamedModes(FieldVisibilityTestCase):
    def test_a_mode_shows_exactly_what_it_names(self):
        fields = self._fields()
        fields.mode = "revise"

        self.assertFalse(self.host.rows["length"].isVisible())
        self.assertTrue(self.host.rows["colour"].isVisible())

    def test_switching_back_restores_the_rest(self):
        fields = self._fields()
        fields.mode = "revise"
        fields.mode = "create"

        self.assertTrue(all(row.isVisible() for row in self.host.rows.values()))

    def test_an_unknown_mode_shows_nothing_rather_than_raising(self):
        """Driven by a combo box: which fields are on screen must never be
        what stops a panel from building."""
        fields = self._fields()
        fields.mode = "sideways"

        self.assertEqual(fields.visible, ())

    def test_adding_a_mode_is_adding_a_row(self):
        """Nothing in the class branches on which modes exist."""
        fields = self._fields()
        fields.define("timing-only", ("length", "period"))
        fields.mode = "timing-only"

        self.assertEqual(set(fields.visible), {"length", "period"})

    def test_redefining_the_current_mode_takes_effect_when_it_is_re_applied(self):
        fields = self._fields()
        fields.mode = "create"
        fields.define("create", ("colour",))

        fields.mode = "create"

        self.assertEqual(set(fields.visible), {"colour"})

    def test_redefining_a_mode_does_not_rewrite_what_is_on_screen(self):
        """The applied set is a copy: a mode hands in the set it keeps."""
        fields = self._fields()
        fields.mode = "revise"
        fields.define("revise", ("length", "period", "colour"))

        self.assertEqual(set(fields.visible), {"colour"}, "until it is re-applied")

    def test_keys_report_what_it_is_in_a_position_to_hide(self):
        """A tool that gates nothing registers nothing, and says so."""
        from uitk import FieldVisibility

        self.assertEqual(FieldVisibility().keys, ())
        self.assertEqual(
            set(self._fields().keys), {"length", "period", "colour"}, "dividers aside"
        )

    def test_unregistered_widgets_are_left_alone(self):
        """It gates part of a panel without owning all of it."""
        from uitk import FieldVisibility

        host = self.track_widget(_Host())
        fields = FieldVisibility()
        fields.register("colour", host.rows["colour"])
        fields.define("none", ())
        host.show()

        fields.mode = "none"

        self.assertFalse(host.rows["colour"].isVisible())
        self.assertTrue(host.rows["length"].isVisible(), "never registered")


class TestFieldsNamedDirectly(FieldVisibilityTestCase):
    """A tool whose modes are fixed has no keys of its own to invent."""

    def test_a_mode_can_name_the_widgets_themselves(self):
        from uitk import FieldVisibility

        host = self.track_widget(_Host())
        fields = FieldVisibility()
        fields.define("numeric", [host.rows["length"], host.rows["period"]])
        fields.define("enum", [host.rows["colour"]])
        host.show()

        fields.mode = "enum"

        self.assertFalse(host.rows["length"].isVisible())
        self.assertTrue(host.rows["colour"].isVisible())

    def test_a_widget_named_by_two_modes_is_one_registration(self):
        """Keying on the widget itself: a second entry for the same widget
        must not be able to hide it while the mode showing it is current."""
        from uitk import FieldVisibility

        host = self.track_widget(_Host())
        fields = FieldVisibility()
        shared, only_numeric = host.rows["length"], host.rows["period"]
        fields.define("numeric", [shared, only_numeric])
        fields.define("enum", [shared])
        host.show()

        fields.mode = "numeric"
        self.assertTrue(shared.isVisible())

        fields.mode = "enum"
        self.assertTrue(shared.isVisible())
        self.assertFalse(only_numeric.isVisible())


class TestInsideAMenu(QtBaseTestCase):
    """The shape the option-box tools build: a form whose type combo says
    which rows it has. Exercised against a real ``Menu``, since that is what
    ``menu.add`` hands back, and the window the default fit resolves to."""

    def test_a_menu_form_shows_the_rows_its_type_names(self):
        from uitk import FieldVisibility
        from uitk.widgets.menu import Menu

        menu = self.track_widget(Menu())
        sep = menu.add("Separator", setTitle="Range")
        spn = menu.add("QDoubleSpinBox", setObjectName="spn_min")
        le = menu.add("QLineEdit", setObjectName="le_enum")
        cmb = menu.add("QComboBox", addItems=["float", "string", "enum"])

        # No fit stated: the menu IS the window these fields are in.
        fields = FieldVisibility()
        for numeric in ("float", "double3"):
            fields.define(numeric, [sep, spn])
        fields.define("enum", [le])
        fields.bind(cmb)
        menu.show()

        self.assertTrue(spn.isVisible(), "float opens the range rows")
        self.assertFalse(le.isVisible())

        cmb.setCurrentIndex(1)  # a type that names no fields
        self.assertFalse(spn.isVisible())
        self.assertFalse(le.isVisible())

        cmb.setCurrentIndex(2)
        self.assertTrue(le.isVisible())
        self.assertFalse(sep.isVisible(), "the rule goes with its rows")


class TestBookkeeping(FieldVisibilityTestCase):
    """What hand-rolled versions forget."""

    def test_a_divider_stands_down_with_its_whole_section(self):
        """A titled rule over rows the mode hides reads as an empty category
        rather than as nothing at all."""
        fields = self._fields()
        fields.mode = "revise"  # timing hidden, look shown

        self.assertFalse(self.host.rules["timing"].isVisible())
        self.assertTrue(self.host.rules["look"].isVisible())

    def test_a_divider_stands_while_any_of_its_section_shows(self):
        fields = self._fields()
        fields.define("partial", ("length",))
        fields.mode = "partial"

        self.assertTrue(self.host.rules["timing"].isVisible())
        self.assertFalse(self.host.rules["look"].isVisible())

    def test_an_empty_group_hides(self):
        fields = self._fields()
        fields.define("nothing", ())
        fields.mode = "nothing"

        self.assertFalse(self.host.group.isVisible())

    def test_a_group_hides_on_what_shows_not_on_what_was_asked_for(self):
        """A mode naming only keys this registry never got is an empty group,
        and leaving it up is the same stray-frame problem the dividers have."""
        fields = self._fields()
        fields.show(["a key nobody registered"])

        self.assertFalse(self.host.group.isVisible())


class TestOneKeyAtATime(FieldVisibilityTestCase):
    """The rule-driven form (2026-09-14): a dependency rule decides ONE key,
    not a whole mode, and the divider/group bookkeeping still follows."""

    def test_set_visible_toggles_one_key_and_keeps_the_rest(self):
        fields = self._fields()
        fields.show(fields.keys)
        self.assertTrue(fields.set_visible("length", False))
        self.assertFalse(self.host.rows["length"].isVisible())
        self.assertTrue(self.host.rows["period"].isVisible())
        self.assertTrue(self.host.rules["timing"].isVisible(), "period still shows")
        fields.set_visible("period", False)
        self.assertFalse(self.host.rules["timing"].isVisible(), "whole section gone")
        fields.set_visible("length", True)
        self.assertTrue(self.host.rules["timing"].isVisible())
        self.assertEqual(set(fields.visible), {"length", "colour"})
        self.assertIsNone(fields.mode, "a per-key change is not a named mode")

    def test_an_unregistered_key_is_declined_not_raised(self):
        fields = self._fields()
        fields.show(fields.keys)
        self.assertFalse(fields.set_visible("nope", False))
        self.assertEqual(set(fields.visible), {"length", "period", "colour"})

    def test_set_visible_touches_only_the_key_it_names(self):
        """Re-applying every row per rule was one widget write per row per
        firing -- and a WidgetComboBox row finds its model row by a scan, so
        rules over an option menu cost O(rows^2)."""
        fields = self._fields()
        fields.show(fields.keys)
        touched = []
        for key, row in self.host.rows.items():
            real = row.setVisible
            row.setVisible = lambda on, _k=key, _r=real: (touched.append(_k), _r(on))
        fields.set_visible("length", False)
        self.assertEqual(touched, ["length"])

    def test_one_key_at_a_time_still_rolls_up_the_captions_and_the_group(self):
        fields = self._fields()
        fields.show(fields.keys)
        for key in ("length", "period", "colour"):
            fields.set_visible(key, False)
        self.assertFalse(self.host.group.isVisible(), "nothing is showing")
        fields.set_visible("colour", True)
        self.assertTrue(self.host.group.isVisible())
        self.assertTrue(self.host.rules["look"].isVisible())
        self.assertFalse(self.host.rules["timing"].isVisible())


class TestRefit(FieldVisibilityTestCase):
    """The host is re-measured after the fields settle, never before."""

    def test_the_build_pass_never_fits(self):
        """It runs while the tool is still building, and the host has not been
        shown to have a size worth correcting."""
        calls = []
        fields = self._fields(fit=lambda: calls.append(1))
        fields.mode = "create"

        self.assertEqual(calls, [])

    def test_a_later_change_fits_on_the_next_turn_of_the_loop(self):
        """Deferred: a container asked to re-measure while it is still hiding
        children measures the layout it is leaving."""
        from qtpy import QtCore

        calls = []
        fields = self._fields(fit=lambda: calls.append(1))
        fields.mode = "create"  # the build pass
        fields.mode = "revise"

        self.assertEqual(calls, [], "not synchronously")
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(30, loop.quit)
        loop.exec_() if hasattr(loop, "exec_") else loop.exec()
        self.assertEqual(calls, [1])

    def test_the_host_is_fitted_without_the_tool_stating_how(self):
        """The default: a tool that says nothing still gets its window
        managed as fields come and go, because the registry can resolve the
        window from any field it holds."""
        from qtpy import QtCore

        fields = self._fields()
        fields.mode = "create"  # the build pass
        self.host.resize(self.host.width(), 400)
        QtWidgets.QApplication.processEvents()

        fields.mode = "revise"  # two of the three rows go

        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(30, loop.quit)
        loop.exec_() if hasattr(loop, "exec_") else loop.exec()
        self.assertLess(self.host.height(), 400, "the window kept the taller mode")


class TestDrivers(FieldVisibilityTestCase):
    """How the decision reaches it."""

    def test_a_combo_carrying_data_drives_by_data(self):
        fields = self._fields()
        combo = self.track_widget(QtWidgets.QComboBox())
        for text, data in (("Create", "create"), ("Revise", "revise")):
            combo.addItem(text, data)
        fields.bind(combo)

        combo.setCurrentIndex(1)

        self.assertEqual(fields.mode, "revise")

    def test_a_combo_carrying_plain_labels_drives_by_text(self):
        """Both spellings are in use across this repo's tools."""
        fields = self._fields()
        fields.define("Revise", ("colour",))
        combo = self.track_widget(QtWidgets.QComboBox())
        combo.addItems(["Create", "Revise"])
        fields.bind(combo)

        combo.setCurrentIndex(1)

        self.assertEqual(fields.mode, "Revise")

    def test_binding_applies_the_combos_opening_entry(self):
        fields = self._fields()
        combo = self.track_widget(QtWidgets.QComboBox())
        combo.addItem("Revise", "revise")
        fields.bind(combo)

        self.assertEqual(set(fields.visible), {"colour"})

    def test_several_labels_can_name_one_set_of_fields(self):
        """A type combo whose numeric entries all want the same rows: the
        mapping is rows in the table, not a predicate in a handler."""
        fields = self._fields()
        for label in ("float", "int", "double3"):
            fields.define(label, ("length", "period"))
        combo = self.track_widget(QtWidgets.QComboBox())
        combo.addItems(["float", "string", "int"])
        fields.bind(combo)

        combo.setCurrentIndex(1)
        self.assertEqual(fields.visible, (), "a type that names no fields")

        combo.setCurrentIndex(2)
        self.assertEqual(set(fields.visible), {"length", "period"})

    def test_a_combo_carrying_settings_as_data_still_drives_by_text(self):
        """An entry's data is the tool's payload, not necessarily a name: a
        dict of settings cannot be a key, and must not raise out of the
        signal that carries it."""
        fields = self._fields()
        combo = self.track_widget(QtWidgets.QComboBox())
        for text in ("create", "revise"):
            combo.addItem(text, {"mode": text})
        fields.bind(combo)

        combo.setCurrentIndex(1)

        self.assertEqual(fields.mode, "revise")
        self.assertEqual(set(fields.visible), {"colour"})

    def test_a_computed_set_needs_no_stored_mode(self):
        """The dynamic form: a tool deriving its fields from a template file
        and one with fixed modes use the same mechanism."""
        fields = self._fields()

        fields.show({"length", "colour"})

        self.assertEqual(set(fields.visible), {"length", "colour"})
        self.assertIsNone(fields.mode, "nothing named this set")

    def test_on_change_reports_the_new_mode(self):
        seen = []
        fields = self._fields(on_change=seen.append)
        fields.mode = "revise"
        fields.show(("colour",))

        self.assertEqual(seen, ["revise", None])


if __name__ == "__main__":
    unittest.main()
