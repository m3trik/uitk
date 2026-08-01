# !/usr/bin/python
# coding=utf-8
"""Tests for ExpandableList widget.

Covers stylesheet propagation to reparented sublists, sublist positioning
before show, and _logical_ancestor integration for marking menu hit-testing.
"""

import sys
from pathlib import Path

# Add package root to path
PACKAGE_ROOT = Path(__file__).parent.parent.absolute()
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from conftest import QtBaseTestCase
from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.expandableList import ExpandableList
from uitk.widgets.mainWindow import MainWindow


class _BareSwitchboard:
    """Minimal stand-in so MainWindow.__init__ completes without uitk.Switchboard."""

    def convert_to_legal_name(self, name):
        return name

    def get_base_name(self, name):
        return name

    def has_tags(self, *_a, **_k):
        return False

    def get_slots_instance(self, *_a, **_k):
        return None

    def center_widget(self, *_a, **_k):
        return None


class TestExpandableList(QtBaseTestCase):
    """Tests for ExpandableList core behavior."""

    def setUp(self):
        super().setUp()
        self.window = QtWidgets.QMainWindow()
        self.track_widget(self.window)

    def test_sublist_inherits_stylesheet(self):
        """Verify sublists inherit stylesheet when reparented to window.

        Bug: Sublists parented to self.window() didn't inherit the UI's
        stylesheet, causing items to appear transparent/unstyled.
        Fixed: 2026-03-11
        """
        # Apply a stylesheet to the window (simulates what _init_ui does)
        test_qss = "QPushButton { background-color: rgb(50, 50, 50); }"
        self.window.setStyleSheet(test_qss)

        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        w1 = lw.add("Button 1")

        # The sublist is parented to self.window(), not to lw directly
        sublist = w1.sublist
        self.assertIsNotNone(sublist)

        # Sublist should have the stylesheet even though it's reparented
        sublist_ss = sublist.styleSheet()
        self.assertTrue(
            len(sublist_ss) > 0,
            "Sublist should have an inherited stylesheet applied",
        )
        self.assertIn("background-color", sublist_ss)

    def test_nested_sublist_inherits_stylesheet(self):
        """Verify deeply nested sublists also get stylesheet propagation."""
        test_qss = "QLabel { background-color: rgb(40, 40, 40); }"
        self.window.setStyleSheet(test_qss)

        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        w1 = lw.add("Item 1")
        w2 = w1.sublist.add("Sub Item")
        w2.sublist.add("Deep Item")

        # Each level of sublist should have a stylesheet
        self.assertTrue(len(w1.sublist.styleSheet()) > 0)
        self.assertTrue(len(w2.sublist.styleSheet()) > 0)

    def test_logical_ancestor_set_on_sublist(self):
        """Verify _logical_ancestor is set so MarkingMenu can detect sublist items.

        Bug: MarkingMenu.mouseReleaseEvent couldn't recognize sublist items
        as belonging to the current UI, causing mouse grab to persist.
        Fixed: 2026-03-11
        """
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        w1 = lw.add("Button 1")

        sublist = w1.sublist
        self.assertTrue(
            hasattr(sublist, "_logical_ancestor"),
            "Sublist should have _logical_ancestor attribute set",
        )
        self.assertIs(
            sublist._logical_ancestor,
            lw,
            "_logical_ancestor should point to the root ExpandableList",
        )

    def test_nested_logical_ancestor_points_to_root(self):
        """Verify nested sublists' _logical_ancestor always points to root list."""
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        w1 = lw.add("Item 1")
        w2 = w1.sublist.add("Sub Item")

        # Both levels should point back to the root (lw)
        self.assertIs(w1.sublist._logical_ancestor, lw)
        self.assertIs(w2.sublist._logical_ancestor, lw)

    def test_sublist_positioned_before_show(self):
        """Verify sublists are moved to correct position before becoming visible.

        Bug: show() was called before move(), causing a flash at position (0,0).
        Fixed: 2026-03-11
        """
        self.window.resize(400, 300)
        self.window.show()

        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.move(100, 100)
        lw.show()

        w1 = lw.add("QPushButton", setText="Button 1")
        w1.sublist.add("Sub Label")

        # Trigger the enter event on w1 to show the sublist
        lw._handle_widget_enter_event(w1)

        # After the handler, the sublist should be visible and NOT at (0, 0)
        self.assertTrue(w1.sublist.isVisible())
        sublist_pos = w1.sublist.pos()
        # The sublist shouldn't be at the parent widget's origin
        self.assertFalse(
            sublist_pos.x() == 0 and sublist_pos.y() == 0,
            f"Sublist should be positioned away from origin, got {sublist_pos}",
        )

    def test_sublist_has_correct_size_before_show(self):
        """Verify sublist has correct dimensions when shown."""
        lw = ExpandableList(self.window, fixed_item_height=25)
        self.track_widget(lw)
        w1 = lw.add("QPushButton", setText="Parent")
        w1.sublist.add(["Child A", "Child B", "Child C"])

        # Before showing, sublist should have non-zero size from sizeHint
        size = w1.sublist.sizeHint()
        self.assertGreater(size.width(), 0, "Sublist width should be > 0")
        self.assertGreater(size.height(), 0, "Sublist height should be > 0")

    def test_sublist_sizes_to_own_content_not_root_width(self):
        """A sublist must size to its own contents, not the starting list's width.

        Bug: width-pinning kwargs passed to the root list (e.g.
        ``setMinimumWidth``) were copied verbatim into every sublist's config
        (``_create_sublist_config`` spreads ``**self.kwargs``), so each flyout was
        forced to the root list's minimum width instead of hugging its own — much
        narrower — contents. Fix: a sublist carries no size constraint of its own
        (``_add_sublist`` resets its min/max size), so it always tracks sizeHint.
        Fixed: 2026-07-10
        """
        lw = ExpandableList(self.window, fixed_item_height=21, setMinimumWidth=200)
        self.track_widget(lw)
        w1 = lw.add("A wide-ish parent item")
        w1.sublist.add("x")  # a single, narrow child

        sublist = w1.sublist
        # The root's pinned width must NOT cascade to the sublist.
        self.assertEqual(
            sublist.minimumWidth(),
            0,
            "sublist must not inherit the root list's forced minimum width",
        )
        # And it should hug its own (narrow) content, not the 200px root width.
        self.assertLess(
            sublist.sizeHint().width(),
            200,
            "sublist should size to its own contents, not the starting list",
        )

    def test_nested_sublist_also_sizes_to_own_content(self):
        """The unconstrained-size invariant must hold at every depth, not just the
        first sublist — a grandchild sublist must not inherit the root's width
        either (the root's kwargs propagate down the chain, so each level's
        ``_add_sublist`` must clear them)."""
        lw = ExpandableList(self.window, fixed_item_height=21, setFixedWidth=180)
        self.track_widget(lw)
        w1 = lw.add("Parent")
        w2 = w1.sublist.add("Child")
        w2.sublist.add("y")  # grandchild leaf

        self.assertEqual(w1.sublist.minimumWidth(), 0)
        self.assertEqual(w2.sublist.minimumWidth(), 0)
        self.assertLess(w2.sublist.sizeHint().width(), 180)

    def test_sublist_not_capped_by_root_max_width(self):
        """A root max-width cap must not clip a wider sublist either — a max
        constraint inherited from the root would shrink a flyout whose contents
        are wider than the starting list, still failing 'size to own content'."""
        lw = ExpandableList(self.window, fixed_item_height=21, setMaximumWidth=30)
        self.track_widget(lw)
        w1 = lw.add("Parent")
        w1.sublist.add("A fairly long child item that exceeds 30px")

        sublist = w1.sublist
        # The root's cap must not cascade — the sublist stays unconstrained.
        self.assertGreater(
            sublist.maximumWidth(),
            30,
            "sublist must not inherit the root list's maximum-width cap",
        )
        # And its content-driven hint is free to exceed the root's 30px cap.
        self.assertGreater(sublist.sizeHint().width(), 30)

    def test_overlay_first_sublist_covers_starting_list_width(self):
        """Covering presets are the exception to content-sizing: the first
        sublist sits on top of the starting list, so it must be at least as wide
        as that list to cover it fully — even when its own content is narrower.

        Covers the explicit overlay presets ``expand_overlay`` (position
        ``overlay``) and ``expand_overlay_left`` (position ``overlay_right``),
        plus ``expand_up`` — whose ``use_item_height`` offset slides the first
        sublist over the root button (the preset the Select-by-Type list uses).
        """
        # A wide PARENT item drives the list width through content (the list fits
        # its widest item) — the way the starting list is actually wide in
        # production. ``resize()`` alone can't force it: the list re-fits to its
        # content on add/show, so a resize to 220 collapses back to the item width.
        wide = "A deliberately wide starting-list parent item"
        for preset in (
            "expand_overlay",
            "expand_overlay_left",
            "expand_overlay_up_left",
            "expand_up",
        ):
            with self.subTest(preset=preset):
                win = QtWidgets.QMainWindow()
                self.track_widget(win)
                win.resize(400, 300)
                win.show()
                lw = ExpandableList(win, fixed_item_height=21)
                self.track_widget(lw)
                lw.apply_preset(preset)
                lw.show()
                root = lw.add(wide)  # wide parent -> wide list
                root.sublist.add("y")  # a narrow child, hint << list width
                # Sanity: the flyout's own content is much narrower than the list.
                self.assertLess(root.sublist.sizeHint().width(), lw.width())

                lw._handle_widget_enter_event(root)
                self.assertGreaterEqual(
                    root.sublist.width(),
                    lw.width(),
                    f"{preset}: overlay first sublist must cover the starting list",
                )

    def test_overlay_up_left_anchors_sublist_bottom_right(self):
        """``expand_overlay_up_left`` anchors the first sublist's BOTTOM-right
        corner to the trigger's bottom-right, so it covers the starting list and
        grows upward; deeper sublists fan LEFT off that stable right edge."""
        self.window.resize(500, 400)
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.apply_preset("expand_overlay_up_left")
        lw.show()
        root = lw.add("Tools")
        for label in ("A", "B", "C", "D"):  # tall enough to prove upward growth
            root.sublist.add(label)

        lw._handle_widget_enter_event(root)
        sub = root.sublist
        trigger_bottom_right = root.mapToGlobal(
            QtCore.QPoint(root.width(), root.height())
        )
        self.assertEqual(
            sub.mapToGlobal(QtCore.QPoint(sub.width(), sub.height())),
            trigger_bottom_right,
        )
        # Growing upward: the flyout's top sits above the trigger's top.
        self.assertLess(
            sub.mapToGlobal(QtCore.QPoint(0, 0)).y(),
            root.mapToGlobal(QtCore.QPoint(0, 0)).y(),
        )
        self.assertEqual(lw._preset_child_position, "left")

    def test_nonoverlay_sublist_stays_content_width_under_wide_root(self):
        """A fan-out (non-overlay) preset keeps content-sized sublists even when
        the starting list is much wider — only overlays widen to cover."""
        self.window.resize(400, 300)
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.apply_preset("expand_right")
        lw.show()
        # Wide PARENT item -> wide list via content (resize() re-fits away on show).
        root = lw.add("A deliberately wide starting-list parent item")
        root.sublist.add("y")

        lw._handle_widget_enter_event(root)
        self.assertLess(
            root.sublist.width(),
            lw.width(),
            "fan-out sublist must size to content, not the wide starting list",
        )

    def test_deep_overlay_sublist_is_content_sized_not_covering(self):
        """The cover-the-parent rule applies only to the FIRST overlay sublist.
        Deeper sublists fan out (child position 'right'/'left') and must size to
        their own content, not the (wide) starting list."""
        self.window.resize(500, 400)
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.apply_preset("expand_overlay")
        lw.show()
        # Wide PARENT item -> wide list via content (resize() re-fits away on show).
        root = lw.add("A deliberately wide starting-list root item")
        cat = root.sublist.add("Category")
        cat.sublist.add("z")  # narrow grandchild

        lw._handle_widget_enter_event(root)  # first (overlay) sublist
        root.sublist._handle_widget_enter_event(cat)  # deeper (fan-out) sublist
        self.assertLess(
            cat.sublist.width(),
            lw.width(),
            "a deep overlay-chain sublist must size to content, not cover the root",
        )

    def test_consumed_release_resets_button_item_down_state(self):
        """A button item (no option box) that got the press but never the
        release — the list consumes it to drive ``on_item_interacted`` — must
        not be left visually sunken.

        Bug: ``eventFilter`` consumed the MouseButtonRelease and emitted, but a
        QAbstractButton item stayed ``isDown()`` True (it sank on press and
        never saw the release), stranding the row visually pressed. The filter
        now resets the down state before emitting.
        """
        lw = ExpandableList(self.window, fixed_item_height=18)
        self.track_widget(lw)
        root = lw.add("By Type")
        btn = QtWidgets.QPushButton("Settings")
        root.sublist.add(btn)

        emitted = []
        root.sublist.on_item_interacted.connect(emitted.append)

        btn.setDown(True)  # simulate the sink from a press
        rel = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(2, 2),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        consumed = root.sublist.eventFilter(btn, rel)

        self.assertTrue(consumed, "the list must consume the item's release")
        self.assertEqual(emitted, [btn], "on_item_interacted must carry the item")
        self.assertFalse(btn.isDown(), "button item must not be left sunken")

    def test_force_hide_collapses_sublist_shown_under_hidden_ancestor(self):
        """A sublist open at hide-time must reopen collapsed.

        Bug: sublists are reparented to the window, so when an ancestor is
        hidden they get a spontaneous hide (``isVisible()`` → False) but keep
        their explicit-visible flag. ``_force_hide_all``'s old ``isVisible()``
        guard then skipped them, the flag survived, and Qt's ``showChildren``
        restored them on the next show — the list "reshown in the previously
        open state". The collapse must clear the flag unconditionally.

        Reproduced deterministically by showing a sublist while its window is
        not visible: ``isVisible()`` is False yet ``isHidden()`` is False (the
        exact mid-hide condition). The fix asserts ``isHidden()`` afterward —
        the flag ``showChildren`` actually consults — not an OS-dependent
        visibility outcome.
        """
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        w1 = lw.add("Parent")
        w1.sublist.add("Child")  # non-empty so it is a real, showable sublist

        # Window is not shown → ancestor not visible. Explicitly show the
        # sublist: not visible (ancestor hidden) but not explicitly hidden.
        w1.sublist.show()
        self.assertFalse(w1.sublist.isVisible())
        self.assertFalse(w1.sublist.isHidden())

        # Hiding the list (what hideEvent does) must collapse it unconditionally.
        lw._force_hide_all()
        self.assertTrue(
            w1.sublist.isHidden(),
            "sublist must be explicitly hidden so a later show won't restore it",
        )

    def test_root_list_attribute(self):
        """Verify root_list always points to the topmost ExpandableList."""
        lw = ExpandableList(self.window)
        self.track_widget(lw)
        w1 = lw.add("A")
        w2 = w1.sublist.add("B")
        w3 = w2.sublist.add("C")

        self.assertIs(w1.sublist.root_list, lw)
        self.assertIs(w2.sublist.root_list, lw)
        self.assertIs(w3.sublist.root_list, lw)

    def test_explicit_hide_collapses_open_sublists(self):
        """Calling hide() on a list must tear down its open sublists.

        Bug: hide() used to early-return while any sublist was visible. Since
        sublists are reparented to the window (not Qt children of the list),
        an explicit dismiss then closed *nothing* — neither the list nor the
        sublist. hide() now force-collapses the hierarchy, then hides.
        """
        lw = ExpandableList(fixed_item_height=21)  # top-level: sublists parent to lw
        self.track_widget(lw)
        w1 = lw.add("Parent")
        c1 = w1.sublist.add("Child")
        c1.sublist.add("Grandchild")
        lw.show()
        lw._handle_widget_enter_event(w1)
        w1.sublist._handle_widget_enter_event(c1)
        self.assertTrue(w1.sublist.isVisible())
        self.assertTrue(c1.sublist.isVisible())

        lw.hide()

        self.assertFalse(lw.isVisible(), "the list itself must hide")
        self.assertTrue(w1.sublist.isHidden(), "sublist must collapse on hide")
        self.assertTrue(c1.sublist.isHidden(), "nested sublist must collapse on hide")

    def test_sublist_stays_collapsed_after_window_reshow(self):
        """A sublist open at hide-time must not reopen on the next show.

        Bug: after ``_force_hide_all`` correctly collapses sublists on hide,
        Qt delivers a synthetic ``Enter`` to the item under the stationary
        cursor when the window reappears. That Enter ran the normal
        hover-to-expand path, silently reopening the previously-expanded
        sublist — the list "reshown in its previously open state".
        Fixed: gate the Enter-driven open behind a show-time latch that
        clears only once the cursor actually moves.
        """
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.show()
        w1 = lw.add("Parent")
        w1.sublist.add("Child")  # non-empty so it is a real, showable sublist

        # Open the sublist (direct call mirrors a genuine hover).
        lw._handle_widget_enter_event(w1)
        self.assertTrue(w1.sublist.isVisible())

        # Window hides — hideEvent/_force_hide_all collapse the sublist.
        self.window.hide()
        self.assertTrue(w1.sublist.isHidden())

        # Reshow re-arms the latch (showEvent records the cursor position).
        self.window.show()
        self.assertIsNotNone(
            lw._suppress_open_pos, "showEvent must arm the auto-open latch on reshow"
        )

        # Pin the latch to the current cursor so the "stationary cursor"
        # condition is deterministic — the suite runs under the native QPA
        # locally (real, moving pointer) and offscreen only in CI.
        lw._suppress_open_pos = QtGui.QCursor.pos()

        # The synthetic Enter Qt fires at the unchanged cursor position must
        # NOT reopen the sublist.
        QtWidgets.QApplication.sendEvent(w1, QtCore.QEvent(QtCore.QEvent.Enter))
        self.assertFalse(
            w1.sublist.isVisible(),
            "sublist must stay collapsed on reshow until the cursor moves",
        )

    def test_auto_open_resumes_after_cursor_moves(self):
        """Once the cursor moves off the show position, hover-to-expand resumes.

        Guards against the reshow latch over-suppressing: a genuine Enter at a
        position different from the recorded show position must open the
        sublist and clear the latch.
        """
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.show()
        w1 = lw.add("Parent")
        w1.sublist.add("Child")

        # Latch armed at a position the cursor is no longer at (it has moved).
        lw._suppress_open_pos = QtCore.QPoint(-9999, -9999)
        QtWidgets.QApplication.sendEvent(w1, QtCore.QEvent(QtCore.QEvent.Enter))

        self.assertTrue(
            w1.sublist.isVisible(), "sublist should open on a genuine hover Enter"
        )
        self.assertIsNone(
            lw._suppress_open_pos, "latch should clear once the cursor has moved"
        )

    def test_clear_destroys_reparented_sublists_not_just_contents(self):
        """clear() must TEAR DOWN the reparented sublist widgets, not just clear
        their contents.

        Bug: sublists are reparented to the window (not children of the parent
        item), so deleting the item orphans the sublist on the window — a flyout
        open at clear() time keeps showing, and `_force_hide_all` can't reach it
        (it iterates this layout, which no longer holds the orphan). Lists with
        `refresh_on_show` call clear() on every show, so the stale flyout "is
        still visible when the marking menu is shown again". clear() now hides +
        deletes each sublist widget.
        """
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.show()
        w1 = lw.add("Parent")
        w1.sublist.add("Child")
        lw._handle_widget_enter_event(w1)  # open the flyout
        sub = w1.sublist
        # isHidden() is the explicit-show flag (what showChildren consults);
        # isVisible() is OS-dependent under offscreen QPA.
        self.assertFalse(sub.isHidden(), "precondition: the flyout is shown")

        destroyed = []
        sub.destroyed.connect(lambda *a: destroyed.append(1))

        lw.clear()

        # The flyout must be hidden immediately (no lingering stale flyout) ...
        self.assertTrue(sub.isHidden(), "clear() left the flyout shown")
        # ... and the orphaned sublist widget must be destroyed, not leaked.
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertTrue(
            destroyed, "clear() orphaned the reparented sublist (never deleted)"
        )

    def test_window_hide_collapses_sublists_even_without_list_hideevent(self):
        """All sublists must collapse when the parent WINDOW hides, even if this
        list's own ``hideEvent`` never fires.

        Bug: sublists are reparented to the window, so a *spontaneous* window
        hide (a DCC host reclaiming the overlay) clears the descendants' mapped
        state WITHOUT delivering a ``QHideEvent`` to the root list — so the
        old hideEvent-only collapse never ran, the sublists kept their
        explicit-show flag, and Qt's ``showChildren`` restored them on the next
        show ("still visible when the marking menu is shown again"). The root
        list now watches the window's own ``Hide`` event.

        Delivering a ``Hide`` to the window WITHOUT hiding the list isolates the
        window-watch: the list stays visible, yet the sublist must collapse.
        """
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.show()
        w1 = lw.add("Parent")
        w1.sublist.add("Child")  # non-empty so it is a real, showable sublist
        lw._handle_widget_enter_event(w1)
        self.assertTrue(w1.sublist.isVisible())

        # showEvent must have installed the window-hide watch.
        self.assertIs(
            lw._watched_window, self.window, "root list must watch its window"
        )

        # Deliver a Hide to the WINDOW only — the list/UI are left visible,
        # modelling the spontaneous hide where descendants get no QHideEvent.
        QtWidgets.QApplication.sendEvent(self.window, QtCore.QEvent(QtCore.QEvent.Hide))

        self.assertTrue(
            w1.sublist.isHidden(),
            "sublist must collapse when the parent window hides, regardless of "
            "whether the list's own hideEvent fired",
        )

    def test_nested_root_list_collapses_sublists_on_window_hide(self):
        """Sanity lock-in for the real marking-menu shape (window -> UI -> root
        list, sublists reparented to the window): a *programmatic* window hide
        collapses the whole nested sublist cascade and it stays collapsed across
        a reshow (Qt's showChildren must not restore it).

        NOTE: a programmatic ``self.window.hide()`` delivers a real ``QHideEvent``
        down to the descendant root list, so this collapse is performed by the
        existing ``hideEvent`` path — this test passes with or without the
        window-watch fix. The *spontaneous*-hide path the window-watch actually
        fixes is bound by ``test_window_hide_collapses_sublists_even_without_list_hideevent``.
        This test's distinct value is the nested-cascade + clean-reshow coverage.
        """
        self.window.show()
        ui = QtWidgets.QWidget(self.window)  # intermediate UI (≈ a submenu)
        ui.show()
        lw = ExpandableList(ui, fixed_item_height=21)
        self.track_widget(lw)
        lw.show()
        w1 = lw.add("Parent")
        c1 = w1.sublist.add("Child")
        c1.sublist.add("Grandchild")
        lw._handle_widget_enter_event(w1)
        w1.sublist._handle_widget_enter_event(c1)
        self.assertTrue(w1.sublist.isVisible())
        self.assertTrue(c1.sublist.isVisible())

        self.window.hide()

        self.assertTrue(w1.sublist.isHidden(), "sublist must collapse on window hide")
        self.assertTrue(
            c1.sublist.isHidden(), "nested sublist must collapse on window hide"
        )

        # Reshow must start clean — no sublist restored by showChildren.
        self.window.show()
        ui.show()
        lw.show()
        QtWidgets.QApplication.processEvents()
        self.assertTrue(w1.sublist.isHidden(), "sublist must stay collapsed on reshow")
        self.assertTrue(
            c1.sublist.isHidden(), "nested sublist must stay collapsed on reshow"
        )

    def test_window_watch_ignores_non_hide_events_and_never_consumes(self):
        """The window-watch branch of eventFilter is Hide-only and never consumes.

        It is handled FIRST so the watched window is never mistaken for a list
        item (its Enter/Leave/Release must not drive the sublist hover machinery)
        and it must return False so the DCC host still receives its own window
        events. A regression that consumed window events, or dropped the Hide
        guard (collapsing sublists on every window Enter/move), would otherwise
        pass silently.
        """
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.show()
        w1 = lw.add("Parent")
        w1.sublist.add("Child")
        lw._handle_widget_enter_event(w1)
        self.assertTrue(w1.sublist.isVisible())
        self.assertIs(lw._watched_window, self.window)

        # A non-Hide event on the watched window: not consumed, and it must NOT
        # collapse the sublist nor be treated as a hover item.
        consumed = lw.eventFilter(self.window, QtCore.QEvent(QtCore.QEvent.Enter))
        self.assertFalse(consumed, "a window event must never be consumed by the watch")
        self.assertTrue(
            w1.sublist.isVisible(),
            "a non-Hide window event must not collapse sublists or act as an item",
        )

        # Hide on the watched window collapses — but still must not consume.
        consumed_hide = lw.eventFilter(self.window, QtCore.QEvent(QtCore.QEvent.Hide))
        self.assertFalse(
            consumed_hide, "even the Hide must return False (never consume)"
        )
        self.assertTrue(
            w1.sublist.isHidden(), "Hide on the watched window must collapse"
        )

    def test_modal_dialog_blocking_window_collapses_sublists(self):
        """A modal dialog opening over the window must collapse open sublists.

        Bug: a modal dialog does NOT hide the window beneath it — Qt sends the
        window a ``WindowBlocked`` event, not a ``Hide``. The Hide-only watch
        therefore never fired, so a sublist open when the dialog opened kept its
        explicit-show flag and floated over (or was restored on the next show).
        The window-watch now collapses on ``WindowBlocked`` as well as ``Hide``.
        """
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.show()
        w1 = lw.add("Parent")
        w1.sublist.add("Child")
        lw._handle_widget_enter_event(w1)
        self.assertTrue(w1.sublist.isVisible())
        self.assertIs(lw._watched_window, self.window)

        # A modal dialog blocks the window (no Hide is delivered) — must collapse.
        consumed = lw.eventFilter(
            self.window, QtCore.QEvent(QtCore.QEvent.WindowBlocked)
        )
        self.assertFalse(
            consumed, "the WindowBlocked watch must never consume the event"
        )
        self.assertTrue(
            w1.sublist.isHidden(),
            "sublist must collapse when a modal dialog blocks the window",
        )

    def test_show_resets_any_sublist_that_survived_a_missed_hide(self):
        """Every show must start fully collapsed, even if the hide was missed.

        Bug: when a dialog masks the window's hide (the window's ``Hide`` never
        reaches the watch, e.g. a non-modal dialog path), a sublist open at hide
        time keeps its explicit-show flag and Qt's ``showChildren`` restores it
        on the next show — "sublists remain visible on next show". The root
        list's ``showEvent`` now force-collapses the whole hierarchy before
        re-displaying, so a missed hide can never leak an open sublist forward.

        Modelled by leaving a sublist explicitly shown (no hide delivered at
        all) and then re-showing the root list — the strongest form of "the
        hide was missed".
        """
        self.window.show()
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        lw.show()
        w1 = lw.add("Parent")
        w1.sublist.add("Child")
        lw._handle_widget_enter_event(w1)
        self.assertFalse(w1.sublist.isHidden(), "precondition: sublist is shown")

        # No hide event of any kind is delivered (the dialog-masked case).
        # Simply re-showing the root list must reset it to a collapsed state.
        lw.showEvent(QtGui.QShowEvent())
        self.assertTrue(
            w1.sublist.isHidden(),
            "showEvent must collapse any sublist that survived a missed hide",
        )

    @staticmethod
    def _build_nested_menu_shape():
        """Build the real marking-menu shape: a top-level window (the MarkingMenu
        stand-in), an intermediate uitk ``MainWindow`` submenu UI added as a
        NON-window child (exactly as ``MarkingMenu.addWidget`` does via
        ``setParent(self)`` with no window flag), and an ExpandableList inside it.
        Returns (top, ui, lw, w1).
        """
        top = QtWidgets.QMainWindow()  # marking-menu top-level stand-in
        top.show()
        ui = MainWindow(
            name="submenu_ui",
            switchboard_instance=_BareSwitchboard(),
            restore_window_size=False,
            ensure_on_screen=False,
        )
        # Mimic MarkingMenu.addWidget: setParent with NO window flag, so the UI
        # becomes a *non-window* child and ``list.window()`` resolves to ``top``.
        ui.setParent(top)
        ui.show()
        # Nest the list DEEP under the UI (central widget + layout), as the real
        # submenu UI does — verified live: Qt does NOT deliver a hideEvent to a
        # deep descendant when an ancestor hides (only to direct children), so
        # the list's own hideEvent can't be relied on to collapse the sublists.
        central = QtWidgets.QWidget(ui)
        inner = QtWidgets.QWidget(central)
        QtWidgets.QVBoxLayout(central).addWidget(inner)
        inner_lay = QtWidgets.QVBoxLayout(inner)
        central.show()
        inner.show()
        lw = ExpandableList(inner, fixed_item_height=21)
        inner_lay.addWidget(lw)
        lw.show()
        w1 = lw.add("Parent")
        w1.sublist.add("Child")
        return top, ui, lw, w1

    def test_submenu_ui_on_hide_collapses_reparented_sublists(self):
        """The containing non-window submenu UI's ``on_hide`` must collapse the
        reparented sublists — the live-Maya bug.

        The marking menu adds submenu UIs as *non-window* children
        (``setParent(self)``), so ``list.window()`` is the top-level menu window
        and the sublists reparent there. Switching submenus calls ``ui.hide()``
        on that non-window submenu UI while the top-level window stays up. In
        LIVE Maya the list's own ``hideEvent`` never fires (Qt delivers a
        hideEvent only to the widget being hidden, not to a deep descendant), so
        the sublist lingered. uitk ``MainWindow`` emits ``on_hide`` from its
        ``hideEvent``, and the list now hooks the nearest such ancestor.

        NOTE: a real ``ui.hide()`` can't reproduce this offscreen — offscreen Qt
        *does* deliver a child ``hideEvent`` that live Windows/Maya does not, so
        a real hide would collapse via ``hideEvent`` and mask the hook. This
        asserts the mechanism directly: emitting the UI's ``on_hide`` collapses
        the sublist.
        """
        top, ui, lw, w1 = self._build_nested_menu_shape()
        for w in (top, ui, lw):
            self.track_widget(w)

        # Faithful to live: the submenu UI is a NON-window child, so the sublists
        # reparent to the top-level window, which stays visible through nav.
        self.assertFalse(ui.isWindow(), "submenu UI must be a non-window child")
        self.assertIs(lw.window(), top, "sublists reparent to the top-level window")

        lw._handle_widget_enter_event(w1)
        self.assertFalse(w1.sublist.isHidden(), "precondition: sublist is open")

        # The list must hook the containing MainWindow's on_hide (the window-only
        # watch couldn't, since the submenu UI is not a window).
        self.assertIs(
            lw._hide_signal_source, ui, "must hook the containing MainWindow's on_hide"
        )

        # The UI hiding emits on_hide — the live nav path (the deep list gets no
        # hideEvent). Emit it directly (mapping-independent) → must collapse.
        ui.on_hide.emit()
        self.assertTrue(
            w1.sublist.isHidden(),
            "the submenu UI's on_hide must collapse the sublist",
        )

    def test_toplevel_window_hide_collapses_through_nonwindow_ui(self):
        """A dismiss of the top-level menu window collapses sublists even with a
        non-window submenu UI between the list and the window.

        Both hooks must be in place: the containing non-window MainWindow's
        ``on_hide`` (navigation) and the top-level window's ``Hide`` watch (full
        dismiss / spontaneous host reclaim / modal dialog).
        """
        top, ui, lw, w1 = self._build_nested_menu_shape()
        for w in (top, ui, lw):
            self.track_widget(w)

        lw._handle_widget_enter_event(w1)
        self.assertFalse(w1.sublist.isHidden(), "precondition: sublist is open")

        # Nav hook = the submenu UI; dismiss hook = the top-level window.
        self.assertIs(lw._hide_signal_source, ui, "on_hide hooked to the submenu UI")
        self.assertIs(lw._watched_window, top, "Hide watch on the top-level window")

        # Full dismiss: the top-level window gets the Hide.
        QtWidgets.QApplication.sendEvent(top, QtCore.QEvent(QtCore.QEvent.Hide))

        self.assertTrue(
            w1.sublist.isHidden(),
            "sublist must collapse on a top-level dismiss even with a non-window "
            "submenu UI between it and the list",
        )

    def test_window_watch_retargets_on_window_change(self):
        """``_watch_window_hide`` must re-target when the list moves to a new
        window — recording the new window AND ceasing to collapse on the old one.

        A regression that failed to reassign ``_watched_window`` (never
        re-watching the new window) or that left the old window driving collapse
        would break a re-parented marking menu, yet pass every other test.
        """
        win_a = QtWidgets.QMainWindow()
        self.track_widget(win_a)
        win_b = QtWidgets.QMainWindow()
        self.track_widget(win_b)

        lw = ExpandableList(win_a, fixed_item_height=21)
        self.track_widget(lw)
        lw._watch_window_hide()
        self.assertIs(lw._watched_window, win_a)

        lw.setParent(win_b)
        lw._watch_window_hide()
        self.assertIs(
            lw._watched_window, win_b, "watch must re-target to the new window"
        )

        # Idempotent: re-calling with the same window is a no-op.
        lw._watch_window_hide()
        self.assertIs(lw._watched_window, win_b)

        # The old (now unwatched) window must NOT collapse sublists; the new one
        # must. Assert on isHidden() — the explicit-show flag showChildren
        # consults — rather than isVisible(), which is OS-dependent offscreen.
        win_b.show()
        lw.show()
        QtWidgets.QApplication.processEvents()
        w1 = lw.add("Parent")
        w1.sublist.add("Child")
        lw._handle_widget_enter_event(w1)
        self.assertFalse(w1.sublist.isHidden(), "sublist should be explicitly shown")

        lw.eventFilter(win_a, QtCore.QEvent(QtCore.QEvent.Hide))
        self.assertFalse(
            w1.sublist.isHidden(),
            "the old, unwatched window must not collapse sublists",
        )
        lw.eventFilter(win_b, QtCore.QEvent(QtCore.QEvent.Hide))
        self.assertTrue(
            w1.sublist.isHidden(), "the new watched window must collapse sublists"
        )


