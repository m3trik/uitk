# !/usr/bin/python
# coding=utf-8
"""Base panel for editor windows with Header, body, Footer, and optional presets."""
import json
from pathlib import Path

from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.header import Header
from uitk.widgets.footer import Footer
from uitk.widgets.mixins.style_sheet import StyleSheet
from uitk.widgets.mixins.preset_manager import QStandardPaths_writableLocation


class EditorPanel(QtWidgets.QWidget):
    """Unified editor panel: Header → body → Footer.

    Provides a consistent layout for editor windows.  Subclasses add
    controls and content to ``body_layout``.  Preset management is
    opt-in via ``init_preset_row()``.

    Parameters
    ----------
    title : str
        Text displayed in the header bar.
    header_buttons : list, optional
        Button names for the header (default ``["pin"]``).
    parent : QWidget, optional
    """

    def __init__(self, title="", header_buttons=None, status_text="", parent=None):
        super().__init__(None)
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

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
        self._header = Header(
            self,
            config_buttons=header_buttons if header_buttons is not None else ["hide"],
        )
        self._header.setText(title.upper())
        frame_layout.addWidget(self._header)

        # Body (main content area with margins)
        body = QtWidgets.QWidget()
        self._body_layout = QtWidgets.QVBoxLayout(body)
        self._body_layout.setContentsMargins(4, 4, 4, 4)
        self._body_layout.setSpacing(4)
        frame_layout.addWidget(body, 1)

        # Footer
        self._footer = Footer(self, add_size_grip=True)
        if status_text:
            self._footer.setDefaultStatusText(status_text)
        frame_layout.addWidget(self._footer)

        # Dark theme
        self.style = StyleSheet(self)
        self.style.set(theme="dark")
        self._size_initialized = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._size_initialized:
            self._size_initialized = True
            QtCore.QTimer.singleShot(0, self._fit_to_content)

    def _fit_to_content(self):
        """Resize the window to snugly fit its table content.

        Computes the ideal height from row heights plus chrome, then
        caps at 85 % of the available screen height so a scroll bar
        appears naturally for very long tables.
        """
        table = self.findChild(QtWidgets.QTableWidget)
        if table is None or table.rowCount() == 0:
            self.adjustSize()
            return

        # Ideal table height
        table_h = table.horizontalHeader().height() + 2  # border
        for r in range(table.rowCount()):
            table_h += table.rowHeight(r)

        # Chrome height (header bar, footer, body margins, frame borders)
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

    @property
    def body_layout(self):
        """``QVBoxLayout`` for editor controls and content."""
        return self._body_layout

    # ── Preset management (opt-in) ───────────────────────────────

    _preset_dir_name = None
    _cmb_preset = None

    def init_preset_row(self, dir_name):
        """Add a preset management row to the body layout.

        Call this from the subclass constructor at the desired vertical
        position.  The subclass must also override
        ``export_preset_data()`` and ``import_preset_data()`` to define
        what is saved and loaded.

        Parameters
        ----------
        dir_name : str
            Subdirectory name under ``AppConfigLocation/uitk/``.
        """
        self._preset_dir_name = dir_name

        FIXED_H = 20
        preset_layout = QtWidgets.QHBoxLayout()

        preset_label = QtWidgets.QLabel("Preset:")
        preset_label.setFixedHeight(FIXED_H)

        self._cmb_preset = QtWidgets.QComboBox()
        self._cmb_preset.setFixedHeight(FIXED_H)
        self._cmb_preset.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self._cmb_preset.setPlaceholderText("No saved presets")
        self._cmb_preset.currentIndexChanged.connect(self._on_preset_selected)

        btn_save = self._preset_icon_btn(
            "save", FIXED_H, "Save current settings as a named preset"
        )
        btn_save.clicked.connect(self._on_save_preset)

        btn_rename = self._preset_icon_btn(
            "edit", FIXED_H, "Rename the selected preset"
        )
        btn_rename.clicked.connect(self._on_rename_preset)

        btn_delete = self._preset_icon_btn(
            "trash", FIXED_H, "Delete the selected preset"
        )
        btn_delete.clicked.connect(self._on_delete_preset)

        btn_folder = self._preset_icon_btn("folder", FIXED_H, "Open preset folder")
        btn_folder.clicked.connect(self._on_open_folder)

        preset_layout.addWidget(preset_label)
        preset_layout.addWidget(self._cmb_preset)
        preset_layout.addWidget(btn_save)
        preset_layout.addWidget(btn_rename)
        preset_layout.addWidget(btn_delete)
        preset_layout.addWidget(btn_folder)

        self._body_layout.addLayout(preset_layout)
        self._refresh_presets()

    # ── Preset directory & file helpers ──────────────────────────

    @property
    def preset_dir(self) -> Path:
        """Auto-derived preset directory under AppConfigLocation."""
        d = Path(QStandardPaths_writableLocation()) / "uitk" / self._preset_dir_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _preset_path(self, name: str) -> Path:
        safe = "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in name)
        return self.preset_dir / f"{safe}.json"

    def _list_presets(self) -> list:
        if not self.preset_dir.exists():
            return []
        return sorted(p.stem for p in self.preset_dir.glob("*.json"))

    # ── Preset hooks (override in subclass) ──────────────────────

    def export_preset_data(self) -> dict:
        """Override to provide data for preset saving."""
        return {}

    def import_preset_data(self, data: dict):
        """Override to apply data from a loaded preset."""

    # ── Preset save / load / delete / rename ─────────────────────

    def save_preset(self, name: str) -> Path:
        """Save current state to a named preset."""
        data = self.export_preset_data()
        data["_meta"] = {"version": 1}
        filepath = self._preset_path(name)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return filepath

    def load_preset(self, name: str) -> bool:
        """Load a preset and apply it."""
        filepath = self._preset_path(name)
        if not filepath.exists():
            return False
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                return False
        data.pop("_meta", None)
        self.import_preset_data(data)
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

    # ── Preset UI wiring ─────────────────────────────────────────

    def _refresh_presets(self, select_name: str = None):
        """Repopulate the preset combo."""
        self._cmb_preset.blockSignals(True)
        try:
            self._cmb_preset.clear()
            names = self._list_presets()
            if names:
                self._cmb_preset.addItems(names)
                if select_name:
                    idx = self._cmb_preset.findText(select_name)
                    self._cmb_preset.setCurrentIndex(max(idx, 0))
                else:
                    self._cmb_preset.setCurrentIndex(-1)
                self._cmb_preset.setPlaceholderText("Select a preset\u2026")
            else:
                self._cmb_preset.setPlaceholderText("No saved presets")
        finally:
            self._cmb_preset.blockSignals(False)

    def _on_preset_selected(self, idx):
        if idx < 0:
            return
        name = self._cmb_preset.itemText(idx)
        if name:
            self.load_preset(name)

    def _on_save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "Save Preset", "Preset name:")
        if ok and name.strip():
            name = name.strip()
            self.save_preset(name)
            self._refresh_presets(select_name=name)

    def _on_rename_preset(self):
        idx = self._cmb_preset.currentIndex()
        if idx < 0:
            return
        current = self._cmb_preset.itemText(idx)
        if not current:
            return
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "Rename Preset", "New name:", text=current
        )
        if ok and new_name.strip() and new_name.strip() != current:
            if self.rename_preset(current, new_name.strip()):
                self._refresh_presets(select_name=new_name.strip())

    def _on_delete_preset(self):
        idx = self._cmb_preset.currentIndex()
        if idx < 0:
            return
        name = self._cmb_preset.itemText(idx)
        if name and self.delete_preset(name):
            self._refresh_presets()

    def _on_open_folder(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.preset_dir)))

    @staticmethod
    def _preset_icon_btn(icon_name, height, tooltip):
        """Create a small icon-only button for the preset row."""
        from uitk.widgets.mixins.icon_manager import IconManager

        btn = QtWidgets.QPushButton()
        btn.setFixedSize(height + 4, height)
        btn.setToolTip(tooltip)
        icon_sz = int(height * 0.7)
        IconManager.set_icon(btn, icon_name, size=(icon_sz, icon_sz))
        return btn
