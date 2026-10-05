# !/usr/bin/python
# coding=utf-8
import html
import json
import re
from typing import Any, Callable, List, Optional, Union
from qtpy import QtWidgets, QtCore
import pythontk as ptk
from uitk.managers.cursor_manager import CursorManager


class SwitchboardDialogsMixin:
    """Modal dialogs and work feedback: message / input / file / form dialogs,
    the data and text viewers, the footer progress context and the busy
    cursor."""

    @staticmethod
    def busy_cursor(shape=QtCore.Qt.WaitCursor):
        """Application busy cursor for the duration of a ``with`` block.

        :meth:`CursorManager.busy` reached through the switchboard, for slot
        code that runs OUTSIDE dispatch (a worker callback, a method called
        directly). Every dispatched slot is already bracketed in one, so a
        slot body never needs it — and never touches
        ``QApplication.setOverrideCursor`` directly: the raw pair pops the top
        of the stack rather than its own entry.
        """
        return CursorManager.busy(shape)

    def progress(
        self,
        ui=None,
        total: Optional[int] = None,
        text: str = "",
        busy: Optional[bool] = None,
    ):
        """Context manager for cooperative progress / task feedback.

        Routes to the active UI's :meth:`Footer.progress` when a footer
        is available; otherwise returns a no-op so callers run unchanged
        on UIs without one.

        Two modes from one entry point:

        * Pass ``total=N`` for a determinate progress bar (known step
          count). Tick with ``update(i + 1)``.
        * Omit *total* (the default) for an indeterminate "task
          indicator" marquee. Tick with bare ``update()`` calls between
          work chunks to drive the animation.

        Adapter-driven slots can omit *total* even for determinate
        progress: :func:`progress_adapter` auto-syncs the bar's max
        from the callback's ``total`` argument on the first tick, so
        the slot doesn't need to pre-compute the loop size.

        The slot dispatcher already shows a system wait cursor for the
        duration of every slot — this is for slots that want *richer*
        feedback in the footer.

        Parameters:
            ui: UI hosting the footer. Defaults to ``active_ui``.
            total: Step count for determinate mode; ``None`` (default)
                selects indeterminate / task-indicator mode.
            text: Optional status text shown alongside the bar.
            busy: Show the footer's busy spinner beside the text. ``None``
                (default) shows it for indeterminate work only; ``True``
                keeps it on a determinate bar whose single steps are long
                (see ``Footer.set_busy``); ``False`` never shows it.

        Yields:
            ``update(value=None, text=None) -> bool`` — returns ``False``
            if the user cancelled (Esc-hold). In task-indicator mode,
            call with no arguments to advance the marquee.

        Determinate example::

            with self.sb.progress(total=len(items), text="Copying") as update:
                for i, item in enumerate(items):
                    process(item)
                    if not update(i + 1):
                        break  # user cancelled

        Task-indicator example::

            with self.sb.progress(text="Working: Get Scene Info") as tick:
                step_one()
                tick()       # pumps the event loop, advances the bar
                step_two()
                tick()
        """
        if ui is None:
            ui = getattr(self, "active_ui", None) or getattr(self, "current_ui", None)
        footer = getattr(ui, "footer", None) if ui is not None else None
        if footer is not None and hasattr(footer, "progress"):
            return footer.progress(total=total, text=text, busy=busy)
        return _NoOpProgressContext()

    @staticmethod
    def progress_adapter(
        update: Callable[..., bool],
    ) -> Callable[..., bool]:
        """Adapt the footer ``update`` callable to the shape downstream
        ``progress_callback`` parameters typically expect.

        Handles both ecosystem shapes with one adapter:

        * ``cb(current, total, message)`` — mayatk pattern
          (``SceneAnalyzer.analyze``, ``MatUtils.get_mat_info``…).
        * ``cb(percent)`` — pythontk pattern
          (``MapCompositor``; expects ``0..100``).

        **Auto-syncs the bar's max from the callback's ``total``** so
        slots don't have to pre-declare the loop size:

            with self.sb.progress(text="Analyzing") as update:
                analyzer.analyze(
                    progress_callback=self.sb.progress_adapter(update),
                )

        On the first tick where ``total > 0``, the bar's maximum is
        retotalled to that value (and the bar switches out of
        indeterminate mode if it was pulsing). Subsequent ticks
        re-sync only when ``total`` actually changes — so a single
        adapter handles fixed-percent callbacks (``total=100``),
        per-item count callbacks (``total=N``), and indeterminate
        ones (``total=0``).

        The returned callable forwards the bool from ``update``, so
        downstreams that read it for cooperative cancellation get it
        for free.
        """
        # The bound ``update`` carries a reference to the host footer,
        # which exposes :meth:`set_progress_total`. Falls back to a
        # no-op for unbound callables (``_NoOpProgressContext._noop``).
        footer = getattr(update, "__self__", None)
        set_total = getattr(footer, "set_progress_total", None)

        def adapted(*args, **kwargs) -> bool:
            value = None
            text = None
            if args and args[0] is not None:
                try:
                    value = int(args[0])
                except (TypeError, ValueError):
                    value = None
            if len(args) >= 3 and args[2] is not None:
                text = str(args[2])
            # Sync bar max from callback's ``total``. ``set_progress_total``
            # short-circuits on matching state, so the per-tick cost is
            # one int comparison once the bar is in sync.
            if set_total is not None and len(args) >= 2 and args[1] is not None:
                try:
                    cb_total = int(args[1])
                except (TypeError, ValueError):
                    cb_total = 0
                if cb_total > 0:
                    set_total(cb_total)
            return bool(update(value, text))

        return adapted

    def confirm(self, question, yes="Yes", no="No") -> bool:
        """Ask *question* in a modal :meth:`message_box` and answer True when
        the user chose *yes* -- the consent callable a tool's install offer
        takes (``ptk.ImgUtils.settle_ktx2_encoder(prompt=sb.confirm)``), so
        no panel re-spells "message_box(q, 'Yes', 'No') == 'Yes'" itself.
        """
        return self.message_box(question, yes, no) == yes

    def message_box(
        self,
        string,
        *buttons,
        location="topMiddle",
        timeout="auto",
        background=0.75,
        default=None,
    ):
        """Spawns a message box with the given text and optionally sets buttons.

        Parameters:
            string: HTML text to display.
            *buttons: Optional buttons: Qt standard-button names (``"Yes"``,
                ``"Cancel"``) or any other label, which becomes a button of
                its own (``"Override All"``). When provided the box is modal
                (``exec_``) and returns the clicked button's name or label;
                otherwise a passive popup.
            default: The button Enter answers, by name or label (modal
                only). ``None`` leaves Qt's choice.
            location: Placement hint (default ``"topMiddle"``).
            timeout: Auto-dismiss seconds for the passive popup. ``"auto"``
                (default) times it to the text -- long enough to read, never
                more than a few seconds (``MessageBox.reading_time``);
                ``None`` or ``0`` keeps it up until dismissed. A box with
                buttons always waits for its answer.
            background (bool/float/str): Controls the label background.
                ``True`` uses default dark grey at 50% opacity,
                ``False`` disables the background,
                a ``float`` 0–1 sets opacity (default 0.5),
                a CSS color ``str`` is used verbatim.
        """
        # Log text without HTML tags
        self.logger.info(f"# {re.sub('<.*?>', '', string)}")

        # Use a new instance for modal (exec) boxes to avoid reentrancy bugs
        if buttons:
            msg_box = self.registered_widgets.MessageBox(self.parent())
            msg_box.location = location
            msg_box.timeout = timeout
            msg_box.setStandardButtons(*buttons)
            if default is not None:
                msg_box.set_default_button(default)
            msg_box.setText(string, background=background)
            # Modal: suspend any slot busy-cursor so buttons show an arrow.
            with CursorManager.suspend():
                return msg_box.exec_()
        else:
            # Safe to reuse for passive popups
            if not hasattr(self, "_messageBox"):
                self._messageBox = self.registered_widgets.MessageBox(self.parent())

            self._messageBox.location = location
            self._messageBox.timeout = timeout
            self._messageBox.setText(string, background=background)
            self._messageBox.show()
            return None

    def text_view_dialog(
        self,
        text: str = "",
        *buttons,
        title: str = "",
        size=(640, 400),
        monospace: bool = False,
        word_wrap: bool = True,
        background=False,
        parent=None,
        link_handler=None,
    ):
        """Spawn a scrollable text-viewer window with optional buttons.

        Sibling to :meth:`message_box` for content too long or too
        structured for a passive popup (reports, log output, formatted
        result dumps). The viewer is a uitk :class:`WindowPanel`
        subclass with its own header, footer, and busy-indicator
        integration — same theming and chrome as the rest of the
        ecosystem's tool windows.

        Always non-modal: the viewer coexists with the host application
        (Maya, etc.) so the user can keep working while reading. The
        viewer's footer participates in the slot dispatcher's
        busy-indicator broadcast, so its own footer shows the
        "Working:" indicator if a slot is dispatched while it's open.

        Parameters:
            text: HTML or plain text to display. May be empty when the
                caller plans to populate via :meth:`TextViewBox.setText`
                / :meth:`append_text` after the call.
            *buttons: Standard-button name strings (``"Ok"``,
                ``"Cancel"``, etc. — same vocabulary as
                :meth:`message_box`). Buttons in the Accept / Reject /
                Destructive roles close the window; Apply / Reset /
                Help leave it open and surface their clicked name via
                ``TextViewBox.clicked_button``.
            title: Window title (shown in the header).
            size: Initial ``(width, height)``. Default ``(640, 400)``.
            monospace: Use a monospace body font. Default ``False``.
            word_wrap: Wrap long lines. ``False`` enables horizontal
                scrolling for tabular content. Default ``True``.
            background: Body background colour. Same semantics as
                :meth:`message_box`. Default ``False`` (widget default).
            parent: Anchor widget. Defaults to ``self.parent()``. The
                viewer reparents to ``parent.window()`` so it survives
                a transient invoker hiding.
            link_handler: ``handler(QUrl) -> bool`` offered each clicked
                link first (see :class:`TextViewBox`) -- pass a DCC's
                ``UiUtils.dispatch_log_link`` so a report's
                ``action://select`` links select what they name.

        Returns:
            The :class:`TextViewBox` instance — the caller can stream
            more content via :meth:`TextViewBox.append_text` or close
            it later via :meth:`close`.
        """
        # Log a stripped, length-capped preview so reports don't flood
        # the log file the way an uncapped echo would.
        # Entities too: escaped content (a JSON report) would log as &quot;.
        preview = html.unescape(re.sub("<.*?>", "", text or ""))
        if len(preview) > 500:
            preview = preview[:500] + "…"
        if preview:
            self.logger.info(f"# {preview}")

        dlg = self.registered_widgets.TextViewBox(
            parent=parent if parent is not None else self.parent(),
            title=title,
            monospace=monospace,
            word_wrap=word_wrap,
            link_handler=link_handler,
        )
        if size:
            dlg.resize(*size)
        if text:
            dlg.setText(text, background=background)
        if buttons:
            dlg.setStandardButtons(*buttons)

        # Keep alive via the existing gc_protect helper so the caller
        # can return without the window being collected.
        self.gc_protect(dlg)
        dlg.show()

        # Non-modal: this returns while the slot dispatcher still holds a
        # WaitCursor override (popped only in its ``finally``). Unlike the
        # modal dialogs above we cannot suspend-and-restore around a
        # bounded event loop, so cancel the busy cursor outright — the
        # report is on screen and the user is meant to interact with it.
        CursorManager.drain()
        return dlg

    def data_view_dialog(
        self,
        data: Any,
        *,
        title: str = "",
        save_path: Optional[str] = "",
        empty_message: str = "Nothing to show.",
        size=(720, 560),
        parent=None,
    ):
        """Show structured *data* as colour-coded JSON in a text viewer.

        The shared viewer for tool-authored data -- scene metadata, manifests,
        records -- so every caller gets the same look
        (:meth:`TextViewBox.format_data`) and the same Save, and polishing it
        polishes them all.

        Parameters:
            data: Any JSON-serializable value; one json cannot encode is shown
                as its ``str``.
            title: Window title; also names the Save dialog.
            save_path: Suggested file for the Save button (``""`` suggests
                none); ``None`` hides Save.
            empty_message: Shown in a message box instead of an empty viewer
                when *data* holds nothing: an empty container, or a dict whose
                values are all empty containers (a store with no records).
            size: Initial ``(width, height)``.
            parent: Anchor widget, as :meth:`text_view_dialog`.

        Returns:
            The :class:`TextViewBox`, or ``None`` when *data* was empty.
        """

        # A dict of EMPTY CONTAINERS is empty (a store with no records); a falsy
        # scalar (0, False, "") is data and still shows, at the top level too.
        def is_empty(value):
            return isinstance(value, (dict, list, tuple)) and not value

        if (
            data is None
            or is_empty(data)
            or (isinstance(data, dict) and all(map(is_empty, data.values())))
        ):
            self.message_box(empty_message)
            return None
        buttons = ("Ok",) if save_path is None else ("Save", "Ok")
        dlg = self.text_view_dialog(
            self.registered_widgets.TextViewBox.format_data(data),
            *buttons,
            title=title,
            size=size,
            monospace=True,
            word_wrap=False,
            parent=parent,
        )
        if save_path is not None:

            def on_clicked(button):
                if button.text().replace("&", "") == "Save":
                    self.save_data_dialog(
                        data, title=title, path=save_path, parent=parent
                    )

            dlg.button_box.clicked.connect(on_clicked)
        return dlg

    def save_data_dialog(
        self, data: Any, title: str = "", path: str = "", parent=None
    ) -> Optional[str]:
        """Write *data* as indented JSON to a ``.json`` file the user picks.

        :meth:`data_view_dialog`'s Save, usable on its own. Written atomically;
        a value json cannot encode is written as its ``str``.

        Returns:
            The written path, or ``None`` when the user cancelled.
        """
        with CursorManager.suspend():
            picked, _ = QtWidgets.QFileDialog.getSaveFileName(
                parent if parent is not None else self.parent(),
                f"Save {title or 'Data'} As",
                path,
                "JSON (*.json)",
            )
        if not picked:
            return None
        if not picked.lower().endswith(".json"):
            picked += ".json"
        ptk.FileUtils.atomic_write_text(
            picked, json.dumps(data, indent=2, ensure_ascii=False, default=str)
        )
        self.message_box(f"Saved to <hl>{ptk.format_path(picked, 'file')}</hl>.")
        return picked

    @staticmethod
    def file_dialog(
        file_types: Union[str, List[str]] = ["*.*"],
        title: str = "Select files to open",
        start_dir: str = "/home",
        filter_description: str = "All Files",
        allow_multiple: bool = True,
    ) -> Union[str, List[str]]:
        """Open a file dialog to select files of the given type(s) using qtpy.

        Parameters:
            file_types (Union[str, List[str]]): Extensions of file types to include. Can be a string or a list of strings.
                Default is ["*.*"], which includes all files.
            title (str): Title of the file dialog. Default is "Select files to open."
            start_dir (str): Initial directory to display in the file dialog. Default is "/home."
            filter_description (str): Description for the filter applied to the file types. Default is "All Files."
            allow_multiple (bool): Whether to allow multiple file selection. Default is True.

        Returns:
            Union[str, List[str]]: A string if a single file is selected, or a list of strings if multiple files are selected.

        Example:
            files = file_dialog(file_types=["*.png", "*.jpg"], title="Select images", filter_description="Images")
        """
        if isinstance(file_types, str):
            file_types = [file_types]

        options = QtWidgets.QFileDialog.Options()
        file_types_string = f"{filter_description} ({' '.join(file_types)})"

        with CursorManager.suspend():
            if allow_multiple:
                files, _ = QtWidgets.QFileDialog.getOpenFileNames(
                    None, title, start_dir, file_types_string, options=options
                )
                return files
            file, _ = QtWidgets.QFileDialog.getOpenFileName(
                None, title, start_dir, file_types_string, options=options
            )
            return file or None

    @staticmethod
    def dir_dialog(title: str = "Select a directory", start_dir: str = "/home") -> str:
        """Open a directory dialog to select a directory using qtpy.

        Parameters:
            title (str): Title of the directory dialog. Default is "Select a directory."
            start_dir (str): Initial directory to display in the dialog. Default is "/home."

        Returns:
            str: Selected directory path.

        Example:
            directory_path = dir_dialog(title="Select a project folder")
        """
        options = QtWidgets.QFileDialog.Options()
        with CursorManager.suspend():
            directory_path = QtWidgets.QFileDialog.getExistingDirectory(
                None, title, start_dir, options=options
            )

        return directory_path

    @staticmethod
    def save_file_dialog(
        file_types: Union[str, List[str]] = ["*.*"],
        title: str = "Save file",
        start_dir: str = "/home",
        filter_description: str = "All Files",
    ) -> Optional[str]:
        """Open a save-file dialog to choose a destination path.

        Parameters:
            file_types: Extensions to include (e.g. ``["*.wav"]``).
                Default is ``["*.*"]``.
            title: Dialog window title.
            start_dir: Initial directory / suggested file path.
            filter_description: Label for the file-type filter.

        Returns:
            The chosen file path, or *None* if the dialog was cancelled.

        Example:
            path = save_file_dialog(
                file_types=["*.wav"],
                title="Export audio",
                filter_description="WAV Files",
            )
        """
        if isinstance(file_types, str):
            file_types = [file_types]

        file_types_string = f"{filter_description} ({' '.join(file_types)})"

        with CursorManager.suspend():
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                None, title, start_dir, file_types_string
            )

        return path or None

    @staticmethod
    def input_dialog(
        title: str = "Input",
        label: str = "Enter value:",
        text: str = "",
        parent: QtWidgets.QWidget = None,
        placeholder: str = "",
        validate: callable = None,
        error_text: str = "Invalid input.",
    ) -> str:
        """Show a modal text-input dialog and return the entered string.

        Builds a small custom ``QDialog`` so it can be properly parented,
        styled to match the host application, and extended with inline
        validation feedback.  Falls back gracefully when no parent is
        supplied.

        Parameters:
            title: Window title.
            label: Descriptive label above the text field.
            text: Pre-filled text (e.g. the current value for rename).
            parent: Optional parent widget for correct modality and
                positioning.  Accepts any ``QWidget``.
            placeholder: Greyed-out hint shown when the field is empty.
            validate: Optional ``callable(text) -> bool``.  While it
                returns ``False`` the OK button stays disabled and a
                brief *error_text* is shown beneath the field.
            error_text: Message displayed when *validate* returns
                ``False``.

        Returns:
            str: The stripped text the user entered, or ``None`` if the
            dialog was cancelled or closed.
        """
        dlg = QtWidgets.QDialog(parent)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(280)

        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(6)

        lbl = QtWidgets.QLabel(label)
        layout.addWidget(lbl)

        line = QtWidgets.QLineEdit(text)
        if placeholder:
            line.setPlaceholderText(placeholder)
        line.selectAll()
        layout.addWidget(line)

        err_lbl = QtWidgets.QLabel("")
        err_lbl.setStyleSheet("color: #e05555; font-size: 11px;")
        err_lbl.setVisible(False)
        layout.addWidget(err_lbl)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        layout.addWidget(btn_box)

        ok_btn = btn_box.button(QtWidgets.QDialogButtonBox.Ok)

        def _validate_text(t=None):
            if t is None:
                t = line.text()
            if validate is not None:
                valid = validate(t)
                ok_btn.setEnabled(valid)
                err_lbl.setText("" if valid else error_text)
                err_lbl.setVisible(not valid)
            else:
                ok_btn.setEnabled(bool(t.strip()))

        line.textChanged.connect(_validate_text)
        _validate_text(text)

        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)

        # Inherit parent stylesheet so the dialog matches the host theme.
        if parent is not None:
            ss = parent.styleSheet()
            if ss:
                dlg.setStyleSheet(ss)

        # Modal: suspend any slot busy-cursor so the line edit shows an
        # I-beam and the buttons an arrow instead of the busy hourglass.
        with CursorManager.suspend():
            accepted = dlg.exec_() == QtWidgets.QDialog.Accepted
        if accepted:
            result = line.text().strip()
            return result if result else None
        return None

    @staticmethod
    def list_input_dialog(
        items,
        title: str = "Select",
        label: str = "Select item(s):",
        parent: QtWidgets.QWidget = None,
        multi: bool = True,
        selected=None,
    ) -> list:
        """Show a modal list picker and return the chosen entries.

        The list twin of :meth:`input_dialog` — same parenting, host-theme
        inheritance, and busy-cursor suspension, so a panel needing "pick some
        of these" doesn't hand-roll a ``QDialog`` that misses all three.

        Parameters:
            items: Iterable of entries. Non-strings are rendered with ``str``;
                the returned values are the rendered strings.
            title: Window title.
            label: Descriptive label above the list.
            parent: Optional parent widget for correct modality and position.
            multi: Allow selecting several entries (default). False restricts
                to one.
            selected: Optional iterable of entries to pre-select.

        Returns:
            list[str]: The selected entries, or ``[]`` if the dialog was
                cancelled or nothing was picked.
        """
        entries = [str(i) for i in (items or [])]
        preselect = {str(s) for s in (selected or [])}

        dlg = QtWidgets.QDialog(parent)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(280)

        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(6)
        layout.addWidget(QtWidgets.QLabel(label))

        listing = QtWidgets.QListWidget()
        listing.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
            if multi
            else QtWidgets.QAbstractItemView.SingleSelection
        )
        listing.addItems(entries)
        for row in range(listing.count()):
            if listing.item(row).text() in preselect:
                listing.item(row).setSelected(True)
        # Double-click is the expected commit gesture in a picker list.
        listing.itemDoubleClicked.connect(dlg.accept)
        layout.addWidget(listing)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        # Inherit parent stylesheet so the dialog matches the host theme.
        if parent is not None:
            ss = parent.styleSheet()
            if ss:
                dlg.setStyleSheet(ss)

        # Modal: suspend any slot busy-cursor so the list shows a normal
        # pointer instead of the busy hourglass.
        with CursorManager.suspend():
            accepted = dlg.exec_() == QtWidgets.QDialog.Accepted

        return [i.text() for i in listing.selectedItems()] if accepted else []

    @staticmethod
    def form_dialog(
        fields,
        title: str = "Options",
        parent: QtWidgets.QWidget = None,
        ok_text: Union[str, Callable] = "OK",
        validate: Callable = None,
        message: str = "",
    ) -> Optional[dict]:
        """Show a modal form of labelled rows and return ``{name: value}``.

        The multi-field twin of :meth:`input_dialog`, for the case a sequence
        of single-purpose dialogs handles badly: **two or more answers the
        user has to tell apart**. A pair of native folder pickers shown back
        to back are the same widget with different captions, so which one is
        "search here" and which is "write here" lives entirely in a title
        bar — and the answer changes when one of them is skipped. Side by
        side and labelled, there is nothing to confuse and no order to
        remember.

        The window is a :class:`~uitk.widgets.formPanel.FormPanel`, so it
        wears the toolset's own chrome (Header, Footer, theme) rather than a
        bare dialog's host default, and every row's ``hint`` is a formatted
        tooltip. See :meth:`FormPanel.set_fields` for the full field spec.

        Use this when the caller does the work AFTER the answers are in.
        When the work belongs on the form — a verb button, a log to watch,
        a second run with one value changed — use :meth:`form_panel`, which
        stays open and keeps its output pane.

        Parameters:
            fields: Iterable of row specs (dicts). See
                :meth:`FormPanel.set_fields`.
            title: Window title.
            parent: Optional parent for correct modality and position.
            ok_text: Accept-button text. Say what will happen ("Copy 12
                files") — the button is the last thing read before
                committing. A ``callable(values) -> str`` is re-evaluated on
                every edit, so a verb chosen ON the form (a Copy/Move row)
                reaches the button that names the operation.
            validate: Optional ``callable(values: dict) -> str``. Return ""
                (or None) when the form is valid, else the message to show in
                the footer; OK stays disabled while it is non-empty.
            message: Optional line above the rows.

        Returns:
            dict|None: ``{name: value}`` for every row, or None when the
            dialog was cancelled or closed.

        Example:
            paths = sb.form_dialog(
                [
                    {"name": "src", "kind": "dir", "label": "Search in",
                     "hint": "3 unresolved texture(s), searched recursively"},
                    {"name": "dest", "kind": "dir", "label": "Copy into",
                     "value": sourceimages, "hint": "12 file(s) land here"},
                ],
                title="Find & Copy Textures",
                ok_text="Copy 12 files",
                validate=lambda v: (
                    "Destination is the search folder — nothing would move."
                    if v["src"] and v["src"] == v["dest"] else ""
                ),
            )
        """
        panel = SwitchboardDialogsMixin.form_panel(
            fields,
            title=title,
            parent=parent,
            ok_text=ok_text,
            validate=validate,
            message=message,
            # A modal that closes before the work starts has nothing to
            # stream, so it carries no output pane.
            output=False,
        )
        accepted = panel.exec_panel()
        values = panel.values() if accepted else None
        panel.deleteLater()
        return values

    @staticmethod
    def form_panel(
        fields,
        title: str = "Options",
        parent: QtWidgets.QWidget = None,
        ok_text: Union[str, Callable] = "OK",
        cancel_text: str = None,
        validate: Callable = None,
        message: str = "",
        help_text: str = "",
        on_run: Callable = None,
        apply_text: str = "Apply",
        output: bool = True,
        min_width: int = 560,
        settings=None,
        settings_key: str = "window_geometry",
    ):
        """Build a :class:`~uitk.widgets.formPanel.FormPanel` — the modeless twin.

        The same rows as :meth:`form_dialog`, in a window that STAYS OPEN and
        runs the operation itself: the accept button calls ``on_run(values)``
        with the panel still up, the operation's log streams into the single
        output pane at the bottom, and the footer carries the status. That is
        the shape every other tool window in the toolset has, and it is what a
        modal cannot be — a modal that has closed can neither show what it did
        nor be re-run with one value changed.

        Does NOT show the panel: the caller decides, because a caller that
        keeps the panel (to re-seed it from live state on the next invocation
        rather than stacking a second window) needs the reference before the
        first show. Call ``panel.present()``. It is a ``WindowPanel``, so
        anything beyond the field specs is added the way a Menu item is —
        ``panel.add("PushButton", setText=..., clicked=...)``.

        Parameters:
            fields: Iterable of row specs (dicts). See
                :meth:`FormPanel.set_fields`.
            title: Header text.
            parent: Anchor widget; the panel reparents to ``parent.window()``.
            ok_text: Accept-button text, or ``callable(values) -> str``.
            cancel_text: Reject-button text. A run-in-place panel gets no
                reject button by default (the header carries the window's
                close); pass a string to force one.
            validate: ``callable(values: dict) -> str`` — "" when valid.
            message: Optional rich-text line above the rows.
            help_text: Rich text for the header's ``?`` button. Build it with
                ``sb.tooltip.fmt(...)``.
            on_run: ``callable(values: dict)`` run in place by the accept
                button. Return a ``callable()`` to say "this was a preview" —
                the panel arms Apply with it (the naming panel's dry-run
                contract). Omit for a panel the caller drives itself.
            apply_text: Text of the armed-preview button.
            output: Show the collapsable output pane (default True).
            min_width: Minimum window width.
            settings: Optional store (``sb.settings.branch("<tool>")``) the
                window's size and position survive across sessions in.
            settings_key: Settings key holding the serialized geometry.

        Returns:
            FormPanel: the (unshown) panel.

        Example:
            panel = sb.form_panel(
                fields,
                title="Find & Copy Textures",
                parent=self.ui,
                on_run=self._execute_find_and_copy,
                validate=self._validate_find_and_copy,
            )
            panel.present()
        """
        from uitk.widgets.formPanel import FormPanel

        return FormPanel(
            fields,
            title=title,
            parent=parent,
            ok_text=ok_text,
            cancel_text=cancel_text,
            validate=validate,
            message=message,
            help_text=help_text,
            on_run=on_run,
            apply_text=apply_text,
            output=output,
            min_width=min_width,
            settings=settings,
            settings_key=settings_key,
        )

    @staticmethod
    def modal_menu(content_fn, parent=None, **kwargs):
        """Show a themed modal Menu popup, block until dismissed.

        Convenience wrapper around :meth:`Menu.run_modal`.  See that method
        for full parameter documentation.

        Parameters:
            content_fn (callable): ``content_fn(menu, state)`` — populate the
                menu with widgets and store result data in *state*.
            parent (QWidget, optional): Parent widget.
            **kwargs: Forwarded to :meth:`Menu.run_modal` (``title``,
                ``buttons``, ``size``, ``min_size``, ``center``, etc.).

        Returns:
            dict or None: The *state* dict on accept, ``None`` on reject.
        """
        from uitk.widgets.menu import Menu

        return Menu.run_modal(content_fn, parent=parent, **kwargs)


class _NoOpProgressContext:
    """Fallback context for SwitchboardDialogsMixin.progress() when no footer
    is available. Yields a no-op update callable so caller code runs
    unmodified — just without visible progress feedback.
    """

    def __enter__(self):
        return self._noop

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    @staticmethod
    def _noop(value=None, text=None):
        return True
