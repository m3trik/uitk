# !/usr/bin/python
# coding=utf-8
"""Unit tests for NamingConventionEditor.

The editor is generic over the ``pythontk.NamingConvention`` protocol, so most
of these run against a small in-memory convention (no user config touched): the
rows it builds (from the convention by default, from host groups when given),
the label beside every field, the write-back of a text or placement edit, the
greyed-but-wired disabled rows, and the semantic presets. One test builds over
the real ``pythontk.NamingConvention`` inside a config sandbox.

Run standalone: python -m test.test_naming_convention_editor
"""

import os
import unittest

from conftest import PRESETS_SANDBOX_DIR, QtBaseTestCase, setup_qt_application

app = setup_qt_application()

import pythontk as ptk
from qtpy import QtWidgets

from uitk.widgets.menu import Menu
from uitk import AffixOption
from uitk.widgets.editors.naming_convention_editor import NamingConventionEditor


class _Rule:
    def __init__(self, text="", mode="auto", label=""):
        self.text, self.mode, self.label = text, mode, label


def _convention(**entries):
    """A fresh in-memory convention class: ``key=(text, label)``."""

    class Convention:
        table = {k: _Rule(t, "auto", lbl) for k, (t, lbl) in entries.items()}
        writes = []

        @classmethod
        def keys(cls):
            return list(cls.table)

        @classmethod
        def get(cls, key):
            return cls.table.get(key) or _Rule(label=key)

        @classmethod
        def label(cls, key):
            return cls.get(key).label or key

        @classmethod
        def set(cls, key, text, mode="auto"):
            cls.writes.append((key, text, mode))
            label = cls.get(key).label
            cls.table[key] = _Rule(text, mode, label)

        @classmethod
        def update(cls, mapping):
            for key, value in mapping.items():
                if isinstance(value, str):
                    value = {"text": value}
                cls.set(key, value.get("text", ""), value.get("mode", "auto"))

        @classmethod
        def as_dict(cls):
            return {k: {"text": r.text, "mode": r.mode} for k, r in cls.table.items()}

        @staticmethod
        def preset_store():
            class Store:
                user_dir = os.path.join(PRESETS_SANDBOX_DIR, "convention_presets")

            return Store

    return Convention


