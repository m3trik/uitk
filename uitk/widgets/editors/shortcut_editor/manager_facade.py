# !/usr/bin/python
# coding=utf-8
"""Adapter that lets the unified :class:`ShortcutEditor` render a standalone
:class:`~uitk.managers.shortcut_manager.ShortcutManager`.

A bare widget (e.g. the sequencer) owns a ``ShortcutManager`` with no
Switchboard in sight. This is the thinnest configuration of the generic
:class:`~uitk.widgets.editors.shortcut_editor.registry_facade.RegistrySwitchboardFacade`:
one group (the manager's single binding set, rendered as one synthetic "UI"),
no presets, owner-fixed scope, rebind-only edits.
"""
from uitk.widgets.editors.shortcut_editor.registry_facade import (
    RegistrySwitchboardFacade,
)


class ManagerSwitchboardFacade(RegistrySwitchboardFacade):
    """Switchboard-shaped view over a :class:`ShortcutManager` for the editor."""

    def __init__(self, manager, ui_name: str = "Shortcuts"):
        self.manager = manager
        super().__init__(
            groups=lambda: [ui_name],
            get_entries=self._entries,
            apply_binding=self._apply,
            # Distinct namespace so the manager editor's view prefs (filter
            # text, show-all/hidden) don't bleed into the real Switchboard
            # editor's.
            settings_namespace="shortcut_manager_editor",
            logger_name="uitk.shortcut_manager_editor",
        )

    def _entries(self, _group: str) -> list:
        entries = self.manager.get_registry()
        for e in entries:
            # A manager binding's scope is fixed by its owner widget (and the
            # host's window_shortcuts toggle), never per-row in the editor.
            e["scope_editable"] = False
        return entries

    def _apply(self, _group: str, method: str, sequence: str, _scope=None):
        """Apply an editor edit. ``method`` is the binding's current sequence
        (the manager keys by sequence), so a non-empty change is a rebind.

        An empty *sequence* is ignored, not destructive: a manager binding has no
        "listed but unbound" state (unlike a slot/command), so clearing it would
        delete the action outright (e.g. the sequencer's Undo) with no way to
        restore it from the editor. The retired ``ShortcutEditorDialog`` likewise
        only ever rebound, never cleared. Scope is ignored — owner-fixed."""
        if sequence and sequence != method:
            self.manager.rebind_shortcut(method, sequence)
