# !/usr/bin/python
# coding=utf-8
"""Integration tests for the switchboard's compiled-module load path.

Covers:
- Switchboard auto-compiles a missing _ui.py on first load.
- Loaded widget tree has the expected Qt object names and children.
- Tag persistence: save_ui_tags writes .ui XML and regenerates _ui.py.
- Hash-based staleness: editing the .ui after compile triggers regen on
  next load.
- Real-world load of the uitk.examples.example UI succeeds.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets

from uitk import compile as compile_mod
from uitk.switchboard import Switchboard


SAMPLE_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Foo</class>
 <widget class="QMainWindow" name="Foo">
  <property name="uitk_tags" stdset="0">
   <string>editor,polygon</string>
  </property>
  <widget class="QWidget" name="central_widget">
   <layout class="QVBoxLayout" name="layout">
    <item>
     <widget class="QPushButton" name="ok_btn">
      <property name="text"><string>OK</string></property>
     </widget>
    </item>
   </layout>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _write(path: Path, content: str = SAMPLE_UI):
    path.write_text(content, encoding="utf-8")


class CompiledLoaderBasic(QtBaseTestCase):
    """Loads a synthetic .ui via CompiledLoader and asserts widget shape."""

    def setUp(self):
        super().setUp()
        try:
            compile_mod._detect_binding()
        except FileNotFoundError:
            self.skipTest("No Qt uic compiler on PATH")
        self.tmp = tempfile.mkdtemp()
        self.dir = self.tmp
        self.ui = Path(self.dir) / "foo.ui"
        _write(self.ui)
        self.sb = Switchboard(
            ui_source=self.dir,
            log_level="WARNING",
            loader="compiled",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_compiled_file_created_on_first_load(self):
        # Registration reads tags from XML directly; compile only happens on load.
        py = compile_mod.compiled_path_for(self.ui)
        self.assertFalse(py.exists())
        self.sb.load_ui(str(self.ui))
        self.assertTrue(py.exists())
        self.assertTrue(compile_mod.is_compiled_fresh(self.ui, py))

    def test_loaded_widget_has_expected_object_name(self):
        widget = self.sb.load_ui(str(self.ui))
        self.assertIsInstance(widget, QtWidgets.QMainWindow)
        # setupUi sets the form's object name from the .ui
        self.assertEqual(widget.objectName(), "Foo")

    def test_loaded_widget_has_expected_children(self):
        widget = self.sb.load_ui(str(self.ui))
        btn = widget.findChild(QtWidgets.QPushButton, "ok_btn")
        self.assertIsNotNone(btn)
        self.assertEqual(btn.text(), "OK")

    def test_tags_resolved_via_loader_lazily(self):
        # Init no longer eagerly parses; _get_ui_tags() lazy-loads on first
        # request and caches. Via the compiled-loader path this auto-compiles
        # foo.ui and reads __uitk_tags__ from foo_ui.py.
        self.assertEqual(self.sb._get_ui_tags("foo"), {"editor", "polygon"})
        self.assertEqual(self.sb._ui_tags["foo"], {"editor", "polygon"})  # cached


class CompiledLoaderStaleness(QtBaseTestCase):
    """Hash-based staleness: editing the .ui forces regen on next access."""

    def setUp(self):
        super().setUp()
        try:
            compile_mod._detect_binding()
        except FileNotFoundError:
            self.skipTest("No Qt uic compiler on PATH")
        self.tmp = tempfile.mkdtemp()
        self.dir = Path(self.tmp)
        self.ui = self.dir / "foo.ui"
        _write(self.ui)
        self.py = compile_mod.compiled_path_for(self.ui)
        self.sb = Switchboard(
            ui_source=self.dir,
            log_level="WARNING",
            loader="compiled",
        )
        self.sb.load_ui(str(self.ui))  # ensures fresh _ui.py

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_edit_then_load_regenerates(self):
        original_hash = compile_mod.read_embedded_hash(self.py)
        _write(self.ui, SAMPLE_UI.replace("editor,polygon", "editor,polygon,extra"))
        self.assertFalse(compile_mod.is_compiled_fresh(self.ui, self.py))
        self.sb.load_ui(str(self.ui))
        new_hash = compile_mod.read_embedded_hash(self.py)
        self.assertNotEqual(original_hash, new_hash)
        self.assertTrue(compile_mod.is_compiled_fresh(self.ui, self.py))


class CompiledLoaderTagPersistence(QtBaseTestCase):
    """save_ui_tags writes .ui XML and regenerates _ui.py via the loader hook."""

    def setUp(self):
        super().setUp()
        try:
            compile_mod._detect_binding()
        except FileNotFoundError:
            self.skipTest("No Qt uic compiler on PATH")
        self.tmp = tempfile.mkdtemp()
        self.dir = Path(self.tmp)
        self.ui = self.dir / "foo.ui"
        _write(self.ui)
        self.py = compile_mod.compiled_path_for(self.ui)
        self.sb = Switchboard(
            ui_source=self.dir,
            log_level="WARNING",
            loader="compiled",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_save_writes_xml_and_regenerates_compiled(self):
        from xml.etree import ElementTree as ET

        self.sb.save_ui_tags(str(self.ui), ["alpha", "beta"])
        # XML still reflects the new tags (Designer Property Editor sees them)
        widget = ET.parse(str(self.ui)).getroot().find("widget")
        prop = next(
            p for p in widget.findall("property") if p.get("name") == "uitk_tags"
        )
        xml_tags = {t.strip() for t in prop.find("string").text.split(",")}
        self.assertEqual(xml_tags, {"alpha", "beta"})
        # _ui.py header is fresh and contains the new tags
        self.assertTrue(compile_mod.is_compiled_fresh(self.ui, self.py))
        self.assertEqual(
            compile_mod.read_embedded_tags(self.py), {"alpha", "beta"}
        )

    def test_save_emits_on_ui_tags_changed(self):
        received = []
        self.sb.on_ui_tags_changed.connect(received.append)
        self.sb.save_ui_tags(str(self.ui), ["x"])
        self.assertEqual(received, ["foo"])


class LoadsExampleEndToEnd(QtBaseTestCase):
    """Load uitk.examples.example end-to-end and verify expected widget tree."""

    def setUp(self):
        super().setUp()
        try:
            compile_mod._detect_binding()
        except FileNotFoundError:
            self.skipTest("No Qt uic compiler on PATH")

    def test_example_loads_with_expected_children(self):
        from uitk import examples
        from uitk.examples.example import ExampleSlots

        sb = Switchboard(
            ui_source=examples,
            slot_source=ExampleSlots,
            log_level="WARNING",
            loader="compiled",
        )
        ui = sb.loaded_ui.example
        self.assertIsNotNone(ui)
        for name in (
            "button_a",
            "button_b",
            "txt_input",
            "tree_demo",
            "header",
            "footer",
            "cmb_options",
            "txt_output",
        ):
            self.assertIsNotNone(
                ui.findChild(QtWidgets.QWidget, name),
                f"child '{name}' missing after load",
            )


class LegacyUiRecovery(QtBaseTestCase):
    """A stale _ui.py with broken imports must auto-regenerate on first load."""

    def setUp(self):
        super().setUp()
        try:
            compile_mod._detect_binding()
        except FileNotFoundError:
            self.skipTest("No Qt uic compiler on PATH")
        self.tmp = tempfile.mkdtemp()
        self.dir = self.tmp
        self.ui = Path(self.dir) / "legacy.ui"
        # .ui referencing a known-registered uitk widget via a malformed
        # legacy header path — the kind that breaks tentacle's old _ui.py
        self.ui.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Legacy</class>
 <widget class="QMainWindow" name="Legacy">
  <widget class="QWidget" name="central">
   <layout class="QVBoxLayout" name="layout">
    <item>
     <widget class="PushButton" name="btn"/>
    </item>
   </layout>
  </widget>
 </widget>
 <customwidgets>
  <customwidget>
   <class>PushButton</class>
   <extends>QPushButton</extends>
   <header>widgets.pushbutton.h</header>
  </customwidget>
 </customwidgets>
 <resources/>
 <connections/>
</ui>
""",
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_load_with_resolver_succeeds_on_legacy_header(self):
        sb = Switchboard(ui_source=self.dir, log_level="WARNING", loader="compiled")
        widget = sb.load_ui(str(self.ui))
        # PushButton is registered (via uitk.widgets) so the resolver finds it.
        btn = widget.findChild(QtWidgets.QPushButton, "btn")
        self.assertIsNotNone(btn)

    def test_recovery_from_pre_existing_broken_compiled(self):
        # Simulate a pre-existing _ui.py emitted by raw pyside6-uic — no
        # uitk header, broken `from widgets.pushbutton.h` import.
        py = compile_mod.compiled_path_for(self.ui)
        py.write_text(
            "from widgets.pushbutton.h import PushButton\n"
            "from qtpy import QtCore, QtWidgets\n"
            "class Ui_Legacy:\n"
            "    def setupUi(self, Form):\n"
            "        Form.setObjectName('Legacy')\n"
            "        self.btn = PushButton(Form)\n"
            "        self.btn.setObjectName('btn')\n",
            encoding="utf-8",
        )
        # is_compiled_fresh treats this as 'unmanaged' and returns True,
        # but the loader should still recover via the ImportError retry.
        sb = Switchboard(ui_source=self.dir, log_level="WARNING", loader="compiled")
        widget = sb.load_ui(str(self.ui))
        btn = widget.findChild(QtWidgets.QPushButton, "btn")
        self.assertIsNotNone(btn)
        # After recovery, the file has our header.
        self.assertIsNotNone(compile_mod.read_embedded_hash(py))


