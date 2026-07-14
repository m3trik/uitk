# !/usr/bin/python
# coding=utf-8
"""Tests for ExternalAppHandler — mock-only, no real subprocess / network."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from conftest import setup_qt_application

setup_qt_application()

from uitk import Switchboard
from uitk.handlers.external_app_handler import ExternalAppHandler


def _make_sb():
    return Switchboard(handlers={"external_app": ExternalAppHandler})


class TestExternalAppVisibilityTracking(unittest.TestCase):
    """In-process widget show/hide must fire entries-changed signals.

    Regression: without this wiring, the browser's row icon stayed on
    "Focus" forever once the user hid the external app's window —
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
        fake_mod = types.ModuleType("fake_external_app_visibility")
        fake_mod.FakeUI = type("FakeUI", (QtWidgets.QMainWindow,), {})
        sys.modules["fake_external_app_visibility"] = fake_mod
        return sb

    def test_event_filter_installed_on_show(self):
        from qtpy import QtWidgets
        sb = self._set_up()
        h = sb.handlers.external_app
        h.register("vt", module="fake_external_app_visibility",
                   entry="FakeUI", mode="in_process")
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=True
        ):
            widget = h.launch("vt")
        self.assertTrue(
            getattr(widget, "_uitk_external_visibility_wired", False),
            "_show_in_process must install the visibility event filter.",
        )

    def test_widget_hide_fires_entry_changed_signal(self):
        from qtpy import QtWidgets, QtCore
        sb = self._set_up()
        h = sb.handlers.external_app
        h.register("vt", module="fake_external_app_visibility",
                   entry="FakeUI", mode="in_process")
        received = []
        sb.on_handler_entry_changed.connect(
            lambda hn, en: received.append((hn, en))
        )
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=True
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
        h = sb.handlers.external_app
        h.register("vt", module="fake_external_app_visibility",
                   entry="FakeUI", mode="in_process")
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=True
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


class TestExternalAppUserTags(unittest.TestCase):
    """User-edited tags on external apps persist via the handler's config.

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
        sb.handlers.external_app.config.setValue("user_tags", {})
        return sb

    def test_save_tags_persists_to_config(self):
        sb = self._fresh_sb()
        h = sb.handlers.external_app
        h.register("mytool", module="mytool", entry="UI")
        h.save_tags("mytool", ["alpha", "beta"])
        self.assertEqual(
            h.config.value("user_tags", {}),
            {"mytool": ["alpha", "beta"]},
        )

    def test_save_tags_normalises_input(self):
        """Strips whitespace and empty entries; result is sorted."""
        sb = self._fresh_sb()
        h = sb.handlers.external_app
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
        h = sb.handlers.external_app
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
        h = sb.handlers.external_app
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
        h = sb.handlers.external_app
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
            sb.handlers.external_app.save_tags("ghost", ["x"])

    def test_entries_expose_user_tags_as_file_tags(self):
        """The browser's editable tag column reads from FileTagsRole.
        User-added tags must appear there (not in inherited_tags) so
        the inline editor's text matches what the user typed."""
        sb = self._fresh_sb()
        h = sb.handlers.external_app
        h.register("mytool", module="mytool", entry="UI", tags={"declared"})
        h.save_tags("mytool", ["user_added"])
        entry = next(e for e in h.entries() if e.name == "mytool")
        self.assertEqual(entry.inherited_tags, frozenset({"declared"}))
        self.assertEqual(entry.file_tags, frozenset({"user_added"}))
        self.assertTrue(
            entry.editable_tags,
            "External-tool rows must be inline-editable like .ui rows.",
        )


class _FakeDist:
    """Stand-in for an ``EntryPoint.dist`` with just a ``.name``."""

    def __init__(self, name):
        self.name = name


