# !/usr/bin/python
# coding=utf-8
"""Searchable, tag-filtered launcher for any UI registered with a Switchboard.

Listed UIs are pulled from ``switchboard._file_manager.ui_registry`` and never
instantiated until the user clicks Launch. Tags are read from the .ui XML at
register time (see ``Switchboard.save_ui_tags`` / ``_parse_ui_tags``) so they
are knowable for every entry without breaking lazy loading.

The browser itself is unregistered — a plain ``EditorPanel`` instantiated
directly by user code, consistent with ``StyleEditor`` and ``ColorMappingDialog``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, List, Optional, Set

from qtpy import QtCore, QtGui, QtWidgets
import pythontk as ptk

# ``EditorPanel`` is the base class — must be a real import. ``Switchboard``
# is referenced at runtime only inside the no-arg ``__init__`` branch
# (lazy-imported there) and in type annotations (TYPE_CHECKING block).
# ``StyleSheet`` is reachable via ``sb.style`` at use sites — no direct
# import needed.
from uitk.widgets.editors.editor_panel import EditorPanel

if TYPE_CHECKING:  # pragma: no cover
    from uitk.switchboard import Switchboard


# ── Launch options (per-launch, not persisted per-UI) ─────────────────────────
#
# Defaults mirror the tentacle marking-menu style (frameless + translucent +
# dark theme + translucentBgWithBorder) so a browser-launched window matches
# the rest of the toolset out of the box.


@dataclass
class LaunchOptions:
    frameless: bool = True
    on_top: bool = False
    translucent: bool = True
    restore_geometry: bool = True
    theme: str = "dark"


# ── Data model ────────────────────────────────────────────────────────────────


class SwitchboardBrowserModel(QtCore.QAbstractTableModel):
    """Table model over a Switchboard's UI registry.

    Each row is a registered UI. Rows are not loaded — they exist as registry
    entries only. ``is_loaded`` / ``is_visible`` are computed live.

    Columns:
        0 = Name
        1 = Tags
        2 = Launch / Focus action (icon button via setIndexWidget)
        3 = Close action (icon button via setIndexWidget)

    Custom roles return the same data regardless of column so filter
    predicates can query any column.
    """

    COL_NAME = 0
    COL_TAGS = 1
    COL_ACTION = 2
    COL_CLOSE = 3
    COLUMN_COUNT = 4

    NameRole = QtCore.Qt.UserRole + 1
    PathRole = QtCore.Qt.UserRole + 2
    TagsRole = QtCore.Qt.UserRole + 3
    LoadedRole = QtCore.Qt.UserRole + 4
    VisibleRole = QtCore.Qt.UserRole + 5
    FileTagsRole = QtCore.Qt.UserRole + 6
    InheritedTagsRole = QtCore.Qt.UserRole + 7

    def __init__(self, switchboard: Switchboard, parent=None):
        super().__init__(parent)
        self.sb: Switchboard = switchboard
        self._names: List[str] = []
        self._tracked: Set[str] = set()  # UIs whose on_show/on_hide we've connected to
        self._refresh()
        self.sb.on_ui_registered.connect(self._on_ui_registered)
        self.sb.on_ui_tags_changed.connect(self._on_ui_tags_changed)

    # ---- registry → rows ----

    def _refresh(self) -> None:
        self.beginResetModel()
        self._names = sorted(self.sb.registry.ui_registry.get("filename") or [])
        self.endResetModel()
        for name in self._names:
            self._track_visibility(name)

    def _on_ui_registered(self, name: str) -> None:
        if name in self._names:
            return
        # Insert in sorted position
        pos = 0
        for i, existing in enumerate(self._names):
            if name < existing:
                pos = i
                break
            pos = i + 1
        self.beginInsertRows(QtCore.QModelIndex(), pos, pos)
        self._names.insert(pos, name)
        self.endInsertRows()
        self._track_visibility(name)

    def _on_ui_tags_changed(self, name: str) -> None:
        if name in self._names:
            row = self._names.index(name)
            top = self.index(row, 0)
            bot = self.index(row, self.COLUMN_COUNT - 1)
            self.dataChanged.emit(top, bot)

    # ---- visibility tracking via MainWindow signals ----

    def _track_visibility(self, name: str) -> None:
        """Lazily connect to a loaded UI's on_show/on_hide signals."""
        if name in self._tracked:
            return
        try:
            if name not in self.sb.loaded_ui:
                return
            ui = self.sb.loaded_ui[name]
        except Exception:
            return

        on_show = getattr(ui, "on_show", None)
        on_hide = getattr(ui, "on_hide", None)
        if on_show is None or on_hide is None:
            return

        def _refresh_row(_name=name):
            if _name in self._names:
                row = self._names.index(_name)
                top = self.index(row, 0)
                bot = self.index(row, self.COLUMN_COUNT - 1)
                self.dataChanged.emit(top, bot)

        try:
            on_show.connect(_refresh_row)
            on_hide.connect(_refresh_row)
            self._tracked.add(name)
        except Exception:
            pass

    def refresh_after_launch(self, name: str) -> None:
        """Public hook: caller invokes this after launching to wire signals."""
        self._track_visibility(name)
        if name in self._names:
            row = self._names.index(name)
            top = self.index(row, 0)
            bot = self.index(row, self.COLUMN_COUNT - 1)
            self.dataChanged.emit(top, bot)

    # ---- QAbstractTableModel ----

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._names)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else self.COLUMN_COUNT

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if orientation != QtCore.Qt.Horizontal:
            return None
        if role == QtCore.Qt.DisplayRole:
            return {
                self.COL_NAME: "Name",
                self.COL_TAGS: "Tags",
                self.COL_ACTION: "",
                self.COL_CLOSE: "",
            }.get(section, "")
        if role == QtCore.Qt.TextAlignmentRole:
            # Left-align the title row so titles sit flush with row content
            # instead of Qt's default center alignment.
            return int(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        return None

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._names):
            return None
        name = self._names[index.row()]

        # Custom roles are column-independent — always describe the row's UI.
        if role == self.NameRole:
            return name
        if role == self.PathRole:
            return self._path_for(name)
        if role == self.TagsRole:
            return sorted(self._all_tags_for(name))
        if role == self.FileTagsRole:
            return sorted(self.sb._ui_xml_tags.get(name, set()))
        if role == self.InheritedTagsRole:
            return sorted(self._inherited_tags_for(name))
        if role == self.LoadedRole:
            return name in self.sb.loaded_ui
        if role == self.VisibleRole:
            return self._is_visible(name)

        # Display role: only Name and Tags columns produce text via the
        # delegate's HTML renderer; the action columns hold widgets.
        if role == QtCore.Qt.DisplayRole:
            if index.column() == self.COL_NAME:
                return name
            # Tags column has no plain-text representation; the delegate
            # paints HTML. Returning empty string suppresses the default
            # text painter from drawing over our paint.
            return ""

        return None

    def flags(self, index):
        base = super().flags(index)
        # Tags column accepts inline editing; commit goes through the
        # delegate's setEditorData / setModelData.
        if index.isValid() and index.column() == self.COL_TAGS:
            return base | QtCore.Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid() or role != QtCore.Qt.EditRole:
            return False
        if index.column() != self.COL_TAGS:
            return False
        name = self._names[index.row()]
        path = self._path_for(name)
        if not path:
            return False
        # value is a comma-separated string of file tags entered by the user
        new_tags = {t.strip() for t in str(value).split(",") if t.strip()}
        try:
            self.sb.save_ui_tags(path, new_tags)
        except Exception:
            return False
        return True

    # ---- helpers ----

    def _path_for(self, name: str) -> Optional[str]:
        return self.sb.registry.ui_registry.get(filename=name, return_field="filepath")

    def _inherited_tags_for(self, name: str) -> Set[str]:
        """Filename + source-directory tags (the non-XML inherited ones)."""
        tags = set(self.sb.get_tags_from_name(name) or set())
        path = self._path_for(name)
        if path and self.sb._source_tags:
            norm = os.path.normpath(os.path.abspath(path))
            for src_dir, src_tags in self.sb._source_tags.items():
                if norm.startswith(src_dir + os.sep) or norm == src_dir:
                    tags.update(src_tags)
                    break
        return tags

    def _all_tags_for(self, name: str) -> Set[str]:
        tags = self._inherited_tags_for(name)
        tags |= set(self.sb._ui_xml_tags.get(name, set()))
        if name in self.sb.loaded_ui:
            try:
                tags |= set(self.sb.loaded_ui[name].tags or set())
            except Exception:
                pass
        return tags

    def _is_visible(self, name: str) -> bool:
        try:
            ui = self.sb.loaded_ui[name] if name in self.sb.loaded_ui else None
        except Exception:
            return False
        return bool(ui and ui.isVisible())

    def all_unique_tags(self) -> List[str]:
        seen: Set[str] = set()
        for name in self._names:
            seen |= self._all_tags_for(name)
        return sorted(seen)


