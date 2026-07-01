# !/usr/bin/python
# coding=utf-8
import os
import inspect
import warnings
import weakref
from dataclasses import dataclass, field
from typing import Optional, Union, Callable, Dict, Any, Tuple
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk

# Opt-in live diagnostic for hide_on_leave. Set UITK_MENU_LEAVE_DEBUG=1 (e.g.
# via Maya.env so it is present before uitk imports) to have every leave-poll
# tick log why a menu stays open or hides — the only reliable way to pin down a
# real-platform "won't hide" symptom that does not reproduce offscreen. See
# Menu._check_cursor_position.
_LEAVE_DEBUG = bool(os.environ.get("UITK_MENU_LEAVE_DEBUG"))

# From this package:
from uitk.widgets.header import Header
from uitk.widgets.footer import Footer
from uitk.widgets.separator import Separator
from uitk.widgets.mixins.style_sheet import StyleSheet
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.convert import ConvertMixin

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


@dataclass
class MenuConfig:
    """Configuration for Menu initialization.

    This dataclass encapsulates all menu configuration parameters,
    making it easier to create, modify, and extend menu configurations.
    """

    parent: Optional[QtWidgets.QWidget] = None
    name: Optional[str] = None
    trigger_button: Union[QtCore.Qt.MouseButton, str, tuple, list, None] = None
    position: Union[str, QtCore.QPoint, list, tuple, None] = "cursorPos"
    min_item_height: Optional[int] = None
    max_item_height: Optional[int] = None
    fixed_item_height: Optional[int] = None
    add_header: bool = True
    add_footer: bool = True
    add_apply_button: bool = False
    add_defaults_button: bool = False
    hide_on_leave: bool = False
    match_parent_width: bool = True
    ensure_on_screen: bool = True
    extra_attrs: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def for_context_menu(
        cls, parent: Optional[QtWidgets.QWidget] = None, **overrides
    ) -> "MenuConfig":
        """Create config for a context menu."""
        defaults = {
            "parent": parent,
            "trigger_button": "right",
            "position": "cursorPos",
            "fixed_item_height": 20,
            "add_header": False,
            "add_footer": False,
            "match_parent_width": False,
            "hide_on_leave": False,
        }
        return cls(**{**defaults, **overrides})

    @classmethod
    def for_dropdown_menu(
        cls, parent: Optional[QtWidgets.QWidget] = None, **overrides
    ) -> "MenuConfig":
        """Create config for a dropdown menu."""
        defaults = {
            "parent": parent,
            "trigger_button": "none",
            "position": "bottom",
            "hide_on_leave": True,
            "add_apply_button": True,
            "add_header": True,
            "match_parent_width": True,
        }
        return cls(**{**defaults, **overrides})

    @classmethod
    def for_popup_menu(
        cls, parent: Optional[QtWidgets.QWidget] = None, **overrides
    ) -> "MenuConfig":
        """Create config for a popup menu."""
        defaults = {
            "parent": parent,
            "trigger_button": "none",
            "position": "cursorPos",
            "add_header": True,
            "match_parent_width": False,
        }
        return cls(**{**defaults, **overrides})


@dataclass
class _ActionButtonConfig:
    """Internal configuration for action buttons in Menu.

    This dataclass encapsulates all properties needed to create and configure
    an action button within a Menu widget.
    """

    text: str
    callback: Optional[Callable] = None
    tooltip: Optional[str] = None
    enabled: bool = True
    visible: bool = True
    fixed_height: Optional[int] = None


class ActionButtonManager:
    """Manages action buttons for Menu widgets.

    Uses a CollapsableGroup as the container so the actions section
    can be collapsed/expanded by the user.
    """

    def __init__(self, menu_widget: QtWidgets.QWidget):
        """Initialize the action button manager.

        Args:
            menu_widget: The menu widget that owns these buttons
        """
        self.menu = menu_widget
        self._buttons: Dict[str, QtWidgets.QPushButton] = {}
        self._widgets: Dict[str, QtWidgets.QWidget] = {}
        self._container: Optional["CollapsableGroup"] = None
        self._layout: Optional[QtWidgets.QVBoxLayout] = None

    @property
    def container(self) -> QtWidgets.QWidget:
        """Get or create the collapsible action button container."""
        if self._container is None:
            from uitk.widgets.collapsableGroup import CollapsableGroup

            self._container = CollapsableGroup("Menu Actions")
            self._container.setObjectName("actionButtonContainer")
            self._container.restore_state = False
            self._layout = QtWidgets.QVBoxLayout()
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(1)
            self._container.setLayout(self._layout)

        return self._container

    # Backwards-compatible alias — old code that checked ``_separator``
    # still works (always falsy, but won't AttributeError).
    @property
    def _separator(self):
        return None

    def create_button(
        self, button_id: str, config: _ActionButtonConfig
    ) -> QtWidgets.QPushButton:
        """Create an action button with the given configuration."""
        button = QtWidgets.QPushButton(config.text)

        if config.tooltip:
            button.setToolTip(config.tooltip)
        if config.callback:
            button.released.connect(config.callback)

        button.setEnabled(config.enabled)
        button.setVisible(config.visible)

        if config.fixed_height:
            button.setFixedHeight(config.fixed_height)

        button.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        button.setObjectName(f"actionButton_{button_id}")

        self._buttons[button_id] = button
        return button

    def add_button(
        self, button_id: str, config: _ActionButtonConfig, index: int = -1
    ) -> QtWidgets.QPushButton:
        """Add an action button to the container."""
        button = self.create_button(button_id, config)
        _ = self.container  # Ensure container exists

        if index >= 0:
            self._layout.insertWidget(index, button)
        else:
            self._layout.addWidget(button)
        return button

    def add_widget(
        self, widget_id: str, widget: QtWidgets.QWidget, index: int = -1
    ) -> QtWidgets.QWidget:
        """Add an arbitrary widget to the action container.

        Unlike ``add_button``, this accepts any pre-configured QWidget
        (e.g. a WidgetComboBox) and places it into the container layout.
        """
        _ = self.container  # Ensure container exists
        self._widgets[widget_id] = widget

        if index >= 0:
            self._layout.insertWidget(index, widget)
        else:
            self._layout.addWidget(widget)
        return widget

    def get_widget(self, widget_id: str) -> Optional[QtWidgets.QWidget]:
        """Get a managed widget by ID."""
        return self._widgets.get(widget_id)

    def remove_widget(self, widget_id: str) -> bool:
        """Remove a managed widget entirely."""
        widget = self._widgets.pop(widget_id, None)
        if widget:
            if self._layout:
                self._layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
            self._update_container_visibility()
            return True
        return False

    def get_button(self, button_id: str) -> Optional[QtWidgets.QPushButton]:
        """Get an action button by ID."""
        return self._buttons.get(button_id)

    def show_button(self, button_id: str) -> bool:
        """Show an action button."""
        button = self.get_button(button_id)
        if button:
            button.show()
            button.setVisible(True)
            if self._container and not self._container.isVisible():
                self._container.show()
                self._container.setVisible(True)
                self._container.updateGeometry()
                if hasattr(self.menu, "updateGeometry"):
                    self.menu.updateGeometry()
            return True
        return False

    def hide_button(self, button_id: str) -> bool:
        """Hide an action button."""
        button = self.get_button(button_id)
        if button:
            button.hide()
            self._update_container_visibility()
            return True
        return False

    def remove_button(self, button_id: str) -> bool:
        """Remove an action button entirely."""
        button = self._buttons.pop(button_id, None)
        if button:
            if self._layout:
                self._layout.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
            self._update_container_visibility()
            return True
        return False

    def has_visible_items(self) -> bool:
        """Check if any buttons or widgets are currently visible."""
        return any(btn.isVisible() for btn in self._buttons.values()) or any(
            w.isVisible() for w in self._widgets.values()
        )

    # Keep old name as alias for backwards compatibility
    has_visible_buttons = has_visible_items

    def _update_container_visibility(self):
        """Hide container when no items are visible."""
        if not self._container:
            return
        if self.has_visible_items():
            self._container.show()
        else:
            self._container.hide()


class MenuPositioner:
    """Encapsulates menu positioning and width matching logic."""

    @staticmethod
    def center_on_cursor(widget: QtWidgets.QWidget) -> None:
        """Center menu on cursor position."""
        pos = QtGui.QCursor.pos()
        center = QtCore.QPoint(
            pos.x() - (widget.width() / 2),
            pos.y() - (widget.height() / 4),
        )
        widget.move(center)

    @staticmethod
    def position_at_coordinate(
        widget: QtWidgets.QWidget, position: Union[QtCore.QPoint, tuple, list]
    ) -> None:
        """Position menu at specific coordinates."""
        if not isinstance(position, QtCore.QPoint):
            position = QtCore.QPoint(position[0], position[1])
        widget.move(position)

    @staticmethod
    def position_relative_to_widget(
        menu: QtWidgets.QWidget, target_widget: QtWidgets.QWidget, position: str
    ) -> None:
        """Position menu relative to another widget."""
        if position == "cursorPos":
            MenuPositioner.center_on_cursor(menu)
            return

        target_rect = target_widget.rect()
        menu_size = menu.sizeHint()

        positions = {
            "bottom": lambda: target_widget.mapToGlobal(target_rect.bottomLeft()),
            "top": lambda: target_widget.mapToGlobal(
                QtCore.QPoint(
                    target_rect.left(), target_rect.top() - menu_size.height()
                )
            ),
            "right": lambda: target_widget.mapToGlobal(target_rect.topRight()),
            "left": lambda: target_widget.mapToGlobal(
                QtCore.QPoint(target_rect.left() - menu_size.width(), target_rect.top())
            ),
            "center": lambda: target_widget.mapToGlobal(target_rect.center()),
        }

        if position in positions:
            menu.move(positions[position]())
        else:
            # Fallback to cursor position
            MenuPositioner.center_on_cursor(menu)

    @staticmethod
    def apply_width_matching(
        menu: QtWidgets.QWidget,
        anchor_widget: Optional[QtWidgets.QWidget],
        match_parent_width: bool,
        position: Union[str, QtCore.QPoint, tuple, list, None],
        logger: Optional[Any] = None,
    ) -> None:
        """Apply width matching if conditions are met.

        Args:
            menu: The menu widget to resize
            anchor_widget: Widget to match width from
            match_parent_width: Whether width matching is enabled
            position: Current position setting (only applies to "top"/"bottom")
            logger: Optional logger for debug output
        """
        if not match_parent_width:
            return

        if not isinstance(position, str) or position not in ("top", "bottom"):
            return

        if not anchor_widget:
            return

        # Get anchor width
        anchor_width = anchor_widget.width()

        # The issue is that when we use setFixedWidth, Qt includes the border in the total width,
        # but the content area needs to fit within that. Since the menu has a 1px border on each side,
        # the actual content width is (total_width - 2px).
        # To match the anchor width AND show the full content, we need to ensure the menu's
        # total width accounts for both the content and the border.

        # Get the menu's content width (what it wants to be)
        content_width = menu.sizeHint().width()

        # Use whichever is larger: anchor width or content width
        # This ensures we don't clip content when it's wider than the anchor
        # Compute total horizontal padding introduced by layout margins and borders
        def _get_layout(widget):
            """Return the widget's layout, handling shadowed .layout attributes."""
            attr = getattr(widget, "layout", None)
            if attr is None:
                return None
            return attr if not callable(attr) else attr()

        horizontal_padding = 0

        layout = _get_layout(menu)
        if layout:
            margins = layout.contentsMargins()
            horizontal_padding += margins.left() + margins.right()

        frame = getattr(menu, "_frame", None)
        if frame:
            frame_layout = _get_layout(frame)
            if frame_layout:
                margins = frame_layout.contentsMargins()
                horizontal_padding += margins.left() + margins.right()

        central_layout = getattr(menu, "centralWidgetLayout", None)
        if central_layout:
            margins = central_layout.contentsMargins()
            horizontal_padding += margins.left() + margins.right()

        # Account for stylesheet border (1px each side)
        horizontal_padding += 2

        width_from_anchor = anchor_width + horizontal_padding

        target_width = max(width_from_anchor, content_width)

        if menu.width() != target_width:
            menu.setFixedWidth(target_width)
            if logger:
                logger.debug(
                    f"MenuPositioner: Set width to {target_width}px (anchor={anchor_width}px, content={content_width}px)"
                )

    @staticmethod
    def position_and_match_width(
        menu: QtWidgets.QWidget,
        anchor_widget: Optional[QtWidgets.QWidget],
        position: Union[str, QtCore.QPoint, tuple, list, None],
        match_parent_width: bool,
        logger: Optional[Any] = None,
    ) -> None:
        """Position menu and apply width matching in one operation.

        This combines positioning and width matching to avoid duplication.

        Args:
            menu: The menu widget to position
            anchor_widget: Widget to anchor to (optional)
            position: Position relative to anchor or absolute
            match_parent_width: Whether to match anchor width
            logger: Optional logger for debug output
        """
        # Apply positioning. Explicit coordinates win over anchor-relative
        # dispatch — passing a QPoint/tuple/list means "use this position",
        # so the anchor (if any) is informational only. Strings continue to
        # dispatch through the anchor when one is provided ("bottom",
        # "right", etc. are anchor-relative by definition).
        if isinstance(position, (tuple, list, QtCore.QPoint)):
            MenuPositioner.position_at_coordinate(menu, position)
        elif position == "cursorPos":
            MenuPositioner.center_on_cursor(menu)
        elif anchor_widget:
            MenuPositioner.position_relative_to_widget(menu, anchor_widget, position)
        else:
            MenuPositioner.center_on_cursor(menu)

        # Apply width matching
        MenuPositioner.apply_width_matching(
            menu, anchor_widget, match_parent_width, position, logger
        )


