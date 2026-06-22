# !/usr/bin/python
# coding=utf-8
"""End-to-end input → menu tests for MarkingMenu.

These tests build a real MarkingMenu instance with a minimal stub Switchboard
and stub UIs, then drive Qt events via QTest. They cover the full sequence of
press/release combinations to ensure no flicker, no stuck states, and no
"press twice to switch" regressions.
"""
import logging
import unittest
from unittest import mock

from qtpy import QtCore, QtGui, QtWidgets

from conftest import QtBaseTestCase
from uitk.widgets.marking_menu._marking_menu import MarkingMenu
from uitk.widgets.marking_menu._resolver import parse_binding_keys


# Default binding fixture mirrors TclMaya's defaults so behavior is realistic.
DEFAULT_BINDINGS = {
    "Key_F12": "hud",
    "Key_F12|LeftButton": "cameras",
    "Key_F12|MiddleButton": "editors",
    "Key_F12|RightButton": "main",
    "Key_F12|LeftButton|RightButton": "maya",
}


class StubUi(QtWidgets.QWidget):
    """Stand-in for a Switchboard-loaded UI tagged ``startmenu``."""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self._tags = {"startmenu"} if name.endswith(("hud", "cameras", "editors", "main", "maya")) else set()
        self.is_initialized = True
        self.header = None
        self.widgets = []
        self.on_child_registered = _NoSignal()
        self.ensure_on_screen = False
        self.style = _NoopStyle()
        self.tags = list(self._tags)

    def has_tags(self, tags):
        if isinstance(tags, str):
            tags = [tags]
        return any(t in self._tags for t in tags)


class _NoSignal:
    def connect(self, *_args, **_kwargs):
        pass


class _NoopStyle:
    def set(self, *args, **kwargs):
        pass


class StubHandlers:
    def __init__(self):
        self.marking_menu = None
        self.ui = StubUiHandler()


class StubUiHandler:
    def get(self, name, **kwargs):
        return None

    def apply_styles(self, ui):
        pass

    def setup_lifecycle(self, ui, **kwargs):
        pass

    def show(self, widget, pos=None, force=False):
        widget.show()


class StubConfigurable:
    """Mimics the marking_menu_bindings persistence layer."""

    def __init__(self, value):
        self._value = value
        self.changed = _NoSignal()

    def get(self, default=None):
        return self._value if self._value is not None else default

    def set(self, value):
        self._value = value


class StubConfigurableNS:
    def __init__(self, bindings):
        self.marking_menu_bindings = StubConfigurable(bindings)


class StubSwitchboard:
    """Minimal Switchboard surface used by MarkingMenu under test."""

    def __init__(self, bindings):
        self._uis: dict = {}
        self._current_ui = None
        self.handlers = StubHandlers()
        self.configurable = StubConfigurableNS(bindings)
        self.visible_windows = []
        self.registered_widgets = type("RW", (), {"Region": object()})()

    def register_ui(self, ui):
        self._uis[ui.objectName()] = ui

    @property
    def current_ui(self):
        return self._current_ui

    @current_ui.setter
    def current_ui(self, ui):
        self._current_ui = ui

    @property
    def active_ui(self):
        # Mirror Switchboard.active_ui — same value, no warning.
        return self._current_ui

    def get_ui(self, name):
        if name is None:
            return self._current_ui
        return self._uis.get(name)

    def ui_history(self, *args, **kwargs):
        return []

    def get_widget(self, name, ui):
        return None

    def hide_unmatched_groupboxes(self, *args, **kwargs):
        pass

    def edit_tags(self, name, remove=None):
        return name

    def get_unknown_tags(self, name, known_tags=None):
        return []

    def register_handler(self, *args, **kwargs):
        pass

    def register(self, *args, **kwargs):
        pass


