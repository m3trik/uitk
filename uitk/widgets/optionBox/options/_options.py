# !/usr/bin/python
# coding=utf-8
from abc import ABC, abstractmethod, ABCMeta
from qtpy import QtWidgets, QtCore
import pythontk as ptk
from uitk.widgets.mixins.attributes import AttributesMixin


# Default tint for the "inactive/disabled" icon state, shared by every gating
# option (ToggleOption, DisableOption, and conceptually ResetOption's bypass).
_DEFAULT_DISABLED_COLOR: str = ptk.Palette.status()["error"][0]  # soft coral


class OptionButton(QtWidgets.QPushButton, AttributesMixin):
    """Icon-only push button used for every option-box action button.

    Defined once at module scope rather than re-declared inside
    ``ButtonOption.create_widget`` on every call — the class object (and its
    metaclass run) was previously rebuilt per option button.
    """


# Resolve metaclass conflict between QObject and ABC
class QObjectABCMeta(type(QtCore.QObject), ABCMeta):
    pass


class BaseOption(QtCore.QObject, ABC, metaclass=QObjectABCMeta):
    """Base class for all option plugins.

    All option plugins should inherit from this class and implement
    the required abstract methods. Options are modular, drop-in components
    that can be added to an OptionBox to extend its functionality.

    Attributes:
        wrapped_widget: The widget that this option is attached to
        widget: The UI widget that will be displayed in the OptionBox container
    """

    def __init__(self, wrapped_widget=None, order=None):
        """Initialize the option.

        Args:
            wrapped_widget: The widget this option will interact with (optional)
            order: Explicit sort position (int). When set, overrides the
                default type-based ordering used by OptionBox._sort_options.
                Lower values appear first. Options without an explicit order
                fall back to type-based grouping.
        """
        QtCore.QObject.__init__(self)
        self.wrapped_widget = wrapped_widget
        self.order = order
        self._widget = None

    @classmethod
    def is_compatible(cls, widget) -> bool:
        """Whether this option type may attach to *widget*.

        Default: compatible with any widget. Override to restrict an option to
        compatible hosts — e.g. a text-field-only option that needs ``text`` /
        ``setText`` / ``textChanged``. :meth:`OptionBoxManager.add_option`
        consults this and **skips incompatible pairings with a warning**, so a
        plugin can be offered narrowly without every caller hand-checking widget
        types. This is the "plugins only seen by compatible widgets" hook.
        """
        return True

    @property
    def widget(self):
        """Get the widget for this option.

        Lazily creates the widget on first access.

        Returns:
            QtWidgets.QWidget: The widget instance
        """
        if self._widget is None:
            self._widget = self.create_widget()
            self.setup_widget()
        return self._widget

    @abstractmethod
    def create_widget(self):
        """Create and return the widget for this option.

        This method must be implemented by subclasses to create
        the actual UI widget that will be displayed.

        Returns:
            QtWidgets.QWidget: The created widget
        """
        pass

    def setup_widget(self):
        """Setup the widget after creation.

        Override this method to perform any additional setup
        after the widget has been created, such as connecting
        signals, setting properties, etc.
        """
        pass

    def on_wrap(self, option_box, container):
        """Called when the option is added to a wrapped widget.

        Override this method to perform any actions needed when
        the option is added to an OptionBox container.

        Args:
            option_box: The OptionBox instance
            container: The container widget
        """
        pass

    def set_wrapped_widget(self, widget):
        """Set or update the wrapped widget.

        Args:
            widget: The widget to wrap
        """
        self.wrapped_widget = widget