class TestClearCancelsPendingHide(QtBaseTestCase):
    """clear() must cancel pending deferred-hide timers, and the hide callback
    must survive a deleted item — otherwise the timer fires on a deleted C++
    widget and raises an uncaught RuntimeError into the event loop (hit by
    refresh_on_show lists that clear() on every show mid-hover).
    """

    def setUp(self):
        super().setUp()
        self.window = QtWidgets.QMainWindow()
        self.track_widget(self.window)

    def test_clear_stops_pending_hide_timer(self):
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        item = lw.add("Button 1")

        # Arm a pending-hide timer the way _start_sublist_hide would.
        timer = QtCore.QTimer(lw)
        timer.setSingleShot(True)
        timer.start(10000)
        item._pending_hide_timer = timer
        self.assertTrue(timer.isActive())

        lw.clear()
        self.assertFalse(timer.isActive(), "clear() must stop the pending hide timer")

    def test_maybe_hide_sublist_survives_deleted_item(self):
        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)

        class _DeadItem:
            @property
            def sublist(self):
                raise RuntimeError("Internal C++ object already deleted")

        # A queued timer firing on a torn-down item must be a safe no-op.
        lw._maybe_hide_sublist(_DeadItem())

    def test_item_text_prefers_plain_text_of_icon_composited_label(self):
        """An icon-composited row (IconManager.set_label_icon) holds rich-text
        <img> markup in .text(); item_text() must still return the plain text
        so the codebase's text-based dispatch keeps working on iconified lists."""
        from uitk.managers.icon_manager import IconManager

        lw = ExpandableList(self.window, fixed_item_height=21)
        self.track_widget(lw)
        item = lw.add("textures", data="/proj/textures")
        IconManager.set_label_icon(item, "folder")

        self.assertIn("<img", item.text(), "row must carry the icon markup")
        self.assertEqual(
            lw.get_item_text(item),
            "textures",
            "item_text() must return plain text, not the <img> markup",
        )
        self.assertEqual(item.item_text(), "textures")
        # The rich text must not have flipped on QLabel mouse tracking — that
        # floods MouseTracking with button-less moves and collapses hover.
        self.assertFalse(
            item.hasMouseTracking(),
            "iconified row must keep mouse tracking off (hover-collapse regression)",
        )


