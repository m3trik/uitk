# !/usr/bin/python
# coding=utf-8
"""Keep a host application's exit from faulting in shiboken's static teardown.

A DCC that owns the ``QApplication`` (Maya) quits through ``ExitProcess``
without finalizing Python, so its DLLs detach while the interpreter still
counts as initialized. Two PySide 6.5 teardown paths then fault, and each
files a crash dump on quit that reads as a live-session crash in triage:

1. shiboken's ``BindingManager`` destructor ``destroy()``s every wrapper left
   in its map, in hash order, and ``destroy()`` leaves a wrapper's C++ pointer
   array NULL. A C++-created object that another wrapper keeps as a *referred
   object* -- the reference PySide takes for ``setModel``, ``setScreen``, the
   return of ``windowHandle()`` and the like -- stays in its referrer's list;
   when a later ``destroy()`` of the referrer's parent walks down to it,
   ``invalidate()`` releases it again and reads the NULL array
   (``shiboken6.abi3.dll`` ``0001:00022460``). ``invalidate()`` skips that
   release for a Python-created object.
2. Wrapping a C++-created ``QObject`` tags it for life with PySide's
   ``_PySideInvalidatePtr`` dynamic property, whose deleter releases the
   wrapper when the object dies. An application-wide event filter is handed
   every object that gets an event, some of them static -- Qt's pixmap cache --
   and a static one dies in its own DLL's teardown, after shiboken's: the
   deleter then reads shiboken's destroyed binding map (``0001:0002272C``).

:meth:`HostExitGuard.release` removes both preconditions on ``aboutToQuit``,
while the interpreter is healthy: it strips the tag from the objects the
application filters handed over (:meth:`note`), and invalidates every
C++-created object a reachable wrapper keeps as a referred object, so none is
left in the map for the teardown to destroy first. Nothing is deleted -- the
C++ objects live on and a later getter wraps them afresh; only a Python
reference kept to one of them goes stale. :meth:`HostExitGuard.arm` connects
it once per application, and only for an application Python did not create: a
standalone process finalizes Python itself, which empties the map before the
DLLs detach and turns the tag's deleter into a no-op.

Example
-------
>>> HostExitGuard.arm()  # Switchboard does this on construction
>>> HostExitGuard.note(obj)  # first line of an application-wide eventFilter
"""

import gc
import logging

from qtpy import QtCore, QtGui, QtWidgets

_log = logging.getLogger(__name__)


class HostExitGuard:
    """Clear, at quit, what shiboken's exit-time teardown would fault on.

    Class-only: its state is kept on the ``QApplication``.
    """

    #: Attribute holding the objects :meth:`note` kept; its presence marks the
    #: application armed. On the application rather than the class, so a module
    #: reload (tentacle's *Reload Scripts*) finds it and connects no second
    #: handler.
    _NOTED_ATTR = "_uitk_host_exit_guard_noted"
    #: PySide's per-object tag (see the module docstring, path 2).
    _PYSIDE_TAG = "_PySideInvalidatePtr"
    #: :meth:`note` drops the objects that died each time it has kept this
    #: many more (at every multiple of it): one scan per batch, not per object.
    _PRUNE_AT = 256

    @classmethod
    def arm(cls, app=None) -> bool:
        """Run :meth:`release` on *app*'s ``aboutToQuit``, when a host owns *app*.

        Idempotent, and never raises: it is called from constructors.

        Parameters:
            app: The application; default ``QApplication.instance()``.

        Returns:
            ``True`` when this call connected the handler; ``False`` when there
            is no application, Python created it (a standalone process), or it
            is armed already.
        """
        try:
            from qtpy import shiboken

            app = app or QtWidgets.QApplication.instance()
            if app is None or getattr(app, cls._NOTED_ATTR, None) is not None:
                return False
            if shiboken.createdByPython(app):
                return False
            app.aboutToQuit.connect(cls.release)
            setattr(app, cls._NOTED_ATTR, set())
            return True
        except Exception:  # a binding without the shiboken API: nothing to guard
            _log.debug("HostExitGuard.arm skipped", exc_info=True)
            return False

    @classmethod
    def note(cls, obj) -> None:
        """Keep *obj*, handed to an application-wide event filter, for :meth:`release`.

        Only a C++-created object that is not a widget, a window or the
        application itself is kept -- the static ones are among those -- and
        only while the guard is armed; otherwise this returns at once. Never
        raises: it runs for every event the filter sees.

        Parameters:
            obj: The ``obj`` argument of ``eventFilter``.
        """
        try:
            app = QtWidgets.QApplication.instance()
            noted = getattr(app, cls._NOTED_ATTR, None)
            if (
                noted is None
                or obj is app
                or obj in noted
                or isinstance(obj, (QtWidgets.QWidget, QtGui.QWindow))
            ):
                return
            from qtpy import shiboken

            if shiboken.createdByPython(obj):
                return
            if noted and len(noted) % cls._PRUNE_AT == 0:
                noted.difference_update([o for o in noted if not shiboken.isValid(o)])
            noted.add(obj)
        except Exception:
            _log.debug("HostExitGuard.note failed", exc_info=True)

    @classmethod
    def release(cls) -> int:
        """Strip the noted objects' tags and invalidate the C++-created referred objects.

        Returns:
            The number of objects stripped or invalidated. Never raises: it
            runs on the host's quit path.
        """
        try:
            from qtpy import shiboken

            count = 0
            noted = getattr(QtWidgets.QApplication.instance(), cls._NOTED_ATTR, None)
            for obj in list(noted or ()):
                if shiboken.isValid(obj):
                    # Removing the property runs its deleter now, while the
                    # binding map it reads still exists.
                    obj.setProperty(cls._PYSIDE_TAG, None)
                    count += 1
            if noted:
                noted.clear()
            targets = cls._referred_cpp_objects()
            for obj in targets:
                shiboken.invalidate(obj)
            return count + len(targets)
        except Exception:
            _log.debug("HostExitGuard.release failed", exc_info=True)
            return 0

    @staticmethod
    def _referred_cpp_objects() -> list:
        """The C++-created ``QObject``s that reachable wrappers keep as referred objects.

        A wrapper's ``tp_traverse`` visits its children and its referred
        objects, so ``gc.get_referents`` reaches both -- also through a wrapper
        whose C++ side is gone but which a parent still lists. A referent whose
        Qt parent is the wrapper is a child, and is skipped: the teardown takes
        a child off its parent's list before destroying it. So is a non-QObject
        referent (a layout or tree item is a child) and a Python-created one.
        """
        from qtpy import shiboken

        valid = shiboken.getAllValidWrappers()
        valid_ids = {id(w) for w in valid}
        seen = {}
        stack = list(valid)
        while stack:
            node = stack.pop()
            if id(node) in seen:
                continue
            seen[id(node)] = node
            stack.extend(
                r
                for r in gc.get_referents(node)
                if isinstance(r, shiboken.Object) and id(r) not in seen
            )
        found = {}
        for node in seen.values():
            for ref in gc.get_referents(node):
                if (
                    id(ref) in found
                    or id(ref) not in valid_ids
                    or not isinstance(ref, QtCore.QObject)
                    or shiboken.createdByPython(ref)
                ):
                    continue
                try:
                    if ref.parent() is node:
                        continue
                except RuntimeError:
                    continue
                found[id(ref)] = ref
        return list(found.values())