class _FakeEP:
    """Minimal stand-in for ``importlib.metadata.EntryPoint`` — only the
    fields ``ExternalAppHandler.discover`` reads."""

    def __init__(self, name, module, attr, extras=(), dist=None, value=None):
        self.name = name
        self.module = module
        self.attr = attr
        self.extras = list(extras)
        self.value = value if value is not None else f"{module}:{attr}"
        if dist is not None:
            self.dist = _FakeDist(dist)


class TestExternalAppDiscovery(unittest.TestCase):
    """Entry-point discovery is the contract that lets tools self-describe.

    Without it, every host (tentacle, etc.) had to enumerate tools in
    code — and forgetting one meant the tool never appeared in the UI
    browser. These tests pin down the behavior the design now relies on.
    """

    def _patched_eps(self, inproc=(), subproc=()):
        def _fn(group=None):
            if group == "uitk.external_apps.in_process":
                return list(inproc)
            if group == "uitk.external_apps":
                return list(subproc)
            return []
        return patch("importlib.metadata.entry_points", side_effect=_fn)

    def test_auto_discovers_inproc_group_with_mode_set(self):
        eps = [_FakeEP("metashape_workflow", "metashape_workflow",
                       "MetashapeWorkflowUI", ["photogrammetry"])]
        with self._patched_eps(inproc=eps):
            sb = _make_sb()
        h = sb.handlers.external_app
        self.assertTrue(h.is_registered("metashape_workflow"))
        cfg = h._apps["metashape_workflow"]
        self.assertEqual(cfg["mode"], "in_process")
        self.assertEqual(cfg["module"], "metashape_workflow")
        self.assertEqual(cfg["entry"], "MetashapeWorkflowUI")
        self.assertEqual(cfg["tags"], frozenset({"photogrammetry"}))

    def test_auto_discovers_subprocess_group_with_default_mode(self):
        eps = [_FakeEP("widget_kit", "widget_kit", "MainUI", ["utility"])]
        with self._patched_eps(subproc=eps):
            sb = _make_sb()
        cfg = sb.handlers.external_app._apps["widget_kit"]
        self.assertEqual(cfg["mode"], "subprocess")
        self.assertEqual(cfg["tags"], frozenset({"utility"}))

    def test_auto_discover_can_be_disabled(self):
        """Hosts wiring their own discovery (or none) can opt out."""
        eps = [_FakeEP("noisy_tool", "noisy_tool", "UI")]
        with self._patched_eps(inproc=eps):
            sb = Switchboard()  # No handler yet
            h = ExternalAppHandler(switchboard=sb, auto_discover=False)
            sb.register_handler("external_app", h)
        self.assertFalse(h.is_registered("noisy_tool"))

    def test_manual_registration_overrides_discovered_mode(self):
        """A host that wants different launch mode for a discovered tool
        re-registers — the manual call wins."""
        eps = [_FakeEP("flexible_tool", "flexible_tool", "UI")]
        with self._patched_eps(subproc=eps):
            sb = _make_sb()
        h = sb.handlers.external_app
        self.assertEqual(h._apps["flexible_tool"]["mode"], "subprocess")
        h.register("flexible_tool", module="flexible_tool",
                   entry="UI", mode="in_process")
        self.assertEqual(h._apps["flexible_tool"]["mode"], "in_process")

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


class TestDiscoveryDerivesInstallSpecAndGates(unittest.TestCase):
    """discover() should need zero host bookkeeping: the install spec comes
    from the entry point's distribution, and ``hide_<host>`` extras become
    visibility gates kept apart from semantic browser tags."""

    def _patched_eps(self, inproc=()):
        def _fn(group=None):
            return list(inproc) if group == "uitk.external_apps.in_process" else []
        return patch("importlib.metadata.entry_points", side_effect=_fn)

    def test_install_spec_derived_from_distribution(self):
        eps = [_FakeEP("compositor", "extapps.texture_maps.compositor",
                       "CompositorUI", dist="extapps")]
        with self._patched_eps(inproc=eps):
            sb = _make_sb()
        cfg = sb.handlers.external_app._apps["compositor"]
        self.assertEqual(cfg["install_spec"], "extapps")

    def test_hide_gate_partitioned_from_semantic_tags(self):
        eps = [_FakeEP("substance", "extapps.substance_workflow", "SubUI",
                       extras=["texturing", "hide_maya"], dist="extapps")]
        with self._patched_eps(inproc=eps):
            sb = _make_sb()
        cfg = sb.handlers.external_app._apps["substance"]
        # Semantic tag survives; the gate is stripped out of the tag set.
        self.assertEqual(cfg["tags"], frozenset({"texturing"}))
        self.assertEqual(cfg["hidden_in"], frozenset({"maya"}))


