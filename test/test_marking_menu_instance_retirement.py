# !/usr/bin/python
# coding=utf-8
"""Regression: a SECOND MarkingMenu in one process must not fight the first.

Live-Maya symptom (tentacle dev-reload workflow): after re-instantiating
TclMaya in a long-lived Maya session, holding L+R opened the chord menu but
releasing over a MenuButton launched nothing. Two-instance probe showed the
gesture being serviced with STALE state:

* ``_submenu_cache`` was a class-level dict shared by every instance, so the
  new instance resolved nav targets to the OLD instance's wrappers — whose
  native-menu content the new instance's build had re-wrapped (hollowed).
* The old instance's activation ``GlobalShortcut`` (and any grabs) stayed
  live, so whichever instance won the event race dispatched with dead caches.

The invariant under test: constructing a new MarkingMenu RETIRES any previous
live instance (activation shortcut disposed, activation callbacks inert) and
never shares per-instance caches.
"""

import unittest

from qtpy import QtCore, QtGui, QtWidgets

from conftest import QtBaseTestCase
from uitk.widgets.marking_menu._marking_menu import MarkingMenu


class MarkingMenuInstanceIsolation(QtBaseTestCase):
    def _make(self, parent):
        mm = MarkingMenu(parent=parent, log_level="ERROR")
        self.track_widget(mm)
        mm.hide()
        return mm

    def setUp(self):
        super().setUp()
        self.parent = QtWidgets.QWidget()
        self.parent.show()
        self.track_widget(self.parent)

    def test_submenu_cache_is_per_instance(self):
        mm1 = self._make(self.parent)
        mm2 = self._make(self.parent)
        self.assertIsNot(
            mm1._submenu_cache,
            mm2._submenu_cache,
            "submenu cache is shared across instances (class-level dict) — "
            "a reloaded instance would resolve nav targets to the old "
            "instance's hollowed wrappers",
        )
        # And neither aliases the class-level fallback (bypass-fixture default).
        self.assertIsNot(mm1._submenu_cache, MarkingMenu._submenu_cache)

    def test_previous_instance_is_retired_on_new_construction(self):
        mm1 = self._make(self.parent)
        self.assertFalse(mm1._retired)
        self.assertIsNotNone(mm1._shortcut_instance)

        mm2 = self._make(self.parent)
        self.assertTrue(mm1._retired, "old instance must be retired")
        self.assertIsNone(
            mm1._shortcut_instance,
            "old instance's activation GlobalShortcut must be disposed",
        )
        self.assertFalse(mm2._retired)
        self.assertIsNotNone(mm2._shortcut_instance)

    def test_retired_instance_ignores_activation(self):
        mm1 = self._make(self.parent)
        self._make(self.parent)  # retires mm1
        mm1._on_activation_press()
        self.assertFalse(
            mm1._activation_key_held,
            "a retired instance must not react to the activation key",
        )
        mm1._on_activation_release()  # must be a silent no-op too

    def test_retiring_disarms_the_switchboards_shortcuts(self):
        """Retiring must release ALL input, not just the activation key.

        Application-scoped shortcuts are parented to the host window, so Qt keeps
        them armed after the instance that registered them is gone; the next
        instance's copies then ambiguate with them and Qt fires neither. Live
        Maya, before this: one reload took two user hotkeys from one armed
        shortcut each to three each.
        """
        from qtpy import QtGui

        mm1 = self._make(self.parent)
        mm1.sb.register_command("probe_cmd", lambda: None, sequence="Ctrl+Alt+5")
        host = mm1.sb._command_host()
        self.assertIsNotNone(host, "no host window resolved — fixture is unsound")

        def armed():
            want = QtGui.QKeySequence("Ctrl+Alt+5")
            count = 0
            for sc in host.findChildren(QtGui.QShortcut):
                try:
                    if sc.key() == want and sc.isEnabled():
                        count += 1
                except RuntimeError:
                    continue
            return count

        self.assertEqual(armed(), 1)
        mm1.retire()
        self.assertEqual(
            armed(), 0, "a retired instance must leave no armed shortcut behind"
        )

    def test_retired_instance_cannot_rearm_activation(self):
        # A stale editor callback (set_activation_key on the old instance)
        # must not re-install its GlobalShortcut.
        mm1 = self._make(self.parent)
        self._make(self.parent)  # retires mm1
        mm1._install_activation_shortcut()
        self.assertIsNone(
            mm1._shortcut_instance,
            "a retired instance must not re-arm its activation shortcut",
        )


