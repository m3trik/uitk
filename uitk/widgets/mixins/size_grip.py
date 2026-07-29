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
    both directions are free, horizontal/vertical when one is locked. When a
    window can't resize in EITHER direction, the sync hides the grip outright
    (:meth:`SizeGripMixin._sync_grip_visibility`) and re-shows it when a
    direction frees."""

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
        (:meth:`_layout_content_max`) sees through default-policy container
        widgets: a ``QGroupBox`` of fixed rows caps at what its rows can use,
        even though Qt's grow-policy heuristic calls it unbounded. A genuinely
        growable leaf — Expanding policy, scroll areas, or any grow-policy
        widget without an explicit max — unbounds its direction, and so does
        a grow-policy spacer: a designer's Expanding spacer is an explicit
        "surplus goes here", so the direction stays resizable (nearly every
        panel .ui in this ecosystem is fixed rows + a trailing Expanding
        spacer — treating those spacers as non-content locked resize across
        the board). Only Fixed spacers contribute a mere hint, which is what
        keeps a collapsed-group window with no absorber (the scene-exporter
        dead-band case) lockable.
        Unbounded directions report ``QWIDGETSIZE_MAX``. Chrome between the
        window and its content container (e.g. QMainWindow toolbars) is added
        onto finite caps — measured from size HINTS, never from live
        geometry: mid-restore the window already has its restored size while
        the central widget's geometry lags one layout pass behind, and that
        transient lag read as permanent chrome, inflating the cap by exactly
        the stale oversize it exists to expose. Windows without a layout —
        or with an EMPTY one — report unbounded in both directions: such
        windows (e.g. marking-menu submenus) typically hold absolutely-
        positioned children the layout knows nothing about, so its tiny
        margins-only maximum is meaningless.
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
        chrome_w = chrome_h = 0
        if container is not window:
            window_hint = window.minimumSizeHint()
            container_hint = container.minimumSizeHint()
            if window_hint.isValid() and container_hint.isValid():
                chrome_w = max(0, window_hint.width() - container_hint.width())
                chrome_h = max(0, window_hint.height() - container_hint.height())
        if max_w < QWIDGETSIZE_MAX:
            max_w = min(max_w + chrome_w, QWIDGETSIZE_MAX)
        if max_h < QWIDGETSIZE_MAX:
            max_h = min(max_h + chrome_h, QWIDGETSIZE_MAX)
        return max_w, max_h

    @staticmethod
    def content_min_height(window: QtWidgets.QWidget) -> int:
        """Return the true minimum height the window's content needs.

        The floor counterpart of :meth:`content_max_size`, and it resolves the
        content container the same way (a ``QMainWindow``'s central widget,
        else the window itself).

        ``window.minimumSizeHint().height()`` alone is an unreliable floor for
        a resize. Qt's ``qSmartMinSize`` REPLACES a child's layout-computed
        minimum with any explicit ``setMinimumSize`` value — even when that
        value is SMALLER than the content requires. A container carrying such
        an under-reporting minimum (e.g. a stale ``minimumSize`` baked into a
        ``.ui``) drags the window's ``minimumSizeHint`` below the real content
        size; a subsequent ``resize()`` to that value then packs fixed-height
        children into too little space and they overlap.

        The container's own ``minimumSizeHint()`` reflects its layout's real
        minimum (it is not subject to the explicit-min override), so the max of
        the two is a floor that always covers the content while still allowing
        dead space above a footer / spacer to be trimmed.
        """
        floor = window.minimumSizeHint().height()
        container = window
        if isinstance(window, QtWidgets.QMainWindow):
            central = window.centralWidget()
            if central is not None:
                container = central
        if container is not window:
            floor = max(floor, container.minimumSizeHint().height())
        return floor

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
        own perpendicular rule). A grow-policy spacer (Expanding /
        MinimumExpanding / Minimum) unbounds the axis — it is the layout's
        designated surplus absorber; a Fixed spacer contributes its sizeHint.
        Spacers never constrain across the axis. Hidden items are skipped.
        Spacing mirrors Qt's own rule — a gap counts only where the
        PRECEDING item is non-empty, so gaps next to hidden widgets and
        spacers are suppressed exactly as ``QBoxLayout`` suppresses them.
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
        along, across, gaps = 0, QWIDGETSIZE_MAX, 0
        # Qt adds a gap BEFORE an item only when the item before it is
        # non-empty (qboxlayout's setupGeom). Hidden widgets and spacers
        # both report isEmpty(), so their adjacent spacing is suppressed —
        # a flat (visible - 1) * spacing over-counts every such gap, and the
        # surplus becomes dead space the window can be stretched into.
        prev_empty = True  # nothing precedes the first item
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            item_empty = item.isEmpty()
            spacer = item.spacerItem()
            if spacer is not None:
                sp = spacer.sizePolicy()
                along_policy = sp.horizontalPolicy() if horiz else sp.verticalPolicy()
                if SizeGripMixin._policy_grows(along_policy):
                    a = QWIDGETSIZE_MAX
                else:
                    hint = spacer.sizeHint()
                    a = hint.width() if horiz else hint.height()
                b = QWIDGETSIZE_MAX  # spacers never constrain across
            elif item.layout() is not None:
                iw, ih = SizeGripMixin._layout_content_max(item.layout())
                a, b = (iw, ih) if horiz else (ih, iw)
            elif item.widget() is not None:
                if item_empty:  # hidden (and not retaining size)
                    prev_empty = True
                    continue
                iw, ih = SizeGripMixin._widget_content_max(item.widget())
                a, b = (iw, ih) if horiz else (ih, iw)
            else:
                prev_empty = item_empty
                continue
            if not prev_empty:
                gaps += 1
            prev_empty = item_empty
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
        spacing = max(layout.spacing(), 0) * gaps
        if along < QWIDGETSIZE_MAX:
            along = min(along + spacing + along_margin, QWIDGETSIZE_MAX)
        if across < QWIDGETSIZE_MAX:
            across = min(across + across_margin, QWIDGETSIZE_MAX)
        return (along, across) if horiz else (across, along)

    #: Dynamic property a rigid-lock owner (``EmbeddedMenu.fit_to_window``)
    #: stamps on its window: the sync must never free an explicit size lock.
    #: A property rather than a min==max inference, because the sync itself
    #: can legitimately pin max down to min (fully-fixed content) — inferring
    #: intent from that state would freeze the bidirectional heal.
    FIXED_LOCK_PROP = "size_grip_fixed_lock"

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

        A window stamped with :attr:`FIXED_LOCK_PROP` (a deliberate rigid
        lock — e.g. a native-menu wrapper's ``fit_to_window``) is left alone:
        freeing its max would undo an explicit size contract the content
        hints know nothing about. Its grip visibility is still refreshed —
        a rigid lock is exactly the state whose grip must hide.

        Every sync also refreshes the window's grip visibility
        (:meth:`_sync_grip_visibility`), so a grip never lingers on a window
        that can't resize and comes back the moment a direction frees.
        """
        if window.property(SizeGripMixin.FIXED_LOCK_PROP):
            SizeGripMixin._sync_grip_visibility(window)
            return
        max_w, max_h = SizeGripMixin.content_max_size(window)
        # Never pin the max below the min — Qt would fight the constraints.
        max_w = max(max_w, window.minimumWidth(), 1)
        max_h = max(max_h, window.minimumHeight(), 1)
        if (max_w, max_h) != (window.maximumWidth(), window.maximumHeight()):
            window.setMaximumSize(max_w, max_h)
        if window.width() > max_w or window.height() > max_h:
            # The size can exceed an ALREADY-correct max: Qt's layout-min
            # tracking may transiently push min above max (min wins on
            # resize), and when the content later re-caps to the same value
            # the setMaximumSize guard above skips — with it, the implicit
            # clamp that snaps off dead space. Snap explicitly instead of
            # relying on the side effect.
            window.resize(min(window.width(), max_w), min(window.height(), max_h))
        SizeGripMixin._sync_grip_visibility(window)

    @staticmethod
    def _sync_grip_visibility(window: QtWidgets.QWidget) -> None:
        """Auto hide/show the window's size grip to match its resizability.

        A grip on a window whose min == max in BOTH directions is a dead
        affordance — hide it; re-show it the moment a direction frees (the
        same bidirectional contract as the max sync). A single-direction
        lock keeps the grip: the hover cursor already tells the user which
        axis remains (:meth:`CornerSizeGrip._update_lock_cursor`). Reads the
        window's actual constraints rather than re-walking the content, so
        it also covers locks the sync didn't produce (an explicit
        ``setFixedSize``, a native .ui max). Guarded by ``isHidden`` so the
        untouched case never churns Qt's visibility machinery.
        """
        resizable = (
            window.maximumWidth() > window.minimumWidth()
            or window.maximumHeight() > window.minimumHeight()
        )
        for grip in window.findChildren(
            QtWidgets.QSizeGrip, SizeGripMixin.size_grip_object_name
        ):
            # findChildren is descendant-wide: skip grips that belong to a
            # hosted child that is its own window (e.g. a popup Menu's
            # footer grip) — their visibility tracks THAT window's sync.
            if grip.window() is not window:
                continue
            if grip.isHidden() != (not resizable):
                grip.setHidden(not resizable)

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
