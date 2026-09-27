# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore, QtGui


class SwitchboardPlacementMixin:
    """Window placement: centering a widget on a point, the screen or the
    cursor, and the cursor's offset from a widget's center."""

    @staticmethod
    def get_cursor_offset_from_center(widget):
        """Get the relative position of the cursor with respect to the center of a given widget.

        Parameters:
            widget (QWidget): The widget to query.

        Returns:
            (obj) QPoint
        """
        return QtGui.QCursor.pos() - widget.rect().center()

    @staticmethod
    def center_widget(
        widget,
        pos=None,
        offset_x=0,
        offset_y=0,
        padding_x=None,
        padding_y=None,
        relative: QtWidgets.QWidget = None,
    ):
        """Adjust the widget's size to fit contents and center it at the given point, on the screen, at cursor, or at the widget's current position if no point is given.

        Parameters:
            widget (QWidget): The widget to move and resize.
            pos (QPoint/str, optional): A point to move to, or 'screen' to center on screen, or 'cursor' to center at cursor position. Defaults to None.
            offset_x (int, optional): The desired offset percentage on the x axis. Defaults to 0.
            offset_y (int, optional): The desired offset percentage on the y axis. Defaults to 0.
            padding_x (int, optional): Additional width from the widget's minimum size or relative widget. If not specified, the widget's current width is used. A maximumWidth too small to fit the result is raised to fit, unless minimumWidth == maximumWidth (a deliberate fixed-size lock, left untouched).
            padding_y (int, optional): Additional height from the widget's minimum size or relative widget. If not specified, the widget's current height is used. Same maximumHeight handling as padding_x.
            relative (QWidget, optional): If given, use this widget's current size as the base size for resizing.
        """
        # Resize the widget if padding values are provided
        if padding_x is not None or padding_y is not None:
            p1 = widget.rect().center()

            w = widget if not relative else relative
            x = w.minimumSizeHint().width() if padding_x is not None else w.width()
            y = w.minimumSizeHint().height() if padding_y is not None else w.height()

            target_w = x + (padding_x if padding_x is not None else 0)
            target_h = y + (padding_y if padding_y is not None else 0)

            # padding_x/padding_y request a content-fit size; a stale
            # Designer-authored maximumSize (sized for different/shorter
            # text) would otherwise silently truncate widget.resize() below,
            # defeating that request. Raise the ceiling rather than let it --
            # but only where maximumWidth/Height is acting as a loose ceiling
            # (minimum < maximum). Where the two are equal, that's a
            # deliberate fixed-size lock (e.g. a square icon tile) rather
            # than a stale leftover, and must not be widened out from under it.
            if (
                padding_x is not None
                and target_w > widget.maximumWidth()
                and widget.maximumWidth() > widget.minimumWidth()
            ):
                widget.setMaximumWidth(target_w)
            if (
                padding_y is not None
                and target_h > widget.maximumHeight()
                and widget.maximumHeight() > widget.minimumHeight()
            ):
                widget.setMaximumHeight(target_h)

            widget.resize(target_w, target_h)
            p2 = widget.rect().center()
            diff = p1 - p2
            widget.move(widget.pos() + diff)

        # Determine the center point based on the provided pos value
        if pos == "screen":
            rect = QtWidgets.QApplication.primaryScreen().availableGeometry()
            centerPoint = rect.center()
        elif pos == "cursor":
            centerPoint = QtGui.QCursor.pos()
        elif pos is None:
            centerPoint = widget.frameGeometry().center()
        elif isinstance(pos, QtCore.QPoint):
            centerPoint = pos
        else:
            raise ValueError(
                "Invalid value for pos. It should be either 'screen', 'cursor', a QPoint instance or None."
            )

        # Compute the offset
        offset = QtCore.QPoint(
            widget.width() * offset_x / 100, widget.height() * offset_y / 100
        )
        # Center the widget considering the offset
        widget.move(centerPoint - widget.rect().center() + offset)
