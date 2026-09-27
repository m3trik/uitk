# !/usr/bin/python
# coding=utf-8
"""The browser's table model: one row per handler-exposed entry, nothing loaded."""

from __future__ import annotations

from typing import Dict, List, Optional, Set, TYPE_CHECKING, Union

import pythontk as ptk
from qtpy import QtCore

from uitk.handlers.handler_entry import HandlerEntry

if TYPE_CHECKING:  # pragma: no cover
    from uitk.switchboard import Switchboard


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

    def __init__(
        self,
        switchboard: Switchboard,
        parent=None,
        inc: Union[str, List[str], None] = None,
        exc: Union[str, List[str], None] = None,
    ):
        super().__init__(parent)
        self.sb: Switchboard = switchboard
        # Structural entry filter (``pythontk.filter_list`` shell-style
        # patterns). Unlike the user-curated hide lists, filtered entries
        # are never materialised into the model at all — absent from
        # counts, chips, presets, and the entry-changed signal path.
        self._inc = inc
        self._exc = exc
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
        if self._inc or self._exc:
            allowed = set(
                ptk.filter_list(
                    [e.name for e in entries],
                    inc=self._inc,
                    exc=self._exc,
                    ignore_case=True,
                )
            )
            entries = [e for e in entries if e.name in allowed]
        entries.sort(key=lambda e: e.name.lower())
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
        # One row per name (last-write-wins) so rows stay consistent with the
        # entry_for_name dispatch used by launch/close/focus — a shadowed
        # duplicate no longer renders a ghost row that misroutes to the other
        # handler. Dict preserves insertion order, so rows stay sorted by name.
        self._entries = list(seen.values())
        self.endResetModel()

    def _on_entries_changed(self, _handler_name: str) -> None:
        # Coarse: a handler's full entry set may have changed
        # (registration / unregistration). Recompute everything; cheap
        # vs. diffing two sorted lists for the row counts we deal with.
        self._refresh()

    def _on_entry_changed(self, _handler_name: str, entry_name: str) -> None:
        # Structurally-excluded entries never reach the model — bail before
        # the unknown-name fallback below coarse-refreshes on every signal.
        # This is load-bearing for hosts that exclude marking-menu pages:
        # those pages emit show/hide traffic on every gesture, and a full
        # model reset per signal makes the menu sluggish while a browser
        # instance exists.
        if not self._passes_entry_filter(entry_name):
            return
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
            return (
                entry.handler.is_visible(entry.name)
                if entry.kind == "ui_file"
                else False
            )
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

    def _passes_entry_filter(self, name: str) -> bool:
        """True when *name* survives the structural inc/exc entry filter."""
        if not (self._inc or self._exc):
            return True
        return bool(
            ptk.filter_list([name], inc=self._inc, exc=self._exc, ignore_case=True)
        )

    def set_entry_filter(
        self,
        inc: Union[str, List[str], None] = None,
        exc: Union[str, List[str], None] = None,
    ) -> None:
        """Replace the structural inc/exc entry filter and re-pull the registry."""
        self._inc = inc
        self._exc = exc
        self._refresh()

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
