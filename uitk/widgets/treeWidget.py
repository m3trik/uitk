# !/usr/bin/python
# coding=utf-8
import html
from qtpy import QtWidgets, QtGui, QtCore
from typing import Optional, Callable, List, Union, Any, Dict

import pythontk as ptk

# From this package:
from uitk.widgets.mixins.item_format import ItemFormatMixin
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.menu_mixin import MenuMixin
from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter
from uitk.widgets.overflow_indicator import OverflowIndicator
from uitk.widgets.row_tags import RowTags
from uitk.managers.icon_manager import IconManager
from uitk.themes.style_sheet import StyleSheet
from uitk.switchboard import Signals
from uitk.widgets.column_config import ColumnConfig


class HierarchyIconMixin:
    """The tree's hierarchy, drawn by the tree itself (``TreeWidget.drawBranches``):
    guide lines that hang each row from its parent's expander, so every level
    reads as one line down from its parent, and the expander -- a thin-walled
    box with a plus or a minus filling the indentation cell, as Maya's
    outliner draws it, or a chevron (:meth:`set_icon_style`). The colours are
    the tree's text colour at :attr:`BRANCH_ALPHA`'s strengths, so they follow
    the theme; the expander under the pointer is drawn at full strength.
    Off (:meth:`enable_hierarchy_icons`): the style's own branches.

    Weighed: the sheet's ``::branch`` rules with an SVG per branch state, the
    route this replaced. An image fills one branch cell, so a child's line
    could not run from its parent's box, and a file has one colour, so the
    guides could not follow the theme (``#555`` on ``#393939``).

    The tree's own sheet (:meth:`_apply_hierarchy_stylesheet`) sets its
    ground, its text and its rows' height (:meth:`set_row_height`).
    """

    _HIER_START = "/* __HIERARCHY_START__ */"
    _HIER_END = "/* __HIERARCHY_END__ */"

    #: How much of the text colour each part shows: the guide lines, the
    #: expander's box and its sign (a hovered expander: all of it).
    BRANCH_ALPHA = {"line": 0.3, "box": 0.55, "sign": 0.85}
    #: The expander's styles: a box with a plus or minus, or a chevron.
    ICON_STYLES = ("plus_minus", "arrows")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._hierarchy_icons_enabled = True
        self._icon_style = "plus_minus"
        self._row_height = 16
        self._last_shown = {}  # each parent's last row shown, since the last layout
        self._hot_branch = None  # the expander under the pointer (_set_hot_branch)
        self._apply_hierarchy_stylesheet()

    def _apply_hierarchy_stylesheet(self):
        """The tree's own sheet: its ground and text, and its rows' height."""
        height = self._row_height
        style = f"""
            QTreeWidget {{
                outline: none;
                background-color: #393939;
                color: #cccccc;
                selection-background-color: transparent;
                show-decoration-selected: 1;
                font-size: 12px;
                gridline-color: transparent;
            }}

            /* No colour here: the widget rule above gives the text its colour.
               A colour on ::item would beat every cell's own foreground brush. */
            QTreeWidget::item {{
                padding: 0px 2px;
                border: none;
                min-height: {height}px;
                max-height: {height}px;
                background: transparent;
                spacing: 0px;
                margin: 0px;
            }}

            QTreeWidget::item:selected {{
                background-color: rgba(90, 140, 190, 0.08);
                color: #ffffff;
                border: none;
            }}

            QTreeWidget::item:hover:!selected {{
                background-color: rgba(255, 255, 255, 0.1);
            }}
        """

        tagged = f"{self._HIER_START}\n{style}\n{self._HIER_END}"
        current = self.styleSheet()
        start = current.find(self._HIER_START)
        end = current.find(self._HIER_END)
        if start != -1 and end != -1:
            current = current[:start] + current[end + len(self._HIER_END) :]
        # Pinned first: a sheet of its own would otherwise measure and draw
        # what it leaves undefined -- the indent and the sort arrows -- in the
        # host's style.
        StyleSheet.pin_base_style(self)
        self.setStyleSheet(current + tagged)

    def set_row_height(self, height: int) -> None:
        """Give every row *height* px (16 by default): a cell widget taller
        than it makes its row taller, so a tree whose cells hold widgets sets
        at least their height to keep its rows even. Setting the height it
        has changes nothing (a new sheet re-polishes the whole tree)."""
        if int(height) == self._row_height:
            return
        self._row_height = int(height)
        if self._hierarchy_icons_enabled:
            self._apply_hierarchy_stylesheet()

    def set_icon_style(self, style: str):
        """Set the expander's style (:attr:`ICON_STYLES`): ``"plus_minus"``, a
        thin-walled box with a plus or a minus (the default), or ``"arrows"``,
        a chevron pointing right or down. ``"modern"`` reads as ``"arrows"``.

        Raises:
            ValueError: *style* is none of them; the current one stays.
        """
        style = "arrows" if style == "modern" else style
        if style not in self.ICON_STYLES:
            raise ValueError(f"Unknown icon style {style!r}: one of {self.ICON_STYLES}")
        self._icon_style = style
        self.viewport().update()

    def enable_hierarchy_icons(self, enabled=True):
        """Draw the hierarchy as this tree does (guides and expanders), or
        leave it to Qt and its style (``False``), with no sheet of the tree's own."""
        self._hierarchy_icons_enabled = enabled
        if enabled:
            self._apply_hierarchy_stylesheet()
        else:
            current = self.styleSheet()
            start = current.find(self._HIER_START)
            end = current.find(self._HIER_END)
            if start != -1 and end != -1:
                self.setStyleSheet(
                    current[:start] + current[end + len(self._HIER_END) :]
                )
        self.viewport().update()

    def get_available_icon_styles(self) -> list:
        """The expander's styles (:attr:`ICON_STYLES`)."""
        return list(self.ICON_STYLES)

    def get_current_icon_style(self) -> str:
        """The expander's current style."""
        return self._icon_style

    # -- painting ------------------------------------------------------------

    def _branch_pen(self, part: str, full: bool = False) -> QtGui.QPen:
        """A 1 px pen in the text colour at *part*'s strength (all of it where *full*)."""
        color = QtGui.QColor(self.palette().color(QtGui.QPalette.Text))
        color.setAlphaF(1.0 if full else self.BRANCH_ALPHA[part])
        pen = QtGui.QPen(color, 1)
        pen.setCapStyle(QtCore.Qt.FlatCap)
        return pen

    def _has_later_shown_sibling(self, index) -> bool:
        """Whether a row after *index* under its parent is shown (not hidden)."""
        parent = index.parent()
        key = (parent.row(), parent.internalId()) if parent.isValid() else None
        last = self._last_shown.get(key)
        if last is None:
            last = -1
            for row in range(self.model().rowCount(parent) - 1, -1, -1):
                if not self.isRowHidden(row, parent):
                    last = row
                    break
            self._last_shown[key] = last
        return index.row() < last

    def _paint_branches(self, painter, rect, index) -> None:
        """Paint *index*'s row's guides and its expander in *rect*, its
        indentation: a cell per level, the row's own last.

        Each row hangs from its parent's expander: an elbow in the parent's
        cell runs down from the row above and across to the row, continuing
        down while a later sibling is shown; each ancestor further left
        continues its own line through the row while one of its children
        below is shown. A row with children has its expander in its own cell,
        a line running on down from it while it is open."""
        indent = self.indentation()
        if indent <= 0 or rect.width() < indent:
            return
        levels = rect.width() // indent
        left, top, height = rect.left(), rect.top(), rect.height()
        side = min(indent, height) - 5  # 11 px in a 16 px cell: room around it
        side -= 1 - side % 2  # odd: the sign sits on a pixel
        box_x = (indent - side) // 2  # in its cell
        box_y = top + (height - side) // 2
        mid_x = box_x + side // 2 + 0.5  # in a cell: where its line runs
        mid_y = box_y + side // 2 + 0.5

        def x_of(cell: int) -> float:
            return left + cell * indent + mid_x

        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        painter.setPen(self._branch_pen("line"))
        own = levels - 1
        model = self.model()
        has_children = model.hasChildren(index)
        expanded = has_children and self.isExpanded(index)

        # The elbow in the parent's cell, then each ancestor's line further left.
        node, cell = index, own - 1
        if cell >= 0 and index.parent().isValid():
            x = x_of(cell)
            bottom = top + height if self._has_later_shown_sibling(index) else mid_y
            painter.drawLine(QtCore.QPointF(x, top), QtCore.QPointF(x, bottom))
            end = left + own * indent + (box_x if has_children else indent - 2)
            painter.drawLine(QtCore.QPointF(x, mid_y), QtCore.QPointF(end, mid_y))
            node, cell = index.parent(), cell - 1
            while cell >= 0 and node.parent().isValid():
                if self._has_later_shown_sibling(node):
                    x = x_of(cell)
                    painter.drawLine(
                        QtCore.QPointF(x, top), QtCore.QPointF(x, top + height)
                    )
                node, cell = node.parent(), cell - 1

        if has_children:
            cell_left = left + own * indent
            box = QtCore.QRectF(
                cell_left + box_x + 0.5, box_y + 0.5, side - 1, side - 1
            )
            if expanded and model.rowCount(index):
                x = x_of(own)
                painter.drawLine(
                    QtCore.QPointF(x, box.bottom() + 1), QtCore.QPointF(x, top + height)
                )
            hot = (
                self._hot_branch is not None
                and self._hot_branch == index.siblingAtColumn(0)
            )
            self._paint_expander(painter, box, expanded, hot)
        painter.restore()

    def _expander_at(self, pos) -> QtCore.QModelIndex:
        """The row (column 0) whose expander cell holds viewport point *pos*;
        an invalid index where none does."""
        index = self.indexAt(pos)
        if not index.isValid():
            return QtCore.QModelIndex()
        cell = index.siblingAtColumn(self.treePosition())
        if not self.model().hasChildren(cell):
            return QtCore.QModelIndex()
        right = self.visualRect(cell).left()
        if right - self.indentation() <= pos.x() < right:
            return cell.siblingAtColumn(0)
        return QtCore.QModelIndex()

    def _set_hot_branch(self, index) -> None:
        """Make *index*'s expander the one drawn hot (an invalid index: none),
        repainting the row it leaves and the row it reaches. Qt repaints a
        hovered row's cells, never its indentation: an expander that judged
        the pointer while painted stayed lit after it left."""
        new = QtCore.QPersistentModelIndex(index) if index.isValid() else None
        old = self._hot_branch
        if (old is None) == (new is None) and (old is None or old == new):
            return
        self._hot_branch = new
        viewport = self.viewport()
        for each in (old, new):
            if each is not None and each.isValid():
                rect = self.visualRect(self.model().index(each.row(), 0, each.parent()))
                viewport.update(
                    QtCore.QRect(0, rect.top(), viewport.width(), rect.height())
                )

    def _paint_expander(
        self, painter, box: QtCore.QRectF, expanded: bool, hot: bool
    ) -> None:
        """The expander in *box*: a thin-walled square with a minus while
        open, a plus while closed -- or a chevron (``"arrows"``)."""
        cx, cy = box.center().x(), box.center().y()
        arm = (box.width() - 5) / 2  # the sign's half length, 3 px inside the wall
        if self._icon_style == "arrows":
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            pen = self._branch_pen("sign", hot)
            pen.setWidthF(1.5)
            painter.setPen(pen)
            a = arm * 0.8
            if expanded:
                points = [(cx - a, cy - a / 2), (cx, cy + a / 2), (cx + a, cy - a / 2)]
            else:
                points = [(cx - a / 2, cy - a), (cx + a / 2, cy), (cx - a / 2, cy + a)]
            painter.drawPolyline(
                QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points])
            )
            return
        if hot:
            ground = QtGui.QColor(self.palette().color(QtGui.QPalette.Text))
            ground.setAlphaF(0.12)
            painter.fillRect(box, ground)
        painter.setPen(self._branch_pen("box", hot))
        painter.drawRect(box)
        # The sign as whole pixels: 2 px clear of the walls, on the centre pixel.
        sign = self._branch_pen("sign", hot).color()
        px, py = int(cx), int(cy)
        reach = (int(box.width()) - 5) // 2
        painter.fillRect(QtCore.QRect(px - reach, py, 2 * reach + 1, 1), sign)
        if not expanded:
            painter.fillRect(QtCore.QRect(px, py - reach, 1, 2 * reach + 1), sign)


