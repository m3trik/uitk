# !/usr/bin/python
# coding=utf-8
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Optional, Union

from qtpy import QtWidgets, QtGui, QtCore
from uitk.signals import Signals
from uitk.widgets.comboBox import ComboBox


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

        # Create overflow indicator (initialized lazily on first popup)
        self._overflow_indicator = None

        # Install event filter on the view to track scrolling
        list_view.viewport().installEventFilter(self)

        self.currentIndexChanged.connect(self._on_index_changed)

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
        index = self._model.index(row, 0)

        container = self._wrap_widget(widget)
        self.view().setIndexWidget(index, container)

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
        """Override to update overflow indicator when popup is shown."""
        super().showPopup()
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

        # Return single item or list matching ComboBox behavior
        if len(added_items) == 1:
            return added_items[0]
        return added_items

    def _add_widget_item(self, widget, label, data, ascending):
        """Internal method to add a widget item."""
        if widget.parent() is not None and widget.parent() is not self.view():
            widget.setParent(None)

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
        self.view().setIndexWidget(index, container)

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
