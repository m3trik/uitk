# !/usr/bin/python
# coding=utf-8
"""Attribute spec + kind-handler registry for parameterised forms.

Originally lived at ``uitk.widgets.attributeWindow._factory``; moved
here so DCC-bridge code and the AttributeWindow panels share one
registry instead of maintaining parallel ones. The old import path
remains as a back-compat shim that re-exports from this module.

Per-kind contract: a :class:`KindHandler` bundles four callables --

* ``build(spec, parent)`` -- construct the Qt widget,
* ``read(widget)`` -- extract its current value,
* ``write(widget, value)`` -- push a value into it,
* ``signal`` (or ``connect``) -- emit when the value changes.

New kinds are registered via :func:`register_kind`. ``make_widget``
stamps the resolved kind on the widget so ``read_value`` /
``set_value`` / ``connect_changed`` can look up the handler from a
bare widget reference.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from qtpy import QtWidgets

from uitk.widgets.checkBox import CheckBox
from uitk.widgets.doubleSpinBox import DoubleSpinBox
from uitk.widgets.spinBox import SpinBox


ChoiceItem = Union[Any, Tuple[str, Any]]
ChoicesSeq = Sequence[ChoiceItem]

INT_MIN = -2147483648
INT_MAX = 2147483647
FLOAT_MIN = -1e100
FLOAT_MAX = 1e100

_KIND_PROP = "_attr_kind"


@dataclass(frozen=True)
class AttributeSpec:
    """Description of one editable attribute / bridge parameter.

    A single dataclass shape covers both AttributeWindow's auto-from-value
    panels and the DCC bridges' explicit registries. The bridges always
    set ``kind`` explicitly (``"int"``, ``"choice"``, ``"path"``,
    ``"file_list"``, ...); AttributeWindow leaves it at ``"auto"`` and
    resolves it from ``type(default)`` via :func:`infer_kind`.

    Attributes:
        key: Identifier used as the widget's objectName. Required.
        label: Display label. Defaults to *key* if empty.
        kind: One of the registered kinds (``"bool" | "int" | "float" |
            "str" | "choice" | "path" | "file_list"``) or ``"auto"`` to
            derive from ``type(default)``. Custom kinds added via
            :func:`register_kind` are also accepted.
        default: Initial widget value.
        minimum / maximum / step: Numeric range and step (int/float kinds).
        decimals: Float precision (float kind only).
        choices: For ``"choice"`` -- either a sequence of values
            (``["Low", "Medium"]``) or a sequence of ``(label, value)``
            pairs. The value is what :func:`read_value` returns.
        tooltip: Tooltip text. The DCC-bridge slots feed this through
            :func:`uitk.bridge.tooltip.format_param_tooltip` to build
            a rich-text version with type/range/default rows.
        section: Optional category label. A builder that groups specs (e.g.
            :class:`uitk.bridge.BridgeSlotsBase`) inserts a titled
            :class:`~uitk.widgets.separator.Separator` before the first spec of
            each new section, so related params read as a labelled block.
            Empty (default) = no divider. Sections are expected contiguous in
            iteration order.
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
    section: str = ""

    def __post_init__(self):
        # An empty key produces a widget with empty objectName that can't be
        # found via `getattr(ui, name)` -- silently breaks lookup downstream.
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
    Lists / tuples deliberately fall through to ``"str"`` -- the
    ``file_list`` kind is a multi-file picker (specific UX), not the
    natural rendering for arbitrary list-valued attributes (vector3
    components, multi-int arrays, etc.). Set ``kind="file_list"``
    explicitly when you actually want a file picker.
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
    """Register a new kind (or override an existing one)."""
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
    """Build a Qt widget for *spec*. Stamps the resolved kind for later lookup."""
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

# ---- bool: uitk CheckBox ---------------------------------------------------
#
# Uses uitk's CheckBox (QCheckBox subclass) rather than the plain Qt one,
# with an explicit "On" / "Off" label that flips on state change. Two
# reasons:
#
# 1. Under the uitk theme, the native checkbox indicator can render very
#    small or invisible depending on the host stylesheet; the text label
#    is an unambiguous secondary indicator that always survives.
# 2. Unifying the bridge bool widget (which historically did this) with
#    AttributeWindow's bool widget (which historically used plain
#    QCheckBox) -- both now show the same artefact for any consumer that
#    builds via :func:`make_widget`. AttributeWindow callers that want
#    a label-less checkbox can ``widget.setText("")`` after construction
#    or register a custom kind.

def _build_bool(spec, parent):
    w = CheckBox(parent)
    if spec.default is not None:
        w.setChecked(bool(spec.default))
    w.setText("On" if w.isChecked() else "Off")
    w.set_checkbox_rich_text_style(w.isChecked())
    w.stateChanged.connect(
        lambda state, btn=w: btn.setText("On" if state else "Off")
    )
    return w


def _read_bool(widget):
    return widget.isChecked()


def _write_bool(widget, value):
    widget.setChecked(bool(value))


# ---- int: uitk SpinBox -----------------------------------------------------
#
# uitk's SpinBox derives from QDoubleSpinBox but returns ``int`` from
# ``value()`` when ``decimals == 0`` -- which is what we want here. Using
# it (rather than plain ``QSpinBox``) gives AttributeWindow int rows the
# same modifier-driven wheel stepping as float rows (Ctrl, Ctrl+Shift,
# Alt, Ctrl+Alt). The plain Qt widget would have silently dropped those.

