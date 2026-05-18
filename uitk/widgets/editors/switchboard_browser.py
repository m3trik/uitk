# !/usr/bin/python
# coding=utf-8
"""Searchable, tag-filtered launcher for any handler-exposed entry.

Listed entries come from :meth:`Switchboard.iter_handler_entries`, which
unifies every launchable handler's items (e.g. .ui files from UiHandler,
registered external tools from ExternalToolHandler). Nothing is loaded
until the user clicks Launch — the browser only inspects entry metadata.

The browser itself is unregistered — a plain ``EditorPanel`` instantiated
directly by user code, consistent with ``StyleEditor`` and ``ColorMappingDialog``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Set

from qtpy import QtCore, QtGui, QtWidgets
import pythontk as ptk

# ``EditorPanel`` is the base class — must be a real import. ``Switchboard``
# is referenced at runtime only inside the no-arg ``__init__`` branch
# (lazy-imported there) and in type annotations (TYPE_CHECKING block).
# ``StyleSheet`` is reachable via ``sb.style`` at use sites — no direct
# import needed.
from uitk.compile import precompile_async
from uitk.handlers.handler_entry import HandlerEntry
from uitk.widgets.editors.editor_panel import EditorPanel
from uitk.widgets.pushButton import PushButton

if TYPE_CHECKING:  # pragma: no cover
    from uitk.switchboard import Switchboard


# ── Launch options (per-launch, not persisted per-UI) ─────────────────────────
#
# Defaults: frameless + dark theme so a browser-launched window matches
# the rest of the toolset out of the box.


@dataclass
class LaunchOptions:
    frameless: bool = True
    translucent: bool = True
    restore_geometry: bool = True
    on_top: bool = True
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
    KindRole = QtCore.Qt.UserRole + 8
    EntryRole = QtCore.Qt.UserRole + 9

    def __init__(self, switchboard: Switchboard, parent=None):
        super().__init__(parent)
        self.sb: Switchboard = switchboard
        self._entries: List[HandlerEntry] = []
        # Index for O(1) lookup by name. When two handlers register the
        # same name the later one wins (logged); see _refresh.
        self._by_name: Dict[str, HandlerEntry] = {}
        self._refresh()
        # Unified signals — fire on any handler. UiHandler-specific signals
        # are forwarded into these by the Switchboard constructor.
        self.sb.on_handler_entries_changed.connect(self._on_entries_changed)
        self.sb.on_handler_entry_changed.connect(self._on_entry_changed)

    # ---- registry → rows ----

    def _refresh(self) -> None:
        self.beginResetModel()
        entries = list(self.sb.iter_handler_entries())
        entries.sort(key=lambda e: e.name.lower())
        self._entries = entries
        seen: Dict[str, HandlerEntry] = {}
        for e in entries:
            if e.name in seen:
                # Name collision across handlers: last write wins, log once.
                self.sb.logger.warning(
                    f"[SwitchboardBrowserModel] duplicate entry name "
                    f"{e.name!r}; later handler shadows earlier."
                )
            seen[e.name] = e
        self._by_name = seen
        self.endResetModel()

    def _on_entries_changed(self, _handler_name: str) -> None:
        # Coarse: a handler's full entry set may have changed
        # (registration / unregistration). Recompute everything; cheap
        # vs. diffing two sorted lists for the row counts we deal with.
        self._refresh()

    def _on_entry_changed(self, _handler_name: str, entry_name: str) -> None:
        # Fine-grained: one entry's live state (visibility) changed.
        # File-backed entries also re-emit on save_ui_tags, so refresh
        # the entry payload (tags may have changed) before firing
        # dataChanged.
        if entry_name not in self._by_name:
            # Could be a brand-new entry — fall back to coarse refresh.
            self._refresh()
            return
        old = self._by_name[entry_name]
        # Re-pull just this entry from its owning handler.
        try:
            new = next(
                (e for e in old.handler.entries() if e.name == entry_name),
                None,
            )
        except Exception:
            new = None
        if new is None:
            # Entry vanished from its handler — full refresh handles removal.
            self._refresh()
            return
        row = self._entries.index(old)
        self._entries[row] = new
        self._by_name[entry_name] = new
        top = self.index(row, 0)
        bot = self.index(row, self.COLUMN_COUNT - 1)
        self.dataChanged.emit(top, bot)

    def refresh_after_launch(self, name: str) -> None:
        """Public hook: caller invokes this after launching to refresh the row."""
        if name in self._by_name:
            self._on_entry_changed("", name)

    # ---- QAbstractTableModel ----

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

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
        if not index.isValid() or index.row() >= len(self._entries):
            return None
        entry = self._entries[index.row()]

        # Custom roles are column-independent — always describe the row.
        if role == self.NameRole:
            return entry.name
        if role == self.EntryRole:
            return entry
        if role == self.PathRole:
            return entry.filepath
        if role == self.KindRole:
            return entry.kind
        if role == self.TagsRole:
            return sorted(entry.all_tags)
        if role == self.FileTagsRole:
            return sorted(entry.file_tags) if entry.file_tags is not None else []
        if role == self.InheritedTagsRole:
            return sorted(entry.inherited_tags)
        if role == self.LoadedRole:
            return entry.handler.is_visible(entry.name) if entry.kind == "ui_file" else False
        if role == self.VisibleRole:
            return self._is_visible(entry)

        # Display role: only Name and Tags columns produce text via the
        # delegate's HTML renderer; the action columns hold widgets.
        if role == QtCore.Qt.DisplayRole:
            if index.column() == self.COL_NAME:
                return entry.name
            # Tags column has no plain-text representation; the delegate
            # paints HTML. Returning empty string suppresses the default
            # text painter from drawing over our paint.
            return ""

        return None

    def flags(self, index):
        base = super().flags(index)
        # Tags column accepts inline editing — but only for entries whose
        # backing store supports it. Non-editable rows still render fine,
        # they just don't expose the editor delegate.
        if index.isValid() and index.column() == self.COL_TAGS:
            entry = self._entries[index.row()]
            if entry.editable_tags:
                return base | QtCore.Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid() or role != QtCore.Qt.EditRole:
            return False
        if index.column() != self.COL_TAGS:
            return False
        entry = self._entries[index.row()]
        if not entry.editable_tags:
            return False
        save_tags = getattr(entry.handler, "save_tags", None)
        if not callable(save_tags):
            return False
        # value is a comma-separated string of file tags entered by the user.
        # Strip any leading "#" — the prefix is display-only formatting
        # (added by the delegate). Users who type "#photogrammetry"
        # expect the same tag as "photogrammetry", not "##photogrammetry".
        new_tags = set()
        for t in str(value).split(","):
            stripped = t.strip().lstrip("#").strip()
            if stripped:
                new_tags.add(stripped)
        try:
            save_tags(entry.name, new_tags)
        except Exception:
            return False
        return True

    # ---- helpers ----

    def entry_for_name(self, name: str) -> Optional[HandlerEntry]:
        return self._by_name.get(name)

    # Compat shims for existing callers (mostly tests) that probed the
    # pre-handler-refactor private fields. Cheap to keep and let the
    # test bed continue to exercise behavior by name rather than entry
    # object. New code should prefer ``entry_for_name`` / ``_entries``.
    @property
    def _names(self) -> List[str]:
        return [e.name for e in self._entries]

    def _all_tags_for(self, name: str) -> Set[str]:
        entry = self._by_name.get(name)
        return set(entry.all_tags) if entry is not None else set()

    def _inherited_tags_for(self, name: str) -> Set[str]:
        entry = self._by_name.get(name)
        return set(entry.inherited_tags) if entry is not None else set()

    def _path_for(self, name: str) -> Optional[str]:
        entry = self._by_name.get(name)
        return entry.filepath if entry is not None else None

    def _is_visible(self, entry: HandlerEntry) -> bool:
        try:
            return bool(entry.handler.is_visible(entry.name))
        except Exception:
            return False

    def all_unique_tags(self) -> List[str]:
        seen: Set[str] = set()
        for entry in self._entries:
            seen |= entry.all_tags
        return sorted(seen)


# ── Row delegate ──────────────────────────────────────────────────────────────


# Color palette for the row paint, sourced from pythontk so we get the same
# desaturated pastel set used elsewhere in the ecosystem (status badges,
# diff trees, etc.) and stay consistent if those palettes are tweaked later.
_STATUS_PALETTE = ptk.Palette.status()
_UI_PALETTE = ptk.Palette.ui()
_NAME_COLOR = _UI_PALETTE["text"].hex  # neutral text
_NAME_VISIBLE_COLOR = _STATUS_PALETTE["warn"].fg.hex  # warm gold (visible)
_INHERITED_TAG_COLOR = _STATUS_PALETTE["locked"].fg.hex  # dimmed grey
_FILE_TAG_COLOR = _STATUS_PALETTE["info"].fg.hex  # soft steel-blue
_KIND_CHIP_COLOR = _STATUS_PALETTE["info"].fg.hex  # same family as file tags

# Kind chips suppress the default "ui_file" chip — it's the dominant
# population and rendering one for every row would be visual noise.
# External / future kinds get an explicit chip so users can tell rows
# apart at a glance and filter on the kind via the tag search.
_KIND_CHIP_LABELS = {
    "external_subprocess": "external",
    "external_in_process": "external:in-proc",
}


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

    Selection / hover styling comes from the global QSS
    (``QAbstractItemView::item:selected`` / ``:hover``) — the delegate
    deliberately does *not* mute ``State_Selected`` so the standard blue
    fill paints through behind the HTML chips, the same as a default
    item view would render.
    """

    _MARGIN = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = QtGui.QTextDocument()
        self._doc.setDocumentMargin(0)
        # No line wrapping in cells — long tag strings should clip
        # horizontally (and scroll on column resize), not wrap into a
        # second line that gets cropped by the 22px row height. Default
        # QTextDocument wraps at the set textWidth; turn that off here
        # once. The textWidth set in paint() still controls the painted
        # extent for clipping, just without forcing a line break.
        _opt = QtGui.QTextOption()
        _opt.setWrapMode(QtGui.QTextOption.NoWrap)
        self._doc.setDefaultTextOption(_opt)

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
        kind = index.data(SwitchboardBrowserModel.KindRole) or ""
        # "Hide inherited tags" lives on the owning browser. The delegate
        # is parented to it, so a quick parent walk reaches the toggle
        # without coupling the delegate to a Switchboard import.
        browser = self.parent()
        hide_inherited = bool(getattr(browser, "hide_inherited_tags", False))
        if hide_inherited:
            inherited = []
        chips = []
        # Kind chip first when the kind has an explicit label — lets the
        # eye anchor "what kind of thing am I looking at" before scanning
        # tags. .ui-backed entries get no chip (they're the default and
        # rendering one for every row is noise).
        kind_label = _KIND_CHIP_LABELS.get(kind)
        if kind_label:
            chips.append(
                f'<span style="color:{_KIND_CHIP_COLOR};font-weight:bold">'
                f"⟨{escape(kind_label)}⟩</span>"
            )
        # Inherited tags — italic to signal "not editable here"
        for t in sorted(inherited):
            chips.append(
                f'<span style="color:{_INHERITED_TAG_COLOR};font-style:italic">'
                f"#{escape(t)}</span>"
            )
        for t in sorted(file_tags):
            chips.append(f'<span style="color:{_FILE_TAG_COLOR}">#{escape(t)}</span>')
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
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if html is not None:
            # Suppress the default text — we draw our own HTML on top of
            # the cell background.  Leaving ``opt.text`` populated would
            # render the plain string under the HTML chips.
            opt.text = ""

        style = opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        if html is not None:
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
                f"Editing file tags only.\n" f"Inherited (not editable here): {inh_str}"
            )
        else:
            editor.setToolTip("Comma-separated tags stored in this .ui file.")

    def setModelData(self, editor, model, index):
        if index.column() != SwitchboardBrowserModel.COL_TAGS:
            return super().setModelData(editor, model, index)
        model.setData(index, editor.text(), QtCore.Qt.EditRole)

    def eventFilter(self, editor, event):
        """Make Esc always dismiss the editor (cancel without commit).

        QLineEdit in modern Qt swallows Esc to revert an undoable
        change — so a user who types and then changes their mind
        sees the text clear but the editor stays open, forcing them
        to commit-or-keep-typing. That reads as "I can't exit edit
        mode without making an entry."

        Intercept Esc here and emit ``closeEditor`` with NoHint so
        the view tears the editor down regardless of QLineEdit's
        internal undo state. Other keys (Tab, Enter, Return,
        Backtab) keep their default handling from
        QStyledItemDelegate.
        """
        if (
            isinstance(editor, QtWidgets.QLineEdit)
            and event.type() == QtCore.QEvent.KeyPress
            and event.key() == QtCore.Qt.Key_Escape
        ):
            # NoHint = cancel; commit path is via Enter/Return only.
            self.closeEditor.emit(
                editor, QtWidgets.QAbstractItemDelegate.NoHint
            )
            return True
        return super().eventFilter(editor, event)


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

