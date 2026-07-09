# !/usr/bin/python
# coding=utf-8
"""Integration tests for the dynamic-init paths exercised by mayatk's
``scene_exporter`` and tentacle's slot classes.

These tests cover contract surface that lives at the intersection of
:class:`uitk.Switchboard`, :class:`uitk.MainWindow`, and the slot
pipeline in ``_slots.py``.  They complement the unit tests
in ``test_menu.py`` (which test :class:`Menu` in isolation).

Coverage:

- **Slot-constructor re-entrancy** — when a slot's ``__init__`` accesses
  ``self.ui.<child>``, the child's ``<name>_init`` is queued in the
  placeholder's ``deferred_widgets`` and processed **after** the slot
  constructor returns, in queue order.

- **``refresh_on_show`` / ``is_initialized``** — slots may opt into being
  re-runnable.  Structural setup is gated behind
  ``if not widget.is_initialized:`` while data refresh runs every call.

- **Re-entrant ``widget.init_slot()`` from a menu-item signal handler** —
  scene_exporter wires checkboxes whose handlers call
  ``widget.init_slot()`` to refresh the parent.  The gated portion must
  skip on re-entry; menu items captured as slot attributes
  (``self._chk = widget.option_box.menu.add(...)``) must remain valid.

- **``option_box.add_option(plugin)`` plugin path** — bypasses ``Menu.add``,
  routes through the same deferred-wrap machinery.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets

from uitk.switchboard import Switchboard


# ---------------------------------------------------------------------------
# Fixture: minimal .ui file with named children
# ---------------------------------------------------------------------------


_UI_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>{cls}</class>
 <widget class="QMainWindow" name="{name}">
  <widget class="QWidget" name="centralwidget">
   <layout class="QVBoxLayout" name="vlayout">
{children}
   </layout>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _child_xml(widget_class, object_name):
    return f"""    <item>
     <widget class="{widget_class}" name="{object_name}"/>
    </item>"""


def _write_ui(path, name, child_specs):
    """Write a minimal .ui file with the given children.

    Args:
        path: Output .ui file path.
        name: UI's objectName (also derives slot class name).
        child_specs: list of (widget_class, object_name) tuples.
    """
    children = "\n".join(_child_xml(c, n) for c, n in child_specs)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_UI_TEMPLATE.format(cls=name.capitalize(), name=name, children=children))


class _DynamicInitBase(QtBaseTestCase):
    """Shared setup: tmp dir + named UI file + Switchboard wiring.

    ``option_box`` is grafted onto common Qt widgets via
    ``patch_common_widgets`` — invoked once in ``setUpClass``.  In
    production this is done early by application bootstrap (tentacle's
    tcl_maya, mayatk's MayaUiHandler).  The patch is class-level and
    persists for the remainder of the process; downstream tests that
    treat ``option_box`` as an instance attribute must tolerate it
    being a property (see ``test_optionBox.TestActionOptionMultiInstance.
    _make_managed_widget``).
    """

    UI_NAME = "dyn"
    CHILDREN = [
        ("QPushButton", "tb000"),
        ("QPushButton", "tb001"),
        ("QComboBox", "cmb000"),
    ]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from uitk.widgets.optionBox.utils import patch_common_widgets

        patch_common_widgets()

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.ui_path = os.path.join(self.tmp.name, f"{self.UI_NAME}.ui")
        _write_ui(self.ui_path, self.UI_NAME, self.CHILDREN)

    def tearDown(self):
        try:
            if hasattr(self, "ui") and self.ui:
                self.ui.close()
        except RuntimeError:
            pass
        self.tmp.cleanup()
        super().tearDown()

    def _make_sb(self, slot_class):
        sb = Switchboard(
            ui_source=self.tmp.name,
            slot_source=slot_class,
            log_level="WARNING",
        )
        self.ui = getattr(sb.loaded_ui, self.UI_NAME)
        self.track_widget(self.ui)
        return sb

    def _drain(self, ms_per_pump=12, pumps=10):
        for _ in range(pumps):
            QtWidgets.QApplication.processEvents(
                QtCore.QEventLoop.AllEvents, ms_per_pump
            )


# ---------------------------------------------------------------------------
# Slot-constructor re-entrancy
# ---------------------------------------------------------------------------


class TestSlotConstructorReentrancy(_DynamicInitBase):
    """Locks down the placeholder + ``deferred_widgets`` machinery in
    :func:`uitk.switchboard.slots._create_slots_instance`.

    The scene_exporter pattern reaches into ``self.ui.<child>`` from the
    slot ``__init__`` (e.g. ``self.ui.txt001.setText("")``).  Each access
    triggers ``MainWindow.__getattr__`` → ``register_widget(child)`` →
    ``init_slot(child)``.  Without the placeholder guard this would
    recursively try to construct the same slot class (infinite loop) or
    run ``<name>_init`` against a half-built slot instance.  The
    contract: child inits queue in ``deferred_widgets`` and run after
    the constructor returns, in queue order.
    """

    def test_slot_ctor_accessing_ui_child_does_not_immediately_run_child_init(self):
        """A slot ``__init__`` that touches a UI child must not synchronously
        run that child's ``<name>_init`` — the slot isn't installed yet.
        """
        events = []

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn
                events.append("ctor:start")
                # Reach into a child — would recurse into init_slot if not deferred.
                _ = self_slot.ui.tb000
                events.append("ctor:after_tb000_access")

            def tb000_init(self_slot, widget):
                events.append("tb000_init")

            def tb001_init(self_slot, widget):
                events.append("tb001_init")

            def cmb000_init(self_slot, widget):
                events.append("cmb000_init")

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()

        # tb000_init must not appear between ctor:start and ctor:after_tb000_access
        ctor_start = events.index("ctor:start")
        ctor_end = events.index("ctor:after_tb000_access")
        between = events[ctor_start + 1:ctor_end]
        self.assertNotIn(
            "tb000_init",
            between,
            f"tb000_init ran during slot __init__: {events}",
        )

    def test_deferred_widgets_processed_after_ctor_returns(self):
        """Children touched during ``__init__`` get their ``<name>_init`` run
        after the constructor returns (via ``_process_deferred_widgets``)."""
        events = []

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn
                _ = self_slot.ui.tb000  # queues into deferred_widgets
                events.append("ctor_returned")

            def tb000_init(self_slot, widget):
                events.append("tb000_init")

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()

        self.assertIn("ctor_returned", events)
        self.assertIn(
            "tb000_init",
            events,
            f"deferred tb000_init never ran: {events}",
        )
        self.assertLess(
            events.index("ctor_returned"),
            events.index("tb000_init"),
            "tb000_init must run AFTER ctor returns",
        )

    def test_deferred_widgets_processed_in_queue_order(self):
        """Multiple children accessed in the constructor are init'd in access order."""
        events = []

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn
                # Touch in deliberately mixed order
                _ = self_slot.ui.cmb000
                _ = self_slot.ui.tb001
                _ = self_slot.ui.tb000

            def tb000_init(self_slot, widget):
                events.append("tb000")

            def tb001_init(self_slot, widget):
                events.append("tb001")

            def cmb000_init(self_slot, widget):
                events.append("cmb000")

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()

        # All three should have run.  Order should reflect the deferred queue
        # built up during the ctor (cmb000 first, then tb001, then tb000).
        # register_children may also independently call init_slot for any
        # widget not yet flagged is_initialized; the placeholder's gate on
        # is_initialized means it's a no-op, but we filter to first-occurrence
        # to avoid flake from ordering-by-attribute-walk.
        firsts = []
        for e in events:
            if e not in firsts:
                firsts.append(e)
        self.assertEqual(firsts, ["cmb000", "tb001", "tb000"])


# ---------------------------------------------------------------------------
# refresh_on_show / is_initialized gating
# ---------------------------------------------------------------------------


class TestRefreshOnShow(_DynamicInitBase):
    """Locks down the gate at
    :func:`uitk.switchboard.slots._perform_slot_init`
    around line 427.  Slot init is idempotent by default; when
    ``widget.refresh_on_show = True`` the slot body re-runs on every
    ``init_slot()`` call.
    """

    def test_init_skips_when_initialized_and_not_refresh(self):
        """Default behavior: second init_slot() is a no-op."""
        calls = []

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn

            def tb000_init(self_slot, widget):
                calls.append(widget.is_initialized)

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()

        self.ui.tb000.init_slot()  # second call
        self._drain()

        # Should have been called exactly once (during register_children).
        self.assertEqual(
            calls,
            [False],
            f"tb000_init ran {len(calls)} times; expected 1 (default idempotent)",
        )

    def test_init_reruns_when_refresh_on_show(self):
        """``refresh_on_show=True`` permits re-running the init body."""
        calls = []

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn

            def tb000_init(self_slot, widget):
                widget.refresh_on_show = True
                calls.append(widget.is_initialized)

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()
        self.ui.tb000.init_slot()  # second call
        self._drain()

        # Two calls: first time is_initialized=False, second time is_initialized=True
        # (set just before the gated re-entry path runs).
        self.assertEqual(len(calls), 2, f"expected 2 init calls, got {len(calls)}: {calls}")
        self.assertEqual(calls[0], False)
        self.assertTrue(calls[1])

    def test_gated_body_separates_structure_from_refresh(self):
        """The scene_exporter pattern: structural setup runs once, refresh
        runs every call."""
        structural = []
        refresh = []

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn

            def cmb000_init(self_slot, widget):
                if not widget.is_initialized:
                    widget.refresh_on_show = True
                    structural.append("once")
                refresh.append("every")

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()

        for _ in range(3):
            self.ui.cmb000.init_slot()
            self._drain()

        self.assertEqual(structural, ["once"])
        self.assertEqual(len(refresh), 4)  # 1 from register_children + 3 manual


# ---------------------------------------------------------------------------
# Re-entrant init_slot from a menu-item signal handler
# ---------------------------------------------------------------------------


class TestReentrantInitSlotFromMenuHandler(_DynamicInitBase):
    """Locks down the scene_exporter pattern where a checkbox added via
    ``widget.option_box.menu.add(...)`` has a handler that calls
    ``widget.init_slot()`` on the parent — refreshing data without
    rebuilding structure (see [_scene_exporter.py:600]).
    """

    def test_menu_item_signal_can_call_parent_init_slot_without_recursion(self):
        """A menu-item handler that calls ``parent.init_slot()`` must not
        infinite-loop and must let the menu item remain alive.

        Note: we ``emit`` the signal directly rather than ``setChecked(True)``
        because Qt's check-state propagation can be debounced or coalesced
        depending on the widget's parent visibility state.  The contract
        being verified is "signal fires → init_slot runs → no recursion",
        not "setChecked emits toggled".
        """
        init_count = [0]

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn
                self_slot._chk = None

            def cmb000_init(self_slot, widget):
                if not widget.is_initialized:
                    widget.refresh_on_show = True
                    self_slot._chk = widget.option_box.menu.add(
                        "QCheckBox", setObjectName="chk_default"
                    )
                init_count[0] += 1

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()

        slot = self.ui.sb.get_slots_instance(self.ui)
        self.assertIsNotNone(slot._chk, "structural setup did not run")

        cmb = self.ui.cmb000
        baseline = init_count[0]

        # Wire up the re-entrant handler.
        slot._chk.toggled.connect(lambda *_: cmb.init_slot())
        # Fire it.
        slot._chk.toggled.emit(True)
        self._drain()

        self.assertGreaterEqual(
            init_count[0],
            baseline + 1,
            f"cmb000_init ran {init_count[0]} times; expected >={baseline + 1} "
            f"after re-entrant call (baseline={baseline})",
        )
        # The captured handle must still be alive (no C++ deletion).
        self.assertEqual(slot._chk.objectName(), "chk_default")

    def test_reentrant_init_skips_gated_structural_setup(self):
        """Re-entrant ``init_slot()`` must NOT re-run the
        ``if not widget.is_initialized:`` block — menu items would
        otherwise duplicate."""
        structural_runs = [0]
        refresh_runs = [0]

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn

            def cmb000_init(self_slot, widget):
                if not widget.is_initialized:
                    widget.refresh_on_show = True
                    structural_runs[0] += 1
                    widget.option_box.menu.add(
                        "QCheckBox", setObjectName="chk_first"
                    )
                refresh_runs[0] += 1

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()
        # Drive several refreshes
        for _ in range(5):
            self.ui.cmb000.init_slot()
            self._drain()

        self.assertEqual(structural_runs[0], 1)
        self.assertEqual(refresh_runs[0], 6)

        # The single chk_first must exist exactly once on the menu.
        menu = self.ui.cmb000.option_box.menu
        chk_count = sum(
            1 for w in menu.findChildren(QtWidgets.QCheckBox)
            if w.objectName() == "chk_first"
        )
        self.assertEqual(chk_count, 1)

    def test_menu_items_stored_as_slot_attributes_remain_valid_across_reinit(self):
        """The slot may capture the return value of ``menu.add(...)``.
        That handle must survive deferred drain and any number of
        ``init_slot()`` re-entries."""
        captured = []

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn
                self_slot._chk = None

            def cmb000_init(self_slot, widget):
                if not widget.is_initialized:
                    widget.refresh_on_show = True
                    self_slot._chk = widget.option_box.menu.add(
                        "QCheckBox", setObjectName="chk_keep"
                    )
                    captured.append(self_slot._chk)

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()

        slot = self.ui.sb.get_slots_instance(self.ui)
        # First handle captured during structural init
        original = captured[0]

        for _ in range(3):
            self.ui.cmb000.init_slot()
            self._drain()

        # Same widget instance, still alive, still parented.
        self.assertIs(slot._chk, original)
        self.assertEqual(slot._chk.objectName(), "chk_keep")
        # Setting a property must not raise (i.e. C++ object alive).
        slot._chk.setChecked(True)
        self.assertTrue(slot._chk.isChecked())


# ---------------------------------------------------------------------------
# add_option(plugin) bypasses Menu.add
# ---------------------------------------------------------------------------


class TestOptionBoxAddOptionPluginPath(_DynamicInitBase):
    """``OptionBoxManager.add_option`` is the lower-level entry point that
    ``enable_menu`` / ``set_action`` / ``browse`` / ``recent`` /
    ``enable_clear`` all sit on top of.  scene_exporter also calls it
    directly for ``RecentValuesOption``::

        self._recent_dirs_option = RecentValuesOption(...)
        widget.option_box.add_option(self._recent_dirs_option)

    This path bypasses ``Menu.add`` entirely, so Fix B (visibility-gated
    activate) and Fix D (registration coalescing) don't apply — but the
    deferred-wrap contract from :class:`OptionBoxManager` still does.
    """

    def test_add_option_plugin_does_not_route_through_menu_add(self):
        """Calling ``mgr.add_option(plugin)`` must not call ``Menu.add``."""
        from uitk.widgets.menu import Menu
        from uitk.widgets.optionBox.options.clear import ClearOption

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn

            def tb000_init(self_slot, widget):
                pass

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()

        widget = self.ui.tb000
        with patch.object(Menu, "add") as mock_menu_add:
            # Use the plugin path directly.
            widget.option_box.add_option(ClearOption(widget))
            self._drain()

        self.assertEqual(
            mock_menu_add.call_count,
            0,
            f"Menu.add called {mock_menu_add.call_count} time(s) on plugin path",
        )

    def test_add_option_synchronous_wrap_when_parent_exists(self):
        """Fix C: when the wrapped widget already has a parent at the time
        ``_schedule_wrap_if_needed`` runs, the wrap completes synchronously.
        This eliminates the visible flicker between MainWindow.showEvent and
        the deferred-timer-driven reparent."""
        from uitk.widgets.optionBox.options.clear import ClearOption
        from qtpy import QtCore

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn

            def tb000_init(self_slot, widget):
                pass

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()

        widget = self.ui.tb000
        self.assertIsNotNone(widget.parent())
        mgr = widget.option_box

        # Track whether QTimer.singleShot(0, ...) is scheduled by the wrap
        scheduled = []
        original_singleShot = QtCore.QTimer.singleShot

        def counting_singleShot(interval, slot, *args, **kwargs):
            scheduled.append((interval, getattr(slot, "__name__", repr(slot))))
            return original_singleShot(interval, slot, *args, **kwargs)

        with patch.object(QtCore.QTimer, "singleShot", counting_singleShot):
            mgr.add_option(ClearOption(widget))

        # The wrap should have completed synchronously — no QTimer schedule
        # for _attempt_wrap_when_ready.
        wrap_schedules = [
            s for s in scheduled if s[1] == "_attempt_wrap_when_ready"
        ]
        self.assertEqual(
            len(wrap_schedules),
            0,
            f"Expected synchronous wrap; got deferred schedule(s): {scheduled}",
        )
        self.assertTrue(
            mgr._is_wrapped,
            "Synchronous wrap should leave _is_wrapped=True after add_option",
        )

    def test_register_children_stable_under_sync_wrap(self):
        """Fix C interaction with ``MainWindow.register_children``: when
        a child slot's init triggers a synchronous wrap (which reparents
        the widget into an ``OptionBoxContainer``), the walk must
        continue iterating the *snapshot* taken before the wrap — not
        re-discover the container as a new sibling, and not double-
        register the wrapped widget.

        This exercises the worst case: ``register_children`` iterates
        the central widget's findChildren list, hits a ``tb`` button, its
        slot calls ``option_box.set_action`` which Fix-C-synchronously
        wraps it, replacing the button in the parent layout with a new
        container.  The walk must not lose track.
        """
        from uitk.widgets.optionBox.options.clear import ClearOption

        registered = []

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn

            def tb000_init(self_slot, widget):
                # Wraps synchronously under Fix C; reparents widget.
                widget.option_box.add_option(ClearOption(widget))
                registered.append("tb000")

            def tb001_init(self_slot, widget):
                registered.append("tb001")

            def cmb000_init(self_slot, widget):
                registered.append("cmb000")

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()

        # Each named child must register exactly once.
        self.assertEqual(
            sorted(registered),
            ["cmb000", "tb000", "tb001"],
            f"Walk produced unexpected registration order/count: {registered}",
        )
        self.assertEqual(
            len(registered),
            len(set(registered)),
            "A child was double-registered during register_children walk",
        )

        # tb000 must have wrapped synchronously; its parent is now the container.
        tb000 = self.ui.tb000
        self.assertTrue(tb000.option_box._is_wrapped)
        from uitk.widgets.optionBox._optionBox import OptionBoxContainer

        self.assertIsInstance(tb000.parent(), OptionBoxContainer)

    def test_add_option_falls_back_to_deferred_when_parentless(self):
        """If the widget has no parent at schedule time, fall back to the
        deferred QTimer retry loop (existing behavior)."""
        from uitk.widgets.optionBox.options.clear import ClearOption
        from uitk.widgets.optionBox.utils import OptionBoxManager

        # Parentless widget — synchronous wrap is impossible
        widget = self.track_widget(QtWidgets.QPushButton())
        self.assertIsNone(widget.parent())

        mgr = OptionBoxManager(widget)
        mgr.add_option(ClearOption(widget))

        # Fallback: timer scheduled, not yet wrapped
        self.assertFalse(mgr._is_wrapped)
        self.assertTrue(mgr._wrap_retry_scheduled)

    def test_add_option_plugin_eventually_wraps(self):
        """``add_option`` results in a wrap regardless of whether the wrap
        path is synchronous (parent attached, post-Fix-C) or deferred
        (parent missing).  The contract callers rely on is the
        post-condition: ``_is_wrapped`` is True after a drain."""
        from uitk.widgets.optionBox.options.clear import ClearOption

        class Dyn:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.dyn

            def tb000_init(self_slot, widget):
                pass

        self._make_sb(Dyn)
        self.ui.register_children()
        self._drain()

        widget = self.ui.tb000
        self.assertIsNotNone(widget.parent())
        mgr = widget.option_box
        self.assertFalse(mgr._is_wrapped)

        mgr.add_option(ClearOption(widget))
        self._drain(pumps=20)

        self.assertTrue(
            mgr._is_wrapped,
            "OptionBoxManager did not wrap after add_option(plugin) + drain",
        )


class TestFlickerDetection(_DynamicInitBase):
    """Detect the user-reported flicker: 'multiple menus initializing
    repeatedly' during initial UI load.

    A flicker is a visible state change observable between
    ``super().showEvent`` (the first paint of the MainWindow) and the
    next event-loop tick.  Any reparent, ``setVisible(True)``, or
    geometry-changing operation in that window paints the un-final
    state to the screen, then re-paints with the final state — exactly
    what the user describes.

    These tests instrument the relevant operations and assert they all
    complete *before* ``super().showEvent``.
    """

    # 4 tb-buttons + 1 cmb = enough to surface multi-wrap interactions
    UI_NAME = "flicker"
    CHILDREN = [
        ("QPushButton", "tb000"),
        ("QPushButton", "tb001"),
        ("QPushButton", "tb002"),
        ("QPushButton", "tb003"),
        ("QComboBox", "cmb000"),
    ]

    def _make_tentacle_like_slot(self, events):
        """Build a slot class that mimics a tentacle slot: each
        ``tbXXX_init`` populates the option_box menu with several items.

        Class name must match ``UI_NAME`` for Switchboard's slot resolver
        (see ``get_slot_class_names``: UI ``flicker`` → ``FlickerSlots`` /
        ``Flicker``).
        """

        class Flicker:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.flicker

            def tb000_init(self_slot, widget):
                widget.option_box.menu.add(
                    "QCheckBox", setObjectName="tb000_chk0", setText="A"
                )
                widget.option_box.menu.add(
                    "QCheckBox", setObjectName="tb000_chk1", setText="B"
                )
                widget.option_box.menu.add(
                    "QCheckBox", setObjectName="tb000_chk2", setText="C"
                )
                events.append(("slot_init", "tb000"))

            def tb001_init(self_slot, widget):
                widget.option_box.menu.add(
                    "QSpinBox", setObjectName="tb001_s0"
                )
                widget.option_box.menu.add(
                    "QSpinBox", setObjectName="tb001_s1"
                )
                events.append(("slot_init", "tb001"))

            def tb002_init(self_slot, widget):
                widget.option_box.menu.add(
                    "QPushButton", setObjectName="tb002_b0", setText="Run"
                )
                events.append(("slot_init", "tb002"))

            def tb003_init(self_slot, widget):
                widget.option_box.menu.add(
                    "QCheckBox", setObjectName="tb003_chk0", setText="X"
                )
                widget.option_box.menu.add(
                    "QCheckBox", setObjectName="tb003_chk1", setText="Y"
                )
                events.append(("slot_init", "tb003"))

        return Flicker

    def _instrument(self, events):
        """Patch the operations that could produce flicker, recording each
        call with a timestamp marker.  Returns a list of cleanup functions.
        """
        from uitk.widgets.optionBox._optionBox import (
            OptionBox,
            OptionBoxContainer,
        )

        cleanups = []

        # 1. Track replaceWidget calls — the core wrap operation
        original_wrap = OptionBox.wrap

        def tracking_wrap(self_ob, wrapped_widget, frameless=False):
            events.append(("wrap_start", wrapped_widget.objectName()))
            result = original_wrap(self_ob, wrapped_widget, frameless=frameless)
            events.append(("wrap_end", wrapped_widget.objectName()))
            return result

        OptionBox.wrap = tracking_wrap
        cleanups.append(lambda: setattr(OptionBox, "wrap", original_wrap))

        # 2. Track OptionBoxContainer.show() — the visible-transition trigger
        original_setvisible = OptionBoxContainer.setVisible

        def tracking_setvisible(self_c, visible):
            events.append(("container_setvisible", visible))
            return original_setvisible(self_c, visible)

        OptionBoxContainer.setVisible = tracking_setvisible
        cleanups.append(
            lambda: setattr(OptionBoxContainer, "setVisible", original_setvisible)
        )

        return cleanups

    def test_no_wrap_or_container_show_after_super_showevent(self):
        """The contract Fix C is supposed to deliver: by the time
        ``MainWindow.showEvent`` returns to the event loop, every
        OptionBoxManager wrap has completed and every container's
        setVisible(True) has fired.  Anything happening AFTER super()
        .showEvent — visible to the user as flicker — fails this test."""
        events = []
        cleanups = self._instrument(events)
        try:
            sb = self._make_sb(self._make_tentacle_like_slot(events))

            # Hook MainWindow.showEvent to mark the boundary.
            ui = self.ui
            original_show_event = type(ui).showEvent

            def marking_show_event(self_ui, event):
                events.append(("ui_showEvent_start", None))
                original_show_event(self_ui, event)
                events.append(("ui_showEvent_returned", None))

            type(ui).showEvent = marking_show_event
            cleanups.append(
                lambda: setattr(type(ui), "showEvent", original_show_event)
            )

            # Trigger the show flow.  MainWindow.showEvent calls
            # register_children if not yet initialized.
            ui.show()
            # Drain — let any leftover deferred timers fire so we can see
            # them in the event log.
            self._drain(pumps=20)

            # Now classify events: anything wrap-related or
            # container-setVisible(True) must NOT appear after
            # ui_showEvent_returned.
            try:
                returned_idx = next(
                    i for i, e in enumerate(events) if e[0] == "ui_showEvent_returned"
                )
            except StopIteration:
                self.fail(f"showEvent never returned; events: {events}")

            after_show = events[returned_idx + 1:]
            offenders = [
                e
                for e in after_show
                if e[0] == "wrap_start"
                or e[0] == "wrap_end"
                or (e[0] == "container_setvisible" and e[1] is True)
            ]
            self.assertEqual(
                offenders,
                [],
                f"Flicker source: visible operations after super().showEvent.\n"
                f"  Offenders: {offenders}\n"
                f"  Full sequence (last 30): {events[-30:]}",
            )

            # Also: every tb-button's wrap must have happened (they all
            # have option_box.menu populated, so all should wrap).
            wrap_starts = {e[1] for e in events if e[0] == "wrap_start"}
            expected = {"tb000", "tb001", "tb002", "tb003"}
            self.assertEqual(
                wrap_starts,
                expected,
                f"Some tb-buttons didn't wrap; got {wrap_starts}, expected {expected}",
            )

        finally:
            for c in cleanups:
                c()

    def test_off_screen_position_corrected_before_drain(self):
        """The strongest reproduction of the user-described flicker:
        force a position that ``_ensure_on_screen`` MUST adjust, then
        verify the adjustment is finalized within ``show_as_popup``'s
        synchronous call frame — not deferred into the event-loop drain
        where it would fire after paint as a visible jump.

        The contract: menu's frameGeometry is on-screen AND no
        ``move()`` calls fire during the post-show event-loop drain.
        """
        from uitk.widgets.menu import Menu
        from qtpy import QtCore as _QtCore

        events = []
        cleanups = self._instrument(events)

        original_move = Menu.move

        def tracking_move(self_m, *args, **kwargs):
            events.append(("menu_move", id(self_m), args))
            return original_move(self_m, *args, **kwargs)

        Menu.move = tracking_move
        cleanups.append(lambda: setattr(Menu, "move", original_move))

        try:
            sb = self._make_sb(self._make_tentacle_like_slot(events))
            ui = self.ui
            ui.show()
            self._drain(pumps=10)

            tb000 = ui.tb000
            menu = tb000.option_box.menu

            menu.show_as_popup(
                anchor_widget=tb000,
                position=_QtCore.QPoint(999999, 999999),
            )
            events.append(("drain_start", id(menu)))
            app = QtWidgets.QApplication.instance()
            for _ in range(10):
                app.processEvents(_QtCore.QEventLoop.AllEvents, 12)

            # 1. Final position must be on-screen.
            screen = QtWidgets.QApplication.primaryScreen()
            self.assertIsNotNone(screen)
            screen_geo = screen.availableGeometry()
            menu_geo = menu.frameGeometry()
            self.assertTrue(
                screen_geo.intersects(menu_geo),
                f"Menu off-screen after show_as_popup. "
                f"menu={menu_geo}, screen={screen_geo}",
            )

            # 2. No move() calls during drain — those would be deferred
            #    moves visible to the user as a jump.
            menu_id = id(menu)
            drain_idx = next(
                i
                for i, e in enumerate(events)
                if e[0] == "drain_start" and e[1] == menu_id
            )
            late_moves = [
                e
                for e in events[drain_idx + 1:]
                if e[0] == "menu_move" and e[1] == menu_id
            ]
            self.assertEqual(
                late_moves,
                [],
                f"{len(late_moves)} Menu.move call(s) during post-show "
                f"drain — visible flicker.\n"
                f"Moves: {late_moves}",
            )

            menu.hide(force=True)

        finally:
            for c in cleanups:
                c()

    def test_no_menu_move_during_drain_after_show_as_popup(self):
        """The user-described flicker: 'multiple menus initializing
        repeatedly, then the actual menu shows moved into place'.

        Synchronous moves within ``show_as_popup``'s call frame (before
        the function returns) are pre-paint and invisible to the user.
        What IS visible is any ``move()`` that fires DURING the event-
        loop drain — paint events fire there too, so a move sandwiched
        with a paint is the flicker.

        Marker: insert a ``drain_start`` event in the timeline right
        before pumping ``QApplication.processEvents``.  Any
        ``menu_move`` after that marker indicates a deferred move that
        the user will see.
        """
        from uitk.widgets.menu import Menu
        from qtpy import QtCore as _QtCore

        events = []
        cleanups = self._instrument(events)

        original_move = Menu.move

        def tracking_move(self_m, *args, **kwargs):
            events.append(("menu_move", self_m.objectName() or id(self_m), args))
            return original_move(self_m, *args, **kwargs)

        Menu.move = tracking_move
        cleanups.append(lambda: setattr(Menu, "move", original_move))

        try:
            sb = self._make_sb(self._make_tentacle_like_slot(events))
            ui = self.ui
            ui.show()
            self._drain(pumps=10)

            tb000 = ui.tb000
            menu = tb000.option_box.menu
            menu.show_as_popup(anchor_widget=tb000, position="bottom")

            # Boundary marker: everything after this is post-return-from-
            # show_as_popup, so any move() here is deferred and visible.
            events.append(("drain_start", menu.objectName() or id(menu)))
            app = QtWidgets.QApplication.instance()
            for _ in range(10):
                app.processEvents(_QtCore.QEventLoop.AllEvents, 12)

            menu_id = menu.objectName() or id(menu)
            drain_idx = next(
                i
                for i, e in enumerate(events)
                if e[0] == "drain_start" and e[1] == menu_id
            )
            moves_during_drain = [
                e
                for e in events[drain_idx + 1:]
                if e[0] == "menu_move" and e[1] == menu_id
            ]
            self.assertEqual(
                moves_during_drain,
                [],
                f"{len(moves_during_drain)} Menu.move call(s) fired during "
                f"event-loop drain after show_as_popup returned — these "
                f"are deferred moves and produce visible flicker.\n"
                f"Moves: {moves_during_drain}\n"
                f"Sequence (last 30): {events[-30:]}",
            )

            menu.hide(force=True)

        finally:
            for c in cleanups:
                c()

    def test_all_wraps_complete_before_first_paint(self):
        """Stronger contract check: each ``wrap_end`` event must precede
        ``ui_showEvent_returned`` in the timeline.  If any wrap straddles
        super().showEvent — i.e., wrap_start before but wrap_end after —
        the user sees a half-wrapped state on screen."""
        events = []
        cleanups = self._instrument(events)
        try:
            sb = self._make_sb(self._make_tentacle_like_slot(events))
            ui = self.ui

            original_show_event = type(ui).showEvent

            def marking_show_event(self_ui, event):
                events.append(("ui_showEvent_start", None))
                original_show_event(self_ui, event)
                events.append(("ui_showEvent_returned", None))

            type(ui).showEvent = marking_show_event
            cleanups.append(
                lambda: setattr(type(ui), "showEvent", original_show_event)
            )

            ui.show()
            self._drain(pumps=20)

            try:
                returned_idx = next(
                    i for i, e in enumerate(events) if e[0] == "ui_showEvent_returned"
                )
            except StopIteration:
                self.fail("showEvent never returned")

            wrap_end_indices = [
                i for i, e in enumerate(events) if e[0] == "wrap_end"
            ]
            late_wraps = [i for i in wrap_end_indices if i > returned_idx]
            self.assertEqual(
                late_wraps,
                [],
                f"{len(late_wraps)} wrap(s) completed after super().showEvent — "
                f"flicker. wrap_end at indices {late_wraps}, "
                f"super().showEvent returned at index {returned_idx}.",
            )

        finally:
            for c in cleanups:
                c()

    def test_no_size_change_after_visible_with_apply_and_defaults_buttons(self):
        """The user-described 'rapidly flashing window' on first option_box
        open: ``add_apply_button=True`` and ``add_defaults_button=True``
        (defaults for option_box menus) historically deferred their
        button creation + ``_layout.invalidate``/``activate``/
        ``adjustSize`` chain into ``Menu.showEvent`` — which fires
        AFTER ``super().setVisible(True)``.  The result was the menu
        becoming visible at one size, then growing to its final size
        once the apply+defaults buttons appeared, painting the resize
        cycle on screen.

        Contract: by the time ``super().setVisible(True)`` is invoked,
        the menu's size must already match what it will be once
        ``showEvent`` returns.  Equivalently, no apply-button/defaults-
        button creation may straddle the visibility transition.
        """
        from uitk.widgets.menu import Menu

        events = []
        cleanups = self._instrument(events)

        # Track the size at three points: pre-setVisible(True), post-
        # super().setVisible(True), post-showEvent.  All three must match.
        size_log = {}

        original_set_visible = Menu.setVisible
        original_show_event = Menu.showEvent
        original_setup_apply = Menu._setup_apply_button
        original_setup_defaults = Menu._setup_defaults_button

        def tracking_set_visible(self_m, visible):
            mid = id(self_m)
            if visible and mid not in size_log:
                size_log.setdefault(mid, {})["pre_setvisible"] = self_m.size()
            original_set_visible(self_m, visible)
            if visible and "post_setvisible" not in size_log.get(mid, {}):
                size_log.setdefault(mid, {})["post_setvisible"] = self_m.size()

        def tracking_show_event(self_m, event):
            result = original_show_event(self_m, event)
            mid = id(self_m)
            size_log.setdefault(mid, {})["post_showevent"] = self_m.size()
            return result

        def tracking_setup_apply(self_m):
            events.append(("setup_apply_button", id(self_m), self_m.isVisible()))
            return original_setup_apply(self_m)

        def tracking_setup_defaults(self_m):
            events.append(("setup_defaults_button", id(self_m), self_m.isVisible()))
            return original_setup_defaults(self_m)

        Menu.setVisible = tracking_set_visible
        Menu.showEvent = tracking_show_event
        Menu._setup_apply_button = tracking_setup_apply
        Menu._setup_defaults_button = tracking_setup_defaults
        cleanups.extend(
            [
                lambda: setattr(Menu, "setVisible", original_set_visible),
                lambda: setattr(Menu, "showEvent", original_show_event),
                lambda: setattr(Menu, "_setup_apply_button", original_setup_apply),
                lambda: setattr(
                    Menu, "_setup_defaults_button", original_setup_defaults
                ),
            ]
        )

        try:
            sb = self._make_sb(self._make_tentacle_like_slot(events))
            ui = self.ui
            ui.show()
            self._drain(pumps=10)

            tb000 = ui.tb000
            menu = tb000.option_box.menu
            # option_box menus default to add_apply_button=True and
            # add_defaults_button=True via patch_common_widgets.
            self.assertTrue(
                getattr(menu, "add_apply_button", False),
                "option_box menus must enable add_apply_button — test "
                "premise broken if this fails",
            )
            self.assertTrue(
                getattr(menu, "add_defaults_button", False),
                "option_box menus must enable add_defaults_button",
            )

            menu.show_as_popup(anchor_widget=tb000, position="bottom")
            self._drain(pumps=10)

            mid = id(menu)
            self.assertIn(mid, size_log, "Menu setVisible/showEvent never fired")
            log = size_log[mid]
            self.assertIn("post_setvisible", log)
            self.assertIn("post_showevent", log)

            # Contract: size after super().setVisible(True) must match size
            # after showEvent returns.  Any difference == visible flicker.
            self.assertEqual(
                log["post_setvisible"],
                log["post_showevent"],
                f"Menu size changed between super().setVisible(True) and "
                f"end of showEvent — visible flash.\n"
                f"  post_setvisible: {log['post_setvisible']}\n"
                f"  post_showevent:  {log['post_showevent']}\n"
                f"  Apply/defaults setup events: "
                f"{[e for e in events if 'setup_' in e[0]]}",
            )

            # Stronger: apply/defaults setup must run while the menu is
            # NOT yet visible.  ``isVisible()`` is captured at the moment
            # _setup_apply_button / _setup_defaults_button was called.
            visible_setup = [
                e
                for e in events
                if e[0] in ("setup_apply_button", "setup_defaults_button")
                and e[1] == mid
                and e[2] is True
            ]
            self.assertEqual(
                visible_setup,
                [],
                f"Apply/defaults button setup ran while menu was already "
                f"visible — that's the flash.\n"
                f"  Offenders: {visible_setup}",
            )

            menu.hide(force=True)

        finally:
            for c in cleanups:
                c()


class TestPrePaintRegistrationFlush(_DynamicInitBase):
    """Menu-item registration must complete INSIDE the pre-paint window.

    ``Menu.add`` defers each item's ``register_widget`` to a coalesced
    tick-0 timer (escaping mid-add recursion). Pre-fix, that timer fired
    AFTER ``MainWindow.showEvent`` painted — item state-restore and nested
    option-box wraps then mutated on screen (the init flash; the bench's
    ``05_drain_deferred_timers`` phase). ``register_children`` now flushes
    every pending menu registration synchronously at its end, still
    pre-paint; the timers later find empty queues and no-op.
    """

    UI_NAME = "regflush"
    CHILDREN = [
        ("QPushButton", "tb000"),
        ("QPushButton", "tb001"),
    ]

    def _make_slot(self):
        class Regflush:
            def __init__(self_slot, switchboard):
                self_slot.sb = switchboard
                self_slot.ui = switchboard.loaded_ui.regflush

            def tb000_init(self_slot, widget):
                widget.option_box.menu.add(
                    "QCheckBox", setObjectName="tb000_chk0", setText="A"
                )
                widget.option_box.menu.add(
                    "QSpinBox", setObjectName="tb000_s0"
                )

            def tb001_init(self_slot, widget):
                widget.option_box.menu.add(
                    "QCheckBox", setObjectName="tb001_chk0", setText="B"
                )

        return Regflush

    def test_menu_items_registered_at_show_return(self):
        """At show()-return (pre-drain), every menu item created by the slot
        inits must already be registered with the MainWindow — pre-fix they
        were still sitting in _pending_registrations awaiting the post-paint
        timer."""
        self._make_sb(self._make_slot())
        self.ui.show()

        # NO drain — this is the state the first paint renders.
        for name in ("tb000_chk0", "tb000_s0", "tb001_chk0"):
            self.assertTrue(
                hasattr(self.ui, name),
                f"menu item {name!r} not registered at show-return — its "
                "registration (and state restore) lands post-paint: the "
                "init flash.",
            )

        from uitk.widgets.menu import _menus_awaiting_registration

        stale = [
            m
            for m in list(_menus_awaiting_registration)
            if m._pending_registrations
            and m._resolve_registration_window() is self.ui
        ]
        self.assertEqual(
            stale,
            [],
            "menus still awaiting registration after show-return "
            f"(pending in {[m.objectName() for m in stale]}).",
        )

    def test_no_register_widget_after_show_returns(self):
        """Boundary proof: zero register_widget calls after showEvent
        returns, and none inside an add() frame (the recursion contract that
        motivated the deferral must survive the flush)."""
        from uitk.widgets.menu import Menu

        events = []
        sb = self._make_sb(self._make_slot())
        ui = self.ui

        original_register = type(ui).register_widget

        def tracking_register(self_ui, widget):
            menu_add_depths = [
                m._add_depth
                for m in ui.findChildren(Menu)
                if getattr(m, "_add_depth", 0)
            ]
            events.append(("register", widget.objectName(), max(menu_add_depths or [0])))
            return original_register(self_ui, widget)

        original_show_event = type(ui).showEvent

        def marking_show_event(self_ui, event):
            original_show_event(self_ui, event)
            events.append(("ui_showEvent_returned", None, 0))

        type(ui).register_widget = tracking_register
        type(ui).showEvent = marking_show_event
        try:
            ui.show()
            self._drain(pumps=20)
        finally:
            type(ui).register_widget = original_register
            type(ui).showEvent = original_show_event

        returned_idx = next(
            (i for i, e in enumerate(events) if e[0] == "ui_showEvent_returned"),
            None,
        )
        self.assertIsNotNone(returned_idx, f"showEvent never returned: {events}")

        after = [e for e in events[returned_idx + 1:] if e[0] == "register"]
        self.assertEqual(
            after,
            [],
            f"register_widget ran AFTER showEvent returned (post-paint): {after}",
        )
        mid_add = [e for e in events if e[0] == "register" and e[2] > 0]
        self.assertEqual(
            mid_add,
            [],
            f"register_widget ran INSIDE an add() frame (recursion hazard): {mid_add}",
        )


if __name__ == "__main__":
    unittest.main()
