# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from uitk.widgets.colorSwatch import ColorSwatch
from uitk.themes.style_sheet import StyleSheet
from uitk.widgets.editors.editor_panel import EditorPanel
from uitk.managers.icon_manager import IconManager


# Tokens shown in the "Basic" tier — the ones a typical user edits to
# personalize the look. Everything else (status palette, secondary
# surfaces, Python-consumed tokens, rarely-edited cosmetic colors) moves
# behind the "All" tier.
BASIC_TOKENS = frozenset(
    {
        # Main surfaces
        "PANEL_BACKGROUND",
        "WINDOW_BACKGROUND",
        "WIDGET_BACKGROUND",
        "DISABLED_BACKGROUND",
        # Text
        "TEXT_COLOR",
        "TEXT_HOVER",
        "TEXT_CHECKED",
        "TEXT_DISABLED",
        # Action accents
        "BUTTON_HOVER",
        "BUTTON_CHECKED",
        # Structural
        "BORDER_COLOR",
        "RADIUS",
    }
)

# Non-color tokens, mapped to their spinbox ``(min, max)`` pixel range.
# Anything not listed here is treated as a color and rendered with a
# ``ColorSwatch``; listed tokens get a ``QSpinBox`` with the ``" px"``
# suffix. Radius/border stay ≤8 (Qt's border-radius rendering degrades on
# small widgets above that); row-height tokens need a taller ceiling.
LENGTH_TOKENS = {
    "RADIUS": (0, 8),
    "BORDER_W": (0, 8),
    "COMBOBOX_ITEM_HEIGHT": (0, 64),
    "TEXT_INSET": (0, 16),
}


