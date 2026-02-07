# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore, QtGui


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

    def keyPressEvent(self, event):
        """Capture key press event."""
        # Handle Modifier keys alone
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


class HotkeyEditor(QtWidgets.QWidget):
    """UI for editing global shortcuts."""

    def __init__(self, switchboard, parent=None):
        super().__init__(parent)
        self.sb = switchboard
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle("Hotkey Editor")
        self.resize(600, 600)

        # Main layout
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # Info Header
        info_label = QtWidgets.QLabel("Customize keyboard shortcuts.")
        info_label.setAlignment(QtCore.Qt.AlignCenter)
        self.main_layout.addWidget(info_label)

        # UI Selection
        ui_layout = QtWidgets.QHBoxLayout()
        ui_label = QtWidgets.QLabel("Target UI:")
        self.cmb_ui = QtWidgets.QComboBox()
        self.cmb_ui.currentTextChanged.connect(self.populate)
        self.chk_hide_empty = QtWidgets.QCheckBox("Hide empty")
        self.chk_hide_empty.setToolTip("Hide UIs that have no assignable slots")
        self.chk_hide_empty.setChecked(True)
        self.chk_hide_empty.stateChanged.connect(self.refresh_ui_list)
        ui_layout.addWidget(ui_label)
        ui_layout.addWidget(self.cmb_ui)
        ui_layout.addWidget(self.chk_hide_empty)
        self.main_layout.addLayout(ui_layout)

        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Action", "Shortcut", "Description", "Reset"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.Fixed
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.main_layout.addWidget(self.table)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_close = QtWidgets.QPushButton("Close")
        self.btn_close.clicked.connect(self.close)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        self.main_layout.addLayout(btn_layout)

        self.refresh_ui_list()

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
        """Populate the UI combobox from all registered UIs.

        Uses the 'Hide empty' checkbox to determine whether to exclude
        UIs that have no assignable slots.
        """
        hide_empty = self.chk_hide_empty.isChecked()
        self.cmb_ui.clear()

        # Get all registered UI filenames from ui_registry (populated at startup)
        # This provides the complete list regardless of lazy-loading state
        filenames = self.sb.registry.ui_registry.get("filename") or []

        # Extract unique base names (e.g., "preferences.ui" -> "Preferences")
        all_names = sorted(
            set(
                self.sb.convert_to_legal_name(name.rsplit(".", 1)[0])
                for name in filenames
            )
        )

        # Filter to only UIs with assignable slots if requested
        if hide_empty:
            available = []
            for name in all_names:
                target_ui = self.sb.get_ui(name)
                if target_ui:
                    registry = self.sb.get_shortcut_registry(target_ui)
                    if registry:
                        available.append(name)
        else:
            available = all_names

        self.cmb_ui.addItems(available)

        if available:
            self.populate()

    def populate(self):
        """Populate the table with shortcuts for selected UI."""
        self.table.setRowCount(0)
        ui_name = self.cmb_ui.currentText()
        if not ui_name:
            return

        # Attempt to find the actual QWidget UI instance
        # Usually internal naming is lowercase, so we might need fuzzy finding
        # But get_slots_instance usually works by Name.

        # In this context, we need the *Widget* to pass to get_shortcut_registry
        # Can we get it via switchboard?

        # Assuming switchboard has access or we can pass a dummy if get_shortcut_registry handles strings?
        # Our implementation of get_shortcut_registry expects a QWidget (ui) to find slots.

        # We'll use the SB helper to reverse resolve if possible, or iterate known windows
        target_ui = self.sb.get_ui(ui_name)
        if not target_ui:
            # UI widget not loaded yet - show informative message
            self.table.setRowCount(1)
            item = QtWidgets.QTableWidgetItem(
                f"UI '{ui_name}' not loaded. Visit it first to configure shortcuts."
            )
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            self.table.setItem(0, 0, item)
            self.table.setSpan(0, 0, 1, 4)
            return

        registry = self.sb.get_shortcut_registry(target_ui)

        # Clear any previous span
        self.table.setSpan(0, 0, 1, 1)

        if not registry:
            self.table.setRowCount(1)
            item = QtWidgets.QTableWidgetItem("No shortcuts defined for this UI.")
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            self.table.setItem(0, 0, item)
            self.table.setSpan(0, 0, 1, 4)
            return

        self.table.setRowCount(len(registry))

        for i, entry in enumerate(registry):
            method_name = entry["method"]
            human_name = entry["name"]
            current_seq = entry["current"] or ""
            default_seq = entry["default"] or ""
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

            # Description
            item_doc = QtWidgets.QTableWidgetItem(doc)
            item_doc.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(i, 2, item_doc)

            # Reset Button
            reset_btn = QtWidgets.QPushButton("Reset")
            reset_btn.setFixedWidth(50)
            if current_seq == default_seq:
                reset_btn.setEnabled(False)

            reset_btn.clicked.connect(
                lambda *args, ui=target_ui, name=method_name, default=default_seq: self.reset_shortcut(
                    ui, name, default
                )
            )
            self.table.setCellWidget(i, 3, reset_btn)

    def on_cell_double_clicked(self, row, column):
        """Handle editing the shortcut."""
        if column != 1:
            return

        ui_name = self.cmb_ui.currentText()
        target_ui = self.sb.get_ui(ui_name)

        # Get method name from hidden data or previous column
        item_name = self.table.item(row, 0)
        # We stored method name in tooltip for simplicity, or we could use QTableWidgetItem.setData
        # Let's rely on re-fetching from registry using row index is risky if sorted.
        # Better to store data.

        # Quick fix: Re-fetch registry to map row to method.
        # *Assumes table order matches registry order if not sorted*
        # To be robust, let's store method name in UserRole
        method_name = item_name.toolTip().replace("Method: ", "")
        current_seq = self.table.item(row, 1).text()

        dlg = KeyCaptureDialog(self, current_seq)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            new_seq = dlg.get_sequence()
            if new_seq != current_seq:
                self.sb.set_user_shortcut(target_ui, method_name, new_seq)
                self.populate()  # Refresh to show green color etc

    def reset_shortcut(self, ui, method_name, default_seq):
        """Reset to default."""
        self.sb.set_user_shortcut(ui, method_name, default_seq)
        self.populate()