class _DismissOnAncestorMove(QtCore.QObject):
    """Hide a popup menu when any window-ancestor of its anchor moves.

    Mirrors the existing ``_install_visibility_filters`` pattern used by
    ``RecentValuesPopup`` / ``PinnedValuesPopup``: walks the anchor's
    parent chain at install time and installs itself as an event filter
    on each ancestor.  On any ``QEvent.Move`` from a top-level window
    ancestor (gated by ``obj.isWindow()`` so layout-driven moves of
    intermediate child widgets don't trigger), the target's ``hide()``
    is invoked.  Pin semantics are honored automatically because
    ``Menu.hide(force=False)`` no-ops when the menu is pinned.
    """

    def __init__(self, target_menu: QtWidgets.QWidget, anchor_widget: QtWidgets.QWidget):
        super().__init__(target_menu)
        self._target = target_menu
        self._watched: list = []
        w = anchor_widget
        while w is not None:
            try:
                w.installEventFilter(self)
                self._watched.append(w)
            except RuntimeError:
                # Widget already deleted; skip.
                pass
            w = w.parentWidget()

    def eventFilter(self, obj, event):
        if (
            event.type() == QtCore.QEvent.Move
            and self._target is not None
            and self._target.isVisible()
            and not getattr(self._target, "is_pinned", False)
        ):
            try:
                if obj.isWindow():
                    self._target.hide()
            except RuntimeError:
                pass
        return False

    def detach(self) -> None:
        """Remove the filter from every watched ancestor and drop refs."""
        for w in self._watched:
            try:
                w.removeEventFilter(self)
            except RuntimeError:
                pass
        self._watched.clear()
        self._target = None


