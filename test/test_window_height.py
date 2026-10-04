# !/usr/bin/python
# coding=utf-8
"""How a window follows the height of what it is holding."""

import unittest

from qtpy import QtWidgets

from conftest import QtBaseTestCase, setup_qt_application

setup_qt_application()


class _RecordingLayout(QtWidgets.QVBoxLayout):
    """Names itself in a shared log every time it is activated."""

    def __init__(self, name, log):
        super().__init__()
        self._name = name
        self._log = log

    def activate(self):
        self._log.append(self._name)
        return super().activate()


class WindowHeightTestCase(QtBaseTestCase):
    def _window(self, rows=5, row_height=40, plain=False, growable=False):
        """A window whose content needs *rows* x *row_height* pixels.

        *plain* builds a bare ``QWidget`` host -- what a tool gets when its
        fields live in a popup menu or a dialog rather than a ``MainWindow``.

        *growable* adds a child that can use extra height. Without one the
        content maximum equals the content minimum, so every path here snaps
        to the content and extra height is dead space by definition -- which
        is correct, and is not the case a preserved delta is about.
        """
        host = QtWidgets.QWidget() if plain else QtWidgets.QMainWindow()
        central = QtWidgets.QWidget()
        box = QtWidgets.QVBoxLayout(central)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        for index in range(rows):
            row = QtWidgets.QLabel(f"row{index}", central)
            row.setFixedHeight(row_height)
            box.addWidget(row)
        if growable:
            filler = QtWidgets.QTextEdit(central)
            filler.setSizePolicy(
                QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding
            )
            box.addWidget(filler)
        if plain:
            outer = QtWidgets.QVBoxLayout(host)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(central)
        else:
            host.setCentralWidget(central)
        self.track_widget(host)
        host.show()
        QtWidgets.QApplication.processEvents()
        return host, central


class TestAdjustBy(WindowHeightTestCase):
    """The shape that PRESERVES height the user added by hand."""

    def test_a_delta_moves_the_height_and_leaves_the_width(self):
        from uitk import WindowHeight

        win, _central = self._window(growable=True)
        win.resize(300, 400)
        QtWidgets.QApplication.processEvents()

        WindowHeight.adjust_by(win, -60, baseline=400)
        QtWidgets.QApplication.processEvents()

        self.assertEqual(win.width(), 300)
        self.assertEqual(win.height(), 340)

    def test_zero_is_a_no_op(self):
        from uitk import WindowHeight

        win, _central = self._window()
        win.resize(300, 400)
        QtWidgets.QApplication.processEvents()

        WindowHeight.adjust_by(win, 0)

        self.assertEqual(win.height(), 400)

    def test_the_baseline_wins_over_the_current_height(self):
        """Qt may have auto-grown the window to meet its new layout minimum
        before the call lands, and that growth IS the caller's delta."""
        from uitk import WindowHeight

        win, _central = self._window(growable=True)
        win.resize(300, 500)
        QtWidgets.QApplication.processEvents()

        WindowHeight.adjust_by(win, 40, baseline=300)
        QtWidgets.QApplication.processEvents()

        self.assertEqual(win.height(), 340, "measured from the baseline, not 500")

    def test_a_shrink_stops_at_the_content_floor(self):
        from uitk import WindowHeight
        from uitk.widgets.mixins.size_grip import SizeGripMixin

        win, central = self._window()
        floor = SizeGripMixin.content_min_height(win)

        WindowHeight.adjust_by(win, -10_000, baseline=win.height())
        QtWidgets.QApplication.processEvents()

        self.assertGreaterEqual(win.height(), floor)
        self.assertGreaterEqual(win.height(), central.minimumSizeHint().height())


