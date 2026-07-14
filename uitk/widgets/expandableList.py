# !/usr/bin/python
# coding=utf-8
import inspect
from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.mixins.attributes import AttributesMixin


class ExpandableList(QtWidgets.QWidget, AttributesMixin):
    """A subclass of QWidget that represents a list of widgets, each potentially having an expandable sublist.

    ExpandableList is a versatile QWidget subclass that manages a collection of widgets. Each widget in the list can be associated
    with data, can have its own sublist of widgets, and can emit signals when it is interacted with or when a new widget is added.

    The ExpandableList can be positioned relative to its parent widget, and each widget in the list can be assigned minimum, maximum,
    or fixed height parameters.

    Signals:
        on_item_added: Emitted when an item is added to the list or any sublist. The new widget is passed as the argument.
        on_item_interacted: Emitted when an item in the list or any sublist is clicked. The interacted widget is passed as the argument.

    Attributes:
        position (str): The relative position of the ExpandableList. Can be 'right', 'left', 'top', 'bottom', or 'center'.
        min_item_height (int): The minimum height for items in the list. If None, the minimum height is not set.
        max_item_height (int): The maximum height for items in the list. If None, the maximum height is not set.
        fixed_item_height (int): The fixed height for items in the list. If None, the height is not fixed.
        sublist_x_offset (int): The x offset for sublists.
        sublist_y_offset (int): The y offset for sublists.
        widget_data (dict): Dictionary mapping widgets to their associated data.
        kwargs: Any additional built in widget attributes can be defined here. ie. setMinimumWidth=120 or setVisible=False

    Example:
        expandable_list = ExpandableList(position='right', fixed_item_height=30)
        expandable_list.add('QPushButton', data='Button Data')
        expandable_list.add(['Item 1', 'Item 2'])
        button = QtWidgets.QPushButton()
        expandable_list.add(button, data='Another Button')

        # Connect to signals
        expandable_list.on_item_added.connect(my_item_added_func)
        expandable_list.on_item_interacted.connect(my_item_interacted_func)
    """

    # Class constants
    VALID_POSITIONS = {
        "right",
        "left",
        "top",
        "bottom",
        "center",
        "overlay",
        "overlay_right",
    }
    DEFAULT_LAYOUT_SPACING = 0.5

    # Grace period after the cursor leaves a sublist's trigger item or
    # the sublist itself before the sublist is actually hidden. The
    # engagement check at fire time keeps the menu open as long as the
    # cursor returns to anywhere in the sublist's hierarchy within this
    # window — tolerates brief overshoots and the gap between an item
    # and its newly-shown sublist.
    HIDE_DELAY_MS = 180

    # Preset configurations for common layout patterns.
    # Each preset defines:
    #   root_position:      Direction the first sublist expands from the root widget.
    #   root_offset:        (x, y) offset for the first sublist relative to the root.
    #   child_position:     Direction deeper sublists expand from their parent.
    #   child_offset:       (x, y) offset for deeper sublists.
    #   use_item_height:    If True, auto-calculates root y-offset from fixed_item_height
    #                       so the first sublist covers the root button.
    PRESETS = {
        "expand_right": {
            "root_position": "right",
            "root_offset": (0, 0),
            "child_position": "right",
            "child_offset": (-1, 0),
        },
        "expand_left": {
            "root_position": "left",
            "root_offset": (0, 0),
            "child_position": "left",
            "child_offset": (1, 0),
        },
        "expand_up": {
            "root_position": "top",
            "root_offset": (0, 0),
            "child_position": "right",
            "child_offset": (-1, 0),
            "use_item_height": True,
        },
        "expand_down": {
            "root_position": "bottom",
            "root_offset": (0, 0),
            "child_position": "right",
            "child_offset": (-1, 0),
        },
        # First sublist overlays the root list — its top item aligns with the
        # triggering item, then extends downward. Deeper sublists fan out to
        # the right in standard menu fashion.
        "expand_overlay": {
            "root_position": "overlay",
            "root_offset": (0, 0),
            "child_position": "right",
            "child_offset": (-1, 0),
        },
        # Same overlay behavior as expand_overlay, but the first sublist
        # is right-aligned with the trigger (top-right of sublist = top-right
        # of original list) and deeper sublists fan out to the LEFT.
        "expand_overlay_left": {
            "root_position": "overlay_right",
            "root_offset": (0, 0),
            "child_position": "left",
            "child_offset": (1, 0),
        },
    }

    on_item_added = QtCore.Signal(object)
    on_item_interacted = QtCore.Signal(object)

    def __init__(
        self,
        parent=None,
        position="right",
        min_item_height=None,
        max_item_height=None,
        fixed_item_height=None,
        sublist_x_offset=0,
        sublist_y_offset=0,
        **kwargs,
    ):
        super().__init__(parent)

        if position not in self.VALID_POSITIONS:
            raise ValueError(
                f"Invalid position '{position}'. Must be one of: {', '.join(self.VALID_POSITIONS)}"
            )

        self.position = position
        self.min_item_height = min_item_height
        self.max_item_height = max_item_height
        self.fixed_item_height = fixed_item_height
        self.sublist_x_offset = sublist_x_offset
        self.sublist_y_offset = sublist_y_offset
        self.kwargs = kwargs

        self.widget_data = {}
        # Hide watches installed by the root list's showEvent: the top-level
        # window (see _watch_window_hide) and the containing uitk MainWindow's
        # on_hide signal (see _watch_ui_hide). None until showEvent runs.
        self._watched_window = None
        self._hide_signal_source = None

        self._setup_layout()
        self._setup_widget_properties()

    def _setup_layout(self):
        """Initialize the widget's layout with appropriate settings."""
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.DEFAULT_LAYOUT_SPACING)
        self.setLayout(self._layout)

    def _setup_widget_properties(self):
        """Configure widget properties and event handling."""
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.installEventFilter(self)
        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**self.kwargs)

    def apply_preset(self, preset_name):
        """Apply a named preset to configure expansion behavior.

        Presets configure how the root widget's first sublist expands, and
        how deeper sublists expand from there. Call this before adding items.

        The preset sets ``position`` and offset properties on this widget
        (controlling the first expansion), and stores the child direction so
        that sublists created by :meth:`add` automatically inherit it.

        Parameters:
            preset_name (str): One of the keys in :attr:`PRESETS`.

        Raises:
            ValueError: If the preset name is not recognized.

        Example:
            >>> widget.apply_preset("expand_up")
            >>> root = widget.add("Menu")
            >>> root.sublist.add(["Option A", "Option B"])
        """
        preset = self.PRESETS.get(preset_name)
        if preset is None:
            raise ValueError(
                f"Unknown preset '{preset_name}'. "
                f"Available: {', '.join(self.PRESETS)}"
            )

        self.position = preset["root_position"]
        rx, ry = preset["root_offset"]
        self.sublist_x_offset = rx

        if preset.get("use_item_height") and self.fixed_item_height:
            # Auto-offset so the first sublist covers the root button.
            self.sublist_y_offset = self.fixed_item_height + ry
        else:
            self.sublist_y_offset = ry

        # Store child config so _create_sublist_config can propagate it
        # to sublists created by root items.
        self._preset_child_position = preset["child_position"]
        self._preset_child_offset = preset["child_offset"]

    def get_items(self):
        """Get all items in the list and its sublists.

        This method recursively retrieves all items from the list, including items from all nested sublists.

        Returns:
            list: A list of all QWidget items in the list and its sublists.
        """
        items = [self._layout.itemAt(i).widget() for i in range(self._layout.count())]
        for item in items:
            if hasattr(item, "sublist"):
                items.extend(item.sublist.get_items())
        return items

    def _get_widget_attribute(self, widget, attribute, default=None):
        """Get an attribute from a widget safely.

        Parameters:
            widget (QtWidgets.QWidget): The widget to get the attribute from.
            attribute (str): The attribute name to retrieve.
            default: The default value to return if attribute doesn't exist.

        Returns:
            Any: The attribute value or default if not found.
        """
        return (
            getattr(widget, attribute, lambda: default)()
            if hasattr(widget, attribute)
            else default
        )

    def get_item_text(self, widget):
        """Get the textual representation of a widget.

        Parameters:
            widget (QtWidgets.QWidget): The widget for which to get the text.

        Returns:
            str: The text associated with the widget, or None if the widget does not have a text attribute.
        """
        return self._get_widget_attribute(widget, "text")

    def get_parent_item_text(self, widget):
        """Get the text attribute of the parent item of a widget's sublist.

        Parameters:
            widget (QtWidgets.QWidget): The widget for which to get the parent item's text.

        Returns:
            str: The text of the parent item, or None if the parent item does not exist or does not have a text attribute.
        """
        try:
            return self.get_item_text(widget.sublist.parent_list.parent_item)
        except AttributeError:
            return None

    def get_item_data(self, widget):
        """Get data associated with a widget in the list or its sublists.

        Parameters:
            widget (QtWidgets.QWidget): The widget to get the data for.

        Returns:
            Any: The data associated with the widget, or None if the widget is not found.
        """
        return self.widget_data.get(widget)

    def get_parent_item_data(self, widget):
        """Get the data associated with the parent item of a widget's sublist.

        Parameters:
            widget (QtWidgets.QWidget): The widget for which to get the parent item's data.

        Returns:
            Any: The data associated with the parent item, or None if the parent item does not exist or does not have associated data.
        """
        try:
            return self.get_item_data(widget.sublist.parent_list.parent_item)
        except AttributeError:
            return None

    def set_item_data(self, widget, data):
        """Set data associated with a widget in the list or its sublists.

        This method sets the data associated with a widget in the list or its sublists. If the widget is not found, it does nothing.

        Parameters:
            widget (QtWidgets.QWidget): The widget to set the data for.
            data: The data to associate with the widget.
        """
        if widget in self.get_items():
            self.widget_data[widget] = data

    def clear(self):
        """Clear all items in the list and its sublists.

        This method recursively removes all items from the list, including items
        from all nested sublists.

        Each sublist is reparented to the *window* (so intermediate native widgets
        can't clip it), which means it is NOT a Qt child of its parent item.
        Deleting the parent item therefore does NOT delete the sublist — it would
        orphan it on the window, where a flyout open at clear time keeps showing
        and ``_force_hide_all`` can no longer reach it (it iterates this layout,
        which no longer holds the orphan). On a list with ``refresh_on_show`` —
        which calls ``clear()`` on every show — those orphans accumulate and the
        stale flyout "is still visible when shown again". So tear the sublist
        widget down explicitly: hide it (drop any open flyout), then detach and
        delete it alongside its parent item.
        """
        # Process widgets in reverse order to avoid index errors
        for i in reversed(range(self._layout.count())):
            widget = self._layout.itemAt(i).widget()
            if widget:
                # Recursively clear, then destroy, the reparented sublist widget.
                sublist = getattr(widget, "sublist", None)
                if sublist is not None:
                    sublist.clear()
                    QtWidgets.QWidget.hide(sublist)  # drop any open flyout now
                    sublist.setParent(None)
                    sublist.deleteLater()

                # Cancel any pending deferred hide before deleting the item —
                # the timer is parented to self (not the item), so it would
                # otherwise fire on a deleted C++ widget and raise an uncaught
                # RuntimeError into the event loop (hit by refresh_on_show,
                # which clear()s on every show mid-hover).
                self._cancel_sublist_hide(widget)

                # Remove and clean up the item itself
                self._layout.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        # Reset the widget_data dictionary
        self.widget_data.clear()

    def _create_widget_from_input(self, x):
        """Create a widget from various input types.

        Parameters:
            x (str, QtWidgets.QWidget, type): Input to create widget from.

        Returns:
            QtWidgets.QWidget: The created widget.

        Raises:
            TypeError: If the input type is not supported.
        """
        if isinstance(x, str):
            try:
                return getattr(QtWidgets, x)(self)
            except (AttributeError, TypeError):
                widget = QtWidgets.QLabel()
                widget.setText(x)
                return widget

        elif isinstance(x, QtWidgets.QWidget):
            return x

        elif inspect.isclass(x) and issubclass(x, QtWidgets.QWidget):
            return x(self)

        else:
            raise TypeError(
                f"Unsupported item type: expected str, QWidget, a subclass of QWidget, "
                f"or a collection (list, tuple, set, map, zip, dict), but got '{type(x)}'"
            )

    def _configure_widget_properties(self, widget):
        """Configure common widget properties like height constraints.

        Parameters:
            widget (QtWidgets.QWidget): The widget to configure.
        """
        if self.min_item_height is not None:
            widget.setMinimumHeight(self.min_item_height)
        if self.max_item_height is not None:
            widget.setMaximumHeight(self.max_item_height)
        if self.fixed_item_height is not None:
            widget.setFixedHeight(self.fixed_item_height)

    def _setup_widget_methods(self, widget):
        """Add convenience methods to the widget for accessing item data.

        Parameters:
            widget (QtWidgets.QWidget): The widget to add methods to.
        """
        widget.item_text = lambda: self.get_item_text(widget)
        widget.item_data = lambda: self.get_item_data(widget)
        widget.parent_item_text = lambda: self.get_parent_item_text(widget)
        widget.parent_item_data = lambda: self.get_parent_item_data(widget)

    def _finalize_widget_setup(self, widget, data, **kwargs):
        """Complete the widget setup process.

        Parameters:
            widget (QtWidgets.QWidget): The widget to finalize.
            data: Data to associate with the widget.
            **kwargs: Additional attributes to set.
        """
        self._layout.addWidget(widget)
        self.on_item_added.emit(widget)

        self.set_item_data(widget, data)
        self._add_sublist(widget)
        self._configure_widget_properties(widget)
        self.set_attributes(widget, **kwargs)
        widget.installEventFilter(self)

        # Sublists are reparented to the window so they sit outside the
        # tracked parent's findChildren scope.  Register this list with
        # MouseTracking on its first populated item — empty leaf sublists
        # are never registered (the dominant cost in the previous design
        # was iterating ~100 empty sublists on every Enter/Press).  The
        # call is idempotent, so subsequent adds short-circuit.
        if hasattr(self, "parent_list"):
            self._register_for_drag_tracking(self)

        # Resize only when already visible. During bulk population, sizing
        # is deferred to a single resize in showEvent on the root list, and
        # sublists are explicitly resized by _handle_widget_enter_event
        # before being shown. Eager resize here was O(N^2) over populate.
        if self.isVisible():
            self.resize(self.sizeHint())

    def add(self, x, data=None, **kwargs):
        """Add an item or multiple items to the list or its sublists.

        The function accepts a string, an object, or a collection of items (a dictionary, list, tuple, set, or map).

        Parameters:
            x (str, object, dict, list, tuple, set, map): The item or items to add.
            data: Data to associate with the added item or items. Default is None.
            **kwargs: Additional arguments to set on the added item or items.

        Returns:
            widget/list: The added widget or list of added widgets.
        """
        # Handle collections
        if isinstance(x, dict):
            return [self.add(key, data=val, **kwargs) for key, val in x.items()]
        elif isinstance(x, (list, tuple, set)):
            return [self.add(item, **kwargs) for item in x]
        elif isinstance(x, zip):
            return [self.add(item, data, **kwargs) for item, data in x]
        elif isinstance(x, map):
            return [self.add(item, **kwargs) for item in list(x)]

        # Create widget from input
        widget = self._create_widget_from_input(x)

        # Setup widget methods and finalize
        self._setup_widget_methods(widget)
        self._finalize_widget_setup(widget, data, **kwargs)

        return widget

    def _create_sublist_config(self):
        """Create configuration dictionary for sublists.

        When a preset has been applied via ``apply_preset()``, child sublists
        inherit the preset's ``child_position`` and ``child_offset`` instead of
        blindly copying the parent's values.

        Returns:
            dict: Configuration parameters for creating sublists.
        """
        child_pos = getattr(self, "_preset_child_position", None)
        child_off = getattr(self, "_preset_child_offset", None)

        config = {
            "position": child_pos if child_pos is not None else self.position,
            "min_item_height": self.min_item_height,
            "max_item_height": self.max_item_height,
            "fixed_item_height": self.fixed_item_height,
            **self.kwargs,
        }

        if child_off is not None:
            config["sublist_x_offset"] = child_off[0]
            config["sublist_y_offset"] = child_off[1]
        else:
            config["sublist_x_offset"] = self.sublist_x_offset
            config["sublist_y_offset"] = self.sublist_y_offset

        return config

    def _setup_sublist_relationships(self, widget, sublist):
        """Setup parent-child relationships for sublists.

        Parameters:
            widget (QtWidgets.QWidget): The parent widget.
            sublist (ExpandableList): The sublist to setup relationships for.
        """
        widget.sublist = sublist
        sublist.parent_list = self
        sublist.parent_item = widget

        # Find the root list by iterating through parent lists
        sublist.root_list = self
        while hasattr(sublist.root_list, "parent_list"):
            sublist.root_list = sublist.root_list.parent_list

        # Set logical ancestor so parent windows (e.g. MarkingMenu) can
        # recognize sublist items as belonging to the original UI hierarchy.
        sublist._logical_ancestor = sublist.root_list

    def _get_inherited_stylesheet(self):
        """Walk the ancestor chain to find the nearest non-empty stylesheet.

        Sublists are reparented to the top-level window to avoid clipping,
        which breaks Qt's stylesheet inheritance.  This method retrieves the
        stylesheet that *would* have been inherited so it can be explicitly
        applied to the sublist.

        Returns:
            str: The stylesheet string, or empty string if none found.
        """
        w = self
        while w:
            ss = w.styleSheet()
            if ss:
                return ss
            w = w.parent()
        return ""

    def _add_sublist(self, widget):
        """Add an expanding list to the given widget.

        Parameters:
            widget (obj): Widget object to which the expandable list will be added.

        Returns:
            obj: The added ExpandableList object.
        """
        # Parent to the nearest QMainWindow ancestor so sublists aren't clipped
        # by intermediate native widgets (e.g. staticWindow in marking menus).
        parent = self.window() or self.parent()
        sublist = ExpandableList(parent, **self._create_sublist_config())
        sublist.setVisible(False)

        # A sublist always sizes to its own contents (its sizeHint is the widest
        # item plus margins), so it must carry no size constraint of its own.
        # Clear any width/size floor, cap, or pin the root's construction kwargs
        # applied — otherwise resize(sizeHint()) is clamped and the flyout comes
        # out "as wide as the starting list" instead of hugging its items. Item
        # heights are constrained on the items, not the list, so the list stays
        # fully unconstrained. A constraint a caller sets *after* creation (e.g.
        # a slot's explicit setMinimumWidth) runs later and still wins.
        sublist.setMinimumSize(0, 0)
        sublist.setMaximumSize(16777215, 16777215)  # Qt's QWIDGETSIZE_MAX

        # Propagate stylesheet so sublist items are styled consistently
        # (reparenting to the window breaks normal CSS inheritance).
        ss = self._get_inherited_stylesheet()
        if ss:
            sublist.setStyleSheet(ss)

        # Connect the signals of the sublist to the signals of the parent list
        sublist.on_item_interacted.connect(self.on_item_interacted.emit)
        sublist.on_item_added.connect(self.on_item_added.emit)

        self._setup_sublist_relationships(widget, sublist)
        return sublist

    def _register_for_drag_tracking(self, target):
        """Register a widget (sublist or item) with the window's MouseTracking.

        Sublists are reparented to the window to avoid clipping, which puts
        them outside the UI subtree that ``MouseTracking`` enumerates via
        ``findChildren``. Items inside sublists need the same treatment
        because the parent's snapshot was taken before they existed.
        Without registration, hover events stop firing on these widgets
        the moment a parent (e.g. MarkingMenu) grabs the mouse — the user
        sees an unresponsive list during a drag-hold.
        """
        win = self.window()
        mt = getattr(win, "mouse_tracking", None)
        if mt is None or not hasattr(mt, "register_external_widgets"):
            return
        try:
            mt.register_external_widgets([target])
        except Exception:
            pass

    def _get_root_list(self):
        """Return the topmost list in this hierarchy (self if already root)."""
        return getattr(self, "root_list", self)

    def _auto_open_suppressed(self):
        """Whether a sublist auto-open should be ignored right now.

        Suppression is armed by the root list's ``showEvent`` with the
        show-time cursor position. Qt delivers a synthetic ``Enter`` to the
        item under the cursor whenever the list (re)appears; without this
        latch that Enter silently reopens whatever sublist was expanded before
        the hide. The first Enter seen at a *different* cursor position clears
        the latch, so genuine hover-to-expand resumes after the user moves.

        Returns:
            bool: True while the synthetic show-time Enter should be ignored.
        """
        root = self._get_root_list()
        show_pos = getattr(root, "_suppress_open_pos", None)
        if show_pos is None:
            return False
        if QtGui.QCursor.pos() == show_pos:
            return True
        root._suppress_open_pos = None
        return False

    def hide(self):
        """Hide this list and collapse every still-open sublist.

        Sublists are reparented to the window (so they aren't clipped by
        intermediate native widgets), which means they are *not* Qt children
        of this list and don't disappear just because it hides. Force-collapse
        the whole hierarchy first so an explicit dismiss never strands an open
        sublist on screen.

        The previous implementation instead *refused* to hide while a sublist
        was visible (an early return); combined with sublists living outside
        this list's child tree, an explicit ``hide()`` then closed nothing at
        all. ``hideEvent`` runs ``_force_hide_all`` too, covering hides that
        bypass this override (e.g. a parent-window hide).
        """
        self._force_hide_all()
        super().hide()

    def showEvent(self, event):
        """On the root list's show, size to content and retroactively
        register every sublist with the window's MouseTracking.

        Per-add resize was removed for O(N) populate; the consolidated
        resize happens here so standalone (non-layout-managed) usage
        still sizes correctly. For layout-managed parents this is a
        no-op, since the layout's setGeometry overrides on the next pass.

        Sublists created before the list was parented into a window with
        ``mouse_tracking`` (typical when populated during slot init) will
        have failed their per-add registration silently. By the time the
        root list is shown the parent chain is fully assembled, so this
        is a reliable point to catch anything that was missed.
        """
        super().showEvent(event)
        if hasattr(self, "parent_list"):
            return  # only run on the root list

        # Defensive reset (safety net): collapse the whole hierarchy before
        # re-displaying. The ancestor-window watch below is the primary fix, but
        # sublists are reparented and keep their explicit-show flag across a
        # hide, so should any hide path ever slip past the watch, Qt's
        # showChildren would restore the open sublist here — "sublists remain
        # visible on next show". Collapsing unconditionally on every show makes a
        # missed hide impossible to leak forward; nothing should legitimately be
        # expanded on a fresh show.
        self._force_hide_all()

        # Collapse every sublist on the hides this list's own hideEvent misses
        # (sublists are reparented to the window): the top-level window hiding
        # (full dismiss / modal dialog) and the containing MainWindow hiding
        # (submenu navigation — a deep descendant gets no hideEvent).
        self._watch_window_hide()
        self._watch_ui_hide()

        # Arm synthetic-Enter suppression (see _auto_open_suppressed): a
        # (re)show makes Qt deliver a synthetic Enter to whatever item sits
        # under a stationary cursor, which would otherwise immediately reopen
        # the sublist that was expanded before the hide — the list "reshown in
        # its previously-expanded state". Record the show-time cursor position;
        # auto-open stays latched off until the cursor actually moves.
        self._suppress_open_pos = QtGui.QCursor.pos()

        self.resize(self.sizeHint())

        win = self.window()
        mt = getattr(win, "mouse_tracking", None)
        if mt is None or not hasattr(mt, "register_external_widgets"):
            return
        sublists = []
        seen = set()
        for item in self.get_items():
            sub = getattr(item, "sublist", None)
            if sub is None or id(sub) in seen:
                continue
            # Skip empty leaf sublists — registering them costs a
            # findChildren scan per update_child_widgets() call with
            # nothing to gain.  They'll register themselves lazily on
            # their first item add.
            if not sub.get_items():
                continue
            seen.add(id(sub))
            sublists.append(sub)
        if sublists:
            try:
                mt.register_external_widgets(sublists)
            except Exception:
                pass

    def hideEvent(self, event):
        """Ensure all sublists are closed when this list is hidden.

        Triggered by any hide mechanism (parent window hiding, explicit
        hide, stacked-widget page change, etc.), so stale sublists never
        persist across show/hide cycles.
        """
        self._force_hide_all()
        super().hideEvent(event)

    def _watch_window_hide(self):
        """Collapse sublists when the top-level window hides.

        Sublists are reparented to ``self.window()`` so intermediate native
        widgets can't clip them — which means they are NOT children of this list
        and don't auto-hide with it. The top-level window receives ``Hide`` for
        both programmatic and spontaneous hides (a DCC host reclaiming the
        overlay), and ``WindowBlocked`` when a modal dialog covers it; watching
        those collapses the sublists on full dismiss / reclaim / modal dialog.

        Idempotent; re-targets if the window changes between shows.
        """
        win = self.window()
        if win is None or win is self or win is self._watched_window:
            return
        if self._watched_window is not None:
            try:
                self._watched_window.removeEventFilter(self)
            except RuntimeError:
                pass  # old window already deleted (C++ side)
        win.installEventFilter(self)
        self._watched_window = win

    def _watch_ui_hide(self):
        """Collapse sublists when the containing uitk ``MainWindow`` hides.

        The window watch alone misses *submenu navigation*: the marking menu
        adds submenu UIs as NON-window children and hides the active one
        (``_current_widget.hide()``) while the top-level menu window stays up.
        This list is nested several levels under that UI, and Qt delivers a
        ``QHideEvent`` only to the widget being hidden — NOT to its deep
        descendants — so this list's own ``hideEvent`` never fires and the
        reparented sublists linger on the still-visible window. uitk
        ``MainWindow`` emits ``on_hide`` from its ``hideEvent``, so connect the
        collapse to the nearest ``MainWindow`` ancestor's signal — a clean,
        targeted hook that touches none of the marking menu's own internals.

        Idempotent; re-targets if the chain changes between shows.
        """
        source = None
        w = self.parentWidget()
        while w is not None:
            if hasattr(w, "on_hide"):  # a uitk MainWindow (the UI container)
                source = w
                break
            if w.isWindow():
                break  # reached the top-level; no MainWindow in between
            w = w.parentWidget()
        if source is self._hide_signal_source:
            return
        if self._hide_signal_source is not None:
            try:
                self._hide_signal_source.on_hide.disconnect(self._force_hide_all)
            except (RuntimeError, TypeError):
                pass  # old source deleted, or was never connected
        self._hide_signal_source = source
        if source is not None:
            source.on_hide.connect(self._force_hide_all)

    def _is_cursor_in_hierarchy(self, cursor_pos):
        """Check if cursor is within this list or any visible child sublist.

        Parameters:
            cursor_pos (QtCore.QPoint): Global cursor position.

        Returns:
            bool: True if cursor is inside any visible part of the hierarchy.
        """
        if self.isVisible() and self.rect().contains(self.mapFromGlobal(cursor_pos)):
            return True
        for i in range(self._layout.count()):
            w = self._layout.itemAt(i).widget()
            if w and hasattr(w, "sublist") and w.sublist.isVisible():
                if w.sublist._is_cursor_in_hierarchy(cursor_pos):
                    return True
        return False

    def _force_hide_all(self):
        """Force-hide every sublist in this hierarchy, bypassing the chained
        ``hide()`` override.

        Hides *unconditionally* — not just sublists that currently read as
        visible. Sublists are reparented to the window, so when an ancestor is
        hidden they get a spontaneous hide (``isVisible()`` goes False) yet keep
        their explicit-visible flag; Qt's ``showChildren`` then restores them on
        the next show, reopening the list in its previously-expanded state. An
        ``isVisible()`` guard here would skip them mid-hide and leave that flag
        set, so the clear must be unconditional. Hiding an already-hidden widget
        is a no-op, so the extra calls are harmless.
        """
        for i in range(self._layout.count()):
            w = self._layout.itemAt(i).widget()
            if w and hasattr(w, "sublist"):
                w.sublist._force_hide_all()
                # Bypass ExpandableList.hide()'s chained-children guard by
                # calling QWidget.hide() directly. ``super(ExpandableList,
                # w.sublist)`` would TypeError if a re-import has produced a
                # second ExpandableList class whose identity differs from this
                # module's name binding.
                QtWidgets.QWidget.hide(w.sublist)

    def _schedule_sublist_hide(self, item):
        """Start (or restart) a deferred hide of ``item.sublist``.

        Called from ``Leave`` events on triggering items and from the
        sublist's own ``leaveEvent``.  The actual hide is gated by an
        engagement re-check at fire time, so a cursor that returns
        anywhere into the sublist's hierarchy within ``HIDE_DELAY_MS``
        keeps it open.
        """
        if not (item and hasattr(item, "sublist") and item.sublist.isVisible()):
            return
        timer = getattr(item, "_pending_hide_timer", None)
        if timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda w=item: self._maybe_hide_sublist(w))
            item._pending_hide_timer = timer
        timer.start(self.HIDE_DELAY_MS)

    def _cancel_sublist_hide(self, item):
        """Cancel any pending deferred hide for ``item.sublist``."""
        timer = getattr(item, "_pending_hide_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()

    def _maybe_hide_sublist(self, item):
        """Engagement re-check: hide ``item.sublist`` only if the cursor
        is not currently on the trigger item, the sublist, or anywhere
        in its visible descendant tree.  Cascades to nested sublists.
        """
        # Defense in depth: even with clear() cancelling timers, a queued fire
        # can still land on an item/sublist whose C++ object was deleted —
        # touching it raises RuntimeError. Treat that as "nothing to hide".
        try:
            if not item or not hasattr(item, "sublist"):
                return
            sublist = item.sublist
            if not sublist.isVisible():
                return
            cursor_pos = QtGui.QCursor.pos()
            on_item = item.rect().contains(item.mapFromGlobal(cursor_pos))
        except RuntimeError:
            return
        if on_item or sublist._is_cursor_in_hierarchy(cursor_pos):
            return
        sublist._force_hide_all()
        QtWidgets.QWidget.hide(sublist)

    @staticmethod
    def get_padding(widget):
        """Get the padding values around a widget.

        Parameters:
            widget (obj): A widget object to get the padding values for.

        Returns:
            tuple: A tuple containing padding values (horizontal padding, vertical padding).
        """
        frame_geo = widget.frameGeometry()
        geo = widget.geometry()

        left_padding = geo.left() - frame_geo.left()
        right_padding = frame_geo.right() - geo.right()
        top_padding = geo.top() - frame_geo.top()
        bottom_padding = frame_geo.bottom() - geo.bottom()

        return (left_padding + right_padding, top_padding + bottom_padding)

    def sizeHint(self):
        """Return the recommended size for the widget.

        This method calculates the total size of the widgets contained in the layout of the ExpandableList, including margins and spacing.

        Returns:
            QtCore.QSize: The recommended size for the widget.
        """
        total_height = 0
        total_width = 0

        for i in range(self._layout.count()):
            widget = self._layout.itemAt(i).widget()
            if widget:
                total_height += widget.sizeHint().height() + self._layout.spacing()
                total_width = max(total_width, widget.sizeHint().width())

        # Adjust for layout's top and bottom margins
        total_height += (
            self._layout.contentsMargins().top()
            + self._layout.contentsMargins().bottom()
        )

        # Adjust for layout's left and right margins for width
        total_width += (
            self._layout.contentsMargins().left()
            + self._layout.contentsMargins().right()
        )

        return QtCore.QSize(total_width, total_height)

    def _calculate_sublist_position(
        self,
        widget,
        parent_list_width,
        parent_list_height,
        child_widget_width,
        child_widget_height,
        new_list_width,
        new_list_height,
    ):
        """Calculate the position for a sublist based on the configured position.

        Parameters:
            widget: The parent widget of the sublist.
            parent_list_width: Width of the parent list.
            parent_list_height: Height of the parent list.
            child_widget_width: Width of the child widget.
            child_widget_height: Height of the child widget.
            new_list_width: Width of the new sublist.
            new_list_height: Height of the new sublist.

        Returns:
            tuple: (x, y) coordinates for the sublist position.
        """
        overlap = getattr(self, "overlap", 0)

        position_configs = {
            "right": (
                child_widget_width - overlap + self.sublist_x_offset,
                self.sublist_y_offset,
            ),
            "left": (
                -new_list_width + overlap + self.sublist_x_offset,
                self.sublist_y_offset,
            ),
            "top": (
                self.sublist_x_offset,
                -new_list_height + overlap + self.sublist_y_offset,
            ),
            "bottom": (
                self.sublist_x_offset,
                child_widget_height - overlap + self.sublist_y_offset,
            ),
            "center": (
                (child_widget_width - new_list_width) // 2 + self.sublist_x_offset,
                (child_widget_height - new_list_height) // 2 + self.sublist_y_offset,
            ),
            # Sublist top-left = trigger top-left. The popup overlays the
            # starting list with its first item aligned to the trigger item;
            # subsequent items extend downward over whatever sits below.
            "overlay": (
                self.sublist_x_offset,
                self.sublist_y_offset,
            ),
            # Sublist top-right = trigger top-right. Use this when the
            # sublist is wider than the trigger and items below expand to
            # the LEFT — keeps the right edge stable so deeper sublists
            # appear flush against the original list's right side.
            "overlay_right": (
                child_widget_width - new_list_width + self.sublist_x_offset,
                self.sublist_y_offset,
            ),
        }

        return position_configs[self.position]

    def _cancel_pending_hides_up_chain(self):
        """Cancel deferred sublist-hide timers for every ancestor trigger
        in this list's chain.  Called when the cursor (re-)engages any
        item or sublist in the hierarchy so brief excursions outside a
        sublist's bounds don't collapse the ancestor menu after delay.
        """
        cur = self
        while hasattr(cur, "parent_item"):
            trigger = cur.parent_item
            timer = getattr(trigger, "_pending_hide_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
            cur = getattr(cur, "parent_list", None)
            if cur is None:
                return

    def _close_sibling_sublists(self, keep_widget):
        """Force-hide every visible sublist in this list whose trigger is
        not ``keep_widget``.  Called when Enter fires on a sibling item
        so the previously-open sublist disappears as the new one shows,
        rather than lingering for the full hide-delay window.
        """
        for i in range(self._layout.count()):
            sibling = self._layout.itemAt(i).widget()
            if sibling is None or sibling is keep_widget:
                continue
            if not (hasattr(sibling, "sublist") and sibling.sublist.isVisible()):
                continue
            self._cancel_sublist_hide(sibling)
            sibling.sublist._force_hide_all()
            QtWidgets.QWidget.hide(sibling.sublist)

    def _handle_widget_enter_event(self, widget):
        """Handle the enter event for a widget with a sublist.

        Parameters:
            widget: The widget that was entered.
        """
        # Any Enter inside this list's chain cancels pending hides for
        # all ancestor triggers — keeps parent menus open while the user
        # navigates into a child sublist or returns from an overshoot.
        self._cancel_pending_hides_up_chain()

        # Immediately close any sibling sublist that's still visible.
        # Without this, when the cursor moves from item A → item B, A's
        # sublist lingers until its delayed-hide timer fires (180ms),
        # appearing as old-still-visible-after-new-shown lag.
        self._close_sibling_sublists(widget)

        if not (hasattr(widget, "sublist") and widget.sublist.get_items()):
            return

        # Re-entering an item with a sublist cancels its own pending hide
        # (left over from a previous Leave on the same item).
        self._cancel_sublist_hide(widget)

        # Ensure correct size before positioning. Every layout sizes the sublist
        # to its own contents (its sizeHint), except the overlay presets: their
        # first sublist sits directly on top of the starting list, so it must be
        # at least as wide as this list to cover it fully (it may still grow
        # wider for longer content). ``self`` is the list that owns the trigger,
        # so this only widens the *first* overlay sublist; deeper fan-out
        # sublists (child position "right"/"left") keep sizing to content.
        hint = widget.sublist.sizeHint()
        target_width = hint.width()
        if self.position.startswith("overlay"):
            target_width = max(target_width, self.width())
        widget.sublist.resize(target_width, hint.height())
        widget.updateGeometry()

        # Get dimensions
        parent_list_width = self.width()
        parent_list_height = self.height()
        child_widget_width = widget.width()
        child_widget_height = widget.height()
        new_list_width = widget.sublist.width()
        new_list_height = widget.sublist.height()

        # Calculate position
        x, y = self._calculate_sublist_position(
            widget,
            parent_list_width,
            parent_list_height,
            child_widget_width,
            child_widget_height,
            new_list_width,
            new_list_height,
        )

        # Compute base position using widget's top-left, then apply offsets
        parent = widget.sublist.parent()
        base_point = widget.mapToGlobal(QtCore.QPoint(0, 0))

        if parent:
            parent_origin = parent.mapToGlobal(QtCore.QPoint(0, 0))
            base_point -= parent_origin

        pos = base_point + QtCore.QPoint(x, y)
        widget.sublist.move(pos)

        # Show AFTER positioning to prevent a flash at the wrong location
        widget.sublist.show()
        widget.sublist.raise_()

    def eventFilter(self, widget, event):
        """Filter events for the ExpandableList.

        Parameters:
            widget (obj): The object that the event was sent to.
            event (obj): The event that occurred.

        Returns:
            bool: False if the event should be further processed, and True if the event should be ignored.
        """
        event_type = event.type()

        # The watched top-level window hiding (full dismiss / spontaneous host
        # reclaim) or being covered by a modal dialog (WindowBlocked — no Hide
        # is delivered then) must collapse every sublist — see
        # _watch_window_hide. Handled first so the window is never mistaken for a
        # list item by the branches below (its Enter/Leave/Release must not drive
        # the sublist hover machinery). WindowDeactivate is deliberately NOT
        # watched: DCC overlays (Blender) spuriously lose activation during
        # normal chord navigation, which would collapse the menu mid-use.
        if widget is self._watched_window:
            if event_type in (QtCore.QEvent.Hide, QtCore.QEvent.WindowBlocked):
                self._force_hide_all()
            return False

        if event_type == QtCore.QEvent.Enter:
            # Ignore the synthetic Enter Qt fires on (re)show under a
            # stationary cursor — it would reopen the sublist that was open
            # before the hide. Direct/programmatic calls to
            # _handle_widget_enter_event bypass this gate intentionally.
            if not self._auto_open_suppressed():
                self._handle_widget_enter_event(widget)

        elif event_type == QtCore.QEvent.Leave:
            # Schedule a deferred hide of this item's sublist (if any),
            # plus the sublist that owns this item (if we're inside one).
            # The engagement re-check at fire time prevents the close
            # when the cursor returns into the hierarchy.
            if hasattr(widget, "sublist") and widget.sublist.isVisible():
                self._schedule_sublist_hide(widget)
            if hasattr(self, "parent_item"):
                self._schedule_sublist_hide(self.parent_item)

        elif event_type == QtCore.QEvent.MouseButtonRelease:
            # Check if widget is a child of this ExpandableList
            if widget in self.get_items():
                self.on_item_interacted.emit(widget)
                return True  # Consume event to prevent double-firing

        return super().eventFilter(widget, event)

    def leaveEvent(self, event):
        """Handle the cursor leaving this list widget.

        If this list is itself a sublist (has ``parent_item``), schedule
        a deferred hide of itself.  The engagement check at fire time
        keeps it open if the cursor returned into the hierarchy.
        """
        if hasattr(self, "parent_item"):
            self._get_root_list()._schedule_sublist_hide(self.parent_item)
        super().leaveEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QMainWindow()
    lw = ExpandableList(
        window, setMinimumWidth=120, fixed_item_height=21, sublist_x_offset=-1
    )
    w1 = lw.add("QPushButton", setObjectName="b001", setText="Button 1")
    w1.sublist.add("list A")
    w2 = lw.add("Label 1")
    w3, w4 = w2.sublist.add(["Label 2", "Label 3"])
    w3.sublist.add("QPushButton", setObjectName="b004", setText="Button 4")
    lw.add("QPushButton", setObjectName="b003", setText="Button 3")

    print("\nitems:", lw.get_items())

    lw.on_item_interacted.connect(lambda x: print(x))

    from uitk.widgets.mixins.style_sheet import StyleSheet

    StyleSheet().set(widget=lw.get_items(), theme="dark")

    window.resize(765, 255)
    window.show()
    sys.exit(app.exec_())

# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Promoting a widget in designer to use a custom class:
>   In Qt Designer, select all the widgets you want to replace, 
        then right-click them and select 'Promote to...'. 

>   In the dialog:
        Base Class:     Class from which you inherit. ie. QWidget
        Promoted Class: Name of the class. ie. "MyWidget"
        Header File:    Path of the file (changing the extension .py to .h)  ie. myfolder.mymodule.mywidget.h

>   Then click "Add", "Promote", 
        and you will see the class change from "QWidget" to "MyWidget" in the Object Inspector pane.
"""

# deprecated ---------------------


# def event(self, event):
#   """Handles events that are sent to the widget.

#   Parameters:
#       event (QtCore.QEvent): The event that was sent to the widget.

#   Returns:
#       bool: True if the event was handled, otherwise False.

#   Notes:
#       This method is called automatically by Qt when an event is sent to the widget.
#       If the event is a `QEvent.ChildPolished` event, it calls the `on_child_polished`
#       method with the child widget as an argument. Otherwise, it calls the superclass
#       implementation of `event`.
#   """
#   if event.type() == QtCore.QEvent.HoverMove:
#       print ('event_hoverMoveEvent'.ljust(25), self.mouseGrabber())
#       # window = QtWidgets.QApplication.activeWindow()
#       # if window and not self.rect().contains(self.mapFromGlobal(QtGui.QCursor.pos())):
#       #   if window.mouseGrabber() == self:
#       #       self.releaseMouse()

#   elif event.type() == QtCore.QEvent.HoverLeave:
#       print ('event_hoverLeaveEvent'.ljust(25), self.mouseGrabber())
#       # window = QtWidgets.QApplication.activeWindow()
#       # if window and not self.rect().contains(self.mapFromGlobal(QtGui.QCursor.pos())):
#           # if window.mouseGrabber() == self:
#       self.releaseMouse()

#   return super().event(event)
