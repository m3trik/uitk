# !/usr/bin/python
# coding=utf-8
"""Themed top-level uitk window: Header → body → Footer.

Base class for any chromed standalone window in the uitk ecosystem —
editors, browsers, viewers, tool palettes. Holds the layout, anchoring,
sizing, and theme-application logic that every such window shares;
subclasses add their own content to ``body_layout``.

Content is built the way a :class:`~uitk.widgets.menu.Menu` is built —
:meth:`add` takes a widget-class name, an instance or a class, applies
setter-style kwargs (``setText=``, ``setObjectName=``, a signal name to
connect), places it as a form row and exposes it as ``panel.<objectName>``.
One idiom for a popup and for a window; only the lifecycle differs. The form
itself is a :class:`~uitk.widgets.form_rows.FormRows`, which any layout can
hold on its own (a page of a stacked panel). The
popup machinery a Menu carries (hide-on-trigger, grab handoffs, deferred
registration) is exactly what a persistent window must not inherit, so the
two share the vocabulary and not the implementation.

Preset / configuration management is intentionally **not** here — see
:class:`uitk.widgets.editors.editor_panel.EditorPanel` for the
preset-enabled subclass. Keeping presets out of the base makes
``WindowPanel`` usable for read-only viewers and other non-editor
surfaces without dragging in editor-specific machinery.
"""

import logging
from typing import TYPE_CHECKING, Dict, Optional, Union

from qtpy import QtWidgets, QtCore
from uitk._bootstrap import Bootstrap
from uitk.widgets.header import Header
from uitk.widgets.footer import Footer
from uitk.widgets.form_rows import FormRows
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

if TYPE_CHECKING:  # pragma: no cover
    from uitk.themes.style_sheet import StyleSheet

_logger = logging.getLogger(__name__)


