# !/usr/bin/python
# coding=utf-8
"""Unit tests for ``uitk.widgets.form_rows.FormRows`` and
``uitk.managers.model_binding.ModelBinding``.

``FormRows`` is WindowPanel's form region lifted out so any layout can hold
one (a page of a stacked panel); ``ModelBinding`` keeps widgets in step with a
model uitk never sees. Both are what an embedded effect page is made of.

Run standalone: python -m test.test_form_rows
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets

from uitk.managers.model_binding import ModelBinding
from uitk.widgets.form_rows import FormRows
from uitk.widgets.windowPanel import WindowPanel


class TestFormRows(QtBaseTestCase):
    def _host(self):
        host = QtWidgets.QWidget()
        self.addCleanup(host.deleteLater)
        layout = QtWidgets.QVBoxLayout(host)
        rows = FormRows(host)
        layout.addWidget(rows)
        return host, rows

    def test_sits_inside_any_layout(self):
        host, rows = self._host()
        self.assertIs(rows.parent(), host)
        self.assertFalse(rows.isWindow())

    def test_add_is_the_menu_idiom(self):
        _host, rows = self._host()
        spin = rows.add(
            "QSpinBox", label="Frames", setObjectName="spn_frames", setValue=12
        )
        self.assertIs(rows.spn_frames, spin)
        self.assertEqual(spin.value(), 12)
        caption = rows.rows_layout.itemAt(0, QtWidgets.QFormLayout.LabelRole)
        self.assertEqual(caption.widget().text(), "Frames")

    def test_companions_share_the_cell_and_grey_with_it(self):
        _host, rows = self._host()
        side = QtWidgets.QPushButton("x")
        key = rows.add("QPushButton", setText="Key", companions=[side])
        self.assertEqual(rows.row_widgets(key), [side])

    def test_never_shadows_its_own_api(self):
        _host, rows = self._host()
        rows.add("QPushButton", setObjectName="add")
        self.assertTrue(callable(rows.add))

    def test_clear_rows_drops_widgets_and_names(self):
        _host, rows = self._host()
        rows.add("QCheckBox", setObjectName="chk_a")
        rows.clear_rows()
        self.assertFalse(hasattr(rows, "chk_a"))
        self.assertEqual(rows.rows_layout.count(), 0)

    def test_a_section_folds_its_rows_and_exposes_them_on_the_form(self):
        from uitk.widgets.collapsableGroup import CollapsableGroup

        _host, rows = self._host()
        section = rows.add_section("Settings", setObjectName="grp_settings")
        spin = section.add("QSpinBox", setObjectName="spn_frames")
        group = section.parentWidget()
        self.assertIsInstance(group, CollapsableGroup)
        self.assertEqual(group.layout().contentsMargins().left(), 0, "flush")
        self.assertIs(rows.grp_settings, group)
        self.assertIs(rows.spn_frames, spin, "a field reads the same either side")
        group.setChecked(False)
        self.assertTrue(section.isHidden())
        group.setChecked(True)
        self.assertFalse(section.isHidden())

    def test_a_fold_leaves_a_mode_hidden_field_hidden(self):
        """The fold hides the section whole; a field a mode hid stays hidden
        when the fold opens again."""
        from uitk.managers.field_visibility import FieldVisibility

        _host, rows = self._host()
        section = rows.add_section("Settings")
        kept = section.add("QSpinBox")
        gone = section.add("QCheckBox")
        FieldVisibility.set_widget_visible(gone, False)
        group = section.parentWidget()
        group.setChecked(False)
        group.setChecked(True)
        self.assertFalse(kept.isHidden())
        self.assertTrue(gone.isHidden())

    def test_clearing_a_section_drops_its_names_from_the_form(self):
        _host, rows = self._host()
        section = rows.add_section("Settings")
        section.add("QCheckBox", setObjectName="chk_a")
        section.clear_rows()
        self.assertFalse(hasattr(rows, "chk_a"))
        section = rows.add_section("More")
        section.add("QCheckBox", setObjectName="chk_b")
        rows.clear_rows()
        self.assertFalse(hasattr(rows, "chk_b"))

    def test_a_window_panel_holds_one_and_exposes_on_both(self):
        panel = WindowPanel(title="Probe")
        self.addCleanup(panel.deleteLater)
        chk = panel.add("QCheckBox", setObjectName="chk_dry")
        self.assertIsInstance(panel.form, FormRows)
        self.assertIs(panel.chk_dry, chk)
        self.assertIs(panel.form.chk_dry, chk)
        panel.clear_rows()
        self.assertFalse(hasattr(panel, "chk_dry"))


class TestModelBinding(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.model = {"period": 2.5, "duty": 0.5, "snap": True}
        self.writes = []
        self.binding = ModelBinding(
            read=lambda: dict(self.model),
            write=lambda field, value: (
                self.writes.append((field, value)),
                self.model.__setitem__(field, value),
            ),
        )

    def _spin(self, cls=QtWidgets.QDoubleSpinBox):
        w = cls()
        self.addCleanup(w.deleteLater)
        return w

    def test_refresh_fills_widgets_without_writing_back(self):
        period = self.binding.bind("period", self._spin())
        self.binding.refresh()
        self.assertEqual(period.value(), 2.5)
        self.assertEqual(self.writes, [])

    def test_an_edit_writes_the_model(self):
        period = self.binding.bind("period", self._spin())
        self.binding.refresh()
        period.setValue(3.0)
        self.assertEqual(self.writes, [("period", 3.0)])

    def test_converters_speak_the_models_terms(self):
        duty = self._spin(QtWidgets.QSpinBox)
        self.binding.bind(
            "duty",
            duty,
            getter=lambda: duty.value() / 100.0,
            setter=lambda v: duty.setValue(round(v * 100)),
        )
        self.binding.refresh()
        self.assertEqual(duty.value(), 50)
        duty.setValue(59)
        self.assertEqual(self.writes, [("duty", 0.59)])

    def test_a_bound_widget_opts_out_of_state_restore(self):
        chk = QtWidgets.QCheckBox()
        self.addCleanup(chk.deleteLater)
        self.binding.bind("snap", chk)
        self.assertFalse(chk.restore_state)

    def test_a_linked_edit_survives_the_refresh_its_write_causes(self):
        """Bug: the model announces every write, the panel refreshes on it, and
        an edit that moves a linked field with it was still landing -- the
        refresh put the first field back to the model's unwritten value.
        Fixed: 2026-10-03
        """
        self.model = {"lead_in": 0.72, "lead_out": 0.72}
        binding = ModelBinding(
            read=lambda: dict(self.model),
            write=lambda field, value: (
                self.model.__setitem__(field, value),
                binding.refresh(),  # the model announces the change
            ),
        )
        a, b = self._spin(), self._spin()
        # A link: editing one moves the other (connected first, as a lock is).
        a.valueChanged.connect(lambda v: b.setValue(v))
        binding.bind("lead_in", a)
        binding.bind("lead_out", b)
        binding.refresh()
        a.setValue(0.0)
        self.assertEqual(self.model, {"lead_in": 0.0, "lead_out": 0.0})
        self.assertEqual((a.value(), b.value()), (0.0, 0.0))

    def test_an_unknown_widget_needs_its_signal(self):
        with self.assertRaises(ValueError):
            self.binding.bind("period", QtWidgets.QLabel())


if __name__ == "__main__":
    unittest.main()