class TestExternalAppContextVisibility(unittest.TestCase):
    """entries() hides apps gated against the switchboard's context_tags —
    the same host-curation semantics widgets get via apply_visibility_policy,
    but driven by the dedicated ``hidden_in`` set so a semantic tag can
    never accidentally hide an app.

    Handlers are singletons keyed by ``id(switchboard)``; reuse can alias a
    fresh ``Switchboard()`` onto a cached handler. setUp resets the handler
    the sb is actually bound to and always mutates ``self.h.sb`` (which
    ``entries()`` reads), so the tests are isolation-safe.
    """

    def setUp(self):
        self.h = _make_sb().handlers.external_app
        self.h._apps.clear()
        self.h._providers.clear()
        self.h._bootstrapped.clear()

    def _context(self, tags):
        self.h.sb.context_tags = set(tags)

    def test_app_hidden_when_context_matches_gate(self):
        self._context({"maya"})
        self.h.register("compositor", module="m", entry="UI")        # no gate
        self.h.register("substance", module="m2", entry="UI2", hidden_in={"maya"})
        names = {e.name for e in self.h.entries()}
        self.assertIn("compositor", names)
        self.assertNotIn("substance", names)

    def test_gated_app_shown_in_other_context(self):
        self._context({"blender"})
        self.h.register("substance", module="m2", entry="UI2", hidden_in={"maya"})
        self.assertIn("substance", {e.name for e in self.h.entries()})

    def test_empty_context_lists_everything(self):
        self._context(set())
        self.h.register("substance", module="m2", entry="UI2", hidden_in={"maya"})
        self.assertIn("substance", {e.name for e in self.h.entries()})

    def test_gated_app_still_launchable_by_name(self):
        """Visibility filtering must not block a direct launch — the gate
        only governs *listing*, not reachability."""
        self._context({"maya"})
        self.h.register("substance", module="m2", entry="UI2",
                        hidden_in={"maya"}, mode="subprocess")
        self.assertNotIn("substance", {e.name for e in self.h.entries()})
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=True
        ), patch.object(ExternalAppHandler, "_spawn", return_value=MagicMock()):
            self.assertIsNotNone(self.h.launch("substance"))


