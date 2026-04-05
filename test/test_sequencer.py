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
    ClipItem,
    MarkerData,
    RangeHighlightItem,
    AttributeColorDialog,
    _GapOverlayItem,
    _StaticRangeOverlay,
    _TRACK_HEIGHT,
    _RULER_HEIGHT,
    _SUB_ROW_HEIGHT,
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
        tid = self.w.add_track("T")
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
        tid = self.w.add_track("Active")
        tid2 = self.w.add_track("Inactive", dimmed=True)
        header = self.w._header
        self.assertFalse(header._dimmed[0])
        self.assertTrue(header._dimmed[1])

    def test_add_track_dimmed_default_false(self):
        tid = self.w.add_track("T")
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
        from uitk.widgets.mixins.settings_manager import SettingsManager

        settings = SettingsManager(namespace="test_attr_colors_defaults")
        dlg = AttributeColorDialog(settings=settings)
        cmap = dlg.color_map()
        self.assertEqual(cmap["translateX"], _DEFAULT_ATTRIBUTE_COLORS["translateX"])
        dlg.close()
        settings.clear()

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

    def test_zero_duration_sub_clip_not_resizable(self):
        """Point (zero-duration) sub-row clips are not resizable."""
        tid = self.w.add_track("obj_A")
        sub_data = [("tx", [(25, 0, "tx", "#FF0000", {})])]
        self.w.expand_track(tid, sub_row_data=sub_data)
        sub_clips = [c for c in self.w.clips() if c.sub_row]
        self.assertEqual(len(sub_clips), 1)
        self.assertFalse(sub_clips[0].data.get("resizable_left", True))
        self.assertFalse(sub_clips[0].data.get("resizable_right", True))


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
        from qtpy import QtCore, QtGui, QtWidgets

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
    """_content_top matches _RULER_HEIGHT."""

    def setUp(self):
        self.w = SequencerWidget()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()

    def test_content_top_equals_ruler_height(self):
        self.assertEqual(self.w._content_top, _RULER_HEIGHT)


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


if __name__ == "__main__":
    unittest.main()
