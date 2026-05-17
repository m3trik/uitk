# !/usr/bin/python
# coding=utf-8
"""Factory for building / reading / writing dynamic-attribute editor widgets.

The widget-construction surface shared by :class:`AttributeWindow` and any
external consumer (``mayatk.mat_utils.marmoset_bridge``,
``metashape_workflow.metashape_workflow_slots``, …). Keep this module's
contract stable so consumers can depend on it without coupling to the
window class.

Two consumer entry points:

* **Value-driven** (AttributeWindow style)::

      spec = AttributeSpec.from_value("Opacity", 0.5)   # kind inferred from type
      widget = make_widget(spec)

* **Spec-driven** (marmoset_bridge style)::

      spec = AttributeSpec(
          key="BAKE_WIDTH", label="Width", kind="int",
          default=2048, minimum=64, maximum=8192, step=64,
          tooltip="Bake output width in pixels.",
      )
      widget = make_widget(spec)

The kind a widget was built for is stamped onto it via ``setProperty`` so
``read_value`` / ``set_value`` / ``connect_changed`` work on a bare widget
without the caller needing to remember the spec.

Adding a new kind from outside the package::

    register_kind(
        "bool_richtext",
        KindHandler(build=..., read=..., write=..., signal="stateChanged"),
    )
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Union

from qtpy import QtWidgets

from uitk.widgets.doubleSpinBox import DoubleSpinBox

ChoiceItem = Union[Any, Tuple[str, Any]]
ChoicesSeq = Sequence[ChoiceItem]

INT_MIN = -2147483648
INT_MAX = 2147483647
FLOAT_MIN = -1e100
FLOAT_MAX = 1e100

_KIND_PROP = "_attr_kind"


@dataclass(frozen=True)
class AttributeSpec:
    """Description of one editable attribute / parameter.

    Attributes:
        key: Identifier used as the widget's objectName. Required, non-empty.
        label: Display label. Defaults to *key* if empty.
        kind: One of the registered kinds (``"bool" | "int" | "float" |
            "str" | "choice" | "path"``) or ``"auto"`` to derive from
            ``type(default)``. Custom kinds added via :func:`register_kind`
            are also accepted.
        default: Initial widget value. Required for ``kind="auto"``.
        minimum / maximum / step: Numeric range and step (int/float kinds).
        decimals: Float precision (float kind only).
        choices: Either a sequence of values (``["Low", "Medium"]``) or a
            sequence of ``(label, value)`` pairs (marmoset style). The
            value is what :func:`read_value` returns.
        tooltip: Tooltip applied to the widget.
    """

    key: str
    label: str = ""
    kind: str = "auto"
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None
    decimals: int = 0
    choices: Optional[ChoicesSeq] = None
    tooltip: str = ""

    def __post_init__(self):
        # An empty key produces a widget with empty objectName that can't be
        # found via `getattr(ui, name)` — silently breaks lookup downstream.
        if not self.key:
            raise ValueError("AttributeSpec.key must be a non-empty string.")

    @classmethod
    def from_value(cls, key: str, value: Any, *, label: str = "") -> "AttributeSpec":
        """Build a minimal spec from a Python value (AttributeWindow style)."""
        return cls(
            key=key,
            label=label or key,
            kind=infer_kind(value),
            default=value,
        )

    @property
    def display_label(self) -> str:
        return self.label or self.key


@dataclass(frozen=True)
class KindHandler:
    """Bundle of callables that build / read / write a widget kind.

    Either ``signal`` (the name of a Qt signal on the built widget) or
    ``connect`` (a custom ``(widget, callback) -> None`` wirer) must be
    provided. ``connect`` wins when both are set; use it for composite
    widgets whose change signal lives on an inner child (e.g. ``path``).
    """

    build: Callable[[AttributeSpec, Optional[QtWidgets.QWidget]], QtWidgets.QWidget]
    read: Callable[[QtWidgets.QWidget], Any]
    write: Callable[[QtWidgets.QWidget, Any], None]
    signal: Optional[str] = None
    connect: Optional[Callable[[QtWidgets.QWidget, Callable[[Any], None]], None]] = None

    def __post_init__(self):
        # Surface malformed handlers at construction, not at registration time.
        if self.signal is None and self.connect is None:
            raise ValueError(
                "KindHandler must provide either `signal` (Qt signal name) "
                "or `connect` (custom wirer)."
            )


_HANDLERS: Dict[str, KindHandler] = {}


# ---------------------------------------------------------------------------
# Type inference (mirrors AttributeWindow's original type_to_widget mapping).
# ---------------------------------------------------------------------------

def infer_kind(value: Any) -> str:
    """Map a Python value to one of the built-in kinds.

    Order matters: ``bool`` is a subclass of ``int``, so check bool first.
    """
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    return "str"


# ---------------------------------------------------------------------------
# Public factory surface.
# ---------------------------------------------------------------------------

def register_kind(name: str, handler: KindHandler) -> None:
    """Register a new kind (or override an existing one).

    The handler's signal/connect contract is enforced by
    :meth:`KindHandler.__post_init__`, so by the time this is called the
    handler is guaranteed valid.
    """
    _HANDLERS[name] = handler


def get_handler(kind: str) -> KindHandler:
    """Return the handler for *kind* (raises KeyError if unregistered)."""
    if kind not in _HANDLERS:
        raise KeyError(
            f"No KindHandler registered for {kind!r}. "
            f"Known kinds: {sorted(_HANDLERS)}"
        )
    return _HANDLERS[kind]


def make_widget(
    spec: AttributeSpec, parent: Optional[QtWidgets.QWidget] = None
) -> QtWidgets.QWidget:
    """Build a Qt widget for *spec*."""
    kind = spec.kind if spec.kind != "auto" else infer_kind(spec.default)
    handler = get_handler(kind)
    widget = handler.build(spec, parent)
    widget.setObjectName(spec.key)
    if spec.tooltip:
        widget.setToolTip(spec.tooltip)
    widget.setProperty(_KIND_PROP, kind)
    return widget


def _widget_kind(widget: QtWidgets.QWidget) -> str:
    kind = widget.property(_KIND_PROP)
    if not kind:
        raise ValueError(
            f"Widget {widget!r} was not produced by make_widget "
            f"(missing {_KIND_PROP!r} property)."
        )
    return kind


def read_value(widget: QtWidgets.QWidget) -> Any:
    """Return the current value of a factory-built widget."""
    return get_handler(_widget_kind(widget)).read(widget)


def set_value(widget: QtWidgets.QWidget, value: Any) -> None:
    """Set the value of a factory-built widget."""
    get_handler(_widget_kind(widget)).write(widget, value)


def connect_changed(
    widget: QtWidgets.QWidget, callback: Callable[[Any], None]
) -> None:
    """Wire the widget's value-change signal to ``callback(new_value)``."""
    handler = get_handler(_widget_kind(widget))
    if handler.connect is not None:
        handler.connect(widget, callback)
        return
    getattr(widget, handler.signal).connect(
        lambda *_: callback(handler.read(widget))
    )


