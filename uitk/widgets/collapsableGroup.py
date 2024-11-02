# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtGui


class CollapsableGroup(QtWidgets.QGroupBox):
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setCheckable(True)
        self.toggled.connect(self.toggle_expand)

    def show_content(self):
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item.widget():
                item.widget().show()

    def hide_content(self):
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item.widget():
                item.widget().hide()

    def calculate_content_height(self):
        return sum(
            item.widget().sizeHint().height() if item.widget() else 0
            for item in [self.layout().itemAt(i) for i in range(self.layout().count())]
        )

    def titleHeight(self):
        return self.fontMetrics().height() + self.style().pixelMetric(
            QtWidgets.QStyle.PM_IndicatorWidth
        )

    def toggle_expand(self, state):
        top_level_widget = self.window()
        current_window_height = top_level_widget.height()
        current_content_height = self.calculate_content_height() - 35

        if state:
            self.show_content()
            new_window_height = current_window_height + current_content_height
        else:
            new_window_height = current_window_height - current_content_height
            self.hide_content()

        top_level_widget.resize(top_level_widget.width(), new_window_height)

    def paintEvent(self, event):
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionGroupBox()
        self.initStyleOption(option)

        # Draw the frame and background
        painter.drawPrimitive(QtWidgets.QStyle.PE_FrameGroupBox, option)

        # Draw the title text with custom color
        text_rect = self.style().subControlRect(
            QtWidgets.QStyle.CC_GroupBox,
            option,
            QtWidgets.QStyle.SC_GroupBoxLabel,
            self,
        )
        text_color = (
            QtGui.QColor("light blue")
            if not self.isChecked()
            else QtGui.QColor("white")
        )
        painter.setPen(text_color)
        painter.drawText(text_rect, self.alignment(), self.title())


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    expandable_area = CollapsableGroup("CLICK ME")
    expandable_area.setLayout(QtWidgets.QVBoxLayout())
    expandable_area.show()
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
