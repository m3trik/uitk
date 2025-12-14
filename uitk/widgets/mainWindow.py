# !/usr/bin/python
# coding=utf-8
import sys
from typing import Any, Optional, Union, List
from qtpy import QtWidgets, QtCore
import pythontk as ptk

# From this package
from uitk import __package__
from uitk.widgets.footer import Footer
from uitk.widgets.mixins.state_manager import StateManager
from uitk.widgets.mixins.settings_manager import SettingsManager
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.style_sheet import StyleSheet


class MainWindow(QtWidgets.QMainWindow, AttributesMixin, ptk.LoggingMixin):
    """Application main window with state persistence and child widget management."""

    on_show = QtCore.Signal()
    on_hide = QtCore.Signal()
    on_close = QtCore.Signal()
    on_focus_in = QtCore.Signal()
    on_focus_out = QtCore.Signal()
    on_child_registered = QtCore.Signal(object)
    on_child_changed = QtCore.Signal(object, object)

    def __init__(
        self,
        name: str,
        switchboard_instance: object,
        central_widget: Optional[QtWidgets.QWidget] = None,
        parent: Optional[QtWidgets.QWidget] = None,
        tags: set = None,
        path: str = None,
        log_level: int = "WARNING",
        restore_window_size: bool = True,
        add_footer: bool = True,
        ensure_on_screen: bool = True,
        default_slot_timeout: Optional[float] = None,
        **kwargs,
    ) -> None:
        """Initializes the main window and its properties.

        Parameters:
            name: The name of the window
            switchboard_instance: The switchboard instance to use
            central_widget: Optional central widget to set
            parent: Optional parent widget
            tags: Optional set of tags
            path: Optional path
            log_level: Logging level to use
            restore_window_size: Whether to save and restore window geometry. Defaults to True.
            add_footer: Whether to add a footer with size grip. Defaults to True.
            ensure_on_screen: Whether to ensure the window is fully on screen when shown. Defaults to True.
            default_slot_timeout: Default timeout in seconds for slots in this window. None disables monitoring.
            **kwargs: Additional keyword arguments
        """
        super().__init__(parent)

        # Default style class ensures translucent border styling even when callers don't specify one
        self._default_style_class = "translucentBgWithBorder"

        self.logger.setLevel(log_level)
        self.logger.set_log_prefix(f"[{name}] ")

        self.sb = switchboard_instance
        self.style = StyleSheet(self, log_level="WARNING")

        self.setObjectName(name)
        self.legal_name = lambda: self.sb.convert_to_legal_name(name)
        self.base_name = lambda: self.sb.get_base_name(name)

        self.settings = SettingsManager(org=__package__, app=name)
        self.state = StateManager(self.settings)

        self.path = path
        self.tags = set(tags or [])
        self.has_tags = lambda tags=None: self.sb.has_tags(self, tags)
        self.is_initialized = False
        self.prevent_hide = False
        self.ensure_on_screen = ensure_on_screen
        self.restore_window_size = (
            restore_window_size  # Enable/disable window size saving
        )
        self.add_footer = add_footer
        self.default_slot_timeout = default_slot_timeout
        self.footer: Optional[Footer] = None
        self.widgets = set()
        self.restore_widget_states = True
        self.restored_widgets = set()
        self._deferred = {}
        self.lock_style = False
        self.original_style = ""

        self.connected_slots = ptk.NamespaceHandler(
            self,
            "connected_slots",
        )  # All connected slots.

        # Install event filter before setting central widget
        self.installEventFilter(self)

        self.set_attributes(WA_NoChildEventsForParent=True, **kwargs)
        self.setFocusPolicy(QtCore.Qt.ClickFocus)

        self.on_close.connect(self.settings.sync)
        self.on_child_changed.connect(self.sync_widget_values)

        # If central widget is provided, set it
        if central_widget:
            self.setCentralWidget(central_widget)

        # Always create size grip, even if no layout exists yet
        self._create_size_grip()

    def _create_size_grip(self) -> None:
        """Create the size grip or footer if configured."""
        if self.add_footer:
            # Use footer with integrated size grip
            # Check if footer already exists on MainWindow or in central widget
            existing_footer = getattr(self, "footer", None)
            if existing_footer:
                return

            central = self.centralWidget()
            if not central:
                return

            # Check for footer defined in .ui file (search by object name only,
            # since class comparison may fail due to Qt's module path differences)
            from qtpy.QtWidgets import QWidget

            footer_child = central.findChild(QWidget, "footer")
            if footer_child:
                self.footer = footer_child
                return

            self.footer = Footer(add_size_grip=True)
            self.footer.attach_to(central)
        else:
            # Legacy size grip without footer
            existing_grip = self.findChild(QtWidgets.QSizeGrip, "size_grip")
            if existing_grip:
                return

            size_grip = QtWidgets.QSizeGrip(self)
            size_grip.setObjectName("size_grip")

            layout = self.centralWidget().layout() if self.centralWidget() else None
            if layout:
                layout.addWidget(size_grip)
                layout.setAlignment(
                    size_grip, QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight
                )

    def setCentralWidget(self, widget: QtWidgets.QWidget) -> None:
        """Overrides QMainWindow's setCentralWidget to handle initialization when the central widget is set or changed."""
        # Set the new central widget
        super().setCentralWidget(widget)

        # Initialize window flags based on the new central widget
        self.initialize_window_flags(widget)

        # Ensure size grip exists and is properly positioned
        self._create_size_grip()

    def initialize_window_flags(self, central_widget: QtWidgets.QWidget) -> None:
        """Initializes the window flags based on the central widget."""
        window = central_widget.window()
        if window is not None and window is not central_widget:
            self.setWindowFlags(window.windowFlags())
        else:
            self.setWindowFlags(central_widget.windowFlags())

    def edit_tags(
        self,
        target: Union[str, QtWidgets.QWidget] = None,
        add: Union[str, List[str]] = None,
        remove: Union[str, List[str]] = None,
        clear: bool = False,
        reset: bool = False,
    ) -> Union[str, None]:
        """Edit tags on a widget or a tag string.
        If target is None, edits tags on this MainWindow.

        Parameters:
            target (str or QWidget): The widget to edit tags on, or a tag string.
            add (str or list[str]): Tags to add.
            remove (str or list[str]): Tags to remove.
            clear (bool): If True, clears all tags.
            reset (bool): If True, resets tags to default (only for widgets).

        Returns:
            str or None: The modified tag string if target is a string, otherwise None.
        """
        if target is None:
            target = self
        return self.sb.edit_tags(
            target, add=add, remove=remove, clear=clear, reset=reset
        )

    def __getattr__(self, attr_name) -> Any:
        """Looks for the widget in the parent class.
        If found, the widget is initialized and returned, else an AttributeError is raised.

        Parameters:
            attr_name (str): the name of the attribute being accessed.

        Returns:
            The value of the widget attribute if it exists, or raises an AttributeError
            if the attribute cannot be found.

        Raises:
            AttributeError: if the attribute does not exist in the current instance
            or the parent class.
        """
        found_widget = self.sb._get_widget_from_ui(self, attr_name)
        if found_widget:
            if found_widget.objectName() and found_widget not in self.widgets:
                self.register_widget(found_widget)
            return found_widget

        raise AttributeError(
            f"{self.__class__.__name__} has no attribute `{attr_name}`"
        )

    @property
    def is_pinned(self) -> bool:
        """Check if the window is pinned (should not auto-hide).

        This is the single source of truth for pin state checking.
        Checks both the prevent_hide flag and the header's pin button state.

        Returns:
            bool: True if window should stay visible (pinned), False otherwise
        """
        # Check prevent_hide flag
        if self.prevent_hide:
            return True

        # Check header pin button state (if header exists and has pin functionality)
        header = getattr(self, "header", None)
        if header and hasattr(header, "pinned"):
            return header.pinned

        return False

    @property
    def slots(self) -> list:
        """Returns a list of the slots connected to the widget's signals.

        Returns:
            list: A list of the slots connected to the widget's signals.
        """
        return self.sb.get_slots_instance(self)

    @property
    def is_stacked_widget(self) -> bool:
        """Checks if the parent of the widget is a QStackedWidget."""
        return isinstance(self.parent(), QtWidgets.QStackedWidget)

    @property
    def is_current_ui(self) -> bool:
        """Returns True if the widget is the currently active UI, False otherwise."""
        return self == self.sb.current_ui

    @is_current_ui.setter
    def is_current_ui(self, value: bool) -> None:
        """Sets the widget as the currently active UI if value is True.

        Raises:
            ValueError if an incompatible value is given.
        """
        if not isinstance(value, bool):
            raise ValueError(
                f"'is_current_ui' must be a boolean value. Got: {value} Type: {type(value)}"
            )
        if value:
            self.sb.current_ui = self

    def register_widget(self, widget: QtWidgets.QWidget, **kwargs: Any) -> None:
        """Registers a widget with the main window, initializing it and connecting its signals."""
        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.warning(f"Expected widget, got {type(widget)}")
            return

        if widget in self.widgets or not widget.objectName():
            if not widget.objectName():
                self.logger.debug(
                    f"[register_widget]: {widget} has no objectName, cannot register"
                )
            return

        widget.ui = self
        widget.base_name = lambda: self.sb.get_base_name(widget.objectName())
        widget.legal_name = lambda: self.sb.convert_to_legal_name(widget.objectName())
        widget.type = type(widget)
        widget.derived_type = ptk.get_derived_type(widget, module="QtWidgets")
        widget.default_signals = lambda: self.sb.default_signals.get(
            widget.derived_type, None
        )

        widget.get_slot = lambda w=widget: getattr(
            self.sb.get_slots_instance(w.ui), w.objectName(), None
        )
        widget.init_slot = lambda *args, w=widget: self.sb.init_slot(w)
        widget.call_slot = lambda *args, w=widget, **kwargs: self.sb.call_slot(
            w, *args, **kwargs
        )
        widget.connect_slot = lambda w=widget, s=None: self.sb.connect_slot(w, s)
        widget.perform_restore_state = (
            lambda w=widget, force=False: self.perform_restore_state(w, force=force)
        )
        widget.register_children = lambda w=widget: self.register_children(w)

        widget.is_initialized = False
        widget.refresh_on_show = False
        if not hasattr(widget, "restore_state"):
            widget.restore_state = True

        ptk.set_attributes(widget, **kwargs)
        setattr(self, widget.objectName(), widget)

        self._add_child_changed_signal(widget)
        self._add_child_destroyed_signal(widget)
        self._add_child_refresh_on_show_signal(widget)

        self.widgets.add(widget)
        self.on_child_registered.emit(widget)
        widget.init_slot()

        # self.logger.debug(f"[register_widget]: {widget.objectName()} ({widget.type})")
        # self.register_children(widget)

    def _add_child_destroyed_signal(self, widget) -> None:
        """Initializes the signal for a given widget that will be emitted when the widget is destroyed.

        This method connects the `destroyed` signal of the widget to a slot that removes the widget from the
        parent object's list of widgets. This ensures that the parent object can keep track of its child widgets
        and clean up any references to them when they are no longer needed.

        Parameters:
            widget (QtWidgets.QWidget): The widget to initialize the signal for.
        """
        widget.destroyed.connect(lambda: self.widgets.discard(widget))

    def _add_child_changed_signal(self, widget) -> None:
        """Initializes the signal for a given widget that will be emitted when the widget's state changes.

        This method iterates over a dictionary of default signals, which maps widget types to signal names.
        If the widget is an instance of a type in the dictionary, the method checks if the widget has a signal
        with the corresponding name. If it does, the method connects the signal to a slot.

        The slot is a lambda function that emits the `on_child_changed` signal of the parent object with the widget
        and the value emitted by the widget's signal as arguments. If the widget's signal does not emit a value,
        the lambda function does nothing.

        The `on_child_changed` signal can then be connected to a method that will be called whenever the widget's state changes.

        Parameters:
            widget (QtWidgets.QWidget): The widget to initialize the signal for.
        """
        signal_name = widget.default_signals()
        if not signal_name:
            return

        signal = getattr(widget, signal_name, None)
        if not signal:
            self.logger.debug(f"No signal '{signal_name}' on {widget}")
            return

        try:
            signal.connect(
                lambda *args, w=widget: self.on_child_changed.emit(
                    w, args[0] if args else None
                )
            )
        except Exception as e:
            self.logger.debug(
                f"Could not connect signal '{signal_name}' on {widget}: {e}"
            )

    def _add_child_refresh_on_show_signal(self, widget) -> None:
        def refresh_if_not_first_show():
            # Only refresh if initialized AND we've already shown at least once
            if getattr(widget, "refresh_on_show", False):
                if getattr(widget, "_is_not_first_show", False):
                    widget.init_slot()
                else:  # Mark as shown for the next time
                    widget._is_not_first_show = True

        self.on_show.connect(refresh_if_not_first_show)

    def trigger_deferred(self) -> None:
        """Executes all deferred methods, in priority order. Any arguments passed to the deferred functions
        will be applied at this point. Once all deferred methods have executed, the dictionary is cleared.
        """
        self.logger.debug(
            f"[trigger_deferred]: Triggering deferred methods: {self._deferred}"
        )
        for priority in sorted(self._deferred):
            for method in self._deferred[priority]:
                method()
        self._deferred.clear()

    def perform_restore_state(self, widget: QtWidgets.QWidget, force=False) -> None:
        """Restores the state of a given widget if it has a restore_state attribute."""
        if not self.restore_widget_states:
            return

        if (
            getattr(widget, "restore_state", False)
            and widget not in self.restored_widgets
        ) or force:
            self.state.load(widget)
            self.restored_widgets.add(widget)

    def sync_widget_values(self, widget: QtWidgets.QWidget, value: Any) -> None:
        """Sync a widget's state value across related UIs and apply the value using StateManager."""
        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.warning(f"[sync_widget_values] Invalid widget: {widget}")
            return

        # Skip syncing None values to prevent clearing valid widget states
        if value is None:
            self.logger.debug(
                f"[{self.objectName()}] [sync_widget_values] Skipping sync of None value for {widget.objectName()}"
            )
            return

        # Save and apply to all relative widgets
        relatives = self.sb.get_ui_relatives(widget.ui, upstream=True, downstream=True)
        for relative in relatives:
            relative_widget = self.sb.get_widget(widget.objectName(), relative)
            if relative_widget and relative_widget is not widget:
                self.logger.debug(
                    f"[{self.objectName()}] [sync_widget_values] Syncing {widget.objectName()} to {relative_widget.objectName()}"
                )

                self.state.save(relative_widget, value)
                self.state.apply(relative_widget, value)

        # Save for the current widget
        self.state.save(widget, value)

    def eventFilter(self, watched, event) -> bool:
        """Override the event filter to register widgets when they are polished."""
        if watched is self and event.type() == QtCore.QEvent.ChildPolished:
            child = event.child()
            if isinstance(child, QtWidgets.QWidget):
                if child.objectName() and child not in self.widgets:
                    self.register_widget(child)
        return super().eventFilter(watched, event)

    def save_window_geometry(self) -> None:
        """Save the current window geometry (size and position) to settings."""
        if not self.restore_window_size:
            return

        geometry = self.saveGeometry()
        # Store QByteArray directly using the clean API
        self.settings.setByteArray("window_geometry", geometry)
        self.logger.debug(
            f"[save_window_geometry]: Saved window geometry for {self.objectName()}"
        )

    def restore_window_geometry(self) -> None:
        """Restore the window geometry (size and position) from settings."""
        if not self.restore_window_size:
            return

        # Get QByteArray directly using the clean API
        geometry = self.settings.getByteArray("window_geometry")

        if geometry and isinstance(geometry, QtCore.QByteArray):
            try:
                if self.restoreGeometry(geometry):
                    self.logger.debug(
                        f"[restore_window_geometry]: Restored window geometry for {self.objectName()}"
                    )
                else:
                    self.logger.debug(
                        f"[restore_window_geometry]: Failed to restore window geometry for {self.objectName()}"
                    )
            except Exception as e:
                self.logger.warning(
                    f"[restore_window_geometry]: Error restoring geometry: {e}"
                )
        else:
            self.logger.debug(
                f"[restore_window_geometry]: No valid geometry data found for {self.objectName()}"
            )

    def clear_saved_geometry(self) -> None:
        """Clear any saved window geometry from settings."""
        self.settings.clear("window_geometry")
        self.logger.debug(
            f"[clear_saved_geometry]: Cleared saved geometry for {self.objectName()}"
        )

    def _ensure_on_screen(self) -> None:
        """Moves the window to be fully visible on the screen if it is partially off-screen."""
        # Get the window's frame geometry (including title bar and borders)
        frame_geo = self.frameGeometry()

        # Find the screen that contains the center of the window
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

    def setVisible(self, visible) -> None:
        """Reimplement setVisible to prevent window from being hidden when pinned."""
        if self.is_pinned and not visible:
            return
        super().setVisible(visible)

    def show(self, pos=None, app_exec=False) -> None:
        """Show the MainWindow.

        Parameters:
            pos (QPoint/str, optional): A point to move to, or 'screen' to center on screen, or 'cursor' to center at cursor position. Defaults to None.
            app_exec (bool, optional): Execute the given qtpy application, display its window, wait for user input,
                    and then terminate the program with a status code returned from the application. Defaults to False.
        Raises:
            SystemExit: Raised if the exit code returned from the qtpy application is not -1.
        """
        super().show()
        self.sb.center_widget(self, pos)

        if self.ensure_on_screen:
            # Use a timer to ensure the window geometry is updated before checking
            QtCore.QTimer.singleShot(0, self._ensure_on_screen)

        if app_exec:
            exit_code = self.sb.app.exec_()
            if exit_code != -1:
                sys.exit(exit_code)

    def showEvent(self, event) -> None:
        """Override the show event to initialize untracked widgets and restore their states."""
        if not self.is_initialized:
            self.logger.debug(f"[showEvent]: Registering children on first show.")
            try:
                self.register_children()
                self.logger.debug(f"[showEvent]: Registering children done.")
            except Exception as e:
                self.logger.debug(f"[showEvent]: Error during register_children: {e}")

        self.trigger_deferred()
        self.activateWindow()

        super().showEvent(event)
        self.on_show.emit()

        self.is_initialized = True

    def eventFilter(self, watched, event) -> bool:
        """Override the event filter to register widgets when they are polished."""
        if event.type() == QtCore.QEvent.ChildPolished:
            child = event.child()
            if isinstance(child, QtWidgets.QWidget):
                if child.objectName() and child not in self.widgets:
                    self.register_widget(child)
        return super().eventFilter(watched, event)

    def register_children(
        self, root_widget: Optional[QtWidgets.QWidget] = None
    ) -> None:
        """Registers all child widgets starting from the given widget (or central widget if None)."""

        def _walk_and_register(widget) -> None:
            if widget.objectName() and widget not in self.widgets:
                self.register_widget(widget)
            for child in widget.findChildren(
                QtWidgets.QWidget, options=QtCore.Qt.FindDirectChildrenOnly
            ):
                _walk_and_register(child)

        root = root_widget or self.centralWidget()
        if root:
            _walk_and_register(root)

    def focusInEvent(self, event) -> None:
        """Override the focus event to set the current UI when this window gains focus."""
        self.sb.current_ui = self
        super().focusInEvent(event)
        self.on_focus_in.emit()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.on_focus_out.emit()

    def hideEvent(self, event) -> None:
        """Reimplement hideEvent to emit custom signal when window is hidden."""
        # Explicitly return focus to the parent window (e.g. Maya).
        # This is necessary in embedded contexts because the OS window manager
        # may otherwise transfer focus to a different application when a
        # top-level tool window is hidden.
        if self.parent():
            parent_window = self.parent().window()
            if parent_window and parent_window.isVisible():
                parent_window.activateWindow()
                parent_window.raise_()

        super().hideEvent(event)
        self.on_hide.emit()

    def closeEvent(self, event) -> None:
        """Reimplement closeEvent to save window geometry and emit custom signal."""
        # Save window geometry before closing
        self.save_window_geometry()

        super().closeEvent(event)
        self.on_close.emit()

    def setStyleSheet(self, style: str) -> None:
        """Overrides the setStyleSheet method to respect locking.

        Parameters:
            style (str): The stylesheet to apply to the window
        """
        if self.lock_style:
            self.logger.debug(
                "Stylesheet is locked: Unlock first using: <window>.lock_style = False."
            )
        else:
            self.original_style = self.styleSheet()
            super().setStyleSheet(style)

    def reset_style(self) -> None:
        """Resets the window's stylesheet to its original state."""
        if not self.lock_style:
            self.setStyleSheet(self.original_style)
        else:
            self.logger.debug(
                "Cannot reset stylesheet while locked. Unlock first using: <window>.lock_style = False."
            )


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    from uitk import Switchboard

    class MyProject: ...

    class MySlots(MyProject):
        def __init__(self, **kwargs):
            self.sb = kwargs.get("switchboard")
            self.ui = self.sb.loaded_ui.example

        def MyButtonsObjectName(self):
            print("Button clicked!")

    # Use the package to define the ui_source and slot_source.
    sb = Switchboard(
        ui_source="../example",
        slot_source=MySlots,
    )
    sb.example.show(app_exec=True)


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
