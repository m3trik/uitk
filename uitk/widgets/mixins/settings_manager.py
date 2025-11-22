# !/usr/bin/python
# coding=utf-8
from typing import Any, Optional
from qtpy import QtCore
import json


class SettingsManager:
    """Manages persistent storage and retrieval of settings via QSettings.

    Provides data integrity protections:
    - Filters out corrupted "None" strings from old/broken code
    - Automatic JSON serialization/deserialization for complex types
    - Namespace support for key grouping

    Parameters:
        organization (str): Organization or package name. Defaults to __package__.
        application (str): Application name, typically your UI/window name.
        namespace (str): Optional key prefix for grouping.
        qsettings (QtCore.QSettings): Optional existing QSettings instance.
    """

    def __init__(
        self,
        org: Optional[str] = None,
        app: Optional[str] = None,
        namespace: Optional[str] = None,
        qsettings: Optional[QtCore.QSettings] = None,
    ):
        if qsettings:
            self.settings = qsettings
        else:
            org = org or __package__ or "DefaultOrg"
            app = app or "DefaultApp"
            self.settings = QtCore.QSettings(org, app)
        self.namespace = namespace

    def __getattr__(self, name):
        # Only called if attribute not found on SettingsManager itself
        return getattr(self.settings, name)

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

    def setByteArray(self, key: str, value: QtCore.QByteArray) -> None:
        """Set a QByteArray value directly without JSON serialization."""
        self.settings.setValue(self._ns_key(key), value)

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
