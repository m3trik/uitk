# !/usr/bin/python
# coding=utf-8
"""HostExitGuard: a host's quit must leave shiboken nothing to fault on.

Maya quits through ``ExitProcess`` without finalizing Python, so the DLLs
detach with the interpreter still initialized, and two PySide 6.5 teardown
paths fault, each filing a crash dump (measured in fresh GUI Maya 2025.3
sessions; the guard's own docstring has the mechanisms):

1. shiboken's ``BindingManager`` destructor releases a C++-created *referred
   object* twice (``0001:00022460``): 5 dumps in 5 quits with every marking-menu
   page warmed, 0 in 8 with the guard; vanilla Maya 0 in 3.
2. PySide's ``_PySideInvalidatePtr`` tag, put on a static Qt object (the pixmap
   cache) that an application-wide event filter was handed, runs its deleter
   after shiboken's teardown (``0001:0002272C``): 3 in 3 quits after a 40 s
   filter hold.

The faults need the host's exit, so they are proven in a real Maya; here the
guard's contract is pinned: after ``release()`` no live wrapper keeps a
C++-created referred object and no noted object carries the tag, nothing else
is touched, and every application filter hands its objects to ``note()``.
"""

import unittest
from unittest import mock

from qtpy import QtCore, QtWidgets, shiboken

from conftest import QtBaseTestCase, run_launch_snippet
from uitk.managers.host_exit_guard import HostExitGuard

# Both run in a fresh interpreter: release() walks every wrapper in the
# process, and would invalidate the shared suite's objects too.
_REFERRED = """
from qtpy import QtGui, QtWidgets, shiboken
from uitk.managers.host_exit_guard import HostExitGuard

def ptrs(objs):
    return sorted(shiboken.getCppPointer(o)[0] for o in objs)

host = QtWidgets.QWidget()                # Python-created, like a uitk window
source = QtWidgets.QListWidget(host)
source.addItems(["a", "b"])
model = source.model()                    # C++-created (a Qt child of source)
view = QtWidgets.QListView(host)
view.setModel(model)                      # view keeps it as a referred object
host.winId()
handle = host.windowHandle()              # C++-created, kept by host
py_model = QtGui.QStandardItemModel()
view2 = QtWidgets.QListView(host)
view2.setModel(py_model)                  # a Python-created referred object
targets = [shiboken.getCppPointer(model)[0], shiboken.getCppPointer(handle)[0]]

before = ptrs(HostExitGuard._referred_cpp_objects())
released = HostExitGuard.release()
after = ptrs(HostExitGuard._referred_cpp_objects())
result = {
    "found_before": [t in before for t in targets],
    "released": released,
    "still_referred": [t in after for t in targets],
    "invalidated": [not shiboken.isValid(model), not shiboken.isValid(handle)],
    "untouched": [shiboken.isValid(o) for o in (host, source, view, view2, py_model)],
    "cpp_alive": [
        source.count(),
        shiboken.getCppPointer(view.model())[0] == targets[0],
        shiboken.getCppPointer(host.windowHandle())[0] == targets[1],
    ],
}
"""

_NOTED = """
from unittest import mock
from qtpy import QtCore, QtWidgets, shiboken
from uitk.managers.host_exit_guard import HostExitGuard
from uitk.widgets.popup.dismissal import OutsideClickDismissal

app = QtWidgets.QApplication.instance()
with mock.patch.object(shiboken, "createdByPython", new=lambda obj: False):
    armed = HostExitGuard.arm()           # stand in for a host-owned app

def tags(ptr):
    # wrapInstance does not tag; a converter-made wrapper would.
    obj = shiboken.wrapInstance(ptr, QtCore.QObject)
    return [bytes(n).decode() for n in obj.dynamicPropertyNames()]

source = QtWidgets.QListWidget()
ptr = shiboken.getCppPointer(source.model())[0]
filt = OutsideClickDismissal(lambda pos: True, lambda: None)
filt.attach()                             # a real application-wide filter
QtCore.QCoreApplication.postEvent(source.model(), QtCore.QEvent(QtCore.QEvent.User))
QtCore.QCoreApplication.postEvent(source, QtCore.QEvent(QtCore.QEvent.User))
app.processEvents()
filt.detach()
noted = getattr(app, HostExitGuard._NOTED_ATTR)
result = {
    "armed": armed,
    "noted": sorted(type(o).__name__ for o in noted),
    "tagged_before": "_PySideInvalidatePtr" in tags(ptr),
}
result["released"] = HostExitGuard.release()
result["tagged_after"] = "_PySideInvalidatePtr" in tags(ptr)
result["noted_after"] = len(noted)
result["cpp_alive"] = source.model().rowCount() == 0
"""


class ReleaseReferredTest(unittest.TestCase):
    """``release()`` over the referred-object shape (teardown path 1)."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_launch_snippet(_REFERRED, "ns['result']", host_app=True)

    def test_the_shape_is_found_before_the_release(self):
        """Both C++-created referred objects are the guard's targets (the
        precondition: without them the rest of this class is vacuous)."""
        self.assertEqual(self.result["found_before"], [True, True])

    def test_no_cpp_created_referred_object_is_left_to_release_twice(self):
        self.assertEqual(self.result["still_referred"], [False, False])
        self.assertEqual(self.result["invalidated"], [True, True])
        self.assertGreaterEqual(self.result["released"], 2)

    def test_children_and_python_created_objects_are_left_alone(self):
        self.assertEqual(self.result["untouched"], [True] * 5)

    def test_nothing_is_deleted(self):
        """The C++ objects live on; a getter wraps them afresh."""
        self.assertEqual(self.result["cpp_alive"], [2, True, True])


class ReleaseNotedTest(unittest.TestCase):
    """``note()`` + ``release()`` over PySide's per-object tag (teardown path 2)."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_launch_snippet(_NOTED, "ns['result']", host_app=True)

    def test_an_application_filter_notes_only_cpp_created_non_widgets(self):
        self.assertTrue(self.result["armed"])
        self.assertIn("QAbstractListModel", self.result["noted"])
        self.assertNotIn("QListWidget", self.result["noted"])  # a widget
        self.assertNotIn("QApplication", self.result["noted"])

    def test_the_noted_object_loses_its_tag(self):
        self.assertTrue(self.result["tagged_before"])  # else vacuous
        self.assertFalse(self.result["tagged_after"])
        self.assertGreaterEqual(self.result["released"], 1)
        self.assertEqual(self.result["noted_after"], 0)

    def test_nothing_is_deleted(self):
        self.assertTrue(self.result["cpp_alive"])