# Tri-state scope cycle used by the search/exclude action buttons. The
# index into ``SCOPES`` is what gets persisted; the icon mapping signals
# the active scope at a glance — a clean uppercase "A" for text matching,
# an asterisk (the universal wildcard / "match all") for the combined
# scope, and a tag glyph for tag-only matching.
SCOPES = (SCOPE_NAME, SCOPE_BOTH, SCOPE_TAGS)
SCOPE_ICONS = {
    SCOPE_NAME: "text",
    SCOPE_BOTH: "asterisk",
    SCOPE_TAGS: "tag",
}


class _BrowserState:
    """Minimal ``state`` shim for ``Menu``'s built-in *Restore Defaults* button.

    ``Menu._restore_menu_defaults`` walks parents looking for a widget that
    exposes a ``state`` attribute with a ``reset(widget)`` method (the contract
    is normally satisfied by ``MainWindow.state`` / ``StateManager``). The
    browser is an ``EditorPanel``, not a ``MainWindow``, so without this shim
    the *Restore Defaults* button silently no-ops.

    We capture each menu widget's initial value at construction time and apply
    it back through the widget's type-appropriate setter on reset. Dispatching
    by widget type (rather than delegating to ``ValueManager.set_value``)
    avoids a known footgun: ``ValueManager`` checks ``setText`` before
    ``setChecked``, so a ``QCheckBox`` — which inherits ``setText`` from
    ``QAbstractButton`` — gets its visible label clobbered with ``"True"``
    / ``"False"`` instead of toggling its checked state.

    Calling the semantic setter (``setChecked`` / ``setCurrentText`` /
    ``setText``) also fires the widget's normal change signals, which is what
    wires the reset back into our settings + filter pipeline.
    """

    def __init__(self):
        self._defaults = {}

    def capture(self, widget, value) -> None:
        self._defaults[widget] = value

    def reset(self, widget) -> None:
        if widget not in self._defaults:
            return
        value = self._defaults[widget]
        if isinstance(widget, QtWidgets.QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QtWidgets.QComboBox):
            widget.setCurrentText(str(value))
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText("" if value is None else str(value))
        else:
            from uitk.widgets.mixins.value_manager import ValueManager

            ValueManager.set_value(widget, value)


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

        # ``refresh`` is a built-in header button that emits
        # ``refresh_requested`` — we wire it post-construction (see below)
        # to drive the same re-pull as the old menu entry, but as a
        # one-click affordance instead of a buried menu item. Matches
        # the pattern used by mayatk.reference_manager.
        # ``menu`` hosts global browser options (presets, theme, hide
        # lists, …); ``minimize`` is the standard window control.
        #
        # ``on_top=False`` matches EditorPanel's default but is kept
        # explicit at the construction site as load-bearing intent: the
        # browser is a *launcher*, not a config surface for another
        # window, and mayatk's UIs (e.g. reference_manager) parent to
        # Maya without forcing themselves above every other window.
        super().__init__(
            title="UI Browser",
            header_buttons=["refresh", "menu", "minimize", "hide"],
            parent=parent,
            on_top=False,
        )
        self.sb: Switchboard = switchboard
        self.resize(420, 560)
        # Skip EditorPanel's QTableWidget-based auto-fit; we use a QTableView
        # and manage our own size.
        self._size_initialized = True

        # Browser-owned settings (hide lists, scope, last options)
        self._settings = self.sb.settings.branch("ui_browser")

        # ``state`` is the contract a Menu's *Restore Defaults* button looks
        # for — see :class:`_BrowserState`. Made public-ish so any nested
        # Menu (option-box menus, header menu) reaches it via parent walk.
        self.state = _BrowserState()

        # Persistent filter-enabled state for each text field. Chip filters
        # and the hide list always apply; only the text-query gates flip.
        self._search_filter_enabled = bool(
            self._settings.value("search.filter_enabled", True)
        )
        self._exclude_filter_enabled = bool(
            self._settings.value("exclude.filter_enabled", True)
        )

        self._model = SwitchboardBrowserModel(self.sb, parent=self)

        # ── Search row ─────────────────────────────────────────────────
        self._search = self._build_filter_lineedit(
            object_name="le_search",
            placeholder="Search (comma-separated; supports * ?)",
            tooltip=(
                "Search the registered UI list.\n"
                "\n"
                "• Multi-term: separate terms with commas — any matching term\n"
                "  keeps the row, e.g.  alpha, beta  matches either.\n"
                "• Wildcards:\n"
                "    *      any sequence of characters\n"
                "    ?      any single character\n"
                "    [seq]  any character in the set, e.g. [abc]\n"
                "  Bare terms are wrapped as *term* (substring match).\n"
                "• Click the filter icon to toggle the filter on/off without\n"
                "  clearing the text. Click the scope icon to cycle through\n"
                "  Name / Name+Tags / Tags."
            ),
            text_settings_key="search.text",
            scope_settings_key="search.scope",
            on_text_changed=self._apply_filter,
            on_filter_toggle=self._set_search_filter_enabled,
            initial_filter_enabled=self._search_filter_enabled,
        )
        self.body_layout.addWidget(self._search)

        # ── Exclude row ────────────────────────────────────────────────
        # Mirrors the search row's controls so a user can shape both halves
        # of the filter independently (e.g. include scope = name only,
        # exclude scope = tags only).
        self._exclude = self._build_filter_lineedit(
            object_name="le_exclude",
            placeholder="Exclude (comma-separated; supports * ?)",
            tooltip=(
                "Hide rows that match any of these patterns.\n"
                "Same wildcard / multi-term syntax as the search field above.\n"
                "\n"
                "• Click the filter icon to toggle the exclude on/off.\n"
                "• Click the scope icon to choose what the patterns match\n"
                "  against (Name / Name+Tags / Tags)."
            ),
            text_settings_key="exclude.text",
            scope_settings_key="exclude.scope",
            on_text_changed=self._apply_filter,
            on_filter_toggle=self._set_exclude_filter_enabled,
            initial_filter_enabled=self._exclude_filter_enabled,
        )
        self.body_layout.addWidget(self._exclude)

        # ── Tag chips ──────────────────────────────────────────────────
        self._chip_scroll = QtWidgets.QScrollArea()
        self._chip_scroll.setWidgetResizable(True)
        self._chip_scroll.setFixedHeight(34)
        self._chip_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self._chip_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._chip_container = QtWidgets.QWidget()
        self._chip_layout = QtWidgets.QHBoxLayout(self._chip_container)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(1)
        self._chip_layout.addStretch(1)
        self._chip_scroll.setWidget(self._chip_container)
        self.body_layout.addWidget(self._chip_scroll)

        self._active_tag_filters: Set[str] = set()
        self._chip_buttons = {}  # tag -> QPushButton

        # ── Header option menu ─────────────────────────────────────────
        # Built *before* the table view because attaching a proxy via
        # ``setSourceModel`` / ``setModel`` immediately invokes the filter
        # predicate, which reads ``self._show`` (created here).
        self._init_header_menu()

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
        self._view.doubleClicked.connect(self._on_double_click)
        self._row_delegate = _BrowserRowDelegate(self)
        self._view.setItemDelegate(self._row_delegate)
        # Header configuration: name stretches, tags expand, action columns fixed
        h = self._view.horizontalHeader()
        h.setSectionResizeMode(
            SwitchboardBrowserModel.COL_NAME, QtWidgets.QHeaderView.ResizeToContents
        )
        h.setSectionResizeMode(
            SwitchboardBrowserModel.COL_TAGS, QtWidgets.QHeaderView.Stretch
        )
        h.setSectionResizeMode(
            SwitchboardBrowserModel.COL_ACTION, QtWidgets.QHeaderView.Fixed
        )
        h.setSectionResizeMode(
            SwitchboardBrowserModel.COL_CLOSE, QtWidgets.QHeaderView.Fixed
        )
        # Action columns are sized to exactly the icon button (22x22) plus
        # zero item padding, so the cell hugs the button with no dead zone
        # on either side. Padding is killed via ``QTableView::item`` QSS so
        # it doesn't reintroduce the whitespace through native styling.
        # ``setMinimumSectionSize`` is required because QHeaderView defaults
        # to a ~30px minimum that silently overrides ``setColumnWidth(22)``.
        h.setMinimumSectionSize(22)
        self._view.setColumnWidth(SwitchboardBrowserModel.COL_ACTION, 22)
        self._view.setColumnWidth(SwitchboardBrowserModel.COL_CLOSE, 22)
        # Selection / hover styling lives entirely in the global QSS
        # (uitk/widgets/mixins/style.qss).  The only per-view override the
        # browser still needs is zero item padding — the action columns
        # are exactly 22px wide and any inherited cell padding would
        # squeeze the icon buttons.
        self._view.setStyleSheet("QTableView::item { padding: 0; }")
        # Mouse tracking is required for ``QStyle::State_MouseOver`` (and
        # therefore QSS ``:hover``) to fire on cursor moves without a
        # button held — the default is off, so item hover tints silently
        # never render.
        self._view.setMouseTracking(True)
        self._view.verticalHeader().setVisible(False)
        self._view.verticalHeader().setDefaultSectionSize(22)
        self._view.setShowGrid(False)
        self.body_layout.addWidget(self._view, 1)

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
        self._view.selectionModel().currentChanged.connect(self._update_footer_status)
        self._refresh_chips()
        self._update_show_ui()
        self._apply_filter()
        self._refresh_row_widgets()
        self._select_first_row()
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

    # ── Search / Exclude line-edit factory ──────────────────────────────────

    def _build_filter_lineedit(
        self,
        *,
        object_name: str,
        placeholder: str,
        tooltip: str,
        text_settings_key: str,
        scope_settings_key: str,
        on_text_changed,
        on_filter_toggle,
        initial_filter_enabled: bool,
    ):
        """Construct a LineEdit with the filter-on/off + scope-cycle controls.

        Both the search and exclude rows share the same UX, so the construction
        is factored into a single helper. Each LineEdit gets two action buttons
        on its option-box:

            1. Filter on/off — two-state cycle (enabled / dimmed-disabled).
            2. Scope — three-state cycle (Name / Name+Tags / Tags) whose icon
               reflects the active scope at a glance.

        The option-box ``menu`` is intentionally never accessed: every option
        the user can toggle is a button, so a dropdown would only show an empty
        popup. Skipping ``.menu`` also skips the menu-button, keeping the
        right edge of the LineEdit clean.
        """
        from uitk.widgets.optionBox.options.action import ActionOption
        from uitk.widgets.optionBox.options.toggle import ToggleOption

        le = self.sb.registered_widgets.LineEdit()
        le.setObjectName(object_name)
        le.setPlaceholderText(placeholder)
        le.setToolTip(tooltip)
        saved_text = self._settings.value(text_settings_key, "") or ""
        if saved_text:
            le.setText(saved_text)

        # textChanged: drive the filter and persist verbatim text. Persisting
        # in the same lambda avoids spawning a second slot just for save.
        le.textChanged.connect(
            lambda v, k=text_settings_key: self._settings.setValue(k, v)
        )
        le.textChanged.connect(lambda _v: on_text_changed())

        # ── Filter on/off toggle ──────────────────────────────────────
        # ToggleOption owns the on/off visuals (theme-coloured icon when on,
        # error-red when off) so the user can see which control caused the
        # filter to stop. Persistence stays in self._settings (presets need
        # to see it), so settings_key=False.
        filter_toggle = ToggleOption(
            wrapped_widget=le,
            icon="filter",
            tooltip_on="Filter enabled. Click to disable.",
            tooltip_off="Filter disabled. Click to enable.",
            initial=initial_filter_enabled,
            settings_key=False,
        )
        filter_toggle.toggled.connect(on_filter_toggle)
        le.option_box.add_option(filter_toggle)

        # ── Scope tri-state action button ──────────────────────────────
        # Icon = SCOPE_ICONS[currently active scope]. Click cycles to
        # the next scope; the per-state callback writes the *new* scope
        # value before the visual state advances, so icon + active scope
        # stay in lock-step.
        saved_scope = self._settings.value(scope_settings_key, SCOPE_BOTH)
        if saved_scope not in SCOPES:
            saved_scope = SCOPE_BOTH
        scope_states = []
        for i, current in enumerate(SCOPES):
            nxt = SCOPES[(i + 1) % len(SCOPES)]
            scope_states.append(
                {
                    "icon": SCOPE_ICONS[current],
                    "tooltip": (
                        f"Scope: matches {current}. " f"Click to switch to '{nxt}'."
                    ),
                    "callback": (
                        lambda s=nxt, k=scope_settings_key: self._set_scope(k, s)
                    ),
                }
            )

        scope_action = ActionOption(
            wrapped_widget=le,
            states=scope_states,
            settings_key=False,
        )
        # Sync visible state to the persisted scope before adding so the
        # initial render shows the correct icon.
        scope_action._current_state = SCOPES.index(saved_scope)
        le.option_box.add_option(scope_action)

        # Stash references on the LineEdit so other call sites (filter
        # predicate, presets) read current values from a single source.
        le._filter_toggle = filter_toggle
        le._scope_action = scope_action
        le._scope_settings_key = scope_settings_key
        le._text_settings_key = text_settings_key

        return le

    def _set_scope(self, settings_key: str, value: str) -> None:
        """Slot called by a scope action button — persist + re-filter.

        The action button itself owns its visual cycle, so we don't touch
        ``_current_state`` here. External callers that want to *programmatically*
        change a scope (presets, tests) should use :meth:`set_search_scope`
        / :meth:`set_exclude_scope` which keep the visual state in sync.
        """
        if value not in SCOPES:
            return
        self._settings.setValue(settings_key, value)
        self._apply_filter()

    def _set_scope_external(self, le, value: str) -> None:
        """Programmatically set a LineEdit's scope, syncing the action visual."""
        if value not in SCOPES:
            return
        self._settings.setValue(le._scope_settings_key, value)
        action = getattr(le, "_scope_action", None)
        if action is not None:
            action._current_state = SCOPES.index(value)
            if action._widget is not None:
                action._apply_state()
        self._apply_filter()

    def set_search_scope(self, value: str) -> None:
        """Public helper: set the search-line-edit scope to ``value``."""
        self._set_scope_external(self._search, value)

    def set_exclude_scope(self, value: str) -> None:
        """Public helper: set the exclude-line-edit scope to ``value``."""
        self._set_scope_external(self._exclude, value)

    def _set_search_filter_enabled(self, enabled: bool) -> None:
        self._search_filter_enabled = bool(enabled)
        self._settings.setValue("search.filter_enabled", self._search_filter_enabled)
        self._apply_filter()

    def _set_exclude_filter_enabled(self, enabled: bool) -> None:
        self._exclude_filter_enabled = bool(enabled)
        self._settings.setValue("exclude.filter_enabled", self._exclude_filter_enabled)
        self._apply_filter()

    def _scope_for(self, le) -> str:
        """Read the persisted scope for a LineEdit built by ``_build_filter_lineedit``."""
        v = self._settings.value(le._scope_settings_key, SCOPE_BOTH)
        return v if v in SCOPES else SCOPE_BOTH

    # ── Header menu (Refresh + Show + Launch + Theme + Presets) ─────────────

    def _init_header_menu(self) -> None:
        """Populate the header dropdown with global browser options.

        Sections in display order:
            • "Refresh" button — re-pulls the registry.
            • "Show:" separator + show-mode combo + Unhide-All button.
            • "Launch options:" separator + frameless / restore-geometry
              checkboxes + theme combo.
            • "Presets:" separator + preset combo (Save / Rename / Delete /
              Open Folder built into the combo by ``PresetManager``).

        Defaults are captured into ``self.state`` after each widget is added,
        so the menu's built-in *Restore Defaults* button (enabled below) can
        round-trip them via :class:`_BrowserState`.

        """
        menu = self._header.menu
        menu.setTitle("Browser Options:")
        # Light-up the built-in Restore Defaults button. Without ``state`` on
        # the browser (see :class:`_BrowserState`) it would silently no-op.
        menu.add_defaults_button = True

        # Refresh is wired as a top-level header button (see
        # ``header_buttons`` in __init__) — the ``refresh_requested``
        # signal drives the same re-pull. Mirrors mayatk's reference
        # manager pattern; promotes Refresh from a buried menu entry
        # to a single-click affordance.
        self._header.refresh_requested.connect(self._on_refresh_clicked)

        # Use uitk's PushButton (not QPushButton) so the button has
        # `option_box` available for the force-compile toggle below.
        self._btn_compile_all = menu.add(
            PushButton,
            setText="Compile all",
            setObjectName="btn_compile_all",
            setToolTip=(
                "Pre-compile every registered .ui to its _ui.py.\n"
                "Stale or missing files are regenerated; up-to-date "
                "files are skipped (hash match).\n\n"
                "Toggle the option-box (refresh icon) on the right to "
                "force-recompile every file regardless of hash."
            ),
        )
        self._btn_compile_all.clicked.connect(self._on_compile_all_clicked)

        # Option-box toggle: when on (state 1), the next click force-recompiles
        # every .ui regardless of hash freshness. State 0 (off) keeps the
        # default behavior (skip files whose hash already matches). Per-state
        # callbacks flip the flag to the *will-be* value before the visual
        # advances, so flag and icon stay in lock-step.
        self._compile_force = False

        def _set_force(value: bool) -> None:
            self._compile_force = value

        self._btn_compile_all.option_box.set_action(
            states=[
                {
                    "icon": "refresh",
                    "color": "#555555",
                    "tooltip": (
                        "Force-recompile: off. Click to enable — next "
                        "'Compile all' will recompile every .ui regardless "
                        "of hash."
                    ),
                    "callback": lambda: _set_force(True),
                },
                {
                    "icon": "refresh",
                    "tooltip": (
                        "Force-recompile: on. Click to disable — next "
                        "'Compile all' will skip files whose hash already "
                        "matches."
                    ),
                    "callback": lambda: _set_force(False),
                },
            ],
            settings_key=False,  # transient: reset to off each session
        )

        self._compile_poll_timer = None

        # ── Show ──
        menu.add("Separator", setTitle="Show:")
        self._show = menu.add(
            "QComboBox",
            setObjectName="cmb_show_mode",
            setToolTip=(
                "Which UIs appear in the list:\n"
                "  visible — exclude UIs/tags from the hide lists.\n"
                "  hidden  — show only UIs/tags that are currently hidden.\n"
                "  all     — ignore the hide lists entirely."
            ),
            addItems=[SHOW_VISIBLE, SHOW_HIDDEN, SHOW_ALL],
        )
        self._show.setCurrentText(self._settings.value("show_mode", SHOW_VISIBLE))
        self._show.currentTextChanged.connect(self._on_show_changed)
        self.state.capture(self._show, SHOW_VISIBLE)

        self._unhide_all_btn = menu.add(
            "QPushButton",
            setText="Unhide all",
            setToolTip="Clear the hidden-UI and hidden-tag lists.",
        )
        self._unhide_all_btn.clicked.connect(self._on_unhide_all)

        # Hide inherited tags — those declared at registration time
        # (filename ``#tag`` suffix, source-directory tag passed to
        # ``register(tags=...)``, entry-point ``[extras]``) rather than
        # user-curated. Helps users focus on tags they've actually added.
        # Off by default to preserve current visual behavior.
        self._cb_hide_inherited_tags = menu.add(
            "QCheckBox",
            setObjectName="cb_hide_inherited_tags",
            setText="Hide inherited tags",
            setToolTip=(
                "Hide tags declared at registration time (filename "
                "suffix, source-dir tag, entry-point extras). Only "
                "user-added tags remain visible — both in row chips "
                "and in the tag chip-filter strip."
            ),
            setChecked=bool(self._settings.value("hide_inherited_tags", False)),
        )
        self._cb_hide_inherited_tags.toggled.connect(
            self._on_hide_inherited_tags_toggled
        )
        self.state.capture(self._cb_hide_inherited_tags, False)

        # ── Launch options ──
        menu.add("Separator", setTitle="Launch options:")
        self._launch_option_widgets = {}
        for key, label, default, tooltip in [
            ("frameless", "Frameless", True, "Remove window title bar."),
            (
                "translucent",
                "Translucent",
                True,
                "Use a translucent background.",
            ),
            (
                "restore_geometry",
                "Restore geometry",
                True,
                "Restore the last saved size/position.",
            ),
            (
                "on_top",
                "Always on top",
                True,
                "Keep the launched window above other windows so the on-top "
                "browser doesn't cover it.",
            ),
        ]:
            cb = menu.add(
                "QCheckBox",
                setObjectName=f"cb_launch_{key}",
                setText=label,
                setToolTip=tooltip,
                setChecked=bool(self._settings.value(f"opt_{key}", default)),
            )
            cb.toggled.connect(
                lambda v, k=key: self._settings.setValue(f"opt_{k}", bool(v))
            )
            self._launch_option_widgets[key] = cb
            self.state.capture(cb, default)
        # Backward-compatible attribute aliases used elsewhere in the class
        self._cb_frameless = self._launch_option_widgets["frameless"]
        self._cb_translucent = self._launch_option_widgets["translucent"]
        self._cb_restore = self._launch_option_widgets["restore_geometry"]
        self._cb_on_top = self._launch_option_widgets["on_top"]

        # Theme: pulled through the switchboard's ``style`` proxy so any
        # theme added to ``StyleSheet`` shows up here automatically.
        theme_names = list(self.sb.style.themes.keys()) or ["dark", "light"]
        default_theme = "dark" if "dark" in theme_names else theme_names[0]
        self._cmb_theme = menu.add(
            "QComboBox",
            setObjectName="cmb_theme",
            setToolTip="Style template applied to the launched window.",
            addItems=theme_names,
        )
        saved_theme = self._settings.value("opt_theme", default_theme)
        if saved_theme not in theme_names:
            saved_theme = default_theme
        self._cmb_theme.setCurrentText(saved_theme)
        self._cmb_theme.currentTextChanged.connect(
            lambda v: self._settings.setValue("opt_theme", v)
        )
        self.state.capture(self._cmb_theme, default_theme)

        # ── Presets ──
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
        cross-menu state (search/exclude line edits, scopes, filter toggles,
        hide lists, launch options, theme, …) rather than only widgets in
        the header menu.
        """
        return {
            "search": {
                "text": self._search.text(),
                "scope": self._scope_for(self._search),
                "filter_enabled": self._search_filter_enabled,
            },
            "exclude": {
                "text": self._exclude.text(),
                "scope": self._scope_for(self._exclude),
                "filter_enabled": self._exclude_filter_enabled,
            },
            "show_mode": self._show.currentText(),
            "active_tag_filters": sorted(self._active_tag_filters),
            "hidden_uis": sorted(self.hidden_uis),
            "hidden_tags": sorted(self.hidden_tags),
            "launch": {
                "frameless": self._cb_frameless.isChecked(),
                "translucent": self._cb_translucent.isChecked(),
                "restore_geometry": self._cb_restore.isChecked(),
                "on_top": self._cb_on_top.isChecked(),
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

        # ── Search / exclude line edits ──
        for le, section in [
            (self._search, data.get("search") or {}),
            (self._exclude, data.get("exclude") or {}),
        ]:
            text = section.get("text")
            if text is not None:
                le.blockSignals(True)
                try:
                    le.setText(text)
                finally:
                    le.blockSignals(False)
                self._settings.setValue(le._text_settings_key, text)
            scope = section.get("scope")
            if scope in SCOPES:
                self._settings.setValue(le._scope_settings_key, scope)
                action = getattr(le, "_scope_action", None)
                if action is not None:
                    action._current_state = SCOPES.index(scope)
                    if action._widget is not None:
                        action._apply_state()

        # ── Filter-enabled flags ──
        # Sync the ToggleOption visuals via set_on(..., emit=False) so the
        # restored icon state reflects the preset without re-firing the
        # toggled callback (which would write to settings again).
        if "search" in data and "filter_enabled" in data["search"]:
            self._search_filter_enabled = bool(data["search"]["filter_enabled"])
            self._settings.setValue(
                "search.filter_enabled", self._search_filter_enabled
            )
            toggle = getattr(self._search, "_filter_toggle", None)
            if toggle is not None:
                toggle.set_on(self._search_filter_enabled, emit=False)
        if "exclude" in data and "filter_enabled" in data["exclude"]:
            self._exclude_filter_enabled = bool(data["exclude"]["filter_enabled"])
            self._settings.setValue(
                "exclude.filter_enabled", self._exclude_filter_enabled
            )
            toggle = getattr(self._exclude, "_filter_toggle", None)
            if toggle is not None:
                toggle.set_on(self._exclude_filter_enabled, emit=False)

        # ── Show combo + theme combo ──
        for combo, val in [
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
        self._settings.setValue("show_mode", self._show.currentText())

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
            ("translucent", self._cb_translucent),
            ("restore_geometry", self._cb_restore),
            ("on_top", self._cb_on_top),
        ]:
            if key in launch:
                cb.setChecked(bool(launch[key]))

        # Single consolidated refresh — chips, view filter.
        self._update_show_ui()
        self._refresh_chips()
        self._apply_filter()

    # ── Header-menu slots ───────────────────────────────────────────────────

    def _on_refresh_clicked(self) -> None:
        self._model._refresh()
        self._refresh_chips()
        self._apply_filter()
        self._update_footer_status()

    def _on_compile_all_clicked(self) -> None:
        """Pre-compile registered .ui files in a background thread.

        Default: only stale/missing _ui.py files are regenerated (hash check).
        With the option-box force toggle on, every .ui is rewritten regardless
        of hash. Footer reflects progress; the button is disabled while the
        job is running.
        """
        ui_paths = [
            entry.filepath for entry in self.sb.registry.ui_registry.named_tuples
        ]
        if not ui_paths:
            self.footer.setStatusText("Compile all: no UIs registered.")
            return

        force = self._compile_force
        job = precompile_async(*ui_paths, force=force)
        if not job:
            if job.reason == "running":
                self.footer.setStatusText(
                    "Compile all: another compile is already in progress."
                )
            else:
                self.footer.setStatusText(
                    f"Compile all: nothing to do "
                    f"({len(ui_paths)} files already up-to-date — "
                    f"toggle the refresh icon to force-recompile)."
                )
            return

        import time as _time

        compile_count = job.stale
        started = _time.perf_counter()
        self._btn_compile_all.setEnabled(False)
        verb = "Force-compiling" if force else "Compiling"
        if force:
            self.footer.setStatusText(f"{verb} {compile_count} UIs…")
        else:
            self.footer.setStatusText(
                f"{verb} {compile_count} of {len(ui_paths)} UIs…"
            )

        # Poll the worker thread without blocking the Qt event loop.
        # QTimer is the idiomatic choice; it stays on the GUI thread so
        # updating widgets is safe.
        timer = QtCore.QTimer(self)
        timer.setInterval(150)
        self._compile_poll_timer = timer

        def _check() -> None:
            if job.is_alive():
                return
            elapsed = _time.perf_counter() - started
            timer.stop()
            self._compile_poll_timer = None
            self._btn_compile_all.setEnabled(True)
            # Refresh — tags/metadata may have shifted during compile. Refresh
            # schedules a deferred ``_update_footer_status`` via QTimer.
            # singleShot(0) on dataChanged, so we must queue our final status
            # *after* that deferred update or it gets clobbered.
            self._on_refresh_clicked()
            done_verb = "force-recompiled" if force else "compiled"
            done_msg = (
                f"Compile all: done — {done_verb} {compile_count} "
                f"of {len(ui_paths)} UIs in {elapsed:.2f}s."
            )
            QtCore.QTimer.singleShot(
                0,
                lambda: self.footer.setStatusText(done_msg),
            )

        timer.timeout.connect(_check)
        timer.start()

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
                1 for e in self._model._entries if self._model._is_visible(e)
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
            translucent=self._cb_translucent.isChecked(),
            restore_geometry=self._cb_restore.isChecked(),
            on_top=self._cb_on_top.isChecked(),
            theme=self._cmb_theme.currentText(),
        )

    # ── Slots ────────────────────────────────────────────────────────────────

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

    def _on_hide_inherited_tags_toggled(self, checked: bool) -> None:
        self._settings.setValue("hide_inherited_tags", bool(checked))
        # Repaint rows (tag chips re-render) and refresh chip strip.
        if hasattr(self, "_view") and self._view.model() is not None:
            top = self._model.index(0, 0)
            bot = self._model.index(
                self._model.rowCount() - 1, self._model.COLUMN_COUNT - 1
            )
            if top.isValid() and bot.isValid():
                self._model.dataChanged.emit(top, bot)
        self._refresh_chips()

    @property
    def hide_inherited_tags(self) -> bool:
        return bool(self._settings.value("hide_inherited_tags", False))

    def _visible_tags(self) -> List[str]:
        """Tags from currently visible (post-filter) rows.

        Active tag filters are forcibly included so the user can always toggle
        them off — otherwise an active chip with no remaining matches would
        vanish from the strip and become un-removable.

        Honors the "Hide inherited tags" toggle — those tags are dropped
        from the chip strip but remain in the underlying row data
        (so filters set programmatically still work).
        """
        seen: Set[str] = set(self._active_tag_filters)
        hide_inherited = self.hide_inherited_tags
        for r in range(self._proxy.rowCount()):
            idx = self._proxy.index(r, 0)
            if hide_inherited:
                # Only user-added file tags surface in the chip strip.
                tags = idx.data(SwitchboardBrowserModel.FileTagsRole) or []
            else:
                tags = idx.data(SwitchboardBrowserModel.TagsRole) or []
            seen.update(tags)
        return sorted(seen)

    def _refresh_chips(self) -> None:
        # Clear all items (chip buttons + trailing stretch)
        while self._chip_layout.count():
            item = self._chip_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()
        self._chip_buttons.clear()
        # Chips reflect the currently visible rows so the user only sees
        # tags that are useful to refine the current view further. Active
        # filters are always included via :meth:`_visible_tags`.
        for t in self._visible_tags():
            btn = QtWidgets.QPushButton(f"#{t}")
            btn.setCheckable(True)
            btn.setChecked(t in self._active_tag_filters)
            btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, tag=t, b=btn: self._on_chip_context_menu(tag, b, pos)
            )
            btn.toggled.connect(
                lambda checked, tag=t: self._on_chip_toggled(tag, checked)
            )
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
        # Tag editing happens inline — double-click the Tags cell, or
        # pick this entry to open the same inline editor programmatically.
        # No modal popup: the QLineEdit delegate is the single edit path.
        tags_idx = self._proxy.index(idx.row(), SwitchboardBrowserModel.COL_TAGS)
        if self._model.flags(self._proxy.mapToSource(tags_idx)) & QtCore.Qt.ItemIsEditable:
            edit_act = menu.addAction("Edit tags")
            edit_act.triggered.connect(
                lambda _=False, i=tags_idx: self._view.edit(i)
            )
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
                    a.triggered.connect(
                        lambda _=False, tt=t: self._toggle_hide_tag(tt, hide=False)
                    )
                else:
                    a = menu.addAction(f"Hide by tag #{t}")
                    a.triggered.connect(
                        lambda _=False, tt=t: self._toggle_hide_tag(tt, hide=True)
                    )

        menu.exec_(self._view.viewport().mapToGlobal(pos))

    def _toggle_hide_ui(self, name: str, hide: bool) -> None:
        s = self.hidden_uis
        if hide:
            s.add(name)
        else:
            s.discard(name)
        self.hidden_uis = s
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
        """Dismiss the entry via its owning handler.

        The handler decides what "close" means — hide a window, terminate
        a subprocess, etc. Browser stays kind-agnostic.
        """
        entry = self._model.entry_for_name(name)
        if entry is None:
            return
        try:
            entry.handler.close(name)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Close failed", f"{name}: {e}")
            return
        self._model.refresh_after_launch(name)

    def _launch(self, name: str) -> None:
        """Launch the entry through its owning handler.

        Browser passes the current launch options (frameless/translucent/
        restore_geometry/on_top/theme) as **kwargs; handlers that don't
        care about UI styling discard the unknown keys.
        """
        entry = self._model.entry_for_name(name)
        if entry is None:
            return
        opts = self.launch_options()
        try:
            entry.handler.launch(
                name,
                frameless=opts.frameless,
                translucent=opts.translucent,
                restore_geometry=opts.restore_geometry,
                on_top=opts.on_top,
                theme=opts.theme,
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Launch failed", f"{name}: {e}")
            return
        self._model.refresh_after_launch(name)

    def _focus(self, name: str) -> None:
        """Raise a currently-visible entry. UI-file entries support this;
        external tools generally don't (we'd need a window handle), so we
        no-op gracefully when the handler can't raise.
        """
        entry = self._model.entry_for_name(name)
        if entry is None:
            return
        # Only ui_file entries have a loaded_ui peek path with raise_().
        if entry.kind != "ui_file":
            return
        try:
            ui = self.sb.loaded_ui[name]
        except Exception:
            return
        ui.raise_()
        ui.activateWindow()

    def _on_model_data_changed(self, *_args) -> None:
        # A row's tags or visibility changed; chip set may need to add/drop
        # entries, and per-row buttons may need their enabled-state updated.
        # All deferred to coalesce bursts (registration of many UIs, rapid
        # signal volleys, etc.) into a single rebuild per event-loop turn.
        self._defer_full_refresh()

    def _defer_full_refresh(self, *_args) -> None:
        # Coalesce multiple updates within an event-loop turn into one
        # rebuild. Guard prevents stacking timers when many signals fire
        # back-to-back.
        #
        # When the browser is hidden, the work is invisible — but the
        # full refresh chain (re-pull entries, recreate every row's
        # buttons via setIndexWidget) is expensive enough to be felt
        # across the host app. Mark dirty + bail; showEvent does one
        # consolidated refresh when the user next opens us.
        if not self.isVisible():
            self._dirty_while_hidden = True
            return
        if getattr(self, "_full_refresh_pending", False):
            return
        self._full_refresh_pending = True
        QtCore.QTimer.singleShot(0, self._do_full_refresh)

    def _do_full_refresh(self) -> None:
        self._full_refresh_pending = False
        self._refresh_chips()
        self._refresh_row_widgets()
        self._update_footer_status()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # While hidden the model might have processed entries-changed
        # signals without triggering row rebuilds (see ``_defer_full_refresh``).
        # Bring the view fully up to date on show.
        if getattr(self, "_dirty_while_hidden", False):
            self._dirty_while_hidden = False
            self._do_full_refresh()

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
            action_btn.setToolTip(f"Focus {name}" if visible else f"Launch {name}")
            if visible:
                action_btn.clicked.connect(lambda _=False, n=name: self._focus(n))
            else:
                action_btn.clicked.connect(lambda _=False, n=name: self._launch(n))
            self._view.setIndexWidget(proxy_idx_action, self._wrap_centered(action_btn))

            # Close: only enabled when the UI is currently visible
            close_btn = self._make_icon_btn()
            IconManager.set_icon(close_btn, "close", size=(12, 12))
            close_btn.setToolTip(f"Hide {name}" if visible else "")
            close_btn.setEnabled(visible)
            close_btn.clicked.connect(lambda _=False, n=name: self._close_ui(n))
            self._view.setIndexWidget(proxy_idx_close, self._wrap_centered(close_btn))

    def _make_icon_btn(self) -> QtWidgets.QPushButton:
        # Delegates to EditorPanel.icon_button (shared template). Slightly
        # smaller (22 vs the 24 default) to match this table's row height.
        return self.icon_button(size=22)

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

    # ── Filter predicate (called by proxy) ───────────────────────────────────

    @staticmethod
    def _haystack(name: str, all_tags: Set[str], scope: str) -> str:
        if scope == SCOPE_NAME:
            return name
        if scope == SCOPE_TAGS:
            return " ".join(sorted(all_tags))
        return name + " " + " ".join(sorted(all_tags))

    @staticmethod
    def _to_patterns(text: str):
        # Bare terms become ``*term*`` (substring match); terms that already
        # carry a glob / character-class pass through verbatim. Applied to
        # both include and exclude patterns.
        terms = [t.strip() for t in text.split(",") if t.strip()]
        return [t if any(c in t for c in "*?[") else f"*{t}*" for t in terms]

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

        # Search (include) — gated by its own filter-enabled toggle.
        if self._search_filter_enabled:
            inc_text = self._search.text().strip()
            if inc_text:
                inc_patterns = self._to_patterns(inc_text)
                inc_haystack = self._haystack(
                    name, all_tags, self._scope_for(self._search)
                )
                if not ptk.filter_list(
                    [inc_haystack], inc=inc_patterns, ignore_case=True
                ):
                    return False

        # Exclude — independent toggle and scope so the user can, e.g.,
        # search by name but exclude by tag.
        if self._exclude_filter_enabled:
            exc_text = self._exclude.text().strip()
            if exc_text:
                exc_patterns = self._to_patterns(exc_text)
                exc_haystack = self._haystack(
                    name, all_tags, self._scope_for(self._exclude)
                )
                if not ptk.filter_list(
                    [exc_haystack], exc=exc_patterns, ignore_case=True
                ):
                    return False

        return True
