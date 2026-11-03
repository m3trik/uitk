# !/usr/bin/python
# coding=utf-8
"""Recent Values option for OptionBox — a value history with pins.

One presenter over one model (:class:`RecentValuesStore`) serves both
value-list plugins: :class:`RecentValuesOption` (the history, pins on top) and
``PinValuesOption`` (pins only) are this option configured two ways. The popup
lists

- **Pinned** -- values the user chose to keep, each optionally named, so a rule
  like ``{scene:_bar.*->}_v{n:03d}`` reads as a plain name (its raw text dimmed
  beside it) and still restores the rule itself;
- **Recent** -- the history, most recent first, minus the pins and the value
  already in the field;
- **Pin current value** -- while the field holds a value not pinned yet.

Captions name the sections only when both have rows. A row restores on click;
its pin toggles pinning, ✕ forgets a recent value and ✎ names a pin.
"""

from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk
from uitk.managers.value_manager import ValueManager
from uitk.themes.style_sheet import StyleSheet
from uitk.widgets.popup.dismissal import AncestorDismissal
from ._options import ButtonOption
from ._persistence import PersistedOption

# Canonical home for the storage/formatting logic is the widget-free
# RecentValuesStore; the value/display helpers are its staticmethods
# (e.g. ``RecentValuesStore.normalize_value`` / ``._entry_data`` /
# ``._is_filesystem_path`` / ``._build_display_map_smart_path``).
from uitk.managers.recent_values_store import RecentValuesStore, RecentValueEntry


