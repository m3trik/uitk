# !/usr/bin/python
# coding=utf-8
from qtpy import QtCore, QtGui, QtWidgets
import pythontk as ptk


class AttributesMixin:
    """A mixin class providing a comprehensive interface for setting attributes on Qt widgets.
    It allows setting of standard widget properties, calling methods, connecting signals to callbacks,
    and handling custom-defined attributes.

    The class defines several utility methods:

    - set_legal_attribute: Handles setting of attributes even when the attribute names contain illegal characters,
      by converting these names into legal formats. It can also retain the original attribute name if required.

    - set_attributes: The primary method used for setting a range of attributes on one or more widgets.
      This method intelligently distinguishes between regular attributes, method calls, and signal connections,
      routing each type to its specific handling procedure.

    - _is_signal: Checks if a given attribute name corresponds to a Qt signal on the widget.

    - _connect_signal: Connects Qt signals to specified callback functions.

    - _set_attribute_or_call_method: Handles setting standard attributes and calling methods on widgets.

    - _set_custom_attribute: A flexible method designed to set custom attributes. This method can be
      overridden or extended in subclasses to accommodate specific custom attributes beyond the standard Qt attributes.

    Usage:
    - Objects of this mixin class or its subclasses can set attributes on Qt widgets by calling `set_attributes`
      with appropriate parameters.
    - The class is designed to work as a mixin with Qt widgets or other classes in a Qt application,
      enhancing them with versatile attribute setting capabilities.

    Example:
    ```
    class MyWidget(QtWidgets.QWidget, AttributesMixin):
        def __init__(self):
            super().__init__()
            self.set_attributes(self, setWindowTitle="My Application", set_size=(200, 100))
    ```
    """

    def set_flags(self, **flags):
        """Sets or unsets given window flags, safely ignoring unsupported cases.

        Parameters:
            flags (dict): A dictionary where keys are flag names (as strings) and values are booleans indicating whether to set or unset the flag.

        Example:
            set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=False)
        """
        try:
            current_flags = self.windowFlags()

            for flag, add in flags.items():
                if hasattr(QtCore.Qt, flag):
                    flag_value = getattr(QtCore.Qt, flag)
                    current_flags = (
                        current_flags | flag_value
                        if add
                        else current_flags & ~flag_value
                    )

            self.setWindowFlags(current_flags)

        except Exception as e:
            print(f"[AttributeMixin] Set_flags failed: {e}")

    def set_legal_attribute(self, obj, name, value, also_set_original=False):
        """If the original name contains illegal characters, this method sets an attribute using
        a legal name created by replacing illegal characters with underscores. The original name
        attribute is also assigned if also_set_original is True.

        Parameters:
            obj (object): The object to which the attribute will be assigned
            name (str): The original name to be assigned
            value (): The value to be assigned to the attribute
            also_set_original (bool): Whether to keep the original attribute if an alternative legal name is created
        """
        import re

        legal_name = re.sub(r"[^0-9a-zA-Z]", "_", name)
        # if the name contains illegal chars; set an alternate attribute using legal characters.
        if name != legal_name:
            setattr(obj, legal_name, value)
            if also_set_original:
                setattr(obj, name, value)
        else:
            setattr(obj, name, value)

    def set_attributes(self, *objects, **attributes):
        if not attributes:
            return

        if not objects:
            objects = (self,)

        for obj in objects:
            for attr, value in attributes.items():
                if self._is_signal(obj, attr):
                    self._connect_signal(obj, attr, value)
                else:
                    self._set_attribute_or_call_method(obj, attr, value)

    def _is_signal(self, obj, attr_name):
        """Check if an attribute is a signal."""
        attr = getattr(obj, attr_name, None)
        return isinstance(attr, QtCore.Signal)

    def _connect_signal(self, obj, signal_name, callback):
        """Connect a signal to a callback function."""
        signal = getattr(obj, signal_name, None)
        if signal and isinstance(signal, QtCore.Signal):
            signal.connect(callback)
        else:
            print(f"Error: {obj} has no signal named {signal_name}")

    def _set_attribute_or_call_method(self, obj, attr, value):
        """Set an attribute or call a method on the object."""
        try:
            attr_value = getattr(QtCore.Qt, attr)
            obj.setAttribute(attr_value, value)
        except AttributeError:
            try:
                method = getattr(obj, attr)
                if callable(method):
                    method(value)
                else:
                    raise AttributeError(f"Attribute '{attr}' is not callable on {obj}")
            except AttributeError:
                self._set_custom_attribute(obj, attr, value)

    def _set_custom_attribute(self, w, attr, value):
        """AttributesMixin that throw an AttributeError in 'set_attributes' are sent here, where they can be assigned a value.
        Custom attributes can be set using a trailing underscore convention to aid readability, and differentiate them from standard attributes.

        Parameters:
            w (obj): The child widget or widgetAction to set attributes for.
            attr (str): Custom keyword attribute.
            value (str): The value corresponding to the given attr.

        attributes:
            transfer_properties (obj): The widget to copy attributes from.
            set_size (list): The size as an x and y value. ie. (40, 80)
            set_width (int): The desired width.
            set_height (int): The desired height.
            set_position (QPoint)(str): Move to the given global position and center. valid: <QPoint>, 'cursor',
            add_menu (QMenu) = Used for adding additional menus to a parent menu. ex. parentMenu = Menu(); childMenu = Menu('Create', add_menu=parentMenu)
            insert_separator (bool): Insert a line separater before the new widget.
            set_layout_direction (str): Set the layout direction using a string value. ie. 'LeftToRight'
            set_alignment (str): Set the alignment using a string value. ie. 'AlignVCenter'
            set_button_symbols (str): Set button symbols using a string value. ex. ie. 'PlusMinus'
            set_limits (tuple): Set the min, max, step, and decimal value using a string value. ex. (0.01, 10, 1, 2)
            setCheckState (int): Set a tri-state checkbox state using an integer value. 0(unchecked), 1(partially checked), 2(checked).
            block_signals_on_restore (bool): If False, widget signals will fire during state restoration. Default is True (signals blocked).
        """
        try:
            if attr == "transfer_properties":
                self._transfer_widget_properties(value, w)

            elif attr == "set_size":
                x, y = value
                w.resize(QtCore.QSize(x, y))

            elif attr == "set_width":
                w.resize(value, w.size().height())

            elif attr == "set_height":
                w.resize(w.size().width(), value)

            elif attr == "set_fixed_size":
                x, y = value
                w.setFixedSize(QtCore.QSize(x, y))

            elif attr == "set_fixed_width":
                w.setFixedWidth(value)

            elif attr == "set_fixed_height":
                w.setFixedHeight(value)

            elif attr == "set_position":
                if value == "cursor":
                    value = QtGui.QCursor.pos()
                w.move(w.mapFromGlobal(value - w.rect().center()))  # move and center

            elif attr == "add_menu":
                value.addMenu(w)

            elif attr == "insert_separator":
                if w.__class__.__name__ == "QAction":
                    self.insertSeparator(w)

            elif attr == "set_layout_direction":
                self.set_attributes(w, setLayoutDirection=getattr(QtCore.Qt, value))

            elif attr == "set_alignment":
                self.set_attributes(w, setAlignment=getattr(QtCore.Qt, value))

            elif attr == "set_button_symbols":
                self.set_attributes(
                    w, setButtonSymbols=getattr(QtWidgets.QAbstractSpinBox, value)
                )

            # presets
            elif attr == "set_limits":
                self._set_spinbox_limits(w, value)

            elif attr == "set_by_value":
                if isinstance(w, QtWidgets.QAbstractSpinBox):
                    self._set_spinbox_by_value(w, value)

            elif attr == "setCheckState":
                state = {
                    0: QtCore.Qt.CheckState.Unchecked,
                    1: QtCore.Qt.CheckState.PartiallyChecked,
                    2: QtCore.Qt.CheckState.Checked,
                }
                w.setCheckState(state[value])

            # Fallback: directly set any custom attribute
            else:
                setattr(w, attr, value)

        except AttributeError as e:
            print(f"Error: {e}")

    def _set_spinbox_limits(self, spinbox, limits):
        """Configure the minimum, maximum, step values, and decimal precision for a given spinbox widget.

        The function allows you to set these parameters using a tuple of up to four values. The decimal precision,
        when not explicitly provided, is inferred from the number of decimal places in the minimum or maximum values,
        depending on whichever is higher. If neither of these values has decimal parts, the default precision is set to zero.

        Parameters:
            spinbox (object): An instance of a spinbox widget. It is assumed that this object supports the setting of minimum, maximum, step,
                and decimal precision.
            limits (list): A list that can contain up to four values, interpreted in the following order:
                1. Lower bound (minimum) - This is cast to a float value. If not provided, a default of 0.0 is used.
                2. Upper bound (maximum) - This is cast to a float value. If not provided, a default of 9999999.0 is used.
                3. Step - The increment/decrement step of the spinbox. If not provided, a default of 1 is used.
                4. Decimals - The decimal precision (number of digits after the decimal point). If not provided, the function
                   calculates this value based on the number of decimal places in the minimum or maximum values.
        """
        if not isinstance(limits, (list, tuple)):
            raise TypeError(
                f"Invalid datatype for limits. Expected list or tuple, got {type(limits)}"
            )

        value_len = len(limits)
        minimum = float(limits[0]) if value_len > 0 else -2147483647
        maximum = float(limits[1]) if value_len > 1 else 2147483647
        step = limits[2] if value_len > 2 else 1.0

        if isinstance(spinbox, QtWidgets.QDoubleSpinBox):
            if value_len > 3:
                decimals = limits[3]
            else:
                min_decimals = (
                    len(str(minimum).split(".")[-1]) if "." in str(minimum) else 0
                )
                max_decimals = (
                    len(str(maximum).split(".")[-1]) if "." in str(maximum) else 0
                )
                decimals = max(min_decimals, max_decimals)

            self.set_attributes(spinbox, setDecimals=decimals)

        self.set_attributes(
            spinbox,
            setMinimum=minimum,
            setMaximum=maximum,
            setSingleStep=step,
            set_button_symbols="NoButtons",
        )

    def _set_spinbox_by_value(self, spinbox, value):
        """Set a spinbox's attributes according to a given value.

        Parameters:
            spinbox (obj): spinbox widget.
            value (multi) = attribute value.
        """
        maximum = spinbox.maximum()
        minimum = -maximum

        if isinstance(value, (int, bool)):
            step = spinbox.singleStep()

            if isinstance(value, bool):
                value = int(value)
                minimum = 0
                maximum = 1

            self.set_attributes(
                spinbox,
                setValue=value,
                setMinimum=minimum,
                setMaximum=maximum,
                setSingleStep=step,
                set_button_symbols="NoButtons",
            )

        elif isinstance(value, float):
            decimals = str(value)[::-1].find(".")  # get decimal places
            step = ptk.move_decimal_point(1, -decimals)

            self.set_attributes(
                spinbox,
                setValue=value,
                setMinimum=minimum,
                setMaximum=maximum,
                setSingleStep=step,
                setDecimals=decimals,
                set_button_symbols="NoButtons",
            )

    @staticmethod
    def _transfer_widget_properties(source, target):
        """Transfers the properties of a source widget to a target widget.

        This function retrieves the meta-object of the source widget and iterates over its properties.
        For each property, it gets the corresponding value from the source widget and sets it on the target widget.

        Parameters:
            source (QWidget): The widget to copy properties from.
            target (QWidget): The widget to copy properties to.
        """
        source_meta_obj = source.metaObject()

        for idx in range(
            source_meta_obj.propertyCount()
        ):  # Iterate over all properties of the source widget.
            prop = source_meta_obj.property(idx)
            attr_name = prop.name()

            value = source.property(
                attr_name
            )  # Get the value of the corresponding property in the source widget.
            target.setProperty(
                attr_name, value
            )  # Set the value of the property on the target widget.


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

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
