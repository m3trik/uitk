# !/usr/bin/python
# coding=utf-8
import inspect
import logging
from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.mixins.attributes import AttributesMixin

logger = logging.getLogger(__name__)


class _ClickDismissFilter(QtCore.QObject):
    """App-level dismiss watcher for a click-mode flyout chain.

    Installed on the QApplication only while a chain is open (see
    ``_begin_click_chain``) and removed the moment it collapses, so its
    per-event cost exists only during an open menu session.

    A dedicated QObject rather than app-installing the owning list's own
    ``eventFilter``: while installed app-wide, the filter receives events for
    *every* widget in the application, and the list's Enter/Leave/Release
    branches would misfire on foreign widgets (e.g. a stray Enter driving
    ``_close_sibling_sublists``).

    Only Qt events are visible here — clicks on a DCC's native (non-Qt)
    surfaces never arrive. Those are covered by the WindowDeactivate watch in
    ``ExpandableList.eventFilter`` instead.
    """

    def __init__(self, root_list):
        # No QObject parent: lifetime is managed explicitly by
        # _begin/_end_click_chain, and the root list must stay free to be
        # deleted (clear()/deleteLater) without dragging this filter with it
        # mid-dispatch.
        super().__init__()
        self._root = root_list

    def eventFilter(self, obj, event):
        event_type = event.type()
        if event_type == QtCore.QEvent.MouseButtonPress:
            # QCursor.pos() rather than the event's global position: dodges
            # the PySide2 globalPos() / PySide6 globalPosition() API split.
            try:
                root = self._root
                if not root._is_cursor_in_hierarchy(QtGui.QCursor.pos()):
                    # Collapse, but do NOT consume — the outside click should
                    # still land on whatever the user pressed (standard menu
                    # dismissal semantics).
                    root._force_hide_all()
            except RuntimeError:
                # Root's C++ object died (clear()/window teardown mid-session);
                # nothing left to dismiss — detach quietly.
                self._detach()
            return False
        if event_type == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
            try:
                self._root._force_hide_all()
            except RuntimeError:
                self._detach()
            return True  # Escape is spent on dismissing the menu.
        return False

    def _detach(self):
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)


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
        position (str): The relative position of the ExpandableList. Can be 'right', 'left', 'top', 'bottom', 'center', or one of the
            overlay anchors ('overlay', 'overlay_right', 'overlay_bottom_right') that open the first sublist on top of the starting list.
        activation (str): How sublists open — 'hover' (default: expand on Enter,
            collapse on a delayed Leave) or 'click' (expand/collapse on item
            click, persist until dismissed by an outside click, Escape, leaf
            activation, or the host window hiding). Meaningful on the root list
            only — sublists always consult the root, so there is no per-sublist
            copy to drift. Set via ``apply_preset`` rather than directly.
        embedded (bool): True when the root is embedded in a normal
            layout-managed host (a window row or a popup menu) rather than the
            fullscreen marking-menu overlay: the root hugs its content height
            and flyouts are shown as frameless focusless Tool windows (with a
            screen clamp) so the host's bounds can't clip them. Root-list
            authoritative, set via ``apply_preset`` (``header_menu`` = embedded
            hover, ``click_menu`` = embedded click).
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

    # Qt Designer widget-box entry.
    designer_spec = {"icon": "list", "object_name": "list", "size": (160, 120)}

    # Class constants
    VALID_POSITIONS = {
        "right",
        "left",
        "top",
        "bottom",
        "center",
        "overlay",
        "overlay_right",
        "overlay_bottom_right",
    }
    VALID_ACTIVATIONS = ("hover", "click")
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
    #   activation:         Optional. "hover" (default) or "click" — how sublists open.
    #   embedded:           Optional. True when the root is embedded in a normal
    #                       layout-managed host (a window row or a popup menu) rather
    #                       than the fullscreen marking-menu overlay: the root hugs its
    #                       content height, and flyouts are shown as frameless Tool
    #                       windows (with a screen clamp) so the host's bounds can't
    #                       clip them.
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
        # Overlay anchored at the trigger's BOTTOM-right corner, so the first
        # sublist covers the starting list and grows UPWARD; deeper sublists
        # fan out to the LEFT. For a list sitting in the upper-left of the
        # marking-menu overlay, where a downward/rightward fan would run into
        # the radial center.
        "expand_overlay_up_left": {
            "root_position": "overlay_bottom_right",
            "root_offset": (0, 0),
            "child_position": "left",
            "child_offset": (1, 0),
        },
        # Standard click-driven menu: the first sublist drops below the root
        # row, deeper sublists fan out to the right. activation="click" —
        # sublists open on item click (not hover), persist until dismissed,
        # and are shown as frameless Tool windows so they escape a small host
        # window's bounds (the other presets serve the fullscreen marking-menu
        # overlay, where clipping was never possible). For embedded menu-bar
        # rows in a standalone window.
        "click_menu": {
            "root_position": "bottom",
            "root_offset": (0, 0),
            "child_position": "right",
            "child_offset": (-1, 0),
            "activation": "click",
            "embedded": True,
        },
        # Hover-driven menu entry for a list embedded in a normal window or a
        # popup menu (e.g. a panel's header menu): sublists open on mouse-over
        # and fan out to the right, shown as frameless Tool windows so the
        # host's bounds can't clip them. Same feel as expand_right in the
        # marking-menu overlay, adapted to a small embedded host.
        "header_menu": {
            "root_position": "right",
            "root_offset": (0, 0),
            "child_position": "right",
            "child_offset": (-1, 0),
            "embedded": True,
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

        # Sublist activation mode ("hover" | "click"); authoritative on the
        # root list only — see the class docstring. Set via apply_preset.
        self.activation = "hover"
        # Whether this root is embedded in a normal layout-managed host (see
        # the PRESETS key docs); authoritative on the root list only.
        self.embedded = False
        # Click-mode session state (root list only): True while a click-opened
        # flyout chain is up and the app-level dismiss filter is installed.
        self._click_chain_open = False
        self._dismiss_filter = None

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

    # -- Qt Designer properties ----------------------------------------------
    # The construction options above, restated as Qt properties so the list can
    # be configured in Designer's property editor instead of only in a slot.
    # Named apart from the plain attributes they wrap (``expandPosition`` for
    # ``position``): a Qt property sharing an attribute's name would intercept
    # the very assignment its setter makes.
    #
    # The three item heights are ``None`` when unset, which a Qt ``int``
    # property can't carry — 0 stands in for "unset" on this side of the fence
    # and is translated back on the way in.

    def getExpandPosition(self) -> str:
        """Direction sublists expand toward — see :attr:`VALID_POSITIONS`."""
        return self.position

    def setExpandPosition(self, value: str) -> None:
        """Set the sublist expansion direction, ignoring unknown values."""
        if value in self.VALID_POSITIONS:
            self.position = value
        else:
            logger.warning(
                "Ignoring invalid ExpandableList position %r; expected one of %s",
                value,
                ", ".join(self.VALID_POSITIONS),
            )

    def setMinItemHeight(self, value: int) -> None:
        """Set the per-item minimum height; 0 clears it."""
        self.min_item_height = int(value) or None

    def setMaxItemHeight(self, value: int) -> None:
        """Set the per-item maximum height; 0 clears it."""
        self.max_item_height = int(value) or None

    def setFixedItemHeight(self, value: int) -> None:
        """Set the per-item fixed height; 0 clears it."""
        self.fixed_item_height = int(value) or None

    def setSublistXOffset(self, value: int) -> None:
        """Set the horizontal offset applied to sublists."""
        self.sublist_x_offset = int(value)

    def setSublistYOffset(self, value: int) -> None:
        """Set the vertical offset applied to sublists."""
        self.sublist_y_offset = int(value)

    expandPosition = QtCore.Property(
        str, fget=getExpandPosition, fset=setExpandPosition
    )
    minItemHeight = QtCore.Property(
        int, fget=lambda self: self.min_item_height or 0, fset=setMinItemHeight
    )
    maxItemHeight = QtCore.Property(
        int, fget=lambda self: self.max_item_height or 0, fset=setMaxItemHeight
    )
    fixedItemHeight = QtCore.Property(
        int, fget=lambda self: self.fixed_item_height or 0, fset=setFixedItemHeight
    )
    sublistXOffset = QtCore.Property(
        int, fget=lambda self: self.sublist_x_offset, fset=setSublistXOffset
    )
    sublistYOffset = QtCore.Property(
        int, fget=lambda self: self.sublist_y_offset, fset=setSublistYOffset
    )

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
                f"Unknown preset '{preset_name}'. Available: {', '.join(self.PRESETS)}"
            )

        self.position = preset["root_position"]
        rx, ry = preset["root_offset"]
        self.sublist_x_offset = rx

        if preset.get("use_item_height") and self.fixed_item_height:
            # Auto-offset so the first sublist covers the root button.
            self.sublist_y_offset = self.fixed_item_height + ry
        else:
            self.sublist_y_offset = ry

        # Whether the first sublist opens on top of the root list — either an
        # explicit overlay position, or a use_item_height preset (expand_up)
        # whose y-offset slides the first sublist over the root button. In
        # both cases the sublist visually replaces the "starting widget", so
        # it must open at least as wide as the root rather than hug its own
        # items; _handle_widget_enter_event reads this to floor the width.
        # Deeper (child) sublists never carry this flag, so they keep sizing
        # to content.
        self._first_sublist_overlays_root = preset["root_position"].startswith(
            "overlay"
        ) or bool(preset.get("use_item_height"))

        # Store child config so _create_sublist_config can propagate it
        # to sublists created by root items.
        self._preset_child_position = preset["child_position"]
        self._preset_child_offset = preset["child_offset"]

        # Activation mode. Only meaningful on the root list (sublists consult
        # the root via _click_mode), and apply_preset is documented as a
        # root-list, before-populate call, so setting it here is authoritative.
        activation = preset.get("activation", "hover")
        if activation not in self.VALID_ACTIVATIONS:
            raise ValueError(
                f"Invalid activation '{activation}'. Must be one of: "
                f"{', '.join(self.VALID_ACTIVATIONS)}"
            )
        self.activation = activation

        self.embedded = bool(preset.get("embedded", False))
        if self.embedded:
            # An embedded root is a menu row inside a normal layout (window
            # strip or popup menu): it must hug its content height (one row
            # per root item) instead of soaking up surplus vertical space
            # through the Expanding policy set at construction.
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
            )

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
        # An icon-composited label (IconManager.set_label_icon) keeps its plain
        # text on this property while its .text() holds rich-text <img> markup;
        # prefer it so text-based dispatch/lookup never sees the markup.
        if hasattr(widget, "property"):
            plain = widget.property("iconLabelText")
            if plain is not None:
                return plain
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
        # Collapse first: the per-item hides below drop the flyouts anyway,
        # but routing through _force_hide_all also retires a click-mode
        # session (chain flag + app-level dismiss filter) when a slot
        # rebuilds the list while a menu is open.
        self._force_hide_all()

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

    def _click_mode(self):
        """Whether this hierarchy uses click activation.

        The root list's ``activation`` is the single source of truth —
        sublists never carry their own copy, so a preset re-applied on the
        root (e.g. across a ``refresh_on_show`` rebuild) can't leave stale
        per-sublist state behind.
        """
        return getattr(self._get_root_list(), "activation", "hover") == "click"

    def _is_embedded(self):
        """Whether this hierarchy's root is embedded in a normal layout host.

        Root-authoritative for the same drift-free reason as ``_click_mode``.
        Embedded roots get popup flyouts + the screen clamp regardless of
        activation mode — clipping is a property of where the root lives, not
        of how its sublists open.
        """
        return bool(getattr(self._get_root_list(), "embedded", False))

    def _ensure_popup_flags(self, sublist):
        """Idempotently promote an embedded-mode sublist to a frameless Tool window.

        Mirrors ``Menu._setup_as_popup``: a single ``setParent(parent, flags)``
        call (setWindowFlags alone would recreate the native handle, then
        setParent again — two recreations), applied lazily on first open while
        the sublist is still hidden (a flag-change hide is then a no-op, and no
        OS-level window exists before it's needed — avoids a WM-visible flash
        on Windows at construction time).

        Why a window at all: hover-mode sublists are plain children of
        ``self.window()``, which is fine under the fullscreen marking-menu
        overlay but clips flyouts at the border of a small standalone window.

        ``WindowDoesNotAcceptFocus`` is load-bearing: without it, clicking a
        flyout activates the Tool window, deactivating the host — which the
        click-mode WindowDeactivate watch in ``eventFilter`` would read as
        "user left" and dismiss the menu mid-interaction. Flyout rows are pure
        click targets (no focus-needing editors), so refusing focus is safe
        and also keeps a DCC host's focus untouched.
        """
        if getattr(sublist, "_popup_configured", False):
            return
        sublist._popup_configured = True
        flags = (
            QtCore.Qt.Tool
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowDoesNotAcceptFocus
        )
        parent = sublist.parentWidget()
        if parent is not None:
            sublist.setParent(parent, flags)
        else:
            sublist.setWindowFlags(flags)
        # After reparenting so it survives the native-handle recreation.
        sublist.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)

    def _is_layout_managed(self):
        """Whether a parent layout owns this widget's geometry.

        True for an embedded list (a row in a popup ``Menu`` or a window
        layout); False for the marking-menu overlay's absolutely-positioned
        roots and for every reparented sublist, which own their own geometry.

        Searches the parent's whole layout tree, not just its top-level
        layout: ``QLayout.indexOf`` only sees its own direct items, and hosts
        nest layouts (a ``Menu`` puts its items in a QGridLayout nested inside
        the central widget's QVBoxLayout), which a top-level-only check reads
        as "unmanaged".
        """
        parent = self.parentWidget()
        layout = parent.layout() if parent is not None else None
        if layout is None:
            return False
        pending = [layout]
        while pending:
            lay = pending.pop()
            if lay.indexOf(self) != -1:
                return True
            for i in range(lay.count()):
                item = lay.itemAt(i)
                nested = item.layout() if item is not None else None
                if nested is not None:
                    pending.append(nested)
        return False

    def _find_host_with(self, attr, start=None):
        """Nearest ancestor of *start* (default ``self``) exposing *attr*.

        The host-integration lookup this widget uses instead of importing its
        hosts: a uitk ``MainWindow`` by ``on_hide``, a popup ``Menu`` by
        ``adopt_transient``. Stops at the first top-level ancestor — checked
        AFTER the attribute, so a top-level host still matches — because
        anything beyond it is a different window, not this list's host.

        Returns:
            QtWidgets.QWidget or None: The matching ancestor, else None.
        """
        w = (start if start is not None else self).parentWidget()
        while w is not None:
            if hasattr(w, attr):
                return w
            if w.isWindow():
                return None
            w = w.parentWidget()
        return None

    def _adopt_into_host_menu(self, sublist):
        """Register an embedded flyout with the popup menu hosting this list.

        A flyout is a separate top-level window, and it is created at populate
        time — when a host ``Menu`` is typically not yet a window itself, so
        ``self.window()`` resolved to the panel behind it and the flyout's
        QObject chain never reaches the menu. A ``hide_on_leave`` menu then
        reads the pointer entering the flyout as having left the menu and
        dismisses itself (taking the flyout with it), and conversely a menu
        that hides on its own leaves the flyout stranded on screen.

        ``Menu.adopt_transient`` is the designed answer for child popups
        parented outside a menu's subtree: while adopted, the pointer over the
        flyout counts as inside the menu's transient family, and the menu
        hiding cascades into the flyout. Duck-typed like this widget's other
        host hooks (``mouse_tracking``, ``on_hide``) so it stays menu-agnostic;
        idempotent on the menu side, so opening a flyout repeatedly is free.

        Resolved from the ROOT list — only the root lives inside the menu's
        widget subtree; deeper sublists are reparented top-levels like this one.
        """
        host = self._find_host_with("adopt_transient", start=self._get_root_list())
        if host is None:
            return  # not menu-hosted (e.g. a plain window); nothing to adopt into
        try:
            host.adopt_transient(sublist)
        except RuntimeError:
            pass  # host died mid-open

    def _ensure_sublist_on_screen(self, sublist):
        """Clamp a top-level flyout fully into its screen's available area.

        Trimmed port of ``Menu._ensure_on_screen``. Hover-mode sublists never
        need this (the fullscreen overlay is the screen); embedded click-mode
        roots can sit anywhere, so a flyout near a screen edge would otherwise
        open partially off-screen. Clamps (slides) rather than flips direction;
        near an edge the flyout may cover its parent row — accepted trade-off.
        """
        frame_geo = sublist.frameGeometry()
        screen = None
        if hasattr(QtWidgets.QApplication, "screenAt"):
            screen = QtWidgets.QApplication.screenAt(frame_geo.center())
        if screen is None:
            screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        x = min(frame_geo.x(), available.right() - frame_geo.width())
        x = max(x, available.left())
        y = min(frame_geo.y(), available.bottom() - frame_geo.height())
        y = max(y, available.top())
        if x != frame_geo.x() or y != frame_geo.y():
            sublist.move(x, y)

    def _begin_click_chain(self):
        """Root list only: mark a click-opened chain live and arm dismissal.

        Installs the app-level outside-press/Escape watcher. Idempotent —
        opening a second flyout while the chain is already up is a no-op here.
        """
        root = self._get_root_list()
        if root._click_chain_open:
            return
        root._click_chain_open = True
        app = QtWidgets.QApplication.instance()
        if app is not None:
            root._dismiss_filter = _ClickDismissFilter(root)
            app.installEventFilter(root._dismiss_filter)

    def _end_click_chain(self):
        """Root list only: retire the chain state and the app-level filter.

        Deliberately performs no hides — it is called *from* ``_force_hide_all``
        (every dismiss path funnels there), so hiding here would recurse.
        """
        root = self._get_root_list()
        if not root._click_chain_open:
            return
        root._click_chain_open = False
        filt = root._dismiss_filter
        root._dismiss_filter = None
        if filt is not None:
            try:
                filt._detach()
            except RuntimeError:
                pass  # app or filter already torn down

    def _any_sublist_visible(self):
        """Whether any direct item's sublist is currently visible.

        Direct check only: descendants of a hidden sublist are always
        force-hidden with it, so a hidden first level implies a fully
        collapsed chain.
        """
        for i in range(self._layout.count()):
            w = self._layout.itemAt(i).widget()
            if w and hasattr(w, "sublist") and w.sublist.isVisible():
                return True
        return False

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
        resize happens here so standalone (non-layout-managed) usage still
        sizes correctly. It is skipped when a parent layout manages this
        list — the layout has ALREADY allocated the correct width by the time
        showEvent runs, and resizing to our own sizeHint clobbers it until the
        next layout pass. That transient wrong width was visible (an embedded
        header-menu list rendering narrower/wider than the menu, "correcting
        itself" after any later interaction) and, worse, mispositioned the
        first flyout: its placement is measured from the trigger row's edge,
        which inherits the list's bogus width.

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

        if not self._is_layout_managed():
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
        source = self._find_host_with("on_hide")  # a uitk MainWindow (UI container)
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

        # Click mode: a full collapse ends the menu session. Funneling the
        # teardown through here means every dismiss path — outside press,
        # Escape, leaf activation, watched-window Hide/WindowBlocked/
        # WindowDeactivate, on_hide, hideEvent, showEvent's defensive reset,
        # clear() — retires the app-level filter without its own wiring.
        # Root-only: sublist recursion above must not touch session state.
        if not hasattr(self, "parent_list") and self.activation == "click":
            self._end_click_chain()

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
            # Sublist bottom-right = trigger bottom-right. The popup covers the
            # starting list and grows upward from the trigger's lower edge;
            # pair with a "left" child position so deeper sublists stay flush
            # against the stable right edge.
            "overlay_bottom_right": (
                child_widget_width - new_list_width + self.sublist_x_offset,
                child_widget_height - new_list_height + self.sublist_y_offset,
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

        # Embedded roots show flyouts as frameless Tool windows (they must
        # escape the host's bounds — a small window or a popup menu, unlike
        # the fullscreen overlay). Applied here — the single choke point for
        # every open path (hover-open, click-toggle, hover-navigation) — while
        # the sublist is still hidden, so the flag-change hide is a no-op.
        # Populate-before-open invariant: every sublist (any depth) was created
        # while still a plain child widget, so its parent — and therefore
        # self.window() during nested _add_sublist calls — is the host window,
        # never another flyout. refresh_on_show re-populates while everything
        # is closed, preserving the invariant.
        if self._is_embedded():
            self._ensure_popup_flags(widget.sublist)
            # Keep a hover-dismissing host menu open while the pointer is on
            # the flyout, and let the menu's hide cascade collapse it.
            self._adopt_into_host_menu(widget.sublist)

        # Ensure correct size before positioning. Every layout sizes the sublist
        # to its own contents (its sizeHint), except the presets whose first
        # sublist sits directly on top of the starting list (explicit overlay
        # positions and expand_up's use_item_height cover): that sublist must be
        # at least as wide as this list to cover it fully (it may still grow
        # wider for longer content). ``self`` is the list that owns the trigger
        # and only a root list carries ``_first_sublist_overlays_root``, so this
        # widens only the *first* covering sublist; deeper fan-out sublists
        # (child position "right"/"left") keep sizing to content.
        hint = widget.sublist.sizeHint()
        target_width = hint.width()
        if self.position.startswith("overlay") or getattr(
            self, "_first_sublist_overlays_root", False
        ):
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

        # Compute base position using widget's top-left, then apply offsets.
        # A click-mode flyout is a top-level window (isWindow) — its move()
        # takes GLOBAL coordinates, so the parent-origin subtraction must be
        # skipped. Hover-mode sublists are window children and keep the
        # parent-relative math.
        parent = widget.sublist.parent()
        base_point = widget.mapToGlobal(QtCore.QPoint(0, 0))

        if parent and not widget.sublist.isWindow():
            parent_origin = parent.mapToGlobal(QtCore.QPoint(0, 0))
            base_point -= parent_origin

        pos = base_point + QtCore.QPoint(x, y)
        widget.sublist.move(pos)

        # Show AFTER positioning to prevent a flash at the wrong location
        widget.sublist.show()
        widget.sublist.raise_()

        # Top-level flyouts can land partially off-screen (the embedded root
        # can sit anywhere, unlike the fullscreen overlay) — clamp into the
        # screen's available area.
        if widget.sublist.isWindow():
            self._ensure_sublist_on_screen(widget.sublist)

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
        # watched in hover mode: DCC overlays (Blender) spuriously lose
        # activation during normal chord navigation, which would collapse the
        # menu mid-use. Click mode (never hosted on an overlay) DOES watch it —
        # it is the only dismissal that fires when the user clicks a DCC's
        # native, non-Qt surface, which the app-level dismiss filter can't see.
        # Safe only because click-mode flyouts carry WindowDoesNotAcceptFocus:
        # clicking a flyout then never deactivates the host window, so a
        # deactivation genuinely means the user left.
        if widget is self._watched_window:
            if event_type in (QtCore.QEvent.Hide, QtCore.QEvent.WindowBlocked):
                self._force_hide_all()
            elif event_type == QtCore.QEvent.WindowDeactivate and self._click_mode():
                self._force_hide_all()
            return False

        if event_type == QtCore.QEvent.Enter:
            # Ignore the synthetic Enter Qt fires on (re)show under a
            # stationary cursor — it would reopen the sublist that was open
            # before the hide. Direct/programmatic calls to
            # _handle_widget_enter_event bypass this gate intentionally.
            # Click mode: hover only *navigates* an already-open chain
            # (menubar behavior — sibling switch, nested fan-out); it never
            # opens one from idle. The chain flag lives on the root.
            if not self._auto_open_suppressed():
                if not self._click_mode() or self._get_root_list()._click_chain_open:
                    self._handle_widget_enter_event(widget)

        elif event_type == QtCore.QEvent.Leave:
            # Schedule a deferred hide of this item's sublist (if any),
            # plus the sublist that owns this item (if we're inside one).
            # The engagement re-check at fire time prevents the close
            # when the cursor returns into the hierarchy.
            # Click mode: menus persist until dismissed — no leave-driven
            # hides at all.
            if not self._click_mode():
                if hasattr(widget, "sublist") and widget.sublist.isVisible():
                    self._schedule_sublist_hide(widget)
                if hasattr(self, "parent_item"):
                    self._schedule_sublist_hide(self.parent_item)

        elif event_type == QtCore.QEvent.MouseButtonRelease:
            # Check if widget is a child of this ExpandableList
            if widget in self.get_items():
                # We consume the release so the item's own release handling
                # never runs (the list drives interaction via on_item_interacted).
                # A QAbstractButton item received the press — which sank it and
                # armed its auto-repeat/down state — but will now never see the
                # release, so it would stay visually pressed. Reset it before
                # emitting. Harmless no-op on non-button items (QLabel rows).
                if hasattr(widget, "setDown"):
                    widget.setDown(False)

                # Click mode: a release drives open/close instead of hover.
                # Items are filtered by their OWNING list (installEventFilter
                # in _finalize_widget_setup), so ``self`` here is the list
                # whose layout holds ``widget`` — _handle_widget_enter_event's
                # geometry math runs on the right instance at any depth.
                if self._click_mode():
                    sub = getattr(widget, "sublist", None)
                    if sub is not None and sub.get_items():
                        if sub.isVisible():
                            # Toggle closed; if that emptied the chain, end
                            # the session (filter removal).
                            sub._force_hide_all()
                            QtWidgets.QWidget.hide(sub)
                            root = self._get_root_list()
                            if not root._any_sublist_visible():
                                root._end_click_chain()
                        else:
                            self._begin_click_chain()
                            self._handle_widget_enter_event(widget)
                        return True
                    # Leaf: close the menu FIRST, then activate exactly like
                    # hover mode. Hide-then-dispatch matches the marking
                    # menu's _handle_widget_action order — the slot may open
                    # a modal dialog, and emitting first would leave the
                    # flyout chain hanging over it until the slot returns.
                    self._get_root_list()._force_hide_all()
                    self.on_item_interacted.emit(widget)
                    return True

                self.on_item_interacted.emit(widget)
                return True  # Consume event to prevent double-firing

        return super().eventFilter(widget, event)

    def leaveEvent(self, event):
        """Handle the cursor leaving this list widget.

        If this list is itself a sublist (has ``parent_item``), schedule
        a deferred hide of itself.  The engagement check at fire time
        keeps it open if the cursor returned into the hierarchy.

        Click mode: menus persist until explicitly dismissed — never
        leave-driven.
        """
        if self._click_mode():
            return
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

    from uitk.themes.style_sheet import StyleSheet

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
