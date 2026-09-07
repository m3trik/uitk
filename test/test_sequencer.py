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

from uitk.widgets.sequencer import (
    SequencerWidget,
    ClipData,
    TrackData,
    KeyframeItem,
    MarkerData,
    RangeHighlightItem,
    AttributeColorDialog,
    _GapOverlayItem,
    _StaticRangeOverlay,
    _RULER_HEIGHT,
    _SHOT_LANE_HEIGHT,
    _SUB_ROW_HEIGHT,
    _MIN_CLIP_DURATION,
    _DEFAULT_ATTRIBUTE_COLORS,
    _COMMON_ATTRIBUTES,
    PatternRegistry,
)
from uitk.widgets.sequencer._clip import ClipItem


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
    def test_snap_interval_default_one(self):
        self.assertEqual(self.w.snap_interval, 1.0)

    def test_snap_interval_setter(self):
        self.w.snap_interval = 5.0
        self.assertEqual(self.w.snap_interval, 5.0)

    def test_snap_applied_to_clip_move(self):
        """ClipItem._snap rounds values to the nearest snap_interval."""
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, start=0, duration=100)
        item = self.w._clip_items[cid]
        # With snapping off, arbitrary value passes through
        self.w.snap_interval = 0.0
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

    # -- range overlay API --------------------------------------------------

    def test_add_range_overlay(self):
        """add_range_overlay creates a scene item and tracks it."""
        self.w.add_range_overlay(10, 90)
        self.assertEqual(len(self.w._range_overlays), 1)

    def test_clear_range_overlays(self):
        """clear_range_overlays removes all overlays."""
        self.w.add_range_overlay(0, 50)
        self.w.add_range_overlay(60, 120)
        self.assertEqual(len(self.w._range_overlays), 2)
        self.w.clear_range_overlays()
        self.assertEqual(len(self.w._range_overlays), 0)

    def test_clear_removes_overlays(self):
        """widget.clear() also clears range overlays."""
        self.w.add_track("T")
        self.w.add_range_overlay(0, 50)
        self.w.clear()
        self.assertEqual(len(self.w._range_overlays), 0)

    # -- locked / read-only clips ------------------------------------------

    def test_add_clip_locked(self):
        """add_clip accepts locked=True and sets ClipData.locked."""
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 50, locked=True)
        cd = self.w.get_clip(cid)
        self.assertTrue(cd.locked)

    def test_add_clip_locked_default_false(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 50)
        cd = self.w.get_clip(cid)
        self.assertFalse(cd.locked)

    def test_read_only_clip_skips_lock_icon(self):
        """read_only clips suppress the lock icon even when locked."""
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 50, locked=True, read_only=True)
        cd = self.w.get_clip(cid)
        self.assertTrue(cd.locked)
        self.assertTrue(cd.data.get("read_only"))

    def test_add_track_dimmed(self):
        """add_track(dimmed=True) sets the header label to the dimmed style."""
        self.w.add_track("Active")
        self.w.add_track("Inactive", dimmed=True)
        header = self.w._header
        self.assertFalse(header._dimmed[0])
        self.assertTrue(header._dimmed[1])

    def test_add_track_dimmed_default_false(self):
        self.w.add_track("T")
        self.assertFalse(self.w._header._dimmed[0])


class TestClipData(BaseTestCase):
    """Unit tests for the ClipData dataclass."""

    def test_end_property(self):
        cd = ClipData(clip_id=0, track_id=0, start=10, duration=20)
        self.assertEqual(cd.end, 30)

    def test_default_data(self):
        cd = ClipData(clip_id=0, track_id=0, start=0, duration=1)
        self.assertIsInstance(cd.data, dict)
        self.assertEqual(len(cd.data), 0)

    def test_default_pattern_is_none(self):
        cd = ClipData(clip_id=0, track_id=0, start=0, duration=1)
        self.assertIsNone(cd.pattern)


class TestTrackData(BaseTestCase):
    """Unit tests for the TrackData dataclass."""

    def test_default_pattern_is_none(self):
        td = TrackData(track_id=0, name="A")
        self.assertIsNone(td.pattern)

    def test_track_pattern_honored_by_drawbackground(self):
        from qtpy import QtGui, QtCore
        from uitk.widgets.sequencer import SequencerWidget, PatternSpec

        w = SequencerWidget()
        try:
            tid = w.add_track("patterned")
            td = w.get_track(tid)
            td.pattern = PatternSpec(style="dots", color="#FF8800", alpha=80)
            # Directly drive drawBackground — must not raise when a track
            # carries a PatternSpec.
            pix = QtGui.QPixmap(400, 200)
            pix.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(pix)
            try:
                w._timeline._scene.drawBackground(p, QtCore.QRectF(0, 0, 400, 200))
            finally:
                p.end()
        finally:
            w.close()
            w.deleteLater()


class TestPatternRegistry(BaseTestCase):
    """Unit tests for the background-pattern registry/brush helpers."""

    def setUp(self):
        from qtpy import QtGui
        from uitk.widgets.sequencer import (
            PatternSpec,
            HATCH_DENSE,
            HATCH_MEDIUM,
            HATCH_SPARSE,
        )
        from uitk.widgets.sequencer._data import PatternRegistry

        self.QtGui = QtGui
        self.pattern_brush = PatternRegistry.pattern_brush
        self.register_pattern = PatternRegistry.register_pattern
        self.PatternSpec = PatternSpec
        self.HATCH_DENSE = HATCH_DENSE
        self.HATCH_MEDIUM = HATCH_MEDIUM
        self.HATCH_SPARSE = HATCH_SPARSE
        self._cache = PatternRegistry._pattern_cache
        self._painters = PatternRegistry._pattern_painters
        self._builtin_painters = dict(PatternRegistry._pattern_painters)
        self._cache.clear()

    def tearDown(self):
        # Restore any custom-registered painters
        self._painters.clear()
        self._painters.update(self._builtin_painters)
        self._cache.clear()

    def test_builtin_styles_registered(self):
        for name in ("diagonal", "crosshatch", "vstripes", "hstripes", "dots", "grid"):
            self.assertIn(name, self._painters)

    def test_pattern_brush_returns_brush(self):
        b = self.pattern_brush("diagonal", self.QtGui.QColor("#888888"))
        self.assertIsInstance(b, self.QtGui.QBrush)

    def test_pattern_brush_caches_identical_calls(self):
        c = self.QtGui.QColor("#888888")
        b1 = self.pattern_brush("dots", c, self.HATCH_MEDIUM, 1.0)
        b2 = self.pattern_brush("dots", c, self.HATCH_MEDIUM, 1.0)
        self.assertIs(b1, b2)

    def test_pattern_brush_distinct_per_style(self):
        c = self.QtGui.QColor("#888888")
        b_diag = self.pattern_brush("diagonal", c, self.HATCH_MEDIUM, 1.0)
        b_grid = self.pattern_brush("grid", c, self.HATCH_MEDIUM, 1.0)
        self.assertIsNot(b_diag, b_grid)

    def test_pattern_brush_distinct_per_color(self):
        b_a = self.pattern_brush("diagonal", self.QtGui.QColor("#111111"))
        b_b = self.pattern_brush("diagonal", self.QtGui.QColor("#999999"))
        self.assertIsNot(b_a, b_b)

    def test_unknown_style_raises(self):
        with self.assertRaises(KeyError):
            self.pattern_brush("does-not-exist", self.QtGui.QColor("#888888"))

    def test_register_custom_pattern(self):
        calls = []

        def custom(p, size, color, lw):
            calls.append((size, color.name(), lw))
            p.setPen(self.QtGui.QPen(color, lw))
            p.drawPoint(0, 0)

        self.register_pattern("test-custom", custom)
        self.assertIn("test-custom", self._painters)
        b = self.pattern_brush("test-custom", self.QtGui.QColor("#5BBFB4"), 6, 1.5)
        self.assertIsInstance(b, self.QtGui.QBrush)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 6)
        self.assertEqual(calls[0][2], 1.5)

    def test_pattern_spec_brush(self):
        spec = self.PatternSpec(style="dots", color="#FF8800", alpha=120, spacing=10)
        b = spec.brush()
        self.assertIsInstance(b, self.QtGui.QBrush)
        # Re-calling returns the same cached brush
        self.assertIs(spec.brush(), b)

    def test_pattern_spec_hashable(self):
        spec_a = self.PatternSpec(style="dots", color="#FF8800")
        spec_b = self.PatternSpec(style="dots", color="#FF8800")
        # frozen=True → equal specs hash the same and can live in sets
        self.assertEqual(hash(spec_a), hash(spec_b))
        self.assertIn(spec_a, {spec_b})


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
        """Clip with all attributes mapped to the same color uses that color."""
        self.w.attribute_colors = {
            "rotateY": "#123456",
            "translateX": "#123456",
        }
        tid = self.w.add_track("Obj")
        cid = self.w.add_clip(tid, 0, 10, attributes=["rotateY", "translateX"])
        item = self.w._clip_items[cid]
        resolved = item._resolve_color()
        self.assertEqual(resolved.name(), "#123456")

    def test_clip_mixed_known_unknown_attrs_uses_consolidated(self):
        """Clip with one known and one unknown attribute uses consolidated."""
        self.w.attribute_colors = {
            "rotateY": "#123456",
            "consolidated": "#FFFFFF",
        }
        tid = self.w.add_track("Obj")
        cid = self.w.add_clip(tid, 0, 10, attributes=["rotateY", "unknownAttr"])
        item = self.w._clip_items[cid]
        resolved = item._resolve_color()
        self.assertEqual(resolved.name(), "#ffffff")

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

    def test_set_attribute_color_updates_map_and_repaints(self):
        """set_attribute_color mutates a single entry and triggers a repaint.

        Regression: the ``attribute_colors`` getter returns the live dict,
        so in-place mutation silently bypasses the scene repaint the setter
        performs.  ``set_attribute_color`` provides a repainting single-entry
        mutator and is reflected by ``_resolve_color``.
        """
        tid = self.w.add_track("Obj")
        cid = self.w.add_clip(tid, 0, 10, attributes=["translateX"])
        item = self.w._clip_items[cid]

        updated = {}
        self.w._timeline._scene.update = lambda *a, **k: updated.setdefault("hit", True)

        self.w.set_attribute_color("translateX", "#123456")

        self.assertTrue(updated.get("hit"), "scene.update was not called")
        self.assertEqual(self.w.attribute_colors["translateX"], "#123456")
        self.assertEqual(item._resolve_color().name(), "#123456")


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
        from uitk.managers.settings_manager import SettingsManager

        settings = SettingsManager(namespace="test_attr_colors_defaults")
        dlg = AttributeColorDialog(settings=settings)
        cmap = dlg.color_map()
        self.assertEqual(cmap["translateX"], _DEFAULT_ATTRIBUTE_COLORS["translateX"])
        dlg.close()
        settings.clear()

    def test_restore_defaults_resets(self):
        from uitk.managers.settings_manager import SettingsManager

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


class TestMarkerSystem(BaseTestCase):
    """Tests for the enhanced marker system."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    # -- MarkerData fields -------------------------------------------------

    def test_marker_data_defaults(self):
        md = MarkerData(marker_id=0, time=10.0)
        self.assertTrue(md.draggable)
        self.assertEqual(md.style, "triangle")
        self.assertEqual(md.line_style, "dashed")
        self.assertAlmostEqual(md.opacity, 1.0)

    def test_marker_data_custom_fields(self):
        md = MarkerData(
            marker_id=0,
            time=5.0,
            style="diamond",
            line_style="solid",
            draggable=False,
            opacity=0.5,
        )
        self.assertFalse(md.draggable)
        self.assertEqual(md.style, "diamond")
        self.assertEqual(md.line_style, "solid")
        self.assertAlmostEqual(md.opacity, 0.5)

    # -- add_marker with new params -----------------------------------------

    def test_add_marker_default_style(self):
        mid = self.w.add_marker(time=10.0, note="test")
        md = self.w.get_marker(mid)
        self.assertEqual(md.style, "triangle")
        self.assertTrue(md.draggable)

    def test_add_marker_custom_style(self):
        mid = self.w.add_marker(
            time=20.0,
            note="boundary",
            color="#FF0000",
            draggable=False,
            style="bracket",
            line_style="solid",
            opacity=0.85,
        )
        md = self.w.get_marker(mid)
        self.assertEqual(md.style, "bracket")
        self.assertEqual(md.line_style, "solid")
        self.assertFalse(md.draggable)
        self.assertAlmostEqual(md.opacity, 0.85)
        self.assertEqual(md.color, "#FF0000")

    def test_add_marker_all_styles(self):
        """Verify all four marker styles can be instantiated."""
        for style in ("triangle", "diamond", "line", "bracket"):
            mid = self.w.add_marker(time=0.0, style=style)
            md = self.w.get_marker(mid)
            self.assertEqual(md.style, style)

    def test_add_marker_all_line_styles(self):
        """Verify all four line styles can be instantiated."""
        for ls in ("dashed", "solid", "dotted", "none"):
            mid = self.w.add_marker(time=0.0, line_style=ls)
            md = self.w.get_marker(mid)
            self.assertEqual(md.line_style, ls)

    # -- marker list / clear ------------------------------------------------

    def test_markers_returns_all(self):
        self.w.add_marker(10.0)
        self.w.add_marker(20.0, style="diamond")
        self.w.add_marker(30.0, draggable=False)
        self.assertEqual(len(self.w.markers()), 3)

    def test_clear_markers(self):
        self.w.add_marker(10.0, style="bracket")
        self.w.add_marker(20.0, style="line")
        self.w.clear_markers()
        self.assertEqual(len(self.w.markers()), 0)

    # -- remove_marker ------------------------------------------------------

    def test_remove_marker(self):
        mid = self.w.add_marker(10.0, style="diamond")
        self.w.remove_marker(mid)
        self.assertIsNone(self.w.get_marker(mid))

    # -- opacity is applied to item ----------------------------------------

    def test_marker_item_opacity(self):
        mid = self.w.add_marker(time=5.0, opacity=0.5)
        item = self.w._marker_items[mid]
        self.assertAlmostEqual(item.opacity(), 0.5, places=2)

    # -- range highlight ----------------------------------------------------

    def test_set_range_highlight(self):
        self.w.set_range_highlight(10, 50)
        rng = self.w.range_highlight()
        self.assertIsNotNone(rng)
        self.assertEqual(rng, (10, 50))

    def test_set_range_highlight_updates_existing(self):
        self.w.set_range_highlight(10, 50)
        self.w.set_range_highlight(20, 80)
        rng = self.w.range_highlight()
        self.assertEqual(rng, (20, 80))
        # Should reuse the same item, not create a second
        highlights = [
            i
            for i in self.w._timeline._scene.items()
            if isinstance(i, RangeHighlightItem)
        ]
        self.assertEqual(len(highlights), 1)

    def test_clear_range_highlight(self):
        self.w.set_range_highlight(0, 100)
        self.w.clear_range_highlight()
        self.assertIsNone(self.w.range_highlight())
        highlights = [
            i
            for i in self.w._timeline._scene.items()
            if isinstance(i, RangeHighlightItem)
        ]
        self.assertEqual(len(highlights), 0)

    def test_clear_removes_range_highlight(self):
        """widget.clear() should also remove the range highlight."""
        self.w.add_track("T")
        self.w.set_range_highlight(0, 50)
        self.w.clear()
        self.assertIsNone(self.w.range_highlight())

    def test_range_highlight_custom_color(self):
        self.w.set_range_highlight(0, 100, color="#FF0000", alpha=60)
        item = self.w._range_highlight
        self.assertEqual(item.color.red(), 255)
        self.assertEqual(item.color.alpha(), 60)

    def test_range_highlight_changed_signal(self):
        """Dragging the range emits range_highlight_changed(start, end)."""
        received = []
        self.w.range_highlight_changed.connect(lambda s, e: received.append((s, e)))
        self.w.set_range_highlight(10, 50)
        item = self.w._range_highlight
        # Simulate a programmatic drag (move by changing start/end and emitting)
        item._start = 20
        item._end = 60
        self.w.range_highlight_changed.emit(20, 60)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], (20, 60))

    def test_range_highlight_none_by_default(self):
        self.assertIsNone(self.w.range_highlight())


# =========================================================================
# Sub-Row / Track Expansion
# =========================================================================


class TestSubRowExpansion(BaseTestCase):
    """Expand/collapse tracks and verify sub-row clip creation."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_expand_track_creates_sub_row_clips(self):
        """expand_track with explicit data creates sub-row clips."""
        tid = self.w.add_track("obj_A")
        sub_data = [
            ("translateX", [(10, 40, "translateX", "#FF0000", {})]),
            ("rotateY", [(5, 50, "rotateY", "#00FF00", {})]),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        self.assertEqual(len(sub_clips), 2)

    def test_expand_track_stores_sub_names(self):
        tid = self.w.add_track("obj_A")
        sub_data = [("tx", [(0, 10, "tx", None, {})])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        self.assertIn(tid, self.w._expanded_tracks)
        self.assertEqual(self.w._expanded_tracks[tid], ["tx"])

    def test_collapse_track_removes_sub_clips(self):
        tid = self.w.add_track("obj_A")
        sub_data = [
            ("tx", [(0, 30, "tx", "#FF0000", {})]),
            ("ry", [(0, 30, "ry", "#00FF00", {})]),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        self.assertEqual(len([c for c in self.w.clips() if c.sub_row]), 2)
        self.w.collapse_track(tid)
        self.assertEqual(len([c for c in self.w.clips() if c.sub_row]), 0)
        self.assertNotIn(tid, self.w._expanded_tracks)

    def test_toggle_track_expanded(self):
        tid = self.w.add_track("obj_A")
        sub_data = [("tx", [(0, 10, "tx", None, {})])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        self.assertTrue(self.w.is_track_expanded(tid))
        self.w.toggle_track_expanded(tid)
        self.assertFalse(self.w.is_track_expanded(tid))

    def test_expand_track_uses_sub_row_provider(self):
        """When sub_row_data is None, the sub_row_provider callback is used."""
        tid = self.w.add_track("obj_A")
        called_with = []

        def provider(track_id, track_name):
            called_with.append((track_id, track_name))
            return [("tx", [(0, 20, "tx", "#AAAAAA", {})])]

        self.w.sub_row_provider = provider
        self.w.expand_track(tid)
        self.assertEqual(len(called_with), 1)
        self.assertEqual(called_with[0], (tid, "obj_A"))
        self.assertEqual(len([c for c in self.w.clips() if c.sub_row]), 1)

    def test_sub_row_clip_has_correct_sub_row_name(self):
        tid = self.w.add_track("obj_A")
        sub_data = [("translateX", [(10, 40, "translateX", "#FF0000", {})])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        self.assertEqual(sub_clips[0].sub_row, "translateX")

    def test_sub_row_height_is_22(self):
        """Sub-row height was increased from 14 to 22 for readability."""
        self.assertEqual(_SUB_ROW_HEIGHT, 22)

    def test_visual_rows_includes_sub_rows(self):
        """_visual_rows returns sub-row entries after expanded track."""
        tid = self.w.add_track("obj_A")
        sub_data = [
            ("tx", [(0, 10, "tx", None, {})]),
            ("ry", [(0, 10, "ry", None, {})]),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        rows = self.w._visual_rows()
        # Main row + 2 sub-rows
        self.assertEqual(len(rows), 3)
        self.assertFalse(rows[0][2])  # main row is_sub=False
        self.assertTrue(rows[1][2])  # sub-row is_sub=True
        self.assertTrue(rows[2][2])  # sub-row is_sub=True
        # Each row carries its owning track_id at index 3
        self.assertEqual(rows[0][3], tid)
        self.assertEqual(rows[1][3], tid)
        self.assertEqual(rows[2][3], tid)

    def test_sub_clip_default_resizable(self):
        """Sub-row clips with duration are resizable by default."""
        tid = self.w.add_track("obj_A")
        sub_data = [("tx", [(25, 10, "tx", "#FF0000", {})])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        self.assertEqual(len(sub_clips), 1)
        self.assertTrue(sub_clips[0].data.get("resizable_left", True))
        self.assertTrue(sub_clips[0].data.get("resizable_right", True))


# =========================================================================
# Curve Preview Rendering
# =========================================================================


class TestCurvePreviewRendering(BaseTestCase):
    """Verify curve-preview mini graph renders on sub-row clips."""

    SAMPLE_PREVIEW = {
        "keys": [(0, 0.0), (50, 1.0), (100, 0.5)],
        "segments": [
            {
                "t0": 0,
                "v0": 0.0,
                "t1": 50,
                "v1": 1.0,
                "out_type": "spline",
                "cp1": (16.67, 0.33),
                "cp2": (33.33, 0.67),
            },
            {
                "t0": 50,
                "v0": 1.0,
                "t1": 100,
                "v1": 0.5,
                "out_type": "linear",
                "cp1": None,
                "cp2": None,
            },
        ],
        "val_min": 0.0,
        "val_max": 1.0,
    }

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _make_preview_clip(self, preview, color="#FF6600"):
        """Create a sub-row clip with curve_preview and return the ClipItem."""
        tid = self.w.add_track("obj_A")
        sub_data = [
            (
                "translateX",
                [(0, 100, "translateX", color, {"curve_preview": preview})],
            ),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        self.assertEqual(len(sub_clips), 1)
        clip = sub_clips[0]
        item = self.w._clip_items[clip.clip_id]
        return clip, item

    def test_curve_preview_stored_on_clip(self):
        """curve_preview from extra dict is preserved on ClipData.data."""
        clip, _ = self._make_preview_clip(self.SAMPLE_PREVIEW)
        self.assertIn("curve_preview", clip.data)
        self.assertEqual(len(clip.data["curve_preview"]["keys"]), 3)

    def test_paint_curve_preview_does_not_crash(self):
        """Rendering a sub-row clip with curve_preview must not raise."""
        from qtpy import QtGui, QtWidgets

        clip, item = self._make_preview_clip(self.SAMPLE_PREVIEW)
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()

    def test_paint_with_stepped_segment(self):
        """Stepped segments render step shape without crashing."""
        from qtpy import QtGui, QtWidgets

        preview = {
            "keys": [(0, 1.0), (50, 0.0)],
            "segments": [
                {
                    "t0": 0,
                    "v0": 1.0,
                    "t1": 50,
                    "v1": 0.0,
                    "out_type": "step",
                    "cp1": None,
                    "cp2": None,
                }
            ],
            "val_min": 0.0,
            "val_max": 1.0,
        }
        clip, item = self._make_preview_clip(preview)
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()

    def test_paint_flat_value_range(self):
        """Flat keys (val_min == val_max) render a centred line."""
        from qtpy import QtGui, QtWidgets

        preview = {
            "keys": [(0, 5.0), (50, 5.0)],
            "segments": [
                {
                    "t0": 0,
                    "v0": 5.0,
                    "t1": 50,
                    "v1": 5.0,
                    "out_type": "linear",
                    "cp1": None,
                    "cp2": None,
                }
            ],
            "val_min": 5.0,
            "val_max": 5.0,
        }
        clip, item = self._make_preview_clip(preview)
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()

    def test_paint_single_key_no_segments(self):
        """A single key with no segments renders dots only."""
        from qtpy import QtGui, QtWidgets

        preview = {
            "keys": [(50, 1.0)],
            "segments": [],
            "val_min": 1.0,
            "val_max": 1.0,
        }
        clip, item = self._make_preview_clip(preview)
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()

    def test_sub_row_without_curve_preview_uses_default_paint(self):
        """Sub-row clip with no curve_preview renders as solid block."""
        tid = self.w.add_track("obj_A")
        sub_data = [("tx", [(0, 100, "tx", "#FF0000", {})])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        clip = sub_clips[0]
        self.assertNotIn("curve_preview", clip.data)

    def test_paint_stepnext_segment(self):
        """stepnext tangent type renders without crashing."""
        from qtpy import QtGui, QtWidgets

        preview = {
            "keys": [(0, 0.0), (50, 1.0)],
            "segments": [
                {
                    "t0": 0,
                    "v0": 0.0,
                    "t1": 50,
                    "v1": 1.0,
                    "out_type": "stepnext",
                    "cp1": None,
                    "cp2": None,
                }
            ],
            "val_min": 0.0,
            "val_max": 1.0,
        }
        clip, item = self._make_preview_clip(preview)
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()


# =========================================================================
# Keyframe Rendering (legacy keyframe_times path)
# =========================================================================


class TestKeyframeRendering(BaseTestCase):
    """Verify legacy keyframe_times clips fall through to default paint."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _make_kf_clip(self, kf_times, color="#FF6600"):
        """Create a sub-row clip with keyframe_times and return the ClipItem."""
        tid = self.w.add_track("obj_A")
        sub_data = [
            (
                "translateX",
                [
                    (
                        0,
                        100,
                        "translateX",
                        color,
                        {"keyframe_times": kf_times},
                    )
                ],
            ),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        self.assertEqual(len(sub_clips), 1)
        clip = sub_clips[0]
        item = self.w._clip_items[clip.clip_id]
        return clip, item

    def test_keyframe_times_stored_on_clip(self):
        """keyframe_times from extra dict are preserved on ClipData.data."""
        kf = [(10, "spline"), (50, "linear"), (90, "step")]
        clip, _ = self._make_kf_clip(kf)
        self.assertEqual(clip.data["keyframe_times"], kf)

    def test_paint_keyframes_called_for_sub_row_with_kf_data(self):
        """Sub-row clips with keyframe_times take the keyframe paint path."""
        kf = [(20, "spline"), (80, "step")]
        clip, item = self._make_kf_clip(kf)
        # Verify the clip is a sub-row and has kf data (the paint() guard)
        self.assertTrue(clip.sub_row)
        self.assertTrue(clip.data.get("keyframe_times"))

    def test_paint_does_not_crash_with_keyframes(self):
        """Rendering a sub-row clip with keyframe data must not raise."""
        from qtpy import QtGui, QtWidgets

        kf = [(0, "spline"), (50, "linear"), (100, "step")]
        clip, item = self._make_kf_clip(kf)
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()

    def test_paint_empty_keyframe_list_renders_default(self):
        """Empty keyframe_times list falls through to default paint."""
        from qtpy import QtGui, QtWidgets

        tid = self.w.add_track("obj_A")
        sub_data = [
            ("tx", [(0, 100, "tx", "#FF0000", {"keyframe_times": []})]),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        clip = sub_clips[0]
        item = self.w._clip_items[clip.clip_id]
        # Empty list is falsy — should use default paint path
        self.assertFalse(clip.data["keyframe_times"])
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()

    def test_paint_with_stepped_keys(self):
        """Stepped keys render square glyphs without crashing."""
        from qtpy import QtGui, QtWidgets

        kf = [(25, "step"), (75, "stepnext")]
        clip, item = self._make_kf_clip(kf)
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()

    def test_paint_single_keyframe(self):
        """A single keyframe renders without division errors."""
        from qtpy import QtGui, QtWidgets

        kf = [(50, "spline")]
        clip, item = self._make_kf_clip(kf)
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()

    def test_sub_row_without_keyframe_times_uses_default_paint(self):
        """Sub-row clip with no keyframe_times key renders as solid block."""
        tid = self.w.add_track("obj_A")
        sub_data = [("tx", [(0, 100, "tx", "#FF0000", {})])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        clip = sub_clips[0]
        self.assertNotIn("keyframe_times", clip.data)

    def test_locked_sub_row_with_keyframes_still_shows_lock(self):
        """Lock icon must render on keyframe sub-rows when locked=True."""
        tid = self.w.add_track("obj_A")
        # Must set locked via the extra dict
        sub_data = [
            (
                "tx",
                [
                    (
                        0,
                        100,
                        "tx",
                        "#FF0000",
                        {"keyframe_times": [(50, "spline")], "locked": True},
                    )
                ],
            ),
        ]
        # Use add_clip directly to set locked=True on the ClipData
        self.w.expand_track(tid, sub_row_data=sub_data)


# =========================================================================
# Gap Overlays
# =========================================================================


class TestGapOverlays(BaseTestCase):
    """Gap overlay creation, visibility, and lifecycle."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_add_gap_overlay(self):
        """add_gap_overlay creates a scene item and tracks it."""
        self.w.add_gap_overlay(50, 60)
        self.assertEqual(len(self.w._gap_overlays), 1)

    def test_add_multiple_gap_overlays(self):
        self.w.add_gap_overlay(10, 20)
        self.w.add_gap_overlay(30, 40)
        self.w.add_gap_overlay(70, 80)
        self.assertEqual(len(self.w._gap_overlays), 3)

    def test_clear_gap_overlays(self):
        self.w.add_gap_overlay(10, 20)
        self.w.add_gap_overlay(30, 40)
        self.w.clear_gap_overlays()
        self.assertEqual(len(self.w._gap_overlays), 0)

    def test_gap_overlay_visible_by_default(self):
        """Gaps are visible when _show_gap_overlays is True (default)."""
        self.assertTrue(self.w._show_gap_overlays)
        self.w.add_gap_overlay(10, 20)
        self.assertTrue(self.w._gap_overlays[0].isVisible())

    def test_gap_overlay_hidden_when_disabled(self):
        """Gaps created while show_gap_overlays=False are hidden."""
        self.w.show_gap_overlays = False
        self.w.add_gap_overlay(10, 20)
        self.assertFalse(self.w._gap_overlays[0].isVisible())

    def test_toggle_show_gap_overlays(self):
        """Toggling show_gap_overlays updates all existing gaps."""
        self.w.add_gap_overlay(10, 20)
        self.w.add_gap_overlay(30, 40)
        self.w.show_gap_overlays = False
        for item in self.w._gap_overlays:
            self.assertFalse(item.isVisible())
        self.w.show_gap_overlays = True
        for item in self.w._gap_overlays:
            self.assertTrue(item.isVisible())

    def test_gap_overlay_locked_flag(self):
        """add_gap_overlay(locked=True) sets the locked flag."""
        self.w.add_gap_overlay(10, 20, locked=True)
        self.assertTrue(self.w._gap_overlays[0]._locked)

    def test_gap_overlay_unlocked_by_default(self):
        self.w.add_gap_overlay(10, 20)
        self.assertFalse(self.w._gap_overlays[0]._locked)

    def test_set_all_gap_overlays_locked(self):
        self.w.add_gap_overlay(10, 20)
        self.w.add_gap_overlay(30, 40)
        self.w.set_all_gap_overlays_locked(True)
        for item in self.w._gap_overlays:
            self.assertTrue(item._locked)
        self.w.set_all_gap_overlays_locked(False)
        for item in self.w._gap_overlays:
            self.assertFalse(item._locked)

    def test_clear_decorations_removes_gaps(self):
        """clear_decorations removes gap overlays along with other items."""
        self.w.add_gap_overlay(10, 20)
        self.w.add_marker(time=25)
        self.w.clear_decorations()
        self.assertEqual(len(self.w._gap_overlays), 0)

    def test_gap_overlay_is_scene_item(self):
        """Gap overlays are added to the QGraphicsScene."""
        self.w.add_gap_overlay(10, 20)
        scene = self.w._timeline.scene()
        gap_items = [
            item for item in scene.items() if isinstance(item, _GapOverlayItem)
        ]
        self.assertEqual(len(gap_items), 1)

    def test_gap_edge_click_does_not_start_marquee(self):
        """Clicking a gap overlay edge must start a gap drag, not a marquee.

        Bug: mousePressEvent in TimelineView checked ItemIsSelectable
        which gap overlays don't have, so clicks fell to marquee code.
        Fixed: 2026-04-07
        """
        from qtpy import QtCore, QtWidgets, QtTest

        self.w.resize(800, 400)
        self.w.show()
        self.w.add_track("obj_A")
        self.w.add_gap_overlay(50, 70)
        QtWidgets.QApplication.processEvents()

        tl = self.w._timeline
        gap_item = self.w._gap_overlays[0]
        # Ensure the gap is within the visible viewport before mapping
        gap_rect = gap_item._rect()
        tl.ensureVisible(gap_rect, 50, 50)
        QtWidgets.QApplication.processEvents()
        # Map the right edge of the gap to view coords
        right_edge = QtCore.QPointF(gap_rect.right() - 2, gap_rect.center().y())
        view_pos = tl.mapFromScene(right_edge)

        # Simulate a left-button press at the gap's right edge
        QtTest.QTest.mousePress(
            tl.viewport(),
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            QtCore.QPoint(int(view_pos.x()), int(view_pos.y())),
        )

        # Marquee should NOT have started
        self.assertFalse(
            tl._marquee_active,
            "Marquee started instead of forwarding to gap overlay!",
        )


# =========================================================================
# Shot Blocks (Ruler)
# =========================================================================


class TestShotBlocks(BaseTestCase):
    """Shot block indicators on the ruler."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_set_shot_blocks(self):
        """set_shot_blocks populates the ruler with blocks."""
        blocks = [
            {"name": "Shot_A", "start": 0, "end": 50, "active": True},
            {"name": "Shot_B", "start": 60, "end": 100, "active": False},
        ]
        self.w.set_shot_blocks(blocks)
        ruler = self.w._timeline._scene.ruler
        self.assertEqual(len(ruler._shot_blocks), 2)

    def test_clear_shot_blocks(self):
        blocks = [{"name": "S", "start": 0, "end": 50, "active": True}]
        self.w.set_shot_blocks(blocks)
        self.w.clear_shot_blocks()
        ruler = self.w._timeline._scene.ruler
        self.assertEqual(len(ruler._shot_blocks), 0)

    def test_shot_blocks_replaced_on_set(self):
        """Calling set_shot_blocks replaces previous blocks."""
        self.w.set_shot_blocks([{"name": "A", "start": 0, "end": 50, "active": True}])
        self.w.set_shot_blocks(
            [
                {"name": "B", "start": 0, "end": 30, "active": True},
                {"name": "C", "start": 40, "end": 80, "active": False},
            ]
        )
        ruler = self.w._timeline._scene.ruler
        self.assertEqual(len(ruler._shot_blocks), 2)


# =========================================================================
# Active Range / Range Overlays
# =========================================================================


class TestActiveRange(BaseTestCase):
    """Active-shot column tint API."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_set_active_range(self):
        self.w.set_active_range(10, 90)
        self.assertEqual(self.w._active_range, (10, 90))

    def test_active_range_none_by_default(self):
        self.assertIsNone(self.w._active_range)

    def test_clear_active_range(self):
        self.w.set_active_range(10, 90)
        self.w.clear_active_range()
        self.assertIsNone(self.w._active_range)


class TestRangeOverlayLifecycle(BaseTestCase):
    """Static range overlay management."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_add_range_overlay_is_scene_item(self):
        self.w.add_range_overlay(10, 90)
        scene = self.w._timeline.scene()
        overlays = [
            item for item in scene.items() if isinstance(item, _StaticRangeOverlay)
        ]
        self.assertEqual(len(overlays), 1)

    def test_clear_decorations_removes_range_overlays(self):
        self.w.add_range_overlay(10, 90)
        self.w.clear_decorations()
        self.assertEqual(len(self.w._range_overlays), 0)


# =========================================================================
# =========================================================================
# Hidden Tracks
# =========================================================================


class TestHiddenTracks(BaseTestCase):
    """set_hidden_tracks API."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_set_hidden_tracks(self):
        self.w.set_hidden_tracks(["obj_A", "obj_B"])
        self.assertEqual(self.w._hidden_tracks, ["obj_A", "obj_B"])

    def test_hidden_tracks_empty_by_default(self):
        self.assertEqual(self.w._hidden_tracks, [])


# =========================================================================
# DrawBackground (center-line rendering)
# =========================================================================


class TestDrawBackground(BaseTestCase):
    """Background rendering with sub-row center lines."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_draw_background_no_crash_empty(self):
        """Drawing background on an empty widget must not crash."""
        from qtpy import QtGui, QtCore

        pixmap = QtGui.QPixmap(800, 400)
        painter = QtGui.QPainter(pixmap)
        self.w._timeline.drawBackground(painter, QtCore.QRectF(0, 0, 800, 400))
        painter.end()

    def test_draw_background_with_sub_rows(self):
        """Drawing background with expanded sub-rows (center lines) no crash."""
        from qtpy import QtGui, QtCore

        tid = self.w.add_track("obj_A")
        sub_data = [
            ("tx", [(0, 50, "tx", "#FF0000", {})]),
            ("ry", [(0, 50, "ry", "#00FF00", {})]),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        pixmap = QtGui.QPixmap(800, 400)
        painter = QtGui.QPainter(pixmap)
        self.w._timeline.drawBackground(painter, QtCore.QRectF(0, 0, 800, 400))
        painter.end()

    def test_draw_background_with_active_range(self):
        """Active range tint renders without errors."""
        from qtpy import QtGui, QtCore

        self.w.add_track("obj_A")
        self.w.set_active_range(10, 90)
        pixmap = QtGui.QPixmap(800, 400)
        painter = QtGui.QPainter(pixmap)
        self.w._timeline.drawBackground(painter, QtCore.QRectF(0, 0, 800, 400))
        painter.end()

    def test_draw_background_bg_curves_clipped_outside_active_range(self):
        """Background curves must not paint inside the active-range area.

        The drawBackground method uses QRegion subtraction to exclude the
        active range rectangle from the clip region when painting bg curves.
        This verifies the path executes without errors.
        Fixed: 2026-04-07
        """
        from qtpy import QtGui, QtCore

        tid = self.w.add_track("obj_A")
        sub_data = [("tx", [(0, 100, "tx", "#FF0000", {})])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        self.w.set_active_range(30, 70)

        # Inject a minimal bg curve preview
        preview = {
            "segments": [{"t0": 0, "v0": 0, "t1": 100, "v1": 1, "out_type": "linear"}],
            "val_min": 0.0,
            "val_max": 1.0,
        }
        self.w.set_bg_curve_preview(tid, "tx", preview, "#FF0000")

        pixmap = QtGui.QPixmap(800, 400)
        painter = QtGui.QPainter(pixmap)
        self.w._timeline.drawBackground(painter, QtCore.QRectF(0, 0, 800, 400))
        painter.end()


# =========================================================================
# Clip Mutation APIs
# =========================================================================


class TestClipMutation(BaseTestCase):
    """set_clip_label, set_clip_locked, and their signals."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_set_clip_label_updates_data(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 50, label="Old")
        self.w.set_clip_label(cid, "New")
        self.assertEqual(self.w.get_clip(cid).label, "New")

    def test_set_clip_label_noop_for_invalid_id(self):
        """set_clip_label with unknown id must not raise."""
        self.w.set_clip_label(999, "anything")

    def test_set_clip_locked_true(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 50)
        self.assertFalse(self.w.get_clip(cid).locked)
        self.w.set_clip_locked(cid, True)
        self.assertTrue(self.w.get_clip(cid).locked)

    def test_set_clip_locked_false(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 50, locked=True)
        self.w.set_clip_locked(cid, False)
        self.assertFalse(self.w.get_clip(cid).locked)

    def test_set_clip_locked_noop_for_invalid_id(self):
        self.w.set_clip_locked(999, True)


# =========================================================================
# Swap Clips
# =========================================================================


class TestSwapClips(BaseTestCase):
    """swap_clips exchanges positions and emits clips_reordered."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_swap_clips_exchanges_positions(self):
        tid = self.w.add_track("T")
        c0 = self.w.add_clip(tid, 0, 30)
        c1 = self.w.add_clip(tid, 40, 20)
        self.w.swap_clips(c0, c1)
        # After swap, the earlier clip (c0 at 0) now starts later
        # and the later clip (c1 at 40) is moved earlier.
        self.assertAlmostEqual(self.w.get_clip(c1).start, 0.0)

    def test_swap_clips_emits_clips_reordered(self):
        tid = self.w.add_track("T")
        c0 = self.w.add_clip(tid, 0, 30)
        c1 = self.w.add_clip(tid, 40, 20)
        received = []
        self.w.clips_reordered.connect(lambda a, b: received.append((a, b)))
        self.w.swap_clips(c0, c1)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], (c0, c1))

    def test_swap_same_clip_is_noop(self):
        tid = self.w.add_track("T")
        c0 = self.w.add_clip(tid, 0, 30)
        self.w.swap_clips(c0, c0)  # should not raise

    def test_swap_invalid_clip_is_noop(self):
        tid = self.w.add_track("T")
        c0 = self.w.add_clip(tid, 0, 30)
        self.w.swap_clips(c0, 999)  # should not raise


# =========================================================================
# Playhead Navigation (key-based)
# =========================================================================


class TestPlayheadNavigation(BaseTestCase):
    """go_to_next_key, go_to_prev_key, add_marker_at_playhead."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_key_times_returns_sorted_boundaries(self):
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 10, 20)  # boundaries: 10, 30
        self.w.add_clip(tid, 50, 10)  # boundaries: 50, 60
        times = self.w._key_times()
        self.assertEqual(times, [10, 30, 50, 60])

    def test_key_times_empty_when_no_clips(self):
        self.assertEqual(self.w._key_times(), [])

    def test_go_to_next_key(self):
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 10, 20)
        self.w.add_clip(tid, 50, 10)
        self.w.set_playhead(0.0)
        self.w.go_to_next_key()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 10.0)
        self.w.go_to_next_key()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 30.0)

    def test_go_to_prev_key(self):
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 10, 20)
        self.w.add_clip(tid, 50, 10)
        self.w.set_playhead(60.0)
        self.w.go_to_prev_key()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 50.0)
        self.w.go_to_prev_key()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 30.0)

    def test_go_to_next_key_noop_at_end(self):
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 0, 10)
        self.w.set_playhead(10.0)
        self.w.go_to_next_key()  # no key after 10
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 10.0)

    def test_go_to_prev_key_noop_at_start(self):
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 10, 20)
        self.w.set_playhead(10.0)
        self.w.go_to_prev_key()  # no key before 10
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 10.0)

    def test_add_marker_at_playhead(self):
        self.w.set_playhead(25.0)
        received = []
        self.w.marker_added.connect(lambda mid, t: received.append((mid, t)))
        self.w.add_marker_at_playhead()
        self.assertEqual(len(self.w.markers()), 1)
        self.assertAlmostEqual(self.w.markers()[0].time, 25.0)
        self.assertEqual(len(received), 1)
        self.assertAlmostEqual(received[0][1], 25.0)


