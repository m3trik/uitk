# !/usr/bin/python
# coding=utf-8
import html
import json
import re
from typing import Any, Callable, List, Optional, Union
from qtpy import QtWidgets, QtCore
import pythontk as ptk
from uitk.managers.cursor_manager import CursorManager
from uitk.themes.style_sheet import StyleSheet


class _Dialogs:
    """Modal dialogs and work feedback behind the Switchboard: message / input /
    file / form dialogs, the data and text viewers, the footer progress context and
    the busy cursor. Owns the passive message-box popup it reuses; reads the
    Switchboard (its Qt parent, registered widgets, active UI) at call time.
    """

    def __init__(self, sb):
        self._sb = sb

    @staticmethod
    def busy_cursor(shape=QtCore.Qt.WaitCursor):
        return CursorManager.busy(shape)

    def progress(
        self,
        ui=None,
        total: Optional[int] = None,
        text: str = "",
        busy: Optional[bool] = None,
    ):
        if ui is None:
            ui = getattr(self._sb, "active_ui", None) or getattr(
                self._sb, "current_ui", None
            )
        footer = getattr(ui, "footer", None) if ui is not None else None
        if footer is not None and hasattr(footer, "progress"):
            return footer.progress(total=total, text=text, busy=busy)
        return _NoOpProgressContext()

    @staticmethod
    def progress_adapter(
        update: Callable[..., bool],
    ) -> Callable[..., bool]:
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
        return self._sb.message_box(question, yes, no) == yes

    def message_box(
        self,
        string,
        *buttons,
        location="topMiddle",
        timeout="auto",
        background=0.75,
        default=None,
    ):
        # Log text without HTML tags
        self._sb.logger.info(f"# {re.sub('<.*?>', '', string)}")

        # Use a new instance for modal (exec) boxes to avoid reentrancy bugs
        if buttons:
            msg_box = self._sb.registered_widgets.MessageBox(self._sb.parent())
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
            if not hasattr(self, "popup"):
                self.popup = self._sb.registered_widgets.MessageBox(self._sb.parent())

            self.popup.location = location
            self.popup.timeout = timeout
            self.popup.setText(string, background=background)
            self.popup.show()
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
        on_refresh: Optional[Callable[[], Any]] = None,
    ):
        # Log a stripped, length-capped preview so reports don't flood
        # the log file the way an uncapped echo would.
        # Entities too: escaped content (a JSON report) would log as &quot;.
        preview = html.unescape(re.sub("<.*?>", "", text or ""))
        if len(preview) > 500:
            preview = preview[:500] + "…"
        if preview:
            self._sb.logger.info(f"# {preview}")

        dlg = self._sb.registered_widgets.TextViewBox(
            parent=parent if parent is not None else self._sb.parent(),
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
        if on_refresh is not None:
            dlg.header.config_buttons("refresh", *dlg.header.buttons)
            dlg.header.refresh_requested.connect(on_refresh)

        # Keep alive via the existing gc_protect helper so the caller
        # can return without the window being collected.
        self._sb.gc_protect(dlg)
        dlg.show()

        # Non-modal: this returns while the slot dispatcher still holds a
        # WaitCursor override (popped only in its ``finally``). Unlike the
        # modal dialogs above we cannot suspend-and-restore around a
        # bounded event loop, so cancel the busy cursor outright — the
        # report is on screen and the user is meant to interact with it.
        CursorManager.drain()
        return dlg

    def preview_dialog(
        self,
        render: Callable[[dict], str],
        specs=(),
        *,
        values: Optional[dict] = None,
        on_change: Optional[Callable[[str, Any], None]] = None,
        actions: Optional[dict] = None,
        status: Optional[Callable[[dict, str], str]] = None,
        title: str = "",
        size=(960, 600),
        monospace: bool = True,
        word_wrap: bool = False,
        parent=None,
    ):
        known = self._sb.registered_widgets.TextViewBox.BUTTONS
        actions = dict(actions or {})
        unknown = [name for name in actions if name.lower() not in known]
        if unknown:
            raise ValueError(
                f"No button for the action(s) {unknown}: name one of "
                f"TextViewBox.BUTTONS ({', '.join(v[2] for v in known.values())})."
            )
        # Keyed by the canonical name a click reports ("Copy"), however the
        # caller spelled it ("copy").
        actions = {known[name.lower()][2]: action for name, action in actions.items()}
        dlg = self._sb.text_view_dialog(
            "",
            *actions,
            "Close",
            title=title,
            size=size,
            monospace=monospace,
            word_wrap=word_wrap,
            parent=parent,
        )
        dlg.bind_preview(
            render, specs, values=values, on_change=on_change, status=status
        )

        def on_clicked(name):
            action = actions.get(name)
            if action is not None:
                action(dlg)

        dlg.button_clicked.connect(on_clicked)
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
        # A dict of EMPTY CONTAINERS is empty (a store with no records); a falsy
        # scalar (0, False, "") is data and still shows, at the top level too.
        def is_empty(value):
            return isinstance(value, (dict, list, tuple)) and not value

        if (
            data is None
            or is_empty(data)
            or (isinstance(data, dict) and all(map(is_empty, data.values())))
        ):
            self._sb.message_box(empty_message)
            return None
        buttons = ("Ok",) if save_path is None else ("Save", "Ok")
        dlg = self._sb.text_view_dialog(
            self._sb.registered_widgets.TextViewBox.format_data(data),
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
                    self._sb.save_data_dialog(
                        data, title=title, path=save_path, parent=parent
                    )

            dlg.button_box.clicked.connect(on_clicked)
        return dlg

    def save_data_dialog(
        self, data: Any, title: str = "", path: str = "", parent=None
    ) -> Optional[str]:
        with CursorManager.suspend():
            picked, _ = QtWidgets.QFileDialog.getSaveFileName(
                parent if parent is not None else self._sb.parent(),
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
        self._sb.message_box(f"Saved to <hl>{ptk.format_path(picked, 'file')}</hl>.")
        return picked

    @staticmethod
    def file_dialog(
        file_types: Union[str, List[str]] = ["*.*"],
        title: str = "Select files to open",
        start_dir: str = "/home",
        filter_description: str = "All Files",
        allow_multiple: bool = True,
    ) -> Union[str, List[str]]:
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
                # Pinned first: a copied sheet otherwise draws what it leaves
                # undefined (the button box, an indicator) in the host's style.
                StyleSheet.pin_base_style(dlg)
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
                # Pinned first: a copied sheet otherwise draws what it leaves
                # undefined (the button box, an indicator) in the host's style.
                StyleSheet.pin_base_style(dlg)
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
        panel = _Dialogs.form_panel(
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
        from uitk.widgets.menu import Menu

        return Menu.run_modal(content_fn, parent=parent, **kwargs)


class _NoOpProgressContext:
    """Fallback context for Switchboard.progress() when no footer
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
