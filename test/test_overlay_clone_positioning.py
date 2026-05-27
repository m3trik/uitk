#!/usr/bin/python
# coding=utf-8
"""Regression: cloned breadcrumb widgets must keep the same global center
as the original they replace. The user-visible invariant: the distance
between a cloned widget and the destination submenu's i-button must
exactly match the layout distance between those two widgets when both
lived in the previous submenu — otherwise the menu appears to "drift"
or "compress" as you descend the hierarchy.

Bug history: previous implementation parented clones to the QMainWindow
and computed ``new_widget.mapFromGlobal(...)`` on a freshly-created
widget. Both work in isolation but make the math fragile to QMainWindow
chrome (menu/dock/status bars) and to Qt's deferred geometry
initialization. The fix parents the clone to ``ui.centralWidget()``
(same coord system as the original i-buttons live in) and computes the
target position via the trusted parent's ``mapFromGlobal``.
"""
import unittest

from qtpy import QtCore, QtWidgets

from conftest import QtBaseTestCase
from uitk.widgets.marking_menu.overlay import Overlay, Path


class TestClonePositioningInvariant(QtBaseTestCase):
    """Build two QMainWindows mimicking polysub and mesh_sub, walk the
    overlay's smooth-positioning + clone-creation pipeline, and verify the
    clone's distance to the breadcrumb i-button matches the same distance
    in the parent submenu — i.e. no drift introduced by the clone path.
    """

    def setUp(self):
        super().setUp()
        # Host fills the role of MarkingMenu's QMainWindow parent
        self.host = QtWidgets.QWidget()
        self.host.resize(1920, 1080)
        self.host.show()
        self.app.processEvents()

        # Source: faux main#startmenu — we only need its i010 (Polygons)
        self.main = QtWidgets.QMainWindow(self.host)
        self.main.resize(600, 475)
        main_cw = QtWidgets.QWidget()
        self.main.setCentralWidget(main_cw)
        self.i010_main = QtWidgets.QPushButton("Polygons", main_cw)
        self.i010_main.setObjectName("i010")
        self.i010_main.setGeometry(160, 0, 66, 21)
        # ``Path.add`` -> ``Path.remove`` reads ``widget.ui`` (the
        # switchboard-set back-reference). Test widgets aren't registered,
        # so we set it manually to mirror the real-world attribute.
        self.i010_main.ui = self.main

        # polygons#submenu (polysub): i010 anchor + i004 mesh target
        self.polysub = QtWidgets.QMainWindow(self.host)
        self.polysub.resize(600, 600)
        polysub_cw = QtWidgets.QWidget()
        self.polysub.setCentralWidget(polysub_cw)
        self.i010_poly = QtWidgets.QPushButton("Polygons", polysub_cw)
        self.i010_poly.setObjectName("i010")
        self.i010_poly.setGeometry(270, 290, 66, 21)
        self.i010_poly.ui = self.polysub
        self.i004_poly = QtWidgets.QPushButton("Mesh", polysub_cw)
        self.i004_poly.setObjectName("i004")
        self.i004_poly.setGeometry(370, 290, 51, 21)
        self.i004_poly.ui = self.polysub

        # polygons#mesh#submenu (meshsub): only i004 anchor (no native i010)
        self.meshsub = QtWidgets.QMainWindow(self.host)
        self.meshsub.resize(600, 600)
        meshsub_cw = QtWidgets.QWidget()
        self.meshsub.setCentralWidget(meshsub_cw)
        self.i004_mesh = QtWidgets.QPushButton("Mesh", meshsub_cw)
        self.i004_mesh.setObjectName("i004")
        self.i004_mesh.setGeometry(270, 290, 66, 21)
        self.i004_mesh.ui = self.meshsub

        self.main.move(100, 100)
        self.main.show()
        self.polysub.move(800, 100)
        self.polysub.show()
        self.meshsub.move(800, 100)
        self.meshsub.show()
        self.app.processEvents()

        # Overlay with a path we can populate directly
        self.overlay = Overlay()
        self.overlay.path = Path()

    def _gc(self, w):
        """Global center of a widget."""
        return w.mapToGlobal(w.rect().center())

    def _smooth(self, ui, w_source, w2_dest):
        """Mirror of ``MarkingMenu._position_submenu_smooth``."""
        p1 = w_source.mapToGlobal(w_source.rect().center())
        w2_dest.resize(w_source.size())
        p2 = w2_dest.mapToGlobal(w2_dest.rect().center())
        diff = p1 - p2
        ui.move(ui.pos() + diff)
        self.app.processEvents()

    def test_clone_distance_to_breadcrumb_equals_polysub_layout_distance(self):
        # Step 1 — main → polysub: smooth-align polysub's i010 with main's
        # i010. ``Path.add`` returns the captured global center (the same
        # value ``_perform_transition`` threads into ``_position_submenu_smooth``).
        self.overlay.path.reset()
        p_polygons = self.overlay.path.add(self.polysub, self.i010_main)
        self.assertIsNotNone(p_polygons)
        self._smooth(self.polysub, self.i010_main, self.i010_poly)

        polygons_in_polysub = self._gc(self.i010_poly)
        mesh_in_polysub = self._gc(self.i004_poly)
        polysub_distance_x = mesh_in_polysub.x() - polygons_in_polysub.x()

        # Step 2 — polysub → meshsub: capture i004_poly center via path.add
        # and smooth-align meshsub's i004 to it.
        p_mesh = self.overlay.path.add(self.meshsub, self.i004_poly)
        self.assertIsNotNone(p_mesh)
        self._smooth(self.meshsub, self.i004_poly, self.i004_mesh)

        # Step 3 — create the polygons clone in meshsub from the
        # intermediate path entry. We don't call clone_widgets_along_path
        # directly because it also creates a Region with signal connections;
        # just call _clone_widget against the intermediate entry.
        intermediate = list(self.overlay.path.intermediate_entries)
        self.assertEqual(len(intermediate), 1)
        prev_widget, position, _ = intermediate[0]
        clone = self.overlay._clone_widget(self.meshsub, prev_widget, position)
        self.app.processEvents()

        clone_center = self._gc(clone)
        mesh_in_meshsub = self._gc(self.i004_mesh)
        meshsub_distance_x = mesh_in_meshsub.x() - clone_center.x()

        # The two distances must match: the clone-to-mesh spacing in
        # meshsub equals the polygons-to-mesh spacing in polysub.
        self.assertEqual(
            meshsub_distance_x,
            polysub_distance_x,
            f"Clone drift: polysub spacing={polysub_distance_x}, "
            f"meshsub spacing={meshsub_distance_x}",
        )

        # And the clone's center must equal the saved position (P_pos).
        self.assertEqual(clone_center.x(), position.x())
        self.assertEqual(clone_center.y(), position.y())

    def test_clone_parented_to_qmainwindow(self):
        """The clone must be a direct child of the QMainWindow, not its
        central widget — empirically required for the hover-to-return
        gesture, which depends on Qt routing enter events to the
        marking-menu filter installed at the QMainWindow level."""
        self.overlay.path.reset()
        position = self.overlay.path.add(self.polysub, self.i010_main)
        self.assertIsNotNone(position)
        clone = self.overlay._clone_widget(self.meshsub, self.i010_main, position)
        self.assertIs(clone.parent(), self.meshsub)

    def test_path_add_returns_none_for_invisible_widget(self):
        """Regression: ``_perform_transition`` reads the anchor from
        ``path.add``'s return value, so the contract — None on skip —
        must hold so the caller can fall back to a live read rather than
        silently picking up the previous path entry."""
        hidden = QtWidgets.QPushButton("hidden", self.polysub.centralWidget())
        hidden.setVisible(False)
        result = self.overlay.path.add(self.polysub, hidden)
        self.assertIsNone(result)
        self.assertIsNone(self.overlay.path.add(self.polysub, None))


if __name__ == "__main__":
    unittest.main()
