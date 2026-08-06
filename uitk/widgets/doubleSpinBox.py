# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.feedback import FeedbackMixin
from uitk.widgets.mixins.menu_mixin import MenuMixin
from uitk.widgets.mixins.spin_box_display import PrefixColumnMixin
from uitk.widgets.mixins.spin_box_display import SpinBoxTextColorMixin
from uitk.widgets.mixins.wheel_step import WheelStepMixin


class DoubleSpinBox(
    WheelStepMixin,
    FeedbackMixin,
    SpinBoxTextColorMixin,
    PrefixColumnMixin,
    QtWidgets.QDoubleSpinBox,
    MenuMixin,
    AttributesMixin,
):
    """Custom QDoubleSpinBox with modifier-driven wheel-step adjustment.

    See :class:`uitk.widgets.mixins.wheel_step.WheelStepMixin` for the
    Ctrl / Ctrl+Shift / Alt / Ctrl+Alt modifier contract,
    :class:`uitk.widgets.mixins.feedback.FeedbackMixin` for the transient
    HUD popup that surfaces the step amount, and
    :class:`uitk.widgets.mixins.spin_box_display.PrefixColumnMixin` for the
    label/value column that ``setPrefix`` lays out.
    """

    # Qt Designer widget-box entry.
    designer_spec = {"icon": "font_size", "object_name": "s"}

    # Class-level menu defaults (applied when menu is first accessed)
    _menu_defaults = {"hide_on_leave": True}

    def __init__(self, parent=None, **kwargs):
        QtWidgets.QDoubleSpinBox.__init__(self, parent)

        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    def textFromValue(self, value: float) -> str:
        """Format the text displayed in the spin box, removing trailing zeros and unnecessary decimal points."""
        return "{:g}".format(value)


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from qtpy.QtCore import QSize

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

    w = DoubleSpinBox(
        parent=None,
        setObjectName="button_test",
        setPrefix="Prefix:",
        resize=QSize(125, 45),
        # setVisible=True,
    )

    w.set_attributes(set_limits=(-100000, 100000, 1, 4))

    w.show()
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