class TestClickActivation(QtBaseTestCase):
    """Tests for the click activation mode (``click_menu`` preset).

    Click mode serves ExpandableLists embedded in standalone windows (e.g.
    tentacle main-menu panels): flyouts open on item click instead of hover,
    persist until dismissed, and are shown as frameless focusless Tool windows
    so they escape the host window's bounds.
    """

    def setUp(self):
        super().setUp()
        self.window = QtWidgets.QMainWindow()
        self.track_widget(self.window)

    def _release_event(self):
        return QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(2, 2),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )

    def _make_click_list(self, items=("Menu",), shown=True):
        """Build a click_menu list with one populated sublist per root item."""
        lw = ExpandableList(self.window, fixed_item_height=18)
        self.track_widget(lw)
        lw.apply_preset("click_menu")
        roots = []
        for text in items:
            root_item = lw.add(text)
            root_item.sublist.add([f"{text} A", f"{text} B"])
            roots.append(root_item)
        # A failing assertion mid-session must not leave the app-level
        # dismiss filter installed for later tests.
        self.addCleanup(lw._end_click_chain)
        if shown:
            self.window.show()
        return lw, roots

    def test_default_activation_is_hover(self):
        """Backward-compat lock: construction and every pre-existing preset
        must resolve to hover activation — click is strictly opt-in."""
        lw = ExpandableList(self.window)
        self.track_widget(lw)
        self.assertEqual(lw.activation, "hover")
        for name in (
            "expand_right",
            "expand_left",
            "expand_up",
            "expand_down",
            "expand_overlay",
            "expand_overlay_left",
            "expand_overlay_up_left",
        ):
            fresh = ExpandableList(self.window, fixed_item_height=18)
            self.track_widget(fresh)
            fresh.apply_preset(name)
            self.assertEqual(fresh.activation, "hover", name)

    def test_click_menu_preset_configuration(self):
        """click_menu = click activation, embedded root (popup flyouts +
        content-hugging Fixed vertical policy), drop-below root, fan-right
        children."""
        lw, _ = self._make_click_list(shown=False)
        self.assertEqual(lw.activation, "click")
        self.assertTrue(lw.embedded)
        self.assertEqual(lw.position, "bottom")
        self.assertEqual(lw._preset_child_position, "right")
        self.assertEqual(
            lw.sizePolicy().verticalPolicy(), QtWidgets.QSizePolicy.Fixed
        )

    def test_header_menu_preset_configuration(self):
        """header_menu = embedded root with HOVER activation, expanding right —
        the panel header-menu style: same feel as expand_right in the overlay,
        but flyouts must escape the small embedded host."""
        lw = ExpandableList(self.window, fixed_item_height=18)
        self.track_widget(lw)
        lw.apply_preset("header_menu")
        self.assertEqual(lw.activation, "hover")
        self.assertTrue(lw.embedded)
        self.assertEqual(lw.position, "right")
        self.assertEqual(lw._preset_child_position, "right")
        self.assertEqual(
            lw.sizePolicy().verticalPolicy(), QtWidgets.QSizePolicy.Fixed
        )

    def test_embedded_hover_flyout_is_popup_window(self):
        """An embedded HOVER list's flyouts get the same popup-window
        promotion as click mode — clipping is a property of where the root
        lives, not of how its sublists open."""
        lw = ExpandableList(self.window, fixed_item_height=18)
        self.track_widget(lw)
        lw.apply_preset("header_menu")
        root_item = lw.add("Menu")
        root_item.sublist.add("Child")
        self.window.show()
        lw._handle_widget_enter_event(root_item)
        sub = root_item.sublist
        self.assertTrue(sub.isWindow())
        self.assertTrue(sub.windowFlags() & QtCore.Qt.WindowDoesNotAcceptFocus)
        self.assertTrue(sub.isVisible())

    def test_embedded_hover_keeps_leave_driven_hides(self):
        """Embedded affects WHERE flyouts render, not hover semantics — the
        Leave grace-period collapse must still be scheduled."""
        lw = ExpandableList(self.window, fixed_item_height=18)
        self.track_widget(lw)
        lw.apply_preset("header_menu")
        root_item = lw.add("Menu")
        root_item.sublist.add("Child")
        self.window.show()
        lw._handle_widget_enter_event(root_item)
        lw.eventFilter(root_item, QtCore.QEvent(QtCore.QEvent.Leave))
        timer = getattr(root_item, "_pending_hide_timer", None)
        self.assertIsNotNone(timer)
        self.assertTrue(timer.isActive())

    def test_invalid_activation_raises(self):
        """An unknown activation value in a preset must fail loudly."""
        lw = ExpandableList(self.window)
        self.track_widget(lw)
        lw.PRESETS = {
            **ExpandableList.PRESETS,
            "bad": {
                "root_position": "bottom",
                "root_offset": (0, 0),
                "child_position": "right",
                "child_offset": (0, 0),
                "activation": "tap",
            },
        }
        with self.assertRaises(ValueError):
            lw.apply_preset("bad")

    def test_enter_does_not_open_when_chain_closed(self):
        """Click mode must not hover-open from idle — that is the whole point.

        Hover only navigates an already-open chain (menubar behavior)."""
        lw, (root_item,) = self._make_click_list()
        lw._suppress_open_pos = None  # disarm the synthetic-Enter latch
        lw.eventFilter(root_item, QtCore.QEvent(QtCore.QEvent.Enter))
        self.assertFalse(root_item.sublist.isVisible())
        self.assertFalse(lw._click_chain_open)

    def test_release_on_parent_item_opens_and_consumes(self):
        """A click (release) on an item with a populated sublist opens it,
        starts the session, and installs the app-level dismiss filter."""
        lw, (root_item,) = self._make_click_list()
        consumed = lw.eventFilter(root_item, self._release_event())
        self.assertTrue(consumed)
        self.assertTrue(root_item.sublist.isVisible())
        self.assertTrue(lw._click_chain_open)
        self.assertIsNotNone(lw._dismiss_filter)

    def test_second_release_toggles_closed_and_ends_session(self):
        lw, (root_item,) = self._make_click_list()
        lw.eventFilter(root_item, self._release_event())
        lw.eventFilter(root_item, self._release_event())
        self.assertTrue(root_item.sublist.isHidden())
        self.assertFalse(lw._click_chain_open)
        self.assertIsNone(lw._dismiss_filter)

    def test_leaf_release_emits_and_collapses_chain(self):
        """A leaf click activates exactly like hover mode (on_item_interacted,
        same signal contract slots rely on), then closes the whole menu."""
        lw, (root_item,) = self._make_click_list()
        emitted = []
        lw.on_item_interacted.connect(emitted.append)
        lw.eventFilter(root_item, self._release_event())
        leaf = root_item.sublist.get_items()[0]
        consumed = root_item.sublist.eventFilter(leaf, self._release_event())
        self.assertTrue(consumed)
        self.assertEqual(emitted, [leaf])
        self.assertTrue(root_item.sublist.isHidden())
        self.assertFalse(lw._click_chain_open)

    def test_hover_navigates_between_siblings_while_open(self):
        """Menubar behavior: once a chain is open, hovering a sibling root
        item switches the open flyout without another click."""
        lw, (item_a, item_b) = self._make_click_list(items=("One", "Two"))
        lw._suppress_open_pos = None
        lw.eventFilter(item_a, self._release_event())
        self.assertTrue(item_a.sublist.isVisible())
        lw.eventFilter(item_b, QtCore.QEvent(QtCore.QEvent.Enter))
        self.assertTrue(item_b.sublist.isVisible())
        self.assertTrue(item_a.sublist.isHidden())

    def test_click_flyout_is_focusless_frameless_tool_window(self):
        """Flyouts must escape the host window's bounds (top-level Tool) and
        must never take focus: a focus-accepting flyout would deactivate the
        host on click, which the click-mode WindowDeactivate watch reads as
        dismissal — the menu would close itself on first use. Also keeps a DCC
        host's focus untouched."""
        lw, (root_item,) = self._make_click_list()
        lw.eventFilter(root_item, self._release_event())
        sub = root_item.sublist
        self.assertTrue(sub.isWindow())
        flags = sub.windowFlags()
        self.assertTrue(flags & QtCore.Qt.Tool)
        self.assertTrue(flags & QtCore.Qt.FramelessWindowHint)
        self.assertTrue(flags & QtCore.Qt.WindowDoesNotAcceptFocus)
        self.assertTrue(sub.testAttribute(QtCore.Qt.WA_ShowWithoutActivating))

    def test_hover_flyout_stays_child_widget(self):
        """Hover mode keeps window-child sublists — the popup promotion is
        strictly a click-mode behavior."""
        lw = ExpandableList(self.window, fixed_item_height=18)
        self.track_widget(lw)
        lw.apply_preset("expand_right")
        root_item = lw.add("Menu")
        root_item.sublist.add("Child")
        self.window.show()
        lw._handle_widget_enter_event(root_item)
        self.assertFalse(root_item.sublist.isWindow())

    def test_click_flyout_positioned_below_trigger_in_global_coords(self):
        """A top-level flyout moves in GLOBAL coordinates; the parent-origin
        subtraction (correct for window-child sublists) must be skipped or the
        flyout lands offset by the window position."""
        lw, (root_item,) = self._make_click_list()
        lw.eventFilter(root_item, self._release_event())
        expected = root_item.mapToGlobal(QtCore.QPoint(0, root_item.height()))
        self.assertEqual(root_item.sublist.pos(), expected)

    def test_outside_press_collapses_without_consuming(self):
        """Standard menu dismissal: the outside click closes the menu AND
        still lands on whatever the user pressed."""
        lw, (root_item,) = self._make_click_list()
        lw.eventFilter(root_item, self._release_event())
        filt = lw._dismiss_filter
        lw._is_cursor_in_hierarchy = lambda *_: False  # cursor is elsewhere
        press = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(1, 1),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        consumed = filt.eventFilter(self.window, press)
        self.assertFalse(consumed, "the outside press must proceed to its target")
        self.assertTrue(root_item.sublist.isHidden())
        self.assertFalse(lw._click_chain_open)

    def test_escape_collapses_and_consumes(self):
        lw, (root_item,) = self._make_click_list()
        lw.eventFilter(root_item, self._release_event())
        filt = lw._dismiss_filter
        esc = QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier
        )
        consumed = filt.eventFilter(self.window, esc)
        self.assertTrue(consumed, "Escape is spent on dismissing the menu")
        self.assertTrue(root_item.sublist.isHidden())
        self.assertFalse(lw._click_chain_open)

    def test_window_hide_ends_session_and_removes_filter(self):
        """Hiding the host window must retire the session through the existing
        watched-window collapse path — no dangling app-level filter."""
        lw, (root_item,) = self._make_click_list()
        lw.eventFilter(root_item, self._release_event())
        self.window.hide()
        self.assertTrue(root_item.sublist.isHidden())
        self.assertFalse(lw._click_chain_open)
        self.assertIsNone(lw._dismiss_filter)

    def test_window_deactivate_dismisses_click_mode_only(self):
        """Deactivation = the user left for another window (or a DCC's native
        surface the app filter can't see) → dismiss. Hover mode must keep
        ignoring it (Blender overlays deactivate spuriously mid-chord)."""
        lw, (root_item,) = self._make_click_list()
        lw.eventFilter(root_item, self._release_event())
        deactivate = QtCore.QEvent(QtCore.QEvent.WindowDeactivate)
        lw.eventFilter(lw._watched_window, deactivate)
        self.assertTrue(root_item.sublist.isHidden())
        self.assertFalse(lw._click_chain_open)

        hover = ExpandableList(self.window, fixed_item_height=18)
        self.track_widget(hover)
        hover_item = hover.add("Menu")
        hover_item.sublist.add("Child")
        self.window.show()
        hover._handle_widget_enter_event(hover_item)
        self.assertTrue(hover_item.sublist.isVisible())
        hover.eventFilter(hover._watched_window, deactivate)
        self.assertTrue(
            hover_item.sublist.isVisible(),
            "hover mode must not collapse on WindowDeactivate",
        )

    def test_leave_schedules_no_hide_in_click_mode(self):
        """Click-opened menus persist until dismissed — never leave-driven."""
        lw, (root_item,) = self._make_click_list()
        lw.eventFilter(root_item, self._release_event())
        lw.eventFilter(root_item, QtCore.QEvent(QtCore.QEvent.Leave))
        timer = getattr(root_item, "_pending_hide_timer", None)
        self.assertTrue(timer is None or not timer.isActive())
        self.assertTrue(root_item.sublist.isVisible())

    def test_clear_ends_click_session(self):
        """A slot rebuilding the list mid-session (refresh_on_show pattern)
        must not strand the chain flag or the app-level filter."""
        lw, (root_item,) = self._make_click_list()
        lw.eventFilter(root_item, self._release_event())
        lw.clear()
        self.assertFalse(lw._click_chain_open)
        self.assertIsNone(lw._dismiss_filter)

    def test_ensure_sublist_on_screen_clamps_into_available_geometry(self):
        """A flyout pushed past the screen edge must be slid fully back into
        the screen's available area."""
        lw, (root_item,) = self._make_click_list()
        lw.eventFilter(root_item, self._release_event())
        sub = root_item.sublist
        screen = QtWidgets.QApplication.primaryScreen()
        available = screen.availableGeometry()
        sub.move(available.right() + 500, available.bottom() + 500)
        lw._ensure_sublist_on_screen(sub)
        self.assertTrue(
            available.contains(sub.frameGeometry()),
            f"flyout {sub.frameGeometry()} must be clamped into {available}",
        )