class ButtonOption(BaseOption):
    """Base class for button-based options.

    Provides common functionality for options that are displayed as buttons.
    """

    def __init__(
        self,
        wrapped_widget=None,
        icon=None,
        tooltip=None,
        callback=None,
        checkable=False,
        order=None,
    ):
        """Initialize the button option.

        Args:
            wrapped_widget: The widget this option will interact with
            icon: Icon name or path for the button
            tooltip: Tooltip text for the button
            callback: Function to call when button is clicked
            checkable: If True, button toggles checked state (for popup menus)
            order: Explicit sort position (int). See BaseOption.
        """
        super().__init__(wrapped_widget, order=order)
        self.icon = icon
        self.tooltip = tooltip
        self.callback = callback
        self._checkable = checkable
        self._ignore_next_click = False
        self._click_block_timer = None

    def _adopt_popup_into_enclosing_menu(self, popup) -> None:
        """Adopt a popup this option just opened into its host ``Menu``, if any.

        When this option's button (``self._widget``) lives inside a ``Menu`` —
        the option-box popup, or a nested option box — the host menu's
        ``hide_on_leave`` must keep it open while the user interacts with the
        popup. The popup is parented to the wrapped widget (a sibling of the
        host), so it would otherwise fall outside the host's hover family.
        No-op when the button is not inside a ``Menu`` (the popup then stands
        alone with its own hide behavior). See ``Menu.adopt_transient`` /
        ``Menu.nearest_enclosing``.
        """
        from uitk.widgets.menu import Menu

        host = Menu.nearest_enclosing(self._widget)
        if host is not None and host is not popup:
            host.adopt_transient(popup)

    def create_widget(self):
        """Create a QPushButton widget."""
        from uitk.managers.icon_manager import IconManager

        # OptionButton (QPushButton + AttributesMixin) is defined at module
        # scope. NOTE: RichText mixin intentionally omitted — option buttons
        # only display icons.
        button = OptionButton()

        # Disable default/focus visuals that can introduce stray frame lines
        button.setAutoDefault(False)
        button.setDefault(False)
        button.setFocusPolicy(QtCore.Qt.NoFocus)

        # CRITICAL: Clear any default text to prevent artifacts
        # Using native Qt setText (not RichText's setRichText)
        button.setText("")

        # Double-check text is actually empty
        if button.text():
            print(
                f"WARNING: OptionButton still has text after clearing: '{button.text()}' (len={len(button.text())})"
            )
            # Force clear using QPushButton's setText directly
            QtWidgets.QPushButton.setText(button, "")

        if self._checkable:
            button.setCheckable(True)

        if self.icon:
            IconManager.set_icon(button, self.icon, size=(15, 15))

        if self.tooltip:
            button.setToolTip(self.tooltip)

        return button

    def setup_widget(self):
        """Setup button connections."""
        if self.callback:
            self._widget.clicked.connect(self._handle_click)

    def _handle_click(self):
        """Handle click with debounce for checkable buttons."""
        if self._ignore_next_click:
            self._ignore_next_click = False
            # Restore the checked state since we're ignoring this click
            if self._checkable and self._widget:
                self._widget.setChecked(not self._widget.isChecked())
            return

        if self.callback:
            self.callback()

    def block_next_click(self):
        """Block the next click event (used when popup closes to prevent immediate reopen)."""
        self._ignore_next_click = True
        # Clear the flag after a short delay in case no click comes
        if self._click_block_timer is not None:
            self._click_block_timer.stop()
        self._click_block_timer = QtCore.QTimer()
        self._click_block_timer.setSingleShot(True)
        self._click_block_timer.timeout.connect(self._clear_click_block)
        self._click_block_timer.start(200)  # 200ms window

    def _clear_click_block(self):
        """Clear the click block flag."""
        self._ignore_next_click = False

    def set_checked(self, checked):
        """Set the checked state of the button."""
        if self._widget and self._checkable:
            self._widget.setChecked(checked)

    # ------------------------------------------------------------------
    # Widget value helpers (shared by PinValuesOption, RecentValuesOption)
    # ------------------------------------------------------------------

    def _get_widget_value(self):
        """Read the current value from the wrapped widget."""
        widget = self.wrapped_widget
        if not widget:
            return None
        if hasattr(widget, "text"):
            return widget.text()
        if hasattr(widget, "value"):
            return widget.value()
        if hasattr(widget, "currentText"):
            return widget.currentText()
        if hasattr(widget, "toPlainText"):
            return widget.toPlainText()
        if hasattr(widget, "isChecked"):
            return widget.isChecked()
        return None

    def _find_parent_window(self):
        """Walk up the widget tree and return the first QMainWindow, QDialog, or top-level widget."""
        widget = self.wrapped_widget or self._widget
        while widget is not None:
            if widget.isWindow():
                return widget
            widget = widget.parentWidget()
        return None

    def _set_widget_value(self, value):
        """Write *value* to the wrapped widget."""
        widget = self.wrapped_widget
        if not widget or value is None:
            return
        try:
            if hasattr(widget, "setText"):
                widget.setText(str(value))
            elif hasattr(widget, "setValue"):
                widget.setValue(value)
            elif hasattr(widget, "setCurrentText"):
                widget.setCurrentText(str(value))
            elif hasattr(widget, "setPlainText"):
                widget.setPlainText(str(value))
            elif hasattr(widget, "setChecked"):
                widget.setChecked(bool(value))
        except Exception as e:
            print(f"{type(self).__name__}: Error setting value: {e}")


