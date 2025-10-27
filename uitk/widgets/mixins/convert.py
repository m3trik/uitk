# !/usr/bin/python
# coding=utf-8
from typing import Union, Optional, Type
from qtpy import QtWidgets, QtCore, QtGui


class ConvertMixin:
    """Class providing utility methods to handle common conversions related to Qt objects."""

    TYPES = {
        QtCore.QPoint: lambda x: QtCore.QPoint(*x),
        QtCore.QSize: lambda x: QtCore.QSize(*x),
        QtCore.QRect: lambda x: QtCore.QRect(*x),
        QtGui.QColor: lambda x: QtGui.QColor(*x),  # Flexible for RGB/RGBA.
        QtCore.QPointF: lambda x: QtCore.QPointF(*x),
        QtCore.QLineF: lambda x: QtCore.QLineF(*x),
        QtCore.QLine: lambda x: QtCore.QLine(*x),
        QtCore.QMargins: lambda x: QtCore.QMargins(*x),
        QtGui.QPolygonF: lambda x: QtGui.QPolygonF(x),  # Passed as iterable.
        QtCore.QDateTime: lambda x: QtCore.QDateTime.fromJulianDay(*x),
        QtCore.QDate: lambda x: QtCore.QDate(*x),
        QtCore.QTime: lambda x: QtCore.QTime(*x),
        QtGui.QVector3D: lambda x: QtGui.QVector3D(*x),
        QtGui.QVector4D: lambda x: QtGui.QVector4D(*x),
    }

    @staticmethod
    def _resolve_qtype(q_object_type):
        """Accept either a Qt type or a string ('QColor'), and return the type object."""
        if isinstance(q_object_type, str):
            # Try QtCore, then QtGui
            for mod in (QtCore, QtGui):
                qt_type = getattr(mod, q_object_type, None)
                if qt_type is not None:
                    return qt_type
            raise ValueError(
                f"Qt type string '{q_object_type}' not found in QtCore or QtGui."
            )
        return q_object_type

    @staticmethod
    def can_convert(value, q_object_type) -> bool:
        """Check if a value can be converted to the specified QObject type (accepts class or string)."""
        qt_type = ConvertMixin._resolve_qtype(q_object_type)
        if isinstance(value, qt_type):
            return True
        if qt_type is QtGui.QColor and isinstance(value, (str, tuple, list)):
            return True
        return qt_type in ConvertMixin.TYPES

    @staticmethod
    def to_qobject(value, q_object_type):
        """Convert a value to a QObject of the specified type (accepts class or string)."""
        qt_type = ConvertMixin._resolve_qtype(q_object_type)

        # If the value is already of the correct type, return it
        if isinstance(value, qt_type):
            return value

        # Early exit for invalid values like None
        if value is None:
            raise ValueError(
                f"[ERROR] Invalid value 'None' for {qt_type.__name__} conversion, please provide a valid {qt_type.__name__}."
            )

        # Handle specific cases based on Qt type
        if qt_type is QtGui.QColor:
            if isinstance(value, str):
                return QtGui.QColor(value)
            elif isinstance(value, (tuple, list)):
                if all(isinstance(v, (int, float)) for v in value):
                    return QtGui.QColor(*value)

        elif qt_type is QtCore.QPoint:
            if isinstance(value, (tuple, list)) and len(value) == 2:
                return QtCore.QPoint(*value)
            else:
                raise ValueError(f"[ERROR] Invalid value for QPoint: {value}")

        elif qt_type is QtCore.QSize:
            if isinstance(value, (tuple, list)) and len(value) == 2:
                return QtCore.QSize(*value)
            else:
                raise ValueError(f"[ERROR] Invalid value for QSize: {value}")

        # General conversion handling for other types
        constructor = ConvertMixin.TYPES.get(qt_type)
        if constructor:
            try:
                return constructor(value)
            except Exception as e:
                raise ValueError(
                    f"Failed to construct {qt_type.__name__} from value {value}: {e}"
                )

        # If none of the above worked, raise an error
        raise ValueError(f"Conversion to {qt_type.__name__} failed for value: {value}")

    @staticmethod
    def to_qkey(key: Union[str, QtCore.Qt.Key]) -> Optional[QtCore.Qt.Key]:
        """Convert a given key identifier to a Qt key constant."""
        if isinstance(key, QtCore.Qt.Key):
            return key
        elif isinstance(key, str):
            key_string = f"Key_{key}" if not key.startswith("Key_") else key
            return getattr(QtCore.Qt, key_string, None)
        else:
            raise ValueError(
                f"[ERROR] Invalid key value: {key}. Expected QtCore.Qt.Key or string."
            )

    @staticmethod
    def to_qmousebutton(
        button: Union[str, QtCore.Qt.MouseButton, tuple, list, None],
    ) -> Union[QtCore.Qt.MouseButton, tuple, None, bool]:
        """Convert button identifier(s) to Qt MouseButton constant(s).

        Parameters:
            button: Button identifier - can be:
                - String: "left", "right", "middle", "back", "forward", "any", "none"
                - Qt.MouseButton constant
                - Tuple/list of strings or Qt.MouseButton constants
                - None (same as "none" - no auto-trigger)

        Returns:
            QtCore.Qt.MouseButton: Single button constant
            tuple: Multiple button constants
            None: Any button allowed (from "any" only)
            False: No auto-trigger (from "none" or None input) - sentinel value

        Raises:
            ValueError: If button type is invalid or string is not recognized

        Examples:
            >>> ConvertMixin.to_qmousebutton("left")
            <MouseButton.LeftButton: 1>

            >>> ConvertMixin.to_qmousebutton("right")
            <MouseButton.RightButton: 2>

            >>> ConvertMixin.to_qmousebutton("any")
            None  # Any button allowed

            >>> ConvertMixin.to_qmousebutton("none")
            False  # No auto-trigger

            >>> ConvertMixin.to_qmousebutton(None)
            False  # Same as "none" - no auto-trigger

            >>> ConvertMixin.to_qmousebutton(("left", "right"))
            (<MouseButton.LeftButton: 1>, <MouseButton.RightButton: 2>)
        """
        # Button string to Qt constant mapping
        button_map = {
            "left": QtCore.Qt.LeftButton,
            "right": QtCore.Qt.RightButton,
            "middle": QtCore.Qt.MiddleButton,
            "back": QtCore.Qt.BackButton,
            "forward": QtCore.Qt.ForwardButton,
            "any": None,  # Special: any button triggers
            "none": False,  # Special: no auto-trigger (sentinel value)
        }

        # Handle None input - treat as "none" (no auto-trigger)
        if button is None:
            return False

        # Handle string input
        if isinstance(button, str):
            normalized = button.lower().strip()
            if normalized in button_map:
                return button_map[normalized]
            else:
                valid_keys = ", ".join(button_map.keys())
                raise ValueError(
                    f"Invalid button string '{button}'. "
                    f"Valid values are: {valid_keys}"
                )

        # Handle tuple/list of buttons
        if isinstance(button, (tuple, list)):
            normalized_buttons = []
            for btn in button:
                if isinstance(btn, str):
                    # Recursively convert string
                    converted = ConvertMixin.to_qmousebutton(btn)
                    # Skip None and False sentinels in tuples (they don't make sense)
                    if converted is not None and converted is not False:
                        normalized_buttons.append(converted)
                elif isinstance(btn, QtCore.Qt.MouseButton):
                    normalized_buttons.append(btn)
                else:
                    raise ValueError(
                        f"Invalid button type in collection: {type(btn)}. "
                        f"Expected str or QtCore.Qt.MouseButton"
                    )

            # Return based on count
            if len(normalized_buttons) == 0:
                return None  # Empty tuple = any button
            elif len(normalized_buttons) == 1:
                return normalized_buttons[0]
            else:
                return tuple(normalized_buttons)

        # Handle Qt MouseButton constant
        if isinstance(button, QtCore.Qt.MouseButton):
            return button

        # Invalid type
        raise ValueError(
            f"Invalid button type: {type(button)}. "
            f"Expected str, QtCore.Qt.MouseButton, tuple, list, or None"
        )


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # Test cases
    print(ConvertMixin.to_qobject((10, 20), QtCore.QPoint))  # QPoint(10,20)
    print(ConvertMixin.to_qobject((30, 40), QtCore.QSize))  # QSize(30,40)
    print(ConvertMixin.to_qobject((50, 60, 70, 80), QtCore.QRect))  # QRect(50,60,70,80)
    print(ConvertMixin.to_qobject((90, 100, 110), QtGui.QColor))  # QColor(90,100,110)
    print(
        ConvertMixin.to_qobject((90, 100, 110, 120), QtGui.QColor)
    )  # QColor(90,100,110,120)
    print(
        ConvertMixin.to_qobject((130.0, 140.0), QtCore.QPointF)
    )  # QPointF(130.0,140.0)
    print(
        ConvertMixin.to_qobject((150.0, 160.0, 170.0), QtGui.QVector3D)
    )  # QVector3D(150.0,160.0,170.0)

    # Test can_convert method
    print(ConvertMixin.can_convert((10, 20), QtCore.QPoint))  # True
    print(ConvertMixin.can_convert((30, 40, 50), QtCore.QSize))  # False
    print(ConvertMixin.can_convert((60, 70, 80, 90), QtCore.QRect))  # True
    print(ConvertMixin.can_convert((100, 110, 120, 130, 140), QtGui.QColor))  # False
    print(ConvertMixin.can_convert((150.0, 160.0), QtCore.QPointF))  # True
    print(
        ConvertMixin.can_convert((170.0, 180.0, 190.0, 200.0), QtGui.QVector4D)
    )  # True

    # Test the to_qkey method with various input types
    print(ConvertMixin.to_qkey("A"))  # Should print the Qt key constant for 'A'
    print(
        ConvertMixin.to_qkey(QtCore.Qt.Key_A)
    )  # Should directly return QtCore.Qt.Key_A
    print(ConvertMixin.to_qkey("Key_A"))  # Should print the Qt key constant for 'A'

    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------


# depricated ------------------------------------------------------------------------
