# !/usr/bin/python
# coding=utf-8
"""Tests for ExternalToolHandler — mock-only, no real subprocess / network."""
import sys
import unittest
from unittest.mock import MagicMock, patch

from conftest import setup_qt_application

setup_qt_application()

from uitk import Switchboard
from uitk.handlers.external_tool_handler import ExternalToolHandler


def _make_sb():
    return Switchboard(handlers={"external_tool": ExternalToolHandler})


class TestExternalToolHandlerRegistry(unittest.TestCase):
    def test_handler_attached_to_switchboard(self):
        sb = _make_sb()
        self.assertIsInstance(sb.handlers.external_tool, ExternalToolHandler)

    def test_singleton_key_does_not_collide_with_other_handlers(self):
        """Regression: SingletonMixin._instances is shared across subclasses,
        so two handlers using `singleton_key=id(switchboard)` would collide and
        the second registration would silently return the first handler's
        instance. ExternalToolHandler must scope its key by class."""
        from uitk.handlers.ui_handler import UiHandler

        sb = Switchboard(
            handlers={"ui": UiHandler, "external_tool": ExternalToolHandler}
        )
        self.assertIsInstance(sb.handlers.ui, UiHandler)
        self.assertIsInstance(sb.handlers.external_tool, ExternalToolHandler)
        self.assertIsNot(sb.handlers.ui, sb.handlers.external_tool)

    def test_register_stores_config(self):
        sb = _make_sb()
        sb.handlers.external_tool.register(
            "mytool",
            module="mytool",
            entry="MyToolUI",
            install_spec="mytool==1.0",
        )
        self.assertTrue(sb.handlers.external_tool.is_registered("mytool"))

    def test_launch_unknown_name_without_module_raises(self):
        sb = _make_sb()
        with self.assertRaises(ValueError):
            sb.handlers.external_tool.launch("nonexistent")


class TestExternalToolHandlerLaunch(unittest.TestCase):
    def setUp(self):
        self.sb = _make_sb()
        self.handler = self.sb.handlers.external_tool

    def test_importable_module_skips_install(self):
        """When module is importable, no install should run."""
        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=True
        ) as is_imp, patch("pythontk.PackageManager") as pm, patch.object(
            ExternalToolHandler, "_spawn", return_value=MagicMock()
        ) as spawn:
            self.handler.launch(module="anymod", entry="UI")
        is_imp.assert_called_once()
        pm.assert_not_called()
        spawn.assert_called_once()

    def test_missing_module_triggers_install(self):
        """When module is not importable but install_spec is set, install runs."""
        pm_instance = MagicMock()
        with patch.object(
            ExternalToolHandler,
            "_is_importable",
            side_effect=[False, True],
        ), patch("pythontk.PackageManager", return_value=pm_instance), patch.object(
            ExternalToolHandler, "_spawn", return_value=MagicMock()
        ) as spawn:
            self.handler.launch(
                module="anymod", entry="UI", install_spec="anymod"
            )
        pm_instance.install.assert_called_once_with("anymod")
        spawn.assert_called_once()

    def test_missing_module_without_install_spec_raises(self):
        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=False
        ):
            with self.assertRaises(RuntimeError):
                self.handler.launch(module="missingmod", entry="UI")

    def test_install_that_does_not_make_module_importable_raises(self):
        pm_instance = MagicMock()
        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=False
        ), patch("pythontk.PackageManager", return_value=pm_instance):
            with self.assertRaises(RuntimeError) as ctx:
                self.handler.launch(
                    module="brokenmod", entry="UI", install_spec="brokenmod"
                )
        self.assertIn("still not importable", str(ctx.exception))

    def test_kwargs_override_registered_values(self):
        self.handler.register(
            "tool",
            module="origmod",
            entry="OrigEntry",
            install_spec="origmod",
        )
        captured = {}

        def fake_spawn(**kw):
            captured.update(kw)
            return MagicMock()

        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=True
        ), patch.object(ExternalToolHandler, "_spawn", side_effect=fake_spawn):
            self.handler.launch("tool", module="overridemod", entry="OverrideEntry")
        self.assertEqual(captured["module"], "overridemod")
        self.assertEqual(captured["entry"], "OverrideEntry")


