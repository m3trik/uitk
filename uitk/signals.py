# !/usr/bin/python
# coding=utf-8
"""Signal utilities and decorators for Qt slot management.

This module provides decorators for annotating slot methods with their
intended signal connections, used by Switchboard for automatic wiring.

Functions:
    block_signals: Decorator that blocks widget signals during method execution.

Classes:
    Signals: Decorator class to specify which signals a slot should connect to.

Example:
    Using @Signals to override default signal connections::

        class MySlots:
            @Signals('clicked', 'pressed')
            def my_button(self, widget=None):
                print("Button interacted")

    Using @block_signals to prevent signal loops::

        @Signals.blockSignals
        def update_widget(self):
            self.spinbox.setValue(10)  # Won't trigger valueChanged
"""
from functools import wraps


def block_signals(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        self.blockSignals(True)
        rtn = fn(self, *args, **kwargs)
        self.blockSignals(False)
        return rtn

    return wrapper


class Signals:
    """Class-based decorator to annotate slot methods with the signals to which they should connect.

    This class takes one or more signal names as strings during initialization and assigns them as attributes
    to the decorated function. The signals can be later retrieved for connecting the slot method to the respective signals.

    Attributes:
        signals (tuple of str): Tuple containing one or more signal names as strings.

    Raises:
        ValueError: If no signals are provided during initialization.
        TypeError: If any of the provided signals is not a string.

    Example:
        @Signals('clicked', 'pressed')
        def on_button_interaction():
            print("Button interacted")
    """

    def __init__(self, *signals):
        if len(signals) == 0:
            raise ValueError("At least one signal must be specified")

        for signal in signals:
            if not isinstance(signal, str):
                raise TypeError(f"Signal must be a string, not {type(signal)}")

        self.signals = signals

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper.signals = self.signals
        return wrapper

    @classmethod
    def blockSignals(cls, func):
        return block_signals(func)