class TreeFormatMixin(ItemFormatMixin):
    """Generic item/column formatting for QTreeWidget.

    The colour map, formatter store and colour resolution are
    :class:`~uitk.widgets.mixins.item_format.ItemFormatMixin`'s, shared with
    ``TableWidget`` (one ``ACTION_COLOR_MAP``: mayatk's
    reference_manager reads ``widget.ACTION_COLOR_MAP["current"]`` off either).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._item_formatters = {}
        self._column_formatters = {}
        self._item_defaults = {}  # {item_id: (fg, bg)}
        self.itemChanged.connect(self._on_item_edited)

    # Public API
    def set_item_formatter(self, item_id, formatter, append=False):
        """Set a formatter for a specific item by ID."""
        self._set_formatter(self._item_formatters, item_id, formatter, append)

    def set_column_formatter(self, col, formatter, append=False):
        """Set a formatter for a specific column."""
        self._set_formatter(self._column_formatters, col, formatter, append)

    def clear_formatters(self):
        """Clear all item and column formatters."""
        self._item_formatters.clear()
        self._column_formatters.clear()
        self._item_defaults.clear()

    def apply_formatting(self):
        """Apply formatting based on the registered formatters."""
        # Block signals for the duration: formatters modify item roles
        # (foreground/background), which fires itemChanged -> _on_item_edited
        # -> formatters -> ... (unbounded recursion -> RecursionError when
        # multiple/appended formatters set differing roles). Mirrors the same
        # guard on TableWidget.apply_formatting.
        with self._formatting_signals_blocked():
            iterator = QtWidgets.QTreeWidgetItemIterator(self)
            while iterator.value():
                item = iterator.value()
                for col in range(self.columnCount()):
                    for fmt in self._get_formatters(item, col):
                        fmt(
                            item,
                            item.data(col, QtCore.Qt.UserRole) or item.text(col),
                            col,
                            self,
                        )
                iterator += 1

    def ensure_valid_color(self, color, color_type, item, col):
        """Ensure a valid QColor, using fallback if needed."""
        return self._valid_color(
            color, color_type, lambda: self._get_default_colors(item, col)
        )

    def set_action_color(
        self,
        item: QtWidgets.QTreeWidgetItem,
        key: str,
        col: int = 0,
        use_bg: bool = False,
    ):
        """Apply semantic color to a tree item."""
        fg_raw, bg_raw = self.ACTION_COLOR_MAP.get(str(key).lower(), (None, None))

        # Skip entirely if reset and nothing to restore
        if key == "reset" and fg_raw is None and bg_raw is None:
            return

        fg = self.ensure_valid_color(fg_raw, "fg", item, col)
        bg = self.ensure_valid_color(bg_raw, "bg", item, col) if use_bg else None

        default_fg, default_bg = self._get_default_colors(item, col)
        fg = fg or self.to_qobject(default_fg, "QColor")
        if use_bg:
            bg = bg or self.to_qobject(default_bg, "QColor")

        if fg:
            item.setForeground(col, fg)
        if use_bg and bg:
            item.setBackground(col, bg)

    def action_color_formatter(self, item, value, col, *_):
        """Formatter that applies action colors based on item value."""
        key = str(value).lower()
        fg, bg = TreeFormatMixin.ACTION_COLOR_MAP.get(key, (None, None))
        fg = self.ensure_valid_color(fg, "fg", item, col)
        bg = self.ensure_valid_color(bg, "bg", item, col)
        if fg:
            item.setForeground(col, fg)
        if bg:
            item.setBackground(col, bg)

    def make_color_map_formatter(self, color_map: dict):
        """Create a formatter from a color mapping dictionary."""

        def _fmt(item, value, col, *_):
            key = str(value).lower()
            fg_raw, bg_raw = color_map.get(key, (None, None))
            if fg_raw is not None:
                fg = self.ensure_valid_color(fg_raw, "fg", item, col)
                if fg:
                    item.setForeground(col, fg)
            if bg_raw is not None:
                bg = self.ensure_valid_color(bg_raw, "bg", item, col)
                if bg:
                    item.setBackground(col, bg)

        return _fmt

    # Private methods
    def _on_item_edited(self, item, col):
        """Handle item editing to reapply formatting."""
        for fmt in self._get_formatters(item, col):
            fmt(item, item.data(col, QtCore.Qt.UserRole) or item.text(col), col, self)

    def _get_default_colors(self, item, col: int):
        """Get the cached default colors for the item at the given column."""
        item_id = id(item)
        if not hasattr(self, "_item_defaults"):
            self._item_defaults = {}
        key = (item_id, col)
        cache = self._item_defaults
        if key not in cache:
            fg = item.foreground(col).color().name()
            bg = item.background(col).color().name()
            cache[key] = (fg, bg)
        return cache[key]

    def _get_formatters(self, item, col) -> list:
        """Get all formatters that apply to the given item and column."""
        formatters = []
        item_id = id(item)

        # Item-specific formatters
        if item_id in self._item_formatters:
            formatters.extend(self._item_formatters[item_id])

        # Column formatters
        if col in self._column_formatters:
            formatters.extend(self._column_formatters[col])

        return formatters


class _RowTintDelegate(QtWidgets.QStyledItemDelegate):
    """Composites column tints, row tints, and per-item colors into a single
    solid opaque background that is immune to Maya's QSS overrides.

    Compositing order (each layer alpha-blends onto the previous):

      1. Base        — widget viewport background (``#393939``)
      2. Alternate   — ``tree.alternateRowColor`` on every other row shown
                       while ``alternatingRowColors`` is on, unless the row has
                       a row tint (layer 4): that tint is its ground
      3. Column tint — ``tree._column_tints[col]``
      4. Row tint    — ``tree._parent_row_color`` or ``tree._child_row_color``
      5. Item bg     — per-item ``BackgroundRole`` (assessment / status colors)
      6. Selection   — translucent overlay when ``selection_style == "tint"``

    Layers 1-5 are the tree's (``TreeWidget._ground``), which paints them under
    a row's indentation too (``TreeWidget.drawRow``). The result is an opaque
    color painted via ``fillRect`` **and** injected into
    ``option.backgroundBrush`` so that ``super().paint()`` cannot override it
    with a QSS-resolved background.
    """

    _SEL_TINT = QtGui.QColor(90, 140, 190, 45)

    @staticmethod
    def _alpha_over(base, overlay):
        """Alpha-composite *overlay* onto an opaque *base*, return opaque QColor.

        Both arguments are ``QColor``.  The result always has alpha 255.
        """
        a = overlay.alphaF()
        r = min(int(base.red() * (1 - a) + overlay.red() * a + 0.5), 255)
        g = min(int(base.green() * (1 - a) + overlay.green() * a + 0.5), 255)
        b = min(int(base.blue() * (1 - a) + overlay.blue() * a + 0.5), 255)
        return QtGui.QColor(r, g, b)

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # Inject per-item ForegroundRole into the palette so the style engine
        # uses it for text drawing, bypassing QSS ``color:`` rules.
        fg = index.data(QtCore.Qt.ForegroundRole)
        if isinstance(fg, QtGui.QBrush) and fg.color().isValid():
            option.palette.setColor(QtGui.QPalette.Text, fg.color())

    #: How much of the cell's text colour a tail's lead shows (``set_cell_tail``).
    LEAD_ALPHA = 0.55

    @staticmethod
    def _tail_layout(text: str, start: int, width: int, metrics, bold_metrics) -> tuple:
        """``(lead, tail)`` as shown for *text* split at *start* in *width* px:
        the tail whole and the lead cut from its left to fit beside it ("…"
        first); a tail wider than *width* alone, cut at its end."""
        lead, tail = text[:start], text[start:]
        room = width - bold_metrics.horizontalAdvance(tail)
        if room <= 0:
            return "", bold_metrics.elidedText(tail, QtCore.Qt.ElideRight, width)
        return metrics.elidedText(lead, QtCore.Qt.ElideLeft, room), tail

    def _paint_tail(self, painter, option, index, start: int, ground) -> None:
        """The cell with its text as a muted lead and a semi-bold tail
        (``TreeWidget.set_cell_tail``), every part drawn by the style, so the
        text takes the colour the sheet gives the cell's state
        (``::item:selected``, ``::item:hover``): the style resolves it only
        while it draws the cell (``CE_ItemViewItem``), never for
        ``drawItemText`` or the palette. The cell's panel is drawn once:
        the tail's columns get the style's cell shifted to write the tail
        after the lead, the rest the cell without text, and the lead -- the
        style's cell on the opaque *ground*, offscreen -- lies over it at
        :attr:`LEAD_ALPHA`, which over an opaque layer is the lead's text
        alone, faded.

        Weighed: the styled delegate's own paint writes one string in one
        font; text drawn with the palette's colours loses the sheet's
        selected and hovered colours that a plain cell beside it shows.
        """
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget is not None else QtWidgets.QApplication.style()
        area = style.subElementRect(QtWidgets.QStyle.SE_ItemViewItemText, opt, widget)
        margin = (
            style.pixelMetric(QtWidgets.QStyle.PM_FocusFrameHMargin, None, widget) + 1
        )
        area = area.adjusted(margin, 0, -margin, 0)
        bold = QtGui.QFont(opt.font)
        bold.setWeight(QtGui.QFont.DemiBold)
        metrics = QtGui.QFontMetrics(opt.font)
        lead, tail = self._tail_layout(
            opt.text, start, area.width(), metrics, QtGui.QFontMetrics(bold)
        )
        cell = opt.rect
        x = area.left() + metrics.horizontalAdvance(lead)  # where the tail starts
        tail_columns = QtCore.QRect(x, cell.top(), area.right() - x + 1, cell.height())

        def draw(target, text, font, clip, shift=0):
            part = QtWidgets.QStyleOptionViewItem(opt)
            part.text, part.font, part.rect = text, font, cell.translated(shift, 0)
            target.save()
            target.setClipRegion(clip, QtCore.Qt.IntersectClip)
            style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, part, target, widget)
            target.restore()

        draw(
            painter,
            "",
            opt.font,
            QtGui.QRegion(cell).subtracted(QtGui.QRegion(tail_columns)),
        )
        draw(painter, tail, bold, QtGui.QRegion(tail_columns), shift=x - area.left())
        if lead:
            ratio = painter.device().devicePixelRatioF()
            layer = QtGui.QImage(
                cell.size() * ratio, QtGui.QImage.Format_ARGB32_Premultiplied
            )
            layer.setDevicePixelRatio(ratio)
            layer.fill(ground)
            offscreen = QtGui.QPainter(layer)
            offscreen.translate(-cell.topLeft())
            draw(offscreen, lead, opt.font, QtGui.QRegion(cell))
            offscreen.end()
            painter.save()
            painter.setClipRect(
                QtCore.QRect(cell.left(), cell.top(), x - cell.left(), cell.height()),
                QtCore.Qt.IntersectClip,
            )
            painter.setOpacity(self.LEAD_ALPHA)
            painter.drawImage(cell.topLeft(), layer)
            painter.restore()

    def paint(self, painter, option, index):
        tree = self.parent()
        alternate = bool(option.features & QtWidgets.QStyleOptionViewItem.Alternate)
        bg = tree._ground(index, alternate)

        # Layer 6 — selection tint (only when selection_style == "tint")
        use_tint = getattr(tree, "_selection_style", "border") == "tint"
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        if use_tint and selected:
            bg = _RowTintDelegate._alpha_over(bg, self._SEL_TINT)
            # Strip State_Selected so the QSS border rule doesn't fire.
            option.state &= ~QtWidgets.QStyle.State_Selected

        # Paint the single solid composite and inject it into the option
        # so super().paint() uses it instead of the QSS-resolved background.
        painter.fillRect(option.rect, bg)
        option.backgroundBrush = QtGui.QBrush(bg)

        start = index.data(TreeWidget.TAIL_ROLE)
        if isinstance(start, int) and index.data(QtCore.Qt.DisplayRole):
            self._paint_tail(painter, option, index, start, bg)
        else:
            super().paint(painter, option, index)


class _HeaderActionBar(QtWidgets.QWidget):
    """Right-aligned strip of icon buttons overlaid on a QHeaderView.

    Parented to the header's viewport so it floats over the header without
    requiring a custom QHeaderView subclass.  Repositioned automatically
    when the tree resizes.

    Not intended for direct use — access via ``TreeWidget.header_actions``.
    """

    def __init__(self, tree: "TreeWidget") -> None:
        header = tree.header()
        super().__init__(header.viewport())
        self._tree = tree
        self._buttons: Dict[str, QtWidgets.QToolButton] = {}
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 4, 0)
        self._layout.setSpacing(2)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self._reposition()

    # -- public API ----------------------------------------------------------

    def add(
        self,
        name: str,
        icon: str,
        tooltip: str = "",
        callback: Optional[Callable] = None,
        toggle: bool = False,
        checked: bool = False,
    ) -> QtWidgets.QToolButton:
        """Add a named icon button to the strip.

        Parameters
        ----------
        name : str
            Unique identifier for the button.
        icon : str
            Icon name resolved by ``IconManager``.
        tooltip : str
            Tooltip text.
        callback : callable, optional
            Connected to ``clicked(bool)`` for toggles or ``clicked()``
            for momentary buttons.
        toggle : bool
            If ``True`` the button is checkable.
        checked : bool
            Initial checked state (only meaningful when *toggle* is True).

        Returns
        -------
        QToolButton
            The created button, for further customization if needed.
        """
        if name in self._buttons:
            self.remove(name)

        btn = QtWidgets.QToolButton(self)
        btn.setAutoRaise(True)
        btn.setFocusPolicy(QtCore.Qt.NoFocus)
        btn.setToolTip(tooltip)
        TooltipPresenter.manage(btn)

        h = max(self._tree.header().height() - 4, 16)
        btn.setFixedSize(h, h)
        icon_size = max(int(h * 0.7), 10)
        btn.setIconSize(QtCore.QSize(icon_size, icon_size))
        btn.setIcon(IconManager.get(icon, size=(icon_size, icon_size)))
        btn.setObjectName(f"hdr_action_{name}")

        if toggle:
            btn.setCheckable(True)
            btn.setChecked(checked)

        if callback is not None:
            btn.clicked.connect(callback)

        self._buttons[name] = btn
        self._layout.addWidget(btn)
        self._reposition()
        self.show()
        return btn

    def remove(self, name: str) -> None:
        """Remove a button by name."""
        btn = self._buttons.pop(name, None)
        if btn is not None:
            self._layout.removeWidget(btn)
            btn.deleteLater()
            self._reposition()
            if not self._buttons:
                self.hide()

    def get(self, name: str) -> Optional[QtWidgets.QToolButton]:
        """Return the button for *name*, or ``None``."""
        return self._buttons.get(name)

    def set_checked(self, name: str, checked: bool) -> None:
        """Programmatically set a toggle button's checked state."""
        btn = self._buttons.get(name)
        if btn is not None and btn.isCheckable():
            btn.setChecked(checked)

    def is_checked(self, name: str) -> bool:
        """Query a toggle button's checked state."""
        btn = self._buttons.get(name)
        return btn.isChecked() if btn is not None and btn.isCheckable() else False

    def clear(self) -> None:
        """Remove all buttons."""
        for btn in list(self._buttons.values()):
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()
        self.hide()

    # -- internal ------------------------------------------------------------

    def _reposition(self) -> None:
        """Right-align self within the header viewport."""
        header = self._tree.header()
        vp = header.viewport()
        hint = self.sizeHint()
        x = vp.width() - hint.width()
        y = (header.height() - hint.height()) // 2
        self.setGeometry(max(x, 0), max(y, 0), hint.width(), hint.height())


class TreeWidget(
    QtWidgets.QTreeWidget,
    MenuMixin,
    AttributesMixin,
    TreeFormatMixin,
    HierarchyIconMixin,
):
    """Enhanced QTreeWidget with flexible data handling, formatting capabilities, and custom hierarchy icons."""

    # Qt Designer widget-box entry.
    designer_spec = {"icon": "branch", "object_name": "tree", "size": (240, 180)}

    # Signals
    item_selected = QtCore.Signal(QtWidgets.QTreeWidgetItem)
    item_data_changed = QtCore.Signal(QtWidgets.QTreeWidgetItem, int)

    #: The item role (on column 0) holding a row's tooltip (:meth:`set_row_tooltip`).
    ROW_TOOLTIP_ROLE = QtCore.Qt.UserRole + 101
    #: The item role (per column) holding where a cell's tail starts (:meth:`set_cell_tail`).
    TAIL_ROLE = QtCore.Qt.UserRole + 102

    def __init__(
        self,
        parent=None,
        selection_mode="extended",
        ctrl_toggle=True,
        selection_style="border",
        **kwargs,
    ):
        """
        Initialize TreeWidget.

        Args:
            parent: Parent widget
            selection_mode: Selection mode string. Options:
                - "none": No selection allowed
                - "single": Single item selection only
                - "extended": Ctrl+Click multi-selection (default)
                - "multi": Click to toggle selection
            ctrl_toggle: If True (default), Ctrl+click on a selected item
                deselects it. If False, Ctrl+click only adds to selection.
            selection_style: Visual style for selected items.
                - "border": Top/bottom blue border (default)
                - "tint": Translucent blue overlay composited by the delegate
            **kwargs: Additional attributes to set
        """
        super().__init__(parent)
        self._selection_style = selection_style
        self._shown_rows = {}  # the rows' numbers since the last layout (_shown_row)
        TreeFormatMixin.__init__(self)
        HierarchyIconMixin.__init__(self)
        # Arrows at the top/bottom edge while rows are scrolled out of view.
        OverflowIndicator.attach(self)

        # Default settings
        self.setProperty("class", self.__class__.__name__)
        self.setAlternatingRowColors(False)
        self.setRootIsDecorated(True)
        self.setIndentation(16)  # Match icon width for proper alignment
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        # Set selection mode
        self._set_selection_mode(selection_mode)

        # Ctrl+click toggle deselection
        self._ctrl_toggle = ctrl_toggle

        # For custom deselection behavior
        self._last_clicked_item = None
        self._was_selected = False
        self._ctrl_pressed = False
        self._shift_pressed = False
        self._click_timer = QtCore.QTimer()
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._handle_delayed_click)

        # Column stretch support
        self._stretch_column = None

        # Full cell text in a cut-short cell's tooltip (``elided_tooltips``).
        self._elided_tooltips = False

        # Header action bar (lazy — created on first access)
        self._header_actions = None

        # Row and column tinting (composited by _RowTintDelegate). A sheet's
        # qproperty is set again at every polish, over the colour a panel set,
        # so the theme sets none of these: the child rows' default is set
        # here, and the alternate ground's is a property of its own
        # (defaultAlternateRowColor) under the panel's (alternateRowColor).
        self._child_row_color = QtGui.QColor(255, 255, 255, 10)
        self._parent_row_color = QtGui.QColor()
        self._alternate_row_color = QtGui.QColor()  # none: the default's
        self._default_alternate_row_color = QtGui.QColor(255, 255, 255, 8)
        self._column_tints = {}  # {col_index: QColor}
        self.setItemDelegate(_RowTintDelegate(self))

        # Connect signals
        self.itemSelectionChanged.connect(self._on_selection_changed)
        # An animated expand or collapse lays the rows out with no
        # updateGeometries until the animation ends.
        self.expanded.connect(self._forget_rows_shown)
        self.collapsed.connect(self._forget_rows_shown)

        self.set_attributes(**kwargs)

    # -- selection style -----------------------------------------------------

    @property
    def selection_style(self) -> str:
        """Visual style for selected items: ``"border"`` or ``"tint"``."""
        return self._selection_style

    @selection_style.setter
    def selection_style(self, value: str):
        self._selection_style = value
        self.viewport().update()

    # -- elided-cell tooltips -----------------------------------------------

    @property
    def elided_tooltips(self) -> bool:
        """Show a cell's full text in its tooltip while the cell shows it cut
        short (elided, or past its first line). Off by default.

        The cell's own tooltip, if any, follows the text -- unless it already
        holds it. Composed at hover time (:meth:`item_tooltip`), so it follows
        column resizes with nothing stored on the items. Turning it on hands
        the tree to ``TooltipPresenter`` (a registered widget already is), the
        one path that asks :meth:`item_tooltip`.
        """
        return self._elided_tooltips

    @elided_tooltips.setter
    def elided_tooltips(self, value: bool) -> None:
        self._elided_tooltips = bool(value)
        if self._elided_tooltips:
            TooltipPresenter.manage(self)

    def is_elided(self, index) -> bool:
        """Whether the cell at *index* shows its text cut short: wider than its
        text area, or more than one line."""
        text = index.data(QtCore.Qt.DisplayRole)
        if not isinstance(text, str) or not text.strip():
            return False
        if "\n" in text.strip():
            return True
        option = QtWidgets.QStyleOptionViewItem()
        self.initViewItemOption(option)
        option.rect = self.visualRect(index)
        self.itemDelegateForIndex(index).initStyleOption(option, index)
        style = self.style()
        area = style.subElementRect(QtWidgets.QStyle.SE_ItemViewItemText, option, self)
        margin = style.pixelMetric(QtWidgets.QStyle.PM_FocusFrameHMargin, None, self)
        return option.fontMetrics.horizontalAdvance(text) > area.width() - 2 * (
            margin + 1
        )

    def item_tooltip(self, index, text: Optional[str]) -> Optional[str]:
        """The tooltip of the cell at *index*: its row's (:meth:`set_row_tooltip`),
        then its own *text* -- led by the cell's full text when
        :attr:`elided_tooltips` is on and the cell shows it cut short.
        ``TooltipPresenter`` calls this at hover time."""
        if self._elided_tooltips and self.is_elided(index):
            full = index.data(QtCore.Qt.DisplayRole).strip()
            if not text or full in text:
                text = text or full
            else:
                text = self._join_tooltips(full, text)
        row = index.siblingAtColumn(0).data(self.ROW_TOOLTIP_ROLE)
        if not row:
            return text
        return self._join_tooltips(row, text) if text else row

    @staticmethod
    def _join_tooltips(first: str, second: str) -> str:
        """*first* above *second*, a blank line apart -- as rich text when
        either is, the plain one escaped."""
        is_rich = ptk.TooltipFormat.is_rich
        if not (is_rich(first) or is_rich(second)):
            return f"{first}\n\n{second}"
        first, second = (
            t if is_rich(t) else html.escape(t).replace("\n", "<br>")
            for t in (first, second)
        )
        return f"{first}<br><br>{second}"

    def set_row_tooltip(self, item, text: Optional[str]) -> None:
        """Give *item*'s row a tooltip every cell shows ahead of its own -- a
        status for the whole row -- or clear it (``None``).

        Kept on the item (:attr:`ROW_TOOLTIP_ROLE`) and composed at hover
        time (:meth:`item_tooltip`), so a cell tooltip set before or after it
        stays its own.  Hands the tree to ``TooltipPresenter``.

        Parameters:
            item: The row's ``QTreeWidgetItem``.
            text: Plain or rich text; ``None`` or ``""`` clears it.
        """
        item.setData(0, self.ROW_TOOLTIP_ROLE, text or None)
        TooltipPresenter.manage(self)

    def set_cell_tail(self, item, column: int, start: Optional[int]) -> None:
        """Draw *item*'s cell in *column* as a lead and a tail from *start*,
        so a long name reads by its end: the lead (a path's parents) in the
        cell's colour, faded, and cut from its left when the column is
        narrow, so the tail (the leaf, ``len(path) - len(leaf)`` on) always
        shows whole, in the cell's colour, semi-bold. Start 0: all of it is
        tail. ``None``: plain text again. Qt's own
        ``setTextElideMode(Qt.ElideLeft)`` cuts from the left too, but in one
        font and one colour, so the leaf would read no apart from its parents.

        Parameters:
            item: The row's ``QTreeWidgetItem``.
            column: The cell's column.
            start: Where the tail begins in the cell's text, or ``None``.
        """
        item.setData(column, self.TAIL_ROLE, None if start is None else int(start))

    def row_tooltip(self, item) -> Optional[str]:
        """*item*'s row tooltip (:meth:`set_row_tooltip`).

        Parameters:
            item: The row's ``QTreeWidgetItem``.

        Returns:
            The row's tooltip as set, or ``None`` when it has none.
        """
        return item.data(0, self.ROW_TOOLTIP_ROLE) or None

    # -- header action bar --------------------------------------------------

    @property
    def header_actions(self) -> _HeaderActionBar:
        """Right-aligned icon-button strip overlaid on the tree header.

        Created lazily on first access.  Use to add filter toggles,
        expand/collapse buttons, or other header-level controls::

            tree.header_actions.add(
                "filter", icon="filter", tooltip="Filter",
                toggle=True, callback=self._on_filter_toggled,
            )
        """
        if self._header_actions is None:
            self._header_actions = _HeaderActionBar(self)
            self._header_actions.hide()  # hidden until buttons are added
        return self._header_actions

    # -- child-row background (styleable via qproperty-childRowColor) ----

    def _get_child_row_color(self):
        return self._child_row_color

    def _set_child_row_color(self, color):
        self._child_row_color = (
            QtGui.QColor(color) if not isinstance(color, QtGui.QColor) else color
        )
        self.viewport().update()

    def setChildRowColor(self, color) -> None:
        """Set the child-row background (Qt-property setter).

        ``pyside6-uic`` compiles a ``.ui`` property into a ``set<Name>`` call,
        so a property Designer can write needs this public spelling — the
        underscore-prefixed setter alone would fail at form load.
        """
        self._set_child_row_color(color)

    childRowColor = QtCore.Property(
        QtGui.QColor, _get_child_row_color, setChildRowColor
    )

    # -- parent-row background (styleable via qproperty-parentRowColor) --

    def _get_parent_row_color(self):
        return self._parent_row_color

    def _set_parent_row_color(self, color):
        self._parent_row_color = (
            QtGui.QColor(color) if not isinstance(color, QtGui.QColor) else color
        )
        self.viewport().update()

    def setParentRowColor(self, color) -> None:
        """Set the parent-row background (Qt-property setter)."""
        self._set_parent_row_color(color)

    parentRowColor = QtCore.Property(
        QtGui.QColor, _get_parent_row_color, setParentRowColor
    )

    # -- alternate-row ground (the theme's qproperty-defaultAlternateRowColor) --

    def _get_alternate_row_color(self):
        own = self._alternate_row_color
        return own if own.isValid() else self._default_alternate_row_color

    def setAlternateRowColor(self, color) -> None:
        """Set the ground every other row is laid over while
        ``alternatingRowColors`` is on (Qt-property setter); an invalid
        ``QColor()`` returns to :attr:`defaultAlternateRowColor`. Qt's own
        alternate ground, the palette's, is transparent on this tree -- Qt
        paints it into a row's indentation, twice, over the row's tint."""
        self._alternate_row_color = QtGui.QColor(color)
        self.viewport().update()

    alternateRowColor = QtCore.Property(
        QtGui.QColor, _get_alternate_row_color, setAlternateRowColor
    )

    def _get_default_alternate_row_color(self):
        return self._default_alternate_row_color

    def setDefaultAlternateRowColor(self, color) -> None:
        """Set the alternate ground shown while none is set
        (:attr:`alternateRowColor`): the theme's ``ALTERNATE_BACKGROUND``,
        set again at every polish -- a property of its own, so a repolish
        never resets the colour a panel set (Qt-property setter)."""
        self._default_alternate_row_color = QtGui.QColor(color)
        self.viewport().update()

    defaultAlternateRowColor = QtCore.Property(
        QtGui.QColor, _get_default_alternate_row_color, setDefaultAlternateRowColor
    )

    # -- construction options, restated as Designer-editable properties ----

    def getSelectionStyle(self) -> str:
        """Visual style for selected rows: ``"border"`` or ``"tint"``."""
        return self._selection_style

    def setSelectionStyle(self, value: str) -> None:
        """Set the selected-row style; delegates to :attr:`selection_style`."""
        self.selection_style = value

    def getCtrlToggle(self) -> bool:
        """Whether Ctrl+click deselects an already-selected item."""
        return self._ctrl_toggle

    def setCtrlToggle(self, value: bool) -> None:
        """Enable or disable Ctrl+click deselection."""
        self._ctrl_toggle = bool(value)

    selectionStyle = QtCore.Property(
        str, fget=getSelectionStyle, fset=setSelectionStyle
    )
    ctrlToggle = QtCore.Property(bool, fget=getCtrlToggle, fset=setCtrlToggle)

    # -- column tinting ---------------------------------------------------

    def set_column_tint(self, column: int, color) -> None:
        """Apply a tint overlay to every cell in *column*.

        *color* can be a ``QColor``, hex string, or ``None`` to remove.
        """
        if color is None:
            self._column_tints.pop(column, None)
        else:
            c = QtGui.QColor(color) if not isinstance(color, QtGui.QColor) else color
            if c.isValid():
                self._column_tints[column] = c
            else:
                self._column_tints.pop(column, None)
        self.viewport().update()

    def clear_column_tints(self) -> None:
        """Remove all column tint overlays."""
        self._column_tints.clear()
        self.viewport().update()

    # -- row grounds (layers 1-5 of _RowTintDelegate) ------------------------

    def _ground(self, index, alternate: bool = False) -> QtGui.QColor:
        """The opaque ground of the cell at *index*: the view's base, the
        alternate ground where *alternate* and the row has no row tint of its
        own, the column's tint, the row's tint, then the cell's own
        ``BackgroundRole``."""
        over = _RowTintDelegate._alpha_over
        base = self.palette().color(QtGui.QPalette.Base)
        if not base.isValid() or base.alpha() == 0:
            base = QtGui.QColor(57, 57, 57)  # #393939 fallback
        bg = QtGui.QColor(base.red(), base.green(), base.blue())

        item = self.itemFromIndex(index)
        row = None
        if item is not None:
            row = (
                self._child_row_color
                if item.parent() is not None
                else self._parent_row_color
            )
            if not (row.isValid() and row.alpha() > 0):
                row = None
        if alternate and row is None:
            bg = over(bg, self._get_alternate_row_color())
        tint = self._column_tints.get(index.column())
        if tint is not None and tint.isValid() and tint.alpha() > 0:
            bg = over(bg, tint)
        if row is not None:
            bg = over(bg, row)
        cell = index.data(QtCore.Qt.BackgroundRole)
        if isinstance(cell, QtGui.QBrush) and cell.color().isValid():
            color = cell.color()
            if color.alpha() == 255:
                bg = QtGui.QColor(color)
            elif color.alpha() > 0:
                bg = over(bg, color)
        return bg

    def _shown_row(self, index) -> int:
        """*index*'s number among the rows shown, the top one 0: the number Qt
        alternates rows by. Counted up through ``indexAbove`` to a row
        numbered since Qt last laid the rows out (``_forget_rows_shown``), so
        each row is counted once per layout, never once per paint."""
        index = index.siblingAtColumn(0)
        known = self._shown_rows
        chain = []
        while index.isValid():
            key = (index.row(), index.internalId())
            if key in known:
                break
            chain.append(key)
            index = self.indexAbove(index)
        number = known[key] if index.isValid() else -1
        for key in reversed(chain):
            number += 1
            known[key] = number
        return number

    def _forget_rows_shown(self, *_) -> None:
        """Drop the rows' numbering (``_shown_row``) and each parent's last
        row shown (``_has_later_shown_sibling``): the rows shown changed."""
        self._shown_rows.clear()
        self._last_shown.clear()

    def updateGeometries(self) -> None:  # noqa: N802 -- Qt's name
        """Every layout of the rows ends here -- a hide (``item.setHidden``
        too, which reaches no override of the non-virtual ``setRowHidden``),
        an expand, an insert, a removal, a sort -- and no scroll or repaint
        does, so the rows shown are counted again from here
        (``_forget_rows_shown``; an animated expand's layout reaches here
        only at its end, hence ``expanded`` / ``collapsed`` too)."""
        self._forget_rows_shown()
        super().updateGeometries()

    def viewportEvent(self, event) -> bool:  # noqa: N802 -- Qt's name
        """Follow the pointer for the hot expander (``_set_hot_branch``)."""
        kind = event.type()
        if kind in (
            QtCore.QEvent.HoverEnter,
            QtCore.QEvent.HoverMove,
            QtCore.QEvent.MouseMove,
        ):
            self._set_hot_branch(self._expander_at(event.position().toPoint()))
        elif kind in (QtCore.QEvent.HoverLeave, QtCore.QEvent.Leave):
            self._set_hot_branch(QtCore.QModelIndex())
        return super().viewportEvent(event)

    def drawBranches(self, painter, rect, index) -> None:  # noqa: N802 -- Qt's name
        """The row's guides and expander, drawn by the tree
        (``HierarchyIconMixin``); Qt's own while hierarchy icons are off.
        Here, not on the mixin: ``QTreeWidget`` precedes it in the MRO."""
        if self._hierarchy_icons_enabled:
            self._paint_branches(painter, rect, index)
        else:
            super().drawBranches(painter, rect, index)

    def drawRow(self, painter, option, index) -> None:  # noqa: N802 -- Qt's name
        """Lay the row's ground under its indentation too, as its first
        column's cell has it (the delegate paints the cells): a row's tint,
        its alternate ground and that column's tint run the whole row. Qt then
        draws the branches, the selection and the hover on it."""
        column = self.treePosition()
        cell = index.siblingAtColumn(column)
        left = self.header().sectionViewportPosition(column)
        right = self.visualRect(cell).left()
        if right > left:
            alternate = self.alternatingRowColors() and self._shown_row(index) % 2 == 1
            rect = QtCore.QRect(
                left, option.rect.top(), right - left, option.rect.height()
            )
            painter.fillRect(rect, self._ground(cell, alternate))
        super().drawRow(painter, option, index)

    def _set_selection_mode(self, mode_str):
        """Set the selection mode from a string."""
        mode_map = {
            "none": QtWidgets.QAbstractItemView.NoSelection,
            "single": QtWidgets.QAbstractItemView.SingleSelection,
            "extended": QtWidgets.QAbstractItemView.ExtendedSelection,
            "multi": QtWidgets.QAbstractItemView.MultiSelection,
        }

        mode = mode_map.get(
            mode_str.lower(), QtWidgets.QAbstractItemView.ExtendedSelection
        )
        self.setSelectionMode(mode)

    def set_selection_mode(self, mode_str):
        """Change the selection mode after initialization."""
        self._set_selection_mode(mode_str)

    def _on_selection_changed(self):
        """Handle selection changes."""
        current = self.currentItem()
        if current:
            self.item_selected.emit(current)

    @property
    def ctrl_toggle(self):
        """Whether Ctrl+click toggles (deselects) an already-selected item."""
        return self._ctrl_toggle

    @ctrl_toggle.setter
    def ctrl_toggle(self, value):
        self._ctrl_toggle = bool(value)

    def mousePressEvent(self, event):
        """Track pre-click state; defer Ctrl+click toggle to release."""
        # Don't interfere with right-click - let it propagate to menu event filter
        if event.button() == QtCore.Qt.RightButton:
            self._last_clicked_item = None  # prevent stale state in release
            if self.has_menu:
                self.menu.trigger_from_widget(self, button=event.button())
            super().mousePressEvent(event)
            return

        item = self.itemAt(event.pos())
        modifiers = event.modifiers()

        # Store state for toggle handling in mouseReleaseEvent
        self._last_clicked_item = item
        self._was_selected = item.isSelected() if item else False
        self._ctrl_pressed = bool(modifiers & QtCore.Qt.ControlModifier)
        self._shift_pressed = bool(modifiers & QtCore.Qt.ShiftModifier)

        super().mousePressEvent(event)

        # Plain click on the only selected item -> deselect (non-Ctrl)
        if (
            item
            and self._was_selected
            and not self._ctrl_pressed
            and not self._shift_pressed
            and event.button() == QtCore.Qt.LeftButton
        ):
            if self.selectionMode() == QtWidgets.QAbstractItemView.ExtendedSelection:
                if len(self.selectedItems()) == 1:
                    QtCore.QTimer.singleShot(0, lambda: item.setSelected(False))
            elif self.selectionMode() == QtWidgets.QAbstractItemView.MultiSelection:
                item.setSelected(False)

    def mouseReleaseEvent(self, event):
        """Handle Ctrl+click toggle after Qt finalises selection."""
        super().mouseReleaseEvent(event)

        item = self._last_clicked_item
        self._last_clicked_item = None  # consume — one press per release

        if (
            event.button() != QtCore.Qt.LeftButton
            or item is None
            or not self._was_selected
            or self._shift_pressed
            or not self._ctrl_pressed
        ):
            return

        # Verify the release landed on the same item that was pressed
        release_item = self.itemAt(event.pos())
        if release_item is not item:
            return

        if self._ctrl_toggle:
            # Ensure Ctrl+click on a selected item deselects it
            if item.isSelected():
                item.setSelected(False)
        else:
            # Prevent Ctrl+click from deselecting — keep item selected
            if not item.isSelected():
                item.setSelected(True)

    def _handle_delayed_click(self):
        """Handle delayed click processing for deselection."""
        pass

    def create_item(
        self,
        text: Union[str, List[str]],
        data: Any = None,
        parent: QtWidgets.QTreeWidgetItem = None,
    ) -> QtWidgets.QTreeWidgetItem:
        """Create a new tree widget item."""
        if isinstance(text, str):
            text = [text]

        item = QtWidgets.QTreeWidgetItem(parent or self, text)

        if data is not None:
            item.setData(0, QtCore.Qt.UserRole, data)

        # Make item editable if needed
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)

        return item

    def item_data(self, item: QtWidgets.QTreeWidgetItem, column: int = 0):
        """Get data from an item."""
        if item is None:
            return None
        data = item.data(column, QtCore.Qt.UserRole)
        return data if data is not None else item.text(column)

    def set_item_data(
        self, item: QtWidgets.QTreeWidgetItem, data: Any, column: int = 0
    ):
        """Set data for an item."""
        if item:
            item.setData(column, QtCore.Qt.UserRole, data)

    def find_item_by_text(
        self, text: str, column: int = 0
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        """Find an item by its text in the specified column."""
        items = self.findItems(
            text, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, column
        )
        return items[0] if items else None

    def find_item_by_data(
        self, data: Any, column: int = 0
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        """Find an item by its user data."""
        iterator = QtWidgets.QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            if item.data(column, QtCore.Qt.UserRole) == data:
                return item
            iterator += 1
        return None

    @Signals.blockSignals
    def add(
        self,
        data: Union[Dict, List, str, Any],
        headers: Optional[List[str]] = None,
        clear: bool = True,
        parent: Optional[QtWidgets.QTreeWidgetItem] = None,
        **kwargs,
    ):
        """Add data to the tree widget with flexible input handling.

        Args:
            data: The data to add. Can be:
                - Dict: Keys become parent items, values become children
                - List of dicts: Each dict becomes a top-level item with key-value children
                - List of strings: Each string becomes a top-level item
                - List of tuples: (text, data) pairs
                - Nested structures: Recursively handled
            headers: Column headers for the tree
            clear: Whether to clear existing items
            parent: Parent item to add under (None for root)
            **kwargs: Additional attributes to set
        """
        self.setUpdatesEnabled(False)
        try:
            if clear and parent is None:
                self.clear()

            # Set headers if provided
            if headers:
                self.setHeaderLabels([str(h) for h in headers])
            elif not self.headerItem() or not self.headerItem().text(0):
                # Set default header if none exists
                self.setHeaderLabels(["Name"])

            # No inner block/unblock: the @Signals.blockSignals decorator
            # already blocks for the whole method. The old inner unblock ran
            # before set_attributes()/apply_formatting(), letting itemChanged
            # escape during the tail of add().
            self._add_recursive(data, parent)

        finally:
            self.setUpdatesEnabled(True)

        self.set_attributes(**kwargs)
        self.apply_formatting()

    def _add_recursive(
        self, data: Any, parent: Optional[QtWidgets.QTreeWidgetItem] = None
    ):
        """Recursively add data to the tree."""
        if isinstance(data, dict):
            for key, value in data.items():
                item = self.create_item(str(key), key, parent)
                if isinstance(value, (dict, list)):
                    self._add_recursive(value, item)
                else:
                    self.create_item(str(value), value, item)

        elif isinstance(data, (list, tuple)):
            for item_data in data:
                if isinstance(item_data, dict):
                    # Dict becomes parent with key-value children
                    for key, value in item_data.items():
                        parent_item = self.create_item(str(key), key, parent)
                        if isinstance(value, (dict, list)):
                            self._add_recursive(value, parent_item)
                        else:
                            self.create_item(str(value), value, parent_item)

                elif isinstance(item_data, (tuple, list)) and len(item_data) >= 2:
                    # Tuple/list: (text, data, [children])
                    text, user_data = item_data[0], item_data[1]
                    item = self.create_item(str(text), user_data, parent)

                    # Handle children if present
                    if len(item_data) > 2 and item_data[2]:
                        self._add_recursive(item_data[2], item)

                elif isinstance(item_data, (dict, list)):
                    # Nested structure
                    self._add_recursive(item_data, parent)
                else:
                    # Simple value
                    self.create_item(str(item_data), item_data, parent)
        else:
            # Single value
            self.create_item(str(data), data, parent)

    def selected_item(self) -> Optional[QtWidgets.QTreeWidgetItem]:
        """Get the currently selected item."""
        return self.currentItem()

    def selected_items(self) -> List[QtWidgets.QTreeWidgetItem]:
        """Get all selected items."""
        return self.selectedItems()

    def selected_data(self, column: int = 0) -> Any:
        """Get data from the currently selected item."""
        item = self.selected_item()
        return self.item_data(item, column) if item else None

    def selected_data_list(self, column: int = 0) -> List[Any]:
        """Get data from all selected items."""
        items = self.selected_items()
        return [self.item_data(item, column) for item in items if item]

    def selected_text(self, column: int = 0) -> Optional[str]:
        """Get text from the currently selected item."""
        item = self.selected_item()
        return item.text(column) if item else None

    def selected_text_list(self, column: int = 0) -> List[str]:
        """Get text from all selected items."""
        items = self.selected_items()
        return [item.text(column) for item in items if item]

    def select_items_by_data(self, data_list: List[Any], column: int = 0):
        """Select multiple items by their data values."""
        self.clearSelection()
        for data in data_list:
            item = self.find_item_by_data(data, column)
            if item:
                item.setSelected(True)

    def select_items_by_text(self, text_list: List[str], column: int = 0):
        """Select multiple items by their text values."""
        self.clearSelection()
        for text in text_list:
            item = self.find_item_by_text(text, column)
            if item:
                item.setSelected(True)

    def set_stretch_column(self, col: int):
        """Set a column to automatically stretch to fill available space."""
        self._stretch_column = col
        self.stretch_column_to_fill(col)

    # -- Column configuration (visibility, reorder, persistence) ----------

    def enable_column_config(
        self,
        settings=None,
        settings_key=None,
        locked=(),
        reorderable=False,
        hidden_by_default=(),
        default_order=(),
    ):
        """Enable header right-click menu for column visibility and drag reorder.

        The shared :class:`~uitk.widgets.column_config.ColumnConfig` --
        ``TableWidget.enable_column_config`` is the same option.

        Parameters:
            settings: A SettingsManager instance (or any object with
                ``branch(name)`` / ``value(key, default)`` /
                ``setValue(key, value)`` / ``sync()``).  If *None*, a
                SettingsManager (``org="uitk"``, ``app="TreeWidget"``) is
                created automatically.
            settings_key: Namespace prefix for stored keys.  Defaults to
                the widget's ``objectName()`` or ``"TreeWidget"``.
            locked: Logical columns that can't be hidden.
            reorderable: The menu's rows can also be dragged into another
                column order (see ``ColumnConfig``).
            hidden_by_default: Logical columns hidden until the user's own
                layout is saved -- optional columns they turn on from the menu.
            default_order: The logical columns left to right until the user's
                own order is saved (see ``ColumnConfig``).
        """
        ColumnConfig.attach(
            self,
            settings=settings,
            settings_key=settings_key or self.objectName() or "TreeWidget",
            locked=locked,
            app="TreeWidget",
            reorderable=reorderable,
            hidden_by_default=hidden_by_default,
            default_order=default_order,
        )

    @property
    def _column_settings(self):
        """The layout's settings branch; ``None`` before :meth:`enable_column_config`."""
        config = ColumnConfig.of(self)
        return config.settings if config is not None else None

    def _show_column_menu(self, pos):
        """Open the header's column menu at header position *pos*."""
        config = ColumnConfig.of(self)
        if config is not None:
            config.show_menu(pos)

    def _save_column_state(self):
        """Write current visibility and visual order to settings."""
        config = ColumnConfig.of(self)
        if config is not None:
            config.save()

    def restore_column_state(self):
        """Apply persisted visibility and order.  Call after headers are set."""
        config = ColumnConfig.of(self)
        if config is not None:
            config.restore()

    # -- Row colour tags ---------------------------------------------------

    def enable_row_tags(
        self, settings=None, settings_key=None, defaults=None, inherit=True
    ):
        """Show per-row colour tags as a strip down the left edge.

        The shared :class:`~uitk.widgets.row_tags.RowTags` --
        ``TableWidget.enable_row_tags`` is the same option: tag rows with
        ``set_tag``, offer the quick-pick swatches with ``add_to_menu``, and
        hear the user's picks on ``assigned``.

        Parameters:
            settings: A SettingsManager the palette is saved in.  If *None*, a
                SettingsManager (``org="uitk"``, ``app="TreeWidget"``) is
                created automatically.
            settings_key: The palette's branch.  Defaults to the widget's
                ``objectName()`` or ``"TreeWidget"``.
            defaults: ``{slot: colour}`` in order; ``Palette.tags()`` if *None*.
            inherit: A row with no tag shows its nearest tagged ancestor's
                colour, fainter.

        Returns:
            The view's :class:`~uitk.widgets.row_tags.RowTags`.
        """
        return RowTags.attach(
            self,
            settings=settings,
            settings_key=settings_key or self.objectName() or "TreeWidget",
            app="TreeWidget",
            defaults=defaults,
            inherit=inherit,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._header_actions is not None:
            self._header_actions._reposition()
        if self._stretch_column is not None:
            self.stretch_column_to_fill(self._stretch_column)

    def showEvent(self, event):
        super().showEvent(event)
        if self._header_actions is not None:
            self._header_actions._reposition()

    def stretch_column_to_fill(self, stretch_col: int):
        """Resize one column to fill remaining horizontal space."""
        header = self.header()
        if stretch_col < 0 or stretch_col >= self.columnCount():
            return

        header.setStretchLastSection(False)
        for col in range(self.columnCount()):
            header.setSectionResizeMode(col, QtWidgets.QHeaderView.Interactive)

        total_width = self.viewport().width()
        if total_width <= 0:
            return

        other_cols_width = sum(
            self.columnWidth(c) for c in range(self.columnCount()) if c != stretch_col
        )
        self.setColumnWidth(stretch_col, max(50, total_width - other_cols_width))

    def expand_all_items(self):
        """Expand all items in the tree."""
        self.expandAll()

    def collapse_all_items(self):
        """Collapse all items in the tree."""
        self.collapseAll()

    def get_all_items(self) -> List[QtWidgets.QTreeWidgetItem]:
        """Get all items in the tree."""
        items = []
        iterator = QtWidgets.QTreeWidgetItemIterator(self)
        while iterator.value():
            items.append(iterator.value())
            iterator += 1
        return items

    def remove_item(self, item: QtWidgets.QTreeWidgetItem):
        """Remove an item from the tree."""
        if item:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                index = self.indexOfTopLevelItem(item)
                if index >= 0:
                    self.takeTopLevelItem(index)

    def set_item_icon(
        self,
        item: QtWidgets.QTreeWidgetItem,
        icon_name: str,
        color: str = None,
    ):
        """Set a custom icon for a specific item."""
        if item and icon_name:
            icon = IconManager.get(icon_name, size=(16, 16), color=color)
            item.setIcon(0, icon)
            # Store icon info for theme updates
            item.setData(
                0,
                QtCore.Qt.UserRole + 100,
                {"icon_name": icon_name, "column": 0, "color": color},
            )

    def set_item_type_icon(
        self,
        item: QtWidgets.QTreeWidgetItem,
        icon_name: str,
        column: int = 0,
        color: str = None,
    ):
        """Set a custom type icon for a specific item (separate from hierarchy indicators).

        This sets an icon in the item itself (next to the text) to indicate object type,
        while leaving the hierarchy indicators (tree lines, +/- boxes) untouched.

        Args:
            item: The tree widget item
            icon_name: Name of the icon (from IconManager)
            column: Column to set the icon in (default 0)
            color: Optional hex color for the icon (e.g. ``"#6EA8DC"``)
        """
        if item and icon_name:
            icon = IconManager.get(icon_name, size=(16, 16), color=color)
            item.setIcon(column, icon)
            # Store icon info for theme updates
            item.setData(
                column,
                QtCore.Qt.UserRole + 100,
                {"icon_name": icon_name, "column": column, "color": color},
            )

    def refresh_item_icons(self, color: str = None):
        """Refresh all item icons with the current theme color.

        Called when theme changes to update tree item icons.

        Args:
            color: Optional color to use. If None, uses IconManager default.
        """

        def refresh_item(item):
            for col in range(item.columnCount()):
                icon_data = item.data(col, QtCore.Qt.UserRole + 100)
                if icon_data and isinstance(icon_data, dict):
                    icon_name = icon_data.get("icon_name")
                    if icon_name:
                        icon_color = icon_data.get("color") or color
                        icon = IconManager.get(
                            icon_name, size=(16, 16), color=icon_color
                        )
                        item.setIcon(col, icon)
            # Recurse to children
            for i in range(item.childCount()):
                refresh_item(item.child(i))

        # Refresh all top-level items and their children
        for i in range(self.topLevelItemCount()):
            refresh_item(self.topLevelItem(i))


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    tree = TreeWidget()

    # Test with different data structures
    test_data = {
        "Root 1": {"Child 1": "Value 1", "Child 2": ["Item A", "Item B", "Item C"]},
        "Root 2": [
            ("Node A", "data_a"),
            ("Node B", "data_b", {"Sub1": "SubValue1", "Sub2": "SubValue2"}),
        ],
    }

    tree.add(test_data, headers=["Items", "Data"])
    tree.expand_all_items()

    # Set up some formatting
    tree.set_column_formatter(0, tree.action_color_formatter)

    tree.show()
    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Promoting a widget in designer to use a custom class:
>   In Qt Designer, select all the widgets you want to replace,
        then right-click them and select 'Promote to...'.

>   In the dialog:
        Base Class:     Class from which you inherit. ie. QWidget
        Promoted Class: Name of the class. ie. "MyWidget"
        Header File:    Path of the file (changing the extension .py to .h)  ie. myfolder.mymodule.mywidget.h

>   Then click "Add", "Promote",
        and you will see the class change from "QWidget" to "MyWidget" in the Object Inspector pane.
"""
