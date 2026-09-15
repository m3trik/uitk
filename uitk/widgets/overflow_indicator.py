# !/usr/bin/python
# coding=utf-8
"""Arrows at the edges of a scroll view where its content continues past them."""

from typing import Optional, Tuple

from qtpy import QtCore, QtGui, QtWidgets


class OverflowIndicator(QtWidgets.QWidget):
    """A mouse-transparent overlay on a scroll area's viewport that marks each
    vertical edge with content beyond it: an arrow at the bottom while more
    lies below, one at the top while the first rows are scrolled out of view,
    neither once everything fits.

    One implementation for every view -- a combo popup, a tree, a table, a
    text log -- attached with :meth:`attach` and then forgotten.  It reads the
    vertical scrollbar's value and range, which ``QAbstractScrollArea`` keeps
    current whether or not the bar is shown (so a popup that hides its bar is
    served the same), follows the viewport's geometry, and repaints on every
    scroll.  Reading the RANGE rather than counting rows is what makes it
    right for hidden rows, filtered models and wrapped text alike.

    Parented to the scroll area rather than to its viewport, deliberately: an
    item view scrolls with ``viewport().scroll(dx, dy)``, which carries every
    viewport child along with the rows (that is how index widgets ride
    theirs), so a viewport child drifts on every scroll and has to be
    re-pinned on every paint.  A sibling stacked above the viewport stays put.

    It caches no wrapper of the area or its children -- the area is read
    from ``parentWidget()`` and the bar from the area on every call.  A
    scrollbar wrapper taken while the runtime loader is still building the
    view is invalidated by the loader's reparent although the bar lives on,
    and the ``RuntimeError`` it then raises inside ``eventFilter`` during
    ``show()`` is an access violation, not a traceback.

    Parameters:
        area: The ``QAbstractScrollArea`` to overlay -- a list, tree, table,
            text edit or ``QScrollArea``.
    """

    # Not a Designer widget-box entry: it anchors itself to a scroll area it
    # is given, so the bare ``cls(parent)`` Designer makes has nothing to do.
    designer_spec = {"visible": False}

    #: Band thickness and arrow (width, height), as fractions of the area's
    #: font height, so the affordance follows the view's text size.
    BAND_EM = 1.0
    ARROW_EM = (0.6, 0.35)
    #: The band is the area's Base colour at this alpha at the outer edge,
    #: fading to clear over the content; the arrow is the area's Text colour
    #: at this alpha.
    BAND_ALPHA = 170
    ARROW_ALPHA = 210

    def __init__(self, area: QtWidgets.QAbstractScrollArea):
        super().__init__(area)
        self._edges: Tuple[str, ...] = ()
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        area.installEventFilter(self)
        area.viewport().installEventFilter(self)
        bar = area.verticalScrollBar()
        bar.valueChanged.connect(self._on_bar_changed)
        bar.rangeChanged.connect(self._on_bar_changed)
        # Explicitly hidden, or a child made before its parent is shown (a
        # popup view, attached ahead of the popup) is shown along with it,
        # empty band and all; ``refresh`` shows it once there is an edge.
        self.hide()
        self._sync()

    # ------------------------------------------------------------------
    # Attaching
    # ------------------------------------------------------------------
    @classmethod
    def attach(cls, area: QtWidgets.QAbstractScrollArea) -> "OverflowIndicator":
        """Return *area*'s indicator, creating it on the first call.

        Parameters:
            area: The scroll area to overlay.

        Returns:
            The one indicator attached to *area*.
        """
        return cls.of(area) or cls(area)

    @classmethod
    def of(cls, area: QtWidgets.QAbstractScrollArea) -> Optional["OverflowIndicator"]:
        """The indicator attached to *area*, or ``None``."""
        return area.findChild(cls, "", QtCore.Qt.FindDirectChildrenOnly)

    def detach(self) -> None:
        """Take the overlay off its area and schedule it for deletion."""
        area = self.area
        if area is not None:
            area.removeEventFilter(self)
            viewport = area.viewport()
            if viewport is not None:
                viewport.removeEventFilter(self)
            bar = area.verticalScrollBar()
            for signal in (bar.valueChanged, bar.rangeChanged):
                try:
                    signal.disconnect(self._on_bar_changed)
                except (RuntimeError, TypeError):
                    pass
        self.hide()
        self.setParent(None)
        self.deleteLater()

    @property
    def area(self) -> Optional[QtWidgets.QAbstractScrollArea]:
        """The scroll area this overlays (its parent); ``None`` once detached."""
        return self.parentWidget()

    @property
    def shown_edges(self) -> Tuple[str, ...]:
        """The edges currently marked, in ``("top", "bottom")`` order --
        empty while everything fits."""
        return self._edges

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-read the scroll range; show, hide or repaint to match."""
        area = self.area
        if area is None:
            return
        edges = self._edges_beyond(area.verticalScrollBar())
        if edges == self._edges:
            return
        self._edges = edges
        self.setVisible(bool(edges))
        self.update()

    @staticmethod
    def _edges_beyond(bar: QtWidgets.QScrollBar) -> Tuple[str, ...]:
        """Which edges have content past them, from the bar's value and range."""
        value = bar.value()
        edges = []
        if value > bar.minimum():
            edges.append("top")
        if value < bar.maximum():
            edges.append("bottom")
        return tuple(edges)

    def _on_bar_changed(self, *_args) -> None:
        self.refresh()

    def _sync(self) -> None:
        """Pin the overlay over the viewport, above it, and refresh."""
        area = self.area
        if area is None:
            return
        viewport = area.viewport()
        if viewport is not None:
            self.setGeometry(viewport.geometry())
        self.raise_()
        self.refresh()

    def eventFilter(self, obj, event):
        # Installed on the area and on its viewport; both want the same
        # answer, so neither is told apart. The area resizes and shows; the
        # viewport moves and resizes as scrollbars and headers come and go.
        etype = event.type()
        if etype in (QtCore.QEvent.Resize, QtCore.QEvent.Move, QtCore.QEvent.Show):
            self._sync()
        elif etype in (
            QtCore.QEvent.FontChange,
            QtCore.QEvent.PaletteChange,
            QtCore.QEvent.StyleChange,
        ):
            self.update()
        return False

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def _metrics(self) -> Tuple[int, Tuple[float, float]]:
        """Band thickness and arrow (width, height) in px for the area's font."""
        em = max(8, self.area.fontMetrics().height())
        band = max(8, round(em * self.BAND_EM))
        return band, (em * self.ARROW_EM[0], em * self.ARROW_EM[1])

    def _colors(self) -> Tuple[QtGui.QColor, QtGui.QColor]:
        """Band fill and arrow ink, from the area's palette.

        The AREA's, not the viewport's: a stylesheet background lands in the
        scroll area's palette (Base), while the viewport's own can still read
        the platform default underneath it.
        """
        palette = self.area.palette()
        fill = QtGui.QColor(palette.color(QtGui.QPalette.Base))
        fill.setAlpha(self.BAND_ALPHA)
        ink = QtGui.QColor(palette.color(QtGui.QPalette.Text))
        ink.setAlpha(self.ARROW_ALPHA)
        return fill, ink

    def paintEvent(self, event):
        if not self._edges or self.area is None:
            return
        band, (arrow_w, arrow_h) = self._metrics()
        fill, ink = self._colors()
        clear = QtGui.QColor(fill)
        clear.setAlpha(0)
        width, height = float(self.width()), float(self.height())
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtCore.Qt.NoPen)
        for edge in self._edges:
            # +1 points outward for the bottom edge, -1 for the top.
            outward = -1.0 if edge == "top" else 1.0
            outer_y = 0.0 if edge == "top" else height
            inner_y = outer_y - outward * band
            gradient = QtGui.QLinearGradient(0.0, outer_y, 0.0, inner_y)
            gradient.setColorAt(0.0, fill)
            gradient.setColorAt(1.0, clear)
            painter.fillRect(
                QtCore.QRectF(0.0, min(outer_y, inner_y), width, band), gradient
            )
            cx = width / 2.0
            mid = (outer_y + inner_y) / 2.0
            apex = QtCore.QPointF(cx, mid + outward * arrow_h / 2.0)
            base_y = mid - outward * arrow_h / 2.0
            painter.setBrush(ink)
            painter.drawPolygon(
                QtGui.QPolygonF(
                    [
                        apex,
                        QtCore.QPointF(cx - arrow_w / 2.0, base_y),
                        QtCore.QPointF(cx + arrow_w / 2.0, base_y),
                    ]
                )
            )
        painter.end()