class LoaderInternals(QtBaseTestCase):
    """Defensive checks on the loader's helper functions."""

    def test_module_name_is_stable_across_calls(self):
        from uitk.loaders.compiled import _module_name_for

        p = Path("/some/dir/foo_ui.py")
        self.assertEqual(_module_name_for(p), _module_name_for(p))

    def test_module_name_differs_for_different_paths(self):
        from uitk.loaders.compiled import _module_name_for

        a = _module_name_for(Path("/some/dir/foo_ui.py"))
        b = _module_name_for(Path("/other/dir/foo_ui.py"))
        self.assertNotEqual(a, b)

    def test_resolve_qt_class_raises_on_unknown(self):
        from uitk.loaders.compiled import _resolve_qt_class

        with self.assertRaises(AttributeError):
            _resolve_qt_class("NotARealQtClass")

    def test_resolve_qt_class_returns_known(self):
        from uitk.loaders.compiled import _resolve_qt_class

        self.assertIs(_resolve_qt_class("QMainWindow"), QtWidgets.QMainWindow)
        self.assertIs(_resolve_qt_class("QWidget"), QtWidgets.QWidget)

    def test_failed_import_does_not_pollute_sys_modules(self):
        """A _ui.py with a bad import must not leave a half-broken entry behind."""
        import sys

        from uitk.loaders.compiled import _import_compiled_module, _module_name_for

        tmp = tempfile.mkdtemp()
        try:
            broken = Path(tmp) / "broken_ui.py"
            broken.write_text(
                "from definitely_not_a_real_module import Nope\n"
                "class Ui_X:\n    def setupUi(self, w): pass\n",
                encoding="utf-8",
            )
            mod_name = _module_name_for(broken)
            with self.assertRaises(ImportError):
                _import_compiled_module(broken)
            self.assertNotIn(mod_name, sys.modules)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
