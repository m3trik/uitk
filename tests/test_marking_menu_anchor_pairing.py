#!/usr/bin/python
# coding=utf-8
"""Regression: submenu anchor alignment must pair launcher and anchor by
``target``, not objectName.

Bug: ``_position_submenu_smooth`` located the arriving submenu's anchor via
``sb.get_widget(w.objectName(), ui)`` — an unenforced cross-file numbering
convention (every button pointing at node X named ``iNNN``). New menu sets
that named buttons freely (blender_menus' Animation → Rigging chain: launcher
``i031`` → anchor ``i032``) silently lost alignment: the arriving submenu
never slid its anchor under the cursor, breaking the radial gesture. User
report: "we didn't name the submenu's menubutton with the same objectname as
the previous menubutton that launched the submenu … we shouldn't have to
worry about the objectname if both buttons already share a target value."

Fix: launcher and self-anchor both carry the node's ``target`` — the same
identity hover-nav and release-resolution already key on — so the pair lookup
matches on it, with ``submenu_name()`` (target + filterTags) disambiguating
shared-target candidates and objectName retained only as a targetless-widget
fallback.

Determinism: the menu fixtures are CHILD widgets (``Qt.Widget`` flag) of one
frameless host, and every position assert compares in HOST coordinates. Real
top-level windows flunked the full-suite run this file was born green in:
the suite runs on the native platform, where a freshly shown window's frame
geometry settles asynchronously — ``ui.move(ui.pos() + diff)`` then computes
from a stale frame origin under load (position asserts failed while the size
assert passed). Child-widget geometry is synchronous and window-manager-free,
and host-space comparison stays exact even if the host itself gets relocated
BETWEEN reads — but Qt 6.10/Windows resolves global maps through the native
window origin, which the WM can nudge a few px *inside* the position flow
itself, so landing asserts allow ``_DRIFT_TOLERANCE`` (see ``assert_landed``).
"""
import logging
import unittest

from qtpy import QtCore, QtWidgets

from conftest import QtBaseTestCase
from uitk.widgets.marking_menu._marking_menu import MarkingMenu
from uitk.widgets.menuButton import MenuButton


class _StubSb:
    """Only the piece ``_position_submenu_smooth`` reads: the legacy
    objectName lookup (mirrors Switchboard.get_widget's child-by-name)."""

    def get_widget(self, name, ui):
        return ui.findChild(QtWidgets.QWidget, name) if name else None


class _MM(MarkingMenu):
    """Bypass MarkingMenu.__init__ — exercise the exact methods under test."""

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        self.logger = logging.getLogger("AnchorPairingTest")
        self.logger.setLevel(logging.ERROR)
        self.sb = _StubSb()


def _menu_button(parent, name, target, filter_tags="", geometry=(10, 10, 80, 24)):
    b = MenuButton(parent, target=target, filterTags=filter_tags)
    b.setObjectName(name)
    b.setGeometry(*geometry)
    b.show()
    return b


# Host-space point the arriving menu's pair widget must land on.
_TARGET = QtCore.QPoint(450, 350)


