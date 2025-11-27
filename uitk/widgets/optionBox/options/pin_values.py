# !/usr/bin/python
# coding=utf-8
"""Pin Values option for OptionBox - allows pinning/saving widget values."""

from qtpy import QtWidgets, QtCore, QtGui
from ._options import ButtonOption


class PinnedValueEntry:
    """Represents a pinned value with an optional alias."""

    def __init__(self, value, alias=None):
        self.value = value
        self.alias = alias

    @property
    def display_text(self):
        """Get the text to display (alias if set, otherwise value)."""
        return self.alias if self.alias else str(self.value)

    def __eq__(self, other):
        if isinstance(other, PinnedValueEntry):
            return self.value == other.value
        return self.value == other

    def __hash__(self):
        return hash(self.value)


class PinnedValuesPopup(QtWidgets.QWidget):
    """A popup widget that displays pinned values with pin/unpin controls.

    This popup shows:
    - The current value (with option to pin/unpin it)
    - All previously pinned values (with options to restore or unpin them)
    """

    # Signals
    value_pinned = QtCore.Signal(object)  # value
    value_unpinned = QtCore.Signal(object)  # value
    value_selected = QtCore.Signal(object)  # value
    alias_set = QtCore.Signal(object)  # PinnedValueEntry (alias was set/changed)
    alias_reverted = QtCore.Signal(object)  # PinnedValueEntry (alias was cleared)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        # Setup UI
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)

        # Style the popup
        self.setStyleSheet(
            """
            PinnedValuesPopup {
                background: palette(window);
                border: 1px solid palette(mid);
                border-radius: 4px;
            }
        """
        )

    def clear(self):
        """Clear all items from the popup."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add_current_value(self, value, is_pinned=False):
        """Add the current value row.

        Args:
            value: The current value
            is_pinned: Whether the current value is already pinned
        """
        row = self._create_value_row(value, is_current=True, is_pinned=is_pinned)
        self._layout.addWidget(row)

    def add_separator(self):
        """Add a separator line."""
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        separator.setStyleSheet("background: palette(mid);")
        separator.setFixedHeight(1)
        self._layout.addWidget(separator)

    def add_pinned_value(self, entry):
        """Add a pinned value row.

        Args:
            entry: PinnedValueEntry with value and optional alias
        """
        row = self._create_value_row(entry, is_current=False, is_pinned=True)
        self._layout.addWidget(row)

    def add_empty_message(self):
        """Add a message when there are no pinned values."""
        label = QtWidgets.QLabel("No pinned values")
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setStyleSheet("padding: 8px; color: gray; font-style: italic;")
        self._layout.addWidget(label)

    def _create_value_row(self, value_or_entry, is_current=False, is_pinned=False):
        """Create a row widget for a value.

        Args:
            value_or_entry: The value or PinnedValueEntry to display
            is_current: Whether this is the current widget value
            is_pinned: Whether this value is pinned

        Returns:
            QWidget: A row widget with value button and pin button
        """
        from uitk.widgets.mixins.icon_manager import IconManager

        # Handle both raw values and PinnedValueEntry
        if isinstance(value_or_entry, PinnedValueEntry):
            entry = value_or_entry
            value = entry.value
            display_text = entry.display_text
        else:
            entry = None
            value = value_or_entry
            display_text = str(value)

        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        # Stacked widget to switch between button and edit mode
        stack = QtWidgets.QStackedWidget()
        stack.setContentsMargins(0, 0, 0, 0)

        # Value button - clicking selects/restores the value
        value_btn = QtWidgets.QPushButton(display_text)
        value_btn.setFlat(True)
        value_btn.setCursor(QtCore.Qt.PointingHandCursor)
        value_btn.setStyleSheet(
            """
            QPushButton {
                text-align: left;
                padding: 4px 8px;
                border: none;
                background: transparent;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: palette(highlight);
                color: palette(highlighted-text);
            }
        """
        )
        value_btn.clicked.connect(lambda: self._on_value_clicked(value))

        # Always show tooltip with full value
        value_btn.setToolTip(str(value))

        # Add context menu for all pinned entries (current or not)
        if entry is not None:
            value_btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            value_btn.customContextMenuRequested.connect(
                lambda pos, e=entry, s=stack: self._show_context_menu(pos, e, s)
            )

        stack.addWidget(value_btn)  # Index 0: button

        # Line edit for alias editing
        alias_edit = QtWidgets.QLineEdit()
        alias_edit.setStyleSheet(
            """
            QLineEdit {
                padding: 3px 7px;
                border: 1px solid palette(highlight);
                border-radius: 3px;
                background: palette(base);
            }
        """
        )
        alias_edit.setPlaceholderText("Enter alias...")

        # Store references for the edit handlers
        alias_edit.setProperty("_entry", entry)
        alias_edit.setProperty("_stack", stack)
        alias_edit.setProperty("_button", value_btn)

        # Connect enter key and focus out to finish editing
        alias_edit.returnPressed.connect(
            lambda e=alias_edit: self._finish_alias_edit(e)
        )
        alias_edit.editingFinished.connect(
            lambda e=alias_edit: self._finish_alias_edit(e)
        )

        stack.addWidget(alias_edit)  # Index 1: edit

        layout.addWidget(stack, 1)  # Stretch to fill

        # Pin/unpin button
        pin_btn = QtWidgets.QPushButton()
        pin_btn.setFixedSize(22, 22)
        pin_btn.setCursor(QtCore.Qt.PointingHandCursor)
        pin_btn.setFlat(True)
        pin_btn.setStyleSheet(
            """
            QPushButton {
                border: none;
                background: transparent;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.1);
            }
        """
        )

        if is_pinned:
            IconManager.set_icon(pin_btn, "pin_active", size=(14, 14))
            pin_btn.setToolTip("Unpin this value")
            pin_btn.clicked.connect(lambda: self._on_unpin_clicked(value))
        else:
            IconManager.set_icon(pin_btn, "pin", size=(14, 14))
            pin_btn.setToolTip("Pin this value")
            pin_btn.clicked.connect(lambda: self._on_pin_clicked(value))

        layout.addWidget(pin_btn)

        # Style the container for current value
        if is_current:
            container.setStyleSheet(
                """
                QWidget {
                    background: rgba(0, 120, 215, 0.15);
                    border-radius: 3px;
                }
            """
            )

        return container

    def _start_alias_edit(self, stack):
        """Start inline alias editing.

        Args:
            stack: The QStackedWidget containing button and edit widgets
        """
        alias_edit = stack.widget(1)  # Get the line edit
        entry = alias_edit.property("_entry")

        if entry:
            # Set current alias or original value as starting text
            alias_edit.setText(entry.alias or str(entry.value))
            alias_edit.selectAll()

        stack.setCurrentIndex(1)  # Switch to edit mode
        alias_edit.setFocus()

    def _finish_alias_edit(self, alias_edit):
        """Finish inline alias editing.

        Args:
            alias_edit: The QLineEdit widget
        """
        entry = alias_edit.property("_entry")
        stack = alias_edit.property("_stack")
        button = alias_edit.property("_button")

        if entry is None or stack is None:
            return

        # Prevent double-processing
        if stack.currentIndex() != 1:
            return

        new_alias = alias_edit.text().strip()

        if new_alias and new_alias != str(entry.value):
            entry.alias = new_alias
            if button:
                button.setText(new_alias)
            self.alias_set.emit(entry)
        else:
            # Cleared or same as original - revert to showing original
            entry.alias = None
            if button:
                button.setText(str(entry.value))
            self.alias_reverted.emit(entry)

        stack.setCurrentIndex(0)  # Switch back to button mode

    def _show_context_menu(self, pos, entry, stack):
        """Show context menu for a pinned value.

        Args:
            pos: Position for the menu
            entry: The PinnedValueEntry
            stack: The QStackedWidget for this row
        """
        button = stack.widget(0)
        menu = QtWidgets.QMenu(self)

        # Set/Change Alias option - starts inline edit
        if entry.alias:
            set_alias_action = menu.addAction("Change Alias")
        else:
            set_alias_action = menu.addAction("Set Alias")
        set_alias_action.triggered.connect(lambda: self._start_alias_edit(stack))

        # Revert to Original option (only if alias is set)
        if entry.alias:
            revert_action = menu.addAction("Revert to Original")
            revert_action.triggered.connect(lambda: self._revert_alias_inline(stack))

        menu.exec_(button.mapToGlobal(pos))

    def _revert_alias_inline(self, stack):
        """Revert alias inline without going through edit mode.

        Args:
            stack: The QStackedWidget for this row
        """
        alias_edit = stack.widget(1)
        button = stack.widget(0)
        entry = alias_edit.property("_entry")

        if entry:
            entry.alias = None
            button.setText(str(entry.value))
            self.alias_reverted.emit(entry)

    def _on_value_clicked(self, value):
        """Handle value button click."""
        self.value_selected.emit(value)
        self.close()

    def _on_pin_clicked(self, value):
        """Handle pin button click."""
        self.value_pinned.emit(value)

    def _on_unpin_clicked(self, value):
        """Handle unpin button click."""
        self.value_unpinned.emit(value)

    def showEvent(self, event):
        """Adjust size when shown."""
        super().showEvent(event)
        self.adjustSize()
        # Ensure minimum width
        if self.width() < 150:
            self.setFixedWidth(150)


class PinValuesOption(ButtonOption):
    """A pin button option that manages pinned widget values.

    This option allows users to "pin" values that can later be restored.
    Clicking the button shows a dropdown with:
    - The current value (with option to pin/unpin it)
    - All previously pinned values (with options to restore or unpin them)

    Example:
        line_edit = QtWidgets.QLineEdit()
        pin_option = PinValuesOption(line_edit)
        option_box = OptionBox(options=[pin_option])
        option_box.wrap(line_edit)

    Features:
        - Click to show dropdown of pinned values
        - Pin current value to save it
        - Click a pinned value to restore it
        - Unpin values to remove them from the list
        - Works with most input widgets
    """

    # Signal emitted when value is pinned/unpinned
    value_pinned = QtCore.Signal(bool, object)  # (is_pinned, value)
    # Signal emitted when a pinned value is restored
    value_restored = QtCore.Signal(object)  # (restored_value)

    def __init__(
        self,
        wrapped_widget=None,
        settings_key=None,
        max_pinned=10,
        double_click_to_edit=False,
        single_click_restore=False,
    ):
        """Initialize the pin values option.

        Args:
            wrapped_widget: The widget whose values to pin
            settings_key: Key for persistent settings. If provided, pinned values
                         will be saved and restored across sessions.
            max_pinned: Maximum number of pinned values to keep
            double_click_to_edit: Require double click to edit pinned value
            single_click_restore: Restore value on single click instead of double
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon="pin",
            tooltip="Pinned values",
            callback=self._show_popup,
            checkable=True,
        )
        self._pinned_entries = []  # List of PinnedValueEntry objects
        self._settings_key = settings_key
        self._max_pinned = max_pinned
        self._double_click_to_edit = double_click_to_edit
        self._single_click_restore = single_click_restore
        self._popup = None
        self._settings = None

        # Load saved pinned values if settings_key provided
        if self._settings_key:
            self._init_settings()
            self._load_pinned_values()

    def _init_settings(self):
        """Initialize settings manager for persistence."""
        if self._settings is None and self._settings_key:
            from uitk.widgets.mixins.settings_manager import SettingsManager

            self._settings = SettingsManager(
                org="uitk", app="PinValues", namespace=self._settings_key
            )

    def _save_pinned_values(self):
        """Save pinned values to persistent storage."""
        if not self._settings:
            return

        # Serialize entries as list of dicts
        data = []
        for entry in self._pinned_entries:
            data.append({"value": entry.value, "alias": entry.alias})

        self._settings.setValue("entries", data)
        self._settings.sync()

    def _load_pinned_values(self):
        """Load pinned values from persistent storage."""
        if not self._settings:
            return

        data = self._settings.value("entries", [])
        if not data:
            return

        self._pinned_entries = []
        for item in data:
            if isinstance(item, dict):
                value = item.get("value")
                alias = item.get("alias")
                if value is not None:
                    self._pinned_entries.append(PinnedValueEntry(value, alias))

        # Update button icon if we have values
        if self._pinned_entries and self._widget:
            self._update_button_icon()

    def create_widget(self):
        """Create the pin button widget."""
        button = super().create_widget()

        if not button.objectName():
            button.setObjectName("pinButton")

        button.setProperty("class", "PinButton")

        # Update icon based on loaded values
        if self._pinned_entries:
            self._update_button_icon()

        return button

    def _on_popup_destroyed(self):
        """Handle popup being destroyed."""
        self._popup = None
        # Block the next click to prevent immediate reopen
        self.block_next_click()
        # Uncheck button when popup closes
        self.set_checked(False)

    def _show_popup(self):
        """Show or hide the popup with pinned values (toggle via checkable button)."""
        # If button is unchecked, close popup if open
        if not self._widget.isChecked():
            if self._popup is not None:
                try:
                    self._popup.close()
                except RuntimeError:
                    pass
                self._popup = None
            return

        # Button is checked - show popup
        # Create a fresh popup
        self._popup = PinnedValuesPopup()

        # Connect destroyed signal to clear reference and uncheck button
        self._popup.destroyed.connect(self._on_popup_destroyed)

        # Connect signals
        self._popup.value_pinned.connect(self._pin_value)
        self._popup.value_unpinned.connect(self._unpin_value)
        self._popup.value_selected.connect(self._restore_value)
        self._popup.alias_set.connect(self._on_alias_changed)
        self._popup.alias_reverted.connect(self._on_alias_changed)

        # Populate the popup
        self._populate_popup()

        # Position and show the popup
        if self._widget:
            # Position below the button, aligned to right edge
            button_rect = self._widget.rect()
            global_pos = self._widget.mapToGlobal(
                QtCore.QPoint(button_rect.right(), button_rect.bottom())
            )
            # Adjust to align popup's right edge with button's right edge
            self._popup.adjustSize()
            global_pos.setX(global_pos.x() - self._popup.width())
            self._popup.move(global_pos)

        self._popup.show()

    def _get_entry_for_value(self, value):
        """Find the PinnedValueEntry for a given value."""
        for entry in self._pinned_entries:
            if entry.value == value:
                return entry
        return None

    def _populate_popup(self):
        """Populate the popup with current value and pinned values."""
        if not self._popup:
            return

        self._popup.clear()

        # Get current value
        current_value = self._get_widget_value()
        current_entry = self._get_entry_for_value(current_value)
        current_is_pinned = current_entry is not None
        has_current = current_value is not None and str(current_value).strip()

        # Add current value row (pass entry if pinned, otherwise raw value)
        if has_current:
            if current_entry is not None:
                self._popup.add_current_value(current_entry, is_pinned=True)
            else:
                self._popup.add_current_value(current_value, is_pinned=False)

        # Get pinned values excluding current, sorted alphabetically by display text
        pinned_excluding_current = sorted(
            [e for e in self._pinned_entries if e.value != current_value],
            key=lambda e: e.display_text.lower(),
        )

        if has_current and pinned_excluding_current:
            self._popup.add_separator()

        # Add pinned values (excluding current if it's pinned)
        for entry in pinned_excluding_current:
            self._popup.add_pinned_value(entry)

        # If nothing to show, add empty message
        if not has_current and not self._pinned_entries:
            self._popup.add_empty_message()

    def _pin_value(self, value):
        """Pin a value to the list."""
        if self._get_entry_for_value(value) is None:
            entry = PinnedValueEntry(value)
            self._pinned_entries.insert(0, entry)  # Add to front
            # Limit the number of pinned values
            if len(self._pinned_entries) > self._max_pinned:
                self._pinned_entries = self._pinned_entries[: self._max_pinned]

            # Update icon to show we have pinned values
            self._update_button_icon()

            # Save to persistent storage
            self._save_pinned_values()

            # Emit signal
            self.value_pinned.emit(True, value)

        # Refresh popup
        self._populate_popup()

    def _unpin_value(self, value):
        """Unpin a value from the list."""
        entry = self._get_entry_for_value(value)
        if entry is not None:
            self._pinned_entries.remove(entry)

            # Update icon
            self._update_button_icon()

            # Save to persistent storage
            self._save_pinned_values()

            # Emit signal
            self.value_pinned.emit(False, value)

        # Refresh popup
        self._populate_popup()

    def _restore_value(self, value):
        """Restore a pinned value to the widget."""
        self._set_widget_value(value)

        # Emit signal
        self.value_restored.emit(value)

    def _on_alias_changed(self, entry):
        """Handle alias being set or reverted (from inline edit).

        Args:
            entry: The PinnedValueEntry that was modified
        """
        self._save_pinned_values()

    def _update_button_icon(self):
        """Update the button icon based on whether there are pinned values."""
        if self._widget is None:
            return  # Widget not created yet

        from uitk.widgets.mixins.icon_manager import IconManager

        if self._pinned_entries:
            IconManager.set_icon(self._widget, "pin_active", size=(17, 17))
            self._widget.setToolTip(f"Pinned values ({len(self._pinned_entries)})")
        else:
            IconManager.set_icon(self._widget, "pin", size=(17, 17))
            self._widget.setToolTip("Pin values")

    def _get_widget_value(self):
        """Get the current value from the wrapped widget."""
        if not self.wrapped_widget:
            return None

        widget = self.wrapped_widget

        # Try different value getters
        if hasattr(widget, "text"):
            return widget.text()
        elif hasattr(widget, "value"):
            return widget.value()
        elif hasattr(widget, "currentText"):
            return widget.currentText()
        elif hasattr(widget, "toPlainText"):
            return widget.toPlainText()
        elif hasattr(widget, "isChecked"):
            return widget.isChecked()

        return None

    def _set_widget_value(self, value):
        """Set the value on the wrapped widget."""
        if not self.wrapped_widget or value is None:
            return

        widget = self.wrapped_widget

        # Try different value setters
        try:
            if hasattr(widget, "setText"):
                widget.setText(str(value))
            elif hasattr(widget, "setValue"):
                widget.setValue(value)
            elif hasattr(widget, "setCurrentText"):
                widget.setCurrentText(str(value))
            elif hasattr(widget, "setPlainText"):
                widget.setPlainText(str(value))
            elif hasattr(widget, "setChecked"):
                widget.setChecked(bool(value))
        except Exception as e:
            print(f"PinValuesOption: Error setting value: {e}")

    @property
    def pinned_values(self):
        """Get the list of pinned values (raw values, not entries)."""
        return [e.value for e in self._pinned_entries]

    @property
    def pinned_entries(self):
        """Get the list of PinnedValueEntry objects."""
        return list(self._pinned_entries)

    @property
    def has_pinned_values(self):
        """Check if there are any pinned values."""
        return bool(self._pinned_entries)

    def clear_pinned_values(self):
        """Clear all pinned values."""
        self._pinned_entries.clear()
        self._update_button_icon()
        self._save_pinned_values()

    def add_pinned_value(self, value, alias=None):
        """Programmatically add a pinned value.

        Args:
            value: The value to pin
            alias: Optional alias for the value
        """
        if self._get_entry_for_value(value) is None:
            entry = PinnedValueEntry(value, alias)
            self._pinned_entries.insert(0, entry)
            if len(self._pinned_entries) > self._max_pinned:
                self._pinned_entries = self._pinned_entries[: self._max_pinned]
            self._update_button_icon()
            self._save_pinned_values()
            self.value_pinned.emit(True, value)
