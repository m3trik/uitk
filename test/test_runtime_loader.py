# !/usr/bin/python
# coding=utf-8
"""Tests for the runtime XML loader (uitk.loaders.runtime).

Mirrors test_compiled_loader.py's contract checks, applied to RuntimeLoader.

Covers:
- Switchboard with ``loader="runtime"`` builds a RuntimeLoader.
- Direct .ui load yields a widget tree with the expected names/children.
- Tag read happens via single XML parse with mtime-keyed caching.
- ``on_tags_written`` invalidates the metadata cache.
- Custom widget classes registered against a known registry are resolved
  via ``QUiLoader.registerCustomWidget``.
- The ``loader`` kwarg also accepts a class object and a pre-built
  instance (parity with the docstring contract).
"""
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets

from uitk import compile as compile_mod
from uitk.loaders.runtime import RuntimeLoader
from uitk.loaders.compiled import CompiledLoader
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


def _write(tmp: Path, name: str = "Foo") -> Path:
    p = tmp / f"{name}.ui"
    p.write_text(SAMPLE_UI, encoding="utf-8")
    return p


class SwitchboardLoaderSelection(QtBaseTestCase):
    """The ``loader`` kwarg picks between compiled and runtime delegates."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.ui = _write(Path(self.tmp))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_default_is_runtime(self):
        sb = Switchboard(ui_source=self.tmp, base_dir=0)
        self.assertIsInstance(sb._loader, RuntimeLoader)

    def test_compiled_string_picks_compiled_loader(self):
        sb = Switchboard(ui_source=self.tmp, base_dir=0, loader="compiled")
        self.assertIsInstance(sb._loader, CompiledLoader)

    def test_runtime_string_picks_runtime_loader(self):
        sb = Switchboard(ui_source=self.tmp, base_dir=0, loader="runtime")
        self.assertIsInstance(sb._loader, RuntimeLoader)

    def test_unknown_string_raises(self):
        with self.assertRaises(ValueError):
            Switchboard(ui_source=self.tmp, base_dir=0, loader="bogus")

    def test_class_object_accepted(self):
        sb = Switchboard(ui_source=self.tmp, base_dir=0, loader=RuntimeLoader)
        self.assertIsInstance(sb._loader, RuntimeLoader)

    def test_prebuilt_instance_accepted(self):
        sb_holder = Switchboard(ui_source=self.tmp, base_dir=0)
        loader = RuntimeLoader(sb_holder)
        sb = Switchboard(ui_source=self.tmp, base_dir=0, loader=loader)
        self.assertIs(sb._loader, loader)

    def test_custom_loader_missing_contract_raises_typeerror(self):
        class IncompleteLoader:
            def __init__(self, switchboard):
                self.sb = switchboard
            # Missing: load, read_ui_tags, on_tags_written

        with self.assertRaises(TypeError) as ctx:
            Switchboard(ui_source=self.tmp, base_dir=0, loader=IncompleteLoader)
        msg = str(ctx.exception)
        # Error must name the missing contract methods.
        self.assertIn("load", msg)
        self.assertIn("read_ui_tags", msg)
        self.assertIn("on_tags_written", msg)


class RuntimeLoaderLoad(QtBaseTestCase):
    """Direct load via QUiLoader produces the expected widget tree."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.ui = _write(Path(self.tmp))
        self.sb = Switchboard(ui_source=self.tmp, base_dir=0, loader="runtime")
        self.loader = self.sb._loader

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_load_returns_qmainwindow(self):
        form = self.loader.load(str(self.ui))
        self.track_widget(form)
        self.assertIsInstance(form, QtWidgets.QMainWindow)

    def test_loaded_tree_has_named_children(self):
        form = self.loader.load(str(self.ui))
        self.track_widget(form)
        self.assertIsNotNone(form.findChild(QtWidgets.QPushButton, "ok_btn"))
        self.assertIsNotNone(form.findChild(QtWidgets.QWidget, "central_widget"))

    def test_no_compiled_artifact_written(self):
        py_path = compile_mod.compiled_path_for(self.ui)
        # Sanity: should not exist beforehand
        self.assertFalse(py_path.exists())
        form = self.loader.load(str(self.ui))
        self.track_widget(form)
        # Runtime path must NOT write a _ui.py.
        self.assertFalse(py_path.exists())


