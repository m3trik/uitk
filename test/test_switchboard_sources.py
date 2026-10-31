# !/usr/bin/python
# coding=utf-8
import unittest
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

from conftest import QtBaseTestCase
from uitk.switchboard import Switchboard


class TestSwitchboardSources(QtBaseTestCase):
    """Tests for Switchboard source input handling."""

    def setUp(self):
        super().setUp()
        self.mock_app = MagicMock()
        self.mock_app.instance.return_value = self.mock_app

        # Create dummy file structure for testing
        self.test_dir = os.path.join(os.path.dirname(__file__), "temp_source_tests")
        os.makedirs(self.test_dir, exist_ok=True)

        # Create dummy UI file
        with open(os.path.join(self.test_dir, "test.ui"), "w") as f:
            f.write("<?xml version='1.0'?><ui version='4.0'></ui>")

        # Create dummy Python file
        with open(os.path.join(self.test_dir, "test_slots.py"), "w") as f:
            f.write("class TestSlots: pass")

    def tearDown(self):
        import shutil
        import gc

        # Force garbage collection to release file handles
        gc.collect()

        # Retry cleanup
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except OSError:
                # Simple retry logic or ignore if really stuck (OS timing)
                try:
                    import time

                    time.sleep(0.1)
                    shutil.rmtree(self.test_dir)
                except OSError:
                    pass  # We tried our best, temporary files might persist manually cleanup later

        super().tearDown()

    def test_single_string_path(self):
        """Test sources as single string paths."""
        sb = Switchboard(
            ui_source=self.test_dir,
            slot_source=self.test_dir,
            base_dir=None,  # Absolute paths used
        )

        self.assertTrue(len(sb.registry.containers) > 0)
        # Check if UI registry found the test.ui
        ui_files = [f.filename for f in sb.registry.ui_registry]
        self.assertIn("test", ui_files)

        # Check if Slots registry found test_slots.py class
        slot_classes = [c.classname for c in sb.registry.slot_registry]
        self.assertIn("TestSlots", slot_classes)

    def test_list_of_paths(self):
        """Test sources as list of paths."""
        sb = Switchboard(
            ui_source=[self.test_dir, self.test_dir],  # Duplicate just to test list
            base_dir=None,
        )
        self.assertTrue(len(sb.registry.ui_registry) >= 1)

    def test_a_relative_source_resolves_beside_the_calling_file(self):
        """Regression: the deprecation wrapper on ``Switchboard.__init__``
        (``ptk.Deprecation.parameter``) added pythontk's ``deprecation.py`` to
        the frame chain the default ``base_dir`` counts, so a relative
        ``ui_source`` -- every quickstart's ``"editor.ui"`` -- resolved under
        ``pythontk/core_utils`` and the app found no UI. Fixed: 2026-10-31."""
        import importlib.util

        caller = os.path.join(self.test_dir, "caller_app.py")
        with open(caller, "w") as f:
            f.write(
                "from uitk.switchboard import Switchboard\n\n"
                "def build():\n"
                "    return Switchboard(ui_source='test.ui')\n"
            )
        spec = importlib.util.spec_from_file_location("caller_app", caller)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        sb = module.build()

        paths = [os.path.normcase(e.filepath) for e in sb.registry.ui_registry]
        self.assertIn(
            os.path.normcase(os.path.join(self.test_dir, "test.ui")), paths
        )

    def test_a_slots_class_passed_in_is_registered_without_importing_its_file(self):
        """Regression: a class handed to ``slot_source`` was found again by
        scanning its file, which imported that file a second time (a loose one
        as ``<stem>_ptk_loader_<id>``): the registry held a copy that was not the
        class given, and the README quickstart (no ``__main__`` guard) re-ran
        itself, nested, until it crashed. Fixed: 2026-10-31."""
        import importlib.util

        runs = os.path.join(self.test_dir, "runs.txt")
        app = os.path.join(self.test_dir, "loose_app.py")
        with open(app, "w") as f:
            f.write(
                f"with open({runs!r}, 'a') as log:\n"
                "    log.write('run\\n')\n\n"
                "class LooseSlots:\n"
                "    def __init__(self, switchboard):\n"
                "        self.sb = switchboard\n"
            )
        spec = importlib.util.spec_from_file_location("loose_app", app)
        module = importlib.util.module_from_spec(spec)
        sys.modules["loose_app"] = module  # imported, as a script's __main__ is
        self.addCleanup(sys.modules.pop, "loose_app", None)
        spec.loader.exec_module(module)

        sb = Switchboard(slot_source=module.LooseSlots, base_dir=None)

        registered = sb.registry.slot_registry.get(
            classname="LooseSlots", return_field="classobj"
        )
        self.assertIs(registered, module.LooseSlots)
        with open(runs) as log:
            self.assertEqual(log.read().count("run"), 1, "the file was imported again")

    def test_tuple_of_paths(self):
        """Test sources as tuple of paths."""
        sb = Switchboard(ui_source=(self.test_dir,), base_dir=None)
        # Should contain 'test'
        self.assertEqual(sb.registry.ui_registry[0].filename, "test")

    def test_module_object(self):
        """Test sources as module objects."""
        # Create a dummy module
        mod = ModuleType("dummy_module")
        mod.__file__ = os.path.join(self.test_dir, "__init__.py")
        sys.modules["dummy_module"] = mod

        try:
            sb = Switchboard(ui_source=mod, base_dir=None)
            # Since mod.__file__ points to test_dir, it should scan test_dir
            self.assertEqual(sb.registry.ui_registry[0].filename, "test")
        finally:
            del sys.modules["dummy_module"]

    def test_list_of_mixed_types(self):
        """Test sources as list of mixed types (str and module)."""
        mod = ModuleType("dummy_module")
        mod.__file__ = os.path.join(self.test_dir, "__init__.py")

        sb = Switchboard(ui_source=[self.test_dir, mod], base_dir=None)
        # It should process both. Since they point to same dir, we might get dupes
        # FileRegistry logic might handle duplicates if configured,
        # but here we just check it doesn't crash
        self.assertTrue(len(sb.registry.ui_registry) >= 1)

    def test_none_sources(self):
        """Test None for sources."""
        sb = Switchboard(ui_source=None)
        self.assertEqual(len(sb.registry.ui_registry), 0)

    def test_base_dir_resolution(self):
        """Test relative path resolution using base_dir."""
        # Relative path
        rel_path = "temp_source_tests"
        base = os.path.dirname(__file__)

        sb = Switchboard(ui_source=rel_path, base_dir=base)
        self.assertEqual(sb.registry.ui_registry[0].filename, "test")

    def test_modify_registry_post_init(self):
        """Test modifying sources after initialization."""
        sb = Switchboard(ui_source=None)

        # Verify empty
        self.assertEqual(len(sb.registry.ui_registry), 0)

        # Test the register method
        sb.register(ui_location=self.test_dir)

        # Verify updated
        self.assertTrue(
            len(sb.registry.ui_registry) > 0, "UI registry should not be empty"
        )
        self.assertIn("test", [f.filename for f in sb.registry.ui_registry])

    def test_register_leaves_out_the_excluded_files(self):
        """``exclude`` drops a file from every location the call registers: the
        .ui from ui_location, the module from slot_location."""
        for name in ("kept", "dropped"):
            with open(os.path.join(self.test_dir, f"{name}.ui"), "w") as f:
                f.write("<?xml version='1.0'?><ui version='4.0'></ui>")
            with open(os.path.join(self.test_dir, f"{name}.py"), "w") as f:
                f.write(f"class {name.title()}Slots: pass")
        sb = Switchboard(ui_source=None)

        sb.register(
            ui_location=self.test_dir, slot_location=self.test_dir, exclude=["dropped.*"]
        )

        uis = [f.filename for f in sb.registry.ui_registry]
        self.assertIn("kept", uis)
        self.assertNotIn("dropped", uis)
        classes = [row.classname for row in sb.registry.slot_registry]
        self.assertIn("KeptSlots", classes)
        self.assertNotIn("DroppedSlots", classes)

    def test_register_exclude_keeps_the_registrys_own_exclusions(self):
        """A slot scan still skips a compiled ``*_ui.py`` when ``exclude`` is given."""
        with open(os.path.join(self.test_dir, "panel_ui.py"), "w") as f:
            f.write("class Ui_Panel: pass")
        sb = Switchboard(ui_source=None)

        sb.register(slot_location=self.test_dir, exclude="nothing.*")

        classes = [row.classname for row in sb.registry.slot_registry]
        self.assertIn("TestSlots", classes)
        self.assertNotIn("Ui_Panel", classes)

    def test_register_icons(self):
        """Test registering icon locations."""
        sb = Switchboard(ui_source=None)

        # Create dummy icon
        with open(os.path.join(self.test_dir, "test_icon.png"), "w") as f:
            f.write("dummy")

        sb.register(icon_location=self.test_dir)

        # Verify
        self.assertTrue(len(sb.registry.icon_registry) > 0)
        filenames = [icon.filename for icon in sb.registry.icon_registry]
        self.assertIn("test_icon", filenames)