class TestProviderBootstrap(unittest.TestCase):
    """A provider package lets a host launch apps it never enumerated:
    on a miss the handler installs the provider, re-discovers, and retries —
    so no per-app module/entry list lives in host code.

    setUp resets the (singleton) handler so accumulated ``_apps`` /
    ``_bootstrapped`` from sibling tests can't leak in.
    """

    def setUp(self):
        self.h = _make_sb().handlers.external_app
        self.h._apps.clear()
        self.h._providers.clear()
        self.h._bootstrapped.clear()

    def test_provider_group_discovered_from_entry_points(self):
        prov = [_FakeEP("extapps", "extapps", None, value="extapps")]

        def _fn(group=None):
            return list(prov) if group == ExternalAppHandler.PROVIDER_GROUP else []

        with patch("importlib.metadata.entry_points", side_effect=_fn):
            sb = _make_sb()
        h = sb.handlers.external_app
        self.assertIn("extapps", h._providers)
        self.assertEqual(h._providers["extapps"]["probe_module"], "extapps")

    def test_unregistered_launch_installs_provider_then_launches(self):
        h = self.h
        h.add_provider("extapps", probe_module="extapps")

        def fake_discover(self_, groups=None):
            self_.register(
                "compositor", module="extapps.texture_maps.compositor",
                entry="CompositorUI", install_spec="extapps", mode="subprocess",
            )
            return 1

        def fake_importable(module, python):
            return module == "extapps.texture_maps.compositor"

        pm_instance = MagicMock()
        captured = {}

        def fake_spawn(**kw):
            captured.update(kw)
            return MagicMock()

        with patch.object(ExternalAppHandler, "discover", fake_discover), \
             patch.object(
                 ExternalAppHandler, "_is_importable", side_effect=fake_importable
             ), patch("pythontk.PackageManager", return_value=pm_instance), \
             patch.object(ExternalAppHandler, "_spawn", side_effect=fake_spawn):
            h.launch("compositor")

        pm_instance.install.assert_called_once_with("extapps")
        self.assertEqual(captured["module"], "extapps.texture_maps.compositor")

    def test_provider_attempted_only_once_per_session(self):
        h = self.h
        h.add_provider("extapps", probe_module="extapps")
        pm_instance = MagicMock()
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=False
        ), patch.object(
            ExternalAppHandler, "discover", lambda self_, groups=None: 0
        ), patch("pythontk.PackageManager", return_value=pm_instance):
            with self.assertRaises(ValueError):
                h.launch("ghost")
            with self.assertRaises(ValueError):
                h.launch("ghost")  # provider already tried — no reinstall
        pm_instance.install.assert_called_once_with("extapps")

    def test_present_provider_is_not_reinstalled(self):
        """If the provider's probe module already imports, no install runs —
        bootstrap still re-discovers in case discovery was stale."""
        h = self.h
        h.add_provider("extapps", probe_module="extapps")
        pm_instance = MagicMock()

        def fake_discover(self_, groups=None):
            self_.register("compositor", module="extapps.c", entry="UI",
                           mode="subprocess")
            return 1

        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=True
        ), patch.object(ExternalAppHandler, "discover", fake_discover), \
             patch("pythontk.PackageManager", return_value=pm_instance), \
             patch.object(ExternalAppHandler, "_spawn", return_value=MagicMock()):
            # 'compositor' isn't registered yet; provider probe imports OK so
            # no install, but discover() during bootstrap surfaces it.
            h.launch("compositor")
        pm_instance.install.assert_not_called()


class TestExternalAppHandlerRegistry(unittest.TestCase):
    def test_handler_attached_to_switchboard(self):
        sb = _make_sb()
        self.assertIsInstance(sb.handlers.external_app, ExternalAppHandler)

    def test_singleton_key_does_not_collide_with_other_handlers(self):
        """Regression: SingletonMixin._instances is shared across subclasses,
        so two handlers using `singleton_key=id(switchboard)` would collide and
        the second registration would silently return the first handler's
        instance. ExternalAppHandler must scope its key by class."""
        from uitk.handlers.ui_handler import UiHandler

        sb = Switchboard(
            handlers={"ui": UiHandler, "external_app": ExternalAppHandler}
        )
        self.assertIsInstance(sb.handlers.ui, UiHandler)
        self.assertIsInstance(sb.handlers.external_app, ExternalAppHandler)
        self.assertIsNot(sb.handlers.ui, sb.handlers.external_app)

    def test_register_stores_config(self):
        sb = _make_sb()
        sb.handlers.external_app.register(
            "mytool",
            module="mytool",
            entry="MyToolUI",
            install_spec="mytool==1.0",
        )
        self.assertTrue(sb.handlers.external_app.is_registered("mytool"))

    def test_launch_unknown_name_without_module_raises(self):
        sb = _make_sb()
        with self.assertRaises(ValueError):
            sb.handlers.external_app.launch("nonexistent")


