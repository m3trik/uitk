# !/usr/bin/python
# coding=utf-8
"""Reusable helper for attaching a QSizeGrip to arbitrary widgets."""

from typing import Optional, Tuple, Union
from qtpy import QtWidgets, QtCore, QtGui

# Qt's QWIDGETSIZE_MAX — the sentinel for "no maximum" on a widget dimension.
QWIDGETSIZE_MAX = 16777215

# Qt's QLAYOUTSIZE_MAX — QLayout.maximumSize() saturates here (not at
# QWIDGETSIZE_MAX), so any layout maximum at or above this means "unbounded".
_QLAYOUTSIZE_MAX = (1 << 19) - 1  # 524287


class CornerSizeGrip(QtWidgets.QSizeGrip):
    """Custom QSizeGrip with a simple diagonal corner indicator.

    On mouse-press the grip syncs its window's maximum size to the content's
    real maximum (see :meth:`SizeGripMixin.sync_window_max_to_content`), so a
    drag can never stretch the window into dead space in a direction where
    every visible child is fixed — and clears any stale lock once the content
    becomes growable again. The hover cursor reflects the lock: diagonal when
    both directions are free, horizontal/vertical when one is locked."""

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
        self._update_lock_cursor()
        self.update()
        super().enterEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Sync the window's max size to its content before the drag starts.

        Press-time (rather than a continuous watcher) keeps the sync at a
        deliberate interaction point: transient layout states can never snap
        the window, and the recompute self-heals a stale lock left by an
        earlier content state. No release-time restore is needed — Qt6's
        QSizeGrip may hand the drag to the OS (``startSystemResize``), which
        makes the release event unreliable, and the sync is bidirectional
        anyway."""
        window = self.window()
        if window is not None:
            SizeGripMixin.sync_window_max_to_content(window)
        super().mousePressEvent(event)

    def _update_lock_cursor(self) -> None:
        """Reflect per-direction resize locks in the hover cursor."""
        window = self.window()
        if window is None:
            return
        max_w, max_h = SizeGripMixin.content_max_size(window)
        h_locked = max_w <= window.minimumWidth()
        v_locked = max_h <= window.minimumHeight()
        if h_locked and v_locked:
            cursor = QtCore.Qt.ArrowCursor
        elif v_locked:
            cursor = QtCore.Qt.SizeHorCursor
        elif h_locked:
            cursor = QtCore.Qt.SizeVerCursor
        else:
            cursor = QtCore.Qt.SizeFDiagCursor
        self.setCursor(cursor)

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

    @staticmethod
    def content_max_size(window: QtWidgets.QWidget) -> Tuple[int, int]:
        """Return ``(max_w, max_h)`` the window's content can actually use.

        A direction is capped only when EVERY visible piece of real content is
        capped in it. Unlike ``QLayout.maximumSize()``, the recursive walk
        (:meth:`_layout_content_max`) treats two things as NOT content:
        spacers (they exist to absorb surplus, so they contribute their hint,
        never unboundedness) and default-policy container widgets (a
        ``QGroupBox`` of fixed rows caps at what its rows can use, even
        though Qt's grow-policy heuristic calls it unbounded). A genuinely
        growable leaf — Expanding policy, scroll areas, or any grow-policy
        widget without an explicit max — still unbounds its direction.
        Unbounded directions report ``QWIDGETSIZE_MAX``. Chrome between the
        window and its content container (e.g. QMainWindow toolbars) is added
        onto finite caps. Windows without a layout — or with an EMPTY one —
        report unbounded in both directions: such windows (e.g. marking-menu
        submenus) typically hold absolutely-positioned children the layout
        knows nothing about, so its tiny margins-only maximum is meaningless.
        """
        container = window
        if isinstance(window, QtWidgets.QMainWindow):
            central = window.centralWidget()
            if central is not None:
                container = central
        layout = container.layout()
        if layout is None or layout.count() == 0:
            return QWIDGETSIZE_MAX, QWIDGETSIZE_MAX
        max_w, max_h = SizeGripMixin._layout_content_max(layout)
        if max_w < QWIDGETSIZE_MAX:
            max_w = min(
                max_w + max(0, window.width() - container.width()),
                QWIDGETSIZE_MAX,
            )
        if max_h < QWIDGETSIZE_MAX:
            max_h = min(
                max_h + max(0, window.height() - container.height()),
                QWIDGETSIZE_MAX,
            )
        return max_w, max_h

    # Size-policy flags that let a widget take more than its sizeHint.
    _GROW_MASK = int(
        QtWidgets.QSizePolicy.GrowFlag
        | QtWidgets.QSizePolicy.ExpandFlag
        | QtWidgets.QSizePolicy.IgnoreFlag
    )

    @staticmethod
    def _policy_grows(policy_value) -> bool:
        """True when a QSizePolicy.Policy lets the widget exceed sizeHint.

        PySide6's ``Policy`` enum is not directly ``int()``-convertible
        (unlike the OR-combined ``PolicyFlag``); go through ``.value`` with
        an int fallback for PySide2.
        """
        raw = getattr(policy_value, "value", policy_value)
        return bool(int(raw) & SizeGripMixin._GROW_MASK)

    @staticmethod
    def _widget_content_max(widget: QtWidgets.QWidget) -> Tuple[int, int]:
        """Per-direction cap for one widget: what it can actually use.

        Mirrors Qt's ``qSmartMaxSize`` precedence (explicit max wins, then a
        non-growing size policy caps at ``sizeHint``) with one refinement: a
        grow-policy CONTAINER defers to its own layout's recursive cap
        instead of being declared unbounded outright — that's what lets a
        default-policy group box of fixed rows stay capped. Grow-policy
        leaves (no layout) remain unbounded, matching Qt semantics.
        """
        max_w, max_h = widget.maximumWidth(), widget.maximumHeight()
        policy = widget.sizePolicy()
        inner = None  # lazily computed inner-layout cap
        if max_w >= QWIDGETSIZE_MAX:
            if not SizeGripMixin._policy_grows(policy.horizontalPolicy()):
                max_w = widget.sizeHint().width()
            elif widget.layout() is not None and widget.layout().count():
                inner = SizeGripMixin._layout_content_max(widget.layout())
                max_w = inner[0]
        if max_h >= QWIDGETSIZE_MAX:
            if not SizeGripMixin._policy_grows(policy.verticalPolicy()):
                max_h = widget.sizeHint().height()
            elif widget.layout() is not None and widget.layout().count():
                if inner is None:
                    inner = SizeGripMixin._layout_content_max(widget.layout())
                max_h = inner[1]
        return max_w, max_h

    @staticmethod
    def _layout_content_max(layout: QtWidgets.QLayout) -> Tuple[int, int]:
        """Recursive ``(max_w, max_h)`` cap of a layout's real content.

        Box layouts: along the axis, item caps SUM (any unbounded item
        unbounds the total); across it, the most restrictive item wins (Qt's
        own perpendicular rule). Spacers contribute their sizeHint along the
        axis and never constrain across it. Hidden items are skipped.
        Non-box layouts (grid/form/stacked — rare in this ecosystem's .ui
        files) fall back to Qt's ``maximumSize()``.
        """
        if not isinstance(layout, QtWidgets.QBoxLayout):
            m = layout.maximumSize()
            return (
                QWIDGETSIZE_MAX if m.width() >= _QLAYOUTSIZE_MAX else m.width(),
                QWIDGETSIZE_MAX if m.height() >= _QLAYOUTSIZE_MAX else m.height(),
            )
        horiz = layout.direction() in (
            QtWidgets.QBoxLayout.LeftToRight,
            QtWidgets.QBoxLayout.RightToLeft,
        )
        along, across, visible = 0, QWIDGETSIZE_MAX, 0
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            spacer = item.spacerItem()
            if spacer is not None:
                hint = spacer.sizeHint()
                a = hint.width() if horiz else hint.height()
                b = QWIDGETSIZE_MAX  # spacers never constrain across
            elif item.layout() is not None:
                iw, ih = SizeGripMixin._layout_content_max(item.layout())
                a, b = (iw, ih) if horiz else (ih, iw)
            elif item.widget() is not None:
                if item.isEmpty():  # hidden (and not retaining size)
                    continue
                iw, ih = SizeGripMixin._widget_content_max(item.widget())
                a, b = (iw, ih) if horiz else (ih, iw)
            else:
                continue
            visible += 1
            if a >= QWIDGETSIZE_MAX or along >= QWIDGETSIZE_MAX:
                along = QWIDGETSIZE_MAX
            else:
                along = min(along + a, QWIDGETSIZE_MAX)
            across = min(across, b)
        margins = layout.contentsMargins()
        along_margin = (
            margins.left() + margins.right()
            if horiz
            else margins.top() + margins.bottom()
        )
        across_margin = (
            margins.top() + margins.bottom()
            if horiz
            else margins.left() + margins.right()
        )
        spacing = max(layout.spacing(), 0) * max(visible - 1, 0)
        if along < QWIDGETSIZE_MAX:
            along = min(along + spacing + along_margin, QWIDGETSIZE_MAX)
        if across < QWIDGETSIZE_MAX:
            across = min(across + across_margin, QWIDGETSIZE_MAX)
        return (along, across) if horiz else (across, along)

    @staticmethod
    def sync_window_max_to_content(window: QtWidgets.QWidget) -> None:
        """Sync the window's maximum size to its content's real maximum.

        Locks a direction when all visible children are fixed in it (extra
        space there is dead space by definition) and FREES it again when the
        content can grow — a bidirectional sync, not a one-way clamp, so a
        stale lock from an earlier content state heals on the next call.
        Setting a maximum below the current size also snaps off any existing
        dead space. Call at deliberate points (grip press, programmatic
        window resizes) rather than continuously, so transient layout states
        can't shrink the window behind the user's back.
        """
        max_w, max_h = SizeGripMixin.content_max_size(window)
        # Never pin the max below the min — Qt would fight the constraints.
        max_w = max(max_w, window.minimumWidth(), 1)
        max_h = max(max_h, window.minimumHeight(), 1)
        if (max_w, max_h) != (window.maximumWidth(), window.maximumHeight()):
            window.setMaximumSize(max_w, max_h)

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

    def _size_grip_default_container(self) -> Optional[QtWidgets.QWidget]:
        """Return the widget that should host the size grip by default."""
        central_widget = None
        if hasattr(self, "centralWidget") and callable(getattr(self, "centralWidget")):
            central_widget = self.centralWidget()
            if isinstance(central_widget, QtWidgets.QWidget):
                return central_widget

        return self if isinstance(self, QtWidgets.QWidget) else None
