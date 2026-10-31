# !/usr/bin/python
# coding=utf-8
"""What the menu holds: adding, finding and removing items.

``add`` / ``add_row`` build and place widgets in the item grid (one full-width
row each unless told otherwise), expose each as ``menu.<objectName>`` and queue
its registration with the owning window; the lookups (``get_items``,
``get_item``...) read the grid back. Also here: the transient "No options"
placeholder a menu shows when opened empty, and the filter that hides items
whose action already has a keyboard shortcut.

One part of :class:`~uitk.widgets.menu.Menu` (see ``menu_parts``).
"""

import inspect
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Union

from qtpy import QtCore, QtWidgets

from uitk.managers.shortcut_manager import ShortcutManager
from uitk.widgets._layout_items import _LayoutItems
from uitk.widgets.separator import Separator

if TYPE_CHECKING:
    from uitk.widgets.menu import Menu

# Widget type cache for faster widget creation
_WIDGET_TYPE_CACHE: Dict[str, type] = {
    "QPushButton": QtWidgets.QPushButton,
    "QLabel": QtWidgets.QLabel,
    "QCheckBox": QtWidgets.QCheckBox,
    "QRadioButton": QtWidgets.QRadioButton,
    "QLineEdit": QtWidgets.QLineEdit,
    "QTextEdit": QtWidgets.QTextEdit,
    "QSpinBox": QtWidgets.QSpinBox,
    "QDoubleSpinBox": QtWidgets.QDoubleSpinBox,
    "QSlider": QtWidgets.QSlider,
    "Separator": Separator,
    "QSeparator": Separator,  # Alias for consistency with Qt naming
}

# Names whose target class would create an import cycle at module load
# (e.g. ComboBox transitively imports this module via MenuMixin). Resolved
# and cached on first use by _MenuItems.resolve_widget_class.
_LAZY_WIDGET_TYPES: Dict[str, Tuple[str, str]] = {
    "QComboBox": ("uitk.widgets.comboBox", "ComboBox"),
}


# Widget types that should have item height constraints applied
# (includes derived classes via isinstance check)
# Note: QTextEdit is intentionally excluded as it's multi-line and needs variable height
_HEIGHT_CONSTRAINED_TYPES = (
    QtWidgets.QPushButton,
    QtWidgets.QLabel,
    QtWidgets.QCheckBox,
    QtWidgets.QRadioButton,
    QtWidgets.QComboBox,
    QtWidgets.QLineEdit,
    QtWidgets.QSpinBox,
    QtWidgets.QDoubleSpinBox,
    QtWidgets.QSlider,
)


