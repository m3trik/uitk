# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.mixins.attributes import AttributesMixin


class HoverSwitcher(QtCore.QObject):
    """Helper class to handle hover switching logic for ToolBox."""

    def __init__(self, toolbox):
        super().__init__(toolbox)
        self.toolbox = toolbox
        self._previous_index = -1

        # Install event filter
        self.toolbox.installEventFilter(self)
        self.toolbox.currentChanged.connect(self._adjust_cursor_position)

    def eventFilter(self, obj, event):
        """Handle mouse move events for hover switching."""
        if obj == self.toolbox:
            if event.type() == QtCore.QEvent.MouseMove:
                # Check if mouse is over any of the tab buttons
                for child in self.toolbox.children():
                    if isinstance(child, QtWidgets.QAbstractButton):
                        # Map global pos to button pos
                        btn_pos = child.mapFromGlobal(QtGui.QCursor.pos())
                        if child.rect().contains(btn_pos):
                            # Find which index this button corresponds to
                            for i in range(self.toolbox.count()):
                                if self.toolbox.itemText(i) == child.text():
                                    if self.toolbox.currentIndex() != i:
                                        self.toolbox.setCurrentIndex(i)
                                    break
        return False

    def _adjust_cursor_position(self, index):
        """Adjust cursor position if moving down and cursor falls outside content."""
        # If we moved up (index < previous_index), we don't need to move cursor
        # because the content will be below the cursor.
        if index > self._previous_index:
            widget = self.toolbox.currentWidget()
            if widget:
                QtCore.QTimer.singleShot(
                    50, lambda: self._ensure_cursor_in_widget(widget)
                )

        self._previous_index = index

    def _ensure_cursor_in_widget(self, widget):
        if widget and widget.isVisible():
            # Get global rect
            top_left = widget.mapToGlobal(QtCore.QPoint(0, 0))
            bottom_right = widget.mapToGlobal(
                QtCore.QPoint(widget.width(), widget.height())
            )
            global_rect = QtCore.QRect(top_left, bottom_right)

            cursor_pos = QtGui.QCursor.pos()

            if not global_rect.contains(cursor_pos):
                x = cursor_pos.x()
                y = cursor_pos.y()

                # Clamp to inside with small padding
                padding = 10

                if x < global_rect.left():
                    x = global_rect.left() + padding
                elif x > global_rect.right():
                    x = global_rect.right() - padding

                if y < global_rect.top():
                    y = global_rect.top() + padding
                elif y > global_rect.bottom():
                    y = global_rect.bottom() - padding

                QtGui.QCursor.setPos(x, y)


class ToolBox(QtWidgets.QToolBox, AttributesMixin):
    """A customized QToolBox with additional features and styling support.

    Inherits from QToolBox and AttributesMixin to provide a consistent interface
    with other uitk widgets.

    Attributes:
        switch_on_hover (bool): If True, tabs will switch when the mouse hovers over them.
    """

    def __init__(self, parent=None, switch_on_hover=False, checkable=False, **kwargs):
        super().__init__(parent)
        self.switch_on_hover = switch_on_hover
        self.set_attributes(**kwargs)

        self.currentChanged.connect(self.updateGeometry)

        # Initialize hover switcher if enabled
        self._hover_switcher = None
        if self.switch_on_hover:
            self._hover_switcher = HoverSwitcher(self)

    def sizeHint(self):
        """Calculate size hint based on current page and tabs."""
        height = 0
        width = super().sizeHint().width()

        # Add height of all tab buttons
        for child in self.children():
            if isinstance(child, QtWidgets.QAbstractButton):
                height += child.sizeHint().height()

        # Add height of current page
        current = self.currentWidget()
        if current:
            if isinstance(current, QtWidgets.QScrollArea) and current.widget():
                widget = current.widget()

                # Force layout update
                if widget.layout():
                    widget.layout().activate()

                # Get content dimensions
                # Prefer layout sizeHint as it's most accurate for containers
                if widget.layout():
                    size_hint = widget.layout().sizeHint()
                    content_height = size_hint.height()
                    content_width = size_hint.width()
                else:
                    size_hint = widget.sizeHint()
                    content_height = size_hint.height()
                    content_width = size_hint.width()

                height += content_height

                # Add scroll area frame and margins
                frame_width = current.frameWidth() * 2
                c_margins = current.contentsMargins()
                
                height += frame_width
                height += c_margins.top() + c_margins.bottom()
                
                content_width += frame_width
                content_width += c_margins.left() + c_margins.right()

                # Add viewport margins
                if current.viewport():
                    v_margins = current.viewport().contentsMargins()
                    height += v_margins.top() + v_margins.bottom()
                    content_width += v_margins.left() + v_margins.right()

                # Add horizontal scrollbar height
                h_bar = current.horizontalScrollBar()
                if h_bar:
                    height += h_bar.sizeHint().height()
                
                # Add vertical scrollbar width if we might hit the height cap
                if height > 800:
                    v_bar = current.verticalScrollBar()
                    if v_bar:
                        content_width += v_bar.sizeHint().width()

                # Add a safety buffer for borders/focus rects
                height += 10
                
                # Update width if content is wider
                width = max(width, content_width)

            else:
                height += current.sizeHint().height()

        # Add some padding/borders
        height += self.frameWidth() * 2
        margins = self.contentsMargins()
        height += margins.top() + margins.bottom()

        # Cap at 800
        height = min(height, 800)

        # Ensure minimum
        height = max(height, 100)

        return QtCore.QSize(width, height)

    def add(self, widget, text, icon=None, **kwargs):
        """Add a widget as a new tab item.

        Parameters:
            widget (QWidget): The widget to add.
            text (str): The text to display on the tab.
            icon (QIcon, optional): The icon to display on the tab.
            **kwargs: Additional attributes to set on the widget.

        Returns:
            int: The index of the added item.
        """
        if icon:
            index = self.addItem(widget, icon, text)
        else:
            index = self.addItem(widget, text)

        self.set_attributes(widget, **kwargs)

        return index