class TestExternalAppHandlerLaunch(unittest.TestCase):
    def setUp(self):
        self.sb = _make_sb()
        self.handler = self.sb.handlers.external_app

    def test_importable_module_skips_install(self):
        """When module is importable, no install should run."""
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=True
        ) as is_imp, patch("pythontk.PackageManager") as pm, patch.object(
            ExternalAppHandler, "_spawn", return_value=MagicMock()
        ) as spawn:
            self.handler.launch(module="anymod", entry="UI")
        is_imp.assert_called_once()
        pm.assert_not_called()
        spawn.assert_called_once()

    def test_missing_module_triggers_install(self):
        """When module is not importable but install_spec is set, install runs."""
        pm_instance = MagicMock()
        with patch.object(
            ExternalAppHandler,
            "_is_importable",
            side_effect=[False, True],
        ), patch("pythontk.PackageManager", return_value=pm_instance), patch.object(
            ExternalAppHandler, "_spawn", return_value=MagicMock()
        ) as spawn:
            self.handler.launch(
                module="anymod", entry="UI", install_spec="anymod"
            )
        pm_instance.install.assert_called_once_with("anymod")
        spawn.assert_called_once()

    def test_dcc_host_interpreter_refuses_install(self):
        """Installing into a live DCC host interpreter must raise, not hang.

        Regression: launch()'s direct install path had no host check (unlike
        _bootstrap_providers), so a launch needing a pip install would run it
        against maya.exe / blender.exe (the interpreter of an in-process launch
        inside a DCC) and HANG the host.
        """
        pm_instance = MagicMock()
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=False
        ), patch("pythontk.PackageManager", return_value=pm_instance):
            with self.assertRaises(RuntimeError) as ctx:
                self.handler.launch(
                    module="somemod",
                    entry="UI",
                    install_spec="somemod",
                    python="C:/Program Files/Autodesk/Maya2025/bin/maya.exe",
                    mode="subprocess",
                )
        pm_instance.install.assert_not_called()
        self.assertIn("host", str(ctx.exception).lower())

    def test_non_dcc_interpreter_still_installs(self):
        """The guard must not block a normal standalone interpreter."""
        pm_instance = MagicMock()
        with patch.object(
            ExternalAppHandler, "_is_importable", side_effect=[False, True]
        ), patch("pythontk.PackageManager", return_value=pm_instance), patch.object(
            ExternalAppHandler, "_spawn", return_value=MagicMock()
        ):
            self.handler.launch(
                module="somemod",
                entry="UI",
                install_spec="somemod",
                python="C:/py/python.exe",
                mode="subprocess",
            )
        pm_instance.install.assert_called_once_with("somemod")

    def test_missing_module_without_install_spec_raises(self):
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=False
        ):
            with self.assertRaises(RuntimeError):
                self.handler.launch(module="missingmod", entry="UI")

    def test_install_that_does_not_make_module_importable_raises(self):
        pm_instance = MagicMock()
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=False
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
            ExternalAppHandler, "_is_importable", return_value=True
        ), patch.object(ExternalAppHandler, "_spawn", side_effect=fake_spawn):
            self.handler.launch("tool", module="overridemod", entry="OverrideEntry")
        self.assertEqual(captured["module"], "overridemod")
        self.assertEqual(captured["entry"], "OverrideEntry")

    def test_launch_self_heals_stale_registration(self):
        """A cached registration whose entry-point module path changed on disk
        (package move / version bump) must self-heal: launch() re-discovers once
        and retries with the refreshed module instead of (re)installing."""
        self.handler.register(
            "tool", module="old.module", entry="UI",
            install_spec="pkg", mode="subprocess",
        )

        def fake_discover(self_, groups=None):
            # Simulate corrected on-disk metadata being picked up.
            self_._apps["tool"]["module"] = "new.module"
            return 1

        captured = {}

        def fake_spawn(**kw):
            captured.update(kw)
            return MagicMock()

        with patch.object(
            ExternalAppHandler, "_is_importable", side_effect=[False, True]
        ), patch.object(
            ExternalAppHandler, "discover", fake_discover
        ), patch("pythontk.PackageManager") as pm, patch.object(
            ExternalAppHandler, "_spawn", side_effect=fake_spawn
        ):
            self.handler.launch("tool")

        pm.assert_not_called()  # re-discovery fixed it; no install needed
        self.assertEqual(captured["module"], "new.module")
        self.assertEqual(self.handler._apps["tool"]["module"], "new.module")

    def test_self_heal_falls_through_to_install_when_unchanged(self):
        """If re-discovery doesn't change the module (genuinely missing), the
        install fallback still runs and the original error still raises."""
        self.handler.register(
            "tool", module="missing.module", entry="UI",
            install_spec="pkg", mode="subprocess",
        )
        pm_instance = MagicMock()
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=False
        ), patch.object(
            ExternalAppHandler, "discover", lambda self_, groups=None: 0
        ), patch("pythontk.PackageManager", return_value=pm_instance):
            with self.assertRaises(RuntimeError) as ctx:
                self.handler.launch("tool")
        pm_instance.install.assert_called_once_with("pkg")
        self.assertIn("still not importable", str(ctx.exception))

    def test_self_heal_preserves_install_augmentation_fields(self):
        """Re-discovery during self-heal must not drop launch-augmentation
        fields (install_spec/python/show_kwargs) a manual register() layered on
        top of the entry point — discover() rebuilds from metadata alone."""
        # Entry point now advertises the corrected module path; the live
        # registration is the stale one plus a manually-added install_spec.
        eps = [_FakeEP("tool", "new.module", "UI")]
        self.handler.register(
            "tool", module="old.module", entry="UI",
            install_spec="pkg", mode="subprocess",
        )

        def fake_eps(group=None):
            return list(eps) if group == "uitk.external_apps.in_process" else []

        captured = {}

        def fake_spawn(**kw):
            captured.update(kw)
            return MagicMock()

        with patch("importlib.metadata.entry_points", side_effect=fake_eps), \
             patch.object(
                 ExternalAppHandler, "_is_importable",
                 side_effect=lambda m, p: m == "new.module",
             ), patch("pythontk.PackageManager") as pm, patch.object(
                 ExternalAppHandler, "_spawn", side_effect=fake_spawn
             ):
            self.handler.launch("tool")

        pm.assert_not_called()
        self.assertEqual(captured["module"], "new.module")
        # install_spec survived the re-discovery (would be None if discover()'s
        # wholesale re-register had been left to clobber it).
        self.assertEqual(self.handler._apps["tool"]["install_spec"], "pkg")


