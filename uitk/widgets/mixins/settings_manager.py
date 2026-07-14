# !/usr/bin/python
# coding=utf-8
import json
import logging
from typing import Any, Callable, List, Optional, Set, Tuple
from qtpy import QtCore

_log = logging.getLogger(__name__)

# Defaults for the (org, app) pair used to construct QSettings when the
# caller doesn't supply them explicitly. Choosing them deliberately —
# rather than letting them fall through to ``__package__`` — keeps every
# uitk-managed setting under a single registry root on Windows
# (``HKCU\Software\uitk\``) and a single config location on Mac/Linux.
DEFAULT_ORG_NAME = "uitk"
DEFAULT_APP_NAME = "shared"

# =============================================================================
# DEPRECATED MIGRATION LOGIC — scheduled for removal
# =============================================================================
#
# Everything from ``_LEGACY_WIDGETS_ORG`` through the end of
# ``_maybe_migrate_legacy_registry`` exists solely to drain older
# registry / QSettings layouts into the current
# ``HKCU\Software\uitk\<app>\`` layout. It is *not* part of the
# current design and should be deleted once no users remain on the
# old layouts.
#
# Removal candidates (delete together — they form one self-contained block):
#
#   - ``_LEGACY_WIDGETS_ORG``
#   - ``_LEGACY_MIXINS_ORG``
#   - ``_LEGACY_MIXINS_DEFAULT_APP``
#   - ``_REGISTRY_MIGRATED_KEY``
#   - ``_INTERNAL_KEYS``
#   - ``_MIGRATED_REGISTRY_PAIRS``
#   - ``_legacy_qsettings_pairs_for``
#   - ``_maybe_migrate_legacy_registry``
#   - The ``_maybe_migrate_legacy_registry(org, app)`` call inside
#     ``SettingsManager.__init__``
#   - The ``_INTERNAL_KEYS`` exclusion inside ``SettingsManager.keys``
#     (the surrounding logic stays; only the filter goes away)
#   - Test class ``TestRegistryMigration`` in ``test/test_settings_manager.py``
#
# Removal criteria (any one is sufficient):
#
#   1. No legacy settings data exists at the legacy registry roots on
#      any machine that runs this code — confirmed by inspection of
#      ``HKCU\Software\uitk.widgets\`` and
#      ``HKCU\Software\uitk.widgets.mixins\`` (these subkeys should be
#      empty or absent).
#   2. The deprecation review date below has passed.
#
# Suggested review date: **2027-05-21** (matches the preset-migration
# review date so both deprecations land in the same cleanup pass).
#
# =============================================================================

_LEGACY_WIDGETS_ORG = "uitk.widgets"
_LEGACY_MIXINS_ORG = "uitk.widgets.mixins"
_LEGACY_MIXINS_DEFAULT_APP = "DefaultApp"

# Internal marker key written inside the destination QSettings after a
# successful migration. The prefix is deliberately library-namespaced
# so it can't collide with arbitrary user namespaces (a user passing
# ``namespace="Meta"`` to ``SettingsManager`` shouldn't see migration
# bookkeeping in their ``keys()`` view).
_REGISTRY_MIGRATED_KEY = "_uitk_internal/migration_v1_done"

# Keys that ``SettingsManager.keys()`` hides from iteration. Internal
# library bookkeeping; not part of any user namespace.
_INTERNAL_KEYS = frozenset({_REGISTRY_MIGRATED_KEY})

_MIGRATED_REGISTRY_PAIRS: Set[Tuple[str, str]] = set()


def _legacy_qsettings_pairs_for(new_org: str, new_app: str) -> List[Tuple[str, str]]:
    """Return ``[(old_org, old_app), ...]`` to drain into (new_org, new_app).

    Returns an empty list when ``new_org`` isn't the default — an explicit
    non-default org means the caller knows what they're doing and we
    shouldn't second-guess their registry layout.

    Pulled out as a function so tests can monkey-patch it to point at
    test-prefixed org/app pairs and avoid touching real registry data.
    """
    if new_org != DEFAULT_ORG_NAME:
        return []
    pairs = [(_LEGACY_WIDGETS_ORG, new_app)]
    if new_app == DEFAULT_APP_NAME:
        # The no-arg ``SettingsManager()`` fallback used to land at
        # ``<__package__>/DefaultApp``, where ``__package__`` resolves to
        # ``uitk.widgets.mixins`` at this module's import time. Drain it
        # into the new shared bucket.
        pairs.append((_LEGACY_MIXINS_ORG, _LEGACY_MIXINS_DEFAULT_APP))
    return pairs


