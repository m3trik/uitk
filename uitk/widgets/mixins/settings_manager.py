# !/usr/bin/python
# coding=utf-8
from typing import Any, Callable, Optional
from qtpy import QtCore
import json


class SettingsManager:
    """Manages persistent storage and retrieval of settings via QSettings.

    Attributes behave as proxies (`SettingItem`), allowing robust interaction:

        # Access value
        val = settings.key.get()

        # Update value
        settings.key.set(value)
        # OR legacy attribute style (still works via __setattr__ intercept)
        settings.key = value

        # Signals
        settings.key.changed.connect(callback)

    Provides data integrity protections:
    - Filters out corrupted "None" strings from old/broken code
    - Automatic JSON serialization/deserialization for complex types
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
            "sync",
            "setByteArray",
            "getByteArray",
            "on_change",
            "keys",
            "_ns_key",
            "_callbacks",
            "SettingItem",
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
            org = org or __package__ or "DefaultOrg"
            app = app or "DefaultApp"
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

    def value(self, key: str, default: Any = None) -> Any:
        value = self.settings.value(self._ns_key(key), default)

        # Filter out corrupted "None" strings from old code
        if value == "None":
            return None

        # Try to decode JSON for lists/dicts
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

    def setValue(self, key: str, value: Any) -> None:
        # Serialize lists/dicts as JSON
        if isinstance(value, (list, dict)):
            value = json.dumps(value)
        self.settings.setValue(self._ns_key(key), value)

        # Trigger callbacks
        callbacks = object.__getattribute__(self, "_callbacks")
        if key in callbacks:
            # Retrieve the deserialized value for callbacks
            actual_value = self.value(key)
            for cb in callbacks[key]:
                try:
                    cb(actual_value)
                except Exception:
                    pass

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
        """Return all keys in the current namespace."""
        all_keys = self.settings.allKeys()
        if self.namespace:
            prefix = f"{self.namespace}/"
            return [k[len(prefix) :] for k in all_keys if k.startswith(prefix)]
        return list(all_keys)

    def setByteArray(self, key: str, value: QtCore.QByteArray) -> None:
        """Set a QByteArray value directly without JSON serialization."""
        self.settings.setValue(self._ns_key(key), value)

    def branch(self, name: str) -> "SettingsManager":
        """Create a new SettingsManager instance using the same QSettings object but with a sub-namespace."""
        new_namespace = f"{self.namespace}/{name}" if self.namespace else name
        return SettingsManager(namespace=new_namespace, qsettings=self.settings)

    def getByteArray(
        self, key: str, default: QtCore.QByteArray = None
    ) -> QtCore.QByteArray:
        """Get a QByteArray value directly."""
        return self.settings.value(self._ns_key(key), default)

    def clear(self, key: Optional[str] = None) -> None:
        """Clears a specific key or all if key is None."""
        if key:
            self.settings.remove(self._ns_key(key))
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
