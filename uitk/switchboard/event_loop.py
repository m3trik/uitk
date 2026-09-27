# !/usr/bin/python
# coding=utf-8
import traceback
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk


class SwitchboardEventLoopMixin:
    """Event-loop helpers: deferred calls, synthetic key presses, modifier-aware
    value inversion and keeping Qt objects alive."""

    @staticmethod
    def invert_on_modifier(value):
        """Invert a numerical or boolean value if the alt key is pressed.

        Parameters:
            value (int, float, bool) = The value to invert.

        Returns:
            (int, float, bool)
        """
        modifiers = QtWidgets.QApplication.instance().keyboardModifiers()
        if modifiers not in (
            QtCore.Qt.AltModifier,
            QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier,
        ):
            return value

        if isinstance(value, bool):
            result = not value
        elif isinstance(value, (int, float)):
            result = abs(value) if value < 0 else -value
        else:
            result = value

        return result

    @staticmethod
    def simulate_key_press(
        ui, key=QtCore.Qt.Key_F12, modifiers=QtCore.Qt.NoModifier, release=False
    ):
        """Simulate a key press event for the given UI and optionally release the keyboard.

        Parameters:
            ui (QtWidgets.QWidget): The UI widget to simulate the key press for.
            key (QtCore.Qt.Key): The key to simulate. Defaults to QtCore.Qt.Key_F12.
            modifiers (QtCore.Qt.KeyboardModifiers): The keyboard modifiers to apply. Defaults to QtCore.Qt.NoModifier.
            release (bool): Whether to simulate a key release event.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError("The 'ui' parameter must be a QWidget or a subclass.")

        # Create and post the key press event
        press_event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, modifiers)
        QtWidgets.QApplication.postEvent(ui, press_event)

        # Optionally create and post the key release event
        if release:
            release_event = QtGui.QKeyEvent(QtCore.QEvent.KeyRelease, key, modifiers)
            QtWidgets.QApplication.postEvent(ui, release_event)

    def defer_with_timer(self, func: callable, *args, ms: int = 300, **kwargs) -> None:
        """Defer execution of any callable with arguments after a delay.

        Parameters:
            func (callable): The function to be called after the delay.
            *args: Positional arguments for the function.
            ms (int, optional): Delay in milliseconds before execution. Default is 300.
            **kwargs: Keyword arguments for the function.

        Raises:
            ValueError: If func is not callable.
            TypeError: If ms is not an integer.
        """
        if not callable(func):
            raise ValueError(
                f"[defer_with_timer] Expected a callable, got {type(func).__name__}"
            )

        if not isinstance(ms, int):
            raise TypeError(
                f"[defer_with_timer] ms must be an integer, got {type(ms).__name__}"
            )

        def safe_call():
            """Executes the function safely and logs any exceptions."""
            try:
                func(*args, **kwargs)
            except Exception as e:
                self.logger.error(
                    f"[defer_with_timer] Exception in deferred call to {func.__name__}: {e}"
                )
                self.logger.debug(traceback.format_exc())
                if args and "ms" not in kwargs and isinstance(args[0], int):
                    raise TypeError(
                        "[defer_with_timer] Did you mean to pass ms as a keyword argument?"
                    )

        # Schedule the deferred execution
        QtCore.QTimer.singleShot(ms, safe_call)

    def gc_protect(self, obj=None, clear=False):
        """
        Protect the given object(s) from garbage collection by holding a strong reference.
        Parameters:
            obj (obj/list): The obj(s) to add to the protected dict.
            clear (bool): Clear the dict before adding any given object(s).
        Returns:
            dict: The protected objects.
        """
        if not hasattr(self, "_gc_protect"):
            self._gc_protect = {}

        if clear:
            self._gc_protect.clear()

        for o in ptk.make_iterable(obj):
            key = o.objectName() or id(o)
            self._gc_protect[key] = o

            # Remove from dict when destroyed
            def _cleanup(key=key):
                self._gc_protect.pop(key, None)

            try:
                o.destroyed.connect(_cleanup)
            except AttributeError:
                self.logger.debug(
                    f"Object {o} does not have a 'destroyed' signal. Cannot connect to it."
                )

        return self._gc_protect
