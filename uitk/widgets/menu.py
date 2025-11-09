# !/usr/bin/python
# coding=utf-8
import inspect
import time
from dataclasses import dataclass, field
from typing import Optional, Union, Callable, Dict, Any
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk
from uitk.widgets.header import Header
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
    "QComboBox": QtWidgets.QComboBox,
    "QSlider": QtWidgets.QSlider,
}


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
    add_apply_button: bool = False
    hide_on_leave: bool = False
    match_parent_width: bool = True
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
            "add_header": True,
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

    Encapsulates all action button creation, configuration, and visibility management.
    """

    def __init__(self, menu_widget: QtWidgets.QWidget):
        """Initialize the action button manager.

        Args:
            menu_widget: The menu widget that owns these buttons
        """
        self.menu = menu_widget
        self._buttons: Dict[str, QtWidgets.QPushButton] = {}
        self._container: Optional[QtWidgets.QWidget] = None
        self._layout: Optional[QtWidgets.QHBoxLayout] = None

    @property
    def container(self) -> QtWidgets.QWidget:
        """Get or create the action button container widget."""
        if self._container is None:
            self._container = QtWidgets.QWidget()
            self._container.setObjectName("actionButtonContainer")
            self._container.hide()
            self._layout = QtWidgets.QHBoxLayout(self._container)
            self._layout.setContentsMargins(1, 1, 1, 1)
            self._layout.setSpacing(1)
        return self._container

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
        self, button_id: str, config: _ActionButtonConfig
    ) -> QtWidgets.QPushButton:
        """Add an action button to the container."""
        button = self.create_button(button_id, config)
        _ = self.container  # Ensure container exists
        self._layout.addWidget(button)
        return button

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
            # Auto-hide container if no buttons are visible
            if self._container and not any(
                btn.isVisible() for btn in self._buttons.values()
            ):
                self._container.hide()
            return True
        return False

    def has_visible_buttons(self) -> bool:
        """Check if any buttons are currently visible."""
        return any(btn.isVisible() for btn in self._buttons.values())


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

        anchor_width = anchor_widget.width()
        if menu.width() != anchor_width:
            menu.setFixedWidth(anchor_width)
            if logger:
                logger.debug(f"MenuPositioner: Matched anchor width: {anchor_width}px")

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
        # Apply positioning
        if anchor_widget:
            MenuPositioner.position_relative_to_widget(menu, anchor_widget, position)
        elif position == "cursorPos":
            MenuPositioner.center_on_cursor(menu)
        elif isinstance(position, (tuple, list, QtCore.QPoint)):
            MenuPositioner.position_at_coordinate(menu, position)
        else:
            MenuPositioner.center_on_cursor(menu)

        # Apply width matching
        MenuPositioner.apply_width_matching(
            menu, anchor_widget, match_parent_width, position, logger
        )


class Menu(QtWidgets.QWidget, AttributesMixin, ptk.LoggingMixin):
    """A custom Qt Widget that serves as a popup menu with additional features.

    The Menu class inherits from QtWidgets.QWidget and provides a customizable
    popup menu with features such as draggable headers and action buttons.
    The menu can be positioned relative to the cursor, a specific coordinate,
    a widget, or its parent.

    Attributes:
        on_item_added (QtCore.Signal): Signal emitted when an item is added to the menu.
        on_item_interacted (QtCore.Signal): Signal emitted when an item in the menu is interacted with.
    """

    on_item_added = QtCore.Signal(object)
    on_item_interacted = QtCore.Signal(object)

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

        Returns:
            Menu: Configured dropdown menu instance

        Example:
            menu = Menu.create_dropdown_menu(widget, position='bottom')
            menu.add("Option 1")
            menu.add("Option 2")
        """
        config = MenuConfig.for_dropdown_menu(parent, **overrides)
        return cls.from_config(config)

    @classmethod
    def create_popup_menu(cls, parent: Optional[QtWidgets.QWidget] = None, **overrides):
        """Factory method: Create a popup menu with no auto-trigger.

        Args:
            parent: Parent widget
            **overrides: Override any default parameters

        Returns:
            Menu: Configured popup menu instance

        Example:
            menu = Menu.create_popup_menu(widget)
            menu.add("Item 1")
            menu.show_as_popup(position='cursorPos')
        """
        config = MenuConfig.for_popup_menu(parent, **overrides)
        return cls.from_config(config)

    @classmethod
    def from_config(cls, config: MenuConfig):
        """Create a Menu from a MenuConfig object.

        This allows for more flexible configuration and better testability.

        Args:
            config: MenuConfig instance

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
            add_apply_button=config.add_apply_button,
            hide_on_leave=config.hide_on_leave,
            match_parent_width=config.match_parent_width,
            **config.extra_attrs,
        )

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
        add_apply_button: bool = False,
        hide_on_leave: bool = False,
        match_parent_width: bool = True,
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
            add_apply_button (bool, optional): Whether to add an apply button. Defaults to False.
                The apply button will emit the parent's 'clicked' signal if available.
            hide_on_leave (bool, optional): Whether to automatically hide the menu when the mouse leaves. Defaults to False.
            match_parent_width (bool, optional): Whether to match the parent widget's width when using positioned menus
                (e.g., position="bottom"). Defaults to True. Only applies when position is relative to parent (not "cursorPos").
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
        # Track initialization time (imports now at module level)
        self._init_start_time = time.perf_counter()
        _step_time = self._init_start_time

        # PERFORMANCE: Defer parent assignment to avoid Qt parent-child overhead during init
        # Store parent for later use but create QWidget without parent initially
        self._deferred_parent = parent
        self._parent_assigned = False
        super().__init__()  # Create QWidget without parent - avoids parent-child tree congestion

        # Disable debug logging to eliminate logging overhead
        self.logger.setLevel(log_level)

        def _log_step(step_name):
            nonlocal _step_time
            now = time.perf_counter()
            duration_ms = (now - _step_time) * 1000
            total_ms = (now - self._init_start_time) * 1000
            self.logger.debug(
                f"Menu.__init__ [{step_name}]: {duration_ms:.3f}ms (total: {total_ms:.3f}ms)"
            )
            _step_time = now

        _log_step("super().__init__")

        if name is not None:
            if not isinstance(name, str):
                raise TypeError(f"Expected 'name' to be a string, got {type(name)}")
            self.setObjectName(name)
        _log_step("setObjectName")

        # Set trigger button using ConvertMixin
        self.trigger_button = trigger_button
        _log_step("trigger_button")

        self.position = position
        self.min_item_height = min_item_height
        self.max_item_height = max_item_height
        self.fixed_item_height = fixed_item_height
        self.add_header = add_header
        self.add_apply_button = add_apply_button
        self.hide_on_leave = hide_on_leave
        self.match_parent_width = match_parent_width
        self.kwargs = kwargs
        self.widget_data = {}
        self.prevent_hide = False
        self._event_filters_installed = False  # Track filter state
        self._mouse_has_entered = False  # Track if mouse has entered menu at least once
        self._current_anchor_widget = None  # Temporary anchor widget for show_as_popup
        _log_step("basic_attrs")

        # Action button manager (replaces individual button state variables)
        self._button_manager = ActionButtonManager(self)
        _log_step("ActionButtonManager")

        # Lazy initialization flags
        self._ui_initialized = False
        self._layout_created = False
        self._style_initialized = False

        # Initialize attributes as None - will be created lazily
        self.layout = None
        self.gridLayout = None
        self.centralWidgetLayout = None
        self._central_widget = None
        self.style = None
        self.header = None  # Created in init_layout() if add_header=True

        # Auto-hide timer - create lazily
        self._leave_timer: Optional[QtCore.QTimer] = None
        # Note: Timer creation deferred to first show() if hide_on_leave is True

        # Position caching for performance
        self._last_parent_geometry = None
        self._cached_menu_position = None

        # NEW: Flag to track if popup window setup has been done
        self._popup_setup_done = False
        _log_step("lazy_init_flags")

        # CRITICAL FIX: Defer _setup_as_popup() to first show
        # Creating 11+ top-level windows during __init__ causes progressive Qt window manager slowdown
        # Only configure window flags when menu is actually shown
        # self._setup_as_popup()  # DEFERRED
        _log_step("_setup_as_popup_deferred")

        # CRITICAL FIX 2: Defer ALL style-related operations to first show
        # setProperty() triggers Qt style system recalculation across ALL widgets
        # With 11+ menus, each setProperty call checks all existing menus -> O(n²) slowdown
        # Store properties to apply later
        self._deferred_properties = {"class": "translucentBgWithBorder"}
        self._deferred_size_policy = (
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )
        self._deferred_min_width = 147
        self._deferred_kwargs = kwargs.copy() if kwargs else {}

        # DON'T call setProperty, setSizePolicy, setMinimumWidth, or set_attributes here
        # They will be applied in show() when actually needed
        _log_step("widget_properties")
        _log_step("set_attributes")

        # PROOF THIS CODE IS RUNNING: Debug output (AFTER timing to avoid affecting measurements)
        self.logger.debug(
            "🔧 STYLE DEFERRAL FIX ACTIVE - Properties stored, not applied"
        )

        init_duration = (
            time.perf_counter() - self._init_start_time
        ) * 1000  # Convert to ms
        self.logger.debug(
            f"Menu.__init__: TOTAL initialization completed in {init_duration:.3f}ms (lazy mode - UI deferred)"
        )

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

        Timer creation is deferred until first show() for performance.
        This setter only stores the configuration.

        Parameters:
            value: True to enable auto-hide on leave, False to disable
        """
        self._hide_on_leave = bool(value)

        if self._hide_on_leave:
            # Just store the setting - timer will be created on first show
            pass
        else:
            # Disable: stop and clear timer if it exists
            if hasattr(self, "_leave_timer") and self._leave_timer is not None:
                self._leave_timer.stop()
                self._leave_timer.deleteLater()
                self._leave_timer = None

    def _ensure_ui_initialized(self):
        """Ensure basic UI is initialized (called on first use)."""
        if not self._ui_initialized:
            self._ui_initialized = True
            self.logger.debug("Menu._ensure_ui_initialized: Initializing UI components")

    def _ensure_layout_created(self):
        """Ensure layout is created (called when first item is added)."""
        if not self._layout_created:
            self._layout_created = True
            self.init_layout()
            self.logger.debug("Menu._ensure_layout_created: Layout created")

    def _ensure_style_initialized(self):
        """Ensure stylesheet is initialized (called on first show)."""
        if not self._style_initialized:
            self._style_initialized = True
            self.style = StyleSheet(self, log_level="WARNING")
            self.logger.debug("Menu._ensure_style_initialized: StyleSheet created")

    def _ensure_timer_created(self):
        """Ensure timer is created if hide_on_leave is enabled (called on first show)."""
        if self.hide_on_leave and self._leave_timer is None:
            self._setup_leave_timer()
            self.logger.debug(
                "Menu._ensure_timer_created: Timer created for hide_on_leave"
            )

    def _install_event_filters(self):
        """Install event filters on the menu and its parent.

        This method is called when the first item is added to the menu.
        It ensures we don't waste resources on empty menus.
        """
        if self._event_filters_installed:
            return  # Already installed

        self._ensure_parent_assigned()  # Assign parent if needed for event filter

        self.installEventFilter(self)
        if self.parent():
            self.parent().installEventFilter(self)

        self._event_filters_installed = True
        self.logger.debug("Menu._install_event_filters: Event filters installed")

    def _uninstall_event_filters(self):
        """Uninstall event filters from the menu and its parent.

        This method is called when the menu becomes empty.
        It frees up resources by removing unnecessary event monitoring.
        """
        if not self._event_filters_installed:
            return  # Already uninstalled

        self.removeEventFilter(self)
        if self.parent():
            self.parent().removeEventFilter(self)

        self._event_filters_installed = False
        self.logger.debug("Menu._uninstall_event_filters: Event filters uninstalled")

    def _ensure_parent_assigned(self):
        """Assign deferred parent if not already done.

        This is called by methods that need the parent relationship
        established before popup setup would normally occur.
        """
        if not self._parent_assigned and self._deferred_parent is not None:
            self.setParent(self._deferred_parent)
            self._parent_assigned = True
            self.logger.debug(f"Menu._ensure_parent_assigned: Assigned deferred parent")

    def _setup_as_popup(self):
        """Configure this menu as a popup window."""
        # PERFORMANCE: Assign deferred parent now (if any)
        if not self._parent_assigned and self._deferred_parent is not None:
            self.setParent(self._deferred_parent)
            self._parent_assigned = True
            self.logger.debug(
                f"Menu._setup_as_popup: Assigned deferred parent {self._deferred_parent}"
            )

        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)

        # If no parent was provided (including deferred), try to parent to active window
        if self.parent() is None:
            try:
                app = QtWidgets.QApplication.instance()
                if app:
                    active_window = app.activeWindow()
                    if active_window and active_window != self:
                        self.setParent(active_window, self.windowFlags())
                        self.logger.debug(
                            f"Menu._setup_as_popup: Parented to active window {active_window}"
                        )
            except Exception as e:
                self.logger.debug(
                    f"Menu._setup_as_popup: Could not parent to active window: {e}"
                )

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

        # CRITICAL FIX: Lazy popup window setup on first show
        # Deferring window flag setup prevents Qt window manager congestion during bulk menu creation
        if not self._popup_setup_done:
            # Apply deferred style properties NOW (when menu is actually needed)
            # This avoids Qt style system O(n²) slowdown during bulk menu creation
            if hasattr(self, "_deferred_properties"):
                for prop_name, prop_value in self._deferred_properties.items():
                    self.setProperty(prop_name, prop_value)

            if hasattr(self, "_deferred_size_policy"):
                self.setSizePolicy(*self._deferred_size_policy)

            if hasattr(self, "_deferred_min_width"):
                self.setMinimumWidth(self._deferred_min_width)

            if hasattr(self, "_deferred_kwargs"):
                self.set_attributes(**self._deferred_kwargs)

            self._setup_as_popup()
            self._popup_setup_done = True
            self.logger.debug("Menu.show_as_popup: Lazy popup window setup completed")

        # Store anchor widget temporarily for _apply_position to use
        # This allows proper width matching even when parent is different
        self._current_anchor_widget = anchor_widget

        # Use the refactored positioning method (DRY - combines positioning and width matching)
        MenuPositioner.position_and_match_width(
            menu=self,
            anchor_widget=anchor_widget or self.parent(),
            position=position,
            match_parent_width=self.match_parent_width,
            logger=self.logger,
        )

        # Ensure stay-on-top is enabled before the window becomes visible.
        # Setting the flag while hidden avoids native teardown/flash cycles.
        if not (self.windowFlags() & QtCore.Qt.WindowStaysOnTopHint):
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        # Show the menu
        self.show()
        self.raise_()
        self.activateWindow()

        # Mark mouse as entered for hide_on_leave to work immediately
        # This is set here because the menu was intentionally opened
        if self.hide_on_leave:
            self._mouse_has_entered = True

        # Clear anchor widget after show
        self._current_anchor_widget = None

        self.logger.debug("Menu.show_as_popup: Menu shown successfully")

    def setCentralWidget(self, widget, overwrite=False):
        if not overwrite and getattr(self, "_central_widget", None) is widget:
            return  # skip if same

        current_central_widget = getattr(self, "_central_widget", None)
        if current_central_widget and current_central_widget is not widget:
            current_central_widget.setParent(None)  # Avoid deleteLater()

        self._central_widget = widget
        self._central_widget.setProperty("class", "centralWidget")
        self.layout.addWidget(self._central_widget)

    def centralWidget(self):
        """Return the central widget."""
        return self._central_widget

    def init_layout(self):
        """Initialize the menu layout. Called lazily on first item add."""
        layout_start = time.perf_counter()
        _step_time = layout_start

        def _log_step(step_name):
            nonlocal _step_time
            now = time.perf_counter()
            duration_ms = (now - _step_time) * 1000
            total_ms = (now - layout_start) * 1000
            self.logger.debug(
                f"Menu.init_layout [{step_name}]: {duration_ms:.3f}ms (total: {total_ms:.3f}ms)"
            )
            _step_time = now

        # Guard against double initialization
        if self.layout is not None:
            self.logger.debug("Menu.init_layout: Already initialized, skipping")
            return

        # CRITICAL OPTIMIZATION: Disable updates AND layout calculation
        updates_were_enabled = self.updatesEnabled()
        self.setUpdatesEnabled(False)

        # Also block signals to prevent event propagation during setup
        was_blocked = self.blockSignals(True)

        try:
            # Create a new layout with no margins
            self.layout = QtWidgets.QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(1)
            # Disable layout activation during setup
            self.layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
            self.setLayout(self.layout)
            _log_step("QVBoxLayout_created")

            # Create a central widget WITHOUT parent first to avoid tree overhead
            # Parent will be assigned when added to layout
            central_widget = QtWidgets.QWidget()
            self.setCentralWidget(central_widget)
            _log_step("setCentralWidget")

            # Create a QVBoxLayout inside the central widget
            self.centralWidgetLayout = QtWidgets.QVBoxLayout(self._central_widget)
            self.centralWidgetLayout.setContentsMargins(1, 1, 1, 1)
            self.centralWidgetLayout.setSpacing(1)
            self.centralWidgetLayout.setSizeConstraint(
                QtWidgets.QLayout.SetNoConstraint
            )
            _log_step("centralWidgetLayout")

            # Create a form layout inside the QVBoxLayout
            self.gridLayout = QtWidgets.QGridLayout()
            self.gridLayout.setContentsMargins(0, 0, 0, 0)
            self.gridLayout.setSpacing(1)
            self.gridLayout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
            _log_step("gridLayout")

            if self.add_header:
                # Create Header instance WITHOUT explicit parent to avoid tree overhead
                # Parent will be assigned when added to layout
                self.header = Header(hide_button=True)
                self.centralWidgetLayout.addWidget(self.header)
                _log_step("Header_created")

            # Add grid layout to the central widget layout
            self.centralWidgetLayout.addLayout(self.gridLayout)
            _log_step("addLayout")

            total_duration = (time.perf_counter() - layout_start) * 1000
            self.logger.debug(
                f"Menu.init_layout: TOTAL layout initialization in {total_duration:.3f}ms"
            )
        finally:
            # Restore signal blocking state
            self.blockSignals(was_blocked)

            # Re-enable updates after layout creation
            if updates_were_enabled:
                self.setUpdatesEnabled(True)

            # Activate layout now that setup is complete
            if self.layout:
                self.layout.activate()

    def _setup_leave_timer(self):
        """Set up timer for auto-hide on mouse leave."""
        self._leave_timer = QtCore.QTimer(self)
        self._leave_timer.setInterval(100)  # Check every 100ms
        self._leave_timer.timeout.connect(self._check_cursor_position)
        self.logger.debug("_setup_leave_timer: Leave timer created")

    def _check_cursor_position(self):
        """Check if cursor is outside menu bounds and hide if so.

        Only hides if the mouse has entered the menu at least once.
        This prevents immediate hiding when menu is positioned away from cursor.
        """
        if not self.isVisible():
            self._leave_timer.stop()
            return

        # Get cursor position relative to this widget
        cursor_pos = self.mapFromGlobal(QtGui.QCursor.pos())

        # Check if cursor is within widget bounds
        if self.rect().contains(cursor_pos):
            # Mouse has entered the menu
            if not self._mouse_has_entered:
                self.logger.debug(
                    "_check_cursor_position: Mouse entered menu for first time"
                )
            self._mouse_has_entered = True
        elif self._mouse_has_entered:
            # Only hide if mouse has entered at least once before
            self.logger.debug("_check_cursor_position: Cursor outside menu, hiding")
            self.hide()
            self._leave_timer.stop()

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

        # Add the action button container to the layout
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

    def get_all_children(self):
        children = self.findChildren(QtWidgets.QWidget)
        return children

    @property
    def contains_items(self) -> bool:
        """Check if the QMenu contains any items."""
        # Handle lazy initialization - gridLayout may not exist yet
        if self.gridLayout is None or not self._layout_created:
            return False
        return bool(self.gridLayout.count())

    def title(self) -> str:
        """Get the menu's title text."""
        if self.header is None:
            return ""
        return self.header.text()

    def setTitle(self, title="") -> None:
        """Set the menu's title to the given string.
        If no title is given, the function will attempt to use the menu parents text.

        Parameters:
            title (str): Text to apply to the menu's title.
        """
        # Ensure layout is created so header exists
        self._ensure_layout_created()
        if self.header is not None:
            self.header.setText(title)

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
        add_start = time.perf_counter()
        _step_time = add_start

        def _log_step(step_name):
            nonlocal _step_time
            now = time.perf_counter()
            duration_ms = (now - _step_time) * 1000
            total_ms = (now - add_start) * 1000
            self.logger.debug(
                f"Menu.add [{step_name}]: {duration_ms:.3f}ms (total: {total_ms:.3f}ms)"
            )
            _step_time = now

        self.logger.debug(
            f"Menu.add: Adding item type={type(x).__name__}, row={row}, col={col}, kwargs={list(kwargs.keys())}"
        )

        # CRITICAL OPTIMIZATION: Disable updates AND layout recalculation during add
        # This prevents Qt from recalculating layout/geometry on every operation
        updates_were_enabled = self.updatesEnabled()
        self.setUpdatesEnabled(False)

        # Block signals to prevent cascading updates
        was_blocked = self.blockSignals(True)

        # Suspend layout activation if layout exists
        layout_was_enabled = False
        if self.gridLayout:
            layout_was_enabled = self.gridLayout.isEnabled()
            self.gridLayout.setEnabled(False)

        try:
            # Lazy initialization: create layout on first item add
            self._ensure_layout_created()
            _log_step("ensure_layout")

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

            _log_step("type_check")

            if isinstance(x, str):
                # OPTIMIZATION: Create widgets WITHOUT parent to avoid Qt tree overhead
                # Parent will be assigned implicitly when added to gridLayout
                widget_class = _WIDGET_TYPE_CACHE.get(x)
                if widget_class:
                    widget = widget_class()
                else:
                    try:
                        widget = getattr(QtWidgets, x)()
                    except (AttributeError, TypeError):
                        widget = QtWidgets.QLabel()
                        widget.setText(x)
                _log_step("widget_creation_str")

            elif isinstance(x, QtWidgets.QWidget) or (
                inspect.isclass(x) and issubclass(x, QtWidgets.QWidget)
            ):
                widget = x() if callable(x) else x
                _log_step("widget_creation_class")

            else:
                raise TypeError(
                    f"Unsupported item type: expected str, QWidget, QAction, or a collection (list, tuple, set, dict, zip, map), got '{type(x)}'"
                )

            widget.item_text = lambda i=widget: self.get_item_text(i)
            widget.item_data = lambda i=widget: self.get_item_data(i)
            _log_step("widget_setup")

            if row is None:
                row = 0
                while self.gridLayout.itemAtPosition(row, col) is not None:
                    row += 1

            if colSpan is None:
                colSpan = self.gridLayout.columnCount() or 1
            _log_step("position_calc")

            # Install event filters when adding the first item
            was_empty = not self.contains_items

            self.gridLayout.addWidget(widget, row, col, rowSpan, colSpan)
            self.on_item_added.emit(widget)
            self.set_item_data(widget, data)
            _log_step("addWidget")

            if self.min_item_height is not None:
                widget.setMinimumHeight(self.min_item_height)
            if self.max_item_height is not None:
                widget.setMaximumHeight(self.max_item_height)
            if self.fixed_item_height is not None:
                widget.setFixedHeight(self.fixed_item_height)
            _log_step("height_constraints")

            self.set_attributes(widget, **kwargs)
            widget.installEventFilter(self)
            setattr(self, widget.objectName(), widget)
            _log_step("attributes_filter")

            # Only resize if menu is visible (prevents flash during lazy initialization)
            if self.isVisible():
                self.resize(self.sizeHint())
            self.layout.invalidate()
            _log_step("resize_invalidate")

            # OPTIMIZATION: Defer event filter installation to showEvent()
            # This eliminates 37-180ms from add() operations
            # Setup apply button on first item add (if requested and has connections)
            if was_empty:
                self.logger.debug(
                    f"Menu.add: First item added (event filters deferred to show)"
                )
                if self.add_apply_button and not self._button_manager.get_button(
                    "apply"
                ):
                    self._setup_apply_button()
                # Update apply button visibility for first item
                if self.add_apply_button:
                    self._update_apply_button_visibility()
            elif self.add_apply_button:
                # Only update visibility if apply button exists and is enabled
                # This avoids redundant checks when add_apply_button=False
                self._update_apply_button_visibility()
            _log_step("apply_button_setup")

            total_duration = (time.perf_counter() - add_start) * 1000
            self.logger.debug(
                f"Menu.add: TOTAL added widget={widget.objectName() or type(widget).__name__}, total_items={self.gridLayout.count()} in {total_duration:.3f}ms"
            )
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

            # Activate layout to apply all changes at once
            if self.layout:
                self.layout.activate()

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

    def get_padding(widget):
        """Get the padding values around a widget.

        This method calculates the padding values (distance from content to frame boundary) for a widget in all four directions.

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
        if self.layout is None:
            return super().sizeHint()

        total_height = 0
        total_width = 0

        for i in range(self.layout.count()):
            widget = self.layout.itemAt(i).widget()
            if widget:
                total_height += widget.sizeHint().height() + self.layout.spacing()
                total_width = max(total_width, widget.sizeHint().width())

        # Adjust for layout's top and bottom margins
        total_height += (
            self.layout.contentsMargins().top() + self.layout.contentsMargins().bottom()
        )
        # Adjust for layout's left and right margins for width
        total_width += (
            self.layout.contentsMargins().left() + self.layout.contentsMargins().right()
        )

        return QtCore.QSize(total_width, total_height)

    def showEvent(self, event) -> None:
        """Handle show event with positioning (optimized for performance)."""
        # CRITICAL OPTIMIZATION: Lazy popup window setup on first show
        # Deferring window flag setup prevents Qt window manager congestion during bulk menu creation
        if not self._popup_setup_done:
            self._setup_as_popup()
            self._popup_setup_done = True
            self.logger.debug("showEvent: Lazy popup window setup completed")

        # CRITICAL OPTIMIZATION: Install event filters on first show, not during add()
        # This eliminates 37-180ms from add() calls
        if not self._event_filters_installed and self.contains_items:
            self._install_event_filters()

        # Lazy initialization: ensure style and timer are created on first show
        # These check their own flags internally, so safe to call every time
        self._ensure_style_initialized()
        self._ensure_timer_created()

        # Reset mouse entered flag when menu is shown
        self._mouse_has_entered = False

        # Only auto-position if we have a position setting
        # _apply_position now caches calculations for performance
        if self.position:
            self._apply_position()

        # Update apply button visibility when menu is shown
        # Only if apply button feature is enabled
        if self.add_apply_button:
            self._update_apply_button_visibility()

        # Start leave timer if enabled
        # Timer is only created if hide_on_leave is True, so this is safe
        if self._leave_timer:
            self._leave_timer.start()
            self.logger.debug("showEvent: Leave timer started")

        super().showEvent(event)

    def hideEvent(self, event) -> None:
        """Handle hide event."""
        # Stop leave timer when menu is hidden
        if self._leave_timer and self._leave_timer.isActive():
            self._leave_timer.stop()
            self.logger.debug("hideEvent: Leave timer stopped")

        super().hideEvent(event)

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

        # Parent-relative positioning - cache based on parent geometry
        if self.parent() and isinstance(self.position, str):
            anchor = getattr(self, "_current_anchor_widget", None) or self.parent()

            # Create cache key from anchor geometry and position
            anchor_geo = (
                anchor.geometry().x(),
                anchor.geometry().y(),
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
        - Item interactions to emit signals
        """
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if widget is self.parent():
                # Use centralized trigger logic
                if self._should_trigger(event.button()):
                    new_state = not self.isVisible()
                    self.logger.debug(
                        f"eventFilter: Parent clicked, toggling menu visibility to {new_state}"
                    )
                    self.setVisible(new_state)

        elif event.type() == QtCore.QEvent.MouseButtonRelease:
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
        if self.prevent_hide:
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
