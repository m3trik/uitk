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
from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402
from uitk.switchboard import Switchboard  # noqa: E402
from uitk.bridge.slots import BridgeSlotsBase  # noqa: E402
from uitk.bridge.spec import (  # noqa: E402
    AttributeSpec,
    KindFactory,
    _KindFactoryInternal,
)
from uitk.bridge.formatters import Formatters  # noqa: E402
from uitk.bridge.parameters import Parameters  # noqa: E402
from uitk.managers.preset_manager import PresetManager  # noqa: E402
from uitk.managers.optional_package_manager import (  # noqa: E402
    OptionalPackageManager,
)


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


class TestBridgeDocsLink(BaseTestCase):
    """``DOCS_URL`` -> one clickable ``"<DOCS_LABEL>: <url>"`` log line at open.

    The header help is a tooltip (no clickable links), so the docs link goes to
    the log pane -- the same closing line the extapps compositor's intro
    carries. Opt-in and data-driven like ``HELP_SPEC``: the default is empty
    and logs nothing; :meth:`docs_url` is the computed-override hook. Routed
    through ``panel_log`` so a panel whose optional engine is missing (no
    bridge, no logger redirect) still shows it.
    """

    def _slots(self, docs_url=None, engine=True):
        import logging
        from types import SimpleNamespace

        class _Logger:
            def __init__(self):
                self.infos = []

            def info(self, m):
                self.infos.append(m)

        class _Bridge:
            logger = _Logger()

        slots = object.__new__(BridgeSlotsBase)
        slots.LOG_TAG = "docs_test"
        if docs_url is not None:
            slots.DOCS_URL = docs_url
        slots._bridge = _Bridge() if engine else None
        slots.make_bridge = lambda: None  # only consulted when engine=False
        slots.ui = SimpleNamespace(txt000=QtWidgets.QTextBrowser())
        slots.sb = SimpleNamespace(logger=logging.getLogger("uitk_test_docs"))
        return slots

    def test_default_is_no_link(self):
        slots = self._slots()
        slots._show_docs_link()
        self.assertEqual(slots._bridge.logger.infos, [])
        self.assertEqual(slots.ui.txt000.toPlainText(), "")

    def test_declared_url_logs_label_and_anchor(self):
        url = "https://github.com/m3trik/extapps/blob/main/docs/x.md"
        slots = self._slots(docs_url=url)
        slots.DOCS_LABEL = "Tuning guide"
        slots._show_docs_link()
        self.assertEqual(len(slots._bridge.logger.infos), 1)
        line = slots._bridge.logger.infos[0]
        self.assertTrue(line.startswith("Tuning guide: "), line)
        self.assertIn(f'<a href="{url}">{url}</a>', line)

    def test_docs_url_hook_overrides_the_attr(self):
        class _Computed(BridgeSlotsBase):
            DOCS_URL = "https://static.invalid/"

            def docs_url(self):
                return "https://computed.invalid/page"

        slots = self._slots()
        slots.__class__ = _Computed
        slots._show_docs_link()
        self.assertIn("computed.invalid/page", slots._bridge.logger.infos[0])
        self.assertNotIn("static.invalid", slots._bridge.logger.infos[0])

    def test_missing_engine_still_shows_the_link(self):
        """No bridge -> ``panel_log`` appends straight to the pane; the docs
        are needed most exactly when the engine isn't installed."""
        url = "https://github.com/m3trik/extapps#readme"
        slots = self._slots(docs_url=url, engine=False)
        slots._show_docs_link()
        app.processEvents()
        self.assertIn(url, slots.ui.txt000.toPlainText())
        self.assertIn(f'href="{url}"', slots.ui.txt000.toHtml())


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

    def test_bridge_temp_dir_survives_a_killed_host(self):
        """A host that dies skips ``atexit``; the leftover must still be reclaimable.

        Regression: the directory used to be a hand-rolled
        ``<temp>/uitk_bridge/<tag>_<pid>`` whose ONLY cleanup was the exit hook.
        DCC hosts are routinely killed, so each of those left a folder behind
        with nothing able to reclaim it. Routed through ``ptk.TempArtifacts``
        it joins a swept prefix namespace instead.  Added: 2026-08-18
        """
        import os
        import shutil
        import time

        import pythontk as ptk

        from uitk.bridge.slots import _BridgeSlotsInternal

        tag = "test_bridge_swept"
        self.addCleanup(_BridgeSlotsInternal._remove_bridge_temp_dir, tag)
        s = self._make(default="", temp_fallback=True, tag=tag)
        path = s.require_output_dir()
        self.addCleanup(shutil.rmtree, path, True)
        self.assertTrue(os.path.isdir(path))

        # Simulate the killed host: the process is gone, so the exit hook never
        # ran and the in-process registry is gone with it.
        _BridgeSlotsInternal._BRIDGE_TEMP_DIRS.pop(tag, None)
        self.assertTrue(os.path.isdir(path), "precondition: the leftover is on disk")

        # Backdate it into a PREVIOUS session, which is the case being modelled.
        # `max_age_days=0` cannot express it: `sweep_stale` skips an entry whose
        # `st_mtime >= cutoff`, and on Windows a directory created in the same
        # clock tick reports st_mtime == time.time() exactly -- so the leftover
        # survived its own sweep about two runs in three. Backdating is
        # deterministic at any clock granularity.
        past = time.time() - 2 * 86400
        os.utime(path, (past, past))

        # A later run allocating the same namespace reclaims it by age.
        swept = ptk.TempArtifacts(
            f"uitk_bridge_{tag}", policy="session", max_age_days=1
        ).sweep_stale()
        self.assertIn(os.path.normcase(path), [os.path.normcase(p) for p in swept])
        self.assertFalse(os.path.isdir(path))

    def test_require_output_dir_false_short_circuits(self):
        s = self._make(require=False, temp_fallback=True, default="")
        self.assertEqual(s.require_output_dir(), "")

    def test_transient_mode_skips_the_scene_default(self):
        """A mode whose Output Dir is scratch must not adopt the scene dir.

        Regression: a Marmoset bake roundtrip consumes its own hand-off
        artifacts, but the blank field resolved to the scene/workspace dir and
        left them beside the scene file. The bridge allocates -- and deletes --
        its own scratch instead, so this tier hands it an empty string.
        Added: 2026-08-18
        """
        s = self._make(default="D:/scene", temp_fallback=True)
        s.TRANSIENT_OUTPUT_MODES = ("round_trip",)
        self.assertEqual(s.require_output_dir("round_trip"), "")
        # Nothing is written back -- a scratch path in the field would read as
        # a user choice on the NEXT run.
        self.assertEqual(s._output_dir_edit.text(), "")
        self.assertFalse(s._bridge.logger.errors)
        # Any other mode is unchanged.
        self.assertEqual(s.require_output_dir("send_to"), "D:/scene")

    def test_transient_mode_still_honors_a_typed_value(self):
        """An explicitly named dir wins even for a transient mode. Added: 2026-08-18"""
        s = self._make(typed="C:/pick", default="D:/scene")
        s.TRANSIENT_OUTPUT_MODES = ("round_trip",)
        self.assertEqual(s.require_output_dir("round_trip"), "C:/pick")


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
            lambda u, log: (order.append("a"), True)[1]
        )
        BridgeSlotsBase.register_log_link_handler(
            lambda u, log: (order.append("b"), True)[1]
        )
        self._dispatch("action://reveal?node=x")
        self.assertEqual(order, ["a"])  # 'b' never tried once 'a' handled it

    def test_handler_returning_false_falls_through(self):
        from uitk.bridge.slots import BridgeSlotsBase

        order = []
        BridgeSlotsBase.register_log_link_handler(
            lambda u, log: (order.append("a"), False)[1]
        )
        BridgeSlotsBase.register_log_link_handler(
            lambda u, log: (order.append("b"), True)[1]
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
            lambda u, log: (order.append("ok"), True)[1]
        )
        self._dispatch("action://select?node=x")  # must not raise
        self.assertEqual(order, ["boom", "ok"])

    def test_open_action_never_reaches_handlers(self):
        from uitk.bridge.slots import BridgeSlotsBase

        reached = []
        BridgeSlotsBase.register_log_link_handler(
            lambda u, log: (reached.append(1), True)[1]
        )
        self._dispatch("action://open?path=")  # empty path → internal no-op
        self.assertEqual(reached, [])

    def test_empty_registry_no_ops(self):
        # No DCC registered (standalone app): a node action is silently ignored.
        self._dispatch("action://select?node=x")  # no handler, no exception


