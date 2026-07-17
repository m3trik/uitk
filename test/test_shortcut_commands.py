# !/usr/bin/python
# coding=utf-8
"""Tests for UI-less, shortcut-bindable commands.

Covers:
- Switchboard.register_command / get_command_registry / set_command_shortcut /
  unregister_command, default-unbound listing, override persistence, and live
  binding once a host window exists.
- ShortcutEditor: the appended "Commands" pseudo-UI, the colour-coded command
  rows, edit/reset routing through set_command_shortcut, show-all inclusion,
  preset export/import round-trip, and collision detection against commands.

Run standalone: python -m test.test_shortcut_commands
"""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtCore, QtGui
from uitk.switchboard import Switchboard
from uitk.examples.example import ExampleSlots
from uitk.widgets.editors.shortcut_editor.registry_editor import ShortcutEditor


class _SwitchboardFixture(QtBaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk import examples

        cls.example_module = examples

    def setUp(self):
        super().setUp()
        self.sb = Switchboard(
            ui_source=self.example_module, slot_source=ExampleSlots
        )
        # Hermetic: the QSettings sandbox is shared across the run, so a command
        # override persisted by an earlier test (or test file, e.g. the shortcut
        # editor's) would otherwise leak in and break default-state assertions.
        # Reset the command-override store so each test starts from the
        # registered command defaults regardless of collection order.
        self.sb._command_settings().clear()


# ---------------------------------------------------------------------------
# Switchboard command registry
# ---------------------------------------------------------------------------
class TestCommandRegistry(_SwitchboardFixture):
    def test_builtin_nav_commands_registered(self):
        reg = {e["method"]: e for e in self.sb.get_command_registry()}
        self.assertIn("reopen_last_ui", reg)
        self.assertIn("repeat_last_command", reg)
        # All carry the command marker + app-scope default.
        for e in reg.values():
            self.assertTrue(e["command"])
            self.assertEqual(e["default_scope"], "application")
        # Both nav commands ship UNBOUND — no surprise default key; the user
        # assigns one in the editor. (The Maya repeat-last regression was fixed
        # by consolidating onto the single command binding path, NOT by shipping
        # a default — see test_repeat_last_binds_single_shortcut_when_assigned.)
        self.assertEqual(reg["reopen_last_ui"]["current"], "")
        self.assertEqual(reg["reopen_last_ui"]["default"], "")
        self.assertEqual(reg["repeat_last_command"]["default"], "")
        self.assertEqual(reg["repeat_last_command"]["current"], "")

    def test_register_appears_with_label_and_doc(self):
        self.sb.register_command(
            "do_thing", lambda: None, label="Do Thing", doc="does a thing"
        )
        entry = {e["method"]: e for e in self.sb.get_command_registry()}["do_thing"]
        self.assertEqual(entry["name"], "Do Thing")
        self.assertEqual(entry["doc"], "does a thing")

    def test_register_default_label_titlecases_name(self):
        self.sb.register_command("my_cmd", lambda: None)
        entry = {e["method"]: e for e in self.sb.get_command_registry()}["my_cmd"]
        self.assertEqual(entry["name"], "My Cmd")

    def test_set_command_shortcut_persists_override(self):
        self.sb.set_command_shortcut("reopen_last_ui", "Ctrl+Alt+R", "application")
        entry = {e["method"]: e for e in self.sb.get_command_registry()}[
            "reopen_last_ui"
        ]
        self.assertEqual(entry["current"], "Ctrl+Alt+R")
        self.assertEqual(entry["current_scope"], "application")

    def test_clear_unbinds_but_keeps_listed(self):
        self.sb.set_command_shortcut("reopen_last_ui", "F8")
        self.sb.set_command_shortcut("reopen_last_ui", "")
        entry = {e["method"]: e for e in self.sb.get_command_registry()}[
            "reopen_last_ui"
        ]
        self.assertEqual(entry["current"], "")  # cleared
        self.assertIn(  # still listed
            "reopen_last_ui", {e["method"] for e in self.sb.get_command_registry()}
        )

    def test_set_unknown_command_is_noop(self):
        self.sb.set_command_shortcut("nope", "Ctrl+X")  # must not raise/create
        self.assertNotIn(
            "nope", {e["method"] for e in self.sb.get_command_registry()}
        )

    def test_unregister_removes_and_disposes(self):
        self.sb.register_command("temp", lambda: None, sequence="Ctrl+8")
        self.sb.unregister_command("temp")
        self.assertNotIn(
            "temp", {e["method"] for e in self.sb.get_command_registry()}
        )
        self.assertNotIn("temp", self.sb._command_shortcuts)


class TestExternalBinding(_SwitchboardFixture):
    """register_command(bind=False, on_rebind=…, value_getter=…) — an
    editor-visible binding whose real key is owned externally (e.g. the marking
    menu's activation GlobalShortcut). Lists + edits in the register without a
    second, colliding QShortcut."""

    def test_lists_with_live_value_from_getter(self):
        holder = {"seq": "F12"}
        self.sb.register_command(
            "ext_show",
            label="Ext Show",
            bind=False,
            value_getter=lambda: holder["seq"],
            on_rebind=lambda seq, scope: holder.__setitem__("seq", seq),
        )
        reg = {e["method"]: e for e in self.sb.get_command_registry()}
        self.assertIn("ext_show", reg)
        self.assertEqual(reg["ext_show"]["current"], "F12")
        # The getter is live — reflects the owner's state, not command settings.
        holder["seq"] = "F11"
        reg = {e["method"]: e for e in self.sb.get_command_registry()}
        self.assertEqual(reg["ext_show"]["current"], "F11")

    def test_creates_no_register_owned_shortcut(self):
        self.sb.register_command(
            "ext_noshort",
            bind=False,
            value_getter=lambda: "F12",
            on_rebind=lambda *_: None,
        )
        self.assertNotIn("ext_noshort", self.sb._command_shortcuts)

    def test_edit_routes_to_on_rebind_not_settings(self):
        got = []
        self.sb.register_command(
            "ext_edit",
            bind=False,
            value_getter=lambda: "F12",
            on_rebind=lambda seq, scope: got.append((seq, scope)),
        )
        self.sb.set_command_shortcut("ext_edit", "F11", "application")
        self.assertEqual(got, [("F11", "application")])
        # Command settings stay untouched — the owner is the source of truth.
        self.assertIsNone(
            self.sb._command_settings().value(self.sb._command_key("ext_edit"))
        )

    def test_reset_also_routes_to_on_rebind(self):
        # The editor's per-row reset flows through set_command_shortcut too.
        got = []
        self.sb.register_command(
            "ext_reset",
            bind=False,
            value_getter=lambda: "F11",
            on_rebind=lambda seq, scope: got.append(seq),
        )
        self.sb.set_command_shortcut("ext_reset", "F12", "application")
        self.assertEqual(got, ["F12"])

    def test_hidden_readonly_flags_honoured(self):
        self.sb.register_command(
            "ext_hidden",
            bind=False,
            hidden=True,
            editable=False,
            value_getter=lambda: "F12 + Left",
        )
        entry = {e["method"]: e for e in self.sb.get_command_registry()}["ext_hidden"]
        self.assertTrue(entry["hidden"])
        self.assertFalse(entry["editable"])

    def test_pending_bind_skips_external(self):
        # _bind_pending_commands (self-heal) must not try to bind a bind=False cmd.
        self.sb.register_command(
            "ext_pending",
            bind=False,
            value_getter=lambda: "F12",
            on_rebind=lambda *_: None,
        )
        self.sb._bind_pending_commands()  # must not raise or create a shortcut
        self.assertNotIn("ext_pending", self.sb._command_shortcuts)


class TestCommandBinding(_SwitchboardFixture):
    def setUp(self):
        super().setUp()
        self._shown = []

    def tearDown(self):
        # Close any window we showed — a leaked visible top-level pollutes the
        # shared QApplication (active-window / focus / geometry) and flakes
        # later tests.
        for w in self._shown:
            try:
                w.close()
            except RuntimeError:
                pass
        super().tearDown()

    def _show_host(self):
        ui = self.sb.loaded_ui.example
        ui.show()
        QtWidgets.QApplication.processEvents()
        self._shown.append(ui)
        return ui

    def test_binds_live_shortcut_when_host_available(self):
        ui = self._show_host()
        self.assertIsNotNone(self.sb._command_host())
        self.sb.set_command_shortcut("reopen_last_ui", "F8", "application")
        self.assertIn("reopen_last_ui", self.sb._command_shortcuts)
        ui.close()

    def test_repeat_last_binds_single_shortcut_when_assigned(self):
        """repeat-last ships UNBOUND; once assigned it binds exactly ONE live
        shortcut and re-binding never stacks a duplicate.

        Regression for the proven Maya failure: tentacle's old base ``Slots``
        created an application-scoped Ctrl+Shift+R QShortcut in *every* slot
        instance's ``__init__`` (one per loaded UI), so with several UIs open Qt
        saw a stack of identical enabled app shortcuts, declared the activation
        ambiguous, and fired none. Routing repeat-last through the single
        ``repeat_last_command`` guarantees one binding regardless of how many
        UIs/slots are loaded — the fix is the consolidation, not a default key.
        """
        self._show_host()
        self.sb._bind_pending_commands()  # what on_ui_loaded triggers
        # Ships unbound: nothing binds until the user assigns a key.
        self.assertNotIn("repeat_last_command", self.sb._command_shortcuts)
        # Assigning binds exactly one application-scoped shortcut.
        self.sb.set_command_shortcut(
            "repeat_last_command", "Ctrl+Shift+R", "application"
        )
        self.assertIn("repeat_last_command", self.sb._command_shortcuts)
        sc = self.sb._command_shortcuts["repeat_last_command"]
        self.assertEqual(sc.key().toString(), "Ctrl+Shift+R")
        self.assertEqual(sc.context(), QtCore.Qt.ApplicationShortcut)
        # Re-running the bind pass must not stack a second shortcut on the key.
        self.sb._bind_pending_commands()
        self.assertIs(self.sb._command_shortcuts["repeat_last_command"], sc)

    def test_clear_disposes_live_shortcut(self):
        self._show_host()
        self.sb.set_command_shortcut("reopen_last_ui", "F8", "application")
        self.assertIn("reopen_last_ui", self.sb._command_shortcuts)
        self.sb.set_command_shortcut("reopen_last_ui", "")
        self.assertNotIn("reopen_last_ui", self.sb._command_shortcuts)

    def test_command_uses_plain_qshortcut_not_latching_global_shortcut(self):
        """Regression: 'the global commands stop working / don't persist.'

        Commands were bound with a GlobalShortcut, whose ``pressed`` only
        re-fires after its app-level event filter sees a matching KeyRelease
        reset an internal ``_is_down`` latch. Verified live in Maya: when that
        release is missed (native viewport focus, focus shifting mid-action) the
        latch sticks and every press after the first is silently swallowed — the
        command fires once, then is dead for the session. A fire-on-press command
        must own a plain QShortcut (fires on every press, no latch), exactly like
        the ordinary slot shortcuts that already persist reliably.
        """
        from uitk.managers.shortcut_manager import GlobalShortcut

        self._show_host()
        fired = []
        self.sb.register_command(
            "probe_repeat", lambda: fired.append(1), sequence="F8"
        )
        sc = self.sb._command_shortcuts["probe_repeat"]
        self.assertIsInstance(sc, QtWidgets.QShortcut)
        self.assertNotIsInstance(sc, GlobalShortcut)  # no _is_down latch
        # Application scope owned by a visible host, and fires on activation.
        self.assertEqual(sc.context(), QtCore.Qt.ApplicationShortcut)
        sc.activated.emit()
        self.assertEqual(fired, [1])
        self.sb.unregister_command("probe_repeat")

    def test_command_owner_is_persistent_ui_not_active_window(self):
        """Regression: 'the global commands never work'.

        A command is bound the moment the user assigns a key in the shortcut
        editor, at which point ``app.activeWindow()`` IS that editor — an
        ephemeral tool window. Owning the application-scoped shortcut by it made
        the command go inert the instant the editor closed. The owner must be a
        persistent, visible UI instead, surviving the editor's close.
        """
        host_ui = self._show_host()  # a persistent, visible loaded UI

        fired = []
        self.sb.register_command("probe_fire", lambda: fired.append(1))

        # A transient window stands in for the shortcut editor and grabs focus.
        transient = QtWidgets.QWidget()
        transient.setObjectName("TransientEditor")
        transient.show()
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.setActiveWindow(transient)
        QtWidgets.QApplication.processEvents()
        self._shown.append(transient)
        self.assertIs(QtWidgets.QApplication.activeWindow(), transient)

        self.sb.set_command_shortcut("probe_fire", "F8", "application")
        sc = self.sb._command_shortcuts["probe_fire"]  # a plain QShortcut
        owner = sc.parent()
        self.assertIsNot(
            owner, transient, "command owned by the transient editor window"
        )
        self.assertTrue(owner.isVisible(), "command owner must be visible")

        # Closing the transient (user closes the editor) must not orphan it.
        transient.close()
        QtWidgets.QApplication.processEvents()
        self.assertTrue(owner.isVisible(), "owner must outlive the editor")

        # Wiring still fires the callback through the surviving owner.
        sc.activated.emit()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(fired, [1])
        self.sb.unregister_command("probe_fire")
        host_ui.close()

    def test_command_host_skips_transient_marking_menu_surface(self):
        """A visible marking-menu surface (startmenu/submenu) must not be chosen
        to own a command — it vanishes on gesture-release, which would make the
        application shortcut inert again (the very bug this whole path fixes)."""
        surface = self.sb.add_ui("probe_startmenu", tags={"startmenu"})
        surface.show()
        QtWidgets.QApplication.processEvents()
        self._shown.append(surface)

        host = self._show_host()  # a real, persistent UI
        chosen = self.sb._command_host()
        self.assertIsNot(chosen, surface, "owned a command by a transient surface")
        self.assertIs(chosen, host)
        surface.close()

    def test_pending_command_binds_on_ui_loaded(self):
        from unittest import mock

        # Force the no-host state at registration (a shared-process Qt app may
        # otherwise have a leftover active window), so the command defers.
        with mock.patch.object(self.sb, "_command_host", return_value=None):
            self.sb.register_command("later", lambda: None, sequence="F9")
        self.assertNotIn("later", self.sb._command_shortcuts)  # deferred, no host
        self._show_host()  # a host now exists
        self.sb._bind_pending_commands()  # what on_ui_loaded triggers
        self.assertIn("later", self.sb._command_shortcuts)

    def test_command_host_falls_back_to_visible_dcc_window(self):
        """With no Switchboard UI visible, the host is an always-visible DCC main
        window — not app.activeWindow() (which is None at startup). This is what
        lets a persisted command bind at next-session startup before any tool is
        opened."""
        maya = self.track_widget(QtWidgets.QWidget())
        maya.setObjectName("MayaWindow")
        maya.show()
        QtWidgets.QApplication.processEvents()
        self._shown.append(maya)
        self.assertIs(self.sb._command_host(), maya)

    def test_persisted_command_binds_at_startup_via_dcc_host(self):
        """Regression: the global commands didn't persist across sessions. The
        value persisted fine, but at startup `on_ui_loaded` fires while the UI
        is still hidden and nothing is the active window, so the old
        activeWindow()-only host fallback returned None and the command never
        bound. With a DCC host up it must bind even though no uitk UI is shown."""
        # Persist the binding, then drop the live shortcut to mimic a fresh
        # session's deferred state.
        self.sb.set_command_shortcut("reopen_last_ui", "F8", "application")
        old = self.sb._command_shortcuts.pop("reopen_last_ui", None)
        if old is not None:
            self.sb._dispose_shortcut(old)
        self.assertNotIn("reopen_last_ui", self.sb._command_shortcuts)

        # Only a DCC host is up — no Switchboard UI visible, and crucially
        # nothing is the active window (the old activeWindow()-only fallback
        # returned None here, so the command never bound).
        maya = self.track_widget(QtWidgets.QWidget())
        maya.setObjectName("MayaWindow")
        maya.show()
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.setActiveWindow(None)
        QtWidgets.QApplication.processEvents()
        self._shown.append(maya)
        self.assertIsNone(QtWidgets.QApplication.activeWindow())

        self.sb._bind_pending_commands()  # what on_ui_loaded triggers at startup
        self.assertIn("reopen_last_ui", self.sb._command_shortcuts)
        self.sb.set_command_shortcut("reopen_last_ui", "")  # cleanup persisted

    def test_deferred_command_binds_when_a_ui_becomes_current(self):
        """A window becoming current (shown + focused) retries deferred binds —
        covers a standalone host that shows its main window only after the
        on_ui_loaded that would otherwise be the command's one bind chance."""
        from unittest import mock

        with mock.patch.object(self.sb, "_command_host", return_value=None):
            self.sb.register_command("probe_curr", lambda: None, sequence="F7")
        self.assertNotIn("probe_curr", self.sb._command_shortcuts)  # deferred

        ui = self._show_host()
        self.sb._current_ui = None  # ensure the setter body runs (not a no-op)
        self.sb.current_ui = ui  # becoming current must retry the bind
        self.assertIn("probe_curr", self.sb._command_shortcuts)
        self.sb.unregister_command("probe_curr")


# ---------------------------------------------------------------------------
# Command binding self-heals a stale host namespace
# ---------------------------------------------------------------------------
class TestCommandNamespaceSelfHeal(_SwitchboardFixture):
    """Regression: 'repeat-last command does not persist across sessions.'

    A command is eagerly bound during ``register_command`` (which runs in
    ``Switchboard.__init__``). If the host's ``context_tags`` are assigned only
    *after* construction, that eager bind resolved the persisted sequence under
    the wrong, un-suffixed settings namespace and latched a stale legacy value.
    The old ``_bind_pending_commands`` bound only *missing* commands, so the
    stale binding was never corrected and the user's real key never bound — a
    dead ``Ctrl+Shift+R`` stayed live while the assigned ``M`` (sitting in the
    host-namespaced key) was ignored. The bind pass must re-resolve and rebind a
    command whose live key drifted from its persisted sequence.
    """

    def setUp(self):
        super().setUp()
        self._shown = []

    def tearDown(self):
        self.sb._command_settings().clear()  # don't leak seeded keys
        for w in self._shown:
            try:
                w.close()
            except RuntimeError:
                pass
        super().tearDown()

    def _maya_host(self):
        maya = QtWidgets.QWidget()
        maya.setObjectName("MayaWindow")
        maya.show()
        QtWidgets.QApplication.processEvents()
        self._shown.append(maya)
        return maya

    def _seed_user_split(self):
        """The exact persisted split observed in the field: the host-namespaced
        value the user assigned, plus a stale un-suffixed legacy default left
        over from a pre-namespacing session."""
        cs = self.sb._command_settings()
        cs.setValue("shortcuts_maya.Commands.repeat_last_command", "M")
        cs.setValue(
            "shortcuts_maya.Commands.repeat_last_command.scope", "application"
        )
        cs.setValue("shortcuts.Commands.repeat_last_command", "Ctrl+Shift+R")
        cs.setValue(
            "shortcuts.Commands.repeat_last_command.scope", "application"
        )

    def test_stale_binding_rebinds_when_namespace_settles(self):
        self._seed_user_split()
        self._maya_host()

        # Eager bind under EMPTY tags (the __init__-before-tags window): resolves
        # the legacy un-suffixed key and latches the stale 'Ctrl+Shift+R'.
        self.assertEqual(self.sb.context_tags, set())
        self.sb._bind_command("repeat_last_command")
        stale = self.sb._command_shortcuts["repeat_last_command"]
        self.assertEqual(stale.key().toString(), "Ctrl+Shift+R")

        # Host assigns its context_tags after construction; the next
        # on_ui_loaded pass must re-resolve under the host namespace and bind
        # the user's actual 'M' (NOT keep the stale legacy key).
        self.sb.context_tags = {"maya"}
        self.sb._bind_pending_commands()
        healed = self.sb._command_shortcuts["repeat_last_command"]
        self.assertEqual(healed.key().toString(), "M")
        self.assertEqual(healed.context(), QtCore.Qt.ApplicationShortcut)

    def test_unchanged_binding_is_not_rebound(self):
        """The self-heal must not churn a correct binding: a command whose live
        key already matches its persisted sequence keeps the SAME QShortcut
        object across bind passes (no needless dispose/recreate)."""
        self._maya_host()
        self.sb.set_command_shortcut("reopen_last_ui", "F8", "application")
        sc = self.sb._command_shortcuts["reopen_last_ui"]
        self.sb._bind_pending_commands()  # no drift -> must be a no-op
        self.assertIs(self.sb._command_shortcuts["reopen_last_ui"], sc)

    def test_scope_only_drift_rebinds(self):
        """A binding can drift in SCOPE alone (same key): the legacy namespace
        had it window-scoped, the host namespace application-scoped. The live
        ``WindowShortcut`` would be inert exactly when the app-scoped binding
        should fire, so the heal must re-resolve scope too — a key-only check
        leaves it mis-scoped."""
        cs = self.sb._command_settings()
        cs.setValue("shortcuts.Commands.repeat_last_command", "M")
        cs.setValue("shortcuts.Commands.repeat_last_command.scope", "window")
        cs.setValue("shortcuts_maya.Commands.repeat_last_command", "M")
        cs.setValue(
            "shortcuts_maya.Commands.repeat_last_command.scope", "application"
        )
        self._maya_host()

        # Eager bind under empty tags -> window-scoped 'M' from the legacy key.
        self.sb._bind_command("repeat_last_command")
        stale = self.sb._command_shortcuts["repeat_last_command"]
        self.assertEqual(stale.key().toString(), "M")
        self.assertEqual(stale.context(), QtCore.Qt.WindowShortcut)

        # Tags settle: same key, but scope must flip to application.
        self.sb.context_tags = {"maya"}
        self.sb._bind_pending_commands()
        healed = self.sb._command_shortcuts["repeat_last_command"]
        self.assertEqual(healed.key().toString(), "M")
        self.assertEqual(healed.context(), QtCore.Qt.ApplicationShortcut)


# ---------------------------------------------------------------------------
# ShortcutEditor integration
# ---------------------------------------------------------------------------
class TestEditorCommands(_SwitchboardFixture):
    def setUp(self):
        super().setUp()
        self.editor = ShortcutEditor(self.sb)
        self.editor.refresh_ui_list()

    def tearDown(self):
        if getattr(self, "editor", None):
            # Don't let a 'show all' toggle leak into other tests via the
            # process-wide sandboxed QSettings.
            self.editor._settings.setValue("show_all", False)
            self.editor.close()
        super().tearDown()

    def _select(self, label):
        idx = self.editor.cmb_ui.findText(label)
        self.editor.cmb_ui.setCurrentIndex(idx)
        self.editor.populate()

    def _select_commands(self):
        self._select(self.editor._COMMANDS_LABEL)

    def _visible_rows(self):
        """(name, seq) for each non-message table row currently shown."""
        rows = []
        for r in range(self.editor.table.rowCount()):
            if self.editor.table.columnSpan(r, 0) > 1:
                continue  # spanning message row
            rows.append(
                (self.editor.table.item(r, 0).text(), self.editor.table.item(r, 1).text())
            )
        return rows

    def _command_row(self, method):
        for r in range(self.editor.table.rowCount()):
            it = self.editor.table.item(r, 0)
            if it and it.toolTip().endswith(method):
                return r
        self.fail(f"{method} row not found")

    def test_action_cell_click_dispatch(self):
        """A click on a Scope/Reset icon cell routes through cellClicked ->
        _on_action_cell_clicked: Reset restores the default; an inert (command)
        Scope badge is a no-op."""
        self.sb.set_command_shortcut("reopen_last_ui", "Ctrl+Alt+8", "application")
        self._select_commands()
        row = self._command_row("reopen_last_ui")
        self.assertEqual(self.editor.table.item(row, 1).text(), "Ctrl+Alt+8")

        # Reset cell carries an action — clicking it clears the override.
        # Emit cellClicked to exercise the wiring, not just the handler.
        self.editor.table.cellClicked.emit(row, self.editor.COL_RESET)
        reg = {e["method"]: e for e in self.sb.get_command_registry()}
        self.assertEqual(reg["reopen_last_ui"]["current"], "")

        # An inert command Scope badge dispatches to nothing (no crash/change).
        self._select_commands()
        row = self._command_row("reopen_last_ui")
        self.assertFalse(self.editor.scope_interactive(row))
        self.editor.table.cellClicked.emit(row, self.editor.COL_SCOPE)
        reg = {e["method"]: e for e in self.sb.get_command_registry()}
        self.assertEqual(reg["reopen_last_ui"]["current_scope"], "application")

    def test_commands_pseudo_ui_listed_at_top(self):
        items = [
            self.editor.cmb_ui.itemText(i)
            for i in range(self.editor.cmb_ui.count())
        ]
        # Special views sort to the top (Assigned, then Commands)...
        self.assertEqual(items[0], self.editor._ASSIGNED_LABEL)
        self.assertEqual(items[1], self.editor._COMMANDS_LABEL)
        # ...but the editor opens on a real UI, not a filtered/command view.
        self.assertNotIn(
            self.editor.cmb_ui.currentText(),
            (self.editor._ASSIGNED_LABEL, self.editor._COMMANDS_LABEL),
        )

    def test_assigned_special_entry_is_first_and_accent_colored(self):
        items = [
            self.editor.cmb_ui.itemText(i)
            for i in range(self.editor.cmb_ui.count())
        ]
        self.assertEqual(items[0], self.editor._ASSIGNED_LABEL)
        # Special entries are accent-coloured to set them apart from UI names.
        brush = self.editor.cmb_ui.itemData(0, QtCore.Qt.ForegroundRole)
        self.assertIsNotNone(brush)
        self.assertEqual(
            brush.color().name().lower(), self.editor._COMMAND_TAG_COLOR.lower()
        )
        # A plain UI entry (last item) carries no such accent.
        last = self.editor.cmb_ui.count() - 1
        self.assertIsNone(
            self.editor.cmb_ui.itemData(last, QtCore.Qt.ForegroundRole)
        )

    def test_assigned_view_lists_only_bound_actions(self):
        # Bind one command; explicitly clear another so it's unassigned.
        self.sb.set_command_shortcut("repeat_last_command", "Ctrl+Alt+9", "application")
        self.sb.set_command_shortcut("reopen_last_ui", "", "application")
        self._select(self.editor._ASSIGNED_LABEL)

        rows = self._visible_rows()
        names = [n for n, _s in rows]
        self.assertTrue(rows, "expected at least the just-bound command")
        # Every listed row has a non-empty shortcut...
        self.assertTrue(
            all(seq for _n, seq in rows),
            "the Assigned view must list only rows with a bound shortcut",
        )
        # ...the bound command is present, the cleared one is absent.
        self.assertIn("Repeat Last Command", names)
        self.assertNotIn("Reopen Last UI", names)

    def test_assigned_view_empty_state_message(self):
        # The empty path (nothing bound) shows a spanning message, not rows.
        self.editor._populate_pairs(
            [],
            empty_message="No shortcuts assigned yet.",
            status_noun="assigned shortcuts",
        )
        self.assertEqual(self.editor.table.rowCount(), 1)
        self.assertIn("assigned", self.editor.table.item(0, 0).text().lower())
        self.assertEqual(
            self.editor.table.columnSpan(0, 0), self.editor.table.columnCount()
        )

    def test_command_rows_carry_sentinel_and_tag(self):
        self._select_commands()
        self.assertGreater(self.editor.table.rowCount(), 0)
        for r in range(self.editor.table.rowCount()):
            action = self.editor.table.item(r, 0)
            tag = self.editor.table.item(r, 5)
            self.assertEqual(action.data(0x0100), self.editor._COMMAND_UI)
            self.assertEqual(tag.text(), self.editor._COMMAND_TAG)

    def test_header_menu_has_titled_sections_with_presets_last(self):
        from uitk.widgets.separator import Separator

        titles = [
            s.title
            for s in self.editor.header.menu.findChildren(Separator)
            if s.title
        ]
        self.assertEqual(titles, ["View", "Presets"])  # Presets pinned last

    def test_header_widgets_share_fixed_height(self):
        h = self.editor.HEADER_WIDGET_HEIGHT
        self.assertEqual(self.editor.cmb_ui.maximumHeight(), h)
        self.assertEqual(self.editor.le_filter.maximumHeight(), h)
        self.assertEqual(self.editor._show_hidden_checkbox.maximumHeight(), h)
        self.assertEqual(self.editor._cmb_preset.maximumHeight(), h)

    def test_filter_haystack_includes_description(self):
        # Regression: moving the Reset column before Description left the filter's
        # _row_haystack reading the old (now Reset) column index, so filtering by
        # description text silently matched nothing.
        self.sb.register_command(
            "findme_cmd", lambda: None, doc="zzdistinctivedoc"
        )
        self._select_commands()
        for r in range(self.editor.table.rowCount()):
            item = self.editor.table.item(r, self.editor.COL_ACTION)
            if item and item.toolTip().endswith("findme_cmd"):
                self.assertIn("zzdistinctivedoc", self.editor._row_haystack(r))
                break
        else:
            self.fail("findme_cmd row not found")

    def test_apply_routes_to_set_command_shortcut(self):
        self._select_commands()
        self.editor._apply_shortcut(0, "Ctrl+Alt+P")
        method = self.editor.table.item(0, 0).toolTip().replace("Method: ", "")
        entry = {e["method"]: e for e in self.sb.get_command_registry()}[method]
        self.assertEqual(entry["current"], "Ctrl+Alt+P")

    def test_reset_routes_to_set_command_shortcut(self):
        self.sb.set_command_shortcut("reopen_last_ui", "F8", "application")
        self._select_commands()
        self.editor.reset_shortcut(
            self.editor._COMMAND_UI, "reopen_last_ui", "", "application"
        )
        entry = {e["method"]: e for e in self.sb.get_command_registry()}[
            "reopen_last_ui"
        ]
        self.assertEqual(entry["current"], "")

    def test_show_all_includes_command_rows(self):
        self.editor._set_show_all(True)
        tags = [
            self.editor.table.item(r, 5).text()
            for r in range(self.editor.table.rowCount())
            if self.editor.table.item(r, 5)
        ]
        self.assertIn(self.editor._COMMAND_TAG, tags)

    def test_export_import_round_trips_commands(self):
        self.sb.set_command_shortcut("reopen_last_ui", "F6", "application")
        data = self.editor.export_shortcuts()
        self.assertIn(self.editor._COMMAND_UI, data)
        self.assertEqual(
            data[self.editor._COMMAND_UI]["reopen_last_ui"]["seq"], "F6"
        )
        # Import a different binding back through the command path.
        self.editor.import_shortcuts(
            {self.editor._COMMAND_UI: {"reopen_last_ui": {"seq": "F7", "scope": "application"}}}
        )
        entry = {e["method"]: e for e in self.sb.get_command_registry()}[
            "reopen_last_ui"
        ]
        self.assertEqual(entry["current"], "F7")

    def test_command_scope_toggle_locked_to_application(self):
        # Even bound, a command's scope toggle is disabled — commands have no
        # window of their own, so window scope is meaningless/fragile.
        self.sb.set_command_shortcut("reopen_last_ui", "F5", "application")
        self._select_commands()
        for r in range(self.editor.table.rowCount()):
            if self.editor.table.item(r, 0).toolTip().endswith("reopen_last_ui"):
                self.assertFalse(self.editor.scope_interactive(r))
                self.assertIn(
                    "application-scoped", self.editor.table.item(r, 2).toolTip()
                )
                self.assertEqual(self.editor.scope_at(r), "application")
                return
        self.fail("reopen_last_ui row not found")

    def test_command_collision_against_command(self):
        self.sb.set_command_shortcut("reopen_last_ui", "Ctrl+9", "application")
        # Assigning the same key to another command (app scope) collides.
        conflicts = self.editor._builtin_internal_collision_checker(
            "Ctrl+9", "application", self.editor._COMMAND_UI, "repeat_last_command"
        )
        self.assertTrue(conflicts)
        self.assertTrue(any("command:" in c.description for c in conflicts))

    def test_non_clearable_command_collision_offers_no_clear(self):
        """A clearable=False external command (e.g. the marking-menu activation
        key, whose on_rebind can't honour an empty sequence) still reports the
        collision but must NOT offer a clear_action that would silently no-op."""
        self.sb.register_command(
            "fixed_activation",
            label="fixed_activation",
            bind=False,
            clearable=False,
            value_getter=lambda: "Ctrl+9",
            on_rebind=lambda seq, scope: None,
        )
        try:
            conflicts = self.editor._builtin_internal_collision_checker(
                "Ctrl+9", "application", self.editor._COMMAND_UI, "repeat_last_command"
            )
            fixed = [c for c in conflicts if "fixed_activation" in c.description]
            self.assertTrue(fixed, "the collision is still reported")
            self.assertIsNone(fixed[0].clear_action)  # but not clearable
            self.assertFalse(fixed[0].breaks_binding)
        finally:
            self.sb.unregister_command("fixed_activation")


# ---------------------------------------------------------------------------
# Host-namespaced persistence (Maya / Blender share one QSettings backend)
# ---------------------------------------------------------------------------
class TestHostNamespacedPersistence(_SwitchboardFixture):
    """Slot/command overrides are namespaced by host ``context_tags`` so Maya
    and Blender (same OS user, one shared QSettings ``(org, app)``) don't
    read/write each other's bindings — mirroring the marking-menu binding store.
    """

    def _clear_state(self):
        # The QSettings sandbox is process-wide (see conftest) and NOT reset
        # between tests, so wipe every shortcut key + migration marker up front
        # for a hermetic start regardless of test order.
        base = self.sb.settings
        for k in list(base.keys()):
            if "shortcuts" in k:
                base.clear(k)

    def setUp(self):
        super().setUp()
        self._clear_state()

    def tearDown(self):
        self._clear_state()
        super().tearDown()

    def _make_sb(self, tags):
        return Switchboard(
            ui_source=self.example_module,
            slot_source=ExampleSlots,
            context_tags=tags,
        )

    def test_shortcut_ns_reflects_host(self):
        self.assertEqual(self._make_sb({"maya"})._shortcut_ns(), "shortcuts_maya.")
        self.assertEqual(
            self._make_sb({"blender"})._shortcut_ns(), "shortcuts_blender."
        )
        self.assertEqual(self._make_sb(None)._shortcut_ns(), "shortcuts.")

    def test_command_key_is_host_namespaced(self):
        self.assertEqual(
            self._make_sb({"maya"})._command_key("reopen_last_ui"),
            "shortcuts_maya.Commands.reopen_last_ui",
        )

    def test_command_overrides_isolated_across_hosts(self):
        sb_m = self._make_sb({"maya"})
        sb_m.set_command_shortcut("reopen_last_ui", "F8", "application")
        sb_b = self._make_sb({"blender"})
        self.assertEqual(  # blender does not see maya's binding
            {e["method"]: e for e in sb_b.get_command_registry()}[
                "reopen_last_ui"
            ]["current"],
            "",
        )
        self.assertEqual(
            {e["method"]: e for e in sb_m.get_command_registry()}[
                "reopen_last_ui"
            ]["current"],
            "F8",
        )

    def test_slot_override_is_host_namespaced(self):
        sb = self._make_sb({"maya"})
        ui = sb.loaded_ui.example
        sb.set_user_shortcut(ui, "txt_input", "Ctrl+J", "window")
        self.assertEqual(
            ui.settings.value("shortcuts_maya.ExampleSlots.txt_input"), "Ctrl+J"
        )
        self.assertIsNone(ui.settings.value("shortcuts.ExampleSlots.txt_input"))

    def test_legacy_override_migrated_into_host_namespace(self):
        std = self._make_sb(None)  # standalone writes the legacy un-suffixed key
        std.set_command_shortcut("reopen_last_ui", "F9", "application")
        sb_m = self._make_sb({"maya"})  # migrates the shared set on construction
        self.assertEqual(
            {e["method"]: e for e in sb_m.get_command_registry()}[
                "reopen_last_ui"
            ]["current"],
            "F9",
        )

    def test_legacy_slot_override_migrated_into_host_namespace(self):
        std = self._make_sb(None)  # standalone writes the legacy un-suffixed key
        ui = std.loaded_ui.example
        std.set_user_shortcut(ui, "txt_input", "Ctrl+J", "window")
        sb_m = self._make_sb({"maya"})  # migrates the shared set on construction
        reg = {
            e["method"]: e
            for e in sb_m.get_shortcut_registry(sb_m.loaded_ui.example)
        }
        self.assertEqual(reg["txt_input"]["current"], "Ctrl+J")

    def test_migration_does_not_clobber_post_migration_edit(self):
        std = self._make_sb(None)
        std.set_command_shortcut("reopen_last_ui", "F9", "application")
        self._make_sb({"maya"}).set_command_shortcut(
            "reopen_last_ui", "F10", "application"
        )  # migrate F9, then the user re-binds to F10
        sb_m2 = self._make_sb({"maya"})  # marker present -> no re-migration
        self.assertEqual(
            {e["method"]: e for e in sb_m2.get_command_registry()}[
                "reopen_last_ui"
            ]["current"],
            "F10",
        )


# ---------------------------------------------------------------------------
# Defensive invariant: no ambiguous application-scoped duplicates
# ---------------------------------------------------------------------------
class TestDuplicateShortcutGuard(QtBaseTestCase):
    """``find_duplicate_application_shortcuts`` detects the exact failure mode
    that killed repeat-last in Maya — two enabled app-scoped QShortcuts on one
    key (Qt fires neither)."""

    def _host(self):
        # A never-shown host is fine: allWidgets() includes hidden widgets, and
        # the helper keys off enabled+context, not visibility. Avoids leaking a
        # visible top-level into the shared QApplication.
        return self.track_widget(QtWidgets.QWidget())

    def _app_shortcut(self, host, seq):
        sc = QtWidgets.QShortcut(QtGui.QKeySequence(seq), host)
        sc.setContext(QtCore.Qt.ApplicationShortcut)
        return sc

    def test_flags_two_enabled_app_shortcuts_on_one_key(self):
        from uitk.managers.shortcut_manager import (
            find_duplicate_application_shortcuts,
        )

        host = self._host()
        seq = "Ctrl+Alt+Shift+F9"  # unique — won't collide with other tests
        self._app_shortcut(host, seq)
        self._app_shortcut(host, seq)
        self.assertEqual(find_duplicate_application_shortcuts().get(seq), 2)

    def test_disabled_duplicate_not_flagged(self):
        from uitk.managers.shortcut_manager import (
            find_duplicate_application_shortcuts,
        )

        host = self._host()
        seq = "Ctrl+Alt+Shift+F11"
        self._app_shortcut(host, seq)
        second = self._app_shortcut(host, seq)
        second.setEnabled(False)  # only one enabled -> not ambiguous
        self.assertNotIn(seq, find_duplicate_application_shortcuts())

    def test_window_scoped_duplicates_not_flagged(self):
        from uitk.managers.shortcut_manager import (
            find_duplicate_application_shortcuts,
        )

        host = self._host()
        seq = "Ctrl+Alt+Shift+F12"
        for _ in range(2):  # window scope is disambiguated by focus -> reusable
            sc = QtWidgets.QShortcut(QtGui.QKeySequence(seq), host)
            sc.setContext(QtCore.Qt.WindowShortcut)
        self.assertNotIn(seq, find_duplicate_application_shortcuts())


# ---------------------------------------------------------------------------
# hidden / editable binding flags (registration + post-hoc) and editor visibility
# ---------------------------------------------------------------------------
class TestBindingVisibilityRegistry(_SwitchboardFixture):
    """The registry layer: hidden/editable defaults, kwargs, post-hoc mutators."""

    def _entry(self, method):
        return {e["method"]: e for e in self.sb.get_command_registry()}[method]

    def test_defaults_visible_and_editable(self):
        self.sb.register_command("plain_cmd", lambda: None)
        e = self._entry("plain_cmd")
        self.assertFalse(e["hidden"])
        self.assertTrue(e["editable"])

    def test_register_hidden_and_non_editable_kwargs(self):
        self.sb.register_command(
            "fixed_cmd", lambda: None, hidden=True, editable=False
        )
        e = self._entry("fixed_cmd")
        self.assertTrue(e["hidden"])
        self.assertFalse(e["editable"])

    def test_set_binding_hidden_post_hoc_and_persists(self):
        self.sb.register_command("toggle_cmd", lambda: None)
        self.assertFalse(self._entry("toggle_cmd")["hidden"])
        self.sb.set_binding_hidden("toggle_cmd", True)
        self.assertTrue(self._entry("toggle_cmd")["hidden"])
        # Persisted under the .hidden twin → a fresh Switchboard re-reading the
        # same sandboxed store resolves the override even though the new spec
        # ships visible by default. (Re-register on the new sb, don't clear.)
        sb2 = Switchboard(ui_source=self.example_module, slot_source=ExampleSlots)
        sb2.register_command("toggle_cmd", lambda: None)
        e2 = {e["method"]: e for e in sb2.get_command_registry()}["toggle_cmd"]
        self.assertTrue(e2["hidden"])

    def test_set_binding_editable_post_hoc(self):
        self.sb.register_command("lockable_cmd", lambda: None)
        self.assertTrue(self._entry("lockable_cmd")["editable"])
        self.sb.set_binding_editable("lockable_cmd", False)
        self.assertFalse(self._entry("lockable_cmd")["editable"])

    def test_mutators_noop_for_unknown_command(self):
        # Must not raise for an unregistered name.
        self.sb.set_binding_hidden("nope", True)
        self.sb.set_binding_editable("nope", False)

    def test_decorator_carries_flags(self):
        from uitk.switchboard import Shortcut

        @Shortcut("Ctrl+K", hidden=True, editable=False)
        def some_slot():
            """doc."""

        meta = some_slot._shortcut_meta
        self.assertTrue(meta["hidden"])
        self.assertFalse(meta["editable"])


class TestEditorHiddenVisibility(_SwitchboardFixture):
    """The editor layer: hidden bindings omitted by default, revealed on toggle;
    non-editable rows render read-only."""

    def setUp(self):
        super().setUp()
        self.editor = ShortcutEditor(self.sb)
        self.editor.refresh_ui_list()

    def tearDown(self):
        if getattr(self, "editor", None):
            self.editor._settings.setValue("show_all", False)
            self.editor._settings.setValue("show_hidden", False)
            self.editor.close()
        super().tearDown()

    def _command_view_methods(self):
        idx = self.editor.cmb_ui.findText(self.editor._COMMANDS_LABEL)
        self.editor.cmb_ui.setCurrentIndex(idx)
        self.editor.populate()
        methods = []
        for r in range(self.editor.table.rowCount()):
            if self.editor.table.columnSpan(r, 0) > 1:
                continue  # message row
            tip = self.editor.table.item(r, 0).toolTip()
            methods.append(tip.replace("Method: ", ""))
        return methods

    def test_hidden_command_absent_by_default_revealed_on_toggle(self):
        self.sb.register_command(
            "ghost_cmd", lambda: None, sequence="Ctrl+Alt+G", hidden=True
        )
        self.assertNotIn("ghost_cmd", self._command_view_methods())
        # Reveal hidden → it shows.
        self.editor._set_show_hidden(True)
        self.assertIn("ghost_cmd", self._command_view_methods())

    def test_hidden_command_excluded_from_show_all_by_default(self):
        self.sb.register_command(
            "ghost2_cmd", lambda: None, sequence="Ctrl+Alt+H", hidden=True
        )
        self.editor._set_show_all(True)
        methods = []
        for r in range(self.editor.table.rowCount()):
            item = self.editor.table.item(r, 0)
            if item and self.editor.table.columnSpan(r, 0) == 1:
                methods.append(item.toolTip().replace("Method: ", ""))
        self.assertNotIn("ghost2_cmd", methods)

    def test_non_editable_row_is_not_editable_in_cell(self):
        self.sb.register_command(
            "fixed2_cmd", lambda: None, sequence="Ctrl+Alt+J", editable=False
        )
        idx = self.editor.cmb_ui.findText(self.editor._COMMANDS_LABEL)
        self.editor.cmb_ui.setCurrentIndex(idx)
        self.editor.populate()
        for r in range(self.editor.table.rowCount()):
            item = self.editor.table.item(r, 0)
            if not item or self.editor.table.columnSpan(r, 0) > 1:
                continue
            if item.toolTip().replace("Method: ", "") == "fixed2_cmd":
                seq_item = self.editor.table.item(r, 1)
                self.assertFalse(
                    bool(seq_item.flags() & QtCore.Qt.ItemIsEditable),
                    "a non-editable binding's Shortcut cell must not be editable",
                )
                break
        else:
            self.fail("fixed2_cmd row not found in the Commands view")

    def test_non_editable_with_sequence_scope_locked_not_unassigned(self):
        # Regression: a bound key must NOT show the misleading "Assign a shortcut
        # before choosing its scope" (unassigned-only) message. A command's scope
        # cell is the consistent, non-interactive application-scoped command badge
        # — commands are always app-scoped, so the badge wins over editable/bound
        # state (kept uniform across the Commands view; see _set_scope_cell).
        self.sb.register_command(
            "fixed3_cmd", lambda: None, sequence="Ctrl+Alt+K", editable=False
        )
        idx = self.editor.cmb_ui.findText(self.editor._COMMANDS_LABEL)
        self.editor.cmb_ui.setCurrentIndex(idx)
        self.editor.populate()
        for r in range(self.editor.table.rowCount()):
            item = self.editor.table.item(r, 0)
            if not item or self.editor.table.columnSpan(r, 0) > 1:
                continue
            if item.toolTip().replace("Method: ", "") == "fixed3_cmd":
                self.assertFalse(self.editor.scope_interactive(r))  # locked
                tip = self.editor.table.item(r, 2).toolTip().lower()
                self.assertNotIn("assign a shortcut", tip)
                self.assertIn("application-scoped", tip)
                break
        else:
            self.fail("fixed3_cmd row not found in the Commands view")

    def test_unbound_command_scope_is_app_badge_not_unassigned(self):
        # A command's scope cell is the consistent, non-interactive
        # application-scoped badge even when UNBOUND — not the grey "assign a
        # shortcut first" icon (which read inconsistently against a bound
        # command's badge in the Commands view).
        self.sb.register_command("unbound_cmd", lambda: None)  # no sequence → unbound
        idx = self.editor.cmb_ui.findText(self.editor._COMMANDS_LABEL)
        self.editor.cmb_ui.setCurrentIndex(idx)
        self.editor.populate()
        for r in range(self.editor.table.rowCount()):
            item = self.editor.table.item(r, 0)
            if not item or self.editor.table.columnSpan(r, 0) > 1:
                continue
            if item.toolTip().replace("Method: ", "") == "unbound_cmd":
                self.assertFalse(self.editor.scope_interactive(r))
                tip = self.editor.table.item(r, 2).toolTip().lower()
                self.assertIn("application-scoped", tip)
                self.assertNotIn("assign a shortcut", tip)
                break
        else:
            self.fail("unbound_cmd row not found in the Commands view")


if __name__ == "__main__":
    unittest.main()
