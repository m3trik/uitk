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
        w3 = w2.sublist.add("Deep Item")

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
        sub_item = w1.sublist.add("Sub Label")

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
        QtWidgets.QApplication.sendEvent(
            self.window, QtCore.QEvent(QtCore.QEvent.Hide)
        )

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
        consumed_hide = lw.eventFilter(
            self.window, QtCore.QEvent(QtCore.QEvent.Hide)
        )
        self.assertFalse(consumed_hide, "even the Hide must return False (never consume)")
        self.assertTrue(w1.sublist.isHidden(), "Hide on the watched window must collapse")

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
        central.show(); inner.show()
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
        self.assertIs(lw._watched_window, win_b, "watch must re-target to the new window")

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
            w1.sublist.isHidden(), "the old, unwatched window must not collapse sublists"
        )
        lw.eventFilter(win_b, QtCore.QEvent(QtCore.QEvent.Hide))
        self.assertTrue(
            w1.sublist.isHidden(), "the new watched window must collapse sublists"
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
