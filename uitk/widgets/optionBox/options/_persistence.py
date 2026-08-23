# !/usr/bin/python
# coding=utf-8
"""Shared persistence wiring for OptionBox plugins.

Four persisted plugins (ActionOption, PinValuesOption, RecentValuesOption,
ToggleOption + its DisableOption/FilterOption subclasses) all maintained
near-duplicate ``settings_key`` resolution + lazy SettingsManager construction.
:class:`PersistedOption` is both the mixin a plugin opts into (declare
``SETTINGS_APP``, call ``_init_persistence``) and the namespace holding the
construction helpers, so a plugin whose key resolution differs — PinValuesOption
does not auto-derive from ``objectName``, and RecentValuesOption hands its store
in — still builds its settings through the same one place. Each keeps full
control over what is actually saved/loaded (the schemas differ: int, list, deque).

**Every namespace built here is host-namespaced** — see
:meth:`PersistedOption.settings_for`. QSettings is keyed by ``(org, app)`` and
shared by every process on the machine, so without a per-host suffix a Maya and a
Blender session read and write the same keys — and they *will*, because mayatk and
blendertk panels are deliberate mirrors that pass the SAME ``settings_key``.
"""

from typing import Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:  # imported lazily in the body to keep import side effects out
    from uitk.managers.settings_manager import SettingsManager


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

    :meth:`settings_for` and :meth:`host_suffix_for` are the class's *namespace*
    role: plugins that can't use this mixin's key resolution still call them, so
    the ``(org, app)`` root and the host suffix have one implementation.
    """

    SETTINGS_APP: str = "Option"

    # ------------------------------------------------------------------ mixin
    def _init_persistence(self, settings_key: Optional[Union[str, bool]]) -> None:
        self._settings_key = settings_key
        self._settings = PersistedOption.settings_for(
            self.SETTINGS_APP,
            self._resolve_settings_key(),
            getattr(self, "wrapped_widget", None),
        )

    def _resolve_settings_key(self) -> Optional[str]:
        """Resolve the namespace string used for QSettings.

        Priority:
            1. Explicit ``settings_key`` string passed at construction.
            2. Auto-derived from ``wrapped_widget.objectName()``.
            3. ``None`` (no persistence) — when ``settings_key=False`` was
               passed or the wrapped widget has no objectName.

        The host suffix is NOT applied here — :meth:`settings_for` owns that, so
        every plugin gets it whether or not it uses this resolver.

        Known gap in the auto-derived case (2): the key is the bare objectName, so
        two PANELS carrying the same widget name share one stored value within a
        host. Measured, and logged in ``.claude/BACKLOG.md`` (2026-08-21, uitk) —
        panel-scoping it moves every existing auto key, so it needs its own pass.
        Pass an explicit ``settings_key`` to opt out.
        """
        if self._settings_key is False:
            return None
        if self._settings_key:
            return self._settings_key
        w = getattr(self, "wrapped_widget", None)
        if w is not None and hasattr(w, "objectName") and w.objectName():
            return w.objectName()
        return None

    # ------------------------------------------------------------------ namespace
    @staticmethod
    def host_suffix_for(widget) -> str:
        """Host-context suffix (``"_maya"`` / ``"_blender"`` / ``""``) for *widget*.

        Finds the owning Switchboard through the widget's registered ``ui``
        (``MainWindow.register_widget`` sets ``widget.ui``, and ``MainWindow.sb`` is
        the Switchboard) and asks *it* — the suffix is not re-derived here. The
        Switchboard's ``_host_suffix`` already delegates to
        :meth:`ShortcutManager.host_namespace_suffix`, the SSoT shared by the
        shortcut store, the marking-menu binding store and the window-persistence
        override key; reading ``context_tags`` and formatting them again would be a
        second derivation free to drift from those. Reached by ``getattr``, the same
        way ``UiHandler._persistence_key`` reaches ``_host_namespaced_branch``.

        ``""`` (no suffix, shared storage) for anything the resolution doesn't
        reach: a widget not registered with a MainWindow, or a Switchboard with no
        ``context_tags``. That is the intended answer, not a fallback — a standalone
        host has nothing to collide with, and the host-agnostic ``extapps`` panels
        (their own tag-less Switchboard) *should* keep one shared recent-files list
        across every session that opens them.
        """
        for owner in (getattr(widget, "ui", None), widget):
            host_suffix = getattr(getattr(owner, "sb", None), "_host_suffix", None)
            if callable(host_suffix):
                return host_suffix()
        return ""

    @staticmethod
    def settings_for(app: str, key: str, widget=None) -> Optional["SettingsManager"]:
        """A :class:`SettingsManager` for an option plugin's persisted state.

        The single construction point for all four persisted plugins, so the
        ``(org="uitk", app=…)`` root and the host namespacing cannot drift between
        them — drift is exactly what produced the bug this exists to prevent, where
        Maya's and Blender's Reference Manager shared one pinned-directory list.

        Returns ``None`` for a falsy *key* (persistence disabled).
        """
        if not key:
            return None
        from uitk.managers.settings_manager import SettingsManager

        suffix = PersistedOption.host_suffix_for(widget)
        namespace = key + suffix
        settings = SettingsManager(org="uitk", app=app, namespace=namespace)
        if suffix:
            PersistedOption._seed_from_shared_namespace(settings, key, namespace)
        return settings

    @staticmethod
    def _seed_from_shared_namespace(settings, legacy_ns: str, ns: str) -> None:
        """One-shot: copy the pre-namespacing shared values into this host's namespace.

        Before host namespacing every host wrote ``<key>``; now each writes
        ``<key>_<host>``. Without this, the move would read as "my pinned
        directories vanished". Mirrors
        ``SwitchboardShortcutMixin._migrate_shortcuts_to_host_namespace``: each host
        *copies* on first run and then diverges, and the shared values are
        deliberately left in place so the *other* host can still seed from them.

        Guarded by a marker rather than by "the namespace is empty", so a user who
        deliberately unpins everything does not get the old list back on next
        launch. The marker lives outside the option's namespace
        (``_uitk_internal/…``), so it never shows up in the plugin's own ``keys()``.
        """
        from uitk.managers.settings_manager import SettingsManager

        marker = f"_uitk_internal/host_seeded/{ns}"
        store = settings.settings  # raw QSettings — the marker is namespace-external
        if store.value(marker):
            return
        legacy = SettingsManager(qsettings=store, namespace=legacy_ns)
        for k in legacy.keys():
            if settings.value(k) is None:
                settings.setValue(k, legacy.value(k))
        store.setValue(marker, True)
