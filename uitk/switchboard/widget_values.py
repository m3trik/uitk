# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets
from uitk.managers.value_manager import ValueManager


class SwitchboardWidgetValuesMixin:
    """What a control's value means, read and written one way: the reader /
    writer / change-signal tables behind ``toggle_multi`` and the rule family."""

    # ------------------------------------------------------------------
    # Widget value / signal plumbing shared by toggle_multi and enable_when
    # ------------------------------------------------------------------

    #: (widget type, value getter) — most-specific first. The one table behind
    #: ``toggle_multi``'s initial apply and ``enable_when``'s reads, so "what
    #: does this control's value mean" is decided once. A leading underscore
    #: names a reader on this mixin; anything else is a zero-arg widget method.
    #: signal name -> zero-arg widget getter that yields what that signal would
    #: deliver for the CURRENT state (an initial apply runs before any signal).
    _SIGNAL_VALUE_READERS = {
        "toggled": "isChecked",
        "clicked": "isChecked",
        "stateChanged": "checkState",
        "currentIndexChanged": "currentIndex",
        "currentTextChanged": "currentText",
        "textChanged": "text",
        "valueChanged": "value",
    }

    _WIDGET_VALUE_READERS = (
        (QtWidgets.QComboBox, "_combo_value"),
        (QtWidgets.QAbstractButton, "isChecked"),
        (QtWidgets.QGroupBox, "isChecked"),
        (QtWidgets.QSpinBox, "value"),
        (QtWidgets.QDoubleSpinBox, "value"),
        (QtWidgets.QAbstractSlider, "value"),
        (QtWidgets.QLineEdit, "text"),
        (QtWidgets.QPlainTextEdit, "toPlainText"),
        (QtWidgets.QTextEdit, "toPlainText"),
    )

    #: What :meth:`value_from` may WRITE — DERIVED from the reader table above,
    #: so the pair cannot drift: a rule can always write back what
    #: :meth:`enable_when` / :meth:`text_from` read. The setters themselves are
    #: NOT restated here — ``ValueManager.set_value`` already owns "how do I set
    #: this widget's value" for every one of these types (and coerces sensibly:
    #: ``"8"`` into a spin box, a truthy value into a checkable button, never a
    #: button's LABEL). Only combos are written locally, and for a reason that
    #: is combo-specific rather than a flaw in the manager — see
    #: :meth:`_set_combo_value`.
    #:
    #: Deriving it, rather than gating on ``ValueManager.is_supported_widget``,
    #: is what makes reader/writer symmetry STRUCTURAL: the two agree today
    #: (that list was corrected in the same pass), but only the derivation
    #: keeps them agreeing when a type is added to the reader table.
    _WIDGET_VALUE_WRITABLE = tuple(t for t, _ in _WIDGET_VALUE_READERS)

    #: Change signals for types the Switchboard's ``default_signals`` table
    #: (the slot-wiring SSoT) doesn't name, or names with a click-only signal
    #: (``QPushButton: clicked`` never fires on a programmatic ``setChecked``,
    #: which is exactly what a dependency rule has to see).
    _VALUE_CHANGE_SIGNALS = (
        (QtWidgets.QAbstractButton, "toggled"),
        (QtWidgets.QGroupBox, "toggled"),
        (QtWidgets.QPlainTextEdit, "textChanged"),
    )

    @staticmethod
    def _combo_value(combo):
        """A combo's value is its ``currentData`` when items carry data, else
        its index — the same reading a slot's ``currentData()`` gives, so a
        condition can be written against the payload ("fbx") not a position.
        Read through the one owner, ``ValueManager.combo_value``."""
        return ValueManager.combo_value(combo, "data", fallback="index")

    def _widget_value_reader(self, widget):
        """``getter(widget) -> value`` for *widget*, or ``None`` if untabled.

        A widget that names its own value (``state_value``: a check list's is
        its checked set) is read by it, as ``ValueManager.get_value`` and
        persistence read it.
        """
        if callable(getattr(widget, "state_value", None)):
            return lambda w: w.state_value()
        for wtype, getter in self._WIDGET_VALUE_READERS:
            if isinstance(widget, wtype):
                if getter.startswith("_"):
                    return getattr(self, getter)
                return lambda w, g=getter: getattr(w, g)()
        return None

    def _set_combo_value(self, combo, value) -> None:
        """Select the item *value* names — the inverse of :meth:`_combo_value`.

        Resolution mirrors how a combo's value is READ: item data first (the
        payload a data-backed combo reports), then the display label, then a
        plain row index. uitk's ``ComboBox`` can display RICH text, which Qt's
        ``findText`` (DisplayRole only) misses, so its own matcher gets the last
        word before the write is abandoned.

        Two deliberate departures from the combo API next door:

          * a value matching NOTHING leaves the combo untouched (and says so)
            rather than falling back to row 0 the way ``setAsCurrent`` does — a
            derived rule must never silently rewrite the user's selection to
            something its resolver did not ask for;
          * the write goes through ``setCurrentIndex``, not ``setCurrentText``,
            which is ``@Signals.blockSignals``-decorated on uitk's ``ComboBox``
            and would move the display without telling anything downstream.
        """
        # ``findData(None)`` matches the first data-less item, so a None value
        # would silently select row 0 -- and None is a non-answer, not a choice.
        if value is None:
            return
        text = str(value)
        index = combo.findData(value)
        if index < 0:
            index = combo.findText(text)
        if index < 0:
            matcher = getattr(combo, "_index_of_text", None)  # uitk rich text
            if callable(matcher):
                match = matcher(text)
                index = -1 if match is None else match
        # ``isinstance(True, int)`` is True, so without the bool guard a
        # resolver returning False would land on ROW 0 — a silent wrong
        # selection. A bool is an answer about a checkbox, never a row.
        if (
            index < 0
            and isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value < combo.count()
        ):
            index = value  # symmetric with _combo_value's index reading
        if index < 0:
            self.logger.warning(
                f"[value_from] {combo.objectName()!r} has no item for {value!r}; "
                f"selection left unchanged"
            )
            return
        combo.setCurrentIndex(index)

    def _widget_value_writer(self, widget):
        """``setter(widget, value)`` for *widget*, or ``None`` if unwritable.

        A combo is written here — :meth:`_set_combo_value` matches by item DATA
        the way :meth:`_combo_value` READS it, and goes through
        ``setCurrentIndex`` because uitk's ``ComboBox.setCurrentText`` is
        ``@Signals.blockSignals``-decorated. Everything else delegates to
        ``ValueManager.set_value``, the ecosystem's one answer to "set this
        widget's value"; the combo family is the ONLY place a uitk widget
        silences a setter, so nothing else can be surprised that way. A
        widget that names its own value (``set_state_value``) is writable
        too, as :meth:`_widget_value_reader` reads it by ``state_value``.
        """
        if isinstance(widget, QtWidgets.QComboBox):
            return self._set_combo_value
        if isinstance(widget, self._WIDGET_VALUE_WRITABLE) or callable(
            getattr(widget, "set_state_value", None)
        ):
            return ValueManager.set_value
        return None

    def _value_change_signal(self, widget):
        """Name of the signal announcing a value change on *widget*: the
        widget's own ``state_signal``, then the override table, then the
        Switchboard's ``default_signals``."""
        own = getattr(widget, "state_signal", None)
        if own and hasattr(widget, own):
            return own
        for wtype, name in self._VALUE_CHANGE_SIGNALS:
            if isinstance(widget, wtype) and hasattr(widget, name):
                return name
        for wtype, name in getattr(self, "default_signals", {}).items():
            if isinstance(widget, wtype) and hasattr(widget, name):
                return name
        return None

    def _resolve_ui_widget(self, ui, ref):
        """Resolve a widget reference — an instance or an objectName on *ui*."""
        if isinstance(ref, QtWidgets.QWidget):
            return ref
        return getattr(ui, ref, None) if isinstance(ref, str) else None

    def _read_signal_value(self, widget, signal):
        """The value a *signal* would deliver for the widget's CURRENT state —
        what an initial apply needs, since no signal has fired yet."""
        reader = self._SIGNAL_VALUE_READERS.get(signal)
        if reader and hasattr(widget, reader):
            value = getattr(widget, reader)()
            # PySide6 hands ``checkState()`` back as a Qt.CheckState enum while
            # ``stateChanged`` delivers the int — match what the signal sends.
            return getattr(value, "value", value)
        getter = self._widget_value_reader(widget)
        return getter(widget) if getter is not None else None