class TestNamingConventionEditor(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.conv = _convention(
            mesh=("_GEO", "Mesh"), camera=("_CAM", "Camera"), light=("_LGT", "Light")
        )
        self.menu = self.track_widget(Menu())

    def _label_beside(self, field):
        grid = self.menu.gridLayout
        for i in range(grid.count()):
            held = grid.itemAt(i).widget()
            if held is not None and (held is field or held.isAncestorOf(field)):
                row, col = grid.getItemPosition(i)[:2]
                self.assertEqual(col, 0, "the field sits in the first column")
                return grid.itemAtPosition(row, 1).widget()
        self.fail("field not in the grid")

    def test_default_rows_come_from_the_convention(self):
        editor = NamingConventionEditor(
            self.menu, convention=self.conv, presets=False
        ).build()
        rows = list(editor.fields())
        self.assertEqual([k for k, _f in rows], ["mesh", "camera", "light"])
        for key, field in rows:
            with self.subTest(key=key):
                self.assertIs(getattr(self.menu, key), field)
                self.assertEqual(field.text(), self.conv.get(key).text)
                label = self._label_beside(field)
                self.assertIsInstance(label, QtWidgets.QLabel)
                self.assertEqual(label.text(), self.conv.label(key))

    def test_host_groups_name_and_order_the_rows(self):
        groups = (
            ("Lights", (("light", "txt_light"),)),
            ("Shapes", (("mesh", "txt_mesh"), ("camera", "txt_cam"))),
        )
        editor = NamingConventionEditor(
            self.menu, groups, convention=self.conv, presets=False
        ).build()
        self.assertEqual(
            [(k, f.objectName()) for k, f in editor.fields()],
            [("light", "txt_light"), ("mesh", "txt_mesh"), ("camera", "txt_cam")],
        )
        self.assertEqual(self.menu.txt_mesh.text(), "_GEO")

    def test_a_text_edit_writes_the_convention_delimited(self):
        editor = NamingConventionEditor(
            self.menu, convention=self.conv, presets=False
        ).build()
        field = dict(editor.fields())["mesh"]
        field.setText("MSH")
        field.editingFinished.emit()
        self.assertEqual(self.conv.get("mesh").text, "_MSH")
        self.assertEqual(field.text(), "_MSH", "the stored spelling is shown")

    def test_an_unchanged_row_writes_nothing(self):
        editor = NamingConventionEditor(
            self.menu, convention=self.conv, presets=False
        ).build()
        dict(editor.fields())["mesh"].editingFinished.emit()
        self.assertEqual(self.conv.writes, [])

    def test_a_placement_change_writes_the_mode(self):
        editor = NamingConventionEditor(
            self.menu, convention=self.conv, presets=False
        ).build()
        field = dict(editor.fields())["camera"]
        picker = field.option_box.find_option(AffixOption)
        self.assertIsNotNone(picker, "every row gets a placement picker")
        picker.widget  # build the button: on_change fires from a built picker
        picker.set_mode("prefix")
        self.assertEqual(
            (self.conv.get("camera").text, self.conv.get("camera").mode),
            ("CAM_", "prefix"),
        )

    def test_fields_do_not_persist_their_own_state(self):
        editor = NamingConventionEditor(
            self.menu, convention=self.conv, presets=False
        ).build()
        for _key, field in editor.fields():
            self.assertIs(field.restore_state, False)

    def test_disabled_rows_are_greyed_explained_and_still_wired(self):
        editor = NamingConventionEditor(
            self.menu,
            convention=self.conv,
            disabled={"camera": "No camera type here."},
            presets=False,
        ).build()
        fields = dict(editor.fields())
        cam = fields["camera"]
        self.assertFalse(cam.isEnabled())
        self.assertEqual(cam.toolTip(), "No camera type here.")
        self.assertFalse(self._label_beside(cam).isEnabled())
        self.assertTrue(fields["mesh"].isEnabled())
        cam.setText("_CAMERA")
        cam.editingFinished.emit()
        self.assertEqual(self.conv.get("camera").text, "_CAMERA")

    def test_tooltip_callable_receives_key_and_label(self):
        editor = NamingConventionEditor(
            self.menu,
            convention=self.conv,
            tooltip=lambda key, label: f"{key}:{label}",
            presets=False,
        ).build()
        self.assertEqual(dict(editor.fields())["light"].toolTip(), "light:Light")

    def test_presets_are_the_convention_snapshot(self):
        editor = NamingConventionEditor(self.menu, convention=self.conv).build()
        presets = self.menu.presets
        self.assertTrue(self.menu.add_presets)
        self.assertEqual(presets.value_provider, self.conv.as_dict)
        self.assertEqual(presets.value_applier, editor.apply_preset)
        self.assertEqual(
            os.path.normpath(str(presets.preset_dir)),
            os.path.normpath(os.path.join(PRESETS_SANDBOX_DIR, "convention_presets")),
        )

    def test_apply_preset_writes_the_convention_and_shows_it(self):
        editor = NamingConventionEditor(
            self.menu, convention=self.conv, presets=False
        ).build()
        field = dict(editor.fields())["mesh"]
        picker = field.option_box.find_option(AffixOption)
        picker.widget
        n = editor.apply_preset(
            {"mesh": {"text": "GEO_", "mode": "prefix"}, "light": "_L", "junk": 3}
        )
        self.assertEqual(n, 2, "non-rule values are skipped")
        self.assertEqual(self.conv.get("mesh").mode, "prefix")
        self.assertEqual(field.text(), "GEO_")
        self.assertEqual(picker.mode, "prefix")
        self.assertEqual(dict(editor.fields())["light"].text(), "_L")

    def test_fields_are_the_rows_this_editor_built(self):
        """``fields()`` returns the rows built here -- one added through
        ``add_row`` included -- never a ``Menu`` member that shares a row's
        objectName.

        Regression: rows were looked up with ``getattr(menu, object_name)``. A
        convention key named like a ``Menu`` member (``render``, ``layout``,
        ``size`` -- default rows are named after their key) yielded that
        METHOD, so a preset load raised ``AttributeError`` after it had
        already rewritten the convention; and an ``add_row`` row was never
        returned, so a preset load left it showing the old spelling.
        """
        conv = _convention(mesh=("_GEO", "Mesh"), render=("_RL", "Render Layer"))
        editor = NamingConventionEditor(
            self.menu, convention=conv, presets=False
        ).build()
        extra = editor.add_row("camera", "txt_cam")
        rows = list(editor.fields())
        self.assertEqual([k for k, _f in rows], ["mesh", "render", "camera"])
        for key, field in rows:
            with self.subTest(key=key):
                self.assertIsInstance(field, QtWidgets.QLineEdit)
        self.assertIs(dict(rows)["camera"], extra)
        editor.apply_preset({"mesh": "_MSH", "render": "_RLY", "camera": "_CAMX"})
        self.assertEqual(dict(rows)["render"].text(), "_RLY")
        self.assertEqual(extra.text(), "_CAMX")

    def test_edits_the_real_naming_convention_by_default(self):
        """No convention passed: pythontk's, every entry a row."""
        with ptk.TestSandbox.user_config():
            ptk.NamingConvention.reload()
            try:
                editor = NamingConventionEditor(self.menu, presets=False).build()
                rows = dict(editor.fields())
                self.assertEqual(list(rows), ptk.NamingConvention.keys())
                self.assertEqual(rows["mesh"].text(), "_GEO")
                rows["mesh"].setText("_MSH")
                rows["mesh"].editingFinished.emit()
                self.assertEqual(ptk.NamingConvention.affix("mesh"), "_MSH")
            finally:
                ptk.NamingConvention.reload()


if __name__ == "__main__":
    unittest.main()
