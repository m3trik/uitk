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

from qtpy import QtWidgets

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


if __name__ == "__main__":
    unittest.main(exit=False)
