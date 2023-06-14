# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets
from pythontk import move_decimal_point


class AttributesMixin:
    """Methods for setting widget AttributesMixin."""

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
        if (
            name != legal_name
        ):  # if the name contains illegal chars; set an alternate attribute using legal characters.
            setattr(obj, legal_name, value)
            if also_set_original:
                setattr(obj, name, value)
        else:
            setattr(obj, name, value)

    def set_attributes(self, obj=None, **kwargs):
        """Works with attributes passed in as a dict or kwargs.
        If attributes are passed in as a dict, kwargs are ignored.

        Parameters:
                obj (obj): the child obj or widgetAction to set attributes for. (default=self)
                **kwargs = The keyword arguments to set.
        """
        if not kwargs:  # if no attributes given.
            return

        if not obj:
            obj = self

        for attr, value in kwargs.items():
            try:
                getattr(obj, attr)(value)

            except Exception:
                # print ('set_attributes:', attr, value)
                self.set_custom_attribute(obj, attr, value)

    def set_custom_attribute(self, w, attr, value):
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
                set_check_state (int): Set a tri-state checkbox state using an integer value. 0(unchecked), 1(partially checked), 2(checked).
        """
        if attr == "transfer_properties":
            self.transfer_properties(value, w)

        elif attr == "set_size":
            x, y = value
            w.resize(QtCore.QSize(x, y))

        elif attr == "set_width":
            w.setFixedWidth(value)
            # w.resize(value, w.size().height())

        elif attr == "set_height":
            w.setFixedHeight(value)
            # w.resize(w.size().width(), value)

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
            self.set_limits(w, value)

        elif attr == "set_spinbox_by_value":
            if isinstance(w, QtWidgets.QAbstractSpinBox):
                self.set_spinbox_by_value(w, value)

        elif attr == "set_check_state":
            state = {
                0: QtCore.Qt.CheckState.Unchecked,
                1: QtCore.Qt.CheckState.PartiallyChecked,
                2: QtCore.Qt.CheckState.Checked,
            }
            w.setCheckState(state[value])

        else:
            print("Error: {} has no attribute {}".format(w, attr))

    def set_limits(self, spinbox, value):
        """Configure the minimum, maximum, step values, and decimal precision for a given spinbox widget.

        The function allows you to set these parameters using a tuple of up to four values. The decimal precision,
        when not explicitly provided, is inferred from the number of decimal places in the minimum or maximum values,
        depending on whichever is higher. If neither of these values has decimal parts, the default precision is set to zero.

        Parameters:
            spinbox (object): An instance of a spinbox widget. It is assumed that this object supports the setting of minimum, maximum, step,
                    and decimal precision.
            value (tuple): A tuple that can contain up to four values, interpreted in the following order:
                    1. Lower bound (minimum) - This is cast to a float value. If not provided, a default of 0.0 is used.
                    2. Upper bound (maximum) - This is cast to a float value. If not provided, a default of 9999999.0 is used.
                    3. Step - The increment/decrement step of the spinbox. If not provided, a default of 1 is used.
                    4. Decimals - The decimal precision (number of digits after the decimal point). If not provided, the function
                       calculates this value based on the number of decimal places in the minimum or maximum values.
        """
        value_len = len(value)
        minimum = float(value[0]) if value_len > 0 else 0
        maximum = float(value[1]) if value_len > 1 else 9999999
        step = value[2] if value_len > 2 else 1

        if value_len > 3:
            decimals = value[3]
        else:  # If decimal value not given, determine from minimum or maximum
            decimals = (
                max(
                    len(str(minimum).split(".")[-1]),  # Count decimals in minimum
                    len(str(maximum).split(".")[-1]),  # Count decimals in maximum
                )
                if any(map(lambda x: len(str(x).split(".")[1]) > 1, [minimum, maximum]))
                else 0
            )  # Ensure the values have decimal part

        if hasattr(spinbox, "setDecimals"):
            self.set_attributes(spinbox, setDecimals=decimals)

        self.set_attributes(
            spinbox,
            setMinimum=minimum,
            setMaximum=maximum,
            setSingleStep=step,
            set_button_symbols="NoButtons",
        )

    def set_spinbox_by_value(self, spinbox, value):
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
            step = move_decimal_point(1, -decimals)

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
    def transfer_properties(source, target):
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

# depricated ------------------------------------------------------------------------

# def move_decimal_point(num, decimal_places):
#       '''Move the decimal place in a given number.

#       Parameters:
#           decimal_places (int): decimal places to move. (works only with values 0 and below.)

#       Returns:
#           (float) the given number with it's decimal place moved by the desired amount.

#       ex. move_decimal_point(11.05, -2) Returns: 0.1105
#       '''
#       for _ in range(abs(decimal_places)):

#           if decimal_places>0:
#               num *= 10; #shifts decimal place right
#           else:
#               num /= 10.; #shifts decimal place left

#       return float(num)