class GatingMixin:
    """Reusable *gating button* capability for option plugins.

    A gating button is one that controls the enabled state of other widgets:

    * it stays clickable while the widgets it gates are disabled (so the user
      can always toggle them back),
    * it enables/disables a set of widgets in sync with its state,
    * it swaps its own icon to a "disabled" tint while inactive,
    * it reports state changes via a ``toggled(bool)`` signal.

    These are exactly the behaviours :class:`ToggleOption` and
    :class:`DisableOption` need, and that :class:`ResetOption`'s bypass mode
    re-implements by hand. Centralising them here keeps the "disable the parent
    widget but keep my button live" pattern correct and DRY everywhere.

    Consumers must:
        * be an option carrying ``self._widget`` (the button) and
          ``self.wrapped_widget``,
        * declare ``toggled = QtCore.Signal(bool)`` on themselves (Qt requires
          the signal on the concrete QObject subclass),
        * call :meth:`_init_gating` from ``__init__`` and
          :meth:`_install_keep_enabled` from ``setup_widget``.

    The mixin is intentionally *not* a QObject — it only adds helper methods, so
    it composes cleanly ahead of the QObject-derived option bases in the MRO.
    """

    def _init_gating(
        self,
        *,
        gated_widgets=(),
        gate_wrapped: bool = False,
        disabled_color: str = None,
        active_color: str = None,
        keep_enabled_when_wrapped_disabled: bool = True,
    ) -> None:
        self._gated_widgets = list(gated_widgets)
        self._gate_wrapped = bool(gate_wrapped)
        # Both state colours are centralized here (disabled defaults to the
        # project error red) yet fully overridable per option; ``active_color``
        # ``None`` keeps the auto theme colour.
        self._disabled_color = disabled_color or _DEFAULT_DISABLED_COLOR
        self._active_color = active_color
        self._keep_enabled_when_wrapped_disabled = bool(
            keep_enabled_when_wrapped_disabled
        )

    def _install_keep_enabled(self) -> None:
        """Flag the button so the container's enabled-sync leaves it clickable.

        :meth:`OptionBoxContainer._sync_option_buttons_enabled` cascade-disables
        every option button when the wrapped widget is disabled — except those
        carrying the ``keepEnabledWhenWrappedDisabled`` property. Without this, a
        gating button that disables its own wrapped widget would disable *itself*
        and become impossible to re-enable.
        """
        if self._keep_enabled_when_wrapped_disabled and self._widget is not None:
            self._widget.setProperty("keepEnabledWhenWrappedDisabled", True)

    def _effective_gated(self):
        """Widgets this button enables/disables — the explicit set, plus the
        wrapped widget when ``gate_wrapped`` is set (deduped, ``None`` dropped)."""
        widgets = list(self._gated_widgets)
        if self._gate_wrapped and self.wrapped_widget is not None:
            widgets.append(self.wrapped_widget)
        seen, ordered = set(), []
        for w in widgets:
            if w is not None and id(w) not in seen:
                seen.add(id(w))
                ordered.append(w)
        return ordered

    def _apply_gating(self, active: bool) -> None:
        """Enable (``active`` True) or disable every effective gated widget."""
        for w in self._effective_gated():
            try:
                w.setEnabled(bool(active))
            except RuntimeError:
                # Underlying C++ widget already deleted; skip.
                pass

    def _apply_icon_state(
        self,
        active: bool,
        icon_active: str,
        icon_inactive: str = None,
        *,
        tooltip_active: str = None,
        tooltip_inactive: str = None,
        fallback_size=(15, 15),
    ) -> None:
        """Swap the button icon/tooltip between the active and inactive states.

        Active → ``icon_active`` in ``active_color`` (``None`` = auto theme);
        inactive → ``icon_inactive`` (falls back to ``icon_active``) tinted
        ``disabled_color``. Single home of the ``IconManager.swap_icon`` dance
        shared by the gating options.
        """
        if self._widget is None:
            return
        from uitk.managers.icon_manager import IconManager

        if active:
            IconManager.swap_icon(
                self._widget,
                icon_active,
                color=self._active_color,
                auto_theme=self._active_color is None,
                fallback_size=fallback_size,
            )
            if tooltip_active is not None:
                self._widget.setToolTip(tooltip_active)
        else:
            IconManager.swap_icon(
                self._widget,
                icon_inactive or icon_active,
                color=self._disabled_color,
                auto_theme=False,
                fallback_size=fallback_size,
            )
            if tooltip_inactive is not None:
                self._widget.setToolTip(tooltip_inactive)
