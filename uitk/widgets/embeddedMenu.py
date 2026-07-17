# !/usr/bin/python
# coding=utf-8
"""Host a live ``QMenu`` as ordinary widget content (non-popup), sized exactly to it.

Home of the menu-wrapping pattern the DCC layers use to present a native application
menu inside a Switchboard ``MainWindow`` (header, pin, hide-on-release behavior):
mayatk re-hosts Maya's real menu-bar ``QMenu``s here; blendertk fills a fresh
``QMenu`` from a harvested Blender menu. Moved from ``mayatk.ui_utils
.maya_native_menus`` — the classes are pure Qt and were Maya-flavored only by
location.
"""
from qtpy import QtWidgets, QtCore


class PersistentMenu(QtWidgets.QMenu):
    """A QMenu that ignores attempts to hide it (e.g. from interaction), suitable for embedding."""

    def setVisible(self, visible):
        if not visible:
            return
        super().setVisible(visible)


class EmbeddedMenuWidget(QtWidgets.QWidget):
    """Embeds a QMenu into a sizeable widget that fits content exactly.

    Menus have fixed-height action rows, so the wrapper is rigid-fit to content
    (no resize handle, no dead space).
    """

    # Per-row pixel estimate for action / separator rows when QMenu's own
    # geometry is unavailable (e.g. before first show, in offscreen tests).
    _ACTION_ROW_PX = 26
    _SEPARATOR_PX = 8
    _MIN_WIDTH = 200
    _EMPTY_HEIGHT_FLOOR = 100

    def __init__(self, menu, parent=None):
        super().__init__(parent)
        self.menu = menu
        self.init_ui()

    def init_ui(self):
        # Layout exists so uitk's header attach_to() can insert at index 0.
        # The QMenu is positioned manually (not added to layout) because
        # QMenu-in-layout misbehaves with item painting and popup logic.
        # 2 px contents margin so the parent QSS border (translucentBgWithBorder)
        # is visible around layout-managed children — without it the header
        # sits flush against the painted border.
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.menu.setParent(self)
        self.menu.setWindowFlags(QtCore.Qt.Widget | QtCore.Qt.FramelessWindowHint)
        self.menu.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Expanding
        )

        # Stretch keeps any later header pinned to the top while the manually
        # positioned QMenu fills the remaining height.
        layout.addStretch(1)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred
        )

        self.menu.show()
        self.menu.setTearOffEnabled(False)

        # Required for the parent QSS class (translucentBgWithBorder) to
        # actually paint background/border on this plain QWidget — without
        # this the rule is matched but no painting happens.
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.menu.setAttribute(QtCore.Qt.WA_StyledBackground, True)

    def _reserved_top(self):
        """Height of layout widgets above the menu (e.g. attached header)."""
        layout = self.layout()
        if not layout:
            return 0
        total = 0
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w and w is not self.menu:
                hint = w.sizeHint()
                if hint.isValid() and hint.height() > 0:
                    total += hint.height()
                elif w.height() > 0:
                    total += w.height()
        return total

    def _menu_content_height(self):
        """Sum of action geometries; falls back to per-row estimate."""
        actions = self.menu.actions()
        if not actions:
            return 0

        self.menu.ensurePolished()
        total = 0
        for action in actions:
            if not action.isVisible():
                continue
            rect = self.menu.actionGeometry(action)
            if rect.isValid() and rect.height() > 0:
                total += rect.height()
            else:
                total += (
                    self._SEPARATOR_PX
                    if action.isSeparator()
                    else self._ACTION_ROW_PX
                )
        margins = self.menu.contentsMargins()
        total += margins.top() + margins.bottom()
        return total

    def content_size(self):
        """Exact size needed for header + populated menu, no dead space."""
        self.menu.ensurePolished()

        menu_hint = self.menu.sizeHint()
        width = max(self._MIN_WIDTH, menu_hint.width() if menu_hint.isValid() else 0)

        height = self._menu_content_height()
        height += self._reserved_top()

        layout = self.layout()
        if layout:
            lm = layout.contentsMargins()
            width += lm.left() + lm.right()
            height += lm.top() + lm.bottom()

        # Floor when menu is empty so the wrapper is still visible during
        # the (now rare) window-shown-before-populate race.
        return QtCore.QSize(width, max(height, self._EMPTY_HEIGHT_FLOOR))

    def sizeHint(self):
        return self.content_size()

    def minimumSizeHint(self):
        return self.content_size()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.menu:
            return
        layout = self.layout()
        if layout:
            lm = layout.contentsMargins()
            left, top, right, bottom = lm.left(), lm.top(), lm.right(), lm.bottom()
        else:
            left = top = right = bottom = 0
        reserved_top = self._reserved_top() + top
        menu_x = left
        menu_w = max(0, self.width() - left - right)
        menu_y = reserved_top
        menu_h = max(0, self.height() - reserved_top - bottom)
        self.menu.setGeometry(menu_x, menu_y, menu_w, menu_h)
        self.menu.setMinimumWidth(menu_w)
        self.menu.lower()
        self._raise_layout_widgets()

    def _raise_layout_widgets(self):
        layout = self.layout()
        if not layout:
            return
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w and w is not self.menu:
                w.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        if self.menu:
            self.menu.lower()
            self._raise_layout_widgets()

    def fit_to_window(self):
        """Resize and lock the parent window to exact content size."""
        self.updateGeometry()
        window = self.window()
        if not window or window is self:
            return

        if window.layout():
            window.layout().activate()

        target = self.content_size()

        # Account for window chrome (header/footer added by MainWindow).
        # adjustSize would compute this for us, but we want a precise lock —
        # so derive chrome by comparing existing window size against this
        # widget's current size, then add it to the target.
        cw = window.centralWidget() if hasattr(window, "centralWidget") else None
        if cw is self and window.size().isValid() and self.size().isValid():
            chrome_w = max(0, window.width() - self.width())
            chrome_h = max(0, window.height() - self.height())
            target = QtCore.QSize(target.width() + chrome_w, target.height() + chrome_h)

        window.setMinimumSize(target)
        window.setMaximumSize(target)
        window.resize(target)
