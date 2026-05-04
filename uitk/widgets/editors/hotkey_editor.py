# !/usr/bin/python
# coding=utf-8
from typing import Callable, List, Optional
from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.mixins.style_sheet import StyleSheet
from uitk.widgets.editors.editor_panel import EditorPanel
from uitk.widgets.mixins.icon_manager import IconManager


# End-user-facing scopes. Widget/widget_children remain decorator-only.
USER_SCOPES = ("window", "application")
SCOPE_LABELS = {"window": "Win", "application": "App"}
SCOPE_ICONS = {"window": "window", "application": "screen"}
SCOPE_TOOLTIPS = {
    "window": "Window scope — fires only when this UI's window is focused. Click to switch to Application scope.",
    "application": "Application scope — fires anywhere in the host app. Click to switch to Window scope.",
}


class CollisionConflict:
    """A single conflict reported by a collision checker.

    Attributes:
        source: Where the conflict came from (e.g. "uitk", "maya").
        description: Human-readable explanation.
        breaks_binding: True when accepting the new binding will leave both
            sides in an undefined / unreliable state (e.g. two same-scope same-
            sequence shortcuts that Qt cannot disambiguate). When True the
            editor offers to auto-clear the conflicting binding.
        clear_action: Optional callable that clears the conflicting binding
            when the user accepts the auto-clear path. Required when
            ``breaks_binding`` is True for the conflict to be resolvable.
    """

    def __init__(
        self,
        source: str,
        description: str,
        breaks_binding: bool = False,
        clear_action: Optional[Callable[[], None]] = None,
    ):
        self.source = source
        self.description = description
        self.breaks_binding = breaks_binding
        self.clear_action = clear_action

    def __repr__(self) -> str:
        return (
            f"CollisionConflict(source={self.source!r}, "
            f"description={self.description!r}, "
            f"breaks_binding={self.breaks_binding}, "
            f"clear_action={'set' if self.clear_action else 'None'})"
        )


class KeyCaptureDialog(QtWidgets.QDialog):
    """Modal dialog to capture a key sequence."""

    def __init__(self, parent=None, current_sequence=""):
        super().__init__(parent)
        self.setWindowTitle("Assign Shortcut")
        self.setWindowIcon(
            self.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxInformation)
        )
        self.resize(300, 150)
        self._sequence = current_sequence

        layout = QtWidgets.QVBoxLayout(self)

        lbl = QtWidgets.QLabel("Press the key combination you want to assign:")
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(lbl)

        self.key_display = QtWidgets.QLabel(current_sequence or "None")
        self.key_display.setAlignment(QtCore.Qt.AlignCenter)
        font = self.key_display.font()
        font.setPointSize(14)
        font.setBold(True)
        self.key_display.setFont(font)
        self.key_display.setStyleSheet(
            "color: #4CAF50; border: 2px solid #555; padding: 10px; border-radius: 5px;"
        )
        layout.addWidget(self.key_display)

        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_clear = QtWidgets.QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_key)
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QtWidgets.QPushButton("OK")
        self.btn_ok.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_clear)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)

        self.style = StyleSheet(self)
        self.style.set(theme="dark")

    def keyPressEvent(self, event):
        """Capture key press event."""
        key = event.key()
        modifiers = event.modifiers()

        if key in (
            QtCore.Qt.Key_Control,
            QtCore.Qt.Key_Shift,
            QtCore.Qt.Key_Alt,
            QtCore.Qt.Key_Meta,
        ):
            return

        sequence = QtGui.QKeySequence(key | modifiers)
        text = sequence.toString(QtGui.QKeySequence.NativeText)

        self._sequence = text
        self.key_display.setText(text)

    def clear_key(self):
        self._sequence = ""
        self.key_display.setText("None")

    def get_sequence(self):
        return self._sequence


