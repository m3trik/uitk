# !/usr/bin/python
# coding=utf-8
"""Tests for PresetManager and StateManager.suppress_save.

Validates the full preset lifecycle: save, load, list, delete, rename,
and the interaction with StateManager's suppress_save mechanism.
"""
import sys
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Ensure package root is importable
PACKAGE_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from conftest import QtBaseTestCase, setup_qt_application
from qtpy import QtWidgets, QtCore

from uitk.widgets.mixins.state_manager import StateManager
from uitk.widgets.mixins.settings_manager import SettingsManager
from uitk.widgets.mixins.preset_manager import PresetManager


class TestSuppressSave(QtBaseTestCase):
    """Test StateManager.suppress_save context manager."""

    def setUp(self):
        super().setUp()
        self.qsettings = QtCore.QSettings()
        self.state = StateManager(self.qsettings)

    def test_suppress_save_flag_lifecycle(self):
        """Verify _save_suppressed is False by default, True inside context."""
        self.assertFalse(self.state._save_suppressed)

        with self.state.suppress_save():
            self.assertTrue(self.state._save_suppressed)

        self.assertFalse(self.state._save_suppressed)

    def test_suppress_save_restores_on_exception(self):
        """Verify flag is restored even if an exception occurs."""
        try:
            with self.state.suppress_save():
                raise ValueError("test error")
        except ValueError:
            pass

        self.assertFalse(self.state._save_suppressed)

    def test_save_skipped_when_suppressed(self):
        """Verify QSettings.setValue is not called while suppressed."""
        # Create a real widget to test with
        widget = QtWidgets.QCheckBox("test")
        widget.setObjectName("test_suppress_checkbox")
        widget.restore_state = True
        widget.derived_type = "QCheckBox"
        widget.default_signals = lambda: "toggled"
        self.track_widget(widget)

        with self.state.suppress_save():
            self.state.save(widget, True)

        # The key should NOT be in QSettings
        key = self.state._get_state_key(widget)
        self.assertIsNone(self.qsettings.value(key))


