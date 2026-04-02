# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from uitk.widgets.colorSwatch import ColorSwatch
from uitk.widgets.mixins.style_sheet import StyleSheet
from uitk.widgets.editors.editor_panel import EditorPanel
from uitk.widgets.mixins.icon_manager import IconManager


class StyleEditor(EditorPanel):
    """UI for editing global stylesheet variables with preset support.

    Presets capture *all* theme overrides (light + dark) in a single JSON
    file so a named snapshot can be saved, restored, renamed, or deleted.
    """

    def __init__(self, parent=None):
        super().__init__(
            title="Style Editor",
            status_text="Override global theme colors.",
            parent=parent,
        )
        self.resize(400, 600)

        FIXED_H = 20

        # Preset row
        self.init_preset_row("style_presets")

        # Theme selector
        theme_layout = QtWidgets.QHBoxLayout()
        theme_label = QtWidgets.QLabel("Theme:")
        theme_label.setFixedHeight(FIXED_H)
        self.cmb_theme = QtWidgets.QComboBox()
        self.cmb_theme.setFixedHeight(FIXED_H)
        self.cmb_theme.addItems(list(StyleSheet.themes.keys()))
        self.cmb_theme.currentTextChanged.connect(self.populate)
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.cmb_theme)
        self.body_layout.addLayout(theme_layout)

        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Variable", "Color", "Reset"])
        self.table.horizontalHeader().setDefaultAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
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
        self.body_layout.addWidget(self.table, 1)

        # Footer actions
        self.footer.add_action_button(
            icon_name="undo", tooltip="Reset all overrides", callback=self.reset_all
        )

        self.populate()

    # ------------------------------------------------------------------
    # Preset hooks
    # ------------------------------------------------------------------

    def export_preset_data(self):
        return StyleSheet.export_overrides()

    def import_preset_data(self, data):
        StyleSheet.import_overrides(data)
        self.populate()

    # ------------------------------------------------------------------
    # Table population and variable editing
    # ------------------------------------------------------------------

    def populate(self):
        """Populate the table with variables for the current theme."""
        self.table.setRowCount(0)
        current_theme = self.cmb_theme.currentText()
        variables = StyleSheet.get_variables(current_theme)
        variables.sort()

        self.table.setRowCount(len(variables))
        self.footer.setStatusText(f"{len(variables)} variables — {current_theme} theme")

        for i, var_name in enumerate(variables):
            # Variable Name
            name_item = QtWidgets.QTableWidgetItem(var_name)
            name_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(i, 0, name_item)

            # Color Swatch
            current_val = StyleSheet.get_variable(var_name, theme=current_theme)

            swatch_container = QtWidgets.QWidget()
            swatch_layout = QtWidgets.QHBoxLayout(swatch_container)
            swatch_layout.setContentsMargins(4, 2, 4, 2)
            swatch_layout.setAlignment(QtCore.Qt.AlignCenter)

            swatch = ColorSwatch(color=current_val)
            swatch.setFixedSize(50, 20)
            swatch_layout.addWidget(swatch)

            self.table.setCellWidget(i, 1, swatch_container)

            swatch.colorChanged.connect(
                lambda c, name=var_name: self.on_color_changed(name, c)
            )

            # Reset Button
            reset_btn = QtWidgets.QPushButton()
            reset_btn.setFixedSize(24, 24)
            reset_btn.setToolTip(f"Reset {var_name} to default")
            IconManager.set_icon(reset_btn, "undo", size=(16, 16))
            reset_btn.clicked.connect(
                lambda *args, name=var_name: self.reset_variable(name)
            )
            self.table.setCellWidget(i, 2, reset_btn)

    def on_color_changed(self, name, color):
        """Handle color change from swatch."""
        theme = self.cmb_theme.currentText()
        StyleSheet.set_variable(name, color, theme=theme)
        self.footer.setStatusText(
            f"{name} → {color.name() if hasattr(color, 'name') else color}"
        )

    def reset_variable(self, name):
        """Reset a single variable."""
        theme = self.cmb_theme.currentText()
        StyleSheet.set_variable(name, None, theme=theme)
        self.refresh_row(name)
        self.footer.setStatusText(f"Reset {name}")

    def reset_all(self):
        """Reset all overrides."""
        StyleSheet.reset_overrides()
        self.populate()
        self.footer.setStatusText("All overrides reset")

    def refresh_row(self, name):
        """Update the swatch for a specific variable name."""
        row = -1
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item.text() == name:
                row = i
                break

        if row != -1:
            container = self.table.cellWidget(row, 1)
            swatch = container.findChild(ColorSwatch)
            if swatch:
                theme = self.cmb_theme.currentText()
                val = StyleSheet.get_variable(name, theme=theme)
                swatch.blockSignals(True)
                swatch.color = val
                swatch.blockSignals(False)