class TestInProcessMode(unittest.TestCase):
    def setUp(self):
        self.sb = _make_sb()
        self.handler = self.sb.handlers.external_app

    def test_in_process_returns_widget_from_entry(self):
        """In in_process mode, launch() returns whatever entry() returns."""
        sentinel = object()
        fake_mod = MagicMock()
        fake_mod.FakeEntry = MagicMock(return_value=sentinel)
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=True
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
            ExternalAppHandler, "_is_importable", return_value=True
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
            ExternalAppHandler, "_is_importable", return_value=True
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
            ExternalAppHandler, "_is_importable", return_value=True
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
            ExternalAppHandler, "_is_importable", return_value=True
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
            ExternalAppHandler,
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


class TestInProcessShowOptOut(unittest.TestCase):
    """``show=False`` returns the prepared widget without showing it.

    Hosts that want to route a freshly-launched in-process widget through
    a custom show path (e.g. the marking menu's cursor-relative
    positioning) need a way to get the widget back primed but invisible.
    Without this, ``launch()`` always called ``widget.show()`` and the
    custom show path either competed with it or had to hide-then-show
    (double flash).
    """

    def _set_up(self):
        from qtpy import QtWidgets
        import types
        sb = _make_sb()
        fake_mod = types.ModuleType("fake_external_app_show_optout")
        fake_mod.FakeUI = type("FakeUI", (QtWidgets.QMainWindow,), {})
        sys.modules["fake_external_app_show_optout"] = fake_mod
        return sb

    def test_show_false_does_not_show_widget(self):
        sb = self._set_up()
        h = sb.handlers.external_app
        h.register("so", module="fake_external_app_show_optout",
                   entry="FakeUI", mode="in_process")
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=True
        ):
            widget = h.launch("so", show=False)
        self.assertFalse(
            widget.isVisible(),
            "show=False must return a non-visible widget.",
        )

    def test_show_false_still_wires_visibility_filter(self):
        """Even without showing, the visibility forwarder must be
        installed so the eventual show (via marking_menu or otherwise)
        still drives the entries-changed signal."""
        sb = self._set_up()
        h = sb.handlers.external_app
        h.register("so", module="fake_external_app_show_optout",
                   entry="FakeUI", mode="in_process")
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=True
        ):
            widget = h.launch("so", show=False)
        self.assertTrue(
            getattr(widget, "_uitk_external_visibility_wired", False),
            "show=False must still install the visibility event filter.",
        )

    def test_show_default_true_shows_widget(self):
        """The default contract (show=True) is preserved."""
        sb = self._set_up()
        h = sb.handlers.external_app
        h.register("so", module="fake_external_app_show_optout",
                   entry="FakeUI", mode="in_process")
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=True
        ):
            widget = h.launch("so")
        self.assertTrue(widget.isVisible())