class HotkeyEditor(EditorPanel):
    """UI for editing global shortcuts with preset support.

    Presets capture all user-customised shortcut bindings across every
    loaded UI in a single JSON file so a named snapshot can be saved,
    restored, renamed, or deleted.
    """

    def __init__(self, switchboard, parent=None):
        super().__init__(
            title="Hotkey Editor",
            status_text="Customize keyboard shortcuts.",
            parent=parent,
        )
        self.sb = switchboard
        self.resize(600, 600)

        FIXED_H = 20

        # Preset row
        self.init_preset_row("hotkey_presets")

        # UI Selection
        ui_layout = QtWidgets.QHBoxLayout()
        ui_label = QtWidgets.QLabel("Target UI:")
        ui_label.setFixedHeight(FIXED_H)
        ui_label.setFixedWidth(
            ui_label.fontMetrics().horizontalAdvance(ui_label.text()) + 6
        )
        self.cmb_ui = QtWidgets.QComboBox()
        self.cmb_ui.setFixedHeight(FIXED_H)
        self.cmb_ui.currentTextChanged.connect(self.populate)
        ui_layout.addWidget(ui_label)
        ui_layout.addWidget(self.cmb_ui)
        self.body_layout.addLayout(ui_layout)

        # Collision checkers — registered by host (tentacle/mayatk) to detect
        # external conflicts (Maya hotkey sets, etc.). Built-in internal
        # checker is registered below.
        self._collision_checkers: List[Callable] = []
        self.add_collision_checker(self._builtin_internal_collision_checker)

        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Action", "Shortcut", "Scope", "Description", "Reset"]
        )
        self.table.horizontalHeader().setDefaultAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )
        # Scope and Reset columns are fixed-width, sized to fit the
        # square icon button exactly (no slack). Description (col 3)
        # absorbs the remaining horizontal space, so Reset stays pinned
        # to the right edge as the table resizes.
        self.table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.Fixed
        )
        self.table.setColumnWidth(2, 24)
        self.table.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QtWidgets.QHeaderView.Fixed
        )
        self.table.setColumnWidth(4, 24)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.body_layout.addWidget(self.table, 1)

        # Tighten spacing: central body layout sits at 2, every sub-row
        # layout (preset row, ui_layout, etc.) drops to 1 for a denser
        # editor without changing the row layout files themselves.
        self.body_layout.setSpacing(2)
        for i in range(self.body_layout.count()):
            sublayout = self.body_layout.itemAt(i).layout()
            if sublayout is not None:
                sublayout.setSpacing(1)

        self.refresh_ui_list()

    # ------------------------------------------------------------------
    # Preset hooks
    # ------------------------------------------------------------------

    def export_preset_data(self):
        return self.export_shortcuts()

    def import_preset_data(self, data):
        self.import_shortcuts(data)
        self.populate()

    # ------------------------------------------------------------------
    # Shortcut export / import
    # ------------------------------------------------------------------

    def export_shortcuts(self) -> dict:
        """Export all user-customised shortcuts across loaded UIs.

        Each binding exports as ``{"seq": str, "scope": str}``. The legacy
        string-only shape (``method_name: sequence``) remains supported on
        import for back-compat with older presets.

        Returns:
            ``{ui_name: {method_name: {"seq": str, "scope": str}, ...}, ...}``
        """
        data: dict = {}
        filenames = self.sb.registry.ui_registry.get("filename") or []
        all_names = sorted(
            set(
                self.sb.convert_to_legal_name(name.rsplit(".", 1)[0])
                for name in filenames
            )
        )
        for ui_name in all_names:
            target_ui = self.sb.get_ui(ui_name)
            if not target_ui:
                continue
            registry = self.sb.get_shortcut_registry(target_ui)
            if not registry:
                continue
            ui_data: dict = {}
            for entry in registry:
                current = entry.get("current") or ""
                scope = entry.get("current_scope", "window")
                ui_data[entry["method"]] = {"seq": current, "scope": scope}
            if ui_data:
                data[ui_name] = ui_data
        return data

    def import_shortcuts(self, data: dict) -> int:
        """Bulk-apply shortcut bindings from a preset dict.

        Accepts both the new ``{"seq": ..., "scope": ...}`` shape and the
        legacy string shape where the value is the sequence directly.

        Args:
            data: ``{ui_name: {method_name: binding, ...}, ...}``
                where ``binding`` is either a string (legacy) or
                ``{"seq": str, "scope": str}`` (current).

        Returns:
            Number of shortcuts updated.
        """
        applied = 0
        for ui_name, bindings in data.items():
            if not isinstance(bindings, dict):
                continue
            target_ui = self.sb.get_ui(ui_name)
            if not target_ui:
                continue
            for method_name, binding in bindings.items():
                if isinstance(binding, dict):
                    sequence = binding.get("seq", "")
                    scope = binding.get("scope")
                else:
                    sequence = binding or ""
                    scope = None  # legacy: preserve decorator default scope
                self.sb.set_user_shortcut(target_ui, method_name, sequence, scope)
                applied += 1
        return applied

    # ------------------------------------------------------------------
    # Show / refresh
    # ------------------------------------------------------------------

    def showEvent(self, event):
        """Refresh data each time the editor is shown."""
        super().showEvent(event)
        # Preserve current selection if possible
        current_ui = self.cmb_ui.currentText()
        self.refresh_ui_list()
        # Restore selection
        idx = self.cmb_ui.findText(current_ui)
        if idx >= 0:
            self.cmb_ui.setCurrentIndex(idx)
        # Always repopulate table with fresh shortcut data
        self.populate()

    def refresh_ui_list(self):
        """Populate the UI combobox with every registered UI.

        Lists names directly from the ui_registry (populated at startup)
        without instantiating any widgets. The actual UI is only built
        when the user selects it — see ``populate``.
        """
        self.cmb_ui.clear()

        filenames = self.sb.registry.ui_registry.get("filename") or []
        all_names = sorted(
            set(
                self.sb.convert_to_legal_name(name.rsplit(".", 1)[0])
                for name in filenames
            )
        )
        self.cmb_ui.addItems(all_names)

        if all_names:
            self.populate()

    def populate(self):
        """Populate the table with shortcuts for the selected UI.

        Loads the UI on demand if it hasn't been instantiated yet —
        ``peek`` first to skip work when already loaded, otherwise
        ``get_ui`` to build it. Loading a single UI on explicit user
        selection is safe; the host-shutdown crash only manifests when
        force-instantiating every registered UI at once (which is why
        ``refresh_ui_list`` does not).
        """
        self.table.setRowCount(0)
        ui_name = self.cmb_ui.currentText()
        if not ui_name:
            return

        target_ui = self.sb.loaded_ui.peek(ui_name) or self.sb.get_ui(ui_name)
        if target_ui is None:
            self.table.setRowCount(1)
            item = QtWidgets.QTableWidgetItem(f"Could not load UI '{ui_name}'.")
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            self.table.setItem(0, 0, item)
            self.table.setSpan(0, 0, 1, 5)
            return

        registry = self.sb.get_shortcut_registry(target_ui)

        # Clear any previous span
        self.table.setSpan(0, 0, 1, 1)

        if not registry:
            self.table.setRowCount(1)
            item = QtWidgets.QTableWidgetItem("No shortcuts defined for this UI.")
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            self.table.setItem(0, 0, item)
            self.table.setSpan(0, 0, 1, 5)
            return

        self.table.setRowCount(len(registry))
        modified = sum(
            1
            for e in registry
            if (e.get("current") or "") != (e.get("default") or "")
            or (e.get("current_scope") or "") != (e.get("default_scope") or "")
        )
        status = f"{len(registry)} shortcuts"
        if modified:
            status += f" ({modified} customised)"
        self.footer.setStatusText(status)

        for i, entry in enumerate(registry):
            method_name = entry["method"]
            human_name = entry["name"]
            current_seq = entry["current"] or ""
            default_seq = entry["default"] or ""
            current_scope = entry.get("current_scope", "window")
            default_scope = entry.get("default_scope", "window")
            doc = entry["doc"]

            # Action Name
            item_name = QtWidgets.QTableWidgetItem(human_name)
            item_name.setToolTip(f"Method: {method_name}")
            item_name.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(i, 0, item_name)

            # Shortcut
            item_seq = QtWidgets.QTableWidgetItem(current_seq)
            item_seq.setTextAlignment(QtCore.Qt.AlignCenter)
            item_seq.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            if current_seq != default_seq:
                item_seq.setForeground(
                    QtGui.QBrush(QtGui.QColor("#4CAF50"))
                )  # Green if modified
            self.table.setItem(i, 1, item_seq)

            # Scope toggle (Window / Application). Decorator-only scopes
            # (widget, widget_children) are surfaced as a disabled label so
            # users see what's set without being able to override unsafely.
            scope_btn = self._make_scope_toggle(
                target_ui, method_name, current_scope, default_scope
            )
            self.table.setCellWidget(i, 2, scope_btn)

            # Description
            item_doc = QtWidgets.QTableWidgetItem(doc)
            item_doc.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(i, 3, item_doc)

            # Reset Button
            reset_btn = self.icon_button(
                icon_name="undo", tooltip="Reset to default shortcut"
            )
            if current_seq == default_seq and current_scope == default_scope:
                reset_btn.setEnabled(False)

            reset_btn.clicked.connect(
                lambda *args, ui=target_ui, name=method_name, dseq=default_seq, dscope=default_scope: self.reset_shortcut(
                    ui, name, dseq, dscope
                )
            )
            self.table.setCellWidget(i, 4, reset_btn)

    def on_cell_double_clicked(self, row, column):
        """Handle editing the shortcut."""
        if column != 1:
            return

        ui_name = self.cmb_ui.currentText()
        target_ui = self.sb.get_ui(ui_name)

        item_name = self.table.item(row, 0)
        method_name = item_name.toolTip().replace("Method: ", "")
        current_seq = self.table.item(row, 1).text()

        # Recover scope from the cell widget
        scope_btn = self.table.cellWidget(row, 2)
        current_scope = (
            scope_btn.property("scope_name")
            if scope_btn is not None
            else "window"
        )

        dlg = KeyCaptureDialog(self, current_seq)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return

        new_seq = dlg.get_sequence()
        if new_seq == current_seq:
            return

        if not self._resolve_collisions(
            target_ui, method_name, new_seq, current_scope
        ):
            return

        self.sb.set_user_shortcut(target_ui, method_name, new_seq, current_scope)
        self.footer.setStatusText(
            f"Assigned {new_seq or 'None'} to {item_name.text()}"
        )
        self.populate()

    def reset_shortcut(self, ui, method_name, default_seq, default_scope="window"):
        """Reset sequence and scope to decorator defaults."""
        self.sb.set_user_shortcut(ui, method_name, default_seq, default_scope)
        self.populate()

    # ------------------------------------------------------------------
    # Scope toggle
    # ------------------------------------------------------------------

    def _make_scope_toggle(
        self, target_ui, method_name: str, current_scope: str, default_scope: str
    ) -> QtWidgets.QPushButton:
        """Build a square icon button that flips between Window and Application scope.

        Decorator-only scopes (widget, widget_children) render as a disabled
        icon so users see what's set but can't override into a less-safe scope.
        """
        icon_name = SCOPE_ICONS.get(current_scope, "window")
        tooltip = SCOPE_TOOLTIPS.get(current_scope, f"Scope: {current_scope}")
        btn = self.icon_button(icon_name=icon_name, tooltip=tooltip)
        btn.setProperty("scope_name", current_scope)

        if current_scope not in USER_SCOPES:
            btn.setEnabled(False)
            return btn

        if current_scope != default_scope:
            btn.setStyleSheet("QPushButton { background: rgba(76, 175, 80, 60); }")

        btn.clicked.connect(
            lambda *_args, ui=target_ui, name=method_name, default=default_scope: self._on_scope_toggle(
                ui, name, default
            )
        )
        return btn

    def _on_scope_toggle(self, target_ui, method_name: str, default_scope: str):
        """Flip scope between Window and Application, with collision check."""
        # Locate the row by method name and read current state
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if not item:
                continue
            if item.toolTip().replace("Method: ", "") != method_name:
                continue

            current_seq = self.table.item(row, 1).text()
            scope_btn = self.table.cellWidget(row, 2)
            current_scope = scope_btn.property("scope_name")

            new_scope = (
                "application" if current_scope == "window" else "window"
            )

            if not self._resolve_collisions(
                target_ui, method_name, current_seq, new_scope
            ):
                return

            self.sb.set_user_shortcut(
                target_ui, method_name, current_seq, new_scope
            )
            self.populate()
            return

    # ------------------------------------------------------------------
    # Collision checking
    # ------------------------------------------------------------------

    def add_collision_checker(self, checker: Callable) -> None:
        """Register a collision checker.

        Args:
            checker: callable with signature
                ``(sequence, scope, ui_name, method_name) -> List[CollisionConflict]``.
                ``sequence``, ``scope``, ``ui_name`` and ``method_name`` describe
                the binding the user is about to assign. Return an empty list
                when there is no conflict. uitk ships an internal checker; host
                packages (mayatk, etc.) register their own to surface external
                hotkey collisions.
        """
        if checker not in self._collision_checkers:
            self._collision_checkers.append(checker)

    def remove_collision_checker(self, checker: Callable) -> None:
        """Unregister a previously added collision checker."""
        if checker in self._collision_checkers:
            self._collision_checkers.remove(checker)

    def _resolve_collisions(
        self, target_ui, method_name: str, sequence: str, scope: str
    ) -> bool:
        """Run all collision checkers and prompt the user when conflicts exist.

        Returns:
            True when the caller should proceed with the assignment, False when
            the user cancelled.
        """
        if not sequence:
            return True

        ui_name = self.cmb_ui.currentText()
        conflicts: List[CollisionConflict] = []
        for checker in self._collision_checkers:
            try:
                result = checker(sequence, scope, ui_name, method_name) or []
            except Exception as exc:  # noqa: BLE001
                self.sb.logger.warning(
                    f"[hotkey_editor] Collision checker {checker} raised: {exc}"
                )
                continue
            conflicts.extend(result)

        if not conflicts:
            return True

        return self._prompt_conflicts(sequence, scope, conflicts)

    def _prompt_conflicts(
        self, sequence: str, scope: str, conflicts: List[CollisionConflict]
    ) -> bool:
        """Show a modal listing conflicts; return True to proceed."""
        breaks = [c for c in conflicts if c.breaks_binding and c.clear_action]
        soft = [c for c in conflicts if not (c.breaks_binding and c.clear_action)]

        lines = [f"<b>{sequence}</b> ({SCOPE_LABELS.get(scope, scope)}) conflicts:"]
        if breaks:
            lines.append("")
            lines.append("<b>Will become unreliable unless cleared:</b>")
            for c in breaks:
                lines.append(f"&nbsp;&nbsp;• [{c.source}] {c.description}")
        if soft:
            lines.append("")
            lines.append("<b>May fire alongside:</b>")
            for c in soft:
                lines.append(f"&nbsp;&nbsp;• [{c.source}] {c.description}")
        body = "<br>".join(lines)

        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Shortcut Conflict")
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setText(body)

        if breaks:
            clear_btn = box.addButton(
                "Clear conflicting && assign",
                QtWidgets.QMessageBox.AcceptRole,
            )
        else:
            clear_btn = None
        proceed_btn = box.addButton(
            "Assign anyway", QtWidgets.QMessageBox.AcceptRole
        )
        cancel_btn = box.addButton(QtWidgets.QMessageBox.Cancel)
        box.setDefaultButton(cancel_btn)

        box.exec_()
        clicked = box.clickedButton()

        if clicked is cancel_btn:
            return False
        if clicked is clear_btn:
            for c in breaks:
                try:
                    c.clear_action()
                except Exception as exc:  # noqa: BLE001
                    self.sb.logger.warning(
                        f"[hotkey_editor] clear_action raised: {exc}"
                    )
        return True

    def _builtin_internal_collision_checker(
        self, sequence: str, scope: str, ui_name: str, method_name: str
    ) -> List[CollisionConflict]:
        """Detect collisions across all loaded UIs in this Switchboard.

        Rules:
          - Application scope collides with everything.
          - Window scope collides only with Window/Application bindings on the
            same UI (different windows are independent focus targets).
          - Genuine duplicates (same sequence, same target window, both same
            scope) are flagged ``breaks_binding=True`` with a clear_action so
            the user can auto-resolve.
        """
        conflicts: List[CollisionConflict] = []
        if not sequence:
            return conflicts

        filenames = self.sb.registry.ui_registry.get("filename") or []
        candidate_names = sorted(
            set(
                self.sb.convert_to_legal_name(name.rsplit(".", 1)[0])
                for name in filenames
            )
        )

        for other_ui_name in candidate_names:
            other_ui = self.sb.get_ui(other_ui_name)
            if not other_ui:
                continue
            registry = self.sb.get_shortcut_registry(other_ui)
            if not registry:
                continue
            for entry in registry:
                other_method = entry["method"]
                other_seq = entry.get("current") or ""
                other_scope = entry.get("current_scope", "window")
                if not other_seq or other_seq != sequence:
                    continue
                if other_ui_name == ui_name and other_method == method_name:
                    continue  # same row

                same_window = other_ui_name == ui_name
                # Scope overlap rules
                if scope == "application" or other_scope == "application":
                    overlaps = True
                elif scope == "window" and other_scope == "window":
                    overlaps = same_window
                else:
                    overlaps = False
                if not overlaps:
                    continue

                breaks = scope == other_scope and (
                    scope == "application" or same_window
                )
                desc = (
                    f"{other_ui_name}.{other_method} "
                    f"({SCOPE_LABELS.get(other_scope, other_scope)})"
                )
                clear = None
                if breaks:
                    clear = (
                        lambda ui=other_ui, m=other_method, dscope=entry.get(
                            "default_scope", "window"
                        ): self.sb.set_user_shortcut(ui, m, "", dscope)
                    )
                conflicts.append(
                    CollisionConflict(
                        source="uitk",
                        description=desc,
                        breaks_binding=breaks,
                        clear_action=clear,
                    )
                )
        return conflicts