class DriveableMarkingMenu(MarkingMenu):
    """MarkingMenu subclass that bypasses Switchboard / GlobalShortcut setup
    so it can be driven by QTest without loading real UI files."""

    def __init__(self, parent, bindings):
        # Bypass MarkingMenu.__init__: we only want the event-handler logic
        # and a few state attributes.
        QtWidgets.QWidget.__init__(self, parent=parent)
        self.logger = logging.getLogger("DriveableMarkingMenu")
        self.logger.setLevel(logging.WARNING)

        self._bindings, self._activation_key_str = parse_binding_keys(bindings)
        self._activation_key = QtCore.Qt.Key_F12 if self._activation_key_str == "Key_F12" else None
        self._activation_key_held = False
        self._standalone_suppress = False
        self._suppress_default_on_reentry = False
        self._non_default_shown = False
        self._current_widget = None
        self._submenu_cache = {}
        self._initial_bindings = bindings
        self._default_bindings = bindings
        self._in_transition = False
        self._last_ui_history_check = None
        self._windows_to_restore = set()

        self.sb = StubSwitchboard(bindings)
        for name in set(bindings.values()):
            self.sb.register_ui(StubUi(name, parent=self))

        self.overlay = _OverlayStub()
        self.mouse_tracking = _MouseTrackingStub()
        self.child_event_filter = _NoopFilter()

        # Frameless full-screen overlay so QTest mouse events land on us.
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.resize(400, 400)

    # -- override the heavy bits to avoid Switchboard / window-manager calls --

    def _init_ui(self, ui):
        ui.is_initialized = True

    def _show_marking_menu(self, widget, **kwargs):
        if self._current_widget and self._current_widget is not widget:
            self._current_widget.hide()
        self._current_widget = widget
        widget.show()
        self.sb.current_ui = widget
        if widget.has_tags("startmenu"):
            self.overlay.start_gesture(QtGui.QCursor.pos())
        if (
            self._suppress_default_on_reentry
            and self._activation_key_held
            and self._activation_key_str is not None
            and widget.objectName() != self._bindings.get(self._activation_key_str)
        ):
            self._non_default_shown = True
        # Mirror production: ensure the overlay window is visible.
        if QtWidgets.QWidget.isHidden(self):
            QtWidgets.QWidget.show(self)
        return widget

    def _show_window(self, widget, pos=None, force=False, **kwargs):
        self._activation_key_held = False
        self._standalone_suppress = True
        self.hide()
        widget.show()
        return widget

    def _dismiss_external_popups(self, *_args, **_kwargs):
        pass

    def _transfer_mouse_control(self, *_args, **_kwargs):
        # In tests we don't need the synthetic press; QTest delivers events
        # directly.
        pass

    def dim_other_windows(self):
        pass

    def restore_other_windows(self):
        pass

    def setCurrentWidget(self, widget):
        if self._current_widget and self._current_widget is not widget:
            self._current_widget.hide()
        self._current_widget = widget
        widget.show()


class _OverlayStub:
    def __init__(self):
        self.path = type(
            "P",
            (),
            {"add": lambda *a: None, "start_pos": None, "is_empty": True},
        )()

    def start_gesture(self, *_args):
        pass

    def clone_widgets_along_path(self, *_args, **_kwargs):
        pass


class _MouseTrackingStub:
    # Mirror the slice of the real MouseTracking interface the menu touches: the
    # input-logging gate flag and the class-scoped log toggles that
    # MarkingMenu.enable_input_logging drives.
    _input_logging_on = False

    def update_child_widgets(self):
        pass

    @classmethod
    def set_log_file(cls, *args, **kwargs):
        pass

    @classmethod
    def set_log_level(cls, *args, **kwargs):
        pass


class _NoopFilter:
    def install(self, *_args, **_kwargs):
        pass