class TestPathWidgetPresetPersistence(BaseTestCase):
    """A ``path``-kind widget's inner QLineEdit must be name-keyed so it
    survives widget-state presets.

    Historically the DCC bridges snapshotted the value-bearing *child*,
    substituting the container's ``_line_edit`` into the managed set, because
    ``PresetManager`` could not read a composite container at all. That is no
    longer how it works (see :class:`TestKindWidgetPresetRoundTrip`), but the
    inner edit keeps its objectName: ``_capture_values`` / ``load`` skip
    empty-objectName widgets, and an unnamed child is a trap either way.
    """

    def test_path_inner_edit_has_objectname(self):
        w = KindFactory.make_widget(AttributeSpec(key="render_output", kind="path"))
        self.assertEqual(w._line_edit.objectName(), "render_output")


class TestKindWidgetPresetRoundTrip(BaseTestCase):
    """Every kind the bridges build must survive a widget-state preset.

    ``PresetManager`` reads and writes a ``KindFactory``-built widget through the
    handler that built it (the ``_attr_kind`` stamp), so the managed set is now
    the real widgets rather than substituted inner children. Before that, the
    isinstance ladder returned ``None`` for a composite container and
    ``_capture_values`` dropped the key: ``check_list`` and ``file_list`` params
    neither saved nor restored, silently.
    """

    CASES = (
        ("render_output", dict(kind="path"), "C:/renders/hero.png"),
        ("scripts", dict(kind="check_list", choices=["a", "b", "c"]), ["a", "c"]),
        ("meshes", dict(kind="file_list"), ["C:/m/a.fbx", "C:/m/b.fbx"]),
        ("scale", dict(kind="float", default=1.0), 2.5),
        ("clear", dict(kind="bool", default=False), True),
        ("shader", dict(kind="choice", choices=["x", "y"], default="x"), "y"),
        (
            "affix",
            dict(kind="affix", default={"text": "", "mode": "auto"}),
            {"text": "_hero", "mode": "suffix"},
        ),
    )

    def _round_trip(self, key, spec_kw, value, empty):
        tmp = Path(tempfile.mkdtemp(prefix="bridge_kind_preset_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)

        widget = KindFactory.make_widget(AttributeSpec(key=key, **spec_kw))
        KindFactory.set_value(widget, value)

        # Exactly what _build_preset_controls now passes: the kind-built widgets.
        mgr = PresetManager.from_widgets(preset_dir=tmp / "user", widgets=[widget])
        mgr.save("p")

        saved = json.loads((tmp / "user" / "p.json").read_text(encoding="utf-8"))
        self.assertEqual(saved.get(key), value, f"{key} never reached disk")

        KindFactory.set_value(widget, empty)
        self.assertEqual(KindFactory.read_value(widget), empty)
        mgr.load("p")
        self.assertEqual(
            KindFactory.read_value(widget), value, f"{key} did not restore"
        )

    def test_every_kind_round_trips(self):
        empties = {
            "path": "",
            "check_list": [],
            "file_list": [],
            "float": 0.0,
            "bool": False,
            "choice": "x",
            "affix": {"text": "", "mode": "auto"},
        }
        for key, spec_kw, value in self.CASES:
            with self.subTest(kind=spec_kw["kind"]):
                self._round_trip(key, spec_kw, value, empties[spec_kw["kind"]])


class TestActionKind(BaseTestCase):
    """The ``action`` kind -- a row of command buttons, not a value.

    ``read`` returns None (nothing to collect or preset), the change-wirer is
    a deliberate no-op (clicks never dirty a preset), and
    ``BridgeSlotsBase._wire_action_params`` connects each action id to the
    same-named slot method -- or disables the button when none exists.
    """

    CHOICES = [
        ("Set From Selection", "do_set", "primary tip"),
        ("Clear", "do_clear"),
    ]

    def _widget(self, **kwargs):
        return KindFactory.make_widget(
            AttributeSpec(key="acts", kind="action", **kwargs)
        )

    def test_buttons_built_and_exposed(self):
        w = self._widget(choices=self.CHOICES)
        self.assertEqual(sorted(w._action_buttons), ["do_clear", "do_set"])
        self.assertEqual(w._action_buttons["do_set"].text(), "Set From Selection")
        self.assertEqual(w._action_buttons["do_set"].toolTip(), "primary tip")

    def test_read_none_write_and_connect_are_noops(self):
        w = self._widget(choices=self.CHOICES)
        self.assertIsNone(KindFactory.read_value(w))
        KindFactory.set_value(w, "anything")  # must not raise
        # The no-op wirer: a click after connect_changed must NOT fire the
        # callback (preset dirty-tracking ignores commands).
        fired = []
        KindFactory.connect_changed(w, lambda *_: fired.append(1))
        w._action_buttons["do_set"].click()
        self.assertEqual(fired, [])

    def test_wire_action_params_connects_and_disables(self):
        slot = BridgeSlotsBase.__new__(BridgeSlotsBase)
        w = self._widget(choices=self.CHOICES)
        slot._param_widgets = {"acts": w}
        calls = []
        slot.do_set = lambda *a: calls.append("set")  # 'do_clear' left absent
        slot._wire_action_params()
        w._action_buttons["do_set"].click()
        self.assertEqual(calls, ["set"])
        self.assertTrue(w._action_buttons["do_set"].isEnabled())
        self.assertFalse(w._action_buttons["do_clear"].isEnabled())
        self.assertIn("do_clear", w._action_buttons["do_clear"].toolTip())

    def test_collect_param_values_excludes_action_rows(self):
        slot = BridgeSlotsBase.__new__(BridgeSlotsBase)
        slot._param_widgets = {
            "acts": self._widget(choices=self.CHOICES),
            "depth": KindFactory.make_widget(
                AttributeSpec(key="depth", kind="int", default=3)
            ),
        }
        self.assertEqual(slot.collect_param_values(), {"depth": 3})


class TestActionKindIconButtons(BaseTestCase):
    """A 4th ``choices`` element turns a secondary action into an icon button.

    It rides the PRIMARY action's option box rather than taking a second
    full-width label, and stays addressable through ``_action_buttons`` so
    neither the wiring nor the disable path has to know which shape it got.
    """

    CHOICES = [
        ("Set From Selection", "do_set", "primary tip"),
        ("Select", "do_select", "select tip", "select"),
        ("Clear", "do_clear", "clear tip", "clear"),
    ]

    def _widget(self):
        return KindFactory.make_widget(
            AttributeSpec(key="acts", kind="action", choices=self.CHOICES)
        )

    def test_icon_entries_render_as_icons_and_text_entries_do_not(self):
        w = self._widget()
        buttons = w._action_buttons
        self.assertEqual(sorted(buttons), ["do_clear", "do_select", "do_set"])
        self.assertEqual(buttons["do_set"].text(), "Set From Selection")
        self.assertTrue(buttons["do_set"].icon().isNull())
        for key in ("do_select", "do_clear"):
            with self.subTest(action=key):
                self.assertEqual(buttons[key].text(), "")
                self.assertFalse(buttons[key].icon().isNull())
                self.assertEqual(buttons[key].toolTip(), f"{key.split(chr(95))[1]} tip")

    def test_icon_actions_wire_and_disable_like_text_ones(self):
        slot = BridgeSlotsBase.__new__(BridgeSlotsBase)
        w = self._widget()
        slot._param_widgets = {"acts": w}
        calls = []
        slot.do_set = lambda *a: calls.append("set")
        slot.do_select = lambda *a: calls.append("select")
        # 'do_clear' left absent -- its icon button must disable, not fail.
        slot._wire_action_params()
        w._action_buttons["do_set"].click()
        w._action_buttons["do_select"].click()
        self.assertEqual(calls, ["set", "select"])
        self.assertTrue(w._action_buttons["do_select"].isEnabled())
        self.assertFalse(w._action_buttons["do_clear"].isEnabled())
        self.assertIn("do_clear", w._action_buttons["do_clear"].toolTip())

    def test_greying_the_row_widget_takes_the_icon_buttons_with_it(self):
        """``set_param_enabled`` greys the ROW, and the icons live inside it.

        An icon that stayed live would act on a row the panel has just
        declared inert -- the same trap the affix picker fell into by being
        wrapped OUTSIDE its row.
        """
        widget = self._widget()
        widget.setEnabled(False)
        for key, button in widget._action_buttons.items():
            with self.subTest(action=key):
                self.assertFalse(button.isEnabled())
    def test_a_leading_icon_entry_still_gets_a_labelled_primary(self):
        """An all-icon row would have no option-box host and no label."""
        w = KindFactory.make_widget(
            AttributeSpec(
                key="acts",
                kind="action",
                choices=[("Only", "do_only", "tip", "select")],
            )
        )
        self.assertEqual(w._action_buttons["do_only"].text(), "Only")

    def test_action_rows_still_carry_no_value(self):
        self.assertIsNone(KindFactory.read_value(self._widget()))


class TestAffixKind(BaseTestCase):
    """The ``affix`` kind -- a text field plus uitk's tri-state mode picker.

    Its value is composite (``{"text", "mode"}``) so a preset restores which
    SIDE the affix lands on, not just its spelling; ``affix_parts`` is how a
    headless consumer turns one into the pair it applies.
    """

    def _widget(self, default=None):
        return KindFactory.make_widget(
            AttributeSpec(key="affix", kind="affix", default=default)
        )

    def test_reads_text_and_mode(self):
        w = self._widget({"text": "hero_", "mode": "prefix"})
        self.assertEqual(
            KindFactory.read_value(w), {"text": "hero_", "mode": "prefix"}
        )

    def test_write_accepts_a_bare_string_as_auto(self):
        """A preset written before this kind existed carries a plain str."""
        w = self._widget()
        KindFactory.set_value(w, "_hero")
        self.assertEqual(
            KindFactory.read_value(w), {"text": "_hero", "mode": "auto"}
        )

    def test_an_unknown_mode_falls_back_to_auto(self):
        w = self._widget()
        KindFactory.set_value(w, {"text": "x", "mode": "sideways"})
        self.assertEqual(KindFactory.read_value(w)["mode"], "auto")

    def test_change_fires_for_both_the_text_and_the_mode(self):
        w = self._widget()
        seen = []
        KindFactory.connect_changed(w, seen.append)
        KindFactory.set_value(w, {"text": "hero_", "mode": "auto"})
        self.assertTrue(seen, "typing did not fire the change wirer")
        before = len(seen)
        option = _KindFactoryInternal._affix_option(w._line_edit)
        option._cycle()
        self.assertGreater(
            len(seen), before, "cycling the mode did not fire the change wirer"
        )
        self.assertEqual(seen[-1]["mode"], option.mode)

    def test_affix_parts_splits_by_the_declared_mode(self):
        cases = [
            ({"text": "hero_", "mode": "prefix"}, ("hero_", "")),
            ({"text": "hero_", "mode": "suffix"}, ("", "hero_")),
            ({"text": "_hero", "mode": "auto"}, ("", "_hero")),
            ({"text": "hero_", "mode": "auto"}, ("hero_", "")),
            ({"text": "", "mode": "prefix"}, ("", "")),
            ("hero_", ("hero_", "")),
            (None, ("", "")),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(KindFactory.affix_parts(value), expected)

    def test_renders_as_its_spelling_not_a_dict_repr(self):
        """A template substituting ``__KEY__`` must not see ``{'text': ...}``."""
        spec = AttributeSpec(key="affix", kind="affix", default="")
        rendered = Parameters.render_context(
            {"affix": {"text": "hero_", "mode": "prefix"}},
            {"affix": spec},
            formatter=Formatters.cli_raw,
        )
        self.assertEqual(rendered["affix"], "hero_")

    def test_the_picker_lands_INSIDE_the_row_not_floating_over_it(self):
        """The option box replaces the field in its PARENT layout.

        Built as a bare QLineEdit, the wrap ran while the field was still
        outside any layout (the row builder adds it afterwards), so the
        container floated over the row and every row-level operation missed
        it -- greying the row left the mode and clear icons live beside a
        disabled value. Composite, like ``path``, the field is laid out
        before the wrap.
        """
        row = QtWidgets.QWidget()
        QtWidgets.QHBoxLayout(row)
        widget = self._widget()
        row.layout().addWidget(widget)

        buttons = widget.findChildren(QtWidgets.QPushButton)
        self.assertTrue(buttons, "the affix picker built no buttons")
        for button in buttons:
            with self.subTest(button=button.objectName()):
                self.assertTrue(
                    widget.isAncestorOf(button),
                    "the option box floated outside the kind widget",
                )

    def test_disabling_the_row_widget_takes_the_picker_with_it(self):
        """What ``set_param_enabled`` walks is the row; the icons ride along."""
        widget = self._widget()
        widget.setEnabled(False)
        for button in widget.findChildren(QtWidgets.QPushButton):
            with self.subTest(button=button.objectName()):
                self.assertFalse(button.isEnabled())

    def test_the_value_bearing_child_is_named_for_preset_capture(self):
        """A widget with an empty objectName is skipped by preset capture."""
        self.assertEqual(self._widget()._line_edit.objectName(), "affix")
    def test_a_scalar_kind_is_unchanged_by_the_literal_hook(self):
        spec = AttributeSpec(key="n", kind="int", default=0)
        self.assertEqual(KindFactory.to_literal(spec, 7), 7)


class _ShowableUi(QtCore.QObject):
    """Stand-in for a panel root carrying uitk ``MainWindow``'s show signal."""

    on_show = QtCore.Signal()


def _bare_slot(params_module=None):
    """An unconstructed slot whose ``params_module`` is a stand-in registry.

    ``BridgeSlotsBase.params_module`` is an abstract property; a subclass
    supplies it, so a test that exercises registry-reading machinery has to as
    well (a class attribute shadows the property, exactly as a real subclass's
    override does).
    """
    cls = type("_StubSlots", (BridgeSlotsBase,), {"params_module": params_module})
    return cls.__new__(cls)


class TestParamEnablement(BaseTestCase):
    """``set_param_enabled`` -- grey a row whose relevance is session state.

    Distinct from visibility (which answers "does this template use the
    knob?"): the row stays on screen so the user can see the value that
    *would* apply, and the reason it currently doesn't.
    """

    def _slot_with_row(self):
        slot = _bare_slot()
        row = QtWidgets.QWidget()
        hbox = QtWidgets.QHBoxLayout(row)
        label = QtWidgets.QLabel("Source Suffix:", row)
        widget = KindFactory.make_widget(
            AttributeSpec(key="sfx", kind="choice", default="a", choices=["a", "b"]),
            row,
        )
        hbox.addWidget(label)
        hbox.addWidget(widget)
        slot._param_rows = {"sfx": row}
        slot._param_widgets = {"sfx": widget}
        return slot, row, label, widget

    def test_disable_greys_children_and_puts_reason_on_the_row(self):
        slot, row, label, widget = self._slot_with_row()
        was_hidden = row.isHidden()
        slot.set_param_enabled("sfx", False, "superseded by the explicit set")

        # Children disabled; the ROW stays enabled so it still receives the
        # hover a disabled child ignores -- Qt delivers no tooltip event to a
        # disabled widget, so the reason has to live on the parent.
        self.assertFalse(label.isEnabled())
        self.assertFalse(widget.isEnabled())
        self.assertTrue(row.isEnabled())
        self.assertEqual(row.toolTip(), "superseded by the explicit set")
        # Greyed, never hidden: enablement must not touch visibility (that
        # belongs to _refresh_param_visibility), so the value stays readable.
        self.assertIs(row.isHidden(), was_hidden)

    def test_re_enable_clears_the_reason(self):
        slot, row, label, widget = self._slot_with_row()
        slot.set_param_enabled("sfx", False, "because")
        slot.set_param_enabled("sfx", True)
        self.assertTrue(label.isEnabled())
        self.assertTrue(widget.isEnabled())
        self.assertEqual(row.toolTip(), "")

    def test_unknown_key_is_ignored(self):
        slot, _row, _label, _widget = self._slot_with_row()
        slot.set_param_enabled("not_registered", False, "x")  # must not raise

    def test_disabled_row_still_reports_its_value(self):
        """A greyed row is inert, not excluded -- ``collect_param_values``
        still reports it, so the send params keep their full shape."""
        slot, _row, _label, _widget = self._slot_with_row()
        slot.set_param_enabled("sfx", False, "because")
        self.assertEqual(slot.collect_param_values(), {"sfx": "a"})

    def test_refresh_hook_does_nothing_without_declared_supersessions(self):
        slot, _row, _label, widget = self._slot_with_row()
        slot.PARAM_SUPERSESSIONS = ()
        self.assertIsNone(slot._refresh_param_enablement())
        self.assertTrue(widget.isEnabled())

    def test_panel_show_re_evaluates_enablement(self):
        """A reopened panel must not keep the PREVIOUS scene's rows locked out.

        The template-change trigger answers "does this template use the
        knob?"; the show answers "is it in effect in THIS scene?" -- session
        state can change entirely while the panel is closed.
        """
        slot, _row, _label, _widget = self._slot_with_row()
        slot.PARAM_SUPERSESSIONS = ()
        slot.ui = _ShowableUi()
        calls = []
        slot._refresh_param_enablement = lambda: calls.append(1)
        slot._wire_enablement_refresh()

        slot.ui.on_show.emit()
        slot.ui.on_show.emit()
        self.assertEqual(calls, [1, 1])

    def test_show_wiring_tolerates_a_ui_without_on_show(self):
        """Not every panel's root is a uitk MainWindow -- that's a no-op."""
        slot, _row, _label, _widget = self._slot_with_row()
        slot.PARAM_SUPERSESSIONS = ()
        slot.ui = QtWidgets.QWidget()
        slot._wire_enablement_refresh()  # must not raise


class TestParamSupersessions(BaseTestCase):
    """A parameter whose value takes other rows out of effect.

    Declared as data next to the parameters themselves, so two panels sharing
    one registry (the Maya and Blender halves of a bridge) grey the same rows
    without either restating the rule.
    """

    REASON = "Auto is on; this is inactive."

    def _slot(self, declared_on_registry=True):
        supersessions = (("AUTO", ("VALUE",), self.REASON),)
        registry = type(
            "_Registry",
            (),
            {"SUPERSESSIONS": supersessions} if declared_on_registry else {},
        )
        slot = _bare_slot(registry)
        if not declared_on_registry:
            slot.PARAM_SUPERSESSIONS = supersessions

        rows, widgets = {}, {}
        for key, spec in (
            ("AUTO", AttributeSpec(key="AUTO", kind="bool", default=False)),
            ("VALUE", AttributeSpec(key="VALUE", kind="float", default=0.02)),
        ):
            row = QtWidgets.QWidget()
            hbox = QtWidgets.QHBoxLayout(row)
            widget = KindFactory.make_widget(spec, row)
            hbox.addWidget(widget)
            rows[key], widgets[key] = row, widget
        slot._param_rows, slot._param_widgets = rows, widgets
        return slot

    def test_registry_declaration_greys_the_governed_row(self):
        slot = self._slot()
        slot._write_param("AUTO", True)
        slot._refresh_param_enablement()
        self.assertFalse(slot._param_widgets["VALUE"].isEnabled())
        self.assertEqual(slot._param_rows["VALUE"].toolTip(), self.REASON)

    def test_turning_the_trigger_off_re_enables_and_clears_the_reason(self):
        slot = self._slot()
        slot._write_param("AUTO", True)
        slot._refresh_param_enablement()
        slot._write_param("AUTO", False)
        slot._refresh_param_enablement()
        self.assertTrue(slot._param_widgets["VALUE"].isEnabled())
        self.assertEqual(slot._param_rows["VALUE"].toolTip(), "")

    def test_class_attr_is_the_fallback_when_the_registry_declares_none(self):
        slot = self._slot(declared_on_registry=False)
        slot._write_param("AUTO", True)
        slot._refresh_param_enablement()
        self.assertFalse(slot._param_widgets["VALUE"].isEnabled())

    def test_editing_the_trigger_refreshes_without_waiting_for_a_show(self):
        """The governed row must go inert on the click, not on the next open."""
        slot = self._slot()
        slot.ui = _ShowableUi()
        slot._wire_enablement_refresh()
        slot._write_param("AUTO", True)  # fires the widget's change signal
        self.assertFalse(slot._param_widgets["VALUE"].isEnabled())


class TestLiveParamTooltips(BaseTestCase):
    """``live_param_tooltips`` -- a row whose tooltip is recomputed on hover.

    ``format_param_tooltip`` runs once at build time, so a row describing
    session state (a scene set the user defines from a selection) would
    describe the state the panel opened on -- exactly the case being checked.
    """

    def _built(self, providers):
        params = {
            "SET": AttributeSpec(key="SET", label="Bake Source", kind="str", default="")
        }
        slot = _bare_slot(type("_Registry", (), {"PARAMS": params}))
        slot._param_widgets, slot._param_rows = {}, {}
        slot._param_labels = {}
        slot._param_section, slot._section_separators = {}, {}
        slot.sb = Switchboard()
        slot.live_param_tooltips = lambda: providers

        slot.ui = QtWidgets.QWidget()
        slot.ui.grp_process = QtWidgets.QGroupBox(slot.ui)
        QtWidgets.QVBoxLayout(slot.ui.grp_process)
        slot.ui.b000 = QtWidgets.QPushButton(slot.ui.grp_process)
        slot.ui.grp_process.layout().addWidget(slot.ui.b000)

        slot._build_param_widgets()
        slot._bind_live_param_tooltips()
        return slot

    @staticmethod
    def _hover(widget):
        """Deliver the ToolTip event Qt sends just before it paints the popup."""
        QtWidgets.QApplication.sendEvent(
            widget,
            QtGui.QHelpEvent(
                QtCore.QEvent.ToolTip, QtCore.QPoint(0, 0), QtCore.QPoint(0, 0)
            ),
        )

    def test_provider_refreshes_the_control_on_every_hover(self):
        state = {"n": 0}

        def provider():
            state["n"] += 1
            return f"stored: {state['n']}"

        slot = self._built({"SET": provider})
        widget = slot._param_widgets["SET"]
        self._hover(widget)
        self.assertEqual(widget.toolTip(), "stored: 1")
        self._hover(widget)
        self.assertEqual(widget.toolTip(), "stored: 2")

    def test_the_row_label_is_a_hover_target_too(self):
        """The caption is the row's identity, so it answers for the row.

        (An ``action`` row's buttons keep their own per-choice tips; they
        pick up live state through ``live_param_tooltip_blocks`` instead.)
        """
        slot = self._built({"SET": lambda: "live"})
        label = slot._param_labels["SET"]
        self._hover(label)
        self.assertEqual(label.toolTip(), "live")

    def test_unknown_keys_are_ignored(self):
        """A shared base may offer a row only some of its panels register."""
        slot = self._built({"NOT_A_PARAM": lambda: "x"})  # must not raise
        self.assertNotIn("NOT_A_PARAM", slot._param_widgets)

    def test_default_hook_is_empty_so_rows_keep_their_static_tooltip(self):
        slot = self._built({})
        widget = slot._param_widgets["SET"]
        before = widget.toolTip()
        self._hover(widget)
        self.assertEqual(widget.toolTip(), before)


class TestLiveParamTooltipBlocks(BaseTestCase):
    """``live_param_tooltip_blocks`` -- live state APPENDED to a row's own tips.

    The whole-tooltip hook is wrong for an ``action`` row: replacing three
    per-choice descriptions ("what does Clear do?") with one row-level string
    is a bad trade, and the buttons are exactly where the user is standing
    when they wonder what the row currently holds.
    """

    CHOICES = [
        # A multi-line tip: the base has line breaks the appended block
        # would collapse if it were not promoted to HTML first.
        ("Set From Selection", "do_set", "capture the selection\nfrom the viewport"),
        ("Clear", "do_clear", "forget it", "clear"),
    ]

    def _built(self, providers, kind="action"):
        params = {
            "SET": AttributeSpec(
                key="SET",
                label="Bake Source",
                kind=kind,
                tooltip="the scene set",
                choices=self.CHOICES if kind == "action" else None,
            )
        }
        slot = _bare_slot(type("_Registry", (), {"PARAMS": params}))
        slot._param_widgets, slot._param_rows = {}, {}
        slot._param_labels = {}
        slot._param_section, slot._section_separators = {}, {}
        slot.sb = Switchboard()
        slot.live_param_tooltip_blocks = lambda: providers

        slot.ui = QtWidgets.QWidget()
        slot.ui.grp_process = QtWidgets.QGroupBox(slot.ui)
        QtWidgets.QVBoxLayout(slot.ui.grp_process)
        slot.ui.b000 = QtWidgets.QPushButton(slot.ui.grp_process)
        slot.ui.grp_process.layout().addWidget(slot.ui.b000)

        slot._build_param_widgets()
        slot._bind_live_param_tooltips()
        return slot

    def test_every_hover_target_gains_the_block(self):
        slot = self._built({"SET": lambda: "<i>2 stored</i>"})
        widget = slot._param_widgets["SET"]
        targets = [
            widget,
            slot._param_labels["SET"],
            *widget._action_buttons.values(),
        ]
        for target in targets:
            with self.subTest(target=type(target).__name__):
                TestLiveParamTooltips._hover(target)
                self.assertIn("2 stored", target.toolTip())

    def test_each_button_keeps_its_own_description(self):
        """The block is appended -- it does not replace what the click does."""
        slot = self._built({"SET": lambda: "<i>live</i>"})
        buttons = slot._param_widgets["SET"]._action_buttons
        TestLiveParamTooltips._hover(buttons["do_set"])
        TestLiveParamTooltips._hover(buttons["do_clear"])
        self.assertIn("capture the selection", buttons["do_set"].toolTip())
        self.assertIn("forget it", buttons["do_clear"].toolTip())
        self.assertNotIn("forget it", buttons["do_set"].toolTip())

    def test_a_plain_text_button_tip_keeps_its_line_breaks(self):
        """Qt renders a tooltip as rich text once it holds a tag, so a plain
        base would silently lose every newline the appended block gave it."""
        slot = self._built({"SET": lambda: "<i>live</i>"})
        button = slot._param_widgets["SET"]._action_buttons["do_set"]
        TestLiveParamTooltips._hover(button)
        self.assertIn(
            "capture the selection<br>from the viewport", button.toolTip()
        )

    def test_rebinding_does_not_stack_the_block(self):
        """The tooltip surface writes its computed text back onto the widget.

        So a second bind that read ``toolTip()`` for its base would fold the
        previous live block in and render two copies -- and grow one more per
        rebind. Measured before the fix: two hovers, two lists.
        """
        slot = self._built({"SET": lambda: "<i>LIVE</i>"})
        button = slot._param_widgets["SET"]._action_buttons["do_set"]
        TestLiveParamTooltips._hover(button)
        self.assertEqual(button.toolTip().count("LIVE"), 1)
        slot._bind_live_param_tooltips()
        TestLiveParamTooltips._hover(button)
        self.assertEqual(button.toolTip().count("LIVE"), 1)
        self.assertIn("capture the selection", button.toolTip())

    def test_a_less_than_sign_is_not_mistaken_for_markup(self):
        """``"<" in text`` would pass a comparison through unescaped, and Qt
        would swallow everything after it as an unclosed tag."""
        slot = self._built({"SET": lambda: "<i>LIVE</i>"})
        self.assertEqual(
            slot._as_tooltip_html("width < height"),
            "<p style='margin:0'>width &lt; height</p>",
        )
        self.assertEqual(
            slot._as_tooltip_html("<b>already rich</b>"), "<b>already rich</b>"
        )
    def test_a_value_row_gets_the_block_under_its_formatted_help(self):
        slot = self._built({"SET": lambda: "<i>live</i>"}, kind="str")
        widget = slot._param_widgets["SET"]
        TestLiveParamTooltips._hover(widget)
        text = widget.toolTip()
        self.assertIn("the scene set", text)
        self.assertLess(text.index("the scene set"), text.index("live"))

    def test_unknown_keys_are_ignored(self):
        slot = self._built({"NOT_A_PARAM": lambda: "x"})  # must not raise
        self.assertNotIn("NOT_A_PARAM", slot._param_widgets)

    def test_default_hook_is_empty(self):
        slot = self._built({})
        button = slot._param_widgets["SET"]._action_buttons["do_set"]
        before = button.toolTip()
        TestLiveParamTooltips._hover(button)
        self.assertEqual(button.toolTip(), before)

class TestInlineParamRows(BaseTestCase):
    """``AttributeSpec.inline`` -- a compact modifier beside the value it governs.

    An "Auto" toggle belongs next to the number it overrides, not on a row of
    its own two lines down. It still has to be a separately addressable row,
    or supersession (which greys the value while Auto is on) would grey the
    toggle with it and trap the user.
    """

    def _built(self, params):
        slot = _bare_slot(type("_Registry", (), {"PARAMS": params}))
        slot._param_widgets, slot._param_rows = {}, {}
        slot._param_labels = {}
        slot._param_section, slot._section_separators = {}, {}

        slot.ui = QtWidgets.QWidget()
        slot.ui.grp_process = QtWidgets.QGroupBox(slot.ui)
        QtWidgets.QVBoxLayout(slot.ui.grp_process)
        slot.ui.b000 = QtWidgets.QPushButton(slot.ui.grp_process)
        slot.ui.grp_process.layout().addWidget(slot.ui.b000)

        slot._build_param_widgets()
        return slot

    @staticmethod
    def _specs(**overrides):
        return {
            "CAGE": AttributeSpec(
                key="CAGE", label="Cage Offset", kind="float", default=0.02
            ),
            "AUTO": AttributeSpec(
                key="AUTO",
                label="Auto",
                kind="bool",
                default=False,
                inline=True,
                **overrides,
            ),
        }

    def test_inline_widget_lands_in_the_previous_row(self):
        slot = self._built(self._specs())
        host = slot._param_rows["CAGE"]
        cell = slot._param_rows["AUTO"]
        self.assertIsNot(cell, host)
        self.assertIs(cell.parent(), host)
        self.assertIs(slot._param_widgets["AUTO"].parent(), cell)

    def test_the_inline_row_greys_independently_of_its_host(self):
        slot = self._built(self._specs())
        slot.set_param_enabled("CAGE", False, "Auto is on")
        self.assertFalse(slot._param_widgets["CAGE"].isEnabled())
        self.assertTrue(slot._param_widgets["AUTO"].isEnabled())

    def test_inline_values_are_collected_like_any_other(self):
        slot = self._built(self._specs())
        self.assertEqual(slot.collect_param_values(), {"CAGE": 0.02, "AUTO": False})

    def test_a_leading_inline_spec_still_gets_its_own_row(self):
        """Nothing to attach to -- it must not be dropped."""
        params = {
            "AUTO": AttributeSpec(key="AUTO", kind="bool", default=False, inline=True),
            "CAGE": AttributeSpec(key="CAGE", kind="float", default=0.02),
        }
        slot = self._built(params)
        self.assertIsNot(slot._param_rows["AUTO"], slot._param_rows["CAGE"])
        self.assertIn("AUTO", slot._param_widgets)

    def test_a_section_opener_is_never_inlined_into_the_row_above(self):
        """A titled divider must not be followed by a row that starts on the
        previous section's line."""
        params = {
            "CAGE": AttributeSpec(key="CAGE", kind="float", default=0.02),
            "AUTO": AttributeSpec(
                key="AUTO", kind="bool", default=False, inline=True, section="Look-dev"
            ),
        }
        slot = self._built(params)
        self.assertIsNot(slot._param_rows["AUTO"], slot._param_rows["CAGE"])
        self.assertIsNot(slot._param_rows["AUTO"].parent(), slot._param_rows["CAGE"])


class TestCheckListKind(BaseTestCase):
    """The ``check_list`` kind -- multi-pick over a fixed entry set.

    The plural counterpart to ``choice``: a checkable row per entry, reading
    back the list of checked VALUES. Entries can arrive at build time or be
    pushed in later via ``set_choices`` (the dynamic-parameter path a panel
    uses for runtime-discovered sets, e.g. unitytk's deployable scripts).
    """

    CHOICES = [("Audio Event", "audio_event"), ("Shot Metadata", "shot_metadata")]

    def _widget(self, **kwargs):
        return KindFactory.make_widget(
            AttributeSpec(key="scripts", kind="check_list", **kwargs)
        )

    def test_default_checks_the_listed_values(self):
        w = self._widget(choices=self.CHOICES, default=["shot_metadata"])
        self.assertEqual(
            [w.item(i).text() for i in range(w.count())],
            ["Audio Event", "Shot Metadata"],
        )
        self.assertEqual(KindFactory.read_value(w), ["shot_metadata"])

    def test_read_write_round_trip(self):
        w = self._widget(choices=self.CHOICES, default=[])
        self.assertEqual(KindFactory.read_value(w), [])
        KindFactory.set_value(w, ["audio_event", "shot_metadata"])
        self.assertEqual(KindFactory.read_value(w), ["audio_event", "shot_metadata"])
        # Writing a value that isn't listed leaves nothing checked (rather
        # than inventing a row for it).
        KindFactory.set_value(w, ["nope"])
        self.assertEqual(KindFactory.read_value(w), [])

    def test_a_scalar_value_is_one_entry_not_its_characters(self):
        """A preset / CLI overlay carrying a bare string must check that entry
        -- iterating the string would check nothing and never say why."""
        w = self._widget(choices=self.CHOICES, default=[])
        KindFactory.set_value(w, "shot_metadata")
        self.assertEqual(KindFactory.read_value(w), ["shot_metadata"])
        KindFactory.set_value(w, None)
        self.assertEqual(KindFactory.read_value(w), [])

    def test_set_choices_fills_a_runtime_populated_row(self):
        # The registry spec declares the kind with NO entries; the panel pushes
        # the discovered set in at init.
        w = self._widget(choices=[], default=[])
        self.assertEqual(w.count(), 0)
        KindFactory.set_choices(w, self.CHOICES)
        self.assertEqual(w.count(), 2)
        KindFactory.set_value(w, ["audio_event"])
        self.assertEqual(KindFactory.read_value(w), ["audio_event"])

    def test_set_choices_preserves_surviving_checks(self):
        """A refill must not silently re-check (or drop) what the user chose --
        entries that come back keep their state, ones that don't are gone."""
        w = self._widget(choices=self.CHOICES, default=["audio_event"])
        KindFactory.set_choices(
            w, [("Audio Event", "audio_event"), ("Shadow Plane", "shadow_plane")]
        )
        self.assertEqual(KindFactory.read_value(w), ["audio_event"])

    def test_bulk_toggles_are_wired_to_a_context_menu(self):
        """Check All / Uncheck All -- the row has no space for buttons, so the
        bulk toggles live on the right-click menu."""
        from qtpy import QtCore

        from uitk.bridge.spec import _KindFactoryInternal as internal

        w = self._widget(choices=self.CHOICES, default=[])
        self.assertEqual(w.contextMenuPolicy(), QtCore.Qt.CustomContextMenu)
        internal._set_all_checked(w, True)
        self.assertEqual(KindFactory.read_value(w), ["audio_event", "shot_metadata"])
        internal._set_all_checked(w, False)
        self.assertEqual(KindFactory.read_value(w), [])

    def test_row_height_follows_the_entry_count(self):
        """Entries arrive at runtime, so a fixed height would either scroll a
        short list or leave dead space under a long one."""
        few = self._widget(choices=self.CHOICES[:1])
        many = self._widget(choices=[(f"Item {i}", i) for i in range(12)])
        self.assertEqual(few.minimumHeight(), few.maximumHeight())
        self.assertLess(few.height(), many.height())
        self.assertLessEqual(many.maximumHeight(), 140)  # capped, then scrolls

    def test_per_entry_tooltip_from_a_triple(self):
        w = self._widget(choices=[("Audio Event", "audio_event", "Plays clips.")])
        self.assertEqual(w.item(0).toolTip(), "Plays clips.")

    def test_bare_entries_read_back_as_their_label(self):
        w = self._widget(choices=["alpha", "beta"], default=["beta"])
        self.assertEqual(KindFactory.read_value(w), ["beta"])

    def test_set_choices_rejects_a_kind_without_entries(self):
        w = KindFactory.make_widget(AttributeSpec(key="name", kind="str"))
        with self.assertRaises(TypeError):
            KindFactory.set_choices(w, ["a", "b"])

    def test_choice_kind_repopulates_and_keeps_its_value(self):
        """Same runtime path for the singular kind (the Unity panels' version
        combo): refilling keeps the current selection when it survives."""
        w = KindFactory.make_widget(
            AttributeSpec(
                key="version", kind="choice", choices=[("Auto", "")], default=""
            )
        )
        KindFactory.set_choices(w, [("Auto", ""), ("6000.0.5f1", "6000.0.5f1")])
        KindFactory.set_value(w, "6000.0.5f1")
        KindFactory.set_choices(
            w,
            [("Auto", ""), ("6000.0.5f1", "6000.0.5f1"), ("2021.3.1f1", "2021.3.1f1")],
        )
        self.assertEqual(KindFactory.read_value(w), "6000.0.5f1")

    def test_tall_kinds_escape_the_one_line_row_clamp(self):
        """A list-shaped row must not be squashed to the 19px input height the
        scalar params use."""
        self.assertIn("check_list", BridgeSlotsBase.TALL_KINDS)


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

    # ------------------------------------------------------------ version floor
    #
    # A pyproject extra (``unity = ["unitytk>=0.0.8"]``) only constrains a FRESH
    # install, so a session already carrying the older release imported fine and
    # then raised AttributeError on the API the caller came for. The floor rides
    # on the requirement string so the probe, the prompt and pip read one value.

    def test_requirement_splits_into_name_and_floor(self):
        split = OptionalPackageManager.split_requirement
        self.assertEqual(split("unitytk>=0.0.8"), ("unitytk", (0, 0, 8)))
        self.assertEqual(split("unitytk >= 0.0.8"), ("unitytk", (0, 0, 8)))
        # A bare name keeps the historical "any version will do" behaviour.
        self.assertEqual(split("unitytk"), ("unitytk", None))
        # Extras / other markers are not part of the distribution name.
        self.assertEqual(split("mayatk[unity]"), ("mayatk", None))

    def test_version_tuple_orders_and_truncates_at_a_suffix(self):
        vt = OptionalPackageManager.version_tuple
        self.assertEqual(vt("0.0.8"), (0, 0, 8))
        self.assertLess(vt("0.0.7"), vt("0.0.8"))
        self.assertLess(vt("0.9.9"), vt("1.0.0"))
        # Truncating a pre-release errs toward "older" — the safe direction.
        self.assertEqual(vt("1.2.0rc1"), (1, 2, 0))
        # No version at all can never clear a floor.
        self.assertEqual(vt(""), ())
        self.assertLess(vt(""), (0, 0, 1))

    def test_probe_rejects_an_installed_but_too_old_package(self):
        """The whole point: importable is not the same as usable."""
        import pythontk as ptk

        real = ptk.__version__
        try:
            ptk.__version__ = "0.0.7"
            self.assertFalse(
                BridgeSlotsBase.optional_package_available("pythontk>=0.0.8")
            )
            ptk.__version__ = "0.0.8"
            self.assertTrue(
                BridgeSlotsBase.optional_package_available("pythontk>=0.0.8")
            )
            # Equal meets the floor; a bare spec ignores version entirely.
            ptk.__version__ = "0.0.9"
            self.assertTrue(
                BridgeSlotsBase.optional_package_available("pythontk>=0.0.8")
            )
            ptk.__version__ = "0.0.1"
            self.assertTrue(BridgeSlotsBase.optional_package_available("pythontk"))
        finally:
            ptk.__version__ = real

    def test_probe_rejects_a_package_declaring_no_version(self):
        """Unknowable is refused, matching "present but broken reads as
        unavailable" — a floor the caller asked for must be provable."""
        import pythontk as ptk

        real = ptk.__version__
        try:
            del ptk.__version__
            self.assertFalse(
                BridgeSlotsBase.optional_package_available("pythontk>=0.0.1")
            )
            # ... but with no floor asked for, it is still available.
            self.assertTrue(BridgeSlotsBase.optional_package_available("pythontk"))
        finally:
            ptk.__version__ = real

    def test_stale_package_offers_an_update_then_requires_a_restart(self):
        """An upgrade cannot take effect in-process: the old package is already
        in ``sys.modules`` and reloading it does not refresh the submodules its
        ``__init__`` re-imports from cache. So the method installs, says so, and
        returns False — the caller must not go on to use the new API."""
        import pythontk as ptk

        real = ptk.__version__
        sb, slots = self._make("Yes")
        try:
            ptk.__version__ = "0.0.7"
            self.assertFalse(slots.ensure_optional_package("pythontk>=0.0.8"))
            # pip got the full constraint, so it can actually resolve the upgrade.
            self.assertEqual(slots.installed, ["pythontk>=0.0.8"])
            # Prompt says "update", not "install" — the user has it already.
            self.assertIn("update", sb.prompts[0][0].lower())
            # ... and the second box is the restart notice, not "could not install".
            self.assertIn("restart", sb.prompts[1][0].lower())
            self.assertNotIn("could not", sb.prompts[1][0].lower())
        finally:
            ptk.__version__ = real

    def test_absent_package_still_says_install_not_update(self):
        sb, slots = self._make("No")
        slots.ensure_optional_package(
            "uitk-not-a-real-pkg>=1.0", feature="Unity Bridge"
        )
        self.assertIn("install", sb.prompts[0][0].lower())
        self.assertNotIn("older", sb.prompts[0][0].lower())

    def test_install_interpreter_is_never_a_dcc_host_binary(self):
        """pip must be driven by a real python, not maya.exe/blender.exe.

        The resolver returns None rather than the host when there is no sibling
        — driving pip through the host binary would hang it, so "no answer" is
        the correct answer.
        """
        exe = OptionalPackageManager.pip_python()
        if exe is not None:
            self.assertNotIn(
                Path(exe).name.lower(), ("maya.exe", "blender.exe", "3dsmax.exe")
            )

    def test_silent_probe_true_for_a_real_package(self):
        """``optional_package_available`` is the implicit-path probe: no
        dialogs, no installs — it is what ``make_bridge`` implementations use
        (they run from ``__init__`` via the log wiring, where a modal would be
        parented to a window that does not exist yet)."""
        self.assertTrue(BridgeSlotsBase.optional_package_available("pythontk"))

    def test_silent_probe_false_for_a_missing_package(self):
        self.assertFalse(
            BridgeSlotsBase.optional_package_available("uitk-not-a-real-pkg")
        )

    def test_silent_probe_rejects_a_namespace_shadow(self):
        """A bare repo/workspace folder on ``sys.path`` imports as an EMPTY
        namespace package (``__file__`` is None) — the live-Maya failure where
        ``_scripts/`` shadowed the real unitytk one level down. The probe must
        read that as unavailable, not available-then-exploding in the bridge
        constructor."""
        import shutil
        import sys as _sys
        import tempfile

        tmp = tempfile.mkdtemp(prefix="uitk_nsp_probe_")
        try:
            # A folder with a nested real package, like a repo checkout:
            # tmp/uitk_fake_nsp_pkg/uitk_fake_nsp_pkg/__init__.py
            (Path(tmp) / "uitk_fake_nsp_pkg" / "uitk_fake_nsp_pkg").mkdir(parents=True)
            _sys.path.insert(0, tmp)
            try:
                self.assertFalse(
                    BridgeSlotsBase.optional_package_available("uitk_fake_nsp_pkg")
                )
            finally:
                _sys.path.remove(tmp)
                _sys.modules.pop("uitk_fake_nsp_pkg", None)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_explicit_ensure_prompts_on_every_call(self):
        """``ensure_optional_package`` is for EXPLICIT user actions only (the
        panels' Manage Unity Scripts install), so each invocation re-asks —
        there is no decline memo, because no implicit path calls this anymore
        and an install action that silently no-ops is a dead click."""
        sb, slots = self._make("No")
        self.assertFalse(slots.ensure_optional_package("uitk-not-a-real-pkg"))
        self.assertFalse(slots.ensure_optional_package("uitk-not-a-real-pkg"))
        self.assertEqual(len(sb.prompts), 2, "explicit action must re-ask")

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

    def test_peek_bridge_absorbs_a_missing_engine(self):
        """``peek_bridge`` is the init-safe accessor: a panel whose optional
        engine is missing must still CONSTRUCT (log wiring and startup info run
        from ``__init__``), so absence comes back as None — never a raise, and
        never a dialog. Letting the raising ``bridge`` property reach the
        constructor took the panel down and stranded the modal it had opened."""

        class _NoEngineSlots(BridgeSlotsBase):
            def __init__(self):
                self._bridge = None

            def make_bridge(self):
                return None

        self.assertIsNone(_NoEngineSlots().peek_bridge())

    def test_panel_log_reports_without_an_engine(self):
        """``panel_log`` must deliver a message while the bridge is missing —
        the Manage Unity Scripts status/install paths report from exactly that
        state. Falls back to the log widget + the Switchboard logger."""

        class _Txt:
            def __init__(self):
                self.lines = []

            def append(self, text):
                self.lines.append(text)

        class _Ui:
            def __init__(self):
                self.txt000 = _Txt()

        class _NoEngineSlots(BridgeSlotsBase):
            def __init__(self, sb):
                self.sb = sb
                self.ui = _Ui()
                self._bridge = None

            def make_bridge(self):
                return None

        slots = _NoEngineSlots(self._Sb("No"))
        slots.panel_log("engine missing", "error")
        self.assertEqual(slots.ui.txt000.lines, ["engine missing"])

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
                OptionalPackageManager.default_install("anything")
        self.assertIn("sibling", str(ctx.exception).lower())


class TestSharedSpecs(BaseTestCase):
    """The specs uitk owns on behalf of every bridge (see Parameters).

    A spec that lives here exists so several bridges cannot drift apart on the
    same knob — which only holds if each caller gets its OWN object.
    """

    def test_shader_type_vocabulary_is_the_shader_engine_s_own(self):
        from uitk.bridge import Parameters

        spec = Parameters.shader_type_spec()
        self.assertEqual(spec.key, "SHADER_TYPE")
        # GameShader's vocabulary verbatim — a second spelling here would have
        # to be translated somewhere, and that somewhere is where it rots.
        self.assertEqual(
            [value for _label, value in spec.choices],
            ["stingray", "standard_surface", "open_pbr"],
        )
        # The game shader leads: these bridges feed a game engine, and it is the
        # only family whose declared slots survive the trip back out.
        self.assertEqual(spec.default, "stingray")

    def test_each_caller_gets_a_distinct_spec(self):
        """AttributeSpec is a mutable dataclass: a shared instance would let one
        bridge's tweak leak into every other bridge's panel."""
        from uitk.bridge import Parameters

        first, second = Parameters.shader_type_spec(), Parameters.shader_type_spec()
        self.assertIsNot(first, second)
        self.assertIsNot(first.choices, second.choices)

    def test_default_is_overridable_per_bridge(self):
        from uitk.bridge import Parameters

        self.assertEqual(
            Parameters.shader_type_spec(default="open_pbr").default, "open_pbr"
        )

    def test_no_section_by_default(self):
        """A titled separator claims every FOLLOWING spec until the next
        section, so a lone sectioned param in an otherwise unsectioned registry
        re-labels its neighbours instead of grouping itself."""
        from uitk.bridge import Parameters

        self.assertEqual(Parameters.shader_type_spec().section, "")
        self.assertEqual(
            Parameters.shader_type_spec(section="Import").section, "Import"
        )



    def test_carrier_vocabulary_is_pythontk_s_own(self):
        """The carrier choice renders pythontk's CARRIER_EXTENSIONS vocabulary --
        the engine refuses any other spelling, so the panel may offer no other."""
        from pythontk.core_utils.app_handoff import CARRIER_EXTENSIONS, CARRIER_PARAM
        from uitk.bridge import Parameters

        spec = Parameters.carrier_spec()
        self.assertEqual(spec.key, CARRIER_PARAM)
        self.assertEqual(spec.kind, "choice")
        self.assertEqual(
            [value for _label, value in spec.choices], list(CARRIER_EXTENSIONS)
        )
        # FBX leads: it is the shipped default on every bridge (USD is opt-in
        # until its live passes close), and combos persist by INDEX.
        self.assertEqual(spec.default, "fbx")
        self.assertEqual(Parameters.carrier_spec(default="usd").default, "usd")

    def test_carrier_spec_is_distinct_per_caller_and_unsectioned(self):
        from uitk.bridge import Parameters

        first, second = Parameters.carrier_spec(), Parameters.carrier_spec()
        self.assertIsNot(first, second)
        self.assertIsNot(first.choices, second.choices)
        self.assertEqual(first.section, "")
        self.assertEqual(Parameters.carrier_spec(section="Export").section, "Export")


if __name__ == "__main__":
    unittest.main()