class StyleEditor(EditorPanel):
    """UI for editing global stylesheet variables with preset support.

    Presets capture *all* theme overrides (light + dark) in a single JSON
    file so a named snapshot can be saved, restored, renamed, or deleted.

    The editor registers itself with the theme system so color/size edits
    show up live in its own chrome. The theme combobox both filters the
    table and re-themes the editor window — switching to "dark" makes the
    editor go dark and its rows reflect the dark theme's values.

    Two value types are handled: color tokens get a :class:`ColorSwatch`;
    length tokens (see ``LENGTH_TOKENS``) get a ``QSpinBox`` with a ``" px"``
    suffix, clamped to each token's pixel range. A "tier" combo filters the
    table to either the 12 most-edited tokens (Basic) or every token (All).
    """

    def __init__(self, parent=None):
        super().__init__(
            title="Style Editor",
            status_text="Override global theme colors.",
            parent=parent,
        )
        self.resize(420, 600)

        FIXED_H = 20

        # Preset row
        self.init_preset_row("style_presets")

        # Theme + tier controls
        controls_layout = QtWidgets.QHBoxLayout()
        theme_label = QtWidgets.QLabel("Theme:")
        theme_label.setFixedHeight(FIXED_H)
        theme_label.setFixedWidth(
            theme_label.fontMetrics().horizontalAdvance("Theme:") + 6
        )
        self.cmb_theme = QtWidgets.QComboBox()
        self.cmb_theme.setFixedHeight(FIXED_H)
        self.cmb_theme.addItems(list(StyleSheet.themes.keys()))
        self.cmb_theme.currentTextChanged.connect(self._on_theme_changed)

        tier_label = QtWidgets.QLabel("Show:")
        tier_label.setFixedHeight(FIXED_H)
        tier_label.setFixedWidth(
            tier_label.fontMetrics().horizontalAdvance("Show:") + 6
        )
        self.cmb_tier = QtWidgets.QComboBox()
        self.cmb_tier.setFixedHeight(FIXED_H)
        self.cmb_tier.addItems(["Basic", "All"])
        self.cmb_tier.currentTextChanged.connect(self.populate)

        # Equal stretch — combos fill the row instead of clumping left.
        controls_layout.addWidget(theme_label)
        controls_layout.addWidget(self.cmb_theme, 1)
        controls_layout.addWidget(tier_label)
        controls_layout.addWidget(self.cmb_tier, 1)
        self.body_layout.addLayout(controls_layout)

        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Variable", "Value", "Reset"])
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
        # Match the UI Browser table's row height for a consistent look.
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.body_layout.addWidget(self.table, 1)

        # Body layout spacing (2px) is set by EditorPanel; tighten every
        # nested control row (preset row, theme row) to 1px for density.
        self.tighten_sublayouts(1)

        # Footer actions
        self.footer.add_action_button(
            icon_name="undo", tooltip="Reset all overrides", callback=self.reset_all
        )

        self.populate()

        # Register this editor with the theme system. ``recursive=False``
        # because Qt stylesheets cascade to children naturally; recursing
        # would wipe ColorSwatch's inline self-styling.
        StyleSheet().set(self, theme=self.cmb_theme.currentText())

    # ------------------------------------------------------------------
    # Preset hooks
    # ------------------------------------------------------------------

    def export_preset_data(self):
        return StyleSheet.export_overrides()

    def import_preset_data(self, data):
        StyleSheet.import_overrides(data)
        self.populate()

    # ------------------------------------------------------------------
    # Theme switch
    # ------------------------------------------------------------------

    def _on_theme_changed(self, theme):
        """Combobox callback: re-theme the editor + repopulate the table.

        Uses ``StyleSheet().set`` rather than ``set_theme(widget=self)``
        so we always re-apply the QSS even if ``self`` somehow fell out
        of ``_widget_configs`` (e.g. a prior reload hit a RuntimeError);
        ``set_theme`` silently no-ops in that case.
        """
        StyleSheet().set(self, theme=theme)
        self.populate()

    # ------------------------------------------------------------------
    # Table population and variable editing
    # ------------------------------------------------------------------

    def populate(self):
        """Populate the table with variables for the current theme + tier.

        Color tokens render first, then a section divider, then length
        tokens. ``setRowCount(0)`` + ``clearSpans()`` resets any prior
        spans before re-rendering.
        """
        self.table.setRowCount(0)
        self.table.clearSpans()
        current_theme = self.cmb_theme.currentText()
        tier = self.cmb_tier.currentText()
        all_vars = StyleSheet.get_variables(current_theme)

        if tier == "Basic":
            visible = [v for v in all_vars if v in BASIC_TOKENS]
        else:
            visible = list(all_vars)

        colors = sorted(v for v in visible if v not in LENGTH_TOKENS)
        lengths = sorted(v for v in visible if v in LENGTH_TOKENS)

        total_rows = len(colors) + (1 + len(lengths) if lengths else 0)
        self.table.setRowCount(total_rows)
        colors_word = "color" if len(colors) == 1 else "colors"
        sizes_word = "size" if len(lengths) == 1 else "sizes"
        self.footer.setStatusText(
            f"{len(colors)} {colors_word}, {len(lengths)} {sizes_word} — "
            f"{current_theme} theme ({tier.lower()})"
        )

        row = 0
        for var_name in colors:
            self._add_color_row(row, var_name, current_theme)
            row += 1
        if lengths:
            self._add_section_header(row, "— Sizes —")
            row += 1
            for var_name in lengths:
                self._add_length_row(row, var_name, current_theme)
                row += 1

    def _add_color_row(self, row, var_name, theme):
        name_item = QtWidgets.QTableWidgetItem(var_name)
        name_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
        self.table.setItem(row, 0, name_item)

        current_val = StyleSheet.get_variable(var_name, theme=theme)

        swatch_container = QtWidgets.QWidget()
        swatch_layout = QtWidgets.QHBoxLayout(swatch_container)
        swatch_layout.setContentsMargins(4, 2, 4, 2)
        swatch_layout.setAlignment(QtCore.Qt.AlignCenter)

        swatch = ColorSwatch(color=current_val)
        swatch.setFixedSize(50, 19)
        swatch_layout.addWidget(swatch)
        self.table.setCellWidget(row, 1, swatch_container)

        swatch.colorChanged.connect(
            lambda c, name=var_name: self.on_color_changed(name, c)
        )

        self._add_reset_button(row, var_name)

    def _add_length_row(self, row, var_name, theme):
        name_item = QtWidgets.QTableWidgetItem(var_name)
        name_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
        self.table.setItem(row, 0, name_item)

        n = StyleSheet.get_variable_px(var_name, theme=theme, default=0)

        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        # No horizontal padding — cell QSS padding is enough breathing room.
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setAlignment(QtCore.Qt.AlignCenter)

        spin = QtWidgets.QSpinBox()
        spin.setRange(*LENGTH_TOKENS[var_name])
        spin.setSuffix(" px")
        spin.setValue(n)
        # 76px: Qt reserves internal width for hidden up/down arrow buttons.
        spin.setFixedSize(76, 19)
        layout.addWidget(spin)
        self.table.setCellWidget(row, 1, container)

        spin.valueChanged.connect(
            lambda v, name=var_name: self.on_length_changed(name, v)
        )

        self._add_reset_button(row, var_name)

    def _add_reset_button(self, row, var_name):
        reset_btn = QtWidgets.QPushButton()
        reset_btn.setFixedSize(24, 24)
        reset_btn.setToolTip(f"Reset {var_name} to default")
        IconManager.set_icon(reset_btn, "undo", size=(16, 16))
        reset_btn.clicked.connect(
            lambda *args, name=var_name: self.reset_variable(name)
        )
        self.table.setCellWidget(row, 2, reset_btn)

    def _add_section_header(self, row, title):
        item = QtWidgets.QTableWidgetItem(title)
        # Non-interactive — the divider is decoration, not data.
        item.setFlags(QtCore.Qt.NoItemFlags)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setTextAlignment(QtCore.Qt.AlignCenter)
        self.table.setItem(row, 0, item)
        self.table.setSpan(row, 0, 1, 3)

    # ------------------------------------------------------------------
    # Value change handlers
    # ------------------------------------------------------------------

    def on_color_changed(self, name, color):
        """Handle color change from swatch."""
        theme = self.cmb_theme.currentText()
        StyleSheet.set_variable(name, color, theme=theme)
        self.footer.setStatusText(
            f"{name} → {color.name() if hasattr(color, 'name') else color}"
        )

    def on_length_changed(self, name, value):
        """Handle length change from spinbox."""
        theme = self.cmb_theme.currentText()
        StyleSheet.set_variable(name, f"{value}px", theme=theme)
        self.footer.setStatusText(f"{name} → {value}px")

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
        """Update the editor widget for a specific variable name."""
        row = -1
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item and item.text() == name:
                row = i
                break

        if row == -1:
            return

        container = self.table.cellWidget(row, 1)
        if container is None:
            return
        theme = self.cmb_theme.currentText()
        val = StyleSheet.get_variable(name, theme=theme)

        swatch = container.findChild(ColorSwatch)
        if swatch:
            swatch.blockSignals(True)
            swatch.color = val
            swatch.blockSignals(False)
            return

        spin = container.findChild(QtWidgets.QSpinBox)
        if spin:
            spin.blockSignals(True)
            spin.setValue(StyleSheet.get_variable_px(name, theme=theme, default=0))
            spin.blockSignals(False)
