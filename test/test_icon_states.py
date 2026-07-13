# !/usr/bin/python
# coding=utf-8
"""Unit tests for IconStates and IconManager color pinning.

Regression focus: stateful (color-coded) icons must render their state
color from the moment the UI is built — the first theme sweep of a session
used to repaint them with the plain theme color, leaving every state
toggle "out of sync until first click".

Run standalone: python -m test.test_icon_states
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtWidgets, QtCore

from uitk.widgets.mixins.icon_manager import IconManager
from uitk.widgets.mixins.icon_states import IconStates


OFF = "#5285a6"
ACTIVE = "#e06c6c"
THEME = "#c8c8c8"


def _icon_image(widget):
    """The widget's current icon rendered at its iconSize, as a QImage."""
    size = widget.iconSize()
    return widget.icon().pixmap(size).toImage()


def _reference_image(name, widget, color):
    """A fresh IconManager render of *name* at the widget's iconSize."""
    size = widget.iconSize()
    icon = IconManager.get(name, (size.width(), size.height()), color)
    return icon.pixmap(size).toImage()


class IconTestCase(QtBaseTestCase):
    """Isolates IconManager's class-level default color per test."""

    def setUp(self):
        super().setUp()
        self._saved_default = IconManager._default_color
        IconManager.set_default_color(None)

    def tearDown(self):
        IconManager.set_default_color(self._saved_default)
        super().tearDown()


class TestIconManagerPinning(IconTestCase):
    """Explicitly-colored icons must survive theme sweeps; theme-managed
    icons must keep following them."""

    def test_explicit_color_survives_theme_sweep(self):
        root = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(root)
        pinned_btn = QtWidgets.QPushButton(root)
        themed_btn = QtWidgets.QPushButton(root)
        layout.addWidget(pinned_btn)
        layout.addWidget(themed_btn)

        IconManager.set_icon(pinned_btn, "target", size=(15, 15), color=OFF)
        IconManager.set_icon(themed_btn, "cube", size=(15, 15))

        IconManager.update_widget_icons(root, THEME)

        self.assertEqual(
            _icon_image(pinned_btn),
            _reference_image("target", pinned_btn, OFF),
            "theme sweep must not repaint a pinned (explicitly colored) icon",
        )
        self.assertEqual(
            _icon_image(themed_btn),
            _reference_image("cube", themed_btn, THEME),
            "theme sweep must still update theme-managed icons",
        )

    def test_theme_managed_call_clears_the_pin(self):
        root = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(root)
        btn = QtWidgets.QPushButton(root)
        layout.addWidget(btn)

        IconManager.set_icon(btn, "target", size=(15, 15), color=OFF)
        # Back under theme management (the reset-to-theme contract).
        IconManager.set_icon(btn, "target", size=(15, 15))

        IconManager.update_widget_icons(root, THEME)

        self.assertEqual(
            _icon_image(btn),
            _reference_image("target", btn, THEME),
            "a theme-managed set_icon call must unpin the widget",
        )

    def test_pin_recorded_in_registry_for_refits(self):
        """OptionBox._update_sizing reads name+color from the registry —
        both must reflect the latest swap so a re-fit re-renders faithfully."""
        btn = self.track_widget(QtWidgets.QPushButton())
        IconManager.set_icon(btn, "target", size=(15, 15), color=ACTIVE)
        info = IconManager.registered_info(btn)
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "target")
        self.assertEqual(info["color"], ACTIVE)

        IconManager.set_icon(btn, "cube", size=(15, 15))
        info = IconManager.registered_info(btn)
        self.assertIsNone(info["color"], "auto-theme call must clear the pin")

    def test_registered_info_rejects_unowned_entry(self):
        """An info entry the weak registry doesn't attribute to THIS widget
        (dead widget, recycled id) must not be trusted — it would render a
        wrong icon/pinned color onto the new widget."""
        btn = self.track_widget(QtWidgets.QPushButton())
        # Fabricate the hazard: an entry under this widget's id with no
        # matching weak-registry owner.
        IconManager._widget_icons.pop(id(btn), None)
        IconManager._widget_icon_info[id(btn)] = {
            "name": "cube",
            "size": (15, 15),
            "color": ACTIVE,
        }
        try:
            self.assertIsNone(IconManager.registered_info(btn))
        finally:
            IconManager._widget_icon_info.pop(id(btn), None)

    def test_theme_sweep_purges_orphaned_side_entries(self):
        """Entries whose widgets died (and were dropped by the weak
        registry) must be purged by the sweep — they leaked per dead
        widget and could be wrongly matched by a recycled id."""
        import gc

        root = self.track_widget(QtWidgets.QWidget())
        btn = QtWidgets.QPushButton()
        IconManager.set_icon(btn, "target", size=(15, 15), color=OFF)
        dead_id = id(btn)
        self.assertIn(dead_id, IconManager._widget_icon_info)

        del btn
        gc.collect()  # drop the weak-registry entry
        self.assertNotIn(dead_id, IconManager._widget_icons)

        IconManager.update_widget_icons(root, THEME)
        self.assertNotIn(
            dead_id,
            IconManager._widget_icon_info,
            "the sweep must purge info entries orphaned by widget death",
        )
        self.assertNotIn(dead_id, IconManager._last_update_color)


