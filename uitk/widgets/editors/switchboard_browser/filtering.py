# !/usr/bin/python
# coding=utf-8
"""Which rows the browser lists: the show modes, the search scopes, the proxy."""

from __future__ import annotations

from qtpy import QtCore

from .model import SwitchboardBrowserModel


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


SHOW_VISIBLE = "visible"
SHOW_HIDDEN = "hidden"
SHOW_ALL = "all"

SCOPE_NAME = "name"
SCOPE_TAGS = "tags"
SCOPE_BOTH = "name + tags"

# Tri-state scope cycle used by the search field's scope action button. The
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
