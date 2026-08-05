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
* ``signal`` (or ``connect``) -- emit when the value changes,
* ``set_choices(widget, choices)`` -- optional; repopulate the entries of a
  choice-driven kind (``choice`` / ``check_list``) after build, so a panel can
  discover them at runtime (installed app versions, deployable scripts, scene
  contents) instead of hard-coding them in the registry.

New kinds are registered via :meth:`KindFactory.register_kind`.
:meth:`KindFactory.make_widget` stamps the resolved kind on the widget
so :meth:`KindFactory.read_value` / :meth:`~KindFactory.set_value` /
:meth:`~KindFactory.connect_changed` can look up the handler from a
bare widget reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from qtpy import QtCore, QtWidgets

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

#: Marker for a bare ``choices`` entry (label == value, no explicit data).
_NO_VALUE = object()


@dataclass(frozen=True)
class AttributeSpec:
    """Description of one editable attribute / bridge parameter.

    A single dataclass shape covers both AttributeWindow's auto-from-value
    panels and the DCC bridges' explicit registries. The bridges always
    set ``kind`` explicitly (``"int"``, ``"choice"``, ``"path"``,
    ``"file_list"``, ...); AttributeWindow leaves it at ``"auto"`` and
    resolves it from ``type(default)`` via :meth:`KindFactory.infer_kind`.

    Attributes:
        key: Identifier used as the widget's objectName. Required.
        label: Display label. Defaults to *key* if empty.
        kind: One of the registered kinds (``"bool" | "int" | "float" |
            "str" | "choice" | "check_list" | "path" | "file_list" |
            "action"``) or ``"auto"`` to derive from ``type(default)``.
            Custom kinds added via :meth:`KindFactory.register_kind` are
            also accepted.
        default: Initial widget value.
        minimum / maximum / step: Numeric range and step (int/float kinds).
        decimals: Float precision (float kind only).
        choices: For the choice-driven kinds (``"choice"``, ``"check_list"``)
            -- a sequence of values (``["Low", "Medium"]``), of
            ``(label, value)`` pairs, or of ``(label, value, tooltip)``
            triples. The value is what :meth:`KindFactory.read_value` returns
            (``check_list`` returns the list of checked ones). Leave empty and
            call :meth:`KindFactory.set_choices` when the entries are only
            known at runtime.
        tooltip: Tooltip text. The DCC-bridge slots feed this through
            :meth:`uitk.bridge.tooltip.Tooltip.format_param_tooltip` to build
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
            kind=KindFactory.infer_kind(value),
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

    ``set_choices`` is optional and only meaningful for kinds that render a
    fixed entry set; kinds without one reject
    :meth:`KindFactory.set_choices` rather than silently no-op'ing.
    """

    build: Callable[[AttributeSpec, Optional[QtWidgets.QWidget]], QtWidgets.QWidget]
    read: Callable[[QtWidgets.QWidget], Any]
    write: Callable[[QtWidgets.QWidget, Any], None]
    signal: Optional[str] = None
    connect: Optional[Callable[[QtWidgets.QWidget, Callable[[Any], None]], None]] = None
    set_choices: Optional[Callable[[QtWidgets.QWidget, ChoicesSeq], None]] = None

    def __post_init__(self):
        # Surface malformed handlers at construction, not at registration time.
        if self.signal is None and self.connect is None:
            raise ValueError(
                "KindHandler must provide either `signal` (Qt signal name) "
                "or `connect` (custom wirer)."
            )


