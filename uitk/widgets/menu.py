# !/usr/bin/python
# coding=utf-8
"""``Menu``: uitk's popup menu widget -- the facade, its configuration and placement.

``Menu`` is a facade over one collaborator per concept in
:mod:`uitk.widgets.menu_parts` (frame and chrome, items, trigger hook, hide on
leave, popup window, action buttons, persistent mode, item registration), each
owning its own state and holding the menu. This module keeps construction, the
public surface, the Qt virtuals and slots (which delegate), the show / hide
lifecycle that orchestrates the parts, and placement (:class:`MenuPositioner`,
``show_as_popup``). Its path is frozen: ``.ui`` headers name
``uitk.widgets.menu``.
"""

from dataclasses import dataclass, field
from typing import Optional, Union, Dict, Any
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk

# From this package:
from uitk._facade import _Forward
from uitk.widgets.header import Header
from uitk.widgets.footer import Footer
from uitk.themes.style_sheet import StyleSheet
from uitk.managers.reset_gesture import ResetGesture
from uitk.widgets.mixins.attributes import AttributesMixin

# The concept parts. The underscore names re-exported here were module
# attributes of this file before the split.
from uitk.widgets.menu_parts._actions import (  # noqa: F401
    ActionButtonManager,
    _ActionButtonConfig,
    _MenuActions,
)
from uitk.widgets.menu_parts._items import (  # noqa: F401
    _HEIGHT_CONSTRAINED_TYPES,
    _LAZY_WIDGET_TYPES,
    _WIDGET_TYPE_CACHE,
    _MenuItems,
)
from uitk.widgets.menu_parts._layout import _MenuFrame
from uitk.widgets.menu_parts._leave import _LEAVE_DEBUG, _MenuLeave  # noqa: F401
from uitk.widgets.menu_parts._persistent_mode import _MenuPersistentMode
from uitk.widgets.menu_parts._popup_window import _MenuPopupWindow
from uitk.widgets.menu_parts._registration import _MenuRegistration
from uitk.widgets.menu_parts._triggers import _MenuTrigger