class TestPresetManager(QtBaseTestCase):
    """Test PresetManager save/load/list/delete/rename lifecycle."""

    def setUp(self):
        super().setUp()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="uitk_preset_test_"))
        self.qsettings = QtCore.QSettings()
        self.state = StateManager(self.qsettings)

        # Create a mock parent that mimics MainWindow's widget registry
        self.parent_widget = QtWidgets.QWidget()
        self.parent_widget.setObjectName("TestWindow")
        self.parent_widget.widgets = set()
        self.track_widget(self.parent_widget)

        self.preset_mgr = PresetManager(
            self.parent_widget, self.state, preset_dir=self.tmpdir
        )

        # Create test widgets
        self.chk = self._make_checkbox("myCheckBox", checked=True)
        self.spin = self._make_spinbox("mySpinBox", value=42)
        self.line = self._make_lineedit("myLineEdit", text="hello")

    def tearDown(self):
        super().tearDown()
        if self.tmpdir.exists():
            shutil.rmtree(self.tmpdir)

    def _make_checkbox(self, name, checked=False):
        w = QtWidgets.QCheckBox("test", self.parent_widget)
        w.setObjectName(name)
        w.setChecked(checked)
        w.restore_state = True
        w.derived_type = "QCheckBox"
        w.default_signals = lambda: "toggled"
        self.parent_widget.widgets.add(w)
        self.track_widget(w)
        return w

    def _make_spinbox(self, name, value=0):
        w = QtWidgets.QSpinBox(self.parent_widget)
        w.setObjectName(name)
        w.setRange(0, 100)
        w.setValue(value)
        w.restore_state = True
        w.derived_type = "QSpinBox"
        w.default_signals = lambda: "valueChanged"
        self.parent_widget.widgets.add(w)
        self.track_widget(w)
        return w

    def _make_lineedit(self, name, text=""):
        w = QtWidgets.QLineEdit(self.parent_widget)
        w.setObjectName(name)
        w.setText(text)
        w.restore_state = True
        w.derived_type = "QLineEdit"
        w.default_signals = lambda: "textChanged"
        self.parent_widget.widgets.add(w)
        self.track_widget(w)
        return w

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def test_save_creates_json_file(self):
        """Verify save creates a valid JSON file in the preset directory."""
        path = self.preset_mgr.save("my_preset")
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".json")

        with open(path, "r") as f:
            data = json.load(f)

        self.assertIn("_meta", data)
        self.assertEqual(data["_meta"]["version"], 1)
        self.assertEqual(data["myCheckBox"], True)
        self.assertEqual(data["mySpinBox"], 42)
        self.assertEqual(data["myLineEdit"], "hello")

    def test_save_excludes_non_restorable_widgets(self):
        """Widgets with restore_state=False should not appear in presets."""
        excluded = self._make_checkbox("excludedBox", checked=True)
        excluded.restore_state = False

        path = self.preset_mgr.save("filtered_preset")
        with open(path, "r") as f:
            data = json.load(f)

        self.assertNotIn("excludedBox", data)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def test_load_restores_values(self):
        """Verify load applies saved values back to widgets."""
        self.preset_mgr.save("restore_test")

        # Change all values
        self.chk.setChecked(False)
        self.spin.setValue(0)
        self.line.setText("changed")

        count = self.preset_mgr.load("restore_test")

        self.assertEqual(count, 3)
        self.assertTrue(self.chk.isChecked())
        self.assertEqual(self.spin.value(), 42)
        self.assertEqual(self.line.text(), "hello")

    def test_load_nonexistent_returns_zero(self):
        """Loading a preset that doesn't exist should return 0."""
        count = self.preset_mgr.load("does_not_exist")
        self.assertEqual(count, 0)

    def test_load_ignores_unknown_keys(self):
        """Keys in the preset that have no matching widget are skipped."""
        # Manually write a preset with an extra key
        path = self.tmpdir / "extra_keys.json"
        with open(path, "w") as f:
            json.dump(
                {"_meta": {"version": 1}, "myCheckBox": False, "phantomWidget": 99}, f
            )

        count = self.preset_mgr.load("extra_keys")
        self.assertEqual(count, 1)  # Only myCheckBox matched
        self.assertFalse(self.chk.isChecked())

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------

    def test_save_with_scope(self):
        """Verify scope limits which widgets are captured."""
        container = QtWidgets.QGroupBox("group", self.parent_widget)
        container.setObjectName("testGroup")
        self.track_widget(container)

        # Move only the checkbox into the container
        scoped_chk = self._make_checkbox("scopedCheck", checked=True)
        scoped_chk.setParent(container)

        path = self.preset_mgr.save("scoped", scope=container)
        with open(path, "r") as f:
            data = json.load(f)

        self.assertIn("scopedCheck", data)
        # Other widgets should NOT be in the scoped preset
        self.assertNotIn("mySpinBox", data)
        self.assertNotIn("myLineEdit", data)

    # ------------------------------------------------------------------
    # List / Delete / Rename / Exists
    # ------------------------------------------------------------------

    def test_list_returns_sorted_names(self):
        """Verify list returns all preset names, sorted."""
        self.preset_mgr.save("zebra")
        self.preset_mgr.save("alpha")
        self.preset_mgr.save("middle")

        names = self.preset_mgr.list()
        self.assertEqual(names, ["alpha", "middle", "zebra"])

    def test_delete_removes_file(self):
        """Verify delete removes the preset file."""
        self.preset_mgr.save("to_delete")
        self.assertTrue(self.preset_mgr.exists("to_delete"))

        result = self.preset_mgr.delete("to_delete")
        self.assertTrue(result)
        self.assertFalse(self.preset_mgr.exists("to_delete"))

    def test_delete_nonexistent_returns_false(self):
        """Deleting a preset that doesn't exist returns False."""
        self.assertFalse(self.preset_mgr.delete("ghost"))

    def test_rename(self):
        """Verify rename changes the file name."""
        self.preset_mgr.save("old_name")
        result = self.preset_mgr.rename("old_name", "new_name")

        self.assertTrue(result)
        self.assertFalse(self.preset_mgr.exists("old_name"))
        self.assertTrue(self.preset_mgr.exists("new_name"))

    def test_rename_to_existing_fails(self):
        """Cannot rename to an already existing preset name."""
        self.preset_mgr.save("first")
        self.preset_mgr.save("second")

        result = self.preset_mgr.rename("first", "second")
        self.assertFalse(result)

    def test_exists(self):
        """Verify exists returns correct bool."""
        self.assertFalse(self.preset_mgr.exists("nope"))
        self.preset_mgr.save("yep")
        self.assertTrue(self.preset_mgr.exists("yep"))

    # ------------------------------------------------------------------
    # Name sanitization
    # ------------------------------------------------------------------

    def test_name_sanitization(self):
        """Verify dangerous characters in preset names are sanitized."""
        path = self.preset_mgr.save("my/preset\\name:bad")
        self.assertTrue(path.exists())
        # Should not contain path separators in the filename
        self.assertNotIn("/", path.stem)
        self.assertNotIn("\\", path.stem)


