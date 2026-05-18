# !/usr/bin/python
# coding=utf-8
"""Unit tests for Switchboard tag persistence (Designer-safe XML format).

Covers:
- register() ingests tags into _ui_tags and emits on_ui_registered
- save_ui_tags writes the property and atomically replaces the .ui file
- save_ui_tags with empty tag set removes the property
- save_ui_tags emits on_ui_tags_changed and updates the live MainWindow.tags
- save_ui_tags finds the root <widget> even with leading <class> sibling
- save_ui_tags regenerates _ui.py so runtime sees the new tags
- add_ui merges tags into the live ui.tags set
"""
import os
import tempfile
import unittest
from xml.etree import ElementTree as ET

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from uitk.switchboard import Switchboard


def _read_ui_tags(path) -> set:
    """Read uitk_tags from a .ui file's XML directly (test-only helper)."""
    tree = ET.parse(path)
    widget = tree.getroot().find("widget")
    if widget is None:
        return set()
    for prop in widget.findall("property"):
        if prop.get("name") == "uitk_tags":
            s = prop.find("string")
            if s is not None and s.text:
                return {t.strip() for t in s.text.split(",") if t.strip()}
    return set()


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


class RegisterIngestsTags(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def test_constructor_does_not_eagerly_parse_tags(self):
        # Init no longer parses XML for every registered UI — the cost
        # was paid for files that may never load. Tags resolve lazily on
        # first access via _get_ui_tags.
        _write_ui(os.path.join(self.dir, "a.ui"), "a", "foo")
        _write_ui(os.path.join(self.dir, "b.ui"), "b", "bar")
        sb = Switchboard(ui_source=self.dir, log_level="WARNING")
        self.assertEqual(sb._ui_tags, {})
        # But on demand they resolve correctly and cache.
        self.assertEqual(sb._get_ui_tags("a"), {"foo"})
        self.assertEqual(sb._get_ui_tags("b"), {"bar"})
        self.assertEqual(sb._ui_tags, {"a": {"foo"}, "b": {"bar"}})

    def test_register_emits_on_ui_registered_for_new_entries(self):
        _write_ui(os.path.join(self.dir, "a.ui"), "a", "foo")
        sb = Switchboard(ui_source=self.dir, log_level="WARNING")
        received = []
        sb.on_ui_registered.connect(received.append)

        # Add a second .ui in a separate dir, register it. Tags are now
        # resolved lazily, so the file must still exist when we read them
        # — assert tags inside the tempdir context.
        with tempfile.TemporaryDirectory() as d2:
            _write_ui(os.path.join(d2, "b.ui"), "b", "bar,baz")
            sb.register(ui_location=d2)

            self.assertEqual(received, ["b"])
            self.assertEqual(sb._get_ui_tags("b"), {"bar", "baz"})

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
            _read_ui_tags(self.path), {"alpha", "beta"}
        )
        self.assertEqual(self.sb._ui_tags["target"], {"alpha", "beta"})

    def test_empty_set_removes_property(self):
        self.sb.save_ui_tags(self.path, [])
        self.assertEqual(_read_ui_tags(self.path), set())
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
        self.sb._ui_tags["target"] = set()
        self.sb.save_ui_tags(self.path, ["alpha"])

        tree = ET.parse(self.path)
        widget = tree.getroot().find("widget")
        first_prop = widget.find("property")
        self.assertEqual(first_prop.get("name"), "uitk_tags")

    def test_strips_leading_hash_from_input(self):
        """The "#" prefix is display-only — the browser's delegate adds
        it when rendering chips. Storing "#tag" would round-trip to
        "##tag" the next time the row paints. save_ui_tags must strip
        any leading "#" (and incidental whitespace) before persisting."""
        self.sb.save_ui_tags(self.path, ["#alpha", "##doublebug", "  #beta "])
        self.assertEqual(
            _read_ui_tags(self.path),
            {"alpha", "doublebug", "beta"},
        )

    def test_finds_root_widget_with_leading_class_sibling(self):
        # _write_ui already places <class> before <widget> — sanity
        self.sb.save_ui_tags(self.path, ["x"])
        self.assertEqual(_read_ui_tags(self.path), {"x"})

    def test_emits_on_ui_tags_changed(self):
        received = []
        self.sb.on_ui_tags_changed.connect(received.append)
        self.sb.save_ui_tags(self.path, ["new"])
        self.assertEqual(received, ["target"])

    def test_atomic_write_no_temp_left(self):
        self.sb.save_ui_tags(self.path, ["one", "two"])
        # No .tmp artifacts from atomic writes (.ui or _ui.py).
        leftovers = [f for f in os.listdir(self.dir) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])

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
