# !/usr/bin/python
# coding=utf-8
"""ClipItem — draggable, resizable clip rectangle on the timeline."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._timeline import TimelineView

from uitk.widgets.sequencer._data import (
    ClipData,
    SELECTED_ACCENT,
    _MIN_POINT_CLIP_WIDTH,
    _MIN_CLIP_DURATION,
    _HANDLE_WIDTH,
    MenuUtils,
    CurveUtils,
    PatternRegistry,
    HATCH_DENSE,
)
from uitk.widgets.sequencer._keyframe import KeyframeItem
from uitk.widgets.sequencer._drag_tooltip import FrameTooltip
from uitk.widgets.sequencer._draggable import DraggableItemMixin
from uitk.managers.cursor_manager import CursorManager


class ClipItem(DraggableItemMixin, QtWidgets.QGraphicsRectItem):
    """A draggable, resizable rectangle representing one clip on the timeline."""

    def __init__(self, clip_data: ClipData, timeline: "TimelineView"):
        super().__init__()
        self._data = clip_data
        self._timeline = timeline
        self._drag_mode = None  # "move", "resize_left", "resize_right"
        # The zone a press landed on, held until the pointer proves it meant
        # to drag rather than click; see _arm_drag.
        self._pending_zone = None
        self._press_screen_pos = None
        self._drag_origin_x = 0.0
        self._drag_origin_start = 0.0
        self._drag_origin_duration = 0.0
        self._drag_peers: list = []  # [(ClipItem, original_start), ...]
        # Group resize: [(ClipItem, original_start, original_duration), ...]
        # plus the fixed edge the whole selection scales about.
        self._resize_peers: list = []
        self._scale_anchor: float = 0.0
        self._scale_limits: tuple = (0.0, float("inf"))
        self._drag_tooltip = FrameTooltip()
        self._waveform_pixmap: Optional[QtGui.QPixmap] = None
        self._waveform_pixmap_size: Optional[tuple] = None
        self._keyframe_items: list = []  # KeyframeItem children for sub-rows
        self._tangent_handle_items: list = []  # TangentHandleItem children
        self._align_times = None  # alignment candidates, resolved on first move
        self._align_hit: bool = False  # drag currently sits on a key frame
        self._keys_dragging = False  # True while any child KeyframeItem is mid-drag
        self._press_modifiers = QtCore.Qt.NoModifier  # chord of the live press
        self.setAcceptHoverEvents(True)
        self.setFlags(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.sync_selectable()
        # Dimmed (non-active shot) clips sit behind active clips
        if clip_data.data.get("dimmed"):
            self.setZValue(-0.5)
        # Sub-row clips show label as tooltip instead of inline text
        if clip_data.sub_row and clip_data.label:
            self.setToolTip(clip_data.label)
        self._sync_geometry()

    def _snap(self, value: float) -> float:
        return DraggableItemMixin.snap_time(value, self._timeline)

    # -- data access --------------------------------------------------------
    @property
    def clip_data(self) -> ClipData:
        return self._data

    def is_selectable(self) -> bool:
        """Whether a click or a marquee may select this clip.

        Three things take the flag away, and all three say the same thing --
        "this bar is not the handle for what you are pointing at":

        * a **sub-row** clip, whose interaction is its
          :class:`~uitk.widgets.sequencer._keyframe.KeyframeItem` children;
        * a **locked** clip, which refuses every edit;
        * a clip on an **expanded** track.  Expanding puts every key of that
          object on screen as its own dot, and the merged bar above them is
          then only a summary: selecting it hands the consumer the WHOLE
          span when the visible thing the user is working on is a key.
        """
        cd = self._data
        if cd.sub_row or cd.locked:
            return False
        return not self._timeline.parent_sequencer.is_track_expanded(cd.track_id)

    def sync_selectable(self) -> None:
        """Re-apply :meth:`is_selectable`, dropping a selection it revokes."""
        selectable = self.is_selectable()
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, selectable)
        if not selectable and self.isSelected():
            self.setSelected(False)

    @property
    def keys_editable(self) -> bool:
        """False when this clip is locked or read-only.

        Its keys may still be SELECTED -- a consumer mirrors the selection
        into its host app, and a marquee sweeps whatever it covers -- but
        never dragged, retangented or deleted through the widget: a
        read-only row is drawn dimmed and locked to say exactly that, and
        an edit from here would be written straight into the host.
        """
        return not (self._data.locked or self._data.data.get("read_only"))

    # -- geometry sync ------------------------------------------------------
    def _sync_geometry(self):
        """Recalculate rect from data using the timeline's mapper."""
        tl = self._timeline
        x = tl.time_to_x(self._data.start)
        w = tl.time_to_x(self._data.start + self._data.duration) - x
        widget = tl.parent_sequencer
        track_y, row_h = widget._row_position(self._data.track_id, self._data.sub_row)
        # Zero-duration (point) clips get a minimum visual width, centered
        if w < _MIN_POINT_CLIP_WIDTH:
            x -= (_MIN_POINT_CLIP_WIDTH - w) / 2.0
            w = _MIN_POINT_CLIP_WIDTH
        new_rect = QtCore.QRectF(x, track_y, max(w, 1), row_h)
        # Invalidate waveform cache when width changes (zoom/resize)
        if self.rect().width() != new_rect.width():
            self._waveform_pixmap = None
        self.setRect(new_rect)
        self._sync_keyframe_items()

    def _sync_keyframe_items(self):
        """Create, destroy, or reposition :class:`KeyframeItem` children.

        Called from :meth:`_sync_geometry` on every zoom / scroll / data
        refresh.  Only sub-row clips with a ``curve_preview`` get children.
        """
        if not self._data.sub_row:
            return

        # If any child key -- or a tangent handle -- is mid-drag, skip the
        # rebuild to avoid destroying active drag state.  Just reposition
        # the existing items.
        if self._keys_dragging or any(h._dragging for h in self._tangent_handle_items):
            for ki in self._keyframe_items:
                ki._reposition()
            self._sync_tangent_handles()
            return

        preview = self._data.data.get("curve_preview") or {}
        keys = preview.get("keys", [])  # [(t, v), ...]
        segments = preview.get("segments", [])

        # Build a comparable fingerprint to decide rebuild vs reposition.
        new_fp = tuple((t, v) for t, v, *_ in keys)
        old_fp = tuple((k._time, k._value) for k in self._keyframe_items)

        if new_fp != old_fp:
            # Tear down old items — through ItemRetirement.retire, because this runs
            # from _sync_geometry which a consumer rebuild can reach while a
            # child's own event is still on the stack; and under selection
            # suppression, because removing a selected key dot fires
            # selectionChanged which must not read as a user deselection.
            from uitk.widgets.sequencer._draggable import ItemRetirement

            sq = self._timeline.parent_sequencer
            sq._selection_suppressed += 1
            # Detach BOTH lists before retiring anything.  Taking a selected
            # dot out of the scene can reach back into this clip -- a tangent
            # resync, a repaint -- and whatever it finds must be the NEW
            # (empty) state, never a list still naming items that are on
            # their way out.  Walking one of those was a read of an object
            # Qt had already finished with.
            retiring = self._tangent_handle_items + self._keyframe_items
            self._tangent_handle_items = []
            self._keyframe_items = []
            try:
                for item in retiring:
                    ItemRetirement.retire(item)
            finally:
                sq._selection_suppressed -= 1

            # Create new items
            for idx, key_data in enumerate(keys):
                t, v = key_data[0], key_data[1]
                # Derive stepped from the segment that starts at this key
                is_stepped = False
                if idx < len(segments):
                    is_stepped = segments[idx].get("out_type") in ("step", "stepnext")
                ki = KeyframeItem(t, v, is_stepped, self)
                self._keyframe_items.append(ki)

        # (Re)position all items and hide bounding keys that fall
        # outside the clip's time range (build_curve_preview includes
        # one extra key on each side for curve continuity).
        start = self._data.start
        end = start + self._data.duration
        eps = 0.5
        for ki in self._keyframe_items:
            ki._reposition()
            in_range = (start - eps) <= ki._time <= (end + eps)
            ki.setVisible(in_range)
            ki.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, in_range)
        self._sync_tangent_handles()

    def _sync_tangent_handles(self):
        """Give every selected, visible key its :class:`TangentHandleItem`
        grab points, and take them from every other key.

        Repositions in place when the wanted set is unchanged (zoom, scroll,
        a key drag ending), rebuilds otherwise.  Nothing while a key drag is
        live -- the preview is being re-timed under the keys -- and never
        while a handle itself is being dragged.
        """
        from uitk.widgets.sequencer._draggable import ItemRetirement
        from uitk.widgets.sequencer._keyframe import TangentHandleItem

        if any(h._dragging for h in self._tangent_handle_items):
            return
        wanted = []
        if not self._keys_dragging:
            for idx, ki in enumerate(self._keyframe_items):
                # A dot already out of the scene is on its way to being
                # destroyed; asking it anything is a read of a dead object.
                if ki.scene() is None:
                    continue
                if not ki.isSelected() or not ki.isVisible():
                    continue
                for side, seg_i, cp_key in ki._tangent_slots(idx):
                    wanted.append((ki, side, seg_i, cp_key))
        if wanted == [h.slot() for h in self._tangent_handle_items]:
            for h in self._tangent_handle_items:
                h._reposition()
            return
        for h in self._tangent_handle_items:
            ItemRetirement.retire(h)
        self._tangent_handle_items = [TangentHandleItem(*w) for w in wanted]

    def boundingRect(self):
        base = super().boundingRect()
        # During key drag, expand bounds to include dragged key
        # positions so Qt doesn't clip the expanded background / curve.
        if not self._keys_dragging:
            return base
        left = base.left()
        right = base.right()
        pad = KeyframeItem._DOT_RADIUS + 2
        for ki in self._keyframe_items:
            if ki.isVisible():
                kx = ki.pos().x()
                left = min(left, kx - pad)
                right = max(right, kx + pad)
        return QtCore.QRectF(left, base.top(), right - left, base.height())

    def _drag_adjusted_segments(self, segments, keys):
        """Return segments with times scaled to current KeyframeItem positions.

        If no keys have moved, returns *segments* unchanged (no copy).
        Bézier control-point times are linearly remapped within each
        segment's new time span.
        """
        items = self._keyframe_items
        if not items or len(items) != len(keys):
            return segments

        # Quick check: did any key actually move?
        moved = False
        for ki, key in zip(items, keys):
            if abs(ki._time - key[0]) > 1e-6:
                moved = True
                break
        if not moved:
            return segments

        # Build adjusted copies
        new_segs = []
        for i, seg in enumerate(segments):
            ns = dict(seg)
            new_t0 = items[i]._time
            new_t1 = items[i + 1]._time
            orig_t0 = seg["t0"]
            orig_t1 = seg["t1"]
            orig_span = orig_t1 - orig_t0
            new_span = new_t1 - new_t0

            ns["t0"] = new_t0
            ns["t1"] = new_t1

            # Scale control-point times proportionally
            if abs(orig_span) > 1e-9:
                for cp_key in ("cp1", "cp2"):
                    cp = seg.get(cp_key)
                    if cp is not None:
                        frac = (cp[0] - orig_t0) / orig_span
                        ns[cp_key] = (new_t0 + frac * new_span, cp[1])

            new_segs.append(ns)

        return new_segs

    def _resolve_color(self) -> QtGui.QColor:
        """Resolve clip color from attributes.

        Uses the attribute color map only when every attribute on the clip
        resolves to the *same* color (e.g. a single-attribute clip or a
        group where all attrs share a color).  Mixed-attribute clips use
        the 'consolidated' color (default white) to indicate that multiple
        attributes are combined.  Attributes not present in the color map
        are treated as having their own unique implicit color, so a clip
        with both a known and unknown attribute is always consolidated.
        """
        attrs = self._data.data.get("attributes")
        if attrs:
            color_map = self._timeline.parent_sequencer.attribute_colors
            resolved = [color_map.get(a) for a in attrs]
            known = {c for c in resolved if c is not None}
            has_unknown = None in resolved
            if len(known) == 1 and not has_unknown:
                return QtGui.QColor(known.pop())
            if known or (has_unknown and len(attrs) > 1):
                return QtGui.QColor(color_map.get("consolidated", "#FFFFFF"))
        return QtGui.QColor(self._data.color or "#CCCCCC")

    @staticmethod
    def _foreground_for(color: QtGui.QColor) -> QtGui.QColor:
        """Return black or white depending on the background luminance."""
        lum = 0.299 * color.redF() + 0.587 * color.greenF() + 0.114 * color.blueF()
        return QtGui.QColor("#1E1E1E") if lum > 0.55 else QtGui.QColor("#FFFFFF")

    #: Alpha of the accent wash a selected clip's fill is tinted with.  Low
    #: enough that the clip's own colour still identifies it, high enough that
    #: the tint reads on the pale fills that dominate a real scene.
    _SELECTED_TINT_ALPHA = 90

    @staticmethod
    def _selected_fill(color: QtGui.QColor) -> QtGui.QColor:
        """*color* tinted toward the selection accent.

        Selection used to be ``color.lighter(130)``, which is a NO-OP on white
        -- and white is exactly what a mixed-attribute clip resolves to (the
        'consolidated' colour), i.e. most clips in a real scene.  Blending
        toward the accent instead is visible on every fill, including the ones
        already at full brightness, and matches the blue the ruler marks the
        selected shot in.

        Deliberately not routed through ``StyleSheet._blend``: that one exists
        to assemble QSS token STRINGS (it parses and re-formats ``rgb()`` /
        ``#hex``), and round-tripping a ``QColor`` through text on every
        repaint is the wrong shape for a paint path.  Same arithmetic,
        different representation.
        """
        accent = QtGui.QColor(SELECTED_ACCENT)
        a = ClipItem._SELECTED_TINT_ALPHA / 255.0
        out = QtGui.QColor(color)
        out.setRed(int(round(color.red() * (1 - a) + accent.red() * a)))
        out.setGreen(int(round(color.green() * (1 - a) + accent.green() * a)))
        out.setBlue(int(round(color.blue() * (1 - a) + accent.blue() * a)))
        return out

    def _paint_selection_outline(self, painter: QtGui.QPainter, rect) -> None:
        """Ring a selected clip in the shared accent.

        The outline carries the selection on its own, so the cue survives the
        cases the fill tint cannot reach: a curve-preview sub-row (which paints
        a graph, not a filled bar) and a clip narrow enough that its interior
        is a few pixels wide.  Drawn INSIDE the rect so neighbouring clips
        can't overdraw it.
        """
        pen = QtGui.QPen(QtGui.QColor(SELECTED_ACCENT), 2.0)
        pen.setJoinStyle(QtCore.Qt.MiterJoin)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(QtCore.QRectF(rect).adjusted(1.0, 1.0, -1.0, -1.0))
        painter.restore()

    # -- painting -----------------------------------------------------------
    def paint(self, painter: QtGui.QPainter, option, widget=None):
        rect = self.rect()
        color = self._resolve_color()
        if self._data.data.get("dimmed"):
            color = color.darker(250)
        selected = self.isSelected()
        if selected:
            color = self._selected_fill(color)

        fg = self._foreground_for(color)

        # Curve-preview mode for sub-row clips: draw a mini normalised
        # graph-editor view (Bézier curves + key dots).
        preview = self._data.data.get("curve_preview")
        if self._data.sub_row and preview:
            # Dim hold clips (flat-key spans shown via "Show Internal Holds")
            if self._data.data.get("is_hold"):
                color = QtGui.QColor(color.darker(180))
                color.setAlpha(100)
            self._paint_curve_preview(painter, rect, preview, color, fg)
            # Lock indicator still needed on sub-rows
            if (
                self._data.locked
                and not self._data.data.get("read_only")
                and rect.width() > 14
                and rect.height() > 10
            ):
                self._paint_lock_icon(painter, rect, fg)
            if selected:
                self._paint_selection_outline(painter, rect)
            return

        painter.setBrush(color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(rect)

        if self._data.pattern is not None:
            PatternRegistry.paint_pattern(painter, rect, self._data.pattern)

        # Interpolated-motion overlay (no physical keys in this shot)
        if self._data.data.get("interpolated"):
            hc = QtGui.QColor(color.darker(180))
            hc.setAlpha(90)
            painter.fillRect(
                rect, PatternRegistry.pattern_brush("diagonal", hc, HATCH_DENSE)
            )

        # Status tint overlay (assessment severity from shot manifest)
        status_hex = self._data.data.get("status_color")
        if status_hex:
            sc = QtGui.QColor(status_hex)
            sc.setAlpha(50)
            painter.setBrush(sc)
            painter.drawRect(rect)

        # Waveform overlay (if envelope data is present)
        waveform = self._data.data.get("waveform")
        if waveform and rect.width() > 4:
            self._paint_waveform(painter, rect, waveform, color)

        # Label — center label (abbreviated attrs) always shown;
        # edge frame numbers only appear during drag operations.
        lbl_center = self._data.data.get("label_center", "")
        w = rect.width()
        dragging = self._drag_mode is not None
        has_label = lbl_center or dragging or self._data.label
        if has_label:
            painter.setPen(fg)
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            fm = painter.fontMetrics()
            pad = 4
            text_rect = rect.adjusted(pad, 0, -pad, 0)
            tw = text_rect.width()

            left_used = 0.0
            right_used = 0.0

            # Edge frame numbers — only during drag/resize
            if dragging and w > 40:
                lbl_left = str(round(self._data.start))
                lbl_right = str(round(self._data.start + self._data.duration))
                left_w = fm.horizontalAdvance(lbl_left)
                left_used = left_w + pad
                left_rect = QtCore.QRectF(
                    text_rect.left(),
                    text_rect.top(),
                    min(left_w, tw * 0.4),
                    text_rect.height(),
                )
                painter.drawText(
                    left_rect,
                    QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                    lbl_left,
                )
                right_w = fm.horizontalAdvance(lbl_right)
                right_used = right_w + pad
                right_rect = QtCore.QRectF(
                    text_rect.right() - min(right_w, tw * 0.4),
                    text_rect.top(),
                    min(right_w, tw * 0.4),
                    text_rect.height(),
                )
                painter.drawText(
                    right_rect,
                    QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight,
                    lbl_right,
                )

            # Center label — during drag show frame count, otherwise
            # show abbreviated attribute names.
            center_text = lbl_center
            if dragging:
                center_text = f"{round(self._data.duration)}f"
            if center_text and tw > 0:
                avail = tw - left_used - right_used
                if avail > fm.horizontalAdvance(".."):
                    center_rect = QtCore.QRectF(
                        text_rect.left() + left_used,
                        text_rect.top(),
                        avail,
                        text_rect.height(),
                    )
                    elided = fm.elidedText(
                        center_text, QtCore.Qt.ElideRight, int(avail)
                    )
                    painter.drawText(
                        center_rect,
                        QtCore.Qt.AlignVCenter | QtCore.Qt.AlignHCenter,
                        elided,
                    )
            elif not lbl_center and not dragging and w > 30 and self._data.label:
                painter.drawText(
                    text_rect,
                    QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                    self._data.label,
                )

        # Lock indicator (skip for read-only clips from non-active shots)
        if (
            self._data.locked
            and not self._data.data.get("read_only")
            and rect.width() > 14
            and rect.height() > 10
        ):
            self._paint_lock_icon(painter, rect, fg)

        # Last, so nothing painted above (pattern, status tint, waveform,
        # label) can sit on top of the selection ring.
        if selected:
            self._paint_selection_outline(painter, rect)

    def _paint_lock_icon(self, painter, rect, fg=None):
        """Draw a small lock glyph at the right edge of the clip."""
        if fg is None:
            fg = QtGui.QColor("#FFFFFF")
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        # Position at top-right
        ix = rect.right() - 12
        iy = rect.top() + 3
        painter.setPen(QtGui.QPen(fg, 1.2))
        painter.setBrush(QtCore.Qt.NoBrush)
        # Shackle arc
        painter.drawArc(
            QtCore.QRectF(ix + 1, iy, 6, 6),
            0 * 16,
            180 * 16,
        )
        # Body rectangle
        painter.setBrush(fg)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(QtCore.QRectF(ix, iy + 4, 8, 6))
        painter.restore()

    def _paint_waveform(self, painter, rect, waveform, base_color):
        """Render a waveform envelope inside the clip rectangle.

        The waveform is pre-rendered to a QPixmap and cached.  The cache
        is invalidated when the clip width changes (zoom/resize).
        """
        n_bins = len(waveform)
        if n_bins == 0:
            return

        w = int(rect.width() - 2)
        h = int(rect.height() - 4)
        if w < 1 or h < 1:
            return

        size_key = (w, h)
        if self._waveform_pixmap is None or self._waveform_pixmap_size != size_key:
            self._waveform_pixmap = self._render_waveform_pixmap(
                waveform, w, h, base_color
            )
            self._waveform_pixmap_size = size_key

        painter.drawPixmap(
            QtCore.QPointF(rect.x() + 1, rect.y() + 2),
            self._waveform_pixmap,
        )

    @staticmethod
    def _render_waveform_pixmap(waveform, w, h, base_color):
        """Pre-render waveform lines into a transparent QPixmap."""
        pixmap = QtGui.QPixmap(w, h)
        pixmap.fill(QtCore.Qt.transparent)

        n_bins = len(waveform)
        cy = h / 2.0

        wave_color = base_color.lighter(170)
        wave_color.setAlpha(200)

        p = QtGui.QPainter(pixmap)
        p.setPen(QtGui.QPen(wave_color, 1))

        for col in range(w):
            idx = min(int(col * n_bins / w), n_bins - 1)
            lo, hi = waveform[idx]
            y_top = cy - hi * (h / 2)
            y_bot = cy - lo * (h / 2)
            p.drawLine(QtCore.QPointF(col, y_top), QtCore.QPointF(col, y_bot))

        p.end()
        return pixmap

    def _paint_curve_preview(self, painter, rect, preview, color, fg):
        """Draw a normalised mini graph-editor view inside a sub-row clip.

        Parameters
        ----------
        preview : dict
            ``{keys, segments, val_min, val_max}`` produced by
            ``build_curve_preview`` on the controller side.
        color : QColor
            Resolved attribute colour.
        fg : QColor
            Foreground (text) colour contrasting with *color*.
        """
        keys = preview.get("keys", [])
        segments = preview.get("segments", [])
        val_min = preview.get("val_min", 0.0)
        val_max = preview.get("val_max", 1.0)

        # During key drag, expand the paint area to cover all visible
        # key positions so the background tint follows the curve.
        paint_rect = rect
        if self._keys_dragging and self._keyframe_items:
            left = rect.left()
            right = rect.right()
            for ki in self._keyframe_items:
                if ki.isVisible():
                    kx = ki.pos().x()
                    left = min(left, kx - 2)
                    right = max(right, kx + 2)
            if right > left:
                paint_rect = QtCore.QRectF(
                    left, rect.top(), right - left, rect.height()
                )

        # --- background tint ---
        bar_color = QtGui.QColor(color)
        bar_color.setAlpha(60)
        painter.setBrush(bar_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(paint_rect)

        if not segments:
            return

        # If keyframe items are being dragged, adjust segment times to
        # follow the current key positions so the curve updates live.
        segments = self._drag_adjusted_segments(segments, keys)

        # --- coordinate mapping helpers ---
        # During any drag, lock the time→pixel mapping to the pre-drag
        # values.  Move: keeps the curve's local pixel coords fixed so
        # it travels with the widget.  Resize: the original fractions
        # applied to the growing/shrinking rect produce a proportional
        # stretch that matches what scaleKey will do on release
        # (new_t = anchor + (t - anchor) * new_dur / old_dur).
        if self._drag_mode is not None:
            map_start = self._drag_origin_start
            map_dur = self._drag_origin_duration
        else:
            map_start = self._data.start
            map_dur = self._data.duration

        def map_x(t):
            if map_dur > 1e-6:
                frac = (t - map_start) / map_dur
            else:
                frac = 0.5
            return rect.x() + frac * rect.width()

        map_y, _is_flat = CurveUtils.make_value_mapper(
            rect.top(), rect.height(), val_min, val_max
        )

        # --- draw curve path (clipped to paint_rect so dragged curves remain visible) ---
        painter.save()
        painter.setClipRect(paint_rect)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        curve_color = QtGui.QColor(color)
        curve_color.setAlpha(180)
        painter.setPen(QtGui.QPen(curve_color, 1.2))
        painter.setBrush(QtCore.Qt.NoBrush)

        painter.drawPath(CurveUtils.build_curve_path(segments, map_x, map_y))
        self._paint_tangent_handles(painter, curve_color)

        painter.restore()
        # Key dots are rendered by KeyframeItem children (un-cropped).

    def _paint_tangent_handles(self, painter, color):
        """Draw the IN/OUT handle LINES of every SELECTED key over the curve.

        Painted here rather than by the key dot: a handle lies on the curve
        this clip draws, inside this clip's rect, so nothing has to grow --
        a key dot whose rect swelled on selection fell inside marquees it
        was never under.  The grab points at the ends are
        :class:`TangentHandleItem` children (:meth:`_sync_tangent_handles`),
        so they can be dragged; the dots repaint the clip when their
        selection changes (:meth:`KeyframeItem.itemChange`).
        """
        for idx, ki in enumerate(self._keyframe_items):
            if not ki.isSelected():
                continue
            # The index rides along: a per-key scan would make a select-all
            # on a long curve quadratic on every repaint.
            painter.setPen(self._handle_pen(color, ki, idx))
            root = ki.pos()
            for p in ki._tangent_handles(idx):
                painter.drawLine(root, p)

    @staticmethod
    def _handle_pen(color, key, index: int) -> QtGui.QPen:
        """The pen a key's handle lines are drawn with: dotted when its
        tangents are broken (:meth:`KeyframeItem.is_broken`), solid when
        unified -- the Graph Editor's own convention."""
        pen = QtGui.QPen(QtGui.QColor(color).lighter(150), 1.0)
        if key.is_broken(index):
            pen.setStyle(QtCore.Qt.DotLine)
        return pen

    # -- hover cursor -------------------------------------------------------
    def hoverMoveEvent(self, event):
        if self._data.locked or self._data.sub_row:
            self.setCursor(QtCore.Qt.ArrowCursor)
            super().hoverMoveEvent(event)
            return
        zone = self._hit_zone(event.pos())
        if zone in ("resize_left", "resize_right"):
            self.setCursor(QtCore.Qt.SizeHorCursor)
        else:
            # No hand over the body.  A press here is a SELECTION until the
            # pointer travels far enough to mean a drag (see ``_arm_drag``),
            # so advertising the grab on hover made every plain click look
            # like one -- reported as clicking a clip not feeling "smooth".
            # The closed hand appears when the drag actually arms.
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    # -- selection ----------------------------------------------------------
    def _set_sole_selection(self) -> None:
        """Make this the only selected item, emitting ONE ``selectionChanged``.

        ``clearSelection()`` and ``setSelected()`` fire the scene's signal
        separately, and every consumer does real work on each one -- the Maya
        adapter mirrors the selection into the scene and reopens the Graph
        Editor -- so the pair costs twice what it should on every click.
        Block, then re-emit once: the idiom the marquee already uses.
        """
        scene = self.scene()
        if scene is None:
            self.setSelected(True)
            return
        was_blocked = scene.signalsBlocked()
        scene.blockSignals(True)
        try:
            scene.clearSelection()
            self.setSelected(True)
        finally:
            scene.blockSignals(was_blocked)
        # A caller that had already blocked the scene wants silence, not one
        # emission from us — restore its state and let it decide.
        if not was_blocked:
            scene.selectionChanged.emit()

    def _press_selection(self, modifiers) -> None:
        """Selection half of a left-press on this clip.

        ``QGraphicsItem``'s own implementation never runs here (the drag needs
        the press, so this class accepts the event itself), which is why a
        plain click used to leave the clip UNSELECTED -- selection was
        reachable only by rubber-band.  The modifiers follow the sequencer's
        marquee, so the same chord means the same thing however the user picks
        clips:

        * ``Alt`` (or ``Ctrl``) -- remove this clip from the selection;
        * ``Shift`` -- add it (a no-op when it is already in);
        * neither   -- make it the selection, UNLESS it is already part of a
          multi-selection.  Collapsing on press would make a group impossible
          to drag; the collapse happens on release instead, and only when the
          press turned out to be a click rather than a drag (see
          :meth:`_release_selection`).
        """
        if not (self.flags() & QtWidgets.QGraphicsItem.ItemIsSelectable):
            return
        if modifiers & (QtCore.Qt.AltModifier | QtCore.Qt.ControlModifier):
            self.setSelected(False)
        elif modifiers & QtCore.Qt.ShiftModifier:
            self.setSelected(True)
        elif not self.isSelected():
            self._set_sole_selection()

    def _release_selection(self, modifiers, moved: bool) -> None:
        """Collapse a multi-selection when an unmodified press was a CLICK.

        Deferred from the press so a group drag keeps its members; once it is
        clear the user did not drag, clicking one clip of a group means "just
        this one", the same as it does in every NLE.
        """
        if moved or modifiers & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
            return
        if not (self.flags() & QtWidgets.QGraphicsItem.ItemIsSelectable):
            return
        scene = self.scene()
        if scene is None or len(scene.selectedItems()) <= 1:
            return
        self._set_sole_selection()

    # -- drag interaction ---------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._press_modifiers = event.modifiers()
            self._press_selection(event.modifiers())
            if self._data.locked or self._data.sub_row:
                # Sub-row keys are dragged by KeyframeItem children.
                super().mousePressEvent(event)
                return
            # The press SELECTS.  It does not grab: the zone is remembered
            # and the drag is armed on the first move that clears Qt's own
            # drag threshold (:meth:`_arm_drag`).  Grabbing here made every
            # single click flicker through a whole drag -- closed-hand
            # cursor, drag frame labels, a tooltip -- before the selection it
            # was actually asking for had even been drawn.
            self._pending_zone = self._hit_zone(event.pos())
            self._press_screen_pos = event.screenPos()
            self._drag_mode = None
            self._drag_peers = []
            self._resize_peers = []
            self._drag_origin_x = event.scenePos().x()
            self._drag_origin_start = self._data.start
            self._drag_origin_duration = self._data.duration
            sq = self._timeline.parent_sequencer
            sq.record_press_modifiers(event.modifiers())
            # Alignment candidates are resolved lazily on the first real
            # move (next to the undo capture below): the set can't change
            # mid-gesture, but resolving it here would make every plain
            # selection click walk each clip and key for nothing.
            self._align_times = None
            # Undo snapshot is captured lazily on the first real move —
            # capturing on press meant every selection click pushed a
            # no-op undo entry and wiped the redo stack.
            self._undo_captured = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def _arm_drag(self, event) -> None:
        """Enter the drag the press only intended, now that it is one."""
        self._drag_mode = self._pending_zone
        self._pending_zone = None
        # Peers are read HERE, not at press: the press may have changed the
        # selection, and this is the set the drag actually moves.  Nothing
        # has moved yet, so their origins are still the pre-drag values.
        self._drag_peers = []
        self._resize_peers = []
        if self._drag_mode == "move" and self.isSelected():
            for item in self._timeline._scene.selectedItems():
                if (
                    isinstance(item, ClipItem)
                    and item is not self
                    and not item._data.locked
                ):
                    self._drag_peers.append((item, item._data.start))
                    # Propagate drag state so peer curve previews
                    # also lock to their pre-drag positions.
                    item._drag_mode = "move"
                    item._drag_origin_start = item._data.start
                    item._drag_origin_duration = item._data.duration
        elif self._drag_mode in ("resize_left", "resize_right") and self.isSelected():
            self._arm_group_scale()
        CursorManager.push(self, QtCore.Qt.ClosedHandCursor)
        self.update()  # repaint to show drag frame labels
        self._show_clip_drag_tooltip(event.scenePos())

    def _arm_group_scale(self) -> None:
        """Prepare an edge drag to scale the WHOLE selection as one unit.

        Dragging one clip's edge while several are selected is a request to
        retime the selection, not to resize the one clip under the hand: the
        set keeps its shape and its internal spacing, and only its overall
        length changes.  The fixed point is the selection's FAR edge (its
        earliest start for a right-edge drag, its latest end for a left-edge
        one), so the grabbed edge is the one that travels.

        Nothing is armed for a lone clip -- :meth:`mouseMoveEvent` then takes
        the single-clip path unchanged.
        """
        members = [
            item
            for item in self._timeline._scene.selectedItems()
            if isinstance(item, ClipItem)
            and item is not self
            and not item._data.locked
            and not item._data.sub_row
        ]
        if not members:
            return
        self._resize_peers = [(m, m._data.start, m._data.duration) for m in members]
        starts = [self._drag_origin_start] + [o for _m, o, _d in self._resize_peers]
        ends = [self._drag_origin_start + self._drag_origin_duration] + [
            o + d for _m, o, d in self._resize_peers
        ]
        self._scale_anchor = (
            min(starts) if self._drag_mode == "resize_right" else max(ends)
        )
        # Legal scale range: no member may shrink below the minimum clip
        # duration, and a left-edge drag may not pull the earliest member
        # back through frame 0.
        durations = [self._drag_origin_duration] + [
            d for _m, _o, d in self._resize_peers
        ]
        lo = max([_MIN_CLIP_DURATION / d for d in durations if d > 1e-9] or [0.0])
        hi = float("inf")
        if self._drag_mode == "resize_left":
            lead = min(starts)
            reach = self._scale_anchor - lead
            # Only a selection that currently sits at or after frame 0 gets
            # the frame-0 ceiling -- the same clamp the single-clip path
            # applies.  A shot padded before 0 already reaches back there,
            # and measuring the ceiling from ITS lead would pin the scale at
            # its floor and collapse the whole group on the first move.
            if lead >= 0.0 and reach > 1e-9:
                hi = self._scale_anchor / reach
        self._scale_limits = (lo, max(lo, hi))
        # Peers paint their drag state too, so their curve previews lock to
        # pre-drag positions the way a group MOVE already makes them.
        for m, _o, _d in self._resize_peers:
            m._drag_mode = self._drag_mode
            m._drag_origin_start = m._data.start
            m._drag_origin_duration = m._data.duration

    def _apply_group_scale(self) -> None:
        """Scale the selection about :attr:`_scale_anchor` from this clip's edge.

        The grabbed edge sets the ratio -- it has already been snapped,
        aligned and clamped by the single-clip path -- and every member,
        this one included, is then re-derived from that one number so the
        set cannot drift out of proportion over a long drag.
        """
        anchor = self._scale_anchor
        right = self._drag_mode == "resize_right"
        if right:
            denom = self._drag_origin_start + self._drag_origin_duration - anchor
            reach = self._data.start + self._data.duration - anchor
        else:
            denom = anchor - self._drag_origin_start
            reach = anchor - self._data.start
        if abs(denom) < 1e-9:
            return
        lo, hi = self._scale_limits
        scale = min(max(reach / denom, lo), hi)
        for item, o_start, o_dur in [
            (self, self._drag_origin_start, self._drag_origin_duration)
        ] + self._resize_peers:
            if right:
                item._data.start = anchor + (o_start - anchor) * scale
            else:
                item._data.start = anchor - (anchor - o_start) * scale
            item._data.duration = o_dur * scale
            if item is not self:
                item._sync_geometry()
                item.update()

    def mouseMoveEvent(self, event):
        if self._drag_mode is None:
            if self._pending_zone is None:
                return super().mouseMoveEvent(event)
            if not self._past_drag_threshold(event):
                event.accept()  # still a click, as far as anyone can tell
                return
            self._arm_drag(event)

        if not getattr(self, "_undo_captured", False):
            self._undo_captured = True
            self._timeline.parent_sequencer._capture_undo()

        if self._align_times is None:
            sq = self._timeline.parent_sequencer
            moving_ids = {self._data.clip_id}
            moving_ids.update(p._data.clip_id for p, _ in self._drag_peers)
            # Pre-drag spans of the moving content: the DCC panels represent
            # one object's animation as a merged bar PLUS per-attribute
            # sub-row clips, so excluding by clip id alone leaves the other
            # representation behind as a stale magnet at the origin.
            spans = [
                (
                    self._data.track_id,
                    self._drag_origin_start,
                    self._drag_origin_start + self._drag_origin_duration,
                )
            ]
            spans.extend(
                (p._data.track_id, origin, origin + p._data.duration)
                for p, origin in self._drag_peers
            )
            self._align_times = sq.alignment_times(
                exclude_clip_ids=moving_ids, exclude_spans=spans
            )

        tl = self._timeline
        dx_time = tl.x_to_time(event.scenePos().x()) - tl.x_to_time(self._drag_origin_x)

        if self._drag_mode == "move":
            new_start = self._align(
                self._snap(max(0.0, self._drag_origin_start + dx_time))
            )
            snapped_delta = new_start - self._drag_origin_start
            # Clamp the GROUP, not each member: clamping a peer on its own
            # (``max(0.0, ...)``) silently deforms the selection whenever a
            # peer sits earlier than the grabbed clip and would cross frame 0.
            # The earliest member decides how far the whole set may travel.
            floor = min([self._drag_origin_start] + [o for _p, o in self._drag_peers])
            if floor + snapped_delta < 0.0:
                snapped_delta = -floor
                new_start = self._drag_origin_start + snapped_delta
            self._data.start = new_start
            # Move peer clips by the same snapped delta
            for peer, origin_start in self._drag_peers:
                peer._data.start = origin_start + snapped_delta
                peer._sync_geometry()
                peer.update()

        elif self._drag_mode == "resize_left":
            # Snap FIRST, then clamp (mirrors resize_right) — snapping
            # after the min-duration clamp can push the start past it
            # and emit a zero- or negative-duration clip_resized.
            new_start = self._align(
                self._snap(max(0.0, self._drag_origin_start + dx_time))
            )
            new_start = min(
                new_start,
                self._drag_origin_start
                + self._drag_origin_duration
                - _MIN_CLIP_DURATION,
            )
            delta = new_start - self._drag_origin_start
            self._data.start = new_start
            self._data.duration = self._drag_origin_duration - delta

        elif self._drag_mode == "resize_right":
            raw_end = self._drag_origin_start + self._drag_origin_duration + dx_time
            snapped_end = self._align(self._snap(raw_end))
            new_dur = max(_MIN_CLIP_DURATION, snapped_end - self._data.start)
            self._data.duration = new_dur

        if self._resize_peers:
            self._apply_group_scale()
        self._sync_geometry()
        self.update()
        self._refresh_align_guides()
        self._update_clip_drag_tooltip(event.scenePos())
        event.accept()

    # -- key alignment ------------------------------------------------------
    def _align(self, value: float) -> float:
        """Pull *value* onto a nearby key frame, when that is turned on.

        Guides are drawn either way (see :meth:`_refresh_align_guides`);
        only the pull itself is opt-in, so the default drag stays free.
        """
        sq = self._timeline.parent_sequencer
        if not sq.snap_to_keys or not self._align_times:
            return value
        hit = sq.nearest_alignment(value, self._align_times)
        best = None if hit is None else hit - value
        # A body drag can align on EITHER edge; capture whichever is closer
        # so the guides never promise an end-alignment the snap didn't take.
        if self._drag_mode == "move" and self._data.duration > 0:
            end = value + self._data.duration
            end_hit = sq.nearest_alignment(end, self._align_times)
            if end_hit is not None:
                end_delta = end_hit - end
                if best is None or abs(end_delta) < abs(best):
                    best = end_delta
        if best is None:
            return value
        # Re-clamp: an end-edge hit near frame 0 can pull the start negative,
        # and move mode assigns this result directly.
        return max(0.0, value + best)

    def _aligned_edges(self) -> list:
        """Frames of this drag that currently sit on an existing key."""
        sq = self._timeline.parent_sequencer
        if not self._align_times:
            return []
        if self._drag_mode == "resize_right":
            probes = [self._data.start + self._data.duration]
        elif self._drag_mode == "resize_left":
            probes = [self._data.start]
        else:  # a move aligns on either edge
            probes = [self._data.start]
            if self._data.duration > 0:
                probes.append(self._data.start + self._data.duration)
        hits = []
        for t in probes:
            hit = sq.nearest_alignment(t, self._align_times)
            if hit is None:
                continue
            if sq.snap_to_keys and abs(hit - t) > 1e-6:
                # Snapping is ON but this edge did not capture (the other
                # edge won, or the clamp overrode it) — drawing a guide here
                # would claim an alignment the release won't deliver.
                continue
            hits.append(hit)
        return hits

    def _refresh_align_guides(self) -> None:
        hits = self._aligned_edges()
        self._timeline.parent_sequencer.set_snap_guides(hits)
        self._align_hit = bool(hits)

    def _is_drag_active(self) -> bool:
        """True while this item owns an in-flight gesture.

        A press that has not yet cleared the drag threshold counts: it holds
        the mouse grab and the origin state a later move would arm from, so
        a cancel (Escape, or a popup stealing the grab) has to reach it too.
        Otherwise the pending zone outlived the gesture that set it.
        """
        return self._drag_mode is not None or self._pending_zone is not None

    def _restore_drag_state(self) -> None:
        self._timeline.parent_sequencer.clear_snap_guides()
        self._align_hit = False
        self._align_times = None
        self._data.start = self._drag_origin_start
        self._data.duration = self._drag_origin_duration
        for peer, origin_start in self._drag_peers:
            peer._data.start = origin_start
            peer._drag_mode = None
            peer._sync_geometry()
            peer.update()
        for peer, origin_start, origin_duration in self._resize_peers:
            peer._data.start = origin_start
            peer._data.duration = origin_duration
            peer._drag_mode = None
            peer._sync_geometry()
            peer.update()
        self._drag_mode = None
        self._pending_zone = None  # an unarmed press is cancelled too
        self._press_screen_pos = None
        self._drag_peers = []
        self._resize_peers = []
        self._sync_geometry()
        CursorManager.pop(self)

    @staticmethod
    def _collision_free_order(landings: list) -> list:
        """Order a group's landings so applying them ONE AT A TIME is safe.

        ``landings`` is ``[(origin_start, clip_id, new_start), ...]``; the
        return is the ``[(clip_id, new_start), ...]`` payload of
        :signal:`clips_batch_moved`.

        A consumer commits a batch clip by clip, and it addresses each clip's
        content by the time range it USED to occupy -- that is the only handle
        it has on "which keys belong to this clip".  So the order matters: if
        one clip lands on a range a still-pending clip has not left yet, the
        pending clip's own commit grabs the arrival too and drags it a second
        time.  The group comes out of the gesture deformed -- clips stacked on
        top of each other, keys at double the delta -- which is what a
        multi-select drag looked like whenever the travel distance exceeded the
        space between two of its clips.

        The gesture is a rigid translation, so one rule is enough: move the
        clip that vacates space FIRST.  Travelling left, that is the earliest;
        travelling right, the latest.  Every landing then falls on timeline
        the group has already left.  (Ordering alone fixes it -- no consumer
        needs to know why, and both DCC adapters inherit the fix.)
        """
        if not landings:
            return []
        # One delta for the whole group, so any member's sign will do; take
        # the largest to stay right if a consumer ever emits a mixed batch.
        lead = max(landings, key=lambda x: abs(x[2] - x[0]))
        forward = (lead[2] - lead[0]) > 0
        ordered = sorted(landings, key=lambda x: x[0], reverse=forward)
        return [(cid, new_start) for _origin, cid, new_start in ordered]

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            # Armed or not, the gesture is over.
            self._pending_zone = None
            self._press_screen_pos = None
        if event.button() == QtCore.Qt.LeftButton and not self._drag_mode:
            # A press this item took but never dragged (locked clip, sub-row,
            # or a plain click on the body) still has to finish its selection.
            self._release_selection(self._press_modifiers, False)
        if event.button() == QtCore.Qt.LeftButton and self._drag_mode:
            mode = self._drag_mode
            peers = self._drag_peers
            scaled = self._resize_peers
            self._drag_mode = None
            self._drag_peers = []
            self._resize_peers = []
            CursorManager.pop(self)
            self.update()  # repaint to hide drag frame labels
            self._drag_tooltip.hide()
            # Clear drag state on peers so their curve previews
            # switch back to live data after release.
            for peer, _ in peers:
                peer._drag_mode = None
                peer.update()
            for peer, _o, _d in scaled:
                peer._drag_mode = None
                peer.update()
            widget = self._timeline.parent_sequencer
            widget.clear_snap_guides()
            self._align_hit = False
            self._align_times = None
            # Only emit when something actually changed — an edge/body
            # click without movement otherwise fires clip_resized /
            # clip_moved with unchanged values and consumers pay a full
            # save + key-scale + widget rebuild for a misclick.
            changed = (
                abs(self._data.start - self._drag_origin_start) > 0.01
                or abs(self._data.duration - self._drag_origin_duration) > 0.01
            )
            # A press that never moved was a CLICK, so it gets the click's
            # selection semantics; a real drag leaves the group intact.
            self._release_selection(self._press_modifiers, moved=changed)
            if changed:
                # The consumer typically rebuilds from here, which retires
                # this very item while Qt is still inside the release --
                # safe because SequencerWidget routes removals through
                # ``ItemRetirement.retire`` (see _draggable), which keeps the object
                # alive for one more event-loop pass.
                if mode == "move":
                    if peers:
                        landings = [
                            (
                                self._drag_origin_start,
                                self._data.clip_id,
                                self._data.start,
                            )
                        ]
                        landings.extend(
                            (origin, peer._data.clip_id, peer._data.start)
                            for peer, origin in peers
                        )
                        widget.clips_batch_moved.emit(
                            self._collision_free_order(landings)
                        )
                    else:
                        widget.clip_moved.emit(self._data.clip_id, self._data.start)
                elif scaled:
                    # The gesture retimed a SELECTION: one payload, so the
                    # consumer commits it as one edit and one undo step.
                    members = [(self, self._drag_origin_start)] + [
                        (peer, origin) for peer, origin, _dur in scaled
                    ]
                    spans = {
                        item._data.clip_id: (
                            item._data.start,
                            item._data.duration,
                        )
                        for item, _origin in members
                    }
                    order = self._collision_free_order(
                        [
                            (origin, item._data.clip_id, item._data.start)
                            for item, origin in members
                        ]
                    )
                    widget.clips_batch_resized.emit(
                        [(cid, *spans[cid]) for cid, _new_start in order]
                    )
                else:
                    widget.clip_resized.emit(
                        self._data.clip_id, self._data.start, self._data.duration
                    )
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # -- context menu -------------------------------------------------------
    def contextMenuEvent(self, event):
        if self._data.data.get("read_only"):
            event.ignore()
            return

        widget = self._timeline.parent_sequencer

        # Collect all selected, non-read-only clips for multi-select ops.
        selected_clips = [
            item
            for item in self._timeline._scene.selectedItems()
            if isinstance(item, ClipItem) and not item._data.data.get("read_only")
        ]
        if self not in selected_clips:
            selected_clips = [self]
        multi = len(selected_clips) > 1

        menu = MenuUtils._styled_menu()

        # Lock / Unlock — operates on all selected clips.
        all_locked = all(c._data.locked for c in selected_clips)
        if all_locked:
            action_lock = menu.addAction(
                f"Unlock ({len(selected_clips)})" if multi else "Unlock"
            )
        else:
            action_lock = menu.addAction(
                f"Lock ({len(selected_clips)})" if multi else "Lock"
            )

        # Rename — only meaningful for a single clip.
        action_rename = menu.addAction("Rename")
        if self._data.locked or multi:
            action_rename.setEnabled(False)

        # Extensibility hook — let consumers add domain-specific actions
        widget.clip_menu_requested.emit(menu, self._data.clip_id)

        chosen = menu.exec_(MenuUtils._menu_exec_pos(event))
        if self.scene() is None:
            # A rebuild (keyframe debounce, store event, undo callback) ran
            # inside the menu's nested event loop and retired this item —
            # the ids below are stale and acting on them would no-op on the
            # wrong clip or raise.
            return
        if chosen == action_lock:
            new_locked = not all_locked
            # Apply visual lock state to every selected clip.
            # Emit clip_locked once per unique object so the consumer
            # (e.g. Maya controller) persists and propagates to siblings
            # without redundant O(n*m) iteration.
            emitted_objs: set = set()
            for clip in selected_clips:
                widget.set_clip_locked(clip._data.clip_id, new_locked)
                obj = clip._data.data.get("obj", clip._data.clip_id)
                if obj not in emitted_objs:
                    emitted_objs.add(obj)
                    widget.clip_locked.emit(clip._data.clip_id, new_locked)
        elif chosen == action_rename:
            self._start_inline_rename()

    # -- double-click to rename --------------------------------------------
    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            # Gate like the context menu: read-only clips must not be
            # renameable, and a sub-row (attribute curve row) has no
            # user-facing label — double-clicking between key dots would
            # spawn the rename editor over the curve.
            if (
                self._data.locked
                or self._data.sub_row
                or self._data.data.get("read_only")
            ):
                return
            self._start_inline_rename()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _start_inline_rename(self):
        """Spawn a QLineEdit proxy widget over the clip for inline renaming."""
        if self.scene() is None:
            return  # retired by a rebuild while the caller's menu was open
        rect = self.rect()
        edit = QtWidgets.QLineEdit()
        edit.setText(self._data.label)
        edit.selectAll()
        edit.setFrame(False)
        edit.setStyleSheet(
            "background:#333; color:#FFF; padding:0 4px; font-size:10px;"
        )
        edit.setFixedHeight(int(rect.height()))

        proxy = self.scene().addWidget(edit)
        proxy.setPos(rect.x(), rect.y())
        proxy.setZValue(100)
        edit.setFixedWidth(max(int(rect.width()), 60))
        edit.setFocus()

        finished = [False]

        def _finish():
            if finished[0]:
                return
            finished[0] = True
            new_label = edit.text()
            self._data.label = new_label
            self.update()
            widget = self._timeline.parent_sequencer
            widget.clip_renamed.emit(self._data.clip_id, new_label)
            if proxy.scene():
                proxy.scene().removeItem(proxy)

        edit.editingFinished.connect(_finish)

    # -- drag tooltip -------------------------------------------------------
    def _clip_drag_frame(self) -> float:
        """Frame value relevant to the current drag mode."""
        if self._drag_mode == "resize_right":
            return float(self._data.start + self._data.duration)
        return float(self._data.start)

    def _drag_tooltip_color(self) -> str:
        """Readout colour — the guide colour while the drag is aligned."""
        sq = self._timeline.parent_sequencer
        if self._align_hit and sq.snap_guides_enabled:
            return sq.SNAP_GUIDE_COLOR
        return self._resolve_color().lighter(160).name()

    def _show_clip_drag_tooltip(self, scene_pos):
        self._drag_tooltip.show(
            self.scene(),
            scene_pos,
            label=FrameTooltip.format_frame(self._clip_drag_frame()),
            color=self._drag_tooltip_color(),
        )

    def _update_clip_drag_tooltip(self, scene_pos):
        self._drag_tooltip.update(
            scene_pos,
            label=FrameTooltip.format_frame(self._clip_drag_frame()),
            color=self._drag_tooltip_color(),
        )

    # -- utilities ----------------------------------------------------------
    def _hit_zone(self, pos) -> str:
        rect = self.rect()
        # Zero-duration (point/stepped) clips render narrower than the
        # resize handles, so every press would land in "resize_left" and
        # the clip could never be moved.  Same for clips whose width
        # leaves no body zone between the two handles.
        if self._data.duration <= 0 or rect.width() <= 2 * _HANDLE_WIDTH:
            return "move"
        local_x = pos.x() - rect.x()
        if local_x <= _HANDLE_WIDTH and self._data.data.get("resizable_left", True):
            return "resize_left"
        elif local_x >= rect.width() - _HANDLE_WIDTH and self._data.data.get(
            "resizable_right", True
        ):
            return "resize_right"
        return "move"