CUSTOM_WIDGET_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>WithCustom</class>
 <widget class="QMainWindow" name="WithCustom">
  <widget class="QWidget" name="central">
   <layout class="QVBoxLayout" name="layout">
    <item>
     <widget class="PushButton" name="b001">
      <property name="text"><string>Click</string></property>
     </widget>
    </item>
   </layout>
  </widget>
 </widget>
 <customwidgets>
  <customwidget>
   <class>PushButton</class>
   <extends>QPushButton</extends>
   <header>uitk.widgets.pushButton</header>
  </customwidget>
 </customwidgets>
 <resources/>
 <connections/>
</ui>
"""


class RuntimeLoaderCustomWidgets(QtBaseTestCase):
    """Custom widgets resolved via Switchboard registry → registerCustomWidget."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.ui = Path(self.tmp) / "WithCustom.ui"
        self.ui.write_text(CUSTOM_WIDGET_UI, encoding="utf-8")
        self.sb = Switchboard(ui_source=self.tmp, base_dir=0, loader="runtime")
        self.loader = self.sb._loader

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_custom_widget_promoted_to_registered_class(self):
        # Switchboard's default widget_registry already exposes uitk widgets
        # (registered in __init__ from uitk/widgets/). Loading the UI must
        # produce a real ``uitk.widgets.pushButton.PushButton`` instance for
        # b001 — not the QPushButton fallback the .ui's <header> would
        # produce if registerCustomWidget hadn't been called.
        from uitk.widgets.pushButton import PushButton

        form = self.loader.load(str(self.ui))
        self.track_widget(form)
        b001 = form.findChild(QtWidgets.QWidget, "b001")
        self.assertIsNotNone(b001)
        self.assertIsInstance(b001, PushButton)

    def test_custom_widget_registered_with_switchboard(self):
        self.loader.load(str(self.ui))
        self.assertIn("PushButton", self.sb.registered_widgets.keys())


class RuntimeLoaderTags(QtBaseTestCase):
    """uitk_tags read directly from XML; cache keyed by mtime."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.ui = _write(Path(self.tmp))
        self.sb = Switchboard(ui_source=self.tmp, base_dir=0, loader="runtime")
        self.loader = self.sb._loader

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_read_ui_tags_extracts_set(self):
        self.assertEqual(
            self.loader.read_ui_tags(str(self.ui)),
            {"editor", "polygon"},
        )

    def test_read_ui_tags_empty_on_missing_file(self):
        self.assertEqual(self.loader.read_ui_tags(""), set())
        bogus = str(Path(self.tmp) / "does_not_exist.ui")
        self.assertEqual(self.loader.read_ui_tags(bogus), set())

    def test_metadata_cache_hits_on_unchanged_file(self):
        # Defensive clear — Switchboard init does not pre-warm the cache
        # (tags are now lazy), but explicit reset keeps the test robust
        # against future paths that could populate it.
        self.loader._metadata_cache.clear()

        # Replace extract_metadata with a counter so we can prove the
        # second read_ui_tags call did not re-parse.
        from unittest.mock import patch

        original = compile_mod.extract_metadata
        call_count = {"n": 0}

        def counting(ui_path):
            call_count["n"] += 1
            return original(ui_path)

        with patch.object(compile_mod, "extract_metadata", side_effect=counting):
            first = self.loader.read_ui_tags(str(self.ui))
            self.assertEqual(call_count["n"], 1)
            second = self.loader.read_ui_tags(str(self.ui))
            self.assertEqual(call_count["n"], 1)  # cache hit, no second parse
            self.assertEqual(first, second)

    def test_on_tags_written_invalidates_cache(self):
        self.loader.read_ui_tags(str(self.ui))
        self.assertIn(self.loader._cache_key(str(self.ui)), self.loader._metadata_cache)
        self.loader.on_tags_written(str(self.ui))
        self.assertNotIn(
            self.loader._cache_key(str(self.ui)), self.loader._metadata_cache
        )

    def test_mtime_change_invalidates_cache(self):
        self.loader.read_ui_tags(str(self.ui))
        # Bump mtime by 2s and rewrite tags so the parsed value differs.
        new_xml = SAMPLE_UI.replace("editor,polygon", "edge")
        self.ui.write_text(new_xml, encoding="utf-8")
        future = time.time() + 2
        os.utime(self.ui, (future, future))
        self.assertEqual(self.loader.read_ui_tags(str(self.ui)), {"edge"})


if __name__ == "__main__":
    unittest.main()
