# !/usr/bin/python
# coding=utf-8
"""Kind-handler registry for parameterised forms (the Qt half of the contract).

:class:`~uitk.bridge.attribute_spec.AttributeSpec`, the Qt-free description
each handler builds from, lives in :mod:`uitk.bridge.attribute_spec`.

DCC-bridge code and the AttributeWindow panel share this one registry
instead of maintaining parallel ones.

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

import contextlib
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from qtpy import QtCore, QtWidgets

# AttributeSpec (and the choice aliases) live in the Qt-free
# ``attribute_spec`` so a registry can be declared without a binding; the
# widget half is built here.
from uitk.bridge.attribute_spec import AttributeSpec, ChoiceItem, ChoicesSeq  # noqa: F401
from uitk.widgets.checkBox import CheckBox
from uitk.widgets.doubleSpinBox import DoubleSpinBox
from uitk.widgets.spinBox import SpinBox


INT_MIN = -2147483648
INT_MAX = 2147483647
FLOAT_MIN = -1e100
FLOAT_MAX = 1e100

_KIND_PROP = "_attr_kind"

#: Marker for a bare ``choices`` entry (label == value, no explicit data).
_NO_VALUE = object()


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

    ``literal`` is optional and only meaningful for kinds whose value is
    COMPOSITE (``affix`` returns ``{"text", "mode"}``): it names the scalar
    stand-in a template substitution should see, so a ``__KEY__`` token renders
    as the spelling the user typed rather than a dict repr. Kinds without one
    substitute their value unchanged.
    """

    build: Callable[[AttributeSpec, Optional[QtWidgets.QWidget]], QtWidgets.QWidget]
    read: Callable[[QtWidgets.QWidget], Any]
    write: Callable[[QtWidgets.QWidget, Any], None]
    signal: Optional[str] = None
    connect: Optional[Callable[[QtWidgets.QWidget, Callable[[Any], None]], None]] = None
    set_choices: Optional[Callable[[QtWidgets.QWidget, ChoicesSeq], None]] = None
    literal: Optional[Callable[[Any], Any]] = None

    def __post_init__(self):
        # Surface malformed handlers at construction, not at registration time.
        if self.signal is None and self.connect is None:
            raise ValueError(
                "KindHandler must provide either `signal` (Qt signal name) "
                "or `connect` (custom wirer)."
            )