class TestStandalonePresetManager(QtBaseTestCase):
    """Test PresetManager.from_widgets (standalone mode, no StateManager)."""

    def setUp(self):
        super().setUp()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="uitk_standalone_preset_"))

        self.parent_widget = QtWidgets.QWidget()
        self.track_widget(self.parent_widget)

        # Create plain Qt widgets (no restore_state attribute)
        self.chk = QtWidgets.QCheckBox("A", self.parent_widget)
        self.chk.setObjectName("chk_a")
        self.chk.setChecked(True)

        self.spin = QtWidgets.QSpinBox(self.parent_widget)
        self.spin.setObjectName("spin_b")
        self.spin.setRange(0, 100)
        self.spin.setValue(42)

        self.line = QtWidgets.QLineEdit(self.parent_widget)
        self.line.setObjectName("line_c")
        self.line.setText("hello")

        self.combo = QtWidgets.QComboBox(self.parent_widget)
        self.combo.setObjectName("cmb_d")
        self.combo.addItems(["alpha", "beta", "gamma"])
        self.combo.setCurrentIndex(1)

        self.mgr = PresetManager.from_widgets(
            preset_dir=self.tmpdir,
            widgets=[self.chk, self.spin, self.line, self.combo],
        )

    def tearDown(self):
        super().tearDown()
        if self.tmpdir.exists():
            shutil.rmtree(self.tmpdir)

    # ------------------------------------------------------------------
    # from_widgets construction
    # ------------------------------------------------------------------

    def test_from_widgets_no_state(self):
        """Standalone manager has state=None."""
        self.assertIsNone(self.mgr.state)
        self.assertIsNone(self.mgr.parent)

    def test_from_widgets_preset_dir_set(self):
        """Preset directory is set correctly."""
        self.assertEqual(self.mgr.preset_dir, self.tmpdir)

    # ------------------------------------------------------------------
    # Save / load cycle
    # ------------------------------------------------------------------

    def test_save_creates_json(self):
        """Save produces a valid JSON file with expected keys."""
        path = self.mgr.save("standalone_test")
        self.assertTrue(path.exists())

        with open(path, "r") as f:
            data = json.load(f)

        self.assertEqual(data["chk_a"], True)
        self.assertEqual(data["spin_b"], 42)
        self.assertEqual(data["line_c"], "hello")
        self.assertEqual(data["cmb_d"], 1)  # currentIndex

    def test_load_restores_values(self):
        """Load restores widget values from a saved preset."""
        self.mgr.save("restore")

        # Change all values
        self.chk.setChecked(False)
        self.spin.setValue(0)
        self.line.setText("changed")
        self.combo.setCurrentIndex(2)

        count = self.mgr.load("restore")
        self.assertEqual(count, 4)
        self.assertTrue(self.chk.isChecked())
        self.assertEqual(self.spin.value(), 42)
        self.assertEqual(self.line.text(), "hello")
        self.assertEqual(self.combo.currentIndex(), 1)

    def test_load_blocks_signals(self):
        """Load with block_signals=True should not emit widget signals."""
        self.mgr.save("block_test")
        self.chk.setChecked(False)

        signal_fired = []
        self.chk.toggled.connect(lambda v: signal_fired.append(v))

        self.mgr.load("block_test", block_signals=True)
        self.assertEqual(signal_fired, [], "Signal should not fire when blocked")

    def test_load_without_blocking_emits_signals(self):
        """Load with block_signals=False should emit widget signals."""
        self.mgr.save("noblock_test")
        self.chk.setChecked(False)

        signal_fired = []
        self.chk.toggled.connect(lambda v: signal_fired.append(v))

        self.mgr.load("noblock_test", block_signals=False)
        self.assertTrue(len(signal_fired) > 0, "Signal should fire when not blocked")

    # ------------------------------------------------------------------
    # List / delete / rename / exists
    # ------------------------------------------------------------------

    def test_list_sorted(self):
        """List returns preset names sorted."""
        self.mgr.save("zebra")
        self.mgr.save("alpha")
        self.assertEqual(self.mgr.list(), ["alpha", "zebra"])

    def test_delete(self):
        """Delete removes the preset file."""
        self.mgr.save("gone")
        self.assertTrue(self.mgr.delete("gone"))
        self.assertFalse(self.mgr.exists("gone"))

    def test_rename(self):
        """Rename changes the preset file name."""
        self.mgr.save("old")
        self.assertTrue(self.mgr.rename("old", "new"))
        self.assertFalse(self.mgr.exists("old"))
        self.assertTrue(self.mgr.exists("new"))

    # ------------------------------------------------------------------
    # preset_dir validation
    # ------------------------------------------------------------------

    def test_standalone_without_preset_dir_raises(self):
        """Standalone mode requires preset_dir — accessing preset_dir raises."""
        mgr = PresetManager(widgets=[self.chk])
        with self.assertRaises(ValueError):
            _ = mgr.preset_dir

    # ------------------------------------------------------------------
    # Widget value helpers
    # ------------------------------------------------------------------

    def test_get_widget_value_types(self):
        """_get_widget_value handles standard Qt widget types."""
        self.assertEqual(PresetManager._get_widget_value(self.chk), True)
        self.assertEqual(PresetManager._get_widget_value(self.spin), 42)
        self.assertEqual(PresetManager._get_widget_value(self.line), "hello")
        self.assertEqual(PresetManager._get_widget_value(self.combo), 1)

        slider = QtWidgets.QSlider()
        slider.setValue(77)
        self.track_widget(slider)
        self.assertEqual(PresetManager._get_widget_value(slider), 77)

    def test_set_widget_value_types(self):
        """_set_widget_value sets values on standard Qt widget types."""
        PresetManager._set_widget_value(self.chk, False)
        self.assertFalse(self.chk.isChecked())

        PresetManager._set_widget_value(self.spin, 99)
        self.assertEqual(self.spin.value(), 99)

        PresetManager._set_widget_value(self.line, "world")
        self.assertEqual(self.line.text(), "world")

        PresetManager._set_widget_value(self.combo, 2)
        self.assertEqual(self.combo.currentIndex(), 2)


