# !/usr/bin/python
# coding=utf-8
"""The Scope and Reset icon cells of a ShortcutEditor row, and the scope vocabulary.

One part of :class:`~uitk.widgets.editors.shortcut_editor.registry_editor.ShortcutEditor`,
which inherits it: the delegate-painted action cells (a scope toggle that
re-registers the binding in the other scope, a reset back to the default) and
the end-user scope names, labels, icons and tooltips they show.
"""

from qtpy import QtCore, QtGui, QtWidgets

from uitk.managers.icon_manager import IconManager
from uitk.widgets.delegates.centered_icon import ICON_OPACITY_ROLE


# End-user-facing scopes. Widget/widget_children remain decorator-only.
USER_SCOPES = ("window", "application")
SCOPE_LABELS = {"window": "Win", "application": "App"}
SCOPE_ICONS = {"window": "window", "application": "screen"}
SCOPE_TOOLTIPS = {
    "window": "Window scope — fires only when this UI's window is focused. Click to switch to Application scope.",
    "application": "Application scope — fires anywhere in the host app. Click to switch to Window scope.",
}


class _ActionCellsMixin:
    """The Scope / Reset icon cells of a binding row."""

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
                    self._SCOPE_MODIFIED_BG if current_scope != default_scope else None
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
            self.sb.set_user_shortcut(target_ui, method_name, current_seq, new_scope)
            self._refresh_preset_state()
            self.populate()

            msg = f"{label} → {SCOPE_LABELS.get(new_scope, new_scope)} scope"
            if conflicts:
                others = ", ".join(dict.fromkeys(c.description for c in conflicts))
                msg += f" — now conflicts with {others}"
            self.footer.setStatusText(msg)
            return
