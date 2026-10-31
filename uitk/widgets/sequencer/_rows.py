# !/usr/bin/python
# coding=utf-8
"""The track rows behind :class:`~uitk.widgets.sequencer._sequencer.SequencerWidget`:
the tracks and their clips, the sub-rows a track expands onto, and where every
row lies -- a part the widget holds and publishes (``_sequencer.py``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from uitk.widgets.sequencer._clip import ClipItem
from uitk.widgets.sequencer._data import ClipData, RowMetrics, TrackData
from uitk.widgets.sequencer._draggable import ItemRetirement

if TYPE_CHECKING:
    from uitk.widgets.sequencer._sequencer import SequencerWidget


class _TrackRows:
    """The track rows: the tracks and their clips (data and scene items, under
    ids handed out in order from 0 again after a clear), which tracks are
    expanded onto which sub-rows and the curves drawn behind those, and where
    every row lies under the header (:attr:`metrics`)."""

    def __init__(self, sequencer: "SequencerWidget"):
        self._sequencer = sequencer
        self.tracks: List[TrackData] = []
        self.clips: Dict[int, ClipData] = {}
        self.items: Dict[int, ClipItem] = {}
        self.next_track_id = 0
        self.next_clip_id = 0
        self.expanded: Dict[int, List[str]] = {}  # track_id → sub-row names
        # Row sizes + key style (density); read by iter_rows and the header.
        self.metrics: RowMetrics = RowMetrics.preset("standard")
        self.sub_row_provider = None  # callable(track_id, track_name) → [(sub_name, [(start,dur,label,color), ...]), ...]
        self.bg_curve_previews: Dict[tuple, dict] = {}  # (track_id, sub_row) → preview

    # -- tracks and clips ----------------------------------------------------
    def add_track(
        self,
        name: str,
        icon,
        dimmed: bool,
        italic: bool,
        color: Optional[str],
        text_color: Optional[str],
    ) -> int:
        sq = self._sequencer
        tid = self.next_track_id
        self.next_track_id += 1
        td = TrackData(
            track_id=tid,
            name=name,
            color=color,
            text_color=text_color,
            icon=icon,
            dimmed=dimmed,
            italic=italic,
        )
        self.tracks.append(td)
        sq._header.add_track_label(
            name,
            icon=icon,
            dimmed=dimmed,
            italic=italic,
            color=color,
            text_color=text_color,
        )
        sq.refresh_extent()
        sq._sync_row_bound_items()
        return tid

    def add_clip(
        self,
        track_id: int,
        start: float,
        duration: float,
        label: str,
        color: Optional[str],
        sub_row: str,
        locked: bool,
        data: dict,
    ) -> int:
        sq = self._sequencer
        cid = self.next_clip_id
        self.next_clip_id += 1
        if color is None:
            color = "#CCCCCC"
        cd = ClipData(
            clip_id=cid,
            track_id=track_id,
            start=start,
            duration=duration,
            label=label,
            color=color,
            locked=locked,
            sub_row=sub_row,
            data=data,
        )
        self.clips[cid] = cd

        # register on track
        for td in self.tracks:
            if td.track_id == track_id:
                td.clips.append(cid)
                break

        # create visual item
        item = ClipItem(cd, sq._timeline)
        self.items[cid] = item
        sq.add_track_item(item)
        sq.refresh_extent()
        return cid

    def remove_clip(self, clip_id: int) -> None:
        if clip_id not in self.clips:
            return
        cd = self.clips.pop(clip_id)
        ItemRetirement.retire(self.items.pop(clip_id, None))
        for td in self.tracks:
            if cd.clip_id in td.clips:
                td.clips.remove(cd.clip_id)

    def set_clip_label(self, clip_id: int, label: str) -> None:
        cd = self.clips.get(clip_id)
        if cd is None:
            return
        cd.label = label
        item = self.items.get(clip_id)
        if item:
            item.update()

    def set_clip_locked(self, clip_id: int, locked: bool) -> None:
        cd = self.clips.get(clip_id)
        if cd is None:
            return
        cd.locked = locked
        item = self.items.get(clip_id)
        if item:
            item.sync_selectable()
            item.update()

    def remove_track(self, track_id: int) -> None:
        sq = self._sequencer
        td = None
        for i, t in enumerate(self.tracks):
            if t.track_id == track_id:
                td = t
                self.tracks.pop(i)
                break
        if td is None:
            return
        self.expanded.pop(track_id, None)
        for cid in list(td.clips):
            sq.remove_clip(cid)
        # Also remove sub-row clips
        sub_cids = [
            cid
            for cid, cd in self.clips.items()
            if cd.track_id == track_id and cd.sub_row
        ]
        for cid in sub_cids:
            sq.remove_clip(cid)
        # Drop this track's background curve previews (mirrors
        # collapse) — stale entries keyed to a recycled track_id
        # would paint another object's curve across the wrong row.
        stale_bg = [k for k in self.bg_curve_previews if k[0] == track_id]
        for k in stale_bg:
            del self.bg_curve_previews[k]
        # Rebuild header labels with their FULL stored presentation and
        # re-apply expansion for still-expanded tracks — a plain-name
        # rebuild dropped icons/colors and desynced every row below an
        # expanded track from its header.
        sq._header.clear_tracks()
        for i, t in enumerate(self.tracks):
            sq._header.add_track_label(
                t.name,
                icon=t.icon,
                dimmed=t.dimmed,
                italic=t.italic,
                color=t.color,
                text_color=t.text_color,
            )
            sub_names = self.expanded.get(t.track_id)
            if sub_names:
                sq._header.set_track_expanded(i, sub_names, self.metrics.sub_row_height)
        sq._timeline._refresh_all()

    def get_track(self, track_id: int) -> Optional[TrackData]:
        for td in self.tracks:
            if td.track_id == track_id:
                return td
        return None

    def clips_on(self, track_id: Optional[int]) -> List[ClipData]:
        if track_id is None:
            return list(self.clips.values())
        return [cd for cd in self.clips.values() if cd.track_id == track_id]

    def clip_attributes(self) -> List[str]:
        return sorted(
            {
                attr
                for cd in self.clips.values()
                for attr in cd.data.get("attributes", [])
            }
        )

    def swap_clips(self, clip_id_a: int, clip_id_b: int) -> None:
        sq = self._sequencer
        a = self.clips.get(clip_id_a)
        b = self.clips.get(clip_id_b)
        if a is None or b is None or clip_id_a == clip_id_b:
            return

        # Identify earlier / later by start
        if a.start > b.start:
            a, b = b, a

        gap = b.start - (a.start + a.duration)
        new_b_start = a.start
        new_a_start = a.start + b.duration + gap

        sq._capture_undo()

        a.start = new_a_start
        b.start = new_b_start

        # Refresh visual items
        for cid in (a.clip_id, b.clip_id):
            item = self.items.get(cid)
            if item:
                item._sync_geometry()
                item.update()

        sq.clips_reordered.emit(clip_id_a, clip_id_b)

    def clear(self) -> None:
        """Drop every track and clip (:meth:`SequencerWidget.clear`)."""
        for cid in list(self.clips):
            ItemRetirement.retire(self.items.pop(cid, None))
        self.clips.clear()
        self.tracks.clear()
        self.expanded.clear()
        # Background curve previews are keyed by (track_id, sub_row);
        # with next_track_id reset below, a stale entry would attach to
        # whatever track recycles that id and paint the wrong curve.
        self.bg_curve_previews.clear()
        self._sequencer._header.clear_tracks()
        self.next_track_id = 0
        self.next_clip_id = 0

    # -- sub-rows ------------------------------------------------------------
    def set_metrics(self, metrics: RowMetrics) -> None:
        if not isinstance(metrics, RowMetrics):
            raise TypeError(f"row_metrics takes a RowMetrics, got {metrics!r}")
        if metrics == self.metrics:
            return
        self.metrics = metrics
        self._sequencer._header.apply_metrics(metrics)
        self._sequencer._timeline._refresh_all()

    def expand(self, track_id: int, sub_row_data) -> None:
        sq = self._sequencer
        if sub_row_data is None and self.sub_row_provider:
            td = sq.get_track(track_id)
            if td is None:
                return
            sub_row_data = self.sub_row_provider(track_id, td.name)
        if not sub_row_data:
            return

        sub_names = [name for name, _ in sub_row_data]
        self.expanded[track_id] = sub_names

        # Remove stale sub-row clips for this track
        stale = [
            cid
            for cid, cd in self.clips.items()
            if cd.track_id == track_id and cd.sub_row
        ]
        for cid in stale:
            sq.remove_clip(cid)

        # Create clips for each sub-row
        for sub_name, segments in sub_row_data:
            for seg in segments:
                start, dur = seg[0], seg[1]
                label = seg[2] if len(seg) > 2 else sub_name
                color = seg[3] if len(seg) > 3 else None
                extra = seg[4] if len(seg) > 4 else {}
                sq.add_clip(
                    track_id,
                    start,
                    dur,
                    label=label,
                    color=color,
                    sub_row=sub_name,
                    **extra,
                )

        self.sync_selectability(track_id)
        idx = self.index_of(track_id)
        if idx is not None:
            sq._header.set_track_expanded(idx, sub_names, self.metrics.sub_row_height)
        sq._timeline._refresh_all()
        sq.track_expanded.emit(track_id)

    def set_bg_curve_preview(
        self, track_id: int, sub_row: str, preview: dict, color: str
    ) -> None:
        key = (track_id, sub_row)
        if preview is None:
            self.bg_curve_previews.pop(key, None)
        else:
            self.bg_curve_previews[key] = {"preview": preview, "color": color}
        self._sequencer._timeline.viewport().update()

    def collapse(self, track_id: int) -> None:
        sq = self._sequencer
        if track_id not in self.expanded:
            return
        self.expanded.pop(track_id)
        # Remove background curve previews for this track
        stale_bg = [k for k in self.bg_curve_previews if k[0] == track_id]
        for k in stale_bg:
            del self.bg_curve_previews[k]
        # Remove sub-row clips
        to_remove = [
            cid
            for cid, cd in self.clips.items()
            if cd.track_id == track_id and cd.sub_row
        ]
        for cid in to_remove:
            sq.remove_clip(cid)
        self.sync_selectability(track_id)
        idx = self.index_of(track_id)
        if idx is not None:
            sq._header.set_track_collapsed(idx)
        sq._timeline._refresh_all()
        sq.track_collapsed.emit(track_id)

    def sync_selectability(self, track_id: int) -> None:
        """Re-apply every main-row clip's selectable flag for *track_id*.

        A main-row clip on an expanded track is only a summary of the key
        dots below it (:meth:`ClipItem.is_selectable`), so expansion revokes
        its selection and collapse gives it back.  A selection actually
        dropped is reported once, as a real selection change: the consumer
        mirrors the widget's selection into its host app and would otherwise
        keep showing a bar the user can no longer pick.
        """
        sq = self._sequencer
        dropped = False
        for cd in self.clips.values():
            if cd.track_id != track_id or cd.sub_row:
                continue
            item = self.items.get(cd.clip_id)
            if item is None:
                continue
            was_selected = item.isSelected()
            sq._selection_suppressed += 1
            try:
                item.sync_selectable()
            finally:
                sq._selection_suppressed -= 1
            dropped = dropped or (was_selected and not item.isSelected())
        if dropped and not sq._selection_suppressed:
            sq._on_scene_selection()

    def toggle(self, track_id: int) -> None:
        sq = self._sequencer
        if sq.is_track_expanded(track_id):
            sq.collapse_track(track_id)
        else:
            sq.expand_track(track_id)

    def on_header_expand(self, label_idx: int) -> None:
        """Handle double-click on a header label to toggle expansion."""
        if label_idx < len(self.tracks):
            self._sequencer.toggle_track_expanded(self.tracks[label_idx].track_id)

    # -- where the rows lie --------------------------------------------------
    def iter_rows(self):
        """The rows' layout (:meth:`SequencerWidget._iter_rows`), which every
        row reader below takes through the widget."""
        m = self.metrics
        y = self._sequencer._content_top
        for td in self.tracks:
            yield td, None, y, m.track_height
            y += m.track_height + m.padding
            for sr in self.expanded.get(td.track_id, []):
                yield td, sr, y, m.sub_row_height
                y += m.sub_row_height + m.padding

    def row_position(self, track_id: int, sub_row: str) -> tuple:
        m = self.metrics
        fallback = None
        for td, sr, y, h in self._sequencer._iter_rows():
            if td.track_id != track_id:
                continue
            if not sub_row:
                if sr is None:
                    return y, h
            elif sr == sub_row:
                return y, h
            # Remember the last row of the matching track: a requested
            # sub-row that isn't expanded falls through to just after
            # the track's final row (legacy behavior).
            fallback = (y + h + m.padding, m.sub_row_height)
        if sub_row and fallback is not None:
            return fallback
        # Past the end — first free y after all rows.
        end_y = self._sequencer._content_top
        for _td, _sr, y, h in self._sequencer._iter_rows():
            end_y = y + h + m.padding
        return end_y, m.track_height

    def total_height(self) -> float:
        pad = self.metrics.padding
        h = 0.0
        for _td, _sr, _y, row_h in self._sequencer._iter_rows():
            h += row_h + pad
        return h

    def visual_rows(self) -> List[tuple]:
        return [
            (y, h, sr is not None, td.track_id)
            for td, sr, y, h in self._sequencer._iter_rows()
        ]

    def index_of(self, track_id: int) -> Optional[int]:
        """Return the list index for *track_id*, or None."""
        for i, td in enumerate(self.tracks):
            if td.track_id == track_id:
                return i
        return None

    def content_span(self) -> Tuple[float, float]:
        sq = self._sequencer
        top = sq._content_top
        return top, max(sq._total_row_height(), sq._timeline.viewport().height() - top)