# Every Menu with a pending deferred-registration queue (see
# ``_MenuRegistration``); the same set object, under its old name.
_menus_awaiting_registration = _MenuRegistration.awaiting_registration


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
    hide_on_trigger: bool = False
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

    # A facade: each concept is a collaborator in ``menu_parts`` that owns its
    # state and holds the menu -- ``_scaffold`` (_MenuFrame), ``_items``,
    # ``_trigger``, ``_leave``, ``_popup`` (_MenuPopupWindow), ``_actions``,
    # ``_persistent`` and ``_registration``. Every public member stays here.
    # The parts reach one another through the menu's own names (public, or a
    # private ``_Forward`` below), so a patch of a menu name reaches every
    # caller. The override points are this class's real methods -- the public
    # surface, the Qt virtuals, the slots (so connections keep a QObject
    # receiver that dies with the menu) and the private hooks a subclass
    # overrides or a test patches on the class (``_shortcut_filter_candidates``,
    # ``_shortcut_filter_emptied``, ``_setup_apply_button``,
    # ``_setup_defaults_button``, ``_prepare_for_show``, ``_apply_position``).
    # A ``_Forward`` name reads, writes and instance-patches its part's member;
    # a subclass method of that name is not what the part runs.

    # Not a Designer widget-box entry: a popup owned by its host widget
    # (`widget.menu`), never placed on a form.
    designer_spec = {"visible": False}

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
        hide_on_trigger: bool = False,
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
            hide_on_trigger (bool, optional): Whether to hide the menu after one of its items is
                interacted with (released on). Defaults to False. Applies to every item; individual
                widgets can be included/excluded via :meth:`set_hide_on_trigger`.
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

        # The parts first: every Qt virtual and slot below delegates to one,
        # so they exist before Qt can call any of them.
        self._scaffold = _MenuFrame(self)
        self._items = _MenuItems(self, empty_message, empty_timeout_ms)
        self._trigger = _MenuTrigger(self)
        self._leave = _MenuLeave(self)
        self._popup = _MenuPopupWindow(self)
        self._actions = _MenuActions(self, add_defaults_button)
        self._persistent = _MenuPersistentMode(self)
        self._registration = _MenuRegistration(self)

        if name is not None:
            if not isinstance(name, str):
                raise TypeError(f"Expected 'name' to be a string, got {type(name)}")
            self.setObjectName(name)

        self.logger.setLevel(log_level)

        # The lifecycle's own state: the anchor ``show_as_popup`` is placing
        # against, the window active before the show (focus goes back to it on
        # hide), the placement cache, and whether the owning MainWindow tracks
        # this menu.
        self._current_anchor_widget = None
        self._active_window_before_show = None
        self._last_parent_geometry = None
        self._cached_menu_position = None
        self._tracked_as_menu = False  # Registered with owning MainWindow.menus()

        # Widget structure (built by the scaffold)
        self.gridLayout: Optional[QtWidgets.QGridLayout] = None
        self.centralWidgetLayout: Optional[QtWidgets.QVBoxLayout] = None
        self.style: Optional[StyleSheet] = None
        self.header: Optional[Header] = None
        self.footer: Optional[Footer] = None

        # hide_on_leave debounce: require this many consecutive out-of-family
        # samples before hiding, so crossing the gap between this menu and a
        # child popup (or a brief excursion) can't dismiss it. Default 1 keeps
        # the legacy single-sample behavior; adopt_transient raises it so only
        # menus that actually spawn children pay the small grace.
        self.leave_grace_samples: int = 1
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

        # The explicit argument wins over what a left-click trigger implied.
        self._leave.enabled = False
        self.hide_on_leave = hide_on_leave
        self.hide_on_trigger = hide_on_trigger
        self.ensure_on_screen = ensure_on_screen

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

        # Popup setup (window-type|FramelessWindowHint reparent + WA_*
        # attributes) is deferred until the menu is actually shown — running
        # it during ``__init__`` creates an OS-level window per Menu, which on
        # Windows produces a brief WM-visible artifact (a flash) for every
        # option_box menu created during ``register_children``.  Deferring it
        # is also what lets the window TYPE be chosen against the popup grab
        # in effect at show time (see ``_resolve_popup_window_type``).
        # Construction leaves the Menu as a hidden child widget;
        # ``show_as_popup`` and ``showEvent`` both call ``_setup_as_popup``
        # (idempotent per resolved window type) before the menu becomes
        # visible.
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

    # ------------------------------------------------------------------
    # Private names, each on the part that owns it (see the class comment)
    # ------------------------------------------------------------------

    # _MenuFrame
    _layout = _Forward("_scaffold", "layout")
    _frame = _Forward("_scaffold", "frame")
    _frame_layout = _Forward("_scaffold", "frame_layout")
    _central_widget = _Forward("_scaffold", "central_widget")
    _pending_title = _Forward("_scaffold", "pending_title")
    _ensure_layout_created = _Forward("_scaffold", "ensure_layout_created")
    _ensure_style_initialized = _Forward("_scaffold", "ensure_style_initialized")
    _ensure_chrome = _Forward("_scaffold", "ensure_chrome")
    _resize_height_to_content = _Forward("_scaffold", "resize_height_to_content")
    _activate_inner_layouts = _Forward("_scaffold", "activate_inner_layouts")
    # _MenuItems
    _add_depth = _Forward("_items", "add_depth")
    _pending_item_added_emits = _Forward("_items", "pending_item_added_emits")
    _empty_message = _Forward("_items", "empty_message")
    _empty_timeout_ms = _Forward("_items", "empty_timeout_ms")
    _empty_placeholder = _Forward("_items", "empty_placeholder")
    _empty_timer = _Forward("_items", "empty_timer")
    _shortcut_hidden_items = _Forward("_items", "shortcut_hidden_items")
    _add_empty_placeholder = _Forward("_items", "add_empty_placeholder")
    _remove_empty_placeholder = _Forward("_items", "remove_empty_placeholder")
    _item_has_shortcut = _Forward("_items", "item_has_shortcut")
    _apply_shortcut_item_filter = _Forward("_items", "apply_shortcut_item_filter")
    _expose_as_attribute = _Forward("_items", "expose_as_attribute")
    _remove_item_event_filter = _Forward("_items", "remove_item_event_filter")
    # _MenuTrigger
    _trigger_button = _Forward("_trigger", "button")
    _event_filters_installed = _Forward("_trigger", "event_filters_installed")
    _filter_target = _Forward("_trigger", "filter_target")
    _parent_signal_source = _Forward("_trigger", "parent_signal_source")
    _pending_trigger_hook = _Forward("_trigger", "pending_trigger_hook")
    _pending_event_filter_install = _Forward("_trigger", "pending_event_filter_install")
    _trigger_hide_timer = _Forward("_trigger", "hide_timer")
    _should_trigger = _Forward("_trigger", "should_trigger")
    _resolve_hide_on_trigger = _Forward("_trigger", "resolve_hide_on_trigger")
    _is_wrapped_item = _Forward("_trigger", "is_wrapped_item")
    _schedule_hide_on_trigger = _Forward("_trigger", "schedule_hide_on_trigger")
    _get_anchor_widget = _Forward("_trigger", "get_anchor_widget")
    _ensure_trigger_hook = _Forward("_trigger", "ensure_trigger_hook")
    _install_event_filters = _ensure_trigger_hook  # its older name
    _uninstall_event_filters = _Forward("_trigger", "uninstall_event_filters")
    # _MenuLeave
    _hide_on_leave = _Forward("_leave", "enabled")
    _leave_timer = _Forward("_leave", "leave_timer")
    _leave_start_timer = _Forward("_leave", "leave_start_timer")
    _mouse_has_entered = _Forward("_leave", "mouse_has_entered")
    _outside_samples = _Forward("_leave", "outside_samples")
    _transient_children = _Forward("_leave", "transient_children")
    _ensure_timer_created = _Forward("_leave", "ensure_timer_created")
    _widget_in_subtree = _Forward("_leave", "widget_in_subtree")  # family protocol
    _iter_transient_family = _Forward("_leave", "iter_transient_family")  # ditto
    _living_transients = _Forward("_leave", "living_transients")
    _pointer_in_family = _Forward("_leave", "pointer_in_family")
    _hide_transient_children = _Forward("_leave", "hide_transient_children")
    _text_edit_in_progress = _Forward("_leave", "text_edit_in_progress")
    _demote_editor_autofocus = _Forward("_leave", "demote_editor_autofocus")
    # _MenuPopupWindow
    _popup_configured = _Forward("_popup", "popup_configured")
    _popup_window_type = _Forward("_popup", "popup_window_type")
    _grab_stolen_from = _Forward("_popup", "grab_stolen_from")
    _dismiss_on_move_filter = _Forward("_popup", "dismiss_on_move_filter")
    _install_dismiss_on_move_filter = _Forward(
        "_popup", "install_dismiss_on_move_filter"
    )
    _detach_dismiss_on_move_filter = _Forward("_popup", "detach_dismiss_on_move_filter")
    _resolve_popup_window_type = _Forward("_popup", "resolve_popup_window_type")
    _ensure_popup_input_grab = _Forward("_popup", "ensure_popup_input_grab")
    _release_popup_input_grab = _Forward("_popup", "release_popup_input_grab")
    _setup_as_popup = _Forward("_popup", "setup_as_popup")
    _ensure_on_screen = _Forward("_popup", "ensure_on_screen")
    # _MenuActions
    _button_manager = _Forward("_actions", "button_manager")
    _add_defaults_button = _Forward("_actions", "add_defaults_button")
    _add_presets = _Forward("_actions", "add_presets")
    _defaults_gesture = _Forward("_actions", "defaults_gesture")
    _defaults_scope = _Forward("_actions", "defaults_scope")
    _update_apply_button_visibility = _Forward(
        "_actions", "update_apply_button_visibility"
    )
    _update_defaults_button_visibility = _Forward(
        "_actions", "update_defaults_button_visibility"
    )
    _setup_presets = _Forward("_actions", "setup_presets")
    # _MenuPersistentMode
    _persistent_mode = _Forward("_persistent", "active")
    _persistent_state = _Forward("_persistent", "state")
    _persistent_hide_button = _Forward("_persistent", "hide_button")
    # _MenuRegistration
    _pending_registrations = _Forward("_registration", "pending")
    _registration_drain_scheduled = _Forward("_registration", "drain_scheduled")
    _registration_window_ref = _Forward("_registration", "window_ref")
    _resolve_registration_window = _Forward("_registration", "resolve_window")
    _register_with_main_window = _Forward("_registration", "register_with_main_window")
    _schedule_registration = _Forward("_registration", "schedule")

    # Called on the class (``Menu._flush_pending_registrations(window)``,
    # ``Menu._resolve_widget_class(name)``), so real static methods.
    _flush_pending_registrations = staticmethod(_MenuRegistration.flush_pending)
    _resolve_widget_class = staticmethod(_MenuItems.resolve_widget_class)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

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
            hide_on_trigger=config.hide_on_trigger,
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
                self._items.start_empty_state()
            self._prepare_for_show()
        else:
            self._items.end_empty_state()
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

        # Before the height pass — it has to measure what will actually show.
        self._apply_shortcut_item_filter()

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

        # Captured BEFORE the popup setup: the popup (if any) whose grab this
        # menu is about to overlay — the native-grab handoff after show (step
        # 7) needs to know who to steal from / hand back to.
        prev_popup = QtWidgets.QApplication.activePopupWidget()

        # Order matters: every step that affects size must run before
        # positioning, and positioning must run before the on-screen
        # check, all while the menu is still hidden.  By the time
        # super().show() runs inside self.show(), the menu is already
        # at its final size and final position — Qt never paints a
        # pre-final state, so the user sees no flicker.
        #
        # 1. Configure as popup (Qt.Tool or Qt.Popup | FramelessWindowHint).
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

        # 7. Native-grab handoff when overlaying another popup's grab
        #    (Qt 6.8+ no longer remaps events off the older popup).
        self._ensure_popup_input_grab(prev_popup)

        self._current_anchor_widget = None

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

        # Has the cursor already entered? A menu that pops up under the
        # cursor must not hide on leave before the cursor moves.
        self._leave.note_shown()

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

        # Start the leave poll, if enabled, after a grace period: a menu that
        # appears at the cursor must not hide before the cursor enters it.
        self._leave.arm_on_show()

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
        self._leave.stop()

        # Detach the dismiss-on-move filter (if any) so we don't accumulate
        # watchers across re-shows and don't keep stale references to
        # ancestors that may be torn down independently.
        self._detach_dismiss_on_move_filter()

        # Cascade to adopted transient children: a child popup opened from
        # within this menu is parented to the wrapped widget (a sibling), so
        # hiding this menu does NOT reach it through the QObject tree. Hide the
        # family explicitly here so closing the menu can't leave orphan popups.
        self._hide_transient_children()

        # Hand a stolen native mouse grab back to the popup underneath — AFTER
        # the transient children, so a child that stole OUR grab unwinds first
        # (its restore-to-us skips, we are hidden) and the popup at the bottom
        # of the chain is re-granted exactly once, by this outermost release.
        self._release_popup_input_grab()

        # CRITICAL FIX: Restore focus to prevent application focus loss
        # Qt.Tool windows can cause focus loss when hidden
        focus_target = None

        # Prefer the window that was active before menu showed — but only while it is still
        # VISIBLE. Activating a hidden window (e.g. a marking-menu overlay whose gesture ended
        # while this popup was open) can't give the user's DCC focus back; on a non-Qt host it
        # strands the OS foreground on an invisible window, deadening every native shortcut
        # until the user clicks the host window.
        if self._active_window_before_show:
            app = QtWidgets.QApplication.instance()
            if (
                app
                and self._active_window_before_show in app.topLevelWidgets()
                and self._active_window_before_show.isVisible()
            ):
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

    # ------------------------------------------------------------------
    # Frame: layouts, central widget, chrome and size (_MenuFrame)
    # ------------------------------------------------------------------

    def setCentralWidget(self, widget, overwrite=False):
        self._scaffold.set_central_widget(widget, overwrite)

    def centralWidget(self):
        """Return the central widget."""
        return self._scaffold.central_widget

    def init_layout(self):
        """Initialize the menu layout. Called lazily on first item add."""
        self._scaffold.init_layout()

    def ensure_chrome(self) -> None:
        """Force-build the deferred Header/Footer now.

        For callers that read ``.header`` / ``.footer`` BEFORE the menu is shown
        (e.g. modal dialogs that configure the header up front). Normal menus do
        not need this — chrome builds automatically on first show.
        """
        self._ensure_chrome()

    def title(self) -> str:
        """Get the menu's title text (the pending value if the header isn't built yet)."""
        return self._scaffold.title()

    def setTitle(self, title="") -> None:
        """Set the menu's title to the given string.

        If the header hasn't been built yet (chrome is deferred to first show),
        the title is stashed and applied when the header is created.

        Parameters:
            title (str): Text to apply to the menu's title.
        """
        self._scaffold.set_title(title)

    def sizeHint(self):
        """Return the recommended size for the widget.

        This method calculates the total size of the widgets contained in the layout of the ExpandableList, including margins and spacing.

        Returns:
            QtCore.QSize: The recommended size for the widget.
        """
        if self._scaffold.layout is None:
            return super().sizeHint()
        return self._scaffold.size_hint()

    # ------------------------------------------------------------------
    # Items (_MenuItems)
    # ------------------------------------------------------------------

    @property
    def contains_items(self) -> bool:
        """Check if the QMenu contains any genuine items.

        The transient empty-state placeholder (see :meth:`_add_empty_placeholder`)
        is intentionally excluded — callers asking "does this menu have
        anything to offer?" should get False while only the placeholder
        is on screen.
        """
        return self._items.contains_items()

    def _shortcut_filter_candidates(self) -> list:
        """Items the shortcut filter may hide (overridden where the body is
        not the grid — see :class:`~uitk.widgets.context_menu.ContextMenu`)."""
        return self.get_items()

    def _shortcut_filter_emptied(self) -> None:
        """Every filterable item is hidden — show the empty-state placeholder
        instead of a bare popup."""
        self._add_empty_placeholder()

    def _on_empty_timeout(self) -> None:
        """Hide the menu when the empty-state timer fires (unless items arrived)."""
        self._items.on_empty_timeout()

    def get_items(self, types=None):
        """Get all items in the list, optionally filtered by type.

        Parameters:
            types (str, type, list of str, list of type, optional): The type(s) or type name(s) of widgets to retrieve. Defaults to None.

        Returns:
            list: A list of all QWidget items in the list, filtered by type if specified.
        """
        return self._items.get_items(types)

    def get_item(self, identifier):
        """Return a QAction or QWidgetAction by index or text.

        Parameters:
            identifier (int or str): If an int, treats it as an index. If a str, treats it as the text of the item.

        Raises:
            ValueError: If the identifier is not an integer (index) or string (text).

        Returns:
            QAction or QWidgetAction: The item found by the identifier.
        """
        return self._items.get_item(identifier)

    def get_item_text(self, widget: QtWidgets.QWidget) -> Optional[str]:
        """Get the textual representation of a widget.

        This method attempts to retrieve text from various widget types by trying
        common text-retrieval methods in order of likelihood.

        Parameters:
            widget: The widget to get text from.

        Returns:
            str: The text associated with the widget, or None if unavailable.
        """
        return _MenuItems.get_item_text(widget)

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
        self._items.remove_widget(widget)

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
        self._items.clear()

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
        return self._items.add(
            x, data=data, row=row, col=col, rowSpan=rowSpan, colSpan=colSpan, **kwargs
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
        return self._items.add_row(
            items,
            title=title,
            spacing=spacing,
            stretch=stretch,
            justify=justify,
            **shared_kwargs,
        )

    # ------------------------------------------------------------------
    # Trigger hook and hide on trigger (_MenuTrigger)
    # ------------------------------------------------------------------

    @property
    def trigger_button(self) -> Union[QtCore.Qt.MouseButton, tuple, None, bool]:
        """Get the current trigger button(s).

        Returns:
            QtCore.Qt.MouseButton: Single button constant
            tuple: Multiple button constants
            None: Any button triggers
            False: No auto-trigger (manual show only)
        """
        return self._trigger.button

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
        self._trigger.set_button(value)

    def set_hide_on_trigger(
        self, widget: QtWidgets.QWidget, hide: Optional[bool]
    ) -> None:
        """Include/exclude one item from the menu-level :attr:`hide_on_trigger`.

        Parameters:
            widget: A menu item (as returned by :meth:`add`).
            hide: ``True`` — this item always hides the menu when triggered;
                ``False`` — this item never hides it; ``None`` — clear the
                override and follow the menu-level setting again.
        """
        widget.setProperty("hide_on_trigger", hide)

    def _handle_nested_trigger(self, container, item) -> None:
        """Hide-on-trigger for an interaction nested inside a container item
        (connected at ``add()`` time; see ``_MenuTrigger.handle_nested_trigger``)."""
        self._trigger.handle_nested_trigger(container, item)

    def _on_parent_triggered(self, checked: bool = False) -> None:  # type: ignore[override]
        """Handle parent widget signal (clicked or pressed)."""
        self._trigger.on_parent_triggered()

    def eventFilter(self, widget, event):
        """Handle events for the menu and its children.

        This filter handles:
        - Parent widget clicks to toggle menu visibility
        - Parent hide events to auto-hide menu
        - Item interactions to emit signals
        """
        self._trigger.filter(widget, event)
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
        self._trigger.trigger_from_widget(widget, button)

    # ------------------------------------------------------------------
    # Hide on leave and the transient popup family (_MenuLeave)
    # ------------------------------------------------------------------

    @property
    def hide_on_leave(self) -> bool:
        """Get whether menu auto-hides when mouse leaves.

        Returns:
            bool: True if menu auto-hides on leave, False otherwise
        """
        return self._leave.enabled

    @hide_on_leave.setter
    def hide_on_leave(self, value: bool) -> None:
        """Set whether menu auto-hides when mouse leaves.

        Parameters:
            value: True to enable auto-hide on leave, False to disable
        """
        self._leave.set_enabled(value)

    def _check_cursor_position(self):
        """The leave poll's tick (see ``_MenuLeave.check_cursor_position``)."""
        self._leave.check_cursor_position()

    def _arm_leave_timer(self):
        """Start the leave-poll timer after showEvent's initial grace period."""
        self._leave.arm_leave_timer()

    def _prune_transients(self) -> None:
        """Drop dead/deleted children from the registry."""
        self._leave.prune_transients()

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
        self._leave.adopt_transient(child)

    # ------------------------------------------------------------------
    # The Menu Actions section (_MenuActions)
    # ------------------------------------------------------------------

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
        return self._actions.presets()

    @presets.setter
    def presets(self, _):
        """No-op setter so the switchboard can harmlessly reassign."""
        pass

    # Real methods (not forwards): tests and tools patch them on the class.
    def _setup_apply_button(self):
        """Create the Apply button that re-emits the anchor's ``clicked``."""
        self._actions.setup_apply_button()

    def _setup_defaults_button(self):
        """Create the Restore Defaults button."""
        self._actions.setup_defaults_button()

    def _restore_menu_defaults(
        self, from_sync: bool = False, action: str = ResetGesture.RESET
    ):
        """Apply a defaults *action* to this menu's fields.

        The name is the mirroring protocol: :meth:`_sync_restore_defaults`
        finds the other instances of a menu by it (see
        ``_MenuActions.restore_menu_defaults``).
        """
        self._actions.restore_menu_defaults(from_sync=from_sync, action=action)

    def _sync_restore_defaults(self, action: str = ResetGesture.RESET):
        """Mirror a defaults *action* onto other instances of this menu."""
        self._actions.sync_restore_defaults(action)

    @property
    def add_defaults_button(self) -> bool:
        """Whether the 'Restore Defaults' button is enabled.

        Setting to ``False`` at runtime removes the button and hides
        the action-button container if no other buttons remain.
        """
        return self._actions.add_defaults_button

    @add_defaults_button.setter
    def add_defaults_button(self, value: bool) -> None:
        self._actions.set_add_defaults_button(value)

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
        return self._actions.add_presets

    @add_presets.setter
    def add_presets(self, value: bool) -> None:
        self._actions.set_add_presets(value)

    # ------------------------------------------------------------------
    # Persistent mode (_MenuPersistentMode)
    # ------------------------------------------------------------------

    def enable_persistent_mode(self, hide_button_tooltip: str = "Hide menu") -> None:
        """Keep the menu visible until the user explicitly hides it.

        This temporarily disables all automatic hide behaviour and injects a
        dedicated Hide button into the header. Call :meth:`disable_persistent_mode`
        to restore the original behaviour.

        Args:
            hide_button_tooltip: Tooltip shown on the injected Hide button.
        """
        self._persistent.enable(hide_button_tooltip)

    def disable_persistent_mode(self) -> None:
        """Restore default hide behaviour after persistent mode."""
        self._persistent.disable()

    @property
    def is_persistent_mode(self) -> bool:
        """Return True when persistent mode is active."""
        return self._persistent.active

    def _on_persistent_hide_clicked(self) -> None:
        """Handle clicks on the injected Hide button."""
        self._persistent.on_hide_clicked()

    # ------------------------------------------------------------------
    # Registration with the owning window (_MenuRegistration)
    # ------------------------------------------------------------------

    def owner_window(self) -> Optional[QtWidgets.QWidget]:
        """Public alias for the owning ``MainWindow``, or ``None``.

        Thin wrapper over :meth:`_resolve_registration_window` so collaborators
        (e.g. a window-scoped :class:`PresetManager`) can reach the host window
        through the same reparent-race-robust resolver used for dynamic-widget
        registration, without depending on a private method.
        """
        return self._resolve_registration_window()

    def _drain_pending_registrations(self) -> None:
        """Process every queued registration in insertion order (the
        coalesced drain's slot; see ``_MenuRegistration.drain``)."""
        self._registration.drain()


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