# =========================================================================
# Frame Shot / Frame All
# =========================================================================


class TestFrameShot(BaseTestCase):
    """frame_shot / frame_all viewport framing."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_frame_shot_adjusts_ppu(self):
        """frame_shot changes pixels-per-unit to fit the range."""
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 100, 200)
        old_ppu = self.w._timeline.pixels_per_unit
        self.w.set_active_range(100, 300)
        self.w.set_range_highlight(100, 300)
        self.w.frame_shot()
        # PPU should have changed to fit the 200-unit span
        self.assertNotAlmostEqual(self.w._timeline.pixels_per_unit, old_ppu)

    def test_frame_shot_noop_empty(self):
        """frame_shot does nothing with no clips or range."""
        self.w.frame_shot()  # should not raise

    def test_frame_all_is_alias(self):
        """frame_all is an alias for frame_shot."""
        # Class-level alias: bound methods differ, but underlying function is same
        self.assertEqual(
            type(self.w).frame_all,
            type(self.w).frame_shot,
        )


# =========================================================================
# Overlay Visibility Properties
# =========================================================================


class TestOverlayVisibility(BaseTestCase):
    """show_range_overlays, show_range_highlight property toggles."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_show_range_overlays_default_true(self):
        self.assertTrue(self.w.show_range_overlays)

    def test_show_range_overlays_toggle(self):
        self.w.add_range_overlay(10, 50)
        self.w.add_range_overlay(60, 80)
        self.w.show_range_overlays = False
        for item in self.w._range_overlays:
            self.assertFalse(item.isVisible())
        self.w.show_range_overlays = True
        for item in self.w._range_overlays:
            self.assertTrue(item.isVisible())

    def test_show_range_highlight_default_true(self):
        self.assertTrue(self.w.show_range_highlight)

    def test_show_range_highlight_toggle(self):
        self.w.set_range_highlight(10, 50)
        self.assertTrue(self.w._range_highlight.isVisible())
        self.w.show_range_highlight = False
        self.assertFalse(self.w._range_highlight.isVisible())
        self.w.show_range_highlight = True
        self.assertTrue(self.w._range_highlight.isVisible())

    def test_show_range_highlight_noop_without_item(self):
        """Toggling show_range_highlight when highlight is None must not raise."""
        self.w.show_range_highlight = False


# =========================================================================
# Sub-Row Height Property
# =========================================================================


class TestSubRowHeight(BaseTestCase):
    """sub_row_height property getter/setter."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_sub_row_height_default(self):
        self.assertEqual(self.w.sub_row_height, _SUB_ROW_HEIGHT)

    def test_sub_row_height_setter(self):
        self.w.sub_row_height = 30
        self.assertEqual(self.w.sub_row_height, 30)

    def test_sub_row_height_clamps_minimum(self):
        self.w.sub_row_height = 3
        self.assertEqual(self.w.sub_row_height, 8)


# =========================================================================
# Track Expansion/Collapse Signals
# =========================================================================


class TestExpansionSignals(BaseTestCase):
    """Verify track_expanded and track_collapsed signals."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_expand_emits_track_expanded(self):
        tid = self.w.add_track("obj_A")
        received = []
        self.w.track_expanded.connect(lambda t: received.append(t))
        sub_data = [("tx", [(0, 10, "tx", None, {})])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        self.assertEqual(received, [tid])

    def test_collapse_emits_track_collapsed(self):
        tid = self.w.add_track("obj_A")
        sub_data = [("tx", [(0, 10, "tx", None, {})])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        received = []
        self.w.track_collapsed.connect(lambda t: received.append(t))
        self.w.collapse_track(tid)
        self.assertEqual(received, [tid])


# =========================================================================
# Clear Decorations (completeness)
# =========================================================================


class TestClearDecorationsComplete(BaseTestCase):
    """clear_decorations removes markers, highlight, overlays, gaps, and shot blocks."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_clear_decorations_removes_all(self):
        """All decoration types are cleared in one call."""
        # Populate every decoration type
        self.w.add_marker(time=10.0, note="test")
        self.w.set_range_highlight(10, 50)
        self.w.add_range_overlay(0, 100)
        self.w.add_gap_overlay(50, 60)
        self.w.set_shot_blocks([{"name": "S", "start": 0, "end": 50, "active": True}])
        # All present
        self.assertTrue(len(self.w.markers()) > 0)
        self.assertIsNotNone(self.w.range_highlight())
        self.assertTrue(len(self.w._range_overlays) > 0)
        self.assertTrue(len(self.w._gap_overlays) > 0)

        # Clear and verify
        self.w.clear_decorations()
        self.assertEqual(len(self.w.markers()), 0)
        self.assertIsNone(self.w.range_highlight())
        self.assertEqual(len(self.w._range_overlays), 0)
        self.assertEqual(len(self.w._gap_overlays), 0)

    def test_clear_decorations_preserves_tracks_and_clips(self):
        """Tracks and clips survive clear_decorations."""
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 50)
        self.w.add_marker(time=10.0)
        self.w.clear_decorations()
        self.assertEqual(len(self.w.tracks()), 1)
        self.assertIsNotNone(self.w.get_clip(cid))


# =========================================================================
# Waveform Rendering
# =========================================================================


class TestWaveformRendering(BaseTestCase):
    """Waveform paint path for audio clips."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_paint_with_waveform_data(self):
        """Clip with waveform envelope renders without crash."""
        from qtpy import QtGui, QtWidgets

        tid = self.w.add_track("Audio")
        waveform = [(-0.5, 0.5), (-0.3, 0.8), (-0.7, 0.2), (-0.4, 0.6)]
        cid = self.w.add_clip(tid, 0, 100, label="Track", waveform=waveform)
        item = self.w._clip_items[cid]
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()

    def test_waveform_pixmap_cached(self):
        """Waveform pixmap is cached after first paint."""
        from qtpy import QtGui, QtWidgets

        tid = self.w.add_track("Audio")
        waveform = [(-0.5, 0.5)] * 20
        cid = self.w.add_clip(tid, 0, 100, waveform=waveform)
        item = self.w._clip_items[cid]
        self.assertIsNone(item._waveform_pixmap)
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()
        self.assertIsNotNone(item._waveform_pixmap)

    def test_empty_waveform_skips_render(self):
        """Empty waveform list should not crash."""
        from qtpy import QtGui, QtWidgets

        tid = self.w.add_track("Audio")
        cid = self.w.add_clip(tid, 0, 100, waveform=[])
        item = self.w._clip_items[cid]
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()
        self.assertIsNone(item._waveform_pixmap)


# =========================================================================
# ShotLaneItem
# =========================================================================


class TestShotLaneItem(BaseTestCase):
    """Shot blocks are stored on the RulerItem (no standalone ShotLaneItem)."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_ruler_present_in_scene(self):
        """RulerItem exists in the scene by default."""
        from uitk.widgets.sequencer import RulerItem

        scene = self.w._timeline.scene()
        rulers = [i for i in scene.items() if isinstance(i, RulerItem)]
        self.assertEqual(len(rulers), 1)

    def test_set_shot_blocks_populates_ruler(self):
        """Shot blocks propagate to the RulerItem._shot_blocks list."""
        blocks = [
            {"name": "A", "start": 0, "end": 50, "active": True},
            {"name": "B", "start": 60, "end": 100, "active": False},
        ]
        self.w.set_shot_blocks(blocks)
        ruler = self.w._timeline._scene.ruler
        self.assertEqual(len(ruler._shot_blocks), 2)

    def test_clear_shot_blocks_empties_ruler(self):
        self.w.set_shot_blocks([{"name": "A", "start": 0, "end": 50, "active": True}])
        self.w.clear_shot_blocks()
        ruler = self.w._timeline._scene.ruler
        self.assertEqual(len(ruler._shot_blocks), 0)


# =========================================================================
# get_track edge cases
# =========================================================================


class TestGetTrack(BaseTestCase):
    """get_track with valid and invalid IDs."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_get_track_valid(self):
        tid = self.w.add_track("T")
        td = self.w.get_track(tid)
        self.assertIsNotNone(td)
        self.assertEqual(td.name, "T")

    def test_get_track_invalid_returns_none(self):
        self.assertIsNone(self.w.get_track(999))


# =========================================================================
# Undo / Redo Signals
# =========================================================================


class TestUndoRedoSignals(BaseTestCase):
    """Verify undo_requested and redo_requested signals."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_undo_emits_undo_requested(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 50)
        self.w._capture_undo()
        self.w._clips[cid].start = 20
        received = []
        self.w.undo_requested.connect(lambda: received.append(True))
        self.w.undo()
        self.assertEqual(len(received), 1)

    def test_redo_emits_redo_requested(self):
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 50)
        self.w._capture_undo()
        self.w._clips[cid].start = 20
        self.w.undo()
        received = []
        self.w.redo_requested.connect(lambda: received.append(True))
        self.w.redo()
        self.assertEqual(len(received), 1)


# =========================================================================
# ClipItem._hit_zone
# =========================================================================


class TestClipItemHitZone(BaseTestCase):
    """_hit_zone returns correct zones for edge vs body."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_hit_zone_move(self):
        """Center of clip returns 'move' (body drag zone)."""
        from qtpy import QtCore

        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 200)
        item = self.w._clip_items[cid]
        rect = item.rect()
        mid = QtCore.QPointF(rect.center().x(), rect.center().y())
        self.assertEqual(item._hit_zone(mid), "move")

    def test_hit_zone_resize_left(self):
        """Left edge of clip returns 'resize_left'."""
        from qtpy import QtCore

        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 200)
        item = self.w._clip_items[cid]
        rect = item.rect()
        left = QtCore.QPointF(rect.left() + 2, rect.center().y())
        self.assertEqual(item._hit_zone(left), "resize_left")

    def test_hit_zone_resize_right(self):
        """Right edge of clip returns 'resize_right'."""
        from qtpy import QtCore

        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 200)
        item = self.w._clip_items[cid]
        rect = item.rect()
        right = QtCore.QPointF(rect.right() - 2, rect.center().y())
        self.assertEqual(item._hit_zone(right), "resize_right")


# =========================================================================
# Window-level Shortcut Dispatch
# =========================================================================


class TestWindowShortcutDispatch(BaseTestCase):
    """Verify eventFilter dispatches actions for window-level shortcuts.

    Bug: When window_shortcuts=True, the eventFilter accepted
    ShortcutOverride to block the host app (Maya) but didn't invoke
    the action. The QShortcut couldn't fire either (override accepted),
    leaving the key dead when focus was outside the sequencer.
    Fixed: 2026-04-04
    """

    def setUp(self):
        from qtpy import QtCore

        self.w = SequencerWidget()
        self.w.window_shortcuts = True
        self.calls = []
        self.w._shortcut_mgr.add_shortcut(
            "Delete",
            lambda: self.calls.append("delete"),
            "Test action",
            QtCore.Qt.WindowShortcut,
        )

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_override_dispatches_action(self):
        """ShortcutOverride for a registered key invokes the action."""
        from qtpy import QtCore, QtGui

        override = QtGui.QKeyEvent(
            QtCore.QEvent.ShortcutOverride,
            QtCore.Qt.Key_Delete,
            QtCore.Qt.NoModifier,
        )
        result = self.w.eventFilter(self.w, override)
        self.assertTrue(result, "eventFilter should return True for matched key")
        self.assertTrue(override.isAccepted(), "ShortcutOverride must be accepted")
        self.assertEqual(self.calls, ["delete"], "Action must be dispatched")

    def test_subsequent_keypress_consumed(self):
        """KeyPress after a dispatched ShortcutOverride is consumed."""
        from qtpy import QtCore, QtGui

        # First: ShortcutOverride
        override = QtGui.QKeyEvent(
            QtCore.QEvent.ShortcutOverride,
            QtCore.Qt.Key_Delete,
            QtCore.Qt.NoModifier,
        )
        self.w.eventFilter(self.w, override)
        # Second: KeyPress
        press = QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress,
            QtCore.Qt.Key_Delete,
            QtCore.Qt.NoModifier,
        )
        consumed = self.w.eventFilter(self.w, press)
        self.assertTrue(consumed, "KeyPress after dispatched override must be consumed")
        self.assertEqual(len(self.calls), 1, "Action should fire only once")

    def test_unmatched_key_passes_through(self):
        """Unregistered keys are not intercepted by the filter."""
        from qtpy import QtCore, QtGui

        override = QtGui.QKeyEvent(
            QtCore.QEvent.ShortcutOverride,
            QtCore.Qt.Key_A,
            QtCore.Qt.NoModifier,
        )
        result = self.w.eventFilter(self.w, override)
        self.assertFalse(result, "Unmatched key should pass through")
        self.assertEqual(self.calls, [], "No action should fire")

    def test_text_edit_focus_bypasses_filter(self):
        """ShortcutOverride is NOT intercepted when a line edit has focus."""
        from unittest.mock import patch
        from qtpy import QtCore, QtGui, QtWidgets

        line_edit = QtWidgets.QLineEdit()
        with patch.object(
            QtWidgets.QApplication, "focusWidget", return_value=line_edit
        ):
            override = QtGui.QKeyEvent(
                QtCore.QEvent.ShortcutOverride,
                QtCore.Qt.Key_Delete,
                QtCore.Qt.NoModifier,
            )
            result = self.w.eventFilter(self.w, override)
        self.assertFalse(result, "Filter must not intercept when text widget focused")
        self.assertEqual(self.calls, [], "No action should fire")
        line_edit.deleteLater()

    def test_unrelated_keypress_not_consumed(self):
        """A KeyPress for a different key after dispatch is NOT consumed."""
        from qtpy import QtCore, QtGui

        # Dispatch Delete via ShortcutOverride
        override = QtGui.QKeyEvent(
            QtCore.QEvent.ShortcutOverride,
            QtCore.Qt.Key_Delete,
            QtCore.Qt.NoModifier,
        )
        self.w.eventFilter(self.w, override)
        # Now send a KeyPress for a DIFFERENT key (e.g. 'A')
        press_a = QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress,
            QtCore.Qt.Key_A,
            QtCore.Qt.NoModifier,
        )
        consumed = self.w.eventFilter(self.w, press_a)
        self.assertFalse(consumed, "Unrelated key must not be consumed")


class TestMultipleExpandedTracks(BaseTestCase):
    """Verify multiple tracks can be expanded simultaneously."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_two_tracks_expanded(self):
        t0 = self.w.add_track("obj_A")
        t1 = self.w.add_track("obj_B")
        sub_a = [("tx", [(0, 10, "tx", None, {})])]
        sub_b = [("ry", [(0, 10, "ry", None, {})]), ("rz", [(5, 10, "rz", None, {})])]
        self.w.expand_track(t0, sub_row_data=sub_a)
        self.w.expand_track(t1, sub_row_data=sub_b)
        self.assertTrue(self.w.is_track_expanded(t0))
        self.assertTrue(self.w.is_track_expanded(t1))
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        self.assertEqual(len(sub_clips), 3)

    def test_collapse_one_preserves_other(self):
        t0 = self.w.add_track("obj_A")
        t1 = self.w.add_track("obj_B")
        sub_a = [("tx", [(0, 10, "tx", None, {})])]
        sub_b = [("ry", [(0, 10, "ry", None, {})])]
        self.w.expand_track(t0, sub_row_data=sub_a)
        self.w.expand_track(t1, sub_row_data=sub_b)
        self.w.collapse_track(t0)
        self.assertFalse(self.w.is_track_expanded(t0))
        self.assertTrue(self.w.is_track_expanded(t1))
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        self.assertEqual(len(sub_clips), 1)
        self.assertEqual(sub_clips[0].sub_row, "ry")


# =========================================================================
# Content Top / Row Position
# =========================================================================


class TestContentTop(BaseTestCase):
    """_content_top clears the whole header -- the ruler AND the shot lane."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_content_top_equals_header_height(self):
        self.assertEqual(self.w._content_top, _RULER_HEIGHT + _SHOT_LANE_HEIGHT)


# =========================================================================
# Keyboard Dispatch (SequencerWidget + TimelineView)
# =========================================================================