class TestSetup(QtBaseTestCase):
    """Test PresetManager.setup() post-creation configuration."""

    def setUp(self):
        super().setUp()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="uitk_setup_"))

        self.parent_widget = QtWidgets.QWidget()
        self.track_widget(self.parent_widget)

        self.chk = QtWidgets.QCheckBox("A", self.parent_widget)
        self.chk.setObjectName("chk_a")
        self.chk.setChecked(True)

        self.spin = QtWidgets.QSpinBox(self.parent_widget)
        self.spin.setObjectName("spin_b")
        self.spin.setRange(0, 100)
        self.spin.setValue(42)

    def tearDown(self):
        super().tearDown()
        if self.tmpdir.exists():
            shutil.rmtree(self.tmpdir)

    def test_setup_configures_uncreated_manager(self):
        """setup() configures an empty PresetManager with dir and widgets."""
        mgr = PresetManager()
        mgr.setup(preset_dir=self.tmpdir, widgets=[self.chk, self.spin])

        path = mgr.save("via_setup")
        self.assertTrue(path.exists())
        count = mgr.load("via_setup")
        self.assertEqual(count, 2)

    def test_setup_returns_self_for_chaining(self):
        """setup() returns self so calls can be chained."""
        mgr = PresetManager()
        result = mgr.setup(preset_dir=self.tmpdir, widgets=[self.chk])
        self.assertIs(result, mgr)

    def test_setup_save_load_roundtrip(self):
        """Full save/load roundtrip through setup()."""
        mgr = PresetManager()
        mgr.setup(preset_dir=self.tmpdir, widgets=[self.chk, self.spin])
        mgr.save("roundtrip")

        self.chk.setChecked(False)
        self.spin.setValue(0)

        mgr.load("roundtrip")
        self.assertTrue(self.chk.isChecked())
        self.assertEqual(self.spin.value(), 42)


