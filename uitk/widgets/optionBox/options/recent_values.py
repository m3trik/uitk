# !/usr/bin/python
# coding=utf-8
"""Recent Values option for OptionBox — shows a selectable history list."""

from qtpy import QtWidgets, QtCore
import pythontk as ptk
from ._options import ButtonOption


def _normalize_value(value):
    """Normalize a value for comparison.

    Strips whitespace and, for path-like strings, normalizes separators
    and case so that ``C:/Dir`` and ``c:\\dir`` compare equal.
    """
    if isinstance(value, str):
        value = value.strip()
        if "/" in value or "\\" in value:
            value = ptk.format_path(value).lower()
    return value


class RecentValuesPopup(QtCore.QObject):
    """Popup that displays recent values using the Menu widget.

    Shows a list of previously used values that can be clicked to restore.
    """

    _MAX_DISPLAY_LENGTH = 60

    def __init__(self, parent=None):
        super().__init__(parent)
        from uitk.widgets.menu import Menu

        self._parent_widget = parent

        self._menu = Menu(
            parent=parent,
            trigger_button="none",
            position=None,
            add_header=False,
            add_footer=False,
            add_apply_button=False,
            hide_on_leave=True,
            match_parent_width=False,
        )
        self._menu.setMinimumWidth(150)

        self._install_visibility_filters()

        self._on_value_selected = None
        self._on_value_removed = None

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
                pass
        self._watched_widgets.clear()

    def eventFilter(self, watched, event):
        """Close popup when any parent widget is hidden."""
        if event.type() == QtCore.QEvent.Hide:
            self.close()
        return False

    def connect_signals(self, on_value_selected=None, on_value_removed=None):
        """Connect signal handlers."""
        self._on_value_selected = on_value_selected
        self._on_value_removed = on_value_removed

    def clear(self):
        self._menu.clear()

    def show(self):
        self._menu.show()

    def close(self):
        self._remove_visibility_filters()
        self._menu.hide()

    def move(self, pos):
        self._menu.move(pos)

    def adjustSize(self):
        self._menu.adjustSize()

    def width(self):
        return self._menu.width()

    def add_recent_value(self, value, is_current=False):
        """Add a recent-value row."""
        row = self._create_value_row(value, is_current=is_current)
        self._menu.add(row)

    def add_separator(self):
        separator = QtWidgets.QFrame()
        separator.setObjectName("recentValuesSeparator")
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        separator.setFixedHeight(1)
        self._menu.add(separator)

    def add_empty_message(self):
        label = QtWidgets.QLabel("No recent values")
        label.setObjectName("recentValuesEmptyLabel")
        label.setAlignment(QtCore.Qt.AlignCenter)
        self._menu.add(label)

    def _create_value_row(self, value, is_current=False):
        from uitk.widgets.mixins.icon_manager import IconManager

        full_text = str(value)
        display_text = ptk.truncate(full_text, self._MAX_DISPLAY_LENGTH, mode="start")

        container = QtWidgets.QWidget()
        container.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        container.setObjectName(
            "recentValueRow_current" if is_current else "recentValueRow"
        )
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(1, 0, 1, 0)
        layout.setSpacing(1)

        # Value button — click to restore
        value_btn = QtWidgets.QPushButton(display_text)
        value_btn.setObjectName("recentValueButton")
        value_btn.setFlat(True)
        value_btn.setCursor(QtCore.Qt.PointingHandCursor)
        value_btn.clicked.connect(lambda: self._on_value_clicked(value))
        value_btn.setToolTip(full_text)
        layout.addWidget(value_btn, 1)

        # Remove button
        remove_btn = QtWidgets.QPushButton()
        remove_btn.setObjectName("recentValueRemoveButton")
        remove_btn.setFixedSize(18, 18)
        remove_btn.setCursor(QtCore.Qt.PointingHandCursor)
        remove_btn.setFlat(True)
        IconManager.set_icon(remove_btn, "close", size=(10, 10))
        remove_btn.setToolTip("Remove from recent values")
        remove_btn.clicked.connect(lambda: self._on_remove_clicked(value))
        layout.addWidget(remove_btn)

        return container

    def _on_value_clicked(self, value):
        if self._on_value_selected:
            self._on_value_selected(value)
        self.close()

    def _on_remove_clicked(self, value):
        if self._on_value_removed:
            self._on_value_removed(value)


