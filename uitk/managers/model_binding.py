# !/usr/bin/python
# coding=utf-8
"""Keep widgets in step with a model uitk never sees: read on change, write on edit.

A panel whose fields ARE some document's values -- a scene setting, a record a
build reads -- must not keep a second copy of them in QSettings: a restore
lands after the panel read the document and writes the last value set in ANY
session over it. :class:`ModelBinding` is the one shape for such fields. The
model is reached only through two callables, so uitk names no domain: *read()*
returns the model's current values as a mapping, *write(field, value)* stores
one. A bound widget opts out of the panel's state restore, is filled from the
model by :meth:`ModelBinding.refresh`, and writes the model when the user
edits it; the caller hooks :meth:`ModelBinding.refresh` to the model's own
change events.
"""

import contextlib
import logging
from typing import Any, Callable, ContextManager, Dict, Mapping, Optional, Tuple

from qtpy import QtWidgets

from uitk.managers.value_manager import ValueManager

_log = logging.getLogger(__name__)


class ModelBinding:
    """Two-way binding between widgets and the fields of an external model.

    Parameters:
        read: ``() -> Mapping[str, Any]`` -- the model's current values.
        write: ``(field, value) -> Any`` -- store one value.
        applying: ``() -> context manager`` entered while :meth:`refresh`
            fills the widgets -- a panel's ``ui.state.suppress_save``: the
            values are applied FOR the user, so a handler that turns one
            field's edit into others' (a ``link_spinboxes`` lock) only
            re-baselines, a readout bound to a field still updates, and
            nothing persists them. Without one the widgets' signals are
            blocked while they are filled.

    Example::

        binding = ModelBinding(
            read=lambda: store.recipe.to_dict(),
            write=lambda field, value: store.update(**{field: value}),
        )
        binding.bind("period", spn_period)
        binding.bind("duty", spn_duty, getter=lambda: spn_duty.value() / 100.0,
                     setter=lambda v: spn_duty.setValue(round(v * 100)))
        store.on_change(binding.refresh)
        binding.refresh()
    """

    #: The signal a widget announces an edit on, by type -- the first match
    #: wins, after an explicit ``signal`` and the widget's own ``state_signal``.
    EDIT_SIGNALS: Tuple[Tuple[type, str], ...] = (
        (QtWidgets.QSpinBox, "valueChanged"),
        (QtWidgets.QDoubleSpinBox, "valueChanged"),
        (QtWidgets.QAbstractSlider, "valueChanged"),
        (QtWidgets.QAbstractButton, "toggled"),
        (QtWidgets.QComboBox, "currentIndexChanged"),
        (QtWidgets.QLineEdit, "editingFinished"),
    )

    def __init__(
        self,
        read: Callable[[], Mapping[str, Any]],
        write: Callable[[str, Any], Any],
        applying: Optional[Callable[[], ContextManager]] = None,
    ):
        self._read = read
        self._write = write
        self._applying = applying
        #: field -> (widget, getter, setter)
        self._fields: Dict[str, Tuple[QtWidgets.QWidget, Callable, Callable]] = {}
        self._syncing = False
        #: Depth of writes in flight -- a model change they cause is this
        #: binding's own echo (see :meth:`refresh`).
        self._writing = 0

    def bind(
        self,
        field: str,
        widget: QtWidgets.QWidget,
        getter: Optional[Callable[[], Any]] = None,
        setter: Optional[Callable[[Any], Any]] = None,
        signal: Optional[str] = None,
    ) -> QtWidgets.QWidget:
        """Bind *widget* to the model's *field*.

        Parameters:
            field: The model key.
            widget: The editor. Its ``restore_state`` is turned off: the model
                owns the value.
            getter: ``() -> value`` in the MODEL's terms; ``ValueManager``
                reads the widget when omitted. Give one to convert (a percent
                field over a fraction).
            setter: ``(value) -> None``, the inverse; ``ValueManager`` writes
                the widget when omitted.
            signal: The edit signal's name; see :attr:`EDIT_SIGNALS`.

        Returns:
            *widget*.

        Raises:
            ValueError: No edit signal is known for *widget*.
        """
        name = (
            signal or getattr(widget, "state_signal", None) or self._signal_for(widget)
        )
        if not name or not hasattr(widget, name):
            raise ValueError(
                f"ModelBinding.bind: no edit signal known for {type(widget).__name__}; "
                "pass signal=."
            )
        widget.restore_state = False
        getter = getter or (lambda w=widget: ValueManager.get_value(w))
        setter = setter or (lambda value, w=widget: ValueManager.set_value(w, value))
        self._fields[field] = (widget, getter, setter)
        getattr(widget, name).connect(lambda *_args, f=field: self._on_edit(f))
        return widget

    @classmethod
    def _signal_for(cls, widget) -> Optional[str]:
        for kind, name in cls.EDIT_SIGNALS:
            if isinstance(widget, kind):
                return name
        return None

    def refresh(self, *_args) -> None:
        """Fill every bound widget from the model, writing nothing back.

        Inside the *applying* context when the binding has one (the widgets'
        own signals flow, marked as applied for the user); otherwise with each
        widget's signals blocked. A widget deleted under the binding is dropped
        from it. A model that cannot be read leaves the widgets as they are,
        and is logged.

        A no-op while one of the binding's own writes is in flight: the change
        the model announces is the edit already on screen, and an edit that
        moves other fields with it (a linked pair) is still landing -- filling
        the widgets then put back the model's not-yet-written values.
        """
        if self._writing:
            return
        try:
            values = self._read() or {}
        except Exception as error:
            _log.warning(
                "ModelBinding.refresh: the model could not be read (%r); "
                "the widgets keep their values.",
                error,
            )
            return
        self._syncing = True
        try:
            with self._applying() if self._applying else contextlib.nullcontext():
                for field, (widget, _getter, setter) in list(self._fields.items()):
                    if field not in values:
                        continue
                    try:
                        if self._applying:
                            setter(values[field])
                            continue
                        blocked = widget.blockSignals(True)
                        try:
                            setter(values[field])
                        finally:
                            widget.blockSignals(blocked)
                    except RuntimeError:  # the C++ widget is gone
                        self._fields.pop(field, None)
        finally:
            self._syncing = False

    def _on_edit(self, field: str) -> None:
        """The user changed *field*'s widget: store its value in the model."""
        if self._syncing or field not in self._fields:
            return
        _widget, getter, _setter = self._fields[field]
        self._writing += 1
        try:
            self._write(field, getter())
        finally:
            self._writing -= 1
