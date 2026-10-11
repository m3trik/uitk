# !/usr/bin/python
# coding=utf-8
"""A slim colour strip down an item view's left edge: one colour tag per row.

:class:`RowTags` attaches to any ``QTreeView`` / ``QTableView`` -- plain Qt views
as much as uitk's ``TreeWidget`` and ``TableWidget``, whose ``enable_row_tags``
option is this class -- and gives it:

* a tag per row: a palette *slot* key (``"tag3"``), never a colour, so
  recolouring a slot recolours every row holding it;
* an automatic layer under it: a host's rule (colour by section, say) shows
  wherever the user set no tag, and clearing a tag shows it again;
* inheritance: a tree row with no tag of its own shows its nearest tagged
  ancestor's colour, fainter, so an expanded group reads as one block;
* a quick-pick swatch row for a context menu (:meth:`RowTags.add_to_menu`), a
  plain ``QMenu`` or a uitk ``Menu``: a click tags every target row at once and
  emits :attr:`RowTags.assigned`; a right-click edits that slot's colour;
* the palette (:meth:`Palette.tags` unless the host gives its own) with the
  user's colours saved under one settings branch (``colors``).

The strip is a mouse-transparent overlay stacked above the viewport -- the
:class:`~uitk.widgets.overflow_indicator.OverflowIndicator` arrangement -- not a
delegate: it survives a host swapping the view's delegates, and the view's own
selection and status colours paint under it untouched.

Tags are kept here, beside the model and never in it, keyed by persistent
index: a tag follows its row through sorts and moves and is dropped with it.
A tag is decoration, not content, so writing one fires no ``dataChanged`` /
``itemChanged`` (a host that treats those as a user's edit never hears it) and
gives no empty table cell an item.
"""

from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple, Union

import pythontk as ptk
from qtpy import QtCore, QtGui, QtWidgets

from uitk.managers.color_model import ColorModel
from uitk.managers.settings_manager import SettingsManager

#: What names a row: a tree/table item, a model index (any column) or a table
#: row number.
Row = Union[
    QtWidgets.QTreeWidgetItem,
    QtWidgets.QTableWidgetItem,
    QtCore.QModelIndex,
    QtCore.QPersistentModelIndex,
    int,
]
#: Rows to act on: a list of rows, a callable answering one when a swatch is
#: picked, or ``None`` for the view's selection at that moment.
Rows = Union[Iterable[Row], Callable[[], Iterable[Row]], None]


class _Swatch(QtWidgets.QWidget):
    """One slot of the swatch row: a click picks it, a right-click asks to edit it.

    The press is accepted too, never only the release: a press that reached a
    ``QMenu`` would arm its widget action, and the release would then trigger
    and close the menu over the pick.
    """

    #: The slot key, or ``None`` for the clear swatch.
    picked = QtCore.Signal(object)
    #: A right-click: the slot key whose colour to edit.
    edit_requested = QtCore.Signal(str)

    SIZE = 16

    def __init__(self, slot: Optional[str], tooltip: str, parent=None):
        super().__init__(parent)
        self.slot = slot
        self.color: Optional[QtGui.QColor] = None
        self.current = False
        self._hover = False
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setToolTip(tooltip)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WA_Hover, True)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if not self.rect().contains(pos):
            return
        if event.button() == QtCore.Qt.LeftButton:
            self.picked.emit(self.slot)
        elif event.button() == QtCore.Qt.RightButton and self.slot is not None:
            self.edit_requested.emit(self.slot)

    def contextMenuEvent(self, event):
        event.accept()  # the right-click is this swatch's edit, not a menu

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        ink = QtGui.QColor(self.palette().color(QtGui.QPalette.WindowText))
        body = QtCore.QRectF(self.rect()).adjusted(2.5, 2.5, -2.5, -2.5)
        if self.color is None:  # the clear swatch: a ring with a slash
            faint = QtGui.QColor(ink)
            faint.setAlpha(170)
            painter.setPen(QtGui.QPen(faint, 1.2))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(body)
            painter.drawLine(body.bottomLeft(), body.topRight())
        else:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(self.color)
            painter.drawRoundedRect(body, 2.5, 2.5)
        if self.current or self._hover:
            ring = QtGui.QColor(ink)
            ring.setAlpha(230 if self.current else 120)
            painter.setPen(QtGui.QPen(ring, 1.2))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRoundedRect(
                QtCore.QRectF(self.rect()).adjusted(0.6, 0.6, -0.6, -0.6), 3.5, 3.5
            )
        painter.end()


