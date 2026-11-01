# !/usr/bin/python
# coding=utf-8
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from qtpy import QtWidgets, QtGui, QtCore
from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter
from uitk.switchboard import Signals
from uitk.widgets.comboBox import ComboBox
from uitk.widgets.widget_combo_box_parts._actions import (
    _ActionsNamespace,
    _ActionsSection,
)
from uitk.widgets.widget_combo_box_parts._arrow_affordance import _ArrowAffordance
from uitk.widgets.widget_combo_box_parts._widget_defaults import _WidgetDefaults


class _RowHandle:
    """What a :class:`WidgetComboBox` row registers on its FieldVisibility.

    ``FieldVisibility`` wants one method, ``setVisible``; a row is not a
    widget that can hide itself (the model row and the caption container go
    together), so this stands in and routes to the combo.
    """

    __slots__ = ("_combo", "_widget")

    def __init__(self, combo, widget):
        self._combo = combo
        self._widget = widget

    def setVisible(self, visible: bool) -> None:  # noqa: N802 -- Qt's spelling
        self._combo.set_row_visible(self._widget, visible)


class WidgetComboBox(ComboBox):
    """ComboBox extended with widget embedding support.

    Inherits all features from ComboBox and adds:
    - Embedded widgets via QListView.setIndexWidget
    - QActions as menu items
    - Mixed content (text, widgets, and actions in one dropdown)

    Uses QStandardItemModel + QListView instead of the default combo model
    to support setIndexWidget() for embedded widgets.
    """

    # A facade over the rows it embeds: the persistent actions section, the
    # dropdown affordance and the "Restore Defaults" snapshots are
    # collaborators in ``widget_combo_box_parts`` (``_ActionsSection``, ``_ArrowAffordance``,
    # ``_WidgetDefaults``), each owning its state and holding the combo; every
    # public member stays here.

    # Qt Designer widget-box entry.
    designer_spec = {"icon": "list", "object_name": "cmb"}

    def __init__(
        self, parent: Optional[QtWidgets.QWidget] = None, editable=False, **kwargs
    ):
        # Call ComboBox.__init__ first to setup base functionality
        super().__init__(parent, editable=editable, **kwargs)

        # Widget-specific: Use QListView + QStandardItemModel for setIndexWidget support
        list_view = QtWidgets.QListView(self)
        list_view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        list_view.setSpacing(0)  # Compact layout with no spacing between items
        # Zero item padding so embedded widgets fill the row edge-to-edge,
        # matching standard combobox visual density. The parent QSS rule
        # `QComboBox QAbstractItemView::item { padding: 1px; }` would otherwise
        # add a 1px frame around every embedded widget. Hover/selection bg
        # is suppressed per-row in ``_CurrentItemIndicatorDelegate`` only
        # for rows that contain an embedded widget — text-only rows keep
        # the standard BUTTON_HOVER blue.
        list_view.setStyleSheet(
            "QComboBox QAbstractItemView::item,"
            " QAbstractItemView::item {"
            "     padding: 0;"
            "     border: none;"
            " }"
        )
        self.setView(list_view)

        # Track the tallest embedded widget so all rows can be sized
        # uniformly — a WidgetComboBox with mixed widgets (sliders, checkboxes,
        # spinboxes) otherwise renders ragged rows. The actions section
        # (separator + button container) is excluded from this tracking
        # because its container is intentionally tall.
        self._uniform_item_height = 0
        # Deliberate vertical gap (px) between embedded-widget rows, added on
        # top of the tight per-widget row height. Exposed via ``item_spacing``.
        self._item_spacing = 1

        self._model = QtGui.QStandardItemModel(self)
        self.setModel(self._model)

        # Set maximum visible items to 25
        self.setMaxVisibleItems(25)

        # Track embedded widgets
        self._widget_items: dict[int, QtWidgets.QWidget] = {}
        self._row_containers: dict[int, QtWidgets.QWidget] = {}
        # Deferred widget embedding: PySide6 can crash (ACCESS_VIOLATION) in
        # setIndexWidget when the view's viewport hasn't been fully realized
        # (e.g. during headless testing or before the first show).  Pending
        # (row, container) pairs are flushed in showPopup().
        self._pending_index_widgets: list[tuple[int, QtWidgets.QWidget]] = []
        # The rows' FieldVisibility, built on first use and rebuilt when the
        # row set changes (see ``fields``).
        self._fields = None
        self._fields_signature: tuple = ()

        # Persistent actions section (separator + action buttons at bottom of dropdown)
        self._actions_ns = _ActionsNamespace(self)
        self._actions_section = _ActionsSection(self)

        self.currentIndexChanged.connect(self._on_index_changed)

        # Dropdown affordance drawn after the displayed text (the theme hides
        # the native QComboBox::down-arrow).  Off by default — matching the
        # base ``ComboBox``, which draws none — so a combo only shows one when
        # a caller opts in via ``arrow_direction`` (chevron) or ``arrow_icon``
        # (custom icon).  ``arrow_alpha`` sets the affordance's opacity.  Size
        # auto-scales with the font.
        self._arrow = _ArrowAffordance(self)

        # Embedded-widget initial values for the optional "Restore Defaults"
        # action.
        self._defaults = _WidgetDefaults(self)

    # ------------------------------------------------------------------
    # Deferred index-widget helpers
    # ------------------------------------------------------------------
    def _set_index_widget(self, row: int, container: QtWidgets.QWidget) -> None:
        """Embed *container* on *row*, deferring if the viewport isn't ready.

        PySide6 crashes with ACCESS_VIOLATION when ``setIndexWidget`` is called
        before the view's C++ viewport backing store has been realized (e.g.
        during headless test execution or before the widget hierarchy has been
        shown).  This helper queues the call instead; ``showPopup`` flushes
        the queue before the dropdown opens.
        """
        view = self.view()
        # Only set directly if the view is actually visible (and thus realized).
        # Checking width() > 0 is insufficient as layout can assign size before realization.
        if view.isVisible():
            index = self._model.index(row, 0)
            view.setIndexWidget(index, container)
        else:
            self._pending_index_widgets.append((row, container))

    def _flush_pending_index_widgets(self) -> None:
        """Install any deferred index widgets now that the viewport is ready."""
        if not self._pending_index_widgets:
            return
        view = self.view()
        pending = list(self._pending_index_widgets)
        self._pending_index_widgets.clear()
        for row, container in pending:
            try:
                index = self._model.index(row, 0)
                view.setIndexWidget(index, container)
            except RuntimeError:
                pass  # C++ object already deleted

    # ------------------------------------------------------------------
    # Override properties to work with QStandardItemModel
    # ------------------------------------------------------------------
    @Signals.blockSignals
    def setItemText(self, index, text):
        """Override to work with QStandardItemModel."""
        if 0 <= index < self._model.rowCount():
            item = self._model.item(index)
            if item:
                item.setText(text)

    def _setText(self, text, index=0):
        """Override to set text via the model, bypassing the
        ``ComboBox.setItemText -> setRichText -> _setText`` recursion.

        The base ``RichText._setText`` resolves ``self.__class__.__base__``
        to ``ComboBox``, whose ``setItemText`` calls ``setRichText`` which
        calls ``_setText`` again — infinite loop.  Going through the model
        item directly breaks the cycle.
        """
        if 0 <= index < self._model.rowCount():
            item = self._model.item(index)
            if item:
                item.setText(str(text) if text is not None else "")

    # ------------------------------------------------------------------
    # Widget-specific methods
    # ------------------------------------------------------------------
    def addWidgetItem(
        self,
        widget: QtWidgets.QWidget,
        label: str = "",
        *,
        data: Any = None,
        select: bool = False,
    ) -> int:
        """Insert *widget* as a selectable row.

        Parameters:
            widget: QWidget to embed inside the popup view.
            label: Optional label displayed in the combo's line edit.
            data: Optional user role payload retrievable via itemData.
            select: If True, make the new row current immediately.
        Returns:
            Row index of the inserted widget.
        """

        if widget.parent() is not None and widget.parent() is not self.view():
            widget.setParent(None)

        # Keep the persistent actions section pinned to the tail: strip it,
        # append the new selectable row, then re-append the actions last. Without
        # this, an addWidgetItem after actions.add() buries the widget below the
        # action rows — it never gets height-synced and the next actions.add()
        # (via _strip_actions_section) deletes it and orphans the separator.
        had_actions = self._actions_section.row_count > 0
        if had_actions:
            self._strip_actions_section()

        row_item = QtGui.QStandardItem(label)
        payload = data if data is not None else widget
        row_item.setData(payload, QtCore.Qt.UserRole)
        self._apply_uniform_height(row_item, widget)

        self._model.appendRow(row_item)
        row = self._model.rowCount() - 1

        container = self._wrap_widget(widget)
        self._set_index_widget(row, container)

        self._widget_items[row] = widget
        self._row_containers[row] = container

        if had_actions:
            self._rebuild_actions_section()

        if select:
            self.setCurrentIndex(row)
        return row

    def addWidgetAction(
        self,
        action: QtWidgets.QAction,
        label: str = "",
        *,
        select: bool = False,
    ) -> int:
        """Insert a QWidgetAction (or plain QAction) as a widget row."""

        return self.addWidgetItem(
            self._action_to_widget(action),
            label or action.text(),
            data=action,
            select=select,
        )

    def widgetAt(self, row: int) -> Optional[QtWidgets.QWidget]:
        """Return the widget stored at *row* if present."""

        return self._widget_items.get(row)

    def takeWidgetAt(self, row: int) -> Optional[QtWidgets.QWidget]:
        """Remove and return the widget stored at *row*."""

        if row not in self._widget_items:
            return None

        index = self._model.index(row, 0)
        self.view().setIndexWidget(index, None)

        container = self._row_containers.pop(row, None)
        widget = self._widget_items.pop(row)
        # Drop the widget's captured default so it can't leak across takes and
        # so a later widget that reuses this (freed) id can't inherit a stale,
        # wrong-type snapshot on Restore Defaults.
        self._defaults.snapshots.pop(id(widget), None)

        if container is not None:
            container.deleteLater()

        self._model.removeRow(row)

        # Renumber tracked AND still-pending widgets: drop the removed row and
        # shift every higher row down by one. Rebuilding from view.indexWidget()
        # would silently lose rows whose index widget was deferred and never
        # installed (a never-shown popup), dropping them from tracking. Qt
        # already shifts realized index widgets via QPersistentModelIndex, so
        # this stays consistent with the view.
        def _renumber(mapping):
            return {
                (r - 1 if r > row else r): v for r, v in mapping.items() if r != row
            }

        self._widget_items = _renumber(self._widget_items)
        self._row_containers = _renumber(self._row_containers)
        self._pending_index_widgets = [
            (r - 1 if r > row else r, c)
            for r, c in self._pending_index_widgets
            if r != row
        ]
        return widget

    def currentWidget(self) -> Optional[QtWidgets.QWidget]:
        """Convenience accessor for the selected widget."""

        return self._widget_items.get(self.currentIndex())

    # ------------------------------------------------------------------
    # Row visibility
    # ------------------------------------------------------------------
    def row_of(self, widget: QtWidgets.QWidget) -> Optional[int]:
        """The model row embedding *widget*, or ``None``."""
        for row, embedded in self._widget_items.items():
            if embedded is widget:
                return row
        return None

    def row_container(self, widget: QtWidgets.QWidget) -> Optional[QtWidgets.QWidget]:
        """The marginless container (caption + widget) of *widget*'s row."""
        row = self.row_of(widget)
        return None if row is None else self._row_containers.get(row)

    def set_row_visible(self, widget: QtWidgets.QWidget, visible: bool) -> None:
        """Show or hide the row embedding *widget*.

        A row a setting has made irrelevant is HIDDEN, not greyed: the model
        row leaves the view (so the popup no longer sizes for it) and the
        container goes with it (so a hidden row's caption cannot widen the
        caption column). Nothing about the widget's VALUE changes -- a hidden
        row still saves, restores and reads like any other.
        """
        row = self.row_of(widget)
        if row is None:
            return
        self.view().setRowHidden(row, not visible)
        container = self._row_containers.get(row)
        if container is not None:
            container.setVisible(visible)

    def is_row_visible(self, widget: QtWidgets.QWidget) -> bool:
        """False when *widget*'s row is hidden (or *widget* is not a row)."""
        row = self.row_of(widget)
        return row is not None and not self.view().isRowHidden(row)

    def field_key(self, widget: QtWidgets.QWidget):
        """The key *widget*'s row registers under on :attr:`fields`: its
        objectName, or the widget itself when it has none."""
        return widget.objectName() or widget

    @property
    def fields(self):
        """The rows as a :class:`~uitk.managers.field_visibility.FieldVisibility`.

        Every embedded widget registers under :meth:`field_key`, in the section
        the titled ``Separator`` row above it names; every titled separator is
        that section's divider, so a section whose every row is hidden takes
        its caption down with it. The actions section is not a field: its
        button row would sit in the last section and hold that caption up.
        Built on first use and rebuilt when the row set changes, which is what
        lets a dependency rule wired before the rows existed find them once
        they do; a rebuilt registry starts from what the view shows, so it
        keeps the rows other rules had hidden.
        """
        last = self._model.rowCount() - self._actions_section.row_count
        rows = [(r, w) for r, w in sorted(self._widget_items.items()) if r < last]
        signature = tuple(id(w) for _r, w in rows)
        if self._fields is not None and signature == self._fields_signature:
            return self._fields
        from uitk.managers.field_visibility import FieldVisibility

        # The rows live in a popup that re-measures itself on every show, so
        # there is no host height to follow: a no-op fit.
        fields = FieldVisibility(fit=lambda: None)
        section = None
        shown = []
        for row, widget in rows:
            if self._is_separator_row(row):
                title = getattr(widget, "title", None)
                title = title() if callable(title) else title
                if title:
                    section = str(title)
                    fields.divider(section, _RowHandle(self, widget))
                continue
            key = self.field_key(widget)
            fields.register(key, _RowHandle(self, widget), section)
            if not self.view().isRowHidden(row):
                shown.append(key)
        fields.show(shown)
        self._fields, self._fields_signature = fields, signature
        return fields

    @classmethod
    def host_of(cls, widget) -> Optional["WidgetComboBox"]:
        """The combo whose row embeds *widget*, or ``None``.

        Walks the parent chain (container, view, popup frame, combo), so a
        rule that resolved the embedded widget by name can reach the registry
        its row lives in.
        """
        parent = getattr(widget, "parent", None)
        node = parent() if callable(parent) else None
        while node is not None:
            if isinstance(node, cls):
                return node if node.row_of(widget) is not None else None
            node = node.parent()
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    # Object name of the opt-in row label, and the gap between it and the
    # widget it describes. The name is looked up with FindDirectChildrenOnly
    # so an embedded widget's own QLabels can never be mistaken for it.
    _ROW_LABEL_OBJECT_NAME = "widgetComboBoxRowLabel"
    _ROW_LABEL_SPACING = 6

    def _wrap_widget(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Embed the widget inside a marginless container for layout control.

        A widget carrying a truthy ``rowLabel`` dynamic property (set
        declaratively via ``set_row_label``) also gets a leading QLabel inside
        this same container. That is the point of doing it here: the container
        already exists for every row, and all of this widget's bookkeeping keys
        off ``_widget_items[row]`` / the ``_embedded_widget`` property rather
        than "the container's only child", so an extra sibling is invisible to
        it. Row height is likewise derived from the *widget's* sizeHint in
        :meth:`_apply_uniform_height`, so a label cannot grow the row.

        Opt-in by design: rows whose widget carries its own text (checkboxes,
        push buttons) would only get a redundant second caption, so an absent
        property leaves the container byte-identical to before.
        """
        container = QtWidgets.QWidget(self.view())
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        row_label = widget.property("rowLabel")
        if row_label:
            label = QtWidgets.QLabel(str(row_label), container)
            # The object name is the single hook: it selects the QSS rule and
            # is what _row_labels() matches on. No `class` property -- nothing
            # reads one here, and StyleSheet stamps that key itself.
            label.setObjectName(self._ROW_LABEL_OBJECT_NAME)
            # Mirror the widget's tooltip so hovering the caption explains the
            # field too -- the label is the part the user reads first.
            tip = widget.toolTip()
            if tip:
                label.setToolTip(tip)
                TooltipPresenter.manage(label)
            layout.addWidget(label, alignment=QtCore.Qt.AlignVCenter)
            layout.addSpacing(self._ROW_LABEL_SPACING)
        # Vertical-center the widget so rows sized to the uniform max-height
        # don't vertically stretch shorter widgets (checkboxes growing tall).
        layout.addWidget(widget, alignment=QtCore.Qt.AlignVCenter)
        container.setProperty("_embedded_widget", widget)
        return container

    def _row_labels(self) -> list:
        """Every opt-in row label currently installed, in row order."""
        labels = []
        for container in self._row_containers.values():
            if container is None or container.isHidden():
                continue
            try:
                label = container.findChild(
                    QtWidgets.QLabel,
                    self._ROW_LABEL_OBJECT_NAME,
                    QtCore.Qt.FindDirectChildrenOnly,
                )
            except RuntimeError:  # container already deleted
                continue
            if label is not None:
                labels.append(label)
        return labels

    def _align_row_labels(self) -> None:
        """Give every row label a common width so the fields line up.

        Left ragged, captions of different lengths start each field at a
        different x and the column reads as broken. ``sizeHint`` stays
        content-based under ``setFixedWidth``, so re-running this is idempotent
        and a row removed later still re-narrows the rest.
        """
        labels = self._row_labels()
        if not labels:
            return
        widest = max(label.sizeHint().width() for label in labels)
        for label in labels:
            if label.width() != widest:
                label.setFixedWidth(widest)

    def _row_target_height(self) -> int:
        """Row sizeHint height for tracked rows: the tight uniform widget
        height plus the deliberate ``item_spacing`` gap. Single source of the
        row-height policy so ``_apply_uniform_height`` / ``_resync_uniform_heights``
        can't drift apart."""
        return self._uniform_item_height + self._item_spacing

    def _apply_uniform_height(self, row_item, widget, track=True):
        """Set ``row_item``'s sizeHint using the uniform height policy.

        When ``track`` is True (default) the widget's natural height feeds
        the running max and may grow other rows. When False (used for the
        actions section's tall multi-button container) the row gets its
        own natural sizeHint and is excluded from tracking.
        """
        natural = widget.sizeHint()
        if not natural.isValid():
            return
        if track:
            if natural.height() > self._uniform_item_height:
                self._uniform_item_height = natural.height()
                self._resync_uniform_heights()
            row_item.setSizeHint(
                QtCore.QSize(natural.width(), self._row_target_height())
            )
        else:
            row_item.setSizeHint(natural)

    def _resync_uniform_heights(self):
        """Re-apply the current uniform height (+ ``item_spacing``) to every
        tracked row."""
        if self._uniform_item_height <= 0:
            return
        target = self._row_target_height()
        # Action rows live at the tail; iterate everything except those.
        # `_action_row_count` is the count of separator + container rows.
        total = self._model.rowCount()
        last_tracked = total - self._actions_section.row_count
        for r in range(last_tracked):
            item = self._model.item(r)
            if item is None or self._is_separator_row(r):
                continue
            sh = item.sizeHint()
            if sh.height() != target:
                item.setSizeHint(QtCore.QSize(sh.width(), target))

    def _recompute_uniform_heights(self):
        """Re-derive ``_uniform_item_height`` from embedded widgets' *current*
        sizeHints, then resync.

        A widget's sizeHint can change after it was first added — most
        notably once the theme is applied, which shifts font metrics (a
        checkbox measured 17px pre-theme, 14px after). The height captured at
        add-time then leaves rows taller than their widget, and the
        vertically-centered widget renders that surplus as dead space between
        rows. Recomputing from live sizes (done at popup time) keeps rows
        tight so ``item_spacing`` is the only deliberate gap.
        """
        total = self._model.rowCount()
        last_tracked = total - self._actions_section.row_count
        tallest = 0
        for r in range(last_tracked):
            widget = self._widget_items.get(r)
            if (
                widget is not None
                and not self._is_separator_row(r)
                and not self.view().isRowHidden(r)
            ):
                tallest = max(tallest, widget.sizeHint().height())
        if tallest > 0:
            self._uniform_item_height = tallest
            self._resync_uniform_heights()

    def _is_separator_row(self, row: int) -> bool:
        """True when *row* embeds a ``Separator``.

        Separator rows are excluded from the uniform-height policy in both
        directions: a titled separator sizes its row to its own fixed height
        (so the group caption keeps the breathing room the widget draws for
        it), and it never feeds the running max that sizes the value rows.
        """
        widget = self._widget_items.get(row)
        return widget is not None and widget.__class__.__name__ == "Separator"

    @property
    def item_spacing(self) -> int:
        """Vertical gap, in pixels, between embedded-widget rows in the
        dropdown (default ``1``). Rows are otherwise sized tightly to their
        widget, so this is the only deliberate inter-row spacing. Setting it
        re-applies row heights immediately."""
        return self._item_spacing

    @item_spacing.setter
    def item_spacing(self, value: int) -> None:
        value = max(0, int(value))
        if value != self._item_spacing:
            self._item_spacing = value
            self._resync_uniform_heights()

    def _shift_tracked_rows_down(self) -> None:
        """Bump every tracked (and still-pending) row index up by one.

        Called immediately after an ``insertRow(0)`` so an ascending insert
        doesn't overwrite ``_widget_items[0]`` / ``_row_containers[0]`` and drop
        the previously-tracked row. Qt shifts realized index widgets via
        QPersistentModelIndex; this keeps the Python-side maps in step so every
        inserted widget stays reachable (and its container is still freed on
        clear()).
        """
        self._widget_items = {r + 1: w for r, w in self._widget_items.items()}
        self._row_containers = {r + 1: c for r, c in self._row_containers.items()}
        self._pending_index_widgets = [
            (r + 1, c) for r, c in self._pending_index_widgets
        ]

    def _on_index_changed(self, row: int) -> None:
        widget = self._widget_items.get(row)
        if widget and widget.focusPolicy() != QtCore.Qt.NoFocus:
            widget.setFocus(QtCore.Qt.OtherFocusReason)

    # ------------------------------------------------------------------
    # Persistent actions section
    # ------------------------------------------------------------------
    @property
    def actions(self) -> _ActionsNamespace:
        """Namespace for managing persistent action buttons at the bottom of
        the dropdown.

        Usage::

            combo.actions.add("✏ Rename…", on_rename)
            combo.actions.add("＋ Add…", on_add)
            combo.actions.clear()
        """
        return self._actions_ns

    @property
    def action_columns(self) -> int:
        """Number of columns the persistent action buttons are arranged into.

        Buttons fill row-major (left-to-right, then top-to-bottom). Default
        ``1`` is a single vertical stack. Set to ``2`` to pack four actions
        into a 2x2 grid, etc. Setting it re-lays out the actions section
        immediately.
        """
        return self._actions_section.columns

    @action_columns.setter
    def action_columns(self, value: int) -> None:
        self._actions_section.set_columns(value)

    @property
    def action_icon_only(self) -> bool:
        """When True, action buttons show only their icon (compact, no text).

        Renders the actions section as a toolbar-style row of square icon
        buttons; the action text is still used as each button's tooltip. Default
        ``False`` (icon + centered text). Setting it re-lays out the section.
        """
        return self._actions_section.icon_only

    @action_icon_only.setter
    def action_icon_only(self, value: bool) -> None:
        self._actions_section.set_icon_only(value)

    @property
    def show_action_separator(self) -> bool:
        """Whether a separator is drawn above the actions section (default True)."""
        return self._actions_section.show_separator

    @show_action_separator.setter
    def show_action_separator(self, value: bool) -> None:
        self._actions_section.set_show_separator(value)

    # The section's rows and bindings, as the namespace and hosts reach them.
    def _strip_actions_section(self) -> None:
        self._actions_section.strip()

    def _rebuild_actions_section(self) -> None:
        self._actions_section.rebuild()

    @property
    def _action_row_count(self) -> int:
        return self._actions_section.row_count

    @property
    def _action_button_conns(self) -> list:
        return self._actions_section.button_conns

    def showPopup(self) -> None:
        """Override to expand the popup to the widest embedded widget."""
        self._flush_pending_index_widgets()
        # Re-derive row heights from the widgets' current sizeHints before the
        # popup is laid out — they may have shrunk since add-time (theme/font
        # changes), and a stale height shows as dead space between rows.
        self._recompute_uniform_heights()
        # Equalize opt-in row-label widths before anything measures a container,
        # so the popup-width pass below accounts for the final caption column.
        self._align_row_labels()

        # Let the base chain run first (ComboBox.showPopup sets
        # view.minimumWidth from sizeHintForColumn, then QComboBox.showPopup
        # creates/positions the popup frame).
        super().showPopup()

        # Now compute the real minimum width from embedded widgets and
        # override; the parent class only considers text-based items.
        view = self.view()
        min_w = max(view.sizeHintForColumn(0), self.width())
        for container in self._row_containers.values():
            if container is not None and not container.isHidden():
                container.adjustSize()
                for w in (
                    container.sizeHint().width(),
                    container.minimumWidth(),
                ):
                    if w > min_w:
                        min_w = w

        if min_w > view.minimumWidth():
            view.setMinimumWidth(min_w + 4)  # Add buffer for borders
            # The popup frame (a QFrame parenting the view) was already
            # sized by QComboBox.showPopup. Resize it to honour the new
            # minimum width.
            popup = view.window()
            if popup is not self.window():
                geo = popup.geometry()
                if geo.width() < (min_w + 4):
                    geo.setWidth(min_w + 4)
                    popup.setGeometry(geo)

    @property
    def arrow_direction(self) -> Optional[str]:
        """Direction of the dropdown-affordance chevron drawn after the text.

        One of ``"down"``, ``"up"``, ``"left"``, ``"right"`` — or ``None``
        (default) to draw no chevron.  The chevron is a thin open stroke in
        the text colour, not a filled triangle.  Ignored when
        :attr:`arrow_icon` is set (the icon takes precedence).  Chevron size,
        stroke and gap auto-scale with the current font.
        """
        return self._arrow.direction

    @arrow_direction.setter
    def arrow_direction(self, value: Optional[str]) -> None:
        self._arrow.set_direction(value)

    @property
    def arrow_icon(self) -> Optional[QtGui.QIcon]:
        """Custom icon drawn as the dropdown affordance, in place of the
        chevron.

        ``None`` (default) falls back to :attr:`arrow_direction` (a chevron,
        or nothing when that is also ``None``).  A non-null ``QIcon`` is drawn
        after the text regardless of ``arrow_direction``, at a font-scaled
        size and at :attr:`arrow_alpha` opacity.
        """
        return self._arrow.icon

    @arrow_icon.setter
    def arrow_icon(self, icon: Optional[QtGui.QIcon]) -> None:
        self._arrow.set_icon(icon)

    @property
    def arrow_alpha(self) -> float:
        """Opacity (``0.0``–``1.0``) of the dropdown affordance — the chevron
        or the custom :attr:`arrow_icon`.  Default ``1.0`` (fully opaque);
        values are clamped to the valid range."""
        return self._arrow.alpha

    @arrow_alpha.setter
    def arrow_alpha(self, value: float) -> None:
        self._arrow.set_alpha(value)

    def paintEvent(self, event) -> None:
        """Paint the base combo, then overlay the optional dropdown affordance
        immediately after the displayed text.

        Theme hides Qt's native ``QComboBox::down-arrow``.  When
        :attr:`arrow_icon` is set it is drawn here; otherwise a chevron
        pointing :attr:`arrow_direction` (text palette colour) is stroked.  Both scale
        with the font and honour :attr:`arrow_alpha`.  Draws nothing when
        neither is set (the default).
        """
        super().paintEvent(event)
        self._arrow.paint()

    @staticmethod
    def _compute_text_end_x(
        field_rect: QtCore.QRect, text_width: int, alignment: int
    ) -> float:
        if alignment & QtCore.Qt.AlignRight:
            return float(field_rect.right())
        if alignment & QtCore.Qt.AlignHCenter:
            return field_rect.center().x() + text_width / 2.0
        return float(field_rect.left() + text_width)

    # ------------------------------------------------------------------
    # High level API (matching ComboBox signature)
    # ------------------------------------------------------------------
    @Signals.blockSignals
    def add(
        self,
        x,
        data=None,
        header=None,
        header_alignment="left",
        clear=True,
        restore_index=False,
        ascending=False,
        _recursion=False,
        **kwargs,
    ):
        """Populate the combo box with text, widgets or actions.

        Matches ComboBox.add() signature while supporting widgets/actions.

        Parameters:
            x: Items to add - strings, widgets, actions, tuples, lists, dicts, etc.
            data: Optional fallback user data.
            header: Optional header text.
            header_alignment: Header alignment ("left", "right", "center").
            clear: When True, existing entries are removed first.
            restore_index: Restore previous selection after adding.
            ascending: Insert items at the top instead of bottom.
            **kwargs: Additional attributes to set.

        Returns:
            Added widget(s) or list of added items.
        """
        self.restore_previous_index = restore_index
        if restore_index:
            self.prev_index = self.currentIndex()

        if not _recursion and clear:
            self.clear()

        if not _recursion:
            self._strip_actions_section()

        if header:
            self.setHeaderText(header)
            self.setHeaderAlignment(header_alignment)
            self.has_header = True
        else:
            self.has_header = False

        added_items = []

        def add_single_item(item_value, item_data, is_widget=False):
            """Internal helper to add a single item."""
            if is_widget:
                # It's a widget - use widget path
                if isinstance(item_value, type) and issubclass(
                    item_value, QtWidgets.QWidget
                ):
                    widget = item_value()
                else:
                    widget = item_value

                label = self._infer_label(widget, None)
                self._add_widget_item(widget, label, item_data, ascending)
                added_items.append(widget)
                return widget
            else:
                # It's text - add via model (not QComboBox.addItem)
                row_item = QtGui.QStandardItem(str(item_value))
                if item_data is not None:
                    row_item.setData(item_data, QtCore.Qt.UserRole)

                if ascending:
                    self._model.insertRow(0, row_item)
                    self._shift_tracked_rows_down()
                else:
                    self._model.appendRow(row_item)

                added_items.append(item_value)
                return item_value

        # Handle list of (label, data) tuples
        if (
            isinstance(x, (list, tuple))
            and x
            and isinstance(x[0], (tuple, list))
            and len(x[0]) >= 2
        ):
            for entry in x:
                if self._looks_like_widget_tuple(entry):
                    widget, label, payload = self._parse_widget_tuple(entry, None, data)
                    self._add_widget_item(widget, label, payload, ascending)
                    added_items.append(widget)
                elif isinstance(entry[0], QtWidgets.QAction):
                    action = entry[0]
                    label = entry[1] if len(entry) > 1 else action.text()
                    widget = self._action_to_widget(action)
                    self._add_widget_item(widget, label, action, ascending)
                    added_items.append(widget)
                else:
                    # Standard (text, data) tuple
                    label, value = entry[0], entry[1]
                    add_single_item(label, value, is_widget=False)

        elif isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, (QtWidgets.QWidget, QtWidgets.QAction)):
                    if isinstance(v, QtWidgets.QAction):
                        widget = self._action_to_widget(v)
                        self._add_widget_item(widget, str(k), v, ascending)
                        added_items.append(widget)
                    else:
                        self._add_widget_item(v, str(k), data, ascending)
                        added_items.append(v)
                else:
                    add_single_item(k, v, is_widget=False)

        elif isinstance(x, (list, tuple, set)):
            for item in x:
                if isinstance(item, QtWidgets.QWidget):
                    label = self._infer_label(item, None)
                    self._add_widget_item(item, label, data, ascending)
                    added_items.append(item)
                elif isinstance(item, QtWidgets.QAction):
                    widget = self._action_to_widget(item)
                    self._add_widget_item(widget, item.text(), item, ascending)
                    added_items.append(widget)
                elif isinstance(item, type) and issubclass(item, QtWidgets.QWidget):
                    widget = item()
                    label = self._infer_label(widget, None)
                    self._add_widget_item(widget, label, data, ascending)
                    added_items.append(widget)
                elif isinstance(item, (tuple, list)) and len(item) >= 1:
                    # Check if it's a widget tuple
                    if self._looks_like_widget_tuple(item):
                        widget, label, payload = self._parse_widget_tuple(
                            item, None, data
                        )
                        self._add_widget_item(widget, label, payload, ascending)
                        added_items.append(widget)
                    elif isinstance(item[0], QtWidgets.QAction):
                        action = item[0]
                        label = item[1] if len(item) > 1 else action.text()
                        widget = self._action_to_widget(action)
                        self._add_widget_item(widget, label, action, ascending)
                        added_items.append(widget)
                    elif len(item) == 2:
                        # Standard (text, data) tuple
                        add_single_item(item[0], item[1], is_widget=False)
                    else:
                        add_single_item(str(item), data, is_widget=False)
                else:
                    add_single_item(item, data, is_widget=False)

        elif isinstance(x, (zip, map)):
            for i, d in x:
                add_single_item(i, d, is_widget=False)

        elif isinstance(x, QtWidgets.QWidget):
            label = self._infer_label(x, None)
            self._add_widget_item(x, label, data, ascending)
            added_items.append(x)

        elif isinstance(x, QtWidgets.QAction):
            widget = self._action_to_widget(x)
            self._add_widget_item(widget, x.text(), x, ascending)
            added_items.append(widget)

        elif isinstance(x, type) and issubclass(x, QtWidgets.QWidget):
            # Widget class passed - instantiate and apply kwargs to the widget
            widget = x()
            # Apply kwargs to the widget using set_attributes pattern
            for key, value in kwargs.items():
                if hasattr(widget, key):
                    attr = getattr(widget, key)
                    if callable(attr):
                        attr(value)
                    else:
                        setattr(widget, key, value)
            label = self._infer_label(widget, None)
            self._add_widget_item(widget, label, data, ascending)
            added_items.append(widget)
            # Clear kwargs so they don't get applied to combo
            kwargs = {}

        elif isinstance(x, str):
            add_single_item(x, data, is_widget=False)
        else:
            raise TypeError(
                f"Unsupported item type: '{type(x)}'. Expected str, widget, action, list, tuple, set, map, zip, or dict."
            )

        self.restore_state = not self.has_header
        self.set_attributes(**kwargs)

        if not _recursion:
            if header or self.header_text:
                self.force_header_display()
            final_index = -1 if self.header_text else 0
            if restore_index and self.prev_index > -1:
                self.setCurrentIndex(self.prev_index)
                final_index = self.prev_index
            elif self.header_text:
                self.prev_index = -1
                final_index = -1
            self.currentIndexChanged.emit(final_index)

            self._rebuild_actions_section()

        # Return single item or list matching ComboBox behavior
        if len(added_items) == 1:
            return added_items[0]
        return added_items

    def _add_widget_item(self, widget, label, data, ascending, track_height=True):
        """Internal method to add a widget item.

        ``track_height`` controls uniform-height enforcement. The actions
        section (separator + multi-button container) passes False so its
        legitimately taller rows don't inflate the uniform height applied
        to selectable rows above.
        """
        if widget.parent() is not None and widget.parent() is not self.view():
            widget.setParent(None)

        is_separator = widget.__class__.__name__ == "Separator"
        if is_separator:
            # For separators, pass empty string to the item so text isn't drawn behind the widget
            row_item = QtGui.QStandardItem("")
            # Disable selection for separators
            row_item.setFlags(
                row_item.flags()
                & ~QtCore.Qt.ItemIsSelectable
                & ~QtCore.Qt.ItemIsEnabled
            )
            # A separator's row is its own height (see ``_is_separator_row``):
            # untracked so it neither inflates the value rows nor gets
            # stretched to them. Its sizeHint height is invalid (NoFrame /
            # HLine), so pin the row to the widget's fixed height explicitly.
            track_height = False
        else:
            row_item = QtGui.QStandardItem(label)

        payload = data if data is not None else widget
        row_item.setData(payload, QtCore.Qt.UserRole)
        self._apply_uniform_height(row_item, widget, track=track_height)
        if is_separator:
            row_item.setSizeHint(QtCore.QSize(0, widget.height()))

        if ascending:
            self._model.insertRow(0, row_item)
            self._shift_tracked_rows_down()
            row = 0
        else:
            self._model.appendRow(row_item)
            row = self._model.rowCount() - 1

        container = self._wrap_widget(widget)
        self._set_index_widget(row, container)

        self._widget_items[row] = widget
        self._row_containers[row] = container
        self._defaults.capture(widget)
        return row

    # ------------------------------------------------------------------
    # Defaults capture / restore
    # ------------------------------------------------------------------
    @property
    def add_defaults_button(self) -> bool:
        """When True, adds a "Restore Defaults" action at the bottom of the
        dropdown that resets every embedded option widget (checkboxes,
        spinboxes, combos, line edits) to the value it had when added.

        Defaults are snapshotted in ``_add_widget_item``, so seed widget
        state BEFORE calling ``add()`` if you want it preserved as the
        reset target.
        """
        return self._defaults.add_button

    @add_defaults_button.setter
    def add_defaults_button(self, value: bool) -> None:
        self._defaults.set_add_button(value)

    # The snapshots, as tests and value readers reach them on the combo.
    _snapshot_value = staticmethod(_WidgetDefaults.snapshot_value)

    @property
    def _widget_defaults(self) -> dict:
        return self._defaults.snapshots

    def _infer_label(self, widget: QtWidgets.QWidget, fallback: Optional[str]) -> str:
        """Infer a label from a widget."""
        if fallback:
            return fallback
        if hasattr(widget, "text"):
            try:
                text = widget.text()  # type: ignore[attr-defined]
                if text:
                    return text
            except Exception:
                pass
        if hasattr(widget, "windowTitle"):
            title = widget.windowTitle()
            if title:
                return title
        object_name = widget.objectName()
        if object_name:
            return object_name
        return widget.metaObject().className() if widget.metaObject() else ""

    def _looks_like_widget_tuple(self, entry: Sequence[Any]) -> bool:
        """Check if a tuple represents a widget entry."""
        if not entry:
            return False
        head = entry[0]
        return isinstance(head, QtWidgets.QWidget) or (
            isinstance(head, type) and issubclass(head, QtWidgets.QWidget)
        )

    def _parse_widget_tuple(
        self,
        entry: Sequence[Any],
        default_label: Optional[str],
        default_data: Any,
    ) -> tuple[QtWidgets.QWidget, str, Any]:
        """Parse a widget tuple into (widget, label, data)."""
        if isinstance(entry[0], type) and issubclass(entry[0], QtWidgets.QWidget):
            widget = entry[0]()
        else:
            widget = entry[0]

        label_candidate: Optional[str] = None
        payload = default_data
        for value in entry[1:]:
            if isinstance(value, str) and label_candidate is None:
                label_candidate = value
            else:
                payload = value
        label_text = self._infer_label(widget, label_candidate or default_label)
        return widget, label_text, payload

    def _action_to_widget(self, action: QtWidgets.QAction) -> QtWidgets.QWidget:
        """Convert a QAction to a widget."""
        if isinstance(action, QtWidgets.QWidgetAction):
            created_widget = action.createWidget(self.view())
            if created_widget is None:
                created_widget = action.defaultWidget() or QtWidgets.QPushButton(
                    action.text(), self.view()
                )
            if hasattr(created_widget, "setDefaultAction"):
                created_widget.setDefaultAction(action)
        else:
            created_widget = QtWidgets.QPushButton(self.view())
            created_widget.setDefault(False)
            created_widget.setAutoDefault(False)
            created_widget.setText(action.text())
            created_widget.clicked.connect(action.trigger)  # type: ignore[attr-defined]
        return created_widget

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------
    def clear(self) -> None:  # type: ignore[override]
        self._actions_section.reset()
        for container in self._row_containers.values():
            if container:
                container.deleteLater()
        self._row_containers.clear()
        self._widget_items.clear()
        self._defaults.snapshots.clear()
        self._pending_index_widgets.clear()
        self._uniform_item_height = 0
        super().clear()


# -----------------------------------------------------------------------------
# Manual test harness
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    combo = WidgetComboBox()

    slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(50)

    nested_combo = QtWidgets.QComboBox()
    nested_combo.addItems(["Alpha", "Beta", "Gamma"])

    spin = QtWidgets.QDoubleSpinBox()
    spin.setDecimals(3)
    spin.setValue(3.141)

    action = QtWidgets.QAction("Trigger Message", combo)

    def on_action_triggered() -> None:
        QtWidgets.QMessageBox.information(combo, "Action", "Triggered from combo entry")

    action.triggered.connect(on_action_triggered)

    combo.add(
        [
            "Standard Item",
            (slider, "Slider"),
            (nested_combo, "Nested Combo"),
            (spin, "SpinBox"),
            (action, "Action Button"),
        ],
        clear=True,
    )

    spin_index = combo.findText("SpinBox")
    if spin_index != -1:
        combo.setCurrentIndex(spin_index)

    combo.resize(320, 32)
    combo.show()

    sys.exit(app.exec_())
