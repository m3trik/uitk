# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets
from uitk.widgets.mixins.text import RichText
from uitk.widgets.mixins.attributes import AttributesMixin


class OptionBox(QtWidgets.QPushButton, AttributesMixin, RichText):
    """A subclass of QPushButton designed to represent an option box that can wrap
    around another widget and display a context menu when clicked.

    Attributes:
        text (method): Overrides the QPushButton's text method with richText.
        setText (method): Overrides the QPushButton's setText method with setRichText.
        sizeHint (method): Overrides the QPushButton's sizeHint method with richTextSizeHint.
        wrapped_widget (QWidget): The widget that the option box wraps around.
    """

    def __init__(self, parent=None, **kwargs):
        QtWidgets.QPushButton.__init__(self, parent)
        """Instantiates the OptionBox with specific text, configures its size based
        on the parent's size, and sets its additional attributes.

        Parameters:
            box_text (str): The text to be displayed on the option box.
            **kwargs: Arbitrary keyword arguments for setting additional attributes.
        """
        # override built-ins
        self.text = self.richText
        self.setText = self.setRichText
        self.sizeHint = self.richTextSizeHint

        self.setStyleSheet("OptionBox {border: none;}")

        # Connect the clicked signal to the show_menu slot
        self.clicked.connect(self.show_menu)

        self.setText("⧉")
        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    def remove_border_for_widget(self, wrapped_widget):
        """Removes the border from the wrapped widget and the instance of this class.
        This is achieved by applying a class-specific style sheet to both widgets.

        Parameters:
            wrapped_widget (QWidget): The widget that is being wrapped by the option box.
        """
        wrapped_widget.setStyleSheet(
            wrapped_widget.__class__.__name__ + " {border: none;}"
        )
        self.setStyleSheet(self.__class__.__name__ + " {border: none;}")

    def wrap(self, wrapped_widget):
        """Wraps the option box around another widget. This involves creating a container
        widget, setting up a new layout, and placing the wrapped widget and the option
        box within that layout.

        Parameters:
            wrapped_widget (QWidget): The widget to be wrapped by the option box.
        """
        g_parent = wrapped_widget.parent()
        container = QtWidgets.QWidget(g_parent)
        container.setProperty("class", "withBorder")

        # Set the height of the container to match the original parent's height
        container.setFixedHeight(wrapped_widget.height())

        # Set the size policy to prevent automatic resizing
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
        )
        container.setSizePolicy(sizePolicy)

        if g_parent.layout() is not None:
            g_parent.layout().replaceWidget(wrapped_widget, container)
            g_parent.layout().update()
        else:
            initial_pos = wrapped_widget.pos()
            container.move(initial_pos)

        self.setObjectName("{}_optionBox".format(wrapped_widget.objectName()))

        self.setMaximumSize(
            wrapped_widget.size().height(), wrapped_widget.size().height()
        )
        wrapped_widget.setMinimumSize(
            wrapped_widget.size().width() - wrapped_widget.size().height(),
            wrapped_widget.size().height(),
        )

        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(wrapped_widget, 0)
        layout.addWidget(self, 1)

        self.wrapped_widget = wrapped_widget
        self.remove_border_for_widget(wrapped_widget)
        container.setVisible(True)

        # Install wrapped widget's event filter onto the option box
        self.installEventFilter(self.wrapped_widget)

    def show_menu(self):
        """Shows the option menu if it contains items."""
        if self.menu.contains_items:
            if not self.wrapped_widget.isVisible():
                # If the wrapped widget is not visible, show at cursor pos.
                orig_pos = self.menu.position
                self.menu.position = "cursorPos"
                self.menu.show()
                self.menu.position = orig_pos
            else:
                self.menu.show()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QWidget()
    parent = QtWidgets.QPushButton(window)
    parent.setText("Button w/option Box")
    parent.resize(140, 21)

    option_box = OptionBox(
        setText='<hl style="color:red;">⛾</hl>',
    )
    option_box.wrap(parent)
    from qtpy.QtGui import QFont

    option_box.setFont(QFont("Arial", 12))  # Set the font size for the options

    option_a = QtWidgets.QAction("Option A", option_box)
    option_b = QtWidgets.QAction("Option B", option_box)

    option_box.addAction(option_a)
    option_box.addAction(option_b)
    option_box.menu.add([option_a, option_b])

    window.show()
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

# Deprecated: --------------------
