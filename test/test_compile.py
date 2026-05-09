# !/usr/bin/python
# coding=utf-8
"""Unit tests for uitk.compile (the .ui -> _ui.py compiler).

Covers:
- extract_metadata reads base class, form class, customwidgets, uitk_tags from XML
- hash_ui_source is stable on identical bytes and changes on any byte
- compiled_path_for derives the paired _ui.py path
- is_compiled_fresh returns False when missing, True after compile, False on edit
- compile_ui writes a file with the embedded constants and qtpy-rewritten imports
- read_embedded_hash / read_embedded_tags / read_embedded_base_class round-trip
- _ui.py without a __source_hash__ header is treated as STALE (uitk owns _ui.py end-to-end)
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from conftest import BaseTestCase

from uitk import compile as compile_mod


SAMPLE_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>SampleForm</class>
 <widget class="QMainWindow" name="SampleForm">
  <property name="uitk_tags" stdset="0">
   <string>alpha,beta,gamma</string>
  </property>
  <property name="windowTitle">
   <string>Sample</string>
  </property>
  <widget class="QWidget" name="central_widget">
   <layout class="QVBoxLayout" name="layout"/>
  </widget>
 </widget>
 <customwidgets>
  <customwidget>
   <class>PushButton</class>
   <extends>QPushButton</extends>
   <header>uitk.widgets.pushButton</header>
  </customwidget>
  <customwidget>
   <class>LineEdit</class>
   <extends>QLineEdit</extends>
   <header>uitk.widgets.lineEdit</header>
  </customwidget>
 </customwidgets>
 <resources/>
 <connections/>
</ui>
"""


def _write_sample(dirpath: Path, name: str = "sample") -> Path:
    p = dirpath / f"{name}.ui"
    p.write_text(SAMPLE_UI, encoding="utf-8")
    return p


