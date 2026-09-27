# !/usr/bin/python
# coding=utf-8
"""``Menu``: uitk's popup menu widget -- the facade, its configuration and placement.

``Menu`` is assembled from one mixin per concept in :mod:`uitk.widgets.menu_parts`
(layout and chrome, items, trigger hook, hide on leave, popup window, action
buttons, persistent mode, item registration); this module keeps construction,
the show / hide lifecycle that orchestrates the parts, and placement
(:class:`MenuPositioner`, ``show_as_popup``). Its path is frozen: ``.ui``
headers name ``uitk.widgets.menu``.
"""

import weakref
from dataclasses import dataclass, field
from typing import Optional, Union, Dict, Any, Tuple, TYPE_CHECKING
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk

if TYPE_CHECKING:
    from uitk.widgets.popup.dismissal import AncestorDismissal

# From this package:
from uitk.widgets.header import Header
from uitk.widgets.footer import Footer
from uitk.themes.style_sheet import StyleSheet
from uitk.widgets.mixins.attributes import AttributesMixin

# The concept parts (base classes: needed at class definition). The underscore
# names re-exported here were module attributes of this file before the split.
from uitk.widgets.menu_parts._actions import (  # noqa: F401
    ActionButtonManager,
    _ActionButtonConfig,
    _MenuActionsMixin,
)
from uitk.widgets.menu_parts._items import (  # noqa: F401
    _HEIGHT_CONSTRAINED_TYPES,
    _LAZY_WIDGET_TYPES,
    _WIDGET_TYPE_CACHE,
    _MenuItemsMixin,
)
from uitk.widgets.menu_parts._layout import _MenuLayoutMixin
from uitk.widgets.menu_parts._leave import _LEAVE_DEBUG, _MenuLeaveMixin  # noqa: F401
from uitk.widgets.menu_parts._persistent_mode import _MenuPersistentModeMixin
from uitk.widgets.menu_parts._popup_window import _MenuPopupWindowMixin
from uitk.widgets.menu_parts._registration import _MenuRegistrationMixin
from uitk.widgets.menu_parts._triggers import _MenuTriggersMixin

# Every Menu with a pending deferred-registration queue (see
# ``_MenuRegistrationMixin``); the same set object, under its old name.
_menus_awaiting_registration = _MenuRegistrationMixin._awaiting_registration


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


class Menu(
    # The concept parts come BEFORE QWidget: several override QWidget virtuals
    # (eventFilter) or are reached from its overrides here, and a base listed
    # after QWidget would lose any shared name to it. Their names are disjoint,
    # so their own order is immaterial.
    _MenuLayoutMixin,
    _MenuItemsMixin,
    _MenuTriggersMixin,
    _MenuLeaveMixin,
    _MenuPopupWindowMixin,
    _MenuActionsMixin,
    _MenuPersistentModeMixin,
    _MenuRegistrationMixin,
    QtWidgets.QWidget,
    AttributesMixin,
    ptk.LoggingMixin,
):
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

        if name is not None:
            if not isinstance(name, str):
                raise TypeError(f"Expected 'name' to be a string, got {type(name)}")
            self.setObjectName(name)

        self.logger.setLevel(log_level)

        # Items this menu hid because their action already has a shortcut —
        # tracked so only those are restored when the preference goes off.
        self._shortcut_hidden_items = []

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
        self._leave_start_timer: Optional[QtCore.QTimer] = None
        self._last_parent_geometry = None
        self._cached_menu_position = None
        self._popup_configured = False  # Track if popup setup has been done
        # Window type the last ``_setup_as_popup`` pass applied (Qt.Tool or
        # Qt.Popup). Re-checked on every show: a menu opened while another
        # popup holds the app-wide grab must itself be a Qt.Popup to get
        # any input at all. See ``_resolve_popup_window_type``.
        self._popup_window_type: Optional[QtCore.Qt.WindowType] = None
        self._tracked_as_menu = False  # Registered with owning MainWindow.menus()
        self._dismiss_on_move_filter: Optional[AncestorDismissal] = None
        self._activating_chain = False  # Re-entrancy guard for sizeHint activation
        # The popup whose native mouse grab this menu stole on show (weakref),
        # to hand back on hide. See _ensure_popup_input_grab.
        self._grab_stolen_from: Optional["weakref.ref"] = None

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
        self.hide_on_trigger = hide_on_trigger
        # Deferred hide used by hide_on_trigger (parented so it dies with the
        # menu instead of firing into a deleted widget).
        self._trigger_hide_timer: Optional[QtCore.QTimer] = None
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
            # Delay timer start by 200ms to give user time to move cursor into menu.
            # Note: _mouse_has_entered was already set above based on cursor position.
            # A QTimer parented to self (not a bare singleShot free function) so the
            # deferred call is destroyed along with the menu instead of firing into
            # an already-deleted _leave_timer (singleShot has no owner to cancel it).
            if self._leave_start_timer is None:
                self._leave_start_timer = QtCore.QTimer(self)
                self._leave_start_timer.setSingleShot(True)
                self._leave_start_timer.timeout.connect(self._arm_leave_timer)
            self._leave_start_timer.start(200)

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
