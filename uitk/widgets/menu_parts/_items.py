# !/usr/bin/python
# coding=utf-8
"""What the menu holds: adding, finding and removing items.

``add`` / ``add_row`` build and place widgets in the item grid (one full-width
row each unless told otherwise), expose each as ``menu.<objectName>`` and queue
its registration with the owning window; the lookups (``get_items``,
``get_item``...) read the grid back. Also here: the transient "No options"
placeholder a menu shows when opened empty, and the filter that hides items
whose action already has a keyboard shortcut.

One part of :class:`~uitk.widgets.menu.Menu`, which inherits it; it holds no
state of its own (``Menu.__init__`` declares every attribute used here) and
is never instantiated alone.
"""

import inspect
from typing import Any, Dict, Optional, Tuple, Union

from qtpy import QtCore, QtWidgets

from uitk.managers.shortcut_manager import ShortcutManager
from uitk.widgets.separator import Separator

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
# and cached on first use by _resolve_widget_class.
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


class _MenuItemsMixin:
    """What the menu holds: adding, finding and removing items."""

    @staticmethod
    def _resolve_widget_class(name: str):
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

    @property
    def contains_items(self) -> bool:
        """Check if the QMenu contains any genuine items.

        The transient empty-state placeholder (see :meth:`_add_empty_placeholder`)
        is intentionally excluded — callers asking "does this menu have
        anything to offer?" should get False while only the placeholder
        is on screen.
        """
        # Handle lazy initialization - gridLayout may not exist yet
        if self.gridLayout is None:
            return False
        count = self.gridLayout.count()
        if self._empty_placeholder is not None:
            count -= 1
        return count > 0

    def _add_empty_placeholder(self) -> None:
        """Insert the transient "No options" message when shown with no items."""
        if self._empty_placeholder is not None or not self._empty_message:
            return
        if self.gridLayout is None:
            return
        label = QtWidgets.QLabel(self._empty_message)
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setObjectName("menuEmptyMessage")
        label.setProperty("class", "menuEmptyMessage")
        if self.min_item_height:
            label.setMinimumHeight(self.min_item_height)
        # Bypass add() — this widget is purely informational and must not
        # be counted by contains_items, registered with the main window,
        # or get the usual item event-filter treatment.
        self.gridLayout.addWidget(label, 0, 0, 1, max(1, self.gridLayout.columnCount()))
        self._empty_placeholder = label

    def _shortcut_filter_candidates(self) -> list:
        """Items the shortcut filter may hide (overridden where the body is
        not the grid — see :class:`~uitk.widgets.context_menu.ContextMenu`)."""
        return self.get_items()

    def _item_has_shortcut(self, item) -> bool:
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
            self.logger.debug(f"[_item_has_shortcut] {name}: {e}")
            return False

    def _apply_shortcut_item_filter(self) -> None:
        """Hide items whose action already has a shortcut, when asked to.

        Driven by the global ``ShortcutManager.hide_bound_menu_items()``
        preference (the shortcut editor's toggle): a menu exists to reach an
        action, so once the action is on a key its row is clutter to the users
        who turn this on.  Re-read on every show — flipping the preference off
        restores exactly the items this hid, leaving rows hidden for any other
        reason alone.
        """
        restored, self._shortcut_hidden_items = self._shortcut_hidden_items, []
        for item in restored:
            try:
                item.setVisible(True)
            except RuntimeError:  # deleted between shows
                pass

        if not ShortcutManager.hide_bound_menu_items():
            return

        candidates = self._shortcut_filter_candidates()
        for item in candidates:
            if item.isHidden() or not self._item_has_shortcut(item):
                continue
            item.setVisible(False)
            self._shortcut_hidden_items.append(item)

        # Filtering everything away would otherwise open a bare empty popup.
        if self._shortcut_hidden_items and all(item.isHidden() for item in candidates):
            self._shortcut_filter_emptied()

    def _shortcut_filter_emptied(self) -> None:
        """Every filterable item is hidden — show the empty-state placeholder
        instead of a bare popup."""
        self._add_empty_placeholder()

    def _remove_empty_placeholder(self) -> None:
        """Tear down the empty placeholder if present."""
        label = self._empty_placeholder
        self._empty_placeholder = None
        if label is None:
            return
        if self.gridLayout is not None:
            self.gridLayout.removeWidget(label)
        label.setParent(None)
        label.deleteLater()

    def _on_empty_timeout(self) -> None:
        """Hide the menu when the empty-state timer fires (unless items arrived)."""
        if self._empty_placeholder is None:
            return  # Real items appeared while shown — leave the menu open.
        if self.isVisible():
            self.hide()

    def get_items(self, types=None):
        """Get all items in the list, optionally filtered by type.

        Parameters:
            types (str, type, list of str, list of type, optional): The type(s) or type name(s) of widgets to retrieve. Defaults to None.

        Returns:
            list: A list of all QWidget items in the list, filtered by type if specified.
        """
        items = [
            self.gridLayout.itemAt(i).widget() for i in range(self.gridLayout.count())
        ]

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
                        self.logger.warning(
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
        """Return a QAction or QWidgetAction by index or text.

        Parameters:
            identifier (int or str): If an int, treats it as an index. If a str, treats it as the text of the item.

        Raises:
            ValueError: If the identifier is not an integer (index) or string (text).

        Returns:
            QAction or QWidgetAction: The item found by the identifier.
        """
        items = self.get_items()

        if isinstance(identifier, int):  # get by index
            if identifier < 0 or identifier >= len(items):
                raise ValueError("Index out of range.")
            item = items[identifier]
        elif isinstance(identifier, str):  # get by text
            for i in items:
                # Resolve each item's label via the guarded helper — not every
                # item type exposes text() (combos use currentText(), spin boxes
                # value(), etc.), so a bare i.text() would AttributeError.
                if self.get_item_text(i) == identifier:
                    item = i
                    break
            else:
                raise ValueError("No item found with the given text.")
        else:
            raise ValueError(
                f"Expected an integer (index) or string (text), got '{type(identifier)}'"
            )

        return item

    def get_item_text(self, widget: QtWidgets.QWidget) -> Optional[str]:
        """Get the textual representation of a widget.

        This method attempts to retrieve text from various widget types by trying
        common text-retrieval methods in order of likelihood.

        Parameters:
            widget: The widget to get text from.

        Returns:
            str: The text associated with the widget, or None if unavailable.
        """
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

    def get_item_data(self, widget):
        """Get data associated with a widget in the list or its sublists.

        This method returns the data associated with the widget in the list or any sublist. If the widget is not found, it returns None.

        Parameters:
            widget (QtWidgets.QWidget): The widget to get the data for.

        Returns:
            Any: The data associated with the widget, or None if the widget is not found.
        """
        try:
            return self.widget_data.get(widget)
        except KeyError:
            return None

    def set_item_data(self, widget, data):
        """Set data associated with a widget in the list or its sublists.

        This method sets the data associated with a widget in the list. If the widget is not found, it does nothing.

        Parameters:
            widget (QtWidgets.QWidget): The widget to set the data for.
            data: The data to associate with the widget.
        """
        if widget in self.get_items():
            self.widget_data[widget] = data

    def remove_widget(self, widget):
        """Remove a widget from the layout.

        The item filter :meth:`add` installed comes off with it: this hands
        the widget's lifetime back to the caller, and a menu that goes on
        filtering a widget it no longer owns both pins the menu alive through
        the widget's filter list and keeps answering that widget's events.

        If this results in an empty menu, the PARENT trigger hooks are
        uninstalled too (:meth:`_uninstall_event_filters`, which covers only
        those -- never the per-item filters).
        """
        self.logger.debug(
            f"Menu.remove_widget: Removing widget={widget.objectName() or type(widget).__name__}"
        )
        self._remove_item_event_filter(widget)
        self.gridLayout.removeWidget(widget)
        if widget in self.widget_data:
            del self.widget_data[widget]

        # Uninstall event filters if menu is now empty
        if not self.contains_items:
            self._uninstall_event_filters()
            self.logger.debug(
                "Menu.remove_widget: Menu now empty, event filters uninstalled"
            )

    def _remove_item_event_filter(self, widget) -> None:
        """Undo the ``installEventFilter`` :meth:`add` puts on every item.

        The counterpart that was missing. Tolerates a widget whose C++ object
        has already gone: the point is that the menu stops filtering it, and a
        wrapper that raises has no filter list left to clean anyway.
        """
        try:
            widget.removeEventFilter(self)
        except (RuntimeError, AttributeError):
            pass

    def clear(self) -> None:
        """Clear all items in the list.

        Each item gives up the filter :meth:`add` installed on it BEFORE it is
        deleted. ``deleteLater`` only schedules the destruction, so an item
        keeps receiving events until the loop drains it -- with the menu still
        filtering them, through ``widget in items`` / ``objectName()`` /
        :meth:`_resolve_hide_on_trigger` on an object being torn down.

        :meth:`_uninstall_event_filters` below does NOT cover this: it removes
        the PARENT/trigger hooks only, which is what its own name means.
        """
        if self.gridLayout is None:
            return

        # Tear down any transient empty-state placeholder first, while its
        # C++ object is still alive (before the reverse-delete loop's
        # deleteLater is processed). This mirrors add()'s teardown so the
        # placeholder can't dangle: leaving self._empty_placeholder set would
        # (1) make the next empty show no-op and (2) let _empty_timer fire
        # _on_empty_timeout -> hide() -> _remove_empty_placeholder() on an
        # already-destroyed label, raising RuntimeError from the timer.
        if self._empty_placeholder is not None:
            if self._empty_timer is not None:
                self._empty_timer.stop()
            self._remove_empty_placeholder()

        item_count = self.gridLayout.count()
        self.logger.debug(f"Menu.clear: Clearing {item_count} items")

        # We're going backwards to avoid index errors.
        for i in reversed(range(self.gridLayout.count())):
            widget = self.gridLayout.itemAt(i).widget()
            if widget:
                self._remove_item_event_filter(widget)
                self.gridLayout.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # Reset the widget_data dictionary
        self.widget_data = {}

        # Uninstall event filters since menu is now empty
        self._uninstall_event_filters()
        self.logger.debug("Menu.clear: All items cleared, event filters uninstalled")

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
        """Add an item or multiple items to the list.

        The function accepts a string, an object, or a collection of items (a dictionary, list, tuple, set, or map).

        Parameters:
            x (str, object, dict, list, tuple, set, map): The item or items to add.
            data: Data to associate with the added item or items. Default is None.
            row (int): The row index at which to add the widget. Default is the last row.
            col (int): The column index at which to add the widget. Default is 0.
            rowSpan (int): The number of rows the widget should span. Default is 1.
            colSpan (int): The number of columns the widget should span. Default is the total number of columns.
            **kwargs: Additional arguments to set on the added item or items.

        Returns:
            widget/list: The added widget or list of added widgets.
        """
        # CRITICAL OPTIMIZATION: Disable updates AND layout recalculation during add
        # This prevents Qt from recalculating layout/geometry on every operation
        updates_were_enabled = self.updatesEnabled()
        self.setUpdatesEnabled(False)

        # Block signals to prevent cascading updates
        was_blocked = self.blockSignals(True)

        # If a transient empty-state placeholder is on screen, drop it now —
        # a real item is arriving and should take its place without leaving
        # the "No options" label behind.
        if self._empty_placeholder is not None:
            if self._empty_timer is not None:
                self._empty_timer.stop()
            self._remove_empty_placeholder()

        # Suspend layout activation if layout exists
        layout_was_enabled = False
        if self.gridLayout:
            layout_was_enabled = self.gridLayout.isEnabled()
            self.gridLayout.setEnabled(False)

        try:
            # Track recursion so the outermost call (depth back to 0) owns the
            # on_item_added flush, regardless of whether signals were already
            # blocked on entry (collection adds recurse with signals blocked).
            self._add_depth += 1

            # Lazy initialization: create layout on first item add
            self._ensure_layout_created()

            if isinstance(x, dict):
                return [self.add(key, data=val, **kwargs) for key, val in x.items()]

            elif isinstance(x, (list, tuple, set)):
                return [self.add(item, **kwargs) for item in x]

            elif isinstance(x, zip):
                return [self.add(item, data, **kwargs) for item, data in x]

            elif isinstance(x, map):
                return [self.add(item, **kwargs) for item in list(x)]

            elif isinstance(x, QtWidgets.QAction):
                return self._add_action_widget(
                    x, row=row, col=col, rowSpan=rowSpan, colSpan=colSpan
                )

            if isinstance(x, str):
                # OPTIMIZATION: Create widgets WITHOUT parent to avoid Qt tree overhead
                # Parent will be assigned implicitly when added to gridLayout
                widget_class = _MenuItemsMixin._resolve_widget_class(x)
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

            widget.item_text = lambda i=widget: self.get_item_text(i)
            widget.item_data = lambda i=widget: self.get_item_data(i)

            if row is None:
                row = 0
                while self.gridLayout.itemAtPosition(row, col) is not None:
                    row += 1

            if colSpan is None:
                colSpan = self.gridLayout.columnCount() or 1

            # DEBUG: Print row assignment
            # Install event filters when adding the first item
            was_empty = not self.contains_items

            self.gridLayout.addWidget(widget, row, col, rowSpan, colSpan)
            # Defer the notification: signals are blocked here (see the
            # _pending_item_added_emits comment in __init__). Emitting now is a
            # no-op for connected slots, so queue it for the outermost add()'s
            # finally to flush once blocking is lifted and the widget is fully
            # configured (attributes/height applied below).
            self._pending_item_added_emits.append(widget)
            self.set_item_data(widget, data)

            # Apply item height constraints only to appropriate widget types
            if isinstance(widget, _HEIGHT_CONSTRAINED_TYPES):
                has_height_constraint = (
                    self.min_item_height is not None
                    or self.max_item_height is not None
                    or self.fixed_item_height is not None
                )
                # Use Fixed policy when explicit height is set, Preferred otherwise
                # Both prevent unwanted vertical expansion while respecting natural size
                vertical_policy = (
                    QtWidgets.QSizePolicy.Fixed
                    if has_height_constraint
                    else QtWidgets.QSizePolicy.Preferred
                )
                widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, vertical_policy)

                if self.min_item_height is not None:
                    widget.setMinimumHeight(self.min_item_height)
                if self.max_item_height is not None:
                    widget.setMaximumHeight(self.max_item_height)
                if self.fixed_item_height is not None:
                    widget.setFixedHeight(self.fixed_item_height)

            self.set_attributes(widget, **kwargs)
            widget.installEventFilter(self)
            self._expose_as_attribute(widget)

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
                    lambda item, w=widget: self._handle_nested_trigger(w, item)
                )

            # Defer registration to the next event-loop tick so it happens
            # AFTER add() finishes (updates re-enabled, signals unblocked).
            # Calling register_widget synchronously here triggers init_slot()
            # which can create nested menus / option-box wraps while add()
            # is still running — causing flashes and layout corruption.
            # Coalesced into a single drain so N items = 1 timer, not N.
            if widget.objectName():
                self._schedule_registration(widget)

            # Only resize if menu is visible (prevents flash during lazy initialization)
            if self.isVisible():
                self.resize(self.sizeHint())
            self._layout.invalidate()

            # Ensure trigger event filters are installed once the menu has content
            # This allows trigger_button clicks to work before the first show()
            if self._trigger_button is not False and not (
                self._event_filters_installed or self._parent_signal_source
            ):
                self._ensure_trigger_hook()

            # Setup apply button on first item add (if requested and has connections)
            if was_empty:
                # Don't create apply button here - defer to showEvent when connections exist
                # Update apply button visibility for first item (if button already exists)
                if self.add_apply_button:
                    self._update_apply_button_visibility()
            elif self.add_apply_button:
                # Only update visibility if apply button exists and is enabled
                # This avoids redundant checks when add_apply_button=False
                self._update_apply_button_visibility()

            return widget

        finally:
            # CRITICAL: Re-enable layout and restore state
            if self.gridLayout and layout_was_enabled:
                self.gridLayout.setEnabled(True)

            # Restore signal blocking
            self.blockSignals(was_blocked)

            # Re-enable updates - this triggers single update instead of one per operation
            if updates_were_enabled:
                self.setUpdatesEnabled(True)

            # Activate layout to apply all changes at once.
            # Skip when invisible: Qt re-activates layouts before paint, so
            # the work is wasted if nothing is on screen.  Bulk-add (40+
            # items during slot init) is the dominant caller and is always
            # invisible — saves 1 activate per item.
            if self._layout and self.isVisible():
                self._layout.activate()

            # Flush queued on_item_added notifications once the OUTERMOST add()
            # has fully unwound and the menu is settled (updates re-enabled,
            # layout activated). add() blocks signals internally, so the
            # synchronous emit during the insert is swallowed — queueing here is
            # what makes the documented signal reach listeners. ``signalsBlocked``
            # is honored, so an externally pre-blocked add() drops its
            # notifications rather than leaking them into a later unblocked call.
            self._add_depth -= 1
            if self._add_depth == 0 and self._pending_item_added_emits:
                pending, self._pending_item_added_emits = (
                    self._pending_item_added_emits,
                    [],
                )
                if not self.signalsBlocked():
                    for added in pending:
                        self.on_item_added.emit(added)

    def _expose_as_attribute(self, widget: QtWidgets.QWidget) -> None:
        """Expose an item as ``menu.<objectName>`` for ergonomic access.

        Never clobbers Menu's own API: an item named "clear"/"show"/"add"
        would silently replace the method, so a name that collides with a
        non-widget attribute is skipped with a warning. Shared by ``add`` and
        ``add_row`` so nested-container rows expose their children identically.
        """
        item_name = widget.objectName()
        if not item_name:
            return
        existing = getattr(self, item_name, None)
        if existing is None or isinstance(existing, QtWidgets.QWidget):
            setattr(self, item_name, widget)
        else:
            self.logger.warning(
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
        """Add a single horizontal row of widgets, optionally under a titled separator.

        The menu's default is one widget per full-width row. ``add_row`` places
        several controls side-by-side by nesting them in a lightweight container
        so the surrounding single-column rows are never reflowed (adding raw
        multi-column grid cells would grow the grid's column count and squeeze
        every other row into the first column). Each child is still exposed as
        ``menu.<objectName>`` and is discoverable via ``findChildren``, so the
        preset system and ``getattr(menu, name)`` lookups behave exactly as they
        do for widgets added one-per-row.

        Parameters:
            items (list): One entry per column. Each entry is a widget-type
                string (e.g. ``"QCheckBox"``), a ``QWidget`` instance/subclass,
                or a ``(spec, kwargs)`` tuple whose ``kwargs`` configure that one
                widget (``setObjectName`` / ``setText`` / ``setChecked`` /
                ``setToolTip`` / ``addItems`` / …).
            title (str, optional): When given, a titled ``Separator`` is added on
                the row above (mirrors ``add("Separator", setTitle=title)``).
            spacing (int): Horizontal spacing, in px, between the row's widgets.
            stretch (bool): Legacy left-pack toggle used only when ``justify`` is
                ``None``: ``True`` appends a trailing stretch so the widgets pack
                to the left; ``False`` lets them fill the row.
            justify (str, optional): How to distribute the widgets across the
                container's full width (the container itself always spans the
                menu column). Overrides ``stretch`` when given. One of:
                ``"left"`` (trailing stretch — same as the legacy default),
                ``"right"`` (leading stretch), ``"center"`` (stretch both ends),
                ``"between"`` (equal gaps between widgets, first/last flush to the
                edges — spans the width), ``"around"`` (equal gaps including the
                ends), or ``"expand"`` (every widget gets an equal stretch factor,
                so each occupies an equal-width slot).
            **shared_kwargs: Applied to every widget in the row (an item's own
                kwargs win on conflict).

        Returns:
            list: The created widgets, in column order.
        """
        if title is not None:
            self.add("Separator", setTitle=title)

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
            widget = self._create_row_widget(spec)
            self.set_attributes(widget, **{**shared_kwargs, **item_kwargs})
            # "expand" gives every widget an equal stretch factor so the slots are
            # equal-width; the others add bare (natural-width) widgets.
            hbox.addWidget(widget, 1 if mode == "expand" else 0)
            # Inter-widget stretches for the space-distributing modes (not after
            # the last widget for "between", which keeps the last one edge-flush).
            if i < len(items) - 1 and mode in ("between", "around"):
                hbox.addStretch(1)
            self._expose_as_attribute(widget)
            widgets.append(widget)

        trail = mode in ("left", "center", "around")
        if trail:  # a trailing stretch left-packs (or balances center/around)
            hbox.addStretch(1)

        # One grid cell, full width: the grid stays single-column so no sibling
        # row is reflowed. A bare QWidget isn't height-constrained, so the row
        # keeps the natural height of its checkboxes.
        self.add(container)
        return widgets

    def _create_row_widget(
        self, x: Union[str, QtWidgets.QWidget, type]
    ) -> QtWidgets.QWidget:
        """Resolve one ``add_row`` item spec to a widget (mirror of ``add``'s dispatch)."""
        if isinstance(x, str):
            widget_class = _MenuItemsMixin._resolve_widget_class(x)
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

    def _add_action_widget(
        self,
        action: QtWidgets.QAction,
        row: Optional[int] = None,
        col: int = 0,
        rowSpan: int = 1,
        colSpan: Optional[int] = None,
    ) -> Optional[QtWidgets.QWidget]:
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
                widget.setParent(self)
        if widget is None:
            # Plain QAction (or a QWidgetAction without a default widget):
            # host it in a QToolButton, the standard QAction carrier —
            # trigger/text/icon/enabled state all track the action.
            button = QtWidgets.QToolButton(self)
            button.setDefaultAction(action)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            widget = button

        if row is None:
            row = 0
            while self.gridLayout.itemAtPosition(row, col):
                row += 1
        if colSpan is None:
            colSpan = self.gridLayout.columnCount() or 1

        self.gridLayout.addWidget(widget, row, col, rowSpan, colSpan)
        return widget
