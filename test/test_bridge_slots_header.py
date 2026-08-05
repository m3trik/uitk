# !/usr/bin/python
# coding=utf-8
"""Unit tests for the data-driven ``BridgeSlotsBase.header_init``.

The bridge / workflow slots used to each hand-roll a ``header_init`` that built
the same "Utilities" separator + menu buttons + ``set_help_text``. That is now a
single default on :class:`uitk.bridge.BridgeSlotsBase` driven by two class-attr
hooks -- :attr:`HEADER_MENU_ITEMS` (or :meth:`header_menu_items`) and
:attr:`HELP_SPEC` (or :meth:`help_spec`). These tests pin that mechanism with a
fake header so a regression can't silently drop a menu item or the help button.
"""
import unittest

from uitk.bridge import BridgeSlotsBase


class _FakeSignal:
    def __init__(self):
        self.handlers = []

    def connect(self, fn):
        self.handlers.append(fn)

    def emit(self):
        for fn in self.handlers:
            fn()


class _FakeButton:
    def __init__(self):
        self.clicked = _FakeSignal()


class _FakeMenu:
    """Records ``add(...)`` calls and exposes each objectName as a fake button."""

    def __init__(self):
        self.adds = []
        self._buttons = {}

    def add(self, typ, **kw):
        self.adds.append((typ, kw))
        name = kw.get("setObjectName")
        if name:
            self._buttons[name] = _FakeButton()

    def __getattr__(self, item):
        buttons = self.__dict__.get("_buttons", {})
        if item in buttons:
            return buttons[item]
        raise AttributeError(item)


class _FakeHeader:
    def __init__(self):
        self.menu = _FakeMenu()
        self.help_text = None

    def set_help_text(self, text):
        self.help_text = text


def _labels(header):
    return [kw.get("setText") for typ, kw in header.menu.adds if typ == "QPushButton"]


class DefaultHeaderMenuTest(unittest.TestCase):
    """The base default = Clear Log only, no help.

    Template management (Refresh / Open Folder) deliberately lives on the
    template combo's own menu (``cmb000_init``), not the header.
    """

    def _slot(self):
        # Bypass __init__ (needs a live switchboard/panel); header_init only
        # touches the passed widget + the slot's handler methods.
        return BridgeSlotsBase.__new__(BridgeSlotsBase)

    def test_default_items_added_and_wired(self):
        slot = self._slot()
        header = _FakeHeader()
        slot.header_init(header)
        # A leading "Utilities" separator, then the panel-level utility.
        self.assertEqual(header.menu.adds[0][0], "Separator")
        self.assertEqual(_labels(header), ["Clear Log"])

    def test_default_handlers_resolve_to_base_methods(self):
        slot = self._slot()
        calls = []
        slot.clear_log = lambda: calls.append("clear")
        header = _FakeHeader()
        slot.header_init(header)
        header.menu._buttons["btn_clear_log"].clicked.emit()
        self.assertEqual(calls, ["clear"])

    def test_template_actions_absent_from_header(self):
        # The moved actions must not silently reappear in the default header.
        slot = self._slot()
        header = _FakeHeader()
        slot.header_init(header)
        self.assertNotIn("btn_open_templates", header.menu._buttons)
        self.assertNotIn("btn_refresh_templates", header.menu._buttons)
        # The handlers themselves stay on the base (the combo menu and any
        # subclass header override -- e.g. rizom's "Open Scripts Folder" --
        # still resolve them).
        self.assertTrue(callable(slot.open_templates_folder))
        self.assertTrue(callable(slot.refresh_templates))

    def test_no_help_when_spec_absent(self):
        slot = self._slot()
        header = _FakeHeader()
        slot.header_init(header)
        self.assertIsNone(header.help_text)


class CustomHeaderMenuTest(unittest.TestCase):
    """Subclasses override the data, not the code."""

    def test_custom_items_and_help(self):
        class _Custom(BridgeSlotsBase):
            HEADER_MENU_ITEMS = (
                ("Do X", "btn_x", "tip x", "_do_x"),
                ("Clear Log", "btn_clear_log", "Clear the log.", "clear_log"),
            )
            HELP_SPEC = {"title": "Title", "body": "Body", "steps": ["one"]}

            def __init__(self):
                self.fired = []

            def _do_x(self):
                self.fired.append("x")

            def clear_log(self):
                self.fired.append("clear")

        slot = _Custom()
        header = _FakeHeader()
        slot.header_init(header)
        self.assertEqual(_labels(header), ["Do X", "Clear Log"])
        # Help button populated (fmt produced a non-empty rich-text string).
        self.assertTrue(header.help_text)
        self.assertIn("Title", header.help_text)
        header.menu._buttons["btn_x"].clicked.emit()
        self.assertEqual(slot.fired, ["x"])

    def test_dynamic_items_via_method_override(self):
        class _Dynamic(BridgeSlotsBase):
            ENGINE_LABEL = "Metashape"

            def header_menu_items(self):
                return (
                    ("Cancel Run", "btn_cancel", f"Kill {self.ENGINE_LABEL}.", "cancel_run"),
                    ("Clear Log", "btn_clear_log", "Clear the log.", "clear_log"),
                )

            def cancel_run(self):
                pass

            def clear_log(self):
                pass

        slot = _Dynamic.__new__(_Dynamic)
        header = _FakeHeader()
        slot.header_init(header)
        self.assertEqual(_labels(header), ["Cancel Run", "Clear Log"])
        cancel_tip = next(
            kw["setToolTip"] for _t, kw in header.menu.adds
            if kw.get("setObjectName") == "btn_cancel"
        )
        self.assertEqual(cancel_tip, "Kill Metashape.")

    def test_missing_handler_raises(self):
        class _Bad(BridgeSlotsBase):
            HEADER_MENU_ITEMS = (("Y", "btn_y", "t", "does_not_exist"),)

        slot = _Bad.__new__(_Bad)
        with self.assertRaises(AttributeError):
            slot.header_init(_FakeHeader())


if __name__ == "__main__":
    unittest.main()