class ExtractMetadata(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.ui = _write_sample(Path(self.tmp))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_base_class_and_form_class(self):
        meta = compile_mod.extract_metadata(self.ui)
        self.assertEqual(meta["base_class"], "QMainWindow")
        self.assertEqual(meta["form_class"], "SampleForm")

    def test_customwidgets_extracted(self):
        meta = compile_mod.extract_metadata(self.ui)
        self.assertEqual(
            meta["customwidgets"],
            [
                ("PushButton", "uitk.widgets.pushButton"),
                ("LineEdit", "uitk.widgets.lineEdit"),
            ],
        )

    def test_uitk_tags_extracted_and_sorted(self):
        meta = compile_mod.extract_metadata(self.ui)
        self.assertEqual(meta["uitk_tags"], ["alpha", "beta", "gamma"])

    def test_no_tags_yields_empty_list(self):
        ui = self.ui.with_name("notags.ui")
        ui.write_text(SAMPLE_UI.replace(
            '<property name="uitk_tags" stdset="0">\n   <string>alpha,beta,gamma</string>\n  </property>\n  ',
            "",
        ), encoding="utf-8")
        meta = compile_mod.extract_metadata(ui)
        self.assertEqual(meta["uitk_tags"], [])

    def test_no_customwidgets(self):
        ui = self.ui.with_name("plain.ui")
        ui.write_text(
            "<?xml version='1.0'?><ui><class>Plain</class>"
            "<widget class='QWidget' name='Plain'/></ui>",
            encoding="utf-8",
        )
        meta = compile_mod.extract_metadata(ui)
        self.assertEqual(meta["customwidgets"], [])
        self.assertEqual(meta["uitk_tags"], [])
        self.assertEqual(meta["base_class"], "QWidget")


class HashAndPath(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.ui = _write_sample(Path(self.tmp))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_hash_is_stable(self):
        h1 = compile_mod.hash_ui_source(self.ui)
        h2 = compile_mod.hash_ui_source(self.ui)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_hash_changes_on_edit(self):
        h1 = compile_mod.hash_ui_source(self.ui)
        self.ui.write_text(SAMPLE_UI.replace("alpha", "ALPHA"), encoding="utf-8")
        h2 = compile_mod.hash_ui_source(self.ui)
        self.assertNotEqual(h1, h2)

    def test_compiled_path_for(self):
        py = compile_mod.compiled_path_for(self.ui)
        self.assertEqual(py.name, "sample_ui.py")
        self.assertEqual(py.parent, self.ui.parent)


class FreshnessAndCompile(BaseTestCase):
    """End-to-end compile cycle. Skipped if no uic compiler is on PATH."""

    def setUp(self):
        super().setUp()
        try:
            compile_mod._detect_binding()
        except FileNotFoundError:
            self.skipTest("No Qt uic compiler on PATH")
        self.tmp = tempfile.mkdtemp()
        self.ui = _write_sample(Path(self.tmp))
        self.py = compile_mod.compiled_path_for(self.ui)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_missing_py_is_not_fresh(self):
        self.assertFalse(self.py.exists())
        self.assertFalse(compile_mod.is_compiled_fresh(self.ui, self.py))

    def test_compile_creates_file(self):
        out = compile_mod.compile_ui(self.ui)
        self.assertTrue(out.exists())
        self.assertEqual(out, self.py)

    def test_compiled_file_has_metadata(self):
        compile_mod.compile_ui(self.ui)
        text = self.py.read_text(encoding="utf-8")
        self.assertIn("__source_hash__", text)
        self.assertIn("__uitk_tags__", text)
        self.assertIn("__base_class__", text)
        self.assertIn("__customwidgets__", text)
        self.assertIn("alpha", text)
        self.assertIn("PushButton", text)

    def test_imports_rewritten_to_qtpy(self):
        compile_mod.compile_ui(self.ui)
        text = self.py.read_text(encoding="utf-8")
        self.assertNotIn("from PySide6", text)
        self.assertNotIn("from PySide2", text)
        self.assertIn("from qtpy", text)

    def test_fresh_after_compile(self):
        compile_mod.compile_ui(self.ui)
        self.assertTrue(compile_mod.is_compiled_fresh(self.ui, self.py))

    def test_stale_after_edit(self):
        compile_mod.compile_ui(self.ui)
        self.assertTrue(compile_mod.is_compiled_fresh(self.ui, self.py))
        self.ui.write_text(SAMPLE_UI.replace("alpha", "ALPHA"), encoding="utf-8")
        self.assertFalse(compile_mod.is_compiled_fresh(self.ui, self.py))

    def test_ensure_compiled_regenerates(self):
        compile_mod.compile_ui(self.ui)
        self.ui.write_text(SAMPLE_UI.replace("alpha", "ALPHA"), encoding="utf-8")
        compile_mod.ensure_compiled(self.ui)
        self.assertTrue(compile_mod.is_compiled_fresh(self.ui, self.py))

    def test_atomic_write_no_temp_left(self):
        before = set(os.listdir(self.tmp))
        compile_mod.compile_ui(self.ui)
        after = set(os.listdir(self.tmp))
        # Only sample.ui (before) plus sample_ui.py (after); no .tmp leftovers.
        self.assertNotIn("sample_ui.py.tmp", after)
        self.assertEqual(after - before, {"sample_ui.py"})


class HeaderReadback(BaseTestCase):
    """Round-trip the header constants from a generated _ui.py."""

    def setUp(self):
        super().setUp()
        try:
            compile_mod._detect_binding()
        except FileNotFoundError:
            self.skipTest("No Qt uic compiler on PATH")
        self.tmp = tempfile.mkdtemp()
        self.ui = _write_sample(Path(self.tmp))
        self.py = compile_mod.compile_ui(self.ui)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_read_embedded_hash(self):
        h = compile_mod.read_embedded_hash(self.py)
        self.assertEqual(h, compile_mod.hash_ui_source(self.ui))

    def test_read_embedded_tags(self):
        tags = compile_mod.read_embedded_tags(self.py)
        self.assertEqual(tags, {"alpha", "beta", "gamma"})

    def test_read_embedded_base_class(self):
        self.assertEqual(compile_mod.read_embedded_base_class(self.py), "QMainWindow")

    def test_read_embedded_form_class(self):
        self.assertEqual(compile_mod.read_embedded_form_class(self.py), "SampleForm")


class HeaderResolver(BaseTestCase):
    """compile_ui rewrites customwidget imports via the header_resolver hook."""

    def setUp(self):
        super().setUp()
        try:
            compile_mod._detect_binding()
        except FileNotFoundError:
            self.skipTest("No Qt uic compiler on PATH")
        self.tmp = tempfile.mkdtemp()
        self.ui = Path(self.tmp) / "legacy.ui"
        # A .ui with a legacy C++-style <header> path that would emit a
        # broken `from widgets.pushbutton.h import PushButton` line otherwise.
        self.ui.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Legacy</class>
 <widget class="QMainWindow" name="Legacy">
  <widget class="QWidget" name="central"/>
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

    def test_resolver_rewrites_broken_import(self):
        def resolver(class_name, original_header):
            if class_name == "PushButton":
                return "uitk.widgets.pushButton"
            return None

        py = compile_mod.compile_ui(self.ui, header_resolver=resolver)
        text = py.read_text(encoding="utf-8")
        self.assertIn("from uitk.widgets.pushButton import PushButton", text)
        self.assertNotIn(
            "from widgets.pushbutton.h import PushButton", text
        )

    def test_no_resolver_leaves_broken_import_intact(self):
        # Without a resolver, the malformed header propagates — surfaces as
        # ImportError at load time, which the loader recovers from.
        py = compile_mod.compile_ui(self.ui)
        text = py.read_text(encoding="utf-8")
        self.assertIn("widgets.pushbutton.h", text)

    def test_resolver_returning_none_leaves_intact(self):
        py = compile_mod.compile_ui(
            self.ui, header_resolver=lambda c, h: None
        )
        text = py.read_text(encoding="utf-8")
        self.assertIn("widgets.pushbutton.h", text)


class HeaderReadbackSafety(BaseTestCase):
    """read_embedded_tags must not eval arbitrary expressions."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def _write_header(self, body: str) -> Path:
        py = Path(self.tmp) / "x_ui.py"
        py.write_text(body, encoding="utf-8")
        return py

    def test_returns_empty_for_callable_expression(self):
        # Even if a (legitimately uitk-emitted) header is replaced with a
        # callable expression, read_embedded_tags must not invoke it.
        py = self._write_header("__uitk_tags__ = print('side effect')\n")
        self.assertEqual(compile_mod.read_embedded_tags(py), set())

    def test_returns_empty_for_non_literal(self):
        py = self._write_header("__uitk_tags__ = some_var\n")
        self.assertEqual(compile_mod.read_embedded_tags(py), set())

    def test_handles_empty_list(self):
        py = self._write_header("__uitk_tags__ = []\n")
        self.assertEqual(compile_mod.read_embedded_tags(py), set())

    def test_handles_quoted_list(self):
        py = self._write_header("__uitk_tags__ = ['alpha', 'beta']\n")
        self.assertEqual(compile_mod.read_embedded_tags(py), {"alpha", "beta"})


class ExtractMetadataEdgeCases(BaseTestCase):
    """Robustness against minimal / malformed .ui files."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_empty_class_element_yields_default(self):
        ui = Path(self.tmp) / "x.ui"
        ui.write_text(
            "<?xml version='1.0'?><ui><class></class>"
            "<widget class='QWidget' name='X'/></ui>",
            encoding="utf-8",
        )
        meta = compile_mod.extract_metadata(ui)
        self.assertEqual(meta["form_class"], "Form")
        self.assertEqual(meta["base_class"], "QWidget")


class RawUicPyFile(BaseTestCase):
    """A _ui.py without a __source_hash__ header is stale; uitk owns the format."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.ui = _write_sample(Path(self.tmp))
        self.py = compile_mod.compiled_path_for(self.ui)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_no_hash_header_is_stale(self):
        # Simulate a raw pyside6-uic _ui.py (no uitk metadata header)
        self.py.write_text(
            "from qtpy import QtWidgets\nclass Ui_X:\n    def setupUi(self, w): pass\n",
            encoding="utf-8",
        )
        self.assertFalse(compile_mod.is_compiled_fresh(self.ui, self.py))

    def test_no_hash_header_returns_no_tags(self):
        self.py.write_text(
            "from qtpy import QtWidgets\nclass Ui_X:\n    def setupUi(self, w): pass\n",
            encoding="utf-8",
        )
        self.assertEqual(compile_mod.read_embedded_tags(self.py), set())
        self.assertIsNone(compile_mod.read_embedded_hash(self.py))

    def test_ensure_compiled_overwrites_raw_uic_with_canonical(self):
        # Bug guard: a raw-uic _ui.py for a QMainWindow .ui must not be left
        # in place, otherwise the loader would default __base_class__ to
        # "QWidget" and call QMainWindow-only methods (e.g. setToolButtonStyle)
        # on a QWidget at form construction.
        self.py.write_text(
            "from qtpy import QtWidgets\nclass Ui_X:\n    def setupUi(self, w): pass\n",
            encoding="utf-8",
        )
        compile_mod.ensure_compiled(self.ui)
        self.assertEqual(compile_mod.read_embedded_base_class(self.py), "QMainWindow")
        self.assertIsNotNone(compile_mod.read_embedded_hash(self.py))
        self.assertTrue(compile_mod.is_compiled_fresh(self.ui, self.py))


class PrecompileAsync(BaseTestCase):
    """Background pre-compile via a daemon thread + uic thread pool.

    Each test wipes ``_ui.py`` files in a private tmp dir, fires
    ``precompile_async``, and waits for the daemon thread to finish.
    """

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)
        # Three .ui files so we can observe parallelism vs. serial.
        self.uis = [
            _write_sample(self.tmp_path, name=f"sample_{i}") for i in range(3)
        ]

    def tearDown(self):
        # Wait for any leftover background thread before cleanup so file
        # locks on Windows don't bite ``shutil.rmtree``.
        active = compile_mod._precompile_active
        if active is not None and active.is_alive():
            active.join(timeout=10)
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def test_kicks_off_thread_when_stale(self):
        job = compile_mod.precompile_async(self.tmp_path)
        try:
            self.assertTrue(bool(job))
            self.assertEqual(job.stale, 3)
            self.assertEqual(job.reason, "")
            self.assertIsNotNone(job.thread)
        finally:
            if job.thread is not None:
                job.thread.join(timeout=10)

        # All three should now be canonical with hash + base_class.
        for ui in self.uis:
            py = compile_mod.compiled_path_for(ui)
            self.assertTrue(py.exists())
            self.assertIsNotNone(compile_mod.read_embedded_hash(py))
            self.assertEqual(
                compile_mod.read_embedded_base_class(py), "QMainWindow"
            )

    def test_returns_none_stale_when_all_fresh(self):
        # Compile once to make everything fresh.
        for ui in self.uis:
            compile_mod.ensure_compiled(ui)

        job = compile_mod.precompile_async(self.tmp_path)
        self.assertFalse(bool(job))
        self.assertIsNone(job.thread)
        self.assertEqual(job.stale, 0)
        self.assertEqual(job.reason, "none-stale")

    def test_skips_nonexistent_paths(self):
        bogus = self.tmp_path / "does_not_exist.ui"
        # Mix real + bogus; bogus must be silently skipped.
        job = compile_mod.precompile_async(self.tmp_path, bogus)
        try:
            self.assertEqual(job.stale, 3)
        finally:
            if job.thread is not None:
                job.thread.join(timeout=10)

    def test_force_recompiles_even_when_fresh(self):
        # Compile once — everything fresh.
        for ui in self.uis:
            compile_mod.ensure_compiled(ui)
        self.assertTrue(
            all(compile_mod.is_compiled_fresh(u, compile_mod.compiled_path_for(u))
                for u in self.uis)
        )

        # Without force: nothing to do.
        job = compile_mod.precompile_async(self.tmp_path)
        self.assertEqual(job.stale, 0)
        self.assertEqual(job.reason, "none-stale")

        # With force: every file is queued.
        job = compile_mod.precompile_async(self.tmp_path, force=True)
        try:
            self.assertEqual(job.stale, 3)
            self.assertEqual(job.reason, "")
            self.assertIsNotNone(job.thread)
        finally:
            if job.thread is not None:
                job.thread.join(timeout=10)

    def test_serial_path_matches_parallel_output(self):
        # jobs=1 forces the serial branch; output must be identical.
        job = compile_mod.precompile_async(self.tmp_path, jobs=1)
        try:
            self.assertTrue(bool(job))
        finally:
            if job.thread is not None:
                job.thread.join(timeout=10)
        for ui in self.uis:
            py = compile_mod.compiled_path_for(ui)
            self.assertTrue(compile_mod.is_compiled_fresh(ui, py))


class BindingDetection(BaseTestCase):
    """uic must match the active runtime so output syntax loads correctly.

    Maya 2025 ships PySide6 6.5.3 while a workspace .venv may have 6.10+.
    uic from 6.10 emits enum-class syntax (``QSizePolicy.Policy.Ignored``)
    that 6.5 rejects, so output must come from the runtime's bundled uic.
    """

    def test_finds_bundled_uic_next_to_active_pyside(self):
        import PySide6

        bundled = compile_mod._find_bundled_uic("PySide6")
        if bundled is None:
            self.skipTest("PySide6 install does not ship uic in this layout")
        pyside_dir = Path(PySide6.__file__).parent.resolve()
        self.assertTrue(
            str(bundled.resolve()).startswith(str(pyside_dir)),
            f"uic at {bundled} is not bundled with active PySide6 at {pyside_dir}",
        )

    def test_bundled_uic_command_includes_g_python(self):
        # When invoking Qt's raw uic, we must pass -g python or it emits C++.
        bundled = compile_mod._find_bundled_uic("PySide6")
        if bundled is None:
            self.skipTest("PySide6 install does not ship uic in this layout")
        binding, argv = compile_mod._detect_uic_command()
        self.assertEqual(binding, "PySide6")
        self.assertIn("-g", argv)
        self.assertIn("python", argv)


if __name__ == "__main__":
    unittest.main()
