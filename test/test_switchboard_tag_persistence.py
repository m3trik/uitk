# !/usr/bin/python
# coding=utf-8
"""Unit tests for Switchboard XML tag persistence (Designer-safe format).

Covers:
- _parse_ui_tags reads <property name="uitk_tags"> from a .ui file
- _parse_ui_tags handles missing property, missing root, malformed XML
- register() ingests XML tags into _ui_xml_tags and emits on_ui_registered
- save_ui_tags writes the property and atomically replaces the file
- save_ui_tags with empty tag set removes the property
- save_ui_tags emits on_ui_tags_changed and updates the live MainWindow.tags
- save_ui_tags finds the root <widget> even with leading <class> sibling
- add_ui merges XML tags into the live ui.tags set
"""
import os
import tempfile
import unittest
from xml.etree import ElementTree as ET

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from uitk.switchboard import Switchboard


def _write_ui(path, name, tags_csv=None, extra_props=""):
    tag_block = ""
    if tags_csv is not None:
        tag_block = (
            f'<property name="uitk_tags" stdset="0">'
            f"<string>{tags_csv}</string></property>"
        )
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>{name.capitalize()}</class>
 <widget class="QMainWindow" name="{name}">
  {tag_block}
  {extra_props}
 </widget>
 <resources/>
 <connections/>
</ui>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class ParseUiTags(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def test_parses_csv_tags(self):
        path = os.path.join(self.dir, "alpha.ui")
        _write_ui(path, "alpha", "anim,rig,export")
        self.assertEqual(
            Switchboard._parse_ui_tags(path), {"anim", "rig", "export"}
        )

    def test_strips_whitespace_and_drops_empty(self):
        path = os.path.join(self.dir, "alpha.ui")
        _write_ui(path, "alpha", " anim ,, rig ,")
        self.assertEqual(Switchboard._parse_ui_tags(path), {"anim", "rig"})

    def test_no_property_returns_empty(self):
        path = os.path.join(self.dir, "alpha.ui")
        _write_ui(path, "alpha", tags_csv=None)
        self.assertEqual(Switchboard._parse_ui_tags(path), set())

    def test_malformed_xml_returns_empty(self):
        path = os.path.join(self.dir, "broken.ui")
        with open(path, "w") as f:
            f.write("<?xml version='1.0'?><ui><widget>not closed")
        self.assertEqual(Switchboard._parse_ui_tags(path), set())

    def test_missing_file_returns_empty(self):
        self.assertEqual(
            Switchboard._parse_ui_tags(os.path.join(self.dir, "nope.ui")), set()
        )


class RegisterIngestsTags(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def test_constructor_parses_tags_without_emitting(self):
        _write_ui(os.path.join(self.dir, "a.ui"), "a", "foo")
        _write_ui(os.path.join(self.dir, "b.ui"), "b", "bar")
        sb = Switchboard(ui_source=self.dir, log_level="WARNING")
        self.assertEqual(sb._ui_xml_tags["a"], {"foo"})
        self.assertEqual(sb._ui_xml_tags["b"], {"bar"})

    def test_register_emits_on_ui_registered_for_new_entries(self):
        _write_ui(os.path.join(self.dir, "a.ui"), "a", "foo")
        sb = Switchboard(ui_source=self.dir, log_level="WARNING")
        received = []
        sb.on_ui_registered.connect(received.append)

        # Add a second .ui in a separate dir, register it
        with tempfile.TemporaryDirectory() as d2:
            _write_ui(os.path.join(d2, "b.ui"), "b", "bar,baz")
            sb.register(ui_location=d2)

        self.assertEqual(received, ["b"])
        self.assertEqual(sb._ui_xml_tags["b"], {"bar", "baz"})

    def test_register_does_not_re_emit_for_existing_entries(self):
        _write_ui(os.path.join(self.dir, "a.ui"), "a", "foo")
        sb = Switchboard(ui_source=self.dir, log_level="WARNING")
        received = []
        sb.on_ui_registered.connect(received.append)
        # Re-register the same dir; existing entry should not re-emit
        sb.register(ui_location=self.dir)
        self.assertEqual(received, [])


class SaveUiTags(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.path = os.path.join(self.dir, "target.ui")
        _write_ui(self.path, "target", "old1,old2")
        self.sb = Switchboard(ui_source=self.dir, log_level="WARNING")

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def test_round_trip(self):
        self.sb.save_ui_tags(self.path, ["alpha", "beta"])
        self.assertEqual(
            Switchboard._parse_ui_tags(self.path), {"alpha", "beta"}
        )
        self.assertEqual(self.sb._ui_xml_tags["target"], {"alpha", "beta"})

    def test_empty_set_removes_property(self):
        self.sb.save_ui_tags(self.path, [])
        self.assertEqual(Switchboard._parse_ui_tags(self.path), set())
        # Property element should not exist in the file
        tree = ET.parse(self.path)
        widget = tree.getroot().find("widget")
        names = [p.get("name") for p in widget.findall("property")]
        self.assertNotIn("uitk_tags", names)

    def test_property_inserted_as_first_property_child(self):
        # File has no uitk_tags initially, plus another property
        _write_ui(
            self.path,
            "target",
            tags_csv=None,
            extra_props='<property name="windowTitle"><string>X</string></property>',
        )
        self.sb._ui_xml_tags["target"] = set()
        self.sb.save_ui_tags(self.path, ["alpha"])

        tree = ET.parse(self.path)
        widget = tree.getroot().find("widget")
        first_prop = widget.find("property")
        self.assertEqual(first_prop.get("name"), "uitk_tags")

    def test_finds_root_widget_with_leading_class_sibling(self):
        # _write_ui already places <class> before <widget> — sanity
        self.sb.save_ui_tags(self.path, ["x"])
        self.assertEqual(Switchboard._parse_ui_tags(self.path), {"x"})

    def test_emits_on_ui_tags_changed(self):
        received = []
        self.sb.on_ui_tags_changed.connect(received.append)
        self.sb.save_ui_tags(self.path, ["new"])
        self.assertEqual(received, ["target"])

    def test_atomic_write_no_temp_left(self):
        before = set(os.listdir(self.dir))
        self.sb.save_ui_tags(self.path, ["one", "two"])
        after = set(os.listdir(self.dir))
        # Only the original file should exist; no .tmp artifacts.
        self.assertEqual(after, before)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.sb.save_ui_tags(
                os.path.join(self.dir, "does_not_exist.ui"), ["x"]
            )


class AddUiMergesXmlTags(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def test_xml_tags_merged_into_live_ui(self):
        _write_ui(
            os.path.join(self.dir, "merge_test.ui"),
            "merge_test",
            "from_xml",
        )
        sb = Switchboard(ui_source=self.dir, log_level="WARNING")
        ui = sb.loaded_ui.merge_test  # triggers lazy load
        self.assertIn("from_xml", ui.tags)


if __name__ == "__main__":
    unittest.main()
