# !/usr/bin/python
# coding=utf-8
"""Tests for the History primitive and the Switchboard navigation API.

Covers:
- History: cap (incl. immediate trim on maxlen change), identity de-dup,
  key-based inc/exc filtering, out-of-range contract, weak pruning, remove.
- Switchboard.ui_history weak storage (leak fix) + unchanged read contract.
- show_prev_ui(): skips the current UI and transient (startmenu/submenu) UIs.
- repeat_last(): re-invokes the last slot with its widget context; the repeat
  doesn't overwrite the captured wrapper; no-op when nothing has run.
- slot_history(): add/remove/index/dedup/length regression after refactor.

Run standalone: python -m test.test_switchboard_history
"""
import gc
import unittest
import weakref

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets
from uitk.switchboard import Switchboard
from uitk.switchboard.history import History
from uitk.switchboard.slots import SlotWrapper
from uitk.examples.example import ExampleSlots


# ---------------------------------------------------------------------------
# History primitive
# ---------------------------------------------------------------------------
class TestHistory(unittest.TestCase):
    def test_cap_drops_oldest_on_add(self):
        h = History(maxlen=3)
        for i in range(5):
            h.add(i)
        self.assertEqual(h.view(allow_duplicates=True), [2, 3, 4])

    def test_maxlen_change_trims_immediately(self):
        h = History(maxlen=10)
        for i in range(6):
            h.add(i)
        h.maxlen = 2  # legacy slot_history(length=...) behaviour
        self.assertEqual(h.view(allow_duplicates=True), [4, 5])

    def test_dedup_keeps_most_recent_occurrence(self):
        h = History(maxlen=10)
        for x in ("a", "b", "a"):
            h.add(x)
        self.assertEqual(h.view(), ["b", "a"])

    def test_key_filter_inc(self):
        class Obj:
            def __init__(self, n):
                self.n = n

        h = History(maxlen=10, key=lambda o: o.n)
        objs = [Obj("foo"), Obj("bar"), Obj("foobar")]
        h.add(objs)
        self.assertEqual([o.n for o in h.view(inc="foo")], ["foo"])  # exact
        self.assertEqual(
            [o.n for o in h.view(inc="foo*")], ["foo", "foobar"]  # prefix
        )

    def test_get_out_of_range_contract(self):
        h = History(maxlen=10)
        h.add(1)
        self.assertEqual(h.get(99), [])  # int oob -> [] (legacy contract)
        self.assertEqual(h.get(slice(5, 9)), [])  # slice never raises -> []

    def test_remove(self):
        h = History(maxlen=10)
        h.add([1, 2, 3])
        h.remove(2)
        self.assertEqual(h.view(allow_duplicates=True), [1, 3])

    def test_weak_storage_prunes_dead(self):
        class Obj:
            pass

        h = History(maxlen=10, weak=True)
        live = Obj()
        dead = Obj()
        h.add(live)
        h.add(dead)
        wr = weakref.ref(dead)
        del dead
        gc.collect()
        self.assertIsNone(wr())
        self.assertEqual(h.view(allow_duplicates=True), [live])
        self.assertEqual(len(h), 1)


