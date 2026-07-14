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
"""
import os
from typing import Callable, List, Optional

import pythontk as ptk


def _is_filesystem_path(value) -> bool:
    """Return True if *value* looks like a filesystem path."""
    s = str(value)
    # Drive letter (C:/) or UNC (\\server) or absolute unix (/home)
    if len(s) >= 2 and s[1] == ":":
        return True
    if s.startswith("//") or s.startswith("\\\\"):
        return True
    if s.startswith("/"):
        return True
    return False


def _build_display_map_smart_path(values) -> Optional[dict]:
    """Build a display map by stripping the common directory prefix.

    Only engages when *all* values look like filesystem paths and there
    are at least two of them.  Returns ``None`` (use default truncation)
    otherwise.
    """
    str_values = [str(v) for v in values]
    if len(str_values) < 2 or not all(_is_filesystem_path(v) for v in str_values):
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


class RecentValueEntry:
    """A recent value whose restore-data differs from its display string.

    Most history entries are plain values (the value *is* what's shown and
    restored). An entry is used only when a presenter needs to show one thing
    while restoring another — e.g. a line edit that displays texture-set names
    but carries the full ``os.pathsep``-joined file paths as ``data``.

    Dedup/normalization key off :attr:`data`, so an entry compares equal to the
    plain value it would restore. Mirrors ``PinValuesOption.PinnedValueEntry``.
    """

    __slots__ = ("data", "display")

    def __init__(self, data, display=None):
        self.data = data
        self.display = display

    def __eq__(self, other):
        if isinstance(other, RecentValueEntry):
            return normalize_value(self.data) == normalize_value(other.data)
        return normalize_value(self.data) == normalize_value(other)

    def __hash__(self):
        n = normalize_value(self.data)
        return hash(n if isinstance(n, str) else str(n))

    def __repr__(self):
        return f"RecentValueEntry(data={self.data!r}, display={self.display!r})"


def _entry_data(value):
    """The restore-data of *value* (its ``.data`` when an entry, else itself)."""
    return value.data if isinstance(value, RecentValueEntry) else value


def _entry_display(value):
    """The explicit display of *value*, or ``None`` to derive one."""
    return value.display if isinstance(value, RecentValueEntry) else None


def normalize_value(value):
    """Normalize a value for comparison.

    Unwraps a :class:`RecentValueEntry` to its data, strips whitespace and,
    for path-like strings, normalizes separators and case so that ``C:/Dir``
    and ``c:\\dir`` compare equal.
    """
    if isinstance(value, RecentValueEntry):
        value = value.data
    if isinstance(value, str):
        value = value.strip()
        if "/" in value or "\\" in value:
            value = ptk.format_path(value).lower()
    return value


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
        max_recent: Maximum number of entries to keep.
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
    """

    MAX_DISPLAY_LENGTH = 120

    def __init__(
        self,
        settings_key: Optional[str] = None,
        max_recent: int = 10,
        display_format="auto",
        validator: Optional[Callable[[object], bool]] = None,
        settings=None,
    ):
        self._values: List = []
        self._settings_key = settings_key
        self._max_recent = max_recent
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
        from uitk.widgets.mixins.settings_manager import SettingsManager

        self._settings = SettingsManager(
            org="uitk", app="RecentValues", namespace=self._settings_key
        )

    @staticmethod
    def _serialize(value):
        """Plain values persist as-is; entries persist as a tagged dict."""
        if isinstance(value, RecentValueEntry):
            return {"__recent_entry__": True, "data": value.data, "display": value.display}
        return value

    @staticmethod
    def _deserialize(value):
        """Rehydrate a tagged dict back into a :class:`RecentValueEntry`."""
        if isinstance(value, dict) and value.get("__recent_entry__"):
            return RecentValueEntry(value.get("data"), value.get("display"))
        return value

    def _save(self):
        if not self._settings:
            return
        self._settings.setValue("entries", [self._serialize(v) for v in self._values])
        self._settings.sync()

    def _load(self):
        if not self._settings:
            return
        data = self._settings.value("entries", []) or []
        # Deduplicate on load (keep first occurrence = most recent).
        seen = set()
        deduped = []
        for v in data:
            v = self._deserialize(v)
            if _entry_data(v) is None:
                continue
            n = normalize_value(v)
            if n not in seen:
                seen.add(n)
                deduped.append(v)
        self._values = deduped

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

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, value) -> None:
        """Insert *value* at the front (most-recent), dedup, trim, persist."""
        if _entry_data(value) is None or not str(_entry_data(value)).strip():
            return
        n = normalize_value(value)
        self._values = [v for v in self._values if normalize_value(v) != n]
        self._values.insert(0, value)
        self._values = self._values[: self._max_recent]
        self._save()
        self._notify()

    def add(self, value) -> None:
        """Seed *value* (append if new); preserves existing order.

        Use for programmatic seeding (e.g. importing a host app's recent
        list). Unlike :meth:`record` it does not move an existing entry to
        the front.
        """
        if _entry_data(value) is None or not str(_entry_data(value)).strip():
            return
        n = normalize_value(value)
        if any(normalize_value(v) == n for v in self._values):
            return
        self._values.append(value)
        if len(self._values) > self._max_recent:
            # The list is most-recent-first, so the OLDEST entries are at the
            # tail. Keep the head (the most recent) and drop from the tail --
            # slicing ``[-max:]`` would instead discard the user's most recent
            # entries when seeding into an already-full store.
            self._values = self._values[: self._max_recent]
        self._save()
        self._notify()

    def remove(self, value) -> None:
        """Remove *value* from the history (no-op if absent)."""
        n = normalize_value(value)
        before = len(self._values)
        self._values = [v for v in self._values if normalize_value(v) != n]
        if len(self._values) != before:
            self._save()
            self._notify()

    def clear(self) -> None:
        """Drop all history."""
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
        out = {v: _entry_display(v) for v in values if _entry_display(v) is not None}
        plain = [v for v in values if v not in out]
        data_of = {v: _entry_data(v) for v in plain}

        if callable(fmt):
            out.update({v: fmt(data_of[v]) for v in plain})
            return out

        if fmt == "basename":
            out.update({v: os.path.basename(str(data_of[v])) for v in plain})
            return out

        if fmt == "auto":
            dm = _build_display_map_smart_path([data_of[v] for v in plain])
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
