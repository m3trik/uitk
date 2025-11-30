# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtGui, QtCore
from uitk.widgets.mixins.attributes import AttributesMixin


class CollapsableGroup(QtWidgets.QGroupBox, AttributesMixin):
    """Expandable/collapsible group box that shows or hides its contents."""

    def __init__(self, title, parent=None, **kwargs):
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(True)  # Start expanded

        # Connect the toggle signal
        self.toggled.connect(self.toggle_expand)

        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    def toggle_expand(self, checked):
        """Toggle the expanded/collapsed state"""
        # Store the current window size before toggling
        window = self.window()
        old_size = window.size()

        # Simply show/hide all child widgets
        self._set_content_visible(checked)

        # Let Qt handle the layout automatically
        self.updateGeometry()

        # Notify parent that our size changed
        if self.parent():
            self.parent().updateGeometry()

        # Adjust window size based on the size change
        QtCore.QTimer.singleShot(0, lambda: self._adjust_window_size(old_size))

    def _adjust_window_size(self, old_size):
        """Adjust the window size after collapse/expand"""
        window = self.window()

        # Get the new size hint
        new_hint = window.sizeHint()

        # Calculate the height difference
        height_diff = new_hint.height() - old_size.height()

        # Only resize if there's a significant change
        if abs(height_diff) > 5:  # Threshold to avoid tiny adjustments
            new_height = max(old_size.height() + height_diff, window.minimumHeight())
            window.resize(old_size.width(), new_height)

    def _set_content_visible(self, visible):
        """Show or hide all child widgets"""
        # Only process if we have a layout
        if not self.layout():
            return

        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item and item.widget():
                item.widget().setVisible(visible)

    def setLayout(self, layout):
        """Override to ensure proper margins for title"""
        super().setLayout(layout)
        if layout:
            # Ensure we have enough top margin for the title
            margins = layout.contentsMargins()
            if margins.top() < 15:
                layout.setContentsMargins(
                    margins.left(), 20, margins.right(), margins.bottom()
                )

    def addWidget(self, widget):
        """Add a widget to the collapsible content area"""
        # Create layout if it doesn't exist
        if not self.layout():
            self.setLayout(QtWidgets.QVBoxLayout())

        self.layout().addWidget(widget)

        # If we're collapsed, hide the new widget
        if not self.isChecked():
            widget.setVisible(False)

    def addLayout(self, layout):
        """Add a layout to the collapsible content area"""
        if not self.layout():
            self.setLayout(QtWidgets.QVBoxLayout())

        self.layout().addLayout(layout)

    def sizeHint(self):
        """Return appropriate size hint based on current state"""
        hint = super().sizeHint()

        # If collapsed, return minimal height
        if not self.isChecked():
            title_height = self.fontMetrics().height()
            collapsed_height = title_height + 25  # Add padding for frame
            return QtCore.QSize(hint.width(), collapsed_height)

        return hint

    def paintEvent(self, event):
        """Custom paint event for styling"""
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
            QtGui.QColor("lightblue") if not self.isChecked() else QtGui.QColor("white")
        )
        painter.setPen(text_color)
        painter.drawText(text_rect, self.alignment(), self.title())


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # Create main window
    main_window = QtWidgets.QMainWindow()
    central_widget = QtWidgets.QWidget()
    main_window.setCentralWidget(central_widget)

    layout = QtWidgets.QVBoxLayout(central_widget)

    # Create collapsible group
    expandable_area = CollapsableGroup("CLICK ME")

    # Add some content to test
    expandable_area.addWidget(QtWidgets.QLabel("Content line 1"))
    expandable_area.addWidget(QtWidgets.QLabel("Content line 2"))
    expandable_area.addWidget(QtWidgets.QPushButton("Test Button"))

    layout.addWidget(expandable_area)
    layout.addStretch()  # Push content to top

    main_window.resize(300, 200)
    main_window.show()

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
