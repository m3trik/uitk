# !/usr/bin/python
# coding=utf-8
"""BridgeSlotsBase semantic-preset integration (no switchboard / .ui needed).

The DCC bridges (marmoset / substance / rizom) use *widget-state* presets. A
runner panel opts into *semantic* presets by overriding ``make_preset_store()``
to return a :class:`pythontk.PresetStore`. Presets are then ``{param_key:
value}`` run-templates shared with that workflow's headless CLI — built-in +
user tiers — captured via ``collect_param_values`` and applied via
``_apply_param_dict``.

These lock that wiring: a built-in run-template loads into the param widgets, a
Save writes a semantic preset the headless store reads back, the round-trip is
faithful, and unknown keys (knobs the panel doesn't surface) are ignored.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from conftest import BaseTestCase, setup_qt_application

# QApplication needed because the bridge/spec modules import qtpy at load.
app = setup_qt_application()

import pythontk as ptk  # noqa: E402
from uitk.bridge.slots import BridgeSlotsBase  # noqa: E402
from uitk.bridge.spec import AttributeSpec, KindFactory  # noqa: E402
from uitk.managers.preset_manager import PresetManager  # noqa: E402


PARAMS = {
    "align_downscale": AttributeSpec(
        key="align_downscale", kind="int", default=1, minimum=1, maximum=16
    ),
    "depth_filter": AttributeSpec(
        key="depth_filter",
        kind="choice",
        default="mild",
        choices=["none", "mild", "moderate", "aggressive"],
    ),
    "face_count": AttributeSpec(
        key="face_count",
        kind="choice",
        default="medium",
        choices=["low", "medium", "high"],
    ),
}


class TestBridgeSemanticPresets(BaseTestCase):
    """Semantic-preset path of BridgeSlotsBase wired to a real PresetStore."""

    def setUp(self):
        super().setUp()
        self._tmp = Path(tempfile.mkdtemp(prefix="bridge_semantic_"))
        self.builtin = self._tmp / "builtin"
        self.user = self._tmp / "user"
        self.builtin.mkdir()
        # A shipped run-template, semantic keys (what a CLI runner would write).
        (self.builtin / "specular.json").write_text(
            json.dumps(
                {
                    "_meta": {"version": 1},
                    "align_downscale": 2,
                    "depth_filter": "moderate",
                }
            ),
            encoding="utf-8",
        )

        # Build a BridgeSlotsBase WITHOUT running __init__ (which needs a
        # switchboard + loaded .ui). Wire only the pieces the semantic-preset
        # path touches: the param-widget map (normally built by
        # _build_param_widgets from the registry).
        self.slots = object.__new__(BridgeSlotsBase)
        self.slots._param_widgets = {
            key: KindFactory.make_widget(spec) for key, spec in PARAMS.items()
        }

        # The SAME store a headless runner would use (built-in + user tiers).
        self.store = ptk.PresetStore(
            "metashape_presets",
            "extapps",
            builtin_dir=str(self.builtin),
            user_dir=str(self.user),
        )
        # Mirror what _build_preset_controls constructs in semantic mode.
        self.mgr = PresetManager(
            preset_dir=str(self.store.user_dir),
            builtin_dir=str(self.store.builtin_dir),
            value_provider=self.slots.collect_param_values,
            value_applier=self.slots._apply_param_dict,
        )

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def _w(self, key):
        return self.slots._param_widgets[key]

    def test_builtin_preset_loads_into_param_widgets(self):
        n = self.mgr.load("specular")
        self.assertEqual(n, 2)  # the 2 keys the preset carried
        self.assertEqual(KindFactory.read_value(self._w("align_downscale")), 2)
        self.assertEqual(KindFactory.read_value(self._w("depth_filter")), "moderate")
        # A key the preset didn't set keeps its default (overlay semantics).
        self.assertEqual(KindFactory.read_value(self._w("face_count")), "medium")

    def test_save_writes_semantic_preset_headless_can_read(self):
        KindFactory.set_value(self._w("align_downscale"), 8)
        KindFactory.set_value(self._w("face_count"), "high")
        self.mgr.save("myrun")
        # The headless store sees the same file, keyed by semantic name.
        data = self.store.load("myrun")
        self.assertEqual(data["align_downscale"], 8)
        self.assertEqual(data["face_count"], "high")
        self.assertEqual(self.store.source("myrun"), "user")

    def test_round_trip_through_store(self):
        KindFactory.set_value(self._w("align_downscale"), 4)
        KindFactory.set_value(self._w("depth_filter"), "aggressive")
        self.mgr.save("run")
        # Mutate the widgets, then load — the applier restores the snapshot.
        KindFactory.set_value(self._w("align_downscale"), 1)
        KindFactory.set_value(self._w("depth_filter"), "none")
        self.mgr.load("run")
        self.assertEqual(KindFactory.read_value(self._w("align_downscale")), 4)
        self.assertEqual(KindFactory.read_value(self._w("depth_filter")), "aggressive")

    def test_user_preset_shadows_builtin(self):
        KindFactory.set_value(self._w("align_downscale"), 9)
        self.mgr.save("specular")  # same name as the built-in
        self.assertEqual(self.mgr.source("specular"), "user")
        self.assertEqual(self.mgr.list(), ["specular"])  # listed once
        KindFactory.set_value(self._w("align_downscale"), 1)
        self.mgr.load("specular")
        self.assertEqual(
            KindFactory.read_value(self._w("align_downscale")), 9
        )  # user won

    def test_unknown_keys_ignored(self):
        # A shared CLI preset may carry knobs this panel doesn't surface.
        applied = self.slots._apply_param_dict(
            {"align_downscale": 3, "not_a_param": 99}
        )
        self.assertEqual(applied, 1)
        self.assertEqual(KindFactory.read_value(self._w("align_downscale")), 3)


class TestBridgeLogLinkOpen(BaseTestCase):
    """The DCC-agnostic ``open`` log link is handled in the base via the
    cross-platform file-manager opener — no Maya needed — so output-dir links
    work when a panel runs as a standalone external app (the photogrammetry
    bridges' common case). Node actions still defer to the Maya dispatcher.
    """

    def test_open_action_reveals_path_without_mayatk(self):
        import os
        import re
        from unittest import mock
        from qtpy import QtCore
        import uitk.bridge.slots as bs

        slots = object.__new__(BridgeSlotsBase)
        tmp = tempfile.mkdtemp(prefix="bridge_open_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        # Build the anchor exactly as LoggingMixin.log_link() does, parse the
        # href back into a QUrl (what anchorClicked delivers), and dispatch.
        href = ptk.LoggingMixin.log_link(tmp, "open", path=tmp)
        url = QtCore.QUrl(re.search(r'href="([^"]+)"', href).group(1))
        with mock.patch.object(
            bs._BridgeSlotsInternal, "_open_in_file_manager"
        ) as opener:
            slots._on_log_link_clicked(url)
        opener.assert_called_once()
        self.assertEqual(
            os.path.normpath(opener.call_args[0][0]), os.path.normpath(tmp)
        )


class TestRequireOutputDir(BaseTestCase):
    """``require_output_dir`` resolution order, incl. the ``TEMP_OUTPUT_FALLBACK``
    tier that lets an unsaved scene hand off without the user picking a path
    (Substance / Marmoset) while leaving the hard error for bridges that need a
    real location (Unity)."""

    def _make(
        self, require=True, temp_fallback=False, default="", typed="", tag="test_bridge"
    ):
        from qtpy import QtWidgets

        class _Logger:
            def __init__(self):
                self.infos, self.errors = [], []

            def info(self, m):
                self.infos.append(m)

            def error(self, m):
                self.errors.append(m)

        class _Bridge:
            def __init__(self):
                self.logger = _Logger()

        slots = object.__new__(BridgeSlotsBase)
        slots.REQUIRE_OUTPUT_DIR = require
        slots.TEMP_OUTPUT_FALLBACK = temp_fallback
        slots.LOG_TAG = tag
        slots._output_dir_edit = QtWidgets.QLineEdit()
        slots._output_dir_edit.setText(typed)
        slots._bridge = _Bridge()
        slots.default_output_dir = lambda: default
        return slots

    def test_typed_value_wins(self):
        s = self._make(typed="  C:/pick  ")
        self.assertEqual(s.require_output_dir(), "C:/pick")

    def test_scene_default_used_and_written_back(self):
        s = self._make(default="D:/scene")
        self.assertEqual(s.require_output_dir(), "D:/scene")
        self.assertEqual(s._output_dir_edit.text(), "D:/scene")
        self.assertTrue(
            any("scene/workspace default" in m for m in s._bridge.logger.infos)
        )

    def test_no_temp_fallback_errors(self):
        # Unity-style: nothing resolves and temp fallback off -> None + error, unchanged.
        s = self._make(default="", temp_fallback=False)
        self.assertIsNone(s.require_output_dir())
        self.assertTrue(s._bridge.logger.errors)
        self.assertFalse(s._bridge.logger.infos)

    def test_temp_fallback_creates_written_back_and_cleans_up(self):
        import os
        from uitk.bridge.slots import _BridgeSlotsInternal

        tag = "test_bridge_temp"
        self.addCleanup(_BridgeSlotsInternal._remove_bridge_temp_dir, tag)
        s = self._make(default="", temp_fallback=True, tag=tag)
        r = s.require_output_dir()
        self.assertTrue(r and os.path.isdir(r))
        self.assertEqual(s._output_dir_edit.text(), r)
        self.assertFalse(s._bridge.logger.errors)
        self.assertTrue(any("temporary folder" in m for m in s._bridge.logger.infos))
        # Reused across sends for the same tag (same process).
        s2 = self._make(default="", temp_fallback=True, tag=tag)
        self.assertEqual(s2.require_output_dir(), r)
        # atexit-style cleanup removes the directory.
        _BridgeSlotsInternal._remove_bridge_temp_dir(tag)
        self.assertFalse(os.path.isdir(r))
        self.assertNotIn(tag, _BridgeSlotsInternal._BRIDGE_TEMP_DIRS)

    def test_require_output_dir_false_short_circuits(self):
        s = self._make(require=False, temp_fallback=True, default="")
        self.assertEqual(s.require_output_dir(), "")


class LogLinkDispatchTest(unittest.TestCase):
    """The dependency-inverted log-panel link registry.

    uitk handles ``action://open`` itself and delegates node actions
    (``select`` / ``reveal``) to handlers the DCC packages register — so uitk
    never imports mayatk/blendertk. Exercises the real
    ``BridgeSlotsBase._on_log_link_clicked`` against a minimal fake ``self``.
    """

    def setUp(self):
        from uitk.bridge.slots import _BridgeSlotsInternal

        self._registry = _BridgeSlotsInternal._LOG_LINK_HANDLERS
        self._saved = list(self._registry)
        self._registry.clear()

    def tearDown(self):
        self._registry[:] = self._saved

    @staticmethod
    def _fake_slots():
        import logging
        import types

        return types.SimpleNamespace(
            bridge=types.SimpleNamespace(logger=logging.getLogger("test_log_link"))
        )

    @staticmethod
    def _dispatch(url_str):
        from qtpy.QtCore import QUrl

        BridgeSlotsBase._on_log_link_clicked(
            LogLinkDispatchTest._fake_slots(), QUrl(url_str)
        )

    def test_register_is_idempotent(self):
        from uitk.bridge.slots import BridgeSlotsBase

        def handler(url, logger):
            return True

        BridgeSlotsBase.register_log_link_handler(handler)
        BridgeSlotsBase.register_log_link_handler(handler)
        self.assertEqual(self._registry.count(handler), 1)

    def test_public_registrar_is_the_class_method(self):
        # register_log_link_handler is now a staticmethod on BridgeSlotsBase
        # (class-only; no module-level re-export). The class is exported from
        # both uitk.bridge and uitk.bridge.slots.
        from uitk.bridge import BridgeSlotsBase as reexported
        from uitk.bridge.slots import BridgeSlotsBase as canonical

        self.assertIs(reexported, canonical)
        self.assertTrue(callable(canonical.register_log_link_handler))

    def test_registered_handler_receives_non_open_action(self):
        from uitk.bridge.slots import BridgeSlotsBase

        seen = []

        def handler(url, logger):
            seen.append(url.host())
            return True

        BridgeSlotsBase.register_log_link_handler(handler)
        self._dispatch("action://select?node=pCube1")
        self.assertEqual(seen, ["select"])

    def test_first_handler_to_report_handled_short_circuits(self):
        from uitk.bridge.slots import BridgeSlotsBase

        order = []
        BridgeSlotsBase.register_log_link_handler(
            lambda u, l: (order.append("a"), True)[1]
        )
        BridgeSlotsBase.register_log_link_handler(
            lambda u, l: (order.append("b"), True)[1]
        )
        self._dispatch("action://reveal?node=x")
        self.assertEqual(order, ["a"])  # 'b' never tried once 'a' handled it

    def test_handler_returning_false_falls_through(self):
        from uitk.bridge.slots import BridgeSlotsBase

        order = []
        BridgeSlotsBase.register_log_link_handler(
            lambda u, l: (order.append("a"), False)[1]
        )
        BridgeSlotsBase.register_log_link_handler(
            lambda u, l: (order.append("b"), True)[1]
        )
        self._dispatch("action://select?node=x")
        self.assertEqual(order, ["a", "b"])

    def test_raising_handler_does_not_shadow_the_next(self):
        from uitk.bridge.slots import BridgeSlotsBase

        order = []

        def boom(url, logger):
            order.append("boom")
            raise RuntimeError("handler blew up")

        BridgeSlotsBase.register_log_link_handler(boom)
        BridgeSlotsBase.register_log_link_handler(
            lambda u, l: (order.append("ok"), True)[1]
        )
        self._dispatch("action://select?node=x")  # must not raise
        self.assertEqual(order, ["boom", "ok"])

    def test_open_action_never_reaches_handlers(self):
        from uitk.bridge.slots import BridgeSlotsBase

        reached = []
        BridgeSlotsBase.register_log_link_handler(
            lambda u, l: (reached.append(1), True)[1]
        )
        self._dispatch("action://open?path=")  # empty path → internal no-op
        self.assertEqual(reached, [])

    def test_empty_registry_no_ops(self):
        # No DCC registered (standalone app): a node action is silently ignored.
        self._dispatch("action://select?node=x")  # no handler, no exception


class TestPathWidgetPresetPersistence(BaseTestCase):
    """A ``path``-kind widget's inner QLineEdit must be name-keyed so it
    survives widget-state presets.

    The DCC bridges snapshot the value-bearing child, substituting the
    container's ``_line_edit`` into the managed set
    (``[getattr(w, "_line_edit", w) for w in ...]``). ``_capture_values`` /
    ``load`` skip empty-objectName widgets, so before the fix the inner edit
    (objectName "") was silently dropped -- a saved path came back empty.
    """

    def test_path_inner_edit_has_objectname(self):
        # The fix: make_widget's path container names its inner edit.
        w = KindFactory.make_widget(AttributeSpec(key="render_output", kind="path"))
        self.assertEqual(w._line_edit.objectName(), "render_output")

    def test_path_value_round_trips_through_widget_state_preset(self):
        tmp = Path(tempfile.mkdtemp(prefix="bridge_path_preset_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)

        container = KindFactory.make_widget(
            AttributeSpec(key="render_output", kind="path")
        )
        KindFactory.set_value(container, "C:/renders/hero.png")

        # Mirror _build_preset_controls' widget-state managed set: the inner
        # edit stands in for the composite path container.
        managed = [getattr(container, "_line_edit", container)]
        mgr = PresetManager.from_widgets(preset_dir=tmp / "user", widgets=managed)
        mgr.save("hero")

        # The path actually reached disk (before the fix the key was absent).
        saved = json.loads((tmp / "user" / "hero.json").read_text(encoding="utf-8"))
        self.assertEqual(saved.get("render_output"), "C:/renders/hero.png")

        # And it restores after the field is cleared.
        KindFactory.set_value(container, "")
        self.assertEqual(KindFactory.read_value(container), "")
        mgr.load("hero")
        self.assertEqual(KindFactory.read_value(container), "C:/renders/hero.png")


class TestEnsureOptionalPackage(unittest.TestCase):
    """`ensure_optional_package` — prompt-and-install for optional engines.

    A panel whose engine lives in an optional distribution (unitytk behind the
    Unity bridge) must offer to install it rather than dead-end. pip is never
    invoked here: the install hook is overridden, so these pin the decision
    logic, not the network.
    """

    class _Sb:
        """Stand-in for the Switchboard: prompts, and carries a logger.

        The real Switchboard has ``.logger`` — modelled here because
        ``ensure_optional_package`` logs through ``self.sb``, the slots class
        having no logger of its own until its bridge exists.
        """

        def __init__(self, answer):
            import logging

            self.answer = answer
            self.prompts = []
            self.logger = logging.getLogger("test_bridge_slots_sb")

        def message_box(self, text, *buttons, **kwargs):
            self.prompts.append((text, buttons))
            return self.answer

    class _Slots(BridgeSlotsBase):
        def __init__(self, sb):
            import logging

            self.sb = sb
            self.installed = []
            self.logger = logging.getLogger("test_ensure_optional_package")

        def _install_optional_package(self, spec):
            self.installed.append(spec)

    def _make(self, answer):
        sb = self._Sb(answer)
        return sb, self._Slots(sb)

    def test_present_package_neither_prompts_nor_installs(self):
        sb, slots = self._make("Yes")
        self.assertTrue(slots.ensure_optional_package("pythontk"))
        self.assertEqual(sb.prompts, [])
        self.assertEqual(slots.installed, [])

    def test_declined_install_returns_false_and_installs_nothing(self):
        sb, slots = self._make("No")
        self.assertFalse(
            slots.ensure_optional_package("uitk-not-a-real-pkg", feature="Unity Bridge")
        )
        self.assertEqual(slots.installed, [])
        self.assertEqual(len(sb.prompts), 1)

    def test_prompt_names_the_feature_and_uses_standard_buttons(self):
        sb, slots = self._make("No")
        slots.ensure_optional_package("uitk-not-a-real-pkg", feature="Unity Bridge")
        text, buttons = sb.prompts[0]
        self.assertIn("Unity Bridge", text)
        self.assertIn("uitk-not-a-real-pkg", text)
        # MessageBox only accepts Qt standard button names.
        self.assertEqual(buttons, ("Yes", "No"))

    def test_accepted_install_runs_then_reports_when_still_missing(self):
        sb, slots = self._make("Yes")
        self.assertFalse(
            slots.ensure_optional_package("uitk-not-a-real-pkg", feature="Unity Bridge")
        )
        self.assertEqual(slots.installed, ["uitk-not-a-real-pkg"])
        # A second box tells the user it failed rather than failing silently.
        self.assertEqual(len(sb.prompts), 2)

    def test_import_name_may_differ_from_the_pip_spec(self):
        sb, slots = self._make("No")
        # Probes the module, not the spec: a present module short-circuits.
        self.assertTrue(
            slots.ensure_optional_package("Pillow-not-real", import_name="pythontk")
        )
        self.assertEqual(sb.prompts, [])

    def test_install_interpreter_is_never_a_dcc_host_binary(self):
        """pip must be driven by a real python, not maya.exe/blender.exe.

        The resolver returns None rather than the host when there is no sibling
        — driving pip through the host binary would hang it, so "no answer" is
        the correct answer.
        """
        exe = BridgeSlotsBase._optional_package_python()
        if exe is not None:
            self.assertNotIn(
                Path(exe).name.lower(), ("maya.exe", "blender.exe", "3dsmax.exe")
            )

    def test_declined_package_is_asked_about_only_once(self):
        """``bridge`` re-invokes ``make_bridge`` on every access while the
        engine is missing, and ~12 call sites reach for it — without a memo one
        declined install would fire a fresh modal dialog on each of them.
        """
        sb, slots = self._make("No")
        for _ in range(5):
            self.assertFalse(
                slots.ensure_optional_package("uitk-not-a-real-pkg", feature="Panel")
            )
        self.assertEqual(len(sb.prompts), 1, "must not re-prompt after a decline")

    def test_failed_install_is_not_retried_on_every_access(self):
        """Same for an install that ran but left the package unimportable —
        otherwise each access repeats the whole prompt-install-fail cycle."""
        sb, slots = self._make("Yes")
        for _ in range(4):
            self.assertFalse(slots.ensure_optional_package("uitk-not-a-real-pkg"))
        self.assertEqual(slots.installed, ["uitk-not-a-real-pkg"], "installed once")
        # One "install?" + one "could not install" box, then silence.
        self.assertEqual(len(sb.prompts), 2)

    def test_memo_does_not_suppress_a_package_that_becomes_available(self):
        """The importability probe short-circuits before the memo is consulted,
        so installing by hand mid-session takes effect without reopening."""
        sb, slots = self._make("No")
        self.assertFalse(slots.ensure_optional_package("uitk-not-a-real-pkg"))
        # A different, present package must still resolve normally.
        self.assertTrue(slots.ensure_optional_package("pythontk"))

    def test_logs_through_the_switchboard_not_a_slots_logger(self):
        """The base has no ``self.logger`` — a slots class gets one from its
        BRIDGE, which by definition does not exist yet here. Logging must go
        through ``self.sb`` or this raises AttributeError on the decline path.
        """
        class _NoLoggerSlots(BridgeSlotsBase):
            def __init__(self, sb):
                self.sb = sb  # deliberately NO self.logger

            def _install_optional_package(self, spec):
                pass

        slots = _NoLoggerSlots(self._Sb("No"))
        self.assertFalse(hasattr(slots, "logger"))
        # Must not raise.
        self.assertFalse(slots.ensure_optional_package("uitk-not-a-real-pkg"))

    def test_declined_engine_raises_an_actionable_error_not_nonetype(self):
        """A declined optional install makes ``make_bridge`` return None.

        Every consumer reaches for ``self.bridge.logger``, so the property must
        convert that into one clear error rather than letting NoneType leak.
        """

        class _NoEngineSlots(BridgeSlotsBase):
            def __init__(self):
                self._bridge = None

            def make_bridge(self):
                return None

        with self.assertRaises(RuntimeError) as ctx:
            _NoEngineSlots().bridge
        self.assertIn("unavailable", str(ctx.exception).lower())
        self.assertNotIn("nonetype", str(ctx.exception).lower())

    def test_install_refuses_rather_than_pipping_a_dcc_host(self):
        """A host with no sibling python must raise, never invoke pip.

        Regression guard: an earlier cut fell back to ``sys.executable``, which
        inside Maya IS ``maya.exe`` — the exact call the DCC-host guard exists
        to prevent, and it would hang the session.
        """
        import sys as _sys
        import tempfile
        from unittest.mock import patch

        tmp = tempfile.mkdtemp()
        lone_host = str(Path(tmp) / "maya.exe")
        Path(lone_host).write_text("")

        _, slots = self._make("Yes")
        # Call the BASE implementation unbound, so the harness override that
        # stands in for pip elsewhere in this class is bypassed.
        with patch.object(_sys, "executable", lone_host):
            with self.assertRaises(RuntimeError) as ctx:
                BridgeSlotsBase._install_optional_package(slots, "anything")
        self.assertIn("sibling", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