class _CheckList(QtWidgets.QListWidget):
    """The ``check_list`` row: a list whose VALUE is its checked entries.

    Persistence keys a plain ``QListWidget`` on ``itemClicked``, which carries
    the clicked item (unstorable) and never fires for a check set in code, so
    the row never saved. It declares its own change signal and value instead
    (the ``state_signal`` / ``state_value`` / ``set_state_value`` protocol
    ``MainWindow`` and ``ValueManager`` honor), and window state, presets and
    resets round-trip the checked values like any other row.
    """

    checkedChanged = QtCore.Signal(list)
    state_signal = "checkedChanged"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_checked: List[Any] = []
        # itemChanged also fires for a label, data or tooltip write (every row
        # a refill builds); only a change of the checked SET is one.
        self.itemChanged.connect(self._emit_if_changed)

    def _emit_if_changed(self, _item=None) -> None:
        """Announce the checked set when it differs from the last one.

        The last one moves even while the list's signals are blocked (the
        emit is dropped then): a write made under a block -- a preset load, a
        model refresh -- must still count, or the user putting the list back
        to the set it held before would announce nothing.
        """
        checked = self.state_value()
        if checked != self._last_checked:
            self._last_checked = checked
            self.checkedChanged.emit(checked)

    @contextlib.contextmanager
    def _one_change(self):
        """Change several rows' check states as ONE change of the checked set.

        Nothing is announced on the way -- a refill's ``clear`` would announce
        the empty set, then each partial set on the way back -- and the whole
        set once after, through :meth:`_emit_if_changed`.
        """
        blocked = self.blockSignals(True)
        try:
            yield
        finally:
            self.blockSignals(blocked)
        self._emit_if_changed()

    def state_value(self) -> List[Any]:
        return _KindFactoryInternal._read_check_list(self)

    def set_state_value(self, value) -> bool:
        """Check exactly *value*'s entries; False when one is no longer listed
        (the ``ValueManager.set_value`` contract a preset load counts)."""
        _KindFactoryInternal._write_check_list(self, value)
        wanted = _KindFactoryInternal._as_value_list(value)
        return len(self.state_value()) == len(wanted)


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
        if spec.placeholder:
            # A number field has no EMPTY state: its minimum is the "unset"
            # value, and Qt shows this text in place of it.
            w.setSpecialValueText(spec.placeholder)
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
        if spec.placeholder:
            w.setPlaceholderText(spec.placeholder)
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
        """Item data, else the label (a bare entry's value IS its label)."""
        from uitk.managers.value_manager import ValueManager

        return ValueManager.combo_value(widget, "data", fallback="text")

    @staticmethod
    def _write_choice(widget, value):
        # False: no entry carries *value* (by data, then by label), so the
        # selection stays -- a preset load counts that as a misfit.
        for i in range(widget.count()):
            if widget.itemData(i) == value:
                widget.setCurrentIndex(i)
                return True
        idx = widget.findText(str(value))
        if idx >= 0:
            widget.setCurrentIndex(idx)
            return True
        return False

    # ---- path: composite (QLineEdit + browse button) ----------------------
    #
    # The container's ``_line_edit`` attribute exposes the QLineEdit so external
    # code (and the read/write helpers below) can find it without walking
    # children. The browse button height matches the 19px row clamp used by
    # the bridge panels; AttributeWindow doesn't clamp the row so the larger
    # control still works there.

    @staticmethod
    def _build_path(spec, parent):
        """A line edit that browses for a DIRECTORY."""
        return _KindFactoryInternal._build_browse_row(spec, parent, "directory")

    @staticmethod
    def _build_file(spec, parent):
        """A line edit that browses for one FILE, filtered by *spec.choices*.

        Registered as its own kind rather than folded into ``path`` behind a
        flag because every panel that wanted a file field hand-rolled the row
        instead (the Marmoset and Unity panels each carry a private
        ``_build_model_row`` that is the same twenty lines with a different
        filter), and a third copy is what this registry exists to prevent.

        *spec.choices* carries the filter as glob patterns -- ``["*.fbx",
        "*.glb"]`` -- reusing the field the way the ``action`` kind does
        rather than widening the frozen dataclass for one kind. Empty offers
        all files.
        """
        return _KindFactoryInternal._build_browse_row(spec, parent, "file")

    @staticmethod
    def _build_browse_row(spec, parent, mode):
        """A line edit carrying option-box CLEAR and BROWSE icon buttons.

        The path-ish kinds differ only in what the dialog picks, so they are
        one row: ``path`` browses for a directory, ``file`` for a file
        filtered by ``spec.choices``, ``files`` for several (the pick, joined
        by :attr:`FILES_SEPARATOR`, replaces the field). The first two used
        to hand-roll a ``QLineEdit`` beside a ``"..."`` push button and drive
        ``QFileDialog`` themselves, which is the option box's whole job --
        and the copies had already drifted, only one of them anchoring the
        dialog on the current value.

        The plugins bring what a private copy does not: the clear button
        hides itself while the field is empty, so a row cannot offer to clear
        nothing, and BOTH buttons are icons sized to the row rather than a
        text button that reads as a third value. Every path shape a caller
        might type still survives a round trip -- the widget reads and writes
        plain text, so a UNC path or an unexpanded variable is preserved.

        ``uitk``'s own :class:`~uitk.widgets.lineEdit.LineEdit` rather than a
        bare ``QLineEdit``: ``option_box`` is a property of the mixin it
        carries (the QWidget patch is applied by ``Switchboard``, so a bare
        field only has it once one exists), and it keeps the standard editing
        chords with the field when a DCC host binds the same sequence.
        """
        from uitk.widgets.lineEdit import LineEdit

        edit = LineEdit()
        default = spec.default
        if isinstance(default, (list, tuple)):
            default = _KindFactoryInternal.FILES_SEPARATOR.join(map(str, default))
        edit.setText("" if default is None else str(default))
        # Name the inner edit (mirrors make_widget's container objectName ==
        # spec.key) so preset capture keys it: consumers that snapshot the
        # value-bearing child rather than the container (e.g. the DCC bridges
        # substitute ``_line_edit`` into their managed set) skip
        # empty-objectName widgets, silently dropping path fields from saved
        # widget-state presets.
        edit.setObjectName(spec.key)
        edit.setMinimumHeight(19)
        edit.setMaximumHeight(19)
        if spec.placeholder:
            edit.setPlaceholderText(spec.placeholder)

        directory = mode == "directory"
        several = mode == "files"
        patterns = [str(c) for c in (spec.choices or [])]
        edit.option_box.enable_clear()
        edit.option_box.browse(
            # A multi-select writes its FIRST pick to the field (the option's
            # rule for any widget); this row holds the whole pick.
            callback=(
                (
                    lambda paths: edit.setText(
                        _KindFactoryInternal.FILES_SEPARATOR.join(paths)
                    )
                )
                if several
                else None
            ),
            file_types=(
                None
                if directory
                else (
                    f"Supported ({' '.join(patterns)});;All files (*)"
                    if patterns
                    else "All files (*)"
                )
            ),
            # The dialog is titled with the row it belongs to; two open file
            # dialogs from one panel are otherwise indistinguishable.
            title=spec.display_label
            or (
                "Select directory"
                if directory
                else ("Select files" if several else "Select file")
            ),
            mode=mode,
            tooltip=(
                "Browse for a folder"
                if directory
                else (
                    "Browse for one or more files" if several else "Browse for a file"
                )
            ),
        )

        container = edit.option_box.container
        container.setParent(parent)
        container._line_edit = edit  # noqa: SLF001 — intentional public attr
        return container

    @staticmethod
    def _read_file(widget):
        return widget._line_edit.text()

    @staticmethod
    def _write_file(widget, value):
        widget._line_edit.setText("" if value is None else str(value))

    @staticmethod
    def _connect_file(widget, callback):
        widget._line_edit.textChanged.connect(
            lambda *_: callback(_KindFactoryInternal._read_file(widget))
        )

    # ---- files: the file row, holding several -------------------------------
    #
    # The ``file`` row whose browse picks SEVERAL files, read as a
    # ``list[str]``. One line edit rather than ``file_list``'s list widget:
    # the paths stay typable and pasteable, the row keeps the clear and browse
    # icons and the placeholder, and a row that usually holds one file stays
    # one line tall.

    #: Between two paths in a ``files`` row: ``;`` is no path character in
    #: practice (Windows' own PATH separator), and the space after it keeps a
    #: field of several paths readable. Read back on ``;`` alone.
    FILES_SEPARATOR = "; "

    @staticmethod
    def _build_files(spec, parent):
        """A line edit that browses for several FILES, filtered by
        *spec.choices* as the ``file`` kind is; the pick replaces the field.
        """
        return _KindFactoryInternal._build_browse_row(spec, parent, "files")

    @staticmethod
    def _read_files(widget) -> List[str]:
        return [
            part.strip() for part in widget._line_edit.text().split(";") if part.strip()
        ]

    @staticmethod
    def _write_files(widget, value) -> None:
        if value is None:
            value = []
        if isinstance(value, str):
            value = [value] if value else []
        widget._line_edit.setText(
            _KindFactoryInternal.FILES_SEPARATOR.join(str(v) for v in value)
        )

    @staticmethod
    def _connect_files(widget, callback):
        widget._line_edit.textChanged.connect(
            lambda *_: callback(_KindFactoryInternal._read_files(widget))
        )

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
    # ``choices`` entry is ``(label, action_id)``, ``(label, action_id, tip)``
    # or ``(label, action_id, tip, icon)`` and becomes one button. The
    # container exposes ``_action_buttons = {action_id: QPushButton}`` so the
    # hosting panel can wire each button to its own method after build
    # (BridgeSlotsBase does this automatically for action ids that name a slot
    # method). ``read`` returns ``None`` -- there is no value to collect or
    # preset -- and the change-wirer is a deliberate no-op so preset
    # dirty-tracking ignores clicks. The first action is the primary affordance
    # and takes the row's stretch; the rest stay compact.
    #
    # An entry that names an ``icon`` renders as an option-box icon button
    # riding the primary action instead of as a second full-width label. Once
    # the primary says what the row is for, its secondary verbs read better as
    # the compact icon grammar the rest of the toolkit already uses for exactly
    # this (uitk's ClearOption, tentacle's uv Transfer source row) -- and the
    # row stops spending its whole width on chrome. The button registered in
    # ``_action_buttons`` is the option's own, so wiring and disabling are
    # identical either way.

    @staticmethod
    def _option_box(widget):
        """The widget's ``OptionBoxManager``, or ``None`` if one can't be made.

        ``Switchboard.__init__`` patches the common Qt classes with an
        ``option_box`` property, but this factory is usable with no Switchboard
        at all (AttributeWindow panels, headless tests) -- and a row that
        silently lost its icon buttons or its affix picker depending on
        construction order would be a bug nobody could see. So: use the patched
        property when it is there, otherwise attach a manager to the instance
        under the same ``_option_box_manager`` name the patch caches on, which
        keeps a later patched access returning this very manager.
        """
        manager = getattr(widget, "_option_box_manager", None)
        if manager is not None:
            return manager
        manager = getattr(widget, "option_box", None)
        if manager is not None:
            return manager
        try:
            from uitk.widgets.optionBox.option_box_manager import OptionBoxManager

            manager = OptionBoxManager(widget)
        except Exception:  # noqa: BLE001 -- degrade to a plain widget
            return None
        widget._option_box_manager = manager
        return manager

    @staticmethod
    def _split_action_choice(entry) -> Tuple[Any, Any, str, str]:
        """Normalize one ``action`` entry to ``(label, action_id, tooltip, icon)``.

        Extends :meth:`_split_choice` with the action-only 4th element. Kept
        separate so the combo kinds' 3-tuple contract stays exactly as it was.
        """
        if isinstance(entry, tuple) and len(entry) == 4:
            return entry[0], entry[1], str(entry[2] or ""), str(entry[3] or "")
        label, action_id, tip = _KindFactoryInternal._split_choice(entry)
        return label, action_id, tip, ""

    @staticmethod
    def _add_action_button(container, label, tip) -> QtWidgets.QPushButton:
        """Build one compact text button for an action row (not yet laid out)."""
        btn = QtWidgets.QPushButton(str(label), container)
        btn.setMinimumHeight(19)
        btn.setMaximumHeight(19)
        if tip:
            btn.setToolTip(tip)
        return btn

    @staticmethod
    def _build_action(spec, parent):
        container = QtWidgets.QWidget(parent)
        hl = QtWidgets.QHBoxLayout(container)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(2)
        container._action_buttons = {}  # noqa: SLF001 -- intentional public attr
        primary = None
        icon_entries = []
        for entry in spec.choices or []:
            label, action_id, tip, icon = _KindFactoryInternal._split_action_choice(
                entry
            )
            if action_id is _NO_VALUE:
                action_id = str(label)
            action_id = str(action_id)
            # An icon entry needs a host to hang its option box off, so the
            # FIRST entry always renders as the text button even if it names
            # an icon -- an all-icon row would have nothing to attach to and
            # no label saying what the row does.
            if icon and primary is not None:
                icon_entries.append((action_id, label, tip, icon))
                continue
            btn = _KindFactoryInternal._add_action_button(container, label, tip)
            hl.addWidget(btn, 1 if primary is None else 0)
            container._action_buttons[action_id] = btn
            if primary is None:
                primary = btn

        # Wrapped only now that the primary is layout-managed: the option box
        # replaces it in place (keeping the stretch) instead of briefly showing
        # as a top-level widget, whose showEvent collapses the container -- the
        # same ordering BridgeSlotsBase's output-dir row documents.
        manager = (
            _KindFactoryInternal._option_box(primary) if primary is not None else None
        )
        for action_id, label, tip, icon in icon_entries:
            if manager is None:
                # No option-box support on this host (a bare Qt build with no
                # Switchboard to patch QPushButton): degrade to a text button
                # rather than dropping the action off the panel entirely.
                btn = _KindFactoryInternal._add_action_button(container, label, tip)
                hl.addWidget(btn, 0)
                container._action_buttons[action_id] = btn
                continue
            option = manager.add_action(
                icon=icon,
                tooltip=tip or str(label),
                settings_key=False,
            )
            # The option is a placement vehicle only -- the click is wired by
            # the hosting panel through ``_action_buttons``, exactly like a
            # text action, so neither wiring path has to know which it got.
            container._action_buttons[action_id] = option.widget
        return container

    # ---- affix: QLineEdit + tri-state affix-mode icon ----------------------
    #
    # A text entry whose value is an AFFIX: the spelling plus a declaration of
    # which side of a base name it lands on. The picker is uitk's shared
    # :class:`~uitk.widgets.optionBox.options.affix.AffixOption` -- one cycling
    # icon (Auto -> Suffix -> Prefix) over ``pythontk.StrUtils.split_affix`` --
    # so a bridge parameter wears exactly the control the mat_utils panels and
    # tentacle's uv Transfer already do, instead of a second combo per registry.
    #
    # ``read`` returns ``{"text": str, "mode": str}``: both halves, so a preset
    # restores the side as well as the spelling. Consumers turn one into the
    # pair they actually apply with :meth:`KindFactory.affix_parts`. The
    # ``literal`` hook renders the text alone, so a template substituting
    # ``__KEY__`` sees the spelling rather than a dict repr.

    #: The three built-in affix modes, in ``AffixOption``'s cycle order.
    #: Descriptive only -- a picker's mode set is configurable, so this is NOT
    #: a whitelist anything is filtered against (see :meth:`_affix_value`).
    AFFIX_MODES = ("auto", "suffix", "prefix")

    @staticmethod
    def _affix_value(value) -> Dict[str, str]:
        """Normalize *value* (``dict`` | ``str`` | ``None``) to ``{text, mode}``.

        A bare string is read as the spelling with mode ``auto`` -- which is
        what a registry default of ``""`` means, and what a preset written
        before this kind existed carries.

        A ``"convention"`` entry in the dict is a DECLARATION, not a value (see
        :meth:`_affix_convention`), so it is deliberately dropped here: what
        this returns is what a preset stores, and the type a field is bound to
        belongs to the registry, not to the user's saved run.
        """
        if isinstance(value, dict):
            text, mode = value.get("text", ""), value.get("mode", "auto")
        else:
            text, mode = value, "auto"
        # NOT filtered against ``AFFIX_MODES``: a picker's mode set is
        # configurable (a spec can declare a convention-bound state, and a
        # caller can register any other), so a whitelist here would silently
        # rewrite every custom mode to "auto" on a preset round-trip. Validation
        # belongs to the one place that knows the mode set --
        # ``AffixOption.set_mode``, which no-ops on a mode it does not have, so
        # a stale or hand-edited preset degrades to the built default.
        return {
            "text": "" if text is None else str(text),
            "mode": str(mode or "auto").lower(),
        }

    @staticmethod
    def _affix_convention(value) -> Optional[str]:
        """The ``NamingConvention`` key an affix spec binds to, if any.

        Declared on the spec as ``default={"text": ..., "convention": "texture"}``.
        Opt-in per parameter: most affixes are a per-run label with no shared
        definition to follow, which is exactly why the state is not built in.
        """
        if isinstance(value, dict):
            key = value.get("convention")
            return str(key) if key else None
        return None

    @staticmethod
    def _affix_option(widget):
        """The widget's :class:`AffixOption`, or ``None`` (no option-box host)."""
        manager = _KindFactoryInternal._option_box(widget)
        if manager is None:
            return None
        from uitk.widgets.optionBox.options.affix import AffixOption

        return manager.find_option(AffixOption)

    @staticmethod
    def _build_affix(spec, parent):
        # Composite, exactly like ``path``: the option box replaces the field
        # it wraps IN ITS PARENT LAYOUT, so the field has to be layout-managed
        # before the wrap. Returning a bare QLineEdit meant the wrap happened
        # while the field was still parentless-in-layout (the row builder adds
        # it afterwards) -- the container then floated over the row instead of
        # joining it, and every row-level operation missed it: greying the row
        # left the mode and clear icons live beside a disabled value.
        container = QtWidgets.QWidget(parent)
        hl = QtWidgets.QHBoxLayout(container)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(2)
        value = _KindFactoryInternal._affix_value(spec.default)
        edit = QtWidgets.QLineEdit(value["text"], container)
        # Named like the container (see ``_build_path``) so preset capture keys
        # on the value-bearing child rather than skipping an empty objectName.
        edit.setObjectName(spec.key)
        edit.setMinimumHeight(19)
        edit.setMaximumHeight(19)
        hl.addWidget(edit, 1)
        container._line_edit = edit  # noqa: SLF001 -- intentional public attr

        # One dispatcher installed at build time: AffixOption takes its
        # ``on_change`` at construction, while ``connect`` arrives later and
        # possibly more than once (a panel may wire both a dependency sync and
        # preset dirty-tracking to the same row).
        container._affix_listeners = []  # noqa: SLF001 -- intentional public attr

        def _mode_changed(_mode, _c=container):
            for callback in list(_c._affix_listeners):
                callback(_KindFactoryInternal._read_affix(_c))

        manager = _KindFactoryInternal._option_box(edit)
        if manager is not None:
            manager.clear_option = True
            convention_key = _KindFactoryInternal._affix_convention(spec.default)
            # settings_key=False: the bridge owns this row's state end to end
            # (registry default -> preset -> ``_write_affix``), and only the
            # PAIR is meaningful. StateManager does not restore kind-built
            # composites, so letting the picker self-persist would restore the
            # MODE from QSettings beside a TEXT that fell back to the registry
            # default -- the spelling applied to the wrong side of the name.
            manager.set_affix(
                default=value["mode"],
                on_change=_mode_changed,
                settings_key=False,
                convention_key=convention_key,
            )
        return container

    @staticmethod
    def _read_affix(widget):
        option = _KindFactoryInternal._affix_option(widget._line_edit)
        return {
            "text": widget._line_edit.text(),
            "mode": option.mode if option is not None else "auto",
        }

    @staticmethod
    def _write_affix(widget, value):
        value = _KindFactoryInternal._affix_value(value)
        widget._line_edit.setText(value["text"])
        option = _KindFactoryInternal._affix_option(widget._line_edit)
        if option is not None:
            option.set_mode(value["mode"])

    @staticmethod
    def _connect_affix(widget, callback):
        widget._line_edit.textChanged.connect(
            lambda *_: callback(_KindFactoryInternal._read_affix(widget))
        )
        listeners = getattr(widget, "_affix_listeners", None)
        if listeners is not None:
            listeners.append(callback)

    @staticmethod
    def _literal_affix(value):
        """Substitution stand-in: the spelling, without the mode."""
        return _KindFactoryInternal._affix_value(value)["text"]

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
        w = _CheckList(parent)
        # Checking is the interaction; a selection highlight on top of it just
        # reads as a second, meaningless state.
        w.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        w.setUniformItemSizes(True)
        # Rows are the font's height and so is the check box; without a gap
        # the boxes stack into one ladder instead of reading as one per row.
        w.setSpacing(1)
        w.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        w.customContextMenuRequested.connect(
            lambda pos, lw=w: _KindFactoryInternal._check_list_menu(lw, pos)
        )
        _KindFactoryInternal._toggle_on_row_click(w)
        _KindFactoryInternal._set_choices_check_list(w, spec.choices or [])
        _KindFactoryInternal._write_check_list(w, spec.default)
        return w

    @staticmethod
    def _toggle_on_row_click(widget) -> None:
        """Make the whole row the hit target, as a QCheckBox's label is.

        Qt toggles a checkable item only on its indicator; a click on the text
        does nothing, which reads as a dead widget. The delegate's own toggle
        runs before ``clicked`` fires, so the row toggles only when the state
        is still what it was at press -- a box click never flips twice.
        """
        at_press = {}

        def pressed(index):
            at_press["index"] = index
            at_press["state"] = index.data(QtCore.Qt.CheckStateRole)

        def clicked(index):
            if at_press.get("index") != index:
                return
            if index.data(QtCore.Qt.CheckStateRole) != at_press.get("state"):
                return  # the indicator already took this click
            item = widget.itemFromIndex(index)
            if item is None or not item.flags() & QtCore.Qt.ItemIsUserCheckable:
                return
            item.setCheckState(
                QtCore.Qt.Unchecked
                if item.checkState() == QtCore.Qt.Checked
                else QtCore.Qt.Checked
            )

        widget.pressed.connect(pressed)
        widget.clicked.connect(clicked)

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
        row_h = (row_h or 18) + 2 * widget.spacing()
        wanted = widget.count() * row_h + 2 * widget.frameWidth() + 4
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
        with widget._one_change():
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
        """(Re)fill the rows, preserving the checked values that survive --
        one change of the checked set, announced only when it is one."""
        checked = _KindFactoryInternal._read_check_list(widget)
        with widget._one_change():
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
        with widget._one_change():
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
        return AttributeSpec.infer_kind(value)

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
    def kind_of(widget: QtWidgets.QWidget) -> Optional[str]:
        """The kind stamped on *widget*, or ``None`` if this factory didn't build it.

        The non-raising probe :meth:`read_value` / :meth:`set_value` lack. Consumers
        that handle a MIXED widget set -- ``PresetManager`` snapshots kind-built
        parameter rows alongside plain ``.ui`` widgets -- need to ask "is this mine?"
        without catching an exception per widget.

        The stamp is a Qt **dynamic property**, not a Python attribute, so a
        ``getattr(widget, "_attr_kind", None)`` written by hand silently answers
        ``None`` for every widget. Routing through here is what keeps that mistake
        from being re-made per consumer.
        """
        return widget.property(_KIND_PROP) or None

    @staticmethod
    def read_value(widget: QtWidgets.QWidget) -> Any:
        """Return the current value of a factory-built widget."""
        return KindFactory.get_handler(_KindFactoryInternal._widget_kind(widget)).read(
            widget
        )

    @staticmethod
    def set_value(widget: QtWidgets.QWidget, value: Any) -> Optional[bool]:
        """Set the value of a factory-built widget.

        Returns:
            False when the widget refused *value* (a ``choice`` no entry
            carries), else the kind's writer's answer (None for most kinds).
        """
        return KindFactory.get_handler(_KindFactoryInternal._widget_kind(widget)).write(
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
            ValueError: *widget* was not built by :meth:`make_widget`.
            TypeError: its kind has no ``set_choices`` (e.g. ``str``, ``int``).
        """
        kind = _KindFactoryInternal._widget_kind(widget)
        handler = KindFactory.get_handler(kind)
        if handler.set_choices is None:
            raise TypeError(f"The {kind!r} kind has no choices to set.")
        handler.set_choices(widget, choices)

    @staticmethod
    def to_literal(spec: AttributeSpec, value: Any) -> Any:
        """The scalar stand-in *value* substitutes as, for a composite kind.

        Most kinds already hold a scalar and pass through unchanged; a kind
        whose ``read`` returns a composite (``affix`` -> ``{"text", "mode"}``)
        registers a ``literal`` on its handler naming the part a template
        actually wants. Called by
        :meth:`uitk.bridge.parameters.Parameters.render_context` before the
        target-language formatter, so a ``__KEY__`` token never renders as a
        dict repr.

        Unregistered kinds pass through -- a caller with a custom kind that
        never registered a handler still gets its own value back.
        """
        kind = (
            spec.kind if spec.kind != "auto" else KindFactory.infer_kind(spec.default)
        )
        handler = _KindFactoryInternal._HANDLERS.get(kind)
        if handler is None or handler.literal is None:
            return value
        return handler.literal(value)

    @staticmethod
    def affix_parts(value: Any, *, default: str = "prefix") -> Tuple[str, str]:
        """``(prefix, suffix)`` for an ``affix``-kind value.

        The bridge-side counterpart to
        :meth:`uitk.widgets.optionBox.option_box_manager.OptionBoxManager.resolve_affix`:
        that one reads a live widget, this one reads a *collected* value (a
        send's params dict, a restored preset), so a consumer never has to
        reach back through the panel to find out which side the affix lands on.

        Parameters:
            value: An ``affix`` value (``{"text", "mode"}``) or a bare string
                (read as mode ``auto``).
            default: Fallback side when the mode is ``auto`` and the spelling
                carries no boundary delimiter -- see
                :func:`pythontk.StrUtils.split_affix`.

        Returns:
            ``(prefix, suffix)`` -- at most one is non-empty; an empty
            spelling returns ``("", "")``.
        """
        import pythontk as ptk

        parts = _KindFactoryInternal._affix_value(value)
        return ptk.StrUtils.split_affix(
            parts["text"], mode=parts["mode"], default=default
        )

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
        signal="checkedChanged",
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
    "file",
    KindHandler(
        _KindFactoryInternal._build_file,
        _KindFactoryInternal._read_file,
        _KindFactoryInternal._write_file,
        connect=_KindFactoryInternal._connect_file,
    ),
)
KindFactory.register_kind(
    "files",
    KindHandler(
        _KindFactoryInternal._build_files,
        _KindFactoryInternal._read_files,
        _KindFactoryInternal._write_files,
        connect=_KindFactoryInternal._connect_files,
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
KindFactory.register_kind(
    "affix",
    KindHandler(
        _KindFactoryInternal._build_affix,
        _KindFactoryInternal._read_affix,
        _KindFactoryInternal._write_affix,
        connect=_KindFactoryInternal._connect_affix,
        literal=_KindFactoryInternal._literal_affix,
    ),
)