class _ValueButton(QtWidgets.QPushButton):
    """A popup row's flat face: its text and an optional dim *detail*.

    The detail -- the raw value behind a pin's name -- is painted flush right
    in the text colour at reduced alpha, so it reads as secondary in any theme
    while the whole face stays one click target with one hover highlight. The
    style draws the face and the text (QSS hover colours and ``text-align``
    apply). When the face is narrower than both texts, the detail gives way
    first (down to a third of the face), then the text; both elide in the
    middle. ``text()`` is the row's text alone.
    """

    _GAP = 12
    _PAD = 6
    _DETAIL_ALPHA = 120
    #: The share of the face a squeezed detail keeps before the text elides.
    _DETAIL_MIN_SHARE = 3
    #: The narrowest a face will go: the popup may be capped below the width
    #: its longest value asks for, and the texts elide to fit.
    _MIN_WIDTH = 120

    def __init__(self, text, detail=None, parent=None):
        super().__init__(text, parent)
        self._detail = detail or ""
        self.setFlat(True)
        # No focus on press, as the icon buttons: taking it would commit an
        # open name editor, whose refresh rebuilds the rows before the release.
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def detail(self) -> str:
        """The dim text at the face's right edge (``""`` when none)."""
        return self._detail

    def _text_need(self, fm) -> int:
        """The width the text takes with its padding (what paint reserves)."""
        return fm.horizontalAdvance(self.text()) + 2 * self._PAD

    def sizeHint(self):
        hint = super().sizeHint()
        if self._detail:
            fm = self.fontMetrics()
            detail = fm.horizontalAdvance(self._detail)
            text = max(hint.width(), self._text_need(fm))
            hint.setWidth(text + self._GAP + detail + self._PAD)
        return hint

    def minimumSizeHint(self):
        hint = self.sizeHint()
        hint.setWidth(min(hint.width(), self._MIN_WIDTH))
        return hint

    def paintEvent(self, event):
        painter = QtWidgets.QStylePainter(self)
        opt = QtWidgets.QStyleOptionButton()
        self.initStyleOption(opt)
        painter.drawControl(QtWidgets.QStyle.CE_PushButtonBevel, opt)

        fm = self.fontMetrics()
        label_rect = QtCore.QRect(self.rect())
        if self._detail:
            # The name is what the user reads, so the detail yields first.
            detail_full = fm.horizontalAdvance(self._detail)
            spare = self.width() - self._text_need(fm) - self._GAP - self._PAD
            detail_w = max(
                min(detail_full, spare),
                min(detail_full, self.width() // self._DETAIL_MIN_SHARE),
            )
            detail_rect = QtCore.QRect(
                self.width() - self._PAD - detail_w, 0, detail_w, self.height()
            )
            label_rect.setRight(detail_rect.left() - self._GAP)
            color = QtGui.QColor(opt.palette.color(QtGui.QPalette.ButtonText))
            color.setAlpha(self._DETAIL_ALPHA)
            painter.setPen(color)
            painter.drawText(
                detail_rect,
                QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
                fm.elidedText(self._detail, QtCore.Qt.ElideMiddle, detail_w),
            )
        opt.rect = label_rect
        # A value is text, not a mnemonic: "R&D" must not paint as "RD".
        opt.text = fm.elidedText(
            self.text(),
            QtCore.Qt.ElideMiddle,
            max(0, label_rect.width() - 2 * self._PAD),
        ).replace("&", "&&")
        painter.drawControl(QtWidgets.QStyle.CE_PushButtonLabel, opt)


class _AliasEdit(QtWidgets.QLineEdit):
    """Inline editor naming a pin: Enter or leaving it commits, Escape cancels."""

    committed = QtCore.Signal(str)
    cancelled = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._open = False
        self.setObjectName("pinnedValueAliasEdit")
        self.editingFinished.connect(self._commit)

    def begin(self, text: str) -> None:
        self._open = True
        self.setText(text)
        self.selectAll()
        self.setFocus(QtCore.Qt.OtherFocusReason)

    def _commit(self):
        if self._open:
            self._open = False
            self.committed.emit(self.text())

    def event(self, event):
        # Claim Escape before a window shortcut closes the popup around us.
        if (
            self._open
            and event.type() == QtCore.QEvent.ShortcutOverride
            and event.key() == QtCore.Qt.Key_Escape
        ):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if self._open and event.key() == QtCore.Qt.Key_Escape:
            self._open = False
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class RecentValuesPopup(QtCore.QObject):
    """The value-list popup both faces share, built on :class:`Menu`.

    The option decides which rows exist -- :meth:`add_pinned_value`,
    :meth:`add_recent_value`, the :meth:`add_pin_current` footer -- and the
    popup draws them and reports gestures through :meth:`connect_signals`.

    Parameters:
        parent: The wrapped widget (theme inheritance and dismissal anchor).
        text_align: ``"center"`` (default), ``"left"`` or ``"right"``.
        pinning: Give recent rows a pin toggle. Pinned rows always have one:
            it is how a pin is removed.
    """

    #: A pin's name editor closed (committed, cancelled or cleared). Rows are
    #: rebuilt only between edits -- a rebuild deletes an open editor -- so
    #: the option refreshes on this.
    rename_closed = QtCore.Signal()

    _MAX_DISPLAY_LENGTH = 120
    #: Longest raw value shown beside a pin's name (the tooltip has it whole).
    _DETAIL_LENGTH = 60
    #: Side of every trailing icon slot, so the columns line up across rows.
    _ICON_BOX = 20

    def __init__(self, parent=None, text_align="center", pinning=False):
        super().__init__(parent)
        from uitk.widgets.menu import Menu

        self._parent_widget = parent
        self._text_align = text_align
        self._pinning = bool(pinning)
        self._editing = None  # the stack whose name editor is open

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

        # Close when an ancestor hides or the anchor's window moves.
        self._dismissal = AncestorDismissal(
            self._parent_widget,
            dismiss=lambda: self.close(),
            on_hide=True,
            parent=self,
        )

        self._on_value_selected = None
        self._on_value_removed = None
        self._on_value_pinned = None
        self._on_value_unpinned = None
        self._on_alias_changed = None

    @property
    def menu(self):
        """Get the underlying Menu widget."""
        return self._menu

    @property
    def editing(self) -> bool:
        """Whether a pin's name editor is open."""
        return self._editing is not None

    def connect_signals(
        self,
        on_value_selected=None,
        on_value_removed=None,
        on_value_pinned=None,
        on_value_unpinned=None,
        on_alias_changed=None,
    ):
        """Connect gesture handlers: each takes the row's value
        (``on_alias_changed`` also the typed name)."""
        self._on_value_selected = on_value_selected
        self._on_value_removed = on_value_removed
        self._on_value_pinned = on_value_pinned
        self._on_value_unpinned = on_value_unpinned
        self._on_alias_changed = on_alias_changed

    def clear(self):
        self._menu.clear()

    def show(self):
        self._menu.show()

    def close(self):
        self._dismissal.detach()
        self._menu.hide()

    def move(self, pos):
        self._menu.move(pos)

    def adjustSize(self):
        self._menu.adjustSize()

    def width(self):
        return self._menu.width()

    # ------------------------------------------------------------------
    # Rows
    # ------------------------------------------------------------------

    def add_section(self, title: str) -> None:
        """A captioned rule above a section's rows."""
        self._menu.add("Separator", setTitle=title)

    def add_separator(self) -> None:
        """A plain rule (above the footer)."""
        self._menu.add("Separator")

    def add_pinned_value(self, value, display_text=None, alias=None, current=False):
        """Add a pinned row.

        Args:
            value: The raw value to restore.
            display_text: The value as shown (``None``: truncated raw text).
            alias: The pin's name. When set it is the row's text and the
                value shows dimmed beside it.
            current: The field holds this value right now (shown bold).
        """
        display_text = self._display(value, display_text)
        if alias:
            text = alias
            detail = ptk.truncate(display_text, self._DETAIL_LENGTH, mode="middle")
        else:
            text, detail = display_text, None
        row = self._create_row(
            value, text, kind="pinned", detail=detail, alias=alias, current=current
        )
        self._menu.add(row)

    def add_recent_value(self, value, display_text=None):
        """Add a recent-value row.

        Args:
            value: The raw value to store/restore.
            display_text: Override text shown on the button.
                If ``None``, falls back to default truncation.
        """
        row = self._create_row(value, self._display(value, display_text), kind="recent")
        self._menu.add(row)

    def add_pin_current(self, value, display_text=None):
        """The footer action pinning the field's current value."""
        container, layout = self._row_container("pinCurrentValueRow")
        face = _ValueButton(
            "Pin current value",
            ptk.truncate(
                self._display(value, display_text), self._DETAIL_LENGTH, mode="middle"
            ),
        )
        face.setObjectName("pinCurrentValueButton")
        face.setToolTip(f"Pin {RecentValuesStore._entry_data(value)}")
        face.setStyleSheet(self._face_css())
        face.clicked.connect(lambda: self._on_pin_clicked(value))
        layout.addWidget(face, 1)
        layout.addWidget(self._pin_toggle(value, pinned=False))
        layout.addWidget(self._slot_placeholder())
        self._menu.add(container)

    def add_empty_message(self, text="No recent values"):
        label = QtWidgets.QLabel(text)
        label.setObjectName("recentValuesEmptyLabel")
        label.setAlignment(QtCore.Qt.AlignCenter)
        self._menu.add(label)

    def _display(self, value, display_text):
        if display_text is not None:
            return display_text
        return ptk.truncate(
            str(RecentValuesStore._entry_data(value)),
            self._MAX_DISPLAY_LENGTH,
            mode="middle",
        )

    def _face_css(self, bold=False) -> str:
        css = {
            "left": "text-align: left; padding-left: 4px;",
            "right": "text-align: right; padding-right: 4px;",
        }.get(self._text_align, "")
        return css + (" font-weight: bold;" if bold else "")

    @staticmethod
    def _row_container(object_name):
        container = QtWidgets.QWidget()
        container.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        container.setObjectName(object_name)
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(1, 0, 8, 0)
        layout.setSpacing(4)
        return container, layout

    def _create_row(self, value, text, kind, detail=None, alias=None, current=False):
        """One row: ``[face][pin][✎ | ✕]``.

        *kind* is ``"pinned"`` or ``"recent"``. A pinned row's face sits in a
        stack with its name editor; its pin unpins and ✎ names it. A recent
        row's pin (only when pinning) pins it and ✕ forgets it.
        """
        pinned = kind == "pinned"
        container, layout = self._row_container(f"{kind}ValueRow")
        full_text = str(RecentValuesStore._entry_data(value))

        face = _ValueButton(text, detail)
        face.setObjectName(f"{kind}ValueButton")
        face.setToolTip(full_text)
        face.setStyleSheet(self._face_css(bold=current))
        face.clicked.connect(lambda: self._on_value_clicked(value))

        stack = None
        if pinned:
            stack = QtWidgets.QStackedWidget()
            stack.addWidget(face)
            editor = _AliasEdit()
            editor.setPlaceholderText(full_text)
            editor.committed.connect(
                lambda name: self._finish_rename(stack, value, name)
            )
            editor.cancelled.connect(lambda: self._finish_rename(stack, value, None))
            stack.addWidget(editor)
            layout.addWidget(stack, 1)
        else:
            layout.addWidget(face, 1)

        face.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        face.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(face, pos, value, stack, alias)
        )

        if pinned or self._pinning:
            layout.addWidget(self._pin_toggle(value, pinned))
        if pinned:
            layout.addWidget(
                self._icon_button(
                    "pinnedValueRenameButton",
                    "edit",
                    "Rename (the value is kept)",
                    lambda: self._start_rename(stack, value, alias),
                    size=12,
                )
            )
        else:
            layout.addWidget(
                self._icon_button(
                    "recentValueRemoveButton",
                    "close",
                    "Remove from recent values",
                    lambda: self._on_remove_clicked(value),
                    size=10,
                )
            )
        return container

    def _pin_toggle(self, value, pinned):
        # The glyph carries the state (filled / hollow) in the theme colour,
        # as on the option button itself: a muted tint vanished on light themes.
        if pinned:
            return self._icon_button(
                "valuePinButton", "pin", "Unpin", lambda: self._on_unpin_clicked(value)
            )
        return self._icon_button(
            "valuePinButton", "pin_empty", "Pin", lambda: self._on_pin_clicked(value)
        )

    def _slot_placeholder(self):
        """An empty icon slot: a widget, not ``addSpacing``, so the layout
        spaces it like the buttons and the icon columns stay aligned."""
        placeholder = QtWidgets.QWidget()
        placeholder.setFixedSize(self._ICON_BOX, self._ICON_BOX)
        return placeholder

    def _icon_button(self, object_name, icon, tooltip, callback, size=14):
        from uitk.managers.icon_manager import IconManager

        button = QtWidgets.QPushButton()
        button.setObjectName(object_name)
        button.setFixedSize(self._ICON_BOX, self._ICON_BOX)
        button.setFlat(True)
        button.setFocusPolicy(QtCore.Qt.NoFocus)
        button.setCursor(QtCore.Qt.PointingHandCursor)
        IconManager.set_icon(button, icon, size=(size, size))
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        return button

    # ------------------------------------------------------------------
    # Rename
    # ------------------------------------------------------------------

    def _start_rename(self, stack, value, alias):
        # No hide-on-leave pause: Menu's leave poll already holds the popup
        # while a line edit inside it has focus.
        self._editing = stack
        stack.setCurrentIndex(1)
        stack.widget(1).begin(alias or str(RecentValuesStore._entry_data(value)))

    def _finish_rename(self, stack, value, name):
        """Close *stack*'s editor; *name* ``None`` means cancelled.

        Opening a second editor commits the first (it loses focus), so the
        one closing is not always the one open.
        """
        if stack is self._editing:
            self._editing = None
        try:
            stack.setCurrentIndex(0)
        except RuntimeError:  # the row went with a refresh
            pass
        if name is not None and self._on_alias_changed:
            self._on_alias_changed(value, name)
        self.rename_closed.emit()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, face, pos, value, stack, alias):
        menu = QtWidgets.QMenu(self._menu)
        StyleSheet.cast_shadow(menu)
        full_text = str(RecentValuesStore._entry_data(value))

        if stack is not None:
            menu.addAction("Rename…").triggered.connect(
                lambda: self._start_rename(stack, value, alias)
            )
            if alias:
                menu.addAction("Clear Name").triggered.connect(
                    lambda: self._finish_rename(stack, value, "")
                )
        elif self._pinning:
            menu.addAction("Pin").triggered.connect(lambda: self._on_pin_clicked(value))
        menu.addAction("Copy Value").triggered.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(full_text)
        )
        menu.addSeparator()
        if stack is not None:
            menu.addAction("Unpin").triggered.connect(
                lambda: self._on_unpin_clicked(value)
            )
        else:
            menu.addAction("Remove").triggered.connect(
                lambda: self._on_remove_clicked(value)
            )

        # Keep the popup open while its context menu is up: adopted into the
        # popup's hover family, the menu counts as "inside" for hide_on_leave.
        self._menu.adopt_transient(menu)
        menu.exec_(face.mapToGlobal(pos))
        # One-shot: don't linger as a hidden member of the hover family.
        try:
            menu.deleteLater()
        except RuntimeError:  # the popup closed under it, and was freed with it
            pass

    # ------------------------------------------------------------------
    # Gestures
    # ------------------------------------------------------------------

    def _on_value_clicked(self, value):
        if self._on_value_selected:
            self._on_value_selected(value)
        self.close()

    def _on_remove_clicked(self, value):
        if self._on_value_removed:
            self._on_value_removed(value)

    def _on_pin_clicked(self, value):
        if self._on_value_pinned:
            self._on_value_pinned(value)

    def _on_unpin_clicked(self, value):
        if self._on_value_unpinned:
            self._on_value_unpinned(value)