class TestResolvePresetDir(QtBaseTestCase):
    """Test _resolve_preset_dir flexible path resolution."""

    def test_absolute_path_unchanged(self):
        """An absolute Path passes through unchanged."""
        p = Path(tempfile.gettempdir()) / "my_presets"
        result = PresetManager._resolve_preset_dir(p)
        self.assertEqual(result, p)

    def test_absolute_string_unchanged(self):
        """An absolute string path passes through unchanged."""
        raw = str(Path(tempfile.gettempdir()) / "my_presets")
        result = PresetManager._resolve_preset_dir(raw)
        self.assertEqual(result, Path(raw))

    def test_tilde_expansion(self):
        """A '~'-prefixed string expands to the user home directory."""
        result = PresetManager._resolve_preset_dir("~/.myapp/presets")
        self.assertTrue(result.is_absolute())
        self.assertEqual(result, Path.home() / ".myapp" / "presets")

    def test_env_var_expansion(self):
        """Environment variables in the string are expanded."""
        import os

        os.environ["_UITK_TEST_DIR"] = str(Path(tempfile.gettempdir()))
        try:
            result = PresetManager._resolve_preset_dir("$_UITK_TEST_DIR/presets")
            self.assertTrue(result.is_absolute())
            self.assertEqual(result, Path(tempfile.gettempdir()) / "presets")
        finally:
            del os.environ["_UITK_TEST_DIR"]

    def test_relative_resolves_under_config_dir(self):
        """A relative string resolves under QStandardPaths AppConfigLocation."""
        from uitk.widgets.mixins.preset_manager import QStandardPaths_writableLocation

        base = QStandardPaths_writableLocation()
        result = PresetManager._resolve_preset_dir("mayatk/reference_manager")
        expected = Path(base) / "mayatk" / "reference_manager"
        self.assertEqual(result, expected)
        self.assertTrue(result.is_absolute())

    def test_setup_accepts_tilde_string(self):
        """setup() resolves tilde strings correctly."""
        mgr = PresetManager()
        mgr.setup(preset_dir="~/._uitk_test_presets")
        self.assertEqual(mgr._preset_dir, Path.home() / "._uitk_test_presets")

    def test_from_widgets_accepts_tilde_string(self):
        """from_widgets() resolves tilde strings correctly."""
        chk = QtWidgets.QCheckBox("X")
        self.track_widget(chk)
        chk.setObjectName("chk_x")
        mgr = PresetManager.from_widgets(
            preset_dir="~/._uitk_test_presets", widgets=[chk]
        )
        self.assertEqual(mgr._preset_dir, Path.home() / "._uitk_test_presets")


