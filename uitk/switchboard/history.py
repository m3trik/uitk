# !/usr/bin/python
# coding=utf-8
"""Ordered, capped history with optional weak storage and key-based filtering.

Backs both :attr:`Switchboard.ui_history` (weak ``QWidget`` refs) and
:attr:`Switchboard.slot_history` (strong callables). Previously these were two
hand-rolled lists with *divergent* capping (UI capped at the write site with a
hard-coded 200; slots capped at the read site via a ``length`` arg) and the UI
list pinned closed windows in memory with strong refs — defeating the weakref
design of ``loaded_ui``. This unifies the append/cap/dedup/filter mechanics in
one place and lets the UI history hold weak refs so a closed UI is freed.
"""
import weakref
import pythontk as ptk


class History:
    """An ordered list of items with a cap, de-duplication, and filtering.

    De-duplication is by item *identity* (most recent occurrence wins, order
    preserved) — matching the prior behaviour of both histories. The ``key``
    callable is used only for ``inc``/``exc`` filtering (UI: ``objectName``,
    slot: ``__name__``).

    Parameters:
        maxlen (int|None): Cap on stored entries; oldest are dropped on add.
            ``None`` disables the cap.
        key (callable|None): ``item -> str`` mapper used by ``inc``/``exc``
            filtering. When ``None``, filtering is skipped.
        weak (bool): Store weak references. Dead referents are pruned lazily on
            every read. Use for ``QWidget`` items so history never keeps a
            closed window alive.
        filter_unmapped (bool): Forwarded as ``check_unmapped`` to
            ``ptk.filter_list`` (slot history sets this True).
    """

    def __init__(self, *, maxlen=200, key=None, weak=False, filter_unmapped=False):
        self._items = []  # list of items, or of weakref.ref when weak
        self._key = key
        self._weak = weak
        self._filter_unmapped = filter_unmapped
        self.maxlen = maxlen  # property setter trims immediately

    @property
    def maxlen(self):
        return self._maxlen

    @maxlen.setter
    def maxlen(self, value):
        # Setting the cap trims immediately (not just on the next add), so
        # slot_history(length=N) keeps its legacy "truncate now" behaviour.
        self._maxlen = value
        self._cap()

    # ── storage helpers ──────────────────────────────────────────────
    def _wrap(self, item):
        return weakref.ref(item) if self._weak else item

    def _alive(self):
        """Return live items in order, pruning dead weak refs in place."""
        if not self._weak:
            return list(self._items)
        live, kept = [], []
        for ref in self._items:
            obj = ref()
            if obj is not None:
                live.append(obj)
                kept.append(ref)
        self._items = kept
        return live

    def _cap(self):
        if self.maxlen is not None and len(self._items) > self.maxlen:
            del self._items[: -self.maxlen]

    # ── mutation ─────────────────────────────────────────────────────
    def add(self, items):
        """Append one or more items (iterables are flattened), then cap."""
        for it in ptk.make_iterable(items):
            self._items.append(self._wrap(it))
        self._cap()

    def remove(self, items):
        """Remove every occurrence of each given item (by equality)."""
        targets = list(ptk.make_iterable(items))
        if self._weak:
            self._items = [r for r in self._items if r() not in targets]
        else:
            self._items = [x for x in self._items if x not in targets]

    def clear(self):
        self._items = []

    # ── views ────────────────────────────────────────────────────────
    def _dedup(self, items):
        # Most-recent occurrence wins, original order preserved.
        return list(dict.fromkeys(items[::-1]))[::-1]

    def view(self, *, allow_duplicates=False, inc=None, exc=None):
        """Return a filtered list view of the live items (non-mutating)."""
        items = self._alive()
        if not allow_duplicates:
            items = self._dedup(items)
        if (inc or exc) and self._key is not None:
            items = ptk.filter_list(
                items, inc, exc, self._key, check_unmapped=self._filter_unmapped
            )
        return items

    def get(self, index=None, *, allow_duplicates=False, inc=None, exc=None):
        """Return the item(s) at ``index`` (int or slice), or the whole view.

        Mirrors the legacy out-of-range contract: an int index returns ``[]``
        and a slice returns ``None`` when the resolved view can't be indexed.
        """
        items = self.view(allow_duplicates=allow_duplicates, inc=inc, exc=exc)
        if index is None:
            return items
        try:
            return items[index]
        except IndexError:
            return [] if isinstance(index, int) else None

    def __len__(self):
        return len(self._alive())

    def __iter__(self):
        return iter(self._alive())
