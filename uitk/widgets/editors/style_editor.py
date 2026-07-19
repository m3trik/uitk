# !/usr/bin/python
# coding=utf-8
from pathlib import Path

from qtpy import QtWidgets, QtCore
from uitk.widgets.colorSwatch import ColorSwatch
from uitk.themes.style_sheet import StyleSheet
from uitk.widgets.editors.editor_panel import EditorPanel
from uitk.managers.icon_manager import IconManager

# Shipped read-only theme presets — one JSON per base theme in
# ``StyleSheet.themes`` (``{"theme": <name>, "overrides": {}}``). They form
# the built-in tier of the editor's preset store, so the base themes appear
# in the same selector as user-saved looks ("themes ARE presets").
BUILTIN_THEMES_DIR = Path(__file__).parents[2] / "themes" / "presets"

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

# Fixed 22px table rows (matches the UI Browser). The QSS QTableWidget::item
# rule reserves a 1px (BORDER_W) border, and the grid another 1px, so the
# rect Qt hands a cell widget is ~19px — value editors are sized 18px tall
# to fit it with a hair of slack (they were clipped at 19px+margins before).
ROW_H = 22
CELL_EDITOR_H = 18


class StyleEditor(EditorPanel):
    """UI for editing global stylesheet variables, with themes as presets.

    The single **Theme** selector is the canonical preset combo: the base
    themes in :attr:`StyleSheet.themes` ship as read-only built-in presets
    (``uitk/themes/presets/*.json``), and user-saved looks layer on top as
    ordinary user presets — one selector, one store, no separate theme
    combo. Loading a preset applies its base theme (and override set)
    ecosystem-wide via :meth:`StyleSheet.apply_theme`; edits made in the
    table become overrides on the loaded preset's base theme (flagged by
    the combo's ``*`` dirty marker until saved).

    A preset persists ``{"theme": <base>, "overrides": {var: value}}``.
    Legacy presets (a full ``{theme_name: {var: value}}`` override dump)
    still load via :meth:`StyleSheet.import_overrides`.

    Restore contract: overrides persist globally (QSettings) and this
    editor re-opens on the active preset's base theme, but OTHER windows
    take the theme their call site passes (``theme="dark"`` across the
    ecosystem) until a preset is loaded — the standard semantic-preset
    restore gap (see ``PresetManager``); an app wanting the saved theme
    at startup applies it from its own entry point.

    Two value types are handled: color tokens get a :class:`ColorSwatch`;
    length tokens (see ``LENGTH_TOKENS``) get a ``QSpinBox`` with a ``" px"``
    suffix, clamped to each token's pixel range. The Basic/All tier combo
    lives in the header's ⋯-menu ("Show:") and filters the table to either
    the 12 most-edited tokens or every token.
    """

    def __init__(self, parent=None):
        super().__init__(
            title="Style Editor",
            status_text="Override global theme colors.",
            parent=parent,
        )
        self.resize(420, 600)

        # Current base theme — refined from the active preset below, after
        # the preset manager exists. Must be set before init_preset_row:
        # wiring the combo computes the dirty state, which calls
        # export_preset_data (and thus reads _theme).
        self._theme = "dark"

        # Theme selector — the canonical preset row, rebranded.
        self.init_preset_row(
            "style_presets",
            builtin_dir=BUILTIN_THEMES_DIR,
            prefix="Theme:  ",
            placeholder="Themes…",
        )
        active = self._preset_mgr.active_preset
        if active:
            stored = self._preset_mgr.read(active) or {}
            if stored.get("theme") in StyleSheet.themes:
                self._theme = stored["theme"]
            self._preset_mgr.refresh_modified_state()
        elif self._preset_mgr.exists(self._theme):
            # Virgin session: activate the built-in matching the default
            # theme so the combo reads "Theme:  dark" instead of the empty
            # placeholder (values are NOT applied — selection only).
            self._preset_mgr.active_preset = self._theme
            self._preset_mgr.refresh_combo()

        # Basic/All tier filter — a header ⋯-menu option rather than a body
        # row, keeping the body down to selector + table.
        from uitk.widgets.comboBox import ComboBox

        if "menu" not in self.header.buttons:
            self.header.config_buttons("menu", *self.header.buttons.keys())
        self.cmb_tier = self.header.menu.add(
            ComboBox,
            setObjectName="cmb_tier",
            setToolTip="Which variables to show: the basic set, or all of them.",
        )
        self.cmb_tier.addItems(["Basic", "All"])
        self.cmb_tier.current_text_prefix = "Show:  "
        self.cmb_tier.currentTextChanged.connect(self.populate)

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
        self.table.verticalHeader().setDefaultSectionSize(ROW_H)
        self.body_layout.addWidget(self.table, 1)

        # Body layout spacing (2px) is set by EditorPanel; tighten every
        # nested control row (the preset row) to 1px for density.
        self.tighten_sublayouts(1)

        # Footer actions
        self.footer.add_action_button(
            icon_name="undo", tooltip="Reset all overrides", callback=self.reset_all
        )

        self.populate()

        # Register this editor with the theme system. ``recursive=False``
        # because Qt stylesheets cascade to children naturally; recursing
        # would wipe ColorSwatch's inline self-styling.
        StyleSheet().set(self, theme=self._theme)

    # ------------------------------------------------------------------
    # Theme state
    # ------------------------------------------------------------------

    @property
    def theme(self) -> str:
        """The base theme currently shown/edited (set by loading a preset)."""
        return self._theme

    def set_tier(self, tier: str):
        """Programmatic Basic/All switch (mirrors a user pick in the header
        menu). Needed because the uitk ``ComboBox`` deliberately suppresses
        signals on programmatic selection (``setCurrentText`` is
        ``@Signals.blockSignals``) — a user pick repopulates via
        ``currentTextChanged``; this path repopulates explicitly.
        """
        self.cmb_tier.setCurrentText(tier)
        self.populate()

    # ------------------------------------------------------------------
    # Preset hooks
    # ------------------------------------------------------------------

    def export_preset_data(self):
        return {
            "theme": self._theme,
            "overrides": StyleSheet.export_overrides().get(self._theme, {}),
        }

    def import_preset_data(self, data):
        theme = data.get("theme")
        if theme is not None:
            if theme in StyleSheet.themes:
                self._theme = theme
                # Applies base theme + overrides to every registered widget
                # (this editor included — it registered itself in __init__).
                StyleSheet.apply_theme(theme, data.get("overrides") or {})
            else:
                # Unknown base theme (hand-edited file, or a preset from a
                # newer uitk): keep the current state, but say so.
                self.footer.setStatusText(f"Unknown base theme: {theme!r}")
        else:
            # Legacy payload: {theme_name: {var: value}, ...} override dump.
            StyleSheet.import_overrides(
                {k: v for k, v in data.items() if isinstance(v, dict)}
            )
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
        current_theme = self._theme
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

        swatch = ColorSwatch(color=current_val)
        swatch.setFixedSize(50, CELL_EDITOR_H)
        self.table.setCellWidget(row, 1, self._centered_cell(swatch, h_margin=4))

        swatch.colorChanged.connect(
            lambda c, name=var_name: self.on_color_changed(name, c)
        )

        self._add_reset_button(row, var_name)

    def _add_length_row(self, row, var_name, theme):
        name_item = QtWidgets.QTableWidgetItem(var_name)
        name_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
        self.table.setItem(row, 0, name_item)

        n = StyleSheet.get_variable_px(var_name, theme=theme, default=0)

        spin = QtWidgets.QSpinBox()
        spin.setRange(*LENGTH_TOKENS[var_name])
        spin.setSuffix(" px")
        spin.setValue(n)
        # 76px: Qt reserves internal width for hidden up/down arrow buttons.
        spin.setFixedSize(76, CELL_EDITOR_H)
        self.table.setCellWidget(row, 1, self._centered_cell(spin))

        spin.valueChanged.connect(
            lambda v, name=var_name: self.on_length_changed(name, v)
        )

        self._add_reset_button(row, var_name)

    @staticmethod
    def _centered_cell(child, h_margin=0):
        """Wrap *child* in a zero-height-margin, center-aligned container.

        Vertical margins must stay 0: the QSS ``QTableWidget::item`` border
        already eats into the rect Qt gives cell widgets, so any fixed
        vertical margin here pushes a fixed-height child past the row's
        bottom edge (the clipped-swatch bug).
        """
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(h_margin, 0, h_margin, 0)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(child)
        return container

    def _add_reset_button(self, row, var_name):
        reset_btn = QtWidgets.QPushButton()
        reset_btn.setFixedSize(CELL_EDITOR_H, CELL_EDITOR_H)
        reset_btn.setToolTip(f"Reset {var_name} to default")
        IconManager.set_icon(reset_btn, "undo", size=(14, 14))
        reset_btn.clicked.connect(
            lambda *args, name=var_name: self.reset_variable(name)
        )
        self.table.setCellWidget(row, 2, self._centered_cell(reset_btn))

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
        StyleSheet.set_variable(name, color, theme=self._theme)
        self._preset_mgr.refresh_modified_state()
        self.footer.setStatusText(
            f"{name} → {color.name() if hasattr(color, 'name') else color}"
        )

    def on_length_changed(self, name, value):
        """Handle length change from spinbox."""
        StyleSheet.set_variable(name, f"{value}px", theme=self._theme)
        self._preset_mgr.refresh_modified_state()
        self.footer.setStatusText(f"{name} → {value}px")

    def reset_variable(self, name):
        """Reset a single variable."""
        StyleSheet.set_variable(name, None, theme=self._theme)
        self._preset_mgr.refresh_modified_state()
        self.refresh_row(name)
        self.footer.setStatusText(f"Reset {name}")

    def reset_all(self):
        """Reset all overrides (every theme, every widget)."""
        StyleSheet.reset_overrides()
        self._preset_mgr.refresh_modified_state()
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
        val = StyleSheet.get_variable(name, theme=self._theme)

        swatch = container.findChild(ColorSwatch)
        if swatch:
            swatch.blockSignals(True)
            swatch.color = val
            swatch.blockSignals(False)
            return

        spin = container.findChild(QtWidgets.QSpinBox)
        if spin:
            spin.blockSignals(True)
            spin.setValue(
                StyleSheet.get_variable_px(name, theme=self._theme, default=0)
            )
            spin.blockSignals(False)
