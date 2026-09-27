# !/usr/bin/python
# coding=utf-8
"""Where a top-level popup surface may sit: its screen, and the on-screen clamp."""

from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets


class PopupPlacement:
    """Screen resolution and the clamp for top-level surfaces.

    Shared by every surface that floats on its own: ``Menu``, an
    ``ExpandableList`` flyout, and ``MainWindow``. Each carried its own copy of
    the clamp, and the flyout's trimmed copy fell back to the PRIMARY screen
    whenever its centre was off every screen, sliding a flyout that opened
    past the far edge of a secondary monitor across the desk to the primary.
    """

    @staticmethod
    def screen_for(rect: QtCore.QRect) -> Optional[QtGui.QScreen]:
        """The screen a surface with global geometry *rect* belongs to.

        The screen under its centre; failing that (the centre is off every
        screen) the screen it overlaps most; failing that the primary screen.

        Parameters:
            rect: The surface's global frame geometry.

        Returns:
            QtGui.QScreen or None: None only when the application has no screen.
        """
        screen = None
        if hasattr(QtWidgets.QApplication, "screenAt"):
            screen = QtWidgets.QApplication.screenAt(rect.center())

        if not screen:
            max_area = 0
            for candidate in QtWidgets.QApplication.screens():
                overlap = rect.intersected(candidate.geometry())
                area = overlap.width() * overlap.height()
                if area > max_area:
                    max_area = area
                    screen = candidate

        if not screen:
            screen = QtWidgets.QApplication.primaryScreen()
        return screen

    @classmethod
    def clamp_to_screen(cls, widget: QtWidgets.QWidget) -> None:
        """Slide a top-level *widget* fully into its screen's available area.

        Slides rather than flips: a surface near an edge may end up covering
        the thing it was anchored to. Moves only when a correction is needed,
        so an on-screen surface sees no ``move()`` at all.

        Parameters:
            widget: A top-level widget; its frame geometry is global.
        """
        frame_geo = widget.frameGeometry()
        screen = cls.screen_for(frame_geo)
        if not screen:
            return

        # Available geometry excludes taskbars and docks.
        screen_geo = screen.availableGeometry()

        x = frame_geo.x()
        y = frame_geo.y()
        width = frame_geo.width()
        height = frame_geo.height()

        if x + width > screen_geo.right():
            x = screen_geo.right() - width
        if x < screen_geo.left():
            x = screen_geo.left()

        if y + height > screen_geo.bottom():
            y = screen_geo.bottom() - height
        if y < screen_geo.top():
            y = screen_geo.top()

        if x != frame_geo.x() or y != frame_geo.y():
            widget.move(x, y)
