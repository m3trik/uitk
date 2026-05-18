# !/usr/bin/python
# coding=utf-8
"""Reusable color-mapping editor widget.

Provides :class:`ColorMappingEditor` (embeddable ``QWidget``) and
:class:`ColorMappingDialog` (popup ``QDialog``) for editing named color
mappings with section headers, per-row reset, and optional
``SettingsManager`` persistence.

Supports single-color entries (``key → "#hex"``) and dual-color entries
(``key → (fg_hex, bg_hex)``), determined automatically from *defaults*.

Example
-------
>>> from uitk.widgets.editors.color_mapping_editor import ColorMappingEditor
>>> editor = ColorMappingEditor(
...     defaults={"error": "#E06666", "warning": "#FFD966"},
...     sections=[("Severity", ["error", "warning"])],
...     settings_ns="myapp/colors",
... )
>>> editor.show()
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from qtpy import QtWidgets, QtCore, QtGui

from uitk.widgets.colorSwatch import ColorSwatch
from uitk.widgets.mixins.settings_manager import SettingsManager
from uitk.widgets.mixins.style_sheet import StyleSheet
from uitk.widgets.mixins.icon_manager import IconManager
from uitk.widgets.mixins.preset_manager import PresetManager
from uitk.widgets.header import Header
from uitk.widgets.footer import Footer
from uitk.widgets.row_selection_delegate import RowSelectionBorderDelegate
from uitk.widgets.widgetComboBox import WidgetComboBox

ColorValue = Union[str, Tuple[str, str]]


class ColorMappingEditor(QtWidgets.QWidget):
    """Reusable widget for editing named color mappings with optional sections.

    Parameters
    ----------
    defaults : dict
        Factory-default mapping.  Values may be hex strings or
        ``(fg, bg)`` tuples.
    sections : list of (str, list[str]), optional
        Grouped entries: ``[("Header", [key, ...]), ...]``.  Keys not
        listed in any section are appended under an "Other" header.
    settings : SettingsManager, optional
        Pre-configured settings manager for persistence.  Takes
        precedence over *settings_ns*.
    settings_ns : str, optional
        Namespace for auto-created ``SettingsManager``.  Ignored when
        *settings* is provided.
    swatch_size : int
        Width/height of each color swatch button.
    parent : QWidget, optional
    """

    colors_changed = QtCore.Signal(dict)
    _FALLBACK_COLOR = "#5B8BD4"

    def __init__(
        self,
        defaults: Dict[str, ColorValue],
        sections: Optional[List[Tuple[str, List[str]]]] = None,
        settings: Optional[SettingsManager] = None,
        settings_ns: Optional[str] = None,
        swatch_size: int = 22,
        add_restore_button: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self._defaults: Dict[str, ColorValue] = dict(defaults)
        self._sections = sections or []
        self._swatch_size = swatch_size

        if settings is not None:
            self._settings = settings
        elif settings_ns:
            self._settings = SettingsManager(namespace=settings_ns)
        else:
            self._settings = None

        # {key: ColorSwatch} for single-color entries
        # {key: (fg_swatch, bg_swatch)} for pair entries
        self._swatches: Dict[
            str, Union[ColorSwatch, Tuple[ColorSwatch, ColorSwatch]]
        ] = {}

        self._build_ui(add_restore_button=add_restore_button)
        self._load_from_settings()

        self.style = StyleSheet(self)
        self.style.set(theme="dark")

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _is_pair(value) -> bool:
        return isinstance(value, (tuple, list)) and len(value) == 2

    def _default_for(self, key: str) -> ColorValue:
        return self._defaults.get(key, self._FALLBACK_COLOR)

    def _current_color(self, key: str) -> ColorValue:
        """Return the saved override or the default for *key*."""
        default = self._default_for(key)
        if not self._settings:
            return default
        if self._is_pair(default):
            fg = self._settings.value(f"{key}/fg") or default[0]
            bg = self._settings.value(f"{key}/bg") or default[1]
            return (fg, bg)
        val = self._settings.value(key)
        return val if val else default

    # ── build ────────────────────────────────────────────────────

    def _has_pairs(self) -> bool:
        """Return True if any default value is a (fg, bg) pair."""
        return any(self._is_pair(v) for v in self._defaults.values())

    def _build_ui(self, add_restore_button: bool = True):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        has_pairs = self._has_pairs()

        # Table
        self._table = QtWidgets.QTableWidget()
        if has_pairs:
            self._table.setColumnCount(4)
            self._table.setHorizontalHeaderLabels(["Name", "FG", "BG", ""])
            self._table.horizontalHeader().setSectionResizeMode(
                0, QtWidgets.QHeaderView.Stretch
            )
            self._table.horizontalHeader().setSectionResizeMode(
                1, QtWidgets.QHeaderView.ResizeToContents
            )
            self._table.horizontalHeader().setSectionResizeMode(
                2, QtWidgets.QHeaderView.ResizeToContents
            )
            self._table.horizontalHeader().setSectionResizeMode(
                3, QtWidgets.QHeaderView.Fixed
            )
            self._table.horizontalHeader().resizeSection(3, 30)
        else:
            self._table.setColumnCount(3)
            self._table.setHorizontalHeaderLabels(["Name", "Color", ""])
            self._table.horizontalHeader().setSectionResizeMode(
                0, QtWidgets.QHeaderView.Stretch
            )
            self._table.horizontalHeader().setSectionResizeMode(
                1, QtWidgets.QHeaderView.ResizeToContents
            )
            self._table.horizontalHeader().setSectionResizeMode(
                2, QtWidgets.QHeaderView.Fixed
            )
            self._table.horizontalHeader().resizeSection(2, 30)
        self._table.horizontalHeader().setDefaultAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        # Row-spanning selection border via shared delegate — see
        # row_selection_delegate.py. Color swatches in the cells make the
        # per-cell QSS :selected outline read as broken row chrome.
        self._table.setItemDelegate(RowSelectionBorderDelegate(self._table))
        layout.addWidget(self._table, 1)

        # Populate rows
        row = 0
        listed_keys: set = set()

        for header, keys in self._sections:
            if not keys:
                continue
            row = self._add_section_header(header, row, has_pairs)
            for key in keys:
                row = self._add_row(key, row, has_pairs)
                listed_keys.add(key)

        unlisted = [k for k in self._defaults if k not in listed_keys]
        if unlisted:
            row = self._add_section_header("Other", row, has_pairs)
            for key in unlisted:
                row = self._add_row(key, row, has_pairs)

        # Bottom button row
        self._btn_layout = QtWidgets.QHBoxLayout()
        if add_restore_button:
            btn_defaults = QtWidgets.QPushButton("Restore Defaults")
            btn_defaults.clicked.connect(self.restore_defaults)
            self._btn_layout.addWidget(btn_defaults)
        self._btn_layout.addStretch()
        layout.addLayout(self._btn_layout)

    def _add_section_header(self, title: str, row: int, has_pairs: bool) -> int:
        """Insert a section header row spanning all columns."""
        from uitk.widgets.tableWidget import CellFormatMixin

        col_count = 4 if has_pairs else 3
        return CellFormatMixin.add_section_row(
            self._table, title, row=row, col_count=col_count
        )

    def _add_row(self, key: str, row: int, has_pairs: bool = False) -> int:
        self._table.insertRow(row)

        # Name
        name_item = QtWidgets.QTableWidgetItem(key)
        name_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
        self._table.setItem(row, 0, name_item)

        default = self._default_for(key)

        if self._is_pair(default):
            fg_sw = self._make_swatch(default[0], f"{key} foreground")
            bg_sw = self._make_swatch(default[1], f"{key} background")
            fg_sw.colorChanged.connect(
                lambda c, k=key: self._on_swatch_changed(k, "fg", c)
            )
            bg_sw.colorChanged.connect(
                lambda c, k=key: self._on_swatch_changed(k, "bg", c)
            )
            self._table.setCellWidget(row, 1, self._swatch_cell(fg_sw))
            self._table.setCellWidget(row, 2, self._swatch_cell(bg_sw))
            self._swatches[key] = (fg_sw, bg_sw)
            reset_col = 3
        else:
            sw = self._make_swatch(default, key)
            sw.colorChanged.connect(
                lambda c, k=key: self._on_swatch_changed(k, None, c)
            )
            if has_pairs:
                # Span FG+BG columns
                self._table.setCellWidget(row, 1, self._swatch_cell(sw))
                self._table.setSpan(row, 1, 1, 2)
                reset_col = 3
            else:
                self._table.setCellWidget(row, 1, self._swatch_cell(sw))
                reset_col = 2
            self._swatches[key] = sw

        # Reset button
        reset_btn = QtWidgets.QPushButton()
        reset_btn.setFixedSize(24, 24)
        reset_btn.setToolTip(f"Reset '{key}' to default")
        IconManager.set_icon(reset_btn, "undo", size=(16, 16))
        reset_btn.clicked.connect(lambda checked=False, k=key: self._reset_key(k))
        self._table.setCellWidget(row, reset_col, reset_btn)

        self._table.setRowHeight(row, self._swatch_size + 2)
        return row + 1

    def _swatch_cell(self, swatch: ColorSwatch) -> QtWidgets.QWidget:
        """Wrap a swatch in a centered container for table cells."""
        container = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(container)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(swatch)
        return container

    def _make_swatch(self, hex_color: str, tooltip: str = "") -> ColorSwatch:
        sw = ColorSwatch(color=hex_color)
        sw.setFixedSize(self._swatch_size, self._swatch_size)
        sw.setCursor(QtCore.Qt.PointingHandCursor)
        if tooltip:
            sw.setToolTip(tooltip)
        return sw

    # ── interaction ──────────────────────────────────────────────

    def _on_swatch_changed(self, key: str, role: Optional[str], color: QtGui.QColor):
        if self._settings:
            hex_val = color.name()
            if role:
                self._settings.setValue(f"{key}/{role}", hex_val)
            else:
                self._settings.setValue(key, hex_val)
        self.colors_changed.emit(self.color_map())

    def _reset_key(self, key: str):
        default = self._default_for(key)
        if self._settings:
            if self._is_pair(default):
                self._settings.clear(f"{key}/fg")
                self._settings.clear(f"{key}/bg")
            else:
                self._settings.clear(key)
        self._apply_color(key, default)
        self.colors_changed.emit(self.color_map())

    def _apply_color(self, key: str, value: ColorValue):
        entry = self._swatches.get(key)
        if entry is None:
            return
        if isinstance(entry, tuple):
            fg_sw, bg_sw = entry
            pair = value if self._is_pair(value) else (value, value)
            fg_sw.blockSignals(True)
            fg_sw.color = pair[0]
            fg_sw.blockSignals(False)
            bg_sw.blockSignals(True)
            bg_sw.color = pair[1]
            bg_sw.blockSignals(False)
        else:
            val = value[0] if self._is_pair(value) else value
            entry.blockSignals(True)
            entry.color = val
            entry.blockSignals(False)

    def _load_from_settings(self):
        for key in self._swatches:
            self._apply_color(key, self._current_color(key))

    # ── public API ───────────────────────────────────────────────

    def add_action_button(self, button: QtWidgets.QPushButton):
        """Append *button* to the footer action row."""
        self._btn_layout.addWidget(button)

    def restore_defaults(self):
        """Clear overrides for keys owned by this editor and revert to defaults."""
        if self._settings:
            for key in self._defaults:
                default = self._default_for(key)
                if self._is_pair(default):
                    self._settings.clear(f"{key}/fg")
                    self._settings.clear(f"{key}/bg")
                else:
                    self._settings.clear(key)
        self._load_from_settings()
        self.colors_changed.emit(self.color_map())

    def color_map(self) -> Dict[str, ColorValue]:
        """Return the full mapping with user overrides applied."""
        result = dict(self._defaults)
        for key in result:
            result[key] = self._current_color(key)
        return result

    def apply_color_map(
        self,
        cmap: Dict[str, ColorValue],
        save_to_settings: bool = True,
    ) -> None:
        """Apply *cmap* to the swatches and (optionally) persist to settings.

        Used by the preset loader: the dict comes from a preset file and
        contains hex strings (single) or ``[fg_hex, bg_hex]`` lists (pair).
        Unknown keys are ignored so a preset saved with an older schema
        still loads cleanly.  Writes follow the **default** shape for each
        key (which is what ``_current_color`` reads back), broadcasting a
        scalar to both ``/fg`` and ``/bg`` slots when the default is a pair,
        and collapsing a pair to its foreground when the default is scalar.
        """
        for key, value in cmap.items():
            if key not in self._swatches:
                continue
            self._apply_color(key, value)
            if save_to_settings and self._settings is not None:
                if self._is_pair(self._default_for(key)):
                    fg, bg = value if self._is_pair(value) else (value, value)
                    self._settings.setValue(f"{key}/fg", fg)
                    self._settings.setValue(f"{key}/bg", bg)
                else:
                    val = value[0] if self._is_pair(value) else value
                    self._settings.setValue(key, val)
        self.colors_changed.emit(self.color_map())


class ColorMappingDialog(QtWidgets.QDialog):
    """``QDialog`` wrapper around :class:`ColorMappingEditor`.

    Provides a unified editor layout with :class:`Header` and
    :class:`Footer` for visual consistency with other editors.

    Parameters
    ----------
    defaults, sections, settings, settings_ns, swatch_size
        Forwarded to ``ColorMappingEditor``.
    title : str
        Window title.
    preset_dir : str or Path, optional
        When set, a preset combobox is added to the footer with
        Save/Rename/Delete/Open Folder actions.  A ``"default"`` preset
        is auto-written from *defaults* on first use if missing.
    parent : QWidget, optional
    """

    DEFAULT_PRESET_NAME = "default"

    colors_changed = QtCore.Signal(dict)

    def __init__(
        self,
        defaults: Dict[str, ColorValue],
        sections=None,
        settings=None,
        settings_ns=None,
        swatch_size: int = 22,
        title: str = "Color Mapping",
        preset_dir: Optional[Union[str, Path]] = None,
        parent=None,
    ):
        super().__init__(None)
        # Mirrors EditorPanel's centralized parenting: anchor to a
        # stable top-level so the dialog survives a transient invoker
        # hiding, while ``Qt.Dialog`` keeps us a real window despite
        # having a Qt parent. ``setParent(parent, flags)`` replaces
        # window flags wholesale, so re-pass the full set.
        _dialog_flags = QtCore.Qt.Dialog | QtCore.Qt.FramelessWindowHint
        self.setWindowFlags(_dialog_flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        if parent is not None:
            anchor = parent.window() or parent
            self.setParent(anchor, _dialog_flags)
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setMinimumWidth(280)

        # Inner frame paints the semi-transparent background
        self._frame = QtWidgets.QFrame(self)
        self._frame.setProperty("class", "translucentBgWithBorder")
        frame_layout = QtWidgets.QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        # Header
        self._header = Header(self, config_buttons=["hide"])
        self._header.setText(title.upper())
        frame_layout.addWidget(self._header)

        # Editor (no internal restore button — we put it in Footer)
        self._editor = ColorMappingEditor(
            defaults=defaults,
            sections=sections,
            settings=settings,
            settings_ns=settings_ns,
            swatch_size=swatch_size,
            add_restore_button=False,
        )
        frame_layout.addWidget(self._editor, 1)

        # Footer with status text and action buttons
        self._footer = Footer(self, add_size_grip=True)
        self._footer.setDefaultStatusText(
            f"{len(defaults)} color{'s' if len(defaults) != 1 else ''}"
        )

        self._preset_manager: Optional[PresetManager] = None
        self._preset_combo: Optional[WidgetComboBox] = None
        if preset_dir is not None:
            self._setup_presets(preset_dir)

        self._footer.add_action_button(
            icon_name="undo",
            tooltip="Restore all colors to defaults",
            callback=self._editor.restore_defaults,
        )
        frame_layout.addWidget(self._footer)

        self._editor.colors_changed.connect(self._on_colors_changed)
        self._editor.colors_changed.connect(self.colors_changed)

        self.style = StyleSheet(self)
        self.style.set(theme="dark")
        self._size_initialized = False

    def _setup_presets(self, preset_dir: Union[str, Path]) -> None:
        """Build a :class:`PresetManager` and footer combo for *preset_dir*.

        The preset stores no widget values — colors are carried in the
        ``_meta`` block via *metadata_provider* / *on_metadata_loaded*.
        A "default" preset is auto-written from the editor's defaults
        on first use so users always have a one-click revert path.
        """
        self._preset_manager = PresetManager(preset_dir=preset_dir, widgets=[])
        self._preset_manager.metadata_provider = lambda: {
            "colors": self._editor.color_map()
        }
        self._preset_manager.on_metadata_loaded = self._on_preset_loaded

        if not self._preset_manager.exists(self.DEFAULT_PRESET_NAME):
            # Save defaults (not user overrides) as the canonical baseline
            saved_provider = self._preset_manager.metadata_provider
            self._preset_manager.metadata_provider = lambda: {
                "colors": dict(self._editor._defaults)
            }
            try:
                self._preset_manager.save(self.DEFAULT_PRESET_NAME)
            finally:
                self._preset_manager.metadata_provider = saved_provider

        self._preset_combo = WidgetComboBox(self._footer)
        self._preset_combo.setObjectName("cmb_color_presets")
        self._preset_combo.setToolTip("Load a saved color preset.")
        self._preset_combo.setMinimumWidth(140)
        self._footer.add_widget(self._preset_combo, side="left")
        self._preset_manager.wire_combo(self._preset_combo)

    def _on_preset_loaded(self, meta: dict) -> None:
        """``PresetManager.on_metadata_loaded`` callback — applies colors."""
        colors = meta.get("colors") if isinstance(meta, dict) else None
        if colors:
            self._editor.apply_color_map(colors)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._size_initialized:
            self._size_initialized = True
            QtCore.QTimer.singleShot(0, self._fit_to_content)

    def _fit_to_content(self):
        """Resize the dialog to snugly fit its table content.

        Caps at 85 % of available screen height so a scroll bar appears
        naturally for very long tables.
        """
        table = self.findChild(QtWidgets.QTableWidget)
        if table is None or table.rowCount() == 0:
            self.adjustSize()
            return

        table_h = table.horizontalHeader().height() + 2
        for r in range(table.rowCount()):
            table_h += table.rowHeight(r)

        chrome = self.height() - table.height()

        screen = self.screen()
        max_h = int(screen.availableGeometry().height() * 0.85) if screen else 800
        ideal = table_h + chrome
        self.resize(self.width(), min(ideal, max_h))

    @property
    def header(self):
        """The :class:`Header` widget at the top."""
        return self._header

    @property
    def footer(self):
        """The :class:`Footer` widget at the bottom."""
        return self._footer

    def _on_colors_changed(self, cmap):
        """Update footer status when a color changes."""
        changed = sum(1 for k, v in cmap.items() if v != self._editor._defaults.get(k))
        total = len(cmap)
        if changed:
            self._footer.setStatusText(f"{total} colors ({changed} customised)")
        else:
            self._footer.setStatusText(f"{total} colors")

    def color_map(self):
        """Return the full mapping with user overrides applied."""
        return self._editor.color_map()