class Menu(QtWidgets.QWidget, AttributesMixin, ptk.LoggingMixin):
    """A custom Qt Widget that serves as a popup menu with additional features.

    The Menu class inherits from QtWidgets.QWidget and provides a customizable
    popup menu with features such as draggable headers and action buttons.
    The menu can be positioned relative to the cursor, a specific coordinate,
    a widget, or its parent.

    Attributes:
        on_item_added (QtCore.Signal): Signal emitted when an item is added to the menu.
        on_item_interacted (QtCore.Signal): Signal emitted when an item in the menu is interacted with.
        on_hidden (QtCore.Signal): Signal emitted when the menu is hidden.
    """

    on_item_added = QtCore.Signal(object)
    on_item_interacted = QtCore.Signal(object)
    on_hidden = QtCore.Signal()

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        name: Optional[str] = None,
        trigger_button: Union[QtCore.Qt.MouseButton, str, tuple, list, None] = None,
        position: Union[str, QtCore.QPoint, list, tuple, None] = "cursorPos",
        min_item_height: Optional[int] = None,
        max_item_height: Optional[int] = None,
        fixed_item_height: Optional[int] = None,
        add_header: bool = True,
        add_footer: bool = True,
        add_apply_button: bool = False,
        add_defaults_button: bool = False,
        hide_on_leave: bool = False,
        match_parent_width: bool = True,
        ensure_on_screen: bool = True,
        empty_message: Optional[str] = "No options",
        empty_timeout_ms: int = 1500,
        log_level: Optional[Union[int, str]] = "WARNING",
        **kwargs,
    ):
        """Initializes a custom qwidget instance that acts as a popup menu.

        The menu can be positioned relative to the cursor, a specific coordinate, a widget, or its parent.
        It can also have a draggable header and an apply button.
        The menu can be styled using the provided keyword arguments.

        Parameters:
            parent (QtWidgets.QWidget, optional): The parent widget. Defaults to None.
            name (str, optional): The name of the menu. Defaults to None.
            trigger_button (QtCore.Qt.MouseButton, str, tuple, list, None): The mouse button(s) that trigger the menu.
                Can be:
                - A Qt mouse button constant (e.g., QtCore.Qt.LeftButton, QtCore.Qt.RightButton)
                - A string: "left", "right", "middle", "back", "forward"
                - "any" to allow any button to trigger the menu
                - "none" or None to disable auto-triggering (menu must be shown manually via .show()) (default)
                - A tuple/list of buttons or strings (e.g., ("left", "right"))
            position (str, optional): The position of the menu. Can be "right", "cursorPos", a coordinate pair, or a widget.
            min_item_height (int, optional): The minimum height of items in the menu. Defaults to None.
            max_item_height (int, optional): The maximum height of items in the menu. Defaults to None.
            fixed_item_height (int, optional): The fixed height of items in the menu. Defaults to None.
            add_header (bool, optional): Whether to add a draggable header to the menu. Defaults to True.
            add_footer (bool, optional): Whether to add a footer with size grip. Defaults to True.
            add_apply_button (bool, optional): Whether to add an apply button. Defaults to False.
                The apply button will emit the parent's 'clicked' signal if available.
            add_defaults_button (bool, optional): Whether to add a 'Restore Defaults' button. Defaults to False.
                The button is only shown when the menu contains stateful option widgets
                (checkboxes, spinboxes, combos, etc.).
            hide_on_leave (bool, optional): Whether to automatically hide the menu when the mouse leaves. Defaults to False.
            match_parent_width (bool, optional): Whether to match the parent widget's width when using positioned menus
                (e.g., position="bottom"). Defaults to True. Only applies when position is relative to parent (not "cursorPos").
            ensure_on_screen (bool, optional): Whether to ensure the menu is fully on screen when shown. Defaults to True.
            **kwargs: Additional keyword arguments to set attributes on the menu.

        Example:
                # Using string button names (recommended for readability)
                menu = Menu(parent=parent_widget, name="MyMenu",
                           trigger_button="right", position="cursorPos")

                # Using Qt constants (also valid)
                menu = Menu(parent=parent_widget, name="MyMenu",
                           trigger_button=QtCore.Qt.RightButton, position="cursorPos")

                # Multiple buttons
                menu = Menu(parent=parent_widget, trigger_button=("left", "right"))

                # Any button triggers
                menu = Menu(parent=parent_widget, trigger_button="any")

                # No auto-trigger (manual show only)
                menu = Menu(parent=parent_widget, trigger_button="none")

                menu.add("QLabel", setText="Label A")
                menu.add("QPushButton", setText="Button A")
                menu.show()
        """
        super().__init__(parent)

        if name is not None:
            if not isinstance(name, str):
                raise TypeError(f"Expected 'name' to be a string, got {type(name)}")
            self.setObjectName(name)

        self.logger.setLevel(log_level)

        # Core event state
        self._event_filters_installed = False
        self._mouse_has_entered = False
        self._current_anchor_widget = None
        self._active_window_before_show = None
        self._filter_target = None
        self._pending_event_filter_install = False
        self._parent_signal_source: Optional[Tuple[QtWidgets.QWidget, str]] = None
        self._pending_trigger_hook = False

        # Per-item _register_with_main_window calls are coalesced into a
        # single deferred drain (see _schedule_registration / _drain_pending_registrations).
        # Order of registration is preserved; the contract is "after add() returns",
        # not "one tick per item" — see test_register_with_main_window_deferred_not_synchronous.
        self._pending_registrations: list = []
        self._registration_drain_scheduled: bool = False
        # Owning MainWindow, captured (weakly) while the menu is still nested
        # under its host so deferred registration survives the menu reparenting
        # to a top-level popup on show — see _resolve_registration_window.
        self._registration_window_ref: Optional["weakref.ref"] = None

        # ``add()`` blocks signals for the duration of the (potentially
        # recursive, bulk) insert so Qt's internal layout churn doesn't
        # cascade.  ``on_item_added`` emits land in this queue while blocked
        # and are flushed once the OUTERMOST add() unwinds (tracked by
        # ``_add_depth``) and the menu is settled — otherwise the documented
        # signal never reaches listeners.
        self._pending_item_added_emits: list = []
        self._add_depth: int = 0

        # Widget structure
        self._layout: Optional[QtWidgets.QVBoxLayout] = None
        self.gridLayout: Optional[QtWidgets.QGridLayout] = None
        self.centralWidgetLayout: Optional[QtWidgets.QVBoxLayout] = None
        self._central_widget: Optional[QtWidgets.QWidget] = None
        self._frame_layout: Optional[QtWidgets.QVBoxLayout] = None
        self._pending_title: Optional[str] = None
        self.style: Optional[StyleSheet] = None
        self.header: Optional[Header] = None
        self.footer: Optional[Footer] = None

        # Helpers and caches
        self._button_manager = ActionButtonManager(self)
        self._leave_timer: Optional[QtCore.QTimer] = None
        self._last_parent_geometry = None
        self._cached_menu_position = None
        self._popup_configured = False  # Track if popup setup has been done
        self._tracked_as_menu = False  # Registered with owning MainWindow.menus()
        self._dismiss_on_move_filter: Optional[_DismissOnAncestorMove] = None
        self._activating_chain = False  # Re-entrancy guard for sizeHint activation

        # Transient popup family: child popups (option-menu dropdowns, context
        # menus, value popups) opened from within this menu that should keep it
        # alive while the pointer is over them and be torn down with it. Held
        # weakly and pruned lazily, so a child destroyed/hidden without notice
        # is cleaned up on next access. See adopt_transient / _pointer_in_family.
        self._transient_children: list = []  # list[weakref.ref[QWidget]]
        # hide_on_leave debounce: require this many consecutive out-of-family
        # samples before hiding, so crossing the gap between this menu and a
        # child popup (or a brief excursion) can't dismiss it. Default 1 keeps
        # the legacy single-sample behavior; adopt_transient raises it so only
        # menus that actually spawn children pay the small grace.
        self.leave_grace_samples: int = 1
        self._outside_samples: int = 0
        # A menu can open away from the cursor (anchored to a button the user
        # just clicked), so its body is never under the pointer. It must still
        # auto-dismiss if the user never reaches it — otherwise a hide_on_leave
        # menu opened-but-ignored lingers forever, because the "entered" guard
        # never arms. Give the never-entered case a longer grace (time to reach
        # the menu) than a deliberate leave after entering.
        self.unentered_grace_samples: int = 15  # ~1.5s at the 100ms poll

        # Data containers and flags
        self.widget_data: Dict[QtWidgets.QWidget, Any] = {}
        self.prevent_hide = False
        self._persistent_mode = False
        self._persistent_state: Dict[str, Any] = {}
        self._persistent_hide_button: Optional[QtWidgets.QPushButton] = None

        # Configuration attributes
        self.trigger_button = trigger_button
        self.position = position
        self.min_item_height = min_item_height
        self.max_item_height = max_item_height
        self.fixed_item_height = fixed_item_height
        self._add_defaults_button = add_defaults_button
        self._add_presets = False
        self.add_header = add_header
        self.add_footer = add_footer
        self.add_apply_button = add_apply_button
        self.match_parent_width = match_parent_width

        self._hide_on_leave = False
        self.hide_on_leave = hide_on_leave
        self.ensure_on_screen = ensure_on_screen

        # Empty-state behavior: when shown with no items, display a brief
        # message ("No options" by default) then auto-hide.  Set
        # ``empty_message=None`` or ``empty_timeout_ms=0`` to disable.
        self._empty_message = empty_message
        self._empty_timeout_ms = max(0, int(empty_timeout_ms))
        self._empty_placeholder: Optional[QtWidgets.QLabel] = None
        self._empty_timer: Optional[QtCore.QTimer] = None

        # Base styling handled via QSS type selectors
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.setMinimumWidth(147)
        if kwargs:
            self.set_attributes(**kwargs)

        # Build the scaffold immediately; chrome (Header/Footer) is deferred to first show.
        self.init_layout()
        self.style = StyleSheet(self, log_level="WARNING")

        # Popup setup (Qt.Tool|FramelessWindowHint reparent + WA_* attributes)
        # is deferred until the menu is actually shown — running it during
        # ``__init__`` creates an OS-level Tool window per Menu, which on
        # Windows produces a brief WM-visible artifact (a flash) for every
        # option_box menu created during ``register_children``.  Construction
        # leaves the Menu as a hidden child widget; ``show_as_popup`` and
        # ``showEvent`` both call ``_setup_as_popup`` (idempotent via
        # ``_popup_configured``) before the menu becomes visible.
        #
        # Explicit hide() prevents Qt's "auto-show with parent" behavior:
        # without it, ``OptionBox.wrap``'s ``container.show()`` cascades to
        # the Menu via its parent chain (Menu → button → container) and
        # fires ``showEvent`` mid-wrap — defeating the whole point of
        # deferring popup setup.  Calling ``hide()`` flips the widget's
        # ``WA_WState_ExplicitShowHide`` attribute so the cascade skips it.
        # Use super().hide() rather than self.hide() to bypass the
        # pin-check + signal-emitting override (which doesn't apply at
        # construction time and would emit ``on_hidden`` from the ctor).
        super().hide()

    @classmethod
    def create_context_menu(
        cls, parent: Optional[QtWidgets.QWidget] = None, **overrides
    ):
        """Factory method: Create a standalone context menu with sensible defaults.

        Args:
            parent: Parent widget
            **overrides: Override any default parameters

        Returns:
            Menu: Configured context menu instance

        Example:
            menu = Menu.create_context_menu(widget)
            menu.add("Copy")
            menu.add("Paste")
        """
        config = MenuConfig.for_context_menu(parent, **overrides)
        return cls.from_config(config)

    @classmethod
    def create_dropdown_menu(
        cls, parent: Optional[QtWidgets.QWidget] = None, **overrides
    ):
        """Factory method: Create a dropdown menu for option boxes.

        Args:
            parent: Parent widget (typically the wrapped widget)
            **overrides: Override any default parameters
        """

        config = MenuConfig.for_dropdown_menu(parent, **overrides)
        return cls.from_config(config)

    @classmethod
    def from_config(cls, config: MenuConfig):
        """Create a Menu from a MenuConfig object.

        This allows for more flexible configuration and better testability.

        Args:
            config: Menu configuration descriptor

        Returns:
            Menu: Configured menu instance
        """

        return cls(
            parent=config.parent,
            name=config.name,
            trigger_button=config.trigger_button,
            position=config.position,
            min_item_height=config.min_item_height,
            max_item_height=config.max_item_height,
            fixed_item_height=config.fixed_item_height,
            add_header=config.add_header,
            add_footer=config.add_footer,
            add_apply_button=config.add_apply_button,
            add_defaults_button=config.add_defaults_button,
            hide_on_leave=config.hide_on_leave,
            match_parent_width=config.match_parent_width,
            ensure_on_screen=config.ensure_on_screen,
            **config.extra_attrs,
        )

    @staticmethod
    def run_modal(
        content_fn,
        parent=None,
        title="",
        buttons=None,
        size=None,
        min_size=None,
        center=True,
        **menu_kwargs,
    ):
        """Show a themed modal Menu popup, block until dismissed.

        Handles all boilerplate: Menu creation with header/footer, button
        wiring, ``QEventLoop`` blocking, and screen centering.  The caller
        supplies a *content_fn* callback to populate the menu and a *buttons*
        spec to define the action bar.

        Parameters:
            content_fn (callable): ``content_fn(menu, state)`` — called after
                the Menu is constructed so the caller can add widgets via
                ``menu.add()`` and store result data in *state*.
            parent (QWidget, optional): Parent widget.  The menu is parented
                to ``parent.window()`` to avoid layout side-effects.
            title (str): Header title text.
            buttons (dict or list, optional): Action buttons.  Accepts:

                * **dict** ``{text: action}`` — ordered by insertion.
                * **list of dicts** ``[{"text": ..., "action": ...,
                  "callback": ..., "tooltip": ...}]`` for full control.

                *action* may be ``"accept"`` (set accepted, close),
                ``"reject"`` (close), or a ``callable(menu, state)`` for
                fully custom behaviour (the callable decides whether to
                close).  Defaults to ``{"OK": "accept", "Cancel": "reject"}``.

                When *action* is ``"accept"`` or ``"reject"``, an optional
                *callback* ``(menu, state) -> bool | None`` runs before
                the default behaviour.  Returning ``False`` vetoes the
                default (e.g. prevents closing on validation failure).
            size (tuple[int, int], optional): Initial ``(width, height)``.
            min_size (tuple[int, int], optional): Minimum ``(width, height)``.
            center (bool): Centre the popup on the screen at the cursor.
                Default ``True``.
            **menu_kwargs: Extra keyword arguments forwarded to :class:`Menu`.

        Returns:
            dict or None: The *state* dict (with ``"accepted": True``) when
            the user accepts, or ``None`` on rejection / dismissal.

        Example::

            def build(menu, state):
                tree = QtWidgets.QTreeWidget()
                menu.add(tree)
                state["tree"] = tree

            result = Menu.run_modal(
                build,
                parent=widget,
                title="Pick Items",
                buttons={"Import": "accept", "Cancel": "reject"},
                size=(460, 440),
            )
            if result:
                print(result["tree"].topLevelItemCount())
        """
        state: Dict[str, Any] = {"accepted": False}
        loop = QtCore.QEventLoop()

        top_parent = parent.window() if parent else None

        defaults: Dict[str, Any] = dict(
            trigger_button="none",
            position="cursorPos",
            add_header=True,
            add_footer=True,
            add_apply_button=False,
            match_parent_width=False,
            fixed_item_height=None,
        )
        defaults.update(menu_kwargs)

        menu = Menu(parent=top_parent, name=title, **defaults)
        # Modal dialogs configure the header up front and show immediately, so
        # build the deferred chrome now rather than waiting for first show.
        menu.ensure_chrome()

        if min_size:
            menu.setMinimumSize(*min_size)
        if size:
            menu.resize(*size)

        if menu.header:
            menu.header.config_buttons("hide")
            if title:
                menu.header.setTitle(title)

        # Let the caller populate the menu and configure state.
        content_fn(menu, state)

        # -- action buttons ------------------------------------------------
        if buttons is None:
            buttons = {"OK": "accept", "Cancel": "reject"}

        if isinstance(buttons, dict):
            button_list = [{"text": t, "action": a} for t, a in buttons.items()]
        else:
            button_list = list(buttons)

        def _make_callback(act, m, s, custom_cb=None):
            """Build a zero-arg callback compatible with Qt signal slots.

            When *custom_cb* is provided alongside a standard action
            (``"accept"`` / ``"reject"``), it runs first.  If it returns
            ``False``, the default behaviour is skipped.
            """
            if act == "accept":

                def _cb():
                    if custom_cb is not None and custom_cb(m, s) is False:
                        return
                    s["accepted"] = True
                    m.hide(force=True)

            elif act == "reject":

                def _cb():
                    if custom_cb is not None and custom_cb(m, s) is False:
                        return
                    m.hide(force=True)

            elif callable(act):

                def _cb():
                    act(m, s)

            else:
                raise ValueError(f"Invalid button action: {act!r}")
            return _cb

        for btn_spec in button_list:
            text = btn_spec["text"]
            action = btn_spec["action"]
            tooltip = btn_spec.get("tooltip", "")
            custom_cb = btn_spec.get("callback")

            menu._button_manager.add_button(
                text.lower().replace(" ", "_"),
                _ActionButtonConfig(
                    text=text,
                    callback=_make_callback(action, menu, state, custom_cb),
                    tooltip=tooltip,
                    fixed_height=26,
                ),
            )

        menu.centralWidgetLayout.addWidget(menu._button_manager.container)

        # -- modal blocking ------------------------------------------------
        menu.on_hidden.connect(loop.quit)
        menu.show()

        if center:
            screen = QtWidgets.QApplication.screenAt(QtGui.QCursor.pos())
            if screen:
                geo = screen.availableGeometry()
                menu.move(
                    geo.center().x() - menu.width() // 2,
                    geo.center().y() - menu.height() // 2,
                )

        loop.exec_()

        if not state["accepted"]:
            return None
        return state

    def _should_trigger(self, button: QtCore.Qt.MouseButton) -> bool:
        """Check if the given button should trigger the menu.

        This centralizes all button-checking logic in one place.

        Parameters:
            button: The mouse button that was pressed

        Returns:
            True if this button should trigger the menu, False otherwise
        """
        # False sentinel = no auto-trigger (menu must be shown manually)
        if self.trigger_button is False:
            return False

        # No trigger button restriction - allow any button
        if self.trigger_button is None:
            return True

        # Single button restriction
        if isinstance(self.trigger_button, QtCore.Qt.MouseButton):
            return button == self.trigger_button

        # Multiple buttons allowed (tuple)
        if isinstance(self.trigger_button, (tuple, list)):
            return button in self.trigger_button

        return False

    @property
    def trigger_button(self) -> Union[QtCore.Qt.MouseButton, tuple, None, bool]:
        """Get the current trigger button(s).

        Returns:
            QtCore.Qt.MouseButton: Single button constant
            tuple: Multiple button constants
            None: Any button triggers
            False: No auto-trigger (manual show only)
        """
        return self._trigger_button

    @trigger_button.setter
    def trigger_button(
        self, value: Union[QtCore.Qt.MouseButton, str, tuple, list, None]
    ) -> None:
        """Set the trigger button(s).

        Accepts Qt constants, strings ("left", "right", "middle", "any", "none"), or tuples/lists.

        Parameters:
            value: Single button (Qt constant or string), tuple/list of buttons,
                  "any" for any button, or "none" to disable auto-triggering
        """
        # Use ConvertMixin to normalize the value
        try:
            self._trigger_button = ConvertMixin.to_qmousebutton(value)
        except ValueError as e:
            self.logger.warning(f"{e}. Defaulting to LeftButton.")
            self._trigger_button = QtCore.Qt.LeftButton

        # Left-click menus act like instant-action menus:
        # - No apply button (actions execute immediately)
        # - Auto-hide when mouse leaves (like standard menus)
        if self._trigger_button == QtCore.Qt.LeftButton:
            self.add_apply_button = False
            self.hide_on_leave = True

        # Keep trigger event filters in sync with the trigger_button setting
        if self._trigger_button is False:
            self._uninstall_event_filters()
        else:
            # Install filters immediately if we already have content/parent
            if self.contains_items and not (
                self._event_filters_installed or self._parent_signal_source
            ):
                self._ensure_trigger_hook()

    @property
    def presets(self):
        """Lazy-initialized PresetManager namespace for saving/loading named presets.

        The simplest way to enable presets is via :attr:`add_presets`::

            widget.menu.add_presets = True
            widget.menu.presets.preset_dir = "~/.myapp/presets"  # optional

        For advanced use, call ``setup()`` directly::

            widget.menu.presets.setup(preset_dir="~/.myapp/presets")

        Returns:
            PresetManager: The preset manager bound to this menu.
        """
        if not hasattr(self, "_preset_manager"):
            from uitk.widgets.mixins.preset_manager import PresetManager

            self._preset_manager = PresetManager(parent=self)
        return self._preset_manager

    @presets.setter
    def presets(self, _):
        """No-op setter so the switchboard can harmlessly reassign."""
        pass

    @property
    def hide_on_leave(self) -> bool:
        """Get whether menu auto-hides when mouse leaves.

        Returns:
            bool: True if menu auto-hides on leave, False otherwise
        """
        return self._hide_on_leave

    @hide_on_leave.setter
    def hide_on_leave(self, value: bool) -> None:
        """Set whether menu auto-hides when mouse leaves.

        Parameters:
            value: True to enable auto-hide on leave, False to disable
        """
        self._hide_on_leave = bool(value)

        if self._hide_on_leave:
            if self._leave_timer is None:
                self._setup_leave_timer()
        else:
            if self._leave_timer is not None:
                self._leave_timer.stop()
                self._leave_timer.deleteLater()
                self._leave_timer = None

    # ------------------------------------------------------------------
    # Persistent mode (keep menu visible even when parent hides)
    # ------------------------------------------------------------------

    def enable_persistent_mode(self, hide_button_tooltip: str = "Hide menu") -> None:
        """Keep the menu visible until the user explicitly hides it.

        This temporarily disables all automatic hide behaviour and injects a
        dedicated Hide button into the header. Call :meth:`disable_persistent_mode`
        to restore the original behaviour.

        Args:
            hide_button_tooltip: Tooltip shown on the injected Hide button.
        """
        if self._persistent_mode:
            return

        self.logger.debug("Menu.enable_persistent_mode: Activating persistent mode")

        # Snapshot state so we can restore it later
        self._persistent_state = {
            "prevent_hide": self.prevent_hide,
            "hide_on_leave": self.hide_on_leave,
            "had_header": self.add_header or bool(self.header),
        }

        self._persistent_mode = True

        # Block auto-hiding behaviour while in persistent mode
        self.prevent_hide = True
        self.hide_on_leave = False

        # Ensure the menu has a header to host the hide button. _ensure_chrome
        # builds it into the frame layout for add_header=True menus; the fallback
        # below injects one for headerless (add_header=False) menus.
        self._ensure_chrome()
        if not self.header:
            self.header = Header(config_buttons=["pin"])
            if self.centralWidgetLayout:
                self.centralWidgetLayout.insertWidget(0, self.header)

        self._install_persistent_hide_button(hide_button_tooltip)

    def disable_persistent_mode(self) -> None:
        """Restore default hide behaviour after persistent mode."""
        if not self._persistent_mode:
            return

        self.logger.debug("Menu.disable_persistent_mode: Restoring default behaviour")

        original = getattr(self, "_persistent_state", {}) or {}

        # Restore behaviour flags before removing the hide guard
        self.prevent_hide = original.get("prevent_hide", False)
        self.hide_on_leave = original.get("hide_on_leave", False)

        self._remove_persistent_hide_button()

        # Remove temporary header if we created one
        if not original.get("had_header", True) and self.header:
            if self.centralWidgetLayout:
                self.centralWidgetLayout.removeWidget(self.header)
            self.header.deleteLater()
            self.header = None

        self._persistent_mode = False
        self._persistent_state = {}

    @property
    def is_persistent_mode(self) -> bool:
        """Return True when persistent mode is active."""
        return self._persistent_mode

    def _install_persistent_hide_button(self, tooltip: str) -> None:
        """Ensure a dedicated hide button exists in persistent mode."""
        if not self.header:
            self.logger.warning(
                "Menu._install_persistent_hide_button: Cannot install without a header"
            )
            return

        # Remove any previous custom hide button before creating a new one
        self._remove_persistent_hide_button()

        hide_button = self.header.create_button(
            "hide.svg",
            self._on_persistent_hide_clicked,
            button_type="persistent_hide_button",
        )
        hide_button.setObjectName("persistentHideButton")
        hide_button.setToolTip(tooltip)
        hide_button.setProperty("class", "PersistentHideButton")
        hide_button.setAutoDefault(False)
        hide_button.setDefault(False)

        self.header.container_layout.addWidget(hide_button)
        self.header.buttons["persistent_hide_button"] = hide_button
        self.header.container_layout.invalidate()
        self.header.trigger_resize_event()

        self._persistent_hide_button = hide_button

    def _remove_persistent_hide_button(self) -> None:
        """Remove the injected persistent hide button, if any."""
        button = self._persistent_hide_button
        if not button:
            return

        if self.header:
            try:
                self.header.container_layout.removeWidget(button)
            except Exception:
                pass
            self.header.buttons.pop("persistent_hide_button", None)

        button.hide()
        button.deleteLater()
        self._persistent_hide_button = None

    def _on_persistent_hide_clicked(self) -> None:
        """Handle clicks on the injected Hide button."""
        # Restore default behaviour, then hide immediately
        self.disable_persistent_mode()
        self.hide(force=True)

    def _ensure_layout_created(self):
        """Ensure layout is created (called when first item is added)."""
        if self._layout is None or self.gridLayout is None:
            self.init_layout()
            self.logger.debug("Menu._ensure_layout_created: Layout created")

    def _ensure_style_initialized(self):
        """Ensure stylesheet is initialized (called on first show)."""
        if self.style is None:
            self.style = StyleSheet(self, log_level="WARNING")
            self.logger.debug("Menu._ensure_style_initialized: StyleSheet created")

    def _ensure_timer_created(self):
        """Ensure timer is created if hide_on_leave is enabled (called on first show)."""
        if self.hide_on_leave and self._leave_timer is None:
            self._setup_leave_timer()
            self.logger.debug(
                "Menu._ensure_timer_created: Timer created for hide_on_leave"
            )

    def _get_anchor_widget(self) -> Optional[QtWidgets.QWidget]:
        """Get the effective anchor widget (parent or filter target)."""
        return self.parent() or self._filter_target

    def _get_parent_signal_slot(self, signal_name: str):
        """Get the appropriate slot for a parent signal name."""
        if signal_name in ("clicked", "pressed"):
            return self._on_parent_triggered
        return None

    def _disconnect_parent_signal(self) -> None:
        if not self._parent_signal_source:
            return

        parent, signal_name = self._parent_signal_source
        slot = self._get_parent_signal_slot(signal_name)
        if parent and slot:
            # Use warnings filter to suppress PyQt's RuntimeWarning when slot wasn't connected
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    getattr(parent, signal_name).disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        self.logger.debug(
            f"Menu._disconnect_parent_signal: Disconnected {signal_name} from {parent}"
        )
        self._parent_signal_source = None

    def _connect_parent_signal(self, parent: QtWidgets.QWidget) -> bool:
        """Attempt to hook into the parent's Qt signal for triggering."""
        # Always disconnect any previous connection before wiring a new one
        self._disconnect_parent_signal()

        # Try to find a suitable signal
        signal_name = None
        if hasattr(parent, "clicked"):
            signal_name = "clicked"
        elif hasattr(parent, "pressed"):
            signal_name = "pressed"
        else:
            return False

        slot = self._on_parent_triggered
        signal = getattr(parent, signal_name)

        # Disconnect any existing connection and connect the slot
        # Use warnings filter to suppress PyQt's RuntimeWarning when slot wasn't connected
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

        try:
            signal.connect(slot)
        except (TypeError, RuntimeError):
            return False

        self._parent_signal_source = (parent, signal_name)
        self.logger.debug(
            f"Menu._connect_parent_signal: Connected {signal_name} signal on {parent}"
        )
        return True

    def _remove_parent_event_filter(self) -> None:
        if self._event_filters_installed:
            try:
                self.removeEventFilter(self)
            except Exception:
                pass

        if self._filter_target:
            try:
                self._filter_target.removeEventFilter(self)
            except Exception:
                pass
            self._filter_target = None

        self._event_filters_installed = False
        self._pending_event_filter_install = False

    def _ensure_trigger_hook(self) -> None:
        """Ensure the menu connects to its trigger source (signal or event filter)."""
        if self._trigger_button is False:
            self._disconnect_parent_signal()
            if self._event_filters_installed or self._filter_target:
                self._remove_parent_event_filter()
            self._pending_trigger_hook = False
            self._pending_event_filter_install = False
            return

        parent = self._get_anchor_widget()
        if parent is None:
            self._pending_trigger_hook = True
            self._pending_event_filter_install = True
            self.logger.debug(
                "Menu._ensure_trigger_hook: Parent unavailable, deferring"
            )
            return

        # Prefer signal-based triggering for left-button clicks
        if (
            self._trigger_button == QtCore.Qt.LeftButton
            and self._connect_parent_signal(parent)
        ):
            if self._event_filters_installed or self._filter_target:
                self._remove_parent_event_filter()
            self._pending_trigger_hook = False
            self._pending_event_filter_install = False
            return

        # Fallback to event filters when signals aren't available or for non-left triggers
        self._disconnect_parent_signal()

        if not self._event_filters_installed:
            self.installEventFilter(self)
            parent.installEventFilter(self)
            self._filter_target = parent
            self._event_filters_installed = True
            self.logger.debug(
                f"Menu._ensure_trigger_hook: Installed event filter on {parent}"
            )
        elif self._filter_target is not parent:
            if self._filter_target:
                try:
                    self._filter_target.removeEventFilter(self)
                except Exception:
                    pass
            parent.installEventFilter(self)
            self._filter_target = parent
            self.logger.debug(
                f"Menu._ensure_trigger_hook: Updated event filter target to {parent}"
            )

        self._pending_trigger_hook = False
        self._pending_event_filter_install = False

    def _uninstall_event_filters(self):
        """Remove any trigger hooks (signals or event filters)."""
        if not self._event_filters_installed and not self._parent_signal_source:
            self._pending_event_filter_install = False
            self._pending_trigger_hook = False
            return

        self._disconnect_parent_signal()
        if self._event_filters_installed or self._filter_target:
            self._remove_parent_event_filter()

        self._pending_event_filter_install = False
        self._pending_trigger_hook = False
        self.logger.debug("Menu._uninstall_event_filters: Trigger hooks removed")

    def _on_parent_triggered(self, checked: bool = False) -> None:  # type: ignore[override]
        """Handle parent widget signal (clicked or pressed)."""
        if self.is_pinned:
            return
        self.trigger_from_widget(self._get_anchor_widget(), button=QtCore.Qt.LeftButton)

    # Alias for backward compatibility
    _install_event_filters = _ensure_trigger_hook

    def _install_dismiss_on_move_filter(self, anchor_widget) -> None:
        """Install (or replace) the dismiss-on-ancestor-move filter.

        Detaches any previous filter first so re-shows don't accumulate
        watchers.  Bound to ``anchor_widget``'s parent chain; safe to call
        with ``None`` (no-op) if the menu has no anchor.
        """
        existing = getattr(self, "_dismiss_on_move_filter", None)
        if existing is not None:
            existing.detach()
            self._dismiss_on_move_filter = None
        if anchor_widget is None:
            return
        self._dismiss_on_move_filter = _DismissOnAncestorMove(
            target_menu=self, anchor_widget=anchor_widget
        )

    def _detach_dismiss_on_move_filter(self) -> None:
        existing = getattr(self, "_dismiss_on_move_filter", None)
        if existing is not None:
            existing.detach()
            self._dismiss_on_move_filter = None

    def _setup_as_popup(self):
        """Configure this menu as a popup window.

        Only runs once to avoid repeated reparenting issues.
        """
        if self._popup_configured:
            return

        self._popup_configured = True

        # Store current parent before changing window flags
        parent_widget = self.parentWidget()
        flags = QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint

        # Use a single setParent(parent, flags) call to avoid double native
        # window recreation (setWindowFlags alone recreates the handle, then
        # setParent with flags would recreate it again).
        if parent_widget is not None:
            self.setParent(parent_widget, flags)
        else:
            # If no parent, try to parent to the active window
            try:
                app = QtWidgets.QApplication.instance()
                if app:
                    active_window = app.activeWindow()
                    if active_window and active_window != self:
                        self.setParent(active_window, flags)
                        self.logger.debug(
                            f"Menu._setup_as_popup: Parented to active window {active_window}"
                        )
                    else:
                        self.setWindowFlags(flags)
            except Exception as e:
                self.setWindowFlags(flags)
                self.logger.debug(
                    f"Menu._setup_as_popup: Could not parent to active window: {e}"
                )

        # Set attributes after reparenting so they survive window handle recreation
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)

    def _ensure_on_screen(self) -> None:
        """Moves the menu to be fully visible on the screen if it is partially off-screen."""
        # Get the menu's frame geometry (including title bar and borders)
        frame_geo = self.frameGeometry()

        # Find the screen that contains the center of the menu
        screen = None
        if hasattr(QtWidgets.QApplication, "screenAt"):
            screen = QtWidgets.QApplication.screenAt(frame_geo.center())

        # If center is off-screen, find the screen with the most overlap
        if not screen:
            max_area = 0
            for s in QtWidgets.QApplication.screens():
                intersect = frame_geo.intersected(s.geometry())
                area = intersect.width() * intersect.height()
                if area > max_area:
                    max_area = area
                    screen = s

        if not screen:
            screen = QtWidgets.QApplication.primaryScreen()

        if not screen:
            return

        # Get the available geometry of the screen (excluding taskbars, etc.)
        screen_geo = screen.availableGeometry()

        # Calculate new position
        x = frame_geo.x()
        y = frame_geo.y()
        width = frame_geo.width()
        height = frame_geo.height()

        # Adjust X
        if x + width > screen_geo.right():
            x = screen_geo.right() - width
        if x < screen_geo.left():
            x = screen_geo.left()

        # Adjust Y
        if y + height > screen_geo.bottom():
            y = screen_geo.bottom() - height
        if y < screen_geo.top():
            y = screen_geo.top()

        # Only move if necessary
        if x != frame_geo.x() or y != frame_geo.y():
            self.move(x, y)

    def setVisible(self, visible: bool) -> None:
        """Override to apply deferred popup setup before becoming visible.

        Every visibility change in Qt routes through ``setVisible``
        (including ``show()``, ``hide()``, ``setVisible``, and parent-
        cascade auto-show on widgets that haven't had ``hide()`` called
        explicitly).  Putting the popup-setup hook here covers every path
        — direct ``setVisible(True)``, ``Menu.show()``, ``show_as_popup``
        — without separate overrides for each.

        Order is critical: ``_setup_as_popup`` calls ``setWindowFlags``
        which Qt documents as hiding the widget.  Running it BEFORE
        ``super().setVisible(True)`` means the hide happens while the
        widget is still hidden (no-op), then super() makes it visible
        with Tool flags applied.  Running it AFTER would re-hide the
        widget mid-show.

        ``_prepare_for_show`` runs the lazy first-show layout setup
        (apply button, defaults button, presets combo, height resize)
        BEFORE the widget becomes visible — historically these ran in
        ``showEvent`` which fires AFTER super().setVisible(True), causing
        a visible flash as buttons/sizing changed on screen.  Running
        them here keeps the menu hidden until layout is final.

        Idempotent — both helpers no-op once their work is done.
        """
        if visible:
            self._setup_as_popup()
            if not self.contains_items:
                self._add_empty_placeholder()
                if self._empty_timeout_ms > 0:
                    if self._empty_timer is None:
                        self._empty_timer = QtCore.QTimer(self)
                        self._empty_timer.setSingleShot(True)
                        self._empty_timer.timeout.connect(self._on_empty_timeout)
                    self._empty_timer.start(self._empty_timeout_ms)
            self._prepare_for_show()
        else:
            if self._empty_timer is not None:
                self._empty_timer.stop()
            self._remove_empty_placeholder()
        super().setVisible(visible)

    def _prepare_for_show(self) -> None:
        """Run lazy first-show layout setup while the menu is still hidden.

        Each block is gated by an idempotency check so this is safe to
        call on every show — only the first call does work.  Splitting
        these out of ``showEvent`` is the difference between a clean
        appearance and the "rapid flashing window" users see when apply
        buttons / defaults buttons / size adjustments fire visibly.
        """
        # Build the deferred chrome (Header/Footer) first, while still hidden,
        # so the apply/defaults setup and height passes below measure the final layout.
        self._ensure_chrome()

        if (
            self.contains_items
            and self._trigger_button is not False
            and not (self._event_filters_installed or self._parent_signal_source)
        ):
            self._ensure_trigger_hook()

        if self.add_defaults_button and not self._button_manager.get_button("defaults"):
            self._setup_defaults_button()
            self._update_defaults_button_visibility()
        elif self.add_defaults_button:
            self._update_defaults_button_visibility()

        self._ensure_style_initialized()
        self._ensure_timer_created()

        if self.add_presets and not self._button_manager.get_widget("presets"):
            self._setup_presets()

        if self.add_apply_button and not self._button_manager.get_button("apply"):
            self._setup_apply_button()
            self._update_apply_button_visibility()
            if self._layout:
                self._layout.invalidate()
                self._layout.activate()
            self.adjustSize()
        elif self.add_apply_button:
            self._update_apply_button_visibility()

        self._resize_height_to_content()

    def show(self) -> None:
        """Show the menu.

        Visibility setup is centralized in :meth:`setVisible`; this
        override exists only to run the post-show on-screen check.

        ``_ensure_on_screen`` runs SYNCHRONOUSLY here (same event-loop
        tick as ``super().show()``) so any position correction completes
        before the paint event fires.  Earlier versions used
        ``QTimer.singleShot(0, ...)`` to defer the check until after
        the native window's frameGeometry stabilized; the deferred
        timer fired AFTER the first paint, producing a visible "menu
        appears, then jumps into place" flash on multi-monitor / off-
        screen-anchor scenarios.  Synchronous + same tick = correct
        position is used by the very first paint.
        """
        super().show()
        if self.ensure_on_screen:
            self._ensure_on_screen()

    def show_as_popup(
        self,
        anchor_widget: Optional[QtWidgets.QWidget] = None,
        position: Union[str, QtCore.QPoint, tuple, list] = "bottom",
    ) -> None:
        """Show this menu as a popup at the specified position.

        Args:
            anchor_widget: Widget to anchor the menu to (optional)
            position: Position relative to anchor widget or "cursorPos"
        """
        self.logger.debug(
            f"Menu.show_as_popup: anchor_widget={anchor_widget}, position={position}"
        )

        # Order matters: every step that affects size must run before
        # positioning, and positioning must run before the on-screen
        # check, all while the menu is still hidden.  By the time
        # super().show() runs inside self.show(), the menu is already
        # at its final size and final position — Qt never paints a
        # pre-final state, so the user sees no flicker.
        #
        # 1. Configure as popup (Qt.Tool | FramelessWindowHint).
        self._setup_as_popup()
        self._current_anchor_widget = anchor_widget

        # Dismiss-on-ancestor-move: if a previous filter survived (e.g. from
        # a re-show without an intervening hide), detach it before installing
        # a fresh one bound to the current anchor.
        self._install_dismiss_on_move_filter(anchor_widget or self.parent())

        # 2. Finalize layout (apply/defaults buttons, presets, trigger
        #    hooks, style, height-fit) — must run BEFORE positioning so
        #    that any size change from added widgets is included in the
        #    measurement that drives position math.
        self._prepare_for_show()

        # 3. Final size pass on the now-complete layout.
        self.adjustSize()
        self._resize_height_to_content()

        # 4. Position relative to anchor (uses the final size from
        #    step 3).
        MenuPositioner.position_and_match_width(
            menu=self,
            anchor_widget=anchor_widget or self.parent(),
            position=position,
            match_parent_width=self.match_parent_width,
            logger=self.logger,
        )

        # 5. On-screen correction (uses the final position from step 4).
        #    Frameless Tool windows have frameGeometry == geometry even
        #    pre-show, so the check is reliable here.
        if self.ensure_on_screen:
            self._ensure_on_screen()

        # 6. Make Qt-visible.  The setVisible override re-runs
        #    _prepare_for_show; each branch is gated and no-ops.
        self.show()
        self.raise_()
        self.activateWindow()

        self._current_anchor_widget = None

    def setCentralWidget(self, widget, overwrite=False):
        if not overwrite and getattr(self, "_central_widget", None) is widget:
            return  # skip if same

        current_central_widget = getattr(self, "_central_widget", None)
        if current_central_widget and current_central_widget is not widget:
            current_central_widget.setParent(None)  # Avoid deleteLater()

        self._central_widget = widget
        self._central_widget.setProperty("class", "centralWidget")
        self._layout.addWidget(self._central_widget)

    def centralWidget(self):
        """Return the central widget."""
        return self._central_widget

    def init_layout(self):
        """Initialize the menu layout. Called lazily on first item add."""
        # Guard against double initialization
        if self._layout is not None:
            return

        # CRITICAL OPTIMIZATION: Disable updates AND layout calculation
        updates_were_enabled = self.updatesEnabled()
        self.setUpdatesEnabled(False)

        # Also block signals to prevent event propagation during setup
        was_blocked = self.blockSignals(True)

        try:
            # Create outer layout for the translucent window (margins for frame border)
            self._layout = QtWidgets.QVBoxLayout(self)
            # Provide a 2px transparent gutter so translucent borders never touch window edges
            self._layout.setContentsMargins(2, 2, 2, 2)
            self._layout.setSpacing(0)
            self._layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
            self.setLayout(self._layout)

            # Create frame container that will have the border
            self._frame = QtWidgets.QFrame(self)
            self._frame.setObjectName("menuFrame")
            self._frame.setProperty("class", "translucentBgWithBorder")
            self._frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
            self._frame.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
            )
            self._layout.addWidget(self._frame)

            # Create inner layout inside the frame (with spacing for border).
            # Stashed on self so deferred chrome (_ensure_chrome) can insert into it on show.
            self._frame_layout = QtWidgets.QVBoxLayout(self._frame)
            frame_layout = self._frame_layout
            # One extra pixel inside the frame keeps children off the painted border
            frame_layout.setContentsMargins(1, 1, 1, 1)
            frame_layout.setSpacing(1)
            frame_layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

            # Header is deferred to first show — see _ensure_chrome().

            # Create a central widget WITHOUT parent first to avoid tree overhead
            # Parent will be assigned when added to layout
            central_widget = QtWidgets.QWidget()
            self.setCentralWidget(central_widget)

            # Create a QVBoxLayout inside the central widget
            self.centralWidgetLayout = QtWidgets.QVBoxLayout(self._central_widget)
            self.centralWidgetLayout.setContentsMargins(2, 1, 2, 1)
            self.centralWidgetLayout.setSpacing(1)
            self.centralWidgetLayout.setSizeConstraint(
                QtWidgets.QLayout.SetNoConstraint
            )

            # Create a form layout inside the QVBoxLayout
            self.gridLayout = QtWidgets.QGridLayout()
            self.gridLayout.setContentsMargins(0, 0, 0, 0)
            self.gridLayout.setSpacing(1)
            self.gridLayout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

            # Add grid layout to the central widget layout
            self.centralWidgetLayout.addLayout(self.gridLayout)

            # Push items to the top so extra vertical space stays at the bottom
            self.centralWidgetLayout.addStretch(1)

            # Add central widget to frame layout
            frame_layout.addWidget(self._central_widget)

            # Footer is deferred to first show — see _ensure_chrome().

        finally:
            # Restore signal blocking state
            self.blockSignals(was_blocked)

            # Re-enable updates after layout creation
            if updates_were_enabled:
                self.setUpdatesEnabled(True)

            # Activate layout now that setup is complete
            if self._layout:
                self._layout.activate()

    def _ensure_chrome(self):
        """Build the deferred chrome (Header + Footer) on first show.
        Idempotent — guarded per sub-widget, safe to call repeatedly.

        Header/Footer are the heaviest part of a Menu and most option-box menus
        are never opened, so they are built here — right before paint, via
        ``_prepare_for_show`` — instead of eagerly during ``register_children``.
        """
        if self._frame_layout is None:
            self._ensure_layout_created()
        fl = self._frame_layout
        if fl is None:
            return

        if self.add_header and self.header is None:
            self.header = Header(config_buttons=["pin"])
            fl.insertWidget(0, self.header)  # ABOVE the central widget
            if self._pending_title is not None:
                self.header.setText(self._pending_title)
                self._pending_title = None

        if self.add_footer and self.footer is None:
            self.footer = Footer(add_size_grip=True)
            fl.addWidget(self.footer)  # LAST → below the central widget

    def ensure_chrome(self) -> None:
        """Force-build the deferred Header/Footer now.

        For callers that read ``.header`` / ``.footer`` BEFORE the menu is shown
        (e.g. modal dialogs that configure the header up front). Normal menus do
        not need this — chrome builds automatically on first show.
        """
        self._ensure_chrome()

    def _setup_leave_timer(self):
        """Set up timer for auto-hide on mouse leave."""
        self._leave_timer = QtCore.QTimer(self)
        self._leave_timer.setInterval(100)  # Check every 100ms
        self._leave_timer.timeout.connect(self._check_cursor_position)

    def _widget_in_subtree(self, widget: Optional[QtWidgets.QWidget]) -> bool:
        """True when *widget* is this menu or any descendant of it.

        Walks the QObject parent chain (not the visual-ancestor test) so it
        also matches widgets living in a *separate top-level popup* opened from
        inside the menu — a ComboBox dropdown, an option-box ⋯ menu — whose
        chain crosses the window boundary back to ``self``. ``isAncestorOf``
        is same-window-only and misses those.
        """
        w = widget
        while w is not None:
            if w is self:
                return True
            w = w.parent()
        return False

    # ------------------------------------------------------------------
    # Transient popup family (hover-coordinated child popups)
    # ------------------------------------------------------------------

    def adopt_transient(self, child: QtWidgets.QWidget) -> None:
        """Keep this menu open while the pointer is over *child*.

        Registers a child popup — an option-menu dropdown, a context menu, a
        value popup, a nested ``Menu`` — as part of this menu's *transient
        family*. While any adopted child is visible, ``hide_on_leave`` treats
        the pointer being over that child (by window geometry OR by QObject
        subtree) as "still inside", and hiding this menu cascades to the child.

        Ownership here is logical, not a QObject relationship: child popups are
        frequently parented to the wrapped widget (a sibling of this menu) for
        lifetime/positioning reasons, which puts them outside this menu's
        subtree. Adoption re-establishes the relationship so the existing
        subtree check (:meth:`_widget_in_subtree`) becomes one special case of
        a broader "is the pointer in my family?" test.

        Children are held weakly and pruned lazily, so one destroyed or hidden
        without notice is cleaned up on next access — a child that dies can
        never wedge this menu open. Adoption is idempotent. The first adoption
        raises :attr:`leave_grace_samples` so a brief gap-crossing toward the
        child does not dismiss this menu.

        Parameters:
            child: The top-level popup widget to adopt. ``self`` and
                non-widgets are ignored.
        """
        if not isinstance(child, QtWidgets.QWidget) or child is self:
            return
        for ref in self._transient_children:
            if ref() is child:
                return  # already adopted
        self._transient_children.append(weakref.ref(child))
        # Prompt pruning when the child reports it hid (optional — lazy pruning
        # in _living_transients is the correctness guarantee; this just keeps
        # the list tidy). Menu exposes on_hidden; plain popups may not.
        on_hidden = getattr(child, "on_hidden", None)
        if on_hidden is not None and hasattr(on_hidden, "connect"):
            try:
                on_hidden.connect(self._prune_transients)
            except (RuntimeError, TypeError):
                pass
        # A newly adopted child means the user is heading toward it: clear any
        # in-flight leave count and give this menu the gap-crossing grace.
        self._outside_samples = 0
        self.leave_grace_samples = max(self.leave_grace_samples, 3)
        self.logger.debug(f"adopt_transient: adopted {child!r}")

    def _living_transients(self):
        """Yield adopted children still alive (valid C++ object), pruning the rest."""
        survivors = []
        for ref in self._transient_children:
            child = ref()
            if child is None:
                continue
            try:
                child.isVisible()  # cheap touch — raises if the C++ object is gone
            except RuntimeError:
                continue
            survivors.append(ref)
            yield child
        self._transient_children = survivors

    def _prune_transients(self) -> None:
        """Drop dead/deleted children from the registry."""
        list(self._living_transients())

    def _iter_transient_family(self, _seen: Optional[set] = None):
        """Yield this menu and every living adopted descendant, recursively.

        Guarded against cycles (``_seen``) so an accidental mutual adoption
        can't spin the 100 ms leave-poll into an infinite loop.
        """
        if _seen is None:
            _seen = set()
        if id(self) in _seen:
            return
        _seen.add(id(self))
        yield self
        for child in self._living_transients():
            sub = getattr(child, "_iter_transient_family", None)
            if callable(sub):
                yield from sub(_seen)
            elif id(child) not in _seen:
                _seen.add(id(child))
                yield child

    def _pointer_in_family(self, global_pos: Optional[QtCore.QPoint] = None) -> bool:
        """True when the pointer is over this menu or any adopted transient.

        Generalizes the rect + subtree test in :meth:`_check_cursor_position`
        to the whole popup family: a hit on any visible family member's window
        geometry, or on any widget whose QObject parent chain leads back into a
        family member, keeps the menu open.
        """
        if global_pos is None:
            global_pos = QtGui.QCursor.pos()
        widget_at = QtWidgets.QApplication.widgetAt(global_pos)
        for member in self._iter_transient_family():
            try:
                if not member.isVisible():
                    continue
                # Map global → member-local and test the local rect. This is
                # coordinate-system agnostic: it is correct whether the member
                # is a top-level Tool window OR a child widget (e.g. a menu
                # parented into the fullscreen marking-menu overlay), and across
                # multi-monitor offsets. frameGeometry() would only be global
                # for top-levels and could otherwise falsely report "inside",
                # wedging hide_on_leave permanently open.
                if member.rect().contains(member.mapFromGlobal(global_pos)):
                    return True
            except RuntimeError:
                continue
            in_subtree = getattr(member, "_widget_in_subtree", None)
            if callable(in_subtree) and in_subtree(widget_at):
                return True
        return False

    def _hide_transient_children(self) -> None:
        """Hide every adopted child (cascade) and clear the registry."""
        if not self._transient_children:
            return
        for child in list(self._living_transients()):
            try:
                child.hide()
            except RuntimeError:
                pass
        self._transient_children = []

    @staticmethod
    def nearest_enclosing(widget: Optional[QtWidgets.QWidget]) -> Optional["Menu"]:
        """Return the nearest ``Menu`` ancestor of *widget* (inclusive), or None.

        Walks the QObject parent chain so a button living inside a menu can find
        the menu that should adopt the popup it spawns. Returns None when the
        widget is not hosted inside a ``Menu`` (e.g. it sits in a bare
        option-box container), in which case the spawned popup stands alone with
        its own hide behavior.
        """
        w = widget
        while w is not None:
            if isinstance(w, Menu):
                return w
            w = w.parent()
        return None

    # Widget types whose focus means the user is actively entering a value, so
    # a stray mouse-leave must not tear the menu down mid-edit. The inline
    # preset Save/Rename field is a ``QLineEdit`` (an editable ComboBox focuses
    # its internal ``QLineEdit``); spin boxes edit through ``QAbstractSpinBox``.
    # Non-text widgets (buttons, plain combos, checkboxes) are intentionally
    # excluded — a click that merely parks focus on one of them must still let
    # the fast hide-on-leave fire when the cursor leaves.
    _EDIT_FOCUS_TYPES = (
        QtWidgets.QLineEdit,
        QtWidgets.QTextEdit,
        QtWidgets.QPlainTextEdit,
        QtWidgets.QAbstractSpinBox,
    )

    def _text_edit_in_progress(self) -> bool:
        """True when a *text-entry* widget inside this menu's subtree has focus.

        Used to suppress ``hide_on_leave`` while the user is actively editing
        one of the menu's widgets — e.g. typing a new name into the preset
        combo's inline Save/Rename line edit. Without this guard a transient
        mouse-leave hid the popup mid-edit, ending the edit prematurely and (on
        a Save seeded with the active preset's own name) silently overwriting
        that template with its unchanged name before the user could retype it.
        """
        app = QtWidgets.QApplication.instance()
        if app is None:
            return False
        focus = app.focusWidget()
        return isinstance(focus, self._EDIT_FOCUS_TYPES) and self._widget_in_subtree(
            focus
        )

    def _demote_editor_autofocus(self) -> None:
        """Stop editor items from passively auto-grabbing keyboard focus.

        A spin box / line edit added to a ``hide_on_leave`` menu defaults to a
        focus policy that includes Tab/activation focus, so it grabs keyboard
        focus the instant the menu is shown and activated — even though the user
        never engaged it. That makes :meth:`_text_edit_in_progress` read True and
        wedges the menu open against ``hide_on_leave`` (the field bug where a
        spin-box option menu — e.g. *Merge* — "never hides" while a checkbox-only
        one — e.g. *Separate* — does). Demoting such editors to ``ClickFocus``
        drops only the *passive* auto-focus: click-to-edit and an explicit
        ``setFocus`` still work, so deliberate editing (the preset inline rename)
        stays protected. Idempotent; only touches ``hide_on_leave`` menus.
        """
        if not self.hide_on_leave:
            return
        # Policies that already don't passively auto-focus. Everything else
        # (TabFocus / StrongFocus / WheelFocus) is demoted. Equality membership
        # rather than a bitwise `& TabFocus` so it's safe across PySide2 and
        # PySide6's stricter enums (Maya 2025 ships 6.5.3).
        no_autofocus = (QtCore.Qt.NoFocus, QtCore.Qt.ClickFocus)
        for item in self.get_items():
            try:
                if (
                    isinstance(item, self._EDIT_FOCUS_TYPES)
                    and item.focusPolicy() not in no_autofocus
                ):
                    item.setFocusPolicy(QtCore.Qt.ClickFocus)
            except RuntimeError:
                pass

    def _check_cursor_position(self):
        """Check if cursor is outside menu bounds and hide if so.

        Only hides if the mouse has entered the menu at least once.
        This prevents immediate hiding when menu is positioned away from cursor.
        Also respects the pinned state — won't hide if pinned — and never hides
        while keyboard focus is on one of the menu's widgets (an in-progress
        edit), so a stray mouse-leave can't dismiss the popup mid-interaction.
        """
        if not self.isVisible():
            self._leave_timer.stop()
            return

        if _LEAVE_DEBUG:
            self._log_leave_state()

        # Don't hide if menu is pinned
        if self.is_pinned:
            self._outside_samples = 0
            return

        # Check the whole popup family, not just this window: the pointer counts
        # as "inside" when it is over this menu OR any adopted transient child
        # (an option-menu dropdown, a context menu, a value popup) — by window
        # geometry or by the QObject subtree walk that catches separate
        # top-level popups parented back under a family member. See
        # _pointer_in_family / adopt_transient.
        if self._pointer_in_family():
            if not self._mouse_has_entered:
                self.logger.debug(
                    "_check_cursor_position: Pointer entered menu family"
                )
            self._mouse_has_entered = True
            self._outside_samples = 0
            return

        # Outside the whole family. Before hiding, honor active text entry: if a
        # line edit / spin box inside the menu has focus the user is mid-edit —
        # tearing the menu down here is what produced the accidental preset
        # overwrite. The menu still hides normally once the edit ends.
        if self._text_edit_in_progress():
            self._outside_samples = 0
            return

        # The pointer is outside the whole family. Count consecutive outside
        # samples and hide once they exceed the grace. Two graces apply:
        #   * entered → a deliberate leave: hide after ``leave_grace_samples``
        #     (default 1 = immediate; raised once a child is adopted to bridge
        #     the gap the pointer crosses between this menu and a child popup).
        #   * never entered → the menu opened away from the cursor and the user
        #     hasn't reached it: hide after the longer ``unentered_grace_samples``
        #     (time to reach it) so an opened-but-ignored hide_on_leave menu
        #     still auto-dismisses instead of lingering forever.
        self._outside_samples += 1
        threshold = (
            max(1, self.leave_grace_samples)
            if self._mouse_has_entered
            else max(1, self.unentered_grace_samples)
        )
        if self._outside_samples >= threshold:
            self.logger.debug(
                "_check_cursor_position: Pointer outside family (entered=%s), hiding",
                self._mouse_has_entered,
            )
            self.hide()
            self._leave_timer.stop()

    def _log_leave_state(self) -> None:
        """Log the hide_on_leave decision state for the current poll tick.

        Active only when ``UITK_MENU_LEAVE_DEBUG`` is set. Names exactly which
        gate is keeping the menu open so a real-session capture can pinpoint a
        "won't hide" symptom that does not reproduce offscreen. Read it as:

        * ``hol=False``           → hide_on_leave is off (nothing to do).
        * ``timer=False``         → the leave poll isn't running.
        * ``pinned=True``         → is_pinned (prevent_hide or header pin) blocks it.
        * ``entered=False``       → cursor never entered; the menu won't hide
                                    until it has (it opened away from the cursor).
        * ``in_family=True`` with ``self_rect=False`` and ``children=0`` → kept
          open by the QObject-subtree walk; ``widgetAt`` names the offending
          widget (a stale/unexpected hit, e.g. under the marking menu's grab).
        """
        try:
            gpos = QtGui.QCursor.pos()
            wa = QtWidgets.QApplication.widgetAt(gpos)
            self_hit = self.rect().contains(self.mapFromGlobal(gpos))
            in_family = self._pointer_in_family(gpos)
            wa_name = f"{type(wa).__name__}({wa.objectName() or '-'})" if wa else "None"
            wa_win = wa.window().objectName() or "-" if wa is not None else "-"
            children = sum(1 for _ in self._living_transients())
            timer_on = bool(self._leave_timer and self._leave_timer.isActive())
            self.logger.warning(
                "[leave] name=%s hol=%s pinned=%s entered=%s timer=%s self_rect=%s "
                "in_family=%s children=%d grace=%s outside=%s widgetAt=%s win=%s",
                self.objectName() or "-",
                self.hide_on_leave,
                self.is_pinned,
                self._mouse_has_entered,
                timer_on,
                self_hit,
                in_family,
                children,
                self.leave_grace_samples,
                self._outside_samples,
                wa_name,
                wa_win,
            )
        except Exception as e:  # diagnostics must never break the poll
            self.logger.warning(f"[leave] diagnostic error: {e}")

    def _resize_height_to_content(self) -> None:
        """Collapse stale vertical space before showing the menu again.

        Menus are often rebuilt while hidden. Without explicitly syncing the
        geometry, Qt can reuse the previous height, leaving an empty gap when
        fewer items remain. Keeping the width untouched avoids fighting the
        width-matching logic while still trimming vertical dead space.
        """

        if not self._layout:
            return

        self._layout.activate()
        hint = self.sizeHint()
        if not hint.isValid():
            return

        target_height = max(hint.height(), self.minimumHeight())
        current_width = self.width() or max(hint.width(), self.minimumWidth())

        if self.height() != target_height:
            self.resize(current_width, target_height)

    def _setup_apply_button(self):
        """Set up the apply button with proper configuration.

        This method creates an apply button that emits the parent's 'clicked' signal
        if available. The button is only created if the clicked signal has connections.
        """
        if not self.parent():
            self.logger.debug(
                "_setup_apply_button: No parent, skipping apply button setup"
            )
            return

        if not hasattr(self.parent(), "clicked"):
            self.logger.debug(
                "_setup_apply_button: Parent has no 'clicked' signal, skipping"
            )
            return

        # Check if the clicked signal has any receivers (connections)
        try:
            receiver_count = self.parent().receivers(QtCore.SIGNAL("clicked()"))
            if receiver_count == 0:
                self.logger.debug(
                    "_setup_apply_button: Parent's 'clicked' signal has no connections, skipping"
                )
                return
        except (AttributeError, TypeError) as e:
            # If we can't check receivers, proceed anyway (fail-safe)
            self.logger.debug(
                f"_setup_apply_button: Could not check signal receivers ({e}), proceeding anyway"
            )

        # Create apply button configuration
        # Button should be visible if menu has items
        config = _ActionButtonConfig(
            text="Apply",
            callback=lambda: self.parent().clicked.emit(),
            tooltip="Execute the command",
            visible=self.contains_items,  # Visible if menu already has items
            fixed_height=26,
        )

        # Add the apply button using the button manager
        self._button_manager.add_button("apply", config)

        # Add the action button container to the central widget layout
        # (it goes in the central area, after the grid layout)
        self.centralWidgetLayout.addWidget(self._button_manager.container)

        self.logger.debug(
            "_setup_apply_button: Apply button created and added to layout"
        )

    def _update_apply_button_visibility(self):
        """Update apply button visibility based on menu state.

        The apply button should be visible whenever the menu contains items.
        """
        if not self.add_apply_button:
            return

        apply_button = self._button_manager.get_button("apply")
        if not apply_button:
            return

        should_show = self.contains_items

        if should_show:
            self._button_manager.show_button("apply")
            self.logger.debug("_update_apply_button_visibility: Showing apply button")
        else:
            self._button_manager.hide_button("apply")
            self.logger.debug("_update_apply_button_visibility: Hiding apply button")

    def _setup_defaults_button(self):
        """Set up the restore defaults button."""
        config = _ActionButtonConfig(
            text="Restore Defaults",
            callback=self._restore_menu_defaults,
            tooltip="Reset all options to their default values",
            visible=self.contains_items,
            fixed_height=18,
        )
        btn = self._button_manager.add_button("defaults", config, index=0)

        # Rename button to allow finding it from other instances for synchronization
        if self.objectName():
            try:
                # Handle switchboard suffixes if present
                clean_name = self.objectName().split("#")[0]
                btn.setObjectName(f"actionButton_defaults_{clean_name}")
            except Exception:
                pass

        if not self._button_manager.container.parent():
            self.centralWidgetLayout.addWidget(self._button_manager.container)

    def owner_window(self) -> Optional[QtWidgets.QWidget]:
        """Public alias for the owning ``MainWindow``, or ``None``.

        Thin wrapper over :meth:`_resolve_registration_window` so collaborators
        (e.g. a window-scoped :class:`PresetManager`) can reach the host window
        through the same reparent-race-robust resolver used for dynamic-widget
        registration, without depending on a private method.
        """
        return self._resolve_registration_window()

    def _resolve_registration_window(self) -> Optional[QtWidgets.QWidget]:
        """Return the owning MainWindow for dynamic-widget registration.

        Registration is *deferred* (see :meth:`_schedule_registration`); by the
        time the drain runs the menu may have reparented itself to a top-level
        popup / Tool window on show, severing the parent chain back to the
        MainWindow. A plain ``self.parent()`` walk then finds nothing and
        registration is silently skipped — the widget never gets
        ``restore_state``, so its value is neither saved nor restored. This was
        the prime suspect behind menu-hosted options resetting only in live
        interactive DCC sessions (where show/reparent races the drain).

        To stay robust we (1) prefer a live parent-chain walk — correct and
        cheap in the common, un-reparented case — and (2) fall back to the
        MainWindow captured weakly while the chain was still intact. The cache
        is refreshed on every successful live walk.
        """
        curr = self.parent()
        while curr is not None:
            if hasattr(curr, "register_widget") and hasattr(curr, "widgets"):
                self._registration_window_ref = weakref.ref(curr)
                return curr
            curr = curr.parent()

        ref = self._registration_window_ref
        window = ref() if ref is not None else None
        if window is not None:
            try:
                window.objectName()  # dead C++ wrapper -> RuntimeError
                return window
            except RuntimeError:
                self._registration_window_ref = None
        return None

    def _register_with_main_window(self, widget: QtWidgets.QWidget) -> None:
        """Find the owning MainWindow and register *widget* with it.

        This enables signal wiring, slot discovery, and QSettings-based
        state persistence for widgets added dynamically via :meth:`add`.
        Resolution goes through :meth:`_resolve_registration_window` so a menu
        that has already reparented to a popup still resolves its MainWindow.
        """
        window = self._resolve_registration_window()
        if window is None:
            self.logger.debug(
                "_register_with_main_window: no MainWindow reachable for "
                f"{widget.objectName()!r}; its state will not persist"
            )
            return
        try:
            window.register_widget(widget)
        except Exception:
            pass

    def _schedule_registration(self, widget: QtWidgets.QWidget) -> None:
        """Queue *widget* for deferred registration with the main window.

        Coalesces N per-item ``QTimer.singleShot`` calls into a single
        drain pass.  Registration order (FIFO) and the deferred-not-sync
        contract from :meth:`Menu.add` are preserved.
        """
        # Capture the owning MainWindow once, while the menu is still nested
        # under its host and the parent chain is intact. By drain time the menu
        # may have reparented to a popup, breaking the walk; the cache set here
        # lets _resolve_registration_window recover it. A later legitimate
        # reparent is still honored — drain-time resolution re-walks live first.
        if self._registration_window_ref is None:
            self._resolve_registration_window()
        self._pending_registrations.append(widget)
        if not self._registration_drain_scheduled:
            self._registration_drain_scheduled = True
            QtCore.QTimer.singleShot(0, self._drain_pending_registrations)

    def _drain_pending_registrations(self) -> None:
        """Process every queued registration in insertion order.

        Anything appended *during* the drain (e.g. a registration that
        ends up calling ``Menu.add`` again on a sibling menu) lands in a
        fresh queue and triggers its own next-tick drain — matching the
        per-item-timer behavior this replaced.

        Exception handling: with one timer per item (the prior
        implementation), each fired independently — a failure in one
        registration didn't drop the rest.  We preserve that property by
        catching all exceptions per-iteration.  ``RuntimeError`` (the
        common case: widget destroyed between schedule and drain) is
        swallowed silently; any other exception is logged so latent bugs
        don't go unnoticed but the drain still completes.
        """
        pending, self._pending_registrations = self._pending_registrations, []
        self._registration_drain_scheduled = False
        for widget in pending:
            try:
                self._register_with_main_window(widget)
            except RuntimeError:
                # Widget destroyed between schedule and drain; skip silently.
                continue
            except Exception as exc:  # noqa: BLE001 — preserve per-timer isolation
                self.logger.error(
                    f"_drain_pending_registrations: {type(exc).__name__} during "
                    f"_register_with_main_window: {exc}",
                )
                continue

    def _restore_menu_defaults(self, from_sync: bool = False):
        """Reset all menu widgets to their default values."""
        window = self.window()
        state = getattr(window, "state", None)

        # Fallback: traverse parents if state not found on window()
        # This handles cases where Menu acts as a Tool/Popup window and window() returns self
        if not state:
            curr = self.parent()
            while curr:
                if hasattr(curr, "state"):
                    state = curr.state
                    break
                curr = curr.parent()

        # Last resort: the MainWindow captured during registration. The live
        # walk above misses it once the menu has reparented to a popup on show
        # (same reparenting that breaks _register_with_main_window).
        if not state:
            window = self._resolve_registration_window()
            state = getattr(window, "state", None) if window is not None else None

        if not state:
            self.logger.debug("_restore_menu_defaults: No state manager found")
            return
        for widget in self.get_items():
            state.reset(widget)
        self.logger.debug("_restore_menu_defaults: Reset complete")

        if not from_sync:
            self._sync_restore_defaults()

    def _sync_restore_defaults(self):
        """Synchronize defaults reset across other instances of this menu."""
        if not self.objectName():
            return

        try:
            clean_name = self.objectName().split("#")[0]
            target_btn_name = f"actionButton_defaults_{clean_name}"
        except Exception:
            return

        app = QtWidgets.QApplication.instance()
        if not app:
            return

        current_btn = self._button_manager.get_button("defaults")

        # Find match buttons in other menus
        for widget in app.allWidgets():
            if widget.objectName() == target_btn_name and widget is not current_btn:
                # Traverse up to find the menu
                parent = widget.parent()
                while parent:
                    if hasattr(parent, "_restore_menu_defaults"):
                        parent._restore_menu_defaults(from_sync=True)
                        break
                    parent = parent.parent()

    @property
    def add_defaults_button(self) -> bool:
        """Whether the 'Restore Defaults' button is enabled.

        Setting to ``False`` at runtime removes the button and hides
        the action-button container if no other buttons remain.
        """
        return self._add_defaults_button

    @add_defaults_button.setter
    def add_defaults_button(self, value: bool) -> None:
        self._add_defaults_button = value
        if not value:
            self._button_manager.remove_button("defaults")

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    @property
    def add_presets(self) -> bool:
        """Whether the presets combo is enabled.

        When ``True``, a ``ComboBox`` preset selector is placed
        in the *Menu Actions* container at the bottom of the menu
        (alongside the *Restore Defaults* and *Apply* buttons).  The
        actual setup is deferred to the first ``showEvent``.

        Set the preset directory separately::

            widget.menu.add_presets = True
            widget.menu.presets.preset_dir = "~/.myapp/presets"

        Setting to ``False`` at runtime removes the combo and hides
        the action container if no other items remain.
        """
        return self._add_presets

    @add_presets.setter
    def add_presets(self, value: bool) -> None:
        self._add_presets = value
        if not value:
            self._button_manager.remove_widget("presets")

    def _setup_presets(self):
        """Create the preset combo inside the menu-actions container.

        Called lazily from ``showEvent`` the first time the menu is
        shown while :attr:`add_presets` is ``True``.
        """
        from uitk.widgets.comboBox import ComboBox

        # Ensure layout exists (may not if add_presets is set before add())
        self._ensure_layout_created()

        # Create combo directly and place it into the action container
        combo = ComboBox()
        combo.setObjectName("cmb_presets")
        combo.setToolTip("Load a saved configuration preset.")
        combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )

        self._button_manager.add_widget("presets", combo)

        # Ensure the container is parented into the central layout
        if not self._button_manager.container.parent():
            self.centralWidgetLayout.addWidget(self._button_manager.container)

        # Wire the combo with the Refresh / Save / ⋯-menu option-box toolbar.
        # wire_combo wraps the combo in its option-box container; since the
        # combo is already in the action-container layout, the wrap replaces it
        # in place (the button_manager still tracks the combo, nested inside).
        self.presets.wire_combo(combo)

        # Make the combo accessible as self.cmb_presets (mirrors self.add() behaviour)
        setattr(self, "cmb_presets", combo)

        # Show the container
        self._button_manager.container.show()

    def _update_defaults_button_visibility(self):
        """Update defaults button visibility based on menu state."""
        if not self.add_defaults_button:
            return

        defaults_button = self._button_manager.get_button("defaults")
        if not defaults_button:
            return

        # Define types that are considered "options" (stateful widgets)
        # We only show the Restore Defaults button if at least one such widget is present
        option_types = (
            QtWidgets.QCheckBox,
            QtWidgets.QRadioButton,
            QtWidgets.QLineEdit,
            QtWidgets.QTextEdit,
            QtWidgets.QAbstractSpinBox,
            QtWidgets.QComboBox,
            QtWidgets.QSlider,
            QtWidgets.QDial,
            QtWidgets.QDateEdit,
            QtWidgets.QTimeEdit,
            QtWidgets.QDateTimeEdit,
            QtWidgets.QPlainTextEdit,
        )

        has_options = False
        for widget in self.get_items():
            if widget and isinstance(widget, option_types):
                has_options = True
                break

        if has_options:
            self._button_manager.show_button("defaults")
        else:
            self._button_manager.hide_button("defaults")

    def get_all_children(self):
        children = self.findChildren(QtWidgets.QWidget)
        return children

    @property
    def is_pinned(self) -> bool:
        """Check if the menu is pinned (should not auto-hide).

        This is the single source of truth for pin state checking.
        Checks both the prevent_hide flag and the header's pin button state.

        Returns:
            bool: True if menu should stay visible (pinned), False otherwise
        """
        # Check prevent_hide flag
        if self.prevent_hide:
            return True

        # Check header pin button state (if header exists and has pin functionality)
        if self.header and hasattr(self.header, "pinned"):
            return self.header.pinned

        return False

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

    def title(self) -> str:
        """Get the menu's title text (the pending value if the header isn't built yet)."""
        if self.header is not None:
            return self.header.text()
        return self._pending_title or ""

    def setTitle(self, title="") -> None:
        """Set the menu's title to the given string.

        If the header hasn't been built yet (chrome is deferred to first show),
        the title is stashed and applied when the header is created.

        Parameters:
            title (str): Text to apply to the menu's title.
        """
        if self.header is not None:
            self.header.setText(title)
        else:
            # Chrome is deferred to first show; stash and apply when it builds.
            self._pending_title = title

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
                if i.text() == identifier:
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

        If this results in an empty menu, event filters will be uninstalled
        to free up resources.
        """
        self.logger.debug(
            f"Menu.remove_widget: Removing widget={widget.objectName() or type(widget).__name__}"
        )
        self.gridLayout.removeWidget(widget)
        if widget in self.widget_data:
            del self.widget_data[widget]

        # Uninstall event filters if menu is now empty
        if not self.contains_items:
            self._uninstall_event_filters()
            self.logger.debug(
                "Menu.remove_widget: Menu now empty, event filters uninstalled"
            )

    def clear(self) -> None:
        """Clear all items in the list.

        This will also uninstall event filters since the menu becomes empty.
        """
        if self.gridLayout is None:
            return

        item_count = self.gridLayout.count()
        self.logger.debug(f"Menu.clear: Clearing {item_count} items")

        # We're going backwards to avoid index errors.
        for i in reversed(range(self.gridLayout.count())):
            widget = self.gridLayout.itemAt(i).widget()
            if widget:
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
                widget_class = _resolve_widget_class(x)
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
            # Expose the item as an attribute for ergonomic access
            # (menu.<objectName>), but never clobber Menu's own API: an item
            # named "clear"/"show"/"add" would silently replace the method.
            item_name = widget.objectName()
            if item_name:
                existing = getattr(self, item_name, None)
                if existing is None or isinstance(existing, QtWidgets.QWidget):
                    setattr(self, item_name, widget)
                else:
                    self.logger.warning(
                        f"[Menu.add] item objectName {item_name!r} collides with "
                        f"an existing Menu attribute; skipping attribute exposure."
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

    def _add_action_widget(
        self,
        action: QtWidgets.QAction,
        row: Optional[int] = None,
        col: int = 0,
        rowSpan: int = 1,
        colSpan: Optional[int] = None,
    ) -> Optional[QtWidgets.QWidget]:
        temp_menu = QtWidgets.QMenu(self)
        temp_menu.addAction(action)

        temp_menu.ensurePolished()
        temp_menu.show()
        QtWidgets.QApplication.processEvents()

        widget = temp_menu.widgetForAction(action)
        if not widget:
            temp_menu.hide()
            temp_menu.deleteLater()
            return None

        widget.setParent(self)
        temp_menu.hide()
        temp_menu.deleteLater()

        if row is None:
            row = 0
            while self.gridLayout.itemAtPosition(row, col):
                row += 1
        if colSpan is None:
            colSpan = self.gridLayout.columnCount() or 1

        self.gridLayout.addWidget(widget, row, col, rowSpan, colSpan)
        return widget

    def _activate_inner_layouts(self) -> None:
        """Synchronously recompute the nested layout sizeHints.

        ``add()`` skips ``self._layout.activate()`` while the menu is
        invisible (Qt re-activates before paint, so the work is wasted for
        an off-screen widget — see the bulk-add note in ``add()``).  The
        side effect is that the *inner* QBoxLayouts (``centralWidgetLayout``
        and the frame layout) keep a cached sizeHint from when they were
        empty — collapsed to just their margins.  ``invalidate()`` only
        posts a deferred ``LayoutRequest`` that never gets processed while
        invisible, and ``sizeHint`` below reads ``self._frame.sizeHint()``
        directly, bypassing the grid's own (correct) recompute.  The net
        result: ``adjustSize()`` on a freshly-populated, not-yet-shown menu
        sizes it to the minimum width, clipping content (e.g. the
        RecentValues / PinnedValues popups, which size-then-show).

        Forcing a synchronous ``activate()`` on the inner chain refreshes
        those cached hints.  The outer ``self._layout`` is intentionally
        left alone — Qt drives its activation and may already be mid-pass.
        Only needed while invisible; once shown Qt drains the pending
        ``LayoutRequest`` and the hints stay current on their own.
        """
        if self._activating_chain:
            return
        self._activating_chain = True
        try:
            if self.centralWidgetLayout is not None:
                self.centralWidgetLayout.activate()
            frame = getattr(self, "_frame", None)
            if frame is not None and frame.layout() is not None:
                frame.layout().activate()
        finally:
            self._activating_chain = False

    def sizeHint(self):
        """Return the recommended size for the widget.

        This method calculates the total size of the widgets contained in the layout of the ExpandableList, including margins and spacing.

        Returns:
            QtCore.QSize: The recommended size for the widget.
        """
        if self._layout is None:
            return super().sizeHint()

        # While invisible the nested layouts hold a stale (collapsed) cached
        # sizeHint; refresh them so adjustSize()/width-matching see the real
        # content width. Once shown, Qt keeps them current — skip the work.
        if not self.isVisible():
            self._activate_inner_layouts()

        total_height = 0
        total_width = 0

        for i in range(self._layout.count()):
            widget = self._layout.itemAt(i).widget()
            if widget:
                total_height += widget.sizeHint().height() + self._layout.spacing()
                total_width = max(total_width, widget.sizeHint().width())

        # Adjust for layout's top and bottom margins
        total_height += (
            self._layout.contentsMargins().top() + self._layout.contentsMargins().bottom()
        )
        # Adjust for layout's left and right margins for width
        total_width += (
            self._layout.contentsMargins().left() + self._layout.contentsMargins().right()
        )

        return QtCore.QSize(total_width, total_height)

    def showEvent(self, event) -> None:
        """Handle show event with positioning (optimized for performance)."""
        # Popup setup is handled in :meth:`setVisible`, which fires before
        # this event.  By the time showEvent runs, the menu is already a
        # configured Tool window with all attributes applied.

        # Track which window was active before showing menu
        # This allows us to restore focus only if our app was active
        app = QtWidgets.QApplication.instance()
        if app:
            self._active_window_before_show = app.activeWindow()
            self.logger.debug(
                f"showEvent: Active window before show: {self._active_window_before_show}"
            )

        # Safety net: if a path showed the menu without routing through
        # setVisible()/_prepare_for_show(), build the chrome now (idempotent).
        self._ensure_chrome()

        # Stop spin-box / line-edit items from auto-grabbing focus when this
        # popup activates — a passively focused editor would otherwise read as
        # "edit in progress" and wedge a hide_on_leave menu open (see
        # _demote_editor_autofocus). Runs before the window activates.
        self._demote_editor_autofocus()

        # Always start unpinned when showing to avoid stale state from previous sessions
        if self.header and hasattr(self.header, "reset_pin_state"):
            self.header.reset_pin_state()

        # CRITICAL OPTIMIZATION: Install event filters on first show, not during add()
        # This eliminates 37-180ms from add() calls
        if (
            self.contains_items
            and self._trigger_button is not False
            and not (self._event_filters_installed or self._parent_signal_source)
        ):
            self._ensure_trigger_hook()
        # Setup defaults button
        if self.add_defaults_button and not self._button_manager.get_button("defaults"):
            self._setup_defaults_button()
            self._update_defaults_button_visibility()
        elif self.add_defaults_button:
            self._update_defaults_button_visibility()

        #
        # Lazy initialization: ensure style and timer are created on first show
        # These check their own flags internally, so safe to call every time
        self._ensure_style_initialized()
        self._ensure_timer_created()

        # Check if cursor is already inside menu when it appears
        # This prevents immediate hide-on-leave when menu pops up under cursor
        self._outside_samples = 0
        cursor_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        if self.rect().contains(cursor_pos):
            self._mouse_has_entered = True
            self.logger.debug(
                "showEvent: Cursor already inside menu, marking as entered"
            )
        else:
            # Reset to False when cursor is outside - menu must wait for cursor to enter
            self._mouse_has_entered = False
            self.logger.debug("showEvent: Cursor outside menu, waiting for entry")

        # Setup presets combo on first show if requested and not already created
        if self.add_presets and not self._button_manager.get_widget("presets"):
            self._setup_presets()

        # Setup apply button on first show if requested and not already created
        # Deferred to showEvent because parent's signal connections may not exist during add()
        if self.add_apply_button and not self._button_manager.get_button("apply"):
            self._setup_apply_button()
            # Update visibility immediately (this shows the container)
            self._update_apply_button_visibility()
            # Force complete layout update
            if self._layout:
                self._layout.invalidate()
                self._layout.activate()
            # Use adjustSize to recalculate based on new content
            self.adjustSize()
            self.logger.debug(
                f"showEvent: Apply button added, menu resized to {self.size()}"
            )

        # Update apply button visibility when menu is shown (for subsequent shows)
        # Only if apply button feature is enabled and button already exists
        elif self.add_apply_button:
            self._update_apply_button_visibility()

        # Ensure the geometry reflects the current item count before positioning.
        self._resize_height_to_content()

        # Only auto-position if we have a position setting AND show_as_popup
        # didn't already handle positioning. _current_anchor_widget is set during
        # show_as_popup's show() call and cleared after, so its presence means
        # show_as_popup already positioned us — don't override with self.position.
        if self.position and not self._current_anchor_widget:
            self._apply_position()

        # Start leave timer if enabled
        # Add grace period before first check to prevent immediate hide when menu
        # appears at cursor position but cursor hasn't entered menu bounds yet
        if self._leave_timer:
            # Delay timer start by 200ms to give user time to move cursor into menu
            # Note: _mouse_has_entered was already set above based on cursor position
            QtCore.QTimer.singleShot(
                200, lambda: self._leave_timer.start() if self._leave_timer else None
            )

        # Register with the owning MainWindow so it can enumerate its open
        # menus (e.g. for the marking menu's window-dim pass). Once per menu:
        # the menu is now a top-level popup, but owner_window() resolves the
        # host window through the reparent-robust resolver. A menu with no
        # MainWindow owner (e.g. a run_modal parented to a bare widget) simply
        # stays untracked — it's outside the switchboard window set.
        if not self._tracked_as_menu:
            owner = self.owner_window()
            if owner is not None and hasattr(owner, "register_menu"):
                owner.register_menu(self)
                self._tracked_as_menu = True

        super().showEvent(event)

    def hide(self, force: bool = False) -> bool:
        """Hide the menu, respecting the pinned state.

        Parameters:
            force: If True, hide even if the menu is pinned

        Returns:
            bool: True if the menu was hidden, False if prevented by pinning
        """
        if self.is_pinned and not force:
            self.logger.debug("hide: Menu is pinned, ignoring hide request")
            return False

        if self.header and getattr(self.header, "pinned", False):
            if hasattr(self.header, "reset_pin_state"):
                self.header.reset_pin_state()
                self.logger.debug("hide: Reset pinned state")

        super().hide()
        return True

    def hideEvent(self, event) -> None:
        """Handle hide event.

        Restores focus to parent widget to prevent application focus loss
        when menu (Qt.Tool window) is hidden.
        """
        # Stop leave timer when menu is hidden
        if self._leave_timer and self._leave_timer.isActive():
            self._leave_timer.stop()
            self.logger.debug("hideEvent: Leave timer stopped")

        # Detach the dismiss-on-move filter (if any) so we don't accumulate
        # watchers across re-shows and don't keep stale references to
        # ancestors that may be torn down independently.
        self._detach_dismiss_on_move_filter()

        # Cascade to adopted transient children: a child popup opened from
        # within this menu is parented to the wrapped widget (a sibling), so
        # hiding this menu does NOT reach it through the QObject tree. Hide the
        # family explicitly here so closing the menu can't leave orphan popups.
        self._hide_transient_children()

        # CRITICAL FIX: Restore focus to prevent application focus loss
        # Qt.Tool windows can cause focus loss when hidden
        focus_target = None

        # Prefer the window that was active before menu showed
        if self._active_window_before_show:
            app = QtWidgets.QApplication.instance()
            if app and self._active_window_before_show in app.topLevelWidgets():
                focus_target = self._active_window_before_show

        # Fallback to parent window if still visible
        if not focus_target and self.parent() and self.parent().isVisible():
            focus_target = self.parent().window()

        # Restore focus if we found a target
        if focus_target:
            focus_target.raise_()
            focus_target.activateWindow()
            self.logger.debug(f"hideEvent: Restored focus to {focus_target}")

        super().hideEvent(event)

        # Emit signal after hide event is processed
        self.on_hidden.emit()

        if self._persistent_mode:
            self.disable_persistent_mode()

    def _apply_position(self):
        """Apply the configured position setting with caching for performance."""
        # Cursor position - always recalculate (cursor moves)
        if self.position == "cursorPos":
            MenuPositioner.center_on_cursor(self)
            return

        # Fixed coordinate - cache it
        if isinstance(self.position, (tuple, list, set, QtCore.QPoint)):
            # Only recalculate if position changed
            if self._cached_menu_position != self.position:
                MenuPositioner.position_at_coordinate(self, self.position)
                self._cached_menu_position = self.position
            else:
                # Use cached position
                if isinstance(self._cached_menu_position, QtCore.QPoint):
                    self.move(self._cached_menu_position)
                else:
                    self.move(
                        QtCore.QPoint(
                            self._cached_menu_position[0], self._cached_menu_position[1]
                        )
                    )
            return

        # Parent-relative positioning - cache based on parent global position
        if self.parent() and isinstance(self.position, str):
            anchor = getattr(self, "_current_anchor_widget", None) or self.parent()

            # Create cache key from anchor's GLOBAL position and size
            # Use mapToGlobal to get screen coordinates so cache invalidates when window moves
            anchor_global_pos = anchor.mapToGlobal(QtCore.QPoint(0, 0))
            anchor_geo = (
                anchor_global_pos.x(),
                anchor_global_pos.y(),
                anchor.width(),
                anchor.height(),
                self.position,
            )

            # Check if we can use cached position
            if self._last_parent_geometry == anchor_geo and self._cached_menu_position:
                self.move(self._cached_menu_position)
                # Still need to handle width matching (cheap operation) - use refactored method
                MenuPositioner.apply_width_matching(
                    self, anchor, self.match_parent_width, self.position, self.logger
                )
                return

            # Recalculate position and apply width matching - use refactored combined method
            MenuPositioner.position_and_match_width(
                menu=self,
                anchor_widget=anchor,
                position=self.position,
                match_parent_width=self.match_parent_width,
                logger=self.logger,
            )

            # Cache the calculated position
            self._last_parent_geometry = anchor_geo
            self._cached_menu_position = self.pos()

    def eventFilter(self, widget, event):
        """Handle events for the menu and its children.

        This filter handles:
        - Parent widget clicks to toggle menu visibility
        - Parent hide events to auto-hide menu
        - Item interactions to emit signals
        """
        event_type = event.type()
        parent_widget = self._get_anchor_widget()

        if event_type == QtCore.QEvent.MouseButtonPress and widget is parent_widget:
            # Use centralized trigger logic
            if self._should_trigger(event.button()):
                new_state = not self.isVisible()
                # Don't hide if pinned (but allow showing)
                if not new_state and self.is_pinned:
                    self.logger.debug(
                        "eventFilter: Menu is pinned, ignoring hide request"
                    )
                else:
                    self.logger.debug(
                        f"eventFilter: Parent clicked, toggling menu visibility to {new_state}"
                    )
                    self.setVisible(new_state)

        elif event_type == QtCore.QEvent.Hide and widget is parent_widget:
            # Hide menu when parent is hidden (unless pinned)
            if self.isVisible() and not self.is_pinned:
                self.hide()

        elif event_type == QtCore.QEvent.MouseButtonRelease:
            if widget in self.get_items():
                self.logger.debug(
                    f"eventFilter: Item interacted: {widget.objectName() or type(widget).__name__}"
                )
                self.on_item_interacted.emit(widget)

        return super().eventFilter(widget, event)

    def trigger_from_widget(
        self,
        widget: Optional[QtWidgets.QWidget] = None,
        *,
        button: QtCore.Qt.MouseButton = QtCore.Qt.LeftButton,
    ) -> None:
        """Toggle visibility using the same rules as the parent click event.

        This method allows programmatic triggering of the menu without
        requiring a parent widget or event filter. It respects the same
        trigger button constraints as interactive clicks.

        Parameters:
            widget: Optional anchor widget to position the menu relative to
            button: The mouse button to simulate (default: LeftButton)
        """
        # Don't allow hiding if menu is pinned
        if self.is_pinned:
            return

        # Use centralized trigger logic
        if not self._should_trigger(button):
            return

        # Toggle visibility
        if not self.isVisible():
            # Show using popup method if we have an anchor widget
            if widget:
                self.show_as_popup(
                    anchor_widget=widget, position=self.position or "bottom"
                )
            else:
                self.setVisible(True)
                self.raise_()
                self.activateWindow()
        else:
            self.hide()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    menu = Menu(position="cursorPos", setTitle="Drag Me")

    # Grid layout example
    # a = menu.add(["Label A", "Label B"])
    a = menu.add("Label A")
    b = menu.add("Label B")
    c = menu.add("QDoubleSpinBox", set_by_value=1.0, row=0, col=1)
    d = menu.add("QDoubleSpinBox", set_by_value=2.0, row=1, col=1)

    menu.on_item_interacted.connect(lambda x: print(x))

    menu.style.set(theme="dark")

    menu.show()
    print(menu.get_items())
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
