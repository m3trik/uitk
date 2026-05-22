# !/usr/bin/python
# coding=utf-8
"""Editor panel: WindowPanel + optional preset save/load row.

Specialization of :class:`WindowPanel` for editors that need to
persist named configurations. The base provides the standard chrome
(Header / body / Footer / theme / anchoring) and this class layers on
the preset combo, the four-icon preset toolbar (save / rename /
delete / open-folder), and the JSON load/save plumbing.

For read-only viewers and other non-editor windowed surfaces, extend
:class:`WindowPanel` directly — none of the preset machinery is forced
onto consumers that don't need it.
"""
import json
from pathlib import Path

from qtpy import QtWidgets, QtCore, QtGui

from uitk.widgets.windowPanel import WindowPanel
from uitk.widgets.mixins.preset_manager import PresetManager


class EditorPanel(WindowPanel):
    """Windowed editor with optional preset management.

    Subclasses add controls and content to ``body_layout``. Preset
    support is opt-in: call :meth:`init_preset_row` from the subclass
    constructor at the desired vertical position, and override
    :meth:`export_preset_data` / :meth:`import_preset_data` to define
    what each preset persists.

    Parameters identical to :class:`WindowPanel`; forwarded unchanged.
    """

    # ── Preset management (opt-in) ───────────────────────────────

    _preset_mgr: "PresetManager | None" = None
    _cmb_preset = None

    def init_preset_row(self, dir_name):
        """Add a preset management row to the body layout.

        Call this from the subclass constructor at the desired vertical
        position. The subclass must also override
        :meth:`export_preset_data` and :meth:`import_preset_data` to
        define what is saved and loaded.

        Parameters
        ----------
        dir_name : str
            Relative subdirectory under :func:`get_presets_root` (the
            ecosystem-wide preset root). The editor's presets live in
            ``<presets_root>/uitk/<dir_name>/``. ``PresetManager``
            handles root resolution, ``M3TRIK_PRESETS_ROOT`` override,
            and legacy migration from older locations like
            ``<AppConfigLocation>/uitk/<dir_name>``.
        """
        self._preset_mgr = PresetManager(preset_dir=f"uitk/{dir_name}")

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
        """The directory where this editor's preset files live.

        Delegates to the underlying :class:`PresetManager`, which
        handles consolidated-root resolution
        (``M3TRIK_PRESETS_ROOT`` override), legacy migration, and
        directory creation.
        """
        if self._preset_mgr is None:
            raise RuntimeError(
                "preset_dir is unavailable until init_preset_row() runs."
            )
        return self._preset_mgr.preset_dir

    @preset_dir.setter
    def preset_dir(self, value) -> None:
        """Redirect this editor's preset directory.

        Accepts anything :attr:`PresetManager.preset_dir` accepts: a
        full path, a tilde string, an env-var expression, or a path
        relative to :func:`get_presets_root`.
        """
        if self._preset_mgr is None:
            raise RuntimeError(
                "preset_dir cannot be set before init_preset_row() runs."
            )
        self._preset_mgr.preset_dir = value

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
                self._cmb_preset.setPlaceholderText("Select a preset…")
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
        """Create a small icon-only button for the preset row.

        Slightly wider than tall (toolbar look). For table-cell square
        buttons, use :meth:`WindowPanel.icon_button` instead.
        """
        from uitk.widgets.mixins.icon_manager import IconManager

        btn = QtWidgets.QPushButton()
        btn.setFixedSize(height + 4, height)
        btn.setToolTip(tooltip)
        icon_sz = int(height * 0.7)
        IconManager.set_icon(btn, icon_name, size=(icon_sz, icon_sz))
        return btn