class TestFitToContent(WindowHeightTestCase):
    """The shape that SNAPS, for a change no one measured in pixels."""

    def test_it_trims_a_window_taller_than_its_content(self):
        from uitk import WindowHeight

        win, central = self._window(rows=3)
        win.resize(300, 600)
        QtWidgets.QApplication.processEvents()

        WindowHeight.fit_to_content(win)
        QtWidgets.QApplication.processEvents()

        self.assertEqual(win.width(), 300)
        self.assertLess(win.height(), 600)
        self.assertGreaterEqual(win.height(), central.minimumSizeHint().height())

    def test_a_window_whose_layout_states_no_height_is_left_alone(self):
        """A marking-menu submenu positions its content absolutely in a
        layout-less central: fitting it to a hint of zero collapsed it to a
        sliver with the real content rendered detached."""
        from uitk import WindowHeight

        win = self.track_widget(QtWidgets.QMainWindow())
        central = QtWidgets.QWidget()
        win.setCentralWidget(central)
        win.resize(300, 220)
        win.show()
        QtWidgets.QApplication.processEvents()
        before = win.height()

        WindowHeight.fit_to_content(win)
        QtWidgets.QApplication.processEvents()

        self.assertEqual(win.height(), before)


class TestActivateLayouts(WindowHeightTestCase):
    """Leaves-up, for EVERY host -- not only for a ``MainWindow``.

    The rule used to live on ``MainWindow`` with a hand-kept copy in
    ``CollapsableGroup`` for other hosts, and the copy activated the window's
    own layout first and then walked children parent-first: the order the
    original's comment says hands back the PREVIOUS content's height.
    """

    def _nested(self, depth=4):
        log = []
        host = self.track_widget(QtWidgets.QWidget())
        host.setLayout(_RecordingLayout("level0", log))
        parent = host
        for level in range(1, depth):
            nested = QtWidgets.QWidget(parent)
            nested.setLayout(_RecordingLayout(f"level{level}", log))
            parent.layout().addWidget(nested)
            parent = nested
        leaf = QtWidgets.QLabel("leaf", parent)
        leaf.setFixedHeight(20)
        parent.layout().addWidget(leaf)
        host.show()
        QtWidgets.QApplication.processEvents()
        return host, log

    def test_a_plain_host_activates_deeper_layouts_first(self):
        from uitk import WindowHeight

        host, log = self._nested()
        log.clear()

        WindowHeight.activate_layouts(host)

        seen = {}
        for index, name in enumerate(log):
            seen.setdefault(name, index)
        ordered = [name for name, _ in sorted(seen.items(), key=lambda kv: kv[1])]
        self.assertTrue(ordered, "no layout was activated at all")
        self.assertEqual(
            ordered,
            sorted(ordered, reverse=True),
            f"layouts activated parent-first: {ordered}",
        )

    def test_depth_counts_widgets_up_to_the_window(self):
        from uitk import WindowHeight

        host, _log = self._nested(depth=3)
        inner = host.findChild(QtWidgets.QWidget)
        self.assertEqual(WindowHeight._depth(host, host.layout()), 0)
        self.assertGreater(
            WindowHeight._depth(host, inner.layout()),
            WindowHeight._depth(host, host.layout()),
        )


class TestFitHost(WindowHeightTestCase):
    """Given a widget, fit whatever window it is in."""

    def test_a_host_that_states_its_own_fit_is_asked_in_its_own_terms(self):
        """A panel may fit differently; asking it by name keeps that."""
        from uitk import WindowHeight

        win, central = self._window()
        calls = []
        win.fit_height_to_content = lambda: calls.append(1)

        WindowHeight.fit_host(central.findChild(QtWidgets.QLabel))

        self.assertEqual(calls, [1])

    def test_anything_else_is_asked_to_adjust_its_size(self):
        """What a popup menu does, and the reason a tool needs no fit of its
        own: the same call works for a panel and for a menu."""
        from uitk import WindowHeight

        host, _central = self._window(rows=2, plain=True)
        host.resize(300, 500)
        QtWidgets.QApplication.processEvents()

        WindowHeight.fit_host(host.findChild(QtWidgets.QLabel))
        QtWidgets.QApplication.processEvents()

        self.assertLess(host.height(), 500)

    def test_no_widget_is_no_error(self):
        """A registry that gates nothing has nothing to resolve a window from."""
        from uitk import WindowHeight

        WindowHeight.fit_host(None)


