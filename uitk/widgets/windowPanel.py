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
One idiom for a popup and for a window; only the lifecycle differs. The
popup machinery a Menu carries (hide-on-trigger, grab handoffs, deferred
registration) is exactly what a persistent window must not inherit, so the
two share the vocabulary and not the implementation.

Preset / configuration management is intentionally **not** here — see
:class:`uitk.widgets.editors.editor_panel.EditorPanel` for the
preset-enabled subclass. Keeping presets out of the base makes
``WindowPanel`` usable for read-only viewers and other non-editor
surfaces without dragging in editor-specific machinery.
"""

import inspect
import logging
from typing import TYPE_CHECKING, Dict, Optional, Union

from qtpy import QtWidgets, QtCore
from uitk.widgets.header import Header
from uitk.widgets.footer import Footer
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.tooltip_mixin import TooltipFormat

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

        # The form region — where :meth:`add` puts things. A QFormLayout, so
        # a labelled row's caption sits to the LEFT of its control and every
        # caption shares one column (the fields line up under each other).
        # Created eagerly and placed FIRST in the body so its position is
        # deterministic whatever a subclass appends after it (an output
        # pane, a table) and however late the first ``add`` arrives; empty,
        # it has no height. Growable content (a table, a log pane) belongs on
        # ``body_layout`` directly, with a stretch — a form row is compact.
        self._rows_host = QtWidgets.QWidget(body)
        self._rows_layout = QtWidgets.QFormLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setHorizontalSpacing(4)
        self._rows_layout.setVerticalSpacing(2)
        self._rows_layout.setLabelAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        self._rows_layout.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self._rows_layout.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.AllNonFixedFieldsGrow
        )
        self._rows_layout.setRowWrapPolicy(QtWidgets.QFormLayout.DontWrapRows)
        self._body_layout.addWidget(self._rows_host)
        #: widget -> the widgets that grey out WITH it: its caption, then any
        #: companions sharing its cell. What a subclass keeping rows in step
        #: (FormPanel's ``enabled_by``) reads.
        self._row_widgets: Dict[QtWidgets.QWidget, list] = {}
        #: Every row caption, in add order -- the label column, which is
        #: sized as one (see :meth:`_sync_caption_widths`).
        self._captions: list = []
        #: objectNames :meth:`add` exposed as attributes — un-exposed by
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
        return self._rows_layout

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

        Parameters:
            x: What to add — a widget-class NAME (resolved through the uitk
                root registry first, so ``"CheckBox"`` is uitk's and
                ``"Separator"`` works, then ``QtWidgets``), a widget instance,
                a widget class, or a list/tuple of any of those. A string
                that names no widget class becomes a caption label carrying
                that text — ``add("Output:")`` — the same affordance a Menu
                has (and the same trap: a typo'd class name is a label, so
                the fallthrough is logged at DEBUG).
            label: Caption placed to the LEFT of the control, in the shared
                label column. Without one the widget spans the row.
            hint: What this row will DO. Rendered as a formatted tooltip on
                the caption, the widget and its companions alike, titled
                with the label — so hovering a form row reads like hovering
                any other control in the toolset.
            tooltip: Pre-formatted rich text used verbatim instead of the
                ``label``/``hint`` composition.
            companions: Widgets that share the field cell (a Browse button
                beside a path field) and grey out with it.
            label_align: Where the caption's TEXT sits inside the column its
                plate fills — ``"left"`` (default), ``"right"``, ``"center"``,
                or a Qt alignment. Right for a caption that reads as a
                lead-in to the control beside it (``"Operation:"``); left
                where the text itself lines up down the column (a leading
                marker, an icon).
            **kwargs: Applied through :meth:`AttributesMixin.set_attributes`
                — setter-style (``setText=``, ``setObjectName=``,
                ``setEnabled=``) and any signal name to connect
                (``clicked=self.on_click``) — exactly a Menu item's kwargs.

        Returns:
            The widget (a list of them for a list/tuple), exposed as
            ``self.<objectName>`` when it has one and the name does not
            collide with a real attribute of the window.

        Example::

            panel = WindowPanel(title="My Tool")
            panel.add("CheckBox", setObjectName="chk_dry", setText="Dry run")
            panel.add("LineEdit", label="Search in", hint="Searched recursively.",
                      setObjectName="txt_src")
            panel.chk_dry.isChecked()
        """
        if isinstance(x, (list, tuple)):
            return [
                self.add(
                    item,
                    label=label,
                    hint=hint,
                    tooltip=tooltip,
                    companions=companions,
                    label_align=label_align,
                    **kwargs,
                )
                for item in x
            ]
        widget = self._build_widget(x)
        self.set_attributes(widget, **kwargs)
        self._add_row(
            widget,
            label=label,
            hint=hint,
            tooltip=tooltip,
            companions=companions,
            label_align=label_align,
        )
        self._expose_as_attribute(widget)
        return widget

    @staticmethod
    def _resolve_widget_class(name: str):
        """The widget class *name* denotes, or None.

        The uitk root registry (``DEFAULT_INCLUDE``) is the single source of
        truth for widget names, so it is asked first — no second table of
        names is born here — and ``QtWidgets`` second. That registry also
        resolves NON-widgets (managers, mixins), so a hit is type-checked
        before anything is instantiated.
        """
        import uitk

        for source in (uitk, QtWidgets):
            try:
                candidate = getattr(source, name)
            except AttributeError:
                continue
            if inspect.isclass(candidate) and issubclass(candidate, QtWidgets.QWidget):
                return candidate
        return None

    def _build_widget(self, x) -> QtWidgets.QWidget:
        """Turn an :meth:`add` argument into a widget instance."""
        if isinstance(x, QtWidgets.QWidget):
            return x
        if inspect.isclass(x) and issubclass(x, QtWidgets.QWidget):
            return x()
        if isinstance(x, str):
            cls = self._resolve_widget_class(x)
            if cls is not None:
                return cls()
            if x.isidentifier() and x[:1].isupper():
                _logger.debug(
                    "WindowPanel.add: %r names no widget class; added as a caption.",
                    x,
                )
            caption = QtWidgets.QLabel(x)
            caption.setProperty("caption", True)
            return caption
        raise TypeError(
            "add() expects a widget-class name, a QWidget instance or class, "
            f"or a list/tuple of those; got {type(x).__name__}"
        )

    @staticmethod
    def _row_tooltip(title, hint, tooltip) -> str:
        """A row's tooltip: the explicit one, else the title + hint composed.

        Composed rather than concatenated so a hint reads as the answer to
        the caption beside it — the title/body shape every other tooltip in
        the toolset uses. A row with no caption (a checkbox, whose label is
        its own text) gets the body alone.
        """
        if tooltip:
            return str(tooltip)
        if not hint:
            return ""
        return TooltipFormat.fmt(title=str(title) if title else None, body=str(hint))

    #: ``label_align`` spellings — the caption's TEXT inside the plate that
    #: fills the label column (see :meth:`_sync_caption_widths`). Vertical
    #: centering is never optional: a caption is height-matched to the
    #: control it names.
    _LABEL_ALIGNMENTS = {
        "left": QtCore.Qt.AlignLeft,
        "right": QtCore.Qt.AlignRight,
        "center": QtCore.Qt.AlignHCenter,
    }

    @classmethod
    def _label_alignment(cls, align):
        """*align* as a Qt alignment — a name, a flag, or None for the default."""
        if align is None:
            return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        if isinstance(align, str):
            try:
                flag = cls._LABEL_ALIGNMENTS[align.lower()]
            except KeyError:
                raise ValueError(
                    f"label_align must be one of {sorted(cls._LABEL_ALIGNMENTS)} "
                    f"or a Qt alignment; got {align!r}"
                ) from None
        else:
            flag = align
        return flag | QtCore.Qt.AlignVCenter

    def _add_row(
        self,
        widget,
        label=None,
        hint=None,
        tooltip=None,
        companions=(),
        label_align=None,
    ) -> Optional[QtWidgets.QLabel]:
        """Place *widget* as a form row; returns its caption label, if any.

        The caption carries the theme's ``caption`` hook — a label that
        NAMES the control beside it rather than being a field of its own,
        so it drops the base QLabel's border but keeps its opaque plate (a
        panel body is translucent; a transparent caption would read against
        the viewport behind the window) — and mirrors the control's enabled
        state at add time so a settled row greys out whole.
        """
        companions = list(companions)
        tip = self._row_tooltip(label, hint, tooltip)

        caption = None
        if label:
            caption = QtWidgets.QLabel(str(label))
            caption.setProperty("caption", True)
            caption.setAlignment(self._label_alignment(label_align))
            font = caption.font()
            font.setBold(True)
            caption.setFont(font)
            caption.setEnabled(widget.isEnabled())

        for companion in companions:
            companion.setEnabled(widget.isEnabled())
        if tip:
            for target in (caption, widget, *companions):
                if target is not None:
                    target.setToolTip(tip)

        if companions:
            cell = QtWidgets.QHBoxLayout()
            cell.setSpacing(2)
            # The row's WIDTH belongs to the control it names: companions ride
            # at their own hint (a button, a tick), and everything left over
            # goes to the field. Without the stretch a companion carrying a
            # long caption simply outbids the control -- a Copy/Move combo
            # crushed to a few pixels by the tick box beside it.
            cell.addWidget(widget, 1)
            for companion in companions:
                cell.addWidget(companion)
            field = cell
        else:
            field = widget

        if caption is not None:
            self._rows_layout.addRow(caption, field)
        else:
            self._rows_layout.addRow(field)
        self._row_widgets[widget] = [w for w in (caption, *companions) if w is not None]
        if caption is not None:
            self._captions.append(caption)
            self._sync_caption_widths()
        return caption

    def _sync_caption_widths(self) -> None:
        """Floor every caption at the widest one: the label column, filled.

        QFormLayout sizes a label to its OWN hint and aligns it inside the
        label column, so every caption but the widest stops short of the
        control it names -- and a caption carries an opaque PLATE, so that
        gap is not whitespace, it is a ragged edge down the middle of the
        form. Flooring them all at the widest hint fills the column the
        layout already reserved: the plates end on one line, flush against
        the field column, and nothing moves (the floor is the column's own
        width, so no field loses a pixel).

        Stateless: each caption's floor is dropped before it is measured, so
        a re-sync after the theme lands (or after a row is added) measures
        the TEXT rather than the floor the last pass set.
        """
        hints = []
        live = []
        for caption in self._captions:
            try:  # a row rebuilt behind us leaves a deleted C++ wrapper here
                caption.setMinimumWidth(0)
                hints.append(caption.sizeHint().width())
            except RuntimeError:
                continue
            live.append(caption)
        self._captions = live
        if not live:
            return
        column = max(hints)
        for caption in live:
            caption.setMinimumWidth(column)

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
        self._row_widgets.clear()
        self._captions.clear()
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                self._drop_layout(item.layout())

    @classmethod
    def _drop_layout(cls, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                cls._drop_layout(item.layout())
        layout.deleteLater()

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
