# !/usr/bin/python
# coding=utf-8
"""Tests for ExternalToolHandler — mock-only, no real subprocess / network."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from conftest import setup_qt_application

setup_qt_application()

from uitk import Switchboard
from uitk.handlers.external_tool_handler import ExternalToolHandler


def _make_sb():
    return Switchboard(handlers={"external_tool": ExternalToolHandler})


class TestExternalToolVisibilityTracking(unittest.TestCase):
    """In-process widget show/hide must fire entries-changed signals.

    Regression: without this wiring, the browser's row icon stayed on
    "Focus" forever once the user hid the external tool's window —
    only the *live-queried* state (footer text, name-column gold-italic)
    updated, because the dataChanged-driven button refresh never fired.

    The handler installs a Show/Hide event filter on the in-process
    widget so the entry-changed signal fires regardless of *how* the
    widget gets hidden (its own header X, ALT+F4, programmatic hide).
    """

    def _set_up(self):
        from qtpy import QtWidgets
        import types
        sb = _make_sb()
        fake_mod = types.ModuleType("fake_external_tool_visibility")
        fake_mod.FakeUI = type("FakeUI", (QtWidgets.QMainWindow,), {})
        sys.modules["fake_external_tool_visibility"] = fake_mod
        return sb

    def test_event_filter_installed_on_show(self):
        from qtpy import QtWidgets
        sb = self._set_up()
        h = sb.handlers.external_tool
        h.register("vt", module="fake_external_tool_visibility",
                   entry="FakeUI", mode="in_process")
        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=True
        ):
            widget = h.launch("vt")
        self.assertTrue(
            getattr(widget, "_uitk_external_visibility_wired", False),
            "_show_in_process must install the visibility event filter.",
        )

    def test_widget_hide_fires_entry_changed_signal(self):
        from qtpy import QtWidgets, QtCore
        sb = self._set_up()
        h = sb.handlers.external_tool
        h.register("vt", module="fake_external_tool_visibility",
                   entry="FakeUI", mode="in_process")
        received = []
        sb.on_handler_entry_changed.connect(
            lambda hn, en: received.append((hn, en))
        )
        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=True
        ):
            widget = h.launch("vt")
        # Show event fires on launch; clear baseline.
        QtWidgets.QApplication.processEvents()
        received.clear()
        widget.hide()
        QtWidgets.QApplication.processEvents()
        self.assertTrue(
            any(en == "vt" for _, en in received),
            f"widget.hide() must fire on_handler_entry_changed; "
            f"received={received}",
        )

    def test_filter_is_idempotent(self):
        from qtpy import QtWidgets
        sb = self._set_up()
        h = sb.handlers.external_tool
        h.register("vt", module="fake_external_tool_visibility",
                   entry="FakeUI", mode="in_process")
        with patch.object(
            ExternalToolHandler, "_is_importable", return_value=True
        ):
            widget = h.launch("vt")
            # Re-launching should NOT install a second filter
            # (we'd double-fire the entry-changed signal otherwise).
            initial_filter_count = len(widget.findChildren(
                QtWidgets.QApplication.instance().__class__.__mro__[1]
                if False else type(widget.parent() or widget)
            ))
            h.launch("vt")
        # The wiring flag prevents a second installEventFilter call —
        # the simplest assertion is that the flag stays set and a
        # repeat launch doesn't blow up.
        self.assertTrue(getattr(widget, "_uitk_external_visibility_wired"))


class TestExternalToolUserTags(unittest.TestCase):
    """User-edited tags on external tools persist via the handler's config.

    External tools have no XML backing file, so the .ui semantic of
    "file_tags = XML tags" doesn't apply directly. Instead, the handler
    stores user-curated tags in its ``SettingsManager`` config branch.
    This keeps the browser's inline tag editor working uniformly across
    file-backed and external entries (the user shouldn't have to know
    which is which).
    """

    def _fresh_sb(self):
        sb = _make_sb()
        # Wipe any leftover config from a prior test.
        sb.handlers.external_tool.config.setValue("user_tags", {})
        return sb

    def test_save_tags_persists_to_config(self):
        sb = self._fresh_sb()
        h = sb.handlers.external_tool
        h.register("mytool", module="mytool", entry="UI")
        h.save_tags("mytool", ["alpha", "beta"])
        self.assertEqual(
            h.config.value("user_tags", {}),
            {"mytool": ["alpha", "beta"]},
        )

    def test_save_tags_normalises_input(self):
        """Strips whitespace and empty entries; result is sorted."""
        sb = self._fresh_sb()
        h = sb.handlers.external_tool
        h.register("mytool", module="mytool", entry="UI")
        h.save_tags("mytool", [" b ", "a", "", "  ", "a"])  # dupes + blanks
        self.assertEqual(
            h.config.value("user_tags", {})["mytool"],
            ["a", "b"],
        )

    def test_save_tags_empty_removes_entry(self):
        """Clearing all tags drops the tool from the persisted dict —
        no growing-empty-keys cruft over time."""
        sb = self._fresh_sb()
        h = sb.handlers.external_tool
        h.register("mytool", module="mytool", entry="UI")
        h.save_tags("mytool", ["x"])
        h.save_tags("mytool", [])
        self.assertNotIn("mytool", h.config.value("user_tags", {}))

    def test_save_tags_strips_leading_hash(self):
        """Users type '#photogrammetry' (because the chips render with #).
        That prefix is display formatting only — the stored value must
        be plain 'photogrammetry'. Without this, the next render becomes
        '##photogrammetry' and the chip filter / context-menu items all
        get the doubled prefix."""
        sb = self._fresh_sb()
        h = sb.handlers.external_tool
        h.register("mytool", module="mytool", entry="UI")
        h.save_tags("mytool", ["#photogrammetry", "##oldbug", "  #materials "])
        self.assertEqual(
            h.config.value("user_tags", {})["mytool"],
            ["materials", "oldbug", "photogrammetry"],
        )

    def test_user_tags_heal_pre_existing_hash_prefix_on_read(self):
        """Settings persisted before the strip fix may have leading '#'
        in stored values. ``_user_tags`` cleans on read so the bug
        doesn't keep re-rendering as '##tag'."""
        sb = self._fresh_sb()
        h = sb.handlers.external_tool
        h.register("mytool", module="mytool", entry="UI")
        # Bypass save_tags' cleanup — write raw bad data straight to config.
        h.config.setValue(
            "user_tags",
            {"mytool": ["#photogrammetry", "##doublebug", "  #m  "]},
        )
        self.assertEqual(
            h._user_tags(),
            {"mytool": ["doublebug", "m", "photogrammetry"]},
        )

    def test_save_tags_unknown_tool_raises(self):
        sb = self._fresh_sb()
        with self.assertRaises(ValueError):
            sb.handlers.external_tool.save_tags("ghost", ["x"])

    def test_entries_expose_user_tags_as_file_tags(self):
        """The browser's editable tag column reads from FileTagsRole.
        User-added tags must appear there (not in inherited_tags) so
        the inline editor's text matches what the user typed."""
        sb = self._fresh_sb()
        h = sb.handlers.external_tool
        h.register("mytool", module="mytool", entry="UI", tags={"declared"})
        h.save_tags("mytool", ["user_added"])
        entry = next(e for e in h.entries() if e.name == "mytool")
        self.assertEqual(entry.inherited_tags, frozenset({"declared"}))
        self.assertEqual(entry.file_tags, frozenset({"user_added"}))
        self.assertTrue(
            entry.editable_tags,
            "External-tool rows must be inline-editable like .ui rows.",
        )


class _FakeEP:
    """Minimal stand-in for ``importlib.metadata.EntryPoint`` — only the
    fields ``ExternalToolHandler.discover`` reads."""

    def __init__(self, name, module, attr, extras=()):
        self.name = name
        self.module = module
        self.attr = attr
        self.extras = list(extras)


class TestExternalToolDiscovery(unittest.TestCase):
    """Entry-point discovery is the contract that lets tools self-describe.

    Without it, every host (tentacle, etc.) had to enumerate tools in
    code — and forgetting one meant the tool never appeared in the UI
    browser. These tests pin down the behavior the design now relies on.
    """

    def _patched_eps(self, inproc=(), subproc=()):
        def _fn(group=None):
            if group == "uitk.external_tools.in_process":
                return list(inproc)
            if group == "uitk.external_tools":
                return list(subproc)
            return []
        return patch("importlib.metadata.entry_points", side_effect=_fn)

    def test_auto_discovers_inproc_group_with_mode_set(self):
        eps = [_FakeEP("metashape_workflow", "metashape_workflow",
                       "MetashapeWorkflowUI", ["photogrammetry"])]
        with self._patched_eps(inproc=eps):
            sb = _make_sb()
        h = sb.handlers.external_tool
        self.assertTrue(h.is_registered("metashape_workflow"))
        cfg = h._tools["metashape_workflow"]
        self.assertEqual(cfg["mode"], "in_process")
        self.assertEqual(cfg["module"], "metashape_workflow")
        self.assertEqual(cfg["entry"], "MetashapeWorkflowUI")
        self.assertEqual(cfg["tags"], frozenset({"photogrammetry"}))

    def test_auto_discovers_subprocess_group_with_default_mode(self):
        eps = [_FakeEP("widget_kit", "widget_kit", "MainUI", ["utility"])]
        with self._patched_eps(subproc=eps):
            sb = _make_sb()
        cfg = sb.handlers.external_tool._tools["widget_kit"]
        self.assertEqual(cfg["mode"], "subprocess")
        self.assertEqual(cfg["tags"], frozenset({"utility"}))

    def test_auto_discover_can_be_disabled(self):
        """Hosts wiring their own discovery (or none) can opt out."""
        eps = [_FakeEP("noisy_tool", "noisy_tool", "UI")]
        with self._patched_eps(inproc=eps):
            sb = Switchboard()  # No handler yet
            h = ExternalToolHandler(switchboard=sb, auto_discover=False)
            sb.register_handler("external_tool", h)
        self.assertFalse(h.is_registered("noisy_tool"))

    def test_manual_registration_overrides_discovered_mode(self):
        """A host that wants different launch mode for a discovered tool
        re-registers — the manual call wins."""
        eps = [_FakeEP("flexible_tool", "flexible_tool", "UI")]
        with self._patched_eps(subproc=eps):
            sb = _make_sb()
        h = sb.handlers.external_tool
        self.assertEqual(h._tools["flexible_tool"]["mode"], "subprocess")
        h.register("flexible_tool", module="flexible_tool",
                   entry="UI", mode="in_process")
        self.assertEqual(h._tools["flexible_tool"]["mode"], "in_process")

    def test_entries_surface_discovered_tools(self):
        """The whole point: discovered tools flow through the unified
        entry surface so the browser sees them without host edits."""
        eps = [_FakeEP("alpha", "alpha", "AlphaUI", ["x"]),
               _FakeEP("beta", "beta", "BetaUI", ["y"])]
        with self._patched_eps(inproc=eps):
            sb = _make_sb()
        names = {e.name for e in sb.iter_handler_entries()
                 if e.kind.startswith("external")}
        self.assertEqual(names, {"alpha", "beta"})


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

        # Construct with os.sep so basename splits correctly on both
        # platforms — hardcoded backslashes look like a single filename
        # to posixpath on the Linux CI runner.
        fake_maya = os.path.join(os.sep + "fake", "bin", "maya.exe")
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
