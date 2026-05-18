# !/usr/bin/python
# coding=utf-8
"""Base panel for editor windows with Header, body, Footer, and optional presets."""
import json
from pathlib import Path
from typing import TYPE_CHECKING

from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.header import Header
from uitk.widgets.footer import Footer
from uitk.widgets.mixins.preset_manager import QStandardPaths_writableLocation

if TYPE_CHECKING:  # pragma: no cover
    from uitk.widgets.mixins.style_sheet import StyleSheet


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
        Button names for the header (default ``["hide"]``).
    status_text : str, optional
        Default text shown in the footer status label.
    parent : QWidget, optional
        Anchor widget. The panel reparents to ``parent.window()`` so
        it survives a transient invoker hiding while remaining a real
        top-level window via ``Qt.Window``.
    on_top : bool, optional
        Apply ``WindowStaysOnTopHint``. Defaults to ``False`` so editors
        behave like normal app windows (matches UI Browser, mayatk's
        reference_manager). Opt in for transient surfaces that must
        float above their host.
    """

    def __init__(
        self,
        title="",
        header_buttons=None,
        status_text="",
        parent=None,
        on_top=False,
    ):
        super().__init__(None)
        # Editors behave like normal app windows parented to the host —
        # matching SwitchboardBrowser and mayatk's reference_manager. A
        # subclass that genuinely needs to float above its host (a
        # transient picker, a tool palette) can opt in with on_top=True.
        # Carrying this as an explicit constructor arg — rather than
        # a flag-manipulation done post-super() — keeps the choice
        # visible at every subclass's construction site.
        _panel_flags = (
            QtCore.Qt.Window
            | QtCore.Qt.FramelessWindowHint
        )
        if on_top:
            _panel_flags |= QtCore.Qt.WindowStaysOnTopHint
        self.setWindowFlags(_panel_flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        # Anchor to a stable top-level so the panel survives a transient
        # invoker hiding (e.g. a MarkingMenu, popup, or temporary host
        # widget). We reparent to ``parent.window()`` rather than ``parent``
        # directly so a caller passing some inner container still ends up
        # anchored to the DCC main window. ``Qt.Window`` keeps us a real
        # top-level despite having a Qt parent — same pattern MarkingMenu
        # uses when launching standalone windows. Re-pass the full flag set
        # because setParent(parent, flags) replaces window flags wholesale.
        if parent is not None:
            anchor = parent.window() or parent
            self.setParent(anchor, _panel_flags)
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

        # Body (main content area with margins).
        # Defaults to the dense 2px margins / 2px spacing used by every
        # production editor in the toolset (matches mayatk's reference
        # manager and tentacle's main windows). Subclasses that need a
        # looser layout can override via ``body_layout`` post-init.
        body = QtWidgets.QWidget()
        self._body_layout = QtWidgets.QVBoxLayout(body)
        self._body_layout.setContentsMargins(2, 2, 2, 2)
        self._body_layout.setSpacing(2)
        frame_layout.addWidget(body, 1)

        # Footer
        self._footer = Footer(self, add_size_grip=True)
        if status_text:
            self._footer.setDefaultStatusText(status_text)
        frame_layout.addWidget(self._footer)

        # Style is exposed via the ``style`` lazy property; theme is
        # applied on first ``showEvent`` so panels constructed but never
        # shown skip the QSS work entirely.
        self._size_initialized = False

    @property
    def style(self) -> "StyleSheet":
        """Lazy :class:`StyleSheet` bound to this panel.

        Constructed on first access. The default ``dark`` theme is
        applied automatically the first time the panel is shown (see
        :meth:`showEvent`); subclasses can override at any time via
        ``self.style.set(theme=..., style_class=...)``.

        Robust against accidental ``self._style = None`` reassignment —
        a missing or None-valued cache rebuilds rather than returning
        None to the caller.
        """
        style = self.__dict__.get("_style")
        if style is None:
            from uitk.widgets.mixins.style_sheet import StyleSheet

            style = StyleSheet(self)
            self._style = style
        return style

    def showEvent(self, event):
        super().showEvent(event)
        # First-show: apply the default dark theme unless someone has
        # already explicitly styled this panel. The dual-condition
        # check is deliberate:
        #   ``_default_theme_applied`` — *we* haven't already considered
        #     this panel for default theming on a prior show. Prevents
        #     re-applying dark on every show / hide cycle.
        #   ``self in StyleSheet._widget_configs`` — *anyone* (subclass,
        #     external caller) has applied any theme to this panel. The
        #     StyleSheet maintains this dict as the single source of
        #     truth for "has been themed", so checking it lets a
        #     subclass that called ``self.style.set(theme="light")`` in
        #     __init__ skip our default and keep their choice.
        if not getattr(self, "_default_theme_applied", False):
            self._default_theme_applied = True
            # Pull the class off the (now-instantiated) instance to
            # avoid a second import statement; the import system caches
            # this anyway, but going through ``type(self.style)`` keeps
            # the lazy chain in one place.
            stylesheet_cls = type(self.style)
            if self not in stylesheet_cls._widget_configs:
                self.style.set(theme="dark")

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

    def tighten_sublayouts(self, spacing: int = 1) -> None:
        """Set every nested sub-layout inside ``body_layout`` to *spacing*.

        Editors often build the body as: one or two horizontal control
        rows (preset row, theme row, ui-picker row) above a table. The
        outer ``body_layout`` spacing controls the gap *between* those
        rows; this helper controls the spacing *inside* each row so the
        controls in a single row pack tightly. Call once at the end of
        the subclass constructor after the rows have been added.
        """
        for i in range(self._body_layout.count()):
            sublayout = self._body_layout.itemAt(i).layout()
            if sublayout is not None:
                sublayout.setSpacing(spacing)

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
    def icon_button(
        icon_name: str = "",
        size: int = 24,
        tooltip: str = "",
        icon_size=None,
    ) -> QtWidgets.QPushButton:
        """Build a square, flat, icon-only button for table cells / toolbars.

        Single source of truth for "small icon button" UI elements across
        editors. Use it for table action columns, header rows, anywhere a
        compact iconographic button is needed.

        Parameters
        ----------
        icon_name : str
            IconManager registry name (e.g. ``"undo"``, ``"window"``).
            When empty, the caller is expected to set the icon afterwards.
        size : int
            Edge length of the square button in pixels. Defaults to 24.
        tooltip : str
            Optional hover tooltip.
        icon_size : tuple[int, int] or None
            Inner icon size. Defaults to ``(size - 8, size - 8)``, which
            gives the icon ~4 px breathing room on each side.

        Returns
        -------
        QtWidgets.QPushButton
            A flat, square, no-focus, pointing-hand-cursor button. The
            caller is responsible for connecting ``clicked``.
        """
        from uitk.widgets.mixins.icon_manager import IconManager

        btn = QtWidgets.QPushButton()
        btn.setFlat(True)
        btn.setFocusPolicy(QtCore.Qt.NoFocus)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.setFixedSize(size, size)
        if tooltip:
            btn.setToolTip(tooltip)
        if icon_name:
            sz = icon_size if icon_size else (max(8, size - 8), max(8, size - 8))
            IconManager.set_icon(btn, icon_name, size=sz)
        return btn

    @staticmethod
    def _preset_icon_btn(icon_name, height, tooltip):
        """Create a small icon-only button for the preset row.

        Slightly wider than tall (toolbar look). For table-cell square
        buttons, use :meth:`icon_button` instead.
        """
        from uitk.widgets.mixins.icon_manager import IconManager

        btn = QtWidgets.QPushButton()
        btn.setFixedSize(height + 4, height)
        btn.setToolTip(tooltip)
        icon_sz = int(height * 0.7)
        IconManager.set_icon(btn, icon_name, size=(icon_sz, icon_sz))
        return btn
