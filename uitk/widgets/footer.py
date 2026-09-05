# !/usr/bin/python
# coding=utf-8
from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichTextFormatter
from uitk.widgets.mixins.size_grip import SizeGripMixin
from uitk.widgets.progressBar import ProgressBar

try:
    from pythontk.str_utils import StrUtils
except ImportError:  # Optional dependency; controller will fall back to simple slicing.
    StrUtils = None


class Footer(QtWidgets.QWidget, AttributesMixin, SizeGripMixin):
    """Footer is a widget that acts as a status bar with an integrated
    thin progress indicator across the bottom edge.

    Layout: a QStackedWidget hosts the visible page (extensible for
    future modes like search/filter). Page 0 stacks a text row -- an
    optional busy spinner, then the status label -- above a slim
    QProgressBar (textless, hidden when idle). The status label carries
    all human-readable text — including the "Hold Esc to cancel…" hint
    relayed from the progress bar via signals. The progress affordance
    stays minimal while the footer remains the single source of truth
    for text; the spinner (:meth:`set_busy`) is the one sign of life a
    3px bar cannot give during a long synchronous step.

    Attributes:
        progress_bar (ProgressBar): The embedded progress bar widget
        status_label (QLabel): The status text label
        busy_indicator (QLabel): The spinner shown beside the status text
    """

    # Qt Designer widget-box entry.
    designer_spec = {
        "icon": "inbox",
        "object_name": "footer",
        "string_properties": {"status": "richtext"},
    }

    # Pixel height of the slim progress indicator at the bottom edge.
    PROGRESS_BAR_HEIGHT = 3

    #: Busy indicator: a uitk icon rotated through BUSY_FRAMES steps, one
    #: step per BUSY_FRAME_MS while the event loop is free and one per
    #: ``update()`` tick while a synchronous slot holds it (see set_busy).
    BUSY_ICON = "refresh"
    BUSY_FRAME_MS = 80
    BUSY_FRAMES = 12

    # Foreground colour per status severity, sourced from pythontk's
    # ``LOG_COLORS`` (via ``RichTextFormatter``) so the footer, message boxes,
    # and console logs share one palette. ``info`` (``None``) leaves the theme
    # default text colour in place. Used by ``setStatusText(..., level=...)``.
    LEVEL_COLORS = {
        "info": None,
        "success": RichTextFormatter.LOG_COLORS.get("SUCCESS", "#7ec77e"),
        "warning": RichTextFormatter.LOG_COLORS.get("WARNING", "#e0b341"),
        "error": RichTextFormatter.LOG_COLORS.get("ERROR", "#e06c6c"),
    }

    def __init__(
        self,
        parent=None,
        add_size_grip=True,
        **kwargs,
    ):
        """Initialize the Footer with optional size grip.

        Parameters:
            parent (QWidget, optional): The parent widget. Defaults to None.
            add_size_grip (bool, optional): Whether to add a size grip. Defaults to True.
            **kwargs: Additional attributes for the footer.
        """
        super().__init__(parent)

        self._status_text = ""
        self._default_status_text = ""
        self._status_level = None
        self._size_grip = None
        self._center_spacer_added = False

        # Hold-to-cancel relay: ProgressBar emits holdStarted/holdEnded;
        # we swap the status text and restore it on release.
        self._status_before_hold: Optional[str] = None

        # Main outer layout (horizontal — leaves room for the size grip on the right)
        self.main_layout = QtWidgets.QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Stacked widget keeps room for future alternate pages (search,
        # filter, etc.) without restructuring the footer.
        self._stacked_widget = QtWidgets.QStackedWidget()
        self._stacked_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        self._stacked_widget.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._stacked_widget.setContentsMargins(0, 0, 0, 0)

        # Page 0 — status label (top, fills available space) + slim
        # progress bar pinned to the bottom edge.
        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Text row: an optional busy spinner, then the status label. The
        # spinner is hidden when idle, so the row costs nothing until a task
        # asks for it (see set_busy).
        text_row = QtWidgets.QHBoxLayout()
        text_row.setContentsMargins(0, 0, 0, 0)
        text_row.setSpacing(0)

        self._busy_indicator = QtWidgets.QLabel()
        self._busy_indicator.setAlignment(QtCore.Qt.AlignCenter)
        self._busy_indicator.setContentsMargins(6, 0, 0, 0)
        self._busy_indicator.hide()
        text_row.addWidget(self._busy_indicator)

        self._status_label = QtWidgets.QLabel()
        self._status_label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        self._status_label.setIndent(8)
        self._status_label.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Expanding
        )
        text_row.addWidget(self._status_label)
        content_layout.addLayout(text_row)

        self._busy_frames: list = []
        self._busy_frame = 0
        self._busy_timer = QtCore.QTimer(self)
        self._busy_timer.setInterval(self.BUSY_FRAME_MS)
        self._busy_timer.timeout.connect(self._advance_busy)

        self._progress_bar = ProgressBar(auto_hide=True)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(self.PROGRESS_BAR_HEIGHT)
        self._progress_bar.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self._progress_bar.finished.connect(self._on_progress_finished)
        self._progress_bar.cancelled.connect(self._on_progress_cancelled)
        self._progress_bar.holdStarted.connect(self._on_hold_started)
        self._progress_bar.holdEnded.connect(self._on_hold_ended)
        content_layout.addWidget(self._progress_bar)

        self._stacked_widget.addWidget(content)
        self.main_layout.addWidget(self._stacked_widget)

        # Style children to blend with footer background (transparent, no borders, no hover)
        self._apply_transparent_style()

        # Set up size grip
        self.setProperty("class", self.__class__.__name__)
        self.setFixedHeight(19)

        if add_size_grip:
            self._setup_size_grip()

        # Debounce timer: re-evaluate text only after resize settles
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._on_resize_settled)

        self.set_attributes(**kwargs)

    @property
    def container_layout(self) -> QtWidgets.QHBoxLayout:
        """Backward compatibility: return main_layout as container_layout."""
        return self.main_layout

    def alignment(self) -> QtCore.Qt.Alignment:
        """Get alignment of the status label (backward compatibility)."""
        return self._status_label.alignment()

    def update_font_size(self):
        """Public method for updating font size (backward compatibility)."""
        self._update_font_size()

    def font(self) -> QtGui.QFont:
        """Get font from status label (backward compatibility)."""
        return self._status_label.font()

    def _setup_size_grip(self):
        """Set up the size grip in the footer."""
        self._grip_spacer = QtWidgets.QSpacerItem(
            6, 0, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum
        )
        self.main_layout.addItem(self._grip_spacer)
        self._size_grip = self.create_size_grip(
            container=self,
            layout=self.main_layout,
            alignment=QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight,
        )

    @staticmethod
    def _refresh_style(widget: QtWidgets.QWidget) -> None:
        """Re-evaluate stylesheet rules that depend on dynamic properties.

        Qt does not re-cascade selectors like ``[footerRounded="true"]``
        when properties are changed after the widget is already polished.
        Triggering unpolish+polish forces fresh evaluation.
        """
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)

    _ROUNDED_QSS_MARKER = "/* footerRounded */"

    @classmethod
    def _apply_rounded_style(cls, widget: QtWidgets.QWidget, rounded: bool) -> None:
        """Apply rounded-corner styling inline on the widget.

        Class/attribute-selector rules in the theme QSS can lose specificity
        races against ``QAbstractButton``'s ``border-radius: 1px``. Setting
        the rule directly on the widget always wins, and we strip the previous
        marker on re-application so callers can flip the flag at runtime.
        """
        existing = widget.styleSheet() or ""
        if cls._ROUNDED_QSS_MARKER in existing:
            # Strip previous injection (everything from marker to end of line).
            lines = [
                ln for ln in existing.splitlines() if cls._ROUNDED_QSS_MARKER not in ln
            ]
            existing = "\n".join(lines).rstrip()
        radius = "3px" if rounded else "0"
        addition = f"border-radius: {radius}; {cls._ROUNDED_QSS_MARKER}"
        widget.setStyleSheet((existing + "\n" if existing else "") + addition)

    # ── Centering ────────────────────────────────────────────────

    def _center_index(self) -> int:
        """Index a centred widget goes at: right after the status stack.

        Centred widgets sit between the status text and whatever was added on
        the right, in the order they were added.
        """
        idx = self.main_layout.indexOf(self._stacked_widget)
        return (idx + 1) if idx >= 0 else 0

    def _center_stretch(self) -> None:
        """Balance the space either side of the centred widgets.

        The status stack occupies everything left of centre, so all that is
        missing is an EQUAL stretch on the far side: two matching stretches
        put whatever sits between them on the footer's midline, and both
        collapse to nothing when the footer is too narrow to honour it (the
        centred widget then simply follows the status text, never clipped by
        it -- the status label's size policy is ``Ignored``).

        Both factors have to be set explicitly.  An expanding spacer left at
        the default stretch of 0 loses every spare pixel to a stretch-1
        neighbour, which would silently park the widget on the right again.
        Created once; a later centred add just re-applies the factors.
        """
        if not self._center_spacer_added:
            if self._size_grip:
                idx = self.main_layout.indexOf(self._grip_spacer)
            else:
                idx = self.main_layout.count()
            self.main_layout.insertStretch(idx, 1)
            self._center_spacer_added = True
        self.main_layout.setStretchFactor(self._stacked_widget, 1)

    # ── Action buttons ───────────────────────────────────────────

    def add_widget(
        self,
        widget: QtWidgets.QWidget,
        side: str = "right",
        background: bool = False,
        rounded: bool = True,
    ) -> QtWidgets.QWidget:
        """Insert an arbitrary widget into the footer on the given side.

        ``side="right"`` places the widget on the right, before the size
        grip (if present).  ``side="left"`` places it at the left edge,
        before the status/progress stack.  ``side="center"`` centres it
        horizontally (see :meth:`_center_stretch`).  Returns *widget* for
        chaining.

        ``background=False`` (default) makes the widget transparent so it
        blends with the footer; set to ``True`` for normal styled background.

        ``rounded=True`` (default) gives the widget slightly rounded
        corners via the ``footerRounded`` style property; set ``False``
        for hard square edges.
        """
        if side not in ("left", "right", "center"):
            raise ValueError(f"side must be 'left', 'right' or 'center', got {side!r}")

        widget.setProperty("footerWidget", not background)
        widget.setProperty("footerRounded", bool(rounded))
        widget.setParent(self)
        # QSS selectors that read dynamic properties only re-evaluate
        # on an explicit unpolish/polish cycle.
        self._refresh_style(widget)
        # Apply the radius inline so it always beats theme QSS regardless
        # of selector-specificity quirks across Qt versions.
        self._apply_rounded_style(widget, rounded)
        if side == "left":
            self.main_layout.insertWidget(0, widget)
        elif side == "center":
            self.main_layout.insertWidget(self._center_index(), widget)
            self._center_stretch()
        else:
            if self._size_grip:
                idx = self.main_layout.indexOf(self._grip_spacer)
                self.main_layout.insertWidget(idx, widget)
            else:
                self.main_layout.addWidget(widget)

        # Grow the footer's fixed height if the new child is taller, so
        # callers can drop in prebuilt widgets without clipping.
        try:
            needed = max(widget.minimumHeight(), widget.sizeHint().height())
        except Exception:
            needed = 0
        if needed and needed > self.height():
            self.setFixedHeight(needed)
        return widget

    def add_action_button(
        self,
        text: str = "",
        icon_name: str = None,
        tooltip: str = "",
        callback=None,
        rounded: bool = True,
        states=None,
    ) -> QtWidgets.QPushButton:
        """Add an action button to the right side of the footer.

        Buttons are inserted before the size grip (if present) and after
        the status/progress area, similar to how :class:`Header` hosts
        icon buttons.

        Parameters:
            text: Button label text.
            icon_name: Icon name (without extension) for ``IconManager``.
            tooltip: Tooltip text.
            callback: Callable connected to the button's ``clicked`` signal.
                With ``states``, used as the fallback for states that carry
                no ``callback`` of their own.
            rounded: When True (default), the button gets slightly rounded
                corners. Set False for hard square edges.
            states: Optional list of state dicts for multi-state cycling —
                same shape as ``ActionOption(states=...)``: optional
                ``icon`` / ``color`` / ``tooltip`` / ``callback`` keys.
                State 0's visuals apply immediately; clicking runs the
                current state's callback then cycles. The controller is
                exposed as ``btn.icon_states`` — assign
                ``btn.icon_states.current_state`` to sync the visuals to
                externally-owned app state.

        Returns:
            The created QPushButton.
        """
        btn = QtWidgets.QPushButton(text, self)
        btn.setProperty("footerWidget", True)
        btn.setProperty("footerRounded", bool(rounded))
        self._refresh_style(btn)
        self._apply_rounded_style(btn, rounded)
        h = self.height()
        btn_h = max(h - 2, 1)  # 1px clearance top and bottom
        initial_icon = icon_name or (states[0].get("icon") if states else None)
        if initial_icon and not text:
            btn.setFixedSize(btn_h, btn_h)  # square for icon-only
        else:
            btn.setFixedHeight(btn_h)  # flexible width for text
        btn.setCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))

        if initial_icon:
            from uitk.managers.icon_manager import IconManager

            # Margin 6 keeps the historical h*0.7 sizing (13 px on a 19 px
            # footer) while delegating the math to IconManager.
            IconManager.fit_icon(btn, initial_icon, h, margin=6)

        if tooltip:
            btn.setToolTip(tooltip)

        if states:
            from uitk.widgets.mixins.icon_states import IconStates

            # Attaching applies the current state's visuals over the
            # fit_icon render above (the fitted size is preserved; a state
            # color is pinned so theme sweeps don't repaint it).
            btn.icon_states = IconStates(states, widget=btn)
            btn.clicked.connect(lambda *_: btn.icon_states.activate(fallback=callback))
        elif callback:
            btn.clicked.connect(callback)

        # Insert before grip spacer if present, otherwise append
        if self._size_grip:
            idx = self.main_layout.indexOf(self._grip_spacer)
            self.main_layout.insertWidget(idx, btn)
        else:
            self.main_layout.addWidget(btn)

        return btn

    @property
    def progress_bar(self) -> ProgressBar:
        """Get the embedded progress bar."""
        return self._progress_bar

    @property
    def status_label(self) -> QtWidgets.QLabel:
        """Get the status label."""
        return self._status_label

    @property
    def size_grip(self) -> Optional[QtWidgets.QSizeGrip]:
        """Get the size grip widget if it exists.

        Returns:
            QSizeGrip or None: The size grip widget, or None if not created.
        """
        return self._size_grip

    @size_grip.setter
    def size_grip(self, value: Optional[QtWidgets.QSizeGrip]) -> None:
        """Set the size grip widget (used internally by SizeGripMixin).

        Parameters:
            value: The size grip widget to set.
        """
        self._size_grip = value

    def setText(self, text: str, level: Optional[str] = None) -> None:
        """Set the status text (convenience method matching QLabel API).

        Parameters:
            text (str): The status text to display.
            level (str, optional): Severity for colour coding — one of
                ``LEVEL_COLORS`` (``info``/``success``/``warning``/``error``).
                ``None`` leaves the theme default colour.
        """
        self.setStatusText(text, level)

    def text(self) -> str:
        """Get the current displayed text (convenience method matching QLabel API).

        Returns:
            str: The text currently shown in the status label.
        """
        return self._status_label.text()

    def setStatusText(
        self, text: str | None = None, level: Optional[str] = None
    ) -> None:
        """Set the status text of the footer.

        Parameters:
            text (str): The new status text.
            level (str, optional): Severity for colour coding — one of
                ``LEVEL_COLORS`` (``info``/``success``/``warning``/``error``).
                ``None`` (default) restores the theme default colour, so
                existing callers are unaffected.
        """
        self._status_text = text or ""
        self._apply_status_level(level)
        self._elide_status_text()

    def _apply_status_level(self, level: Optional[str]) -> None:
        """Colour the status label by severity, preserving its transparency.

        No-ops when the level is unchanged so the common case (every plain
        ``setStatusText`` call, which passes ``level=None``) never triggers a
        redundant stylesheet re-polish. On a change it re-applies the
        transparent/no-border base so switching from a coloured level back to
        ``info``/``None`` cleanly drops the colour override. The base string
        matches :meth:`_apply_transparent_style` exactly, so the initial
        ``None`` state is already correct without a restyle.
        """
        if level == self._status_level:
            return
        self._status_level = level
        color = self.LEVEL_COLORS.get(level)
        base = "background: transparent; border: none;"
        self._status_label.setStyleSheet(base + (f" color: {color};" if color else ""))

    def setDefaultStatusText(self, text: str | None = None) -> None:
        """Set fallback text shown when no explicit status is provided."""
        self._default_status_text = text or ""
        if not self._status_text:
            self._elide_status_text()

    def statusText(self) -> str:
        """Get the status text of the footer.

        Returns:
            str: The current status text.
        """
        return self._status_text

    def getDefaultStatusText(self) -> str:
        """Get the fallback text shown when no explicit status is set."""
        return self._default_status_text

    def getSizeGripEnabled(self) -> bool:
        """Whether the footer currently shows a resize grip."""
        return self._size_grip is not None and not self._size_grip.isHidden()

    def setSizeGripEnabled(self, value: bool) -> None:
        """Show or hide the resize grip, creating it on first enable.

        The grip is otherwise a construction-time choice (``add_size_grip``),
        which a form author can't reach; this makes it a checkbox in Designer.
        """
        if value and self._size_grip is None:
            self._setup_size_grip()
        if self._size_grip is not None:
            self._size_grip.setVisible(bool(value))

    def setStatus(self, value: str) -> None:
        """Set the status text (Qt-property setter for :meth:`setStatusText`).

        Named to match the ``status`` property: ``pyside6-uic`` compiles a
        ``.ui`` property into a ``set<Name>`` call, so the pair has to exist.
        """
        self.setStatusText(value)

    # -- Qt Designer properties ----------------------------------------------
    # ``status`` rather than ``statusText``: the getter of that name is an
    # established method (``footer.statusText()``) and a Qt property would
    # shadow it. Both write the same state.
    status = QtCore.Property(str, fget=statusText, fset=setStatus)
    defaultStatusText = QtCore.Property(
        str, fget=getDefaultStatusText, fset=setDefaultStatusText
    )
    sizeGripEnabled = QtCore.Property(
        bool, fget=getSizeGripEnabled, fset=setSizeGripEnabled
    )

    def start_progress(
        self,
        total: Optional[int] = None,
        text: str = "",
        busy: Optional[bool] = None,
    ) -> Callable[[Optional[int], Optional[str]], bool]:
        """Start showing progress in the footer.

        Two modes from one entry point — pass *total* when you know the
        step count, omit it (or pass ``None``) for an indeterminate
        "task indicator" marquee.

        Parameters:
            total: Total number of steps. ``None`` (default) enables
                indeterminate / busy mode — the bar pulses and callers
                tick it via ``update()`` without a value.
            text: Optional status text to show with the bar.
            busy: Show the busy spinner beside the status text
                (:meth:`set_busy`). ``None`` (default) shows it for
                indeterminate work only — the 3px marquee is the only other
                sign of life there — and hides it on a determinate bar.
                ``True`` keeps it on a determinate bar whose single steps
                are long (an export's file write); ``False`` never shows it.

        Returns:
            Callable: ``update(value=None, text=None) -> bool``. Returns
            ``False`` if the user pressed Esc to cancel.

        Example (determinate)::

            update = footer.start_progress(100, "Loading...")
            for i in range(100):
                if not update(i + 1):
                    break  # cancelled
            footer.finish_progress()

        Example (indeterminate task indicator)::

            update = footer.start_progress(text="Working: ...")
            chunk_1()
            update()           # tick — pumps the event loop so the
            chunk_2()          # marquee actually advances during the
            update()           # synchronous work.
            footer.finish_progress()
        """
        if text:
            self.setStatusText(text)
        # text="" keeps the label off the thin bar (the footer's status label
        # shows it); host_label still carries it into host-native progress UI.
        self._progress_bar.start_task(total, text="", show=True, host_label=text)
        if busy is None:
            busy = total is None or total <= 0
        self.set_busy(bool(busy))
        return self.update_progress

    def update_progress(
        self, value: Optional[int] = None, text: Optional[str] = None
    ) -> bool:
        """Tick the progress bar and optionally update the status text.

        Parameters:
            value: Determinate progress value. ``None`` (default) just
                pumps the event loop — use this in indeterminate mode
                to keep the marquee advancing between work chunks.
            text: Optional new status text (shown in the footer label,
                not on the bar itself).

        Returns:
            ``False`` if the task was cancelled (user held Esc),
            ``True`` otherwise.

        Critical side effect: ``ProgressBar.update_progress`` calls
        ``QApplication.processEvents()`` once per tick. That is what
        keeps the bar (and the rest of the UI) responsive while a slot
        runs synchronously — the slot must voluntarily call ``update()``
        between work chunks to drive the animation.
        """
        if text is not None and self._status_before_hold is None:
            # Skip status updates during a hold; the held hint stays put,
            # and we restore the pre-hold text on release.
            self.setStatusText(text)
        # A tick is the one moment a synchronous slot hands the loop back,
        # so it is also when the spinner gets its next frame (the timer
        # only fires while the loop is free).
        self._advance_busy()
        # ``ProgressBar.update_progress`` requires an int. ``None`` is a
        # text/pump-only tick, so hold the bar where it is: a determinate
        # bar fed a 0 here snapped back to empty on every narration tick
        # ("converting…") between real steps. In indeterminate mode the
        # value only feeds the emitted signal. *text* is forwarded even
        # though this bar draws none (``setTextVisible(False)``): the bar
        # relays it to host-native progress UI, which would otherwise be
        # stuck showing the label the task started with while the footer
        # shows live text.
        if value is None:
            value = max(0, self._progress_bar.value())
        return self._progress_bar.update_progress(value, text)

    def finish_progress(self, text: Optional[str] = None, delay_ms: int = 1000):
        """Finish the progress and hide the bar.

        Parameters:
            text: Optional completion message to show briefly in the
                footer label.
            delay_ms: Delay before hiding the bar (default 1000ms).
        """
        self._stop_busy()
        if text:
            self.setStatusText(text)
        QtCore.QTimer.singleShot(delay_ms, self._on_progress_finished)

    def cancel_progress(self):
        """Cancel the current progress operation."""
        self._progress_bar.cancel()

    def set_progress_total(self, total: int) -> None:
        """Adjust the bar's task total mid-flight.

        Thin proxy over :meth:`ProgressBar.set_total` so adapters can
        sync the bar from a downstream callback's ``total`` without
        the slot pre-knowing the loop size.
        """
        self._progress_bar.set_total(total)

    def progress(
        self,
        total: Optional[int] = None,
        text: str = "",
        busy: Optional[bool] = None,
    ) -> "FooterProgressContext":
        """Context manager for cooperative progress / task feedback.

        Pass *total* for a determinate bar; omit it for an indeterminate
        "task indicator" marquee. Callers drive the bar by ticking
        ``update()`` between work chunks — see
        :meth:`update_progress`. *busy* is :meth:`start_progress`'s: the
        spinner beside the text, on by default for indeterminate work.

        Example (determinate)::

            with footer.progress(total=len(files), text="Copying") as update:
                for i, f in enumerate(files):
                    copy(f)
                    if not update(i + 1):
                        break   # cancelled

        Example (indeterminate task indicator)::

            with footer.progress(text="Working: Get Scene Info") as tick:
                step_one()
                tick()
                step_two()
                tick()
        """
        return FooterProgressContext(self, total, text, busy)

    def _on_progress_finished(self):
        """Hide and reset the bar when the task completes."""
        self._stop_busy()
        self._progress_bar.hide()
        self._progress_bar.reset()

    def _on_progress_cancelled(self):
        """Hide the bar on cancel, but do NOT reset it.

        The cancelled task is still running -- its loop has not yet reached the
        checkpoint that will tell it to stop. ``reset()`` drops the bar's scope
        reference, after which ``update()`` reports "keep going" forever, so
        routing cancel through :meth:`_on_progress_finished` meant Esc silently
        did nothing and the work ran to completion. ``start_task`` is the reset
        point; hiding is all that belongs here.
        """
        self._progress_bar.hide()
        self._stop_busy()

    def _on_hold_started(self, hold_ms: int):
        """Relay the bar's hold hint into the status label."""
        if self._status_before_hold is None:
            self._status_before_hold = self._status_text
        self.setStatusText(f"Hold Esc to cancel… ({hold_ms} ms)")

    def _on_hold_ended(self):
        """Restore the pre-hold status text when Escape is released."""
        if self._status_before_hold is None:
            return
        prior = self._status_before_hold
        self._status_before_hold = None
        self.setStatusText(prior)

    # ── Busy indicator ───────────────────────────────────────────

    @property
    def busy_indicator(self) -> QtWidgets.QLabel:
        """The spinner label shown beside the status text while busy."""
        return self._busy_indicator

    @property
    def is_busy(self) -> bool:
        """Whether the busy indicator is showing."""
        return not self._busy_indicator.isHidden()

    def set_busy(self, busy: bool) -> None:
        """Show or hide the busy spinner beside the status text.

        The spinner is what says "still working" when the bar cannot: a
        determinate bar parked on one long step (a file write, an external
        conversion) and a 3px indeterminate marquee both read as hung. It
        turns on a timer while the event loop is free, and on every
        :meth:`update_progress` tick while a synchronous slot holds the loop
        -- the same tick that repaints the bar. Honest by construction: it
        cannot move while nothing is pumping, so a frozen spinner means a
        frozen host, never a decorative one.

        Frames are rendered on each start, so a theme change between runs is
        picked up; a missing icon renders nothing rather than a broken box.
        ``start_progress(busy=...)`` is the usual entry point; this is for
        toggling it mid-task.
        """
        if not busy:
            self._stop_busy()
            return
        if self.is_busy:
            return
        self._busy_frames = self._render_busy_frames()
        self._busy_frame = 0
        if not self._busy_frames:
            return
        self._busy_indicator.setPixmap(self._busy_frames[0])
        self._busy_indicator.show()
        self._busy_timer.start()
        self._elide_status_text()

    def _stop_busy(self) -> None:
        self._busy_timer.stop()
        if not self._busy_indicator.isHidden():
            self._busy_indicator.hide()
            self._elide_status_text()

    def _advance_busy(self) -> None:
        """Show the next frame (no-op while hidden)."""
        if not self._busy_frames or self._busy_indicator.isHidden():
            return
        self._busy_frame = (self._busy_frame + 1) % len(self._busy_frames)
        self._busy_indicator.setPixmap(self._busy_frames[self._busy_frame])

    def _busy_icon_size(self) -> int:
        """Logical size of the spinner: the text row with 2px clearance top
        and bottom -- 12px on the default 19px footer."""
        row = self.height() - self.PROGRESS_BAR_HEIGHT
        return max(8, row - 4)

    def _render_busy_frames(self) -> list:
        """Rotate :attr:`BUSY_ICON` into :attr:`BUSY_FRAMES` pixmaps.

        Rendered at twice the logical size and tagged with a 2x device pixel
        ratio, so the rotated raster stays crisp when the label paints it at
        its logical size (a 12px icon rotated in place aliases badly).
        """
        from uitk.managers.icon_manager import IconManager

        size = self._busy_icon_size()
        base = IconManager.get(self.BUSY_ICON, size=(size * 2, size * 2)).pixmap(
            size * 2, size * 2
        )
        if base.isNull():
            return []
        half = base.width() / 2.0
        frames = []
        for i in range(self.BUSY_FRAMES):
            frame = QtGui.QPixmap(base.size())
            frame.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(frame)
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
            painter.translate(half, half)
            painter.rotate(360.0 * i / self.BUSY_FRAMES)
            painter.translate(-half, -half)
            painter.drawPixmap(0, 0, base)
            painter.end()
            frame.setDevicePixelRatio(2.0)
            frames.append(frame)
        margins = self._busy_indicator.contentsMargins()
        self._busy_indicator.setFixedSize(size + margins.left() + margins.right(), size)
        return frames

    def resizeEvent(self, event):
        """Debounce resize: restart timer on each event so we only
        recalculate font + elision once the user finishes resizing."""
        self._resize_timer.start()
        super().resizeEvent(event)

    def showEvent(self, event):
        """Ensure text is properly sized and elided on first show."""
        super().showEvent(event)
        self._update_font_size()
        self._elide_status_text()

    def _on_resize_settled(self):
        """Called once after resize events stop (debounced)."""
        self._update_font_size()
        self._elide_status_text()

    def _update_font_size(self):
        """Calculate font size for the label relative to widget's height."""
        label_font_size = self.height() * 0.35
        font = self._status_label.font()
        font.setPointSizeF(label_font_size)
        font.setBold(False)
        self._status_label.setFont(font)

    def _elide_status_text(self):
        """Elide the displayed status text to fit available label width."""
        text = self._status_text or self._default_status_text
        if not text:
            self._status_label.setText("")
            return

        fm = QtGui.QFontMetrics(self._status_label.font())
        indent = self._status_label.indent()
        margin = (indent if indent > 0 else 8) * 2
        if self._size_grip and not self._size_grip.isHidden():
            margin += self._size_grip.width()
        if not self._busy_indicator.isHidden():
            margin += self._busy_indicator.width()
        available = self._stacked_widget.width() - margin

        if available <= 0:
            # Widget not laid out yet; show full text (will be elided on show)
            self._status_label.setText(text)
            return

        elided = fm.elidedText(text, QtCore.Qt.ElideMiddle, available)
        self._status_label.setText(elided)

    def _apply_transparent_style(self):
        """Style children to blend seamlessly with the footer.

        The theme stylesheet (style.qss) sets `padding-right: 10000px`
        and `text-align: right` on horizontal QProgressBars, which
        collapses the chunk's drawable area to zero. The slim indicator
        carries no text and only needs the chunk visible, so we override
        padding/margin and let the theme's chunk color come through.
        """
        bar_style = (
            "QProgressBar {"
            "  background: transparent;"
            "  border: none;"
            "  padding: 0;"
            "  margin: 0;"
            "}"
            "QProgressBar::chunk {"
            "  border: none;"
            "  margin: 0;"
            "}"
        )
        self._stacked_widget.setStyleSheet(
            "QStackedWidget { background: transparent; border: none; }"
        )
        self._status_label.setStyleSheet("background: transparent; border: none;")
        self._busy_indicator.setStyleSheet("background: transparent; border: none;")
        self._progress_bar.setStyleSheet(bar_style)

    def status_controller(
        self,
        resolver: Optional[Callable[[], str]] = None,
        default_text: str | None = "",
        truncate_kwargs: Optional[Mapping[str, Any]] = None,
    ) -> "FooterStatusController":
        """Bind a :class:`FooterStatusController` to this footer and return it.

        The factory form is the one consumers should use: a slot reaches its footer
        through the Switchboard (``self.ui.footer``) and gets its status controller
        from the widget it already has, instead of importing the controller class
        out of ``uitk.widgets.footer``. Same arguments as the class, minus ``footer``.
        """
        return FooterStatusController(
            footer=self,
            resolver=resolver,
            default_text=default_text,
            truncate_kwargs=truncate_kwargs,
        )

    def attach_to(self, widget: QtWidgets.QWidget) -> None:
        """Attach this footer to the bottom of a QWidget or QMainWindow's centralWidget."""
        if hasattr(widget, "footer") and getattr(widget, "footer") is self:
            return

        if isinstance(widget, QtWidgets.QMainWindow) and widget.centralWidget():
            widget = widget.centralWidget()

        layout = widget.layout()
        if not isinstance(layout, QtWidgets.QLayout):
            layout = QtWidgets.QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            widget.setLayout(layout)
        layout.addWidget(self)
        self.setParent(widget)
        setattr(widget, "footer", self)


