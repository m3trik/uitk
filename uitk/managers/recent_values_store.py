# !/usr/bin/python
# coding=utf-8
"""Widget-free *recent values* model — the shared source of truth for value history.

Where :class:`SettingsManager` persists arbitrary key/value settings, a
:class:`RecentValuesStore` manages one ordered, deduped, most-recent-first list
of values with optional persistence, validity filtering and display formatting.

It deliberately imports no *widget* (only ``QSettings`` via
:class:`SettingsManager` for persistence), so the same model can back multiple
presenters — e.g. ``RecentValuesOption`` (the option-box gear popup composes a
store) and tentacle's main Workspace list (renders ``valid_values`` /
``display_map`` directly).

This mirrors the ecosystem's ``PresetStore`` split (one Qt-free model, several
front-ends) so "recent values" stops being a popup-only feature.

Beside the history it keeps **pins**: values the user chose to keep, each
optionally named (:class:`PinnedValueEntry`). Pins never age out of the history
and hold none of its slots, so ``RecentValuesOption`` (history + pins) and
``PinValuesOption`` (pins only, ``max_recent=0``) are one model configured two
ways.
"""

import os
from typing import Callable, List, Optional

import pythontk as ptk


class RecentValueEntry:
    """A recent value whose restore-data differs from its display string.

    Most history entries are plain values (the value *is* what's shown and
    restored). An entry is used only when a presenter needs to show one thing
    while restoring another — e.g. a line edit that displays texture-set names
    but carries the full ``os.pathsep``-joined file paths as ``data``.

    Dedup/normalization key off :attr:`data`, so an entry compares equal to the
    plain value it would restore, as :class:`PinnedValueEntry` does.
    """

    __slots__ = ("data", "display")

    def __init__(self, data, display=None):
        self.data = data
        self.display = display

    def __eq__(self, other):
        if isinstance(other, RecentValueEntry):
            return RecentValuesStore.normalize_value(
                self.data
            ) == RecentValuesStore.normalize_value(other.data)
        return RecentValuesStore.normalize_value(
            self.data
        ) == RecentValuesStore.normalize_value(other)

    def __hash__(self):
        n = RecentValuesStore.normalize_value(self.data)
        return hash(n if isinstance(n, str) else str(n))

    def __repr__(self):
        return f"RecentValueEntry(data={self.data!r}, display={self.display!r})"


class PinnedValueEntry:
    """A pinned value and the alias the user named it by, if any.

    *value* is what a restore writes back (a plain value or a
    :class:`RecentValueEntry`); *alias* is a label for the popup alone, so a
    naming rule like ``{scene:_bar.*->}_v{n:03d}`` can read as "Strip _bar,
    versioned" and still restore the rule itself. Equality keys off the value,
    never the alias.
    """

    __slots__ = ("value", "alias")

    def __init__(self, value, alias=None):
        self.value = value
        self.alias = alias or None

    @property
    def display_text(self) -> str:
        """The alias when set, else the value's text."""
        return self.alias or str(RecentValuesStore._entry_data(self.value))

    def __eq__(self, other):
        if isinstance(other, PinnedValueEntry):
            other = other.value
        return RecentValuesStore.normalize_value(
            self.value
        ) == RecentValuesStore.normalize_value(other)

    def __hash__(self):
        n = RecentValuesStore.normalize_value(self.value)
        return hash(n if isinstance(n, str) else str(n))

    def __repr__(self):
        return f"PinnedValueEntry(value={self.value!r}, alias={self.alias!r})"