# ---------------------------------------------------------------------------
# Built-in kind handlers.
# ---------------------------------------------------------------------------

# ---- bool: QCheckBox -------------------------------------------------------

def _build_bool(spec, parent):
    w = QtWidgets.QCheckBox(parent)
    if spec.default is not None:
        w.setChecked(bool(spec.default))
    return w


def _read_bool(widget):
    return widget.isChecked()


def _write_bool(widget, value):
    widget.setChecked(bool(value))


# ---- int: QSpinBox ---------------------------------------------------------

def _build_int(spec, parent):
    w = QtWidgets.QSpinBox(parent)
    w.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
    w.setMinimum(int(spec.minimum) if spec.minimum is not None else INT_MIN)
    w.setMaximum(int(spec.maximum) if spec.maximum is not None else INT_MAX)
    if spec.step is not None:
        w.setSingleStep(int(spec.step))
    if spec.default is not None:
        w.setValue(int(spec.default))
    return w


def _read_int(widget):
    return widget.value()


def _write_int(widget, value):
    widget.setValue(int(value))


# ---- float: DoubleSpinBox --------------------------------------------------

def _build_float(spec, parent):
    w = DoubleSpinBox(parent)
    w.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
    w.setDecimals(spec.decimals or 4)
    w.setMinimum(float(spec.minimum) if spec.minimum is not None else FLOAT_MIN)
    w.setMaximum(float(spec.maximum) if spec.maximum is not None else FLOAT_MAX)
    if spec.step is not None:
        w.setSingleStep(float(spec.step))
    if spec.default is not None:
        w.setValue(float(spec.default))
    return w