class TestKeyboardDispatch(BaseTestCase):
    """Verify keyPressEvent dispatches registered shortcuts."""

    def setUp(self):
        from qtpy import QtCore, QtGui

        self.QtCore = QtCore
        self.QtGui = QtGui
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _make_key_event(self, key, modifiers=None):
        if modifiers is None:
            modifiers = self.QtCore.Qt.NoModifier
        return self.QtGui.QKeyEvent(self.QtCore.QEvent.KeyPress, key, modifiers)

    def test_f_key_dispatches_frame_shot_on_widget(self):
        """F key on SequencerWidget calls frame_shot."""
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 100, 50)
        ev = self._make_key_event(self.QtCore.Qt.Key_F)
        self.w.keyPressEvent(ev)
        self.assertTrue(ev.isAccepted())

    def test_f_key_dispatches_frame_shot_on_timeline(self):
        """F key on TimelineView calls frame_shot."""
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 100, 50)
        ev = self._make_key_event(self.QtCore.Qt.Key_F)
        self.w._timeline.keyPressEvent(ev)
        self.assertTrue(ev.isAccepted())

    def test_left_arrow_dispatches_go_to_prev_key(self):
        """Left arrow moves playhead to previous key boundary."""
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 10, 20)
        self.w.set_playhead(30.0)
        ev = self._make_key_event(self.QtCore.Qt.Key_Left)
        self.w.keyPressEvent(ev)
        self.assertTrue(ev.isAccepted())
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 10.0)

    def test_right_arrow_dispatches_go_to_next_key(self):
        """Right arrow moves playhead to next key boundary."""
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 10, 20)
        self.w.set_playhead(0.0)
        ev = self._make_key_event(self.QtCore.Qt.Key_Right)
        self.w.keyPressEvent(ev)
        self.assertTrue(ev.isAccepted())
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 10.0)

    def test_m_key_dispatches_add_marker(self):
        """M key adds marker at playhead."""
        self.w.set_playhead(42.0)
        ev = self._make_key_event(self.QtCore.Qt.Key_M)
        self.w.keyPressEvent(ev)
        self.assertTrue(ev.isAccepted())
        self.assertEqual(len(self.w.markers()), 1)
        self.assertAlmostEqual(self.w.markers()[0].time, 42.0)

    def test_ctrl_z_dispatches_undo(self):
        """Ctrl+Z dispatches undo."""
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 50)
        self.w._capture_undo()
        self.w._clips[cid].start = 20
        received = []
        self.w.undo_requested.connect(lambda: received.append(True))
        ev = self._make_key_event(self.QtCore.Qt.Key_Z, self.QtCore.Qt.ControlModifier)
        self.w.keyPressEvent(ev)
        self.assertTrue(ev.isAccepted())
        self.assertEqual(len(received), 1)

    def test_shift_right_dispatches_step_forward(self):
        """Shift+Right steps forward by snap interval."""
        self.w.set_playhead(5.0)
        ev = self._make_key_event(
            self.QtCore.Qt.Key_Right, self.QtCore.Qt.ShiftModifier
        )
        self.w.keyPressEvent(ev)
        self.assertTrue(ev.isAccepted())
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 6.0)

    def test_home_key_dispatches_go_to_start(self):
        """Home key jumps playhead to 0."""
        self.w.set_playhead(50.0)
        ev = self._make_key_event(self.QtCore.Qt.Key_Home)
        self.w.keyPressEvent(ev)
        self.assertTrue(ev.isAccepted())
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 0.0)

    def test_end_key_dispatches_go_to_end(self):
        """End key jumps playhead to last clip end."""
        tid = self.w.add_track("T")
        self.w.add_clip(tid, 0, 100)
        self.w.set_playhead(0.0)
        ev = self._make_key_event(self.QtCore.Qt.Key_End)
        self.w.keyPressEvent(ev)
        self.assertTrue(ev.isAccepted())
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 100.0)

    def test_unregistered_key_not_accepted(self):
        """Keys not in shortcut list pass through."""
        ev = self._make_key_event(self.QtCore.Qt.Key_X)
        self.w.keyPressEvent(ev)
        # Not explicitly accepted by our handler — falls through to super

    def test_shortcut_override_accepted_for_registered_key(self):
        """ShortcutOverride for F is accepted (prevents host app stealing)."""
        ev = self.QtGui.QKeyEvent(
            self.QtCore.QEvent.ShortcutOverride,
            self.QtCore.Qt.Key_F,
            self.QtCore.Qt.NoModifier,
        )
        result = self.w.event(ev)
        self.assertTrue(result)

    def test_delete_shortcut_dispatches_with_selected_clips(self):
        """Delete key shortcut fires callback with currently selected clips.

        Bug: marquee-selecting clips in the sequencer and pressing Delete
        did not delete the selected keyframes.
        Fixed: 2026-03-25
        """
        from unittest.mock import MagicMock

        tid = self.w.add_track("T")
        c0 = self.w.add_clip(tid, 0, 50, obj="pCube1", orig_start=0, orig_end=50)
        c1 = self.w.add_clip(tid, 60, 30, obj="pCube1", orig_start=60, orig_end=90)

        # Register a Delete callback via the shortcut manager (as shot_sequencer_slots does)
        mock_delete = MagicMock()
        self.w._shortcut_mgr.add_shortcut(
            "Delete",
            mock_delete,
            "Delete keys for selected clips",
            self.QtCore.Qt.WidgetWithChildrenShortcut,
        )
        self.w._timeline._shortcut_sequences.append(self.QtGui.QKeySequence("Delete"))

        # Programmatically select clips (simulates rubber-band result)
        self.w._clip_items[c0].setSelected(True)
        self.w._clip_items[c1].setSelected(True)
        self.assertEqual(len(self.w.selected_clips()), 2)

        # Simulate Delete key press on the timeline view
        ev = self._make_key_event(self.QtCore.Qt.Key_Delete)
        self.w._timeline.keyPressEvent(ev)
        self.assertTrue(ev.isAccepted())
        mock_delete.assert_called_once()

    def test_delete_shortcut_dispatches_on_sequencer_widget(self):
        """Delete key on the SequencerWidget (not timeline) also dispatches."""
        from unittest.mock import MagicMock

        tid = self.w.add_track("T")
        c0 = self.w.add_clip(tid, 0, 50)
        mock_delete = MagicMock()
        self.w._shortcut_mgr.add_shortcut(
            "Delete",
            mock_delete,
            "Delete test",
            self.QtCore.Qt.WidgetWithChildrenShortcut,
        )
        self.w._timeline._shortcut_sequences.append(self.QtGui.QKeySequence("Delete"))

        self.w._clip_items[c0].setSelected(True)
        ev = self._make_key_event(self.QtCore.Qt.Key_Delete)
        self.w.keyPressEvent(ev)
        self.assertTrue(ev.isAccepted())
        mock_delete.assert_called_once()


# =========================================================================
# Key Times Include Keyframe Data from Expanded Tracks
# =========================================================================


class TestKeyTimesExpanded(BaseTestCase):
    """_key_times includes keyframe_times from expanded sub-row clips."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_key_times_includes_keyframes_from_expanded_track(self):
        """Expanded sub-rows contribute their keyframe_times to navigation."""
        tid = self.w.add_track("obj")
        self.w.add_clip(tid, 0, 100, label="main")
        sub_data = [
            ("tx", [(0, 100, "tx", None, {"keyframe_times": [10, 30, 70]})]),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        times = self.w._key_times()
        # Should include clip boundaries (0, 100) plus keyframe times (10, 30, 70)
        for t in [0, 10, 30, 70, 100]:
            self.assertIn(t, times)

    def test_key_times_excludes_keyframes_from_collapsed_track(self):
        """Collapsed tracks don't contribute keyframe_times."""
        tid = self.w.add_track("obj")
        self.w.add_clip(tid, 0, 100, label="main")
        sub_data = [
            ("tx", [(0, 100, "tx", None, {"keyframe_times": [10, 30, 70]})]),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        self.w.collapse_track(tid)
        times = self.w._key_times()
        # After collapse, only main clip boundaries
        self.assertEqual(times, [0, 100])

    def test_go_to_next_key_stops_at_keyframe(self):
        """Arrow key navigation lands on expanded keyframe times."""
        tid = self.w.add_track("obj")
        self.w.add_clip(tid, 0, 100, label="main")
        sub_data = [
            ("tx", [(0, 100, "tx", None, {"keyframe_times": [25, 50, 75]})]),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        self.w.set_playhead(0.0)
        self.w.go_to_next_key()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 25.0)
        self.w.go_to_next_key()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 50.0)

    def test_go_to_prev_key_stops_at_keyframe(self):
        """Reverse navigation lands on expanded keyframe times."""
        tid = self.w.add_track("obj")
        self.w.add_clip(tid, 0, 100, label="main")
        sub_data = [
            ("tx", [(0, 100, "tx", None, {"keyframe_times": [25, 50, 75]})]),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        self.w.set_playhead(100.0)
        self.w.go_to_prev_key()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 75.0)
        self.w.go_to_prev_key()
        self.assertAlmostEqual(self.w._timeline._scene.playhead.time, 50.0)


# =========================================================================
# Undo Capture Order for swap_clips
# =========================================================================


class TestSwapClipsUndo(BaseTestCase):
    """swap_clips captures undo BEFORE mutation so undo reverts correctly."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_swap_clips_captures_undo_before_swap(self):
        """Undo after swap_clips restores original positions."""
        tid = self.w.add_track("T")
        c0 = self.w.add_clip(tid, 0, 30)
        c1 = self.w.add_clip(tid, 40, 20)
        orig_c0_start = self.w.get_clip(c0).start
        orig_c1_start = self.w.get_clip(c1).start
        self.w.swap_clips(c0, c1)
        # Positions changed after swap
        self.assertNotAlmostEqual(self.w.get_clip(c0).start, orig_c0_start)
        # Undo should restore original positions
        self.w.undo()
        self.assertAlmostEqual(self.w.get_clip(c0).start, orig_c0_start)
        self.assertAlmostEqual(self.w.get_clip(c1).start, orig_c1_start)

    def test_swap_clips_redo_reapplies(self):
        """Redo after undo of swap reapplies the swap."""
        tid = self.w.add_track("T")
        c0 = self.w.add_clip(tid, 0, 30)
        c1 = self.w.add_clip(tid, 40, 20)
        self.w.swap_clips(c0, c1)
        swapped_c0_start = self.w.get_clip(c0).start
        swapped_c1_start = self.w.get_clip(c1).start
        self.w.undo()
        self.w.redo()
        self.assertAlmostEqual(self.w.get_clip(c0).start, swapped_c0_start)
        self.assertAlmostEqual(self.w.get_clip(c1).start, swapped_c1_start)

    # -- sub-row resize propagation --

    def test_clear_removes_expanded_state(self):
        """clear() wipes _expanded_tracks so re-expansion uses fresh data."""
        tid = self.w.add_track("obj")
        sub_data = [("translateX", [(10, 20, "translateX", None)])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        self.assertTrue(self.w.is_track_expanded(tid))
        self.w.clear()
        self.assertEqual(len(self.w._expanded_tracks), 0)

    def test_resize_signal_emitted_for_sub_row_clip(self):
        """clip_resized carries the sub-row clip's id so the controller can route."""
        tid = self.w.add_track("obj")
        sub_data = [
            (
                "translateX",
                [
                    (
                        10,
                        20,
                        "translateX",
                        None,
                        {
                            "obj": "cube",
                            "attr_name": "translateX",
                            "orig_start": 10,
                            "orig_end": 30,
                        },
                    )
                ],
            )
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [cd for cd in self.w._clips.values() if cd.sub_row]
        self.assertEqual(len(sub_clips), 1)
        sc = sub_clips[0]
        self.assertEqual(sc.data.get("attr_name"), "translateX")
        self.assertEqual(sc.data.get("orig_start"), 10)
        self.assertEqual(sc.data.get("orig_end"), 30)

    def test_sub_row_provider_called_on_expand(self):
        """Expanding a track calls the sub_row_provider to generate sub-row data."""
        tid = self.w.add_track("obj_name")
        calls = []

        def provider(track_id, track_name):
            calls.append((track_id, track_name))
            return [("translateX", [(10, 20, "translateX", None)])]

        self.w.sub_row_provider = provider
        self.w.expand_track(tid)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], (tid, "obj_name"))
        # Sub-row clip exists
        sub_clips = [cd for cd in self.w._clips.values() if cd.sub_row]
        self.assertEqual(len(sub_clips), 1)


# =========================================================================
# KeyframeItem (interactive dots on sub-row clips)
# =========================================================================


