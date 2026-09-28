# !/usr/bin/python
# coding=utf-8
"""A view's header menu of columns to show, hide and reorder, with the layout remembered.

:class:`ColumnConfig` attaches to any item view with a horizontal header -- a
plain ``QTableWidget`` / ``QTreeWidget`` as much as uitk's ``TableWidget`` and
``TreeWidget``, whose ``enable_column_config`` option is this class -- and gives
it:

* a right-click menu on the header, one checkable row per column (ticked while
  shown); the last column showing, and any column the host locks, can't be
  hidden;
* reordering: drag the header sections (``movable``), or -- ``reorderable`` --
  drag the menu's rows, which is how a view whose header click sorts gets one;
* a column's width behaviour kept with the column: one that takes the spare
  width goes on taking it wherever it is moved, and a fixed one moved last
  stays fixed (see :meth:`ColumnConfig._settle_fill`);
* the layout saved on every change (``hidden_columns`` and ``column_order``,
  logical indices, under one settings branch) and applied by :meth:`restore`.

The plain menu is a ``QMenu`` of checkable actions: a flat list of toggles,
where ``ContextMenu``'s flyouts and option boxes have nothing to add, and a
``QMenu`` parented to the header takes the window's stylesheet. The reorderable
one holds a list of the same rows instead, which stays up while rows are
ticked and dragged.
"""

from typing import Iterable, List, Optional

from qtpy import QtCore, QtGui, QtWidgets

from uitk.managers.cursor_manager import CursorManager
from uitk.managers.icon_manager import IconManager
from uitk.managers.settings_manager import SettingsManager


class _ColumnRows(QtWidgets.QListWidget):
    """The reorderable menu's rows: a click ticks one, a drag moves it.

    The drag is this widget's own press-move-release, not Qt's drag and drop:
    a ``QDrag`` runs a nested event loop inside the menu's popup, and a row
    only ever moves within this one list. A row goes where the pointer is as it
    moves; the release reports the order. A click that never moved toggles.
    """

    #: The logical columns, top to bottom, after a drag drops a row.
    reordered = QtCore.Signal(list)
    #: A row was clicked: its logical column.
    clicked_column = QtCore.Signal(int)

    #: Side of a row's tick (and of the blank that keeps unticked rows aligned).
    MARK_SIZE = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        # The menu's own panel shows through: the rows read as the plain menu's.
        self.setProperty("class", "transparentBgNoBorder")
        self.setIconSize(QtCore.QSize(self.MARK_SIZE, self.MARK_SIZE))
        self.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setToolTip("Click a column to show or hide it; drag it to move it.")
        self._pressed = None  # (item, press position) while the button is down
        self._dragging = False

    def columns(self) -> List[int]:
        return [self.item(r).data(QtCore.Qt.UserRole) for r in range(self.count())]

    #: Room after the widest label, so it doesn't run into the menu's edge.
    _TRAILING = 24

    def fit(self) -> None:
        """Size to show every row, no scroll bars."""
        rows = sum(self.sizeHintForRow(r) for r in range(self.count()))
        frame = 2 * self.frameWidth()
        width = self.sizeHintForColumn(0) + frame + self._TRAILING
        self.setFixedSize(width, rows + frame)

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        if event.button() != QtCore.Qt.LeftButton or item is None:
            return super().mousePressEvent(event)
        self._pressed = (item, event.pos())
        event.accept()

    def mouseMoveEvent(self, event):
        if self._pressed is None:
            return super().mouseMoveEvent(event)
        item, start = self._pressed
        if not self._dragging:
            travel = (event.pos() - start).manhattanLength()
            if travel < QtWidgets.QApplication.startDragDistance():
                return
            self._dragging = True
            item.setBackground(self.palette().highlight())
            CursorManager.push(self.viewport(), QtCore.Qt.ClosedHandCursor)
        target = self.indexAt(event.pos()).row()
        if target < 0:  # above the first row or below the last
            target = 0 if event.pos().y() < 0 else self.count() - 1
        row = self.row(item)
        if target != row:
            self.insertItem(target, self.takeItem(row))
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._pressed is None:
            return super().mouseReleaseEvent(event)
        item, _start = self._pressed
        dragged, self._pressed, self._dragging = self._dragging, None, False
        event.accept()
        if dragged:
            item.setBackground(QtGui.QBrush())
            CursorManager.pop(self.viewport())
            self.reordered.emit(self.columns())
        elif self.itemAt(event.pos()) is item:
            self.clicked_column.emit(item.data(QtCore.Qt.UserRole))

    def mouseDoubleClickEvent(self, event):
        # A quick second click toggles again rather than opening an editor.
        self.mousePressEvent(event)