class ArmTest(QtBaseTestCase):
    """``arm()`` connects once, and only for an application Python did not create."""

    def setUp(self):
        super().setUp()
        self.app = QtWidgets.QApplication.instance()
        self.addCleanup(self._disarm)

    def _disarm(self):
        if getattr(self.app, HostExitGuard._NOTED_ATTR, None) is not None:
            delattr(self.app, HostExitGuard._NOTED_ATTR)
            try:
                self.app.aboutToQuit.disconnect(HostExitGuard.release)
            except (RuntimeError, TypeError):
                pass

    def _receivers(self):
        return self.app.receivers(QtCore.SIGNAL("aboutToQuit()"))

    def test_a_python_created_application_is_not_armed(self):
        """A standalone process finalizes Python itself; nothing to guard."""
        self.assertTrue(shiboken.createdByPython(self.app))
        before = self._receivers()
        self.assertFalse(HostExitGuard.arm())
        self.assertEqual(self._receivers(), before)

    def test_a_host_owned_application_is_armed_once(self):
        before = self._receivers()
        with mock.patch.object(shiboken, "createdByPython", new=lambda obj: False):
            self.assertTrue(HostExitGuard.arm())
            self.assertFalse(HostExitGuard.arm())
        self.assertEqual(self._receivers(), before + 1)

    def test_nothing_is_noted_while_disarmed(self):
        source = QtWidgets.QListWidget()
        self.track_widget(source)
        HostExitGuard.note(source.model())
        self.assertIsNone(getattr(self.app, HostExitGuard._NOTED_ATTR, None))

    def test_a_switchboard_arms_the_guard(self):
        from uitk import Switchboard

        calls = []
        with mock.patch.object(
            HostExitGuard, "arm", new=lambda *a, **k: calls.append(1)
        ):
            sb = Switchboard()
        self.addCleanup(sb.deleteLater)
        self.assertEqual(len(calls), 1)


class NoteCostTest(QtBaseTestCase):
    """``note()`` runs for every event an application filter sees, so keeping
    many live objects must not rescan the kept set for each new one."""

    def setUp(self):
        super().setUp()
        self.app = QtWidgets.QApplication.instance()
        self.addCleanup(ArmTest._disarm, self)
        self.host_owned = mock.patch.object(
            shiboken, "createdByPython", new=lambda obj: False
        )
        with self.host_owned:
            self.assertTrue(HostExitGuard.arm())

    def noted(self):
        return getattr(self.app, HostExitGuard._NOTED_ATTR)

    def test_noting_many_live_objects_prunes_in_batches(self):
        objs = [QtCore.QObject() for _ in range(3 * HostExitGuard._PRUNE_AT)]
        checks = []
        real = shiboken.isValid

        def counting(obj):
            checks.append(1)
            return real(obj)

        with self.host_owned, mock.patch.object(shiboken, "isValid", new=counting):
            for obj in objs:
                HostExitGuard.note(obj)
        self.assertEqual(len(self.noted()), len(objs))
        # One scan per _PRUNE_AT new objects, not one per object past it.
        self.assertLess(len(checks), 4 * len(objs))

    def test_the_dead_are_pruned(self):
        dead = [QtCore.QObject() for _ in range(HostExitGuard._PRUNE_AT)]
        live = [QtCore.QObject() for _ in range(HostExitGuard._PRUNE_AT)]
        with self.host_owned:
            for obj in dead:
                HostExitGuard.note(obj)
            for obj in dead:
                shiboken.delete(obj)
            for obj in live:
                HostExitGuard.note(obj)
        self.assertEqual({id(o) for o in self.noted()}, {id(o) for o in live})


class FilterWiringTest(QtBaseTestCase):
    """Every application-wide filter uitk installs hands its objects to ``note()``."""

    def _noted_by(self, filt):
        seen = []
        target = QtCore.QObject()
        with mock.patch.object(HostExitGuard, "note", new=seen.append):
            filt.eventFilter(target, QtCore.QEvent(QtCore.QEvent.User))
        return seen == [target]

    def test_the_global_shortcut_hold_filter(self):
        from uitk.managers.shortcut_manager import GlobalShortcut

        host = QtWidgets.QWidget()
        self.track_widget(host)
        self.assertTrue(self._noted_by(GlobalShortcut("F12", host)))

    def test_the_outside_click_dismissal(self):
        from uitk.widgets.popup.dismissal import OutsideClickDismissal

        self.assertTrue(
            self._noted_by(OutsideClickDismissal(lambda pos: True, lambda: None))
        )

    def test_the_busy_cursor_modal_filter(self):
        from uitk.managers.cursor_manager import _ModalSuspendFilter

        self.assertTrue(self._noted_by(_ModalSuspendFilter(self.app)))


if __name__ == "__main__":
    unittest.main()