class _SwatchRow(QtWidgets.QWidget):
    """The context menu's row of swatches: the clear swatch, then each slot."""

    #: A swatch was picked or asked to be edited. A uitk ``Menu`` that holds
    #: the row hides on it (a leaf trigger); a ``QMenu`` host closes on it.
    on_item_interacted = QtCore.Signal(object)

    def __init__(self, tags: "RowTags", rows: Rows, parent=None):
        super().__init__(parent)
        self._tags = tags
        self._rows = rows
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(2)
        self.swatches: List[_Swatch] = []
        for number, slot in enumerate([None, *tags.slots]):
            tip = (
                "No color"
                if slot is None
                else f"Color {number} -- right-click to change it"
            )
            swatch = _Swatch(slot, tip, self)
            swatch.picked.connect(self._pick)
            swatch.edit_requested.connect(self._edit)
            layout.addWidget(swatch)
            self.swatches.append(swatch)
        layout.addStretch(1)
        self.refresh()

    def showEvent(self, event):
        # A uitk Menu keeps its rows between showings; the targets and the
        # palette may have changed since.
        self.refresh()
        super().showEvent(event)

    def refresh(self) -> None:
        """Re-read the palette, and ring the slot every target row shares."""
        targets = self._tags._targets(self._rows)
        held = {self._tags.tag(index) for index in targets}
        common = next(iter(held)) if len(held) == 1 else False
        for swatch in self.swatches:
            if swatch.slot is not None:
                swatch.color = self._tags.qcolor(swatch.slot)
            swatch.current = bool(targets) and swatch.slot == common
            swatch.update()

    def _pick(self, slot: Optional[str]) -> None:
        self._tags._assign(self._rows, slot)
        self.on_item_interacted.emit(slot)

    def _edit(self, slot: str) -> None:
        pos = QtGui.QCursor.pos()
        self.on_item_interacted.emit(slot)  # the menu goes first
        tags = self._tags
        QtCore.QTimer.singleShot(0, lambda: tags.edit_color(slot, pos))


