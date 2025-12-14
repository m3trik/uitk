# !/usr/bin/python
# coding=utf-8
import inspect
import time
import warnings
from dataclasses import dataclass, field
from typing import Optional, Union, Callable, Dict, Any, Tuple
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk

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
    "QComboBox": QtWidgets.QComboBox,
    "QSlider": QtWidgets.QSlider,
    "Separator": Separator,
    "QSeparator": Separator,  # Alias for consistency with Qt naming
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
            self._layout.setContentsMargins(0, 0, 0, 0)
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
        horizontal_padding = 0

        layout = menu.layout()
        if layout:
            margins = layout.contentsMargins()
            horizontal_padding += margins.left() + margins.right()

        frame = getattr(menu, "_frame", None)
        if frame:
            frame_layout = frame.layout()
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
        hide_on_leave: bool = False,
        match_parent_width: bool = True,
        ensure_on_screen: bool = True,
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

        # Widget structure
        self.layout: Optional[QtWidgets.QVBoxLayout] = None
        self.gridLayout: Optional[QtWidgets.QGridLayout] = None
        self.centralWidgetLayout: Optional[QtWidgets.QVBoxLayout] = None
        self._central_widget: Optional[QtWidgets.QWidget] = None
        self.style: Optional[StyleSheet] = None
        self.header: Optional[Header] = None
        self.footer: Optional[Footer] = None

        # Helpers and caches
        self._button_manager = ActionButtonManager(self)
        self._leave_timer: Optional[QtCore.QTimer] = None
        self._last_parent_geometry = None
        self._cached_menu_position = None
        self._popup_configured = False  # Track if popup setup has been done

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
        self.add_header = add_header
        self.add_footer = add_footer
        self.add_apply_button = add_apply_button
        self.match_parent_width = match_parent_width

        self._hide_on_leave = False
        self.hide_on_leave = hide_on_leave
        self.ensure_on_screen = ensure_on_screen

        # Base styling handled via QSS type selectors
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.setMinimumWidth(147)
        if kwargs:
            self.set_attributes(**kwargs)

        # Build UI immediately
        self.init_layout()
        self.style = StyleSheet(self, log_level="WARNING")

        # Configure as popup window
        self._setup_as_popup()

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
            hide_on_leave=config.hide_on_leave,
            match_parent_width=config.match_parent_width,
            ensure_on_screen=config.ensure_on_screen,
            **config.extra_attrs,
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
            "had_header": bool(self.header),
        }

        self._persistent_mode = True

        # Block auto-hiding behaviour while in persistent mode
        self.prevent_hide = True
        self.hide_on_leave = False

        # Ensure the menu has a header to host the hide button
        self._ensure_layout_created()
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
        if self.layout is None or self.gridLayout is None:
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

    def _setup_as_popup(self):
        """Configure this menu as a popup window.

        Only runs once to avoid repeated reparenting issues.
        """
        if self._popup_configured:
            return

        self._popup_configured = True

        # Store current parent before changing window flags
        parent_widget = self.parentWidget()

        # Set window flags to make this a tool window
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)

        # Re-apply parent with the new window flags so Qt treats this as a tool window
        if parent_widget is not None:
            self.setParent(parent_widget, self.windowFlags())
        else:
            # If no parent, try to parent to the active window
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

    def show(self) -> None:
        """Show the menu."""
        super().show()
        if self.ensure_on_screen:
            # Use a timer to ensure the window geometry is updated before checking
            QtCore.QTimer.singleShot(0, self._ensure_on_screen)

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

        # Don't use WindowStaysOnTopHint as it keeps menu on top even when other apps are focused
        # The Tool window flag with raise_() and activateWindow() is sufficient for popup behavior

        # Ensure geometry matches current content before showing
        self.adjustSize()
        self._resize_height_to_content()

        # Show the menu
        self.show()
        self.raise_()
        self.activateWindow()

        # Clear anchor widget after show
        self._current_anchor_widget = None

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
        # Guard against double initialization
        if self.layout is not None:
            return

        # CRITICAL OPTIMIZATION: Disable updates AND layout calculation
        updates_were_enabled = self.updatesEnabled()
        self.setUpdatesEnabled(False)

        # Also block signals to prevent event propagation during setup
        was_blocked = self.blockSignals(True)

        try:
            # Create outer layout for the translucent window (margins for frame border)
            self.layout = QtWidgets.QVBoxLayout(self)
            # Provide a 2px transparent gutter so translucent borders never touch window edges
            self.layout.setContentsMargins(2, 2, 2, 2)
            self.layout.setSpacing(0)
            self.layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
            self.setLayout(self.layout)

            # Create frame container that will have the border
            self._frame = QtWidgets.QFrame(self)
            self._frame.setObjectName("menuFrame")
            self._frame.setProperty("class", "translucentBgWithBorder")
            self._frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
            self._frame.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
            )
            self.layout.addWidget(self._frame)

            # Create inner layout inside the frame (with spacing for border)
            frame_layout = QtWidgets.QVBoxLayout(self._frame)
            # One extra pixel inside the frame keeps children off the painted border
            frame_layout.setContentsMargins(1, 1, 1, 1)
            frame_layout.setSpacing(1)
            frame_layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

            # Add header to top area
            if self.add_header:
                self.header = Header(config_buttons=["pin"])
                frame_layout.addWidget(self.header)

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

            # Add central widget to frame layout
            frame_layout.addWidget(self._central_widget)

            # Add footer to bottom area (always last)
            if self.add_footer:
                self.footer = Footer(add_size_grip=True)
                frame_layout.addWidget(self.footer)

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

    def _check_cursor_position(self):
        """Check if cursor is outside menu bounds and hide if so.

        Only hides if the mouse has entered the menu at least once.
        This prevents immediate hiding when menu is positioned away from cursor.
        Also respects the pinned state - won't hide if pinned.
        """
        if not self.isVisible():
            self._leave_timer.stop()
            return

        # Don't hide if menu is pinned
        if self.is_pinned:
            return

        # Get cursor position relative to this widget
        cursor_pos = self.mapFromGlobal(QtGui.QCursor.pos())

        # Check if cursor is within widget bounds OR over a child widget
        cursor_inside = self.rect().contains(cursor_pos)

        # Also check if cursor is over a child widget (for nested widgets)
        if not cursor_inside:
            widget_at = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
            if widget_at:
                if self.isAncestorOf(widget_at):
                    cursor_inside = True
                else:
                    # Check for ComboBox popups (which are separate windows)
                    # This prevents the menu from closing when interacting with a dropdown
                    for combo in self.findChildren(QtWidgets.QComboBox):
                        if combo.view() and combo.view().isVisible():
                            # Check if widget_at is the view or part of it (e.g. viewport)
                            if widget_at == combo.view() or combo.view().isAncestorOf(
                                widget_at
                            ):
                                cursor_inside = True
                                break

        if cursor_inside:
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

    def _resize_height_to_content(self) -> None:
        """Collapse stale vertical space before showing the menu again.

        Menus are often rebuilt while hidden. Without explicitly syncing the
        geometry, Qt can reuse the previous height, leaving an empty gap when
        fewer items remain. Keeping the width untouched avoids fighting the
        width-matching logic while still trimming vertical dead space.
        """

        if not self.layout:
            return

        self.layout.activate()
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

    def get_all_children(self):
        children = self.findChildren(QtWidgets.QWidget)
        return children

    @property
    def is_pinned(self) -> bool:
        """Check if the menu is pinned (should not auto-hide).

        This is the single source of truth for pin state checking.
        Checks both the legacy prevent_hide flag and the header's pin button state.

        Returns:
            bool: True if menu should stay visible (pinned), False otherwise
        """
        # Check legacy prevent_hide flag
        if self.prevent_hide:
            return True

        # Check header pin button state (if header exists and has pin functionality)
        if self.header and hasattr(self.header, "pinned"):
            return self.header.pinned

        return False

    @property
    def contains_items(self) -> bool:
        """Check if the QMenu contains any items."""
        # Handle lazy initialization - gridLayout may not exist yet
        if self.gridLayout is None:
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

        # Suspend layout activation if layout exists
        layout_was_enabled = False
        if self.gridLayout:
            layout_was_enabled = self.gridLayout.isEnabled()
            self.gridLayout.setEnabled(False)

        try:
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
                widget_class = _WIDGET_TYPE_CACHE.get(x)
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
            self.on_item_added.emit(widget)
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
            setattr(self, widget.objectName(), widget)

            # Only resize if menu is visible (prevents flash during lazy initialization)
            if self.isVisible():
                self.resize(self.sizeHint())
            self.layout.invalidate()

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
        # Track which window was active before showing menu
        # This allows us to restore focus only if our app was active
        app = QtWidgets.QApplication.instance()
        if app:
            self._active_window_before_show = app.activeWindow()
            self.logger.debug(
                f"showEvent: Active window before show: {self._active_window_before_show}"
            )

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

        # Lazy initialization: ensure style and timer are created on first show
        # These check their own flags internally, so safe to call every time
        self._ensure_style_initialized()
        self._ensure_timer_created()

        # Check if cursor is already inside menu when it appears
        # This prevents immediate hide-on-leave when menu pops up under cursor
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

        # Setup apply button on first show if requested and not already created
        # Deferred to showEvent because parent's signal connections may not exist during add()
        if self.add_apply_button and not self._button_manager.get_button("apply"):
            self._setup_apply_button()
            # Update visibility immediately (this shows the container)
            self._update_apply_button_visibility()
            # Force complete layout update
            if self.layout:
                self.layout.invalidate()
                self.layout.activate()
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

        # Only auto-position if we have a position setting
        # _apply_position now caches calculations for performance
        if self.position:
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
