# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay
from uitk.widgets.mixins.menu_mixin import MenuMixin
from uitk.widgets.mixins.option_box_mixin import OptionBoxMixin


class PushButton(
    MenuMixin,
    QtWidgets.QPushButton,
    OptionBoxMixin,
    AttributesMixin,
    RichText,
    TextOverlay,
):
    """QPushButton with automatic Menu and OptionBox integration.

    Features:
    - self.menu: Standalone menu (via MenuMixin)
    - self.option_box: OptionBox functionality (via OptionBoxMixin)
    - self.option_box.menu: Separate option box menu
    """

    def __init__(self, parent=None, **kwargs):
        QtWidgets.QPushButton.__init__(self, parent)

        # override built-ins
        self.text = self.richText
        self.setText = self.setRichText
        self.sizeHint = self.richTextSizeHint

        # Customize standalone menu (provided by MenuMixin)
        self.menu.trigger_button = "right"
        self.menu.fixed_item_height = 20
        self.menu.hide_on_leave = True
        self.menu.add_apply_button = True  # Enable apply button for pushbutton menus

        # OptionBox is also available via OptionBoxMixin
        # Users can access: self.option_box.menu, self.option_box.clear_option, etc.

        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from qtpy.QtCore import QSize

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

    w = PushButton(
        parent=None,
        setObjectName="button_test",
        setText='<hl style="color:black;">A QPushButton <hl style="color:violet;"><b>with Rich Text</b></hl>',
        resize=QSize(125, 45),
        # setVisible=True,
    )

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