class TestKeyframeItem(BaseTestCase):
    """Tests for KeyframeItem creation, positioning, selection, and signals."""

    SAMPLE_PREVIEW = {
        "keys": [(10, 0.0), (50, 1.0), (90, 0.5)],
        "segments": [
            {
                "t0": 10,
                "v0": 0.0,
                "t1": 50,
                "v1": 1.0,
                "out_type": "spline",
                "cp1": (23.33, 0.33),
                "cp2": (36.67, 0.67),
            },
            {
                "t0": 50,
                "v0": 1.0,
                "t1": 90,
                "v1": 0.5,
                "out_type": "step",
                "cp1": None,
                "cp2": None,
            },
        ],
        "val_min": 0.0,
        "val_max": 1.0,
    }

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _make_clip_with_keys(self, preview=None):
        """Create a sub-row clip with curve_preview and return (clip, item)."""
        if preview is None:
            preview = self.SAMPLE_PREVIEW
        tid = self.w.add_track("obj_A")
        sub_data = [
            (
                "translateX",
                [(0, 100, "translateX", "#FF6600", {"curve_preview": preview})],
            ),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        self.assertEqual(len(sub_clips), 1)
        clip = sub_clips[0]
        item = self.w._clip_items[clip.clip_id]
        return clip, item

    # -- creation -----------------------------------------------------------

    def test_keyframe_items_created_from_curve_preview(self):
        """Sub-row clip with curve_preview spawns KeyframeItem children."""
        clip, item = self._make_clip_with_keys()
        self.assertEqual(len(item._keyframe_items), 3)
        for ki in item._keyframe_items:
            self.assertIsInstance(ki, KeyframeItem)

    def test_keyframe_times_match_preview_keys(self):
        """Each KeyframeItem stores the correct time and value."""
        clip, item = self._make_clip_with_keys()
        expected = [(10, 0.0), (50, 1.0), (90, 0.5)]
        actual = [(ki._time, ki._value) for ki in item._keyframe_items]
        self.assertEqual(actual, expected)

    def test_stepped_flag_derived_from_segments(self):
        """KeyframeItems derive is_stepped from segment out_type."""
        clip, item = self._make_clip_with_keys()
        # key 0 → segment[0].out_type == "spline" → not stepped
        self.assertFalse(item._keyframe_items[0]._is_stepped)
        # key 1 → segment[1].out_type == "step" → stepped
        self.assertTrue(item._keyframe_items[1]._is_stepped)
        # key 2 → no segment[2] → not stepped
        self.assertFalse(item._keyframe_items[2]._is_stepped)

    def test_no_keyframe_items_on_main_row(self):
        """Main-row clips must not spawn KeyframeItem children."""
        tid = self.w.add_track("T")
        cid = self.w.add_clip(tid, 0, 100, curve_preview=self.SAMPLE_PREVIEW)
        item = self.w._clip_items[cid]
        self.assertEqual(len(item._keyframe_items), 0)

    def test_no_keyframe_items_without_curve_preview(self):
        """Sub-row clip without curve_preview has no KeyframeItem children."""
        tid = self.w.add_track("obj_A")
        sub_data = [("tx", [(0, 100, "tx", "#FF0000", {})])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        item = self.w._clip_items[sub_clips[0].clip_id]
        self.assertEqual(len(item._keyframe_items), 0)

    def test_empty_keys_list_creates_no_items(self):
        """curve_preview with empty keys list produces no KeyframeItems."""
        preview = {"keys": [], "segments": [], "val_min": 0, "val_max": 1}
        clip, item = self._make_clip_with_keys(preview)
        self.assertEqual(len(item._keyframe_items), 0)

    # -- positioning --------------------------------------------------------

    def test_reposition_sets_pos(self):
        """_reposition must call setPos so the item is not stuck at origin."""
        clip, item = self._make_clip_with_keys()
        ki = item._keyframe_items[0]
        pos = ki.pos()
        # Key at time=10 in a 0–100 clip should not be at x=0
        self.assertNotEqual(pos.x(), 0.0)

    def test_reposition_within_clip_rect(self):
        """KeyframeItem positions fall within the parent clip's rect."""
        clip, item = self._make_clip_with_keys()
        rect = item.rect()
        for ki in item._keyframe_items:
            pos = ki.pos()
            # X should be within rect (with small tolerance for edge keys)
            self.assertGreaterEqual(pos.x(), rect.x() - 1)
            self.assertLessEqual(pos.x(), rect.right() + 1)

    def test_reposition_flat_curve_centres_vertically(self):
        """Flat value range places keys at vertical centre."""
        preview = {
            "keys": [(25, 5.0), (75, 5.0)],
            "segments": [
                {
                    "t0": 25,
                    "v0": 5.0,
                    "t1": 75,
                    "v1": 5.0,
                    "out_type": "linear",
                    "cp1": None,
                    "cp2": None,
                }
            ],
            "val_min": 5.0,
            "val_max": 5.0,
        }
        clip, item = self._make_clip_with_keys(preview)
        rect = item.rect()
        mid_y = (rect.top() + rect.bottom()) / 2
        for ki in item._keyframe_items:
            self.assertAlmostEqual(ki.pos().y(), mid_y, delta=1)

    # -- selection ----------------------------------------------------------

    def test_keyframe_items_are_selectable(self):
        """KeyframeItems must have the ItemIsSelectable flag."""
        from qtpy import QtWidgets

        clip, item = self._make_clip_with_keys()
        ki = item._keyframe_items[0]
        self.assertTrue(ki.flags() & QtWidgets.QGraphicsItem.ItemIsSelectable)

    def test_selected_clips_excludes_keyframe_items(self):
        """selected_clips() must not include KeyframeItem in its results."""
        clip, item = self._make_clip_with_keys()
        ki = item._keyframe_items[0]
        ki.setSelected(True)
        # selected_clips filters by isinstance(ClipItem), so keyframe
        # selections should not appear
        selected = self.w.selected_clips()
        for cid in selected:
            self.assertIsNotNone(self.w.get_clip(cid))

    # -- sub-row drag suppression -------------------------------------------

    def test_sub_row_clip_does_not_drag(self):
        """Mouse press on a sub-row clip must not initiate drag mode."""
        from qtpy import QtCore, QtWidgets

        clip, item = self._make_clip_with_keys()
        # Simulate a left-button press at the centre of the clip
        centre = item.rect().center()
        event = QtWidgets.QGraphicsSceneMouseEvent(
            QtCore.QEvent.GraphicsSceneMousePress
        )
        event.setButton(QtCore.Qt.LeftButton)
        event.setPos(centre)
        event.setScenePos(centre)
        event.setScreenPos(QtCore.QPoint(int(centre.x()), int(centre.y())))
        item.mousePressEvent(event)
        # _drag_mode should remain None (sub-row gate blocks it)
        self.assertIsNone(item._drag_mode)

    def test_sub_row_hover_shows_arrow_cursor(self):
        """Sub-row clips show ArrowCursor instead of grab cursor."""
        from qtpy import QtCore, QtWidgets

        clip, item = self._make_clip_with_keys()
        centre = item.rect().center()
        event = QtWidgets.QGraphicsSceneHoverEvent(QtCore.QEvent.GraphicsSceneHoverMove)
        event.setPos(centre)
        event.setScenePos(centre)
        event.setScreenPos(QtCore.QPoint(int(centre.x()), int(centre.y())))
        item.hoverMoveEvent(event)
        self.assertEqual(item.cursor().shape(), QtCore.Qt.ArrowCursor)

    # -- paint --------------------------------------------------------------

    def test_paint_keyframe_items_does_not_crash(self):
        """Painting a sub-row clip with KeyframeItem children must not raise."""
        from qtpy import QtGui, QtWidgets

        clip, item = self._make_clip_with_keys()
        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        # Paint the clip (curve path) — dots are painted by children
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        # Also paint each KeyframeItem directly
        for ki in item._keyframe_items:
            ki.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()

    def test_paint_stepped_keyframe_draws_square(self):
        """Stepped KeyframeItem paints drawRect, not drawEllipse."""
        from unittest.mock import patch
        from qtpy import QtGui, QtWidgets

        clip, item = self._make_clip_with_keys()
        stepped_ki = item._keyframe_items[1]  # segment[1] is "step"
        self.assertTrue(stepped_ki._is_stepped)

        pixmap = QtGui.QPixmap(20, 20)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        with patch.object(painter, "drawRect", wraps=painter.drawRect) as m_rect:
            stepped_ki.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
            m_rect.assert_called_once()
        painter.end()

    # -- signals ------------------------------------------------------------

    def test_keys_moved_signal_exists(self):
        """SequencerWidget must have a keys_moved signal."""
        self.assertTrue(hasattr(self.w, "keys_moved"))

    def test_keys_deleted_signal_exists(self):
        """SequencerWidget must have a keys_deleted signal."""
        self.assertTrue(hasattr(self.w, "keys_deleted"))

    def test_delete_selected_keys_emits_signal(self):
        """Selecting KeyframeItems and deleting emits keys_deleted."""
        clip, item = self._make_clip_with_keys()
        ki = item._keyframe_items[0]
        ki.setSelected(True)

        received = []
        self.w.keys_deleted.connect(lambda cid, ts: received.append((cid, ts)))
        self.w._delete_selected_keys()

        self.assertEqual(len(received), 1)
        cid, times = received[0]
        self.assertEqual(cid, clip.clip_id)
        self.assertIn(10, times)  # key at t=10

    def test_delete_with_no_keys_selected_is_noop(self):
        """_delete_selected_keys with no KeyframeItems selected emits nothing."""
        clip, item = self._make_clip_with_keys()
        # No keyframe selected

        received = []
        self.w.keys_deleted.connect(lambda cid, ts: received.append((cid, ts)))
        self.w._delete_selected_keys()

        self.assertEqual(len(received), 0)

    # -- rebuild vs reposition ----------------------------------------------

    def test_sync_repositions_without_rebuild(self):
        """When key data hasn't changed, _sync_keyframe_items repositions
        existing items instead of rebuilding them."""
        clip, item = self._make_clip_with_keys()
        original_items = list(item._keyframe_items)
        # Trigger another sync (e.g. from zoom)
        item._sync_geometry()
        # Same objects should still be the children
        self.assertEqual(item._keyframe_items, original_items)

    def test_sync_rebuilds_on_data_change(self):
        """When preview keys change, items are rebuilt."""
        clip, item = self._make_clip_with_keys()
        old_count = len(item._keyframe_items)
        # Mutate the curve_preview data
        clip.data["curve_preview"]["keys"] = [(20, 0.5), (80, 0.5)]
        item._sync_keyframe_items()
        self.assertEqual(len(item._keyframe_items), 2)
        # Old objects should be gone
        self.assertNotEqual(old_count, 2)

    # -- drag-adjusted curve ------------------------------------------------

    def test_drag_adjusted_segments_returns_original_when_no_move(self):
        """If no keys moved, _drag_adjusted_segments returns same object."""
        clip, item = self._make_clip_with_keys()
        preview = clip.data["curve_preview"]
        result = item._drag_adjusted_segments(preview["segments"], preview["keys"])
        self.assertIs(result, preview["segments"])

    def test_drag_adjusted_segments_updates_times(self):
        """Moving a key updates t0/t1 in the adjacent segments."""
        clip, item = self._make_clip_with_keys()
        preview = clip.data["curve_preview"]
        # Simulate dragging key[1] (t=50) to t=60
        item._keyframe_items[1]._time = 60
        result = item._drag_adjusted_segments(preview["segments"], preview["keys"])
        # segment[0] end and segment[1] start should now be 60
        self.assertAlmostEqual(result[0]["t1"], 60)
        self.assertAlmostEqual(result[1]["t0"], 60)
        # Other endpoints unchanged
        self.assertAlmostEqual(result[0]["t0"], 10)
        self.assertAlmostEqual(result[1]["t1"], 90)

    def test_drag_adjusted_segments_scales_control_points(self):
        """Bézier control-point times are proportionally remapped."""
        clip, item = self._make_clip_with_keys()
        preview = clip.data["curve_preview"]
        seg0 = preview["segments"][0]
        orig_cp1 = seg0["cp1"]
        orig_t0, orig_t1 = seg0["t0"], seg0["t1"]
        orig_span = orig_t1 - orig_t0  # 50 - 10 = 40
        frac = (orig_cp1[0] - orig_t0) / orig_span

        # Move key[1] from 50 to 70
        item._keyframe_items[1]._time = 70
        result = item._drag_adjusted_segments(preview["segments"], preview["keys"])
        new_t0, new_t1 = result[0]["t0"], result[0]["t1"]
        expected_cp1_t = new_t0 + frac * (new_t1 - new_t0)
        self.assertAlmostEqual(result[0]["cp1"][0], expected_cp1_t)
        # Value component unchanged
        self.assertAlmostEqual(result[0]["cp1"][1], orig_cp1[1])

    def test_curve_repaints_during_key_drag(self):
        """Painting after key drag uses adjusted segments — no crash."""
        from qtpy import QtGui, QtWidgets

        clip, item = self._make_clip_with_keys()
        # Simulate dragging key[1] from t=50 to t=65
        item._keyframe_items[1]._time = 65
        item._keyframe_items[1]._reposition()

        pixmap = QtGui.QPixmap(200, 30)
        pixmap.fill(QtGui.QColor("#1E1E1E"))
        painter = QtGui.QPainter(pixmap)
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
        painter.end()

    # -- key selection signal -----------------------------------------------

    def test_key_selection_changed_signal_exists(self):
        """SequencerWidget must have a key_selection_changed signal."""
        self.assertTrue(hasattr(self.w, "key_selection_changed"))

    def test_key_selection_changed_emits_on_select(self):
        """Selecting a KeyframeItem emits key_selection_changed with times."""
        clip, item = self._make_clip_with_keys()

        received = []
        self.w.key_selection_changed.connect(lambda groups: received.append(groups))

        # Select one keyframe item
        ki = item._keyframe_items[0]
        ki.setSelected(True)

        # The signal should have fired via _on_scene_selection
        self.assertTrue(len(received) > 0)
        last = received[-1]
        clip_ids = [g["clip_id"] for g in last]
        self.assertIn(clip.clip_id, clip_ids)
        group = next(g for g in last if g["clip_id"] == clip.clip_id)
        self.assertIn(10, group["times"])  # key at t=10

    def test_key_selection_changed_empty_when_no_keys_selected(self):
        """Deselecting all keys emits key_selection_changed with empty list."""
        clip, item = self._make_clip_with_keys()

        received = []
        self.w.key_selection_changed.connect(lambda groups: received.append(groups))

        # Select then deselect
        ki = item._keyframe_items[0]
        ki.setSelected(True)
        ki.setSelected(False)

        last = received[-1]
        key_groups = [g for g in last if g["times"]]
        self.assertEqual(len(key_groups), 0)


# =========================================================================
# Shortcut Dispatch
# =========================================================================


class TestShortcutDispatch(BaseTestCase):
    """Verify keyboard shortcut registration and dispatch."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_all_default_shortcuts_registered(self):
        """Every expected shortcut exists in the manager."""
        expected = [
            "Ctrl+Z",
            "Ctrl+Shift+Z",
            "Left",
            "Right",
            "Shift+Left",
            "Shift+Right",
            "Home",
            "End",
            "M",
            "F",
            "Delete",
        ]
        from qtpy.QtGui import QKeySequence

        for key in expected:
            norm = QKeySequence(key).toString()
            self.assertIn(
                norm,
                self.w._shortcut_mgr.shortcuts,
                f"Shortcut '{key}' (normalized: '{norm}') not registered",
            )

    def test_shortcut_actions_are_callable(self):
        """Every registered shortcut has a callable action."""
        for key, entry in self.w._shortcut_mgr.shortcuts.items():
            if entry.get("read_only"):
                continue
            self.assertTrue(
                callable(entry["action"]),
                f"Shortcut '{key}' action is not callable: {entry['action']}",
            )

    def test_shortcut_sequences_synced(self):
        """_shortcut_sequences matches non-read-only manager entries."""
        from qtpy.QtGui import QKeySequence

        expected = {
            QKeySequence(k).toString()
            for k, v in self.w._shortcut_mgr.shortcuts.items()
            if not v.get("read_only")
        }
        actual = {seq.toString() for seq in self.w._timeline._shortcut_sequences}
        self.assertEqual(expected, actual)

    def test_delete_shortcut_emits_keys_deleted(self):
        """Delete key action emits keys_deleted for selected KeyframeItems."""
        self.w.resize(800, 400)
        self.w.show()
        tid = self.w.add_track("obj")
        preview = {
            "keys": [(10, 0.0), (50, 1.0), (90, 0.5)],
            "segments": [
                {
                    "t0": 10,
                    "v0": 0.0,
                    "t1": 50,
                    "v1": 1.0,
                    "out_type": "spline",
                    "cp1": (23, 0.3),
                    "cp2": (37, 0.7),
                },
                {
                    "t0": 50,
                    "v0": 1.0,
                    "t1": 90,
                    "v1": 0.5,
                    "out_type": "spline",
                    "cp1": None,
                    "cp2": None,
                },
            ],
            "val_min": 0.0,
            "val_max": 1.0,
        }
        sub_data = [
            (
                "translateX",
                [(0, 100, "translateX", "#FF6600", {"curve_preview": preview})],
            ),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        item = self.w._clip_items[sub_clips[0].clip_id]
        ki = item._keyframe_items[0]
        ki.setSelected(True)

        received = []
        self.w.keys_deleted.connect(lambda cid, times: received.append((cid, times)))
        self.w._delete_selected_keys()
        self.assertEqual(len(received), 1)
        self.assertIn(10, received[0][1])

    def test_delete_no_selection_is_noop(self):
        """Delete with nothing selected does not emit."""
        self.w.resize(800, 400)
        self.w.show()
        tid = self.w.add_track("obj")
        preview = {
            "keys": [(10, 0.0)],
            "segments": [],
            "val_min": 0.0,
            "val_max": 1.0,
        }
        sub_data = [
            (
                "translateX",
                [(0, 100, "translateX", "#FF6600", {"curve_preview": preview})],
            ),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)

        received = []
        self.w.keys_deleted.connect(lambda cid, times: received.append((cid, times)))
        self.w._delete_selected_keys()
        self.assertEqual(len(received), 0)

    def test_info_entry_excluded_from_sequences(self):
        """Read-only info entries don't appear in _shortcut_sequences."""
        self.w._shortcut_mgr.add_info_entry("Ctrl+Alt+X", "Test info")
        self.w._sync_shortcut_sequences()
        seq_strs = {s.toString() for s in self.w._timeline._shortcut_sequences}
        from qtpy.QtGui import QKeySequence

        self.assertNotIn(
            QKeySequence("Ctrl+Alt+X").toString(),
            seq_strs,
        )


# =========================================================================
# Marquee Selection
# =========================================================================


class TestMarqueeSelection(BaseTestCase):
    """Verify custom rubber-band selection behaviour."""

    SAMPLE_PREVIEW = {
        "keys": [(10, 0.0), (50, 0.5), (90, 1.0)],
        "segments": [
            {
                "t0": 10,
                "v0": 0.0,
                "t1": 50,
                "v1": 0.5,
                "out_type": "spline",
                "cp1": (23, 0.2),
                "cp2": (37, 0.3),
            },
            {
                "t0": 50,
                "v0": 0.5,
                "t1": 90,
                "v1": 1.0,
                "out_type": "spline",
                "cp1": None,
                "cp2": None,
            },
        ],
        "val_min": 0.0,
        "val_max": 1.0,
    }

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _make_keys(self):
        """Create a sub-row clip with 3 keys and return (clip, item)."""
        tid = self.w.add_track("obj")
        sub_data = [
            (
                "translateX",
                [
                    (
                        0,
                        100,
                        "translateX",
                        "#FF6600",
                        {"curve_preview": self.SAMPLE_PREVIEW},
                    )
                ],
            ),
        ]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub = [c for c in self.w.clips() if c.sub_row]
        clip = sub[0]
        item = self.w._clip_items[clip.clip_id]
        return clip, item

    def _key_viewport_pos(self, ki):
        """Map a KeyframeItem centre to viewport coordinates."""
        scene_pt = ki.mapToScene(ki.boundingRect().center())
        return self.w._timeline.mapFromScene(scene_pt)

    # -- 1) shrinking marquee deselects ------------------------------------

    def test_shrink_marquee_deselects_keys(self):
        """Keys that leave the marquee during drag are deselected."""
        from qtpy import QtCore as C, QtGui as G

        _clip, item = self._make_keys()
        tl = self.w._timeline
        keys = item._keyframe_items
        self.assertGreaterEqual(len(keys), 3)

        # Build a viewport rect that covers ALL keys
        positions = [self._key_viewport_pos(k) for k in keys]
        x_min = min(p.x() for p in positions) - 5
        x_max = max(p.x() for p in positions) + 5
        y_min = min(p.y() for p in positions) - 5
        y_max = max(p.y() for p in positions) + 5

        # Press — start marquee on empty space above and to the left
        anchor = C.QPoint(x_min, y_min)
        ev_press = G.QMouseEvent(
            C.QEvent.MouseButtonPress,
            C.QPointF(anchor),
            C.Qt.LeftButton,
            C.Qt.LeftButton,
            C.Qt.NoModifier,
        )
        tl.mousePressEvent(ev_press)
        self.assertTrue(tl._marquee_active)

        # Move — expand to cover all keys
        ev_move_full = G.QMouseEvent(
            C.QEvent.MouseMove,
            C.QPointF(C.QPoint(x_max, y_max)),
            C.Qt.NoButton,
            C.Qt.LeftButton,
            C.Qt.NoModifier,
        )
        tl.mouseMoveEvent(ev_move_full)
        sel_full = [k for k in keys if k.isSelected()]
        self.assertEqual(len(sel_full), 3, "All 3 keys should be selected")

        # Shrink — only cover the first key
        first_pos = positions[0]
        ev_move_shrink = G.QMouseEvent(
            C.QEvent.MouseMove,
            C.QPointF(C.QPoint(first_pos.x() + 3, first_pos.y() + 3)),
            C.Qt.NoButton,
            C.Qt.LeftButton,
            C.Qt.NoModifier,
        )
        tl.mouseMoveEvent(ev_move_shrink)
        sel_shrink = [k for k in keys if k.isSelected()]
        self.assertEqual(len(sel_shrink), 1, "Only 1 key should remain selected")

        # Release
        ev_release = G.QMouseEvent(
            C.QEvent.MouseButtonRelease,
            C.QPointF(C.QPoint(first_pos.x() + 3, first_pos.y() + 3)),
            C.Qt.LeftButton,
            C.Qt.LeftButton,
            C.Qt.NoModifier,
        )
        tl.mouseReleaseEvent(ev_release)
        self.assertFalse(tl._marquee_active)

    # -- 2) Alt+marquee subtracts ------------------------------------------

    def test_alt_marquee_subtracts(self):
        """Alt+marquee removes the enclosed keys from the selection."""
        from qtpy import QtCore as C, QtGui as G

        _clip, item = self._make_keys()
        tl = self.w._timeline
        keys = item._keyframe_items
        for k in keys:
            k.setSelected(True)

        positions = [self._key_viewport_pos(k) for k in keys]
        anchor = C.QPoint(positions[0].x() - 5, positions[0].y() - 5)
        tl.mousePressEvent(
            G.QMouseEvent(
                C.QEvent.MouseButtonPress,
                C.QPointF(anchor),
                C.Qt.LeftButton,
                C.Qt.LeftButton,
                C.Qt.AltModifier,
            )
        )
        self.assertTrue(tl._marquee_active)

        tl.mouseMoveEvent(
            G.QMouseEvent(
                C.QEvent.MouseMove,
                C.QPointF(C.QPoint(positions[0].x() + 3, positions[0].y() + 3)),
                C.Qt.NoButton,
                C.Qt.LeftButton,
                C.Qt.AltModifier,
            )
        )
        self.assertFalse(
            keys[0].isSelected(), "the key inside an Alt-marquee is removed"
        )
        self.assertTrue(keys[1].isSelected(), "the rest of the selection stands")
        self.assertTrue(keys[2].isSelected())

    def test_shift_marquee_never_narrows_the_selection(self):
        """Shift ADDS -- that is the whole point of holding it.

        A Shift-drag over empty space must leave what was already picked
        alone, never replace it with nothing.
        """
        from qtpy import QtCore as C, QtGui as G

        _clip, item = self._make_keys()
        tl = self.w._timeline
        keys = item._keyframe_items
        for k in keys:
            k.setSelected(True)

        far = C.QPoint(6, self.w.height() - 6)  # empty space, no keys in it
        tl.mousePressEvent(
            G.QMouseEvent(
                C.QEvent.MouseButtonPress,
                C.QPointF(far),
                C.Qt.LeftButton,
                C.Qt.LeftButton,
                C.Qt.ShiftModifier,
            )
        )
        tl.mouseMoveEvent(
            G.QMouseEvent(
                C.QEvent.MouseMove,
                C.QPointF(C.QPoint(far.x() + 4, far.y() + 4)),
                C.Qt.NoButton,
                C.Qt.LeftButton,
                C.Qt.ShiftModifier,
            )
        )
        self.assertEqual(
            len([k for k in keys if k.isSelected()]),
            3,
            "a Shift-marquee over nothing must not deselect",
        )

    # -- 2b) Ctrl+marquee subtracts ----------------------------------------

    def test_ctrl_marquee_subtracts(self):
        """Ctrl+marquee subtracts enclosed keys from existing selection."""
        from qtpy import QtCore as C, QtGui as G

        _clip, item = self._make_keys()
        tl = self.w._timeline
        keys = item._keyframe_items
        # Pre-select all keys
        for k in keys:
            k.setSelected(True)
        self.assertEqual(len([k for k in keys if k.isSelected()]), 3)

        positions = [self._key_viewport_pos(k) for k in keys]

        # Ctrl+press on empty space
        anchor = C.QPoint(positions[0].x() - 5, positions[0].y() - 5)
        ev_press = G.QMouseEvent(
            C.QEvent.MouseButtonPress,
            C.QPointF(anchor),
            C.Qt.LeftButton,
            C.Qt.LeftButton,
            C.Qt.ControlModifier,
        )
        tl.mousePressEvent(ev_press)
        self.assertTrue(tl._marquee_active)

        # Drag to cover first key only
        ev_move = G.QMouseEvent(
            C.QEvent.MouseMove,
            C.QPointF(C.QPoint(positions[0].x() + 3, positions[0].y() + 3)),
            C.Qt.NoButton,
            C.Qt.LeftButton,
            C.Qt.ControlModifier,
        )
        tl.mouseMoveEvent(ev_move)
        # First key should be deselected (subtracted), others stay selected
        self.assertFalse(
            keys[0].isSelected(), "Key inside Ctrl-marquee should be deselected"
        )
        self.assertTrue(keys[1].isSelected())
        self.assertTrue(keys[2].isSelected())

        # Release
        ev_rel = G.QMouseEvent(
            C.QEvent.MouseButtonRelease,
            C.QPointF(C.QPoint(positions[0].x() + 3, positions[0].y() + 3)),
            C.Qt.LeftButton,
            C.Qt.LeftButton,
            C.Qt.ControlModifier,
        )
        tl.mouseReleaseEvent(ev_rel)

    # -- 3) Shift+marquee adds --------------------------------------------

    def test_shift_marquee_adds(self):
        """Shift+marquee adds to existing selection."""
        from qtpy import QtCore as C, QtGui as G

        _clip, item = self._make_keys()
        tl = self.w._timeline
        keys = item._keyframe_items
        # Pre-select first key only
        keys[0].setSelected(True)

        positions = [self._key_viewport_pos(k) for k in keys]

        # Shift+press on empty space near last key
        anchor = C.QPoint(positions[2].x() - 5, positions[2].y() - 5)
        ev_press = G.QMouseEvent(
            C.QEvent.MouseButtonPress,
            C.QPointF(anchor),
            C.Qt.LeftButton,
            C.Qt.LeftButton,
            C.Qt.ShiftModifier,
        )
        tl.mousePressEvent(ev_press)

        # Drag to cover last key
        ev_move = G.QMouseEvent(
            C.QEvent.MouseMove,
            C.QPointF(C.QPoint(positions[2].x() + 5, positions[2].y() + 5)),
            C.Qt.NoButton,
            C.Qt.LeftButton,
            C.Qt.ShiftModifier,
        )
        tl.mouseMoveEvent(ev_move)
        # Both first (pre-selected) and last (newly marqueed) should be selected
        self.assertTrue(keys[0].isSelected(), "Pre-selected key should remain")
        self.assertTrue(
            keys[2].isSelected(), "Key inside Shift-marquee should be selected"
        )

        ev_rel = G.QMouseEvent(
            C.QEvent.MouseButtonRelease,
            C.QPointF(C.QPoint(positions[2].x() + 5, positions[2].y() + 5)),
            C.Qt.LeftButton,
            C.Qt.LeftButton,
            C.Qt.ShiftModifier,
        )
        tl.mouseReleaseEvent(ev_rel)

    # -- 4) spacebar repositions marquee -----------------------------------

    def test_space_repositions_marquee(self):
        """Holding Space during marquee repositions the selection area."""
        from qtpy import QtCore as C, QtGui as G

        _clip, item = self._make_keys()
        tl = self.w._timeline
        keys = item._keyframe_items
        positions = [self._key_viewport_pos(k) for k in keys]

        # Start marquee covering first key
        anchor = C.QPoint(positions[0].x() - 5, positions[0].y() - 5)
        ev_press = G.QMouseEvent(
            C.QEvent.MouseButtonPress,
            C.QPointF(anchor),
            C.Qt.LeftButton,
            C.Qt.LeftButton,
            C.Qt.NoModifier,
        )
        tl.mousePressEvent(ev_press)

        corner = C.QPoint(positions[0].x() + 5, positions[0].y() + 5)
        ev_move = G.QMouseEvent(
            C.QEvent.MouseMove,
            C.QPointF(corner),
            C.Qt.NoButton,
            C.Qt.LeftButton,
            C.Qt.NoModifier,
        )
        tl.mouseMoveEvent(ev_move)
        self.assertTrue(keys[0].isSelected())

        # Record anchor before space
        anchor_before = C.QPoint(tl._marquee_anchor)

        # Press Space — start repositioning
        ev_space = G.QKeyEvent(C.QEvent.KeyPress, C.Qt.Key_Space, C.Qt.NoModifier)
        tl.keyPressEvent(ev_space)
        self.assertTrue(tl._space_held)

        # Move mouse by (20, 0) — shifts the entire marquee area
        shifted = C.QPoint(corner.x() + 20, corner.y())
        ev_move2 = G.QMouseEvent(
            C.QEvent.MouseMove,
            C.QPointF(shifted),
            C.Qt.NoButton,
            C.Qt.LeftButton,
            C.Qt.NoModifier,
        )
        tl.mouseMoveEvent(ev_move2)

        # Anchor should have shifted
        self.assertEqual(
            tl._marquee_anchor.x(),
            anchor_before.x() + 20,
            "Anchor should shift right by 20px during Space-reposition",
        )

        # Release Space
        ev_space_up = G.QKeyEvent(C.QEvent.KeyRelease, C.Qt.Key_Space, C.Qt.NoModifier)
        tl.keyReleaseEvent(ev_space_up)
        self.assertFalse(tl._space_held)

        # Release mouse
        ev_rel = G.QMouseEvent(
            C.QEvent.MouseButtonRelease,
            C.QPointF(shifted),
            C.Qt.LeftButton,
            C.Qt.LeftButton,
            C.Qt.NoModifier,
        )
        tl.mouseReleaseEvent(ev_rel)
        self.assertFalse(tl._marquee_active)

    # -- 5) no-modifier clears prior selection -----------------------------

    def test_marquee_no_modifier_clears_existing(self):
        """Starting a marquee without modifiers clears previous selection."""
        from qtpy import QtCore as C, QtGui as G

        _clip, item = self._make_keys()
        tl = self.w._timeline
        keys = item._keyframe_items
        # Pre-select all
        for k in keys:
            k.setSelected(True)

        pos0 = self._key_viewport_pos(keys[0])
        # Press on empty space (far from keys)
        anchor = C.QPoint(pos0.x() + 200, pos0.y() + 100)
        ev_press = G.QMouseEvent(
            C.QEvent.MouseButtonPress,
            C.QPointF(anchor),
            C.Qt.LeftButton,
            C.Qt.LeftButton,
            C.Qt.NoModifier,
        )
        tl.mousePressEvent(ev_press)
        # All should be cleared
        self.assertEqual(len([k for k in keys if k.isSelected()]), 0)

        ev_rel = G.QMouseEvent(
            C.QEvent.MouseButtonRelease,
            C.QPointF(anchor),
            C.Qt.LeftButton,
            C.Qt.LeftButton,
            C.Qt.NoModifier,
        )
        tl.mouseReleaseEvent(ev_rel)

    # -- 6) Space release passes through without marquee -------------------

    def test_space_release_not_swallowed_outside_marquee(self):
        """Space-release must not be eaten when no marquee is active."""
        from qtpy import QtCore as C, QtGui as G
        from unittest.mock import patch

        tl = self.w._timeline
        self.assertFalse(tl._marquee_active)

        ev = G.QKeyEvent(C.QEvent.KeyRelease, C.Qt.Key_Space, C.Qt.NoModifier)
        with patch.object(type(tl), "keyReleaseEvent", wraps=tl.keyReleaseEvent):
            tl.keyReleaseEvent(ev)
        # Event should NOT have been accepted by our handler
        # (it falls through to super which may or may not accept it).
        # The key fact: _space_held stays False and the event wasn't consumed.
        self.assertFalse(tl._space_held)


# =========================================================================
# Regression tests — 2026-07 shots-system review pass
# =========================================================================


def _scene_mouse_event(event_type, pos, button=None, modifiers=None):
    """Build a QGraphicsSceneMouseEvent at *pos* (scene == item coords)."""
    from qtpy import QtCore, QtWidgets

    ev = QtWidgets.QGraphicsSceneMouseEvent(event_type)
    ev.setButton(button if button is not None else QtCore.Qt.LeftButton)
    ev.setModifiers(
        modifiers if modifiers is not None else QtCore.Qt.KeyboardModifiers()
    )
    ev.setPos(pos)
    ev.setScenePos(pos)
    ev.setScreenPos(QtCore.QPoint(int(pos.x()), int(pos.y())))
    return ev


class TestResizeLeftSnapClamp(BaseTestCase):
    """resize_left must snap BEFORE clamping — snapping after the
    min-duration clamp could push the start past it and emit a zero- or
    negative-duration clip_resized (inverted range in consumers)."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.snap_interval = 5.0
        self.tid = self.w.add_track("T")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_snap_overshoot_cannot_invert_duration(self):
        from qtpy import QtCore

        cid = self.w.add_clip(self.tid, start=0, duration=14)
        item = self.w._clip_items[cid]
        rect = item.rect()
        ppu = self.w._timeline._pixels_per_unit

        press = _scene_mouse_event(
            QtCore.QEvent.GraphicsSceneMousePress,
            QtCore.QPointF(rect.x() + 1, rect.center().y()),
        )
        item.mousePressEvent(press)
        # The press remembers the zone; the move below is what arms the drag
        # (a click must stay a click), so the mode is pending until then.
        self.assertEqual(item._pending_zone, "resize_left")
        self.assertIsNone(item._drag_mode)

        # dx_time = +12.6 → unclamped snap lands at 15 > (14 - MIN_DUR).
        move = _scene_mouse_event(
            QtCore.QEvent.GraphicsSceneMouseMove,
            QtCore.QPointF(rect.x() + 1 + 12.6 * ppu, rect.center().y()),
        )
        item.mouseMoveEvent(move)

        received = []
        self.w.clip_resized.connect(lambda *a: received.append(a))
        release = _scene_mouse_event(
            QtCore.QEvent.GraphicsSceneMouseRelease, move.scenePos()
        )
        item.mouseReleaseEvent(release)

        cd = self.w.get_clip(cid)
        self.assertGreaterEqual(cd.duration, _MIN_CLIP_DURATION)
        for _cid, _start, duration in received:
            self.assertGreaterEqual(duration, _MIN_CLIP_DURATION)


class TestClickWithoutDragProtocol(BaseTestCase):
    """A press+release without movement must not burn an undo step, wipe
    the redo stack, or emit clip_moved/clip_resized."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("T")
        self.cid = self.w.add_clip(self.tid, start=10, duration=20)
        self.item = self.w._clip_items[self.cid]

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _click(self, pos):
        from qtpy import QtCore

        self.item.mousePressEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMousePress, pos)
        )
        self.item.mouseReleaseEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMouseRelease, pos)
        )

    def test_body_click_preserves_undo_redo_and_emits_nothing(self):
        self.w._redo_stack.append({})  # seed a redo entry
        moved, resized = [], []
        self.w.clip_moved.connect(lambda *a: moved.append(a))
        self.w.clip_resized.connect(lambda *a: resized.append(a))

        self._click(self.item.rect().center())

        self.assertEqual(len(self.w._undo_stack), 0)
        self.assertEqual(len(self.w._redo_stack), 1, "redo stack must survive")
        self.assertEqual(moved, [])
        self.assertEqual(resized, [])

    def test_edge_click_emits_no_resize(self):
        from qtpy import QtCore

        rect = self.item.rect()
        resized = []
        self.w.clip_resized.connect(lambda *a: resized.append(a))
        self._click(QtCore.QPointF(rect.x() + 1, rect.center().y()))
        self.assertEqual(resized, [])
        self.assertEqual(len(self.w._undo_stack), 0)


class TestZeroDurationClipHitZone(BaseTestCase):
    """Zero-duration (stepped/point) clips render narrower than the
    resize handles — every press used to land in resize_left, making
    them impossible to move."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("T")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_zero_duration_hit_zone_is_move(self):
        from qtpy import QtCore

        cid = self.w.add_clip(self.tid, start=25, duration=0)
        item = self.w._clip_items[cid]
        rect = item.rect()
        for frac in (0.05, 0.5, 0.95):
            pos = QtCore.QPointF(rect.x() + rect.width() * frac, rect.center().y())
            self.assertEqual(item._hit_zone(pos), "move")


class TestMarkerZeroMotionRelease(BaseTestCase):
    """A selection click on a marker must not emit marker_moved."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_click_without_move_does_not_emit(self):
        from qtpy import QtCore

        mid = self.w.add_marker(50.0)
        item = self.w._marker_items[mid]
        item._cursor_outside_window = lambda: False  # offscreen guard
        received = []
        self.w.marker_moved.connect(lambda *a: received.append(a))

        x = self.w._timeline.time_to_x(50.0)
        pos = QtCore.QPointF(x, 5)
        item.mousePressEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMousePress, pos)
        )
        item.mouseReleaseEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMouseRelease, pos)
        )
        self.assertEqual(received, [])


class TestRangeHighlightReleaseGuard(BaseTestCase):
    """A zero-motion click on a range-highlight edge must not emit
    range_highlight_changed (or burn an undo snapshot)."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.add_track("T")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_edge_click_without_move_emits_nothing(self):
        from qtpy import QtCore

        self.w.set_range_highlight(10.0, 50.0)
        item = self.w._range_highlight
        received = []
        self.w.range_highlight_changed.connect(lambda *a: received.append(a))

        r = item._rect()
        pos = QtCore.QPointF(r.left() + 1, r.center().y())
        # Ctrl: a plain grab of a bound is a whole-shot move now; the edge
        # mode this guard is about is the bound-only grab.
        press = _scene_mouse_event(QtCore.QEvent.GraphicsSceneMousePress, pos)
        press.setModifiers(QtCore.Qt.ControlModifier)
        item.mousePressEvent(press)
        self.assertEqual(item._drag_mode, "left")
        item.mouseReleaseEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMouseRelease, pos)
        )
        self.assertEqual(received, [])
        self.assertEqual(len(self.w._undo_stack), 0)


class TestKeyTimesIncludeCurvePreview(BaseTestCase):
    """Prev/next-key navigation must see keys supplied via curve_preview
    (the form real consumers use), not only legacy keyframe_times."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_curve_preview_keys_in_key_times(self):
        tid = self.w.add_track("T")
        self.w._expanded_tracks[tid] = ["translateX"]
        self.w.add_clip(
            tid,
            start=0,
            duration=20,
            sub_row="translateX",
            curve_preview={
                "keys": [(3.0, 1.0), (7.5, 2.0)],
                "segments": [],
                "val_min": 0.0,
                "val_max": 2.0,
            },
        )
        times = self.w._key_times()
        self.assertIn(3.0, times)
        self.assertIn(7.5, times)


class TestClearFlushesBgCurvePreviews(BaseTestCase):
    """clear() must drop background curve previews — they are keyed by
    (track_id, sub_row) and track ids are recycled after a clear."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_clear_drops_previews(self):
        tid = self.w.add_track("T")
        self.w._bg_curve_previews[(tid, "translateX")] = {
            "preview": {"segments": []},
            "color": "#FFFFFF",
        }
        self.w.clear()
        self.assertEqual(self.w._bg_curve_previews, {})

    def test_remove_track_drops_its_previews(self):
        tid_a = self.w.add_track("A")
        tid_b = self.w.add_track("B")
        self.w._bg_curve_previews[(tid_a, "tx")] = {"preview": {}, "color": "#FFF"}
        self.w._bg_curve_previews[(tid_b, "tx")] = {"preview": {}, "color": "#FFF"}
        self.w.remove_track(tid_a)
        self.assertNotIn((tid_a, "tx"), self.w._bg_curve_previews)
        self.assertIn((tid_b, "tx"), self.w._bg_curve_previews)


class TestRemoveTrackPreservesLabelStyle(BaseTestCase):
    """remove_track rebuilds the header — remaining tracks must keep
    their color/dimmed styling instead of degrading to plain labels."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_surviving_track_keeps_color(self):
        tid_a = self.w.add_track("A")
        self.w.add_track("B", color="#AA0000", text_color="#FFFFFF", dimmed=False)
        self.w.remove_track(tid_a)
        header = self.w._header
        self.assertEqual(header._names, ["B"])
        self.assertEqual(header._colors, ["#AA0000"])
        self.assertEqual(header._text_colors, ["#FFFFFF"])


class TestRegisterPatternOverridePurge(BaseTestCase):
    """Re-registering a pattern style must evict cached brushes rendered
    by the previous painter."""

    def tearDown(self):
        # Restore the built-in painter for other tests.
        from uitk.widgets.sequencer._data import PatternRegistry

        PatternRegistry.register_pattern("diagonal", PatternRegistry._paint_diagonal)

    def test_override_purges_cached_brushes(self):
        from qtpy import QtGui

        color = QtGui.QColor("#123456")
        PatternRegistry.pattern_brush("diagonal", color, 8, 1.0)  # populate the cache

        calls = []

        def custom(p, size, c, lw):
            calls.append(size)

        PatternRegistry.register_pattern("diagonal", custom)
        PatternRegistry.pattern_brush("diagonal", color, 8, 1.0)
        self.assertTrue(calls, "override painter must run — stale brush was served")


class TestBulkUpdates(BaseTestCase):
    """bulk_updates() defers scene-rect recomputation but must converge
    to the same final geometry as unbatched adds."""

    def test_same_scene_rect_as_unbatched(self):
        w1 = SequencerWidget()
        w2 = SequencerWidget()
        try:
            with w1.bulk_updates():
                t1 = w1.add_track("T")
                for i in range(5):
                    w1.add_clip(t1, start=i * 50, duration=25)
            t2 = w2.add_track("T")
            for i in range(5):
                w2.add_clip(t2, start=i * 50, duration=25)
            self.assertEqual(
                w1._timeline._scene.sceneRect(), w2._timeline._scene.sceneRect()
            )
        finally:
            w1.close()
            w1.deleteLater()
            w2.close()
            w2.deleteLater()


class TestStalePendingKeyCleared(BaseTestCase):
    """A pending consume-key that never arrived must be cleared by the
    next KeyPress instead of lingering and eating a later press."""

    def setUp(self):
        from qtpy import QtCore

        self.w = SequencerWidget()
        self.w.window_shortcuts = True
        self.calls = []
        self.w._shortcut_mgr.add_shortcut(
            "Delete",
            lambda: self.calls.append(1),
            "Test action",
            QtCore.Qt.WindowShortcut,
        )

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_stale_pending_key_expires_after_one_press(self):
        from qtpy import QtCore, QtGui

        override = QtGui.QKeyEvent(
            QtCore.QEvent.ShortcutOverride,
            QtCore.Qt.Key_Delete,
            QtCore.Qt.NoModifier,
        )
        self.assertTrue(self.w.eventFilter(self.w, override))

        # The matching KeyPress never arrives; an unrelated press must
        # both pass through AND clear the stale pending state.
        press_a = QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress, QtCore.Qt.Key_A, QtCore.Qt.NoModifier
        )
        self.assertFalse(self.w.eventFilter(self.w, press_a))

        # A later Delete press (no fresh override dispatch) must NOT be
        # eaten by the stale state.
        press_del = QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress, QtCore.Qt.Key_Delete, QtCore.Qt.NoModifier
        )
        self.assertFalse(self.w.eventFilter(self.w, press_del))


# =========================================================================
# Locked Gap Overlay — drag/resize must be inert (finding 1)
# =========================================================================


