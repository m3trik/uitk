# !/usr/bin/python
# coding=utf-8
"""Reusable helper for attaching a QSizeGrip to arbitrary widgets."""

from typing import Optional, Union
from qtpy import QtWidgets, QtCore, QtGui


class CornerSizeGrip(QtWidgets.QSizeGrip):
    """Custom QSizeGrip with a simple diagonal corner indicator."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._hovered = False
        self._base_color = QtGui.QColor(255, 255, 255, 140)
        self._hover_color = QtGui.QColor(255, 255, 255, 200)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, False)
        self.setAttribute(QtCore.Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.SizeFDiagCursor)
        self.setMinimumSize(12, 12)
        self.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)

    def enterEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    @staticmethod
    def _to_color(value: Union[QtGui.QColor, QtCore.Qt.GlobalColor, str, tuple, list]):
        if isinstance(value, QtGui.QColor):
            return QtGui.QColor(value)
        if isinstance(value, (tuple, list)):
            return QtGui.QColor(*value)
        if isinstance(value, QtCore.Qt.GlobalColor):
            return QtGui.QColor(value)
        return QtGui.QColor(value)

    def getBaseColor(self) -> QtGui.QColor:
        return QtGui.QColor(self._base_color)

    def setBaseColor(self, value) -> None:
        try:
            color = self._to_color(value)
        except Exception:
            return
        if color != self._base_color:
            self._base_color = color
            self.update()

    def getHoverColor(self) -> QtGui.QColor:
        return QtGui.QColor(self._hover_color)

    def setHoverColor(self, value) -> None:
        try:
            color = self._to_color(value)
        except Exception:
            return
        if color != self._hover_color:
            self._hover_color = color
            self.update()

    baseColor = QtCore.Property(QtGui.QColor, fget=getBaseColor, fset=setBaseColor)
    hoverColor = QtCore.Property(QtGui.QColor, fget=getHoverColor, fset=setHoverColor)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QtCore.Qt.transparent)

        color = self._hover_color if self._hovered else self._base_color

        rect = self.rect().adjusted(1, 1, -1, -1)
        triangle = QtGui.QPolygon(
            [
                QtCore.QPoint(rect.right(), rect.top()),
                QtCore.QPoint(rect.right(), rect.bottom()),
                QtCore.QPoint(rect.left(), rect.bottom()),
            ]
        )

        painter.setBrush(color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPolygon(triangle)

        painter.setPen(QtGui.QPen(color.lighter(120), 1))
        painter.drawLine(rect.right(), rect.top(), rect.right(), rect.bottom())
        painter.drawLine(rect.right(), rect.bottom(), rect.left(), rect.bottom())

        painter.end()


class SizeGripMixin:
    """Mixin that provides a consistent QSizeGrip attachment helper."""

    size_grip_object_name = "size_grip"
    size_grip_alignment = QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight

    def create_size_grip(
        self,
        container: Optional[QtWidgets.QWidget] = None,
        layout: Optional[QtWidgets.QLayout] = None,
        *,
        alignment: Optional[QtCore.Qt.Alignment] = None,
    ) -> Optional[QtWidgets.QSizeGrip]:
        """Create or reuse a size grip and ensure it is inserted in *layout*."""
        if not isinstance(self, QtWidgets.QWidget):
            return None

        container = container or self._size_grip_default_container()
        if container is None:
            return None

        layout = layout or container.layout()
        size_grip = self.findChild(QtWidgets.QSizeGrip, self.size_grip_object_name)

        if size_grip is None:
            size_grip = CornerSizeGrip(container)
            size_grip.setObjectName(self.size_grip_object_name)
        elif size_grip.parentWidget() is not container:
            size_grip.setParent(container)

        size_grip.setProperty("class", "SizeGrip")
        setattr(self, self.size_grip_object_name, size_grip)

        style = size_grip.style()
        try:
            if style:
                style.unpolish(size_grip)
                style.polish(size_grip)
        except Exception:
            pass

        if layout is None:
            return size_grip

        if layout.indexOf(size_grip) == -1:
            layout.addWidget(size_grip)

        target_alignment = (
            alignment
            if alignment is not None
            else getattr(self, "size_grip_alignment", self.size_grip_alignment)
        )
        layout.setAlignment(size_grip, target_alignment)

        return size_grip

    def ensure_size_grip(
        self,
        *,
        container: Optional[QtWidgets.QWidget] = None,
        layout: Optional[QtWidgets.QLayout] = None,
        alignment: Optional[QtCore.Qt.Alignment] = None,
    ) -> Optional[QtWidgets.QSizeGrip]:
        """Backward-compatible alias for :meth:`create_size_grip`."""

        return self.create_size_grip(
            container=container,
            layout=layout,
            alignment=alignment,
        )

    def _size_grip_default_container(self) -> Optional[QtWidgets.QWidget]:
        """Return the widget that should host the size grip by default."""
        central_widget = None
        if hasattr(self, "centralWidget") and callable(getattr(self, "centralWidget")):
            central_widget = self.centralWidget()
            if isinstance(central_widget, QtWidgets.QWidget):
                return central_widget

        return self if isinstance(self, QtWidgets.QWidget) else None