def _maybe_migrate_legacy_registry(org: str, app: str) -> None:
    """Drain QSettings keys from legacy (org, app) pairs into (org, app).

    Best-effort: each legacy pair is iterated; keys not yet present at
    the destination are copied; existing destination keys win (no
    overwrite). After successful copy the legacy QSettings is
    ``clear()``-ed so the next access doesn't re-process the same keys.

    Idempotency:

    * Process-local — ``_MIGRATED_REGISTRY_PAIRS`` shortcuts the check
      after the first call for a given (org, app).
    * On-disk — a ``Meta/MigratedFromLegacy`` marker key is written
      inside the destination QSettings, so subsequent processes see it
      and skip.

    Failure mode: I/O / permission errors are caught and logged at
    warning level rather than propagated, so a hosed migration can't
    break the host app's startup.
    """
    if (org, app) in _MIGRATED_REGISTRY_PAIRS:
        return
    _MIGRATED_REGISTRY_PAIRS.add((org, app))

    pairs = _legacy_qsettings_pairs_for(org, app)
    if not pairs:
        return

    try:
        new_qs = QtCore.QSettings(org, app)
        if new_qs.value(_REGISTRY_MIGRATED_KEY):
            return
    except Exception as e:  # noqa: BLE001 — defensive at process start
        _log.warning("registry migration: could not open %s/%s: %s", org, app, e)
        return

    for old_org, old_app in pairs:
        try:
            old_qs = QtCore.QSettings(old_org, old_app)
            keys = old_qs.allKeys()
            if not keys:
                continue
            for key in keys:
                if key == _REGISTRY_MIGRATED_KEY:
                    continue  # don't carry the marker forward
                if new_qs.contains(key):
                    continue  # live data wins on collision
                new_qs.setValue(key, old_qs.value(key))
            _log.debug("registry migration: drained %s/%s -> %s/%s (%d keys)",
                       old_org, old_app, org, app, len(keys))
            # Empty out the legacy location after the drain. The empty
            # registry subkey shell stays (QSettings has no API to delete
            # the parent key itself) — visible but harmless.
            old_qs.clear()
            old_qs.sync()
        except Exception as e:  # noqa: BLE001
            _log.warning("registry migration: %s/%s -> %s/%s failed: %s",
                         old_org, old_app, org, app, e)

    try:
        new_qs.setValue(_REGISTRY_MIGRATED_KEY, True)
        new_qs.sync()
    except Exception as e:  # noqa: BLE001
        _log.warning("registry migration: could not write marker for %s/%s: %s",
                     org, app, e)


# Sentinel distinguishing "key absent" from any stored value (including None),
# so a caller-supplied default is returned verbatim rather than decoded.
_MISSING = object()


def decode_stored_value(value: Any) -> Any:
    """Read-side mirror of :func:`encode_stored_value`.

    Maps the legacy ``"None"`` corruption sentinel to ``None`` and JSON-decodes
    strings — which restores both this module's own encoding (containers,
    quoted ambiguous strings) and the stringified bools / numbers that
    QSettings backends produce natively. Non-JSON strings pass through
    verbatim; non-strings are returned untouched.

    Shared by :meth:`SettingsManager.value` and ``StateManager``'s raw-store
    read paths so every decode in the persistence stack stays symmetric with
    the single encoder.
    """
    if value == "None":
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def encode_stored_value(value: Any) -> Any:
    """Encode *value* for QSettings so a JSON-decoding read restores it losslessly.

    The single serialization chokepoint shared by :class:`SettingsManager`
    and ``StateManager`` (for raw-``QSettings`` stores), paired with the
    ``json.loads`` on the read side (:meth:`SettingsManager.value`).

    - Containers (list / dict / tuple) are JSON-encoded; tuples come back as
      lists (JSON parity), and the encoding avoids QSettings' platform-
      dependent QVariant round-trip.
    - Strings are stored **plain** — human-readable in the registry / ini —
      *except* the ambiguous ones: strings that themselves parse as JSON
      (``"1.10"``, ``"123"``, ``"true"``, ``"[1, 2]"``) plus the legacy
      ``"None"`` corruption sentinel. Those are stored JSON-quoted so the
      read-side decode returns the original string instead of a
      number / bool / container. (The eager decode itself is load-bearing:
      QSettings backends stringify bools and numbers, and ``json.loads`` is
      what turns ``"true"`` back into ``True``.)
    - Everything else passes through untouched.
    """
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value)
    if isinstance(value, str):
        if value == "None":
            return json.dumps(value)
        try:
            json.loads(value)
        except (ValueError, TypeError):
            return value  # not JSON-parseable -> unambiguous, store plain
        return json.dumps(value)  # ambiguous -> quote so it decodes verbatim
    return value