class FooterProgressContext:
    """Context manager for footer progress tracking."""

    def __init__(
        self,
        footer: Footer,
        total: Optional[int],
        text: str,
        busy: Optional[bool] = None,
    ):
        self._footer = footer
        self._total = total
        self._text = text
        self._busy = busy

    def __enter__(self) -> Callable[[Optional[int], Optional[str]], bool]:
        """Start progress and return update callback."""
        return self._footer.start_progress(self._total, self._text, self._busy)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finish progress."""
        if exc_type is None and not self._footer.progress_bar.is_cancelled:
            self._footer.finish_progress("Complete", delay_ms=500)
        else:
            self._footer._on_progress_finished()
        return False


class FooterStatusController:
    """Helper that keeps a footer in sync with a resolver function."""

    def __init__(
        self,
        footer: Footer,
        resolver: Optional[Callable[[], str]] = None,
        default_text: str | None = "",
        truncate_kwargs: Optional[Mapping[str, Any]] = None,
    ):
        self._footer = footer
        self._resolver = resolver or (lambda: "")
        self._truncate_kwargs = self._sanitize_truncate_kwargs(truncate_kwargs)
        if default_text is not None:
            self._footer.setDefaultStatusText(default_text)
        self.update()

    def set_resolver(self, resolver: Callable[[], str]) -> None:
        self._resolver = resolver or (lambda: "")
        self.update()

    def set_truncation(
        self,
        truncate_kwargs: Optional[Mapping[str, Any]] = None,
        **extra_kwargs: Any,
    ) -> None:
        """Configure truncation behavior for footer updates via StrUtils.truncate kwargs."""
        combined: dict[str, Any] = {}
        if truncate_kwargs:
            combined.update(dict(truncate_kwargs))
        if extra_kwargs:
            combined.update(extra_kwargs)
        self._truncate_kwargs = self._sanitize_truncate_kwargs(combined)
        self.update()

    def update(self) -> None:
        if not self._footer:
            return
        value = self._resolver() if self._resolver else ""
        value = self._truncate_value(value)
        self._footer.setStatusText(value)

    def _truncate_value(self, value: str) -> str:
        """Apply optional truncation using StrUtils when available."""
        if not value:
            return value

        kwargs = self._truncate_kwargs
        if not kwargs:
            return value

        length = kwargs.get("length")
        if not isinstance(length, int) or length <= 0 or len(value) <= length:
            return value

        if StrUtils:
            try:
                return StrUtils.truncate(
                    value,
                    **kwargs,
                )
            except Exception:
                pass  # Fall back to a simplified truncation strategy.

        return self._fallback_truncate(value, kwargs)

    def _fallback_truncate(self, value: str, kwargs: Mapping[str, Any]) -> str:
        insert = kwargs.get("insert", "..") or ""
        mode = (kwargs.get("mode") or "start").lower()
        length = kwargs.get("length")
        if not isinstance(length, int) or length <= 0:
            return value

        if mode in ("end", "right"):
            return value[:length] + insert

        if mode == "middle" and length > len(insert):
            visible = max(1, length - len(insert))
            left = visible // 2
            right = visible - left
            return value[:left] + insert + value[-right:]

        tail_length = max(1, length - len(insert)) if insert else length
        return insert + value[-tail_length:]

    @staticmethod
    def _sanitize_truncate_kwargs(
        truncate_kwargs: Optional[Mapping[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if not truncate_kwargs:
            return None
        try:
            candidate = dict(truncate_kwargs)
        except Exception:
            return None
        length = candidate.get("length")
        if not isinstance(length, int) or length <= 0:
            return None
        return candidate


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(w)

    # Add some content
    label = QtWidgets.QLabel("Main Content Area")
    label.setAlignment(QtCore.Qt.AlignCenter)
    layout.addWidget(label)

    # Add footer
    footer = Footer(setStatusText="Ready")
    layout.addWidget(footer)

    w.resize(400, 300)
    w.show()

    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Promoting a widget in designer to use a custom class:
>   In Qt Designer, select all the widgets you want to replace,
        then right-click them and select 'Promote to...'.

>   In the dialog:
        Base Class:     Class from which you inherit. ie. QWidget
        Promoted Class: Name of the class. ie. "MyWidget"
        Header File:    Path of the file (changing the extension .py to .h)  ie. myfolder.mymodule.mywidget.h

>   Then click "Add", "Promote",
        and you will see the class change from "QWidget" to "MyWidget" in the Object Inspector pane.
"""