class TestInProcessMode(unittest.TestCase):
    def setUp(self):
        self.sb = _make_sb()
        self.handler = self.sb.handlers.external_tool

    def test_in_process_returns_widget_from_entry(self):
        """In in_process mode, launch() returns whatever entry() returns."""
        sentinel = object()
        fake_mod = MagicMock()
        fake_mod.FakeEntry = MagicMock(return_value=sentinel)
        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=True
        ), patch(
            "importlib.import_module", return_value=fake_mod
        ) as import_mod:
            result = self.handler.launch(
                module="fakemod", entry="FakeEntry", mode="in_process"
            )
        import_mod.assert_called_once_with("fakemod")
        fake_mod.FakeEntry.assert_called_once_with()
        self.assertIs(result, sentinel)

    def test_in_process_without_entry_raises(self):
        """in_process mode has no `python -m` fallback — entry is required."""
        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=True
        ):
            with self.assertRaises(ValueError):
                self.handler.launch(module="fakemod", mode="in_process")

    def test_in_process_caches_widget_by_name(self):
        """Re-launching the same registered name returns the cached widget,
        so close-and-reopen via a button doesn't spawn duplicate windows."""
        self.handler.register(
            "tool", module="m", entry="E", mode="in_process"
        )

        first_widget = MagicMock()
        first_widget.objectName.return_value = "first"
        fake_mod = MagicMock()
        fake_mod.E = MagicMock(return_value=first_widget)

        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=True
        ), patch("importlib.import_module", return_value=fake_mod):
            a = self.handler.launch("tool")
            b = self.handler.launch("tool")
        self.assertIs(a, b)
        # Entry was only called once — second launch hit the cache.
        fake_mod.E.assert_called_once()

    def test_in_process_recreates_when_widget_dead(self):
        """If the cached widget's C++ side has been deleted, launch() must
        create a fresh one instead of returning the dead wrapper."""
        self.handler.register(
            "tool", module="m", entry="E", mode="in_process"
        )

        dead_widget = MagicMock()
        dead_widget.objectName.side_effect = RuntimeError("deleted")
        new_widget = MagicMock()
        new_widget.objectName.return_value = "new"

        fake_mod = MagicMock()
        fake_mod.E = MagicMock(side_effect=[dead_widget, new_widget])

        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=True
        ), patch("importlib.import_module", return_value=fake_mod):
            self.handler.launch("tool")
            result = self.handler.launch("tool")
        self.assertIs(result, new_widget)
        self.assertEqual(fake_mod.E.call_count, 2)

    def test_in_process_ad_hoc_call_does_not_cache(self):
        """Without a registered name, launch() can't key the cache —
        every call returns a fresh widget."""
        fake_mod = MagicMock()
        fake_mod.E = MagicMock(return_value=MagicMock())
        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=True
        ), patch("importlib.import_module", return_value=fake_mod):
            self.handler.launch(module="m", entry="E", mode="in_process")
            self.handler.launch(module="m", entry="E", mode="in_process")
        self.assertEqual(fake_mod.E.call_count, 2)

    def test_in_process_install_uses_current_interpreter(self):
        """When module is missing in in_process mode, install runs against
        sys.executable (not _default_python which picks a standalone)."""
        pm_instance = MagicMock()
        fake_mod = MagicMock()
        fake_mod.E = MagicMock(return_value="ui")
        with patch.object(
            ExternalToolHandler,
            "_is_importable",
            side_effect=[False, True],
        ), patch(
            "pythontk.PackageManager", return_value=pm_instance
        ) as pm_cls, patch(
            "importlib.import_module", return_value=fake_mod
        ):
            self.handler.launch(
                module="fakemod",
                entry="E",
                install_spec="fakemod",
                mode="in_process",
            )
        # PackageManager constructed against sys.executable, not a sibling
        pm_cls.assert_called_once_with(python_path=sys.executable)


class TestSpawnSnippet(unittest.TestCase):
    """Verify the subprocess invocation shape without running it."""

    def test_spawn_with_entry_uses_dash_c_snippet(self):
        with patch("pythontk.AppLauncher.launch") as launch:
            ExternalToolHandler._spawn(
                python=sys.executable,
                module="foo",
                entry="FooUI",
                show_kwargs={"pos": "screen", "app_exec": True},
            )
        call = launch.call_args
        args = call.kwargs.get("args") or call.args[1]
        self.assertEqual(args[0], "-c")
        snippet = args[1]
        self.assertIn("from foo import FooUI", snippet)
        self.assertIn("FooUI()", snippet)
        self.assertIn("pos='screen'", snippet)
        self.assertIn("app_exec=True", snippet)

    def test_spawn_without_entry_uses_dash_m(self):
        with patch("pythontk.AppLauncher.launch") as launch:
            ExternalToolHandler._spawn(
                python=sys.executable,
                module="foo",
                entry=None,
                show_kwargs=None,
            )
        call = launch.call_args
        args = call.kwargs.get("args") or call.args[1]
        self.assertEqual(args, ["-m", "foo"])


class TestDefaultPython(unittest.TestCase):
    """Regression: inside Maya, sys.executable is maya.exe — running
    `maya.exe -c "<python>"` invokes MEL, not Python. Default interpreter
    selection must skip DCC hosts and find a real Python."""

    def test_prefers_python_on_path(self):
        from uitk.handlers import external_tool_handler as eth

        with patch.object(eth.shutil, "which", return_value="/usr/bin/python"):
            self.assertEqual(eth._default_python(), "/usr/bin/python")

    def test_falls_back_to_mayapy_sibling(self):
        from uitk.handlers import external_tool_handler as eth

        fake_maya = "C:\\Program Files\\Autodesk\\Maya2025\\bin\\maya.exe"
        with patch.object(eth.shutil, "which", return_value=None), patch.object(
            eth.sys, "executable", fake_maya
        ), patch.object(eth.os.path, "isfile", return_value=True):
            result = eth._default_python()
        self.assertTrue(result.lower().endswith("mayapy.exe"))

    def test_last_resort_returns_sys_executable(self):
        from uitk.handlers import external_tool_handler as eth

        fake_exe = "/some/standalone/python"
        with patch.object(eth.shutil, "which", return_value=None), patch.object(
            eth.sys, "executable", fake_exe
        ):
            self.assertEqual(eth._default_python(), fake_exe)


class TestIsImportable(unittest.TestCase):
    def test_same_interpreter_uses_find_spec(self):
        """When python == sys.executable, find_spec path is used."""
        self.assertTrue(
            ExternalToolHandler._is_importable("sys", sys.executable)
        )
        self.assertFalse(
            ExternalToolHandler._is_importable(
                "definitely_not_a_real_module_xyz", sys.executable
            )
        )

    def test_different_interpreter_runs_probe(self):
        """When python differs from sys.executable, a subprocess probe runs."""
        with patch(
            "uitk.handlers.external_tool_handler.subprocess.run"
        ) as run:
            run.return_value = MagicMock(returncode=0)
            result = ExternalToolHandler._is_importable("foo", "/other/python")
        run.assert_called_once()
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