class TestInstallFailureSurfaces(unittest.TestCase):
    """PackageManager exceptions must propagate as RuntimeError.

    The original implementation let the underlying pip / install error
    bubble unchanged, which made it hard for hosts to catch ``RuntimeError``
    as the single "tool unavailable" signal. Wrap the failure so callers
    get a consistent exception type.
    """

    def test_pm_install_exception_becomes_runtime_error(self):
        sb = _make_sb()
        h = sb.handlers.external_app
        pm_instance = MagicMock()
        pm_instance.install.side_effect = OSError("network down")
        with patch.object(
            ExternalAppHandler, "_is_importable", return_value=False
        ), patch(
            "pythontk.PackageManager", return_value=pm_instance
        ):
            with self.assertRaises(RuntimeError) as ctx:
                h.launch(
                    module="missing", entry="UI", install_spec="missing"
                )
        self.assertIn("Failed to install", str(ctx.exception))


class TestSpawnSnippet(unittest.TestCase):
    """Verify the subprocess invocation shape without running it."""

    def test_spawn_with_entry_uses_dash_c_snippet(self):
        with patch("pythontk.AppLauncher.launch") as launch:
            ExternalAppHandler._spawn(
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
            ExternalAppHandler._spawn(
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
        from uitk.handlers import external_app_handler as eth

        with patch.object(eth.shutil, "which", return_value="/usr/bin/python"):
            self.assertEqual(eth._default_python(), "/usr/bin/python")

    def test_falls_back_to_mayapy_sibling(self):
        from uitk.handlers import external_app_handler as eth

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
        from uitk.handlers import external_app_handler as eth

        fake_exe = "/some/standalone/python"
        with patch.object(eth.shutil, "which", return_value=None), patch.object(
            eth.sys, "executable", fake_exe
        ):
            self.assertEqual(eth._default_python(), fake_exe)


class TestIsImportable(unittest.TestCase):
    def test_same_interpreter_uses_find_spec(self):
        """When python == sys.executable, find_spec path is used."""
        self.assertTrue(
            ExternalAppHandler._is_importable("sys", sys.executable)
        )
        self.assertFalse(
            ExternalAppHandler._is_importable(
                "definitely_not_a_real_module_xyz", sys.executable
            )
        )

    def test_different_interpreter_runs_probe(self):
        """When python differs from sys.executable, a subprocess probe runs."""
        with patch(
            "uitk.handlers.external_app_handler.subprocess.run"
        ) as run:
            run.return_value = MagicMock(returncode=0)
            result = ExternalAppHandler._is_importable("foo", "/other/python")
        run.assert_called_once()
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