class TestFitHostLater(WindowHeightTestCase):
    """The deferred form, for a widget that has just shown or hidden its parts."""

    def _recording(self, shown=True):
        win, central = self._window()
        calls = []
        win.fit_height_to_content = lambda: calls.append(1)
        if not shown:
            win.hide()
        return central.findChild(QtWidgets.QLabel), calls

    @staticmethod
    def _turn():
        from qtpy import QtCore

        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(30, loop.quit)
        loop.exec_() if hasattr(loop, "exec_") else loop.exec()

    def test_it_fits_on_the_next_turn_not_now(self):
        """A container asked while it is still hiding children measures the
        layout it is leaving."""
        from uitk import WindowHeight

        row, calls = self._recording()
        WindowHeight.fit_host_later(row)
        self.assertEqual(calls, [], "not synchronously")
        self._turn()
        self.assertEqual(calls, [1])

    def test_calls_in_one_turn_fit_once(self):
        from uitk import WindowHeight

        row, calls = self._recording()
        for _ in range(3):
            WindowHeight.fit_host_later(row)
        self._turn()
        self.assertEqual(calls, [1])
        WindowHeight.fit_host_later(row)
        self._turn()
        self.assertEqual(calls, [1, 1], "the next turn may fit again")

    def test_a_window_not_on_screen_is_left_to_its_show(self):
        """A fit queued during a build lands after the show and overrides the
        size that show restored."""
        from uitk import WindowHeight

        row, calls = self._recording(shown=False)
        WindowHeight.fit_host_later(row)
        self._turn()
        self.assertEqual(calls, [])

    def test_no_widget_is_no_error(self):
        from uitk import WindowHeight

        WindowHeight.fit_host_later(None)

    def _main_window(self):
        """A uitk ``MainWindow`` -- it fits itself on its FIRST show only."""
        from uitk.switchboard import Switchboard
        from uitk.widgets.mainWindow import MainWindow

        central = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(central).addWidget(QtWidgets.QLabel("row", central))
        win = MainWindow(
            "fit_on_show_probe",
            Switchboard(log_level="WARNING"),
            central_widget=central,
            log_level="WARNING",
        )
        self.track_widget(win)
        calls = []
        win.fit_height_to_content = lambda: calls.append(1)
        return win, central.findChild(QtWidgets.QLabel), calls

    def test_a_window_hidden_since_a_show_fits_when_shown_again(self):
        """Content changed while a once-shown window was hidden (a mode switched
        from elsewhere) came back at the height of what it had left: the
        window fits itself on its first show only.
        Fixed: 2026-10-04
        """
        from uitk import WindowHeight

        win, row, calls = self._main_window()
        win.show()
        self._turn()
        win.hide()
        before = len(calls)
        for _ in range(2):
            WindowHeight.fit_host_later(row)
        self._turn()
        self.assertEqual(len(calls), before, "not while hidden")
        win.show()
        self._turn()
        self.assertEqual(len(calls), before + 1, "on the show it comes back with")
        win.hide()
        win.show()
        self._turn()
        self.assertEqual(len(calls), before + 1, "once")

    def test_a_window_never_shown_is_left_to_its_first_show(self):
        """Its first show sizes it (fitting or restoring); a fit queued during
        the build would land after that show and override the restore."""
        from uitk import WindowHeight

        win, row, calls = self._main_window()
        WindowHeight.fit_host_later(row)
        win.show()
        shown = len(calls)
        self._turn()
        self.assertEqual(len(calls), shown)


if __name__ == "__main__":
    unittest.main()