class _KindFactoryInternal(object):
    """Registry + built-in per-kind build/read/write helpers for KindFactory."""

    _HANDLERS: Dict[str, KindHandler] = {}

    @staticmethod
    def _widget_kind(widget: QtWidgets.QWidget) -> str:
        kind = widget.property(_KIND_PROP)
        if not kind:
            raise ValueError(
                f"Widget {widget!r} was not produced by make_widget "
                f"(missing {_KIND_PROP!r} property)."
            )
        return kind

    # -----------------------------------------------------------------------
    # Built-in kind handlers.
    # -----------------------------------------------------------------------

    # ---- bool: uitk CheckBox ----------------------------------------------
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
    #    builds via :meth:`KindFactory.make_widget`. AttributeWindow callers
    #    that want a label-less checkbox can ``widget.setText("")`` after
    #    construction or register a custom kind.

    @staticmethod
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

    @staticmethod
    def _read_bool(widget):
        return widget.isChecked()

    @staticmethod
    def _write_bool(widget, value):
        widget.setChecked(bool(value))

    # ---- int: uitk SpinBox ------------------------------------------------
    #
    # uitk's SpinBox derives from QDoubleSpinBox but returns ``int`` from
    # ``value()`` when ``decimals == 0`` -- which is what we want here. Using
    # it (rather than plain ``QSpinBox``) gives AttributeWindow int rows the
    # same modifier-driven wheel stepping as float rows (Ctrl, Ctrl+Shift,
    # Alt, Ctrl+Alt). The plain Qt widget would have silently dropped those.

    @staticmethod
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

    @staticmethod
    def _read_int(widget):
        return widget.value()

    @staticmethod
    def _write_int(widget, value):
        widget.setValue(int(value))

    # ---- float: DoubleSpinBox ---------------------------------------------

    @staticmethod
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

    @staticmethod
    def _read_float(widget):
        return widget.value()

    @staticmethod
    def _write_float(widget, value):
        widget.setValue(float(value))

    # ---- str: QLineEdit ---------------------------------------------------

    @staticmethod
    def _build_str(spec, parent):
        w = QtWidgets.QLineEdit(parent)
        if spec.default is not None:
            w.setText(str(spec.default))
        return w

    @staticmethod
    def _read_str(widget):
        return widget.text()

    @staticmethod
    def _write_str(widget, value):
        widget.setText("" if value is None else str(value))

    # ---- choice: QComboBox ------------------------------------------------
    #
    # Accepts ``choices`` as ``["a", "b"]`` (label==value),
    # ``[("a", 1), ("b", 2)]`` (explicit label/value) or
    # ``[("a", 1, "tip")]`` (with a per-entry tooltip). ``read_value`` returns
    # the value (itemData when present, else text). ``write_value`` matches
    # by itemData first, then text.

    @staticmethod
    def _split_choice(entry) -> Tuple[Any, Any, str]:
        """Normalize one ``choices`` entry to ``(label, value, tooltip)``.

        A bare entry yields ``_NO_VALUE`` so the combo keeps its historical
        "itemData stays None" behaviour (``read`` then falls back to the text)
        rather than round-tripping ``str(entry)`` as the value.
        """
        if isinstance(entry, tuple):
            if len(entry) == 3:
                return entry[0], entry[1], str(entry[2] or "")
            if len(entry) == 2:
                return entry[0], entry[1], ""
        return entry, _NO_VALUE, ""

    @staticmethod
    def _build_choice(spec, parent):
        w = QtWidgets.QComboBox(parent)
        _KindFactoryInternal._set_choices_choice(w, spec.choices or [])
        if spec.default is not None:
            _KindFactoryInternal._write_choice(w, spec.default)
        return w

    @staticmethod
    def _set_choices_choice(widget, choices) -> None:
        """(Re)fill the combo, keeping the current value when it survives."""
        current = _KindFactoryInternal._read_choice(widget) if widget.count() else None
        widget.clear()
        for entry in choices or []:
            label, value, tip = _KindFactoryInternal._split_choice(entry)
            if value is _NO_VALUE:
                widget.addItem(str(label))  # itemData defaults to None
            else:
                widget.addItem(str(label), value)
            if tip:
                widget.setItemData(widget.count() - 1, tip, QtCore.Qt.ToolTipRole)
        if current is not None:
            _KindFactoryInternal._write_choice(widget, current)

    @staticmethod
    def _read_choice(widget):
        data = widget.currentData()
        return widget.currentText() if data is None else data

    @staticmethod
    def _write_choice(widget, value):
        for i in range(widget.count()):
            if widget.itemData(i) == value:
                widget.setCurrentIndex(i)
                return
        idx = widget.findText(str(value))
        if idx >= 0:
            widget.setCurrentIndex(idx)

    # ---- path: composite (QLineEdit + browse button) ----------------------
    #
    # The container's ``_line_edit`` attribute exposes the QLineEdit so external
    # code (and the read/write helpers below) can find it without walking
    # children. The browse button height matches the 19px row clamp used by
    # the bridge panels; AttributeWindow doesn't clamp the row so the larger
    # control still works there.

    @staticmethod
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

    @staticmethod
    def _read_path(widget):
        return widget._line_edit.text()

    @staticmethod
    def _write_path(widget, value):
        widget._line_edit.setText("" if value is None else str(value))

    @staticmethod
    def _connect_path(widget, callback):
        widget._line_edit.textChanged.connect(
            lambda *_: callback(_KindFactoryInternal._read_path(widget))
        )

    # ---- file_list: composite (QListWidget + Add / Remove buttons) --------
    #
    # Multi-file picker producing a ``list[str]``. The container's
    # ``_list_widget`` attribute exposes the QListWidget. Used by substance's
    # baked-maps row but generally useful for any "pick N files" interaction.

    @staticmethod
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
        for item in spec.default or []:
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

    @staticmethod
    def _read_file_list(widget) -> List[str]:
        lw = widget._list_widget
        return [lw.item(i).text() for i in range(lw.count())]

    @staticmethod
    def _write_file_list(widget, value) -> None:
        lw = widget._list_widget
        lw.clear()
        for item in value or []:
            lw.addItem(str(item))

    @staticmethod
    def _connect_file_list(widget, callback):
        widget._list_widget.model().rowsInserted.connect(
            lambda *_: callback(_KindFactoryInternal._read_file_list(widget))
        )
        widget._list_widget.model().rowsRemoved.connect(
            lambda *_: callback(_KindFactoryInternal._read_file_list(widget))
        )

    # ---- action: composite (row of action buttons) -------------------------
    #
    # A parameter row whose "value" is a set of ACTIONS, not data: each
    # ``choices`` entry is ``(label, action_id)`` / ``(label, action_id, tip)``
    # and becomes one QPushButton. The container exposes
    # ``_action_buttons = {action_id: QPushButton}`` so the hosting panel can
    # wire each button to its own method after build (BridgeSlotsBase does
    # this automatically for action ids that name a slot method). ``read``
    # returns ``None`` -- there is no value to collect or preset -- and the
    # change-wirer is a deliberate no-op so preset dirty-tracking ignores
    # clicks. The first action is the primary affordance and takes the row's
    # stretch; the rest stay compact.

    @staticmethod
    def _build_action(spec, parent):
        container = QtWidgets.QWidget(parent)
        hl = QtWidgets.QHBoxLayout(container)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(2)
        container._action_buttons = {}  # noqa: SLF001 -- intentional public attr
        for i, entry in enumerate(spec.choices or []):
            label, action_id, tip = _KindFactoryInternal._split_choice(entry)
            if action_id is _NO_VALUE:
                action_id = str(label)
            btn = QtWidgets.QPushButton(str(label), container)
            btn.setMinimumHeight(19)
            btn.setMaximumHeight(19)
            if tip:
                btn.setToolTip(tip)
            hl.addWidget(btn, 1 if i == 0 else 0)
            container._action_buttons[str(action_id)] = btn
        return container

    @staticmethod
    def _read_action(widget):
        return None

    @staticmethod
    def _write_action(widget, value):
        pass

    @staticmethod
    def _connect_action(widget, callback):
        # Actions are not values; nothing to observe.
        pass

    # ---- check_list: QListWidget of checkable rows -------------------------
    #
    # Multi-pick over a fixed entry set -- the plural counterpart to
    # ``choice`` -- reading back the ``list`` of checked values. Entries come
    # from ``choices`` (same shape as ``choice``, per-entry tooltips included)
    # and ``default`` is the list of values checked on build. A panel whose
    # entries are only known at runtime builds the row with empty ``choices``
    # and fills it via :meth:`KindFactory.set_choices`.

    @staticmethod
    def _build_check_list(spec, parent):
        w = QtWidgets.QListWidget(parent)
        # Checking is the interaction; a selection highlight on top of it just
        # reads as a second, meaningless state.
        w.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        w.setUniformItemSizes(True)
        w.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        w.customContextMenuRequested.connect(
            lambda pos, lw=w: _KindFactoryInternal._check_list_menu(lw, pos)
        )
        _KindFactoryInternal._set_choices_check_list(w, spec.choices or [])
        _KindFactoryInternal._write_check_list(w, spec.default)
        return w

    #: Height bounds (px) of a check_list row -- tall enough to read as a list
    #: when nearly empty, capped so a long set scrolls instead of eating the panel.
    CHECK_LIST_MIN_H = 48
    CHECK_LIST_MAX_H = 140

    @staticmethod
    def _fit_check_list_height(widget) -> None:
        """Size the list to its rows, within the height bounds.

        A fixed height would either scroll a 3-entry list or leave dead space
        under a 10-entry one; the entries arrive at runtime, so the row height
        follows them.
        """
        row_h = widget.sizeHintForRow(0) if widget.count() else 0
        wanted = widget.count() * (row_h or 18) + 2 * widget.frameWidth() + 4
        height = min(
            max(wanted, _KindFactoryInternal.CHECK_LIST_MIN_H),
            _KindFactoryInternal.CHECK_LIST_MAX_H,
        )
        widget.setMinimumHeight(height)
        widget.setMaximumHeight(height)

    @staticmethod
    def _check_list_menu(widget, pos) -> None:
        """Right-click bulk toggles -- a long checklist is tedious without them
        and the parameter row has no space for buttons.

        Shown with ``popup`` rather than ``exec``: the latter spins a nested
        event loop, which is the last thing to start inside a DCC host's loop
        for a two-item convenience menu. Parented (kept alive) and
        delete-on-close (not accumulated on the widget).
        """
        menu = QtWidgets.QMenu(widget)
        menu.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        menu.addAction(
            "Check All",
            lambda: _KindFactoryInternal._set_all_checked(widget, True),
        )
        menu.addAction(
            "Uncheck All",
            lambda: _KindFactoryInternal._set_all_checked(widget, False),
        )
        menu.popup(widget.mapToGlobal(pos))

    @staticmethod
    def _set_all_checked(widget, checked: bool) -> None:
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        for i in range(widget.count()):
            widget.item(i).setCheckState(state)

    @staticmethod
    def _check_list_value(item) -> Any:
        """The item's value -- its stored data, else its label."""
        data = item.data(QtCore.Qt.UserRole)
        return item.text() if data is None else data

    @staticmethod
    def _as_value_list(value) -> List[Any]:
        """Normalize a written ``check_list`` value to a list of wanted values.

        A bare string is ONE value, not an iterable of characters -- a preset
        or CLI overlay carrying a scalar (``"audio_event"``) would otherwise
        check nothing at all, silently. A list (rather than a set) also keeps
        unhashable values working; these lists are a handful of entries long.
        """
        if value is None:
            return []
        if isinstance(value, (list, tuple, set, frozenset)):
            return list(value)
        return [value]

    @staticmethod
    def _set_choices_check_list(widget, choices) -> None:
        """(Re)fill the rows, preserving the checked values that survive."""
        checked = _KindFactoryInternal._read_check_list(widget)
        widget.clear()
        for entry in choices or []:
            label, value, tip = _KindFactoryInternal._split_choice(entry)
            item = QtWidgets.QListWidgetItem(str(label), widget)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            if value is not _NO_VALUE:
                item.setData(QtCore.Qt.UserRole, value)
            if tip:
                item.setToolTip(tip)
            item.setCheckState(
                QtCore.Qt.Checked
                if _KindFactoryInternal._check_list_value(item) in checked
                else QtCore.Qt.Unchecked
            )
        _KindFactoryInternal._fit_check_list_height(widget)

    @staticmethod
    def _read_check_list(widget) -> List[Any]:
        items = (widget.item(i) for i in range(widget.count()))
        return [
            _KindFactoryInternal._check_list_value(item)
            for item in items
            if item.checkState() == QtCore.Qt.Checked
        ]

    @staticmethod
    def _write_check_list(widget, value) -> None:
        wanted = _KindFactoryInternal._as_value_list(value)
        for i in range(widget.count()):
            item = widget.item(i)
            item.setCheckState(
                QtCore.Qt.Checked
                if _KindFactoryInternal._check_list_value(item) in wanted
                else QtCore.Qt.Unchecked
            )


