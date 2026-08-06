# !/usr/bin/python
# coding=utf-8
"""Shared display behaviour for the spin-box widgets.

Used by :class:`uitk.widgets.spinBox.SpinBox` and
:class:`uitk.widgets.doubleSpinBox.DoubleSpinBox` — both derive from
``QDoubleSpinBox``:

- :class:`SpinBoxTextColorMixin` tints the displayed value text.
- :class:`PrefixColumnMixin` lays the ``prefix`` label and the value out as a
  two-part column that survives a narrow field.
"""
import re

from qtpy import QtCore, QtGui


# Our color directive is tagged with a ``/*tc*/`` marker so it can be replaced
# or removed without disturbing any other inline style on the widget (e.g. the
# option-box border tweaks appended during wrapping).
_TC_DIRECTIVE = re.compile(r"\s*/\*tc\*/[^;]*;")


class SpinBoxTextColorMixin:
    """Tint a spin box's displayed value text.

    The tint is applied as a ``color`` directive on the **spin box itself** (not
    its internal ``lineEdit()``): under the uitk theme the displayed value is
    drawn via the ``QAbstractSpinBox`` color rule, which overrides a color set
    on the embedded line edit — so the spin box is the only level that reliably
    wins. The directive is merged into (not allowed to clobber) any existing
    inline stylesheet. Pass ``None`` / ``""`` to clear it and fall back to the
    theme color.
    """

    def set_text_color(self, color) -> None:
        """Tint the displayed value text.

        Args:
            color: Any QSS color string (``"#ff5555"``, ``"red"``,
                ``"rgb(220,80,80)"``) — or ``None`` to clear the override.
        """
        self._text_color = color or None
        base = _TC_DIRECTIVE.sub("", self.styleSheet())
        if self._text_color:
            base = "{} /*tc*/color: {};".format(base, self._text_color).strip()
        self.setStyleSheet(base)

    def text_color(self):
        """The current value-text color override, or ``None`` if unset."""
        return getattr(self, "_text_color", None)


