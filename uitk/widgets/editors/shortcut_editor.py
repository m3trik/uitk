# !/usr/bin/python
# coding=utf-8
"""Editor windows used by :meth:`ShortcutManager.show_editor`.

These dialogs are private to the shortcut editor flow — the
``ShortcutManager`` lazy-imports them when its ``show_editor()`` is
called. They live in ``uitk.widgets.editors`` alongside the other
editor windows (HotkeyEditor, StyleEditor, SwitchboardBrowser) rather
than in ``mixins/`` because they are GUI windows, not behavior to be
mixed into a host class.
"""
from typing import TYPE_CHECKING
from qtpy import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:  # pragma: no cover
    from uitk.widgets.mixins.shortcuts import ShortcutManager


class KeyCaptureDialog(QtWidgets.QDialog):
    """Modal dialog that captures a single key combination."""

    def __init__(self, parent=None, current: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Press a key combination")
        self.setFixedSize(300, 120)
        self._sequence = current

        layout = QtWidgets.QVBoxLayout(self)
        self._label = QtWidgets.QLabel(current or "Press a key…")
        self._label.setAlignment(QtCore.Qt.AlignCenter)
        self._label.setStyleSheet("font-size:14px; font-weight:bold; color:#4CAF50;")
        layout.addWidget(self._label)

        btn_row = QtWidgets.QHBoxLayout()
        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.clicked.connect(self._clear)
        btn_ok = QtWidgets.QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (
            QtCore.Qt.Key_unknown,
            QtCore.Qt.Key_Control,
            QtCore.Qt.Key_Shift,
            QtCore.Qt.Key_Alt,
            QtCore.Qt.Key_Meta,
        ):
            return
        mods = event.modifiers()
        mod_int = mods.value if hasattr(mods, "value") else int(mods)
        kp = QtCore.Qt.KeypadModifier
        kp_int = kp.value if hasattr(kp, "value") else int(kp)
        mod_int &= ~kp_int
        seq = QtGui.QKeySequence(key | mod_int).toString()
        self._sequence = seq
        self._label.setText(seq)

    def _clear(self):
        self._sequence = ""
        self._label.setText("(none)")

    def get_sequence(self) -> str:
        return self._sequence


class ShortcutEditorDialog(QtWidgets.QWidget):
    """Editor panel for viewing and remapping ShortcutManager bindings.

    Uses the shared :class:`EditorPanel` layout (Header → body → Footer)
    for visual consistency with other editors.
    """

    def __init__(self, manager: "ShortcutManager", parent=None, title="Shortcuts"):
        super().__init__(None)
        self._mgr = manager

        from uitk.widgets.editors.editor_panel import EditorPanel
        from uitk.widgets.mixins.icon_manager import IconManager

        self._IconManager = IconManager

        # Use EditorPanel as the internal layout host
        self._panel = EditorPanel(
            title=title,
            status_text="Double-click the Shortcut column to reassign.",
            parent=None,
        )

        self._table = QtWidgets.QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Action", "Shortcut", ""])
        header = self._table.horizontalHeader()
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        header.resizeSection(2, 30)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        self._panel.body_layout.addWidget(self._table)

        self._populate()

    @property
    def panel(self):
        """The :class:`EditorPanel` widget."""
        return self._panel

    def show(self):
        self._panel.show()
        self._panel.raise_()

    def close(self):
        self._panel.close()

    def _populate(self):
        self._table.setRowCount(0)
        entries = sorted(
            self._mgr.shortcuts.items(),
            key=lambda kv: kv[1].get("description", kv[0]),
        )
        self._table.setRowCount(len(entries))
        modified = 0
        for i, (key, data) in enumerate(entries):
            desc = data.get("description", key)
            desc_item = QtWidgets.QTableWidgetItem(desc)
            desc_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self._table.setItem(i, 0, desc_item)

            key_item = QtWidgets.QTableWidgetItem(key)
            key_item.setTextAlignment(QtCore.Qt.AlignCenter)
            key_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            default = data.get("default_key", key)
            if key != default:
                key_item.setForeground(QtGui.QBrush(QtGui.QColor("#4CAF50")))
                modified += 1
            self._table.setItem(i, 1, key_item)

            btn = QtWidgets.QPushButton()
            btn.setFixedSize(24, 24)
            btn.setToolTip("Reset to default shortcut")
            self._IconManager.set_icon(btn, "undo", size=(16, 16))
            read_only = data.get("read_only", False)
            btn.setEnabled(key != default and not read_only)
            btn.clicked.connect(lambda checked=False, r=i: self._reset_row(r))
            self._table.setCellWidget(i, 2, btn)

        status = f"{len(entries)} shortcuts"
        if modified:
            status += f" ({modified} customised)"
        self._panel.footer.setStatusText(status)

    def _on_double_click(self, row, col):
        if col != 1:
            return
        current_key = self._table.item(row, 1).text()
        entries = sorted(
            self._mgr.shortcuts.items(),
            key=lambda kv: kv[1].get("description", kv[0]),
        )
        if row < len(entries) and entries[row][1].get("read_only"):
            return
        dlg = KeyCaptureDialog(self._panel, current_key)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            new_key = dlg.get_sequence()
            if new_key and new_key != current_key:
                if not self._mgr.rebind_shortcut(current_key, new_key):
                    QtWidgets.QMessageBox.warning(
                        self._panel,
                        "Shortcut Conflict",
                        f'"{new_key}" is already assigned to another action.',
                    )
                    return
                desc_item = self._table.item(row, 0)
                action_name = desc_item.text() if desc_item else current_key
                self._panel.footer.setStatusText(f"Assigned {new_key} to {action_name}")
                self._populate()

    def _reset_row(self, row):
        current_key = self._table.item(row, 1).text()
        entry = self._mgr.shortcuts.get(current_key)
        if entry:
            default = entry.get("default_key", current_key)
            if default != current_key:
                self._mgr.rebind_shortcut(current_key, default)
                self._populate()