class TestAnchorPairing(QtBaseTestCase):
    """Launcher↔anchor pairing for submenu alignment."""

    _drain_qt_events_in_teardown = False

    def setUp(self):
        super().setUp()
        self.mm = _MM()
        self.track_widget(self.mm)

        # One frameless host; both menus are embedded children (Qt.Widget) so
        # geometry is pure widget-tree math — no native frames, no WM.
        self.host = QtWidgets.QWidget()
        self.host.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.host.resize(900, 700)
        self.host.show()
        self.track_widget(self.host)

        # Departing menu: hosts the launcher (only size/geometry matter — the
        # anchor point is passed explicitly, as production does via path.add).
        self.departing = QtWidgets.QMainWindow(self.host, QtCore.Qt.Widget)
        self.departing.setObjectName("object_animation#submenu")
        self.departing.setCentralWidget(QtWidgets.QWidget())
        self.departing.setGeometry(0, 0, 200, 200)
        self.departing.show()

        # Arriving menu: mirrors blender_menus' rig#submenu — the anchor's
        # objectName (i032) does NOT match the launcher's (i031); only the
        # target pairs them.
        self.arriving = QtWidgets.QMainWindow(self.host, QtCore.Qt.Widget)
        self.arriving.setObjectName("rig#submenu")
        self.arriving.setCentralWidget(QtWidgets.QWidget())
        self.arriving.setGeometry(420, 60, 300, 300)
        central = self.arriving.centralWidget()
        self.anchor = _menu_button(central, "i032", "rig", geometry=(10, 10, 100, 30))
        self.sibling_a = _menu_button(
            central, "i033", "armature", geometry=(10, 50, 100, 30)
        )
        self.sibling_b = _menu_button(
            central, "i034", "pose", geometry=(10, 90, 100, 30)
        )
        self.arriving.show()

        self.launcher = _menu_button(
            self.departing.centralWidget(), "i031", "rig", geometry=(20, 20, 71, 24)
        )
        QtWidgets.QApplication.processEvents()

    def _position(self, launcher=None):
        """Run the alignment against ``_TARGET`` (host space → global at call
        time; child geometry applies synchronously, no event pumping)."""
        self.mm._position_submenu_smooth(
            self.arriving,
            launcher or self.launcher,
            anchor_global=self.host.mapToGlobal(_TARGET),
        )

    def _host_pos(self, widget):
        """``widget``'s center in HOST coordinates — the current host origin
        cancels out of both reads, so the value is WM-independent."""
        return self.host.mapFromGlobal(widget.mapToGlobal(widget.rect().center()))

    # Qt 6.10/Windows resolves global maps through the NATIVE window origin,
    # and the WM nudges a freshly shown frameless host asynchronously — under
    # a full-suite run that origin drifted a few px INSIDE the position flow
    # (between the anchor capture and production's own mapToGlobal read), so
    # exact equality flaked by (1,5) in exactly the tests that create widgets
    # mid-test. A wrong-anchor pairing regression is off by hundreds of px —
    # a small tolerance keeps the assert meaningful and the suite stable.
    _DRIFT_TOLERANCE = 8

    def assert_landed(self, widget, msg):
        pos = self._host_pos(widget)
        drift = (pos - _TARGET).manhattanLength()
        self.assertLessEqual(
            drift, self._DRIFT_TOLERANCE, f"{msg} (landed {pos}, want {_TARGET})"
        )

    def test_pairs_by_target_when_object_names_differ(self):
        """THE regression: i031 → i032 share target 'rig'; the arriving menu
        must still slide its anchor under the captured trigger point."""
        self._position()
        self.assert_landed(
            self.anchor,
            "anchor must land at the launcher's captured trigger point — "
            "pairing must key on target, not objectName",
        )

    def test_anchor_resized_to_launcher(self):
        """Visual continuity: the paired anchor takes the launcher's size so
        the button doesn't pop during the transition."""
        self._position()
        self.assertEqual(self.anchor.size(), self.launcher.size())

    def test_target_match_beats_coincidental_name_match(self):
        """A same-named widget with a DIFFERENT target (blender_menus' b031
        names two unrelated nodes) must lose to the target match."""
        decoy = _menu_button(
            self.arriving.centralWidget(), "i031", "pose", geometry=(10, 130, 100, 30)
        )
        self.track_widget(decoy)
        self._position()
        self.assert_landed(
            self.anchor,
            "target identity must win over a coincidental objectName reuse",
        )
        self.assertNotEqual(decoy.size(), self.launcher.size())

    def test_filter_tags_disambiguate_shared_target(self):
        """Two candidates share the bare target (a shared submenu reached
        through different filterTags): full submenu_name() picks the pair."""
        edge = _menu_button(
            self.arriving.centralWidget(),
            "x001",
            "polygons",
            filter_tags="edge",
            geometry=(150, 10, 100, 30),
        )
        face = _menu_button(
            self.arriving.centralWidget(),
            "x002",
            "polygons",
            filter_tags="face",
            geometry=(150, 50, 100, 30),
        )
        launcher = _menu_button(
            self.departing.centralWidget(),
            "x000",
            "polygons",
            filter_tags="face",
            geometry=(20, 60, 71, 24),
        )
        for w in (edge, face, launcher):
            self.track_widget(w)

        self._position(launcher=launcher)
        self.assert_landed(
            face,
            "submenu_name() (target + filterTags) must disambiguate "
            "shared-target candidates",
        )

    def test_objectname_fallback_for_targetless_widgets(self):
        """Back-compat: a targetless launcher still pairs by objectName."""
        named_twin = QtWidgets.QPushButton(self.arriving.centralWidget())
        named_twin.setObjectName("plain001")
        named_twin.setGeometry(150, 90, 100, 30)
        named_twin.show()
        launcher = QtWidgets.QPushButton(self.departing.centralWidget())
        launcher.setObjectName("plain001")
        launcher.setGeometry(20, 100, 71, 24)
        launcher.show()
        for w in (named_twin, launcher):
            self.track_widget(w)

        self._position(launcher=launcher)
        self.assert_landed(
            named_twin,
            "targetless widgets must keep the legacy objectName pairing",
        )

    def test_no_pair_is_a_graceful_noop(self):
        """No target match and no name match: the menu must not move (and
        must not raise) — same silent degradation as before."""
        launcher = _menu_button(
            self.departing.centralWidget(),
            "zz99",
            "nonexistent_node",
            geometry=(20, 140, 71, 24),
        )
        self.track_widget(launcher)
        before = self.arriving.pos()

        self._position(launcher=launcher)
        self.assertEqual(self.arriving.pos(), before)


if __name__ == "__main__":
    unittest.main()