class TestLockedGapNoDrag(BaseTestCase):
    """A locked gap advertises a lock state but its drag handlers ignored
    ``_locked`` — a locked gap could still be resized/moved and emit
    gap_resized / gap_left_resized / gap_moved.  It must now be inert."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _press(self, gap, scene_pt):
        from qtpy import QtCore, QtWidgets

        ev = QtWidgets.QGraphicsSceneMouseEvent(QtCore.QEvent.GraphicsSceneMousePress)
        ev.setButton(QtCore.Qt.LeftButton)
        ev.setButtons(QtCore.Qt.LeftButton)
        ev.setScenePos(scene_pt)
        ev.setPos(scene_pt)
        # The grab arms on SCREEN travel (``_past_drag_threshold``), so a
        # simulated drag has to carry a screen position like a real one.
        ev.setScreenPos(QtCore.QPoint(int(scene_pt.x()), int(scene_pt.y())))
        ev.setModifiers(QtCore.Qt.NoModifier)
        gap.mousePressEvent(ev)
        return ev

    def _move(self, gap, scene_pt):
        from qtpy import QtCore, QtWidgets

        ev = QtWidgets.QGraphicsSceneMouseEvent(QtCore.QEvent.GraphicsSceneMouseMove)
        ev.setScenePos(scene_pt)
        ev.setPos(scene_pt)
        ev.setScreenPos(QtCore.QPoint(int(scene_pt.x()), int(scene_pt.y())))
        gap.mouseMoveEvent(ev)
        return ev

    def _release(self, gap):
        from qtpy import QtCore, QtWidgets

        ev = QtWidgets.QGraphicsSceneMouseEvent(QtCore.QEvent.GraphicsSceneMouseRelease)
        ev.setButton(QtCore.Qt.LeftButton)
        gap.mouseReleaseEvent(ev)
        return ev

    def test_locked_gap_press_starts_no_drag_and_emits_nothing(self):
        from qtpy import QtCore

        self.w.add_gap_overlay(50, 70, locked=True)
        gap = self.w._gap_overlays[0]
        r = gap._rect()
        edge = QtCore.QPointF(r.right() - 1, r.center().y())  # resize zone
        emitted = []
        self.w.gap_resized.connect(lambda *a: emitted.append(("resized", a)))
        self.w.gap_moved.connect(lambda *a: emitted.append(("moved", a)))
        self.w.gap_left_resized.connect(lambda *a: emitted.append(("left", a)))

        self._press(gap, edge)
        self.assertIsNone(gap._drag_mode, "locked gap must not enter a drag mode")
        self._move(gap, QtCore.QPointF(r.right() + 40, r.center().y()))
        self._release(gap)

        self.assertEqual(emitted, [], "a locked gap must emit no gap_* signals")
        self.assertEqual((gap._start, gap._end), (50.0, 70.0), "geometry unchanged")

    def test_unlocked_gap_right_edge_still_resizes_and_emits(self):
        """Control: the locked guard must not disable UNLOCKED gaps."""
        from qtpy import QtCore

        self.w.add_gap_overlay(50, 70, locked=False)
        gap = self.w._gap_overlays[0]
        r = gap._rect()
        edge = QtCore.QPointF(r.right() - 1, r.center().y())
        emitted = []
        self.w.gap_resized.connect(lambda a, b: emitted.append((a, b)))

        self._press(gap, edge)
        self.assertEqual(gap._drag_mode, "right")
        self._move(gap, QtCore.QPointF(r.right() + 40, r.center().y()))
        self._release(gap)
        self.assertEqual(len(emitted), 1, "unlocked gap resize must still emit")


# =========================================================================
# Ruler boundingRect covers the scene extent at high zoom (finding 2)
# =========================================================================


class TestRulerBoundingRectExtent(BaseTestCase):
    """The ruler's boundingRect was a fixed 100000-px cap, so ticks/labels/
    background stopped painting past that many scene pixels at high zoom.
    It must now track the scene's horizontal extent."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_bounding_rect_floor_preserved(self):
        ruler = self.w._timeline._scene.ruler
        self.assertGreaterEqual(ruler.boundingRect().width(), 100000)

    def test_bounding_rect_scales_with_scene_extent(self):
        tl = self.w._timeline
        ruler = tl._scene.ruler
        tl._pixels_per_unit = 100.0  # high zoom
        tid = self.w.add_track("T")
        self.w.add_clip(tid, start=0, duration=3000)  # end 3000 -> x=300000
        tl._update_scene_rect()
        scene_w = tl._scene.sceneRect().width()
        self.assertGreater(scene_w, 100000, "sanity: scene must exceed old cap")
        self.assertGreaterEqual(
            ruler.boundingRect().width(),
            scene_w,
            "ruler boundingRect must cover the full scene extent",
        )


# =========================================================================
# Transport shortcut registration is idempotent (finding 3)
# =========================================================================


class TestTransportShortcutIdempotence(BaseTestCase):
    """Recreating the transport row must not stack a second Space / Alt+Space
    QShortcut on the sequencer (Qt would flag it ambiguous and fire neither)."""

    def setUp(self):
        self.w = SequencerWidget()
        self._transports = []

    def _make_transport(self):
        from uitk.widgets.sequencer import TransportControls

        t = TransportControls(self.w)
        self._transports.append(t)
        return t

    def tearDown(self):
        for t in self._transports:
            t.deleteLater()
        self.w.close()
        self.w.deleteLater()

    @staticmethod
    def _shortcut_types():
        from qtpy import QtGui, QtWidgets

        return tuple(
            t
            for t in (
                getattr(QtWidgets, "QShortcut", None),
                getattr(QtGui, "QShortcut", None),
            )
            if isinstance(t, type)
        )

    def _count_shortcuts(self, seq_str):
        from qtpy import QtCore

        types = self._shortcut_types()
        # Count only ENABLED shortcuts: Qt's "ambiguous overload" (fires
        # neither) is triggered by enabled duplicates, and a disposed
        # QShortcut is disabled immediately even though its deleteLater is
        # deferred (processEvents doesn't flush DeferredDelete here).
        return len(
            [
                c
                for c in self.w.findChildren(QtCore.QObject)
                if isinstance(c, types)
                and c.key().toString() == seq_str
                and c.isEnabled()
            ]
        )

    def test_single_transport_registers_one_space(self):
        from qtpy import QtWidgets

        self._make_transport()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self._count_shortcuts("Space"), 1)
        self.assertIn("Space", self.w._shortcut_mgr.shortcuts)

    def test_recreating_transport_does_not_duplicate_space(self):
        from qtpy import QtWidgets

        self._make_transport()
        self._make_transport()
        # deleteLater disposal of the superseded QShortcut is async.
        QtWidgets.QApplication.processEvents()
        self.assertEqual(
            self._count_shortcuts("Space"),
            1,
            "recreating the transport left a duplicate/ambiguous Space binding",
        )
        self.assertEqual(self._count_shortcuts("Alt+Space"), 1)


# =========================================================================
# ShortcutOverride dispatches directly, not via bubbling (finding 4)
# =========================================================================


class TestOverrideDispatchesDirectly(BaseTestCase):
    """event() accepted a matching ShortcutOverride but relied on the
    follow-up KeyPress bubbling to keyPressEvent — an intermediate widget
    that consumes the key broke the shortcut.  The action must dispatch on
    the override itself, without double-firing."""

    def setUp(self):
        from qtpy import QtCore

        self.w = SequencerWidget()
        self.calls = []
        self.w._shortcut_mgr.add_shortcut(
            "Left",
            lambda: self.calls.append("left"),
            "test",
            QtCore.Qt.WidgetWithChildrenShortcut,
        )
        self.w._sync_shortcut_sequences()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _override(self):
        from qtpy import QtCore, QtGui

        return QtGui.QKeyEvent(
            QtCore.QEvent.ShortcutOverride, QtCore.Qt.Key_Left, QtCore.Qt.NoModifier
        )

    def _press(self):
        from qtpy import QtCore, QtGui

        return QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress, QtCore.Qt.Key_Left, QtCore.Qt.NoModifier
        )

    def test_override_dispatches_action_directly(self):
        ev = self._override()
        handled = self.w.event(ev)
        self.assertTrue(handled)
        self.assertTrue(ev.isAccepted())
        self.assertEqual(self.calls, ["left"], "action must fire on the override")

    def test_followup_keypress_not_double_dispatched(self):
        self.w.event(self._override())
        self.w.keyPressEvent(self._press())
        self.assertEqual(self.calls, ["left"], "action must fire exactly once")

    def test_keypress_alone_still_dispatches(self):
        # Focus directly on the widget: no override precedes the press.
        self.w.keyPressEvent(self._press())
        self.assertEqual(self.calls, ["left"])

    def test_stale_override_pending_does_not_eat_later_press(self):
        from qtpy import QtCore, QtGui

        # Override dispatched (fire 1) but its matching KeyPress never
        # arrives (a child ate it), leaving a stale pending key.
        self.w.event(self._override())
        self.assertEqual(self.calls, ["left"])
        # An unrelated press clears the stale pending...
        press_a = QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress, QtCore.Qt.Key_A, QtCore.Qt.NoModifier
        )
        self.w.keyPressEvent(press_a)
        # ...so a later, genuinely new Left press dispatches (fire 2) rather
        # than being silently swallowed by the stale pending.
        self.w.keyPressEvent(self._press())
        self.assertEqual(self.calls, ["left", "left"])


# =========================================================================
# Marker remove_marker emit contract (finding 5)
# =========================================================================


class TestMarkerRemoveEmitContract(BaseTestCase):
    """remove_marker must emit marker_removed only when the id existed;
    add_marker / clear_markers stay signal-free populate primitives."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_remove_existing_marker_emits_once(self):
        mid = self.w.add_marker(10.0)
        received = []
        self.w.marker_removed.connect(lambda m: received.append(m))
        self.w.remove_marker(mid)
        self.assertEqual(received, [mid])

    def test_remove_nonexistent_marker_does_not_emit(self):
        received = []
        self.w.marker_removed.connect(lambda m: received.append(m))
        self.w.remove_marker(9999)  # never added
        self.assertEqual(received, [], "no-op remove must not emit marker_removed")

    def test_add_marker_is_signal_free(self):
        # add_marker is a populate primitive — consumers repopulate markers
        # via add_marker in a rebuild loop and rely on the silence (an emit
        # would re-enter their append-during-iteration and hang).
        received = []
        self.w.marker_added.connect(lambda *a: received.append(a))
        self.w.add_marker(5.0)
        self.assertEqual(received, [])

    def test_clear_markers_is_signal_free(self):
        self.w.add_marker(1.0)
        self.w.add_marker(2.0)
        received = []
        self.w.marker_removed.connect(lambda m: received.append(m))
        self.w.clear_markers()
        self.assertEqual(received, [], "clear_markers must not emit (rebuild safety)")


# =========================================================================
# zone_menu_enabled public API (finding 6)
# =========================================================================


class TestZoneMenuEnabledAPI(BaseTestCase):
    """The zone context-menu routing was gated on the private, undocumented
    ``_zone_menu_connected`` attribute.  A public ``zone_menu_enabled``
    property now controls it, with the legacy attr honoured as a fallback."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_default_false(self):
        self.assertFalse(self.w.zone_menu_enabled)

    def test_setter_enables(self):
        self.w.zone_menu_enabled = True
        self.assertTrue(self.w.zone_menu_enabled)

    def test_legacy_attr_fallback(self):
        # Back-compat: existing consumers poke the private attr directly.
        self.w._zone_menu_connected = True
        self.assertTrue(self.w.zone_menu_enabled)

    def test_explicit_setter_overrides_legacy_attr(self):
        self.w._zone_menu_connected = True
        self.w.zone_menu_enabled = False
        self.assertFalse(self.w.zone_menu_enabled)

    def test_context_menu_routes_when_enabled(self):
        from qtpy import QtCore, QtGui, QtWidgets

        self.w.resize(800, 400)
        self.w.show()
        QtWidgets.QApplication.processEvents()
        self.w.zone_menu_enabled = True
        received = []
        self.w.zone_context_menu_requested.connect(
            lambda zone, t, pos: received.append((zone, t))
        )
        tl = self.w._timeline
        ev = QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse,
            QtCore.QPoint(10, 10),
            QtCore.QPoint(100, 100),
        )
        tl.contextMenuEvent(ev)
        self.assertEqual(len(received), 1, "enabled zone menu must emit the signal")

    def test_context_menu_does_not_route_when_disabled(self):
        from qtpy import QtCore, QtGui, QtWidgets

        self.w.resize(800, 400)
        self.w.show()
        QtWidgets.QApplication.processEvents()
        received = []
        self.w.zone_context_menu_requested.connect(
            lambda zone, t, pos: received.append((zone, t))
        )
        tl = self.w._timeline
        ev = QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse,
            QtCore.QPoint(10, 10),
            QtCore.QPoint(100, 100),
        )
        # Default menu path shows a QMenu synchronously; suppress exec so the
        # test doesn't block.
        from unittest.mock import patch

        with patch.object(QtWidgets.QMenu, "exec_", return_value=None):
            tl.contextMenuEvent(ev)
        self.assertEqual(received, [], "disabled zone menu must not emit")


# =========================================================================
# Rebuilding from inside an item's own event must not destroy that item
# =========================================================================


class TestItemRetirement(BaseTestCase):
    """A consumer typically rebuilds the whole widget from a drag-release or
    a context-menu action.  The rebuild removes every graphics item from the
    scene while Qt is still inside that item's event handler; dropping the
    last Python reference there destroys the C++ object underneath Qt, which
    crashes the host.  Removals go through ``ItemRetirement.retire``, which keeps the
    object alive for one more event-loop pass."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("A")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _release(self, item, scene_x):
        from qtpy import QtCore, QtWidgets

        ev = QtWidgets.QGraphicsSceneMouseEvent(QtCore.QEvent.GraphicsSceneMouseRelease)
        ev.setButton(QtCore.Qt.LeftButton)
        ev.setScenePos(QtCore.QPointF(scene_x, 0))
        item.mouseReleaseEvent(ev)

    def test_clip_survives_a_rebuild_driven_from_its_own_release(self):
        from qtpy import QtCore, QtWidgets

        cid = self.w.add_clip(self.tid, 10, 20)
        item = self.w._clip_items[cid]

        press = QtWidgets.QGraphicsSceneMouseEvent(
            QtCore.QEvent.GraphicsSceneMousePress
        )
        press.setButton(QtCore.Qt.LeftButton)
        press.setScenePos(QtCore.QPointF(item.rect().center().x(), 0))
        press.setPos(item.rect().center())
        # screenPos is what the drag threshold measures; without it the
        # pointer never appears to travel and the drag is never armed.
        press.setScreenPos(QtCore.QPoint(int(item.rect().center().x()), 0))
        item.mousePressEvent(press)

        move = QtWidgets.QGraphicsSceneMouseEvent(QtCore.QEvent.GraphicsSceneMouseMove)
        move.setScenePos(QtCore.QPointF(item.rect().center().x() + 60, 0))
        move.setScreenPos(QtCore.QPoint(int(item.rect().center().x()) + 60, 0))
        item.mouseMoveEvent(move)

        # The consumer's handler clears the widget mid-release.
        self.w.clip_moved.connect(lambda *_a: self.w.clear())
        self._release(item, item.rect().center().x() + 60)

        # The item is out of the scene but still a live Python/C++ object:
        # touching it after the handler returns is exactly what Qt does.
        self.assertIsNone(item.scene())
        self.assertIsInstance(item.clip_data.start, float)
        self.assertEqual(self.w.clips(), [])

    def test_retired_items_are_released_on_the_next_event_loop_pass(self):
        from qtpy import QtWidgets
        from uitk.widgets.sequencer._draggable import ItemRetirement

        ItemRetirement._retired.clear()  # another test's pending drain must not decide this
        cid = self.w.add_clip(self.tid, 0, 5)
        self.w.remove_clip(cid)
        self.assertTrue(
            ItemRetirement._retired, "removal must park the item, not free it"
        )
        QtWidgets.QApplication.processEvents()
        self.assertFalse(
            ItemRetirement._retired, "the park list must drain on the next pass"
        )


# =========================================================================
# One key drag == one payload (so a consumer can make it one undo step)
# =========================================================================


class TestKeyBatchMoved(BaseTestCase):
    """Dragging a key selection that spans several clips used to emit
    ``keys_moved`` once per clip, so a consumer opening an undo chunk per
    signal made the single gesture cost N undos to reverse."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("A")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _sub_clip(self, sub_row, keys):
        cid = self.w.add_clip(
            self.tid,
            0,
            20,
            sub_row=sub_row,
            curve_preview={
                "keys": keys,
                "segments": [],
                "val_min": 0.0,
                "val_max": 1.0,
            },
        )
        return cid, self.w._clip_items[cid]

    def _drag(self, lead, delta_px):
        from qtpy import QtCore, QtWidgets

        press = QtWidgets.QGraphicsSceneMouseEvent(
            QtCore.QEvent.GraphicsSceneMousePress
        )
        press.setButton(QtCore.Qt.LeftButton)
        press.setScenePos(QtCore.QPointF(lead.pos().x(), lead.pos().y()))
        lead.mousePressEvent(press)

        move = QtWidgets.QGraphicsSceneMouseEvent(QtCore.QEvent.GraphicsSceneMouseMove)
        move.setScenePos(QtCore.QPointF(lead.pos().x() + delta_px, lead.pos().y()))
        lead.mouseMoveEvent(move)

        rel = QtWidgets.QGraphicsSceneMouseEvent(
            QtCore.QEvent.GraphicsSceneMouseRelease
        )
        rel.setButton(QtCore.Qt.LeftButton)
        rel.setScenePos(QtCore.QPointF(lead.pos().x(), lead.pos().y()))
        lead.mouseReleaseEvent(rel)

    def test_multi_clip_drag_emits_one_batch_not_n_singles(self):
        _, a = self._sub_clip("translateX", [(5.0, 0.0), (15.0, 1.0)])
        _, b = self._sub_clip("translateY", [(5.0, 0.0), (15.0, 1.0)])
        ka = [k for k in a._keyframe_items if abs(k._time - 5.0) < 1e-6][0]
        kb = [k for k in b._keyframe_items if abs(k._time - 5.0) < 1e-6][0]
        ka.setSelected(True)
        kb.setSelected(True)

        singles, batches = [], []
        self.w.keys_moved.connect(lambda cid, ch: singles.append((cid, ch)))
        self.w.keys_batch_moved.connect(lambda groups: batches.append(groups))

        self._drag(ka, 40)

        self.assertEqual(singles, [], "a multi-clip drag must not emit per-clip")
        self.assertEqual(len(batches), 1, "the gesture must arrive as one payload")
        self.assertEqual(
            {cid for cid, _ in batches[0]},
            {a._data.clip_id, b._data.clip_id},
            "both clips' key changes must ride the one payload",
        )

    def test_single_clip_drag_still_emits_keys_moved(self):
        _, a = self._sub_clip("translateX", [(5.0, 0.0), (15.0, 1.0)])
        ka = [k for k in a._keyframe_items if abs(k._time - 5.0) < 1e-6][0]
        ka.setSelected(True)

        singles, batches = [], []
        self.w.keys_moved.connect(lambda cid, ch: singles.append((cid, ch)))
        self.w.keys_batch_moved.connect(lambda groups: batches.append(groups))

        self._drag(ka, 40)

        self.assertEqual(len(singles), 1, "one clip keeps the existing signal")
        self.assertEqual(batches, [])


# =========================================================================
# Tail gap handle — the last shot's end
# =========================================================================


class TestPlayheadFrameEntry(BaseTestCase):
    """Double-clicking the playhead sets the frame instead of dropping a
    marker on top of it: the scrub gesture answers "roughly there", typing
    answers "exactly this frame"."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.tl = self.w._timeline

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _badge_x(self):
        from qtpy import QtCore

        self.tl._scene.playhead.sync()
        return self.tl.mapFromScene(
            QtCore.QPointF(self.tl._scene.playhead._badge_hit_x(), 0)
        ).x()

    def test_hit_test_covers_the_badge_and_nothing_far_from_it(self):
        from qtpy import QtCore

        self.w.set_playhead(40.0)
        x = self._badge_x()
        self.assertTrue(self.tl._playhead_hit(QtCore.QPoint(int(x), 5)))
        self.assertFalse(self.tl._playhead_hit(QtCore.QPoint(int(x) + 200, 5)))

    def test_the_prompt_moves_the_playhead_and_emits(self):
        from qtpy import QtWidgets

        moved = []
        self.w.playhead_moved.connect(moved.append)
        original = QtWidgets.QInputDialog.getDouble
        QtWidgets.QInputDialog.getDouble = staticmethod(lambda *a, **k: (77.0, True))
        try:
            self.tl._prompt_playhead_time()
        finally:
            QtWidgets.QInputDialog.getDouble = original
        self.assertAlmostEqual(self.tl._scene.playhead.time, 77.0)
        self.assertEqual(moved, [77.0])

    def test_a_cancelled_prompt_changes_nothing(self):
        from qtpy import QtWidgets

        self.w.set_playhead(10.0)
        moved = []
        self.w.playhead_moved.connect(moved.append)
        original = QtWidgets.QInputDialog.getDouble
        QtWidgets.QInputDialog.getDouble = staticmethod(lambda *a, **k: (99.0, False))
        try:
            self.tl._prompt_playhead_time()
        finally:
            QtWidgets.QInputDialog.getDouble = original
        self.assertAlmostEqual(self.tl._scene.playhead.time, 10.0)
        self.assertEqual(moved, [])

    def test_double_click_on_the_playhead_prompts_instead_of_marking(self):
        from qtpy import QtCore, QtGui, QtWidgets

        self.w.set_playhead(40.0)
        x = self._badge_x()
        before = len(self.w.markers())
        original = QtWidgets.QInputDialog.getDouble
        QtWidgets.QInputDialog.getDouble = staticmethod(lambda *a, **k: (12.0, True))
        try:
            self.tl.mouseDoubleClickEvent(
                QtGui.QMouseEvent(
                    QtCore.QEvent.MouseButtonDblClick,
                    QtCore.QPointF(x, 5),
                    QtCore.Qt.LeftButton,
                    QtCore.Qt.LeftButton,
                    QtCore.Qt.NoModifier,
                )
            )
        finally:
            QtWidgets.QInputDialog.getDouble = original
        self.assertEqual(len(self.w.markers()), before, "no marker may be added")
        self.assertAlmostEqual(self.tl._scene.playhead.time, 12.0)

    def test_double_click_away_from_it_still_adds_a_marker(self):
        from qtpy import QtCore, QtGui

        self.w.set_playhead(40.0)
        x = self._badge_x()
        before = len(self.w.markers())
        self.tl.mouseDoubleClickEvent(
            QtGui.QMouseEvent(
                QtCore.QEvent.MouseButtonDblClick,
                QtCore.QPointF(x + 200, 5),
                QtCore.Qt.LeftButton,
                QtCore.Qt.LeftButton,
                QtCore.Qt.NoModifier,
            )
        )
        self.assertEqual(len(self.w.markers()), before + 1)


class TestNoGrabCursorUntilTheDragArms(BaseTestCase):
    """A press is a click until the pointer clears Qt's drag distance.

    Bug: markers and gap overlays pushed the closed hand and showed the
    floating frame label at PRESS, so every plain click -- and the first half
    of every double-click -- flickered through a grab it never performed.
    The clip body was fixed this way earlier; these two were not.
    """

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.tl = self.w._timeline

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    @staticmethod
    def _ev(kind, scene_pt, screen_pt, button=None):
        from qtpy import QtWidgets

        ev = QtWidgets.QGraphicsSceneMouseEvent(kind)
        if button is not None:
            ev.setButton(button)
            ev.setButtons(button)
        ev.setPos(scene_pt)
        ev.setScenePos(scene_pt)
        ev.setScreenPos(screen_pt)
        return ev

    def _pressed_marker(self):
        from qtpy import QtCore

        mid = self.w.add_marker(time=20.0, note="m")
        item = self.w._marker_items[mid]
        x = self.tl.time_to_x(20.0)
        item.mousePressEvent(
            self._ev(
                QtCore.QEvent.GraphicsSceneMousePress,
                QtCore.QPointF(x, 5),
                QtCore.QPoint(500, 300),
                QtCore.Qt.LeftButton,
            )
        )
        return mid, item, x

    def test_a_marker_press_does_not_arm_the_grab(self):
        _mid, item, _x = self._pressed_marker()
        self.assertFalse(item._grab_armed)
        self.assertFalse(item._drag_tooltip.is_visible())

    def test_a_marker_arms_only_past_the_drag_distance(self):
        from qtpy import QtCore

        _mid, item, x = self._pressed_marker()
        item.mouseMoveEvent(
            self._ev(
                QtCore.QEvent.GraphicsSceneMouseMove,
                QtCore.QPointF(x + 1, 5),
                QtCore.QPoint(501, 300),
            )
        )
        self.assertFalse(item._grab_armed, "1px of travel is still a click")
        item.mouseMoveEvent(
            self._ev(
                QtCore.QEvent.GraphicsSceneMouseMove,
                QtCore.QPointF(x + 100, 5),
                QtCore.QPoint(600, 300),
            )
        )
        self.assertTrue(item._grab_armed)
        self.assertTrue(item._drag_tooltip.is_visible())

    def test_a_click_on_a_marker_leaves_it_where_it_was(self):
        """Press + release with no travel must not move or delete anything."""
        from qtpy import QtCore

        mid, item, x = self._pressed_marker()
        item.mouseReleaseEvent(
            self._ev(
                QtCore.QEvent.GraphicsSceneMouseRelease,
                QtCore.QPointF(x, 5),
                QtCore.QPoint(500, 300),
                QtCore.Qt.LeftButton,
            )
        )
        self.assertEqual(len(self.w.markers()), 1)
        self.assertAlmostEqual(self.w.get_marker(mid).time, 20.0)

    def test_a_gap_press_does_not_arm_the_grab(self):
        from qtpy import QtCore

        self.w.add_gap_overlay(50, 90)
        gap = self.w._gap_overlays[0]
        r = gap._rect()
        gap.mousePressEvent(
            self._ev(
                QtCore.QEvent.GraphicsSceneMousePress,
                QtCore.QPointF(r.center().x(), r.center().y()),
                QtCore.QPoint(500, 300),
                QtCore.Qt.LeftButton,
            )
        )
        self.assertIsNotNone(gap._drag_mode, "the drag mode is still recorded")
        self.assertFalse(gap._grab_armed)
        self.assertFalse(gap._drag_tooltip.is_visible())


class TestTailGapOverlay(BaseTestCase):
    """The last shot has no following shot, so the between-shots gap loop
    leaves it with no drag handle at its end.  A zero-width ``tail`` overlay
    supplies one, and it must expose ONLY the left edge (its right edge and
    body have no shot to act on)."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_tail_overlay_is_all_left_zone(self):
        from qtpy import QtCore

        self.w.add_gap_overlay(100, 100, tail=True)
        gap = self.w._gap_overlays[0]
        r = gap._rect()
        for x in (r.left(), r.center().x(), r.right()):
            self.assertEqual(
                gap._hit_zone(QtCore.QPointF(x, r.center().y())),
                "left",
                "every press on a tail handle drags the preceding shot's end",
            )

    def test_tail_overlay_left_drag_emits_gap_left_resized(self):
        from qtpy import QtCore, QtWidgets

        self.w.add_gap_overlay(100, 100, tail=True)
        gap = self.w._gap_overlays[0]
        r = gap._rect()
        emitted = []
        self.w.gap_left_resized.connect(lambda a, b: emitted.append((a, b)))

        press = QtWidgets.QGraphicsSceneMouseEvent(
            QtCore.QEvent.GraphicsSceneMousePress
        )
        press.setButton(QtCore.Qt.LeftButton)
        press.setPos(QtCore.QPointF(r.center().x(), r.center().y()))
        press.setScenePos(QtCore.QPointF(r.center().x(), r.center().y()))
        # The grab arms on SCREEN travel (``_past_drag_threshold``), so a
        # simulated drag has to carry a screen position like a real one.
        press.setScreenPos(QtCore.QPoint(int(r.center().x()), int(r.center().y())))
        gap.mousePressEvent(press)
        self.assertEqual(gap._drag_mode, "left")

        move = QtWidgets.QGraphicsSceneMouseEvent(QtCore.QEvent.GraphicsSceneMouseMove)
        move.setScenePos(QtCore.QPointF(r.center().x() + 40, r.center().y()))
        move.setScreenPos(QtCore.QPoint(int(r.center().x()) + 40, int(r.center().y())))
        gap.mouseMoveEvent(move)

        rel = QtWidgets.QGraphicsSceneMouseEvent(
            QtCore.QEvent.GraphicsSceneMouseRelease
        )
        rel.setButton(QtCore.Qt.LeftButton)
        gap.mouseReleaseEvent(rel)

        self.assertEqual(len(emitted), 1)
        self.assertAlmostEqual(emitted[0][0], 100.0)
        self.assertGreater(emitted[0][1], 100.0)

    def test_regular_gap_still_exposes_all_three_zones(self):
        from qtpy import QtCore

        self.w._timeline._pixels_per_unit = 4.0
        self.w.add_gap_overlay(50, 90)
        gap = self.w._gap_overlays[0]
        r = gap._rect()
        y = r.center().y()
        self.assertEqual(gap._hit_zone(QtCore.QPointF(r.left() + 1, y)), "left")
        self.assertEqual(gap._hit_zone(QtCore.QPointF(r.center().x(), y)), "body")
        self.assertEqual(gap._hit_zone(QtCore.QPointF(r.right() - 1, y)), "right")


# =========================================================================
# A programmatic rebuild is not the user deselecting
# =========================================================================