class RowTags(QtWidgets.QWidget):
    """Per-row colour tags on an item view, shown as a strip down its left edge.

    A sibling of the view's viewport, stacked above it, so scrolling never
    drags it; reach it with :meth:`of`, make it with :meth:`attach`.

    Parameters:
        view: The ``QTreeView`` or ``QTableView`` (widgets included).
        settings: A ``SettingsManager`` (anything with ``branch`` / ``value`` /
            ``setValue`` / ``remove`` / ``sync``) the palette is saved in.
            ``None`` makes one (``org="uitk"``, ``app=`` *app*).
        settings_key: The branch the palette is kept under: the view's
            ``objectName()`` by default, else its class name.
        app: The settings application name used when *settings* is ``None``.
        defaults: ``{slot: colour}`` -- the slots and their default colours, in
            order; :meth:`Palette.tags` when ``None``.
        inherit: A tree row with no tag shows its nearest tagged ancestor's.
    """

    # Not a Designer widget-box entry: it anchors itself to a view it is
    # given, so the bare ``cls(parent)`` Designer makes has nothing to do.
    designer_spec = {"visible": False}

    #: ``(rows, slot)`` -- the user tagged *rows* (column-0 ``QModelIndex``\\ es)
    #: from the swatch row; *slot* is ``None`` when they cleared the tags.  Not
    #: emitted by :meth:`set_tag`: a host restoring its saved tags hears nothing.
    assigned = QtCore.Signal(list, object)
    #: ``{slot: "#RRGGBB"}`` -- the palette after a colour changed or was reset.
    colors_changed = QtCore.Signal(dict)

    #: Strip width in px -- the combo box's current-item accent strip.
    STRIP_WIDTH = 4
    #: Alpha of a colour a row inherits from an ancestor.
    INHERITED_ALPHA = 110

    def __init__(
        self,
        view: QtWidgets.QAbstractItemView,
        settings=None,
        settings_key: Optional[str] = None,
        app: str = "RowTags",
        defaults: Optional[Mapping[str, Any]] = None,
        inherit: bool = True,
    ):
        super().__init__(view)
        self.inherit = True
        self._settings = None
        self._defaults: Dict[str, str] = {}
        self._colors: Dict[str, str] = {}
        self._qcolors: Dict[str, QtGui.QColor] = {}
        #: The user's tags and the host's automatic ones, by column-0 row.
        self._user: Dict[QtCore.QPersistentModelIndex, str] = {}
        self._auto: Dict[QtCore.QPersistentModelIndex, str] = {}
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.configure(view, settings, settings_key, app, defaults, inherit)
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)
        view.verticalScrollBar().valueChanged.connect(self._repaint)
        model = view.model()
        if model is not None:
            for signal in (
                model.dataChanged,
                model.layoutChanged,
                model.modelReset,
                model.rowsInserted,
                model.rowsRemoved,
                model.rowsMoved,
            ):
                signal.connect(self._repaint)
            for signal in (model.rowsRemoved, model.modelReset):
                signal.connect(self._prune)
        if isinstance(view, QtWidgets.QTreeView):
            view.expanded.connect(self._repaint)
            view.collapsed.connect(self._repaint)
        self._sync()
        self.show()

    # ------------------------------------------------------------ attaching
    @classmethod
    def attach(
        cls,
        view: QtWidgets.QAbstractItemView,
        settings=None,
        settings_key: Optional[str] = None,
        app: str = "RowTags",
        defaults: Optional[Mapping[str, Any]] = None,
        inherit: bool = True,
    ) -> "RowTags":
        """*view*'s row tags, made on the first call and re-pointed after.

        Parameters are those of the class; a second call keeps the one overlay
        and the tags on the rows, and reconfigures the palette and settings.
        """
        tags = cls.of(view)
        if tags is None:
            return cls(view, settings, settings_key, app, defaults, inherit)
        tags.configure(view, settings, settings_key, app, defaults, inherit)
        return tags

    @classmethod
    def of(cls, view: QtWidgets.QAbstractItemView) -> Optional["RowTags"]:
        """The row tags attached to *view*, or ``None``."""
        return view.findChild(cls, "", QtCore.Qt.FindDirectChildrenOnly)

    def configure(
        self,
        view: QtWidgets.QAbstractItemView,
        settings=None,
        settings_key: Optional[str] = None,
        app: str = "RowTags",
        defaults: Optional[Mapping[str, Any]] = None,
        inherit: bool = True,
    ) -> None:
        """Point the palette at *settings* / *settings_key* and load it."""
        key = settings_key or view.objectName() or type(view).__name__
        if settings is None:
            settings = SettingsManager(org="uitk", app=app)
        self._settings = settings.branch(key)
        if defaults is None:
            defaults = ptk.Palette.tags()
        self._defaults = {str(slot): self._hex(c) for slot, c in defaults.items()}
        saved = self._settings.value("colors", {})
        self._colors = dict(self._defaults)
        for slot, color in saved.items() if isinstance(saved, dict) else ():
            if slot in self._defaults:
                try:
                    self._colors[slot] = self._hex(color)
                except ValueError:
                    pass  # a hand-edited or corrupt entry: the default stands
        self._qcolors = {s: QtGui.QColor(c) for s, c in self._colors.items()}
        self.inherit = bool(inherit)
        self.update()

    def detach(self) -> None:
        """Take the strip off its view and schedule it for deletion.  The tags
        stay on the rows."""
        view = self.view
        if view is not None:
            view.removeEventFilter(self)
            viewport = view.viewport()
            if viewport is not None:
                viewport.removeEventFilter(self)
        self.hide()
        self.setParent(None)
        self.deleteLater()

    @property
    def view(self) -> Optional[QtWidgets.QAbstractItemView]:
        """The view this overlays (its parent); ``None`` once detached."""
        return self.parentWidget()

    @property
    def settings(self):
        """The settings branch the palette is kept in."""
        return self._settings

    # ------------------------------------------------------------ the palette
    @property
    def slots(self) -> List[str]:
        """The slot keys, in palette order."""
        return list(self._defaults)

    def colors(self) -> Dict[str, str]:
        """``{slot: "#RRGGBB"}``, the user's colours over the defaults."""
        return dict(self._colors)

    def color(self, slot: Optional[str]) -> Optional[str]:
        """*slot*'s colour (``"#RRGGBB"``), or ``None`` for an unknown slot."""
        return self._colors.get(slot) if slot else None

    def qcolor(self, slot: Optional[str]) -> Optional[QtGui.QColor]:
        """*slot*'s colour as a ``QColor`` (a copy), or ``None``."""
        color = self._qcolors.get(slot) if slot else None
        return QtGui.QColor(color) if color is not None else None

    def set_color(self, slot: str, color: Any) -> None:
        """Recolour *slot* -- every row holding it -- and save the palette.

        Parameters:
            slot: One of :attr:`slots`.
            color: A ``"#RRGGBB"`` string, ``QColor`` or ``ptk.Color``.

        Raises:
            KeyError: *slot* is not one of :attr:`slots`.
            ValueError: *color* is not a colour.
        """
        if slot not in self._defaults:
            raise KeyError(f"{slot!r} is not one of {self.slots}")
        self._colors[slot] = self._hex(color)
        self._save_colors()

    def reset_colors(self) -> None:
        """Every slot back to its default colour; the saved palette dropped."""
        self._colors = dict(self._defaults)
        self._save_colors()

    def edit_color(self, slot: str, pos: Optional[QtCore.QPoint] = None) -> bool:
        """Let the user pick *slot*'s colour in the colour popup.

        Parameters:
            slot: One of :attr:`slots`.
            pos: Where the popup opens (global); under the view when ``None``.

        Returns:
            Whether the colour changed.
        """
        from uitk.widgets.editors.color_editor import ColorEditorPopup

        chosen = ColorEditorPopup.get_color(
            self.qcolor(slot), parent=self.view, title="Tag Color", pos=pos
        )
        if chosen is None:
            return False
        self.set_color(slot, chosen)
        return True

    # ------------------------------------------------------------ the tags
    def tag(self, row: Row) -> Optional[str]:
        """The user's tag on *row*, or ``None``."""
        return self._user.get(QtCore.QPersistentModelIndex(self._index(row)))

    def auto_tag(self, row: Row) -> Optional[str]:
        """The host's automatic tag on *row*, or ``None``."""
        return self._auto.get(QtCore.QPersistentModelIndex(self._index(row)))

    def shown_tag(self, row: Row) -> Optional[str]:
        """The slot *row*'s strip shows -- the user's tag, else the automatic
        one, else (with :attr:`inherit`) an ancestor's -- or ``None``."""
        return self._shown(self._index(row))[0]

    def set_tag(
        self, rows: Iterable[Row], slot: Optional[str], auto: bool = False
    ) -> List[QtCore.QModelIndex]:
        """Tag *rows* with *slot*, or clear their tags (``None``).

        Emits nothing: this is how a host restores its saved tags or applies
        its automatic ones.  The user's picks go through the swatch row, which
        emits :attr:`assigned`.

        Parameters:
            rows: The rows to tag.
            slot: A slot key (one of :attr:`slots`), or ``None`` to clear.
            auto: Write the automatic layer instead of the user's.

        Returns:
            The rows' column-0 indexes.
        """
        indexes = [i for i in (self._index(r) for r in rows) if i.isValid()]
        layer = self._auto if auto else self._user
        for index in indexes:
            key = QtCore.QPersistentModelIndex(index)
            if slot:
                layer[key] = str(slot)
            else:
                layer.pop(key, None)
        self.update()
        return indexes

    def selected_rows(self) -> List[QtCore.QModelIndex]:
        """The view's selected rows: one column-0 index each."""
        view = self.view
        selection = view.selectionModel() if view is not None else None
        if selection is None:
            return []
        rows, seen = [], set()
        for index in selection.selectedIndexes():
            first = index.sibling(index.row(), 0)
            key = QtCore.QPersistentModelIndex(first)
            if key not in seen:
                seen.add(key)
                rows.append(first)
        return rows

    # ------------------------------------------------------------ the menu
    def menu_row(self, rows: Rows = None, parent=None) -> QtWidgets.QWidget:
        """A swatch row that tags *rows*: the clear swatch, then each slot.

        Parameters:
            rows: The rows a pick tags -- a list, a callable answering one at
                pick time, or ``None`` for the view's selection at that moment
                (what a menu built once and kept wants).
            parent: The row's parent widget.

        Returns:
            The row; its ``on_item_interacted`` signal fires on every pick and
            edit request, which is how a menu holding it knows to close.
        """
        return _SwatchRow(self, rows, parent)

    def add_to_menu(self, menu, rows: Rows = None) -> QtWidgets.QWidget:
        """Add a swatch row (:meth:`menu_row`) to *menu* and return it.

        Parameters:
            menu: A ``QMenu`` (the row goes in a ``QWidgetAction``, and a pick
                closes the menu) or a uitk ``Menu`` (``menu.add``; a pick is a
                trigger like any item's, so the menu's ``hide_on_trigger``
                decides whether it hides).
            rows: As :meth:`menu_row`.
        """
        if isinstance(menu, QtWidgets.QMenu):
            row = self.menu_row(rows, parent=menu)
            action = QtWidgets.QWidgetAction(menu)
            action.setDefaultWidget(row)
            menu.addAction(action)
            row.on_item_interacted.connect(lambda *_: menu.close())
            return row
        row = self.menu_row(rows)
        menu.add(row)
        return row

    # ------------------------------------------------------------ internals
    @staticmethod
    def _hex(color: Any) -> str:
        """*color*, in any shape ``ColorModel.to_rgbaf`` reads, as ``"#RRGGBB"``."""
        rgbaf = ColorModel.to_rgbaf(color)
        if rgbaf is None:
            raise ValueError(f"not a colour: {color!r}")
        return ptk.Color.from_rgbf(*rgbaf[:3]).hex.upper()

    def _save_colors(self) -> None:
        """Save the slots that differ from their defaults; repaint; announce."""
        self._qcolors = {s: QtGui.QColor(c) for s, c in self._colors.items()}
        changed = {
            slot: color
            for slot, color in self._colors.items()
            if color != self._defaults[slot]
        }
        if changed:
            self._settings.setValue("colors", changed)
        else:
            self._settings.remove("colors")
        self._settings.sync()
        self.update()
        self.colors_changed.emit(self.colors())

    def _index(self, row: Row) -> QtCore.QModelIndex:
        """*row*'s column-0 index (invalid when it names no row)."""
        view = self.view
        if isinstance(row, QtCore.QPersistentModelIndex):
            row = QtCore.QModelIndex(row)
        if isinstance(row, QtCore.QModelIndex):
            return row.sibling(row.row(), 0) if row.isValid() else row
        if isinstance(row, QtWidgets.QTreeWidgetItem):
            return view.indexFromItem(row, 0)
        if isinstance(row, QtWidgets.QTableWidgetItem):
            index = view.indexFromItem(row)
            return index.sibling(index.row(), 0)
        if isinstance(row, int):
            return view.model().index(row, 0, view.rootIndex())
        raise TypeError(f"not a row: {row!r}")

    def _targets(self, rows: Rows) -> List[QtCore.QModelIndex]:
        """*rows* resolved now: column-0 indexes, valid ones only."""
        if rows is None:
            return self.selected_rows()
        if callable(rows):
            rows = rows()
        return [i for i in (self._index(r) for r in rows or ()) if i.isValid()]

    def _assign(self, rows: Rows, slot: Optional[str]) -> None:
        """The user picked *slot* for *rows*: tag them and say so."""
        indexes = self.set_tag(self._targets(rows), slot)
        if indexes:
            self.assigned.emit(indexes, slot)

    def _own(self, index: QtCore.QModelIndex) -> Optional[str]:
        """Column-0 *index*'s own slot: the user's tag, else the automatic one
        (a slot no longer in the palette counts as none)."""
        key = QtCore.QPersistentModelIndex(index)
        slot = self._user.get(key) or self._auto.get(key)
        return slot if slot in self._qcolors else None

    def _shown(self, index: QtCore.QModelIndex) -> Tuple[Optional[str], bool]:
        """``(slot, inherited)`` the strip shows for column-0 *index*."""
        slot = self._own(index)
        if slot is not None or not self.inherit:
            return slot, False
        parent = index.parent()
        while parent.isValid():
            slot = self._own(parent)
            if slot is not None:
                return slot, True
            parent = parent.parent()
        return None, False

    def _prune(self, *_args) -> None:
        """Drop the tags of rows the model removed (their keys went invalid)."""
        for layer in (self._user, self._auto):
            for key in [k for k in layer if not k.isValid()]:
                del layer[key]
        self.update()

    def _visible_rows(self):
        """``(column-0 index, top, height)`` per row in the viewport, top down."""
        view = self.view
        model = view.model()
        height = view.viewport().height()
        if isinstance(view, QtWidgets.QTableView):
            root = view.rootIndex()
            first = view.rowAt(0)
            if first < 0:
                return
            last = view.rowAt(height - 1)
            if last < 0:
                last = model.rowCount(root) - 1
            for row in range(first, last + 1):
                if not view.isRowHidden(row):
                    yield (
                        model.index(row, 0, root),
                        view.rowViewportPosition(row),
                        view.rowHeight(row),
                    )
        elif isinstance(view, QtWidgets.QTreeView):
            index = view.indexAt(QtCore.QPoint(0, 0))
            while index.isValid():
                rect = view.visualRect(index)
                if rect.top() >= height:
                    break
                yield index.sibling(index.row(), 0), rect.top(), rect.height()
                index = view.indexBelow(index)

    def _repaint(self, *_args) -> None:
        self.update()

    def _sync(self) -> None:
        """Pin the strip down the viewport's left edge, above it."""
        view = self.view
        if view is None:
            return
        viewport = view.viewport()
        if viewport is not None:
            geo = viewport.geometry()
            self.setGeometry(geo.x(), geo.y(), self.STRIP_WIDTH, geo.height())
        self.raise_()

    def eventFilter(self, obj, event):
        # Installed on the view and on its viewport: the viewport moves and
        # resizes as scrollbars and headers come and go.
        if event.type() in (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Move,
            QtCore.QEvent.Show,
        ):
            self._sync()
        return False

    def paintEvent(self, event):
        view = self.view
        if view is None or view.model() is None:
            return
        painter = QtGui.QPainter(self)
        try:
            for index, top, height in self._visible_rows():
                slot, inherited = self._shown(index)
                color = self._qcolors.get(slot)
                if color is None:
                    continue
                if inherited:
                    color = QtGui.QColor(color)
                    color.setAlpha(self.INHERITED_ALPHA)
                painter.fillRect(0, top, self.width(), height, color)
        finally:
            painter.end()
