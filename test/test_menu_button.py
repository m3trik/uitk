# !/usr/bin/python
# coding=utf-8
"""Unit tests for the MenuButton widget.

MenuButton replaces the legacy ``i``-prefixed navigation buttons. These tests
pin the type-based / property-based contract the marking menu relies on:

- routing is carried as Designer/.ui-settable QtCore.Property values
  (``target`` / ``filterTags``), not in ``accessibleName()``;
- ``target`` and the filter tags stay separate (never re-merged);
- detection is by type (``isinstance``), and breadcrumb clones carry the
  routing via ``clone_properties``.

Run standalone: python -m test.test_menu_button
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtCore, QtGui  # noqa: E402

from uitk.widgets.menuButton import MenuButton  # noqa: E402


class TestMenuButtonProperties(QtBaseTestCase):
    """Property storage and the .ui round-trip path."""

    def test_constructor_kwargs_set_routing(self):
        b = MenuButton(target="polygons#submenu", filterTags="face")
        self.assertEqual(b.target, "polygons#submenu")
        self.assertEqual(b.filterTags, "face")

    def test_setProperty_routes_to_setters(self):
        """QUiLoader/Designer set values via QObject.setProperty — the declared
        QtCore.Property must route those to the validated setters."""
        b = MenuButton()
        b.setProperty("target", "edit#submenu")
        b.setProperty("filterTags", "edge")
        self.assertEqual(b.target, "edit#submenu")
        self.assertEqual(b.filter_tag_list(), ["edge"])

    def test_class_property_set_for_qss(self):
        """Styled via QPushButton[class~="MenuButton"]."""
        self.assertEqual(MenuButton().property("class"), "MenuButton")


class TestMenuButtonTargetResolution(QtBaseTestCase):
    """Target stays clean; filter tags are exposed separately as a list — the
    two are never re-merged into one overloaded string."""

    def test_target_is_clean_passthrough(self):
        b = MenuButton(target="cameras#submenu")
        self.assertEqual(b.target, "cameras#submenu")

    def test_target_and_filter_tags_stay_separate(self):
        """The whole point of the widget: routing isn't smuggled into one field."""
        b = MenuButton(target="polygons#submenu", filterTags="face")
        self.assertEqual(b.target, "polygons#submenu")
        self.assertEqual(b.filter_tag_list(), ["face"])

    def test_filter_tag_list_comma_and_space(self):
        b = MenuButton(target="display#submenu", filterTags="edge, vertex")
        self.assertEqual(b.filter_tag_list(), ["edge", "vertex"])

    def test_filter_tag_list_empty_when_unset(self):
        self.assertEqual(MenuButton(target="x#submenu").filter_tag_list(), [])

    def test_empty_target_is_empty_string(self):
        self.assertEqual(MenuButton().target, "")


class TestMenuButtonClone(QtBaseTestCase):
    """Breadcrumb clones (overlay._clone_widget) copy the declared
    ``clone_properties`` so a cloned MenuButton still navigates."""

    def test_declares_clone_properties(self):
        self.assertEqual(MenuButton.clone_properties, ("target", "filterTags"))

    def test_clone_property_copy_round_trips(self):
        """Reproduce the overlay's generic copy: setProperty(name, src.property(name))."""
        src = MenuButton(target="polygons#submenu", filterTags="face")
        clone = MenuButton()
        for name in src.clone_properties:
            clone.setProperty(name, src.property(name))
        self.assertEqual(clone.target, "polygons#submenu")
        self.assertEqual(clone.filter_tag_list(), ["face"])


class TestMenuButtonDetectionContract(QtBaseTestCase):
    """The marking menu discriminates nav buttons by type."""

    def test_is_a_pushbutton(self):
        """isinstance(QPushButton) still holds (subclass)."""
        self.assertIsInstance(MenuButton(), QtWidgets.QPushButton)

    def test_plain_pushbutton_is_not_a_menubutton(self):
        """A regular slot button must not be picked up as a navigator."""
        self.assertNotIsInstance(QtWidgets.QPushButton(), MenuButton)


class TestMenuButtonHoverReset(QtBaseTestCase):
    """A marking-menu button is normally hidden *under the cursor* — the menu
    closes in place, so no ``leaveEvent`` precedes the hide. Qt leaves
    ``WA_UnderMouse`` set in that case, which keeps ``State_MouseOver`` (and the
    QSS ``:hover`` rule) active, so the button reappears painted as hovered until
    a real enter/leave recomputes it ("hover styling doesn't always clear").
    ``hideEvent`` must drop the lingering hover state on every hide.
    """

    @staticmethod
    def _is_hover_styled(widget):
        """True when the widget's style option still carries the QSS ``:hover``
        state (``State_MouseOver``) — what actually paints a button hovered."""
        opt = QtWidgets.QStyleOption()
        opt.initFrom(widget)
        return bool(opt.state & QtWidgets.QStyle.State_MouseOver)

    def _hovered_button(self):
        b = self.track_widget(MenuButton(target="polygons#submenu"))
        b.show()
        # Simulate the cursor being over the button — what a real enterEvent
        # leaves behind, and the driver Qt reads for State_MouseOver / :hover.
        b.setAttribute(QtCore.Qt.WA_UnderMouse, True)
        self.assertTrue(self._is_hover_styled(b))
        return b

    def test_hideEvent_clears_hover_state(self):
        """Deterministic guard: the override drops the hover style-state
        regardless of whether the offscreen platform synthesizes a leave."""
        b = self._hovered_button()
        b.hideEvent(QtGui.QHideEvent())
        self.assertFalse(
            self._is_hover_styled(b),
            "MenuButton.hideEvent must clear State_MouseOver so the button is "
            "not reshown styled as hovered.",
        )

    def test_real_hide_clears_hover_state(self):
        """The override is wired into the real hide() path (children receive a
        QHideEvent when their menu window hides)."""
        b = self._hovered_button()
        b.hide()
        self.assertFalse(self._is_hover_styled(b))


if __name__ == "__main__":
    unittest.main()
