# !/usr/bin/python
# coding=utf-8
"""Tests for the SequencerWidget."""
import sys
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parent.parent.absolute()
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from conftest import setup_qt_application, BaseTestCase

app = setup_qt_application()

from uitk.widgets.sequencer._sequencer import (
    SequencerWidget,
    ClipData,
    TrackData,
    ClipItem,
    AttributeColorDialog,
    _TRACK_HEIGHT,
    _RULER_HEIGHT,
    _MIN_CLIP_DURATION,
    _DEFAULT_ATTRIBUTE_COLORS,
    _COMMON_ATTRIBUTES,
)


class TestSequencerWidget(BaseTestCase):
    """Core API tests for the SequencerWidget."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    # -- tracks -------------------------------------------------------------
    def test_add_track(self):
        tid = self.w.add_track("Track A")
        self.assertEqual(tid, 0)
        self.assertEqual(len(self.w.tracks()), 1)
        self.assertEqual(self.w.get_track(tid).name, "Track A")

    def test_add_multiple_tracks(self):
        t0 = self.w.add_track("A")
        t1 = self.w.add_track("B")
        self.assertNotEqual(t0, t1)
        self.assertEqual(len(self.w.tracks()), 2)

    def test_remove_track(self):
        tid = self.w.add_track("X")
        cid = self.w.add_clip(tid, 0, 50, label="clip")
        self.w.remove_track(tid)
        self.assertEqual(len(self.w.tracks()), 0)
        self.assertIsNone(self.w.get_clip(cid))

    # -- clips --------------------------------------------------------------
    def test_add_clip(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, start=100, duration=50, label="Fade")
        cd = self.w.get_clip(cid)
        self.assertIsNotNone(cd)
        self.assertEqual(cd.start, 100)
        self.assertEqual(cd.duration, 50)
        self.assertEqual(cd.end, 150)
        self.assertEqual(cd.label, "Fade")

    def test_add_clip_with_custom_data(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 10, template="fade_in_out", priority=2)
        cd = self.w.get_clip(cid)
        self.assertEqual(cd.data["template"], "fade_in_out")
        self.assertEqual(cd.data["priority"], 2)

    def test_remove_clip(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 10)
        self.w.remove_clip(cid)
        self.assertIsNone(self.w.get_clip(cid))
        self.assertEqual(len(self.w.clips()), 0)

    def test_clips_filtered_by_track(self):
        t0 = self.w.add_track("A")
        t1 = self.w.add_track("B")
        self.w.add_clip(t0, 0, 10)
        self.w.add_clip(t0, 20, 10)
        self.w.add_clip(t1, 0, 30)
        self.assertEqual(len(self.w.clips(track_id=t0)), 2)
        self.assertEqual(len(self.w.clips(track_id=t1)), 1)
        self.assertEqual(len(self.w.clips()), 3)

    # -- clear --------------------------------------------------------------
    def test_clear(self):
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 0, 10)
        self.w.clear()
        self.assertEqual(len(self.w.tracks()), 0)
        self.assertEqual(len(self.w.clips()), 0)

    # -- time mapper --------------------------------------------------------
    def test_time_to_x_round_trip(self):
        tl = self.w._timeline
        for t in (0, 50, 100, 999.5):
            x = tl.time_to_x(t)
            self.assertAlmostEqual(tl.x_to_time(x), t, places=5)

    def test_zoom_changes_pixels_per_unit(self):
        tl = self.w._timeline
        old = tl.pixels_per_unit
        tl.pixels_per_unit = old * 2
        self.assertAlmostEqual(tl.pixels_per_unit, old * 2)

    # -- playhead -----------------------------------------------------------
    def test_set_playhead(self):
        self.w.set_playhead(42.0)
        ph = self.w._timeline._scene.playhead
        self.assertAlmostEqual(ph.time, 42.0)

    # -- snapping -----------------------------------------------------------
    def test_snap_interval_default_off(self):
        self.assertEqual(self.w.snap_interval, 0.0)

    def test_snap_interval_setter(self):
        self.w.snap_interval = 5.0
        self.assertEqual(self.w.snap_interval, 5.0)

    def test_snap_applied_to_clip_move(self):
        """ClipItem._snap rounds values to the nearest snap_interval."""
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, start=0, duration=100)
        item = self.w._clip_items[cid]
        # With snapping off, arbitrary value passes through
        self.assertAlmostEqual(item._snap(12.3), 12.3)
        # With snapping on, value rounds to nearest interval
        self.w.snap_interval = 5.0
        self.assertAlmostEqual(item._snap(12.3), 10.0)
        self.assertAlmostEqual(item._snap(13.0), 15.0)
        self.assertAlmostEqual(item._snap(0.0), 0.0)

    def test_snap_interval_rejects_negative(self):
        self.w.snap_interval = -3.0
        self.assertEqual(self.w.snap_interval, 0.0)

    # -- multi-selection ----------------------------------------------------
    def test_selected_clips_empty_by_default(self):
        self.assertEqual(self.w.selected_clips(), [])

    def test_selected_clips_programmatic(self):
        tid = self.w.add_track("T")
        c0 = self.w.add_clip(tid, 0, 50)
        c1 = self.w.add_clip(tid, 60, 30)
        # Programmatically select both items
        self.w._clip_items[c0].setSelected(True)
        self.w._clip_items[c1].setSelected(True)
        sel = self.w.selected_clips()
        self.assertIn(c0, sel)
        self.assertIn(c1, sel)
        self.assertEqual(len(sel), 2)

    def test_selection_changed_signal(self):
        tid = self.w.add_track("T")
        c0 = self.w.add_clip(tid, 0, 50)
        received = []
        self.w.selection_changed.connect(lambda ids: received.append(ids))
        self.w._clip_items[c0].setSelected(True)
        self.assertTrue(len(received) > 0)
        self.assertIn(c0, received[-1])

    # -- undo / redo -------------------------------------------------------
    def test_undo_restores_clip_position(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, start=10, duration=50)
        # Simulate a drag: capture, mutate, then undo
        self.w._capture_undo()
        self.w._clips[cid].start = 30
        self.assertAlmostEqual(self.w.get_clip(cid).start, 30)
        self.w.undo()
        self.assertAlmostEqual(self.w.get_clip(cid).start, 10)

    def test_redo_reapplies_change(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, start=10, duration=50)
        self.w._capture_undo()
        self.w._clips[cid].start = 30
        self.w.undo()
        self.assertAlmostEqual(self.w.get_clip(cid).start, 10)
        self.w.redo()
        self.assertAlmostEqual(self.w.get_clip(cid).start, 30)

    def test_undo_on_empty_stack_is_noop(self):
        self.w.undo()  # should not raise

    def test_redo_on_empty_stack_is_noop(self):
        self.w.redo()  # should not raise

    def test_new_action_clears_redo_stack(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, start=10, duration=50)
        self.w._capture_undo()
        self.w._clips[cid].start = 20
        self.w.undo()
        # New action should clear redo
        self.w._capture_undo()
        self.w._clips[cid].start = 40
        self.assertEqual(len(self.w._redo_stack), 0)

    # -- frame shortcuts ----------------------------------------------------
    def test_step_forward(self):
        self.w.set_playhead(10.0)
        self.w.step_forward()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 11.0)

    def test_step_backward(self):
        self.w.set_playhead(10.0)
        self.w.step_backward()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 9.0)

    def test_step_backward_clamps_to_zero(self):
        self.w.set_playhead(0.0)
        self.w.step_backward()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 0.0)

    def test_go_to_start(self):
        self.w.set_playhead(50.0)
        self.w.go_to_start()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 0.0)

    def test_go_to_end(self):
        tid = self.w.add_track("T")
        self.w.add_clip(tid, start=0, duration=100)
        self.w.add_clip(tid, start=200, duration=50)
        self.w.go_to_end()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 250.0)

    def test_step_uses_snap_interval(self):
        self.w.snap_interval = 5.0
        self.w.set_playhead(10.0)
        self.w.step_forward()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 15.0)

    # -- _move_playhead helper ---------------------------------------------
    def test_move_playhead_emits_signal(self):
        received = []
        self.w.playhead_moved.connect(lambda t: received.append(t))
        self.w._move_playhead(25.0)
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 25.0)
        self.assertEqual(len(received), 1)
        self.assertAlmostEqual(received[0], 25.0)

    # -- _snapshot helper --------------------------------------------------
    def test_snapshot_returns_positions(self):
        tid = self.w.add_track("T")
        c0 = self.w.add_clip(tid, 10, 50)
        c1 = self.w.add_clip(tid, 80, 20)
        snap = self.w._snapshot()
        self.assertEqual(snap[c0], (10, 50))
        self.assertEqual(snap[c1], (80, 20))

    def test_snapshot_used_by_undo_redo(self):
        """Verify undo/redo round-trip through the _snapshot helper."""
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 40)
        self.w._capture_undo()
        self.w._clips[cid].start = 100
        self.w._capture_undo()
        self.w._clips[cid].start = 200
        self.w.undo()
        self.assertAlmostEqual(self.w.get_clip(cid).start, 100)
        self.w.undo()
        self.assertAlmostEqual(self.w.get_clip(cid).start, 0)
        self.w.redo()
        self.assertAlmostEqual(self.w.get_clip(cid).start, 100)


class TestClipData(BaseTestCase):
    """Unit tests for the ClipData dataclass."""

    def test_end_property(self):
        cd = ClipData(clip_id=0, track_id=0, start=10, duration=20)
        self.assertEqual(cd.end, 30)

    def test_default_data(self):
        cd = ClipData(clip_id=0, track_id=0, start=0, duration=1)
        self.assertIsInstance(cd.data, dict)
        self.assertEqual(len(cd.data), 0)


class TestAttributeColors(BaseTestCase):
    """Tests for the attribute color configuration system."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_default_attribute_colors(self):
        """Widget starts with default attribute color map."""
        colors = self.w.attribute_colors
        self.assertIn("translateX", colors)
        self.assertIn("rotateZ", colors)
        self.assertEqual(colors["translateX"], _DEFAULT_ATTRIBUTE_COLORS["translateX"])

    def test_set_attribute_colors(self):
        """Setting attribute_colors replaces the map."""
        custom = {"translateX": "#FF0000", "custom_attr": "#00FF00"}
        self.w.attribute_colors = custom
        self.assertEqual(self.w.attribute_colors["translateX"], "#FF0000")
        self.assertEqual(self.w.attribute_colors["custom_attr"], "#00FF00")

    def test_clip_resolves_attribute_color(self):
        """Clip with attributes data resolves color from the widget map."""
        self.w.attribute_colors = {"rotateY": "#123456"}
        tid = self.w.add_track("Obj")
        cid = self.w.add_clip(tid, 0, 10, attributes=["rotateY", "translateX"])
        item = self.w._clip_items[cid]
        resolved = item._resolve_color()
        self.assertEqual(resolved.name(), "#123456")

    def test_clip_falls_back_to_default_color(self):
        """Clip without attributes falls back to ClipData.color."""
        tid = self.w.add_track("Obj")
        cid = self.w.add_clip(tid, 0, 10, color="#AABBCC")
        item = self.w._clip_items[cid]
        resolved = item._resolve_color()
        self.assertEqual(resolved.name(), "#aabbcc")

    def test_clip_no_matching_attr_uses_clip_color(self):
        """Clip with attributes that aren't in the color map uses clip color."""
        self.w.attribute_colors = {}
        tid = self.w.add_track("Obj")
        cid = self.w.add_clip(tid, 0, 10, color="#DDEEFF", attributes=["unknown"])
        item = self.w._clip_items[cid]
        resolved = item._resolve_color()
        self.assertEqual(resolved.name(), "#ddeeff")


