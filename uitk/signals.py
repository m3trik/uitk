# !/usr/bin/python
# coding=utf-8
from functools import wraps


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
