# !/usr/bin/python
# coding=utf-8
"""Where a :class:`~uitk.widgets.sequencer._sequencer.SequencerWidget`'s
playhead and view go: steps, jumps and framing -- a part the widget holds and
publishes (``_sequencer.py``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uitk.widgets.sequencer._sequencer import SequencerWidget

#: Pixels of margin :meth:`SequencerWidget.frame_shot` leaves on each side.
_FRAME_PADDING = 40
#: A viewport narrower than this is not laid out yet -- framing into it sets a
#: zoom the user then has to undo, so the first-show framing waits for a resize.
_MIN_FRAME_VIEWPORT_WIDTH = _FRAME_PADDING * 3


class _Navigation:
    """Where the playhead and the view go: the playhead's steps and jumps (to
    keys, to the ends), framing a time range or the active shot -- once on
    the first show, as soon as there is a viewport to frame it in -- and the
    view a rebuild puts back."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        # Armed at the end of the widget's construction (see there).
        self.pending_first_frame = False

    # -- the playhead --------------------------------------------------------
    def set_playhead(self, time: float) -> None:
        self._sequencer._timeline._scene.playhead.time = time

    def move_playhead(self, time: float) -> None:
        sq = self._sequencer
        sq._timeline._scene.playhead.time = time
        sq.playhead_moved.emit(sq._timeline._scene.playhead.time)

    def step_forward(self) -> None:
        sq = self._sequencer
        interval = sq.snap_interval
        step = interval if interval > 0 else 1.0
        sq._move_playhead(sq._timeline._scene.playhead.time + step)

    def step_backward(self) -> None:
        sq = self._sequencer
        interval = sq.snap_interval
        step = interval if interval > 0 else 1.0
        # Floored at the timeline's own reach rather than 0 -- stepping back
        # into a shot that lives before the origin is legitimate.
        floor = min(0.0, sq._timeline.content_time_bounds()[0])
        sq._move_playhead(max(floor, sq._timeline._scene.playhead.time - step))

    def key_times(self) -> list:
        sq = self._sequencer
        own = sq.active_editor.key_times()
        if own is not None:
            return own
        times: set = set()
        expanded = sq._expanded_tracks
        for cd in sq._clips.values():
            times.add(cd.start)
            if cd.duration > 0:
                times.add(cd.end)
            # Include keyframe times from expanded sub-row clips.  Keys
            # arrive either as legacy "keyframe_times" or inside a
            # "curve_preview" dict (the form real consumers supply) —
            # without the latter, next/prev-key navigation skips every
            # visible key dot and only lands on clip boundaries.
            if cd.sub_row and cd.track_id in expanded:
                kf = cd.data.get("keyframe_times") or cd.shown_key_times()
                for entry in kf:
                    times.add(entry[0] if isinstance(entry, (list, tuple)) else entry)
        return sorted(times)

    def go_to_next_key(self) -> None:
        sq = self._sequencer
        current = sq._timeline._scene.playhead.time
        for t in sq._key_times():
            if t > current + 0.01:
                sq._move_playhead(t)
                return

    def go_to_prev_key(self) -> None:
        sq = self._sequencer
        current = sq._timeline._scene.playhead.time
        for t in reversed(sq._key_times()):
            if t < current - 0.01:
                sq._move_playhead(t)
                return

    def go_to_end(self) -> None:
        sq = self._sequencer
        sq._move_playhead(max((cd.end for cd in sq._clips.values()), default=0.0))

    # -- the view ------------------------------------------------------------
    def frame_shot(self) -> bool:
        sq = self._sequencer
        rh = sq.range_highlight()
        if rh is not None:
            t_min, t_max = rh
        elif sq._active_range is not None:
            t_min, t_max = sq._active_range
        elif sq._clips:
            t_min = min(cd.start for cd in sq._clips.values())
            t_max = max(cd.end for cd in sq._clips.values())
        else:
            return False
        sq.frame_time_range(t_min, t_max)
        return True

    def frame_time_range(self, t_min: float, t_max: float, fit_values: bool) -> None:
        sq = self._sequencer
        timeline = sq._timeline
        span = max(t_max - t_min, 1.0)
        vp_w = timeline.viewport().width()
        padding = _FRAME_PADDING
        usable = max(vp_w - padding * 2, 1)
        timeline._pixels_per_unit = usable / span
        timeline._refresh_all()
        timeline.horizontalScrollBar().setValue(
            int(timeline.time_to_x(t_min) - padding)
        )
        if fit_values:
            sq.active_editor.frame_values()

    def frame_first_show(self) -> None:
        """Frame the active shot once, as soon as there is something to frame."""
        sq = self._sequencer
        if not (self.pending_first_frame and sq.frame_on_first_show):
            return
        if sq._timeline.viewport().width() < _MIN_FRAME_VIEWPORT_WIDTH:
            return
        if sq.range_highlight() is None and sq._active_range is None and not sq._clips:
            return  # nothing to frame yet; a later show/resize retries
        self.pending_first_frame = False
        sq.frame_shot()

    def viewport_state(self) -> dict:
        sq = self._sequencer
        names = []
        for tid in sq._expanded_tracks:
            td = sq.get_track(tid)
            if td is not None:
                names.append(td.name)
        return {
            "zoom": sq._timeline.pixels_per_unit,
            "h_scroll": sq._timeline.horizontalScrollBar().value(),
            "expanded": names,
        }

    def restore_viewport_state(self, state: dict) -> None:
        timeline = self._sequencer._timeline
        timeline.pixels_per_unit = float(state["zoom"])  # clamps, re-lays out
        timeline.horizontalScrollBar().setValue(int(state["h_scroll"]))
