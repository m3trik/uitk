# !/usr/bin/python
# coding=utf-8
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Optional, Union

from qtpy import QtWidgets, QtGui, QtCore
from uitk.widgets.mixins.switchboard_slots import Signals
from uitk.widgets.comboBox import ComboBox


class _ActionsNamespace:
    """Lightweight helper surfaced as ``WidgetComboBox.actions``.

    Provides a concise API for managing persistent action buttons that
    appear below a separator at the bottom of the dropdown.

    Usage::

        combo.actions.add("✏ Rename…", on_rename)
        combo.actions.add("＋ Add…", on_add)
        # Or batch via dict / list of tuples:
        combo.actions.add({
            "✏ Rename…": on_rename,
            "＋ Add…": on_add,
        })

        combo.actions.remove("＋ Add…")
        combo.actions.clear()
    """

    __slots__ = ("_combo", "_actions")

    def __init__(self, combo: "WidgetComboBox") -> None:
        self._combo = combo
        self._actions: list[QtWidgets.QAction] = []

    # --- Public API ---

    def add(self, label_or_items, callback=None):
        """Add one or more persistent actions.

        Accepts flexible input forms:
            add("Label", callback)              — single action
            add({"Label": callback, ...})       — dict of label→callback
            add([("Label", callback), ...])     — list of (label, callback) pairs

        Parameters:
            label_or_items: A string label, a dict mapping labels to callables,
                or a sequence of (label, callable) pairs.
            callback: Callable triggered when the action is clicked.
                Required when *label_or_items* is a string; ignored otherwise.

        Returns:
            The created QAction (single form) or list of QActions (batch form).
        """
        if isinstance(label_or_items, str):
            action = self._make_action(label_or_items, callback)
            self._actions.append(action)
            self._combo._rebuild_actions_section()
            return action

        pairs = (
            label_or_items.items()
            if isinstance(label_or_items, dict)
            else label_or_items
        )
        created = []
        for label, cb in pairs:
            action = self._make_action(label, cb)
            self._actions.append(action)
            created.append(action)
        self._combo._rebuild_actions_section()
        return created

    def remove(self, label: str) -> bool:
        """Remove the first action matching *label*.

        Returns True if an action was removed, False otherwise.
        """
        for i, action in enumerate(self._actions):
            if action.text() == label:
                self._actions.pop(i)
                self._combo._rebuild_actions_section()
                return True
        return False

    def clear(self) -> None:
        """Remove all persistent actions and the separator."""
        self._actions.clear()
        self._combo._strip_actions_section()

    # --- Dunder helpers ---

    def __len__(self) -> int:
        return len(self._actions)

    def __bool__(self) -> bool:
        return bool(self._actions)

    def __iter__(self):
        return iter(self._actions)

    def __contains__(self, label: str) -> bool:
        return any(a.text() == label for a in self._actions)

    # --- Internals ---

    def _make_action(self, label: str, callback) -> QtWidgets.QAction:
        action = QtWidgets.QAction(label, self._combo)
        if callback is not None:
            action.triggered.connect(callback)
        return action