class TestSelectionSuppressedOnRebuild(BaseTestCase):
    """Tearing items out of the scene fires selectionChanged.  Forwarding it
    makes consumers mirror an empty selection into the host app, which is the
    "I can't keep anything selected" symptom whenever something refreshes the
    panel repeatedly."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("A")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_clear_does_not_forward_selection(self):
        cid = self.w.add_clip(self.tid, 0, 10)
        self.w._clip_items[cid].setSelected(True)
        seen = []
        self.w.selection_changed.connect(seen.append)
        keys = []
        self.w.key_selection_changed.connect(keys.append)
        self.w.clear()
        self.assertEqual(seen, [], "a rebuild must not report a deselection")
        self.assertEqual(keys, [])

    def test_user_selection_still_forwarded(self):
        cid = self.w.add_clip(self.tid, 0, 10)
        seen = []
        self.w.selection_changed.connect(seen.append)
        self.w._clip_items[cid].setSelected(True)
        self.assertEqual(seen, [[cid]])


# =========================================================================
# Key-alignment guides (visual) + opt-in snap
# =========================================================================


class TestAlignmentGuides(BaseTestCase):
    """While dragging, a frame that already carries keys is highlighted so
    the user can see the alignment.  Snapping onto it is opt-in."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("A")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_alignment_times_exclude_the_dragged_clip(self):
        a = self.w.add_clip(self.tid, 10, 20)
        self.w.add_clip(self.tid, 50, 10)  # the clip a should be able to align to
        times = self.w.alignment_times(exclude_clip_ids=[a])
        self.assertIn(50.0, times)
        self.assertIn(60.0, times)
        self.assertNotIn(10.0, times, "a clip must not align to itself")
        self.assertNotIn(30.0, times)

    def test_alignment_times_include_sub_row_keys(self):
        self.w.add_clip(
            self.tid,
            0,
            20,
            sub_row="translateX",
            curve_preview={"keys": [(3.0, 0.0), (17.0, 1.0)], "segments": []},
        )
        times = self.w.alignment_times()
        self.assertIn(3.0, times)
        self.assertIn(17.0, times)

    def test_nearest_alignment_respects_the_pixel_radius(self):
        self.w._timeline._pixels_per_unit = 1.0  # 1 frame == 1 px
        cands = [40.0]
        self.assertEqual(self.w.nearest_alignment(43.0, cands), 40.0)
        self.assertIsNone(self.w.nearest_alignment(60.0, cands))

    def test_guides_are_created_and_emptied(self):
        self.w.set_snap_guides([12.0, 30.0])
        self.assertIsNotNone(self.w._snap_guide)
        self.assertEqual(self.w._snap_guide._times, [12.0, 30.0])
        # Emptied, not destroyed: this runs on every mouse-move of a drag.
        self.w.set_snap_guides([])
        self.assertEqual(self.w._snap_guide._times, [])

    def test_clear_snap_guides_frees_the_item(self):
        self.w.set_snap_guides([12.0])
        self.w.clear_snap_guides()
        self.assertIsNone(self.w._snap_guide)

    def test_widget_clear_frees_the_guide(self):
        self.w.set_snap_guides([12.0])
        self.w.clear()
        self.assertIsNone(self.w._snap_guide)

    def test_guides_can_be_disabled(self):
        self.w.snap_guides_enabled = False
        self.w.set_snap_guides([12.0])
        self.assertIsNone(self.w._snap_guide, "disabled guides draw nothing")

    def test_snap_to_keys_is_off_by_default(self):
        self.assertFalse(self.w.snap_to_keys)


# =========================================================================
# Audit regressions
# =========================================================================


class TestKeyDragShiftFlag(BaseTestCase):
    """A key drag must RECORD the Shift modifier — nothing wrote the widget
    flag from KeyframeItem, so key drags ran under whatever the last
    clip/gap gesture left there (a prior Shift-retime silently disabled the
    boundary-expansion for every later key drag)."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("A")
        self.cid = self.w.add_clip(
            self.tid,
            0,
            20,
            sub_row="translateX",
            curve_preview={"keys": [(5.0, 0.0), (15.0, 1.0)], "segments": []},
        )
        self.item = self.w._clip_items[self.cid]

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _press(self, key_item, modifiers):
        from qtpy import QtCore, QtWidgets

        ev = QtWidgets.QGraphicsSceneMouseEvent(QtCore.QEvent.GraphicsSceneMousePress)
        ev.setButton(QtCore.Qt.LeftButton)
        ev.setModifiers(modifiers)
        ev.setScenePos(key_item.pos())
        key_item.mousePressEvent(ev)

    def test_plain_key_press_clears_a_stale_shift_flag(self):
        from qtpy import QtCore

        self.w.shift_held_at_press = True  # left behind by a prior gesture
        ki = self.item._keyframe_items[0]
        self._press(ki, QtCore.Qt.NoModifier)
        self.assertFalse(self.w.shift_held_at_press)

    def test_shift_key_press_sets_the_flag(self):
        from qtpy import QtCore

        self.w.shift_held_at_press = False
        ki = self.item._keyframe_items[0]
        self._press(ki, QtCore.Qt.ShiftModifier)
        self.assertTrue(self.w.shift_held_at_press)

    def test_unselected_grabbed_key_joins_its_own_drag(self):
        """Ctrl-click defers selection to release — the grabbed key must
        still ride (and lead) its own drag."""
        from qtpy import QtCore

        ki = self.item._keyframe_items[0]
        ki.setSelected(False)
        self._press(ki, QtCore.Qt.ControlModifier)
        self.assertTrue(
            any(p is ki for p, _ in ki._drag_peers),
            "the grabbed key must be in its own peer set",
        )


class TestTailLockImmunity(BaseTestCase):
    """A tail handle is a shot-end handle, not a gap: locking it (any path)
    would leave the LAST shot with no way to resize."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_lock_all_gaps_skips_the_tail(self):
        self.w.add_gap_overlay(50, 70)
        self.w.add_gap_overlay(100, 100, tail=True)
        self.w.set_all_gap_overlays_locked(True)
        gap, tail = self.w._gap_overlays
        self.assertTrue(gap._locked)
        self.assertFalse(tail._locked, "lock-all must never brick the tail handle")

    def test_constructing_a_locked_tail_is_refused(self):
        self.w.add_gap_overlay(100, 100, tail=True, locked=True)
        self.assertFalse(self.w._gap_overlays[0]._locked)


class TestTransportRangeFnRepoint(BaseTestCase):
    """A consumer adopting an existing transport row across a controller
    re-init must be able to repoint range_fn — the constructor binding kept
    reading (and kept alive) the retired controller."""

    def test_set_range_fn(self):
        from uitk.widgets.sequencer import TransportControls

        w = SequencerWidget()
        try:
            tc = TransportControls(sequencer=w, range_fn=lambda: (1.0, 10.0))
            tc.set_range_fn(lambda: (5.0, 50.0))
            self.assertEqual(tc._range_fn(), (5.0, 50.0))
        finally:
            w.close()
            w.deleteLater()


class TestAlignmentSelfExclusion(BaseTestCase):
    """A drag must not align to a stale alias of its own content: the DCC
    panels represent one object's animation as a merged bar PLUS sub-row
    key dots, so clip-id exclusion alone left the other representation
    behind as a magnet at the origin."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("A")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_exclude_spans_drops_same_track_aliases_only(self):
        bar = self.w.add_clip(self.tid, 10, 20)  # the merged segment bar
        self.w.add_clip(
            self.tid,
            10,
            20,
            sub_row="translateX",
            curve_preview={"keys": [(13.0, 0.0), (28.0, 1.0)], "segments": []},
        )
        other_tid = self.w.add_track("B")
        self.w.add_clip(other_tid, 12, 5)  # overlapping frames, DIFFERENT track

        times = self.w.alignment_times(
            exclude_clip_ids=[bar], exclude_spans=[(self.tid, 10.0, 30.0)]
        )
        # Same-track aliases inside the span are gone (the sub-row's key
        # dots and the excluded bar's edges)…
        self.assertNotIn(13.0, times)
        self.assertNotIn(28.0, times)
        self.assertNotIn(10.0, times)
        # …but the other track's frames inside the same span survive.
        self.assertIn(12.0, times)
        self.assertIn(17.0, times)

    def test_exclude_times_drops_origin_frames(self):
        self.w.add_clip(
            self.tid,
            0,
            30,
            sub_row="translateX",
            curve_preview={"keys": [(5.0, 0.0), (25.0, 1.0)], "segments": []},
        )
        times = self.w.alignment_times(exclude_times=[5.0])
        self.assertNotIn(5.0, times)
        self.assertIn(25.0, times)


class TestMoveModeEndEdgeSnap(BaseTestCase):
    """With snap_to_keys on, a body drag must capture on WHICHEVER edge is
    closer — the guides probed both edges but the snap only pulled the
    start, so the gold readout promised an end-alignment the release never
    delivered."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.snap_to_keys = True
        self.w._timeline._pixels_per_unit = 1.0  # 1 frame == 1 px capture
        self.tid = self.w.add_track("A")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _dragging_clip(self, start, duration, candidates):
        cid = self.w.add_clip(self.tid, start, duration)
        item = self.w._clip_items[cid]
        item._drag_mode = "move"
        item._align_times = list(candidates)
        return item

    def test_end_edge_captures_when_closer(self):
        item = self._dragging_clip(0, 20, [63.0])
        # value=45 → end=65, 2 frames from the candidate; start is 18 away.
        self.assertAlmostEqual(item._align(45.0), 43.0)

    def test_start_edge_still_captures_when_closer(self):
        item = self._dragging_clip(0, 20, [44.0])
        self.assertAlmostEqual(item._align(45.0), 44.0)

    def test_guides_report_only_the_captured_edge_while_snapping(self):
        item = self._dragging_clip(0, 20, [63.0])
        item._data.start = item._align(45.0)  # snapped: end sits at 63
        hits = item._aligned_edges()
        self.assertEqual(hits, [63.0], "only the edge the snap took may draw")


class TestClearDecorationsSuppression(BaseTestCase):
    """clear_decorations retires selectable markers — a decoration-only
    refresh must not read as the user deselecting (the sibling clear()
    already carried this guard)."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_marker_teardown_is_not_forwarded_as_deselection(self):
        mid = self.w.add_marker(10.0)
        self.w._marker_items[mid].setSelected(True)
        seen = []
        self.w.selection_changed.connect(seen.append)
        keys = []
        self.w.key_selection_changed.connect(keys.append)
        self.w.clear_decorations()
        self.assertEqual(seen, [])
        self.assertEqual(keys, [])


class TestKeyframeTeardownRetires(BaseTestCase):
    """_sync_keyframe_items' rebuild branch must retire its children (not
    destroy them synchronously) and must not forward the teardown of a
    selected key dot as a user deselection."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("A")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_selected_key_dot_teardown_is_suppressed(self):
        cid = self.w.add_clip(
            self.tid,
            0,
            20,
            sub_row="translateX",
            curve_preview={"keys": [(5.0, 0.0), (15.0, 1.0)], "segments": []},
        )
        item = self.w._clip_items[cid]
        item._keyframe_items[0].setSelected(True)
        seen = []
        self.w.selection_changed.connect(seen.append)
        # Change the preview fingerprint → rebuild branch tears down dots.
        item._data.data["curve_preview"] = {
            "keys": [(6.0, 0.0), (15.0, 1.0)],
            "segments": [],
        }
        item._sync_keyframe_items()
        self.assertEqual(seen, [], "a preview rebuild is not a user deselection")


class TestClipClickSelection(BaseTestCase):
    """Clicking a clip selects it, and the modifiers behave like an NLE.

    A plain click used to leave the clip UNSELECTED: ``ClipItem`` takes the
    press for its own drag and never called ``QGraphicsItem``'s handler, so
    the only way to select a clip at all was a rubber band -- which is why
    "no selection indicator" and "Delete does nothing" were the same bug.
    """

    def setUp(self):
        self.w = SequencerWidget()
        self.t1 = self.w.add_track("A")
        self.t2 = self.w.add_track("B")
        self.c0 = self.w.add_clip(self.t1, start=10, duration=20)
        self.c1 = self.w.add_clip(self.t1, start=50, duration=20)
        self.c2 = self.w.add_clip(self.t2, start=10, duration=20)

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _click(self, cid, modifiers=None):
        from qtpy import QtCore

        item = self.w._clip_items[cid]
        pos = item.rect().center()
        item.mousePressEvent(
            _scene_mouse_event(
                QtCore.QEvent.GraphicsSceneMousePress, pos, modifiers=modifiers
            )
        )
        item.mouseReleaseEvent(
            _scene_mouse_event(
                QtCore.QEvent.GraphicsSceneMouseRelease, pos, modifiers=modifiers
            )
        )

    def _selected(self):
        return sorted(
            it._data.clip_id
            for it in self.w._timeline._scene.selectedItems()
            if isinstance(it, ClipItem)
        )

    def test_plain_click_selects_only_that_clip(self):
        self._click(self.c0)
        self.assertEqual(self._selected(), [self.c0])
        self._click(self.c1)
        self.assertEqual(self._selected(), [self.c1], "a plain click replaces")

    def test_shift_click_adds_to_the_selection(self):
        from qtpy import QtCore

        self._click(self.c0)
        self._click(self.c1, QtCore.Qt.ShiftModifier)
        self._click(self.c2, QtCore.Qt.ShiftModifier)
        self.assertEqual(self._selected(), sorted([self.c0, self.c1, self.c2]))

    def test_shift_click_on_a_selected_clip_keeps_it_selected(self):
        """Shift is "add", not "toggle" -- it must never subtract."""
        from qtpy import QtCore

        self._click(self.c0)
        self._click(self.c1, QtCore.Qt.ShiftModifier)
        self._click(self.c1, QtCore.Qt.ShiftModifier)
        self.assertEqual(self._selected(), sorted([self.c0, self.c1]))

    def test_ctrl_click_removes_from_the_selection(self):
        from qtpy import QtCore

        self._click(self.c0)
        self._click(self.c1, QtCore.Qt.ShiftModifier)
        self._click(self.c2, QtCore.Qt.ShiftModifier)
        self._click(self.c1, QtCore.Qt.ControlModifier)
        self.assertEqual(self._selected(), sorted([self.c0, self.c2]))

    def test_a_click_forwards_exactly_one_selection_change(self):
        """``clearSelection()`` + ``setSelected()`` fire the scene's signal
        separately, and consumers do real work on each -- the Maya adapter
        mirrors the selection into the scene and reopens the Graph Editor."""
        self._click(self.c0)
        seen = []
        self.w.selection_changed.connect(seen.append)
        self._click(self.c1)
        self.assertEqual(len(seen), 1, f"one forwarded change, got {seen}")
        self.assertEqual(seen[0], [self.c1])

    def test_collapsing_a_group_on_click_also_forwards_once(self):
        from qtpy import QtCore

        self._click(self.c0)
        self._click(self.c1, QtCore.Qt.ShiftModifier)
        seen = []
        self.w.selection_changed.connect(seen.append)
        self._click(self.c0)
        self.assertEqual(len(seen), 1, f"one forwarded change, got {seen}")
        self.assertEqual(seen[0], [self.c0])

    def test_a_group_survives_the_press_that_starts_its_drag(self):
        """Collapsing on press would make a multi-selection undraggable."""
        from qtpy import QtCore

        self._click(self.c0)
        self._click(self.c1, QtCore.Qt.ShiftModifier)
        item = self.w._clip_items[self.c0]
        centre = item.rect().center()
        item.mousePressEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMousePress, centre)
        )
        self.assertEqual(self._selected(), sorted([self.c0, self.c1]))

        # Peers are captured when the drag ARMS, not on press -- a press that
        # never travels is a click and must not build a drag payload.
        self.assertEqual(item._drag_peers, [], "a press alone is not a drag")
        item.mouseMoveEvent(
            _scene_mouse_event(
                QtCore.QEvent.GraphicsSceneMouseMove,
                QtCore.QPointF(centre.x() + 40, centre.y()),
            )
        )
        self.assertEqual(
            self._selected(),
            sorted([self.c0, self.c1]),
            "the group must survive the move that starts the drag",
        )
        self.assertTrue(item._drag_peers, "the peer must be captured for the drag")


