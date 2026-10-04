# !/usr/bin/python
# coding=utf-8
"""One window over every preset in the ecosystem: browse, lock, collect, share.

The front end of :class:`pythontk.PresetLibrary`. Every tool's presets live in
their own folder under one root; this window shows them all as one tree (App ›
Tool › Mode), and adds what no single panel can:

* **Lock** -- a locked preset can't be overwritten, renamed or deleted from its
  panel (Save offers ``"<name> copy"``). A guard against accidents, not security.
* **Hide** -- a hidden preset (a shipped built-in too) leaves its panel's preset
  list but stays on disk, dimmed here; the panel keeps showing the one it is on.
  The row menu hides the selection, a tree node's menu everything under it.
* **Collections** -- a named set of presets (at most one per preset) that is
  exported as one bundle, installed by other artists, and updated in place by a
  later version of the same bundle. The collections box beside the filter both
  narrows the list and is where a collection is made (＋), renamed
  (double-click), edited, exported and deleted (☰); a preset's Collection cell
  (click it) puts that preset in, moves it between, or takes it out of one.
* **Backup / import** -- the backup is the same bundle format; an import is
  reviewed in-window (per-preset status + action) before anything is written,
  and a backup is taken first.

A host can focus the window on some packages' presets (``inc`` / ``exc``, or
:meth:`PresetEditor.set_entry_filter`) without changing what it manages.

Lazy by construction: it never imports or builds a tool. The library scans
folder markers and file names (the UI Browser's approach to ``.ui`` files), and
open panels learn about changes through :meth:`PresetManager.notify`.
"""

import time
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple, Union

from qtpy import QtCore, QtGui, QtWidgets
import pythontk as ptk

from uitk.managers.icon_manager import IconManager
from uitk.managers.preset_manager import PresetManager
from uitk.widgets.column_config import ColumnConfig
from uitk.widgets.editors.editor_panel import EditorPanel
from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter
from uitk.widgets.optionBox.options.choice import ChoiceOption
from uitk.widgets.optionBox.options.filter import NEGATE_PREFIX, FilterOption

Patterns = Union[str, List[str], None]


class _PresetFlag(NamedTuple):
    """A yes / no mark the editor's menus set on presets (lock, hide).

    Parameters:
        attr: The ``PresetEntry`` attribute that reads it.
        setter: The ``PresetLibrary`` method that writes it
            (``(entries, flag) -> count``).
        builtins: Whether a shipped built-in can carry it.
        on: The row that sets it: ``(label, tooltip)``.
        off: The row that clears it: ``(label, tooltip)``.
        done: The footer's words for each, past tense: ``(set, cleared)``.
    """

    attr: str
    setter: str
    builtins: bool
    on: Tuple[str, str]
    off: Tuple[str, str]
    done: Tuple[str, str]