class KindFactory(_KindFactoryInternal):
    """Build / read / write Qt widgets by ``kind``, backed by the registry.

    The public factory surface. Consumers call
    ``KindFactory.make_widget(spec)`` to build a widget and
    ``KindFactory.read_value(widget)`` / ``.set_value`` / ``.connect_changed``
    to operate on it without knowing its kind. New kinds are added via
    :meth:`register_kind`.
    """

    # -----------------------------------------------------------------------
    # Type inference (mirrors AttributeWindow's original type_to_widget mapping).
    # -----------------------------------------------------------------------

    @staticmethod
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

    # -----------------------------------------------------------------------
    # Public factory surface.
    # -----------------------------------------------------------------------

    @staticmethod
    def register_kind(name: str, handler: KindHandler) -> None:
        """Register a new kind (or override an existing one)."""
        _KindFactoryInternal._HANDLERS[name] = handler

    @staticmethod
    def get_handler(kind: str) -> KindHandler:
        """Return the handler for *kind* (raises KeyError if unregistered)."""
        if kind not in _KindFactoryInternal._HANDLERS:
            raise KeyError(
                f"No KindHandler registered for {kind!r}. "
                f"Known kinds: {sorted(_KindFactoryInternal._HANDLERS)}"
            )
        return _KindFactoryInternal._HANDLERS[kind]

    @staticmethod
    def make_widget(
        spec: AttributeSpec, parent: Optional[QtWidgets.QWidget] = None
    ) -> QtWidgets.QWidget:
        """Build a Qt widget for *spec*. Stamps the resolved kind for later lookup."""
        kind = (
            spec.kind if spec.kind != "auto" else KindFactory.infer_kind(spec.default)
        )
        handler = KindFactory.get_handler(kind)
        widget = handler.build(spec, parent)
        widget.setObjectName(spec.key)
        if spec.tooltip:
            widget.setToolTip(spec.tooltip)
        widget.setProperty(_KIND_PROP, kind)
        return widget

    @staticmethod
    def read_value(widget: QtWidgets.QWidget) -> Any:
        """Return the current value of a factory-built widget."""
        return KindFactory.get_handler(_KindFactoryInternal._widget_kind(widget)).read(
            widget
        )

    @staticmethod
    def set_value(widget: QtWidgets.QWidget, value: Any) -> None:
        """Set the value of a factory-built widget."""
        KindFactory.get_handler(_KindFactoryInternal._widget_kind(widget)).write(
            widget, value
        )

    @staticmethod
    def set_choices(widget: QtWidgets.QWidget, choices: ChoicesSeq) -> None:
        """Repopulate a choice-driven widget's entries after it was built.

        The runtime half of the registry: a spec declares the kind and the
        static entries, and a panel that only learns the real set at runtime
        (installed app versions, deployable scripts, scene contents) pushes
        them in here without knowing which widget class backs the kind. Values
        still checked / selected survive the refill when they reappear.

        Raises:
            KeyError: *widget* was not built by :meth:`make_widget`.
            TypeError: its kind has no ``set_choices`` (e.g. ``str``, ``int``).
        """
        kind = _KindFactoryInternal._widget_kind(widget)
        handler = KindFactory.get_handler(kind)
        if handler.set_choices is None:
            raise TypeError(f"The {kind!r} kind has no choices to set.")
        handler.set_choices(widget, choices)

    @staticmethod
    def connect_changed(
        widget: QtWidgets.QWidget, callback: Callable[[Any], None]
    ) -> None:
        """Wire the widget's value-change signal to ``callback(new_value)``."""
        handler = KindFactory.get_handler(_KindFactoryInternal._widget_kind(widget))
        if handler.connect is not None:
            handler.connect(widget, callback)
            return
        getattr(widget, handler.signal).connect(
            lambda *_: callback(handler.read(widget))
        )