# ── Tag editor dialog ─────────────────────────────────────────────────────────


class TagEditDialog(QtWidgets.QDialog):
    """Modal for editing the file-level tags of a single UI.

    Inherited tags (filename + source-directory) are shown as read-only chips
    for context. Only file tags are editable here; saving calls
    ``Switchboard.save_ui_tags``.
    """

    def __init__(self, ui_name, inherited_tags, file_tags, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit tags — {ui_name}")
        self.setModal(True)
        self.resize(360, 300)

        self._tags: Set[str] = set(file_tags or set())

        layout = QtWidgets.QVBoxLayout(self)

        # Inherited (read-only): from the .ui filename or the directory the
        # UI was registered from. Edit those at the source, not here.
        if inherited_tags:
            inherited_lbl = QtWidgets.QLabel("Inherited (read-only):")
            inherited_lbl.setToolTip(
                "These tags come from the .ui filename (e.g. 'name#tag.ui')\n"
                "or from the directory passed to switchboard.register(...).\n"
                "They're not stored in this file, so they can't be edited here."
            )
            layout.addWidget(inherited_lbl)
            inh_row = QtWidgets.QHBoxLayout()
            inh_row.setSpacing(4)
            for t in sorted(inherited_tags):
                chip = QtWidgets.QLabel(f"#{t}")
                chip.setStyleSheet(
                    "padding: 2px 6px; border-radius: 8px;"
                    " background: #444; color: #aaa;"
                )
                chip.setToolTip(
                    f"#{t} — inherited; not editable here.\n"
                    "Custom tags added below are stored in the .ui file."
                )
                inh_row.addWidget(chip)
            inh_row.addStretch(1)
            layout.addLayout(inh_row)

        # File tags — these are the ones written into the .ui XML by
        # save_ui_tags. Adding a tag here works alongside any inherited tags.
        file_lbl = QtWidgets.QLabel("File tags (stored in this .ui):")
        file_lbl.setToolTip(
            "Tags written into the .ui file as <property name='uitk_tags'>.\n"
            "Travels with the file; visible and editable in Qt Designer."
        )
        layout.addWidget(file_lbl)
        self._list = QtWidgets.QListWidget()
        self._list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        for t in sorted(self._tags):
            self._list.addItem(t)
        layout.addWidget(self._list, 1)

        add_row = QtWidgets.QHBoxLayout()
        self._line = QtWidgets.QLineEdit()
        self._line.setPlaceholderText("Add tag and press Enter")
        self._line.returnPressed.connect(self._on_add)
        btn_add = QtWidgets.QPushButton("Add")
        btn_add.clicked.connect(self._on_add)
        btn_remove = QtWidgets.QPushButton("Remove")
        btn_remove.clicked.connect(self._on_remove)
        add_row.addWidget(self._line, 1)
        add_row.addWidget(btn_add)
        add_row.addWidget(btn_remove)
        layout.addLayout(add_row)

        # Buttons
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _on_add(self):
        text = self._line.text().strip().lstrip("#")
        if not text or "," in text:
            self._line.clear()
            return
        if text in self._tags:
            self._line.clear()
            return
        self._tags.add(text)
        self._refresh_list(select=text)
        self._line.clear()

    def _on_remove(self):
        item = self._list.currentItem()
        if not item:
            return
        self._tags.discard(item.text())
        self._refresh_list()

    def _refresh_list(self, select: Optional[str] = None):
        self._list.clear()
        for t in sorted(self._tags):
            self._list.addItem(t)
        if select:
            for i in range(self._list.count()):
                if self._list.item(i).text() == select:
                    self._list.setCurrentRow(i)
                    break

    def tags(self) -> Set[str]:
        return set(self._tags)


# ── Row delegate ──────────────────────────────────────────────────────────────


# Color palette for the row paint, sourced from pythontk so we get the same
# desaturated pastel set used elsewhere in the ecosystem (status badges,
# diff trees, etc.) and stay consistent if those palettes are tweaked later.
_STATUS_PALETTE = ptk.Palette.status()
_UI_PALETTE = ptk.Palette.ui()
_NAME_COLOR = _UI_PALETTE["text"].hex                  # neutral text
_NAME_VISIBLE_COLOR = _STATUS_PALETTE["warn"].fg.hex   # warm gold (visible)
_INHERITED_TAG_COLOR = _STATUS_PALETTE["locked"].fg.hex  # dimmed grey
_FILE_TAG_COLOR = _STATUS_PALETTE["info"].fg.hex       # soft steel-blue


class _BrowserRowDelegate(QtWidgets.QStyledItemDelegate):
    """Per-column renderer for the browser table.

    Column 0 (Name): bold; gold + italic when the UI is currently visible.
    Column 1 (Tags): mixed-source chips. Inherited tags (filename +
        source-directory) are gray + italic to signal they're read-only.
        File tags (XML ``uitk_tags``) are teal + regular weight; these are
        what inline-editing modifies.

    Inline editing on the Tags column edits only the file-tags portion as
    a comma-separated string. Inherited tags are not shown in the editor —
    they live elsewhere and editing them here would be misleading.
    """

    _MARGIN = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = QtGui.QTextDocument()
        self._doc.setDocumentMargin(0)

    def _name_html(self, index) -> str:
        from html import escape

        name = index.data(SwitchboardBrowserModel.NameRole) or ""
        visible = bool(index.data(SwitchboardBrowserModel.VisibleRole))
        if visible:
            return (
                f'<span style="color:{_NAME_VISIBLE_COLOR};font-weight:bold;'
                f'font-style:italic">{escape(name)}</span>'
            )
        return (
            f'<span style="color:{_NAME_COLOR};font-weight:bold">'
            f"{escape(name)}</span>"
        )

    def _tags_html(self, index) -> str:
        from html import escape

        inherited = index.data(SwitchboardBrowserModel.InheritedTagsRole) or []
        file_tags = index.data(SwitchboardBrowserModel.FileTagsRole) or []
        chips = []
        # Inherited first — italic to signal "not editable here"
        for t in sorted(inherited):
            chips.append(
                f'<span style="color:{_INHERITED_TAG_COLOR};font-style:italic">'
                f"#{escape(t)}</span>"
            )
        for t in sorted(file_tags):
            chips.append(
                f'<span style="color:{_FILE_TAG_COLOR}">#{escape(t)}</span>'
            )
        return " ".join(chips)

    def _build_html(self, index) -> Optional[str]:
        col = index.column()
        if col == SwitchboardBrowserModel.COL_NAME:
            return self._name_html(index)
        if col == SwitchboardBrowserModel.COL_TAGS:
            return self._tags_html(index)
        return None

    def paint(self, painter, option, index):
        html = self._build_html(index)
        if html is None:
            # Action columns are filled via setIndexWidget; let the default
            # paint handle them (background, etc.).
            super().paint(painter, option, index)
            return

        # Default selection / hover background
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        self._doc.setHtml(html)
        self._doc.setTextWidth(option.rect.width() - 2 * self._MARGIN)

        painter.save()
        painter.translate(
            option.rect.left() + self._MARGIN, option.rect.top() + self._MARGIN
        )
        clip = QtCore.QRectF(
            0, 0, option.rect.width() - 2 * self._MARGIN, option.rect.height()
        )
        self._doc.drawContents(painter, clip)
        painter.restore()

    def sizeHint(self, option, index):
        html = self._build_html(index)
        if html is None:
            return super().sizeHint(option, index)
        self._doc.setHtml(html)
        self._doc.setTextWidth(option.rect.width() - 2 * self._MARGIN)
        return QtCore.QSize(
            int(self._doc.idealWidth()) + 2 * self._MARGIN,
            int(self._doc.size().height()) + 2 * self._MARGIN,
        )

    # ── Inline editing on the Tags column ──────────────────────────

    def createEditor(self, parent, option, index):
        if index.column() != SwitchboardBrowserModel.COL_TAGS:
            return super().createEditor(parent, option, index)
        editor = QtWidgets.QLineEdit(parent)
        editor.setPlaceholderText("comma-separated file tags")
        return editor

    def setEditorData(self, editor, index):
        if index.column() != SwitchboardBrowserModel.COL_TAGS:
            return super().setEditorData(editor, index)
        # Edit only the file-tags portion. Inherited tags aren't shown here
        # because editing them would be a lie — they come from filename or
        # registration, not from this file's XML. Tooltip surfaces the
        # inherited set so the user knows nothing was dropped.
        file_tags = index.data(SwitchboardBrowserModel.FileTagsRole) or []
        inherited = index.data(SwitchboardBrowserModel.InheritedTagsRole) or []
        editor.setText(", ".join(file_tags))
        if inherited:
            inh_str = ", ".join(f"#{t}" for t in inherited)
            editor.setToolTip(
                f"Editing file tags only.\n"
                f"Inherited (not editable here): {inh_str}"
            )
        else:
            editor.setToolTip("Comma-separated tags stored in this .ui file.")

    def setModelData(self, editor, model, index):
        if index.column() != SwitchboardBrowserModel.COL_TAGS:
            return super().setModelData(editor, model, index)
        model.setData(index, editor.text(), QtCore.Qt.EditRole)


# ── Filter proxy ──────────────────────────────────────────────────────────────


class _BrowserFilterProxy(QtCore.QSortFilterProxyModel):
    """Proxy that delegates row acceptance to the owning browser's predicate."""

    def __init__(self, browser):
        super().__init__(browser)
        self._browser = browser

    def filterAcceptsRow(self, source_row, source_parent):
        src = self.sourceModel()
        # Table model: column is required. Custom roles are
        # column-independent so column 0 works for the predicate inputs.
        idx = src.index(source_row, 0, source_parent)
        name = idx.data(SwitchboardBrowserModel.NameRole)
        tags = set(idx.data(SwitchboardBrowserModel.TagsRole) or [])
        if not name:
            return False
        return self._browser._row_passes_filter(name, tags)


# ── Main browser ──────────────────────────────────────────────────────────────


SHOW_VISIBLE = "visible"
SHOW_HIDDEN = "hidden"
SHOW_ALL = "all"

SCOPE_NAME = "name"
SCOPE_TAGS = "tags"
SCOPE_BOTH = "name + tags"


class SwitchboardBrowser(EditorPanel):
    """Searchable launcher for every UI registered with a Switchboard.

    ``switchboard`` is optional. When omitted, a fresh ``Switchboard``
    is constructed from any ``**switchboard_kwargs`` you pass (typically
    ``ui_source``). The integration pattern most callers want is to pass
    an *existing* switchboard so launched UIs land in the same
    ``loaded_ui`` namespace, share registered widgets / icons, and route
    through the same handlers (e.g. tentacle's marking menu)::

        # Integrated — preferred for application-embedded use
        browser = SwitchboardBrowser(switchboard=app.sb)

        # Standalone — auto-creates an empty Switchboard which the
        # caller can feed via switchboard_kwargs
        browser = SwitchboardBrowser(ui_source="/path/to/ui_dir")

    Mirrors the ``mayatk.MayaUiHandler`` pattern of "use what's given,
    otherwise stand one up" so the browser can be opened from anywhere
    without forcing the caller to wire a switchboard first.
    """

    def __init__(
        self,
        switchboard: Optional[Switchboard] = None,
        parent=None,
        **switchboard_kwargs,
    ):
        # Accept an existing Switchboard, or auto-create one. Passing
        # both is ambiguous — the kwargs would silently apply to the
        # caller's switchboard or be dropped, neither obviously right —
        # so reject the mix loudly.
        if switchboard is not None and switchboard_kwargs:
            raise ValueError(
                "SwitchboardBrowser: pass an existing 'switchboard' OR "
                "switchboard_kwargs (e.g. ui_source=...), not both."
            )
        if switchboard is None:
            # Lazy import — avoid pulling Switchboard at module load when
            # the caller is going to provide their own instance anyway.
            from uitk.switchboard import Switchboard

            switchboard = Switchboard(**switchboard_kwargs)

        # ``menu`` button gives us a header dropdown that hosts the preset
        # combo and global browser options (Refresh, presets, …).
        # ``collapse`` and ``minimize`` give the same window-management
        # affordances we configure on launched UIs.
        super().__init__(
            title="UI Browser",
            header_buttons=["menu", "collapse", "minimize", "hide"],
            parent=parent,
        )
        self.sb: Switchboard = switchboard
        self.resize(420, 560)
        # Skip EditorPanel's QTableWidget-based auto-fit; we use a QTableView
        # and manage our own size.
        self._size_initialized = True

        # Browser-owned settings (hide lists, scope, last options)
        self._settings = self.sb.settings.branch("ui_browser")

        # Persistent filter-enabled state (controls whether the text query
        # is applied; chip filters and hide system always apply).
        self._filter_enabled = bool(self._settings.value("filter_enabled", True))

        self._model = SwitchboardBrowserModel(self.sb, parent=self)

        # ── Search row ─────────────────────────────────────────────────
        # Use uitk's registered LineEdit so we get OptionBoxMixin (action
        # button + dropdown menu) — pattern mirrors mayatk reference_manager.
        self._search = self.sb.registered_widgets.LineEdit()
        self._search.setPlaceholderText("Search (comma-separated; supports * ?)")
        self._search.setToolTip(
            "Search the registered UI list.\n"
            "\n"
            "• Multi-term: separate terms with commas — any matching term keeps\n"
            "  the row, e.g.  alpha, beta  matches either.\n"
            "• Wildcards:\n"
            "    *      any sequence of characters\n"
            "    ?      any single character\n"
            "    [seq]  any character in the set, e.g. [abc]\n"
            "  Bare terms are wrapped as *term* automatically (substring match).\n"
            "• Use the option-box menu (▾) to set the search scope, change the\n"
            "  filter mode, or specify an exclude pattern.\n"
            "• Click the action button to toggle the filter on/off without\n"
            "  clearing the text."
        )
        self._search.textChanged.connect(self._apply_filter)

        # Filter enable/disable as an option-box action (cycle states)
        self._search.option_box.set_action(
            states=[
                {
                    "icon": "filter",
                    "tooltip": "Filter enabled. Click to disable.",
                    "callback": lambda: self._set_filter_enabled(False),
                },
                {
                    "icon": "filter",
                    "color": "#555555",
                    "tooltip": "Filter disabled. Click to enable.",
                    "callback": lambda: self._set_filter_enabled(True),
                },
            ],
        )

        # Search options live inside the line edit's option-box menu
        self._search.option_box.menu.setTitle("Search options:")
        self._scope = self._search.option_box.menu.add(
            "QComboBox",
            setObjectName="cmb_search_scope",
            setToolTip="What the search text matches against.",
            addItems=[SCOPE_BOTH, SCOPE_NAME, SCOPE_TAGS],
        )
        self._scope.setCurrentText(self._settings.value("scope", SCOPE_BOTH))
        self._scope.currentTextChanged.connect(self._on_scope_changed)

        # Exclude line edit — wired through pythontk.filter_list's ``exc=``
        # parameter, so it accepts the same wildcards / comma-delimited terms
        # as the include search above.
        self._exclude = self._search.option_box.menu.add(
            "QLineEdit",
            setObjectName="le_exclude",
            setPlaceholderText="Exclude (comma-separated; supports * ?)",
            setToolTip=(
                "Hide rows that match any of these patterns.\n"
                "Same wildcard / multi-term syntax as the main search field."
            ),
            setText=self._settings.value("exclude", "") or "",
        )
        self._exclude.textChanged.connect(self._on_exclude_changed)

        self.body_layout.addWidget(self._search)

        # ── Show row ───────────────────────────────────────────────────
        show_row = QtWidgets.QHBoxLayout()
        show_row.addWidget(QtWidgets.QLabel("Show:"))
        self._show = QtWidgets.QComboBox()
        self._show.addItems([SHOW_VISIBLE, SHOW_HIDDEN, SHOW_ALL])
        # Force the combobox AND its dropdown view to fit the longest item.
        # ``AdjustToContents`` alone is sometimes ignored by the parent layout
        # on first show, so we explicitly compute the longest item width
        # via font metrics and set both the combo's and the popup view's
        # minimum width.
        self._show.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToContents
        )
        self._show.setSizePolicy(
            QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed
        )
        fm = self._show.fontMetrics()
        max_w = max(
            fm.horizontalAdvance(self._show.itemText(i))
            for i in range(self._show.count())
        )
        # +30 covers the dropdown arrow, internal padding, and a small
        # margin so text doesn't kiss the edges.
        self._show.setMinimumWidth(max_w + 30)
        self._show.view().setMinimumWidth(max_w + 30)
        self._show.setCurrentText(self._settings.value("show_mode", SHOW_VISIBLE))
        self._show.currentTextChanged.connect(self._on_show_changed)
        show_row.addWidget(self._show)
        self._unhide_all_btn = QtWidgets.QPushButton("Unhide all")
        self._unhide_all_btn.clicked.connect(self._on_unhide_all)
        show_row.addWidget(self._unhide_all_btn)
        show_row.addStretch(1)
        self.body_layout.addLayout(show_row)

        # ── Tag chips ──────────────────────────────────────────────────
        self._chip_scroll = QtWidgets.QScrollArea()
        self._chip_scroll.setWidgetResizable(True)
        self._chip_scroll.setFixedHeight(34)
        self._chip_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAsNeeded
        )
        self._chip_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._chip_container = QtWidgets.QWidget()
        self._chip_layout = QtWidgets.QHBoxLayout(self._chip_container)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(4)
        self._chip_layout.addStretch(1)
        self._chip_scroll.setWidget(self._chip_container)
        self.body_layout.addWidget(self._chip_scroll)

        self._active_tag_filters: Set[str] = set()
        self._chip_buttons = {}  # tag -> QPushButton

        # ── Table view ─────────────────────────────────────────────────
        self._proxy = _BrowserFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        self._view = QtWidgets.QTableView()
        self._view.setModel(self._proxy)
        self._view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        # Tags column (col 1) accepts inline editing via the delegate;
        # name column (col 0) is read-only.
        self._view.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        self._view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._on_row_context_menu)
        self._view.selectionModel().currentChanged.connect(self._update_action_button)
        self._view.doubleClicked.connect(self._on_double_click)
        self._row_delegate = _BrowserRowDelegate(self)
        self._view.setItemDelegate(self._row_delegate)
        # Header configuration: name stretches, tags expand, action columns fixed
        h = self._view.horizontalHeader()
        h.setSectionResizeMode(SwitchboardBrowserModel.COL_NAME, QtWidgets.QHeaderView.ResizeToContents)
        h.setSectionResizeMode(SwitchboardBrowserModel.COL_TAGS, QtWidgets.QHeaderView.Stretch)
        h.setSectionResizeMode(SwitchboardBrowserModel.COL_ACTION, QtWidgets.QHeaderView.Fixed)
        h.setSectionResizeMode(SwitchboardBrowserModel.COL_CLOSE, QtWidgets.QHeaderView.Fixed)
        # Action columns are sized to exactly the icon button (22x22) plus
        # zero item padding, so the cell hugs the button with no dead zone
        # on either side. Padding is killed via ``QTableView::item`` QSS so
        # it doesn't reintroduce the whitespace through native styling.
        # ``setMinimumSectionSize`` is required because QHeaderView defaults
        # to a ~30px minimum that silently overrides ``setColumnWidth(22)``.
        h.setMinimumSectionSize(22)
        self._view.setColumnWidth(SwitchboardBrowserModel.COL_ACTION, 22)
        self._view.setColumnWidth(SwitchboardBrowserModel.COL_CLOSE, 22)
        self._view.setStyleSheet("QTableView::item { padding: 0; }")
        self._view.verticalHeader().setVisible(False)
        self._view.verticalHeader().setDefaultSectionSize(22)
        self._view.setShowGrid(False)
        self.body_layout.addWidget(self._view, 1)

        # ── Footer action button ───────────────────────────────────────
        # Use uitk's PushButton so we get an OptionBox dropdown menu for
        # launch flags — pattern mirrors mayatk scene_exporter task options.
        self._action_btn = self.sb.registered_widgets.PushButton()
        self._action_btn.setText("Launch")
        self._action_btn.setMinimumHeight(28)
        self._action_btn.clicked.connect(self._on_action_clicked)
        self._action_btn.option_box.menu.setTitle("Launch options:")

        # Defaults match the tentacle marking menu launch style:
        #   - Frameless + Translucent + dark theme + translucentBgWithBorder
        # so the browser-launched window matches the tools UX out of the box.
        # No "Start pinned" option — pin/unpin is the launched window's own
        # header concern (its hide button replaces pin in this UX).
        self._launch_option_widgets = {}
        for key, label, default, tooltip in [
            ("frameless", "Frameless", True, "Remove window title bar."),
            (
                "on_top",
                "On top",
                True,
                # Default ON: launched UIs need to share the browser's
                # on-top z-class, otherwise they end up hidden behind the
                # browser when the browser is on-top (the marking-menu
                # default). Recent-raise wins within the same z-class so
                # the launched UI ends up above the browser.
                "Keep the window above other application windows.",
            ),
            (
                "translucent",
                "Translucent",
                True,
                "Translucent background with rounded border (matches marking-menu style).",
            ),
            (
                "restore_geometry",
                "Restore geometry",
                True,
                "Restore the last saved size/position.",
            ),
        ]:
            cb = self._action_btn.option_box.menu.add(
                "QCheckBox",
                setText=label,
                setToolTip=tooltip,
                setChecked=bool(self._settings.value(f"opt_{key}", default)),
            )
            cb.toggled.connect(
                lambda v, k=key: self._settings.setValue(f"opt_{k}", bool(v))
            )
            self._launch_option_widgets[key] = cb
        # Backward-compatible attribute aliases used elsewhere in the class
        self._cb_frameless = self._launch_option_widgets["frameless"]
        self._cb_on_top = self._launch_option_widgets["on_top"]
        self._cb_translucent = self._launch_option_widgets["translucent"]
        self._cb_restore = self._launch_option_widgets["restore_geometry"]

        # Theme: pulled through the switchboard's ``style`` proxy (the
        # ``SwitchboardStyleMixin``) so any theme added to ``StyleSheet``
        # shows up here automatically without a direct import.
        theme_names = list(self.sb.style.themes.keys()) or ["dark", "light"]
        self._cmb_theme = self._action_btn.option_box.menu.add(
            "QComboBox",
            setObjectName="cmb_theme",
            setToolTip="Style template applied to the launched window.",
            addItems=theme_names,
        )
        saved_theme = self._settings.value("opt_theme", "dark")
        if saved_theme not in theme_names:
            saved_theme = theme_names[0]
        self._cmb_theme.setCurrentText(saved_theme)
        self._cmb_theme.currentTextChanged.connect(
            lambda v: self._settings.setValue("opt_theme", v)
        )

        self.body_layout.addWidget(self._action_btn)

        # ── Header option menu ─────────────────────────────────────────
        # Lives off the header's "menu" button; hosts the preset selector
        # plus global browser toggles. Built last because the preset's
        # metadata provider reads from body widgets that must already exist.
        self._init_header_menu()

        # ── Footer status ──────────────────────────────────────────────
        # Idle: counts (registered / visible / shown). Selected: the
        # selected UI's name + path. HTML-formatted via the footer's
        # status label (which is a QLabel under the hood).
        self.footer.setDefaultStatusText("")

        # Final wiring. Footer/chip/row-widget refresh share a single
        # debounced path (``_do_full_refresh``); per-signal connections
        # to ``_update_footer_status`` would re-fire its O(N) visible-count
        # loop on every dataChanged, which is wasteful. Selection changes
        # update only the footer (no row rebuild needed).
        self._model.dataChanged.connect(self._on_model_data_changed)
        self._model.rowsInserted.connect(self._defer_full_refresh)
        self._model.rowsRemoved.connect(self._defer_full_refresh)
        self._proxy.layoutChanged.connect(self._defer_full_refresh)
        self._view.selectionModel().currentChanged.connect(
            self._update_footer_status
        )
        self._refresh_chips()
        self._update_show_ui()
        self._apply_filter()
        self._refresh_row_widgets()
        self._select_first_row()
        self._update_action_button()
        self._update_footer_status()

    # ── helpers ──────────────────────────────────────────────────────────────

    @property
    def hidden_uis(self) -> Set[str]:
        raw = self._settings.value("hidden_uis", []) or []
        return set(raw)

    @hidden_uis.setter
    def hidden_uis(self, value: Iterable[str]) -> None:
        self._settings.setValue("hidden_uis", sorted(set(value)))

    @property
    def hidden_tags(self) -> Set[str]:
        raw = self._settings.value("hidden_tags", []) or []
        return set(raw)

    @hidden_tags.setter
    def hidden_tags(self, value: Iterable[str]) -> None:
        self._settings.setValue("hidden_tags", sorted(set(value)))

    # ── Header menu (presets + global toggles) ──────────────────────────────

    def _init_header_menu(self) -> None:
        """Populate the header dropdown with global browser options.

        Two sections:
            • "Refresh" button — re-pulls the registry (handy after a
              ``register()`` call from another tool).
            • Preset combo (Save / Rename / Delete / Open Folder built into
              the combo's actions section by ``PresetManager.wire_combo``).

        The preset manager captures and restores all browser state — text
        filter, scope, exclude, hide lists, launch options, theme, etc. —
        via the ``metadata_provider`` / ``on_metadata_loaded`` hooks, which
        means presets are portable across machines / users (no machine-
        specific paths or widget object pointers stored).

        On-top behavior is inherited from ``EditorPanel`` (always on-top);
        no toggle is exposed because the symptom that motivated one — the
        browser disappearing when the launching popup menu closed — was a
        focus-restoration bug, not an on-top problem. That bug is fixed
        in ``_EditorRegistry.show`` via a deferred re-raise.
        """
        menu = self._header.menu
        menu.setTitle("Browser Options:")

        self._btn_refresh = menu.add(
            "QPushButton",
            setText="Refresh",
            setObjectName="btn_refresh",
            setToolTip="Re-read the switchboard registry and rebuild the list.",
        )
        self._btn_refresh.clicked.connect(self._on_refresh_clicked)

        menu.add("Separator", setTitle="Presets:")

        # ``setup`` creates a ``cmb_presets`` WidgetComboBox in the menu
        # with Save / Rename / Delete / Open Folder built-in. Metadata
        # hooks pipe through our full state dict so presets carry
        # everything — not just the menu's own widgets.
        menu.presets.setup(
            preset_dir="uitk/switchboard_browser/presets",
            metadata_provider=self._export_preset_data,
            on_metadata_loaded=self._import_preset_data,
        )

    # ── Preset I/O ──────────────────────────────────────────────────────────

    def _export_preset_data(self) -> dict:
        """Serialize all browser state into a JSON-safe dict.

        Used as ``PresetManager.metadata_provider`` so the preset captures
        cross-menu state (search line edit, exclude, hide lists, launch
        options, theme, …) rather than only widgets in the header menu.
        """
        return {
            "search_text": self._search.text(),
            "exclude": self._exclude.text(),
            "scope": self._scope.currentText(),
            "show_mode": self._show.currentText(),
            "filter_enabled": self._filter_enabled,
            "active_tag_filters": sorted(self._active_tag_filters),
            "hidden_uis": sorted(self.hidden_uis),
            "hidden_tags": sorted(self.hidden_tags),
            "launch": {
                "frameless": self._cb_frameless.isChecked(),
                "on_top": self._cb_on_top.isChecked(),
                "translucent": self._cb_translucent.isChecked(),
                "restore_geometry": self._cb_restore.isChecked(),
                "theme": self._cmb_theme.currentText(),
            },
        }

    def _import_preset_data(self, data: dict) -> None:
        """Apply a loaded preset's state to all browser controls.

        Signals are blocked during application so we don't trigger a
        cascade of filter re-evaluations per widget; a single
        ``_apply_filter`` + ``_refresh_chips`` is fired at the end.
        """
        # PresetManager passes the full ``_meta`` dict (which includes
        # ``version`` and our keys). Tolerate missing keys for forward /
        # backward compat.

        # Text fields — block signals to suppress the per-keystroke
        # apply_filter that would otherwise re-fire for each setter.
        for w, val in [
            (self._search, data.get("search_text", "")),
            (self._exclude, data.get("exclude", "")),
        ]:
            w.blockSignals(True)
            try:
                w.setText(val or "")
            finally:
                w.blockSignals(False)

        # Combos
        for combo, val in [
            (self._scope, data.get("scope")),
            (self._show, data.get("show_mode")),
            (self._cmb_theme, (data.get("launch") or {}).get("theme")),
        ]:
            if val is None:
                continue
            combo.blockSignals(True)
            try:
                combo.setCurrentText(val)
            finally:
                combo.blockSignals(False)

        # Filter enabled flag — also reflect in settings
        if "filter_enabled" in data:
            self._filter_enabled = bool(data["filter_enabled"])
            self._settings.setValue("filter_enabled", self._filter_enabled)

        # Active chip filters; cleared first so the loaded set is exact.
        self._active_tag_filters = set(data.get("active_tag_filters") or [])

        # Hide lists — these go through the property setters, which
        # persist to settings.
        if "hidden_uis" in data:
            self.hidden_uis = data["hidden_uis"]
        if "hidden_tags" in data:
            self.hidden_tags = data["hidden_tags"]

        # Launch checkboxes
        launch = data.get("launch") or {}
        for key, cb in [
            ("frameless", self._cb_frameless),
            ("on_top", self._cb_on_top),
            ("translucent", self._cb_translucent),
            ("restore_geometry", self._cb_restore),
        ]:
            if key in launch:
                cb.setChecked(bool(launch[key]))

        # Persist scope/show/exclude/search since their per-widget
        # textChanged signals were blocked during the bulk apply.
        self._settings.setValue("scope", self._scope.currentText())
        self._settings.setValue("show_mode", self._show.currentText())
        self._settings.setValue("exclude", self._exclude.text())

        # Single consolidated refresh — chips, view filter, action button.
        self._update_show_ui()
        self._refresh_chips()
        self._apply_filter()
        self._update_action_button()

    # ── Header-menu slots ───────────────────────────────────────────────────

    def _on_refresh_clicked(self) -> None:
        self._model._refresh()
        self._refresh_chips()
        self._apply_filter()
        self._update_footer_status()

    # ── Footer status ───────────────────────────────────────────────────────

    def _update_footer_status(self, *_args) -> None:
        """Refresh the footer status line.

        Two display modes:
          * No row selected → counts: registered / visible / showing.
          * Row selected → selected UI's name + path, with a "● visible"
            marker when the UI is currently shown.

        Plain text (not HTML): the Footer elides via ``QFontMetrics.elidedText``
        which doesn't understand markup — feeding it HTML risks cutting a
        tag mid-stream and breaking rendering. Visual hierarchy is carried
        by middle-dot / em-dash separators instead.
        """
        try:
            footer = self.footer
        except Exception:
            return

        idx = self._view.currentIndex() if hasattr(self, "_view") else None
        name = (
            idx.data(SwitchboardBrowserModel.NameRole)
            if idx is not None and idx.isValid()
            else None
        )

        if name:
            path = idx.data(SwitchboardBrowserModel.PathRole) or ""
            visible = bool(idx.data(SwitchboardBrowserModel.VisibleRole))
            visibility_marker = "● visible — " if visible else ""
            text = f"{name} — {visibility_marker}{path}"
        else:
            registered = self._model.rowCount()
            visible_count = sum(
                1 for n in self._model._names if self._model._is_visible(n)
            )
            shown = self._proxy.rowCount()
            text = (
                f"{registered} registered · "
                f"{visible_count} visible · "
                f"showing {shown}"
            )

        footer.setStatusText(text)

    def launch_options(self) -> LaunchOptions:
        return LaunchOptions(
            frameless=self._cb_frameless.isChecked(),
            on_top=self._cb_on_top.isChecked(),
            translucent=self._cb_translucent.isChecked(),
            restore_geometry=self._cb_restore.isChecked(),
            theme=self._cmb_theme.currentText(),
        )

    # ── Slots ────────────────────────────────────────────────────────────────

    def _on_scope_changed(self, value: str) -> None:
        self._settings.setValue("scope", value)
        self._apply_filter()

    def _set_filter_enabled(self, enabled: bool) -> None:
        self._filter_enabled = bool(enabled)
        self._settings.setValue("filter_enabled", self._filter_enabled)
        self._apply_filter()

    def _on_exclude_changed(self, value: str) -> None:
        self._settings.setValue("exclude", value)
        self._apply_filter()

    def _on_show_changed(self, value: str) -> None:
        self._settings.setValue("show_mode", value)
        self._update_show_ui()
        self._apply_filter()

    def _update_show_ui(self) -> None:
        self._unhide_all_btn.setVisible(self._show.currentText() == SHOW_HIDDEN)

    def _on_unhide_all(self) -> None:
        self.hidden_uis = set()
        self.hidden_tags = set()
        self._refresh_chips()
        self._apply_filter()

    def _refresh_chips(self) -> None:
        # Clear all items (chip buttons + trailing stretch)
        while self._chip_layout.count():
            item = self._chip_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()
        self._chip_buttons.clear()
        for t in self._model.all_unique_tags():
            btn = QtWidgets.QPushButton(f"#{t}")
            btn.setCheckable(True)
            btn.setChecked(t in self._active_tag_filters)
            btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, tag=t, b=btn: self._on_chip_context_menu(tag, b, pos)
            )
            btn.toggled.connect(lambda checked, tag=t: self._on_chip_toggled(tag, checked))
            self._chip_layout.addWidget(btn)
            self._chip_buttons[t] = btn
        self._chip_layout.addStretch(1)

    def _on_chip_toggled(self, tag: str, checked: bool) -> None:
        if checked:
            self._active_tag_filters.add(tag)
        else:
            self._active_tag_filters.discard(tag)
        self._apply_filter()

    def _on_chip_context_menu(self, tag: str, btn: QtWidgets.QPushButton, pos) -> None:
        menu = QtWidgets.QMenu(self)
        if tag in self.hidden_tags:
            act = menu.addAction(f"Unhide tag #{tag}")
            act.triggered.connect(lambda: self._toggle_hide_tag(tag, hide=False))
        else:
            act = menu.addAction(f"Hide all UIs tagged #{tag}")
            act.triggered.connect(lambda: self._toggle_hide_tag(tag, hide=True))
        menu.exec_(btn.mapToGlobal(pos))

    def _toggle_hide_tag(self, tag: str, hide: bool) -> None:
        s = self.hidden_tags
        if hide:
            s.add(tag)
        else:
            s.discard(tag)
        self.hidden_tags = s
        self._apply_filter()

    def _on_row_context_menu(self, pos) -> None:
        idx = self._view.indexAt(pos)
        if not idx.isValid():
            return
        name = idx.data(SwitchboardBrowserModel.NameRole)
        tags = idx.data(SwitchboardBrowserModel.TagsRole) or []

        menu = QtWidgets.QMenu(self)
        edit_act = menu.addAction("Edit tags…")
        edit_act.triggered.connect(lambda: self._edit_tags_for(name))

        menu.addSeparator()
        if name in self.hidden_uis:
            unh = menu.addAction("Unhide this UI")
            unh.triggered.connect(lambda: self._toggle_hide_ui(name, hide=False))
        else:
            h = menu.addAction("Hide this UI")
            h.triggered.connect(lambda: self._toggle_hide_ui(name, hide=True))

        if tags:
            menu.addSeparator()
            for t in tags:
                if t in self.hidden_tags:
                    a = menu.addAction(f"Unhide tag #{t}")
                    a.triggered.connect(lambda _=False, tt=t: self._toggle_hide_tag(tt, hide=False))
                else:
                    a = menu.addAction(f"Hide by tag #{t}")
                    a.triggered.connect(lambda _=False, tt=t: self._toggle_hide_tag(tt, hide=True))

        menu.exec_(self._view.viewport().mapToGlobal(pos))

    def _toggle_hide_ui(self, name: str, hide: bool) -> None:
        s = self.hidden_uis
        if hide:
            s.add(name)
        else:
            s.discard(name)
        self.hidden_uis = s
        self._apply_filter()

    def _edit_tags_for(self, name: str) -> None:
        path = self.sb.registry.ui_registry.get(filename=name, return_field="filepath")
        if not path:
            QtWidgets.QMessageBox.warning(
                self, "Edit tags", f"No file path for '{name}'."
            )
            return
        inherited = self._model._inherited_tags_for(name)
        file_tags = set(self.sb._ui_xml_tags.get(name, set()))
        dlg = TagEditDialog(name, inherited, file_tags, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            new_tags = dlg.tags()
            try:
                self.sb.save_ui_tags(path, new_tags)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save tags failed", str(e))
                return
            self._refresh_chips()
            self._apply_filter()

    def _on_double_click(self, index) -> None:
        # Double-click on Tags column kicks off inline editing — handled by
        # the view's edit triggers; don't launch in that case.
        if index.column() == SwitchboardBrowserModel.COL_TAGS:
            return
        # Action / close columns have their own buttons; ignore double-click.
        if index.column() in (
            SwitchboardBrowserModel.COL_ACTION,
            SwitchboardBrowserModel.COL_CLOSE,
        ):
            return
        # Name column: launch / focus.
        self._on_action_clicked()

    def _on_action_clicked(self) -> None:
        idx = self._view.currentIndex()
        if not idx.isValid():
            return
        name = idx.data(SwitchboardBrowserModel.NameRole)
        if not name:
            return
        if idx.data(SwitchboardBrowserModel.VisibleRole):
            self._focus(name)
        else:
            self._launch(name)

    def _close_ui(self, name: str) -> None:
        """Hide a currently-loaded UI.

        Routes through the launched UI's own ``Header.hide_window`` when
        present — that's the same code path the launched window's own hide
        button uses, so pin / collapse / minimize state is reset cleanly
        and any header-level hide hooks (subclasses, signals) fire as if
        the user had clicked the in-window button. Falls back to a direct
        ``ui.hide()`` for UIs that don't have a uitk Header.

        ``request_hide()`` is intentionally **not** used here: it checks
        pin state and refuses to hide pinned windows or windows without
        a pin button, which is wrong for an explicit user gesture.
        """
        if name not in self.sb.loaded_ui:
            return
        try:
            ui = self.sb.loaded_ui[name]
        except Exception:
            return
        if not isinstance(ui, QtWidgets.QWidget):
            return

        header = getattr(ui, "header", None)
        if header is None or not hasattr(header, "hide_window"):
            header = (
                ui.findChild(QtWidgets.QWidget, "header")
                if hasattr(ui, "findChild")
                else None
            )
        hidden_via_header = False
        if header is not None and hasattr(header, "hide_window"):
            try:
                header.hide_window()
                hidden_via_header = True
            except Exception:
                # Fall through to the plain hide() below
                pass
        if not hidden_via_header:
            ui.hide()

        # Externally-launched UIs may not be tracked yet — calling this
        # ensures the row's visibility state refreshes even when our
        # ``on_show``/``on_hide`` listeners weren't wired up at launch.
        self._model.refresh_after_launch(name)
        self._update_action_button()

    def _launch(self, name: str) -> None:
        opts = self.launch_options()
        try:
            ui = getattr(self.sb.loaded_ui, name)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Launch failed", f"{name}: {e}")
            return

        try:
            # Parent to the switchboard's own parent (typically the host
            # DCC's main window — Maya, etc. — set by tentacle's TclMaya).
            # Mirrors MarkingMenu._init_ui: setParent(self.parent(), Qt.Window).
            sb_parent = self.sb.parent() if hasattr(self.sb, "parent") else None
            if sb_parent is not None:
                ui.setParent(sb_parent, QtCore.Qt.Window)

            ui.set_flags(
                FramelessWindowHint=opts.frameless,
                WindowStaysOnTopHint=opts.on_top,
                Tool=opts.frameless,
            )
            if opts.translucent:
                ui.set_attributes(WA_TranslucentBackground=True)

            # Apply theme + style class. Theme is user-selectable; the
            # style class is paired with the translucent flag because the
            # rounded-border look only makes sense when the BG is alpha.
            if hasattr(ui, "style"):
                try:
                    style_class = (
                        "translucentBgWithBorder" if opts.translucent else ""
                    )
                    ui.style.set(theme=opts.theme, style_class=style_class)
                except Exception:
                    pass

            # Configure the launched window's header to expose hide / collapse
            # / menu buttons (no pin — the hide button is the canonical
            # dismiss action in this UX). Only apply when the header has not
            # already been configured, mirroring UiHandler.apply_styles.
            self._configure_launched_header(ui)

            if not opts.restore_geometry and hasattr(ui, "clear_saved_geometry"):
                ui.clear_saved_geometry()
            ui.show(pos="screen")
            # Raise + activate so the launched UI ends up *above* the
            # browser within the on-top z-class. Without this the
            # browser (also on-top by default) would cover the new
            # window; recent-raise wins within a z-class so we
            # explicitly bid for top.
            ui.raise_()
            ui.activateWindow()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Launch failed", f"{name}: {e}")
            return

        self._model.refresh_after_launch(name)
        self._update_action_button()

    @staticmethod
    def _configure_launched_header(ui) -> None:
        """Add hide/collapse/menu buttons to a launched UI's header.

        Skips if the header already has buttons (a UI with a deliberate
        custom set should keep it). Falls back to ``findChild`` because
        QUiLoader-loaded widgets use dynamic subclasses, so a plain
        ``isinstance`` walk would miss them. Failure to find or configure
        a header is non-fatal — the window still launches.
        """
        header = getattr(ui, "header", None)
        if header is None or not hasattr(header, "config_buttons"):
            header = (
                ui.findChild(QtWidgets.QWidget, "header")
                if hasattr(ui, "findChild")
                else None
            )
        if header is None or not hasattr(header, "config_buttons"):
            return
        if getattr(header, "buttons", None):
            return
        try:
            header.config_buttons("menu", "collapse", "hide")
        except Exception:
            pass

    def _focus(self, name: str) -> None:
        try:
            ui = self.sb.loaded_ui[name]
        except Exception:
            return
        ui.raise_()
        ui.activateWindow()

    def _update_action_button(self, *_args) -> None:
        idx = self._view.currentIndex()
        if not idx.isValid():
            self._action_btn.setText("Launch")
            self._action_btn.setEnabled(False)
            return
        self._action_btn.setEnabled(True)
        if idx.data(SwitchboardBrowserModel.VisibleRole):
            self._action_btn.setText("Focus")
        else:
            self._action_btn.setText("Launch")

    def _on_model_data_changed(self, *_args) -> None:
        # A row's tags or visibility changed; chip set may need to add/drop
        # entries, and per-row buttons may need their enabled-state updated.
        # All deferred to coalesce bursts (registration of many UIs, rapid
        # signal volleys, etc.) into a single rebuild per event-loop turn.
        self._defer_full_refresh()
        self._update_action_button()

    def _defer_full_refresh(self, *_args) -> None:
        # Coalesce multiple updates within an event-loop turn into one
        # rebuild. Guard prevents stacking timers when many signals fire
        # back-to-back.
        if getattr(self, "_full_refresh_pending", False):
            return
        self._full_refresh_pending = True
        QtCore.QTimer.singleShot(0, self._do_full_refresh)

    def _do_full_refresh(self) -> None:
        self._full_refresh_pending = False
        self._refresh_chips()
        self._refresh_row_widgets()
        self._update_footer_status()

    def _select_first_row(self) -> None:
        if self._proxy.rowCount() == 0:
            return
        idx = self._proxy.index(0, 0)
        self._view.setCurrentIndex(idx)

    # ── Per-row icon buttons (Launch/Focus + Close) ──────────────────────────

    def _refresh_row_widgets(self) -> None:
        """(Re)install action + close icon buttons for every visible row.

        ``QTableView.setIndexWidget`` is keyed by proxy model index, but
        proxy filtering shifts the visible rows. Each refresh replaces any
        existing widgets with fresh instances — Qt deletes the old ones —
        so connections never accumulate.

        Each button is wrapped in a centered container so the cell's
        selection highlight looks clean around it (vs. a button anchored
        to the top-left of a wider cell).
        """
        if not hasattr(self, "_view"):
            return
        from uitk.widgets.mixins.icon_manager import IconManager

        for r in range(self._proxy.rowCount()):
            proxy_idx_action = self._proxy.index(r, SwitchboardBrowserModel.COL_ACTION)
            proxy_idx_close = self._proxy.index(r, SwitchboardBrowserModel.COL_CLOSE)
            name = proxy_idx_action.data(SwitchboardBrowserModel.NameRole)
            visible = bool(proxy_idx_action.data(SwitchboardBrowserModel.VisibleRole))

            # Action icons:
            #   visible → "eye" (focus the window)
            #   not visible → "open_external" (open it as its own window),
            #     which reads more clearly than a generic transport "play"
            #     for an action that pops a new top-level window.
            action_btn = self._make_icon_btn()
            IconManager.set_icon(
                action_btn,
                "eye" if visible else "open_external",
                size=(14, 14),
            )
            action_btn.setToolTip(
                f"Focus {name}" if visible else f"Launch {name}"
            )
            if visible:
                action_btn.clicked.connect(
                    lambda _=False, n=name: self._focus(n)
                )
            else:
                action_btn.clicked.connect(
                    lambda _=False, n=name: self._launch(n)
                )
            self._view.setIndexWidget(
                proxy_idx_action, self._wrap_centered(action_btn)
            )

            # Close: only enabled when the UI is currently visible
            close_btn = self._make_icon_btn()
            IconManager.set_icon(close_btn, "close", size=(12, 12))
            close_btn.setToolTip(f"Hide {name}" if visible else "")
            close_btn.setEnabled(visible)
            close_btn.clicked.connect(lambda _=False, n=name: self._close_ui(n))
            self._view.setIndexWidget(
                proxy_idx_close, self._wrap_centered(close_btn)
            )

    @staticmethod
    def _make_icon_btn() -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton()
        btn.setFlat(True)
        btn.setFocusPolicy(QtCore.Qt.NoFocus)
        btn.setFixedSize(22, 22)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        return btn

    @staticmethod
    def _wrap_centered(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(widget)
        return container

    def _apply_filter(self) -> None:
        # Filter invalidates immediately so tests/clients can read row
        # state synchronously. Row-widget rebuild (which is the expensive
        # part, ~2 buttons per visible row) is debounced via
        # ``layoutChanged`` -> ``_defer_full_refresh``.
        self._proxy.invalidate()
        self._update_action_button()

    # ── Filter predicate (called by proxy) ───────────────────────────────────

    def _row_passes_filter(self, name: str, all_tags: Set[str]) -> bool:
        # Hide-mode predicate
        mode = self._show.currentText()
        is_hidden = (name in self.hidden_uis) or bool(all_tags & self.hidden_tags)
        if mode == SHOW_VISIBLE and is_hidden:
            return False
        if mode == SHOW_HIDDEN and not is_hidden:
            return False

        # Active chip filter (AND across selected chips)
        if self._active_tag_filters and not self._active_tag_filters <= all_tags:
            return False

        # Text query — skipped entirely when the filter action is disabled.
        # Note: the exclude pattern is also part of the filter and is gated
        # by the same enable toggle, so disabling the filter shows everything
        # the hide / chip predicates allow.
        if not self._filter_enabled:
            return True

        scope = self._scope.currentText()
        if scope == SCOPE_NAME:
            haystack = name
        elif scope == SCOPE_TAGS:
            haystack = " ".join(sorted(all_tags))
        else:
            haystack = name + " " + " ".join(sorted(all_tags))

        # Bare terms get wrapped as *term* for substring matching; explicit
        # globs / character-classes pass through verbatim. Same rule applies
        # to both include and exclude patterns.
        def _to_patterns(text: str):
            terms = [t.strip() for t in text.split(",") if t.strip()]
            return [t if any(c in t for c in "*?[") else f"*{t}*" for t in terms]

        inc_patterns = _to_patterns(self._search.text().strip())
        exc_patterns = _to_patterns(self._exclude.text().strip())

        # pythontk.filter_list returns the matching subset; an empty result
        # for a single haystack means the row is filtered out.
        matches = ptk.filter_list(
            [haystack],
            inc=inc_patterns or None,
            exc=exc_patterns or None,
            ignore_case=True,
        )
        return bool(matches)