def _build_int(spec, parent):
    # SpinBox defaults to ``decimals=0`` -> ``value()`` returns ``int``.
    w = SpinBox(parent)
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
# Accepts ``choices`` as either ``["a", "b"]`` (label==value) or
# ``[("a", 1), ("b", 2)]`` (explicit label/value). ``read_value`` returns
# the value (itemData when present, else text). ``write_value`` matches
# by itemData first, then text.

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
# The container's ``_line_edit`` attribute exposes the QLineEdit so external
# code (and the read/write helpers below) can find it without walking
# children. The browse button height matches the 19px row clamp used by
# the bridge panels; AttributeWindow doesn't clamp the row so the larger
# control still works there.

def _build_path(spec, parent):
    container = QtWidgets.QWidget(parent)
    hl = QtWidgets.QHBoxLayout(container)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(2)
    edit = QtWidgets.QLineEdit("" if spec.default is None else str(spec.default))
    # Name the inner edit (mirrors make_widget's container objectName == spec.key)
    # so preset capture keys it: consumers that snapshot the value-bearing child
    # rather than the container (e.g. the DCC bridges substitute ``_line_edit``
    # into their managed set) skip empty-objectName widgets, silently dropping
    # path fields from saved widget-state presets.
    edit.setObjectName(spec.key)
    edit.setMinimumHeight(19)
    edit.setMaximumHeight(19)
    browse = QtWidgets.QPushButton("...")
    browse.setFixedWidth(22)
    browse.setMinimumHeight(19)
    browse.setMaximumHeight(19)
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


# ---- file_list: composite (QListWidget + Add / Remove buttons) -------------
#
# Multi-file picker producing a ``list[str]``. The container's
# ``_list_widget`` attribute exposes the QListWidget. Used by substance's
# baked-maps row but generally useful for any "pick N files" interaction.

def _build_file_list(spec, parent):
    container = QtWidgets.QWidget(parent)
    grid = QtWidgets.QGridLayout(container)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(2)
    grid.setVerticalSpacing(2)

    list_widget = QtWidgets.QListWidget(container)
    list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    list_widget.setMinimumHeight(48)
    list_widget.setMaximumHeight(80)
    for item in (spec.default or []):
        list_widget.addItem(str(item))

    add_btn = QtWidgets.QPushButton("Add...", container)
    add_btn.setMinimumHeight(19)
    add_btn.setMaximumHeight(19)
    rm_btn = QtWidgets.QPushButton("Remove", container)
    rm_btn.setMinimumHeight(19)
    rm_btn.setMaximumHeight(19)

    def _browse_files():
        # Anchor at the directory of the first item if any, else home.
        start = ""
        if list_widget.count():
            try:
                from pathlib import Path
                start = str(Path(list_widget.item(0).text()).parent)
            except Exception:  # noqa: BLE001
                start = ""
        if not start:
            from pathlib import Path
            start = str(Path.home())
        paths, _filter = QtWidgets.QFileDialog.getOpenFileNames(
            container,
            "Select files",
            start,
            "Images (*.png *.tif *.tiff *.exr *.tga *.jpg *.jpeg *.psd);;"
            "All files (*)",
        )
        existing = {list_widget.item(i).text() for i in range(list_widget.count())}
        for path in paths:
            if path and path not in existing:
                list_widget.addItem(path)

    def _remove_selected():
        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))

    add_btn.clicked.connect(_browse_files)
    rm_btn.clicked.connect(_remove_selected)

    grid.addWidget(list_widget, 0, 0, 2, 1)
    grid.addWidget(add_btn, 0, 1)
    grid.addWidget(rm_btn, 1, 1)
    grid.setColumnStretch(0, 1)
    container._list_widget = list_widget  # noqa: SLF001
    return container


def _read_file_list(widget) -> List[str]:
    lw = widget._list_widget
    return [lw.item(i).text() for i in range(lw.count())]


def _write_file_list(widget, value) -> None:
    lw = widget._list_widget
    lw.clear()
    for item in (value or []):
        lw.addItem(str(item))


def _connect_file_list(widget, callback):
    widget._list_widget.model().rowsInserted.connect(
        lambda *_: callback(_read_file_list(widget))
    )
    widget._list_widget.model().rowsRemoved.connect(
        lambda *_: callback(_read_file_list(widget))
    )


# ---------------------------------------------------------------------------
# Register the built-ins.
# ---------------------------------------------------------------------------

register_kind("bool",      KindHandler(_build_bool,      _read_bool,      _write_bool,      signal="stateChanged"))
register_kind("int",       KindHandler(_build_int,       _read_int,       _write_int,       signal="valueChanged"))
register_kind("float",     KindHandler(_build_float,     _read_float,     _write_float,     signal="valueChanged"))
register_kind("str",       KindHandler(_build_str,       _read_str,       _write_str,       signal="textChanged"))
register_kind("choice",    KindHandler(_build_choice,    _read_choice,    _write_choice,    signal="currentIndexChanged"))
register_kind("path",      KindHandler(_build_path,      _read_path,      _write_path,      connect=_connect_path))
register_kind("file_list", KindHandler(_build_file_list, _read_file_list, _write_file_list, connect=_connect_file_list))