class TestAttributeColorDialog(BaseTestCase):
    """Tests for the AttributeColorDialog UI."""

    def test_dialog_creates_common_swatches(self):
        dlg = AttributeColorDialog()
        for attr in _COMMON_ATTRIBUTES:
            self.assertIn(attr, dlg._swatches)
        dlg.close()

    def test_dialog_shows_active_extras(self):
        dlg = AttributeColorDialog(active_attrs=["blendWeight", "envelope"])
        self.assertIn("blendWeight", dlg._swatches)
        self.assertIn("envelope", dlg._swatches)
        dlg.close()

    def test_color_map_returns_defaults(self):
        dlg = AttributeColorDialog()
        cmap = dlg.color_map()
        self.assertEqual(cmap["translateX"], _DEFAULT_ATTRIBUTE_COLORS["translateX"])
        dlg.close()

    def test_restore_defaults_resets(self):
        from uitk.widgets.mixins.settings_manager import SettingsManager

        settings = SettingsManager(namespace="test_attr_colors_restore")
        settings.setValue("translateX", "#000000")
        dlg = AttributeColorDialog(settings=settings)
        dlg._restore_defaults()
        # After restore, color reverts to default
        self.assertEqual(
            dlg._current_color("translateX"),
            _DEFAULT_ATTRIBUTE_COLORS["translateX"],
        )
        dlg.close()
        settings.clear()


if __name__ == "__main__":
    unittest.main()