# ---------------------------------------------------------------------------
# Switchboard UI history + navigation verbs
# ---------------------------------------------------------------------------
class TestSwitchboardNavigation(QtBaseTestCase):
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

    def tearDown(self):
        # show_prev_ui() shows a real window; close any loaded UI so a leaked
        # visible top-level can't flake later (focus/active-window-sensitive)
        # tests in the shared QApplication.
        for ui in list(self.sb.loaded_ui.values()):
            try:
                ui.close()
            except RuntimeError:
                pass
        super().tearDown()

    def test_ui_history_store_is_weak(self):
        # The leak fix: the UI history must not pin closed windows alive.
        self.assertTrue(self.sb._ui_history._weak)

    def test_ui_history_returns_live_uis_in_order(self):
        a = self.sb.add_ui("navA")
        b = self.sb.add_ui("navB")
        self.sb.current_ui = a
        self.sb.current_ui = b
        hist = self.sb.ui_history()
        self.assertEqual([u.objectName() for u in hist[-2:]], ["navA", "navB"])

    def test_show_prev_ui_skips_visible_and_transient(self):
        a = self.sb.add_ui("realA")
        sub = self.sb.add_ui("subB", tags={"submenu"})
        c = self.sb.add_ui("realC")
        self.sb.current_ui = a
        self.sb.current_ui = sub
        self.sb.current_ui = c
        c.show()  # c is on screen -> nothing to reopen there
        QtWidgets.QApplication.processEvents()
        shown = self.sb.show_prev_ui()
        # reversed = [c(visible,skip), sub(transient,skip), a(hidden)] -> a
        self.assertIs(shown, a)
        self.assertTrue(a.isVisible())

    def test_show_prev_ui_none_when_only_visible(self):
        a = self.sb.add_ui("solo")
        self.sb.current_ui = a
        a.show()  # the one UI is already on screen -> nothing to reopen
        QtWidgets.QApplication.processEvents()
        self.assertIsNone(self.sb.show_prev_ui())

    def test_show_prev_ui_reopens_closed_current(self):
        # Regression: 'reopen last ui' worked once then died. Showing a UI makes
        # it _current_ui (focus); after the user closes it, it is still current,
        # and the old "skip the current one" rule then made it unreopenable. It
        # must reopen instead of returning None.
        a = self.sb.add_ui("reopenA")
        b = self.sb.add_ui("reopenB")
        self.sb.current_ui = a
        self.sb.current_ui = b
        b.show()
        QtWidgets.QApplication.processEvents()
        # First press brings back the hidden A; showing it makes it current.
        self.assertIs(self.sb.show_prev_ui(), a)
        self.sb.current_ui = a
        a.hide()  # user closes the reopened window
        QtWidgets.QApplication.processEvents()
        # Pressing again must reopen A, not no-op.
        self.assertIs(self.sb.show_prev_ui(), a)
        self.assertTrue(a.isVisible())

    def test_repeat_last_reinvokes_with_widget(self):
        calls = []

        def myslot(widget=None):
            calls.append(widget)

        w = self.track_widget(QtWidgets.QPushButton())
        w.setObjectName("b000")
        wrapper = SlotWrapper(myslot, w, self.sb)

        wrapper()  # first dispatch
        self.assertEqual(len(calls), 1)
        self.assertIs(self.sb._last_slot_wrapper, wrapper)

        ret = self.sb.repeat_last()
        self.assertEqual(len(calls), 2)
        self.assertIs(calls[1], w)  # widget context preserved
        # The repeat must not overwrite the captured wrapper with itself.
        self.assertIs(self.sb._last_slot_wrapper, wrapper)

    def test_repeat_last_replays_required_positional(self):
        # Regression: a slot taking the signal payload as a *required*
        # positional (e.g. a list slot's clicked ``item``) must repeat with
        # that arg. A bare wrapper() re-call dropped it and raised
        # "TypeError: ...list000() missing 1 required positional argument: 'item'".
        seen = []

        def list_slot(item):
            seen.append(item)

        w = self.track_widget(QtWidgets.QPushButton())
        w.setObjectName("list000")
        wrapper = SlotWrapper(list_slot, w, self.sb)

        wrapper("payload")  # first dispatch carries the signal's item arg
        self.assertEqual(seen, ["payload"])

        self.sb.repeat_last()
        self.assertEqual(seen, ["payload", "payload"])  # replayed same item

    def test_repeat_last_noop_when_nothing_run(self):
        self.sb._last_slot_wrapper = None
        self.assertIsNone(self.sb.repeat_last())

    def test_repeat_last_survives_dead_widget(self):
        class RaisingWrapper:
            _last_invocation_args = ()
            _last_invocation_kwargs = {}

            def _invoke(self, *args, **kwargs):
                raise RuntimeError("dead C++ widget")

        self.sb._last_slot_wrapper = RaisingWrapper()
        self.assertIsNone(self.sb.repeat_last())  # fails soft, no crash
        self.assertFalse(self.sb._suppress_slot_capture)  # flag reset

    def test_show_prev_ui_skips_stale_entry(self):
        class FakeUI:
            def __init__(self, name, raise_on_show=False):
                self._name = name
                self._raise = raise_on_show
                self.shown = False

            def objectName(self):
                return self._name

            def has_tags(self, tags):
                return False

            def isVisible(self):
                return False  # hidden -> a reopen candidate

            def show(self):
                if self._raise:
                    raise RuntimeError("dead C++ window")
                self.shown = True

        good = FakeUI("good")
        stale = FakeUI("stale", raise_on_show=True)
        self.sb._current_ui = None
        self.sb._ui_history.add(good)
        self.sb._ui_history.add(stale)  # most recent -> tried first
        shown = self.sb.show_prev_ui()
        self.assertIs(shown, good)
        self.assertTrue(good.shown)

    def test_prev_slot_returns_bare_method(self):
        # Back-compat: prev_slot must still be the underlying method (HUD reads
        # __doc__/__name__ off it), not the wrapper.
        def doc_slot(widget=None):
            """docstring."""

        w = self.track_widget(QtWidgets.QPushButton())
        w.setObjectName("b001")
        SlotWrapper(doc_slot, w, self.sb)()
        self.assertIs(self.sb.prev_slot, doc_slot)
        self.assertEqual(self.sb.prev_slot.__doc__, "docstring.")


# ---------------------------------------------------------------------------
# slot_history regression (post-refactor)
# ---------------------------------------------------------------------------
class TestSlotHistoryRegression(QtBaseTestCase):
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

    def test_dedup_keeps_recent(self):
        def a():
            pass

        def b():
            pass

        self.sb.slot_history(add=a)
        self.sb.slot_history(add=b)
        self.sb.slot_history(add=a)
        names = [m.__name__ for m in self.sb.slot_history()]
        self.assertEqual(names.count("a"), 1)
        self.assertEqual(self.sb.slot_history(index=-1), a)

    def test_length_trims_without_add(self):
        slots = []
        for i in range(8):
            f = (lambda: None)
            f.__name__ = f"s{i}"
            slots.append(f)
            self.sb.slot_history(add=f, allow_duplicates=True)
        capped = self.sb.slot_history(length=3, allow_duplicates=True)
        self.assertLessEqual(len(capped), 3)

    def test_filter_inc(self):
        def foo_a():
            pass

        def bar_b():
            pass

        self.sb.slot_history(add=foo_a)
        self.sb.slot_history(add=bar_b)
        res = self.sb.slot_history(inc="foo*")
        self.assertEqual([m.__name__ for m in res], ["foo_a"])


if __name__ == "__main__":
    unittest.main()
