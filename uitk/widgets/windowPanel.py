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
    from uitk.themes.style_sheet import StyleSheet


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

        # Size / geometry state, initialized up front (before any child
        # widgets) so an early resize/move event during construction finds
        # these attributes already present. ``_geometry_settings`` stays None
        # until a subclass opts into persistence via :meth:`persist_geometry`
        # — then the window's size and position are saved (debounced) on
        # resize / move / hide / close and restored on first show, so a
        # user-adjusted size survives across sessions. WindowPanel is a plain
        # QWidget (unlike MainWindow, which bakes this in), so its editors
        # previously always reopened at the constructor default; this brings
        # the same behaviour here without coupling the base to a Switchboard
        # (the settings store is injected).
        self._size_initialized = False
        self._restoring = False
        self._geometry_settings = None
        self._geometry_key = "window_geometry"
        self._geometry_save_timer = QtCore.QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(500)
        self._geometry_save_timer.timeout.connect(self.save_window_geometry)

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
        # shown skip the QSS work entirely (see ``_size_initialized`` above,
        # which also gates the first-show geometry restore / content fit).

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
            from uitk.themes.style_sheet import StyleSheet

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
            # A saved user size is authoritative: restore it and skip the
            # content-fit. Re-fitting a hand-resized window to content is
            # exactly what discarded the adjusted size every session. Only fit
            # when there's nothing to restore — a first-ever show, or a panel
            # that never opted into persistence.
            # Guard the debounced save: restoreGeometry() emits resize/move
            # events that would otherwise re-schedule a save of the just-restored
            # size (a redundant write; mirrors MainWindow's restore guard).
            self._restoring = True
            try:
                restored = self.restore_window_geometry()
            finally:
                self._restoring = False
            if not restored:
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

    # ── Geometry persistence (opt-in) ────────────────────────────

    def persist_geometry(self, settings, key: str = "window_geometry") -> None:
        """Enable saving / restoring this window's geometry via *settings*.

        Lets the window's size and position survive across sessions. Call once
        from a subclass constructor **before** the first show, so a
        previously-saved size is restored on that show.

        Parameters
        ----------
        settings : SettingsManager
            Store geometry is written to / read from — typically an editor's
            own ``sb.settings.branch(...)``. Passing ``None`` leaves
            persistence disabled (the default), so the window fits to content
            as before.
        key : str
            Settings key holding the serialized geometry (a raw QByteArray).
            Distinct keys let sibling launch-variants that share one settings
            branch each remember their own size (e.g. the full vs. focused
            shortcut editor).
        """
        self._geometry_settings = settings
        self._geometry_key = key

    def save_window_geometry(self) -> None:
        """Persist the current size + position, when persistence is enabled.

        No-op before the first show (nothing meaningful to save yet), for a
        degenerate size (e.g. mid-reparent), or while the header has minimized
        the window — so a transient / rolled-up geometry never overwrites the
        user's real one.
        """
        if self._geometry_settings is None or not self._size_initialized:
            return
        if self.width() <= 0 or self.height() <= 0:
            return
        if self.property("_header_minimized"):
            return
        self._geometry_settings.setByteArray(self._geometry_key, self.saveGeometry())

    def restore_window_geometry(self) -> bool:
        """Restore a previously-saved geometry.

        Returns
        -------
        bool
            True when a valid saved geometry was applied — the restored size
            is then the user's own and authoritative, so the caller must not
            re-fit it to content. False when there was nothing usable to
            restore (persistence off, no saved data, or a failed / degenerate
            restore); the window is then free to fit to content.
        """
        if self._geometry_settings is None:
            return False
        geometry = self._geometry_settings.getByteArray(self._geometry_key)
        if not geometry or not isinstance(geometry, QtCore.QByteArray):
            return False
        try:
            if not self.restoreGeometry(geometry):
                return False
        except Exception:  # noqa: BLE001 — corrupt/foreign blob; fall back to fit
            return False
        # Reject a restore that produced a degenerate size.
        if self.width() <= 0 or self.height() <= 0:
            return False
        return True

    def clear_saved_geometry(self) -> None:
        """Forget any saved geometry (no-op when persistence is disabled)."""
        if self._geometry_settings is not None:
            self._geometry_settings.clear(self._geometry_key)

    def _schedule_geometry_save(self) -> None:
        """(Re)start the debounced geometry save — no-op until persistence is
        enabled and the window has had its first show, or while restoring (the
        restore's own resize/move must not re-save)."""
        if (
            self._geometry_settings is not None
            and self._size_initialized
            and not self._restoring
        ):
            self._geometry_save_timer.start()

    def resizeEvent(self, event):
        """Debounce-save geometry on resize once persistence is enabled."""
        super().resizeEvent(event)
        self._schedule_geometry_save()

    def moveEvent(self, event):
        """Debounce-save geometry on move once persistence is enabled."""
        super().moveEvent(event)
        self._schedule_geometry_save()

    def hideEvent(self, event):
        """Persist geometry on hide — the editors' normal 'close' path."""
        self.save_window_geometry()
        super().hideEvent(event)

    def closeEvent(self, event):
        """Persist geometry on close."""
        self.save_window_geometry()
        super().closeEvent(event)

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
        from uitk.managers.icon_manager import IconManager

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
