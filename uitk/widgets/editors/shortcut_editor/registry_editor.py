# !/usr/bin/python
# coding=utf-8
import html
from typing import Callable, List, Optional
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk
from uitk.widgets.editors.editor_panel import EditorPanel
from uitk.widgets.optionBox.options.filter import FilterOption, NEGATE_PREFIX
from uitk.widgets.comboBox import ComboBox
from uitk.widgets.delegates.row_selection import RowSelectionBorderDelegate
from uitk.widgets.delegates.centered_icon import (
    CenteredIconActionDelegate,
    ICON_OPACITY_ROLE,
)
from uitk.widgets.delegates.shortcut_capture import install_shortcut_capture
from uitk.widgets.mixins.icon_manager import IconManager
from uitk.widgets.separator import Separator


# End-user-facing scopes. Widget/widget_children remain decorator-only.
USER_SCOPES = ("window", "application")
SCOPE_LABELS = {"window": "Win", "application": "App"}
SCOPE_ICONS = {"window": "window", "application": "screen"}
SCOPE_TOOLTIPS = {
    "window": "Window scope — fires only when this UI's window is focused. Click to switch to Application scope.",
    "application": "Application scope — fires anywhere in the host app. Click to switch to Window scope.",
}

# Palette for the per-row rich-text hover card (see _binding_tooltip).
_TT_MUTED = "#9E9E9E"  # description + the "Shortcut" label
_TT_KEY = "#8FD0FF"  # the bound key itself — an accent that reads at a glance


class CollisionConflict:
    """A single conflict reported by a collision checker.

    Attributes:
        source: Where the conflict came from (e.g. "uitk", "maya").
        description: Human-readable explanation.
        breaks_binding: True when accepting the new binding will leave both
            sides in an undefined / unreliable state (e.g. two same-scope same-
            sequence shortcuts that Qt cannot disambiguate). When True the
            editor offers to auto-clear the conflicting binding.
        clear_action: Optional callable that clears the conflicting binding
            when the user accepts the auto-clear path. Required when
            ``breaks_binding`` is True for the conflict to be resolvable.
    """

    def __init__(
        self,
        source: str,
        description: str,
        breaks_binding: bool = False,
        clear_action: Optional[Callable[[], None]] = None,
    ):
        self.source = source
        self.description = description
        self.breaks_binding = breaks_binding
        self.clear_action = clear_action

    def __repr__(self) -> str:
        return (
            f"CollisionConflict(source={self.source!r}, "
            f"description={self.description!r}, "
            f"breaks_binding={self.breaks_binding}, "
            f"clear_action={'set' if self.clear_action else 'None'})"
        )