class RecentValuesOption(ButtonOption):
    """A history button that manages recent widget values.

    Clicking the button shows a dropdown of previously used values
    that can be restored with a single click.

    The list is populated automatically when ``record()`` is called
    (typically after a successful action like export), or values
    can be seeded programmatically via ``add_recent_value()``.

    Example::

        line_edit = QtWidgets.QLineEdit()
        recent = RecentValuesOption(line_edit, settings_key="my_recent")
        option_box = OptionBox(options=[recent])
        option_box.wrap(line_edit)

        # After user action:
        recent.record()  # saves current widget value
    """

    value_selected = QtCore.Signal(object)
    """Emitted when the user clicks a recent value to restore it."""

    def __init__(
        self,
        wrapped_widget=None,
        settings_key=None,
        max_recent=10,
    ):
        """Initialize the recent values option.

        Args:
            wrapped_widget: The widget whose values to track.
            settings_key: Key for persistent storage.  If provided,
                recent values survive across sessions.
            max_recent: Maximum number of entries to keep.
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon="clock",
            tooltip="Recent values",
            callback=self._show_popup,
            checkable=True,
        )
        self._recent_values: list = []
        self._settings_key = settings_key
        self._max_recent = max_recent
        self._popup = None
        self._settings = None

        if self._settings_key:
            self._init_settings()
            self._load_recent_values()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _init_settings(self):
        if self._settings is None and self._settings_key:
            from uitk.widgets.mixins.settings_manager import SettingsManager

            self._settings = SettingsManager(
                org="uitk", app="RecentValues", namespace=self._settings_key
            )

    def _save_recent_values(self):
        if not self._settings:
            return
        self._settings.setValue("entries", list(self._recent_values))
        self._settings.sync()

    def _load_recent_values(self):
        if not self._settings:
            return
        data = self._settings.value("entries", [])
        if not data:
            return
        # Deduplicate on load (keeps first occurrence = most recent)
        seen = set()
        deduped = []
        for v in data:
            if v is None:
                continue
            n = _normalize_value(v)
            if n not in seen:
                seen.add(n)
                deduped.append(v)
        self._recent_values = deduped
        if self._widget:
            self._update_button_tooltip()

    # ------------------------------------------------------------------
    # Widget creation
    # ------------------------------------------------------------------

    def create_widget(self):
        button = super().create_widget()
        if not button.objectName():
            button.setObjectName("recentButton")
        button.setProperty("class", "RecentButton")
        QtCore.QTimer.singleShot(0, self._update_button_tooltip)
        return button

    # ------------------------------------------------------------------
    # Popup
    # ------------------------------------------------------------------

    def _on_popup_hidden(self):
        self._popup = None
        self.block_next_click()
        self.set_checked(False)

    def _show_popup(self):
        if not self._widget.isChecked():
            if self._popup is not None:
                try:
                    self._popup.close()
                except RuntimeError:
                    pass
                self._popup = None
            return

        self._popup = RecentValuesPopup(parent=self.wrapped_widget)
        self._popup.menu.on_hidden.connect(self._on_popup_hidden)
        self._popup.connect_signals(
            on_value_selected=self._restore_value,
            on_value_removed=self._remove_value,
        )

        self._populate_popup()
        self._popup.adjustSize()

        if self._widget:
            wrapped = self.wrapped_widget
            if wrapped:
                widget_rect = wrapped.rect()
                global_pos = wrapped.mapToGlobal(QtCore.QPoint(0, widget_rect.height()))
            else:
                button_rect = self._widget.rect()
                global_pos = self._widget.mapToGlobal(
                    QtCore.QPoint(button_rect.right(), button_rect.bottom())
                )
                global_pos.setX(global_pos.x() - self._popup.width())

            self._popup.move(global_pos)

        self._popup.show()

    def _populate_popup(self):
        if not self._popup:
            return

        self._popup.clear()

        current_value = self._get_widget_value()
        normalized_current = _normalize_value(current_value)
        has_current = current_value is not None and str(current_value).strip()

        # Show current value at the top if not empty
        if has_current:
            self._popup.add_recent_value(current_value, is_current=True)
            self._popup.add_separator()

        # Recent values excluding the current one
        others = [
            v for v in self._recent_values if _normalize_value(v) != normalized_current
        ]

        for v in others:
            self._popup.add_recent_value(v)

        if not has_current and not others:
            self._popup.add_empty_message()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _restore_value(self, value):
        self._set_widget_value(value)
        self.value_selected.emit(value)

    def _remove_value(self, value):
        normalized = _normalize_value(value)
        self._recent_values = [
            v for v in self._recent_values if _normalize_value(v) != normalized
        ]
        self._save_recent_values()
        self._update_button_tooltip()
        # Refresh popup in-place
        QtCore.QTimer.singleShot(0, self._refresh_popup_deferred)

    def _refresh_popup_deferred(self):
        if self._popup and self._popup.menu.isVisible():
            self._populate_popup()
            self._popup.adjustSize()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, value=None):
        """Record a value into the recent list.

        If *value* is ``None`` the current widget value is used.
        Duplicates are moved to the front (most-recent-first order).
        """
        if value is None:
            value = self._get_widget_value()
        if value is None or not str(value).strip():
            return

        normalized = _normalize_value(value)
        # Remove existing duplicate
        self._recent_values = [
            v for v in self._recent_values if _normalize_value(v) != normalized
        ]
        # Insert at front
        self._recent_values.insert(0, value)
        # Trim
        self._recent_values = self._recent_values[: self._max_recent]

        self._save_recent_values()
        self._update_button_tooltip()

    def add_recent_value(self, value):
        """Programmatically seed a recent value (appends if not duplicate)."""
        if value is None or not str(value).strip():
            return
        normalized = _normalize_value(value)
        if any(_normalize_value(v) == normalized for v in self._recent_values):
            return
        self._recent_values.append(value)
        if len(self._recent_values) > self._max_recent:
            self._recent_values = self._recent_values[-self._max_recent :]
        self._save_recent_values()
        self._update_button_tooltip()

    @property
    def recent_values(self):
        """Return a copy of the recent values list (most-recent first)."""
        return list(self._recent_values)

    def clear_recent_values(self):
        """Clear all recent values."""
        self._recent_values.clear()
        self._save_recent_values()
        self._update_button_tooltip()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_button_tooltip(self, *_args):
        if self._widget is None:
            return
        n = len(self._recent_values)
        if n:
            self._widget.setToolTip(f"Recent values ({n})")
        else:
            self._widget.setToolTip("Recent values")
