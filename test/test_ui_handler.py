# !/usr/bin/python
# coding=utf-8
"""Unit tests for ``UiHandler.can_resolve`` — the base UI-resolution hook.

``can_resolve`` is the handler-side contract behind
``SwitchboardWidgetMixin.ui_name_resolves``: it reports whether ``get(name)``
would resolve to a UI *without building it*, so marking-menu destination
resolution (nav-button click + auto-hide) can recognise a handler's UIs. The
base implementation resolves registered ``.ui`` file stems (stripping any
``#submenu`` suffix); subclasses extend it for non-file sources (e.g.
``MayaUiHandler`` adds its native-menu names — see mayatk's
``test_maya_ui_handler``). Pinning the base keeps that contract stable.

``__init__`` is bypassed (it discovers slots/UIs); ``can_resolve`` only needs
``self.sb.is_registered_ui``.
"""
import types
import unittest

from uitk.handlers.ui_handler import UiHandler


class TestUiHandlerCanResolve(unittest.TestCase):
    def setUp(self):
        self.handler = object.__new__(UiHandler)
        self._registered = {"polygons", "editors"}
        self.handler.sb = types.SimpleNamespace(
            is_registered_ui=lambda n: n in self._registered
        )

    def test_registered_stem_resolves(self):
        self.assertTrue(self.handler.can_resolve("polygons"))

    def test_unregistered_stem_does_not_resolve(self):
        self.assertFalse(self.handler.can_resolve("not_a_ui"))

    def test_submenu_suffix_strips_to_base(self):
        """'<stem>#submenu' resolves on the base stem, mirroring get()."""
        self.assertTrue(self.handler.can_resolve("polygons#submenu"))
        self.assertFalse(self.handler.can_resolve("not_a_ui#submenu"))

    def test_tagged_submenu_strips_to_base(self):
        """Only the first '#'-segment (the base) is consulted."""
        self.assertTrue(self.handler.can_resolve("polygons#edge#submenu"))

    def test_empty_name_does_not_resolve(self):
        self.assertFalse(self.handler.can_resolve(""))
        self.assertFalse(self.handler.can_resolve(None))


if __name__ == "__main__":
    unittest.main()