class PresetEditor(EditorPanel):
    """Manage every preset store under the presets root in one window.

    Parameters:
        parent: Anchor widget (see :class:`WindowPanel`).
        library: The :class:`pythontk.PresetLibrary` to show. Defaults to one
            over the live presets root.
        inc: Focus the window on these stores -- shell-style patterns naming
            folders under the root, each taking its stores with it
            (``"mayatk"``, ``"mayatk/scene_*"``; see
            :meth:`pythontk.PresetLibrary.in_scope`).
        exc: Leave these stores out, in the same pattern form.

    A focused window lists, counts and edits only its stores. Collections are
    root-wide, so every collection is still offered (with the count of its
    presets in view), and an export or a backup still carries all of them.
    """

    #: First key segment -> the app group shown in the tree, for uitk's own
    #: stores. uitk names no host: a host registers its folder's label at
    #: startup (:meth:`register_app_label`). Anything unlabelled is title-cased
    #: from its folder name.
    APP_LABELS = {
        "uitk": "Interface",
        "workspace_templates": "Workspace",
    }

    @classmethod
    def register_app_label(cls, folder: str, label: str) -> None:
        """Show the presets under *folder* (a key's first segment) as *label*.

        A host calls this where it starts up -- ``register_app_label("mayatk",
        "Maya")`` -- so the tree names apps without uitk knowing any.
        Idempotent; the last registration for a folder wins.
        """
        cls.APP_LABELS[folder] = label

    # Description last: prose of any length, it takes the width the window has
    # to spare and grows with it, and its tooltip shows it whole. Every other
    # column is as wide as what it shows. (The header menu reorders them; the
    # spare width stays with Description wherever it is moved.)
    HEADERS = (
        "Name",
        "Collection",
        "Tags",
        "Lock",
        "Modified",
        "Tool",
        "Description",
    )
    (
        COL_NAME,
        COL_COLLECTION,
        COL_TAGS,
        COL_LOCK,
        COL_MODIFIED,
        COL_TOOL,
        COL_DESCRIPTION,
    ) = range(7)
    #: The most of a description its tooltip shows (wrapped); past it, the
    #: text is cut at a word and ends in an ellipsis.
    DESCRIPTION_TIP_CHARS = 1000
    PAGE_PRESETS, PAGE_IMPORT = 0, 1

    #: Collections-box rows that are not a collection. Never a collection id
    #: (ids are ``[a-z0-9-]``), so they persist beside the ids unambiguously.
    ALL_PRESETS = "@all"
    NO_COLLECTION = "@none"

    #: The Show list (the eye button on the filter field): every kind of
    #: preset, ticked while shown. Each section splits the presets, and a row
    #: shows while, in every section, a kind it has is ticked -- so unticking
    #: "Built-in" hides the built-ins, and unticking all but "Edited" in its
    #: section shows only those. Values start with ``@``; a tag is its own.
    SHOW_ALL = "@all"
    UNTAGGED = "@untagged"
    SHOW_SECTIONS = (
        (
            "Kind",
            (
                ("Built-in", "@builtin", "Presets shipped with a tool."),
                (
                    "Locked",
                    "@locked",
                    "Your presets protected from being saved over, renamed or deleted.",
                ),
                ("Editable", "@unlocked", "Your presets, not locked."),
            ),
        ),
        (
            "In panel lists",
            (
                ("Listed", "@listed", "Presets their panels' preset lists show."),
                (
                    "Hidden",
                    "@hidden",
                    "Presets left out of their panels' preset lists (kept on disk).",
                ),
            ),
        ),
        (
            "Since export or install",
            (
                (
                    "Edited",
                    "@edited",
                    "Collection presets whose content changed since the "
                    "collection was last exported or installed -- what a "
                    "re-export would ship, or what an update would call a "
                    "conflict.",
                ),
                (
                    "Unchanged",
                    "@unchanged",
                    "Every other preset, in a collection or not.",
                ),
            ),
        ),
    )

    #: The marks the row, tree and collection menus set and clear.
    _FLAGS = {
        "lock": _PresetFlag(
            "read_only",
            "set_read_only",
            False,
            ("Lock", "Protect them: none can be saved over, renamed or deleted."),
            ("Unlock", "Let them be saved over, renamed and deleted again."),
            ("Locked", "Unlocked"),
        ),
        "hide": _PresetFlag(
            "hidden",
            "set_hidden",
            True,
            (
                "Hide",
                "Leave them out of their panels' preset lists. Nothing is "
                "deleted, and a panel keeps showing the one it is on.",
            ),
            ("Show", "List them in their panels' preset lists again."),
            ("Hid", "Showed"),
        ),
    }

    def __init__(
        self,
        parent=None,
        library: Optional["ptk.PresetLibrary"] = None,
        inc: Patterns = None,
        exc: Patterns = None,
    ):
        super().__init__(
            title="Preset Editor",
            header_buttons=["refresh", "menu", "minimize", "hide"],
            parent=parent,
        )
        self.library = library or ptk.PresetLibrary()
        self._inc, self._exc = inc, exc
        self.resize(900, 540)
        from uitk.managers.settings_manager import SettingsManager

        # One store for the window: its geometry and every filter control, so
        # the filter text, its toggle, the facets and the collection picked
        # all come back together.
        self._settings = SettingsManager(namespace="preset_editor")
        self.persist_geometry(self._settings)

        self._entries: List[ptk.PresetEntry] = []
        self._rows: List[ptk.PresetEntry] = []
        self._collections: Dict[str, dict] = {}
        self._plan: Optional[ptk.ImportPlan] = None
        self._populating = False
        self._swallow_release = False
        self._shown = False
        #: Collection members edited since export / install, worked out once
        #: per scan (it hashes each member) and only when a filter asks.
        self._edited: Optional[set] = None
        #: ``(column, order)`` of the header's sort, or ``None`` (tool, name).
        self._sort: Optional[Tuple[int, QtCore.Qt.SortOrder]] = None

        # The views first: the filter controls re-filter the table as they
        # restore their persisted state.
        self._tree = QtWidgets.QTreeWidget()
        self._tree.setObjectName("tree_tools")
        self._tree.setHeaderHidden(True)
        self._tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self._table = self._build_table()
        self._stack = QtWidgets.QStackedWidget()
        self._stack.addWidget(self._table)
        self._stack.addWidget(self._build_import_page())

        # ── Filter row: text + facets | collections ───────────────────
        filter_row = QtWidgets.QHBoxLayout()
        self.body_layout.addLayout(filter_row)
        self._build_search(filter_row)
        self._build_collection_box(filter_row)

        # ── Tree | stacked (presets table / import review) ────────────
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 700])
        self.body_layout.addWidget(splitter, 1)
        self._tree.itemSelectionChanged.connect(self._populate_table)

        self._init_header_menu()
        self._header.refresh_requested.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build_search(self, row: QtWidgets.QHBoxLayout) -> None:
        """The filter field: text (with its on/off toggle) and the facet buttons."""
        from uitk.widgets.lineEdit import LineEdit

        self._search = LineEdit()
        self._search.setObjectName("le_search")
        self._search.setPlaceholderText("Filter (exact; * for substring; ! excludes)")
        self._search.setToolTip(
            "Filter the presets by name, description, tool, collection or tag.\n"
            "\n"
            "• Separate terms with commas — any matching term keeps the row.\n"
            "• Matching is exact (ignoring case) unless you add wildcards:\n"
            "    *  any run of characters (*web* = contains)   ?  one character\n"
            "• Prefix a term with ! to exclude it, e.g.  maya, !*test*\n"
            "• The filter icon turns the text off without clearing it; the\n"
            "  eye lists every kind of preset and tag: untick one to hide it."
        )
        row.addWidget(self._search, 1)
        box = self._search.option_box
        box.set_filter(
            settings=self._settings,
            text_key="filter.text",
            on_changed=self._populate_table,
            enabled_key="filter.enabled",
            on_toggled=lambda _on: self._populate_table(),
        )
        self._text_filter = box.find_option(FilterOption)
        self._show_filter = box.add_choice(
            icon="eye",
            label="Show",
            choices=self._show_choices,
            default=self.SHOW_ALL,
            exclude=True,  # ticked = shown; the value is what is left out
            on_changed=lambda _value: self._populate_table(),
            settings=self._settings,
            settings_key="filter.show",
        )

    def _build_collection_box(self, row: QtWidgets.QHBoxLayout) -> None:
        """The collections box: a filter that is also where collections are managed.

        Its rows are the collections (name, version, count), so the box names
        the collection its ☰ menu acts on -- a collection needs no preset in
        view to be edited, exported or deleted.
        """
        from uitk.widgets.comboBox import ComboBox

        cmb = ComboBox()
        cmb.setObjectName("cmb_collection")
        cmb.setMinimumContentsLength(16)
        cmb.setToolTip(
            "Show one collection's presets.\n"
            "＋ makes a collection; ☰ imports one, or edits, locks, exports or\n"
            "deletes the one shown; a double-click renames it."
        )
        # Only the name is the user's to rewrite; version and count are facts.
        cmb.set_cells(
            [
                {"key": "name", "label": "Name"},
                {"key": "version", "label": "Version", "editable": False},
                {"key": "count", "label": "Presets", "editable": False},
            ],
            cell_format="{name}",
        )
        row.addWidget(cmb)
        cmb.option_box.add_action(
            callback=self.prompt_new_collection,
            icon="add",
            tooltip="New collection… (the selected presets can go straight in).",
        )
        cmb.option_box.add_action(
            callback=self._show_collection_menu,
            icon="menu",
            tooltip="Import a collection, or edit, lock, export or delete the one "
            "shown.",
        )
        cmb.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        cmb.customContextMenuRequested.connect(
            lambda pos: self._show_collection_menu(cmb.mapToGlobal(pos))
        )
        cmb.currentIndexChanged.connect(self._on_collection_picked)
        cmb.on_cells_edited.connect(self._on_collection_cells_edited)
        self._cmb_collection = cmb

    def _build_table(self) -> QtWidgets.QTableWidget:
        table = QtWidgets.QTableWidget(0, len(self.HEADERS))
        table.setObjectName("tbl_presets")
        table.setHorizontalHeaderLabels(list(self.HEADERS))
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        table.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setWordWrap(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_DESCRIPTION, QtWidgets.QHeaderView.Stretch)
        # Item tooltips wrapped to a readable width, up long enough to read --
        # a description's whole text.
        TooltipPresenter.manage(table)
        # A click sorts by that column, a second reverses it. The LIST is sorted
        # (see _visible_entries), never the view: rows map to presets by
        # position, and a view sort would leave every edit on the wrong one.
        header.sectionClicked.connect(self._on_header_clicked)
        # Right-click the header to show, hide or reorder columns (Name stays),
        # kept with the window's other settings. The header itself is not
        # movable -- a click on it sorts -- so the order is dragged in the menu.
        ColumnConfig.attach(
            table,
            settings=self._settings,
            settings_key="columns",
            locked=[self.COL_NAME],
            movable=False,
            reorderable=True,
        ).restore()
        table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_context_menu)
        table.itemChanged.connect(self._on_item_changed)
        table.itemSelectionChanged.connect(self._update_status)
        # The Collection cell is a button: hovering it shows a hand, a click
        # opens its menu without disturbing a multi-row selection it is part of.
        table.viewport().setMouseTracking(True)
        table.viewport().installEventFilter(self)
        return table

    def _build_import_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._lbl_import = QtWidgets.QLabel()
        self._lbl_import.setObjectName("lbl_import")
        self._lbl_import.setWordWrap(True)
        layout.addWidget(self._lbl_import)
        self._lbl_warnings = QtWidgets.QLabel()
        self._lbl_warnings.setObjectName("lbl_import_warnings")
        self._lbl_warnings.setWordWrap(True)
        layout.addWidget(self._lbl_warnings)
        self._tbl_import = QtWidgets.QTableWidget(0, 5)
        self._tbl_import.setObjectName("tbl_import")
        self._tbl_import.setHorizontalHeaderLabels(
            ["Tool", "Preset", "Status", "Action", "Note"]
        )
        self._tbl_import.verticalHeader().setVisible(False)
        self._tbl_import.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._tbl_import.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeToContents
        )
        self._tbl_import.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._tbl_import, 1)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._btn_apply_import = QtWidgets.QPushButton("Apply")
        self._btn_apply_import.setObjectName("b_apply_import")
        self._btn_apply_import.clicked.connect(self.apply_import)
        buttons.addWidget(self._btn_apply_import)
        self._btn_cancel_import = QtWidgets.QPushButton("Cancel")
        self._btn_cancel_import.setObjectName("b_cancel_import")
        self._btn_cancel_import.clicked.connect(self.cancel_import)
        buttons.addWidget(self._btn_cancel_import)
        layout.addLayout(buttons)
        return page

    def _init_header_menu(self) -> None:
        from uitk.widgets.pushButton import PushButton
        from uitk.widgets.separator import Separator

        menu = self._header.menu
        menu.setTitle("Presets:")
        menu.hide_on_trigger = True

        def button(text, tip, slot, name):
            btn = menu.add(PushButton, setText=text, setObjectName=name, setToolTip=tip)
            btn.clicked.connect(slot)
            return btn

        menu.add(Separator, setTitle="Backup")
        button(
            "Back up all",
            "Save every preset to the backups folder.",
            self._on_backup,
            "b_backup",
        )
        button(
            "Back up to file…",
            "Save every preset to a bundle you choose.",
            self._on_backup_to_file,
            "b_backup_to_file",
        )
        button(
            "Restore from backup…",
            "Review a backup, then apply it. The presets as they are now are "
            "backed up first. (A shared collection is imported from the "
            "collections box's ☰ menu.)",
            lambda: self._on_import(backups=True),
            "b_restore",
        )
        button(
            "Open backups folder",
            "Open the folder holding backups.",
            lambda: self._open_folder(self._backups_dir),
            "b_open_backups",
        )
        menu.add(Separator, setTitle="Maintenance")
        button(
            "Open presets folder",
            "Open the folder every tool saves its presets under.",
            lambda: self._open_folder(self.library.root),
            "b_open_root",
        )
        button(
            "Clean up",
            "Remove metadata left behind by deleted presets, and empty folders.",
            self._on_clean_up,
            "b_clean_up",
        )

    def _fit_to_content(self):
        """Keep the constructor size: the tree/table split has no natural height."""

    def showEvent(self, event):
        # After the base: it applies the theme, whose icon colour the table's
        # badges are drawn in. A RE-show rescans -- the window is cached, and
        # panels save presets while it is hidden; the first show only repaints
        # what the constructor has just scanned.
        super().showEvent(event)
        if self._shown:
            self.refresh()
        else:
            self._shown = True
            self._populate_table()

    # ---------------------------------------------------------------- labels
    def _segment_label(self, index: int, segment: str) -> str:
        if index == 0 and segment in self.APP_LABELS:
            return self.APP_LABELS[segment]
        return segment.replace("_", " ").strip().title() or segment

    def _segment_labels(self, key: str) -> List[str]:
        return [self._segment_label(i, s) for i, s in enumerate(key.split("/"))]

    def tool_label(self, key: str) -> str:
        """``"mayatk/rizom_bridge/unwrap_hard"`` -> ``"Maya › Rizom Bridge › Unwrap Hard"``."""
        return " › ".join(self._segment_labels(key))

    def _collection_name(self, collection_id: Optional[str]) -> str:
        if not collection_id:
            return ""
        header = self._collections.get(collection_id)
        return header.get("name", collection_id) if header else collection_id

    # ------------------------------------------------------------------ focus
    def set_entry_filter(self, inc: Patterns = None, exc: Patterns = None) -> None:
        """Focus the window on the stores *inc* / *exc* describe (no args: all).

        The same patterns the constructor takes. A host applies it from an
        editors post-build hook so every build of the window carries it::

            sb.editors.add_post_build_hook(
                "preset_editor", lambda e: e.set_entry_filter(inc=["mayatk", "uitk"])
            )
        """
        self._inc, self._exc = inc, exc
        self.refresh()

    # ---------------------------------------------------------------- refresh
    def refresh(self) -> None:
        """Re-scan the root and rebuild the tree, collections box, facets and table."""
        self._entries = self.library.entries(inc=self._inc, exc=self._exc)
        self._collections = {c["id"]: c for c in self.library.collections()}
        self._edited = None
        self._populate_collections()
        self._populating = True  # a facet falling back re-filters once, below
        try:
            self._show_filter.refresh()
        finally:
            self._populating = False
        self._populate_tree()
        self._populate_table()

    def _populate_collections(self) -> None:
        cmb = self._cmb_collection
        current = cmb.currentData() if cmb.count() else None
        if current is None:
            current = self._settings.value("filter.collection", self.ALL_PRESETS)
        counts: Dict[Optional[str], int] = {}
        for entry in self._entries:
            counts[entry.collection] = counts.get(entry.collection, 0) + 1
        cmb.blockSignals(True)
        try:
            cmb.clear()
            cmb.addItem("All presets", self.ALL_PRESETS)
            cmb.addItem("Not in a collection", self.NO_COLLECTION)
            for cid, header in sorted(
                self._collections.items(),
                key=lambda kv: str(kv[1].get("name", "")).lower(),
            ):
                n = counts.get(cid, 0)
                version = header.get("version")
                index = cmb.add_cells(
                    {
                        "name": header.get("name", cid),
                        "version": f"v{version}" if version else "",
                        "count": f"{n} preset{'' if n == 1 else 's'}",
                    },
                    cid,
                )
                cmb.setItemData(
                    index, self._collection_tooltip(header), QtCore.Qt.ToolTipRole
                )
            index = cmb.findData(current)
            cmb.setCurrentIndex(max(index, 0))
        finally:
            cmb.blockSignals(False)
        self._sync_collection_box()

    def _collection_tooltip(self, header: dict) -> str:
        lines = [header.get("name", "")]
        if header.get("description"):
            lines.append(header["description"])
        facts = []
        if header.get("version"):
            facts.append(f"version {header['version']}")
        if header.get("author"):
            facts.append(f"by {header['author']}")
        if header.get("source"):
            facts.append(f"installed from {header['source']}")
        if facts:
            lines.append(", ".join(facts))
        return "\n".join(lines)

    def _sync_collection_box(self) -> None:
        """Persist the pick; only a collection row renames on double-click."""
        cmb = self._cmb_collection
        self._settings.setValue("filter.collection", self.collection_filter())
        cmb.rename_on_double_click = self.picked_collection() is not None

    def _populate_tree(self) -> None:
        selected = self.selected_prefix()
        counts: Dict[str, int] = {}
        for entry in self._entries:
            parts = entry.domain.split("/")
            for i in range(1, len(parts) + 1):
                prefix = "/".join(parts[:i])
                counts[prefix] = counts.get(prefix, 0) + 1
        self._tree.blockSignals(True)
        try:
            self._tree.clear()
            root_item = QtWidgets.QTreeWidgetItem(
                [f"All presets ({len(self._entries)})"]
            )
            root_item.setData(0, QtCore.Qt.UserRole, "")
            self._tree.addTopLevelItem(root_item)
            nodes: Dict[str, QtWidgets.QTreeWidgetItem] = {}
            for prefix in sorted(counts, key=lambda p: self.tool_label(p).lower()):
                parts = prefix.split("/")
                label = self._segment_label(len(parts) - 1, parts[-1])
                item = QtWidgets.QTreeWidgetItem([f"{label} ({counts[prefix]})"])
                item.setData(0, QtCore.Qt.UserRole, prefix)
                item.setToolTip(0, prefix)
                parent = nodes.get("/".join(parts[:-1]))
                if parent is None:
                    self._tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)
                nodes[prefix] = item
            self._tree.expandToDepth(0)
            target = nodes.get(selected) if selected else root_item
            (target or root_item).setSelected(True)
            self._tree.setCurrentItem(target or root_item)
        finally:
            self._tree.blockSignals(False)

    def selected_prefix(self) -> str:
        """The key prefix of the selected tree node (``""`` = all presets)."""
        items = self._tree.selectedItems()
        return items[0].data(0, QtCore.Qt.UserRole) if items else ""

    def select_prefix(self, prefix: str) -> bool:
        """Select the tree node for *prefix* (a store key or a parent of one)."""
        matches = [
            item
            for item in self._iter_tree_items()
            if item.data(0, QtCore.Qt.UserRole) == prefix
        ]
        if not matches:
            return False
        self._tree.setCurrentItem(matches[0])
        return True

    def _iter_tree_items(self):
        stack = [
            self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())
        ]
        while stack:
            item = stack.pop()
            yield item
            stack.extend(item.child(i) for i in range(item.childCount()))

    # ---------------------------------------------------------------- filters
    def _show_choices(self) -> list:
        """The Show list: every kind, then the tags in use."""
        choices = [
            (
                "Show all",
                self.SHOW_ALL,
                "Tick every row again. Untick a row to hide the presets of its "
                "kind; the list stays open for the next.",
            )
        ]
        for caption, rows in self.SHOW_SECTIONS:
            choices.append(ChoiceOption.Section(caption))
            choices.extend(rows)
        choices.append(ChoiceOption.Section("Tags"))
        choices.append(("Untagged", self.UNTAGGED, "Presets with no tag."))
        tags = sorted({t for e in self._entries for t in e.tags}, key=str.lower)
        choices.extend(tags)  # a tag is its own label
        return choices

    def _passes_show(self, entry: ptk.PresetEntry, left_out: set) -> bool:
        """Whether *entry* shows with the Show list's *left_out* unticked.

        In every section it needs a kind still ticked: its tier / lock, its
        panel-list state, its edited state, and -- any one of -- its tags.
        """
        if entry.tier == "builtin":
            kind = "@builtin"
        else:
            kind = "@locked" if entry.read_only else "@unlocked"
        if kind in left_out:
            return False
        if ("@hidden" if entry.hidden else "@listed") in left_out:
            return False
        if left_out & {"@edited", "@unchanged"}:
            edited = self._is_edited(entry)
            if ("@edited" if edited else "@unchanged") in left_out:
                return False
        return any(t not in left_out for t in entry.tags or (self.UNTAGGED,))

    def _is_edited(self, entry: ptk.PresetEntry) -> bool:
        """Whether *entry* is a collection member changed since export / install."""
        if self._edited is None:
            self._edited = {
                (e.domain, e.name)
                for e in self._entries
                if e.collection and self.library.is_modified(e)
            }
        return (entry.domain, entry.name) in self._edited

    def _passes_text(self, entry: ptk.PresetEntry, patterns) -> bool:
        fields = (
            entry.label,
            entry.name,
            entry.description,
            *self._segment_labels(entry.domain),
            self._collection_name(entry.collection),
            *entry.tags,
        )
        return bool(
            ptk.filter_list(
                [fields],
                inc=patterns,
                nested_as_unit=True,
                ignore_case=True,
                negate_prefix=NEGATE_PREFIX,
            )
        )

    def _visible_entries(self) -> List[ptk.PresetEntry]:
        prefix = self.selected_prefix()
        collection = self.collection_filter()
        left_out = set(self._show_filter.value)
        patterns = self._text_filter.patterns()
        out = []
        for entry in self._entries:
            if not self._is_under(entry.domain, prefix):
                continue
            if collection == self.NO_COLLECTION:
                if entry.collection:
                    continue
            elif collection != self.ALL_PRESETS and entry.collection != collection:
                continue
            if left_out and not self._passes_show(entry, left_out):
                continue
            if patterns and not self._passes_text(entry, patterns):
                continue
            out.append(entry)
        out.sort(key=lambda e: (self.tool_label(e.domain).lower(), e.label.lower()))
        if self._sort is not None:
            column, order = self._sort
            # Stable: rows the column ties keep the default order.
            out.sort(
                key=self._sort_key(column),
                reverse=order == QtCore.Qt.DescendingOrder,
            )
        return out

    @staticmethod
    def _is_under(domain: str, prefix: str) -> bool:
        """Whether store *domain* is under tree node *prefix* (``""``: all)."""
        return not prefix or domain == prefix or domain.startswith(prefix + "/")

    def _entries_under(self, prefix: str) -> List[ptk.PresetEntry]:
        """The presets under tree node *prefix*, whatever the filter row shows."""
        return [e for e in self._entries if self._is_under(e.domain, prefix)]

    def _cell_texts(self, entry: ptk.PresetEntry) -> Dict[int, str]:
        """What each column shows for *entry*."""
        if entry.tier == "builtin":
            lock = "Built-in"
        else:
            lock = "Locked" if entry.read_only else ""
        return {
            self.COL_NAME: entry.label,
            self.COL_DESCRIPTION: entry.description,
            self.COL_TOOL: self.tool_label(entry.domain),
            self.COL_COLLECTION: self._collection_name(entry.collection),
            self.COL_TAGS: ", ".join(entry.tags),
            self.COL_LOCK: lock,
            self.COL_MODIFIED: self._format_time(entry.modified),
        }

    def _sort_key(self, column: int):
        """The key a header sort by *column* orders the presets with.

        A name sorts naturally (``Take 2`` before ``Take 10``), the modified
        time chronologically (not as the minute it shows), any other column by
        the text it shows; all ignore case, and an empty cell comes first.
        """
        if column == self.COL_NAME:
            return lambda e: ptk.StrUtils.natural_sort_key(e.label, ignore_case=True)
        if column == self.COL_MODIFIED:
            return lambda e: (e.modified is not None, e.modified or 0.0)
        return lambda e: self._cell_texts(e)[column].casefold()

    def _on_header_clicked(self, column: int) -> None:
        """Sort the rows by *column*; the sorted column again reverses it."""
        ascending = QtCore.Qt.AscendingOrder
        order = (
            QtCore.Qt.DescendingOrder
            if self._sort == (column, ascending)
            else ascending
        )
        self._sort = (column, order)
        header = self._table.horizontalHeader()
        header.setSortIndicator(column, order)
        header.setSortIndicatorShown(True)
        self._populate_table()

    def _populate_table(self, *_args) -> None:
        if self._populating:
            return
        selected = {(e.domain, e.name) for e in self.selected_entries()}
        self._rows = self._visible_entries()
        self._populating = True
        table = self._table
        try:
            table.setRowCount(0)
            table.setRowCount(len(self._rows))
            italic = QtGui.QFont(table.font())
            italic.setItalic(True)
            badge = IconManager.get("stack", size=(12, 12))
            # A hidden preset reads as out of use: its panel no longer lists it.
            dim = QtGui.QBrush(
                table.palette().color(QtGui.QPalette.Disabled, QtGui.QPalette.Text)
            )
            # Metadata any user preset takes, locked or not (a lock guards the
            # payload); the name only while it can be renamed.
            user_columns = (self.COL_TAGS, self.COL_DESCRIPTION)
            for row, entry in enumerate(self._rows):
                editable = entry.tier == "user" and not entry.read_only
                for col, text in self._cell_texts(entry).items():
                    item = QtWidgets.QTableWidgetItem(text)
                    flags = item.flags() & ~QtCore.Qt.ItemIsEditable
                    if (col == self.COL_NAME and editable) or (
                        col in user_columns and entry.tier == "user"
                    ):
                        flags |= QtCore.Qt.ItemIsEditable
                    item.setFlags(flags)
                    if entry.tier == "builtin":
                        item.setFont(italic)
                    if entry.hidden:
                        item.setForeground(dim)
                    table.setItem(row, col, item)
                tip = str(entry.path)
                if entry.hidden:
                    tip += "\nHidden: its panel's preset list leaves it out."
                table.item(row, self.COL_NAME).setToolTip(tip)
                if entry.description:
                    # Whole, up to the cap; the presenter wraps it as it shows.
                    table.item(row, self.COL_DESCRIPTION).setToolTip(
                        self._description_tip(entry.description)
                    )
                collection_item = table.item(row, self.COL_COLLECTION)
                collection_item.setIcon(badge)
                collection_item.setToolTip(
                    "Built-in presets can't join a collection; duplicate one first."
                    if entry.tier == "builtin"
                    else "Click to put this preset in a collection, move it, "
                    "or take it out."
                )
            self._select_rows(
                r for r, e in enumerate(self._rows) if (e.domain, e.name) in selected
            )
        finally:
            self._populating = False
        self._update_status()

    @classmethod
    def _description_tip(cls, text: str) -> str:
        """*text* whole, or past :attr:`DESCRIPTION_TIP_CHARS` cut at a word
        (a single longer word at the cap) and ended with an ellipsis."""
        cap = cls.DESCRIPTION_TIP_CHARS
        if len(text) <= cap:
            return text
        head = text[:cap]
        if not text[cap].isspace():  # the cap falls inside a word: drop it
            words = head.rsplit(None, 1)
            if len(words) > 1:
                head = words[0]
        return head.rstrip() + "…"

    def _select_rows(self, rows) -> None:
        """Select whole *rows*, adding to the selection (``selectRow`` would
        replace it under ExtendedSelection)."""
        model = self._table.selectionModel()
        flags = QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows
        for row in rows:
            model.select(self._table.model().index(row, 0), flags)

    @staticmethod
    def _format_time(epoch: Optional[float]) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(epoch)) if epoch else ""

    # -------------------------------------------------------------- selection
    def selected_entries(self) -> List[ptk.PresetEntry]:
        """The presets of the selected table rows, in row order."""
        rows = sorted({i.row() for i in self._table.selectionModel().selectedRows()})
        return [self._rows[r] for r in rows if r < len(self._rows)]

    def select_entries(self, names) -> None:
        """Select the rows whose preset name is in *names* (test/automation helper)."""
        wanted = set(names)
        self._table.clearSelection()
        self._select_rows(r for r, e in enumerate(self._rows) if e.name in wanted)

    def _targets(self, row: int) -> List[ptk.PresetEntry]:
        """What a menu opened on *row* acts on: the selection when the row is in
        it, else that row alone (which becomes the selection)."""
        selected = {i.row() for i in self._table.selectionModel().selectedRows()}
        if row not in selected:
            self._table.clearSelection()
            self._select_rows([row])
        return self.selected_entries()

    def _update_status(self) -> None:
        entries = self.selected_entries()
        if len(entries) == 1:
            e = entries[0]
            self.footer.setStatusText(
                f"{e.label}  ·  {self.tool_label(e.domain)}  ·  {e.path}"
            )
            return
        if entries:
            self.footer.setStatusText(f"{len(entries)} presets selected")
            return
        tools = len({e.domain for e in self._entries})
        self.footer.setStatusText(
            f"{len(self._rows)} of {len(self._entries)} presets  ·  {tools} tools  ·  "
            f"{len(self._collections)} collections"
        )

    def _report(self, text: str, level: Optional[str] = None) -> None:
        self.footer.setStatusText(text, level)

    # ------------------------------------------------------------------ edits
    def _changed(self, keys) -> None:
        """Rescan, then refresh any open panel selector of the touched stores."""
        keys = sorted(set(keys))
        self.refresh()
        if keys:
            PresetManager.notify(keys)

    def _guarded(self, entries, action: str, run):
        """Run *run()*, an edit of *entries*; its result, or ``None`` if it can't run.

        A row goes stale when a panel -- in this process or another DCC --
        renames or deletes its preset while this window is open: the row then
        names a file that is gone, and the library raises for it (``KeyError``
        / ``FileNotFoundError``). A stale row is caught before anything is
        written, so an edit of several rows happens whole or not at all; a
        write that fails anyway (a race, a refused write: any ``OSError``) is
        caught too. Either way the list rescans, open panels with it, and the
        footer says why -- nothing raises out of the action (or, from a cell
        or a menu, out of the slot, where nobody would see it).

        Parameters:
            entries: The rows the edit acts on.
            action: What was attempted, for the footer (``"lock them"``).
            run: The edit; it never returns ``None``.

        Returns:
            What *run* returned, or ``None`` when it did not run or failed.
        """
        error = None
        if all(e.path.is_file() for e in entries):
            try:
                return run()
            except (KeyError, OSError) as exc:
                error = exc
        self._changed(e.domain for e in entries)
        if error is None or isinstance(error, (KeyError, FileNotFoundError)):
            reason = "the presets changed on disk since this list was read"
        else:
            reason = str(error)
        self._report(f"Couldn't {action}: {reason}. List refreshed.", "warning")
        return None

    def lock(self, entries=None, flag: bool = True) -> int:
        """Lock (or unlock) presets; defaults to the selection."""
        entries = self.selected_entries() if entries is None else entries
        return self._set_flag("lock", entries, flag)

    def hide_presets(self, entries=None, flag: bool = True) -> int:
        """Hide presets from their panels' preset lists, or list them again.

        Defaults to the selection; built-ins too. Nothing is deleted, and a
        panel keeps showing the preset it is on. (Not ``hide``: that is the
        window's own.)
        """
        entries = self.selected_entries() if entries is None else entries
        return self._set_flag("hide", entries, flag)

    def _set_flag(self, flag: str, entries, value: bool) -> int:
        """Set (or clear) mark *flag* (a :attr:`_FLAGS` key) on *entries*.

        Returns:
            How many presets took it (``0`` when a stale row stopped it).
        """
        spec = self._FLAGS[flag]
        targets = [e for e in entries if spec.builtins or e.tier == "user"]
        label = (spec.on if value else spec.off)[0]
        count = self._guarded(
            targets,
            f"{label.lower()} them",
            lambda: getattr(self.library, spec.setter)(targets, value),
        )
        if count is None:
            return 0
        self._changed(e.domain for e in targets)
        self._report(f"{spec.done[0 if value else 1]} {count} preset(s).")
        return count

    def duplicate(self, entry=None) -> Optional[ptk.PresetEntry]:
        """Duplicate a preset (the selection) to an unlocked user copy."""
        entry = entry or (self.selected_entries() or [None])[0]
        if entry is None:
            return None
        copy = self._guarded(
            [entry], "duplicate it", lambda: self.library.duplicate(entry)
        )
        if copy is None:
            return None
        self._changed([entry.domain])
        self.select_entries([copy.name])
        self._report(f"Duplicated as '{copy.label}'.")
        return copy

    def assign(self, collection_id: Optional[str], entries=None) -> int:
        """Put presets (the selection) into a collection, or out of any (``None``)."""
        entries = self.selected_entries() if entries is None else entries
        count = self._guarded(
            entries,
            "move them",
            lambda: self.library.assign(entries, collection_id),
        )
        if count is None:
            return 0
        self._changed(e.domain for e in entries)
        name = (
            self._collection_name(collection_id) if collection_id else "no collection"
        )
        self._report(f"Moved {count} preset(s) to {name}.")
        return count

    def delete(self, entries=None) -> int:
        """Delete presets (the selection); locked ones are skipped. Backs up first."""
        entries = self.selected_entries() if entries is None else entries
        targets = [e for e in entries if e.tier == "user" and not e.read_only]
        if not targets:
            self._report(
                "Nothing to delete: built-in and locked presets are kept.", "warning"
            )
            return 0
        backup = self.library.backup(reason="delete")
        count = self.library.delete(targets)
        self._changed(e.domain for e in targets)
        skipped = len(entries) - len(targets)
        note = f" ({skipped} read-only kept)" if skipped else ""
        where = f" Backup: {backup.name}" if backup else ""
        self._report(f"Deleted {count} preset(s){note}.{where}")
        return count

    def _on_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if self._populating or item.row() >= len(self._rows):
            return
        entry = self._rows[item.row()]
        text = item.text().strip()
        if item.column() == self.COL_NAME:
            renamed = self._guarded(
                [entry],
                f"rename it to '{text}'",
                lambda: (
                    bool(text)
                    and text != entry.label
                    and self.library.rename(entry, text)
                ),
            )
            if renamed is None:
                return
            if renamed:
                self._changed([entry.domain])
                self.select_entries([ptk.PresetStore.sanitize_preset_name(text)])
                self._report(f"Renamed to '{text}'.")
            else:
                self._report(
                    f"Couldn't rename to '{text}' (name taken or locked).", "warning"
                )
                self._populate_table()
        elif item.column() == self.COL_TAGS:
            tagged = self._guarded(
                [entry],
                "tag it",
                lambda: self.library.set_tags([entry], text.split(",")),
            )
            if tagged is not None:
                self._changed([entry.domain])
        elif item.column() == self.COL_DESCRIPTION:
            described = self._guarded(
                [entry],
                "describe it",
                lambda: self.library.set_description([entry], text),
            )
            if described is not None:
                self._changed([entry.domain])

    def _copy_contents(self, entry: ptk.PresetEntry) -> Optional[str]:
        """Copy *entry*'s file text to the clipboard; ``None`` when it is gone."""
        text = self._guarded(
            [entry], "copy it", lambda: entry.path.read_text(encoding="utf-8")
        )
        if text is not None:
            QtWidgets.QApplication.clipboard().setText(text)
        return text

    # ------------------------------------------------------------ row menu
    def build_context_menu(self):
        """The row menu for the selection, built but not shown.

        ``None`` when nothing is selected. Collection membership has its own
        menu, on the Collection cell (:meth:`build_collection_cell_menu`);
        renaming is a double-click (or F2) on the name.
        """
        from uitk.widgets.context_menu import ContextMenu

        entries = self.selected_entries()
        if not entries:
            return None
        menu = ContextMenu(parent=self._table)
        self._add_flag_rows(menu, entries, "lock")
        self._add_flag_rows(menu, entries, "hide")
        if len(entries) == 1:
            e = entries[0]
            menu.add("Duplicate", callback=lambda: self.duplicate(e))
            menu.add_separator()
            menu.add(
                "Reveal in folder", callback=lambda: self._open_folder(e.path.parent)
            )
            menu.add("Copy contents", callback=lambda: self._copy_contents(e))
        if any(e.tier == "user" and not e.read_only for e in entries):
            menu.add_separator()
            menu.add("Delete", callback=lambda: self.delete(entries))
        return menu

    def _add_flag_rows(self, menu, entries, flag: str, suffix: str = "") -> None:
        """The set and clear rows of mark *flag* (``"lock"`` / ``"hide"``) for
        *entries*: each row that would change something, so a mix offers both
        and neither way takes two clicks. *suffix* words the rows for a group
        (``" all"``)."""
        spec = self._FLAGS[flag]
        targets = [e for e in entries if spec.builtins or e.tier == "user"]
        for value, (label, tip) in ((True, spec.on), (False, spec.off)):
            if any(bool(getattr(e, spec.attr)) != value for e in targets):
                menu.add(
                    label + suffix,
                    callback=lambda v=value: self._set_flag(flag, targets, v),
                    setToolTip=tip,
                )

    def _on_context_menu(self, pos) -> None:
        index = self._table.indexAt(pos)
        if not index.isValid():
            return
        global_pos = self._table.viewport().mapToGlobal(pos)
        if index.column() == self.COL_COLLECTION:
            menu = self.build_collection_cell_menu(index.row())
        else:
            self._targets(index.row())
            menu = self.build_context_menu()
        if menu is not None:
            menu.exec_(global_pos)

    # ------------------------------------------------------------ tree menu
    def build_tree_menu(self, prefix: str):
        """A tree node's menu (*prefix*; ``""`` is the root), built but not shown.

        It acts on every preset under the node -- the ones its count counts,
        whatever the filter row shows: hide or show them, lock or unlock them
        (each row only when it would change something), open the node's
        folder, back its presets up.
        """
        from uitk.widgets.context_menu import ContextMenu

        entries = self._entries_under(prefix)
        title = self.tool_label(prefix) if prefix else "All presets"
        menu = ContextMenu(parent=self._tree)
        menu.add_separator(f"{title} ({len(entries)})")
        self._add_flag_rows(menu, entries, "hide", " all")
        self._add_flag_rows(menu, entries, "lock", " all")
        menu.add_separator()
        folder = self.library.root.joinpath(*[p for p in prefix.split("/") if p])
        menu.add(
            "Open folder",
            callback=lambda: self._open_folder(folder),
            setToolTip="Open the folder these presets are saved in.",
        )
        if any(e.tier == "user" for e in entries):
            keys = sorted({e.domain for e in entries})
            menu.add(
                "Back up these presets",
                callback=lambda: self._on_backup(keys=keys, name=f"Backup ({title})"),
                setToolTip="Save your presets here to the backups folder "
                "(built-ins ship with their tools).",
            )
        return menu

    def _on_tree_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item is None:
            return
        menu = self.build_tree_menu(item.data(0, QtCore.Qt.UserRole) or "")
        menu.exec_(self._tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------- collection cell menu
    def build_collection_cell_menu(self, row: int):
        """The Collection cell's membership menu, built but not shown.

        For *row*'s preset, or the selection it is in: add to, move between,
        take out of a collection. What a collection IS -- its name, description, bundle -- is edited from
        the collections box; this menu only moves presets in and out.
        """
        from uitk.widgets.context_menu import ContextMenu

        entries = self._targets(row)
        user = [e for e in entries if e.tier == "user"]
        menu = ContextMenu(parent=self._table)
        if not user:
            menu.add(
                "Built-in presets can't join a collection",
                setEnabled=False,
                setToolTip="Duplicate one first: the copy is yours to collect.",
            )
            return menu
        current = {e.collection for e in user}
        cid = next(iter(current)) if len(current) == 1 else None
        name = self._collection_name(cid)
        count = f"{len(user)} presets" if len(user) > 1 else user[0].label
        menu.add_separator(f"{count} · {name}" if cid else count)
        others = [
            (other, header.get("name", other))
            for other, header in sorted(
                self._collections.items(),
                key=lambda kv: str(kv[1].get("name", "")).lower(),
            )
            if current != {other}  # hidden only when every preset is in it
        ]
        if cid:
            menu.add(
                f"Show only {name}", callback=lambda: self.set_collection_filter(cid)
            )
        if others:
            flyout = menu.add("Move to" if current != {None} else "Add to")
            for other, other_name in others:
                menu.add(
                    other_name,
                    parent=flyout,
                    callback=lambda c=other: self.assign(c, user),
                )
        menu.add("New collection…", callback=lambda: self.prompt_new_collection(user))
        if current != {None}:
            menu.add_separator()
            menu.add(
                f"Remove from {name}" if cid else "Remove from its collection",
                callback=lambda: self.assign(None, user),
            )
        return menu

    def _collection_cell_clicked(self, row: int) -> None:
        self._targets(row)
        rect = self._table.visualRect(
            self._table.model().index(row, self.COL_COLLECTION)
        )
        pos = self._table.viewport().mapToGlobal(rect.bottomLeft())
        # After the click has been delivered: the menu's own loop must not run
        # inside the viewport's press handling.
        QtCore.QTimer.singleShot(0, lambda: self._show_collection_cell_menu(row, pos))

    def _show_collection_cell_menu(self, row: int, pos: QtCore.QPoint) -> None:
        if row >= len(self._rows):
            return
        menu = self.build_collection_cell_menu(row)
        if menu is not None:
            menu.exec_(pos)

    @staticmethod
    def _event_pos(event) -> QtCore.QPoint:
        position = getattr(event, "position", None)
        return position().toPoint() if callable(position) else event.pos()

    def eventFilter(self, obj, event):
        viewport = getattr(self, "_table", None)
        viewport = viewport.viewport() if viewport is not None else None
        if obj is not viewport:
            return super().eventFilter(obj, event)
        etype = event.type()
        if etype == QtCore.QEvent.MouseMove:
            over = self._table.columnAt(self._event_pos(event).x())
            if over == self.COL_COLLECTION:
                viewport.setCursor(QtCore.Qt.PointingHandCursor)
            else:
                viewport.unsetCursor()
        elif etype in (
            QtCore.QEvent.MouseButtonPress,
            QtCore.QEvent.MouseButtonDblClick,
        ):
            # A release that went elsewhere (onto the popup) must not leave the
            # next, unrelated one to be swallowed.
            self._swallow_release = False
            plain = not event.modifiers() & (
                QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier
            )
            index = self._table.indexAt(self._event_pos(event))
            if (
                event.button() == QtCore.Qt.LeftButton
                and plain
                and index.isValid()
                and index.column() == self.COL_COLLECTION
            ):
                # Consumed with its release, so the view never sees a click
                # that would collapse a multi-row selection to this one row.
                self._swallow_release = True
                if etype == QtCore.QEvent.MouseButtonPress:
                    self._collection_cell_clicked(index.row())
                return True
        elif etype == QtCore.QEvent.MouseButtonRelease and self._swallow_release:
            self._swallow_release = False
            return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------ collections
    def collection_filter(self) -> str:
        """The collections box's pick.

        A collection id, :attr:`ALL_PRESETS` or :attr:`NO_COLLECTION`.
        """
        return self._cmb_collection.currentData() or self.ALL_PRESETS

    def set_collection_filter(self, value: str) -> bool:
        """Show one collection (an id), :attr:`ALL_PRESETS` or :attr:`NO_COLLECTION`."""
        index = self._cmb_collection.findData(value)
        if index < 0:
            return False
        self._cmb_collection.setCurrentIndex(index)
        return True

    def picked_collection(self) -> Optional[str]:
        """The id of the collection the box shows, or ``None`` (all / none)."""
        value = self.collection_filter()
        return None if value in (self.ALL_PRESETS, self.NO_COLLECTION) else value

    def _on_collection_picked(self, *_args) -> None:
        self._sync_collection_box()
        self._populate_table()

    def create_collection(
        self, name: str, description: str = "", entries=None
    ) -> Optional[dict]:
        """Create collection *name* holding *entries* (user presets), and show it.

        Never left empty or part-made when a member can't move in: a stale row
        stops it before anything is written (see :meth:`_guarded`).
        """
        members = [e for e in entries or () if e.tier == "user"]
        try:
            header = self._guarded(
                members,
                "create the collection",
                lambda: self._new_collection(name, description, members),
            )
        except ValueError as e:
            self._report(f"Couldn't create it: {e}.", "warning")
            return None
        if header is None:
            return None
        self._changed(e.domain for e in members)
        self.set_collection_filter(header["id"])
        self._report(f"Created '{header['name']}' with {len(members)} preset(s).")
        return header

    def _new_collection(self, name: str, description: str, members) -> dict:
        """The header, then its *members*; a member that fails takes the header back.

        The failure is re-raised for :meth:`_guarded` to report. It is a race
        (the rows were checked just before): the rollback untags a member that
        already moved in, so one moved out of another collection stays out.
        """
        header = self.library.create_collection(name, description)
        if members:
            try:
                self.library.assign(members, header["id"])
            except (KeyError, OSError):
                self.library.delete_collection(header["id"])
                raise
        return header

    def edit_collection(self, collection_id: str, **fields) -> Optional[dict]:
        """Change a collection's ``name`` / ``description``."""
        try:
            header = self.library.update_collection(collection_id, **fields)
        except (KeyError, ValueError) as e:
            self.refresh()  # an inline rename already shows the refused name
            self._report(f"Couldn't change it: {e}.", "warning")
            return None
        self.refresh()
        self._report(f"Saved '{header['name']}'.")
        return header

    def delete_collection(
        self, collection_id: str, *, delete_members: bool = False
    ) -> Dict[str, int]:
        """Delete a collection; its presets are kept, untagged.

        With *delete_members*, presets unchanged since the collection was
        exported or installed are deleted too (a backup is taken first); ones
        edited since are kept, untagged.
        """
        members = self.library.members(collection_id)
        name = self._collection_name(collection_id)
        backup = (
            self.library.backup(reason="delete") if delete_members and members else None
        )
        counts = self.library.delete_collection(
            collection_id, delete_members=delete_members
        )
        if self.picked_collection() == collection_id:
            self.set_collection_filter(self.ALL_PRESETS)
        self._changed(e.domain for e in members)
        parts = []
        if counts["deleted"]:
            parts.append(f"{counts['deleted']} preset(s) deleted")
        if counts["untagged"]:
            parts.append(f"{counts['untagged']} kept")
        where = f" Backup: {backup.name}" if backup else ""
        self._report(
            f"Deleted {name}" + (f": {', '.join(parts)}." if parts else ".") + where
        )
        return counts

    def build_collection_menu(self):
        """The collections box's ☰ menu, built but not shown.

        *Import…* always; for the collection the box shows, edit, lock, export
        and delete.
        """
        from uitk.widgets.context_menu import ContextMenu

        menu = ContextMenu(parent=self._cmb_collection)
        menu.add(
            "Import…",
            callback=self._on_import,
            setToolTip="Review a shared collection's bundle, then install it.",
        )
        cid = self.picked_collection()
        if cid is None:
            menu.add_separator()
            menu.add(
                "Pick a collection to edit, lock, export or delete it",
                setEnabled=False,
            )
            return menu
        header = self._collections.get(cid, {})
        name = header.get("name", cid)
        version = f" · v{header['version']}" if header.get("version") else ""
        menu.add_separator(f"{name}{version}")
        menu.add("Edit…", callback=lambda: self.prompt_edit_collection(cid))
        self._add_flag_rows(menu, self.library.members(cid), "lock")
        menu.add(
            "Export…",
            callback=lambda: self._on_export_collection(cid),
            setToolTip="Save it as a bundle to share. Its version goes up by one.",
        )
        menu.add_separator()
        delete = menu.add(
            "Delete",
            callback=lambda: self.delete_collection(cid),
            setToolTip="Its presets are kept, just no longer in a collection.",
        )
        menu.add(
            "Delete with its presets",
            parent=delete,
            callback=lambda: self.delete_collection(cid, delete_members=True),
            setToolTip=(
                "Also deletes the presets unchanged since it was exported or "
                "installed; ones you edited are kept. A backup is taken first."
            ),
        )
        return menu

    def _show_collection_menu(self, pos: Optional[QtCore.QPoint] = None) -> None:
        cmb = self._cmb_collection
        if pos is None:
            pos = cmb.mapToGlobal(QtCore.QPoint(0, cmb.height()))
        self.build_collection_menu().exec_(pos)

    def _on_collection_cells_edited(self, index: int, cells: dict) -> None:
        cid = self._cmb_collection.itemData(index)
        if "name" in cells and cid not in (None, self.ALL_PRESETS, self.NO_COLLECTION):
            self.edit_collection(cid, name=cells["name"])

    def _collection_form(self, collection_id: Optional[str] = None, members=()):
        """The New / Edit collection form (a :class:`FormPanel`, not shown).

        *members* are the presets a new collection would start with; the form
        offers to add them (on by default).
        """
        from uitk.widgets.formPanel import FormPanel

        header = self._collections.get(collection_id) if collection_id else None
        fields = [
            {
                "name": "name",
                "label": "Name",
                "value": header.get("name", "") if header else "",
                "placeholder": "e.g. Studio Standard",
                "hint": "What people pick it by. Unique among your collections.",
            },
            {
                "name": "description",
                "label": "Description",
                "value": header.get("description", "") if header else "",
                "placeholder": "Optional",
                "hint": "What it is for; shown to the people who install it.",
            },
        ]
        if members:
            n = len(members)
            fields.append(
                {
                    "name": "add_selected",
                    "kind": "check",
                    "label": f"Add the {n} selected preset{'' if n == 1 else 's'}",
                    "value": True,
                    "hint": "A preset belongs to one collection at most; one "
                    "already in another moves to this one.",
                }
            )

        def validate(values) -> str:
            name = values["name"].strip()
            if not name:
                return "Name the collection."
            if self.library.collection_named(name, exclude=collection_id):
                return f"A collection named '{name}' already exists."
            return ""

        return FormPanel(
            fields,
            title=f"Edit {header.get('name', '')}" if header else "New collection",
            parent=self,
            ok_text="Save" if header else "Create",
            validate=validate,
            output=False,
        )

    def prompt_new_collection(self, members=None) -> Optional[dict]:
        """Ask for a new collection's name and description, then create it.

        *members* defaults to the selected user presets.
        """
        if members is None:
            members = [e for e in self.selected_entries() if e.tier == "user"]
        form = self._collection_form(members=members)
        try:
            if not form.exec_panel():
                return None
            values = form.values()
        finally:
            form.deleteLater()
        return self.create_collection(
            values["name"],
            values["description"],
            members if values.get("add_selected") else None,
        )

    def prompt_edit_collection(self, collection_id: str) -> Optional[dict]:
        """Ask for a collection's new name and description, then save them."""
        form = self._collection_form(collection_id)
        try:
            if not form.exec_panel():
                return None
            values = form.values()
        finally:
            form.deleteLater()
        return self.edit_collection(
            collection_id, name=values["name"], description=values["description"]
        )

    def export_collection(self, collection_id: str, path) -> Path:
        """Export collection *collection_id* as a bundle at *path*."""
        written = self.library.export(path, collection=collection_id)
        self.refresh()
        header = self.library.collection(collection_id) or {}
        self._report(
            f"Exported {header.get('name', collection_id)} v{header.get('version')} "
            f"to {written}.",
            "success",
        )
        return written

    def _on_export_collection(self, collection_id: str) -> None:
        name = self._collection_name(collection_id)
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            f"Export {name}",
            str(Path.home() / f"{name}.presets.zip"),
            "Preset bundles (*.zip)",
        )
        if path:
            self.export_collection(collection_id, path)

    # ---------------------------------------------------------------- backup
    def _on_backup(self, *, keys=None, name=None) -> None:
        """Back up to the backups folder: every preset, or the stores *keys*."""
        path = self.library.backup(keys=keys, name=name)
        if path is None:
            self._report("There are no presets to back up.", "warning")
        else:
            self._report(f"Backed up to {path}.", "success")

    def _on_backup_to_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Back up all presets",
            str(Path.home() / "presets-backup.zip"),
            "Preset bundles (*.zip)",
        )
        if not path:
            return
        written = self.library.backup(path)
        if written is None:
            self._report("There are no presets to back up.", "warning")
        else:
            self._report(f"Backed up to {written}.", "success")

    def _on_clean_up(self) -> None:
        counts = self.library.clean_up()
        self.refresh()
        self._report(
            f"Cleaned up {counts['sidecars']} stray metadata file(s) and "
            f"{counts['folders']} empty folder(s)."
        )

    @property
    def _backups_dir(self) -> Path:
        return self.library.root / ".backups"

    @staticmethod
    def _open_folder(path: Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    # ---------------------------------------------------------------- import
    def _on_import(self, backups: bool = False) -> None:
        """Pick a bundle and review it: a shared collection (the ☰ menu), or
        with *backups* a backup (the header menu; opens in the backups folder).
        The review reads the bundle, so either kind goes through either door."""
        start = self._backups_dir if backups else Path.home()
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Restore from backup" if backups else "Import a collection",
            str(start if start.is_dir() else Path.home()),
            "Preset bundles (*.zip)",
        )
        if path:
            self.import_bundle(path)

    def import_bundle(self, path) -> Optional[ptk.ImportPlan]:
        """Plan an import of bundle *path* and show it for review (writes nothing)."""
        try:
            plan = self.library.plan_import(path)
        except (ValueError, OSError) as e:
            self._report(str(e), "error")
            return None
        self._plan = plan
        header = plan.header
        kind = "Collection" if plan.kind == "collection" else "Backup"
        version = f" v{header.get('version')}" if header.get("version") else ""
        counts = ", ".join(
            f"{n} {status}" for status, n in sorted(plan.counts().items())
        )
        self._lbl_import.setText(
            f"<b>{kind}: {header.get('name') or Path(path).name}{version}</b>"
            f"<br>{counts or 'empty'}"
        )
        self._lbl_warnings.setText("<br>".join(plan.warnings))
        self._lbl_warnings.setVisible(bool(plan.warnings))

        table = self._tbl_import
        table.setRowCount(len(plan.items))
        for row, item in enumerate(plan.items):
            table.setItem(
                row, 0, QtWidgets.QTableWidgetItem(self.tool_label(item.domain))
            )
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(item.label))
            table.setItem(row, 2, QtWidgets.QTableWidgetItem(item.status))
            combo = QtWidgets.QComboBox()
            combo.addItems(list(item.choices()))
            combo.setCurrentText(item.action)
            combo.setEnabled(len(item.choices()) > 1)
            combo.currentTextChanged.connect(
                lambda text, it=item: setattr(it, "action", text)
            )
            table.setCellWidget(row, 3, combo)
            table.setItem(row, 4, QtWidgets.QTableWidgetItem(item.reason))
        self._btn_apply_import.setEnabled(bool(plan.pending()))
        self._stack.setCurrentIndex(self.PAGE_IMPORT)
        self._report(
            f"Review the import: {len(plan.pending())} change(s) will be applied."
        )
        return plan

    def apply_import(self) -> Optional[ptk.ImportResult]:
        """Apply the reviewed plan, then return to the list.

        A backup is taken first. After a collection bundle, the box shows the
        collection it installed.
        """
        plan = self._plan
        if plan is None:
            return None
        try:
            result = self.library.apply(plan)
        except (ValueError, OSError, KeyError) as e:
            self._report(f"Import failed: {e}", "error")
            return None
        self._plan = None
        self._stack.setCurrentIndex(self.PAGE_PRESETS)
        self._changed(result.domains)
        installed = plan.header.get("id") if plan.kind == "collection" else None
        if installed and self.set_collection_filter(installed):
            self.select_prefix("")  # every tool: what arrived, all of it
        done = ", ".join(
            f"{n} {action}" for action, n in sorted(result.applied.items())
        )
        where = f" Backup: {result.backup.name}" if result.backup else ""
        self._report(f"Imported: {done or 'nothing to do'}.{where}", "success")
        return result

    def cancel_import(self) -> None:
        """Leave the review without changing anything."""
        self._plan = None
        self._stack.setCurrentIndex(self.PAGE_PRESETS)
        self._report("Import cancelled; nothing changed.")
