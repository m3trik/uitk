# !/usr/bin/python
# coding=utf-8
"""Generic Switchboard-shaped adapter for the unified :class:`ShortcutEditor`.

The editor was written Switchboard-first, but plenty of binding stores live
outside a Switchboard — a widget-local :class:`ShortcutManager`, a DCC-native
hotkey registry (mayatk/blendertk macros), … Rather than fork per-store editors
or thread a ``registry`` parameter through the editor's many ``self.sb.*``
call-sites, this facade presents the small Switchboard surface the editor
actually touches, backed by plain callables:

- ``groups()`` — the binding *group* names. Each group renders as one entry in
  the editor's target combobox (a Switchboard UI's role), so a provider with
  natural grouping (e.g. macro categories) gets the combo as a group filter and
  the editor's show-all view as the flat "everything" table for free.
- ``get_entries(group)`` — editor-shaped registry entries for one group (the
  dict shape of ``Switchboard.get_shortcut_registry``).
- ``apply_binding(group, method, sequence, scope)`` — commit an edit. An empty
  *sequence* means "clear"; a provider whose store cannot represent an unbound
  entry (e.g. :class:`ShortcutManager`) simply ignores it.

Cosmetic / behavioural hints (all optional) are plain attributes the editor
reads via ``getattr`` — the real-Switchboard path never carries them, so it is
byte-for-byte unchanged:

- ``editor_title`` / ``editor_status_text`` — window chrome.
- ``ui_column_label`` / ``ui_combo_prefix`` — re-label the editor's UI
  dimension when groups aren't UIs (e.g. "Category").
- ``default_show_all`` — first-run default for the show-all toggle (a persisted
  user choice still wins).
- ``preset_config`` — opt-in preset row over the provider's own preset store
  (``dir_name`` / ``package`` / ``builtin_dir`` / ``value_provider`` /
  ``value_applier``), so the editor persists the SAME semantic JSON any
  headless reader of that store sees.
"""
import logging
from typing import Callable, Dict, List, Optional

from uitk.managers.settings_manager import SettingsManager


class _GroupUI:
    """Opaque stand-in for a Switchboard UI owning one binding group.

    The editor only ever calls ``objectName()`` on a UI object and otherwise
    passes it straight back to ``get_shortcut_registry`` / ``set_user_shortcut``,
    so a name + a back-reference to the facade is all it needs.
    """

    def __init__(self, name: str, facade):
        self._name = name
        self.facade = facade

    def objectName(self) -> str:
        return self._name


class _LoadedUiStub:
    """Stands in for ``sb.loaded_ui`` — every group is always "loaded"."""

    def __init__(self, facade: "RegistrySwitchboardFacade"):
        self._facade = facade

    def peek(self, name: Optional[str] = None):
        return self._facade.get_ui(name)

    def values(self):
        return [self._facade.get_ui(name) for name in self._facade._group_names()]


class _UiRegistryStub:
    """Stands in for ``sb.registry`` — exposes the group names as UI names."""

    def __init__(self, facade: "RegistrySwitchboardFacade"):
        self._facade = facade
        self.ui_registry = self

    def get(self, field=None, **_kwargs):
        # The editor calls ``ui_registry.get("filename")`` to list UIs; in
        # facade mode it uses these names verbatim (no filename-extension
        # strip), so group names may contain any character, "." included.
        return self._facade._group_names()


class _WidgetFactory:
    """Stands in for ``sb.registered_widgets`` — the editor only constructs a
    ``LineEdit`` (its filter field) through it."""

    @property
    def LineEdit(self):
        from uitk.widgets.lineEdit import LineEdit

        return LineEdit


class RegistrySwitchboardFacade:
    """Switchboard-shaped view over grouped binding entries for the editor."""

    #: Sentinel the editor checks to enter facade mode (skip the Assigned /
    #: Commands pseudo-views and the Switchboard preset row). Cheaper + looser
    #: than an isinstance import cycle.
    _is_manager_facade = True

    def __init__(
        self,
        *,
        groups: Callable[[], List[str]],
        get_entries: Callable[[str], List[dict]],
        apply_binding: Callable[[str, str, str, Optional[str]], None],
        settings_namespace: str = "registry_facade_editor",
        logger_name: str = "uitk.registry_facade_editor",
        editor_title: Optional[str] = None,
        editor_status_text: Optional[str] = None,
        ui_column_label: Optional[str] = None,
        ui_combo_prefix: Optional[str] = None,
        default_show_all: bool = False,
        preset_config: Optional[dict] = None,
    ):
        self._groups = groups
        self._get_entries = get_entries
        self._apply_binding = apply_binding
        # Distinct namespace so this facade's view prefs (filter text, show-all,
        # geometry) don't bleed into the real Switchboard editor's.
        self.settings = SettingsManager(namespace=settings_namespace)
        self.registered_widgets = _WidgetFactory()
        self.registry = _UiRegistryStub(self)
        self.logger = logging.getLogger(logger_name)
        self.loaded_ui = _LoadedUiStub(self)
        self._uis: Dict[str, _GroupUI] = {}

        self.editor_title = editor_title
        self.editor_status_text = editor_status_text
        self.ui_column_label = ui_column_label
        self.ui_combo_prefix = ui_combo_prefix
        self.default_show_all = default_show_all
        self.preset_config = preset_config

    # -- group resolution (each group is one synthetic, always-loaded UI) ---

    def _group_names(self) -> List[str]:
        """The provider's current group names (re-read on every refresh)."""
        return list(self._groups())

    def get_ui(self, name=None):
        """Resolve a group name (or ``_GroupUI``) to its synthetic UI object.

        ``None`` resolves to the first group so editor paths that fall back to
        "the current UI" stay functional. Group UIs are cached per name so row
        identity is stable across repopulates.
        """
        if isinstance(name, _GroupUI):
            return name
        if name is None:
            names = self._group_names()
            if not names:
                return None
            name = names[0]
        if name not in self._uis:
            self._uis[name] = _GroupUI(name, self)
        return self._uis[name]

    def convert_to_legal_name(self, name: str) -> str:
        return name

    def _ui_names_with_shortcut_overrides(self) -> set:
        return set()

    # -- registry ------------------------------------------------------------

    def get_shortcut_registry(self, ui=None) -> List[dict]:
        group = ui.objectName() if isinstance(ui, _GroupUI) else ui
        if group is None:
            names = self._group_names()
            group = names[0] if names else ""
        return self._get_entries(group)

    def get_static_shortcut_registry(self, name=None) -> List[dict]:
        return self.get_shortcut_registry(name)

    # -- edits route back to the provider --------------------------------------

    def set_user_shortcut(self, ui, method: str, sequence: str, scope=None):
        """Commit an editor edit for *method* in *ui*'s group.

        An empty *sequence* is the editor's "clear" (reset-to-unbound); whether
        that is honoured is the provider's call — ``apply_binding`` receives it
        verbatim.
        """
        group = ui.objectName() if isinstance(ui, _GroupUI) else (ui or "")
        self._apply_binding(group, method, sequence, scope)