def _read_float(widget):
    return widget.value()


def _write_float(widget, value):
    widget.setValue(float(value))


# ---- str: QLineEdit --------------------------------------------------------

def _build_str(spec, parent):
    w = QtWidgets.QLineEdit(parent)
    if spec.default is not None:
        w.setText(str(spec.default))
    return w


def _read_str(widget):
    return widget.text()


def _write_str(widget, value):
    widget.setText("" if value is None else str(value))


# ---- choice: QComboBox -----------------------------------------------------
#
# Accepts ``choices`` as either ``["a", "b"]`` (label==value, metashape style)
# or ``[("a", 1), ("b", 2)]`` (label/value pair, marmoset style).
# ``read_value`` returns the value (itemData when present, else text).
# ``write_value`` matches by itemData first, then text.

def _build_choice(spec, parent):
    w = QtWidgets.QComboBox(parent)
    for entry in spec.choices or []:
        if isinstance(entry, tuple) and len(entry) == 2:
            label, value = entry
            w.addItem(str(label), value)
        else:
            w.addItem(str(entry))   # itemData defaults to None
    if spec.default is not None:
        _write_choice(w, spec.default)
    return w


def _read_choice(widget):
    data = widget.currentData()
    return widget.currentText() if data is None else data


def _write_choice(widget, value):
    for i in range(widget.count()):
        if widget.itemData(i) == value:
            widget.setCurrentIndex(i)
            return
    idx = widget.findText(str(value))
    if idx >= 0:
        widget.setCurrentIndex(idx)


# ---- path: composite (QLineEdit + browse button) ---------------------------
#
# Mirrors the composite widget used by marmoset_bridge: the container's
# ``_line_edit`` attribute exposes the QLineEdit so external code (and the
# read/write helpers below) can find it without walking children.

def _build_path(spec, parent):
    container = QtWidgets.QWidget(parent)
    hl = QtWidgets.QHBoxLayout(container)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(2)
    edit = QtWidgets.QLineEdit("" if spec.default is None else str(spec.default))
    browse = QtWidgets.QPushButton("...")
    browse.setFixedWidth(22)
    hl.addWidget(edit, 1)
    hl.addWidget(browse)
    container._line_edit = edit  # noqa: SLF001 — intentional public attr on container

    def _on_browse():
        start = edit.text() or ""
        path = QtWidgets.QFileDialog.getExistingDirectory(
            container, "Select directory", start
        )
        if path:
            edit.setText(path)

    browse.clicked.connect(_on_browse)
    return container


def _read_path(widget):
    return widget._line_edit.text()


def _write_path(widget, value):
    widget._line_edit.setText("" if value is None else str(value))


def _connect_path(widget, callback):
    widget._line_edit.textChanged.connect(lambda *_: callback(_read_path(widget)))


# ---------------------------------------------------------------------------
# Register the built-ins.
# ---------------------------------------------------------------------------

register_kind("bool",   KindHandler(_build_bool,   _read_bool,   _write_bool,   signal="stateChanged"))
register_kind("int",    KindHandler(_build_int,    _read_int,    _write_int,    signal="valueChanged"))
register_kind("float",  KindHandler(_build_float,  _read_float,  _write_float,  signal="valueChanged"))
register_kind("str",    KindHandler(_build_str,    _read_str,    _write_str,    signal="textChanged"))
register_kind("choice", KindHandler(_build_choice, _read_choice, _write_choice, signal="currentIndexChanged"))
register_kind("path",   KindHandler(_build_path,   _read_path,   _write_path,   connect=_connect_path))
