# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtGui, QtWidgets
import inspect


class Convert:
    """Class providing utility methods to handle common conversions related to Qt objects."""

    types = {
        QtCore.QPoint: (2, lambda x: QtCore.QPoint(*x)),
        QtCore.QSize: (2, lambda x: QtCore.QSize(*x)),
        QtCore.QRect: (4, lambda x: QtCore.QRect(*x)),
        QtGui.QColor: (4, lambda x: QtGui.QColor(*x)),
        QtCore.QPointF: (2, lambda x: QtCore.QPointF(*x)),
        QtCore.QLineF: (4, lambda x: QtCore.QLineF(*x)),
        QtCore.QLine: (4, lambda x: QtCore.QLine(*x)),
        QtCore.QMargins: (4, lambda x: QtCore.QMargins(*x)),
        QtGui.QPolygonF: (None, lambda x: QtGui.QPolygonF(*x)),
        QtCore.QDateTime: (3, lambda x: QtCore.QDateTime(*x)),
        QtCore.QDate: (3, lambda x: QtCore.QDate(*x)),
        QtCore.QTime: (3, lambda x: QtCore.QTime(*x)),
        QtGui.QVector3D: (3, lambda x: QtGui.QVector3D(*x)),
        QtGui.QVector4D: (4, lambda x: QtGui.QVector4D(*x)),
    }

    @staticmethod
    def to_qobject(value, q_object_type):
        """Convert a tuple or list to a QObject if not already one."""
        if isinstance(value, q_object_type):
            return value

        if q_object_type not in Convert.types or not isinstance(value, (tuple, list)):
            raise ValueError(
                f"Value must be a {q_object_type.__name__} or a tuple/list. got {type(value)}"
            )

        num_params, constructor = Convert.types[q_object_type]

        if num_params is not None and len(value) != num_params:
            raise ValueError(
                f"Incorrect number of arguments for {q_object_type.__name__}. got {len(value)}"
            )

        return constructor(value)

    @staticmethod
    def can_convert(value, q_object_type):
        """Check if a value can be converted to a certain QObject type."""
        if q_object_type not in Convert.types or not isinstance(value, (tuple, list)):
            return False

        num_params, _ = Convert.types[q_object_type]
        return num_params is None or len(value) == num_params


if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # Test cases
    print(Convert.to_qobject((10, 20), QtCore.QPoint))  # QPoint(10,20)
    print(Convert.to_qobject((30, 40), QtCore.QSize))  # QSize(30,40)
    print(Convert.to_qobject((50, 60, 70, 80), QtCore.QRect))  # QRect(50,60,70,80)
    print(
        Convert.to_qobject((90, 100, 110, 120), QtGui.QColor)
    )  # QColor(90,100,110,120)
    print(Convert.to_qobject((130.0, 140.0), QtCore.QPointF))  # QPointF(130.0,140.0)
    print(
        Convert.to_qobject((150.0, 160.0, 170.0), QtGui.QVector3D)
    )  # QVector3D(150.0,160.0,170.0)

    # Test can_convert method
    print(Convert.can_convert((10, 20), QtCore.QPoint))  # True
    print(Convert.can_convert((30, 40, 50), QtCore.QSize))  # False
    print(Convert.can_convert((60, 70, 80, 90), QtCore.QRect))  # True
    print(Convert.can_convert((100, 110, 120, 130, 140), QtGui.QColor))  # False
    print(Convert.can_convert((150.0, 160.0), QtCore.QPointF))  # True
    print(Convert.can_convert((170.0, 180.0, 190.0, 200.0), QtGui.QVector4D))  # True

    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------


# depricated ------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