class RecentValuesStore:
    """Ordered, deduped, most-recent-first value history.

    Qt-light: persistence is delegated to :class:`SettingsManager` (QSettings),
    never to a widget. Mutations notify subscribers so any number of presenters
    stay in sync.

    Parameters:
        settings_key: Namespace for persistent storage. When given (and no
            explicit *settings*), a :class:`SettingsManager` is created under
            ``org="uitk", app="RecentValues"`` — the same location the legacy
            ``RecentValuesOption`` used, so existing history is preserved.
            Used **verbatim**: this store is widget-free by design, so it cannot
            reach a Switchboard to host-namespace the key the way the option-box
            plugins do (see ``_persistence.PersistedOption.settings_for``).
            A DCC-hosted caller building a store directly therefore owns that
            distinction itself — either pass a host-distinct *settings_key*, or
            hand in a *settings* manager built by that factory. ``RecentValuesOption``
            takes the second route, so a widget-wrapped history is namespaced.
        max_recent: Maximum number of unpinned entries to keep. A pinned
            value rides free, so :attr:`values` can hold more than this.
        display_format: How values render in :meth:`display_map`:
            ``"auto"`` — strip the common directory prefix when all values are
            filesystem paths, else truncate; ``"truncate"`` — middle-truncate;
            ``"basename"`` — last path component; or a ``callable(value) -> str``.
        validator: Optional ``callable(value) -> bool``. Drives
            :meth:`valid_values` (filtered view) and :meth:`prune_invalid`
            (destructive cleanup). When ``None`` every value is considered valid.
        settings: An existing :class:`SettingsManager` to persist into (DI hook
            for tests and for sharing one backing store). Overrides
            *settings_key* for the backing store; *settings_key* is then unused.
        max_pinned: Maximum number of pins; pinning past it drops the oldest
            pin. ``None`` (default) keeps every pin.
    """

    MAX_DISPLAY_LENGTH = 120
    #: Settings keys: the history, and the pins with their aliases.
    RECENT_KEY = "entries"
    PINNED_KEY = "pinned"

    @staticmethod
    def _is_filesystem_path(value) -> bool:
        """Return True if *value* is an absolute filesystem path."""
        s = str(value)
        # Drive (C: / C:\ / C:/), UNC (\\server) or absolute unix (/home). A
        # colon after one letter alone is no drive: "v:{n}" is a token.
        if len(s) >= 2 and s[0].isalpha() and s[1] == ":":
            if len(s) == 2 or s[2] in "/\\":
                return True
        if s.startswith("//") or s.startswith("\\\\"):
            return True
        if s.startswith("/"):
            return True
        return False

    @staticmethod
    def _build_display_map_smart_path(values) -> Optional[dict]:
        """Build a display map by stripping the common directory prefix.

        Only engages when *all* values look like filesystem paths and there
        are at least two of them.  Returns ``None`` (use default truncation)
        otherwise.
        """
        str_values = [str(v) for v in values]
        if len(str_values) < 2 or not all(
            RecentValuesStore._is_filesystem_path(v) for v in str_values
        ):
            return None

        normalized = [ptk.format_path(v) for v in str_values]
        try:
            prefix = os.path.commonpath(normalized)
        except ValueError:
            return None

        if not prefix:
            return None

        display_map = {}
        for raw, norm in zip(values, normalized):
            tail = norm[len(prefix) :].lstrip("/")
            display_map[raw] = f"…/{tail}" if tail else str(raw)
        return display_map

    @staticmethod
    def _entry_data(value):
        """The restore-data of *value* (its ``.data`` when an entry, else itself)."""
        return value.data if isinstance(value, RecentValueEntry) else value

    @staticmethod
    def _entry_display(value):
        """The explicit display of *value*, or ``None`` to derive one."""
        return value.display if isinstance(value, RecentValueEntry) else None

    @staticmethod
    def normalize_value(value):
        """Normalize a value for comparison.

        Unwraps a :class:`RecentValueEntry` to its data, strips whitespace and,
        for absolute filesystem paths, normalizes separators -- and, on Windows,
        case -- so that ``C:/Dir`` and ``c:\\dir`` compare equal there. A Linux
        filesystem is case-sensitive: ``/proj/Shot`` and ``/proj/shot`` are two
        folders, and folding them would drop one from the list.

        Anything else compares verbatim, slashes and all: ``{scene:\\d+->}``
        and ``{scene:\\D+->}`` are different rules, and folding them as a path
        would make recording one evict the other. A relative path is ambiguous
        with such text, so it is compared verbatim too -- a near-duplicate row
        costs less than a lost value.
        """
        if isinstance(value, RecentValueEntry):
            value = value.data
        if isinstance(value, str):
            value = value.strip()
            if RecentValuesStore._is_filesystem_path(value):
                value = ptk.format_path(value)
                if os.name == "nt":
                    value = value.lower()
        return value

    @staticmethod
    def _is_blank(value) -> bool:
        """Whether *value* has no data worth keeping (``None`` or whitespace)."""
        data = RecentValuesStore._entry_data(value)
        return data is None or not str(data).strip()

    def __init__(
        self,
        settings_key: Optional[str] = None,
        max_recent: int = 10,
        display_format="auto",
        validator: Optional[Callable[[object], bool]] = None,
        settings=None,
        max_pinned: Optional[int] = None,
    ):
        self._values: List = []
        self._pinned: List[PinnedValueEntry] = []
        self._settings_key = settings_key
        self._max_recent = max_recent
        self._max_pinned = max_pinned
        self._display_format = display_format
        self._validator = validator
        self._subscribers: List[Callable[[], None]] = []
        self._settings = settings

        if self._settings is None and settings_key:
            self._init_settings()
        if self._settings is not None:
            self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _init_settings(self):
        from uitk.managers.settings_manager import SettingsManager

        self._settings = SettingsManager(
            org="uitk", app="RecentValues", namespace=self._settings_key
        )

    @staticmethod
    def _serialize(value):
        """Plain values persist as-is; entries persist as a tagged dict."""
        if isinstance(value, RecentValueEntry):
            return {
                "__recent_entry__": True,
                "data": value.data,
                "display": value.display,
            }
        return value

    @staticmethod
    def _deserialize(value):
        """Rehydrate a tagged dict back into a :class:`RecentValueEntry`."""
        if isinstance(value, dict) and value.get("__recent_entry__"):
            return RecentValueEntry(value.get("data"), value.get("display"))
        return value

    @staticmethod
    def _is_pin_record(value) -> bool:
        """Whether a stored item is a pin: ``{"value": ..., "alias": ...}``."""
        return (
            isinstance(value, dict)
            and "value" in value
            and not value.get("__recent_entry__")
        )

    def _read_list(self, key) -> list:
        data = self._settings.value(key, []) or []
        return list(data) if isinstance(data, (list, tuple)) else [data]

    def _save(self):
        if not self._settings:
            return
        self._settings.setValue(
            self.RECENT_KEY, [self._serialize(v) for v in self._values]
        )
        self._settings.setValue(
            self.PINNED_KEY,
            [
                {"value": self._serialize(e.value), "alias": e.alias}
                for e in self._pinned
            ],
        )
        self._settings.sync()

    def _load(self):
        if not self._settings:
            return
        # Pins that PinValuesOption stored before the two plugins shared this
        # model sit under the history's key; they load as pins and are saved
        # back under PINNED_KEY.
        recent, legacy_pins = [], []
        for v in self._read_list(self.RECENT_KEY):
            (legacy_pins if self._is_pin_record(v) else recent).append(v)
        records = [
            r for r in self._read_list(self.PINNED_KEY) if self._is_pin_record(r)
        ]
        # Deduplicate on load (keep first occurrence = most recent).
        seen = set()
        deduped = []
        for v in recent:
            v = self._deserialize(v)
            if RecentValuesStore._entry_data(v) is None:
                continue
            n = RecentValuesStore.normalize_value(v)
            if n not in seen:
                seen.add(n)
                deduped.append(v)
        self._values = deduped

        seen = set()
        self._pinned = []
        for r in records + legacy_pins:
            value = self._deserialize(r.get("value"))
            if self._is_blank(value):
                continue
            n = RecentValuesStore.normalize_value(value)
            if n not in seen:
                seen.add(n)
                self._pinned.append(PinnedValueEntry(value, r.get("alias")))

    # ------------------------------------------------------------------
    # Observer
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[], None]) -> None:
        """Register *callback* to be invoked (no args) after any mutation."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[], None]) -> None:
        """Remove a previously-registered *callback* (no-op if absent)."""
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass

    def _notify(self):
        for cb in list(self._subscribers):
            try:
                cb()
            except Exception:
                # A misbehaving presenter must not break the model or the
                # other subscribers.
                pass

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @property
    def values(self) -> List:
        """A copy of the full history (most-recent first, raw values)."""
        return list(self._values)

    def is_valid(self, value) -> bool:
        """Whether *value* passes the configured validator (True if none)."""
        if self._validator is None:
            return True
        try:
            return bool(self._validator(value))
        except Exception:
            return False

    def valid_values(self) -> List:
        """History filtered to entries passing the validator (non-destructive)."""
        return [v for v in self._values if self.is_valid(v)]

    @property
    def pinned(self) -> List:
        """A copy of the pinned values (newest pin first, raw values)."""
        return [e.value for e in self._pinned]

    @property
    def pinned_entries(self) -> List[PinnedValueEntry]:
        """The pins with their aliases (newest pin first)."""
        return list(self._pinned)

    def pinned_entry(self, value) -> Optional[PinnedValueEntry]:
        """The pin holding *value*, or ``None`` when it is not pinned."""
        n = RecentValuesStore.normalize_value(value)
        for entry in self._pinned:
            if RecentValuesStore.normalize_value(entry.value) == n:
                return entry
        return None

    def is_pinned(self, value) -> bool:
        """Whether *value* is pinned."""
        return self.pinned_entry(value) is not None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def _trim(self):
        """Keep at most ``max_recent`` unpinned values, dropping the oldest.

        A pinned value rides free: it is shown with the pins, so letting it
        hold a history slot would shrink the history the user sees. Kept in
        the list all the same, so an unpin returns it to its place.
        """
        kept, unpinned = [], 0
        for v in self._values:
            if self.is_pinned(v):
                kept.append(v)
            elif unpinned < self._max_recent:
                kept.append(v)
                unpinned += 1
        self._values = kept

    def record(self, value) -> None:
        """Insert *value* at the front (most-recent), dedup, trim, persist."""
        if self._is_blank(value):
            return
        n = RecentValuesStore.normalize_value(value)
        self._values = [
            v for v in self._values if RecentValuesStore.normalize_value(v) != n
        ]
        self._values.insert(0, value)
        self._trim()
        self._save()
        self._notify()

    def add(self, value) -> None:
        """Seed *value* (append if new); preserves existing order.

        Use for programmatic seeding (e.g. importing a host app's recent
        list). Unlike :meth:`record` it does not move an existing entry to
        the front. Seeding into a full store drops from the tail (the
        oldest), never the user's most recent entries.
        """
        if self._is_blank(value):
            return
        n = RecentValuesStore.normalize_value(value)
        if any(RecentValuesStore.normalize_value(v) == n for v in self._values):
            return
        self._values.append(value)
        self._trim()
        self._save()
        self._notify()

    @staticmethod
    def _clean_alias(value, alias) -> Optional[str]:
        """*alias* stripped; ``None`` when blank or the value's own text."""
        alias = (alias or "").strip()
        if not alias or alias == str(RecentValuesStore._entry_data(value)).strip():
            return None
        return alias

    def pin(self, value, alias: Optional[str] = None) -> bool:
        """Pin *value* (newest first), optionally naming it.

        Returns:
            Whether *value* is pinned now -- ``False`` for a blank or
            already-pinned value, or with ``max_pinned=0``. Past
            ``max_pinned`` the oldest pin is dropped (into the history).
        """
        if self._is_blank(value) or self.is_pinned(value):
            return False
        self._pinned.insert(0, PinnedValueEntry(value, self._clean_alias(value, alias)))
        if self._max_pinned is not None:
            del self._pinned[self._max_pinned :]
            self._trim()  # a dropped pin counts against the history again
        self._save()
        self._notify()
        return self.is_pinned(value)

    def unpin(self, value) -> bool:
        """Unpin *value*; it moves to the front of the history.

        So a stray click is one click to undo -- even for a pin whose history
        entry aged past ``max_recent`` while the pin kept it. A store keeping
        no history (``max_recent=0``) drops the value.

        Returns:
            Whether a pin was removed.
        """
        entry = self.pinned_entry(value)
        if entry is None:
            return False
        self._pinned = [e for e in self._pinned if e is not entry]
        n = RecentValuesStore.normalize_value(entry.value)
        self._values = [
            v for v in self._values if RecentValuesStore.normalize_value(v) != n
        ]
        self._values.insert(0, entry.value)
        self._trim()
        self._save()
        self._notify()
        return True

    def set_alias(self, value, alias: Optional[str]) -> bool:
        """Name the pin holding *value*; a blank or verbatim *alias* clears it.

        Returns:
            Whether the alias changed (``False`` when *value* is not pinned).
        """
        entry = self.pinned_entry(value)
        if entry is None:
            return False
        alias = self._clean_alias(entry.value, alias)
        if alias == entry.alias:
            return False
        entry.alias = alias
        self._save()
        self._notify()
        return True

    def clear_pinned(self) -> None:
        """Drop every pin (the history is untouched)."""
        if not self._pinned:
            return
        self._pinned.clear()
        self._save()
        self._notify()

    def remove(self, value) -> None:
        """Remove *value* from the history (no-op if absent)."""
        n = RecentValuesStore.normalize_value(value)
        before = len(self._values)
        self._values = [
            v for v in self._values if RecentValuesStore.normalize_value(v) != n
        ]
        if len(self._values) != before:
            self._save()
            self._notify()

    def clear(self) -> None:
        """Drop all history. Pins stay: they were chosen, not collected."""
        if not self._values:
            return
        self._values.clear()
        self._save()
        self._notify()

    def prune_invalid(self) -> List:
        """Drop every entry failing the validator; return the removed values.

        No-op (returns ``[]``) when no validator is configured.
        """
        if self._validator is None:
            return []
        removed = [v for v in self._values if not self.is_valid(v)]
        if removed:
            self._values = [v for v in self._values if self.is_valid(v)]
            self._save()
            self._notify()
        return removed

    # ------------------------------------------------------------------
    # Display formatting
    # ------------------------------------------------------------------

    def display_map(self, values=None) -> dict:
        """Return ``{raw_value: display_string}`` for *values*.

        Defaults to the current history. Unlike the historical option-box
        helper this always returns full display strings (never an empty
        "let the popup truncate" sentinel), so non-popup presenters can use
        the result directly.
        """
        if values is None:
            values = self._values
        values = list(values)
        fmt = self._display_format

        # Entries carrying an explicit display bypass formatting entirely;
        # the rest are formatted against their unwrapped data.
        out = {
            v: RecentValuesStore._entry_display(v)
            for v in values
            if RecentValuesStore._entry_display(v) is not None
        }
        plain = [v for v in values if v not in out]
        data_of = {v: RecentValuesStore._entry_data(v) for v in plain}

        if callable(fmt):
            out.update({v: fmt(data_of[v]) for v in plain})
            return out

        if fmt == "basename":
            # Only a path has a base name; anything else -- a naming rule with
            # a "\d" in it -- would be cut at its slash.
            out.update(
                {
                    v: (
                        os.path.basename(str(data_of[v]))
                        if RecentValuesStore._is_filesystem_path(data_of[v])
                        else ptk.truncate(
                            str(data_of[v]), self.MAX_DISPLAY_LENGTH, mode="middle"
                        )
                    )
                    for v in plain
                }
            )
            return out

        if fmt == "auto":
            dm = RecentValuesStore._build_display_map_smart_path(
                [data_of[v] for v in plain]
            )
            if dm is not None:
                out.update({v: dm[data_of[v]] for v in plain})
                return out
            # fall through to truncation

        out.update(
            {
                v: ptk.truncate(str(data_of[v]), self.MAX_DISPLAY_LENGTH, mode="middle")
                for v in plain
            }
        )
        return out