class TestIconStates(IconTestCase):
    """The shared state-cycling behavior."""

    def _states(self, log):
        return [
            {
                "icon": "target",
                "color": OFF,
                "tooltip": "off-state",
                "callback": lambda: log.append("to-on"),
            },
            {
                "icon": "target",
                "color": ACTIVE,
                "tooltip": "on-state",
                "callback": lambda: log.append("to-off"),
            },
        ]

    def test_attach_applies_state_zero_visuals(self):
        log = []
        btn = self.track_widget(QtWidgets.QPushButton())
        btn.setIconSize(QtCore.QSize(15, 15))
        IconStates(self._states(log), widget=btn)

        self.assertEqual(btn.toolTip(), "off-state")
        self.assertEqual(
            _icon_image(btn),
            _reference_image("target", btn, OFF),
            "attaching must render the current state's color immediately",
        )
        self.assertEqual(log, [], "attaching must not fire state callbacks")

    def test_activate_runs_callback_then_advances(self):
        log = []
        btn = self.track_widget(QtWidgets.QPushButton())
        btn.setIconSize(QtCore.QSize(15, 15))
        cycle = IconStates(self._states(log), widget=btn)

        cycle.activate()
        self.assertEqual(log, ["to-on"])
        self.assertEqual(cycle.current_state, 1)
        self.assertEqual(btn.toolTip(), "on-state")

        cycle.activate()
        self.assertEqual(log, ["to-on", "to-off"])
        self.assertEqual(cycle.current_state, 0)

    def test_callback_assigning_state_supersedes_auto_advance(self):
        """The app-state-sync pattern: the callback places every toggle
        (including the clicked one) on the correct state — a blind
        auto-advance on top would overshoot it."""
        btn = self.track_widget(QtWidgets.QPushButton())
        btn.setIconSize(QtCore.QSize(15, 15))

        cycle = IconStates(
            [
                {"icon": "target", "callback": lambda: setattr_state(1)},
                {"icon": "target", "callback": lambda: setattr_state(0)},
            ],
            widget=btn,
        )

        def setattr_state(index):
            cycle.current_state = index

        cycle.activate()
        self.assertEqual(
            cycle.current_state,
            1,
            "explicit set inside the callback must not be advanced past",
        )
        cycle.activate()
        self.assertEqual(cycle.current_state, 0)

    def test_programmatic_set_applies_visuals_without_callbacks(self):
        log = []
        btn = self.track_widget(QtWidgets.QPushButton())
        btn.setIconSize(QtCore.QSize(15, 15))
        cycle = IconStates(self._states(log), widget=btn)

        cycle.current_state = 1

        self.assertEqual(log, [], "programmatic sync must not fire callbacks")
        self.assertEqual(btn.toolTip(), "on-state")
        self.assertEqual(
            _icon_image(btn), _reference_image("target", btn, ACTIVE)
        )

    def test_on_change_hook_and_notify_suppression(self):
        seen = []
        cycle = IconStates(
            [{"icon": "target"}, {"icon": "target"}], on_change=seen.append
        )
        cycle.current_state = 1
        self.assertEqual(seen, [1])
        cycle.set_current_state(0, notify=False)
        self.assertEqual(seen, [1], "notify=False must skip the on_change hook")
        self.assertEqual(cycle.current_state, 0)

    def test_fallback_callback_used_when_state_has_none(self):
        log = []
        cycle = IconStates([{"icon": "target"}, {"icon": "target"}])
        cycle.activate(fallback=lambda: log.append("fallback"))
        self.assertEqual(log, ["fallback"])
        self.assertEqual(cycle.current_state, 1)


class TestStatefulActionSurvivesThemeSweep(IconTestCase):
    """End-to-end regression: an ActionOption's state color must survive the
    first theme pass of a session (the original out-of-sync bug)."""

    def test_state_color_survives_sweep(self):
        from uitk.widgets.optionBox.options.action import ActionOption

        root = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(root)

        opt = ActionOption(
            states=[
                {"icon": "filter", "color": ACTIVE, "tooltip": "on"},
                {"icon": "filter", "color": OFF, "tooltip": "off"},
            ],
            settings_key=False,
        )
        button = opt.widget  # create + attach (renders state 0)
        layout.addWidget(button)

        # First style application of a session.
        IconManager.update_widget_icons(root, THEME)

        self.assertEqual(
            _icon_image(button),
            _reference_image("filter", button, ACTIVE),
            "the first theme sweep must not wipe the state color",
        )
        self.assertEqual(button.toolTip(), "on")


class TestFooterStatefulButton(IconTestCase):
    """Footer.add_action_button(states=...) — the centralized replacement
    for hand-rolled footer toggle color dances."""

    def _footer(self):
        from uitk.widgets.footer import Footer

        return self.track_widget(Footer(add_size_grip=False))

    def test_states_render_immediately_and_cycle_on_click(self):
        log = []
        footer = self._footer()
        btn = footer.add_action_button(
            states=[
                {
                    "icon": "target",
                    "color": OFF,
                    "tooltip": "multi",
                    "callback": lambda: log.append(True),
                },
                {
                    "icon": "target",
                    "color": ACTIVE,
                    "tooltip": "single",
                    "callback": lambda: log.append(False),
                },
            ],
        )

        self.assertTrue(hasattr(btn, "icon_states"))
        self.assertEqual(btn.toolTip(), "multi")
        self.assertEqual(
            _icon_image(btn),
            _reference_image("target", btn, OFF),
            "footer state button must be color-coded from creation",
        )

        btn.click()
        self.assertEqual(log, [True])
        self.assertEqual(btn.icon_states.current_state, 1)
        self.assertEqual(btn.toolTip(), "single")

    def test_programmatic_sync_tracks_external_state(self):
        footer = self._footer()
        btn = footer.add_action_button(
            states=[
                {"icon": "target", "color": OFF, "tooltip": "multi"},
                {"icon": "target", "color": ACTIVE, "tooltip": "single"},
            ],
        )
        btn.icon_states.current_state = 1
        self.assertEqual(btn.toolTip(), "single")
        self.assertEqual(
            _icon_image(btn), _reference_image("target", btn, ACTIVE)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
