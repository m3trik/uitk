# !/usr/bin/python
# coding=utf-8
"""Pin Values option for OptionBox - allows pinning/saving widget values."""

from qtpy import QtWidgets, QtCore, QtGui
from ._options import ButtonOption


def _normalize_value(value):
    """Normalize a value for comparison (strips whitespace from strings)."""
    if isinstance(value, str):
        return value.strip()
    return value


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
            return _normalize_value(self.value) == _normalize_value(other.value)
        return _normalize_value(self.value) == _normalize_value(other)

    def __hash__(self):
        return hash(_normalize_value(self.value))


class PinnedValuesPopup(QtCore.QObject):
    """A popup that displays pinned values using the Menu widget.

    This popup shows:
    - The current value (with option to pin/unpin it)
    - All previously pinned values (with options to restore or unpin them)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        from uitk.widgets.menu import Menu

        self._parent_widget = parent

        # Create a Menu configured as a popup
        self._menu = Menu(
            parent=parent,
            trigger_button="none",  # We control showing manually
            position=None,  # We position manually - don't auto-reposition
            add_header=False,
            add_footer=False,
            add_apply_button=False,
            hide_on_leave=True,  # Hide when mouse leaves
            match_parent_width=False,
        )
        self._menu.setMinimumWidth(150)

        # Install event filters on parent and ancestors to close on hide
        self._install_visibility_filters()

        # Callbacks for handling actions
        self._on_value_pinned = None
        self._on_value_unpinned = None
        self._on_value_selected = None
        self._on_alias_changed = None

    @property
    def menu(self):
        """Get the underlying Menu widget."""
        return self._menu

    def _install_visibility_filters(self):
        """Install event filters on parent and ancestors to detect hide events."""
        self._watched_widgets = []
        widget = self._parent_widget
        while widget is not None:
            widget.installEventFilter(self)
            self._watched_widgets.append(widget)
            widget = widget.parent()

    def _remove_visibility_filters(self):
        """Remove event filters from watched widgets."""
        for widget in self._watched_widgets:
            try:
                widget.removeEventFilter(self)
            except RuntimeError:
                pass  # Widget may already be deleted
        self._watched_widgets.clear()

    def eventFilter(self, watched, event):
        """Close popup when any parent widget is hidden."""
        if event.type() == QtCore.QEvent.Hide:
            self.close()
        return False  # Don't block the event

    def connect_signals(
        self,
        on_value_pinned=None,
        on_value_unpinned=None,
        on_value_selected=None,
        on_alias_changed=None,
    ):
        """Connect signal handlers."""
        self._on_value_pinned = on_value_pinned
        self._on_value_unpinned = on_value_unpinned
        self._on_value_selected = on_value_selected
        self._on_alias_changed = on_alias_changed

    def clear(self):
        """Clear all items from the popup."""
        self._menu.clear()

    def show(self):
        """Show the popup."""
        self._menu.show()

    def close(self):
        """Close the popup and clean up event filters."""
        self._remove_visibility_filters()
        self._menu.hide()

    def move(self, pos):
        """Move the popup to a position."""
        self._menu.move(pos)

    def adjustSize(self):
        """Adjust the popup size."""
        self._menu.adjustSize()

    def width(self):
        """Get popup width."""
        return self._menu.width()

    def add_current_value(self, value, is_pinned=False):
        """Add the current value row."""
        row = self._create_value_row(value, is_current=True, is_pinned=is_pinned)
        self._menu.add(row)

    def add_separator(self):
        """Add a separator line."""
        separator = QtWidgets.QFrame()
        separator.setObjectName("pinnedValuesSeparator")
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        separator.setFixedHeight(1)
        self._menu.add(separator)

    def add_pinned_value(self, entry):
        """Add a pinned value row."""
        row = self._create_value_row(entry, is_current=False, is_pinned=True)
        self._menu.add(row)

    def add_empty_message(self):
        """Add a message when there are no pinned values."""
        label = QtWidgets.QLabel("No pinned values")
        label.setObjectName("pinnedValuesEmptyLabel")
        label.setAlignment(QtCore.Qt.AlignCenter)
        self._menu.add(label)

    def _create_value_row(self, value_or_entry, is_current=False, is_pinned=False):
        """Create a row widget for a value."""
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
        container.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        container.setObjectName(
            "pinnedValueRow_current" if is_current else "pinnedValueRow"
        )
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(1)

        # Stacked widget to switch between button and edit mode
        stack = QtWidgets.QStackedWidget()
        stack.setContentsMargins(0, 0, 0, 0)

        # Value button - clicking selects/restores the value
        value_btn = QtWidgets.QPushButton(display_text)
        value_btn.setObjectName("pinnedValueButton")
        value_btn.setFlat(True)
        value_btn.setCursor(QtCore.Qt.PointingHandCursor)
        value_btn.clicked.connect(lambda: self._on_value_clicked(value))
        value_btn.setToolTip(str(value))

        # Add context menu for pinned entries
        if entry is not None:
            value_btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            value_btn.customContextMenuRequested.connect(
                lambda pos, e=entry, s=stack, b=value_btn: self._show_context_menu(
                    pos, e, s, b
                )
            )

        stack.addWidget(value_btn)  # Index 0: button

        # Line edit for alias editing
        alias_edit = QtWidgets.QLineEdit()
        alias_edit.setObjectName("pinnedValueAliasEdit")
        alias_edit.setPlaceholderText("Enter alias...")
        alias_edit.setProperty("_entry", entry)
        alias_edit.setProperty("_stack", stack)
        alias_edit.setProperty("_button", value_btn)

        alias_edit.returnPressed.connect(
            lambda e=alias_edit: self._finish_alias_edit(e)
        )
        alias_edit.editingFinished.connect(
            lambda e=alias_edit: self._finish_alias_edit(e)
        )

        stack.addWidget(alias_edit)  # Index 1: edit
        layout.addWidget(stack, 1)

        # Pin/unpin button
        pin_btn = QtWidgets.QPushButton()
        pin_btn.setObjectName("pinnedValuePinButton")
        pin_btn.setFixedSize(22, 22)
        pin_btn.setCursor(QtCore.Qt.PointingHandCursor)
        pin_btn.setFlat(True)

        if is_pinned:
            IconManager.set_icon(pin_btn, "radio", size=(14, 14))
            pin_btn.setToolTip("Unpin this value")
            pin_btn.clicked.connect(lambda: self._on_unpin_clicked(value))
        else:
            IconManager.set_icon(pin_btn, "radio_empty", size=(14, 14))
            pin_btn.setToolTip("Pin this value")
            pin_btn.clicked.connect(lambda: self._on_pin_clicked(value))

        layout.addWidget(pin_btn)

        return container

    def _start_alias_edit(self, stack):
        """Start inline alias editing."""
        alias_edit = stack.widget(1)
        entry = alias_edit.property("_entry")

        if entry:
            alias_edit.setText(entry.alias or str(entry.value))
            alias_edit.selectAll()

        stack.setCurrentIndex(1)
        alias_edit.setFocus()

    def _finish_alias_edit(self, alias_edit):
        """Finish inline alias editing."""
        entry = alias_edit.property("_entry")
        stack = alias_edit.property("_stack")
        button = alias_edit.property("_button")

        if entry is None or stack is None:
            return

        if stack.currentIndex() != 1:
            return

        new_alias = alias_edit.text().strip()

        if new_alias and new_alias != str(entry.value):
            entry.alias = new_alias
            if button:
                button.setText(new_alias)
            if self._on_alias_changed:
                self._on_alias_changed(entry)
        else:
            entry.alias = None
            if button:
                button.setText(str(entry.value))
            if self._on_alias_changed:
                self._on_alias_changed(entry)

        stack.setCurrentIndex(0)

    def _show_context_menu(self, pos, entry, stack, button):
        """Show context menu for a pinned value."""
        # Temporarily disable hide_on_leave to prevent menu closing during context menu
        original_hide_on_leave = self._menu.hide_on_leave
        self._menu.hide_on_leave = False

        menu = QtWidgets.QMenu(self._menu)

        if entry.alias:
            set_alias_action = menu.addAction("Change Alias")
        else:
            set_alias_action = menu.addAction("Set Alias")
        set_alias_action.triggered.connect(lambda: self._start_alias_edit(stack))

        if entry.alias:
            remove_alias_action = menu.addAction("Remove Alias")
            remove_alias_action.triggered.connect(
                lambda: self._remove_alias_inline(stack, button, entry)
            )

        menu.exec_(button.mapToGlobal(pos))

        # Restore hide_on_leave after context menu closes
        self._menu.hide_on_leave = original_hide_on_leave

    def _remove_alias_inline(self, stack, button, entry):
        """Remove alias inline without going through edit mode."""
        entry.alias = None
        button.setText(str(entry.value))
        if self._on_alias_changed:
            self._on_alias_changed(entry)

    def _on_value_clicked(self, value):
        """Handle value button click."""
        if self._on_value_selected:
            self._on_value_selected(value)
        self.close()

    def _on_pin_clicked(self, value):
        """Handle pin button click."""
        if self._on_value_pinned:
            self._on_value_pinned(value)

    def _on_unpin_clicked(self, value):
        """Handle unpin button click."""
        if self._on_value_unpinned:
            self._on_value_unpinned(value)


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
            icon="radio_empty",
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

        # Connect to wrapped widget's value change signals to update icon
        self._connect_value_change_signals()

        # Defer initial icon update to ensure wrapped widget has its value set
        QtCore.QTimer.singleShot(0, self._update_button_icon)

        return button

    def _connect_value_change_signals(self):
        """Connect to the wrapped widget's value change signals."""
        widget = self.wrapped_widget
        if not widget:
            return

        # Try to connect to common value change signals
        if hasattr(widget, "textChanged"):
            widget.textChanged.connect(self._update_button_icon)
        elif hasattr(widget, "textEdited"):
            widget.textEdited.connect(self._update_button_icon)
        if hasattr(widget, "valueChanged"):
            widget.valueChanged.connect(self._update_button_icon)
        if hasattr(widget, "currentTextChanged"):
            widget.currentTextChanged.connect(self._update_button_icon)
        if hasattr(widget, "currentIndexChanged"):
            widget.currentIndexChanged.connect(self._update_button_icon)

    def _on_popup_hidden(self):
        """Handle popup being hidden."""
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
        # Create a fresh popup with wrapped widget as parent for theme inheritance
        self._popup = PinnedValuesPopup(parent=self.wrapped_widget)

        # Connect menu's on_hidden signal to uncheck button when menu closes
        self._popup.menu.on_hidden.connect(self._on_popup_hidden)

        # Connect callbacks
        self._popup.connect_signals(
            on_value_pinned=self._pin_value,
            on_value_unpinned=self._unpin_value,
            on_value_selected=self._restore_value,
            on_alias_changed=self._on_alias_changed,
        )

        # Populate and size the popup first
        self._populate_popup()
        self._popup.adjustSize()

        # Position and show the popup
        if self._widget:
            # Get the wrapped widget (the actual input widget, not the pin button)
            wrapped = self.wrapped_widget
            if wrapped:
                # Position below the wrapped widget, aligned to left edge
                widget_rect = wrapped.rect()
                global_pos = wrapped.mapToGlobal(QtCore.QPoint(0, widget_rect.height()))
            else:
                # Fallback: position below the button
                button_rect = self._widget.rect()
                global_pos = self._widget.mapToGlobal(
                    QtCore.QPoint(button_rect.right(), button_rect.bottom())
                )
                global_pos.setX(global_pos.x() - self._popup.width())

            self._popup.move(global_pos)

        self._popup.show()

    def _get_entry_for_value(self, value):
        """Find the PinnedValueEntry for a given value using normalized comparison."""
        for entry in self._pinned_entries:
            if entry == value:  # Uses PinnedValueEntry.__eq__ with normalization
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
            self._popup.add_separator()

        # Get pinned values excluding current, sorted alphabetically by display text
        # Use normalized comparison to handle trailing slashes/whitespace differences
        normalized_current = _normalize_value(current_value)
        pinned_excluding_current = sorted(
            [
                e
                for e in self._pinned_entries
                if _normalize_value(e.value) != normalized_current
            ],
            key=lambda e: e.display_text.lower(),
        )

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

            self._on_pinned_values_changed(is_pinned=True, value=value)

    def _unpin_value(self, value):
        """Unpin a value from the list."""
        entry = self._get_entry_for_value(value)
        if entry is not None:
            self._pinned_entries.remove(entry)
            self._on_pinned_values_changed(is_pinned=False, value=value)

    def _on_pinned_values_changed(self, is_pinned, value):
        """Common handler for pin/unpin operations.

        Updates UI, persists changes, emits signals, and refreshes popup.
        """
        self._update_button_icon()
        self._save_pinned_values()
        self.value_pinned.emit(is_pinned, value)

        # Defer popup refresh to after click event completes
        # This prevents the menu from hiding when the clicked button is destroyed
        QtCore.QTimer.singleShot(0, self._refresh_popup_deferred)

    def _refresh_popup_deferred(self):
        """Refresh the popup content (called via deferred timer).

        This method is called after button click events complete to avoid
        destroying the clicked button while it's still processing events.
        """
        if self._popup and self._popup.menu.isVisible():
            self._populate_popup()
            self._popup.adjustSize()

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

    def _update_button_icon(self, *args):
        """Update the button icon based on whether the current value is pinned.

        Args:
            *args: Ignored. Accepts arguments from signal connections.
        """
        if self._widget is None:
            return  # Widget not created yet

        from uitk.widgets.mixins.icon_manager import IconManager

        current_value = self._get_widget_value()
        current_is_pinned = self._get_entry_for_value(current_value) is not None

        if current_is_pinned:
            IconManager.set_icon(self._widget, "radio", size=(17, 17))
            self._widget.setToolTip(
                f"Pinned values ({len(self._pinned_entries)}) - current value is pinned"
            )
        elif self._pinned_entries:
            IconManager.set_icon(self._widget, "radio_empty", size=(17, 17))
            self._widget.setToolTip(f"Pinned values ({len(self._pinned_entries)})")
        else:
            IconManager.set_icon(self._widget, "radio_empty", size=(17, 17))
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