class TestEmbeddedHostMenuAdoption(QtBaseTestCase):
    """An embedded list hosted inside a hide-on-leave popup Menu.

    Bug: entering the flyout dismissed the header menu. Sublists are created
    at populate time, when the host Menu is not yet a top-level window, so
    ``self.window()`` resolved to the panel behind it — the flyout's QObject
    chain never reached the Menu, its family test missed the flyout, and the
    pointer entering it read as "left the menu". The converse also stranded
    an open flyout when the menu hid on its own. Fixed by adopting each
    flyout into the host menu's transient family as it opens.
    """

    def setUp(self):
        super().setUp()
        self.window = QtWidgets.QMainWindow()
        self.track_widget(self.window)

    def _menu_hosted_list(self):
        from uitk.widgets.menu import Menu

        host = QtWidgets.QPushButton(self.window)
        menu = self.track_widget(
            Menu(host, hide_on_leave=True, add_header=False, add_footer=False)
        )
        lw = menu.add(ExpandableList, setObjectName="list000")
        lw.fixed_item_height = 18
        lw.apply_preset("header_menu")
        root_item = lw.add("Menu")
        root_item.sublist.add(["Leaf A", "Leaf B"])
        self.window.show()
        menu.show()
        QtWidgets.QApplication.processEvents()
        lw._handle_widget_enter_event(root_item)
        # Park the flyout clearly outside the menu's own rect — the real
        # geometry (it fans right), and the condition the rect test fails on.
        root_item.sublist.move(
            menu.mapToGlobal(QtCore.QPoint(menu.width() + 40, 0))
        )
        QtWidgets.QApplication.processEvents()
        return menu, lw, root_item

    def test_pointer_over_flyout_keeps_host_menu_open(self):
        menu, lw, root_item = self._menu_hosted_list()
        sub = root_item.sublist
        point = sub.mapToGlobal(sub.rect().center())
        self.assertFalse(
            menu.rect().contains(menu.mapFromGlobal(point)),
            "precondition: the flyout must sit outside the menu's own rect",
        )
        self.assertTrue(
            menu._pointer_in_family(point),
            "the pointer on the flyout must count as inside the menu family",
        )

    def test_host_menu_hide_collapses_flyout(self):
        """The menu's transient cascade must take the flyout down with it —
        a top-level flyout is not a child widget and would otherwise be
        stranded on screen."""
        menu, lw, root_item = self._menu_hosted_list()
        menu.hide()
        QtWidgets.QApplication.processEvents()
        self.assertTrue(root_item.sublist.isHidden())

    def test_adoption_is_idempotent(self):
        menu, lw, root_item = self._menu_hosted_list()
        for _ in range(3):
            lw._handle_widget_enter_event(root_item)
        adopted = [c for c in menu._living_transients() if c is root_item.sublist]
        self.assertEqual(len(adopted), 1)

    def test_no_host_menu_is_harmless(self):
        """A list embedded in a plain window has nothing to adopt into; the
        walk must terminate at the top-level host, not raise or hang."""
        lw = ExpandableList(self.window, fixed_item_height=18)
        self.track_widget(lw)
        lw.apply_preset("header_menu")
        root_item = lw.add("Menu")
        root_item.sublist.add("Child")
        self.window.show()
        lw._handle_widget_enter_event(root_item)
        self.assertTrue(root_item.sublist.isVisible())


