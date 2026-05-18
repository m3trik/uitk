# !/usr/bin/python
# coding=utf-8
"""Shared persistence wiring for OptionBox plugins.

Three options (ActionOption, PinValuesOption, RecentValuesOption) all maintain
near-duplicate ``settings_key`` resolution + lazy SettingsManager construction.
This module lifts the common bits so a new plugin can opt in by mixing it in
and declaring ``SETTINGS_APP``. Each subclass keeps full control over what is
actually saved/loaded (the schemas differ: int, list, deque).
"""

from typing import Optional, Union


class PersistedOption:
    """Mixin that adds ``settings_key`` resolution + lazy SettingsManager.

    Subclasses set the ``SETTINGS_APP`` class attribute (the ``app`` argument
    forwarded to :class:`SettingsManager`) and call :meth:`_init_persistence`
    once with the constructor's ``settings_key`` value.

    ``settings_key`` accepts:
        - ``str``  → explicit namespace
        - ``None`` → auto-derive from ``wrapped_widget.objectName()``
        - ``False`` → persistence disabled (consumer owns storage externally)

    After :meth:`_init_persistence`, ``self._settings`` is either a
    :class:`SettingsManager` instance or ``None``. Subclasses guard on truthiness
    before reading/writing.
    """

    SETTINGS_APP: str = "Option"

    def _init_persistence(self, settings_key: Optional[Union[str, bool]]) -> None:
        self._settings_key = settings_key
        self._settings = None
        key = self._resolve_settings_key()
        if not key:
            return
        from uitk.widgets.mixins.settings_manager import SettingsManager

        self._settings = SettingsManager(
            org="uitk", app=self.SETTINGS_APP, namespace=key
        )

    def _resolve_settings_key(self) -> Optional[str]:
        """Resolve the namespace string used for QSettings.

        Priority:
            1. Explicit ``settings_key`` string passed at construction.
            2. Auto-derived from ``wrapped_widget.objectName()``.
            3. ``None`` (no persistence) — when ``settings_key=False`` was
               passed or the wrapped widget has no objectName.
        """
        if self._settings_key is False:
            return None
        if self._settings_key:
            return self._settings_key
        w = getattr(self, "wrapped_widget", None)
        if w is not None and hasattr(w, "objectName") and w.objectName():
            return w.objectName()
        return None
