# !/usr/bin/python
# coding=utf-8
"""Recent Values option for OptionBox — shows a selectable history list."""

from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk
from ._options import ButtonOption

# Canonical home for the storage/formatting logic is the widget-free
# RecentValuesStore. Re-exported here for backward compatibility \u2014 earlier
# code (and tests) import these names from this module.
from uitk.widgets.mixins.recent_values_store import (  # noqa: F401 -- re-export surface
    RecentValuesStore,
    RecentValueEntry,
    normalize_value as _normalize_value,
    _entry_data,
    _is_filesystem_path,
    _build_display_map_smart_path,
)


class RecentValuesPopup(QtCore.QObject):
    """Popup that displays recent values using the Menu widget.

    Shows a list of previously used values that can be clicked to restore.
    """

    _MAX_DISPLAY_LENGTH = 120

    def __init__(self, parent=None, text_align="center"):
        super().__init__(parent)
        from uitk.widgets.menu import Menu

        self._parent_widget = parent
        self._text_align = text_align

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
        menu_layout = self._menu._layout
        if menu_layout:
            menu_layout.setContentsMargins(1, 1, 1, 1)

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
        """Close popup when any parent widget is hidden or a window-ancestor moves."""
        et = event.type()
        if et == QtCore.QEvent.Hide:
            self.close()
        elif et == QtCore.QEvent.Move:
            try:
                if watched.isWindow():
                    self.close()
            except RuntimeError:
                pass
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

    def add_recent_value(self, value, display_text=None):
        """Add a recent-value row.

        Args:
            value: The raw value to store/restore.
            display_text: Override text shown on the button.
                If ``None``, falls back to default truncation.
        """
        row = self._create_value_row(value, display_text=display_text)
        self._menu.add(row)

    def add_empty_message(self):
        label = QtWidgets.QLabel("No recent values")
        label.setObjectName("recentValuesEmptyLabel")
        label.setAlignment(QtCore.Qt.AlignCenter)
        self._menu.add(label)

    def _create_value_row(self, value, display_text=None):
        from uitk.widgets.mixins.icon_manager import IconManager

        full_text = str(_entry_data(value))
        if display_text is None:
            display_text = ptk.truncate(
                full_text, self._MAX_DISPLAY_LENGTH, mode="middle"
            )

        container = QtWidgets.QWidget()
        container.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        container.setObjectName("recentValueRow")
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(1, 0, 8, 0)
        layout.setSpacing(4)

        # Value button — click to restore
        value_btn = QtWidgets.QPushButton(display_text)
        value_btn.setObjectName("recentValueButton")
        value_btn.setFlat(True)
        value_btn.setCursor(QtCore.Qt.PointingHandCursor)
        value_btn.clicked.connect(lambda: self._on_value_clicked(value))
        value_btn.setToolTip(full_text)
        if self._text_align == "left":
            value_btn.setStyleSheet("text-align: left; padding-left: 4px;")
        elif self._text_align == "right":
            value_btn.setStyleSheet("text-align: right; padding-right: 4px;")
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
        display_format="auto",
        popup_align="right",
        text_align="center",
        auto_record=False,
        store=None,
    ):
        """Initialize the recent values option.

        Args:
            wrapped_widget: The widget whose values to track.
            settings_key: Key for persistent storage.  If provided,
                recent values survive across sessions.
            max_recent: Maximum number of entries to keep.
            display_format: Controls how values appear in the popup.
                ``"auto"`` — strip common directory prefix when all
                values are filesystem paths; otherwise truncate.
                ``"truncate"`` — always use simple start-truncation
                (previous default behaviour).
                ``"basename"`` — show only the last path component.
                A callable ``(value) -> str`` for arbitrary formatting.
            popup_align: Horizontal alignment of the popup.
                ``"right"`` — align popup's right edge to the parent
                window's right edge (default).
                ``"left"`` — align popup's left edge to the wrapped widget.
            text_align: Text alignment for value labels in the popup.
                ``"center"`` (default), ``"left"``, or ``"right"``.
            auto_record: When True, automatically call ``record()`` when
                the wrapped widget commits a value:
                  - ``QLineEdit``: on ``editingFinished``
                  - widgets exposing a ``validated(bool, str)`` signal
                    (e.g. ``uitk.LineEdit`` with ``set_validator()``):
                    only when ``is_valid`` is True
                  - ``QComboBox``: on ``editTextChanged`` only when the
                    text matches an item (avoids per-keystroke noise).
                Off by default — callers must invoke ``record()`` from
                their own commit path (e.g. browse success, action).
            store: An existing :class:`RecentValuesStore` to present. When
                given it overrides *settings_key*/*max_recent*/*display_format*
                and lets several presenters (e.g. this popup and an
                ExpandableList) share one history.
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon="clock",
            tooltip="Recent values",
            callback=self._show_popup,
            checkable=True,
        )
        self._popup_align = popup_align
        self._text_align = text_align
        self._popup = None
        self._auto_record = bool(auto_record)
        self._auto_record_connected = False

        # Storage, persistence and display-formatting live in the shared,
        # widget-free store; this option is just a presenter over it.
        self._store = store or RecentValuesStore(
            settings_key=settings_key,
            max_recent=max_recent,
            display_format=display_format,
        )
        self._store.subscribe(self._update_button_tooltip)

        if self._auto_record and wrapped_widget is not None:
            self._install_auto_record(wrapped_widget)

    @property
    def store(self):
        """The backing :class:`RecentValuesStore` (shareable across presenters)."""
        return self._store

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

        self._popup = RecentValuesPopup(
            parent=self.wrapped_widget, text_align=self._text_align
        )
        self._popup.menu.on_hidden.connect(self._on_popup_hidden)
        self._popup.connect_signals(
            on_value_selected=self._restore_value,
            on_value_removed=self._remove_value,
        )

        self._populate_popup()

        # Let the menu size to its natural sizeHint, clamped to the screen so
        # it can't run off-screen for very long values.
        window = self._find_parent_window()
        self._popup.menu.setMaximumWidth(self._screen_width_cap(window))
        self._popup.adjustSize()

        if self._widget:
            wrapped = self.wrapped_widget
            if wrapped:
                widget_rect = wrapped.rect()
                if self._popup_align == "right" and window:
                    # Align popup's right edge to the window's right edge
                    win_right = window.mapToGlobal(QtCore.QPoint(window.width(), 0)).x()
                    popup_x = win_right - self._popup.width() - 8
                    popup_y = wrapped.mapToGlobal(
                        QtCore.QPoint(0, widget_rect.height())
                    ).y()
                    global_pos = QtCore.QPoint(popup_x, popup_y)
                else:
                    global_pos = wrapped.mapToGlobal(
                        QtCore.QPoint(0, widget_rect.height())
                    )
            else:
                button_rect = self._widget.rect()
                global_pos = self._widget.mapToGlobal(
                    QtCore.QPoint(button_rect.right(), button_rect.bottom())
                )
                global_pos.setX(global_pos.x() - self._popup.width())

            self._popup.move(self._clamp_to_screen(global_pos, window))

        self._popup.show()

    def _screen_for_window(self, window):
        """Return the QScreen the popup will appear on (best effort)."""
        if window is not None:
            handle = window.windowHandle()
            if handle is not None and handle.screen() is not None:
                return handle.screen()
            screen = QtGui.QGuiApplication.screenAt(window.mapToGlobal(window.rect().center()))
            if screen is not None:
                return screen
        return QtGui.QGuiApplication.primaryScreen()

    def _screen_width_cap(self, window):
        """Maximum popup width — a little less than the target screen's width."""
        screen = self._screen_for_window(window)
        if screen is None:
            return 16777215  # Qt's QWIDGETSIZE_MAX
        return max(150, screen.availableGeometry().width() - 32)

    def _clamp_to_screen(self, global_pos, window):
        """Keep the popup inside the screen's available geometry."""
        screen = self._screen_for_window(window)
        if screen is None:
            return global_pos
        geo = screen.availableGeometry()
        w = self._popup.width()
        h = self._popup.menu.sizeHint().height()
        x = max(geo.left() + 4, min(global_pos.x(), geo.right() - w - 4))
        y = max(geo.top() + 4, min(global_pos.y(), geo.bottom() - h - 4))
        return QtCore.QPoint(x, y)

    def _populate_popup(self):
        if not self._popup:
            return

        self._popup.clear()

        # The popup restores a *previously used* value, so the widget's current
        # value is intentionally excluded — re-selecting the value you already
        # have is a no-op. Dedup against history by the restore-data, not by the
        # (possibly friendly) display string.
        normalized_current = _normalize_value(self._current_widget_record())
        others = [
            v for v in self._store.values if _normalize_value(v) != normalized_current
        ]

        display_map = self._store.display_map(others)
        for v in others:
            self._popup.add_recent_value(v, display_text=display_map.get(v))

        if not others:
            self._popup.add_empty_message()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _restore_value(self, value):
        widget = self.wrapped_widget
        if isinstance(value, RecentValueEntry):
            set_value = getattr(widget, "set_value", None)
            if callable(set_value):
                set_value(value.data, display=value.display)
            else:
                self._set_widget_value(value.data)
        else:
            self._set_widget_value(value)
        self.value_selected.emit(value)

    # ------------------------------------------------------------------
    # Data-aware widget read
    # ------------------------------------------------------------------

    def _get_widget_data(self):
        """Return the wrapped widget's hidden data payload, or ``None``.

        Data-carrying widgets (e.g. ``uitk.LineEdit`` after ``set_value`` with
        a distinct display) expose ``data()`` returning the payload, or
        ``None`` when the text *is* the value.
        """
        widget = self.wrapped_widget
        getter = getattr(widget, "data", None)
        if callable(getter):
            try:
                return getter()
            except Exception:
                return None
        return None

    def _current_widget_record(self):
        """The value to store/compare for the widget's current state.

        Returns a :class:`RecentValueEntry` (display text + restore-data) when
        the widget carries a distinct data payload, otherwise the plain text.
        """
        display = self._get_widget_value()
        data = self._get_widget_data()
        if data is not None and _normalize_value(data) != _normalize_value(display):
            return RecentValueEntry(data, display=display)
        return display

    def _remove_value(self, value):
        self._store.remove(value)  # store notifies -> button tooltip updates
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

        If *value* is ``None`` the current widget value is used. When the
        wrapped widget carries a distinct data payload (see
        ``uitk.LineEdit.set_value``) the recorded entry keeps both the display
        text and the restore-data. Duplicates are moved to the front
        (most-recent-first order).
        """
        if value is None:
            value = self._current_widget_record()
        self._store.record(value)

    def add_recent_value(self, value):
        """Programmatically seed a recent value (appends if not duplicate)."""
        self._store.add(value)

    def set_wrapped_widget(self, widget):
        """Set or update the wrapped widget, re-installing auto-record if enabled."""
        super().set_wrapped_widget(widget)
        if self._auto_record and widget is not None and not self._auto_record_connected:
            self._install_auto_record(widget)

    def _install_auto_record(self, widget):
        """Wire up commit-time auto-recording for *widget*.

        Always prefers a true commit signal (``editingFinished`` or
        equivalent) over the live ``validated`` signal — recording on
        ``validated`` would still produce one entry per valid prefix as
        the user types (e.g. ``C:/Users``, ``C:/Users/foo``, ...).

        When the widget also exposes an ``is_valid`` property (e.g.
        ``uitk.LineEdit`` with a validator installed) the value is only
        recorded when it is not ``False``.  ``True`` and ``None`` (no
        validator set) both pass.

        Signals tried, in order:
            - ``editingFinished()`` (QLineEdit/QSpinBox/...)
            - ``activated(str)`` (QComboBox — fired on user selection)
        """
        if self._auto_record_connected:
            return

        editing_finished = getattr(widget, "editingFinished", None)
        if editing_finished is not None and hasattr(editing_finished, "connect"):
            editing_finished.connect(self._on_editing_finished_record)
            self._auto_record_connected = True
            return

        activated = getattr(widget, "activated", None)
        if activated is not None and hasattr(activated, "connect"):
            activated.connect(self._on_combo_activated_record)
            self._auto_record_connected = True
            return

    def _on_editing_finished_record(self):
        widget = self.wrapped_widget
        if widget is None:
            return
        # Flush any pending validator debounce so is_valid reflects current text
        validate_now = getattr(widget, "validate_now", None)
        if callable(validate_now):
            validate_now()
        if getattr(widget, "is_valid", None) is False:
            return
        self.record()

    def _on_combo_activated_record(self, *args):
        widget = self.wrapped_widget
        if widget is None:
            return
        # activated emits str in newer Qt, int in older; just use widget text
        text = widget.currentText() if hasattr(widget, "currentText") else None
        if text:
            self.record(text)

    @property
    def recent_values(self):
        """Return a copy of the recent values list (most-recent first)."""
        return self._store.values

    def clear_recent_values(self):
        """Clear all recent values."""
        self._store.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_button_tooltip(self, *_args):
        if self._widget is None:
            return
        n = len(self._store.values)
        if n:
            self._widget.setToolTip(f"Recent values ({n})")
        else:
            self._widget.setToolTip("Recent values")