class _MenuItems:
    """What a :class:`Menu` holds: adding, finding and removing items.

    Owns the bulk-add bookkeeping (the ``on_item_added`` queue and the add
    depth), the empty-state placeholder and its timer, and the items the
    shortcut filter hid. The item data (``widget_data``) and the grid
    (``gridLayout``) stay public attributes of the menu it holds; every hook a
    subclass may override (``add``, ``_shortcut_filter_candidates``,
    ``_shortcut_filter_emptied``) is called through the menu.
    """

    def __init__(
        self, menu: "Menu", empty_message: Optional[str], empty_timeout_ms: int
    ) -> None:
        self._menu = menu
        # ``add()`` blocks signals for the duration of the (potentially
        # recursive, bulk) insert so Qt's internal layout churn doesn't
        # cascade.  ``on_item_added`` emits land in this queue while blocked
        # and are flushed once the OUTERMOST add() unwinds (tracked by
        # ``add_depth``) and the menu is settled — otherwise the documented
        # signal never reaches listeners.
        self.pending_item_added_emits: list = []
        self.add_depth: int = 0
        # Empty-state behavior: when shown with no items, display a brief
        # message ("No options" by default) then auto-hide.  An
        # ``empty_message`` of None or an ``empty_timeout_ms`` of 0 disables it.
        self.empty_message = empty_message
        self.empty_timeout_ms = max(0, int(empty_timeout_ms))
        self.empty_placeholder: Optional[QtWidgets.QLabel] = None
        self.empty_timer: Optional[QtCore.QTimer] = None
        # Items this menu hid because their action already has a shortcut —
        # tracked so only those are restored when the preference goes off.
        self.shortcut_hidden_items: list = []

    @staticmethod
    def resolve_widget_class(name: str):
        cls = _WIDGET_TYPE_CACHE.get(name)
        if cls is not None:
            return cls
        spec = _LAZY_WIDGET_TYPES.get(name)
        if spec is None:
            return None
        import importlib

        cls = getattr(importlib.import_module(spec[0]), spec[1])
        _WIDGET_TYPE_CACHE[name] = cls
        return cls

    def contains_items(self) -> bool:
        grid = self._menu.gridLayout
        # Handle lazy initialization - gridLayout may not exist yet
        if grid is None:
            return False
        count = grid.count()
        if self.empty_placeholder is not None:
            count -= 1
        return count > 0

    # ------------------------------------------------------------------
    # The empty state
    # ------------------------------------------------------------------

    def start_empty_state(self) -> None:
        """Show the placeholder and arm its auto-hide (a show with no items)."""
        self.add_empty_placeholder()
        if self.empty_timeout_ms > 0:
            if self.empty_timer is None:
                # Its timeout reaches the menu's slot, so the connection dies
                # with the menu (the timer is the menu's child anyway).
                self.empty_timer = QtCore.QTimer(self._menu)
                self.empty_timer.setSingleShot(True)
                self.empty_timer.timeout.connect(self._menu._on_empty_timeout)
            self.empty_timer.start(self.empty_timeout_ms)

    def end_empty_state(self) -> None:
        """Stop the auto-hide and drop the placeholder (a hide, a real item)."""
        if self.empty_timer is not None:
            self.empty_timer.stop()
        self.remove_empty_placeholder()

    def add_empty_placeholder(self) -> None:
        """Insert the transient "No options" message when shown with no items."""
        grid = self._menu.gridLayout
        if self.empty_placeholder is not None or not self.empty_message:
            return
        if grid is None:
            return
        label = QtWidgets.QLabel(self.empty_message)
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setObjectName("menuEmptyMessage")
        label.setProperty("class", "menuEmptyMessage")
        if self._menu.min_item_height:
            label.setMinimumHeight(self._menu.min_item_height)
        # Bypass add() — this widget is purely informational and must not
        # be counted by contains_items, registered with the main window,
        # or get the usual item event-filter treatment.
        grid.addWidget(label, 0, 0, 1, max(1, grid.columnCount()))
        self.empty_placeholder = label

    def remove_empty_placeholder(self) -> None:
        """Tear down the empty placeholder if present."""
        label = self.empty_placeholder
        self.empty_placeholder = None
        if label is None:
            return
        grid = self._menu.gridLayout
        if grid is not None:
            grid.removeWidget(label)
        label.setParent(None)
        label.deleteLater()

    def on_empty_timeout(self) -> None:
        """Hide the menu when the empty-state timer fires (unless items arrived)."""
        if self.empty_placeholder is None:
            return  # Real items appeared while shown — leave the menu open.
        if self._menu.isVisible():
            self._menu.hide()

    # ------------------------------------------------------------------
    # The shortcut-bound item filter
    # ------------------------------------------------------------------

    def item_has_shortcut(self, item) -> bool:
        """Whether *item*'s action currently holds a keyboard shortcut.

        An item is matched to a command by objectName through the Switchboard
        its UI belongs to (``register_widget`` gives every registered item its
        ``ui``).  Anything unregistered — a plain label row, a menu built
        outside a UI — has no command identity and so never matches.
        """
        name = item.objectName()
        sb = getattr(getattr(item, "ui", None), "sb", None)
        if not name or sb is None:
            return False
        try:
            return bool(sb.widget_has_shortcut(item))
        except Exception as e:  # a menu must open whatever the registry does
            self._menu.logger.debug(f"[_item_has_shortcut] {name}: {e}")
            return False

    def apply_shortcut_item_filter(self) -> None:
        """Hide items whose action already has a shortcut, when asked to.

        Driven by the global ``ShortcutManager.hide_bound_menu_items()``
        preference (the shortcut editor's toggle): a menu exists to reach an
        action, so once the action is on a key its row is clutter to the users
        who turn this on.  Re-read on every show — flipping the preference off
        restores exactly the items this hid, leaving rows hidden for any other
        reason alone.
        """
        restored, self.shortcut_hidden_items = self.shortcut_hidden_items, []
        for item in restored:
            try:
                item.setVisible(True)
            except RuntimeError:  # deleted between shows
                pass

        if not ShortcutManager.hide_bound_menu_items():
            return

        menu = self._menu
        candidates = menu._shortcut_filter_candidates()
        for item in candidates:
            if item.isHidden() or not self.item_has_shortcut(item):
                continue
            item.setVisible(False)
            self.shortcut_hidden_items.append(item)

        # Filtering everything away would otherwise open a bare empty popup.
        if self.shortcut_hidden_items and all(item.isHidden() for item in candidates):
            menu._shortcut_filter_emptied()

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def get_items(self, types=None):
        items = _LayoutItems.widgets(self._menu.gridLayout)

        if types is not None:
            # Ensure types is a list for easier processing
            if not isinstance(types, (list, tuple)):
                types = [types]

            # Convert string type names to actual types
            processed_types = []
            for type_item in types:
                if isinstance(type_item, str):
                    widget_type = getattr(QtWidgets, type_item, None)
                    if widget_type is not None:
                        processed_types.append(widget_type)
                    else:
                        # A name is resolved against QtWidgets, so a uitk class name
                        # ("CheckBox") or a typo resolves to nothing — and dropping
                        # it silently leaves an EMPTY processed_types, which filters
                        # every item out. That reads as "the menu holds none of
                        # those" rather than "you asked for a type that isn't one".
                        # Caught in the field: a tb004 whose state was read from
                        # get_items("CheckBox") was False no matter what the boxes
                        # said, so its label could never say ON.
                        self._menu.logger.warning(
                            f"[get_items] {type_item!r} is not a QtWidgets class; "
                            f"nothing can match it (pass the class itself, or the "
                            f"Q-prefixed base name)."
                        )
                else:
                    processed_types.append(type_item)

            items = [  # Filter items by type
                item
                for item in items
                if any(isinstance(item, t) for t in processed_types)
            ]

        return items

    def get_item(self, identifier):
        menu = self._menu
        items = menu.get_items()

        if isinstance(identifier, int):  # get by index
            if identifier < 0 or identifier >= len(items):
                raise ValueError("Index out of range.")
            item = items[identifier]
        elif isinstance(identifier, str):  # get by text
            for i in items:
                # Resolve each item's label via the guarded helper — not every
                # item type exposes text() (combos use currentText(), spin boxes
                # value(), etc.), so a bare i.text() would AttributeError.
                if menu.get_item_text(i) == identifier:
                    item = i
                    break
            else:
                raise ValueError("No item found with the given text.")
        else:
            raise ValueError(
                f"Expected an integer (index) or string (text), got '{type(identifier)}'"
            )

        return item

    @staticmethod
    def get_item_text(widget: QtWidgets.QWidget) -> Optional[str]:
        # Try text() method (most common for QLabel, QPushButton, etc.)
        if hasattr(widget, "text") and callable(widget.text):
            return widget.text()

        # Try currentText() for combo boxes
        if hasattr(widget, "currentText") and callable(widget.currentText):
            return widget.currentText()

        # Try value() for spin boxes
        if hasattr(widget, "value") and callable(widget.value):
            return str(widget.value())

        # Try placeholderText for line edits as fallback
        if hasattr(widget, "placeholderText") and callable(widget.placeholderText):
            return widget.placeholderText()

        return None

    # ------------------------------------------------------------------
    # Removing
    # ------------------------------------------------------------------

    def remove_widget(self, widget):
        menu = self._menu
        menu.logger.debug(
            f"Menu.remove_widget: Removing widget={widget.objectName() or type(widget).__name__}"
        )
        self.remove_item_event_filter(widget)
        menu.gridLayout.removeWidget(widget)
        if widget in menu.widget_data:
            del menu.widget_data[widget]

        # Uninstall event filters if menu is now empty
        if not menu.contains_items:
            menu._uninstall_event_filters()
            menu.logger.debug(
                "Menu.remove_widget: Menu now empty, event filters uninstalled"
            )

    def remove_item_event_filter(self, widget) -> None:
        """Undo the ``installEventFilter`` :meth:`add` puts on every item.

        The counterpart that was missing. Tolerates a widget whose C++ object
        has already gone: the point is that the menu stops filtering it, and a
        wrapper that raises has no filter list left to clean anyway.
        """
        try:
            widget.removeEventFilter(self._menu)
        except (RuntimeError, AttributeError):
            pass

    def clear(self) -> None:
        menu = self._menu
        grid = menu.gridLayout
        if grid is None:
            return

        # Tear down any transient empty-state placeholder first, while its
        # C++ object is still alive (before the reverse-delete loop's
        # deleteLater is processed). This mirrors add()'s teardown so the
        # placeholder can't dangle: leaving it set would (1) make the next
        # empty show no-op and (2) let the empty timer fire on_empty_timeout
        # -> hide() -> remove_empty_placeholder() on an already-destroyed
        # label, raising RuntimeError from the timer.
        if self.empty_placeholder is not None:
            self.end_empty_state()

        item_count = grid.count()
        menu.logger.debug(f"Menu.clear: Clearing {item_count} items")

        # Last item first.
        for widget in reversed(_LayoutItems.widgets(grid)):
            self.remove_item_event_filter(widget)
            grid.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()

        # Reset the widget_data dictionary
        menu.widget_data = {}

        # Uninstall event filters since menu is now empty
        menu._uninstall_event_filters()
        menu.logger.debug("Menu.clear: All items cleared, event filters uninstalled")

    # ------------------------------------------------------------------
    # Adding
    # ------------------------------------------------------------------

    def add(
        self,
        x: Union[str, QtWidgets.QWidget, type, dict, list, tuple, set, zip, map],
        data: Any = None,
        row: Optional[int] = None,
        col: int = 0,
        rowSpan: int = 1,
        colSpan: Optional[int] = None,
        **kwargs,
    ) -> Union[QtWidgets.QWidget, list]:
        menu = self._menu
        # CRITICAL OPTIMIZATION: Disable updates AND layout recalculation during add
        # This prevents Qt from recalculating layout/geometry on every operation
        updates_were_enabled = menu.updatesEnabled()
        menu.setUpdatesEnabled(False)

        # Block signals to prevent cascading updates
        was_blocked = menu.blockSignals(True)

        # If a transient empty-state placeholder is on screen, drop it now —
        # a real item is arriving and should take its place without leaving
        # the "No options" label behind.
        if self.empty_placeholder is not None:
            self.end_empty_state()

        # Suspend layout activation if layout exists
        layout_was_enabled = False
        if menu.gridLayout:
            layout_was_enabled = menu.gridLayout.isEnabled()
            menu.gridLayout.setEnabled(False)

        try:
            # Track recursion so the outermost call (depth back to 0) owns the
            # on_item_added flush, regardless of whether signals were already
            # blocked on entry (collection adds recurse with signals blocked).
            self.add_depth += 1

            # Lazy initialization: create layout on first item add
            menu._ensure_layout_created()

            # A collection recurses through the menu, so an override of
            # ``add`` (ContextMenu's) sees every member.
            if isinstance(x, dict):
                return [menu.add(key, data=val, **kwargs) for key, val in x.items()]

            elif isinstance(x, (list, tuple, set)):
                return [menu.add(item, **kwargs) for item in x]

            elif isinstance(x, zip):
                return [menu.add(item, data, **kwargs) for item, data in x]

            elif isinstance(x, map):
                return [menu.add(item, **kwargs) for item in list(x)]

            elif isinstance(x, QtWidgets.QAction):
                return self.add_action_widget(
                    x, row=row, col=col, rowSpan=rowSpan, colSpan=colSpan
                )

            if isinstance(x, str):
                # OPTIMIZATION: Create widgets WITHOUT parent to avoid Qt tree overhead
                # Parent will be assigned implicitly when added to gridLayout
                widget_class = _MenuItems.resolve_widget_class(x)
                if widget_class:
                    widget = widget_class()
                else:
                    try:
                        widget = getattr(QtWidgets, x)()
                    except (AttributeError, TypeError):
                        widget = QtWidgets.QLabel()
                        widget.setText(x)

            elif isinstance(x, QtWidgets.QWidget) or (
                inspect.isclass(x) and issubclass(x, QtWidgets.QWidget)
            ):
                widget = x() if callable(x) else x

            else:
                raise TypeError(
                    f"Unsupported item type: expected str, QWidget, QAction, or a collection (list, tuple, set, dict, zip, map), got '{type(x)}'"
                )

            widget.item_text = lambda i=widget: menu.get_item_text(i)
            widget.item_data = lambda i=widget: menu.get_item_data(i)

            if row is None:
                row = _LayoutItems.first_free_row(menu.gridLayout, col)

            if colSpan is None:
                colSpan = menu.gridLayout.columnCount() or 1

            # Install event filters when adding the first item
            was_empty = not menu.contains_items

            menu.gridLayout.addWidget(widget, row, col, rowSpan, colSpan)
            # Defer the notification: signals are blocked here (see
            # pending_item_added_emits in __init__). Emitting now is a no-op
            # for connected slots, so queue it for the outermost add()'s
            # finally to flush once blocking is lifted and the widget is fully
            # configured (attributes/height applied below).
            self.pending_item_added_emits.append(widget)
            menu.set_item_data(widget, data)

            # Apply item height constraints only to appropriate widget types
            if isinstance(widget, _HEIGHT_CONSTRAINED_TYPES):
                has_height_constraint = (
                    menu.min_item_height is not None
                    or menu.max_item_height is not None
                    or menu.fixed_item_height is not None
                )
                # Use Fixed policy when explicit height is set, Preferred otherwise
                # Both prevent unwanted vertical expansion while respecting natural size
                vertical_policy = (
                    QtWidgets.QSizePolicy.Fixed
                    if has_height_constraint
                    else QtWidgets.QSizePolicy.Preferred
                )
                widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, vertical_policy)

                if menu.min_item_height is not None:
                    widget.setMinimumHeight(menu.min_item_height)
                if menu.max_item_height is not None:
                    widget.setMaximumHeight(menu.max_item_height)
                if menu.fixed_item_height is not None:
                    widget.setFixedHeight(menu.fixed_item_height)

            menu.set_attributes(widget, **kwargs)
            widget.installEventFilter(menu)
            self.expose_as_attribute(widget)

            # Container items (e.g. ExpandableList) drive their own
            # interaction and consume their internal mouse releases, so the
            # release-based hide-on-trigger in eventFilter never fires for
            # them. Bridge their interaction signal instead: a leaf activation
            # counts as a trigger; a row that merely opens a deeper level is
            # navigation and must not dismiss the menu.
            nested_signal = getattr(widget, "on_item_interacted", None)
            if nested_signal is not None and callable(
                getattr(nested_signal, "connect", None)
            ):
                nested_signal.connect(
                    lambda item, w=widget: menu._handle_nested_trigger(w, item)
                )

            # Defer registration to the next event-loop tick so it happens
            # AFTER add() finishes (updates re-enabled, signals unblocked).
            # Calling register_widget synchronously here triggers init_slot()
            # which can create nested menus / option-box wraps while add()
            # is still running — causing flashes and layout corruption.
            # Coalesced into a single drain so N items = 1 timer, not N.
            if widget.objectName():
                menu._schedule_registration(widget)

            # Only resize if menu is visible (prevents flash during lazy initialization)
            if menu.isVisible():
                menu.resize(menu.sizeHint())
            menu._layout.invalidate()

            # Ensure trigger event filters are installed once the menu has content
            # This allows trigger_button clicks to work before the first show()
            if menu._trigger_button is not False and not (
                menu._event_filters_installed or menu._parent_signal_source
            ):
                menu._ensure_trigger_hook()

            # Setup apply button on first item add (if requested and has connections)
            if was_empty:
                # Don't create apply button here - defer to showEvent when connections exist
                # Update apply button visibility for first item (if button already exists)
                if menu.add_apply_button:
                    menu._update_apply_button_visibility()
            elif menu.add_apply_button:
                # Only update visibility if apply button exists and is enabled
                # This avoids redundant checks when add_apply_button=False
                menu._update_apply_button_visibility()

            return widget

        finally:
            # CRITICAL: Re-enable layout and restore state
            if menu.gridLayout and layout_was_enabled:
                menu.gridLayout.setEnabled(True)

            # Restore signal blocking
            menu.blockSignals(was_blocked)

            # Re-enable updates - this triggers single update instead of one per operation
            if updates_were_enabled:
                menu.setUpdatesEnabled(True)

            # Activate layout to apply all changes at once.
            # Skip when invisible: Qt re-activates layouts before paint, so
            # the work is wasted if nothing is on screen.  Bulk-add (40+
            # items during slot init) is the dominant caller and is always
            # invisible — saves 1 activate per item.
            if menu._layout and menu.isVisible():
                menu._layout.activate()

            # Flush queued on_item_added notifications once the OUTERMOST add()
            # has fully unwound and the menu is settled (updates re-enabled,
            # layout activated). add() blocks signals internally, so the
            # synchronous emit during the insert is swallowed — queueing here is
            # what makes the documented signal reach listeners. ``signalsBlocked``
            # is honored, so an externally pre-blocked add() drops its
            # notifications rather than leaking them into a later unblocked call.
            self.add_depth -= 1
            if self.add_depth == 0 and self.pending_item_added_emits:
                pending, self.pending_item_added_emits = (
                    self.pending_item_added_emits,
                    [],
                )
                if not menu.signalsBlocked():
                    for added in pending:
                        menu.on_item_added.emit(added)

    def expose_as_attribute(self, widget: QtWidgets.QWidget) -> None:
        """Expose an item as ``menu.<objectName>`` for ergonomic access.

        Never clobbers Menu's own API: an item named "clear"/"show"/"add"
        would silently replace the method, so a name that collides with a
        non-widget attribute is skipped with a warning. Shared by ``add`` and
        ``add_row`` so nested-container rows expose their children identically.
        """
        menu = self._menu
        item_name = widget.objectName()
        if not item_name:
            return
        existing = getattr(menu, item_name, None)
        if existing is None or isinstance(existing, QtWidgets.QWidget):
            setattr(menu, item_name, widget)
        else:
            menu.logger.warning(
                f"[Menu.add] item objectName {item_name!r} collides with "
                f"an existing Menu attribute; skipping attribute exposure."
            )

    def add_row(
        self,
        items: list,
        title: Optional[str] = None,
        spacing: int = 4,
        stretch: bool = True,
        justify: Optional[str] = None,
        **shared_kwargs,
    ) -> list:
        menu = self._menu
        if title is not None:
            menu.add("Separator", setTitle=title)

        container = QtWidgets.QWidget()
        hbox = QtWidgets.QHBoxLayout(container)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(spacing)

        # Resolve the distribution mode. ``justify`` wins; otherwise fall back to
        # the legacy boolean (``stretch=True`` → left-pack, ``False`` → fill).
        mode = justify if justify is not None else ("left" if stretch else "expand")

        lead = mode in ("right", "center", "around")
        if lead:  # a stretch before the first widget pushes the row rightward
            hbox.addStretch(1)

        widgets = []
        for i, item in enumerate(items):
            spec, item_kwargs = item if isinstance(item, tuple) else (item, {})
            widget = self.create_row_widget(spec)
            menu.set_attributes(widget, **{**shared_kwargs, **item_kwargs})
            # "expand" gives every widget an equal stretch factor so the slots are
            # equal-width; the others add bare (natural-width) widgets.
            hbox.addWidget(widget, 1 if mode == "expand" else 0)
            # Inter-widget stretches for the space-distributing modes (not after
            # the last widget for "between", which keeps the last one edge-flush).
            if i < len(items) - 1 and mode in ("between", "around"):
                hbox.addStretch(1)
            self.expose_as_attribute(widget)
            widgets.append(widget)

        trail = mode in ("left", "center", "around")
        if trail:  # a trailing stretch left-packs (or balances center/around)
            hbox.addStretch(1)

        # One grid cell, full width: the grid stays single-column so no sibling
        # row is reflowed. A bare QWidget isn't height-constrained, so the row
        # keeps the natural height of its checkboxes.
        menu.add(container)
        return widgets

    @staticmethod
    def create_row_widget(x: Union[str, QtWidgets.QWidget, type]) -> QtWidgets.QWidget:
        """Resolve one ``add_row`` item spec to a widget (mirror of ``add``'s dispatch)."""
        if isinstance(x, str):
            widget_class = _MenuItems.resolve_widget_class(x)
            if widget_class:
                return widget_class()
            try:
                return getattr(QtWidgets, x)()
            except (AttributeError, TypeError):
                label = QtWidgets.QLabel()
                label.setText(x)
                return label
        if isinstance(x, QtWidgets.QWidget) or (
            inspect.isclass(x) and issubclass(x, QtWidgets.QWidget)
        ):
            return x() if callable(x) else x
        raise TypeError(
            f"add_row: unsupported item type {type(x)!r}; expected str, QWidget, or (spec, kwargs)."
        )

    def add_action_widget(
        self,
        action: QtWidgets.QAction,
        row: Optional[int] = None,
        col: int = 0,
        rowSpan: int = 1,
        colSpan: Optional[int] = None,
    ) -> Optional[QtWidgets.QWidget]:
        menu = self._menu
        # No temporary QMenu: the old realization path built a real QMenu,
        # SHOWED it (a momentary empty popup on screen during add() — an
        # init flash) and pumped the event loop to materialize
        # widgetForAction — an API newer PySide6 bindings no longer expose
        # (gone in 6.10, so the path also hard-crashed there).
        widget = None
        if isinstance(action, QtWidgets.QWidgetAction):
            # The action carries its own widget — take it directly.
            widget = action.defaultWidget()
            if widget is not None:
                widget.setParent(menu)
        if widget is None:
            # Plain QAction (or a QWidgetAction without a default widget):
            # host it in a QToolButton, the standard QAction carrier —
            # trigger/text/icon/enabled state all track the action.
            button = QtWidgets.QToolButton(menu)
            button.setDefaultAction(action)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            widget = button

        if row is None:
            row = _LayoutItems.first_free_row(menu.gridLayout, col)
        if colSpan is None:
            colSpan = menu.gridLayout.columnCount() or 1

        menu.gridLayout.addWidget(widget, row, col, rowSpan, colSpan)
        return widget
