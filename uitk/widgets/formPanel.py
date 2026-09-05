# !/usr/bin/python
# coding=utf-8
"""Themed form window: Header → labelled rows → output log → Footer.

The polished home for "ask for two or more answers the user has to tell
apart, then do the thing" — the shape a sequence of native pickers handles
badly, because two folder dialogs shown back to back are the SAME widget
with different captions and the answer moves when one of them is skipped.

Built on :class:`WindowPanel`, so it wears the same chrome as every other
tool window in the toolset and is built the same way — :meth:`add` is the
base's, the Menu idiom — and adds only the FORM contract on top:
``values()`` over every value-bearing row, a validator whose reason lives in
the footer, an accept button that names the operation, and the two ways of
running it.

Two modes, one widget:

- **run-in-place** (``on_run=``) — the panel stays open, runs the operation
  itself, and streams its log into the single output pane at the bottom.
  This is the Scene Exporter shape: read the form, press the verb, watch it
  happen, adjust and press again. :meth:`present` shows it modelessly. A
  handler that returns a callable has previewed rather than committed: the
  panel arms an **Apply** button holding that callable, the naming panel's
  dry-run contract.
- **modal** (no ``on_run``) — :meth:`exec_panel` blocks and returns whether
  the form was accepted; the caller reads :meth:`values` and does the work.
  This is what backs ``Switchboard.form_dialog``.

Field hints are **tooltips**, not labels. A hint under every row is a wall
of prose that has to be read past to reach the controls, and it is longest
exactly when the form is busiest; on hover it is available at the one moment
it is wanted, and the panel stays a form. What replaces the prose on screen
is one output pane — the only text area the panel has, so there is no
question which one to read.
"""

from typing import Callable, Dict, List, Optional, Union

from qtpy import QtCore, QtWidgets
from uitk.managers.cursor_manager import CursorManager

from uitk.widgets.windowPanel import WindowPanel