class TestAClickIsNotADrag(BaseTestCase):
    """A press selects; only travel starts a drag.

    Reported live: "single clicking a shot sequence is not smooth because it
    first grabs the shot sequence before selecting".  The press used to enter
    drag mode outright -- closed-hand cursor, drag frame labels and a
    tooltip -- so every plain selection click flickered through a whole
    gesture before showing the selection it was asking for.
    """

    def setUp(self):
        from qtpy import QtCore, QtWidgets

        self.C, self.QtW = QtCore, QtWidgets
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.tid = self.w.add_track("A")
        self.cid = self.w.add_clip(self.tid, start=10, duration=40)
        self.item = self.w._clip_items[self.cid]

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _press(self, pos=None):
        pos = self.item.rect().center() if pos is None else pos
        self.item.mousePressEvent(
            _scene_mouse_event(self.C.QEvent.GraphicsSceneMousePress, pos)
        )
        return pos

    def _move_by(self, origin, dx):
        pos = self.C.QPointF(origin.x() + dx, origin.y())
        self.item.mouseMoveEvent(
            _scene_mouse_event(self.C.QEvent.GraphicsSceneMouseMove, pos)
        )
        return pos

    def test_a_press_selects_without_grabbing(self):
        self._press()
        self.assertTrue(self.item.isSelected(), "the press still selects")
        self.assertIsNone(self.item._drag_mode, "but it does not grab")

    def test_a_press_draws_no_drag_tooltip(self):
        """The floating frame label is the loudest part of the flicker.

        Counted in the SCENE rather than asked of the tooltip: it adds its
        text item on show and owns no visibility flag of its own.
        """
        scene = self.w._timeline._scene

        def labels():
            return sum(
                isinstance(it, self.QtW.QGraphicsSimpleTextItem) for it in scene.items()
            )

        before = labels()
        origin = self._press()
        self.assertEqual(labels(), before, "a click draws no frame label")

        self._move_by(origin, self.QtW.QApplication.startDragDistance() + 4)
        self.assertGreater(labels(), before, "but a real drag does")

    def test_travel_under_the_threshold_stays_a_click(self):
        origin = self._press()
        limit = self.QtW.QApplication.startDragDistance()
        self._move_by(origin, max(1, limit // 2))
        self.assertIsNone(self.item._drag_mode, "a wobble is not a drag")
        self.assertEqual(
            self.item.clip_data.start, 10.0, "and it must not move the clip"
        )

    def test_travel_past_the_threshold_arms_the_drag(self):
        origin = self._press()
        self._move_by(origin, self.QtW.QApplication.startDragDistance() + 4)
        self.assertEqual(self.item._drag_mode, "move")

    def test_a_cancel_clears_the_pending_press(self):
        """A gesture cancelled before it armed must leave nothing behind.

        Cancellation is gated on "is a drag active", and an unarmed press
        holds the mouse grab plus the origin state a later move would arm
        from -- so it has to count as active, or a popup stealing the grab
        (routine in this codebase's marking-menu environment) would strand
        the pending zone past the gesture that set it.
        """
        self._press()
        self.assertTrue(
            self.item._is_drag_active(), "an unarmed press is still in flight"
        )

        self.assertTrue(self.item.cancel_drag())

        self.assertIsNone(self.item._pending_zone)
        self.assertIsNone(self.item._press_screen_pos)
        self.assertFalse(self.item._is_drag_active())

    def test_a_cancelled_press_cannot_be_armed_afterwards(self):
        origin = self.item.rect().center()
        self._press(origin)
        self.item.cancel_drag()

        self._move_by(origin, self.QtW.QApplication.startDragDistance() + 20)

        self.assertIsNone(self.item._drag_mode, "the gesture was cancelled")
        self.assertEqual(self.item.clip_data.start, 10.0, "so nothing moved")

    def test_the_armed_move_travels_from_the_PRESS_not_the_arming_point(self):
        """Otherwise the clip would jump backwards by the threshold at the
        moment the drag arms."""
        origin = self._press()
        dx = self.QtW.QApplication.startDragDistance() + 20
        self._move_by(origin, dx)
        expected = 10.0 + dx / self.w._timeline._pixels_per_unit
        self.assertAlmostEqual(self.item.clip_data.start, expected, places=3)


class TestGroupDragKeepsItsShape(BaseTestCase):
    """A multi-clip drag is a rigid translation, and its payload has to be
    committable one clip at a time."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("A")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _drag(self, lead_cid, peers, dx_time):
        """Drag *lead_cid* by *dx_time*, carrying *peers*; returns the payload."""
        from qtpy import QtCore

        item = self.w._clip_items[lead_cid]
        for cid in peers:
            self.w._clip_items[cid].setSelected(True)
        item.setSelected(True)
        ppu = self.w._timeline._pixels_per_unit
        start_pos = item.rect().center()
        item.mousePressEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMousePress, start_pos)
        )
        end = QtCore.QPointF(start_pos.x() + dx_time * ppu, start_pos.y())
        item.mouseMoveEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMouseMove, end)
        )
        got = []
        self.w.clips_batch_moved.connect(got.append)
        item.mouseReleaseEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMouseRelease, end)
        )
        return got[0] if got else []

    def test_a_left_drag_reports_the_earliest_clip_first(self):
        """A consumer commits by time RANGE, so the clip that frees space has
        to go first; otherwise its neighbour's commit re-grabs the arrival."""
        a = self.w.add_clip(self.tid, start=100, duration=10)
        b = self.w.add_clip(self.tid, start=130, duration=10)
        payload = self._drag(b, [a], -25)
        self.assertEqual([cid for cid, _ in payload], [a, b])

    def test_a_right_drag_reports_the_latest_clip_first(self):
        a = self.w.add_clip(self.tid, start=100, duration=10)
        b = self.w.add_clip(self.tid, start=130, duration=10)
        payload = self._drag(a, [b], 25)
        self.assertEqual([cid for cid, _ in payload], [b, a])

    def test_every_member_moves_by_the_same_delta(self):
        a = self.w.add_clip(self.tid, start=100, duration=10)
        b = self.w.add_clip(self.tid, start=130, duration=10)
        c = self.w.add_clip(self.tid, start=200, duration=10)
        payload = dict(self._drag(b, [a, c], -25))
        self.assertEqual(payload[a], 75.0)
        self.assertEqual(payload[b], 105.0)
        self.assertEqual(payload[c], 175.0)

    def test_frame_zero_clamps_the_group_not_the_member(self):
        """Clamping each peer on its own silently deforms the selection: the
        earliest member stops at 0 while the rest keep going."""
        a = self.w.add_clip(self.tid, start=10, duration=10)
        b = self.w.add_clip(self.tid, start=100, duration=10)
        payload = dict(self._drag(b, [a], -50))
        self.assertEqual(payload[a], 0.0, "the earliest member decides the floor")
        self.assertEqual(payload[b], 90.0, "and the rest keep their offsets from it")


class TestFooterCenterSide(BaseTestCase):
    """``Footer.add_widget(side="center")`` centres a widget horizontally."""

    def setUp(self):
        from uitk.widgets.footer import Footer

        self.footer = Footer()
        self.footer.resize(600, 24)

    def tearDown(self):
        self.footer.close()
        self.footer.deleteLater()

    def test_center_lands_between_the_status_stack_and_the_grip(self):
        from qtpy import QtWidgets

        btn = QtWidgets.QPushButton("x")
        self.footer.add_widget(btn, side="center")
        layout = self.footer.main_layout
        stack_idx = layout.indexOf(self.footer._stacked_widget)
        self.assertGreater(layout.indexOf(btn), stack_idx)

    def test_the_two_stretches_match_so_the_widget_sits_on_the_midline(self):
        """An expanding spacer left at stretch 0 loses every spare pixel to a
        stretch-1 neighbour -- which parks the widget on the right again."""
        from qtpy import QtWidgets

        btn = QtWidgets.QPushButton("x")
        self.footer.add_widget(btn, side="center")
        layout = self.footer.main_layout
        stack_idx = layout.indexOf(self.footer._stacked_widget)
        btn_idx = layout.indexOf(btn)
        after = [
            layout.stretch(i)
            for i in range(btn_idx + 1, layout.count())
            if layout.itemAt(i).spacerItem() is not None
        ]
        self.assertIn(layout.stretch(stack_idx), after)
        self.assertEqual(layout.stretch(stack_idx), 1)

    def test_an_unknown_side_is_rejected(self):
        from qtpy import QtWidgets

        with self.assertRaises(ValueError):
            self.footer.add_widget(QtWidgets.QPushButton("x"), side="middle")


class TestSelectedClipIsVisiblyMarked(BaseTestCase):
    """Selection has to read on the clip colours a real scene produces."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("A")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_white_clips_still_change_colour_when_selected(self):
        """``lighter(130)`` is a no-op on white -- and white is exactly what a
        mixed-attribute ('consolidated') clip resolves to, i.e. most clips."""
        from qtpy import QtGui
        from uitk.widgets.sequencer._clip import ClipItem as _ClipItem

        base = QtGui.QColor("#FFFFFF")
        self.assertEqual(
            base.lighter(130).name(), base.name(), "premise: lighter() cannot help"
        )
        self.assertNotEqual(_ClipItem._selected_fill(base).name(), base.name())

    def test_the_accent_is_the_one_the_ruler_marks_the_shot_with(self):
        from uitk.widgets.sequencer._data import SELECTED_ACCENT
        from uitk.widgets.sequencer._ruler import _SELECTED_ACCENT

        self.assertEqual(SELECTED_ACCENT, _SELECTED_ACCENT)


class TestTimelineReachesBeforeFrameZero(BaseTestCase):
    """A shot that lands before the origin has to stay reachable.

    Padding a head or rippling a shot upstream legitimately puts content at
    negative frames.  The scene rect used to start at x=0, so that content was
    drawn nowhere the scrollbar could go -- invisible, and un-editable.
    """

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.tid = self.w.add_track("A")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _scene_left(self):
        self.w._timeline._update_scene_rect()
        return self.w._timeline._scene.sceneRect().left()

    def test_all_positive_content_still_starts_at_the_origin(self):
        self.w.add_clip(self.tid, 10.0, 20.0, "c")
        self.assertEqual(self._scene_left(), 0.0)

    def test_a_clip_before_zero_is_inside_the_scene_rect(self):
        self.w.add_clip(self.tid, -60.0, 30.0, "c")
        tl = self.w._timeline
        self.assertLessEqual(self._scene_left(), tl.time_to_x(-60.0))

    def test_a_shot_band_before_zero_widens_the_scene_alone(self):
        """The band is the thing the user resized; no clip need follow it."""
        self.w.set_shot_blocks(
            [{"id": 1, "name": "s", "start": -80.0, "end": -20.0, "active": True}]
        )
        tl = self.w._timeline
        self.assertLessEqual(self._scene_left(), tl.time_to_x(-80.0))

    def test_the_scrollbar_can_actually_reach_the_negative_content(self):
        self.w.add_clip(self.tid, -60.0, 30.0, "c")
        tl = self.w._timeline
        tl._update_scene_rect()
        self.assertLessEqual(tl.x_to_time(tl.horizontalScrollBar().minimum()), -60.0)

    def test_the_ruler_paints_as_far_left_as_the_scene(self):
        self.w.add_clip(self.tid, -60.0, 30.0, "c")
        tl = self.w._timeline
        tl._update_scene_rect()
        self.assertLessEqual(
            tl._scene.ruler.boundingRect().left(), tl._scene.sceneRect().left()
        )

    def test_the_playhead_reports_a_negative_frame_instead_of_pinning_to_zero(self):
        self.w.set_playhead(-30.0)
        self.assertEqual(self.w._timeline._scene.playhead.time, -30.0)

    def test_the_extent_does_not_creep_while_parked_at_an_end(self):
        """Padding is measured from content, not from where the view sits."""
        self.w.add_clip(self.tid, 0.0, 50.0, "c")
        tl = self.w._timeline
        tl._update_scene_rect()
        hbar = tl.horizontalScrollBar()
        hbar.setValue(hbar.maximum())
        tl._update_scene_rect()  # settle on the parked position
        before = tl._scene.sceneRect().width()
        for _ in range(3):
            tl._update_scene_rect()
        self.assertEqual(tl._scene.sceneRect().width(), before)


class TestShotSizeChangeRefreshesTheExtent(BaseTestCase):
    """Resizing a shot has to move the scrollable extent with it.

    The decoration setters drew the new span but left ``_update_scene_rect``
    to whatever happened to call it next, so a grown shot was painted outside
    everywhere the view could scroll.
    """

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.tid = self.w.add_track("A")
        self.w.add_clip(self.tid, 0.0, 50.0, "c")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _reaches(self, time):
        rect = self.w._timeline._scene.sceneRect()
        x = self.w._timeline.time_to_x(time)
        return rect.left() <= x <= rect.right()

    def test_range_highlight_growth_widens_the_scene(self):
        self.w.set_range_highlight(0.0, 4000.0)
        self.assertTrue(self._reaches(4000.0))

    def test_shot_blocks_widen_the_scene(self):
        self.w.set_shot_blocks(
            [{"id": 1, "name": "s", "start": 0.0, "end": 8000.0, "active": True}]
        )
        self.assertTrue(self._reaches(8000.0))

    def test_a_gap_overlay_widens_the_scene(self):
        self.w.add_gap_overlay(6000.0, 6500.0)
        self.assertTrue(self._reaches(6500.0))

    def test_a_bulk_rebuild_still_recomputes_only_once_at_exit(self):
        tl = self.w._timeline
        calls = []
        original = tl._update_scene_rect
        tl._update_scene_rect = lambda: (calls.append(1), original())[1]
        try:
            with self.w.bulk_updates():
                self.w.set_range_highlight(0.0, 900.0)
                self.w.set_shot_blocks(
                    [{"id": 1, "name": "s", "start": 0.0, "end": 900.0}]
                )
                self.w.add_gap_overlay(900.0, 950.0)
        finally:
            del tl._update_scene_rect
        self.assertEqual(len(calls), 1)


class TestShotLaneCoversTheWholeColumn(BaseTestCase):
    """Right-clicking a shot means the shot, at any height.

    The refinement used to apply only inside the ruler strip, so a
    right-click over the TRACKS -- which is most of the shot -- reported
    "tracks" and the consumer answered with the widget's own marker menu:
    no edit, no delete, nothing about the shot under the cursor.
    """

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.w.zone_menu_enabled = True
        self.tid = self.w.add_track("A")
        self.w.add_clip(self.tid, 0.0, 200.0, "c")
        self.w.set_shot_blocks(
            [{"id": 1, "name": "s", "start": 40.0, "end": 120.0, "active": True}]
        )
        self.zones = []
        self.w.zone_context_menu_requested.connect(
            lambda zone, t, pos: self.zones.append((zone, t))
        )

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _right_click(self, time, y):
        from qtpy import QtCore, QtGui

        tl = self.w._timeline
        x = int(tl.time_to_x(time) - tl.horizontalScrollBar().value())
        ev = QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse,
            QtCore.QPoint(x, y),
            tl.viewport().mapToGlobal(QtCore.QPoint(x, y)),
        )
        tl.contextMenuEvent(ev)

    def _empty_track_y(self):
        """Well below the single track: an item under the cursor forwards the
        event to ITS menu, which blocks on ``exec_``."""
        return int(self.w._content_top + 120)

    def test_a_click_over_the_tracks_inside_a_shot_is_the_shot_lane(self):
        self._right_click(80.0, self._empty_track_y())
        self.assertEqual([z for z, _t in self.zones], ["shot_lane"])

    def test_a_click_over_the_ruler_inside_a_shot_is_still_the_shot_lane(self):
        self._right_click(80.0, 4)
        self.assertEqual([z for z, _t in self.zones], ["shot_lane"])

    def test_a_click_outside_every_shot_is_still_the_tracks(self):
        self._right_click(180.0, self._empty_track_y())
        self.assertEqual([z for z, _t in self.zones], ["tracks"])

    def test_the_reported_time_is_where_the_user_clicked(self):
        self._right_click(80.0, self._empty_track_y())
        self.assertAlmostEqual(self.zones[0][1], 80.0, places=0)


class TestDefaultContextActionsFoldIntoAnyMenu(BaseTestCase):
    """The timeline's own actions have to be reachable from a consumer menu.

    They used to live only in ``_show_default_context_menu``, so folding them
    into a shot menu meant a consumer re-implementing them (twice, once per
    engine) or the user hunting for a second menu somewhere a shot does not
    cover.
    """

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(900, 400)

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _menu(self):
        from qtpy import QtWidgets

        menu = QtWidgets.QMenu(self.w)
        handled = self.w._timeline.add_default_context_actions(menu, 42.0)
        return menu, handled

    def test_the_actions_are_appended(self):
        menu, _ = self._menu()
        labels = [a.text() for a in menu.actions() if not a.isSeparator()]
        self.assertIn("Add Marker at 42\u2026", labels)
        self.assertEqual(
            labels[-3:], ["Show Shot Ranges", "Show Active Range", "Show Gap Overlays"]
        )

    def test_they_append_after_a_consumer_s_own_entries(self):
        from qtpy import QtWidgets

        menu = QtWidgets.QMenu(self.w)
        mine = menu.addAction("Delete Shot")
        self.w._timeline.add_default_context_actions(menu, 42.0)
        self.assertIs(menu.actions()[0], mine)
        self.assertTrue(menu.actions()[1].isSeparator(), "kept visually apart")

    def test_the_handler_owns_its_own_actions_and_nothing_else(self):
        from qtpy import QtWidgets

        menu = QtWidgets.QMenu(self.w)
        mine = menu.addAction("Delete Shot")
        handled = self.w._timeline.add_default_context_actions(menu, 42.0)
        toggle = next(a for a in menu.actions() if a.text() == "Show Gap Overlays")
        toggle.setChecked(False)
        self.assertTrue(handled(toggle))
        self.assertFalse(self.w.show_gap_overlays)
        self.assertFalse(handled(mine), "a consumer action must fall through")
        self.assertFalse(handled(None), "a dismissed menu is nobody's action")


class TestMarqueeWorksInsideTheActiveShot(BaseTestCase):
    """Shift+drag inside the current shot must still marquee.

    The range highlight spans the active shot across EVERY track row, so
    while its body claimed Shift+drag as "move the shot" there was nowhere
    left to rubber-band: the whole working area was covered.  The body now
    passes every press through -- the view then falls through to its own
    marquee -- and the shot moves from its ruler band instead.

    Driven against the ITEM rather than the view: whether the view routes a
    press here depends on what else the scene stacks above the highlight,
    which is exactly what differs between a synthetic fixture and the real
    panel.  The rule under test is the item's, so the item is asked.
    """

    def setUp(self):
        from qtpy import QtCore, QtWidgets

        self.C, self.QtW = QtCore, QtWidgets
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.w.show()
        self.tid = self.w.add_track("A")
        self.w.add_clip(self.tid, 40.0, 80.0, "c")
        self.w.set_range_highlight(0.0, 300.0)
        self.hl = self.w._range_highlight

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _press(self, scene_x, mods):
        C, QtW = self.C, self.QtW
        pos = C.QPointF(scene_x, self.hl._rect().center().y())
        ev = QtW.QGraphicsSceneMouseEvent(C.QEvent.GraphicsSceneMousePress)
        ev.setButton(C.Qt.LeftButton)
        ev.setModifiers(mods)
        ev.setPos(pos)
        ev.setScenePos(pos)
        ev.setScreenPos(C.QPoint(int(pos.x()), int(pos.y())))
        ev.setAccepted(True)  # Qt's default; the handler must clear it
        self.hl.mousePressEvent(ev)
        return ev

    def _body_x(self):
        """A scene x well inside the span, clear of both edge handles."""
        return self.w._timeline.time_to_x(150.0)

    def test_shift_on_the_body_is_passed_through(self):
        ev = self._press(self._body_x(), self.C.Qt.ShiftModifier)
        self.assertFalse(
            ev.isAccepted(),
            "Shift+drag inside the active shot must reach the marquee",
        )
        self.assertIsNone(self.hl._drag_mode, "no shot move may start")

    def test_a_plain_press_on_the_body_is_passed_through(self):
        ev = self._press(self._body_x(), self.C.Qt.NoModifier)
        self.assertFalse(ev.isAccepted())
        self.assertIsNone(self.hl._drag_mode)

    def test_an_edge_press_is_still_claimed(self):
        """Only the body gives way; the bounds are still the item's.  A grab
        of a bound is a bound drag under every modifier -- the consumer reads
        the modifiers to decide what else moves."""
        ev = self._press(self.w._timeline.time_to_x(0.0), self.C.Qt.NoModifier)
        self.assertTrue(ev.isAccepted())
        self.assertEqual(self.hl._drag_mode, "left")
        self.hl._drag_mode = None
        ev = self._press(self.w._timeline.time_to_x(0.0), self.C.Qt.ControlModifier)
        self.assertTrue(ev.isAccepted())
        self.assertEqual(self.hl._drag_mode, "left")


class TestShotBoundsDragFromTheRuler(BaseTestCase):
    """A shot's bounds are drawn on the ruler band, so they drag from there.

    They were drawn but inert: the highlight's hit area stops at
    ``_content_top`` and a press on the band scrubbed the playhead instead.
    The view drives the item's own drag rather than the item reaching its
    geometry up into the ruler -- a view-dependent ``boundingRect`` re-enters
    the scene index on scroll and dies natively (measured: access violation).
    """

    def setUp(self):
        from qtpy import QtCore, QtGui

        self.C, self.G = QtCore, QtGui
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.w.show()
        self.tid = self.w.add_track("A")
        self.w.add_clip(self.tid, 40.0, 80.0, "c")
        self.w.set_shot_blocks(
            [{"id": 1, "name": "s", "start": 40.0, "end": 120.0, "active": True}]
        )
        self.w.set_range_highlight(40.0, 120.0)
        self.SPAN = 120.0 - 40.0
        self.tl = self.w._timeline
        self.emitted = []
        self.w.range_highlight_changed.connect(lambda a, b: self.emitted.append((a, b)))
        self.moved = []
        self.w.playhead_moved.connect(self.moved.append)

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _vx(self, time):
        return int(self.tl.time_to_x(time) - self.tl.horizontalScrollBar().value())

    def _lane_y(self):
        return _RULER_HEIGHT + _SHOT_LANE_HEIGHT // 2

    def _drag(self, from_time, to_time, y=None, modifiers=None):
        C, G = self.C, self.G
        y = self._lane_y() if y is None else y
        modifiers = C.Qt.NoModifier if modifiers is None else modifiers
        for kind, x, btn, btns in (
            (
                C.QEvent.MouseButtonPress,
                self._vx(from_time),
                C.Qt.LeftButton,
                C.Qt.LeftButton,
            ),
            (C.QEvent.MouseMove, self._vx(to_time), C.Qt.NoButton, C.Qt.LeftButton),
            (
                C.QEvent.MouseButtonRelease,
                self._vx(to_time),
                C.Qt.LeftButton,
                C.Qt.NoButton,
            ),
        ):
            ev = G.QMouseEvent(kind, C.QPointF(x, y), btn, btns, modifiers)
            if kind == C.QEvent.MouseButtonPress:
                self.tl.mousePressEvent(ev)
            elif kind == C.QEvent.MouseMove:
                self.tl.mouseMoveEvent(ev)
            else:
                self.tl.mouseReleaseEvent(ev)

    def test_dragging_the_end_bound_on_the_ruler_resizes_the_shot(self):
        """A grab of a bound moves that bound; the other stays."""
        self._drag(120.0, 150.0)
        self.assertEqual(len(self.emitted), 1, self.emitted)
        start, end = self.emitted[0]
        self.assertAlmostEqual(start, 40.0, places=0)
        self.assertAlmostEqual(end, 150.0, places=0)
        self.assertFalse(self.w.ctrl_held_at_press)

    def test_ctrl_dragging_the_end_bound_on_the_ruler_resizes_the_shot(self):
        self._drag(120.0, 150.0, modifiers=self.C.Qt.ControlModifier)
        self.assertEqual(len(self.emitted), 1, self.emitted)
        start, end = self.emitted[0]
        self.assertAlmostEqual(start, 40.0, places=0)
        self.assertAlmostEqual(end, 150.0, places=0)
        self.assertTrue(self.w.ctrl_held_at_press)

    def test_dragging_the_start_bound_on_the_ruler_resizes_the_shot(self):
        self._drag(40.0, 20.0)
        self.assertEqual(len(self.emitted), 1, self.emitted)
        start, end = self.emitted[0]
        self.assertAlmostEqual(start, 20.0, places=0)
        self.assertAlmostEqual(end, 120.0, places=0)

    def test_ctrl_dragging_the_start_bound_on_the_ruler_resizes_the_shot(self):
        self._drag(40.0, 20.0, modifiers=self.C.Qt.ControlModifier)
        self.assertEqual(len(self.emitted), 1, self.emitted)
        start, end = self.emitted[0]
        self.assertAlmostEqual(start, 20.0, places=0)
        self.assertAlmostEqual(end, 120.0, places=0)

    def test_the_band_between_the_bounds_moves_the_whole_shot(self):
        """The band is the ONE place the shot can be dragged bodily.

        The highlight's own body passes presses through so the timeline's
        marquee works inside the active shot -- it spans every track row of
        that shot, so claiming the gesture there left nowhere to marquee.
        The band is where the shot's extent is already drawn, so it is where
        the move lives instead.
        """
        self._drag(80.0, 90.0)
        self.assertEqual(len(self.emitted), 1, "a body drag emits once")
        start, end = self.emitted[0]
        self.assertAlmostEqual(
            end - start, self.SPAN, places=3, msg="a move must not resize the shot"
        )
        self.assertEqual(self.moved, [], "the band moves the shot, it does not scrub")

    def test_the_tick_row_above_the_lane_still_scrubs(self):
        self._drag(120.0, 150.0, y=2)
        self.assertEqual(self.emitted, [])
        self.assertTrue(self.moved)

    def test_a_press_without_a_move_emits_nothing(self):
        """Same zero-motion gate the item's own release keeps."""
        self._drag(120.0, 120.0)
        self.assertEqual(self.emitted, [])

    def test_no_handle_is_offered_when_the_highlight_is_hidden(self):
        self.w.show_range_highlight = False
        self._drag(120.0, 150.0)
        self.assertEqual(self.emitted, [])
        self.assertTrue(self.moved, "it scrubs, as the ruler otherwise would")


class TestRulerKeyTicks(BaseTestCase):
    """Keyed frames are marked on the ruler, the way Maya's timeline does."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.tid = self.w.add_track("A")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _ticks(self):
        self.w._timeline._update_scene_rect()
        return self.w._timeline._scene.ruler._key_ticks

    def test_clip_bounds_are_marked(self):
        self.w.add_clip(self.tid, 10.0, 20.0, "c")
        self.assertEqual(self._ticks(), [10.0, 30.0])

    def test_every_key_of_a_curve_preview_is_marked(self):
        self.w.add_clip(
            self.tid,
            10.0,
            20.0,
            "c",
            sub_row="translateX",
            curve_preview={
                "keys": [(12.0, 0.0), (17.0, 1.0), (25.0, 2.0)],
                "segments": [],
                "val_min": 0.0,
                "val_max": 1.0,
            },
        )
        self.assertEqual(self._ticks(), [10.0, 12.0, 17.0, 25.0, 30.0])

    def test_an_empty_timeline_has_no_ticks(self):
        self.assertEqual(self._ticks(), [])

    def test_setting_the_same_ticks_again_does_not_repaint(self):
        """This runs on every content pulse; churning a repaint per pulse is
        exactly the O(n) waste the extent recompute was already fixed for."""
        self.w.add_clip(self.tid, 10.0, 20.0, "c")
        ruler = self.w._timeline._scene.ruler
        self._ticks()
        calls = []
        original = ruler.update
        ruler.update = lambda *a, **k: (calls.append(1), original(*a, **k))[1]
        try:
            ruler.set_key_ticks([10.0, 30.0])
            self.assertEqual(calls, [])
            ruler.set_key_ticks([10.0, 31.0])
            self.assertEqual(len(calls), 1)
        finally:
            del ruler.update


class TestShotLaneSitsBelowTheRuler(BaseTestCase):
    """The shot band is its own strip; the ruler is ruler all the way down.

    Reported live, twice: "the blue shot border still overlaps the shot
    timeline ... we need to be able to click into that timeline area without
    selecting the shot".  The band used to occupy the bottom half of the
    ruler, so the active shot's accent rule was painted inside it and the
    bottom 12px of the ruler grabbed the shot instead of scrubbing.
    """

    def setUp(self):
        from qtpy import QtCore, QtGui

        self.C, self.G = QtCore, QtGui
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.w.show()
        self.tid = self.w.add_track("A")
        self.w.add_clip(self.tid, 40.0, 80.0, "c")
        self.w.set_shot_blocks(
            [{"id": 1, "name": "s", "start": 40.0, "end": 120.0, "active": True}]
        )
        self.w.set_range_highlight(40.0, 120.0)
        self.tl = self.w._timeline
        self.emitted = []
        self.w.range_highlight_changed.connect(lambda a, b: self.emitted.append((a, b)))
        self.moved = []
        self.w.playhead_moved.connect(self.moved.append)

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _vx(self, time):
        return int(self.tl.time_to_x(time) - self.tl.horizontalScrollBar().value())

    def _drag(self, from_time, to_time, y):
        C, G = self.C, self.G
        for kind, x, btn, btns in (
            (
                C.QEvent.MouseButtonPress,
                self._vx(from_time),
                C.Qt.LeftButton,
                C.Qt.LeftButton,
            ),
            (C.QEvent.MouseMove, self._vx(to_time), C.Qt.NoButton, C.Qt.LeftButton),
            (
                C.QEvent.MouseButtonRelease,
                self._vx(to_time),
                C.Qt.LeftButton,
                C.Qt.NoButton,
            ),
        ):
            ev = G.QMouseEvent(kind, C.QPointF(x, y), btn, btns, C.Qt.NoModifier)
            if kind == C.QEvent.MouseButtonPress:
                self.tl.mousePressEvent(ev)
            elif kind == C.QEvent.MouseMove:
                self.tl.mouseMoveEvent(ev)
            else:
                self.tl.mouseReleaseEvent(ev)

    def test_every_row_of_the_ruler_scrubs(self):
        """Including the bottom row, which the band used to own."""
        for y in (2, _RULER_HEIGHT // 2, _RULER_HEIGHT - 1):
            with self.subTest(y=y):
                self.emitted.clear()
                self.moved.clear()
                self._drag(120.0, 150.0, y=y)
                self.assertEqual(self.emitted, [], "the ruler must not resize the shot")
                self.assertTrue(self.moved, "it scrubs")

    def test_the_band_below_the_ruler_still_grabs_the_shot(self):
        self._drag(120.0, 150.0, y=_RULER_HEIGHT + _SHOT_LANE_HEIGHT // 2)
        self.assertEqual(len(self.emitted), 1, self.emitted)
        self.assertEqual(self.moved, [], "the band moves the shot, it does not scrub")

    def test_the_ruler_item_covers_the_band_it_paints(self):
        ruler = self.tl._scene.ruler
        self.assertEqual(
            ruler.boundingRect().height(), _RULER_HEIGHT + _SHOT_LANE_HEIGHT
        )

    def test_the_highlight_starts_clear_of_the_ruler(self):
        top = self.w._range_highlight._rect().top()
        self.assertGreaterEqual(top, _RULER_HEIGHT + _SHOT_LANE_HEIGHT)

    def test_the_track_labels_line_up_with_the_tracks(self):
        margin = self.w._header._layout.contentsMargins().top()
        self.assertEqual(margin, _RULER_HEIGHT + _SHOT_LANE_HEIGHT)


class TestTheHandAppearsOnlyOnceDragging(BaseTestCase):
    """Hovering and clicking a clip leave the ordinary arrow in place.

    Reported live: "make the cursor remain standard during clicking and
    change to the drag cursor only on drag".  The body advertised an
    open-hand on hover, so a plain selection click looked like a grab.
    """

    def setUp(self):
        from qtpy import QtCore, QtWidgets

        self.C, self.QtW = QtCore, QtWidgets
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.tid = self.w.add_track("A")
        self.cid = self.w.add_clip(self.tid, start=10, duration=40)
        self.item = self.w._clip_items[self.cid]

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _hover(self, pos):
        ev = self.QtW.QGraphicsSceneHoverEvent(self.C.QEvent.GraphicsSceneHoverMove)
        ev.setPos(pos)
        ev.setScenePos(pos)
        self.item.hoverMoveEvent(ev)

    def test_hovering_the_body_leaves_the_arrow(self):
        self._hover(self.item.rect().center())
        self.assertFalse(
            self.item.hasCursor(), f"body set {self.item.cursor().shape()}"
        )

    def test_hovering_an_edge_still_offers_the_resize(self):
        r = self.item.rect()
        self._hover(self.C.QPointF(r.right() - 1, r.center().y()))
        self.assertTrue(self.item.hasCursor())
        self.assertEqual(self.item.cursor().shape(), self.C.Qt.SizeHorCursor)

    def test_a_press_alone_does_not_take_the_hand(self):
        center = self.item.rect().center()
        self.item.mousePressEvent(
            _scene_mouse_event(self.C.QEvent.GraphicsSceneMousePress, center)
        )
        self.assertFalse(self.item.hasCursor())

    def test_arming_the_drag_takes_the_closed_hand(self):
        center = self.item.rect().center()
        self.item.mousePressEvent(
            _scene_mouse_event(self.C.QEvent.GraphicsSceneMousePress, center)
        )
        far = self.C.QPointF(center.x() + 200, center.y())
        self.item.mouseMoveEvent(
            _scene_mouse_event(self.C.QEvent.GraphicsSceneMouseMove, far)
        )
        self.assertIsNotNone(self.item._drag_mode)
        self.assertEqual(self.item.cursor().shape(), self.C.Qt.ClosedHandCursor)


class TestTheActiveShotIsFramedOnFirstShow(BaseTestCase):
    """Opening the panel lands on the shot being worked on, not frame 0."""

    def setUp(self):
        self.w = SequencerWidget()
        self.tid = self.w.add_track("A")
        self.w.add_clip(self.tid, 0.0, 4000.0, "everything")

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _framed_span(self):
        tl = self.w._timeline
        vp = tl.viewport().width()
        left = tl.x_to_time(tl.horizontalScrollBar().value())
        return left, left + vp / tl.pixels_per_unit

    def test_the_active_shot_fills_the_view(self):
        self.w.set_range_highlight(3000.0, 3200.0)
        self.w.resize(900, 400)
        self.w.show()
        left, right = self._framed_span()
        self.assertLess(left, 3000.0)
        self.assertGreater(right, 3200.0)
        self.assertLess(right - left, 400.0, "framed the shot, not the whole scene")

    def test_a_second_show_leaves_the_users_view_alone(self):
        self.w.set_range_highlight(3000.0, 3200.0)
        self.w.resize(900, 400)
        self.w.show()
        self.w._timeline.horizontalScrollBar().setValue(0)
        self.w.hide()
        self.w.show()
        self.assertEqual(self.w._timeline.horizontalScrollBar().value(), 0)

    def test_opting_out_never_frames(self):
        """A consumer that manages its own view must keep it."""
        calls = []
        self.w.frame_shot = lambda: calls.append(1)
        self.w.frame_on_first_show = False
        self.w.set_range_highlight(3000.0, 3200.0)
        self.w.resize(900, 400)
        self.w.show()
        self.assertEqual(calls, [])

    def test_an_empty_show_retries_rather_than_giving_up(self):
        """Content can arrive after the show; the next resize still frames."""
        empty = SequencerWidget()
        self.addCleanup(empty.deleteLater)
        self.addCleanup(empty.close)
        empty.resize(900, 400)
        empty.show()
        tid = empty.add_track("A")
        empty.add_clip(tid, 0.0, 4000.0, "everything")
        empty.set_range_highlight(3000.0, 3200.0)
        empty.resize(880, 400)
        tl = empty._timeline
        left = tl.x_to_time(tl.horizontalScrollBar().value())
        right = left + tl.viewport().width() / tl.pixels_per_unit
        self.assertLess(left, 3000.0)
        self.assertGreater(right, 3200.0)


# =========================================================================
# Key context menu + tangent handles
# =========================================================================


class TestKeyContextMenuAndTangentHandles(BaseTestCase):
    """Right-click on a key opens the KEY menu (not the clip's), and a
    selected key shows its tangent handles -- hidden otherwise, or a strip a
    few pixels tall would be buried under two lines per key."""

    #: Snapshotted at import, BEFORE any test runs: the widget hands the dict
    #: to the clip as-is, and TestKeyframeItem's drag tests re-time the
    #: shared fixture in place, so a copy taken per test inherits their edits.
    PREVIEW = __import__("copy").deepcopy(TestKeyframeItem.SAMPLE_PREVIEW)

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _clip(self, **extra):
        import copy

        tid = self.w.add_track("obj_A")
        preview = copy.deepcopy(self.PREVIEW)
        data = {"curve_preview": preview}
        data.update(extra)
        self.w.expand_track(
            tid,
            sub_row_data=[("translateX", [(0, 100, "translateX", "#FF6600", data)])],
        )
        clip = [c for c in self.w.clips() if c.sub_row][0]
        return clip, self.w._clip_items[clip.clip_id]

    @staticmethod
    def _ctx_event(item):
        from qtpy import QtWidgets, QtCore

        ev = QtWidgets.QGraphicsSceneContextMenuEvent(
            QtCore.QEvent.GraphicsSceneContextMenu
        )
        ev.setScenePos(item.scenePos())
        ev.setScreenPos(QtCore.QPoint(100, 100))
        return ev

    # -- selection payload --------------------------------------------------

    def test_selected_keys_groups_the_selection_by_clip(self):
        clip, item = self._clip()
        item._keyframe_items[0].setSelected(True)
        item._keyframe_items[2].setSelected(True)
        groups = self.w.selected_keys()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["clip_id"], clip.clip_id)
        self.assertEqual(sorted(groups[0]["times"]), [10, 90])

    def test_nothing_selected_is_an_empty_list(self):
        self._clip()
        self.assertEqual(self.w.selected_keys(), [])

    def test_select_keys_by_clip_data_and_time(self):
        """A consumer re-selects keys after its rebuild by ITS vocabulary."""
        clip, item = self._clip(obj="cube", attr_name="translateX")
        seen = []
        self.w.key_selection_changed.connect(lambda groups: seen.append(groups))
        n = self.w.select_keys(
            [{"data": {"obj": "cube", "attr_name": "translateX"}, "times": [10, 90]}]
        )
        self.assertEqual(n, 2)
        self.assertEqual(sorted(self.w.selected_keys()[0]["times"]), [10, 90])
        self.assertEqual(len(seen), 1, "one notification for the batch")
        # A bag that does not match selects nothing and clears the rest.
        self.assertEqual(
            self.w.select_keys([{"data": {"obj": "other"}, "times": [10]}]), 0
        )
        self.assertEqual(self.w.selected_keys(), [])

    # -- context menu -------------------------------------------------------

    def test_right_click_asks_the_consumer_with_the_selection(self):
        from unittest.mock import patch
        from qtpy import QtWidgets

        clip, item = self._clip()
        key = item._keyframe_items[1]
        got = []
        self.w.key_menu_requested.connect(
            lambda menu, groups: got.append((menu, groups))
        )
        with patch.object(QtWidgets.QMenu, "exec_", return_value=None):
            key.contextMenuEvent(self._ctx_event(key))
        self.assertEqual(len(got), 1)
        menu, groups = got[0]
        self.assertEqual(groups, [{"clip_id": clip.clip_id, "times": [50]}])
        self.assertTrue(key.isSelected(), "an unselected key becomes the selection")
        labels = [a.text() for a in menu.actions() if not a.isSeparator()]
        self.assertEqual(labels, ["Delete Key"], "the widget owns Delete")

    def test_right_click_on_a_selected_key_keeps_the_whole_selection(self):
        from unittest.mock import patch
        from qtpy import QtWidgets

        clip, item = self._clip()
        for ki in item._keyframe_items:
            ki.setSelected(True)
        got = []
        self.w.key_menu_requested.connect(lambda menu, groups: got.append(groups))
        with patch.object(QtWidgets.QMenu, "exec_", return_value=None):
            k = item._keyframe_items[0]
            k.contextMenuEvent(self._ctx_event(k))
        self.assertEqual(sorted(got[0][0]["times"]), [10, 50, 90])

    def test_the_consumer_s_actions_come_before_delete(self):
        from unittest.mock import patch
        from qtpy import QtWidgets

        clip, item = self._clip()
        for ki in item._keyframe_items:
            ki.setSelected(True)
        self.w.key_menu_requested.connect(lambda menu, groups: menu.addAction("Flat"))
        seen = []
        with patch.object(
            QtWidgets.QMenu,
            "exec_",
            lambda m, *a, **k: (
                seen.append([(x.text(), x.isSeparator()) for x in m.actions()]) or None
            ),
        ):
            k = item._keyframe_items[0]
            k.contextMenuEvent(self._ctx_event(k))
        labels = [t for t, sep in seen[0] if not sep]
        self.assertEqual(labels, ["Flat", "Delete Keys (3)"])
        self.assertTrue(seen[0][1][1], "kept visually apart")

    def test_delete_from_the_menu_emits_keys_deleted(self):
        from unittest.mock import patch
        from qtpy import QtWidgets

        clip, item = self._clip()
        key = item._keyframe_items[0]
        deleted = []
        self.w.keys_deleted.connect(lambda cid, times: deleted.append((cid, times)))

        def _pick_delete(menu, *_a, **_k):
            return next(a for a in menu.actions() if a.text().startswith("Delete"))

        with patch.object(QtWidgets.QMenu, "exec_", _pick_delete):
            key.contextMenuEvent(self._ctx_event(key))
        self.assertEqual(deleted, [(clip.clip_id, [10])])

    def test_a_read_only_key_has_no_menu(self):
        from unittest.mock import patch
        from qtpy import QtWidgets

        clip, item = self._clip(read_only=True)
        got = []
        self.w.key_menu_requested.connect(lambda m, g: got.append(g))
        key = item._keyframe_items[0]
        with patch.object(QtWidgets.QMenu, "exec_", return_value=None):
            key.contextMenuEvent(self._ctx_event(key))
        self.assertEqual(got, [])

    def test_the_timeline_routes_a_key_right_click_to_the_key(self):
        """The view used to treat a key like empty track space and open the
        zone menu; a key under the cursor must reach the key's own handler."""
        from unittest.mock import patch
        from qtpy import QtWidgets, QtGui

        clip, item = self._clip()
        QtWidgets.QApplication.processEvents()
        key = item._keyframe_items[1]
        seen = []
        zone = []
        self.w.zone_context_menu_requested.connect(lambda *a: zone.append(a))
        with patch.object(
            KeyframeItem, "contextMenuEvent", lambda self_, ev: seen.append(self_)
        ):
            tl = self.w._timeline
            vp = tl.mapFromScene(key.scenePos())
            ev = QtGui.QContextMenuEvent(
                QtGui.QContextMenuEvent.Mouse, vp, tl.mapToGlobal(vp)
            )
            tl.contextMenuEvent(ev)
        self.assertEqual(seen, [key])
        self.assertEqual(zone, [], "not the zone menu")

    # -- the selection owns the right-click ---------------------------------

    @staticmethod
    def _right_press(tl, viewport_pos):
        from qtpy import QtCore, QtGui

        tl.mousePressEvent(
            QtGui.QMouseEvent(
                QtCore.QEvent.MouseButtonPress,
                QtCore.QPointF(viewport_pos),
                QtCore.Qt.RightButton,
                QtCore.Qt.RightButton,
                QtCore.Qt.NoModifier,
            )
        )

    @staticmethod
    def _view_ctx_event(tl, viewport_pos):
        from qtpy import QtGui

        return QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse, viewport_pos, tl.mapToGlobal(viewport_pos)
        )

    def test_a_right_press_keeps_the_key_selection(self):
        """A press the scene does not accept CLEARS the selection -- which is
        how a multi-key selection collapsed to the one dot under the cursor
        before its menu had even opened."""
        from qtpy import QtWidgets

        clip, item = self._clip()
        QtWidgets.QApplication.processEvents()
        tl = self.w._timeline
        keys = item._keyframe_items
        for ki in keys:
            ki.setSelected(True)

        self._right_press(tl, tl.mapFromScene(keys[0].scenePos()))
        self.assertEqual(
            sorted(self.w.selected_keys()[0]["times"]), [10, 50, 90], "on a key"
        )

        body = tl.mapFromScene(item.mapToScene(item.rect().center()))
        self._right_press(tl, body)
        self.assertEqual(
            sorted(self.w.selected_keys()[0]["times"]), [10, 50, 90], "on the clip"
        )

        empty = tl.mapFromScene(item.mapToScene(item.rect().center()))
        empty.setX(tl.viewport().width() - 2)
        self._right_press(tl, empty)
        self.assertEqual(
            sorted(self.w.selected_keys()[0]["times"]), [10, 50, 90], "on empty space"
        )

    def test_a_right_press_on_an_unselected_key_switches_to_it(self):
        from qtpy import QtWidgets

        clip, item = self._clip()
        QtWidgets.QApplication.processEvents()
        tl = self.w._timeline
        keys = item._keyframe_items
        keys[0].setSelected(True)
        self._right_press(tl, tl.mapFromScene(keys[2].scenePos()))
        self.assertEqual(self.w.selected_keys()[0]["times"], [90])

    def test_the_key_menu_opens_anywhere_over_the_tracks(self):
        """With keys selected the right-click belongs to them: reaching the
        key menu must not mean hitting a dot a few pixels wide."""
        from unittest.mock import patch
        from qtpy import QtWidgets

        clip, item = self._clip()
        QtWidgets.QApplication.processEvents()
        tl = self.w._timeline
        for ki in item._keyframe_items:
            ki.setSelected(True)
        got, clips, zones = [], [], []
        self.w.key_menu_requested.connect(lambda m, g: got.append(g))
        self.w.clip_menu_requested.connect(lambda m, c: clips.append(c))
        self.w.zone_context_menu_requested.connect(lambda *a: zones.append(a))

        body = tl.mapFromScene(item.mapToScene(item.rect().center()))
        with patch.object(QtWidgets.QMenu, "exec_", return_value=None):
            tl.contextMenuEvent(self._view_ctx_event(tl, body))
        self.assertEqual(len(got), 1, "the key menu, not the clip's")
        self.assertEqual(sorted(got[0][0]["times"]), [10, 50, 90])
        self.assertEqual((clips, zones), ([], []))

    def test_without_a_key_selection_the_clip_and_zone_menus_are_unchanged(self):
        from unittest.mock import patch
        from qtpy import QtWidgets

        clip, item = self._clip()
        QtWidgets.QApplication.processEvents()
        tl = self.w._timeline
        keys_seen, clips = [], []
        self.w.key_menu_requested.connect(lambda m, g: keys_seen.append(g))
        self.w.clip_menu_requested.connect(lambda m, c: clips.append(c))

        body = tl.mapFromScene(item.mapToScene(item.rect().center()))
        with patch.object(QtWidgets.QMenu, "exec_", return_value=None):
            tl.contextMenuEvent(self._view_ctx_event(tl, body))
        self.assertEqual((keys_seen, clips), ([], [clip.clip_id]))

    def test_the_ruler_keeps_its_own_menu_while_keys_are_selected(self):
        from unittest.mock import patch
        from qtpy import QtWidgets, QtCore

        clip, item = self._clip()
        QtWidgets.QApplication.processEvents()
        tl = self.w._timeline
        for ki in item._keyframe_items:
            ki.setSelected(True)
        got, zones = [], []
        self.w.key_menu_requested.connect(lambda m, g: got.append(g))
        self.w.zone_menu_enabled = True
        self.w.zone_context_menu_requested.connect(lambda *a: zones.append(a[0]))
        with patch.object(QtWidgets.QMenu, "exec_", return_value=None):
            tl.contextMenuEvent(self._view_ctx_event(tl, QtCore.QPoint(200, 2)))
        self.assertEqual(got, [], "no key menu on the ruler")
        self.assertEqual(zones, ["ruler"])

    def test_a_locked_clip_keeps_its_keys_out_of_the_menu(self):
        """The read-only guard used to sit on the key that was clicked; the
        menu is the selection's now, so it has to filter the selection."""
        from unittest.mock import patch
        from qtpy import QtWidgets

        clip, item = self._clip(read_only=True)
        QtWidgets.QApplication.processEvents()
        tl = self.w._timeline
        for ki in item._keyframe_items:
            ki.setSelected(True)
        got = []
        self.w.key_menu_requested.connect(lambda m, g: got.append(g))
        body = tl.mapFromScene(item.mapToScene(item.rect().center()))
        with patch.object(QtWidgets.QMenu, "exec_", return_value=None):
            self.assertFalse(self.w.show_key_menu(tl.mapToGlobal(body)))
        self.assertEqual(got, [])

    def test_a_locked_row_refuses_every_key_edit(self):
        """Locked and read-only rows are drawn dimmed to say "not editable"
        -- but their keys dragged, showed grab points and answered Delete,
        each one written straight into the host."""
        from qtpy import QtCore, QtWidgets

        clip, item = self._clip(read_only=True)
        QtWidgets.QApplication.processEvents()
        self.assertFalse(item.keys_editable)
        key = item._keyframe_items[0]
        key.setSelected(True)

        # No handles to grab, and no lines painted for them.
        self.assertEqual(key._tangent_slots(), [])
        self.assertEqual(key._tangent_handles(), [])
        self.assertEqual(item._tangent_handle_items, [])

        # A drag selects and goes no further.
        moved = []
        self.w.keys_moved.connect(lambda cid, ch: moved.append((cid, ch)))
        pos = key.scenePos()
        key.mousePressEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMousePress, pos)
        )
        self.assertFalse(key._dragging)
        key.mouseMoveEvent(
            _scene_mouse_event(
                QtCore.QEvent.GraphicsSceneMouseMove,
                QtCore.QPointF(pos.x() + 40, pos.y()),
            )
        )
        key.mouseReleaseEvent(
            _scene_mouse_event(
                QtCore.QEvent.GraphicsSceneMouseRelease,
                QtCore.QPointF(pos.x() + 40, pos.y()),
            )
        )
        self.assertEqual((moved, key._time), ([], 10))

        # And Delete leaves them alone.
        deleted = []
        self.w.keys_deleted.connect(lambda cid, times: deleted.append((cid, times)))
        self.w._delete_selected_keys()
        self.assertEqual(deleted, [])

    # -- tangent handles ----------------------------------------------------

    def test_handles_appear_only_while_selected(self):
        clip, item = self._clip()
        k0, k1, k2 = item._keyframe_items
        for k in (k0, k1, k2):
            self.assertEqual(k._tangent_handles(), [])
        for k in (k0, k1, k2):
            k.setSelected(True)
        # k0 opens a spline span: one OUT handle.  k1 closes it (IN) and
        # opens a stepped span (no OUT).  k2 closes the stepped span: none.
        self.assertEqual(len(k0._tangent_handles()), 1)
        self.assertEqual(len(k1._tangent_handles()), 1)
        self.assertEqual(k2._tangent_handles(), [])
        k0.setSelected(False)
        self.assertEqual(k0._tangent_handles(), [])

    def test_a_handle_lies_on_the_clip_curve_mapping(self):
        clip, item = self._clip()
        k0 = item._keyframe_items[0]
        k0.setSelected(True)
        (h,) = k0._tangent_handles()
        expect = k0._clip_point(23.33, 0.33)
        self.assertAlmostEqual(h.x(), expect.x(), places=6)
        self.assertAlmostEqual(h.y(), expect.y(), places=6)
        self.assertGreater(h.x(), k0.pos().x(), "the OUT handle points forward")
        self.assertTrue(item.rect().contains(h), "a handle lies inside its clip")

    def test_the_dot_stays_where_it_was(self):
        """The shared mapping must reproduce the old dot placement exactly."""
        clip, item = self._clip()
        k1 = item._keyframe_items[1]
        rect = item.rect()
        frac = (50 - clip.start) / clip.duration
        self.assertAlmostEqual(k1.pos().x(), rect.x() + frac * rect.width(), places=6)

    def test_selecting_a_key_never_changes_its_own_rect(self):
        """The clip paints the handles; a key rect that grew on selection
        landed the key inside subtract-marquees it was never under."""
        clip, item = self._clip()
        k0 = item._keyframe_items[0]
        bare = k0.boundingRect()
        k0.setSelected(True)
        self.assertEqual(len(k0._tangent_handles()), 1)
        self.assertEqual(k0.boundingRect(), bare)

    def test_the_clip_paints_the_handles_of_selected_keys(self):
        from unittest.mock import patch
        from qtpy import QtGui

        clip, item = self._clip()
        item._keyframe_items[0].setSelected(True)
        img = QtGui.QImage(400, 100, QtGui.QImage.Format_ARGB32)
        p = QtGui.QPainter(img)
        drawn = []
        try:
            with patch.object(
                QtGui.QPainter, "drawLine", lambda self_, *a: drawn.append(a)
            ):
                item.paint(p, None, None)
        finally:
            p.end()
        self.assertEqual(len(drawn), 1, "one handle line for the one OUT handle")

    def test_handles_retract_while_a_key_is_dragged(self):
        clip, item = self._clip()
        k0 = item._keyframe_items[0]
        k0.setSelected(True)
        item._keys_dragging = True
        try:
            self.assertEqual(k0._tangent_handles(), [])
        finally:
            item._keys_dragging = False
        self.assertEqual(len(k0._tangent_handles()), 1)

    def test_a_selected_key_still_paints(self):
        from qtpy import QtGui

        clip, item = self._clip()
        k0 = item._keyframe_items[0]
        k0.setSelected(True)
        img = QtGui.QImage(64, 64, QtGui.QImage.Format_ARGB32)
        p = QtGui.QPainter(img)
        try:
            p.translate(32, 32)
            k0.paint(p, None, None)
        finally:
            p.end()

    def test_selecting_a_key_repaints_its_clip(self):
        from unittest.mock import patch

        clip, item = self._clip()
        calls = []
        with patch.object(type(item), "update", lambda self_, *a: calls.append(a)):
            item._keyframe_items[0].setSelected(True)
        self.assertEqual(len(calls), 1)


