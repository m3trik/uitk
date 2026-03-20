# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtGui, QtCore
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.settings_manager import SettingsManager


class CollapsableGroup(QtWidgets.QGroupBox, AttributesMixin):
    """Expandable/collapsible group box that shows or hides its contents."""

    def __init__(self, title, parent=None, **kwargs):
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(True)  # Start expanded
        self.restore_state = True  # Default to restoring state
        self.settings = SettingsManager()
        self._expanded_height = None  # Saved height before collapse
        self._state_enforced = False  # Guards against double _enforce_state
        self._suppress_window_resize = False  # Skip window resize during restore

        # Connect the toggle signal
        self.toggled.connect(self.toggle_expand)

        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

        # Ensure state is applied after UI loading (fixes uic loading issue)
        QtCore.QTimer.singleShot(0, self._enforce_state)

    def _enforce_state(self, suppress_resize=False):
        """Ensure the visibility matches the checked state.

        Parameters:
            suppress_resize: If True, skip window resize during state
                enforcement.  Used by MainWindow to settle group states
                before restoring saved window geometry.
        """
        if self._state_enforced:
            return
        self._state_enforced = True

        if self.restore_state and self.objectName():
            key = f"CollapsableGroup/{self.objectName()}/checked"
            val = self.settings.value(key)
            if val is not None:
                # Block signals so setChecked doesn't trigger toggle_expand
                # via toggled signal (we call it explicitly below).
                self.blockSignals(True)
                self.setChecked(val)
                self.blockSignals(False)

        self._suppress_window_resize = suppress_resize
        try:
            self.toggle_expand(self.isChecked())
        finally:
            self._suppress_window_resize = False

    def _collapsed_height(self):
        """Return the height to use when collapsed (title bar only)."""
        return self.fontMetrics().height()

    def toggle_expand(self, checked):
        """Toggle the expanded/collapsed state"""
        # Save state
        if self.restore_state and self.objectName():
            key = f"CollapsableGroup/{self.objectName()}/checked"
            self.settings.setValue(key, checked)

        # Capture the actual heights BEFORE making changes
        window = self.window()
        old_window_height = window.height() if window else 0
        old_group_height = self.height()

        # Show/hide all child widgets
        self._set_content_visible(checked)

        if checked:
            self.setMaximumHeight(16777215)  # Restore max height
            # Use the saved pre-collapse height if available, otherwise
            # fall back to sizeHint.  This prevents drift when sizeHint
            # is larger than the actual rendered height (e.g. window was
            # smaller than the ideal size).
            if self._expanded_height is not None:
                new_group_height = self._expanded_height
                self._expanded_height = None
            else:
                new_group_height = super(CollapsableGroup, self).sizeHint().height()
        else:
            # Remember the actual height before collapsing so expand can
            # restore to exactly the same value.
            self._expanded_height = old_group_height
            collapsed = self._collapsed_height()
            self.setMaximumHeight(collapsed)
            new_group_height = collapsed

        # Let Qt handle the layout
        self.updateGeometry()
        if self.parent():
            self.parent().updateGeometry()

        # Force layout to recalculate minimum sizes before resizing
        delta = new_group_height - old_group_height
        if window and delta != 0:
            if window.layout():
                window.layout().activate()
            self._apply_window_resize(old_window_height, delta)

    def _apply_window_resize(self, old_window_height, delta):
        """Apply the computed delta to the window after the layout settles."""
        if self._suppress_window_resize:
            return
        window = self.window()
        if not window:
            return
        new_height = max(old_window_height + delta, window.minimumHeight())
        window.resize(window.width(), new_height)

    def _set_content_visible(self, visible):
        """Show or hide all child widgets.

        When showing, also ensures immediate children of each layout item
        are visible.  This handles OptionBoxContainer wrappers whose inner
        widgets were hidden during a previous collapse and never un-hidden
        because toggle only touches direct layout children.
        """
        if not self.layout():
            return

        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            w = item.widget() if item else None
            if not w:
                continue
            w.setVisible(visible)
            # When expanding, ensure children inside wrapper containers
            # (e.g. OptionBoxContainer) are also made visible so that
            # widgets wrapped after a collapse aren't left hidden.
            if visible and w.layout():
                for j in range(w.layout().count()):
                    child_item = w.layout().itemAt(j)
                    child = child_item.widget() if child_item else None
                    if child and child.isHidden():
                        child.setVisible(True)

    def setLayout(self, layout):
        """Override setLayout. The stylesheet handles title positioning
        via ``margin`` and ``subcontrol-origin``, so we do **not** force
        extra top margin here."""
        super().setLayout(layout)

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
        """Return appropriate size hint based on current state."""
        hint = super().sizeHint()
        if not self.isChecked():
            return QtCore.QSize(hint.width(), self._collapsed_height())
        return hint


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
