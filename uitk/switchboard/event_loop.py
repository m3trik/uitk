# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk


class _EventLoop:
    """Event-loop helpers behind the Switchboard: deferred calls, synthetic key
    presses, modifier-aware value inversion and keeping Qt objects alive. Owns the
    strong references :meth:`gc_protect` holds.
    """

    def __init__(self, logger):
        self._logger = logger  # () -> the Switchboard's logger, read per call
        self._protected = {}  # gc_protect: key -> object held alive

    @staticmethod
    def invert_on_modifier(value):
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
                self._logger().error(
                    f"[defer_with_timer] Exception in deferred call to {func.__name__}: {e}",
                    exc_info=True,
                )
                if args and "ms" not in kwargs and isinstance(args[0], int):
                    raise TypeError(
                        "[defer_with_timer] Did you mean to pass ms as a keyword argument?"
                    )

        # Schedule the deferred execution
        QtCore.QTimer.singleShot(ms, safe_call)

    def gc_protect(self, obj=None, clear=False):
        if clear:
            self._protected.clear()

        for o in ptk.make_iterable(obj):
            key = o.objectName() or id(o)
            self._protected[key] = o

            # Remove from dict when destroyed
            def _cleanup(key=key):
                self._protected.pop(key, None)

            try:
                o.destroyed.connect(_cleanup)
            except AttributeError:
                self._logger().debug(
                    f"Object {o} does not have a 'destroyed' signal. Cannot connect to it."
                )

        return self._protected
