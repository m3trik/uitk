# !/usr/bin/python
# coding=utf-8
from typing import Union, Optional, Type
from qtpy import QtCore, QtGui, QtWidgets


class ConvertMixin:
    """Class providing utility methods to handle common conversions related to Qt objects."""

    # Adjusted types dictionary without rigid tuple length, relying on dynamic handling instead.
    types = {
        QtCore.QPoint: lambda x: QtCore.QPoint(*x),
        QtCore.QSize: lambda x: QtCore.QSize(*x),
        QtCore.QRect: lambda x: QtCore.QRect(*x),
        QtGui.QColor: lambda x: QtGui.QColor(*x),  # Now flexible for RGB/RGBA.
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
    def can_convert(value, q_object_type: Type) -> bool:
        """Check if a given value can be converted to the specified QObject type.

        Parameters:
            value: The value to check for conversion compatibility.
            q_object_type: The Qt class type to check against.

        Returns:
            True if a conversion function exists for `q_object_type`, False otherwise.
        """
        # Check for a direct match or string conversion for QColor
        if issubclass(q_object_type, QtGui.QColor) and isinstance(
            value, (str, tuple, list)
        ):
            return True

        # Check for the existence of a conversion function in the types dictionary
        return q_object_type in ConvertMixin.types

    @staticmethod
    def to_qobject(
        value, q_object_type: Type[Union[QtCore.QObject, QtGui.QColor]]
    ) -> Optional[Union[QtCore.QObject, QtGui.QColor]]:
        """Convert a value to a QObject of the specified type if not already one.

        This method dynamically handles conversions, leveraging the types dictionary
        for mappings and utilizing special handling where necessary.
        """
        # Directly return the value if it's already an instance of the target Qt type
        if isinstance(value, q_object_type):
            return value

        # Dynamic handling for QColor to support a variety of initialization formats
        if issubclass(q_object_type, QtGui.QColor):
            if isinstance(value, str):
                return QtGui.QColor(value)
            elif isinstance(value, (tuple, list)):
                if all(isinstance(v, float) for v in value):
                    # Treat as normalized float values
                    return QtGui.QColor.fromRgbF(*value)
                elif all(isinstance(v, int) for v in value):
                    # Treat as integer RGB values
                    return QtGui.QColor.fromRgb(*value)

        # Handle conversions for other types specified in the types dictionary
        constructor = ConvertMixin.types.get(q_object_type)
        if constructor:
            try:  # Attempt to construct the QObject using the provided value
                return constructor(value)
            except Exception as e:
                print(
                    f"Failed to construct {q_object_type.__name__} from value {value}: {e}"
                )

        print(f"Conversion to {q_object_type.__name__} failed for value: {value}")
        return None

    @staticmethod
    def to_qkey(key: Union[str, QtCore.Qt.Key]) -> Optional[QtCore.Qt.Key]:
        """Convert a given key identifier to a Qt key constant. Handles both string identifiers and Qt.Key enum values.

        Parameters:
            key: The key identifier to convert, which can be a string or a QtCore.Qt.Key enum.

        Returns:
            The corresponding Qt key constant if the conversion is successful, otherwise None.
        """
        if isinstance(key, QtCore.Qt.Key):
            return key
        elif isinstance(key, str):
            key_string = f"Key_{key}" if not key.startswith("Key_") else key
            return getattr(QtCore.Qt, key_string, None)
        else:
            return None


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