class MarkingMenuInputScenarios(QtBaseTestCase):
    """Drives press/release sequences with QTest and asserts the visible UI."""

    # This class drives a multi-step input simulation across test methods
    # via QTest. processEvents() in tearDown advances the marking-menu
    # state past what the next test's assertions expect, so opt out.
    _drain_qt_events_in_teardown = False

    def setUp(self):
        super().setUp()
        # Flush events left pending by a prior test/file BEFORE building this
        # test's input sequence. This class opts out of the teardown drain
        # (it would advance the menu state the next test expects), but stray
        # DeferredDelete / posted events from an earlier test — e.g. a combobox
        # popup show/grab — otherwise interleave with our QTest events and
        # intermittently knock the menu out of its expected state. Draining here,
        # before self.mm exists, isolates the test without touching its own
        # not-yet-created state.
        self._drain_qt_events()

        # mouseReleaseEvent resolves the widget under the *real* OS cursor via
        # QApplication.widgetAt(QCursor.pos()); if that lands on an unrelated
        # widget it returns early WITHOUT _sync_menu_to_state, so the menu never
        # falls back to the default. With windows overlapping at their default
        # positions and the cursor uncontrolled, widgetAt's result (and the
        # raise/activate z-order race behind it) is non-deterministic — the
        # source of test_08's intermittent 'main' != 'hud'. None of these tests
        # exercise the click-dispatch path; pin widgetAt to None so every
        # release deterministically takes the canonical "cursor over nothing →
        # sync to new input state" branch.
        widget_at_patch = mock.patch.object(
            QtWidgets.QApplication, "widgetAt", return_value=None
        )
        widget_at_patch.start()
        self.addCleanup(widget_at_patch.stop)

        self.parent = QtWidgets.QWidget()
        self.parent.resize(400, 400)
        self.parent.show()
        self.track_widget(self.parent)

        self.mm = DriveableMarkingMenu(self.parent, dict(DEFAULT_BINDINGS))
        # Use QWidget.show directly — MarkingMenu.show() resolves a UI by
        # name, which we don't want during setup.
        QtWidgets.QWidget.show(self.mm)
        QtWidgets.QApplication.processEvents()
        self.track_widget(self.mm)

    # -- Helpers ------------------------------------------------------------

    def activate(self):
        """Simulate the activation key being pressed."""
        self.mm._activation_key_held = True
        self.mm._sync_menu_to_state(buttons=0, modifiers=0)
        QtWidgets.QApplication.processEvents()

    def deactivate(self):
        self.mm._activation_key_held = False
        self.mm._non_default_shown = False
        self.mm._current_widget = None

    def press(self, button, buttons_held_after):
        """Fake a mousePressEvent reaching MarkingMenu."""
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            button,
            buttons_held_after,
            QtCore.Qt.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(self.mm, event)
        QtWidgets.QApplication.processEvents()

    def release(self, button, buttons_held_after):
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            button,
            buttons_held_after,
            QtCore.Qt.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(self.mm, event)
        QtWidgets.QApplication.processEvents()

    def assert_current(self, name):
        ui = self.mm.sb.current_ui
        self.assertIsNotNone(ui, f"expected '{name}', got None")
        self.assertEqual(ui.objectName(), name)

    # -- Scenarios ----------------------------------------------------------

    def test_01_activation_shows_default(self):
        self.activate()
        self.assert_current("hud")

    def test_02_left_press_shows_left_menu(self):
        self.activate()
        self.press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.assert_current("cameras")

    def test_03_left_press_release_returns_to_default(self):
        self.activate()
        self.press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.release(QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.assert_current("hud")

    def test_04_left_then_right_held_shows_chord_menu(self):
        self.activate()
        self.press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.press(QtCore.Qt.RightButton, QtCore.Qt.LeftButton | QtCore.Qt.RightButton)
        self.assert_current("maya")

    def test_05_release_left_with_right_held_shows_right_menu(self):
        # A partial chord release is DEFERRED by the tolerance (it must not switch
        # immediately — that was the "menu shifts" regression); the switch to the
        # remaining-button menu happens only once the held button passes the
        # tolerance (here simulated by firing the timeout).
        self.activate()
        self.press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.press(QtCore.Qt.RightButton, QtCore.Qt.LeftButton | QtCore.Qt.RightButton)
        self.release(QtCore.Qt.LeftButton, QtCore.Qt.RightButton)
        self.assert_current("maya")  # deferred — no immediate switch
        self.mm._on_chord_release_timeout()  # R held past tolerance → switch
        self.assert_current("main")

    def test_06_release_right_with_left_held_shows_left_menu(self):
        self.activate()
        self.press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.press(QtCore.Qt.RightButton, QtCore.Qt.LeftButton | QtCore.Qt.RightButton)
        self.release(QtCore.Qt.RightButton, QtCore.Qt.LeftButton)
        self.assert_current("maya")  # deferred — no immediate switch
        self.mm._on_chord_release_timeout()  # L held past tolerance → switch
        self.assert_current("cameras")

    def test_07_press_release_press_different_button_no_double_press(self):
        """Regression: press L, release L, press R → must show R menu on the
        FIRST press of R, not the second."""
        self.activate()
        self.press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.assert_current("cameras")
        self.release(QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.assert_current("hud")
        self.press(QtCore.Qt.RightButton, QtCore.Qt.RightButton)
        self.assert_current("main")

    def test_08_right_then_release_then_left(self):
        self.activate()
        self.press(QtCore.Qt.RightButton, QtCore.Qt.RightButton)
        self.assert_current("main")
        self.release(QtCore.Qt.RightButton, QtCore.Qt.NoButton)
        self.assert_current("hud")
        self.press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.assert_current("cameras")

    def test_09_modifier_falls_back_to_button_binding(self):
        """Ctrl+L has no specific binding → should resolve to 'cameras'."""
        self.activate()
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.ControlModifier,
        )
        QtWidgets.QApplication.sendEvent(self.mm, event)
        QtWidgets.QApplication.processEvents()
        self.assert_current("cameras")

    def test_10_release_key_clears_non_default_flag(self):
        """When the activation key is released, _non_default_shown resets so
        the next session starts clean."""
        self.activate()
        self.press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.assert_current("cameras")
        self.deactivate()
        self.activate()
        self.assert_current("hud")

    def test_11_chord_three_buttons_falls_back_to_priority(self):
        """L+M+R has no binding → priority button (R) wins."""
        self.activate()
        self.press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.press(QtCore.Qt.MiddleButton, QtCore.Qt.LeftButton | QtCore.Qt.MiddleButton)
        # L+M has no binding; priority is M → editors
        self.assert_current("editors")
        self.press(
            QtCore.Qt.RightButton,
            QtCore.Qt.LeftButton | QtCore.Qt.MiddleButton | QtCore.Qt.RightButton,
        )
        # L+M+R has no binding; priority is R → main (chord 'maya' is L+R only)
        self.assert_current("main")

    def test_12b_suppress_release_then_press_different_button_shows_new_menu(self):
        """Regression: with suppress_default_on_reentry, if the user fully
        releases button A (menu hides) and then presses button B, menu B
        must show on that press — not stay hidden."""
        self.mm._suppress_default_on_reentry = True
        self.activate()
        self.press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.assert_current("cameras")
        self.release(QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.assertIsNone(self.mm._current_widget)
        # Now press R — main should show.
        self.press(QtCore.Qt.RightButton, QtCore.Qt.RightButton)
        self.assert_current("main")
        self.assertIsNotNone(self.mm._current_widget)
        self.assertEqual(self.mm._current_widget.objectName(), "main")
        self.assertTrue(self.mm._current_widget.isVisible())

    def test_12_suppress_default_on_reentry_hides_when_returning_to_default(self):
        """With suppress_default_on_reentry, releasing all buttons after a
        non-default menu hides the child instead of bouncing back to default."""
        self.mm._suppress_default_on_reentry = True
        self.activate()
        self.assert_current("hud")
        self.press(QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.assert_current("cameras")
        self.release(QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        # current_ui still references the last shown UI but the widget is hidden.
        self.assertIsNone(self.mm._current_widget)


class MarkingMenuHoverNavigation(QtBaseTestCase):
    """Hovering a MenuButton must open its ``target`` submenu.

    Guards the regression where nav buttons stopped navigating on mouse-over
    because ``child_enterEvent`` read a stale carrier (``accessibleName``)
    instead of the typed ``target`` property. Deterministic — no real input.
    """

    def setUp(self):
        super().setUp()
        self.sb = StubSwitchboard(dict(DEFAULT_BINDINGS))
        self.parent = QtWidgets.QWidget()
        self.track_widget(self.parent)
        self.mm = DriveableMarkingMenu(self.parent, dict(DEFAULT_BINDINGS))
        self.mm.sb = self.sb
        self.track_widget(self.mm)

    def _enter(self, widget):
        pt = QtCore.QPointF(0, 0)
        self.mm.child_enterEvent(widget, QtGui.QEnterEvent(pt, pt, pt))

    def test_hover_opens_target_submenu(self):
        from uitk.widgets.menuButton import MenuButton

        host = StubUi("polygons#startmenu")
        submenu = StubUi("foo#submenu")
        self.sb.register_ui(host)
        self.sb.register_ui(submenu)

        btn = self._nav_button(MenuButton(target="foo"), host)

        opened = []
        self.mm._set_submenu = lambda menu, w: opened.append(menu)
        self._enter(btn)

        self.assertEqual(len(opened), 1, "hover did not open a submenu")
        self.assertIs(opened[0], submenu)

    def test_hover_filtered_button_opens_component_submenu(self):
        """A filtered button (target + filterTags) hovers to its component
        submenu (polygons Edge -> polygons#edge#submenu), not the base — the
        regression that made the polygons component buttons inert on hover."""
        from uitk.widgets.menuButton import MenuButton

        base = StubUi("polygons#submenu")  # the UI the button lives on
        component = StubUi("polygons#edge#submenu")
        self.sb.register_ui(base)
        self.sb.register_ui(component)

        btn = self._nav_button(MenuButton(target="polygons", filterTags="edge"), base)

        opened = []
        self.mm._set_submenu = lambda menu, w: opened.append(menu)
        self._enter(btn)

        self.assertEqual(len(opened), 1, "filtered button did not navigate on hover")
        self.assertIs(opened[0], component)

    def test_hover_on_targetless_menubutton_is_noop(self):
        from uitk.widgets.menuButton import MenuButton

        btn = self._nav_button(MenuButton(), StubUi("polygons#startmenu"))  # no target

        opened = []
        self.mm._set_submenu = lambda menu, w: opened.append(menu)
        self._enter(btn)

        self.assertEqual(opened, [], "target-less button should not navigate")

    def test_hover_on_plain_button_is_noop(self):
        """A regular slot button must not be treated as a navigator."""
        btn = self._nav_button(QtWidgets.QPushButton(), StubUi("polygons#startmenu"))

        opened = []
        self.mm._set_submenu = lambda menu, w: opened.append(menu)
        self._enter(btn)

        self.assertEqual(opened, [])

    def _nav_button(self, btn, host):
        """Wire a widget the way register_widget would (``ui`` + ``base_name``)
        so child_enterEvent's downstream checks don't AttributeError."""
        btn.ui = host
        btn.base_name = lambda: "x"  # anything != "chk"
        self.track_widget(btn)
        return btn


if __name__ == "__main__":
    unittest.main()
