# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk
from uitk.widgets.colorSwatch import ColorSwatch
from uitk.widgets.mixins.style_sheet import StyleSheet


class StyleEditor(QtWidgets.QWidget):
    """UI for editing global stylesheet variables."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle("Style Editor")
        self.resize(400, 600)

        # Main layout
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # Info Header
        info_label = QtWidgets.QLabel("Override global theme colors.")
        info_label.setAlignment(QtCore.Qt.AlignCenter)
        self.main_layout.addWidget(info_label)

        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Variable", "Color", "Reset"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeToContents
        )
        self.table.verticalHeader().setVisible(False)
        self.main_layout.addWidget(self.table)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_reset_all = QtWidgets.QPushButton("Reset All")
        self.btn_reset_all.clicked.connect(self.reset_all)
        self.btn_close = QtWidgets.QPushButton("Close")
        self.btn_close.clicked.connect(self.close)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_reset_all)
        btn_layout.addWidget(self.btn_close)
        self.main_layout.addLayout(btn_layout)

        self.populate()

    def populate(self):
        """Populate the table with variables."""
        self.table.setRowCount(0)
        variables = StyleSheet.get_variables(
            "light"
        )  # Get list from light theme (keys are same)
        variables.sort()

        self.table.setRowCount(len(variables))

        for i, var_name in enumerate(variables):
            # Variable Name
            name_item = QtWidgets.QTableWidgetItem(var_name)
            name_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(i, 0, name_item)

            # Color Swatch
            # Get current resolved value (incorporating overrides)
            current_val = StyleSheet.get_variable(
                var_name, theme="light"
            )  # Use 'light' as base but get_variable resolves overrides

            # Since get_variable returns string (e.g. "rgb(..)" or "#hex"), Swatch handles it?
            # ColorSwatch takes a QColor or valid input. We might need to convert.
            # But MatUtils colors are often CSS strings.
            # uitk ConvertMixin converts common types.

            swatch_container = QtWidgets.QWidget()
            swatch_layout = QtWidgets.QHBoxLayout(swatch_container)
            swatch_layout.setContentsMargins(4, 2, 4, 2)
            swatch_layout.setAlignment(QtCore.Qt.AlignCenter)

            swatch = ColorSwatch(color=current_val)
            swatch.setFixedSize(50, 20)
            swatch_layout.addWidget(swatch)

            self.table.setCellWidget(i, 1, swatch_container)

            # Connect signal
            # Use closure to capture var_name
            swatch.colorChanged.connect(
                lambda c, name=var_name: self.on_color_changed(name, c)
            )

            # Reset Button
            reset_btn = QtWidgets.QPushButton("Reset")
            reset_btn.setToolTip(f"Reset {var_name} to default")
            reset_btn.clicked.connect(
                lambda *args, name=var_name: self.reset_variable(name)
            )
            self.table.setCellWidget(i, 2, reset_btn)

    def on_color_changed(self, name, color):
        """Handle color change from swatch."""
        StyleSheet.set_variable(name, color)
        # Note: StyleSheet.reload() is called automatically by set_variable
        # so changes should reflect immediately in the UI (including this editor if it uses StyleSheet)

    def reset_variable(self, name):
        """Reset a single variable."""
        StyleSheet.set_variable(name, None)
        # Refresh the specific row's swatch to match the restored default
        self.refresh_row(name)

    def reset_all(self):
        """Reset all overrides."""
        StyleSheet.reset_overrides()
        self.populate()  # Refresh entire table

    def refresh_row(self, name):
        """Update the swatch for a specific variable name."""
        # Find the row
        row = -1
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item.text() == name:
                row = i
                break

        if row != -1:
            # We recreate the swatch to be safe and simple, or find it
            # Finding it:
            container = self.table.cellWidget(row, 1)
            swatch = container.findChild(ColorSwatch)
            if swatch:
                val = StyleSheet.get_variable(name, theme="light")
                # Block signals to prevent triggering on_color_changed which sets the variable again
                swatch.blockSignals(True)
                swatch.color = val
                swatch.blockSignals(False)