class FormPanel(WindowPanel):
    """Themed form window over a list of field specs.

    Parameters
    ----------
    fields : list[dict]
        Row specs. See :meth:`set_fields` for the recognized keys.
    title : str
        Header text.
    parent : QWidget, optional
        Anchor widget; the panel reparents to ``parent.window()``.
    ok_text : str or callable
        Accept-button text. Say what will happen ("Copy 12 textures") — it is
        the last thing read before committing. A ``callable(values) -> str``
        is re-evaluated on every edit, so a verb chosen ON the form (a
        Copy/Move row) reaches the button that names the operation.
    cancel_text : str
        Reject-button text. A modal gets ``"Cancel"`` by default because
        discarding is a real answer there; a run-in-place panel gets NO
        reject button — the header already carries the window's close, and a
        second one in the footer says nothing the first does not. Pass a
        string to force one either way.
    validate : callable, optional
        ``callable(values: dict) -> str``. Return "" when the form is valid,
        else the message to show. The accept button stays disabled while it
        is non-empty and the reason sits in the footer. Re-run on every edit.
    message : str, optional
        Rich-text line above the rows. For the one thing that must be read
        without hovering; everything else belongs in a tooltip.
    help_text : str, optional
        Rich text for the header's ``?`` button — build it with
        :meth:`TooltipFormat.fmt`.
    output : bool
        Show the collapsable output pane (default True). ``form_dialog``
        turns it off: a modal that closes before the work starts has nothing
        to stream.
    on_run : callable, optional
        ``callable(values: dict)`` run by the accept button with the panel
        still open. Return a ``callable()`` to say "this was a preview" — the
        panel then arms Apply with it and running anything else drops it.
        When ``on_run`` is omitted the accept button accepts and closes.
    apply_text : str
        Text of the armed-preview button. Defaults to ``"Apply"``.
    min_width : int
        Minimum window width. Defaults to 560.
    settings : SettingsManager, optional
        Store the window's size and position survive across sessions in —
        typically ``sb.settings.branch("<tool>")``. None (default) leaves the
        window fitting to content on every open.
    settings_key : str
        Settings key holding the serialized geometry.
    """

    # Not a Designer widget-box entry: a top-level window shell.
    designer_spec = {"visible": False}

    #: Emitted after a successful run-in-place pass, with the values used.
    ran = QtCore.Signal(dict)

    #: Footer placeholder while a run-in-place handler is working. Compared
    #: back against the live status so a handler that set its own line keeps
    #: it, and one that said nothing does not end up reading "Working…" over
    #: work that has finished.
    RUNNING_STATUS = "Working…"

    #: ``(widget type, change signal)`` — what makes an added widget a FIELD:
    #: it is registered under its objectName, read by :meth:`values`, and its
    #: signal re-validates. Most-specific first. The readers live in
    #: :meth:`values` / :meth:`set_values`, one branch per row here; a new
    #: kind is one row and one branch each. Deliberately NOT the switchboard's
    #: ``_WIDGET_VALUE_READERS``: that table's combo contract is
    #: ``currentData``-else-index (a slot conditions on the payload), while a
    #: form's published contract is the visible ``currentText``.
    _FIELD_TYPES = (
        (QtWidgets.QCheckBox, "toggled"),
        (QtWidgets.QComboBox, "currentIndexChanged"),
        (QtWidgets.QLineEdit, "textChanged"),
    )

    def __init__(
        self,
        fields,
        title: str = "Options",
        parent: QtWidgets.QWidget = None,
        ok_text: Union[str, Callable] = "OK",
        cancel_text: str = None,
        validate: Callable = None,
        message: str = "",
        help_text: str = "",
        output: bool = True,
        on_run: Callable = None,
        apply_text: str = "Apply",
        min_width: int = 560,
        settings=None,
        settings_key: str = "window_geometry",
    ):
        super().__init__(title=title, header_buttons=["hide"], parent=parent)

        # Before the first show, or the size restored on it is the one this
        # constructor is still building.
        if settings is not None:
            self.persist_geometry(settings, settings_key)

        self._ok_text = ok_text
        self._validate = validate
        self._on_run = on_run
        self._accepted = False
        self._modal_loop = None
        self._logger = None
        self._running = False
        self._validation_error = ""
        self._apply_text = apply_text
        self._apply_btn = None
        self._pending_commit = None

        self.setMinimumWidth(min_width)
        self.setProperty("class", self.__class__.__name__)

        if help_text:
            self.header.set_help_text(help_text)

        # Message: one rich-text line, ABOVE the rows (the base placed its
        # form region first), only when the caller supplies one. It takes the
        # caption's plate -- prose over a translucent body is as unreadable as
        # a caption is -- but not the caption hook itself: it names no field,
        # and it WRAPS, so it needs vertical room a form row must not have.
        self._message_label = QtWidgets.QLabel("")
        self._message_label.setObjectName("formPanelMessage")
        self._message_label.setWordWrap(True)
        self._message_label.setVisible(bool(message))
        if message:
            self._message_label.setText(message)
        self.body_layout.insertWidget(0, self._message_label)

        #: objectName -> field widget, in add order.
        self._editors: Dict[str, QtWidgets.QWidget] = {}
        #: objectName -> the widgets that grey out WITH the field.
        self._companions: Dict[str, list] = {}
        #: objectName -> the ``"check"`` row that can switch it back on.
        self._dependencies: Dict[str, str] = {}
        #: objectName -> the enabled state it was added with.
        self._static_enabled: Dict[str, bool] = {}
        self._specs: List[dict] = []

        # Output pane — the panel's ONE text area.
        self._output_group = None
        self.output = None
        if output:
            self._build_output_pane()

        # Buttons in the footer, so the body is only ever the form. A
        # QDialogButtonBox (rather than loose buttons) keeps the platform
        # button order and gives callers the standard Ok/Cancel lookup.
        #
        # A run-in-place panel gets NO reject button: the header already draws
        # this window's close, and a Close in the footer beside the verb is a
        # second control for something already on screen — worse, it sits
        # where the eye looks for the action. A modal keeps Cancel, where
        # discarding really is one of the two answers.
        wants_cancel = bool(cancel_text) or on_run is None
        buttons = QtWidgets.QDialogButtonBox.Ok
        if wants_cancel:
            buttons |= QtWidgets.QDialogButtonBox.Cancel
        self.button_box = QtWidgets.QDialogButtonBox(buttons)
        self._ok_btn = self.button_box.button(QtWidgets.QDialogButtonBox.Ok)
        self._cancel_btn = self.button_box.button(QtWidgets.QDialogButtonBox.Cancel)
        if not callable(ok_text):
            self._ok_btn.setText(str(ok_text))
        if self._cancel_btn is not None:
            self._cancel_btn.setText(cancel_text or "Cancel")
        self._ok_btn.setDefault(True)
        for btn in (self._ok_btn, self._cancel_btn):
            if btn is not None:
                btn.setMinimumWidth(max(btn.sizeHint().width() * 2, 90))
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self._on_reject)
        self.footer.add_widget(self.button_box, side="right", background=True)

        self.set_fields(fields)

    # ------------------------------------------------------------------
    # Building — the base's add(), plus field registration
    # ------------------------------------------------------------------

    def add(
        self,
        x,
        label: Optional[str] = None,
        hint: Optional[str] = None,
        tooltip: Optional[str] = None,
        companions=(),
        label_align=None,
        enabled_by: Optional[str] = None,
        **kwargs,
    ):
        """:meth:`WindowPanel.add`, and the widget becomes a FIELD when it can.

        A value-bearing widget (see ``_FIELD_TYPES``) with an ``objectName``
        is registered under that name: :meth:`values` reads it, its change
        signal re-validates, and its caption and companions grey out with it.
        Anything else is plain content, placed and exposed but not read.

        The base's positional parameters are spelled out, in its order, so
        ``add("LineEdit", "Search in")`` means the same thing here as on any
        other window — the one extra, ``enabled_by``, comes after them.

        Parameters:
            enabled_by: Name of a ``"check"`` row that can switch this one
                back on: the row is live when it was added enabled OR that
                box is ticked, re-evaluated as it is toggled. A settled row
                an opt-in reopens needs this, or the opt-in is unreachable —
                ticking a box beside a row that stays grey does nothing.
            **kwargs: the setter/signal kwargs of :meth:`WindowPanel.add`.
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
                    enabled_by=enabled_by,
                    **kwargs,
                )
                for item in x
            ]
        widget = super().add(
            x,
            label=label,
            hint=hint,
            tooltip=tooltip,
            companions=companions,
            label_align=label_align,
            **kwargs,
        )
        self._register_field(widget, enabled_by)
        return widget

    def clear_rows(self) -> None:
        """The base's, plus the field registries — they point at those rows.

        A registry left behind would hand :meth:`values` a deleted widget;
        clearing it HERE rather than only in :meth:`set_fields` keeps a direct
        ``clear_rows()`` on a form as safe as on any other window.
        """
        super().clear_rows()
        self._editors.clear()
        self._companions.clear()
        self._dependencies.clear()
        self._static_enabled.clear()

    @classmethod
    def _field_signal(cls, widget) -> Optional[str]:
        """The change-signal name that makes *widget* a field, or None."""
        for widget_type, signal in cls._FIELD_TYPES:
            if isinstance(widget, widget_type):
                return signal
        return None

    def _register_field(self, widget, enabled_by) -> None:
        name = widget.objectName()
        signal = self._field_signal(widget)
        if not name or signal is None:
            return
        self._editors[name] = widget
        self._companions[name] = list(self._row_widgets.get(widget, ()))
        self._static_enabled[name] = widget.isEnabled()
        if enabled_by:
            self._dependencies[name] = enabled_by
        # Connected AFTER the widget was configured by add(), so seeding a
        # value never fires a validation over a half-built form.
        getattr(widget, signal).connect(self._on_field_changed)

    def _on_field_changed(self, *_args) -> None:
        self._apply_dependencies()
        self.revalidate()

    # ------------------------------------------------------------------
    # Fields — the declarative layer over add()
    # ------------------------------------------------------------------

    def set_fields(self, fields) -> None:
        """(Re)build the rows from *fields* — each spec is one :meth:`add`.

        Recognized keys:

        - ``name`` (required) — the widget's ``objectName``: the key in
          :meth:`values`, and the attribute the widget is exposed as
          (``panel.source_dir``).
        - ``label`` — bold caption to the LEFT of the editor. Defaults to
          ``name``.
        - ``label_align`` — where that caption's TEXT sits in the column its
          plate fills: ``"left"`` (default), ``"right"``, ``"center"``. Right
          reads as a lead-in to the control beside it (``"Operation:"``);
          left keeps a leading marker lined up down the column.
        - ``kind`` — ``"text"`` (default), ``"dir"`` / ``"file"`` (line edit
          carrying its own inline browse button), ``"choice"`` (combo over
          ``items``), ``"check"`` (checkbox whose ``label`` is its own
          text).
        - ``value`` — initial value; for ``"choice"``, the selected entry.
        - ``placeholder`` — greyed text shown in an empty ``"text"``/``"dir"``/
          ``"file"`` editor. What LEAVING IT EMPTY does, said where the empty
          field is: an answer the form accepts is not a gap to be explained
          in a tooltip nobody hovers.
        - ``items`` — entries for ``"choice"``.
        - ``hint`` — what this row will DO. Shown on hover, over the label
          AND the editor, so it is reachable from wherever the pointer is.
        - ``tooltip`` — pre-formatted rich text, used verbatim in place of
          the ``label``/``hint`` pair a plain hint is composed into.
        - ``enabled`` — False greys the row out. It still reports its value,
          so a settled step ("all paths resolve — nothing to search") stays
          visible with its reason rather than vanishing and leaving a gap.
        - ``enabled_by`` — see :meth:`add`.
        - ``start_dir`` — where a ``"dir"``/``"file"`` browse opens; defaults
          to the row's current value.
        - ``inline`` — field specs (same keys) placed in this row's cell, to
          the RIGHT of its editor, instead of rows of their own. For the
          second answer that belongs WITH the first — a dry-run tick beside
          the operation it previews — where a row of its own would put a
          caption on a question the row beside it already asked. Each is a
          field in full: read by :meth:`values`, re-validating on change,
          exposed as ``panel.<name>``. It shares the host row's enabled
          state, since the row greys as one.

        This method OWNS the form region: a re-seed clears it, including
        anything :meth:`add` placed there directly since the last one.
        """
        specs = [dict(f) for f in (fields or [])]
        if not specs:
            raise ValueError("FormPanel requires at least one field.")
        for spec in specs:
            if not spec.get("name"):
                raise ValueError(f"Every field needs a 'name': {spec!r}")

        self._reset_form()
        self._specs = specs
        for spec in specs:
            self._add_field(spec)
        self._apply_dependencies()
        self.revalidate()

    def _reset_form(self) -> None:
        """Drop the rows and everything the footer is still saying about them.

        A failed run, a plan armed for a scope that is no longer loaded — the
        rows just changed, so all of it now describes something that is not
        here. ``_validation_error`` resets WITH the status: revalidate's
        no-op guard compares against it, and a rebuilt form that happens to
        fail with the same message would otherwise skip the rewrite — OK
        disabled with an empty footer, the reason nowhere on screen.
        """
        self.clear_rows()
        self.disarm_apply()
        self._validation_error = ""
        self.set_status("")

    def _add_field(self, spec) -> QtWidgets.QWidget:
        """One spec → one :meth:`add`, plus any field riding the same row.

        The widget is built and SEEDED before it is added: ``add`` connects
        the change signal on registration, and a value set after that would
        validate a form that is still half-built. The browse button is
        attached AFTER — it wraps the editor in place, so the editor has to
        be in the layout first.
        """
        inline_specs = [dict(sub) for sub in (spec.get("inline") or [])]
        for sub in inline_specs:
            if not sub.get("name"):
                raise ValueError(f"Every inline field needs a 'name': {sub!r}")
        widget = self._build_field_widget(spec)
        inline_widgets = [self._build_field_widget(sub) for sub in inline_specs]

        # A checkbox's label IS its box text, so no caption: a heading over a
        # checkbox reads as a second control.
        label = (
            None
            if spec.get("kind") == "check"
            else str(spec.get("label") or spec["name"])
        )
        self.add(
            widget,
            label=label,
            hint=spec.get("hint"),
            tooltip=spec.get("tooltip"),
            companions=inline_widgets,
            label_align=spec.get("label_align"),
            enabled_by=spec.get("enabled_by"),
        )
        for sub, sub_widget in zip(inline_specs, inline_widgets):
            self._register_inline_field(sub, sub_widget)
        self._share_row_width(widget, inline_widgets)
        for sub, sub_widget in ((spec, widget), *zip(inline_specs, inline_widgets)):
            if sub.get("kind") in ("dir", "file"):
                self._attach_browse(sub, sub_widget)
        return widget

    def _build_field_widget(self, spec) -> QtWidgets.QWidget:
        """One spec → its configured widget, not yet placed in a row.

        Split out from :meth:`_add_field` because an ``inline`` spec is the
        same field built the same way — it is only PLACED differently (in
        its host's cell rather than a row of its own).
        """
        name = spec["name"]
        kind = spec.get("kind", "text")
        label = str(spec.get("label") or name)
        if kind == "check":
            widget = self._build_widget("CheckBox")
            widget.setText(label)
            widget.setChecked(bool(spec.get("value")))
        elif kind == "choice":
            widget = self._build_widget("ComboBox")
            widget.addItems([str(i) for i in (spec.get("items") or [])])
            if spec.get("value") is not None:
                index = widget.findText(str(spec["value"]))
                if index >= 0:
                    widget.setCurrentIndex(index)
        else:
            widget = self._build_widget("LineEdit")
            widget.setText(str(spec.get("value") or ""))
            if spec.get("placeholder"):
                widget.setPlaceholderText(str(spec["placeholder"]))
        widget.setObjectName(name)
        widget.setEnabled(bool(spec.get("enabled", True)))
        return widget

    def _share_row_width(self, widget, inline_widgets) -> None:
        """Split the cell evenly between the field and the fields inline with it.

        A companion BUTTON rides at its own hint — it is a control on the
        field, and the width belongs to the field. An inline FIELD is not:
        it is a second answer, and a row where one answer is a full-width
        control and the next is jammed against the margin reads as one
        control with a label stuck to it. Equal stretch gives them equal
        width, so the pair reads as the pair it is.
        """
        if not inline_widgets:
            return
        cell = self._rows_layout.itemAt(
            self._rows_layout.rowCount() - 1, QtWidgets.QFormLayout.FieldRole
        ).layout()
        if cell is None:  # no companions -> the widget stands in the cell alone
            return
        for target in (widget, *inline_widgets):
            cell.setStretchFactor(target, 1)

    def _register_inline_field(self, spec, widget) -> None:
        """Make a companion widget a FIELD in its own right.

        It shares its host's cell, so it also shares the host's enabled
        state (:meth:`WindowPanel._add_row` greys a row whole) — but its
        VALUE is its own: it is read by :meth:`values`, re-validates on
        change, and answers to ``panel.<name>`` like any other field.

        Its tooltip is re-stated here because the row's went onto every
        widget in the cell: an inline field names something the host row
        does not, so the hint under the pointer has to be its own.
        """
        tip = self._row_tooltip(
            spec.get("label") or spec["name"], spec.get("hint"), spec.get("tooltip")
        )
        if tip:
            widget.setToolTip(tip)
        self._register_field(widget, spec.get("enabled_by"))
        self._expose_as_attribute(widget)

    def _attach_browse(self, spec, editor) -> None:
        """The picker for a path field, as the editor's own option button.

        An inline option-box button rather than a *Browse…* beside the
        field: the button is the width of its icon instead of its caption,
        and every pixel it gives back goes to the one thing on the row that
        is never wide enough — the path. It still reads as subordinate to
        the labelled field (it sits INSIDE it), which is what kept the
        native picker legible when it was a button.
        """
        editor.option_box.add_action(
            icon="folder",
            tooltip=f"Browse for a {'file' if spec.get('kind') == 'file' else 'folder'}…",
            callback=lambda s=spec, e=editor: self._browse(s, e),
        )

    def _browse(self, spec, line) -> None:
        start = spec.get("start_dir") or line.text() or ""
        # Suspend any host busy-cursor so the picker shows normal cursors.
        caption = str(spec.get("label") or spec["name"])
        with CursorManager.suspend():
            if spec.get("kind") == "file":
                chosen, _ = QtWidgets.QFileDialog.getOpenFileName(self, caption, start)
            else:
                chosen = QtWidgets.QFileDialog.getExistingDirectory(
                    self, caption, start
                )
        if chosen:
            line.setText(chosen.replace("\\", "/"))

    # ------------------------------------------------------------------
    # Reactivity
    # ------------------------------------------------------------------

    def _apply_dependencies(self, *_args) -> None:
        """Re-evaluate every ``enabled_by`` row against its driver checkbox.

        The caption and any companion buttons travel with the editor so the
        whole row greys out and comes back together — a live editor under a
        greyed label reads as neither.
        """
        for name, driver_name in self._dependencies.items():
            driver = self._editors.get(driver_name)
            if driver is None:
                continue
            live = self._static_enabled.get(name, True) or (
                driver.isChecked() if isinstance(driver, QtWidgets.QCheckBox) else False
            )
            for widget in (self._editors.get(name), *self._companions.get(name, ())):
                if widget is not None:
                    widget.setEnabled(live)

    def revalidate(self, *_args) -> str:
        """Re-run the validator, retitle the accept button, show the reason.

        The reason goes in the FOOTER — the panel's one status line — so an
        invalid form never grows a body widget that pushes the controls
        around as the user types.

        Returns:
            str: the current validation error, "" when the form is valid.
        """
        values = self.values()
        error = (self._validate(values) if self._validate is not None else "") or ""
        self._ok_btn.setEnabled(not error and not self._running)
        if callable(self._ok_text):
            self._ok_btn.setText(str(self._ok_text(values)))
        # Only ever writes the status it OWNS. A run failure is also an
        # error-level footer line, and the ``finally`` that re-enables the
        # button re-validates — clearing on "the footer shows an error" would
        # wipe the report of the failure that just happened.
        if error != self._validation_error:
            self._validation_error = error
            self.set_status(error, level="error" if error else None)
        return error

    # ------------------------------------------------------------------
    # Values
    # ------------------------------------------------------------------

    def values(self) -> dict:
        """``{name: value}`` for every field, including disabled ones.

        A disabled row reports its value because it is a settled ANSWER, not
        an absent one — "the destination is sourceimages" stays true while
        the row that says so is greyed. One branch per ``_FIELD_TYPES`` row.
        """
        out = {}
        for name, editor in self._editors.items():
            if isinstance(editor, QtWidgets.QCheckBox):
                out[name] = editor.isChecked()
            elif isinstance(editor, QtWidgets.QComboBox):
                out[name] = editor.currentText()
            else:
                out[name] = editor.text().strip()
        return out

    def set_values(self, values: dict) -> None:
        """Write *values* back into the matching fields (unknown names ignored)."""
        for name, value in (values or {}).items():
            editor = self._editors.get(name)
            if editor is None:
                continue
            if isinstance(editor, QtWidgets.QCheckBox):
                editor.setChecked(bool(value))
            elif isinstance(editor, QtWidgets.QComboBox):
                index = editor.findText(str(value))
                if index >= 0:
                    editor.setCurrentIndex(index)
            else:
                editor.setText(str(value or ""))

    def editor(self, name: str):
        """The field widget named *name*, or None (``panel.<name>`` is the same)."""
        return self._editors.get(name)

    # ------------------------------------------------------------------
    # Output pane
    # ------------------------------------------------------------------

    def _build_output_pane(self) -> None:
        """One collapsable log pane, matching the Scene Exporter's.

        ``QTextBrowser`` rather than ``QTextEdit`` because the log handler
        routes ``action://`` links through ``anchorClicked`` — a log line
        that can offer "select the node" is worth the two extra settings.
        """
        from uitk.widgets.collapsableGroup import CollapsableGroup

        self._output_group = CollapsableGroup("• • •", self)
        self._output_group.setObjectName("output_grp")
        self._output_group.setAlignment(QtCore.Qt.AlignCenter)
        font = self._output_group.font()
        font.setBold(True)
        self._output_group.setFont(font)

        group_layout = QtWidgets.QVBoxLayout(self._output_group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(1)

        self.output = QtWidgets.QTextBrowser(self._output_group)
        self.output.setObjectName("output")
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(90)
        self.output.setOpenLinks(False)
        self.output.setOpenExternalLinks(False)
        group_layout.addWidget(self.output)

        self.body_layout.addWidget(self._output_group, 1)

    @property
    def logger(self):
        """Per-instance logger whose records land in the output pane.

        Per-INSTANCE, not the class-shared logger a ``LoggingMixin`` hands
        out: two panels open at once would otherwise append into each
        other's pane, and closing one would tear down the other's handler.
        """
        if self._logger is None:
            self._logger = self._build_logger()
        return self._logger

    def _build_logger(self):
        """Build (and redirect) this panel's logger — the Scene Exporter recipe."""
        import logging

        logger = logging.Logger(f"uitk.FormPanel.{id(self):x}", logging.NOTSET)
        logger.propagate = False
        logger.parent = None
        try:
            from pythontk.core_utils.logging_mixin import LoggerExt

            LoggerExt.patch(logger)
        except ImportError:  # pragma: no cover — pythontk is a hard dep in practice
            return logger

        logger.setLevel(logging.INFO)
        logger.hide_logger_name(True)
        if self.output is not None:
            from uitk.widgets.textEditLogHandler import TextEditLogHandler

            logger.set_text_handler(TextEditLogHandler)
            logger.setup_logging_redirect(self.output)
        return logger

    def clear_output(self) -> None:
        if self.output is not None:
            self.output.clear()

    def set_status(self, text: str, level: Optional[str] = None) -> None:
        """Footer status line. ``level`` colours it (info/success/warning/error)."""
        self.footer.setStatusText(text, level)

    # ------------------------------------------------------------------
    # Accept / run
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        if self._running:
            return
        error = self.revalidate()
        if error:
            return

        values = self.values()
        if self._on_run is None:
            self._accepted = True
            self._finish_modal()
            self.close()
            return

        self.run(values)

    def run(self, values: dict = None) -> None:
        """Run the handler in place with the panel still open."""
        if self._on_run is None or self._running:
            return
        values = self.values() if values is None else values
        self._invoke(lambda: self._on_run(values), values)

    def apply_pending(self) -> None:
        """Commit the plan the last preview armed, reported like any other run."""
        commit = self._pending_commit
        if commit is None or self._running:
            return
        self._invoke(commit, self.values())

    def _invoke(self, call, values) -> None:
        """Run one pass — a preview, a live run, or an armed commit — and report it.

        Failures are reported into the pane and the footer rather than raised
        at a caller that is a Qt signal — a traceback into the DCC's script
        editor is exactly the "look somewhere else" this panel exists to
        remove. A cancel is an ANSWER, not a failure, so it gets its own
        branch: what the handler got through stays in the pane and the footer
        says why it stopped, rather than colouring a deliberate stop red.

        Any pass supersedes the one before it, so an armed plan is dropped
        BEFORE the new work starts: a button still offering to commit a
        preview that a later run has invalidated is worse than no button.
        """
        self._running = True
        self._ok_btn.setEnabled(False)
        self.disarm_apply()
        self.clear_output()
        self.set_status(self.RUNNING_STATUS)
        QtWidgets.QApplication.processEvents()
        try:
            outcome = call()
        except self._cancelled_exceptions():
            self.logger.warning("Cancelled.")
            self.set_status("Cancelled.", level="warning")
        except Exception as error:  # noqa: BLE001 — reported, not swallowed
            self.logger.exception(f"{error}")
            self.set_status(str(error), level="error")
        else:
            if callable(outcome):
                # The handler previewed instead of committing, and handed back
                # the call that WOULD commit it.
                self.arm_apply(outcome)
            elif self.footer.statusText() == self.RUNNING_STATUS:
                # A handler that said nothing about itself gets the
                # placeholder cleared rather than left reading "Working…"
                # over finished work.
                self.set_status("")
            self.ran.emit(dict(values))
        finally:
            self._running = False
            self.revalidate()

    # -- armed preview ---------------------------------------------------

    @property
    def pending_commit(self):
        """The call the armed Apply button would make, or None."""
        return self._pending_commit

    def arm_apply(self, commit: Callable, note: str = None) -> None:
        """Hold *commit* — the identical live call — behind an Apply button.

        The button is created on first use and lives to the RIGHT of the
        accept button: the verb the user pressed stays where they pressed it,
        and the new affordance arrives beside it rather than under their
        cursor. Same contract as the naming panel's dry run.
        """
        self._pending_commit = commit
        if self._apply_btn is None:
            self._apply_btn = self.footer.add_action_button(
                text=self._apply_text,
                icon_name="check",
                tooltip="Apply the changes the last preview reported.",
                callback=self.apply_pending,
            )
        self._apply_btn.setVisible(True)
        self.set_status(
            note or f"Preview only — {self._apply_text} to commit", level="warning"
        )

    def disarm_apply(self) -> None:
        """Drop any armed plan and hide the Apply button.

        Gated on having BEEN armed, not on ``isVisible()``: a child of an
        unshown window reads as invisible however it was set, which would
        leave the footer note behind.
        """
        was_armed = self._pending_commit is not None
        self._pending_commit = None
        if self._apply_btn is not None and was_armed:
            self._apply_btn.setVisible(False)
            self.set_status("")

    @staticmethod
    def _cancelled_exceptions():
        """The ecosystem's cooperative-cancel signal, as an ``except`` tuple.

        ``pythontk.OperationCancelled`` derives from **BaseException** on
        purpose, so a bulk slot's Esc-cancel is not swallowed by an ordinary
        ``except Exception`` somewhere down the stack. The same choice makes
        it escape a Qt signal, though — the one place a raised object has
        nowhere to go — so the panel names it explicitly rather than widening
        its catch to everything. An empty tuple (matching nothing) when
        pythontk is not importable.
        """
        try:
            from pythontk.core_utils.cancel_scope import OperationCancelled
        except ImportError:  # pragma: no cover — pythontk is a hard dep here
            return ()
        return (OperationCancelled,)

    def _on_reject(self) -> None:
        self._accepted = False
        self._finish_modal()
        self.close()

    # ------------------------------------------------------------------
    # Modal mode
    # ------------------------------------------------------------------

    def exec_panel(self) -> bool:
        """Show modally, block, and return whether the form was accepted.

        ``WindowPanel`` is a QWidget, not a QDialog, so the block is a local
        event loop rather than ``exec_``. The modality is set BEFORE the
        window flags are re-applied: ``setWindowModality`` silently resets
        ``windowFlags`` to the widget-type defaults, which would strip the
        frameless-window flags the chrome is drawn against.
        """
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(self._panel_flags)

        self._accepted = False
        loop = QtCore.QEventLoop()
        self._modal_loop = loop
        # Suspend any slot busy-cursor for the modal, so the fields show an
        # I-beam and the buttons an arrow instead of the busy hourglass.
        with CursorManager.suspend():
            self.present()
            loop.exec_()
        return self._accepted

    def _finish_modal(self) -> None:
        """Release :meth:`exec_panel`'s event loop, if one is running."""
        loop, self._modal_loop = self._modal_loop, None
        if loop is not None and loop.isRunning():
            loop.quit()

    def hideEvent(self, event):
        # The header's hide button and a window-manager close both arrive as
        # a hide, and a modal loop left spinning behind a hidden window locks
        # the host. Ending it here covers every dismissal path.
        self._finish_modal()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._finish_modal()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        # A frameless window gets no window-manager close, and outside a
        # QDialog there is no default-button machinery either, so the panel
        # wires both keys itself.
        if event.key() == QtCore.Qt.Key_Escape:
            self._on_reject()
            return
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            # Never over a focused button: Return on a Browse must browse, and
            # on Apply must apply. Accepting here can move files — it is not
            # a key to fire on a guess about what has focus.
            # ``self.focusWidget()``, not the application's: the app-wide one
            # reports whatever last held focus anywhere, so a button in
            # another window would veto this panel's Return.
            if not isinstance(self.focusWidget(), QtWidgets.QAbstractButton):
                if self._ok_btn.isEnabled():
                    self._on_accept()
            return
        super().keyPressEvent(event)

    def _fit_to_content(self):
        """Fit to the form, not to a table — and never below the asked-for size.

        ``WindowPanel._fit_to_content`` measures a contained QTableWidget;
        this panel's growable child is the output pane, whose minimum is
        already in the layout hint, so ``adjustSize`` is the right fit.

        It runs on a zero-timer AFTER the first show, though, so a caller that
        sized the window before showing it would watch that size snap back to
        the form's minimum — and the output pane, the one child that wants the
        room, is exactly what gets squeezed. Grow to fit; never shrink past
        what was asked for.
        """
        width, height = self.width(), self.height()
        self.adjustSize()
        self.resize(max(self.width(), width), max(self.height(), height))


# --------------------------------------------------------------------------------------------

# module name
# print(__name__)
# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
