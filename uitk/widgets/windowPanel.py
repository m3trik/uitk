# !/usr/bin/python
# coding=utf-8
"""Themed top-level uitk window: Header → body → Footer.

Base class for any chromed standalone window in the uitk ecosystem —
editors, browsers, viewers, tool palettes. Holds the layout, anchoring,
sizing, and theme-application logic that every such window shares;
subclasses add their own content to ``body_layout``.

Preset / configuration management is intentionally **not** here — see
:class:`uitk.widgets.editors.editor_panel.EditorPanel` for the
preset-enabled subclass. Keeping presets out of the base makes
``WindowPanel`` usable for read-only viewers and other non-editor
surfaces without dragging in editor-specific machinery.
"""
from typing import TYPE_CHECKING

from qtpy import QtWidgets, QtCore
from uitk.widgets.header import Header
from uitk.widgets.footer import Footer

if TYPE_CHECKING:  # pragma: no cover
    from uitk.widgets.mixins.style_sheet import StyleSheet


class WindowPanel(QtWidgets.QWidget):
    """Themed top-level window with a Header / body / Footer layout.

    Provides a consistent shell for any standalone uitk window. The
    body is empty by default — subclasses populate it via
    :attr:`body_layout`. Header config buttons, status text, and a
    size-gripped footer come standard.

    Parameters
    ----------
    title : str
        Text displayed in the header bar.
    header_buttons : list, optional
        Button names for the header (default ``["hide"]``).
    status_text : str, optional
        Default text shown in the footer status label.
    parent : QWidget, optional
        Anchor widget. The panel reparents to ``parent.window()`` so
        it survives a transient invoker hiding while remaining a real
        top-level window via ``Qt.Window``.
    on_top : bool, optional
        Apply ``WindowStaysOnTopHint``. Defaults to ``False`` so
        windows behave like normal app windows. Opt in for transient
        surfaces that must float above their host.
    """

    def __init__(
        self,
        title="",
        header_buttons=None,
        status_text="",
        parent=None,
        on_top=False,
    ):
        super().__init__(None)

        # Panels behave like normal app windows parented to the host. A
        # subclass that genuinely needs to float above its host (a
        # transient picker, a tool palette) can opt in with on_top=True.
        # Carrying this as an explicit constructor arg — rather than a
        # flag-manipulation done post-super() — keeps the choice visible
        # at every subclass's construction site.
        _panel_flags = QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint
        if on_top:
            _panel_flags |= QtCore.Qt.WindowStaysOnTopHint
        self.setWindowFlags(_panel_flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        # Anchor to a stable top-level so the panel survives a transient
        # invoker hiding (e.g. a MarkingMenu, popup, or temporary host
        # widget). We reparent to ``parent.window()`` rather than
        # ``parent`` directly so a caller passing some inner container
        # still ends up anchored to the host main window. ``Qt.Window``
        # keeps us a real top-level despite having a Qt parent —
        # same pattern MarkingMenu uses when launching standalone
        # windows. Re-pass the full flag set because
        # setParent(parent, flags) replaces window flags wholesale.
        if parent is not None:
            anchor = parent.window() or parent
            self.setParent(anchor, _panel_flags)
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        # Inner frame paints the semi-transparent background.
        self._frame = QtWidgets.QFrame(self)
        self._frame.setProperty("class", "translucentBgWithBorder")
        frame_layout = QtWidgets.QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        # Header
        self._header = Header(
            self,
            config_buttons=header_buttons if header_buttons is not None else ["hide"],
        )
        self._header.setText(title.upper())
        frame_layout.addWidget(self._header)

        # Body (main content area with margins).
        # Defaults to the dense 2 px margins / 2 px spacing used by
        # every production editor in the toolset. Subclasses that need
        # a looser layout can override via ``body_layout`` post-init.
        body = QtWidgets.QWidget()
        self._body_layout = QtWidgets.QVBoxLayout(body)
        self._body_layout.setContentsMargins(2, 2, 2, 2)
        self._body_layout.setSpacing(2)
        frame_layout.addWidget(body, 1)

        # Footer
        self._footer = Footer(self, add_size_grip=True)
        if status_text:
            self._footer.setDefaultStatusText(status_text)
        frame_layout.addWidget(self._footer)

        # Style is exposed via the ``style`` lazy property; theme is
        # applied on first ``showEvent`` so panels constructed but never
        # shown skip the QSS work entirely.
        self._size_initialized = False

    @property
    def style(self) -> "StyleSheet":
        """Lazy :class:`StyleSheet` bound to this panel.

        Constructed on first access. The default ``dark`` theme is
        applied automatically the first time the panel is shown (see
        :meth:`showEvent`); subclasses can override at any time via
        ``self.style.set(theme=..., style_class=...)``.

        Robust against accidental ``self._style = None`` reassignment —
        a missing or None-valued cache rebuilds rather than returning
        None to the caller.
        """
        style = self.__dict__.get("_style")
        if style is None:
            from uitk.widgets.mixins.style_sheet import StyleSheet

            style = StyleSheet(self)
            self._style = style
        return style

    def showEvent(self, event):
        super().showEvent(event)
        # First-show: apply the default dark theme unless someone has
        # already explicitly styled this panel. The dual-condition
        # check is deliberate:
        #   ``_default_theme_applied`` — *we* haven't already considered
        #     this panel for default theming on a prior show. Prevents
        #     re-applying dark on every show / hide cycle.
        #   ``self in StyleSheet._widget_configs`` — *anyone* (subclass,
        #     external caller) has applied any theme to this panel. The
        #     StyleSheet maintains this dict as the single source of
        #     truth for "has been themed", so checking it lets a
        #     subclass that called ``self.style.set(theme="light")`` in
        #     __init__ skip our default and keep their choice.
        if not getattr(self, "_default_theme_applied", False):
            self._default_theme_applied = True
            stylesheet_cls = type(self.style)
            if self not in stylesheet_cls._widget_configs:
                self.style.set(theme="dark")

        if not self._size_initialized:
            self._size_initialized = True
            QtCore.QTimer.singleShot(0, self._fit_to_content)

    def _fit_to_content(self):
        """Resize the window to snugly fit its primary content.

        Computes the ideal height from a contained table's row heights
        plus chrome when present, otherwise falls back to
        :meth:`adjustSize`. Caps at 85 % of the available screen height
        so a scroll bar appears naturally for very long content.

        Override in subclasses that have a different "primary content"
        metric (e.g. text-area-based windows).
        """
        table = self.findChild(QtWidgets.QTableWidget)
        if table is None or table.rowCount() == 0:
            self.adjustSize()
            return

        table_h = table.horizontalHeader().height() + 2  # border
        for r in range(table.rowCount()):
            table_h += table.rowHeight(r)

        chrome = self.height() - table.height()

        screen = self.screen()
        max_h = int(screen.availableGeometry().height() * 0.85) if screen else 800
        ideal = table_h + chrome
        self.resize(self.width(), min(ideal, max_h))

    @property
    def header(self):
        """The :class:`Header` widget at the top."""
        return self._header

    @property
    def footer(self):
        """The :class:`Footer` widget at the bottom."""
        return self._footer

    @property
    def body_layout(self):
        """``QVBoxLayout`` for panel content."""
        return self._body_layout

    def tighten_sublayouts(self, spacing: int = 1) -> None:
        """Set every nested sub-layout inside ``body_layout`` to *spacing*.

        Bodies often have a few horizontal control rows above a main
        widget. The outer ``body_layout`` spacing controls the gap
        between rows; this helper controls the spacing inside each row
        so controls in a single row pack tightly. Call once at the end
        of the subclass constructor after the rows have been added.
        """
        for i in range(self._body_layout.count()):
            sublayout = self._body_layout.itemAt(i).layout()
            if sublayout is not None:
                sublayout.setSpacing(spacing)

    @staticmethod
    def icon_button(
        icon_name: str = "",
        size: int = 24,
        tooltip: str = "",
        icon_size=None,
    ) -> QtWidgets.QPushButton:
        """Build a square, flat, icon-only button for table cells / toolbars.

        Single source of truth for "small icon button" UI elements
        across windowed tools. Use it for table action columns, header
        rows, anywhere a compact iconographic button is needed.

        Parameters
        ----------
        icon_name : str
            IconManager registry name (e.g. ``"undo"``, ``"window"``).
            When empty, the caller is expected to set the icon
            afterwards.
        size : int
            Edge length of the square button in pixels. Defaults to 24.
        tooltip : str
            Optional hover tooltip.
        icon_size : tuple[int, int] or None
            Inner icon size. Defaults to ``(size - 8, size - 8)``,
            which gives the icon ~4 px breathing room on each side.

        Returns
        -------
        QtWidgets.QPushButton
            A flat, square, no-focus, pointing-hand-cursor button. The
            caller is responsible for connecting ``clicked``.
        """
        from uitk.widgets.mixins.icon_manager import IconManager

        btn = QtWidgets.QPushButton()
        btn.setFlat(True)
        btn.setFocusPolicy(QtCore.Qt.NoFocus)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.setFixedSize(size, size)
        if tooltip:
            btn.setToolTip(tooltip)
        if icon_name:
            sz = icon_size if icon_size else (max(8, size - 8), max(8, size - 8))
            IconManager.set_icon(btn, icon_name, size=sz)
        return btn