class WindowPanel(QtWidgets.QWidget, AttributesMixin):
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

    # Not a Designer widget-box entry: a top-level window shell; forms are authored
    # as their own MainWindow.
    designer_spec = {"visible": False}

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
        # Kept on the instance: ``setWindowModality`` silently RESETS
        # ``windowFlags`` to the widget-type defaults, so a subclass that goes
        # modal has to re-apply exactly this set afterwards (FormPanel does) --
        # and re-deriving it there would be a second place to keep in step.
        self._panel_flags = _panel_flags
        self.setWindowFlags(_panel_flags)
        Bootstrap.set_translucent(self)

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
            Bootstrap.set_translucent(self)

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

        # The form region — where :meth:`add` puts things: a FormRows (a
        # labelled row's caption sits to the LEFT of its control, every
        # caption in one column). Created eagerly and placed FIRST in the body
        # so its position is deterministic whatever a subclass appends after
        # it (an output pane, a table) and however late the first ``add``
        # arrives; empty, it has no height. Growable content (a table, a log
        # pane) belongs on ``body_layout`` directly, with a stretch.
        self._rows_host = FormRows(body)
        self._body_layout.addWidget(self._rows_host)
        #: objectNames :meth:`add` exposed on the WINDOW — un-exposed by
        #: :meth:`clear_rows`, so a rebuilt panel holds no dead wrappers.
        self._exposed_names = set()

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

        # Re-measured HERE as well as at add time: the theme lands on first
        # show, and a caption measured before it is missing the plate's
        # padding -- captions floored to that hint would stop just short of
        # the column they are meant to fill.
        self._sync_caption_widths()

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

    def present(self, raise_window: bool = True) -> "WindowPanel":
        """Show this window, raise + activate it, and return it.

        The one way a uitk window is brought up, because a plain ``show()``
        loses to the popup case below and every caller would otherwise
        re-derive it (three did: ``sb.editors.show``, ``ShortcutManager``, and
        the DCC macro managers — only the first got it right).

        Popup-context recovery
        ----------------------
        When this runs from inside a ``QMenu`` action slot (the user clicked a
        menu item which fired our slot), the menu's ``hideEvent`` runs *after*
        the slot returns and explicitly ``raise_()`` / ``activateWindow()``-s
        the previously-active window — burying the window just shown. So when
        an active popup is present, a re-raise is scheduled on the next
        event-loop tick, once the menu has finished closing. The synchronous
        show + raise still happens first, so callers and tests see the window
        become visible immediately.

        Parameters:
            raise_window: When False, show without raising / activating (for a
                caller that is only un-hiding a window, not bringing it forward).

        Returns:
            ``self`` — so a caller can cache what it just presented.
        """
        self.show()
        if raise_window:
            self.raise_()
            self.activateWindow()
            if self.is_in_popup_context():
                QtCore.QTimer.singleShot(
                    0, lambda: (self.raise_(), self.activateWindow())
                )
        return self

    def is_in_popup_context(self) -> bool:
        """True when an active popup will steal focus back from this window.

        True iff there is currently an active popup widget that is not this
        window — meaning the popup's own hide flow will run after the caller
        returns and re-raise its previously-active window, so this window needs
        the deferred re-raise :meth:`present` schedules.
        """
        active_popup = QtWidgets.QApplication.activePopupWidget()
        return active_popup is not None and active_popup is not self

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

    @property
    def rows_layout(self) -> QtWidgets.QFormLayout:
        """The ``QFormLayout`` :meth:`add` places rows in."""
        return self._rows_host.rows_layout

    @property
    def form(self) -> FormRows:
        """The :class:`FormRows` holding the panel's rows."""
        return self._rows_host

    # The form's internals, as the subclasses keeping rows in step read them
    # (FormPanel's ``enabled_by`` reads the companions; its custom rows the
    # layout).
    @property
    def _rows_layout(self) -> QtWidgets.QFormLayout:
        return self._rows_host.rows_layout

    @property
    def _row_widgets(self) -> Dict[QtWidgets.QWidget, list]:
        return self._rows_host._row_widgets

    # ── Dynamic build — the Menu idiom ──────────────────────────────

    def add(
        self,
        x: Union[str, QtWidgets.QWidget, type, list, tuple],
        label: Optional[str] = None,
        hint: Optional[str] = None,
        tooltip: Optional[str] = None,
        companions=(),
        label_align=None,
        **kwargs,
    ) -> Union[QtWidgets.QWidget, list]:
        """Add a widget to the body the way ``Menu.add`` adds an item.

        :meth:`FormRows.add` on the panel's form (every parameter is its), the
        widget then exposed on the WINDOW as well -- ``panel.<objectName>`` --
        under the window's ownership rule (:meth:`_expose_as_attribute`).

        Example::

            panel = WindowPanel(title="My Tool")
            panel.add("CheckBox", setObjectName="chk_dry", setText="Dry run")
            panel.add("LineEdit", label="Search in", hint="Searched recursively.",
                      setObjectName="txt_src")
            panel.chk_dry.isChecked()
        """
        added = self._rows_host.add(
            x,
            label=label,
            hint=hint,
            tooltip=tooltip,
            companions=companions,
            label_align=label_align,
            **kwargs,
        )
        for widget in added if isinstance(added, list) else [added]:
            if isinstance(widget, QtWidgets.QWidget):
                self._expose_as_attribute(widget)
        return added

    _row_tooltip = staticmethod(FormRows._row_tooltip)

    def _build_widget(self, x) -> QtWidgets.QWidget:
        """Turn an :meth:`add` argument into a widget instance."""
        return FormRows._build_widget(x)

    def _sync_caption_widths(self) -> None:
        """Floor every caption at the widest (:meth:`FormRows._sync_caption_widths`)."""
        self._rows_host._sync_caption_widths()

    def _expose_as_attribute(self, widget: QtWidgets.QWidget) -> None:
        """Expose a widget as ``self.<objectName>`` — Menu's rule, tightened.

        Never clobbers the window's own API. Menu refuses a name whose
        current value is not a widget; a window also has read-only
        PROPERTIES that return widgets (``header``, ``footer``), which that
        test lets through and ``setattr`` then rejects. So the rule here is
        by ownership: anything the CLASS defines is off limits, and only an
        instance attribute that is itself an exposed widget (a rebuilt row)
        may be replaced.
        """
        name = widget.objectName()
        if not name:
            return
        existing = self.__dict__.get(name)
        if hasattr(type(self), name) or not (
            existing is None or isinstance(existing, QtWidgets.QWidget)
        ):
            _logger.warning(
                "WindowPanel.add: objectName %r collides with an existing "
                "attribute of %s; skipping attribute exposure.",
                name,
                type(self).__name__,
            )
            return
        setattr(self, name, widget)
        self._exposed_names.add(name)

    def clear_rows(self) -> None:
        """Drop every row :meth:`add` placed, and the attributes exposing them.

        The exposed names go too: the widgets are ``deleteLater``'d, and an
        attribute still pointing at one would hand back a dead C++ wrapper.
        """
        for name in self._exposed_names:
            self.__dict__.pop(name, None)
        self._exposed_names.clear()
        self._rows_host.clear_rows()

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
        TooltipPresenter.manage(btn)
        if icon_name:
            sz = icon_size if icon_size else (max(8, size - 8), max(8, size - 8))
            IconManager.set_icon(btn, icon_name, size=sz)
        return btn
