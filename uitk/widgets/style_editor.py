# !/usr/bin/python
# coding=utf-8
import json
from pathlib import Path

from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk
from uitk.widgets.colorSwatch import ColorSwatch
from uitk.widgets.mixins.style_sheet import StyleSheet
from uitk.widgets.mixins.preset_manager import QStandardPaths_writableLocation


class StyleEditor(QtWidgets.QWidget):
    """UI for editing global stylesheet variables with preset support.

    Presets capture *all* theme overrides (light + dark) in a single JSON
    file so a named snapshot can be saved, restored, renamed, or deleted.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle("Style Editor")
        self.resize(400, 600)

        # Main layout
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(4)

        FIXED_H = 20

        # Info Header
        info_label = QtWidgets.QLabel("Override global theme colors.")
        info_label.setAlignment(QtCore.Qt.AlignCenter)
        info_label.setFixedHeight(FIXED_H)
        self.main_layout.addWidget(info_label)

        # ── Preset row ──────────────────────────────────────────────
        preset_layout = QtWidgets.QHBoxLayout()
        preset_label = QtWidgets.QLabel("Preset:")
        preset_label.setFixedHeight(FIXED_H)
        self.cmb_preset = QtWidgets.QComboBox()
        self.cmb_preset.setFixedHeight(FIXED_H)
        self.cmb_preset.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.cmb_preset.setPlaceholderText("No saved presets")
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_selected)

        self.btn_save_preset = QtWidgets.QPushButton("Save")
        self.btn_save_preset.setFixedHeight(FIXED_H)
        self.btn_save_preset.setToolTip("Save current overrides as a named preset")
        self.btn_save_preset.clicked.connect(self._on_save_preset)

        self.btn_rename_preset = QtWidgets.QPushButton("Rename")
        self.btn_rename_preset.setFixedHeight(FIXED_H)
        self.btn_rename_preset.setToolTip("Rename the selected preset")
        self.btn_rename_preset.clicked.connect(self._on_rename_preset)

        self.btn_delete_preset = QtWidgets.QPushButton("Delete")
        self.btn_delete_preset.setFixedHeight(FIXED_H)
        self.btn_delete_preset.setToolTip("Delete the selected preset")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)

        self.btn_open_folder = QtWidgets.QPushButton("…")
        self.btn_open_folder.setFixedSize(28, FIXED_H)
        self.btn_open_folder.setToolTip("Open preset folder")
        self.btn_open_folder.clicked.connect(self._on_open_folder)

        preset_layout.addWidget(preset_label)
        preset_layout.addWidget(self.cmb_preset)
        preset_layout.addWidget(self.btn_save_preset)
        preset_layout.addWidget(self.btn_rename_preset)
        preset_layout.addWidget(self.btn_delete_preset)
        preset_layout.addWidget(self.btn_open_folder)
        self.main_layout.addLayout(preset_layout)

        # ── Theme selector ──────────────────────────────────────────
        theme_layout = QtWidgets.QHBoxLayout()
        theme_label = QtWidgets.QLabel("Theme:")
        theme_label.setFixedHeight(FIXED_H)
        self.cmb_theme = QtWidgets.QComboBox()
        self.cmb_theme.setFixedHeight(FIXED_H)
        self.cmb_theme.addItems(list(StyleSheet.themes.keys()))
        self.cmb_theme.currentTextChanged.connect(self.populate)
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.cmb_theme)
        self.main_layout.addLayout(theme_layout)

        # ── Table ───────────────────────────────────────────────────
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

        # ── Footer buttons ──────────────────────────────────────────
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_reset_all = QtWidgets.QPushButton("Reset All")
        self.btn_reset_all.setFixedHeight(FIXED_H)
        self.btn_reset_all.clicked.connect(self.reset_all)
        self.btn_close = QtWidgets.QPushButton("Close")
        self.btn_close.setFixedHeight(FIXED_H)
        self.btn_close.clicked.connect(self.close)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_reset_all)
        btn_layout.addWidget(self.btn_close)
        self.main_layout.addLayout(btn_layout)

        self._refresh_presets()
        self.populate()

    # ------------------------------------------------------------------
    # Preset directory & file helpers
    # ------------------------------------------------------------------

    @property
    def preset_dir(self) -> Path:
        """Auto-derived preset directory under AppConfigLocation."""
        d = Path(QStandardPaths_writableLocation()) / "uitk" / "style_presets"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _preset_path(self, name: str) -> Path:
        safe = "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in name)
        return self.preset_dir / f"{safe}.json"

    def _list_presets(self) -> list:
        if not self.preset_dir.exists():
            return []
        return sorted(p.stem for p in self.preset_dir.glob("*.json"))

    # ------------------------------------------------------------------
    # Preset save / load / delete / rename
    # ------------------------------------------------------------------

    def save_preset(self, name: str) -> Path:
        """Save current global overrides (all themes) to a named preset."""
        data = StyleSheet.export_overrides()
        data["_meta"] = {"version": 1}
        filepath = self._preset_path(name)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return filepath

    def load_preset(self, name: str) -> bool:
        """Load a preset and apply it as the new global overrides.

        Performs a single bulk import + one reload.
        """
        filepath = self._preset_path(name)
        if not filepath.exists():
            return False
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                return False
        data.pop("_meta", None)
        StyleSheet.import_overrides(data)
        self.populate()  # Refresh swatches from new state
        return True

    def delete_preset(self, name: str) -> bool:
        filepath = self._preset_path(name)
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def rename_preset(self, old: str, new: str) -> bool:
        old_path = self._preset_path(old)
        new_path = self._preset_path(new)
        if not old_path.exists() or new_path.exists():
            return False
        old_path.rename(new_path)
        return True

    # ------------------------------------------------------------------
    # Preset UI wiring
    # ------------------------------------------------------------------

    def _refresh_presets(self, select_name: str = None):
        """Repopulate the preset combo."""
        self.cmb_preset.blockSignals(True)
        try:
            self.cmb_preset.clear()
            names = self._list_presets()
            if names:
                self.cmb_preset.addItems(names)
                if select_name:
                    idx = self.cmb_preset.findText(select_name)
                    self.cmb_preset.setCurrentIndex(max(idx, 0))
                else:
                    self.cmb_preset.setCurrentIndex(-1)
                self.cmb_preset.setPlaceholderText("Select a preset\u2026")
            else:
                self.cmb_preset.setPlaceholderText("No saved presets")
        finally:
            self.cmb_preset.blockSignals(False)

    def _on_preset_selected(self, idx):
        if idx < 0:
            return
        name = self.cmb_preset.itemText(idx)
        if name:
            self.load_preset(name)

    def _on_save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "Save Preset", "Preset name:")
        if ok and name.strip():
            name = name.strip()
            self.save_preset(name)
            self._refresh_presets(select_name=name)

    def _on_rename_preset(self):
        idx = self.cmb_preset.currentIndex()
        if idx < 0:
            return
        current = self.cmb_preset.itemText(idx)
        if not current:
            return
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "Rename Preset", "New name:", text=current
        )
        if ok and new_name.strip() and new_name.strip() != current:
            if self.rename_preset(current, new_name.strip()):
                self._refresh_presets(select_name=new_name.strip())

    def _on_delete_preset(self):
        idx = self.cmb_preset.currentIndex()
        if idx < 0:
            return
        name = self.cmb_preset.itemText(idx)
        if name and self.delete_preset(name):
            self._refresh_presets()

    def _on_open_folder(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.preset_dir)))

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
            reset_btn = QtWidgets.QPushButton("Reset")
            reset_btn.setToolTip(f"Reset {var_name} to default")
            reset_btn.clicked.connect(
                lambda *args, name=var_name: self.reset_variable(name)
            )
            self.table.setCellWidget(i, 2, reset_btn)

    def on_color_changed(self, name, color):
        """Handle color change from swatch."""
        theme = self.cmb_theme.currentText()
        StyleSheet.set_variable(name, color, theme=theme)

    def reset_variable(self, name):
        """Reset a single variable."""
        theme = self.cmb_theme.currentText()
        StyleSheet.set_variable(name, None, theme=theme)
        self.refresh_row(name)

    def reset_all(self):
        """Reset all overrides."""
        StyleSheet.reset_overrides()
        self.populate()

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