class _ValueListOption(ButtonOption):
    """The value-list button both faces configure: one popup over one store.

    :class:`RecentValuesOption` and ``PinValuesOption`` are siblings over this
    base, not parent and child, so ``find_option(RecentValuesOption)`` never
    answers with a field's pin button. A face declares its class attributes
    (storage app, glyph, names, empty text) and its defaults; everything else
    -- the popup, pinning, naming, recording -- is this one implementation.
    """

    value_selected = QtCore.Signal(object)
    """Emitted when the user clicks a value to restore it."""
    value_pinned = QtCore.Signal(bool, object)
    """Emitted ``(is_pinned, value)`` when a value is pinned or unpinned."""

    #: The face a subclass presents.
    SETTINGS_APP: str
    ICON: str
    TOOLTIP: str
    BUTTON_NAME: str
    BUTTON_CLASS: str
    EMPTY_TEXT: str

    # The clock glyph is constant; its *presence* is the affordance and its
    # brightness is the state. While nothing is stored the popup would only
    # show "No recent values", so the button is dimmed to the muted grey (the
    # "locked/inactive" tier) to read as nothing-to-open; a first record or pin
    # brightens it back to the theme color. An explicit color is *pinned* in
    # IconManager, so theme sweeps and the OptionBox size re-fit preserve it.
    _EMPTY_DIM: str = ptk.Palette.status()["locked"][0]  # "#888888"

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
        pinning=True,
        max_pinned=None,
    ):
        """Initialize the recent values option.

        Args:
            wrapped_widget: The widget whose values to track.
            settings_key: Key for persistent storage.  If provided,
                recent values and pins survive across sessions.
            max_recent: Maximum number of history entries to keep (pins
                excluded).
            display_format: Controls how values appear in the popup.
                ``"auto"`` — strip common directory prefix when all
                values are filesystem paths; otherwise truncate.
                ``"truncate"`` — always use simple start-truncation
                (previous default behaviour).
                ``"basename"`` — show only the last path component of a
                path (anything else shows whole).
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
                given it overrides *settings_key*/*max_recent*/*display_format*/
                *max_pinned* and lets several presenters (e.g. this popup and
                an ExpandableList) share one history.
            pinning: Offer to pin recent values and the current value
                (default). ``False`` shows a plain history, as before pins.
            max_pinned: Maximum number of pins (``None``: unlimited).
        """
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon=self.ICON,
            tooltip=self.TOOLTIP,
            callback=self._show_popup,
            checkable=True,
        )
        self._popup_align = popup_align
        self._text_align = text_align
        self._pinning = bool(pinning)
        self._popup = None
        self._auto_record = bool(auto_record)
        self._auto_record_connected = False

        # Storage, persistence and display-formatting live in the shared,
        # widget-free store; this option is just a presenter over it. The
        # SettingsManager is built HERE rather than inside the store, through the
        # same factory the other persisted options use: host namespacing needs the
        # wrapped widget (to reach its Switchboard's ``context_tags``) and the
        # store is deliberately widget-free. An injected *store* is left alone —
        # it is a caller-owned model, and its namespace is the caller's business.
        self._store = store or RecentValuesStore(
            settings_key=settings_key,
            max_recent=max_recent,
            display_format=display_format,
            settings=PersistedOption.settings_for(
                self.SETTINGS_APP, settings_key, wrapped_widget
            ),
            max_pinned=max_pinned,
        )
        self._store.subscribe(self._update_button_visuals)

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
            button.setObjectName(self.BUTTON_NAME)
        button.setProperty("class", self.BUTTON_CLASS)
        # Initial tooltip + glyph SYNCHRONOUSLY: a deferred (singleShot) update
        # lands on the tick after first paint and flickers the glyph. _widget
        # must be assigned first — this runs inside BaseOption.widget's lazy
        # create (which assigns _widget only on return), and
        # _update_button_visuals no-ops while _widget is None.
        self._widget = button
        self._update_button_visuals()
        return button

    # ------------------------------------------------------------------
    # Popup
    # ------------------------------------------------------------------

    def _on_popup_hidden(self):
        popup, self._popup = self._popup, None
        if popup is not None:
            # Each open builds a fresh popup parented to the field, so a hidden
            # one is freed. Deferred: a name editor's focus-out commit, which
            # the hide sets off, still runs against live rows.
            popup.menu.deleteLater()
            popup.deleteLater()
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
            parent=self.wrapped_widget,
            text_align=self._text_align,
            pinning=self._pinning,
        )
        self._popup.menu.on_hidden.connect(self._on_popup_hidden)
        self._popup.rename_closed.connect(self._refresh_soon)
        self._popup.connect_signals(
            on_value_selected=self._restore_value,
            on_value_removed=self._remove_value,
            on_value_pinned=self._pin_value,
            on_value_unpinned=self._unpin_value,
            on_alias_changed=self._rename_value,
        )

        self._populate_popup()
        self._place_popup()
        self._popup.show()

    def _place_popup(self):
        """Size the popup to its rows and anchor it under the wrapped widget.

        Re-run after every in-place refresh, so a right-aligned popup keeps
        its right edge as rows come and go.
        """
        # Let the menu size to its natural sizeHint, clamped to the screen so
        # it can't run off-screen for very long values.
        window = self._find_parent_window()
        self._popup.menu.setMaximumWidth(self._screen_width_cap(window))
        self._popup.adjustSize()

        if not self._widget:
            return
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
                global_pos = wrapped.mapToGlobal(QtCore.QPoint(0, widget_rect.height()))
        else:
            button_rect = self._widget.rect()
            global_pos = self._widget.mapToGlobal(
                QtCore.QPoint(button_rect.right(), button_rect.bottom())
            )
            global_pos.setX(global_pos.x() - self._popup.width())

        self._popup.move(self._clamp_to_screen(global_pos, window))

    def _screen_for_window(self, window):
        """Return the QScreen the popup will appear on (best effort)."""
        if window is not None:
            handle = window.windowHandle()
            if handle is not None and handle.screen() is not None:
                return handle.screen()
            screen = QtGui.QGuiApplication.screenAt(
                window.mapToGlobal(window.rect().center())
            )
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

        popup = self._popup
        store = self._store
        popup.clear()

        current = self._current_widget_record()
        normalized_current = RecentValuesStore.normalize_value(current)

        # Pins read by name: alphabetical by what the row shows.
        pins = store.pinned_entries
        pin_text = store.display_map([e.value for e in pins])
        pins.sort(key=lambda e: (e.alias or pin_text[e.value]).lower())

        # The history restores a *previously used* value, so it leaves out the
        # widget's current value — re-selecting the value you already have is
        # a no-op — and the pins, listed above. Dedup is by restore-data, not
        # by the (possibly friendly) display string.
        recent = [
            v
            for v in store.values
            if not store.is_pinned(v)
            and RecentValuesStore.normalize_value(v) != normalized_current
        ]
        recent_text = store.display_map(recent)

        captions = bool(pins) and bool(recent)
        if captions:
            popup.add_section("Pinned")
        for e in pins:
            popup.add_pinned_value(
                e.value,
                pin_text[e.value],
                alias=e.alias,
                current=RecentValuesStore.normalize_value(e.value)
                == normalized_current,
            )
        if captions:
            popup.add_section("Recent")
        for v in recent:
            popup.add_recent_value(v, display_text=recent_text.get(v))

        if not pins and not recent:
            popup.add_empty_message(self.EMPTY_TEXT)

        if (
            self._pinning
            and not RecentValuesStore._is_blank(current)
            and not store.is_pinned(current)
        ):
            popup.add_separator()
            popup.add_pin_current(current, store.display_map([current])[current])

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

    def _pin_value(self, value):
        if self._store.pin(value):
            self.value_pinned.emit(True, value)
        self._refresh_soon()

    def _unpin_value(self, value):
        if self._store.unpin(value):
            self.value_pinned.emit(False, value)
        self._refresh_soon()

    def _rename_value(self, value, alias):
        # The popup's rename_closed, right after this, refreshes the rows.
        self._store.set_alias(value, alias)

    def _remove_value(self, value):
        self._store.remove(value)  # store notifies -> button tooltip updates
        self._refresh_soon()

    def _refresh_soon(self):
        # After the click that asked for it: the clicked button lives in a
        # row the refresh destroys.
        QtCore.QTimer.singleShot(0, self._refresh_popup_deferred)

    def _refresh_popup_deferred(self):
        # Never under an open name editor: the rebuild would delete it. The
        # editor's close (rename_closed) asks again.
        if self._popup and self._popup.menu.isVisible() and not self._popup.editing:
            self._populate_popup()
            self._place_popup()

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
        if data is not None and RecentValuesStore.normalize_value(
            data
        ) != RecentValuesStore.normalize_value(display):
            return RecentValueEntry(data, display=display)
        return display

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

    def add_pinned_value(self, value, alias=None):
        """Programmatically pin *value*, optionally named; a pin stays as is.

        Args:
            value: The value to pin.
            alias: Optional name the popup shows for it.
        """
        if self._store.pin(value, alias):
            self.value_pinned.emit(True, value)

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
        text = (
            ValueManager.combo_value(widget, "text")
            if hasattr(widget, "currentText")
            else None
        )
        if text:
            self.record(text)

    @property
    def recent_values(self):
        """Return a copy of the recent values list (most-recent first)."""
        return self._store.values

    def clear_recent_values(self):
        """Clear all recent values (pins stay)."""
        self._store.clear()

    @property
    def pinned_values(self):
        """The pinned values (raw values, newest pin first)."""
        return self._store.pinned

    @property
    def pinned_entries(self):
        """The pins as :class:`PinnedValueEntry` objects (value + alias)."""
        return self._store.pinned_entries

    @property
    def has_pinned_values(self):
        """Whether anything is pinned."""
        return bool(self._store.pinned)

    def clear_pinned_values(self):
        """Unpin everything (the history is untouched)."""
        self._store.clear_pinned()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_button_visuals(self, *_args):
        """Sync tooltip and icon tint to the store (subscribed to it).

        Store notifications re-run this on every record/pin/remove;
        ``_swap_state_icon`` skips the rasterize when the tint is already
        correct.
        """
        if self._widget is None:
            return
        store = self._store
        pins = len(store.pinned)
        recent = sum(1 for v in store.values if not store.is_pinned(v))
        if recent or pins:
            tooltip = self.TOOLTIP + (f" ({recent})" if recent else "")
            self._widget.setToolTip(tooltip + (f" · {pins} pinned" if pins else ""))
        else:
            self._widget.setToolTip(self.EMPTY_TEXT)
        # Dimmed while empty (nothing to open), theme color once values exist.
        self._swap_state_icon(self.icon, None if recent or pins else self._EMPTY_DIM)


class RecentValuesOption(_ValueListOption):
    """A history button: the field's recent values, with pins on top.

    Clicking the button shows the popup (see the module docstring): pinned
    values first, then the history, then a footer to pin the field's current
    value. The history fills when ``record()`` is called (typically after a
    successful action like export) or on commit with ``auto_record``; values
    can also be seeded with ``add_recent_value()`` / ``add_pinned_value()``.

    Pins are for the values worth keeping -- a naming rule, a project root --
    and can be named, so ``{scene:_bar.*->}_v{n:03d}`` reads as "Strip _bar,
    versioned". A pin never ages out of the history and takes none of its
    slots. ``pinning=False`` shows the plain history.

    Example::

        line_edit = QtWidgets.QLineEdit()
        recent = RecentValuesOption(line_edit, settings_key="my_recent")
        option_box = OptionBox(options=[recent])
        option_box.wrap(line_edit)

        # After user action:
        recent.record()  # saves current widget value
    """

    SETTINGS_APP = "RecentValues"
    ICON = "clock"
    TOOLTIP = "Recent values"
    BUTTON_NAME = "recentButton"
    BUTTON_CLASS = "RecentButton"
    EMPTY_TEXT = "No recent values"