class ShortcutEditor(EditorPanel):
    """UI for editing global shortcuts with preset support.

    Presets capture all user-customised shortcut bindings across every
    loaded UI in a single JSON file so a named snapshot can be saved,
    restored, renamed, or deleted.
    """

    # UI-less commands (Switchboard.register_command) are listed under a
    # pseudo-UI: ``_COMMANDS_LABEL`` is its combobox item; ``_COMMAND_UI`` is
    # the sentinel stored on a command row's Action item (in place of a real UI
    # name) so the edit/reset/scope/collision handlers route through
    # ``set_command_shortcut`` instead of a UI. The colour-coded tag marks
    # command rows where the UI is normally shown.
    _COMMANDS_LABEL = "⌘ Commands"
    _COMMAND_UI = "\x00command"
    _COMMAND_TAG = "⌘ global"
    _COMMAND_TAG_COLOR = "#42A5F5"

    # A second special combobox entry (not a real UI): a cross-cutting view of
    # every action that currently has a shortcut assigned, across all UIs +
    # commands — the quick "what have I bound?" filter. Special entries sort to
    # the top of the combo and are accent-coloured to set them apart from the
    # plain UI names beneath them.
    _ASSIGNED_LABEL = "★ Assigned"

    # Table columns. Named so the layout (and per-launch column customisation
    # via :meth:`set_columns_hidden`) reads by intent, not magic index. The UI
    # column is shown only in 'show all'; any column may be hidden by a caller
    # launching a focused editor (e.g. a manager view hides Description).
    COL_ACTION = 0
    COL_SHORTCUT = 1
    COL_SCOPE = 2
    COL_RESET = 3
    COL_DESCRIPTION = 4
    COL_UI = 5
    COLUMN_COUNT = 6

    # Custom item-data roles for the icon action cells (Scope / Reset). The Scope
    # cell stores its current scope so an edit reads it back; both store a
    # click-action descriptor (a dict) — or ``None`` when the cell is a fixed /
    # disabled badge — consumed by :meth:`_on_action_cell_clicked`. Reading state
    # off the item (rather than a cell-widget button) lets the cells render as
    # centered, colour-coded icons via :class:`CenteredIconActionDelegate`.
    _SCOPE_ROLE = QtCore.Qt.UserRole + 1
    _ACTION_ROLE = QtCore.Qt.UserRole + 2

    # Single source for the table row height. The icon-only Scope/Reset columns
    # are sized to this same value and their icons are painted centered, so the
    # cell stays a tidy square — change this one value and the row, the two
    # columns, and the icons all scale together.
    ROW_HEIGHT = 22
    # Icon edge for the Scope/Reset action cells (and the table's decoration
    # size). Leaves a few px of breathing room inside the square row.
    ACTION_ICON_SIZE = 14
    # Shared fixed height for the editor's header widgets — the UI combo, the
    # filter field, and the header ⋯-menu controls (show-hidden checkbox, preset
    # combo). Matches the height the other editors' headers use and the header
    # menu's own item height, so everything in the header band lines up.
    HEADER_WIDGET_HEIGHT = 20
    # Scope + Reset are icon-only columns (a square toggle / undo button), so
    # their headers are left blank — the icons and per-control tooltips carry
    # the meaning, and a text title would only crowd the narrow fixed columns.
    _COLUMN_LABELS = ("Action", "Shortcut", "", "", "Description", "UI")

    def __init__(self, switchboard, parent=None, focus=None):
        super().__init__(
            title="Shortcut Editor",
            status_text="Customize keyboard shortcuts.",
            parent=parent,
        )
        self.sb = switchboard
        self.resize(600, 600)
        # Focused launch (e.g. ``focus="commands"`` → a single-purpose global-
        # shortcuts panel): pin a view + hide the UI selector. Applied in
        # showEvent once the UI list exists (see :meth:`_apply_focus`).
        self._focus = focus
        # Manager mode: the editor is rendering a standalone
        # ``ShortcutManager`` (via :class:`ManagerSwitchboardFacade`) rather than
        # a real Switchboard — there are no UIs, commands or presets, and each
        # binding's scope is fixed by its owner widget. The single unified editor
        # serves both; the facade flag drives the few mode-specific skips
        # (preset row, special combo views) so the real-Switchboard path stays
        # byte-for-byte unchanged.
        self._manager_mode = bool(getattr(switchboard, "_is_manager_facade", False))
        # Columns hidden for this launch (see :meth:`set_columns_hidden`). The UI
        # column is managed separately by the show-all toggle and is not tracked
        # here.
        self._hidden_columns: set = set()

        # Session settings for the filter row (text / enabled). Branch so keys
        # don't collide with other editors sharing the store.
        self._settings = self.sb.settings.branch("shortcut_editor")
        self._migrate_legacy_settings_branch()
        # Remember a user-adjusted window size / position across sessions.
        # Keyed by launch variant so the full editor and the focused
        # "commands" panel — which share this settings branch — don't clobber
        # each other's size. (The constructor's resize(600, 600) above stays
        # the first-run default; a saved size overrides it on show.)
        self.persist_geometry(
            self._settings, key=f"window_geometry.{self._focus or 'main'}"
        )
        self._show_all = bool(self._settings.value("show_all", False))
        if self._focus:
            self._show_all = False  # a focused launch pins one view, never "all UIs"
        # Hidden bindings (registered ``hidden=True`` or hidden post-hoc via
        # ``set_binding_hidden``) are omitted from every view unless this is on.
        # They remain in the registry — collision detection always sees them.
        self._show_hidden = bool(self._settings.value("show_hidden", False))

        # UI selection. A uitk ComboBox carries the "Target UI:" label as a
        # display-only prefix on the current item, so there's no separate
        # QLabel and the prefix never appears in the dropdown (item text/data
        # stay clean — selection logic still reads currentText()).
        self.cmb_ui = ComboBox()
        self.cmb_ui.setObjectName("cmb_target_ui")
        self.cmb_ui.setFixedHeight(self.HEADER_WIDGET_HEIGHT)
        self.cmb_ui.current_text_prefix = "" if self._focus else "Target UI:  "
        self.cmb_ui.currentTextChanged.connect(self.populate)
        # Option-box toggle: switch between filtering by the selected UI and
        # listing every UI's slots at once (see _add_show_all_toggle). Skipped in
        # a focused launch — the combo is a single locked entry there, so a
        # show-all toggle (and its option-box overlay) would have nothing to do.
        if not self._focus:
            self._add_show_all_toggle()
        self.cmb_ui.setEnabled(not self._show_all)
        self.body_layout.addWidget(self.cmb_ui)

        # Filter row — a shared filter LineEdit whose option-box carries a
        # filter on/off toggle (silence the query without clearing the text),
        # mirroring the UI browser. Matches hide non-matching rows in place
        # (cheap) rather than rebuilding the table.
        self.le_filter = self.sb.registered_widgets.LineEdit()
        self.le_filter.setObjectName("le_shortcut_filter")
        self.le_filter.setPlaceholderText(
            "Filter actions (exact; * for substring; ! excludes)"
        )
        self.le_filter.setToolTip(
            "Filter the shortcut list by action name / description.\n"
            "\n"
            "• Multi-term: separate terms with commas — any matching term\n"
            "  keeps the row.\n"
            "• Matching is exact unless you add wildcards:\n"
            "    *  any sequence (*move* = contains)   ?  any single char\n"
            "    [seq]  any character in the set.\n"
            "• Prefix a term with ! to exclude it, e.g.  *move*, !*mirror*\n"
            "  keeps rows containing 'move' but drops any containing 'mirror'.\n"
            "• Click the filter icon to toggle filtering on/off without\n"
            "  clearing the text."
        )
        self.le_filter.option_box.set_filter(
            settings=self._settings,
            text_key="filter.text",
            on_changed=self._apply_filter,
            enabled_key="filter.enabled",
            on_toggled=lambda _on: self._apply_filter(),
        )
        self._filter = self.le_filter.option_box.find_option(FilterOption)
        self.le_filter.setFixedHeight(self.HEADER_WIDGET_HEIGHT)
        self.body_layout.addWidget(self.le_filter)

        # Collision checkers — registered by host (tentacle/mayatk) to detect
        # external conflicts (Maya hotkey sets, etc.). Built-in internal
        # checker is registered below.
        self._collision_checkers: List[Callable] = []
        self.add_collision_checker(self._builtin_internal_collision_checker)

        # Table
        self.table = QtWidgets.QTableWidget()
        # The UI column is shown only in 'show all' mode (see _set_show_all).
        self.table.setColumnCount(self.COLUMN_COUNT)
        self.table.setHorizontalHeaderLabels(list(self._COLUMN_LABELS))
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        # The themed ``QHeaderView::section { padding: 4px }`` pushes the default
        # minimum section size up (~30px), which would clamp the icon columns'
        # ``setColumnWidth(ROW_HEIGHT)``. Lower the floor so their fixed widths
        # are honoured exactly (mirrors ``TableActions._apply_sizing``).
        header.setMinimumSectionSize(self.ROW_HEIGHT)
        header.setSectionResizeMode(
            self.COL_ACTION, QtWidgets.QHeaderView.ResizeToContents
        )
        # Shortcut column is fixed at a width sized to the longest sequence
        # users realistically bind (full modifier chord + a long key name) so
        # it stops eating the slack a Stretch column would — the Description
        # column (also Stretch, below) absorbs that space instead. The actual
        # sequence text is short and centered; the full binding + description
        # are surfaced on hover via the per-row tooltips in ``_build_row``.
        header.setSectionResizeMode(self.COL_SHORTCUT, QtWidgets.QHeaderView.Fixed)
        self._size_shortcut_column()
        # Scope and Reset are fixed-width square cells (== ROW_HEIGHT) holding a
        # centered icon; Reset sits between Scope and Description, which (Stretch)
        # absorbs the remaining horizontal space.
        header.setSectionResizeMode(self.COL_SCOPE, QtWidgets.QHeaderView.Fixed)
        self.table.setColumnWidth(self.COL_SCOPE, self.ROW_HEIGHT)
        header.setSectionResizeMode(self.COL_RESET, QtWidgets.QHeaderView.Fixed)
        self.table.setColumnWidth(self.COL_RESET, self.ROW_HEIGHT)
        header.setSectionResizeMode(
            self.COL_DESCRIPTION, QtWidgets.QHeaderView.Stretch
        )
        # UI column — sized to its content, revealed only in 'show all' mode.
        header.setSectionResizeMode(
            self.COL_UI, QtWidgets.QHeaderView.ResizeToContents
        )
        self.table.setColumnHidden(self.COL_UI, not self._show_all)
        self.table.verticalHeader().setVisible(False)
        # Match the UI Browser table's row height for a consistent look. The
        # Scope/Reset columns are sized to this same value (square icon cells).
        self.table.verticalHeader().setDefaultSectionSize(self.ROW_HEIGHT)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        # Explicit double-click only: the default triggers include
        # AnyKeyPressed/EditKeyPressed, so a stray keystroke on a selected
        # row would open the capture editor and silently rebind the
        # shortcut. install_shortcut_capture opens the editor on double-click
        # regardless of triggers.
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        # SelectRows + the global QSS per-cell ``:selected`` border would
        # draw inner seams between adjacent cells of a selected row; the
        # row-spanning delegate paints one continuous outline instead.
        # Decoration size for the Scope/Reset icon cells (the delegate reads
        # ``option.decorationSize`` to size the centered pixmap).
        self.table.setIconSize(
            QtCore.QSize(self.ACTION_ICON_SIZE, self.ACTION_ICON_SIZE)
        )
        self.table.setItemDelegate(RowSelectionBorderDelegate(self.table))
        # Scope and Reset render as centered, colour-coded item icons (not cell-
        # widget buttons) via CenteredIconActionDelegate — the icon is painted
        # centered in the cell, so the themed ``::item`` horizontal padding can't
        # offset/clip it and no per-view padding override is needed (which would
        # have stripped the text columns' breathing room). Clicks dispatch through
        # the table's cellClicked signal (see _on_action_cell_clicked).
        self._icon_action_delegate = CenteredIconActionDelegate(self.table)
        self.table.setItemDelegateForColumn(self.COL_SCOPE, self._icon_action_delegate)
        self.table.setItemDelegateForColumn(self.COL_RESET, self._icon_action_delegate)
        self.table.cellClicked.connect(self._on_action_cell_clicked)
        # The Shortcut column (1) is edited in-cell: double-click opens a
        # key-capture editor instead of a modal dialog. ``bordered`` keeps
        # the row-spanning selection outline on that column.
        install_shortcut_capture(
            self.table,
            self.COL_SHORTCUT,
            lambda row, _col, seq: self._apply_shortcut(row, seq),
            bordered=True,
        )
        self.body_layout.addWidget(self.table, 1)
        # A focused 'commands' launch drops the columns that don't apply to the
        # global triggers: Scope (commands are always app-scoped), Description
        # (folded into the Action label), and UI (they're UI-less). The combo is
        # already stripped to the single Commands view.
        if self._focus == "commands":
            self._hidden_columns.update(
                {self.COL_SCOPE, self.COL_DESCRIPTION, self.COL_UI}
            )
        # Per-launch column customisation (e.g. a focused manager view hides
        # Description) is applied last so it overrides the defaults above.
        self._apply_hidden_columns()

        # Header ⋯-menu: titled View / Presets sections (presets at the bottom).
        # Built after the table so the preset row's dirty-check has everything it
        # needs, and once so section order is explicit.
        self._build_header_menu()

        # Body layout spacing (2px) is set by EditorPanel; tighten every
        # nested control row (preset row, ui_layout) to 1px for density.
        self.tighten_sublayouts(1)

        self.refresh_ui_list()

    def _migrate_legacy_settings_branch(self) -> None:
        """Carry this editor's persisted UI prefs (filter text/toggle, show-all)
        from the pre-rename ``hotkey_editor`` settings branch into the current
        ``shortcut_editor`` branch, once.

        No-op once the new branch holds any key (so a later edit is never
        clobbered) or when there's nothing legacy to copy. Part of the
        hotkey->shortcut rename; safe to drop once no user carries the old
        branch.
        """
        new = self._settings
        if new.keys():
            return
        old = self.sb.settings.branch("hotkey_editor")
        for key in old.keys():
            new.setValue(key, old.value(key))

    # ------------------------------------------------------------------
    # Preset hooks
    # ------------------------------------------------------------------

    def export_preset_data(self):
        return self.export_shortcuts()

    def import_preset_data(self, data):
        self.import_shortcuts(data)
        self.populate()

    # ------------------------------------------------------------------
    # Shortcut export / import
    # ------------------------------------------------------------------

    def export_shortcuts(self, loaded_only: bool = False) -> dict:
        """Export all user-customised shortcuts across loaded UIs.

        Each binding exports as ``{"seq": str, "scope": str}``. The legacy
        string-only shape (``method_name: sequence``) remains supported on
        import for back-compat with older presets.

        Parameters:
            loaded_only: When True, read only UIs already instantiated this
                session (``peek``, never ``get_ui``) — an unbuilt UI has no
                live edits to capture. Used for the cheap dirty-check
                (:attr:`PresetManager.modified_value_provider`); save passes
                False so the preset is a complete snapshot of every UI.

        Returns:
            ``{ui_name: {method_name: {"seq": str, "scope": str}, ...}, ...}``
        """
        data: dict = {}
        for ui_name in self._registered_ui_names():
            target_ui = (
                self.sb.loaded_ui.peek(ui_name)
                if loaded_only
                else self.sb.get_ui(ui_name)
            )
            if not target_ui:
                continue
            registry = self.sb.get_shortcut_registry(target_ui)
            if not registry:
                continue
            ui_data: dict = {}
            for entry in registry:
                current = entry.get("current") or ""
                scope = entry.get("current_scope", "window")
                ui_data[entry["method"]] = {"seq": current, "scope": scope}
            if ui_data:
                data[ui_name] = ui_data

        # UI-less commands are always available (no build needed), so they're
        # captured regardless of loaded_only — under the _COMMAND_UI key so
        # import_shortcuts routes them back through set_command_shortcut.
        cmd_data = {
            e["method"]: {
                "seq": e.get("current") or "",
                "scope": e.get("current_scope", "application"),
            }
            for e in self._command_entries()
        }
        if cmd_data:
            data[self._COMMAND_UI] = cmd_data
        return data

    def import_shortcuts(self, data: dict) -> int:
        """Bulk-apply shortcut bindings from a preset dict.

        Accepts both the new ``{"seq": ..., "scope": ...}`` shape and the
        legacy string shape where the value is the sequence directly.

        Args:
            data: ``{ui_name: {method_name: binding, ...}, ...}``
                where ``binding`` is either a string (legacy) or
                ``{"seq": str, "scope": str}`` (current).

        Returns:
            Number of shortcuts updated.
        """
        applied = 0
        for ui_name, bindings in data.items():
            if not isinstance(bindings, dict):
                continue
            is_command = ui_name == self._COMMAND_UI
            target_ui = None if is_command else self.sb.get_ui(ui_name)
            if not is_command and not target_ui:
                continue
            for method_name, binding in bindings.items():
                if isinstance(binding, dict):
                    sequence = binding.get("seq", "")
                    scope = binding.get("scope")
                else:
                    sequence = binding or ""
                    scope = None  # legacy: preserve decorator default scope
                if is_command:
                    self.sb.set_command_shortcut(method_name, sequence, scope)
                else:
                    self.sb.set_user_shortcut(target_ui, method_name, sequence, scope)
                applied += 1
        return applied

    # ------------------------------------------------------------------
    # Show / refresh
    # ------------------------------------------------------------------

    def showEvent(self, event):
        """Refresh data each time the editor is shown."""
        super().showEvent(event)
        # Re-measure the Shortcut column against the now-themed font.
        self._size_shortcut_column()
        # Preserve current selection if possible
        current_ui = self.cmb_ui.currentText()
        self.refresh_ui_list()
        # Restore selection
        idx = self.cmb_ui.findText(current_ui)
        if idx >= 0:
            self.cmb_ui.setCurrentIndex(idx)
        # Always repopulate table with fresh shortcut data
        self.populate()

    def refresh_ui_list(self):
        """Populate the UI combobox: special views first, then every registered UI.

        Lists names directly from the ui_registry (populated at startup) without
        instantiating any widgets — the actual UI is built only when the user
        selects it (see ``populate``). The cross-cutting special views (Assigned,
        Commands) sort to the top and are accent-coloured; the initial *selection*
        still lands on the first real UI so the editor opens on a concrete UI,
        not a filtered view.
        """
        self.cmb_ui.clear()

        if self._focus == "commands":
            # Focused launch: the combo is a single, locked entry (⌘ Commands) —
            # not a UI switcher. Populate just that (no other UIs, no show-all
            # option), so there's nothing to switch and no orphaned option-box
            # overlay: the combo stays visible, stripped to the one view at hand.
            specials = [(self._COMMANDS_LABEL, "The global (UI-less) command triggers.")]
            self.cmb_ui.addItem(self._COMMANDS_LABEL)
            self._style_special_items(specials)
            self.cmb_ui.blockSignals(True)
            self.cmb_ui.setCurrentIndex(0)
            self.cmb_ui.blockSignals(False)
            self.populate()
            return

        real_names = self._registered_ui_names()
        specials = self._special_entries(real_names)
        labels = [label for label, _tip in specials] + real_names
        self.cmb_ui.addItems(labels)
        self._style_special_items(specials)

        if not labels:
            return
        # Open on the first real UI (after the specials), falling back to item 0
        # when there are no real UIs (a commands-only host). Block signals across
        # the index move so populate() runs exactly once below (and setting the
        # index to its current value would emit nothing at all).
        default_idx = len(specials) if real_names else 0
        self.cmb_ui.blockSignals(True)
        self.cmb_ui.setCurrentIndex(default_idx)
        self.cmb_ui.blockSignals(False)
        self.populate()

    def _command_entries(self) -> list:
        """Command registry entries, or [] when the switchboard has none."""
        get = getattr(self.sb, "get_command_registry", None)
        return get() if callable(get) else []

    def _entry_visible(self, entry) -> bool:
        """Whether ``entry`` shows in the current view: always when 'Show hidden'
        is on, otherwise only non-hidden entries. The one visibility predicate,
        shared by :meth:`_visible_entries` and :meth:`_gather_all_pairs`."""
        return self._show_hidden or not entry.get("hidden")

    def _visible_entries(self, entries) -> list:
        """Drop ``hidden`` entries unless the 'Show hidden' toggle is on.

        The single visibility chokepoint for the *display* paths (single-UI,
        Commands, show-all, assigned). Deliberately NOT applied in
        :meth:`_registry_for`, which the collision checker shares — a hidden
        binding must still block a colliding assignment even while invisible.
        """
        return [e for e in entries if self._entry_visible(e)]

    def _registered_ui_names(self) -> list:
        """Sorted, de-duplicated legal names of every registered UI.

        Read straight from the ui_registry (populated at startup) — no widget is
        instantiated. Single source for the combobox list, the show-all/assigned
        gather, the preset export, and the internal collision scan.
        """
        filenames = self.sb.registry.ui_registry.get("filename") or []
        return sorted(
            set(
                self.sb.convert_to_legal_name(name.rsplit(".", 1)[0])
                for name in filenames
            )
        )

    def _special_entries(self, real_names: list) -> list:
        """The non-UI 'pseudo-UI' combobox entries, shown at the top.

        Returns ``[(label, tooltip), ...]``:
          - 'Assigned' — every action with a shortcut, across all UIs + commands.
          - 'Commands' — the UI-less global commands, when any are registered.

        Empty when the host has neither UIs nor commands (nothing to view).
        """
        if self._manager_mode:
            # A standalone manager has a single binding set — no cross-cutting
            # 'Assigned' / 'Commands' pseudo-UIs to switch between.
            return []
        has_commands = bool(self._command_entries())
        entries = []
        if real_names or has_commands:
            entries.append(
                (
                    self._ASSIGNED_LABEL,
                    "Show only actions that have a shortcut assigned — "
                    "across every UI and command.",
                )
            )
        if has_commands:
            entries.append(
                (
                    self._COMMANDS_LABEL,
                    "Show the global commands (not tied to any UI).",
                )
            )
        return entries

    def _style_special_items(self, specials: list) -> None:
        """Accent-colour the leading special combo entries + attach their tooltips.

        Sets them apart from the plain UI names beneath them: the icon prefix
        (★ / ⌘) already differentiates, and the colour reinforces it in the
        dropdown. Tints the text via ``ForegroundRole`` (keeps the themed font,
        unlike a full ``FontRole`` override).
        """
        brush = QtGui.QBrush(QtGui.QColor(self._COMMAND_TAG_COLOR))
        for i, (_label, tooltip) in enumerate(specials):
            self.cmb_ui.setItemData(i, brush, QtCore.Qt.ForegroundRole)
            if tooltip:
                self.cmb_ui.setItemData(i, tooltip, QtCore.Qt.ToolTipRole)

    def populate(self):
        """Populate the table with shortcuts for the selected UI.

        Loads the UI on demand if it hasn't been instantiated yet —
        ``peek`` first to skip work when already loaded, otherwise
        ``get_ui`` to build it. Loading a single UI on explicit user
        selection is safe; the host-shutdown crash only manifests when
        force-instantiating every registered UI at once (which is why
        ``refresh_ui_list`` does not).
        """
        if self._show_all:
            self._populate_all()
            return

        ui_name = self.cmb_ui.currentText()
        if ui_name == self._ASSIGNED_LABEL:
            self._populate_assigned()
            return
        if ui_name == self._COMMANDS_LABEL:
            self._populate_commands()
            return

        self.table.setRowCount(0)
        # The UI column is hidden in the single-UI view; re-assert it in case
        # the Commands view (which reveals it) was shown just before.
        self.table.setColumnHidden(self.COL_UI, not self._show_all)
        if not ui_name:
            return

        target_ui = self.sb.loaded_ui.peek(ui_name) or self.sb.get_ui(ui_name)
        if target_ui is None:
            self._show_message_row(
                f"Could not load UI '{ui_name}'.",
                status=f"Could not load '{ui_name}'.",
            )
            return

        registry = self._visible_entries(self.sb.get_shortcut_registry(target_ui))

        # Clear any previous span
        self.table.setSpan(0, 0, 1, 1)

        if not registry:
            self._show_message_row(
                "No shortcuts defined for this UI.", status="0 shortcuts"
            )
            return

        self.table.setRowCount(len(registry))
        modified = self._modified_count(registry)
        status = f"{len(registry)} shortcuts"
        if modified:
            status += f" ({modified} customised)"
        self._set_status(status)

        for i, entry in enumerate(registry):
            self._build_row(i, ui_name, entry)

        # Re-apply the active text filter to the freshly built rows so a UI
        # switch keeps the user's filter in effect.
        self._apply_filter()

    def _registry_for(self, ui_name: str) -> list:
        """Shortcut-registry entries for ``ui_name`` without ever building it:
        the authoritative live registry when the UI is loaded, else the
        no-build static registry (``.ui`` XML + persisted settings).

        Single source for the loaded-vs-static decision, shared by the
        'show all' / 'assigned' gather and the internal collision checker —
        both must stay force-build-free (building every registered UI was the
        host-shutdown crash / native-menu MEL re-run).
        """
        loaded = self.sb.loaded_ui.peek(ui_name)
        if loaded is not None:
            return self.sb.get_shortcut_registry(loaded)
        return self.sb.get_static_shortcut_registry(ui_name)

    def _gather_all_pairs(self) -> list:
        """``(ui_name, entry)`` for every registered UI's slots + UI-less commands.

        A row's UI is instantiated only when its binding is edited — the gather
        itself never force-builds (see :meth:`_registry_for`). Shared by the
        'show all' and 'assigned' views.
        """
        pairs = []  # (ui_name, entry)
        for name in self._registered_ui_names():
            pairs.extend((name, e) for e in (self._registry_for(name) or []))
        # UI-less commands round out the list, tagged via _build_row.
        pairs.extend((self._COMMAND_UI, e) for e in self._command_entries())
        # Honour the 'Show hidden' toggle for these cross-cutting views too.
        return [(n, e) for (n, e) in pairs if self._entry_visible(e)]

    def _populate_all(self):
        """List slots for *every* registered UI at once (plus commands)."""
        self._populate_pairs(
            self._gather_all_pairs(),
            empty_message="No shortcuts found.",
            status_noun="shortcuts",
        )

    def _populate_assigned(self):
        """List only actions that currently have a shortcut, across all UIs +
        commands — the 'Assigned' cross-cutting view."""
        assigned = [
            (name, entry)
            for name, entry in self._gather_all_pairs()
            if entry.get("current")
        ]
        self._populate_pairs(
            assigned,
            empty_message="No shortcuts assigned yet.",
            status_noun="assigned shortcuts",
        )

    def _populate_pairs(self, pairs, *, empty_message: str, status_noun: str) -> None:
        """Render a flat ``(ui_name, entry)`` list spanning many UIs.

        Shared by the 'show all' and 'assigned' views: reveals the UI column (so
        each row's origin is visible), handles the empty state, and footers a
        count.
        """
        self.table.setRowCount(0)
        self.table.setSpan(0, 0, 1, 1)
        # These views span many UIs, so the per-row UI column is meaningful here
        # even outside 'show all' (the single-UI / Commands views manage it too).
        self.table.setColumnHidden(self.COL_UI, False)

        if not pairs:
            self._show_message_row(empty_message, status=f"0 {status_noun}")
            return

        self.table.setRowCount(len(pairs))
        ui_count = len({n for n, _e in pairs if n != self._COMMAND_UI})
        modified = self._modified_count(e for _n, e in pairs)
        status = f"{len(pairs)} {status_noun}"
        if ui_count:
            status += f" across {ui_count} UIs"
        if modified:
            status += f" ({modified} customised)"
        self._set_status(status)

        for i, (name, entry) in enumerate(pairs):
            self._build_row(i, name, entry)

        self._apply_filter()

    def _populate_commands(self):
        """List only the UI-less commands (the 'Commands' pseudo-UI view)."""
        self.table.setRowCount(0)
        self.table.setSpan(0, 0, 1, 1)
        # Reveal the UI column so the colour-coded command tag shows even in the
        # single-UI view (normally hidden outside 'show all') — but keep it hidden
        # in a focused launch, which drops the UI column entirely.
        if not self._focus:
            self.table.setColumnHidden(self.COL_UI, False)

        registry = self._visible_entries(self._command_entries())
        if not registry:
            self._show_message_row("No commands registered.", status="0 commands")
            return

        self.table.setRowCount(len(registry))
        modified = self._modified_count(registry)
        status = f"{len(registry)} commands"
        if modified:
            status += f" ({modified} customised)"
        self._set_status(status)

        for i, entry in enumerate(registry):
            self._build_row(i, self._COMMAND_UI, entry)

        self._apply_filter()

    def _build_row(self, i: int, ui_name: str, entry: dict) -> None:
        """Build table row ``i`` for ``entry`` belonging to ``ui_name``.

        The row carries its UI name (on the Action item's ``UserRole``) so the
        edit / scope / reset handlers act on the right UI in 'show all' mode and
        lazily instantiate it via ``get_ui`` only when actually edited.
        """
        method_name = entry["method"]
        current_seq = entry["current"] or ""
        default_seq = entry["default"] or ""
        # Composed tooltip: action name + description + the bound sequence.
        # Surfaced on the Shortcut and Description cells (both can elide/narrow)
        # so the full context is reachable on hover. The Action cell keeps its
        # "Method: …" tooltip — handlers and a test parse that.
        row_tooltip = self._binding_tooltip(entry["name"], entry["doc"], current_seq)
        current_scope = entry.get("current_scope", "window")
        default_scope = entry.get("default_scope", "window")
        # A command entry carries no UI; its rows store the _COMMAND_UI sentinel
        # so the edit handlers route through set_command_shortcut.
        is_command = bool(entry.get("command"))
        row_ui = self._COMMAND_UI if is_command else ui_name
        # A non-editable binding (registered/​set ``editable=False``) is a fixed,
        # semantic key: shown for discoverability + collision-checking but not
        # rebindable. Drop the in-cell edit flag and disable the scope/reset
        # controls so the row is read-only.
        editable = bool(entry.get("editable", True))

        # Action name — carries the row's UI (or command sentinel) for handlers.
        item_name = QtWidgets.QTableWidgetItem(entry["name"])
        item_name.setToolTip(f"Method: {method_name}")
        item_name.setData(QtCore.Qt.UserRole, row_ui)
        item_name.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
        self.table.setItem(i, self.COL_ACTION, item_name)

        # Shortcut (edited in-cell via the capture delegate)
        item_seq = QtWidgets.QTableWidgetItem(current_seq)
        item_seq.setTextAlignment(QtCore.Qt.AlignCenter)
        seq_flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        if editable:
            seq_flags |= QtCore.Qt.ItemIsEditable
            item_seq.setToolTip(row_tooltip)
        else:
            item_seq.setToolTip("Fixed key — not user-rebindable.")
        item_seq.setFlags(seq_flags)
        if current_seq != default_seq:
            item_seq.setForeground(QtGui.QBrush(QtGui.QColor("#4CAF50")))  # modified
        self.table.setItem(i, self.COL_SHORTCUT, item_seq)

        # Scope (Window / Application) — a centered, colour-coded icon cell.
        # Decorator-only scopes (widget, widget_children) and not-yet-bound /
        # fixed rows render as a muted, non-interactive icon so users see what's
        # set without being able to override unsafely. Scope only means something
        # once a sequence exists to fire, and it gates whether reusing the key is
        # a collision.
        self._set_scope_cell(
            i,
            current_scope,
            default_scope,
            has_sequence=bool(current_seq),
            editable=editable,
            scope_editable=bool(entry.get("scope_editable", True)),
            is_command=is_command,
        )

        # Reset (sits between Scope and Description) — centered undo icon, muted
        # and inert when the binding is already at its default or not editable.
        at_default = current_seq == default_seq and current_scope == default_scope
        self._set_reset_cell(
            i, default_seq, default_scope, enabled=editable and not at_default
        )

        # Description
        item_doc = QtWidgets.QTableWidgetItem(entry["doc"])
        item_doc.setToolTip(row_tooltip)
        item_doc.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
        self.table.setItem(i, self.COL_DESCRIPTION, item_doc)

        # UI column (revealed in 'show all' and the Commands view). Command
        # rows show a colour-coded "no UI" tag in place of a UI name.
        if is_command:
            item_ui = QtWidgets.QTableWidgetItem(self._COMMAND_TAG)
            item_ui.setForeground(QtGui.QBrush(QtGui.QColor(self._COMMAND_TAG_COLOR)))
            item_ui.setToolTip("Global command — not tied to any UI.")
        else:
            item_ui = QtWidgets.QTableWidgetItem(ui_name)
        item_ui.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
        self.table.setItem(i, self.COL_UI, item_ui)

    def _size_shortcut_column(self) -> None:
        """Width the Shortcut column to the longest chord users realistically bind.

        Recomputed on show (not just at construction) so the *themed* table font
        — applied via QSS after ``__init__`` — is measured, not the default app
        font (the repo's "measure before polish" gotcha).
        """
        fm = self.table.fontMetrics()
        advance = getattr(fm, "horizontalAdvance", None) or fm.width
        self.table.setColumnWidth(
            self.COL_SHORTCUT, advance("Ctrl+Shift+Alt+Backspace") + 24
        )

    @staticmethod
    def _binding_tooltip(name: str, doc: str, seq: str) -> str:
        """Rich-text hover card for a row: bold action name, muted description,
        then the bound key set off on its own line — colour-coded, monospaced
        and spaced so it reads at a glance.

        Keeps the full description reachable when the Description cell elides and
        the assigned sequence reachable beside the narrow Shortcut cell. Returned
        as HTML (Qt renders a tooltip as rich text when it contains markup);
        inputs are escaped so a stray ``<`` / ``&`` can't break the layout.
        """
        head = [f"<b>{html.escape(name)}</b>"]
        if doc:
            head.append(f"<span style='color:{_TT_MUTED};'>{html.escape(doc)}</span>")

        if seq:
            key = (
                f"<span style='color:{_TT_KEY}; font-family:monospace; "
                f"font-weight:bold;'>{html.escape(seq)}</span>"
            )
        else:
            key = f"<i style='color:{_TT_MUTED};'>Unassigned</i>"

        return (
            f"<div>{'<br>'.join(head)}"
            f"<div style='margin-top:5px; color:{_TT_MUTED};'>"
            f"Shortcut&nbsp;&nbsp;{key}</div></div>"
        )

    def _show_message_row(self, message: str, status: str) -> None:
        """Show a single spanning info row (empty / load-failure states)."""
        self.table.setRowCount(1)
        item = QtWidgets.QTableWidgetItem(message)
        item.setFlags(QtCore.Qt.ItemIsEnabled)
        self.table.setItem(0, 0, item)
        self.table.setSpan(0, 0, 1, self.table.columnCount())
        self._set_status(status)

    @staticmethod
    def _modified_count(entries) -> int:
        """Number of entries whose sequence or scope differs from its default."""
        return sum(
            1
            for e in entries
            if (e.get("current") or "") != (e.get("default") or "")
            or (e.get("current_scope") or "") != (e.get("default_scope") or "")
        )

    def _row_ui_name(self, row: int) -> str:
        """The UI a row belongs to (stored on its Action item).

        Falls back to the combobox selection for safety; real rows always carry
        it, a message row would not.
        """
        item = self.table.item(row, self.COL_ACTION)
        name = item.data(QtCore.Qt.UserRole) if item is not None else None
        return name or self.cmb_ui.currentText()

    def _add_show_all_toggle(self) -> None:
        """Add the 'show all UIs' toggle to the Target-UI combobox's option box.

        When on, the table lists every registered UI's slots at once and the
        combobox is disabled — there's nothing to filter by. The combo being
        disabled would normally cascade-disable its option buttons too (see
        ``OptionBoxContainer._sync_option_buttons_enabled``); the toggle opts out
        via ``keep_enabled_when_wrapped_disabled`` so it stays clickable and the
        user can re-enable the combo.

        The toggle's ``is_on`` means *"filtering by the selected UI"* (the combo
        is enabled) — the inverse of ``show_all`` — so the icon goes error-red in
        the off / show-all state, matching the disabled combo (red == disabled).
        """
        from uitk.widgets.optionBox.options.toggle import ToggleOption

        toggle = ToggleOption(
            wrapped_widget=self.cmb_ui,
            icon="asterisk",
            tooltip_on="Filtering by the selected UI. Click to show all UIs.",
            tooltip_off="Showing all UIs (combo disabled). Click to filter by the selected UI.",
            initial=not self._show_all,
            keep_enabled_when_wrapped_disabled=True,
            settings_key=False,
        )
        toggle.toggled.connect(lambda filtering: self._set_show_all(not filtering))
        self.cmb_ui.option_box.add_option(toggle)

    def _set_show_all(self, show_all: bool) -> None:
        """Switch between the single-UI and all-UIs views."""
        self._show_all = bool(show_all)
        self._settings.setValue("show_all", self._show_all)
        self.cmb_ui.setEnabled(not self._show_all)
        self.table.setColumnHidden(self.COL_UI, not self._show_all)
        self.populate()

    def _build_header_menu(self) -> None:
        """Populate the header ⋯-menu with titled sections.

        Order top→bottom: a **View** section (the 'Show hidden bindings' toggle)
        and, for a real Switchboard, a **Presets** section pinned to the bottom
        (the preset combo + its toolbar). Titled :class:`Separator`\\ s label each
        section. The preset row is added last so it sits at the bottom regardless
        of the other items. Ensures the header's menu button exists first — in
        manager mode the preset row (which normally creates it) is skipped.
        """
        if "menu" not in self.header.buttons:
            self.header.config_buttons("menu", *self.header.buttons.keys())
        menu = self.header.menu

        # View section.
        menu.add(Separator(title="View"))
        cb = QtWidgets.QCheckBox("Show hidden bindings")
        cb.setToolTip(
            "Reveal bindings registered hidden (functional / semantic keys)."
        )
        cb.setFixedHeight(self.HEADER_WIDGET_HEIGHT)
        cb.setChecked(self._show_hidden)  # set before connect so it doesn't fire
        cb.toggled.connect(self._set_show_hidden)
        menu.add(cb)
        self._show_hidden_checkbox = cb

        # Presets section, pinned to the bottom of the menu (real Switchboard
        # only — a standalone manager has no presets). The dirty-check reads only
        # already-loaded UIs (peek, no build); save still captures every UI.
        if not self._manager_mode:
            menu.add(Separator(title="Presets"))
            self.init_preset_row(
                "shortcut_presets",
                modified_value_provider=lambda: self.export_shortcuts(
                    loaded_only=True
                ),
                in_header_menu=True,
            )
            self._cmb_preset.setFixedHeight(self.HEADER_WIDGET_HEIGHT)

    def _set_show_hidden(self, show_hidden: bool) -> None:
        """Reveal/omit ``hidden=True`` bindings across every view."""
        self._show_hidden = bool(show_hidden)
        self._settings.setValue("show_hidden", self._show_hidden)
        self.populate()

    def _refresh_preset_state(self) -> None:
        """Refresh the preset row's dirty indicator, if there is one.

        Manager mode skips the preset row (a standalone manager has no presets),
        so ``_preset_mgr`` is None then — guard rather than special-case each
        edit handler."""
        if getattr(self, "_preset_mgr", None) is not None:
            self._preset_mgr.refresh_modified_state()

    # ------------------------------------------------------------------
    # Column customisation (focused launches)
    # ------------------------------------------------------------------

    def set_columns_hidden(self, columns, hidden: bool = True) -> None:
        """Show/hide table columns for a focused editor launch.

        Pass one or more ``COL_*`` constants (e.g. ``COL_DESCRIPTION``) to tailor
        the editor to a caller's needs — e.g. a standalone ``ShortcutManager``
        view hides the Description column. The choice persists across repopulates
        (it's column state, not row state). The UI column stays under the
        show-all toggle's control and should not be set here.
        """
        if isinstance(columns, int):
            columns = (columns,)
        for col in columns:
            if col == self.COL_UI:
                continue  # owned by the show-all toggle, not per-launch config
            if hidden:
                self._hidden_columns.add(col)
            else:
                self._hidden_columns.discard(col)
        self._apply_hidden_columns()

    def _apply_hidden_columns(self) -> None:
        """Apply the configured hidden columns to the table."""
        for col in range(self.COLUMN_COUNT):
            # The UI column is normally owned by the show-all toggle — except in a
            # focused launch (no toggle), where it's part of the hidden config.
            if col == self.COL_UI and not self._focus:
                continue
            self.table.setColumnHidden(col, col in self._hidden_columns)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _filter_patterns(self):
        """Active include patterns, or ``None`` when filtering is inert.

        Delegates to the :class:`FilterOption` — ``None`` means "show
        everything" (filter disabled or text empty); otherwise the field text as
        glob patterns. The on/off state + persistence live in the option.
        """
        return self._filter.patterns()

    def _row_haystack(self, row: int) -> str:
        """Text searched for a row: action name + description (+ UI when shown)."""
        cols = (
            (self.COL_ACTION, self.COL_DESCRIPTION, self.COL_UI)
            if self._show_all
            else (self.COL_ACTION, self.COL_DESCRIPTION)
        )
        parts = []
        for col in cols:
            item = self.table.item(row, col)
            if item is not None:
                parts.append(item.text())
        return " ".join(parts)

    def _apply_filter(self) -> None:
        """Hide table rows that don't match the active filter, in place.

        A no-op while the table shows a message row (empty / load-failure
        states span column 0, which real rows clear) so the message is never
        filtered away. Updates the footer with the visible count.
        """
        if self.table.columnSpan(0, 0) > 1:
            return  # message row, not real content
        patterns = self._filter_patterns()
        total = self.table.rowCount()
        visible = 0
        for row in range(total):
            hide = patterns is not None and not ptk.filter_list(
                [self._row_haystack(row)],
                inc=patterns,
                ignore_case=True,
                negate_prefix=NEGATE_PREFIX,
            )
            self.table.setRowHidden(row, hide)
            if not hide:
                visible += 1
        self._update_status(visible if patterns is not None else None, total)

    def _set_status(self, text: str) -> None:
        """Set the footer status and remember it as the filter's base text.

        Used by ``populate`` (incl. its empty / load-failure branches) so a
        stale ``showing X of N`` count never lingers after switching to a UI
        with no matching rows.
        """
        self._base_status = text
        self.footer.setStatusText(text)

    def _compose_status(self, visible, total) -> str:
        """Footer text: base population status + an optional visible count.

        ``visible is None`` (filter inert) returns the base status alone; a
        partial count is appended only when some rows are hidden.
        """
        status = getattr(self, "_base_status", "")
        if visible is not None and visible != total:
            tail = f"showing {visible} of {total}"
            status = f"{status} — {tail}" if status else tail.capitalize()
        return status

    def _update_status(self, visible, total) -> None:
        """Push the composed status to the footer."""
        self.footer.setStatusText(self._compose_status(visible, total))

    def _apply_shortcut(self, row: int, new_seq: str) -> None:
        """Apply a captured sequence to the binding on ``row``.

        Shared commit path for the in-cell capture editor: reads the
        method/scope from the row, runs collision resolution, persists
        the binding, and repopulates. No-ops when the row is gone or the
        sequence is unchanged.
        """
        item_name = self.table.item(row, self.COL_ACTION)
        if item_name is None:
            return  # row rebuilt out from under us
        method_name = item_name.toolTip().replace("Method: ", "")
        seq_item = self.table.item(row, self.COL_SHORTCUT)
        current_seq = seq_item.text() if seq_item is not None else ""
        if new_seq == current_seq:
            # Re-capturing the key the row already holds is a no-op; say so
            # (info-level) rather than silently doing nothing — otherwise an
            # attempted "assign the same key again" reads as a broken editor.
            if new_seq:
                self.footer.setStatusText(
                    f"'{new_seq}' is already assigned to {item_name.text()}.",
                    level="info",
                )
            return

        # Read the UI from the row (not the combobox) so edits land on the
        # right UI in 'show all' mode; get_ui builds it on demand if unloaded.
        ui_name = self._row_ui_name(row)
        current_scope = self.scope_at(row) or "window"

        if not self._resolve_collisions(
            ui_name, method_name, new_seq, current_scope
        ):
            # The user declined the conflict prompt (or it was otherwise
            # blocked). Make the cancel visible: an eye-catching coloured footer
            # plus a console line, so a refused duplicate isn't a silent no-op.
            conflicts = self._collect_conflicts(
                ui_name, method_name, new_seq, current_scope
            )
            targets = ", ".join(dict.fromkeys(c.description for c in conflicts))
            msg = (
                f"'{new_seq}' is already assigned"
                + (f" to {targets}" if targets else "")
                + " — left unchanged."
            )
            self.footer.setStatusText(msg, level="warning")
            self.sb.logger.warning(f"[shortcut_editor] {msg}")
            return

        if ui_name == self._COMMAND_UI:
            self.sb.set_command_shortcut(method_name, new_seq, current_scope)
        else:
            target_ui = self.sb.get_ui(ui_name)
            if target_ui is None:  # statically-listed UI that fails to build
                self.footer.setStatusText(
                    f"Could not load '{ui_name}'.", level="error"
                )
                return
            self.sb.set_user_shortcut(target_ui, method_name, new_seq, current_scope)

        # Capture the label before populate() — it rebuilds the table and
        # deletes this row's items, leaving item_name a dangling C++ object.
        label = item_name.text()
        self._refresh_preset_state()
        self.populate()
        # Footer the confirmation AFTER populate(): populate() sets the row-count
        # status, so a pre-populate message would be overwritten before it ever
        # painted. The green 'success' colour is the eye-catching cue.
        self.footer.setStatusText(
            f"Assigned {new_seq or 'None'} to {label}", level="success"
        )

    def reset_shortcut(self, ui, method_name, default_seq, default_scope="window"):
        """Reset sequence and scope to decorator/registration defaults.

        ``ui`` may be a UI object/name (resolved + instantiated on demand via
        ``get_ui``, so a 'show all' row whose UI isn't loaded is built only when
        reset) or the ``_COMMAND_UI`` sentinel for a UI-less command.
        """
        if ui == self._COMMAND_UI:
            self.sb.set_command_shortcut(method_name, default_seq, default_scope)
        else:
            target_ui = self.sb.get_ui(ui)
            if target_ui is None:
                return  # UI failed to build on demand; nothing to reset
            self.sb.set_user_shortcut(
                target_ui, method_name, default_seq, default_scope
            )
        self._refresh_preset_state()
        self.populate()

    # ------------------------------------------------------------------
    # Icon action cells (Scope / Reset)
    # ------------------------------------------------------------------

    # Opacity for a dimmed (disabled / inert) action icon — the delegate-painted
    # equivalent of Qt greying a disabled button's icon.
    _ACTION_DIM_OPACITY = 0.4
    # Green tint behind a scope icon whose scope differs from its default.
    _SCOPE_MODIFIED_BG = QtGui.QColor(76, 175, 80, 60)

    def _action_item(
        self,
        icon_name,
        *,
        color=None,
        tooltip="",
        scope=None,
        action=None,
        bg=None,
        dim=False,
    ) -> QtWidgets.QTableWidgetItem:
        """Build a non-selectable, centered icon item for a Scope/Reset cell.

        ``color=None`` paints the icon in the current theme colour; ``dim`` greys
        it (disabled look); ``bg`` is a state tint behind the icon; ``action`` is
        the click descriptor stored under ``_ACTION_ROLE`` (``None`` => an inert
        badge); ``scope`` (stored under ``_SCOPE_ROLE``) lets the edit path read
        the binding's current scope back without a cell-widget button.
        """
        item = QtWidgets.QTableWidgetItem()
        # Enabled (so the cell paints normally) but neither selectable nor
        # editable — clicks are handled via cellClicked, not selection/edit.
        item.setFlags(QtCore.Qt.ItemIsEnabled)
        item.setTextAlignment(QtCore.Qt.AlignCenter)
        item.setIcon(
            IconManager.get(
                icon_name,
                size=(self.ACTION_ICON_SIZE, self.ACTION_ICON_SIZE),
                color=color,
                use_theme=color is None,
            )
        )
        if tooltip:
            item.setToolTip(tooltip)
        if scope is not None:
            item.setData(self._SCOPE_ROLE, scope)
        item.setData(self._ACTION_ROLE, action)
        if bg is not None:
            item.setBackground(bg)
        if dim:
            item.setData(ICON_OPACITY_ROLE, self._ACTION_DIM_OPACITY)
        return item

    def _set_scope_cell(
        self,
        i: int,
        current_scope: str,
        default_scope: str,
        *,
        has_sequence: bool,
        editable: bool,
        scope_editable: bool,
        is_command: bool,
    ) -> None:
        """Render row ``i``'s Scope cell as a centered, colour-coded icon.

        Inert states (no key bound, fixed/non-editable key, owner-fixed scope,
        a command's forced Application scope, or a decorator-only scope) paint a
        muted icon with an explanatory tooltip and store no click action. The
        interactive Window/Application toggle stores a ``scope`` action and tints
        its background green when the scope differs from the default.
        """
        icon_name = SCOPE_ICONS.get(current_scope, "window")
        base_tip = SCOPE_TOOLTIPS.get(current_scope, f"Scope: {current_scope}")

        if is_command:
            # A UI-less command has no window of its own; window scope would bind
            # it to an arbitrary host window (and die if that window closes), so
            # commands are ALWAYS application-scoped. Show a single consistent
            # non-interactive tinted badge in its active state — checked first, so
            # an *unbound* command reads the same as a bound one (a greyed
            # "assign first" icon here just looked inconsistent against its bound
            # siblings in the Commands view).
            c = QtGui.QColor(self._COMMAND_TAG_COLOR)
            c.setAlpha(90)
            item = self._action_item(
                icon_name,
                color=self._COMMAND_TAG_COLOR,
                tooltip="Commands are always application-scoped.",
                scope=current_scope,
                bg=c,
            )
        elif not has_sequence:
            item = self._action_item(
                icon_name,
                tooltip="Assign a shortcut before choosing its scope.",
                scope=current_scope,
                dim=True,
            )
        elif not editable:
            item = self._action_item(
                icon_name,
                tooltip="Fixed key — scope is not user-editable.",
                scope=current_scope,
                dim=True,
            )
        elif not scope_editable:
            item = self._action_item(
                icon_name,
                tooltip=f"Scope is fixed to its owner ({current_scope}).",
                scope=current_scope,
                dim=True,
            )
        elif current_scope not in USER_SCOPES:
            item = self._action_item(
                icon_name,
                tooltip=base_tip,
                scope=current_scope,
                dim=True,
            )
        else:
            item = self._action_item(
                icon_name,
                tooltip=base_tip,
                scope=current_scope,
                action={"kind": "scope", "default_scope": default_scope},
                bg=(
                    self._SCOPE_MODIFIED_BG
                    if current_scope != default_scope
                    else None
                ),
            )
        self.table.setItem(i, self.COL_SCOPE, item)

    def _set_reset_cell(
        self, i: int, default_seq: str, default_scope: str, *, enabled: bool
    ) -> None:
        """Render row ``i``'s Reset cell — an undo icon, muted and inert when the
        binding is already at its default (or not editable)."""
        if enabled:
            item = self._action_item(
                "undo",
                tooltip="Reset to default shortcut",
                action={
                    "kind": "reset",
                    "default_seq": default_seq,
                    "default_scope": default_scope,
                },
            )
        else:
            item = self._action_item(
                "undo", tooltip="Already at the default shortcut.", dim=True
            )
        self.table.setItem(i, self.COL_RESET, item)

    def scope_at(self, row: int):
        """The scope name stored on a row's Scope cell (``None`` for a message row)."""
        item = self.table.item(row, self.COL_SCOPE)
        return item.data(self._SCOPE_ROLE) if item is not None else None

    def scope_interactive(self, row: int) -> bool:
        """Whether a row's Scope cell is a live toggle (vs a fixed / disabled badge)."""
        item = self.table.item(row, self.COL_SCOPE)
        return bool(item.data(self._ACTION_ROLE)) if item is not None else False

    def _row_method(self, row: int) -> str:
        """The method name for ``row`` (parsed off the Action item's tooltip)."""
        item = self.table.item(row, self.COL_ACTION)
        return item.toolTip().replace("Method: ", "") if item is not None else ""

    def _on_action_cell_clicked(self, row: int, col: int) -> None:
        """Dispatch a click on a Scope / Reset icon cell to its stored action.

        Each action cell carries a descriptor under ``_ACTION_ROLE`` (``None`` for
        an inert badge). Scope flips Window<->Application; Reset restores the
        registration default. Other columns are ignored here (the Shortcut column
        is handled by the capture delegate).
        """
        if col not in (self.COL_SCOPE, self.COL_RESET):
            return
        item = self.table.item(row, col)
        action = item.data(self._ACTION_ROLE) if item is not None else None
        if not action:
            return
        ui_name = self._row_ui_name(row)
        method = self._row_method(row)
        if action["kind"] == "scope":
            self._on_scope_toggle(ui_name, method, action["default_scope"])
        elif action["kind"] == "reset":
            self.reset_shortcut(
                ui_name, method, action["default_seq"], action["default_scope"]
            )

    def _on_scope_toggle(self, ui, method_name: str, default_scope: str):
        """Flip scope between Window and Application — applied immediately.

        ``ui`` may be a UI object or name (resolved via ``get_ui``). A scope
        flip is a reversible mode change, so it does *not* pop the conflict
        modal (that is reserved for binding a key). Any conflict the new scope
        introduces is surfaced inline in the footer; the user can flip back or
        change the sequence.

        Commands never reach here — their scope toggle is disabled (commands are
        application-scoped), so this path is UI-only.
        """
        target_ui = self.sb.get_ui(ui)
        if target_ui is None:
            return
        ui_name = ui if isinstance(ui, str) else target_ui.objectName()

        # Locate the row by UI + method (method names repeat across UIs in the
        # 'show all' view), then read its current state.
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_ACTION)
            if not item or self._row_ui_name(row) != ui_name:
                continue
            if item.toolTip().replace("Method: ", "") != method_name:
                continue

            label = item.text()
            current_seq = self.table.item(row, self.COL_SHORTCUT).text()
            current_scope = self.scope_at(row)

            new_scope = "application" if current_scope == "window" else "window"

            conflicts = self._collect_conflicts(
                ui_name, method_name, current_seq, new_scope
            )
            self.sb.set_user_shortcut(
                target_ui, method_name, current_seq, new_scope
            )
            self._refresh_preset_state()
            self.populate()

            msg = f"{label} → {SCOPE_LABELS.get(new_scope, new_scope)} scope"
            if conflicts:
                others = ", ".join(dict.fromkeys(c.description for c in conflicts))
                msg += f" — now conflicts with {others}"
            self.footer.setStatusText(msg)
            return

    # ------------------------------------------------------------------
    # Collision checking
    # ------------------------------------------------------------------

    def add_collision_checker(self, checker: Callable) -> None:
        """Register a collision checker.

        Args:
            checker: callable with signature
                ``(sequence, scope, ui_name, method_name) -> List[CollisionConflict]``.
                ``sequence``, ``scope``, ``ui_name`` and ``method_name`` describe
                the binding the user is about to assign. Return an empty list
                when there is no conflict. uitk ships an internal checker; host
                packages (mayatk, etc.) register their own to surface external
                hotkey collisions.
        """
        if checker not in self._collision_checkers:
            self._collision_checkers.append(checker)

    def remove_collision_checker(self, checker: Callable) -> None:
        """Unregister a previously added collision checker."""
        if checker in self._collision_checkers:
            self._collision_checkers.remove(checker)

    def _collect_conflicts(
        self, ui_name: str, method_name: str, sequence: str, scope: str
    ) -> List[CollisionConflict]:
        """Run every collision checker and return their conflicts (no prompt).

        ``ui_name`` is the binding's UI (passed by the caller, not read from the
        combobox) so it's correct in 'show all' mode where rows span many UIs.
        """
        if not sequence:
            return []
        conflicts: List[CollisionConflict] = []
        for checker in self._collision_checkers:
            try:
                conflicts.extend(checker(sequence, scope, ui_name, method_name) or [])
            except Exception as exc:  # noqa: BLE001
                self.sb.logger.warning(
                    f"[shortcut_editor] Collision checker {checker} raised: {exc}"
                )
        return conflicts

    def _resolve_collisions(
        self, ui, method_name: str, sequence: str, scope: str
    ) -> bool:
        """Prompt the user when the proposed binding conflicts.

        ``ui`` may be a UI object or name. Returns:
            True when the caller should proceed with the assignment, False when
            the user cancelled.
        """
        ui_name = ui if isinstance(ui, str) else self.sb.get_ui(ui).objectName()
        conflicts = self._collect_conflicts(ui_name, method_name, sequence, scope)
        if not conflicts:
            return True
        return self._prompt_conflicts(sequence, scope, conflicts)

    def _prompt_conflicts(
        self, sequence: str, scope: str, conflicts: List[CollisionConflict]
    ) -> bool:
        """Show a modal listing conflicts; return True to proceed.

        Offers, as the conflicts allow: *Clear conflicting & assign* (clears
        uitk duplicates), *Assign & free Maya binding* (also unbinds Maya's
        hotkey — enabled only when Maya's active set is editable; shown disabled
        with the reason on a locked set), and *Assign anyway*.
        """
        breaks = [c for c in conflicts if c.breaks_binding and c.clear_action]
        maya_clearable = [c for c in conflicts if c.source == "maya" and c.clear_action]
        maya_locked = [c for c in conflicts if c.source == "maya" and not c.clear_action]
        soft = [c for c in conflicts if not (c.breaks_binding and c.clear_action)]

        lines = [f"<b>{sequence}</b> ({SCOPE_LABELS.get(scope, scope)}) conflicts:"]
        if breaks:
            lines.append("")
            lines.append("<b>Will become unreliable unless cleared:</b>")
            for c in breaks:
                lines.append(f"&nbsp;&nbsp;• [{c.source}] {c.description}")
        if soft:
            lines.append("")
            lines.append("<b>May fire alongside:</b>")
            for c in soft:
                lines.append(f"&nbsp;&nbsp;• [{c.source}] {c.description}")
        body = "<br>".join(lines)

        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Shortcut Conflict")
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setText(body)

        clear_btn = None
        if breaks:
            clear_btn = box.addButton(
                "Clear conflicting && assign", QtWidgets.QMessageBox.AcceptRole
            )
        # "Assign & free Maya binding" — also unbinds Maya's hotkey. Enabled only
        # on an editable set (the conflict carries a clear_action); on a locked
        # set the option is shown disabled with its reason, not silently absent.
        maya_btn = None
        if maya_clearable:
            maya_btn = box.addButton(
                "Assign && free Maya binding", QtWidgets.QMessageBox.AcceptRole
            )
        elif maya_locked:
            locked_btn = box.addButton(
                "Free Maya binding (set locked)", QtWidgets.QMessageBox.AcceptRole
            )
            locked_btn.setEnabled(False)
            locked_btn.setToolTip(
                "Switch Maya to a custom (non-default) hotkey set to clear its binding."
            )
        box.addButton("Assign anyway", QtWidgets.QMessageBox.AcceptRole)
        cancel_btn = box.addButton(QtWidgets.QMessageBox.Cancel)
        box.setDefaultButton(cancel_btn)

        box.exec_()
        clicked = box.clickedButton()

        if clicked is cancel_btn:
            return False

        def _run_clears(items):
            for c in items:
                try:
                    c.clear_action()
                except Exception as exc:  # noqa: BLE001
                    self.sb.logger.warning(
                        f"[shortcut_editor] clear_action raised: {exc}"
                    )

        if clicked is clear_btn:
            _run_clears(breaks)
        elif clicked is maya_btn:
            # Free Maya's key AND clear uitk duplicates for a fully clean assign.
            _run_clears(breaks + maya_clearable)
        return True

    @staticmethod
    def _scopes_overlap(scope: str, other_scope: str, same_context: bool) -> bool:
        """Whether two same-key bindings actually collide given their scopes.

        A binding collides only when both can match the key in a context Qt
        can't disambiguate:
          - Either side application-scoped → fires app-wide, overlapping every
            other binding on that key ("safe unless application wide").
          - Both window-scoped → overlap only within the *same* context
            (same window, or both commands); different windows are independent
            focus targets, so the key is safe to reuse across them.
        """
        if scope == "application" or other_scope == "application":
            return True
        if scope == "window" and other_scope == "window":
            return same_context
        return False

    def _builtin_internal_collision_checker(
        self, sequence: str, scope: str, ui_name: str, method_name: str
    ) -> List[CollisionConflict]:
        """Detect collisions against other UIs + commands in this Switchboard.

        Loaded UIs are checked against their live registry. Unloaded UIs are
        deliberately *not* skipped: a UI the user has customised carries a
        **persisted** binding that becomes a real ``QShortcut`` the moment the
        UI loads — or next session — so an application-scoped one silently
        collides into an ambiguous overload that kills *both* shortcuts (the
        reported "repeat-last works once then dies": its key was already owned
        by an unbuilt UI's slot). Those persisted bindings are read from the
        no-build static registry (``get_static_shortcut_registry``), limited to
        UIs that actually carry an override (a single cheap settings scan via
        ``_ui_names_with_shortcut_overrides``) so an assignment never
        force-builds — nor even XML-parses — every registered UI (the old
        slow/crash-prone path). Uncustomised unloaded UIs hold only decorator
        defaults and are left for a future pass.

        Rules:
          - Application scope collides with everything (it fires app-wide).
          - Window scope collides only with Window/Application bindings on the
            same UI (different windows are independent focus targets, so the
            same key is safe to reuse across them).
          - Every collision that survives those rules is genuinely ambiguous,
            so all are flagged ``breaks_binding=True`` with a clear_action — the
            user is always offered to overwrite the conflicting uitk binding,
            mirroring the Maya checker's clear option.
        """
        conflicts: List[CollisionConflict] = []
        if not sequence:
            return conflicts

        overridden_unloaded = None  # computed lazily on the first unloaded UI
        for other_ui_name in self._registered_ui_names():
            if self.sb.loaded_ui.peek(other_ui_name) is None:
                # Unbuilt UI: its *persisted* bindings still become live
                # shortcuts on load / next session, so they must be checked —
                # but only when the user has actually customised the UI (a
                # single cheap settings scan), so the static (XML) read isn't
                # paid for every registered UI. _registry_for never builds.
                if overridden_unloaded is None:
                    overridden_unloaded = self.sb._ui_names_with_shortcut_overrides()
                if other_ui_name not in overridden_unloaded:
                    continue
            registry = self._registry_for(other_ui_name)
            if not registry:
                continue
            for entry in registry:
                other_method = entry["method"]
                other_seq = entry.get("current") or ""
                other_scope = entry.get("current_scope", "window")
                if not other_seq or other_seq != sequence:
                    continue
                if other_ui_name == ui_name and other_method == method_name:
                    continue  # same row

                if not self._scopes_overlap(
                    scope, other_scope, same_context=other_ui_name == ui_name
                ):
                    continue

                # Everything that reaches here overlaps ambiguously, so it is a
                # genuine collision the user should be offered to overwrite —
                # exactly the parity with the Maya checker's clear option. Carry
                # a clear_action that frees the *other* binding so the dialog's
                # "Clear conflicting && assign" path can resolve it.
                desc = (
                    f"{other_ui_name}.{other_method} "
                    f"({SCOPE_LABELS.get(other_scope, other_scope)})"
                )
                # Resolve by *name* (not the captured object) so the clear works
                # for an unloaded UI too — set_user_shortcut needs a live slots
                # instance, so get_ui builds it on demand only when the user
                # actually accepts the clear.
                clear = (
                    lambda name=other_ui_name, m=other_method, dscope=entry.get(
                        "default_scope", "window"
                    ): self.sb.set_user_shortcut(self.sb.get_ui(name), m, "", dscope)
                )
                conflicts.append(
                    CollisionConflict(
                        source="uitk",
                        description=desc,
                        breaks_binding=True,
                        clear_action=clear,
                    )
                )

        # UI-less commands participate too — a command is its own focus-
        # independent surface, so two commands collide only when one is
        # application-scoped (the same rule as a single shared window).
        for entry in self._command_entries():
            other_method = entry["method"]
            other_seq = entry.get("current") or ""
            other_scope = entry.get("current_scope", "application")
            if not other_seq or other_seq != sequence:
                continue
            if ui_name == self._COMMAND_UI and other_method == method_name:
                continue  # same row
            # Commands share one focus-independent surface, so two window-scoped
            # commands overlap only when the edited row is itself a command.
            if not self._scopes_overlap(
                scope, other_scope, same_context=ui_name == self._COMMAND_UI
            ):
                continue
            # A non-clearable command (e.g. the marking-menu activation key, whose
            # on_rebind can't honour an empty sequence) keeps its key: report the
            # conflict as coexisting rather than offering a clear that no-ops.
            clearable = entry.get("clearable", True)
            clear = (
                (
                    lambda m=other_method, dscope=entry.get(
                        "default_scope", "application"
                    ): self.sb.set_command_shortcut(m, "", dscope)
                )
                if clearable
                else None
            )
            conflicts.append(
                CollisionConflict(
                    source="uitk",
                    description=(
                        f"command:{entry['name']} "
                        f"({SCOPE_LABELS.get(other_scope, other_scope)})"
                    ),
                    breaks_binding=clearable,
                    clear_action=clear,
                )
            )
        return conflicts