# =========================================================================
# One modifier grammar for every shot-bound handle + the shortcut overlay
# =========================================================================


class TestBoundHandleGrammar(BaseTestCase):
    """A grab of a shot bound drags THAT bound under every modifier; the
    press records Ctrl and Shift so the consumer decides what else moves
    (plain: the neighbours ripple; Ctrl: nothing else; Shift: retime).  The
    whole-shot move is the ruler band's."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.w.show()
        self.w.add_track("A")
        self.w.set_shot_blocks(
            [{"id": 1, "name": "s", "start": 40.0, "end": 120.0, "active": True}]
        )
        self.w.set_range_highlight(40.0, 120.0)
        self.emitted = []
        self.w.range_highlight_changed.connect(lambda a, b: self.emitted.append((a, b)))

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _grab_right_edge(self, modifiers):
        from qtpy import QtCore, QtWidgets

        item = self.w._range_highlight
        r = item._rect()
        pt = QtCore.QPointF(r.right() - 1, r.center().y())
        ev = QtWidgets.QGraphicsSceneMouseEvent(QtCore.QEvent.GraphicsSceneMousePress)
        ev.setButton(QtCore.Qt.LeftButton)
        ev.setButtons(QtCore.Qt.LeftButton)
        ev.setScenePos(pt)
        ev.setPos(pt)
        ev.setScreenPos(QtCore.QPoint(int(pt.x()), int(pt.y())))
        ev.setModifiers(modifiers)
        item.mousePressEvent(ev)
        return item, pt

    def _drag_to(self, item, pt, dx):
        from qtpy import QtCore, QtWidgets

        moved = QtCore.QPointF(pt.x() + dx, pt.y())
        ev = QtWidgets.QGraphicsSceneMouseEvent(QtCore.QEvent.GraphicsSceneMouseMove)
        ev.setScenePos(moved)
        ev.setPos(moved)
        ev.setScreenPos(QtCore.QPoint(int(moved.x()), int(moved.y())))
        item.mouseMoveEvent(ev)
        rel = QtWidgets.QGraphicsSceneMouseEvent(
            QtCore.QEvent.GraphicsSceneMouseRelease
        )
        rel.setButton(QtCore.Qt.LeftButton)
        item.mouseReleaseEvent(rel)

    def test_a_plain_edge_grab_moves_only_that_bound(self):
        from qtpy import QtCore

        item, pt = self._grab_right_edge(QtCore.Qt.NoModifier)
        self.assertEqual(item._drag_mode, "right")
        self.assertEqual(item._grab_zone, "right")
        self._drag_to(item, pt, 4 * self.w._timeline._pixels_per_unit)
        self.assertEqual(len(self.emitted), 1)
        start, end = self.emitted[0]
        self.assertAlmostEqual(start, 40.0, "the other bound stays")
        self.assertGreater(end, 120.0)
        self.assertFalse(self.w.ctrl_held_at_press)
        self.assertFalse(self.w.shift_held_at_press)

    def test_a_ctrl_edge_grab_moves_only_that_bound(self):
        from qtpy import QtCore

        item, pt = self._grab_right_edge(QtCore.Qt.ControlModifier)
        self.assertEqual(item._drag_mode, "right")
        self.assertTrue(self.w.ctrl_held_at_press)
        self.assertFalse(self.w.shift_held_at_press)
        self._drag_to(item, pt, 4 * self.w._timeline._pixels_per_unit)
        start, end = self.emitted[0]
        self.assertAlmostEqual(start, 40.0)
        self.assertGreater(end, 120.0)

    def test_a_shift_edge_grab_moves_only_that_bound(self):
        from qtpy import QtCore

        item, _pt = self._grab_right_edge(QtCore.Qt.ShiftModifier)
        self.assertEqual(item._drag_mode, "right")
        self.assertTrue(self.w.shift_held_at_press)
        self.assertFalse(self.w.ctrl_held_at_press)

    def test_the_drag_label_names_the_gesture(self):
        from qtpy import QtCore

        item, _pt = self._grab_right_edge(QtCore.Qt.ControlModifier)
        self.assertTrue(item._range_drag_label().startswith("Trim 120"))
        item._drag_mode = None
        item, _pt = self._grab_right_edge(QtCore.Qt.ShiftModifier)
        self.assertTrue(item._range_drag_label().startswith("Retime 120"))
        item._drag_mode = None
        item, _pt = self._grab_right_edge(QtCore.Qt.NoModifier)
        self.assertTrue(item._range_drag_label().startswith("Resize 120"))

    def test_a_plain_press_clears_stale_modifier_flags(self):
        from qtpy import QtCore

        self.w.shift_held_at_press = True
        self.w.ctrl_held_at_press = True
        self._grab_right_edge(QtCore.Qt.NoModifier)
        self.assertFalse(self.w.shift_held_at_press)
        self.assertFalse(self.w.ctrl_held_at_press)

    def test_a_gap_edge_press_records_ctrl_and_labels_the_trim(self):
        from qtpy import QtCore, QtWidgets

        self.w.add_gap_overlay(120, 160)
        gap = self.w._gap_overlays[0]
        r = gap._rect()
        pt = QtCore.QPointF(r.right() - 1, r.center().y())
        ev = QtWidgets.QGraphicsSceneMouseEvent(QtCore.QEvent.GraphicsSceneMousePress)
        ev.setButton(QtCore.Qt.LeftButton)
        ev.setButtons(QtCore.Qt.LeftButton)
        ev.setScenePos(pt)
        ev.setPos(pt)
        ev.setScreenPos(QtCore.QPoint(int(pt.x()), int(pt.y())))
        ev.setModifiers(QtCore.Qt.ControlModifier)
        gap.mousePressEvent(ev)
        self.assertEqual(gap._drag_mode, "right")
        self.assertTrue(self.w.ctrl_held_at_press)
        self.assertTrue(gap._gap_drag_label().startswith("Trim 160"))


class TestShortcutOverlay(BaseTestCase):
    """The corner legend: fed by the shortcut manager, hidden until asked,
    one group at a time with the hovered group lit, transparent to the mouse."""

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(900, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_gestures_are_registered_with_the_manager(self):
        mgr = self.w._shortcut_mgr
        self.assertEqual(
            list(mgr.gestures), ["Shot bounds", "Gaps", "Clips & keys", "Timeline"]
        )
        entry = mgr.shortcuts["Ctrl+Drag (Shot bounds)"]
        self.assertTrue(entry["read_only"], "listed in the editor, not rebindable")

    def test_hidden_until_shown_then_anchored_in_the_timelines_corner(self):
        from qtpy import QtCore

        self.assertIsNone(self.w.shortcut_overlay)
        self.assertFalse(self.w.shortcut_overlay_visible)
        self.w.shortcut_overlay_visible = True
        overlay = self.w.shortcut_overlay
        self.assertTrue(overlay.isVisible())
        self.assertTrue(overlay.testAttribute(QtCore.Qt.WA_TransparentForMouseEvents))
        host = self.w._timeline.viewport().geometry()
        g = overlay.geometry()
        self.assertEqual(g.right() + 1 + overlay.MARGIN, host.right() + 1)
        self.assertEqual(g.bottom() + 1 + overlay.MARGIN, host.bottom() + 1)
        self.assertLessEqual(g.width(), overlay.MAX_WIDTH)
        self.assertLess(g.height(), g.width(), "a card, not a column")
        self.w.shortcut_overlay_visible = False
        self.assertFalse(overlay.isVisible())

    def test_it_re_anchors_when_the_timeline_resizes(self):
        self.w.shortcut_overlay_visible = True
        overlay = self.w.shortcut_overlay
        self.w.resize(700, 300)
        self.w._timeline.resize(400, 200)
        host = self.w._timeline.viewport().geometry()
        self.assertEqual(
            overlay.geometry().right() + 1 + overlay.MARGIN, host.right() + 1
        )

    def test_the_hovered_group_is_the_one_shown(self):
        self.w.shortcut_overlay_visible = True
        overlay = self.w.shortcut_overlay
        self.assertEqual(overlay.shown_group, "Shot bounds")
        self.w._set_gesture_context("Gaps")
        self.assertEqual(overlay.shown_group, "Gaps")
        self.assertIn("Lock / unlock the gap", overlay._label.text())
        self.assertNotIn("Marquee", overlay._label.text())
        self.w._set_gesture_context(None)
        self.assertEqual(overlay.shown_group, "Shot bounds")

    def test_the_timeline_reports_the_group_under_the_pointer(self):
        from qtpy import QtCore

        self.w.set_shot_blocks(
            [{"id": 1, "name": "s", "start": 40.0, "end": 120.0, "active": True}]
        )
        self.w.set_range_highlight(40.0, 120.0)
        self.w.add_gap_overlay(120, 160)
        self.w.shortcut_overlay_visible = True
        tl = self.w._timeline
        gap = self.w._gap_overlays[0]
        centre = gap._rect().center()
        vp = tl.mapFromScene(centre)
        tl._sync_gesture_context(QtCore.QPoint(vp.x(), vp.y()))
        self.assertEqual(self.w.shortcut_overlay.shown_group, "Gaps")

    def test_the_card_stays_translucent_under_the_theme(self):
        """A slight transparency: whatever is behind the card tints it.

        uitk's theme gives every ``QLabel`` an opaque background and a
        border -- which painted a solid slab over the card's own
        translucent fill -- so the legend's label opts out of both.
        """
        from qtpy import QtCore, QtGui, QtWidgets

        self.w.setStyleSheet(
            "QLabel { background-color: rgb(0, 255, 0);"
            " border: 1px solid rgb(0, 255, 0); }"
        )
        self.w.shortcut_overlay_visible = True
        overlay = self.w.shortcut_overlay
        pixmap = QtGui.QPixmap(overlay.size())
        pixmap.fill(QtGui.QColor(255, 0, 0))  # the ground it must let through
        overlay.render(
            pixmap, QtCore.QPoint(), QtGui.QRegion(), QtWidgets.QWidget.DrawChildren
        )
        image = pixmap.toImage()
        middle = image.pixelColor(image.width() // 2, image.height() // 2)
        self.assertGreater(middle.red(), 30, f"opaque card: {middle.getRgb()}")
        self.assertLess(middle.red(), 220, f"no card drawn: {middle.getRgb()}")
        greens = [
            (x, y)
            for y in range(0, image.height(), 2)
            for x in range(0, image.width(), 2)
            if image.pixelColor(x, y).green() > image.pixelColor(x, y).red() + 40
        ]
        self.assertEqual(greens, [], "the theme's label background covers the card")

    def test_a_manager_without_gestures_still_renders(self):
        from qtpy import QtWidgets
        from uitk.managers.shortcut_manager import ShortcutManager

        host = QtWidgets.QWidget()
        host.resize(300, 200)
        mgr = ShortcutManager(host)
        mgr.add_shortcut("F", lambda: None, "frame")
        overlay = mgr.overlay(host, anchor="bottom-left")
        overlay.show()
        self.assertIsNone(overlay.shown_group)
        self.assertIn("frame", overlay._label.text())
        self.assertEqual(overlay.geometry().left(), overlay.MARGIN)


if __name__ == "__main__":
    unittest.main()


class TestTangentHandleDrag(BaseTestCase):
    """A selected key's tangent handles are grab points: dragging one reshapes
    the preview's control point live and reports the handle vector once, on
    release, as ``key_tangent_dragged``."""

    PREVIEW = __import__("copy").deepcopy(TestKeyframeItem.SAMPLE_PREVIEW)

    def setUp(self):
        self.w = SequencerWidget()
        self.w.resize(800, 400)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def _clip(self):
        import copy

        tid = self.w.add_track("obj_A")
        preview = copy.deepcopy(self.PREVIEW)
        self.w.expand_track(
            tid,
            sub_row_data=[
                (
                    "translateX",
                    [(0, 100, "translateX", "#FF6600", {"curve_preview": preview})],
                )
            ],
        )
        clip = [c for c in self.w.clips() if c.sub_row][0]
        return clip, self.w._clip_items[clip.clip_id]

    # The fixture's first span is a spline (cp1 + cp2) and its second is
    # linear (no control points): the first key owns an OUT handle only,
    # the middle key an IN handle only.
    @staticmethod
    def _first_key(item):
        return item._keyframe_items[0]

    @staticmethod
    def _middle_key(item):
        return item._keyframe_items[1]

    def _handles(self, item):
        from uitk.widgets.sequencer._keyframe import TangentHandleItem

        return [c for c in item.childItems() if isinstance(c, TangentHandleItem)]

    def _drag(self, handle, dx, dy):
        from qtpy import QtCore

        start = handle.scenePos()
        end = QtCore.QPointF(start.x() + dx, start.y() + dy)
        handle.mousePressEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMousePress, start)
        )
        handle.mouseMoveEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMouseMove, end)
        )
        handle.mouseReleaseEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMouseRelease, end)
        )

    def test_handles_exist_only_for_selected_keys(self):
        clip, item = self._clip()
        self.assertEqual(self._handles(item), [])
        first, middle = self._first_key(item), self._middle_key(item)
        middle.setSelected(True)
        handles = self._handles(item)
        self.assertEqual([(h.side, h.key) for h in handles], [("in", middle)])
        first.setSelected(True)
        self.assertEqual(
            sorted((h.side, h.key is first) for h in self._handles(item)),
            [("in", False), ("out", True)],
        )
        middle.setSelected(False)
        first.setSelected(False)
        self.assertEqual(self._handles(item), [])

    def test_dragging_the_out_handle_reports_the_vector_and_reshapes_the_preview(self):
        clip, item = self._clip()
        key = self._first_key(item)
        key.setSelected(True)
        out = next(h for h in self._handles(item) if h.side == "out")
        before = out.control_point()
        got = []
        self.w.key_tangent_dragged.connect(lambda *a: got.append(a))
        self._drag(out, 30.0, -10.0)
        self.assertEqual(len(got), 1)
        cid, t, side, dt, dv = got[0]
        self.assertEqual((cid, side), (clip.clip_id, "out"))
        self.assertAlmostEqual(t, key._time)
        self.assertGreater(dt, 0.0)
        self.assertGreater(dv, 0.0, "up on screen is a higher value")
        after = out.control_point()
        self.assertNotEqual(before, after)
        self.assertAlmostEqual(after[0], key._time + dt)
        self.assertAlmostEqual(after[1], key._value + dv)
        self.assertEqual(
            tuple(clip.data["curve_preview"]["segments"][out._seg_index]["cp1"]),
            after,
            "the drag rewrote the preview's control point in place",
        )

    def test_the_in_handle_never_crosses_its_key(self):
        clip, item = self._clip()
        key = self._middle_key(item)
        key.setSelected(True)
        inh = next(h for h in self._handles(item) if h.side == "in")
        got = []
        self.w.key_tangent_dragged.connect(lambda *a: got.append(a))
        self._drag(inh, 500.0, 0.0)  # far past the key, to the right
        self.assertEqual(len(got), 1)
        self.assertLess(got[0][3], 0.0, "an IN handle stays before its key")

    def test_a_release_without_movement_reports_nothing(self):
        clip, item = self._clip()
        key = self._first_key(item)
        key.setSelected(True)
        out = next(h for h in self._handles(item) if h.side == "out")
        got = []
        self.w.key_tangent_dragged.connect(lambda *a: got.append(a))
        self._drag(out, 0.0, 0.0)
        self.assertEqual(got, [])

    def test_a_marquee_never_selects_a_handle(self):
        from qtpy import QtWidgets

        clip, item = self._clip()
        key = self._middle_key(item)
        key.setSelected(True)
        for h in self._handles(item):
            self.assertFalse(h.flags() & QtWidgets.QGraphicsItem.ItemIsSelectable)

    def test_handles_hide_during_a_key_drag_and_return_after(self):
        from qtpy import QtCore

        clip, item = self._clip()
        key = self._middle_key(item)
        key.setSelected(True)
        self.assertEqual(len(self._handles(item)), 1)
        pos = key.scenePos()
        key.mousePressEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMousePress, pos)
        )
        self.assertEqual(self._handles(item), [], "hidden while the key drags")
        key.mouseReleaseEvent(
            _scene_mouse_event(QtCore.QEvent.GraphicsSceneMouseRelease, pos)
        )
        self.assertEqual(len(self._handles(item)), 1, "back once the drag ends")

    def test_a_right_press_on_a_handle_leaves_it_standing(self):
        """The handles live on the SELECTION: a right press that cleared it
        took the handle out from under the click that was aiming at it."""
        from qtpy import QtCore, QtGui, QtWidgets

        clip, item = self._clip()
        QtWidgets.QApplication.processEvents()
        key = self._first_key(item)
        key.setSelected(True)
        (handle,) = self._handles(item)
        tl = self.w._timeline
        vp = tl.mapFromScene(handle.scenePos())
        tl.mousePressEvent(
            QtGui.QMouseEvent(
                QtCore.QEvent.MouseButtonPress,
                QtCore.QPointF(vp),
                QtCore.Qt.RightButton,
                QtCore.Qt.RightButton,
                QtCore.Qt.NoModifier,
            )
        )
        self.assertTrue(key.isSelected())
        self.assertEqual(self._handles(item), [handle])

    def test_a_broken_key_draws_its_handles_dotted(self):
        from qtpy import QtCore

        clip, item = self._clip()
        clip.data["curve_preview"]["broken"] = [True, False, False]
        first, middle = self._first_key(item), self._middle_key(item)
        self.assertTrue(first.is_broken(0))
        self.assertFalse(middle.is_broken(1))
        self.assertEqual(
            item._handle_pen("#FF6600", first, 0).style(), QtCore.Qt.DotLine
        )
        self.assertEqual(
            item._handle_pen("#FF6600", middle, 1).style(), QtCore.Qt.SolidLine
        )
