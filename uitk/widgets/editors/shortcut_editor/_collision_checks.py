# !/usr/bin/python
# coding=utf-8
"""Collision checking for a ShortcutEditor: the checker registry and the conflict prompt.

One part of :class:`~uitk.widgets.editors.shortcut_editor.registry_editor.ShortcutEditor`,
which inherits it. A host registers checkers (a DCC's native hotkey map) that
report :class:`~uitk.widgets.editors.shortcut_editor.collision_conflict.CollisionConflict`
records; the built-in checker finds duplicates inside the registry itself; the
prompt offers to clear, free or override before a binding is assigned.
"""

from typing import Callable, List

from qtpy import QtWidgets

from uitk.widgets.editors.shortcut_editor.collision_conflict import CollisionConflict
from ._action_cells import SCOPE_LABELS


class _CollisionChecksMixin:
    """The collision-checker registry and the conflict prompt."""

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
        uitk duplicates), one *Assign & free <label> binding* per source whose
        binding the user may free alongside the assign (a host checker's
        conflict carrying a ``clear_action`` -- shown disabled, with the
        conflict's ``clear_blocked`` reason, when the host cannot clear it), and
        *Assign anyway*. Nothing here names a host: the checker describes its
        own conflicts (:class:`CollisionConflict`).
        """
        breaks = [c for c in conflicts if c.breaks_binding and c.clear_action]
        # Another owner's binding that coexists unless the user frees it: the
        # clearable ones get an enabled button, the blocked ones a disabled one.
        external = [
            c
            for c in conflicts
            if not c.breaks_binding and (c.clear_action or c.clear_blocked)
        ]
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
        # "Assign & free <label> binding" -- also clears that source's binding.
        # Enabled when the conflict carries a clear_action; when the source says
        # why it cannot clear (``clear_blocked``) the option is shown disabled
        # with that reason, not silently absent.
        free_buttons = []  # [(button, conflicts it clears)]
        for label in dict.fromkeys(c.display_label for c in external):
            group = [c for c in external if c.display_label == label]
            clearable = [c for c in group if c.clear_action]
            if clearable:
                button = box.addButton(
                    f"Assign && free {label} binding", QtWidgets.QMessageBox.AcceptRole
                )
                free_buttons.append((button, clearable))
            else:
                locked_btn = box.addButton(
                    f"Free {label} binding (locked)", QtWidgets.QMessageBox.AcceptRole
                )
                locked_btn.setEnabled(False)
                locked_btn.setToolTip(group[0].clear_blocked)
        box.addButton("Assign anyway", QtWidgets.QMessageBox.AcceptRole)
        cancel_btn = box.addButton(QtWidgets.QMessageBox.Cancel)
        box.setDefaultButton(cancel_btn)

        box.exec_()
        clicked = box.clickedButton()
        # Parented to ``self``, so PySide will not free the box when the local
        # reference drops — the parent owns it. Release it explicitly (deferred,
        # so the button-identity checks below still resolve) to avoid a hidden
        # QMessageBox child accumulating on the editor for every conflict prompt.
        box.deleteLater()

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
        else:
            for button, clearable in free_buttons:
                if clicked is button:
                    # Free that source's key AND clear uitk duplicates for a
                    # fully clean assign.
                    _run_clears(breaks + clearable)
                    break
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
                def clear(
                    name=other_ui_name,
                    m=other_method,
                    dscope=entry.get("default_scope", "window"),
                ):
                    self.sb.set_user_shortcut(self.sb.get_ui(name), m, "", dscope)

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
                    lambda m=other_method, dscope=entry.get("default_scope", "application"): (
                        self.sb.set_command_shortcut(m, "", dscope)
                    )
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