# ---------------------------------------------------------------------------
# Register the built-ins.
# ---------------------------------------------------------------------------

KindFactory.register_kind(
    "bool",
    KindHandler(
        _KindFactoryInternal._build_bool,
        _KindFactoryInternal._read_bool,
        _KindFactoryInternal._write_bool,
        signal="stateChanged",
    ),
)
KindFactory.register_kind(
    "int",
    KindHandler(
        _KindFactoryInternal._build_int,
        _KindFactoryInternal._read_int,
        _KindFactoryInternal._write_int,
        signal="valueChanged",
    ),
)
KindFactory.register_kind(
    "float",
    KindHandler(
        _KindFactoryInternal._build_float,
        _KindFactoryInternal._read_float,
        _KindFactoryInternal._write_float,
        signal="valueChanged",
    ),
)
KindFactory.register_kind(
    "str",
    KindHandler(
        _KindFactoryInternal._build_str,
        _KindFactoryInternal._read_str,
        _KindFactoryInternal._write_str,
        signal="textChanged",
    ),
)
KindFactory.register_kind(
    "choice",
    KindHandler(
        _KindFactoryInternal._build_choice,
        _KindFactoryInternal._read_choice,
        _KindFactoryInternal._write_choice,
        signal="currentIndexChanged",
        set_choices=_KindFactoryInternal._set_choices_choice,
    ),
)
KindFactory.register_kind(
    "check_list",
    KindHandler(
        _KindFactoryInternal._build_check_list,
        _KindFactoryInternal._read_check_list,
        _KindFactoryInternal._write_check_list,
        signal="itemChanged",
        set_choices=_KindFactoryInternal._set_choices_check_list,
    ),
)
KindFactory.register_kind(
    "path",
    KindHandler(
        _KindFactoryInternal._build_path,
        _KindFactoryInternal._read_path,
        _KindFactoryInternal._write_path,
        connect=_KindFactoryInternal._connect_path,
    ),
)
KindFactory.register_kind(
    "file_list",
    KindHandler(
        _KindFactoryInternal._build_file_list,
        _KindFactoryInternal._read_file_list,
        _KindFactoryInternal._write_file_list,
        connect=_KindFactoryInternal._connect_file_list,
    ),
)
KindFactory.register_kind(
    "action",
    KindHandler(
        _KindFactoryInternal._build_action,
        _KindFactoryInternal._read_action,
        _KindFactoryInternal._write_action,
        connect=_KindFactoryInternal._connect_action,
    ),
)
