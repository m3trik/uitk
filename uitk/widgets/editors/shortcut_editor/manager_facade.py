# !/usr/bin/python
# coding=utf-8
"""Adapter that lets the unified :class:`ShortcutEditor` render a standalone
:class:`~uitk.widgets.mixins.shortcuts.ShortcutManager`.

The editor was written Switchboard-first, but a bare widget (e.g. the
sequencer) owns a ``ShortcutManager`` with no Switchboard in sight. Rather than
fork a second editor (the retired ``ShortcutEditorDialog``) or thread a
``registry`` parameter through the editor's many ``self.sb.*`` call-sites, this
facade presents the small Switchboard surface the editor actually touches —
backed by the manager's single binding set as one synthetic "UI". All
mode-specific behaviour (no presets, no Assigned/Commands pseudo-views,
owner-fixed scope) is keyed off ``_is_manager_facade`` inside the editor, so the
real-Switchboard path is byte-for-byte unchanged.
"""
import logging
from typing import List, Optional

from uitk.widgets.mixins.settings_manager import SettingsManager


class _ManagerUI:
    """Opaque stand-in for a Switchboard UI owning a manager's bindings.

    The editor only ever calls ``objectName()`` on a UI object and otherwise
    passes it straight back to ``get_shortcut_registry`` / ``set_user_shortcut``,
    so a name + a back-reference to the manager is all it needs.
    """

    def __init__(self, name: str, manager):
        self._name = name
        self.manager = manager

    def objectName(self) -> str:
        return self._name


class _LoadedUiStub:
    """Stands in for ``sb.loaded_ui`` — a single, always-"loaded" manager UI."""

    def __init__(self, ui: _ManagerUI):
        self._ui = ui

    def peek(self, _name: Optional[str] = None):
        return self._ui

    def values(self):
        return [self._ui]


class _UiRegistryStub:
    """Stands in for ``sb.registry`` — exposes the one synthetic UI name."""

    def __init__(self, ui_name: str):
        self._ui_name = ui_name
        self.ui_registry = self

    def get(self, field=None, **_kwargs):
        # The editor calls ``ui_registry.get("filename")`` to list UIs.
        return [self._ui_name]


class _WidgetFactory:
    """Stands in for ``sb.registered_widgets`` — the editor only constructs a
    ``LineEdit`` (its filter field) through it."""

    @property
    def LineEdit(self):
        from uitk.widgets.lineEdit import LineEdit

        return LineEdit


class ManagerSwitchboardFacade:
    """Switchboard-shaped view over a :class:`ShortcutManager` for the editor."""

    #: Sentinel the editor checks to enter manager mode (skip presets / special
    #: views, lock scope). Cheaper + looser than an isinstance import cycle.
    _is_manager_facade = True

    def __init__(self, manager, ui_name: str = "Shortcuts"):
        self.manager = manager
        self._ui_name = ui_name
        # Distinct namespace so the manager editor's view prefs (filter text,
        # show-all/hidden) don't bleed into the real Switchboard editor's.
        self.settings = SettingsManager(namespace="shortcut_manager_editor")
        self.registered_widgets = _WidgetFactory()
        self.registry = _UiRegistryStub(ui_name)
        self.logger = logging.getLogger("uitk.shortcut_manager_editor")
        self._ui = _ManagerUI(ui_name, manager)
        self.loaded_ui = _LoadedUiStub(self._ui)

    # -- UI resolution (all resolve to the one synthetic manager UI) --------

    def get_ui(self, _name=None):
        return self._ui

    def convert_to_legal_name(self, name: str) -> str:
        return name

    def _ui_names_with_shortcut_overrides(self) -> set:
        return set()

    # -- registry (manager bindings, scope locked to the owner widget) ------

    def get_shortcut_registry(self, _ui=None) -> List[dict]:
        entries = self.manager.get_registry()
        for e in entries:
            # A manager binding's scope is fixed by its owner widget (and the
            # host's window_shortcuts toggle), never per-row in the editor.
            e["scope_editable"] = False
        return entries

    def get_static_shortcut_registry(self, _name=None) -> List[dict]:
        return self.get_shortcut_registry()

    # -- edits route back to the manager ------------------------------------

    def set_user_shortcut(self, _ui, method: str, sequence: str, scope=None):
        """Apply an editor edit. ``method`` is the binding's current sequence
        (the manager keys by sequence), so a non-empty change is a rebind.

        An empty *sequence* is ignored, not destructive: a manager binding has no
        "listed but unbound" state (unlike a slot/command), so clearing it would
        delete the action outright (e.g. the sequencer's Undo) with no way to
        restore it from the editor. The retired ``ShortcutEditorDialog`` likewise
        only ever rebound, never cleared. ``scope`` is ignored — owner-fixed."""
        if sequence and sequence != method:
            self.manager.rebind_shortcut(method, sequence)