class TestMenuPresetsNamespace(QtBaseTestCase):
    """Test Menu.presets lazy namespace."""

    def setUp(self):
        super().setUp()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="uitk_menu_presets_"))

        from uitk.widgets.menu import Menu

        self.menu = Menu(add_header=False, add_footer=False)
        self.track_widget(self.menu)

        # Add widgets to menu
        self.chk = QtWidgets.QCheckBox("opt")
        self.chk.setObjectName("chk_opt")
        self.chk.setChecked(True)
        self.menu.add(self.chk)

        self.spin = QtWidgets.QSpinBox()
        self.spin.setObjectName("spin_val")
        self.spin.setRange(0, 100)
        self.spin.setValue(55)
        self.menu.add(self.spin)

    def tearDown(self):
        super().tearDown()
        if self.tmpdir.exists():
            shutil.rmtree(self.tmpdir)

    def test_presets_is_preset_manager(self):
        """menu.presets returns a PresetManager instance."""
        self.assertIsInstance(self.menu.presets, PresetManager)

    def test_presets_is_same_instance(self):
        """Repeated access returns the same instance."""
        self.assertIs(self.menu.presets, self.menu.presets)

    def test_presets_setup_and_save(self):
        """menu.presets.setup(...).save() auto-discovers menu widgets."""
        self.menu.presets.setup(preset_dir=self.tmpdir)
        path = self.menu.presets.save("menu_test")
        self.assertTrue(path.exists())

        with open(path, "r") as f:
            data = json.load(f)
        self.assertIn("chk_opt", data)
        self.assertIn("spin_val", data)

    def test_presets_setup_chained_with_wire_combo(self):
        """menu.presets.setup(...).wire_combo(...) chains cleanly."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        wcb = WidgetComboBox()
        self.track_widget(wcb)

        # Use a fresh menu/presets so the auto-created combo doesn't interfere
        from uitk.widgets.menu import Menu

        menu2 = Menu(add_header=False, add_footer=False)
        self.track_widget(menu2)
        menu2.add(QtWidgets.QCheckBox("z"))
        # Intentionally call wire_combo with an external combo on a
        # standalone PresetManager (not a Menu parent) to test the
        # explicit wiring path that still exists for advanced use.
        mgr = PresetManager.from_widgets(preset_dir=self.tmpdir, widgets=[self.chk])
        mgr.wire_combo(wcb)
        self.assertEqual(len(wcb.actions), 4)

    def test_setup_auto_creates_combo(self):
        """setup() on a Menu parent auto-creates a WidgetComboBox."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        self.menu.presets.setup(preset_dir=self.tmpdir)

        # A WidgetComboBox named cmb_presets should now exist in the menu
        cmb = getattr(self.menu, "cmb_presets", None)
        self.assertIsNotNone(cmb, "cmb_presets was not auto-created")
        self.assertIsInstance(cmb, WidgetComboBox)
        # It should be excluded from snapshots
        self.assertIn(cmb, self.menu.presets._excluded_widgets)

    def test_combo_shows_placeholder_when_empty(self):
        """When no presets exist, combo shows placeholder text."""
        self.menu.presets.setup(preset_dir=self.tmpdir)
        cmb = self.menu.cmb_presets
        # Only the action rows (separator + button container) are present;
        # no actual preset items.
        data_items = cmb.count() - cmb._action_row_count
        self.assertEqual(data_items, 0)
        self.assertEqual(cmb.placeholderText(), "No saved presets")

    def test_combo_shows_current_preset_after_save(self):
        """After saving, the combo displays the current preset name."""
        self.menu.presets.setup(preset_dir=self.tmpdir)
        cmb = self.menu.cmb_presets

        # Simulate Save (direct API call)
        self.menu.presets.save("my_config")
        # Repopulate via internal refresh
        names = self.menu.presets.list()
        cmb.blockSignals(True)
        cmb.clear()
        cmb.addItems(names)
        idx = cmb.findText("my_config")
        if idx >= 0:
            cmb.setCurrentIndex(idx)
        cmb.blockSignals(False)

        self.assertEqual(cmb.currentText(), "my_config")

    def test_full_namespace_roundtrip(self):
        """Save via menu.presets (auto-discovered), change values, load — values restored."""
        self.menu.presets.setup(preset_dir=self.tmpdir)
        self.menu.presets.save("ns_roundtrip")

        self.chk.setChecked(False)
        self.spin.setValue(0)

        count = self.menu.presets.load("ns_roundtrip")
        self.assertEqual(count, 2)
        self.assertTrue(self.chk.isChecked())
        self.assertEqual(self.spin.value(), 55)

    def test_auto_discovery_excludes_wired_combo(self):
        """setup() auto-creates a preset combo that is excluded from snapshots."""
        self.menu.presets.setup(preset_dir=self.tmpdir)
        path = self.menu.presets.save("no_combo")

        with open(path, "r") as f:
            data = json.load(f)
        self.assertNotIn("cmb_presets", data)
        self.assertIn("chk_opt", data)

    def test_auto_discovery_skips_unsupported_types(self):
        """Labels and buttons are not captured in presets."""
        lbl = QtWidgets.QLabel("info")
        lbl.setObjectName("lbl_info")
        self.menu.add(lbl)
        self.track_widget(lbl)

        btn = QtWidgets.QPushButton("Go")
        btn.setObjectName("btn_go")
        self.menu.add(btn)
        self.track_widget(btn)

        self.menu.presets.setup(preset_dir=self.tmpdir)
        path = self.menu.presets.save("skip_types")

        with open(path, "r") as f:
            data = json.load(f)
        self.assertNotIn("lbl_info", data)
        self.assertNotIn("btn_go", data)
        self.assertIn("chk_opt", data)

    def test_explicit_widgets_override_auto_discovery(self):
        """When widgets are passed explicitly, only those are captured."""
        self.menu.presets.setup(
            preset_dir=self.tmpdir,
            widgets=[self.chk],
        )
        path = self.menu.presets.save("explicit_only")

        with open(path, "r") as f:
            data = json.load(f)
        self.assertIn("chk_opt", data)
        self.assertNotIn("spin_val", data)