class ColumnConfig(QtCore.QObject):
    """Show, hide and reorder a view's columns from its header; persisted.

    A child of the view's header, so it lives and dies with it; reach it with
    :meth:`of`, make it with :meth:`attach`.

    Parameters:
        view: The item view (a ``QTableView`` or ``QTreeView``, widgets included).
        settings: A ``SettingsManager`` (anything with ``branch`` / ``value`` /
            ``setValue`` / ``sync``). ``None`` makes one (``org="uitk"``,
            ``app=`` *app*).
        settings_key: The branch the layout is kept under: the view's
            ``objectName()`` by default, else its class name.
        locked: Logical columns that can't be hidden (a table's name column).
        app: The settings application name used when *settings* is ``None``.
        movable: Let the header sections be dragged into another order. Off
            where a header click sorts: Qt starts a section move on any press
            of a movable header, so a click that drifts drags instead.
        reorderable: The menu's rows can be dragged into another column order
            (a click on a row still shows or hides its column, and the menu
            stays up for the next). The way to reorder with *movable* off.
    """

    #: A reorderable menu row's role holding whether its column is shown (the
    #: row shows a tick while it is).
    SHOWN_ROLE = QtCore.Qt.UserRole + 1

    def __init__(
        self,
        view: QtWidgets.QAbstractItemView,
        settings=None,
        settings_key: Optional[str] = None,
        locked: Iterable[int] = (),
        app: str = "ColumnConfig",
        movable: bool = True,
        reorderable: bool = False,
    ):
        header = self.header_of(view)
        super().__init__(header)
        self.locked = set()
        self.reorderable = False
        self._settings = None
        self._moving = False
        #: True while ``stretchLastSection`` is this class's own fallback (see
        #: :meth:`_settle_fill`), not the view's way of filling.
        self._fallback = False
        self.configure(view, settings, settings_key, locked, app, movable, reorderable)
        header.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_menu)
        header.sectionMoved.connect(self._on_moved)

    # ------------------------------------------------------------ attaching
    @classmethod
    def attach(
        cls,
        view: QtWidgets.QAbstractItemView,
        settings=None,
        settings_key: Optional[str] = None,
        locked: Iterable[int] = (),
        app: str = "ColumnConfig",
        movable: bool = True,
        reorderable: bool = False,
    ) -> "ColumnConfig":
        """*view*'s column config, made on the first call and re-pointed after.

        Parameters are those of the class. A second call keeps the one menu
        and reconfigures it (settings, key, locked columns, movable,
        reorderable).
        """
        config = cls.of(view)
        if config is None:
            return cls(view, settings, settings_key, locked, app, movable, reorderable)
        config.configure(
            view, settings, settings_key, locked, app, movable, reorderable
        )
        return config

    @classmethod
    def of(cls, view: QtWidgets.QAbstractItemView) -> Optional["ColumnConfig"]:
        """The column config attached to *view*, or ``None``."""
        return cls.header_of(view).findChild(cls, "", QtCore.Qt.FindDirectChildrenOnly)

    @staticmethod
    def header_of(view: QtWidgets.QAbstractItemView) -> QtWidgets.QHeaderView:
        """*view*'s horizontal header (``horizontalHeader`` / a tree's ``header``)."""
        get = getattr(view, "horizontalHeader", None) or view.header
        return get()

    def configure(
        self,
        view: QtWidgets.QAbstractItemView,
        settings=None,
        settings_key: Optional[str] = None,
        locked: Iterable[int] = (),
        app: str = "ColumnConfig",
        movable: bool = True,
        reorderable: bool = False,
    ) -> None:
        """Point the layout at *settings* / *settings_key*; lock *locked*."""
        key = settings_key or view.objectName() or type(view).__name__
        if settings is None:
            settings = SettingsManager(org="uitk", app=app)
        self._settings = settings.branch(key)
        self.locked = set(locked)
        self.reorderable = bool(reorderable)
        self.header.setSectionsMovable(movable)

    # ------------------------------------------------------------ the columns
    @property
    def header(self) -> QtWidgets.QHeaderView:
        return self.parent()

    @property
    def settings(self):
        """The settings branch the layout is kept in."""
        return self._settings

    def labels(self) -> List[str]:
        """Each logical column's header text (``"Column <n>"`` when it has none)."""
        header = self.header
        model = header.model()
        out = []
        for column in range(header.count()):
            text = (
                model.headerData(column, header.orientation(), QtCore.Qt.DisplayRole)
                if model is not None
                else None
            )
            out.append(str(text) if text is not None else f"Column {column}")
        return out

    def order(self) -> List[int]:
        """The logical columns, left to right as the view shows them."""
        header = self.header
        return [header.logicalIndex(v) for v in range(header.count())]

    def can_hide(self, column: int) -> bool:
        """Whether *column* may be hidden: not locked, not the last one showing."""
        if column in self.locked:
            return False
        header = self.header
        return any(
            not header.isSectionHidden(c) for c in range(header.count()) if c != column
        )

    def set_hidden(self, column: int, hidden: bool = True) -> bool:
        """Hide (or show) *column* and save the layout.

        Returns:
            ``False`` when a guard refuses (see :meth:`can_hide`), else ``True``.
        """
        header = self.header
        if header.isSectionHidden(column) == bool(hidden):
            return True
        if hidden and not self.can_hide(column):
            return False
        self._settle_fill()  # the column filling is fixed before it can go
        header.setSectionHidden(column, bool(hidden))
        self._settle_fill()
        self.save()
        return True

    def set_order(self, order: Iterable[int]) -> bool:
        """Show the columns in *order* (logical indices, left to right); save.

        Returns:
            ``False`` when *order* is not every column exactly once.
        """
        order = list(order)
        if sorted(order) != list(range(self.header.count())):
            return False
        self._settle_fill()  # before a move changes which column is last
        self._move_to(order)
        self.save()
        return True

    def _move_to(self, order: List[int]) -> None:
        header = self.header
        self._moving = True
        try:
            for visual_target, logical in enumerate(order):
                current = header.visualIndex(logical)
                if current != visual_target:
                    header.moveSection(current, visual_target)
        finally:
            self._moving = False

    def _settle_fill(self, order: Optional[List[int]] = None) -> None:
        """Keep the spare width with the column(s) that take it.

        Qt's ``stretchLastSection`` fills a POSITION: once columns move, the
        old last one would shrink back and whatever landed last would take
        the spare width. So a view that fills that way has the fill handed,
        once, to the column holding it -- ``Stretch`` on that column, and
        ``stretchLastSection`` off -- before anything moves or hides. After
        that, ``stretchLastSection`` is only a fallback, on while every
        ``Stretch`` column is hidden, so the last one showing fills instead of
        a gap opening at the right edge; Qt gives it its own width back when a
        ``Stretch`` column returns. A view with no ``Stretch`` column (fixed
        widths, or a host sizing one itself) is left as it is.

        Parameters:
            order: The visual order to read "last" from (a header drag reports
                the move after it happened); defaults to the current one.
        """
        header = self.header
        if header.count() == 0:
            return
        stretch = QtWidgets.QHeaderView.Stretch
        if header.stretchLastSection() and not self._fallback:
            shown = [c for c in order or self.order() if not header.isSectionHidden(c)]
            header.setStretchLastSection(False)
            if shown:
                header.setSectionResizeMode(shown[-1], stretch)
        stretching = [
            c for c in range(header.count()) if header.sectionResizeMode(c) == stretch
        ]
        self._fallback = bool(stretching) and all(
            header.isSectionHidden(c) for c in stretching
        )
        header.setStretchLastSection(self._fallback)

    # ------------------------------------------------------------------ menu
    def build_menu(self) -> QtWidgets.QMenu:
        """The header menu, built but not shown: a ticked row per shown column,
        in the order the view shows them.

        A row that can't change anything is disabled (a locked column, the
        last one showing); a hidden column's row always can. A
        :attr:`reorderable` menu holds the rows as a list instead (see
        :class:`_ColumnRows`), acted on as they are clicked and dragged.
        """
        header = self.header
        menu = QtWidgets.QMenu(header)
        menu.setToolTipsVisible(True)
        if self.reorderable:
            rows = _ColumnRows(menu)
            self._fill_rows(rows)
            rows.clicked_column.connect(lambda column: self._toggle_row(rows, column))
            rows.reordered.connect(self.set_order)
            holder = QtWidgets.QWidgetAction(menu)
            holder.setDefaultWidget(rows)
            menu.addAction(holder)
            return menu
        labels = self.labels()
        for column in self.order():
            shown = not header.isSectionHidden(column)
            action = menu.addAction(labels[column])
            action.setCheckable(True)
            action.setChecked(shown)
            action.setEnabled(not shown or self.can_hide(column))
            if column in self.locked:
                action.setToolTip("Always shown.")
            action.setData(column)
        return menu

    def _fill_rows(self, rows: "_ColumnRows") -> None:
        """(Re)fill *rows* from the view: order, ticks, what can be toggled."""
        header = self.header
        labels = self.labels()
        size = rows.MARK_SIZE
        tick = IconManager.get("check", size=(size, size))
        blank = QtGui.QPixmap(size, size)
        blank.fill(QtCore.Qt.transparent)
        fixed = rows.palette().brush(QtGui.QPalette.Disabled, QtGui.QPalette.Text)
        rows.clear()
        for column in self.order():
            shown = not header.isSectionHidden(column)
            item = QtWidgets.QListWidgetItem(labels[column])
            item.setData(QtCore.Qt.UserRole, column)
            item.setData(self.SHOWN_ROLE, shown)
            item.setIcon(tick if shown else QtGui.QIcon(blank))
            if column in self.locked:
                tip = "Always shown; drag to move it."
            elif shown and not self.can_hide(column):
                tip = "The last column showing; drag to move it."
            else:
                tip = None
            if tip:  # a row a click can't change reads as the plain menu's
                item.setToolTip(tip)
                item.setForeground(fixed)
            rows.addItem(item)
        rows.fit()

    def _toggle_row(self, rows: "_ColumnRows", column: int) -> None:
        self.set_hidden(column, not self.header.isSectionHidden(column))
        self._fill_rows(rows)

    def show_menu(self, pos: QtCore.QPoint) -> None:
        """Open the menu at header position *pos*; apply the row picked."""
        menu = self.build_menu()
        try:
            chosen = menu.exec_(self.header.mapToGlobal(pos))
            if chosen is not None and chosen.data() is not None:
                self.set_hidden(chosen.data(), not chosen.isChecked())
        finally:
            menu.deleteLater()

    # ------------------------------------------------------------ persistence
    def _on_moved(self, logical: int, old_visual: int, _new_visual: int) -> None:
        """A section was dragged: keep the fill with its column, save the order.

        The move has already happened, so the order it started from -- where
        "last" is read -- is rebuilt by putting *logical* back.
        """
        if self._moving:
            return
        before = self.order()
        before.remove(logical)
        before.insert(old_visual, logical)
        self._settle_fill(before)
        self.save()

    def save(self) -> None:
        """Write the visibility and the visual order to the settings."""
        s = self._settings
        if s is None:
            return
        header = self.header
        count = header.count()
        s.setValue(
            "hidden_columns", [c for c in range(count) if header.isSectionHidden(c)]
        )
        s.setValue("column_order", self.order())
        s.sync()

    def restore(self) -> None:
        """Apply the saved visibility and order. Call once the headers are set.

        An order saved for another number of columns is ignored, and a locked
        column shows whatever was saved.
        """
        s = self._settings
        if s is None:
            return
        header = self.header
        count = header.count()
        self._settle_fill()  # the column the view fills with, as authored
        hidden = s.value("hidden_columns", [])
        if hidden:
            for column in range(count):
                header.setSectionHidden(
                    column, column in hidden and column not in self.locked
                )
        order = s.value("column_order", [])
        if order and len(order) == count:
            self._move_to(order)
        self._settle_fill()