class PrefixColumnMixin:
    """Lay a spin box's ``prefix`` label and its value out as a column.

    ``setPrefix("Bias:")`` separates the label from the value with a **tab**, so
    a stack of fields lines their values up on a shared column. A tab in a
    ``QLineEdit`` is a *fixed* stop (``QTextOption``'s default, 80 px) with no
    public setter — which is fine at full panel width and silently destructive
    once the field is narrower than that stop: the value is laid out past the
    right edge and scrolls out of view entirely. A half-width field (two
    parameters sharing a row) hits this on its own, and an option-box icon
    button beside the field — a per-field reset, pin, etc. — takes another
    ~19 px out of the same budget, so the value disappears exactly where the
    button sits and reads as the button covering it.

    This mixin degrades the label instead of the value, in three steps: the tab
    column while the value still fits behind it, a single-space separator once
    it doesn't, and an *elided* label when even that overflows — so the value is
    readable at any width the layout hands out. The choice is re-evaluated
    whenever the field is resized (which includes being wrapped in an option
    box) or the font changes, and each step up carries hysteresis so a field
    parked on a threshold can't flap between two forms.

    The choice is an **output** of the allocated width and never an input to
    it: the size hints are re-stated in terms of the label at full length
    (:meth:`_hint_for_full_label`), which is the only thing standing between
    this and a shrink spiral.

    The label is picked up however it was set. ``setPrefix`` records it and is
    idempotent with respect to the separator — a ``.ui`` file stores the tab a
    previous ``setPrefix`` appended and ``pyside6-uic`` replays that stored
    string back through this method, so a naive append grew the label a tab per
    round-trip (two stops, 160 px, no field wide enough to show anything at
    all). A prefix set through the **meta-object** never reaches this method at
    all — that is the ``QUiLoader`` path every runtime-loaded panel takes, and
    the C++ setter wins there — so it is adopted on the next evaluation instead,
    but only in its tab-separated form: a caller composing an exact prefix by
    hand keeps it verbatim (see :meth:`_adopt_external_prefix`).
    """

    # Separator inserted between the label and the value.
    _COLUMN_SEPARATOR = "\t"
    _COMPACT_SEPARATOR = " "
    # Extra px of room required to step back UP a form (elided -> full label,
    # compact -> tab column), so a field sitting on either threshold can't flap.
    # Stepping DOWN is unconditional: the value must never wait on slack.
    _COLUMN_HYSTERESIS = 8

    # ------------------------------------------------------------------ prefix
    def setPrefix(self, prefix: str) -> None:
        """Set the label shown ahead of the value (separator managed here)."""
        self._prefix_label = prefix.rstrip(" \t")
        # force: an explicit call is authoritative — skip the adopt-back check,
        # which would otherwise read the *outgoing* prefix as an external edit.
        self._apply_prefix_column(force=True)

    def prefix_label(self) -> str:
        """The prefix as set, without the separator (or elision) applied here.

        Empty for a prefix this mixin does not manage (see
        :meth:`_adopt_external_prefix`).
        """
        self._adopt_external_prefix()
        return getattr(self, "_prefix_label", "") or ""

    # ------------------------------------------------------------ Qt overrides
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # First resize is also the first time the field has a meaningful width;
        # until then the authored column stands.
        self._prefix_column_ready = True
        self._apply_prefix_column()

    def showEvent(self, event):
        super().showEvent(event)
        # Backstop for a field the layout happens to hand its final size before
        # the first show (no resize event to react to).
        self._prefix_column_ready = True
        self._apply_prefix_column()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.FontChange:
            self._apply_prefix_column()

    def sizeHint(self):
        return self._hint_for_full_label(super().sizeHint())

    def minimumSizeHint(self):
        return self._hint_for_full_label(super().minimumSizeHint())

    # ------------------------------------------------------------------- hints
    def _hint_for_full_label(self, hint):
        """Re-state *hint* in terms of the **full** label, whatever is displayed.

        Qt derives both size hints from the current prefix string. Left alone,
        a collapsed or elided prefix reports a narrower hint, the layout hands
        the field less width, and the narrower field elides further — a spiral
        that ends with the label gone entirely (measured: a 100 px half-row
        field collapsing to 32 px while its neighbour absorbed the slack). The
        label choice has to be an *output* of the allocated width and never an
        input to it, so the hint is normalized to the label at full length plus
        a compact separator — which is what Qt reported for the tab form
        anyway, since ``QFontMetrics`` measures a tab as a plain advance and
        never as the stop the renderer will use.

        Qt composes the hint as *chrome + widest candidate*, where the
        candidates are the prefixed value and ``specialValueText`` — which is
        shown **instead of** the whole string, prefix included, and so takes no
        part in the correction. Backing the chrome out and re-composing against
        the full label covers every ordering of the two; a special value wider
        than the label leaves the hint untouched, as it should. Correcting
        blindly instead claimed the label's width on top of a string that never
        shows it. The re-compose is exact without a special value; with one it
        carries a few px of ``QStyle::sizeFromContents`` rounding, which is
        harmless — the floor that prevents the spiral is what has to hold, and
        it does. No uitk spin box in the ecosystem sets a special value today;
        this is a standard ``QAbstractSpinBox`` knob a consumer may reach for,
        and the hint math has to survive it.
        """
        label = getattr(self, "_prefix_label", None)
        if not label:
            return hint
        shown_prefix = super().prefix()
        full_prefix = f"{label}{self._COMPACT_SEPARATOR}"
        if shown_prefix == full_prefix:
            return hint  # already the reference form — the correction is 0
        # Measured on the CONCATENATED string, as QAbstractSpinBox measures it
        # — advance(prefix + value) is not advance(prefix) + advance(value), so
        # correcting by the bare prefix widths leaves a few px of drift.
        fm = self.fontMetrics()
        probe = self._widest_value_text()
        full = fm.horizontalAdvance(f"{full_prefix}{probe}")
        shown = fm.horizontalAdvance(f"{shown_prefix}{probe}")
        special = fm.horizontalAdvance(self.specialValueText())
        chrome = hint.width() - max(shown, special)
        hint.setWidth(max(0, chrome + max(full, special)))
        return hint

    # ---------------------------------------------------------------- internal
    def _apply_prefix_column(self, force: bool = False) -> None:
        """Re-pick the separator and push the resulting prefix to Qt."""
        if getattr(self, "_applying_prefix_column", False):
            return
        if not force:
            self._adopt_external_prefix()
        label = getattr(self, "_prefix_label", None)
        if label is None:  # no prefix has been set through any path
            return
        wanted = self._resolve_prefix(label) if label else ""
        if not force and wanted == super().prefix():
            return
        # setPrefix re-renders the editor and invalidates the size hint, either
        # of which can re-enter through resizeEvent.
        self._applying_prefix_column = True
        try:
            super().setPrefix(wanted)
        finally:
            self._applying_prefix_column = False
        self._applied_prefix = wanted

    def _adopt_external_prefix(self) -> None:
        """Re-read the label when the prefix changed behind this mixin's back.

        ``QUiLoader`` applies a ``.ui`` property through the meta-object, which
        calls the **C++** ``setPrefix`` and never this class's override — so on
        every runtime-loaded panel (i.e. all of them) the authored label arrives
        this way. Comparing against the prefix this mixin last wrote also lets
        any later external change win instead of being clobbered on the next
        resize.

        Only the **tab-separated** form is claimed. A caller reaching past
        ``setPrefix`` to compose an exact string means it (mayatk's curtain
        panel space-pads a group of labels to a shared width through the C++
        setter); re-deriving a label from it and re-separating that would undo
        the very alignment it went to the trouble of computing.

        Adoption is *lazy* — there is no signal for a prefix set behind the
        meta-object, so it lands on the next evaluation (resize / show / font
        change). ``.ui`` loading always sets the prefix before the first
        layout, so the panel case is covered; a caller changing it on an
        already-settled field whose geometry then never moves would have to
        nudge the field itself.
        """
        current = super().prefix()
        if current == getattr(self, "_applied_prefix", None):
            return
        self._prefix_label = (
            current.rstrip(" \t") if current.endswith(self._COLUMN_SEPARATOR) else None
        )
        # Record it either way, so an unclaimed prefix is judged once rather
        # than re-examined on every resize.
        self._applied_prefix = current

    def _resolve_prefix(self, label: str) -> str:
        """The prefix to display: tab column, compact, or elided label.

        Each step gives the value more room at the label's expense; the value
        itself is never traded away.
        """
        usable = self._usable_text_width()
        if usable <= 0:  # not laid out yet — keep the authored column
            return f"{label}{self._COLUMN_SEPARATOR}"

        current = super().prefix()
        value_w = self._value_text_width()
        # Hysteresis applies to each step UP only, so a field parked on a
        # threshold can't flip back and forth between two forms.
        showing_column = current.endswith(self._COLUMN_SEPARATOR)
        slack = 0 if showing_column else self._COLUMN_HYSTERESIS
        if self._tab_column_x(label) + value_w + slack <= usable:
            return f"{label}{self._COLUMN_SEPARATOR}"

        fm = self.fontMetrics()
        room = usable - value_w - fm.horizontalAdvance(self._COMPACT_SEPARATOR)
        showing_full = showing_column or current.rstrip(" ") == label
        slack = 0 if showing_full else self._COLUMN_HYSTERESIS
        if fm.horizontalAdvance(label) + slack <= room:
            return f"{label}{self._COMPACT_SEPARATOR}"
        if room <= 0:  # the value alone fills the field — drop the label
            return ""
        elided = fm.elidedText(label, QtCore.Qt.ElideRight, int(room))
        return f"{elided}{self._COMPACT_SEPARATOR}"

    def _usable_text_width(self) -> int:
        """Px of the embedded line edit actually available to draw text."""
        if not getattr(self, "_prefix_column_ready", False):
            return 0
        editor = self.lineEdit()
        if editor is None:
            return 0
        margins = editor.textMargins()
        return editor.width() - margins.left() - margins.right()

    def _tab_column_x(self, label: str) -> float:
        """X (px) at which the value starts when the label is tab-separated.

        Measured through ``QTextLayout`` rather than assumed, so it tracks the
        widget's font and whatever tab stop the running Qt defaults to.
        """
        layout = QtGui.QTextLayout(f"{label}{self._COLUMN_SEPARATOR} ", self.font())
        layout.beginLayout()
        line = layout.createLine()
        line.setLineWidth(1e6)
        layout.endLayout()
        x = line.cursorToX(len(label) + 1)
        return x[0] if isinstance(x, (tuple, list)) else x

    def _widest_value_text(self) -> str:
        """The widest string this box can show for its value, suffix included.

        The bounds pair, so :meth:`_hint_for_full_label` can correct a hint in
        the terms Qt built it with. Qt weighs ``specialValueText`` as a third
        candidate; that one is handled at the call site rather than here,
        because it is the one candidate the prefix takes no part in.
        """
        fm = self.fontMetrics()
        widest = max(
            (self.textFromValue(self.minimum()), self.textFromValue(self.maximum())),
            key=fm.horizontalAdvance,
        )
        return f"{widest}{self.suffix()}"

    def _value_text_width(self) -> float:
        """Px the widest value this box can display needs (suffix included).

        Driven by the *range* rather than the live value so ordinary editing
        can't flip the separator mid-keystroke; the current text is folded in
        so a value being typed past the bounds' width still stays visible.

        ``specialValueText`` is deliberately excluded: it is shown *instead of*
        the prefix (at the minimum only), so budgeting the column around it
        would pessimize every other value for a string the label never shares a
        field with.
        """
        fm = self.fontMetrics()
        return max(
            fm.horizontalAdvance(self._widest_value_text()),
            # One concatenated measurement, for the same reason
            # _hint_for_full_label concatenates: advance(a) + advance(b) is not
            # advance(a + b).
            fm.horizontalAdvance(f"{self.cleanText()}{self.suffix()}"),
        )
