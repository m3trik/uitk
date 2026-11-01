# !/usr/bin/python
# coding=utf-8
"""A combo's persistent actions -- parts of
:class:`~uitk.widgets.widgetComboBox.WidgetComboBox` (see
``widget_combo_box_parts``): the public ``actions`` namespace, and the section
it renders below the rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy import QtCore, QtWidgets

from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

if TYPE_CHECKING:
    from uitk.widgets.widgetComboBox import WidgetComboBox


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

        # After editing an action in place (an icon, its text):
        action.setIcon(icon)
        combo.actions.refresh()
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

    def refresh(self) -> None:
        """Re-render the section from the actions as they are now.

        ``add`` renders each action's text, icon and tooltip once; an edit made
        to an action afterwards (icons set on the returned actions) shows after
        this. Its enabled state needs no refresh: each button follows it live.
        """
        self._combo._rebuild_actions_section()

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


class _ActionsSection:
    """A :class:`WidgetComboBox`'s persistent actions section: the optional
    separator and the button grid pinned below the rows, built from
    :attr:`WidgetComboBox.actions`.

    Owns its layout settings, how many tail rows it occupies, and the
    action→button enabled-state bindings of its current build; holds the combo
    and adds its rows through it.
    """

    # Square size (px) of an icon-only action button.
    ICON_BUTTON_SIZE = 24

    def __init__(self, combo: "WidgetComboBox") -> None:
        self._combo = combo
        self.row_count: int = 0
        # Action buttons are laid out in this many columns, filled row-major.
        # Default 1 = a single vertical stack (back-compat).
        self.columns: int = 1
        # When True, action buttons show only their icon (no text) and render as
        # compact square buttons — a toolbar-style row. Default False (text).
        self.icon_only: bool = False
        # Whether to draw the separator above the actions section. Default True.
        self.show_separator: bool = True
        # (action, slot) pairs binding each action's ``changed`` signal to its
        # button's enabled state. Tracked so ``strip`` can disconnect them and
        # not accumulate dangling connections to deleted buttons across
        # rebuilds.
        self.button_conns: list = []

    def set_columns(self, value: int) -> None:
        value = max(1, int(value))
        if value != self.columns:
            self.columns = value
            self._combo._rebuild_actions_section()

    def set_icon_only(self, value: bool) -> None:
        value = bool(value)
        if value != self.icon_only:
            self.icon_only = value
            self._combo._rebuild_actions_section()

    def set_show_separator(self, value: bool) -> None:
        value = bool(value)
        if value != self.show_separator:
            self.show_separator = value
            self._combo._rebuild_actions_section()

    def reset(self) -> None:
        """Forget the section: the combo's ``clear`` takes its rows."""
        self.disconnect_buttons()
        self.row_count = 0

    def disconnect_buttons(self) -> None:
        """Drop the action.changed→button bindings from the last rebuild."""
        for action, slot in self.button_conns:
            try:
                action.changed.disconnect(slot)
            except (RuntimeError, TypeError):
                pass  # action deleted or already disconnected
        self.button_conns.clear()

    def bind_button(
        self, btn: QtWidgets.QPushButton, action: QtWidgets.QAction
    ) -> None:
        """Mirror *action*'s enabled state onto *btn*, now and on change.

        Lets a caller ``action.setEnabled(False)`` to grey out the matching
        button (e.g. disabling Rename/Delete for a read-only built-in preset)
        without reaching into the popup's internal button widgets.
        """
        btn.setEnabled(action.isEnabled())

        def _sync():
            try:
                btn.setEnabled(action.isEnabled())
            except RuntimeError:
                pass  # button deleted

        action.changed.connect(_sync)
        self.button_conns.append((action, _sync))

    def strip(self) -> None:
        """Remove existing action rows (separator + buttons) from the bottom."""
        self.disconnect_buttons()
        if self.row_count == 0:
            return

        combo = self._combo
        total = combo._model.rowCount()
        for row in range(total - 1, total - self.row_count - 1, -1):
            if row < 0:
                break
            container = combo._row_containers.pop(row, None)
            combo._widget_items.pop(row, None)
            if container is not None:
                container.deleteLater()
            combo._model.removeRow(row)

        remaining = combo._model.rowCount()
        combo._pending_index_widgets = [
            (r, c) for r, c in combo._pending_index_widgets if r < remaining
        ]
        self.row_count = 0

    def rebuild(self) -> None:
        """Rebuild the (optional separator +) action buttons at the bottom.

        Buttons are grouped inside a single container widget (zero margins)
        added as one model row. They are arranged in
        :attr:`WidgetComboBox.action_columns` columns, filled row-major, so e.g.
        four actions with ``action_columns == 2`` form a tidy 2x2 grid (or a
        single row when ``action_columns`` equals the action count). When
        :attr:`WidgetComboBox.action_icon_only` is set the buttons are compact,
        icon-only squares (text → tooltip) for a toolbar-style row; otherwise
        they show a centered icon + text and expand to fill. The separator
        above the section is drawn unless
        :attr:`WidgetComboBox.show_action_separator` is False. Each button
        mirrors its QAction's enabled state via :meth:`bind_button`.
        """
        combo = self._combo
        combo._strip_actions_section()
        actions = combo.actions
        if not actions:
            return

        row_count = 0
        icon_only = self.icon_only

        if self.show_separator:
            from uitk.widgets.separator import Separator

            # Default Separator HLine is too subtle against the popup background —
            # strengthen it with a palette-aware border-top so the actions section
            # reads as a distinct group from the items above.  Uses palette(text)
            # so it stays visible on dark themes where palette(mid) blends in.
            sep = Separator()
            sep.setFrameShape(QtWidgets.QFrame.NoFrame)
            sep.setFixedHeight(7)
            sep.setStyleSheet(
                "QFrame {"
                " background: transparent;"
                " border: none;"
                " border-top: 1px solid palette(text);"
                " margin: 3px 6px;"
                "}"
            )
            sep_row = combo._add_widget_item(
                sep, "", None, ascending=False, track_height=False
            )
            # A NoFrame/HLine separator advertises an invalid sizeHint height, so
            # _apply_uniform_height can't size its row and the view falls back to
            # the delegate's font-based default — taller than the 7px line, which
            # renders as dead space above and below it (and between the separator
            # and the buttons). Pin the row to the separator's own fixed height.
            sep_item = combo._model.item(sep_row)
            if sep_item is not None:
                sep_item.setSizeHint(QtCore.QSize(0, sep.minimumHeight()))
            row_count += 1

        # Build a single container holding all action buttons in a grid.
        ncols = max(1, self.columns)
        container = QtWidgets.QWidget(combo.view())
        layout = QtWidgets.QGridLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(2)
        layout.setVerticalSpacing(1)

        max_btn_width = 0
        for i, action in enumerate(actions):
            btn = QtWidgets.QPushButton(container)
            if action.icon() and not action.icon().isNull():
                btn.setIcon(action.icon())
            # Text becomes the tooltip in icon-only mode so the action is still
            # discoverable without a visible label; the accessible name keeps it
            # identifiable to screen readers (and tests) in both modes.
            btn.setToolTip(action.toolTip() or action.text())
            TooltipPresenter.manage(btn)
            btn.setAccessibleName(action.text())
            if icon_only:
                side = self.ICON_BUTTON_SIZE
                btn.setIconSize(QtCore.QSize(side - 8, side - 8))
                btn.setFixedSize(QtCore.QSize(side, side))
            else:
                btn.setText(action.text())
                btn.setSizePolicy(
                    QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
                )
                btn.setStyleSheet("text-align: center;")
            btn.setDefault(False)
            btn.setAutoDefault(False)
            btn.setProperty("class", "combobox-action")
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.clicked.connect(action.trigger)
            btn.clicked.connect(combo.hidePopup)
            self.bind_button(btn, action)
            layout.addWidget(btn, i // ncols, i % ncols)
            # Track widest button via sizeHint (reliable for QPushButton).
            w = btn.sizeHint().width()
            if w > max_btn_width:
                max_btn_width = w

        # Equal-width columns so the grid reads as aligned pairs (and so
        # compact icon buttons distribute evenly across the row).
        for c in range(ncols):
            layout.setColumnStretch(c, 1)

        # Force the container to adopt a valid size before it's embedded.
        container.setMinimumWidth(
            max_btn_width * ncols + layout.horizontalSpacing() * (ncols - 1)
        )
        container.adjustSize()

        row = combo._add_widget_item(
            container, "", None, ascending=False, track_height=False
        )
        item = combo._model.item(row)
        if item:
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)
        row_count += 1

        self.row_count = row_count
