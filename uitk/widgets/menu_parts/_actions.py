# !/usr/bin/python
# coding=utf-8
"""The "Menu Actions" section: Apply, Restore Defaults and the presets selector.

:class:`ActionButtonManager` owns the collapsible container the section lives
in; the mixin decides, on first show, which of its entries the menu gets -- an
Apply button that re-emits the anchor's ``clicked``, a Restore Defaults button
driven by :class:`~uitk.managers.reset_gesture.ResetGesture` (mirrored onto
other instances of the same menu), and a preset combo wired by the menu's
:class:`~uitk.managers.preset_manager.PresetManager`.

One part of :class:`~uitk.widgets.menu.Menu`, which inherits it; it holds no
state of its own (``Menu.__init__`` declares every attribute used here) and
is never instantiated alone.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, Optional

from qtpy import QtCore, QtWidgets

from uitk.managers.reset_gesture import ResetGesture
from uitk.managers.state_manager import StateManager
from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

if TYPE_CHECKING:
    from uitk.widgets.collapsableGroup import CollapsableGroup


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
        # Parent to the container at construction: a parentless button that
        # gets setVisible(True) below (visible=contains_items) MAPS as its own
        # on-screen top-level window until add_button's addWidget reparents it
        # — a visible stray flash on every FIRST popup open (option-box menus,
        # whose apply/defaults buttons default on).
        button = QtWidgets.QPushButton(config.text, self.container)

        if config.tooltip:
            button.setToolTip(config.tooltip)
        TooltipPresenter.manage(button)
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


class _MenuActionsMixin:
    """The "Menu Actions" section: Apply, Restore Defaults and the presets selector."""

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
            from uitk.managers.preset_manager import PresetManager

            self._preset_manager = PresetManager(parent=self)
        return self._preset_manager

    @presets.setter
    def presets(self, _):
        """No-op setter so the switchboard can harmlessly reassign."""
        pass

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
            visible=self.contains_items,
            fixed_height=18,
        )
        btn = self._button_manager.add_button("defaults", config, index=0)
        # Click resets, Shift+Click makes the current values the defaults,
        # Ctrl+Shift+Click returns to factory. The gesture teaches that in the
        # tooltip and previews it on the button while a modifier is held.
        # ``released`` matches the menu's other action buttons.
        self._defaults_gesture = ResetGesture(
            btn,
            state=lambda: StateManager.for_widget(self),
            widgets=self._defaults_scope,
            signal="released",
            on_performed=self._sync_restore_defaults,
        )

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

    def _restore_menu_defaults(
        self, from_sync: bool = False, action: str = ResetGesture.RESET
    ):
        """Apply a defaults *action* (:class:`ResetGesture`) to this menu's fields.

        Runs through the window ``StateManager`` scoped to
        :meth:`_defaults_scope`, so a menu resets FIELDS like a panel does:
        option locks clear first and ``exclude_from_reset`` is honored. The
        Restore Defaults button reaches the same place through its gesture.
        """
        state = StateManager.for_widget(self)
        if state is None:
            self.logger.debug("_restore_menu_defaults: No state manager found")
            return
        ResetGesture.perform(state, action, self._defaults_scope())
        self.logger.debug(f"_restore_menu_defaults: {action} complete")

        if not from_sync:
            self._sync_restore_defaults(action)

    def _defaults_scope(self) -> list:
        """This menu's fields: each item and its descendants.

        An option-box wrap replaces the item in the grid with its container (see
        :meth:`_is_wrapped_item`), so the fields that carry reset buttons and
        locks are never grid items themselves.
        """
        return [
            widget
            for item in self.get_items()
            for widget in (item, *item.findChildren(QtWidgets.QWidget))
        ]

    def _sync_restore_defaults(self, action: str = ResetGesture.RESET):
        """Mirror a defaults *action* onto other instances of this menu.

        A reset or factory reset is mirrored; a save is not. Saved defaults are
        keyed by field name, which the instances share, so a mirrored save made
        each one save ITS current values over the ones the user just saved.
        """
        if action == ResetGesture.SAVE or not self.objectName():
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
                        parent._restore_menu_defaults(from_sync=True, action=action)
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