class SettingsManager:
    """Manages persistent storage and retrieval of settings via QSettings.

    Attributes behave as proxies (`SettingItem`), allowing robust interaction:

        # Access value
        val = settings.key.get()

        # Update value
        settings.key.set(value)
        # NOTE: direct attribute assignment (``settings.key = value``) is
        # intentionally rejected (``__setattr__`` raises AttributeError) to
        # avoid ambiguity between assigning a proxy and a value -- always use
        # ``settings.key.set(value)``.

        # Signals
        settings.key.changed.connect(callback)

    Provides data integrity protections:
    - Filters out corrupted "None" strings from old/broken code
    - Automatic JSON serialization/deserialization for complex types
    - Lossless string round-trips: strings that would JSON-decode to
      something else ("1.10", "true", "123") are stored quoted so they
      come back verbatim (see :func:`encode_stored_value`)
    - Namespace support for key grouping
    - Change callbacks for reactive updates
    """

    class SettingItem:
        """Proxy object representing a specific setting key."""

        def __init__(self, manager: "SettingsManager", key: str):
            self._manager = manager
            self._key = key
            self.changed = self._SignalProxy(manager, key)

        def get(self, default: Any = None) -> Any:
            """Retrieve the value of this setting."""
            return self._manager.value(self._key, default)

        def set(self, value: Any) -> None:
            """Update the value of this setting."""
            self._manager.setValue(self._key, value)

        def __repr__(self):
            return f"<SettingItem key='{self._key}' value={self.get()}>"

        class _SignalProxy:
            """Helper to provide .connect syntax."""

            def __init__(self, manager: "SettingsManager", key: str):
                self._manager = manager
                self._key = key

            def connect(self, callback: Callable[[Any], None]) -> None:
                self._manager.on_change(self._key, callback)

    # Reserved names that should not be treated as settings keys
    _RESERVED = frozenset(
        {
            "settings",
            "namespace",
            "get",
            "value",
            "setValue",
            "clear",
            "remove",
            "sync",
            "setByteArray",
            "getByteArray",
            "on_change",
            "keys",
            "_ns_key",
            "_callbacks",
            "SettingItem",
            "branch",
            "set_defaults",
        }
    )

    def __init__(
        self,
        org: Optional[str] = None,
        app: Optional[str] = None,
        namespace: Optional[str] = None,
        qsettings: Optional[QtCore.QSettings] = None,
    ):
        object.__setattr__(self, "_callbacks", {})
        if qsettings:
            object.__setattr__(self, "settings", qsettings)
        else:
            org = org or DEFAULT_ORG_NAME
            app = app or DEFAULT_APP_NAME
            # Drain legacy registry layouts (uitk.widgets/<app>,
            # uitk.widgets.mixins/DefaultApp) into the current location
            # before constructing the live QSettings. One-shot per
            # (org, app) per process; see _maybe_migrate_legacy_registry.
            _maybe_migrate_legacy_registry(org, app)
            object.__setattr__(self, "settings", QtCore.QSettings(org, app))
        object.__setattr__(self, "namespace", namespace)

    def __getattr__(self, name: str) -> "SettingItem":
        """Attribute-style access returns a SettingItem proxy."""
        if name.startswith("_") or name in self._RESERVED:
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
        return self.SettingItem(self, name)

    def __setattr__(self, name: str, value: Any) -> None:
        """Prevent direct attribute assignment to enforce usage of .set() on proxies."""
        if name.startswith("_") or name in self._RESERVED:
            object.__setattr__(self, name, value)
            return

        # Enforce usage of .set()
        # This breaks compatibility with `settings.key = val`
        # but prevents ambiguity between setting a proxy and a value.
        raise AttributeError(
            f"Direct assignment to '{name}' is not allowed. "
            f"Use 'settings.{name}.set(value)' instead."
        )

    def _ns_key(self, key: str) -> str:
        if self.namespace:
            return f"{self.namespace}/{key}"
        return key

    def branch(self, name: str) -> "SettingsManager":
        """Create a new SettingsManager instance targeted at a sub-namespace."""
        new_ns = self._ns_key(name)
        return SettingsManager(qsettings=self.settings, namespace=new_ns)

    def set_defaults(self, defaults: dict) -> None:
        """Apply default values for a set of keys if they are not already set."""
        for key, value in defaults.items():
            if self.value(key) is None:
                self.setValue(key, value)

    def value(self, key: str, default: Any = None) -> Any:
        value = self.settings.value(self._ns_key(key), _MISSING)
        # Decode belongs to STORED values only: a missing key returns the
        # caller's default verbatim (running it through the decode turned a
        # default of "1.10" into the float 1.1 with nothing stored at all).
        if value is _MISSING:
            return default
        return decode_stored_value(value)

    def setValue(self, key: str, value: Any) -> None:
        # Containers are JSON-encoded; ambiguous strings ("1.10", "true", …)
        # are JSON-quoted so value()'s decode restores them verbatim instead
        # of a number/bool. See encode_stored_value.
        self.settings.setValue(self._ns_key(key), encode_stored_value(value))

        # Trigger callbacks
        callbacks = object.__getattribute__(self, "_callbacks")
        if key in callbacks:
            # Retrieve the deserialized value for callbacks
            actual_value = self.value(key)
            for cb in callbacks[key]:
                try:
                    cb(actual_value)
                except Exception as e:
                    _log.debug("on_change callback for %r failed: %s", key, e)

    def on_change(self, key: str, callback: Callable[[Any], None]) -> None:
        """Register a callback to be invoked when a key's value changes.

        Args:
            key: The settings key to watch.
            callback: Function called with the new value when key is set.
        """
        callbacks = object.__getattribute__(self, "_callbacks")
        if key not in callbacks:
            callbacks[key] = []
        callbacks[key].append(callback)

    def keys(self) -> list:
        """Return all keys in the current namespace.

        Library-internal keys (see :data:`_INTERNAL_KEYS`) are excluded
        so callers iterating their own data don't see migration
        bookkeeping or other implementation artifacts. The filter is
        the only line tying this method to the migration system; when
        the migration code is retired (see deprecation block above),
        remove just that comprehension condition.
        """
        all_keys = [k for k in self.settings.allKeys() if k not in _INTERNAL_KEYS]
        if self.namespace:
            prefix = f"{self.namespace}/"
            return [k[len(prefix) :] for k in all_keys if k.startswith(prefix)]
        return list(all_keys)

    def setByteArray(self, key: str, value: QtCore.QByteArray) -> None:
        """Set a QByteArray value directly without JSON serialization."""
        self.settings.setValue(self._ns_key(key), value)

    def getByteArray(
        self, key: str, default: QtCore.QByteArray = None
    ) -> QtCore.QByteArray:
        """Get a QByteArray value directly."""
        return self.settings.value(self._ns_key(key), default)

    def remove(self, key: str) -> None:
        """Remove a single key from the current namespace.

        Mirrors ``QSettings.remove`` so a ``SettingsManager`` and a raw
        ``QSettings`` are interchangeable as a ``StateManager`` backing
        store. (Before this existed, ``__getattr__`` manufactured a
        ``SettingItem`` proxy for the name, so ``store.remove(key)`` failed
        with a ``TypeError`` at call time.)
        """
        self.settings.remove(self._ns_key(key))

    def clear(self, key: Optional[str] = None) -> None:
        """Clears a specific key, or all keys in the current namespace."""
        if key:
            self.remove(key)
        elif self.namespace:
            self.settings.remove(self.namespace)
        else:
            self.settings.clear()

    def sync(self) -> None:
        self.settings.sync()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ...


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------