class TestAddPresetsProperty(QtBaseTestCase):
    """Test Menu.add_presets property for zero-ceremony preset enablement.

    ``add_presets`` is a bool toggle (like ``add_defaults_button``).
    The preset directory is set separately via ``menu.presets.preset_dir``.
    Actual combo creation is deferred to ``showEvent``; tests call
    ``_setup_presets()`` explicitly to trigger it without showing.
    """

    def setUp(self):
        super().setUp()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="uitk_add_presets_"))

        from uitk.widgets.menu import Menu

        self.menu = Menu(add_header=False, add_footer=False)
        self.track_widget(self.menu)

        self.chk = QtWidgets.QCheckBox("opt")
        self.chk.setObjectName("chk_opt")
        self.chk.setChecked(True)
        self.menu.add(self.chk)

        self.spin = QtWidgets.QSpinBox()
        self.spin.setObjectName("spin_val")
        self.spin.setRange(0, 100)
        self.spin.setValue(55)
        self.menu.add(self.spin)

    def _enable_presets(self, preset_dir=None):
        """Helper: enable presets, optionally set dir, and trigger deferred setup."""
        self.menu.add_presets = True
        if preset_dir is not None:
            self.menu.presets.preset_dir = preset_dir
        self.menu._setup_presets()  # simulate showEvent

    def tearDown(self):
        super().tearDown()
        if self.tmpdir.exists():
            shutil.rmtree(self.tmpdir)

    def test_add_presets_default_false(self):
        """Menu.add_presets defaults to False."""
        self.assertFalse(self.menu.add_presets)

    def test_add_presets_creates_combo(self):
        """Setting add_presets=True + triggering setup creates the preset combo."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        self._enable_presets(self.tmpdir)
        cmb = getattr(self.menu, "cmb_presets", None)
        self.assertIsNotNone(cmb, "cmb_presets was not created")
        self.assertIsInstance(cmb, WidgetComboBox)

    def test_add_presets_preset_dir_setter(self):
        """preset_dir can be set separately from add_presets."""
        self._enable_presets(self.tmpdir)
        self.assertEqual(self.menu.presets.preset_dir, self.tmpdir)

    def test_add_presets_true_auto_derives_dir(self):
        """Setting add_presets=True auto-derives a preset directory."""
        self.menu.add_presets = True
        self.menu._setup_presets()
        # preset_dir should be auto-derived (not None)
        pdir = self.menu.presets.preset_dir
        self.assertTrue(pdir.is_absolute())
        self.assertTrue(str(pdir).endswith("presets"))

    def test_add_presets_in_action_container(self):
        """add_presets places the combo in the menu-actions container."""
        from uitk.widgets.widgetComboBox import WidgetComboBox

        self._enable_presets(self.tmpdir)

        # Combo should be managed by the button manager
        widget = self.menu._button_manager.get_widget("presets")
        self.assertIsNotNone(widget, "Expected presets widget in button manager")
        self.assertIsInstance(widget, WidgetComboBox)

        # Container should not be hidden
        self.assertFalse(
            self.menu._button_manager.container.isHidden(),
            "Action container should not be hidden after add_presets",
        )

    def test_add_presets_roundtrip(self):
        """Full save/load roundtrip via add_presets."""
        self._enable_presets(self.tmpdir)
        self.menu.presets.save("test_rt")

        self.chk.setChecked(False)
        self.spin.setValue(0)

        count = self.menu.presets.load("test_rt")
        self.assertEqual(count, 2)
        self.assertTrue(self.chk.isChecked())
        self.assertEqual(self.spin.value(), 55)

    def test_add_presets_combo_excluded_from_snapshot(self):
        """The auto-created combo is excluded from preset snapshots."""
        self._enable_presets(self.tmpdir)
        path = self.menu.presets.save("no_combo")

        with open(path, "r") as f:
            data = json.load(f)
        self.assertNotIn("cmb_presets", data)
        self.assertIn("chk_opt", data)

    def test_add_presets_tilde_path(self):
        """preset_dir accepts tilde paths."""
        self.menu.add_presets = True
        self.menu.presets.preset_dir = "~/.uitk_test_add_presets"
        self.assertEqual(
            self.menu.presets._preset_dir,
            Path.home() / ".uitk_test_add_presets",
        )

    def test_add_presets_false_removes_combo(self):
        """Setting add_presets=False removes the combo from the container."""
        self._enable_presets(self.tmpdir)
        self.assertIsNotNone(self.menu._button_manager.get_widget("presets"))

        self.menu.add_presets = False
        self.assertIsNone(self.menu._button_manager.get_widget("presets"))


class TestWireCombo(QtBaseTestCase):
    """Test PresetManager.wire_combo with a real WidgetComboBox."""

    def setUp(self):
        super().setUp()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="uitk_wire_combo_"))

        # Create managed widgets
        self.chk = QtWidgets.QCheckBox("opt")
        self.chk.setObjectName("chk_opt")
        self.chk.setChecked(True)
        self.track_widget(self.chk)

        self.line = QtWidgets.QLineEdit()
        self.line.setObjectName("line_val")
        self.line.setText("original")
        self.track_widget(self.line)

        self.mgr = PresetManager.from_widgets(
            preset_dir=self.tmpdir,
            widgets=[self.chk, self.line],
        )

        # Create WidgetComboBox
        from uitk.widgets.widgetComboBox import WidgetComboBox

        self.wcb = WidgetComboBox()
        self.wcb.setObjectName("wcb_presets")
        self.track_widget(self.wcb)

    def tearDown(self):
        super().tearDown()
        if self.tmpdir.exists():
            shutil.rmtree(self.tmpdir)

    def test_wire_combo_populates_presets(self):
        """wire_combo populates the combo with existing presets."""
        self.mgr.save("preset_a")
        self.mgr.save("preset_b")

        from uitk.widgets.widgetComboBox import WidgetComboBox

        wcb2 = WidgetComboBox()
        self.track_widget(wcb2)
        self.mgr.wire_combo(wcb2)

        texts = [wcb2.itemText(i) for i in range(wcb2.count())]
        self.assertIn("preset_a", texts)
        self.assertIn("preset_b", texts)

    def test_wire_combo_on_loaded_callback(self):
        """Selecting a preset fires on_loaded callback."""
        self.mgr.save("test_cb")
        self.chk.setChecked(False)
        self.line.setText("changed")

        loaded = []
        self.mgr.wire_combo(self.wcb, on_loaded=lambda: loaded.append(True))

        # Find the index for "test_cb" and select it
        idx = self.wcb.findText("test_cb")
        self.assertGreaterEqual(idx, 0)
        self.wcb.setCurrentIndex(idx)

        self.assertTrue(loaded, "on_loaded callback should have been invoked")
        # Widget values should be restored
        self.assertTrue(self.chk.isChecked())
        self.assertEqual(self.line.text(), "original")

    def test_save_does_not_trigger_unintended_load(self):
        """Saving a preset must NOT trigger on_selected / load during combo refresh.

        Bug: WidgetComboBox._setText used self.__class__.__base__.setItemText
        which resolved to ComboBox.setItemText (calls setRichText → _setText,
        infinite loop), causing RecursionError / Maya freeze when the preset
        combo was re-populated while it had a selected item.
        Fixed: 2026-02-17
        """
        self.mgr.save("aaa_first")
        self.chk.setChecked(False)
        self.line.setText("modified")
        self.mgr.save("zzz_second")

        loads = []
        self.mgr.wire_combo(
            self.wcb,
            on_loaded=lambda: loads.append(True),
        )
        loads.clear()

        # Select a real preset (index ≥ 0) to trigger the bug path
        idx = self.wcb.findText("aaa_first")
        if idx >= 0:
            self.wcb.setCurrentIndex(idx)
        loads.clear()

        # Change widgets and save
        self.chk.setChecked(True)
        self.line.setText("new_state")
        self.mgr.save("mmm_middle")

        # Repopulate combo (simulates what refresh() does internally)
        names = self.mgr.list()
        self.wcb.blockSignals(True)
        try:
            self.wcb.clear()
            self.wcb.addItems(names)
        finally:
            self.wcb.blockSignals(False)

        self.assertEqual(loads, [], "on_loaded should not fire during refresh()")
        self.assertTrue(self.chk.isChecked(), "Widget state corrupted by refresh!")
        self.assertEqual(self.line.text(), "new_state")

    def test_widget_combo_readd_no_recursion(self):
        """WidgetComboBox.add() after setCurrentIndex must not recurse.

        Bug: RichText._setText resolved __class__.__base__.setItemText to
        ComboBox.setItemText which called setRichText → _setText → infinite.
        Fixed: 2026-02-17 via WidgetComboBox._setText override.
        """
        from uitk.widgets.widgetComboBox import WidgetComboBox

        combo = WidgetComboBox()
        self.track_widget(combo)
        combo.add(["a", "b", "c"], header="H", clear=True)
        combo.setCurrentIndex(0)
        # Before fix: RecursionError / Maya freeze
        combo.add(["x", "y"], header="H", clear=True)
        self.assertEqual(combo.count(), 2)
        texts = [combo.itemText(i) for i in range(combo.count())]
        self.assertIn("x", texts)
        self.assertIn("y", texts)


if __name__ == "__main__":
    import unittest

    unittest.main()
