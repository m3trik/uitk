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
from uitk.bridge.spec import AttributeSpec, make_widget, read_value, set_value  # noqa: E402
from uitk.widgets.mixins.preset_manager import PresetManager  # noqa: E402


PARAMS = {
    "align_downscale": AttributeSpec(
        key="align_downscale", kind="int", default=1, minimum=1, maximum=16
    ),
    "depth_filter": AttributeSpec(
        key="depth_filter", kind="choice", default="mild",
        choices=["none", "mild", "moderate", "aggressive"],
    ),
    "face_count": AttributeSpec(
        key="face_count", kind="choice", default="medium",
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
            json.dumps({"_meta": {"version": 1},
                        "align_downscale": 2, "depth_filter": "moderate"}),
            encoding="utf-8",
        )

        # Build a BridgeSlotsBase WITHOUT running __init__ (which needs a
        # switchboard + loaded .ui). Wire only the pieces the semantic-preset
        # path touches: the param-widget map (normally built by
        # _build_param_widgets from the registry).
        self.slots = object.__new__(BridgeSlotsBase)
        self.slots._param_widgets = {
            key: make_widget(spec) for key, spec in PARAMS.items()
        }

        # The SAME store a headless runner would use (built-in + user tiers).
        self.store = ptk.PresetStore(
            "metashape_presets", "extapps",
            builtin_dir=str(self.builtin), user_dir=str(self.user),
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
        self.assertEqual(read_value(self._w("align_downscale")), 2)
        self.assertEqual(read_value(self._w("depth_filter")), "moderate")
        # A key the preset didn't set keeps its default (overlay semantics).
        self.assertEqual(read_value(self._w("face_count")), "medium")

    def test_save_writes_semantic_preset_headless_can_read(self):
        set_value(self._w("align_downscale"), 8)
        set_value(self._w("face_count"), "high")
        self.mgr.save("myrun")
        # The headless store sees the same file, keyed by semantic name.
        data = self.store.load("myrun")
        self.assertEqual(data["align_downscale"], 8)
        self.assertEqual(data["face_count"], "high")
        self.assertEqual(self.store.source("myrun"), "user")

    def test_round_trip_through_store(self):
        set_value(self._w("align_downscale"), 4)
        set_value(self._w("depth_filter"), "aggressive")
        self.mgr.save("run")
        # Mutate the widgets, then load — the applier restores the snapshot.
        set_value(self._w("align_downscale"), 1)
        set_value(self._w("depth_filter"), "none")
        self.mgr.load("run")
        self.assertEqual(read_value(self._w("align_downscale")), 4)
        self.assertEqual(read_value(self._w("depth_filter")), "aggressive")

    def test_user_preset_shadows_builtin(self):
        set_value(self._w("align_downscale"), 9)
        self.mgr.save("specular")  # same name as the built-in
        self.assertEqual(self.mgr.source("specular"), "user")
        self.assertEqual(self.mgr.list(), ["specular"])  # listed once
        set_value(self._w("align_downscale"), 1)
        self.mgr.load("specular")
        self.assertEqual(read_value(self._w("align_downscale")), 9)  # user won

    def test_unknown_keys_ignored(self):
        # A shared CLI preset may carry knobs this panel doesn't surface.
        applied = self.slots._apply_param_dict(
            {"align_downscale": 3, "not_a_param": 99}
        )
        self.assertEqual(applied, 1)
        self.assertEqual(read_value(self._w("align_downscale")), 3)


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
        with mock.patch.object(bs, "_open_in_file_manager") as opener:
            slots._on_log_link_clicked(url)
        opener.assert_called_once()
        self.assertEqual(
            os.path.normpath(opener.call_args[0][0]), os.path.normpath(tmp)
        )


if __name__ == "__main__":
    unittest.main()
