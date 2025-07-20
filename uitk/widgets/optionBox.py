# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets
from uitk.widgets.mixins.text import RichText
from uitk.widgets.mixins.icon_manager import IconManager
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
        IconManager.set_icon(self, "option_box", size=(17, 17))

        self.clicked.connect(self.show_menu)
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

    def wrap(self, wrapped_widget: QtWidgets.QWidget) -> None:
        """Wraps the option box around another widget, creating a container and syncing border style."""
        self.wrapped_widget = wrapped_widget
        self.container = self._create_wrapping_container(wrapped_widget)

        self._adjust_wrapped_widget_size(wrapped_widget)
        self._sync_object_name(wrapped_widget)
        self._patch_stylesheet_sync(wrapped_widget)
        self._sync_container_border()
        self.container.setVisible(True)

    def _create_wrapping_container(
        self, wrapped_widget: QtWidgets.QWidget
    ) -> QtWidgets.QWidget:
        """Create and return a container QWidget that wraps around the given widget."""
        parent = wrapped_widget.parent()
        container = QtWidgets.QWidget(parent)
        container.setFixedHeight(wrapped_widget.height())
        container.setSizePolicy(
            QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
            )
        )

        if parent.layout():
            parent.layout().replaceWidget(wrapped_widget, container)
            parent.layout().update()
        else:
            container.move(wrapped_widget.pos())

        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.setParent(container)
        layout.addWidget(wrapped_widget)
        layout.addWidget(self)

        return container

    def _adjust_wrapped_widget_size(self, wrapped_widget: QtWidgets.QWidget) -> None:
        """Adjust minimum and maximum sizes of the option box and wrapped widget."""
        height = wrapped_widget.size().height()
        width = wrapped_widget.size().width()

        self.setMaximumSize(height, height)
        wrapped_widget.setMinimumSize(width - height, height)

    def _sync_object_name(self, wrapped_widget: QtWidgets.QWidget) -> None:
        """Bind the option box's objectName to track the wrapped widget's objectName."""

        def sync_name():
            self.setObjectName(f"{wrapped_widget.objectName()}_optionBox")

        sync_name()

        original_set_name = wrapped_widget.setObjectName

        def new_set_name(name):
            original_set_name(name)
            sync_name()

        wrapped_widget.setObjectName = new_set_name.__get__(wrapped_widget)

    def _patch_stylesheet_sync(self, wrapped_widget: QtWidgets.QWidget) -> None:
        """Patch wrapped widget's setStyleSheet to sync container border style."""
        original_set_style = wrapped_widget.setStyleSheet

        def new_set_style(this, style):
            original_set_style(style)
            self._sync_container_border()

        wrapped_widget.setStyleSheet = new_set_style.__get__(wrapped_widget)

    def _sync_container_border(self) -> None:
        """Syncs the container's border with the wrapped widget's border style."""
        style = self.wrapped_widget.styleSheet()
        border = ""
        # Extract any line containing 'border'
        for line in style.split(";"):
            if "border" in line:
                border += line.strip() + ";"
        if border:  # Set the border for the container
            self.container.setStyleSheet(f"QWidget.withBorder {{{border}}}")
        else:  # Default/fallback border style
            self.container.setStyleSheet("QWidget.withBorder {border: none;}")

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