class MarkingMenuSurvivesModuleReload(QtBaseTestCase):
    """The retirement registry must be process-wide, not per class OBJECT.

    ``Settings > Reload Scripts`` reloads uitk in place, which builds a SECOND
    ``MarkingMenu`` class object. When the registry lived on the class, the new
    generation started with an EMPTY set, so the pre-reload instance was never
    retired: its activation ``GlobalShortcut`` stayed armed on the same host
    widget as the new one's, the two ambiguated, and the menu stopped opening
    until the DCC was restarted.
    """

    def setUp(self):
        super().setUp()
        self.parent = QtWidgets.QWidget()
        self.parent.show()
        self.track_widget(self.parent)

    @staticmethod
    def _reloaded_class():
        """A second ``MarkingMenu`` class object, as ``importlib.reload`` makes.

        Executed into a THROWAWAY module namespace rather than reloading the
        real one, so the generation fork under test is reproduced exactly
        without leaving the rest of the suite bound to a half-new module.
        """
        import importlib.util

        name = "uitk.widgets.marking_menu._marking_menu"
        spec = importlib.util.find_spec(name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.MarkingMenu

    def test_new_generation_retires_the_pre_reload_instance(self):
        mm1 = MarkingMenu(parent=self.parent, log_level="ERROR")
        self.track_widget(mm1)
        mm1.hide()

        Reloaded = self._reloaded_class()
        self.assertIsNot(Reloaded, MarkingMenu, "fixture must fork the class")

        mm2 = Reloaded(parent=self.parent, log_level="ERROR")
        self.track_widget(mm2)
        mm2.hide()

        self.assertTrue(
            mm1._retired,
            "an instance from before the reload must be retired by the one after",
        )
        self.assertIsNone(
            mm1._shortcut_instance,
            "the pre-reload activation shortcut must be disposed — two armed "
            "shortcuts on one host widget ambiguate and the menu stops opening",
        )

    def test_registry_is_shared_across_generations(self):
        Reloaded = self._reloaded_class()
        self.assertIs(
            MarkingMenu._live_registry(),
            Reloaded._live_registry(),
            "both class generations must resolve the SAME process-wide registry",
        )

    def test_retire_all_reaches_every_generation(self):
        mm1 = MarkingMenu(parent=self.parent, log_level="ERROR")
        self.track_widget(mm1)
        mm1.hide()

        Reloaded = self._reloaded_class()
        # retire_all is the pre-reload teardown hook tentacle calls; invoked
        # from the NEW generation it must still reach the OLD instance, and it
        # must hand the instances back so the caller can dispose of them
        # without touching the private registry.
        self.assertEqual(Reloaded.retire_all(), [mm1])
        self.assertTrue(mm1._retired)


class RetiringDoesNotDisarmTheReplacement(QtBaseTestCase):
    """``retire()`` disposes the retiring instance's Switchboard shortcuts.

    That sweep is what stops a rebuild from stacking ambiguous bindings on the
    host window, but it makes an invariant load-bearing that nothing else
    states: each MarkingMenu must own its OWN Switchboard. Were one ever shared
    between instances, the retire that runs at the END of the replacement's
    ``__init__`` would dispose the bindings that replacement had just
    registered, and its hotkeys would be dead on arrival — silently, because a
    disposed shortcut raises nothing.
    """

    def setUp(self):
        super().setUp()
        self.parent = QtWidgets.QWidget()
        self.parent.show()
        self.track_widget(self.parent)
        self.host = QtWidgets.QWidget()
        self.host.show()
        self.track_widget(self.host)

    def _make(self):
        mm = MarkingMenu(parent=self.parent, log_level="ERROR")
        self.track_widget(mm)
        mm.hide()
        return mm

    def _armed(self, sequence):
        want = QtGui.QKeySequence(sequence)
        count = 0
        for shortcut in self.host.findChildren(QtGui.QShortcut):
            try:
                if shortcut.key() == want and shortcut.isEnabled():
                    count += 1
            except RuntimeError:  # C++ side already gone
                continue
        return count

    def test_each_instance_owns_its_switchboard(self):
        mm1 = self._make()
        mm2 = self._make()
        self.assertIsNot(
            mm1.sb,
            mm2.sb,
            "retire() disposes self.sb's shortcuts — a Switchboard shared "
            "between instances would take the replacement's bindings with it",
        )

    def _bind(self, menu, sequence):
        """Arm one application-scoped shortcut on the shared host, the way a
        slot's binding is held (see ``dispose_shortcuts``)."""
        slots = type("_Slots", (), {})()
        slots._connected_shortcuts = {
            "do_thing": menu.sb._make_host_shortcut(
                sequence, self.host, lambda: None, QtCore.Qt.ApplicationShortcut
            )
        }
        menu.sb.slot_instances["probe_ui"] = slots

    def test_the_replacements_binding_survives_and_does_not_stack(self):
        mm1 = self._make()
        self._bind(mm1, "Ctrl+Alt+5")
        self.assertEqual(self._armed("Ctrl+Alt+5"), 1, "fixture armed nothing")

        mm2 = self._make()  # retires mm1, disposing its Switchboard's shortcuts
        self.assertTrue(mm1._retired)
        self.assertEqual(
            self._armed("Ctrl+Alt+5"),
            0,
            "the retired instance's binding must not stay armed on the host",
        )

        self._bind(mm2, "Ctrl+Alt+5")
        self.assertEqual(
            self._armed("Ctrl+Alt+5"),
            1,
            "exactly one armed shortcut per sequence — two on one parent are "
            "ambiguous and Qt fires neither",
        )


if __name__ == "__main__":
    unittest.main(exit=False)