class TestCodeBuiltUi(QtBaseTestCase):
    """``Switchboard.register_ui``: a UI built in code resolves, wraps and binds
    as a ``.ui`` file does (2026-10-31)."""

    def setUp(self):
        super().setUp()
        import tempfile

        self.test_dir = tempfile.mkdtemp(prefix="uitk_code_built_")
        with open(os.path.join(self.test_dir, "tool_slots.py"), "w") as f:
            f.write(
                "class ToolSlots:\n"
                "    def __init__(self, switchboard):\n"
                "        self.sb = switchboard\n"
                "        self.calls = []\n\n"
                "    def b000(self, *args):\n"
                "        self.calls.append('b000')\n"
            )
        self.built = []

    def tearDown(self):
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)
        super().tearDown()

    def _build(self):
        from qtpy import QtWidgets

        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        button = QtWidgets.QPushButton("Go")
        button.setObjectName("b000")
        layout.addWidget(button)
        self.built.append(widget)
        return widget

    def test_a_registered_ui_builds_once_on_first_ask_and_binds_by_object_name(self):
        from qtpy import QtWidgets

        sb = Switchboard(slot_source=self.test_dir, base_dir=None)
        sb.register_ui("tool", self._build)
        self.assertTrue(sb.is_registered_ui("tool"))
        self.assertTrue(sb.ui_name_resolves("tool"))
        self.assertEqual(self.built, [], "built before anything asked for it")

        ui = sb.loaded_ui.tool
        self.assertIsInstance(ui, sb.registered_widgets.MainWindow)
        self.assertIs(sb.get_ui("tool"), ui)
        self.assertEqual(len(self.built), 1)

        ui.show()
        for _ in range(5):
            QtWidgets.QApplication.processEvents()
        ui.findChild(QtWidgets.QPushButton, "b000").click()
        self.assertEqual(sb.get_slots_instance(ui).calls, ["b000"])
        ui.close()

    def test_a_builder_that_returns_no_widget_is_named(self):
        sb = Switchboard(slot_source=self.test_dir, base_dir=None)
        sb.register_ui("broken", lambda: "not a widget")
        with self.assertRaises(Exception) as raised:
            sb.get_ui("broken")
        self.assertIn("broken", str(raised.exception))

    def test_register_ui_refuses_a_non_callable(self):
        sb = Switchboard(base_dir=None)
        with self.assertRaises(TypeError):
            sb.register_ui("tool", "tool.ui")

    def test_a_ui_file_of_the_same_name_wins(self):
        with open(os.path.join(self.test_dir, "tool.ui"), "w") as f:
            f.write(
                '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n'
                ' <class>tool</class>\n <widget class="QWidget" name="tool"/>\n'
                " <resources/>\n <connections/>\n</ui>\n"
            )
        sb = Switchboard(ui_source=self.test_dir, slot_source=self.test_dir, base_dir=None)
        sb.register_ui("tool", self._build)
        self.assertEqual(sb.loaded_ui.tool.path and os.path.normcase(sb.loaded_ui.tool.path),
                         os.path.normcase(self.test_dir))
        self.assertEqual(self.built, [])


if __name__ == "__main__":
    unittest.main()
