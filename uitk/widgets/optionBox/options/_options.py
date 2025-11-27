# !/usr/bin/python
# coding=utf-8
from abc import ABC, abstractmethod, ABCMeta
from qtpy import QtWidgets, QtCore


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

    def __init__(self, wrapped_widget=None):
        """Initialize the option.

        Args:
            wrapped_widget: The widget this option will interact with (optional)
        """
        QtCore.QObject.__init__(self)
        self.wrapped_widget = wrapped_widget
        self._widget = None

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
    ):
        """Initialize the button option.

        Args:
            wrapped_widget: The widget this option will interact with
            icon: Icon name or path for the button
            tooltip: Tooltip text for the button
            callback: Function to call when button is clicked
            checkable: If True, button toggles checked state (for popup menus)
        """
        super().__init__(wrapped_widget)
        self.icon = icon
        self.tooltip = tooltip
        self.callback = callback
        self._checkable = checkable
        self._ignore_next_click = False
        self._click_block_timer = None

    def create_widget(self):
        """Create a QPushButton widget."""
        from uitk.widgets.mixins.icon_manager import IconManager
        from uitk.widgets.mixins.attributes import AttributesMixin

        # Create a custom button class with our mixins
        # NOTE: RichText mixin removed - option buttons only display icons
        from qtpy import QtCore

        class OptionButton(QtWidgets.QPushButton, AttributesMixin):
            pass

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
            IconManager.set_icon(button, self.icon, size=(17, 17))

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