class WidgetComboBox(ComboBox):
    """ComboBox extended with widget embedding support.

    Inherits all features from ComboBox and adds:
    - Embedded widgets via QListView.setIndexWidget
    - QActions as menu items
    - Mixed content (text, widgets, and actions in one dropdown)

    Uses QStandardItemModel + QListView instead of the default combo model
    to support setIndexWidget() for embedded widgets.
    """

    def __init__(
        self, parent: Optional[QtWidgets.QWidget] = None, editable=False, **kwargs
    ):
        # Call ComboBox.__init__ first to setup base functionality
        super().__init__(parent, editable=editable, **kwargs)

        # Widget-specific: Use QListView + QStandardItemModel for setIndexWidget support
        list_view = QtWidgets.QListView(self)
        list_view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        list_view.setSpacing(0)  # Compact layout with no spacing between items
        self.setView(list_view)

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

        # Persistent actions section (separator + action buttons at bottom of dropdown)
        self._actions_ns = _ActionsNamespace(self)
        self._action_row_count: int = 0

        # Create overflow indicator (initialized lazily on first popup)
        self._overflow_indicator = None

        # Install event filter on the view to track scrolling
        list_view.viewport().installEventFilter(self)

        self.currentIndexChanged.connect(self._on_index_changed)

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

        row_item = QtGui.QStandardItem(label)
        payload = data if data is not None else widget
        row_item.setData(payload, QtCore.Qt.UserRole)
        size_hint = widget.sizeHint()
        if size_hint.isValid():
            row_item.setSizeHint(size_hint)

        self._model.appendRow(row_item)
        row = self._model.rowCount() - 1

        container = self._wrap_widget(widget)
        self._set_index_widget(row, container)

        self._widget_items[row] = widget
        self._row_containers[row] = container

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
        return self.addWidgetItem(
            created_widget,
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

        if container is not None:
            container.deleteLater()

        self._model.removeRow(row)
        self._rebuild_index_maps()
        return widget

    def currentWidget(self) -> Optional[QtWidgets.QWidget]:
        """Convenience accessor for the selected widget."""

        return self._widget_items.get(self.currentIndex())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _wrap_widget(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Embed the widget inside a marginless container for layout control."""

        container = QtWidgets.QWidget(self.view())
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(widget)
        container.setProperty("_embedded_widget", widget)
        return container

    def _rebuild_index_maps(self) -> None:
        """After row removal remap stored widgets to their new rows."""

        if not self._widget_items:
            return

        new_widgets: dict[int, QtWidgets.QWidget] = {}
        new_containers: dict[int, QtWidgets.QWidget] = {}
        for row in range(self._model.rowCount()):
            index = self._model.index(row, 0)
            widget = self.view().indexWidget(index)
            if widget is None:
                continue
            inner_widget = widget.property("_embedded_widget")
            if inner_widget is None:
                continue
            new_widgets[row] = inner_widget
            new_containers[row] = widget
        self._widget_items = new_widgets
        self._row_containers = new_containers

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

    def _strip_actions_section(self) -> None:
        """Remove existing action rows (separator + buttons) from the bottom."""
        if self._action_row_count == 0:
            return

        total = self._model.rowCount()
        for row in range(total - 1, total - self._action_row_count - 1, -1):
            if row < 0:
                break
            container = self._row_containers.pop(row, None)
            self._widget_items.pop(row, None)
            if container is not None:
                container.deleteLater()
            self._model.removeRow(row)

        remaining = self._model.rowCount()
        self._pending_index_widgets = [
            (r, c) for r, c in self._pending_index_widgets if r < remaining
        ]
        self._action_row_count = 0

    def _rebuild_actions_section(self) -> None:
        """Rebuild the separator + action buttons at the bottom.

        All action buttons are grouped inside a single container widget
        with zero margins and left alignment, added as one model row
        beneath the separator.
        """
        self._strip_actions_section()
        if not self._actions_ns._actions:
            return

        from uitk.widgets.separator import Separator

        sep = Separator()
        self._add_widget_item(sep, "", None, ascending=False)

        # Build a single container holding all action buttons vertically.
        container = QtWidgets.QWidget(self.view())
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        max_btn_width = 0
        for action in self._actions_ns._actions:
            btn = QtWidgets.QPushButton(container)
            btn.setText(action.text())
            if action.icon() and not action.icon().isNull():
                btn.setIcon(action.icon())
            btn.setDefault(False)
            btn.setAutoDefault(False)
            btn.setProperty("class", "combobox-action")
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.clicked.connect(action.trigger)
            btn.clicked.connect(self.hidePopup)
            btn.setStyleSheet("text-align: left; padding-left: 4px;")
            layout.addWidget(btn)
            # Track widest button via sizeHint (reliable for QPushButton).
            w = btn.sizeHint().width()
            if w > max_btn_width:
                max_btn_width = w

        # Force the container to adopt a valid size before it's embedded.
        container.setMinimumWidth(max_btn_width)
        container.adjustSize()

        row = self._add_widget_item(container, "", None, ascending=False)
        item = self._model.item(row)
        if item:
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)

        self._action_row_count = 2  # separator + 1 container row

    def _create_overflow_indicator(self) -> QtWidgets.QLabel:
        """Create a minimal triangle arrow indicator for overflow."""
        view = self.view()
        if not view or not view.viewport():
            return None

        indicator = QtWidgets.QLabel(view.viewport())
        indicator.setAlignment(QtCore.Qt.AlignCenter)
        # Simple down-pointing triangle
        indicator.setText("▼")
        indicator.setStyleSheet(
            """
            QLabel {
                background-color: rgba(0, 0, 0, 100);
                color: white;
                font-size: 10px;
                padding: 2px;
            }
        """
        )
        indicator.setFixedHeight(16)
        indicator.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        indicator.hide()
        return indicator

    def _update_overflow_indicator(self) -> None:
        """Show or hide the overflow indicator based on item count."""
        item_count = self._model.rowCount()
        max_visible = self.maxVisibleItems()

        # Show indicator if there are more items than can be displayed
        if item_count > max_visible:
            view = self.view()
            if not view or not view.isVisible():
                return

            # Create indicator if it doesn't exist
            if self._overflow_indicator is None:
                self._overflow_indicator = self._create_overflow_indicator()
                if self._overflow_indicator is None:
                    return

            self._overflow_indicator.show()
            self._reposition_indicator()
        else:
            if self._overflow_indicator:
                self._overflow_indicator.hide()

    def showPopup(self) -> None:
        """Override to expand popup to widest widget and update overflow."""
        self._flush_pending_index_widgets()

        # Let the base chain run first (ComboBox.showPopup sets
        # view.minimumWidth from sizeHintForColumn, then QComboBox.showPopup
        # creates/positions the popup frame).
        super().showPopup()

        # Now compute the real minimum width from embedded widgets and
        # override; the parent class only considers text-based items.
        view = self.view()
        min_w = max(view.sizeHintForColumn(0), self.width())
        for container in self._row_containers.values():
            if container is not None:
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

        # Use a longer delay to ensure the view is fully laid out
        QtCore.QTimer.singleShot(50, self._update_overflow_indicator)
        # Also update again after scrollbar adjustments
        QtCore.QTimer.singleShot(150, self._update_overflow_indicator)

    def hidePopup(self) -> None:
        """Override to hide overflow indicator when popup is hidden."""
        if self._overflow_indicator:
            self._overflow_indicator.hide()
        super().hidePopup()

    def eventFilter(self, obj, event):
        """Event filter to reposition indicator on scroll and resize events."""
        if obj == self.view().viewport():
            # Reposition indicator on scroll, resize, or paint events
            if event.type() in (QtCore.QEvent.Paint, QtCore.QEvent.Resize):
                if self._overflow_indicator and self._overflow_indicator.isVisible():
                    self._reposition_indicator()
        return super().eventFilter(obj, event)

    def _reposition_indicator(self):
        """Reposition the indicator at the bottom of the viewport."""
        if not self._overflow_indicator:
            return

        view = self.view()
        if not view or not view.isVisible():
            return

        viewport = view.viewport()
        if viewport:
            indicator_width = viewport.width()
            indicator_height = self._overflow_indicator.height()
            indicator_y = viewport.height() - indicator_height

            self._overflow_indicator.setGeometry(
                0, indicator_y, indicator_width, indicator_height
            )
            self._overflow_indicator.raise_()

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
                row = self._add_widget_item(widget, label, item_data, ascending)
                added_items.append(widget)
                return widget
            else:
                # It's text - add via model (not QComboBox.addItem)
                row_item = QtGui.QStandardItem(str(item_value))
                if item_data is not None:
                    row_item.setData(item_data, QtCore.Qt.UserRole)

                if ascending:
                    self._model.insertRow(0, row_item)
                    row = 0
                else:
                    self._model.appendRow(row_item)
                    row = self._model.rowCount() - 1

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

    def _add_widget_item(self, widget, label, data, ascending):
        """Internal method to add a widget item."""
        if widget.parent() is not None and widget.parent() is not self.view():
            widget.setParent(None)

        if widget.__class__.__name__ == "Separator":
            # For separators, pass empty string to the item so text isn't drawn behind the widget
            row_item = QtGui.QStandardItem("")
            # Disable selection for separators
            row_item.setFlags(
                row_item.flags()
                & ~QtCore.Qt.ItemIsSelectable
                & ~QtCore.Qt.ItemIsEnabled
            )
        else:
            row_item = QtGui.QStandardItem(label)

        payload = data if data is not None else widget
        row_item.setData(payload, QtCore.Qt.UserRole)
        size_hint = widget.sizeHint()
        if size_hint.isValid():
            row_item.setSizeHint(size_hint)

        if ascending:
            self._model.insertRow(0, row_item)
            row = 0
        else:
            self._model.appendRow(row_item)
            row = self._model.rowCount() - 1

        index = self._model.index(row, 0)

        container = self._wrap_widget(widget)
        self._set_index_widget(row, container)

        self._widget_items[row] = widget
        self._row_containers[row] = container
        return row

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
        for container in self._row_containers.values():
            if container:
                container.deleteLater()
        self._row_containers.clear()
        self._widget_items.clear()
        self._pending_index_widgets.clear()
        self._action_row_count = 0
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