class TestEmbeddedSizing(QtBaseTestCase):
    """Geometry ownership for an embedded (layout-managed) list.

    Bug: on first interaction an embedded list rendered at its own sizeHint
    instead of the width its parent layout had allocated, "correcting itself"
    on the next layout pass — and the first flyout was mispositioned, because
    its placement is measured from the trigger row's edge, which inherits the
    list's width. Cause: ``showEvent`` unconditionally ran
    ``resize(sizeHint())``, clobbering an allocation the layout had already
    made. That resize now only runs when no parent layout owns the geometry.
    """

    def setUp(self):
        super().setUp()
        self.window = QtWidgets.QMainWindow()
        self.track_widget(self.window)

    def _menu_hosted_list(self):
        from uitk.widgets.menu import Menu

        host = QtWidgets.QPushButton(self.window)
        menu = self.track_widget(
            Menu(host, hide_on_leave=True, add_header=False, add_footer=False)
        )
        lw = menu.add(ExpandableList, setObjectName="list000")
        lw.fixed_item_height = 18
        lw.apply_preset("header_menu")
        root_item = lw.add("Assign: someLongMaterialName")
        root_item.sublist.add(["Leaf A", "Leaf B"])
        # A much wider sibling entry, so the menu's allocation and the list's
        # own sizeHint genuinely differ (otherwise the test proves nothing).
        menu.add(
            "QPushButton",
            setText="Reload Scene Textures ................",
            setObjectName="b013",
        )
        self.window.show()
        menu.show()
        return menu, lw, root_item

    def test_embedded_list_is_layout_managed(self):
        """The host nests its item layout (Menu: a QGridLayout inside the
        central widget's QVBoxLayout), so the check must search the layout
        tree — a top-level-only indexOf reads it as unmanaged."""
        _menu, lw, _root = self._menu_hosted_list()
        self.assertTrue(lw._is_layout_managed())

    def test_embedded_list_keeps_allocated_width_on_show(self):
        _menu, lw, root_item = self._menu_hosted_list()
        width_at_first_interaction = lw.width()
        row_at_first_interaction = root_item.width()
        QtWidgets.QApplication.processEvents()  # the settling layout pass
        self.assertEqual(
            width_at_first_interaction,
            lw.width(),
            "the list must not change width after the first layout pass",
        )
        self.assertEqual(row_at_first_interaction, root_item.width())

    def test_first_flyout_opens_at_settled_row_edge(self):
        """The mispositioning this bug produced: the flyout is placed from the
        trigger row's right edge, so a transient wrong row width moved it."""
        _menu, lw, root_item = self._menu_hosted_list()
        lw._handle_widget_enter_event(root_item)
        flyout_x = root_item.sublist.x()
        QtWidgets.QApplication.processEvents()
        expected = root_item.mapToGlobal(
            QtCore.QPoint(root_item.width(), 0)
        ).x()
        self.assertEqual(flyout_x, expected)

    def test_standalone_list_still_self_sizes_on_show(self):
        """Regression guard: the marking-menu overlay's roots are absolutely
        positioned in a layout-less central widget and DEPEND on the show-time
        self-resize."""
        central = QtWidgets.QWidget()
        self.window.setCentralWidget(central)
        lw = ExpandableList(central, fixed_item_height=18)
        self.track_widget(lw)
        lw.apply_preset("expand_up")
        lw.add("Recent Files").sublist.add(["a" * 40])
        self.window.show()
        self.assertFalse(lw._is_layout_managed())
        self.assertEqual(lw.width(), lw.sizeHint().width())


if __name__ == "__main__":
    import unittest

    unittest.main()
