# !/usr/bin/python
# coding=utf-8
"""What a marking menu needs from the application hosting it: :class:`MarkingMenuHost`.

In a plain Qt application a marking menu needs nothing from its host: it parents to the
window it is given, binds its activation key with an application shortcut, reads the mouse
from Qt and shows its windows the Qt way. An application that is not purely Qt answers some
of those differently -- its event loop is native code, it owns the keyboard before Qt sees a
key, its windows are foreign to Qt -- and it says so by implementing this protocol and passing
it as ``MarkingMenu(host=...)``.

:class:`PureMarkingMenuHost` is the default: exactly the plain-Qt behavior. A host adapter
subclasses it and overrides only what differs.

Three members serve whoever *launches* a menu rather than the menu itself, because they come
before the menu exists: :meth:`MarkingMenuHost.start` makes Qt usable in the process,
:meth:`MarkingMenuHost.defer` schedules the build for when the host is ready for it, and
:meth:`MarkingMenuHost.live_menu` names a menu the host already drives. Every other member is
called by :class:`~uitk.widgets.marking_menu._marking_menu.MarkingMenu`.

Importable without a Qt binding (a launcher resolves its host before Qt is provisioned): the
binding is imported in the methods that use it.
"""

from typing import Any, Callable, Optional, Protocol, runtime_checkable


@runtime_checkable
class MarkingMenuHost(Protocol):
    """The answers a marking menu asks of the application that hosts it.

    Attributes:
        preload_only_from_host_loop: The host's own event loop is native code, so the
            menu's deferred warm-up advances only when called straight from it, never
            beneath a script that is pumping events (where building a page lands
            mid-script).
        shortcut_window_name: ``objectName()`` of the host's always-up main window, which
            owns application-scoped shortcuts (``ShortcutManager.register_host_window``);
            ``None`` for none.
        ui_handler: The ``UiHandler`` class the menu registers as its ``"ui"`` handler
            (how its standalone windows are shown and styled); ``None`` keeps uitk's.
    """

    preload_only_from_host_loop: bool
    shortcut_window_name: Optional[str]
    ui_handler: Optional[type]

    def start(self) -> None:
        """Make Qt usable in this process (a binding, a ``QApplication``, an event pump).

        For the launcher, before any widget exists."""

    def defer(self, fn: Callable[[], Any]) -> Any:
        """Run *fn* once the host is ready to build a UI; returns its result when run now.

        For the launcher: a host whose startup scripts run before its UI is up schedules
        *fn* on its own loop (and returns None)."""

    def live_menu(self) -> Any:
        """The menu this host already drives, or ``None``.

        For the launcher: a host that wires one menu per process into its own input
        (a keymap) hands that one back instead of a second build stacking over it."""

    def main_window(self) -> Any:
        """The window the menu parents to when none is given, or ``None``."""

    def mouse_buttons(self) -> Any:
        """The mouse buttons held now, as a ``Qt.MouseButtons`` mask."""

    def bind_activation_key(self, menu, key: str) -> None:
        """The host's own half of the activation binding, on *key* (``"Key_Z"``).

        Called once the menu is built and after every ``set_activation_key``. The menu
        always binds the key itself with an application shortcut on its parent; a host
        whose native loop consumes keystrokes before Qt binds it there too."""

    def adopt_window(self, widget) -> None:
        """Tie a top-level window to the host's own window (stacking, minimize).

        Called for the menu's overlay when it is built and on every show, and for each
        standalone window the menu shows."""

    def key_event(self, menu, event) -> None:
        """See each key press and release the menu receives, before the menu does."""

    def attach(self, menu) -> None:
        """Take a newly built menu: anything the host does once per menu."""


class PureMarkingMenuHost:
    """The plain-Qt answers: the menu behaves exactly as it does with no host.

    A host adapter subclasses this and overrides only what its application answers
    differently (``mtk.MayaMarkingMenuHost``, ``btk.BlenderMarkingMenuHost``).
    """

    preload_only_from_host_loop: bool = False
    shortcut_window_name: Optional[str] = None
    ui_handler: Optional[type] = None

    def start(self) -> None:
        """Nothing to stand up: a Qt application already runs its own loop."""

    def defer(self, fn: Callable[[], Any]) -> Any:
        """Run *fn* now and return its result."""
        return fn()

    def live_menu(self) -> Any:
        """None: every launch builds its menu (a new one retires the last)."""
        return None

    def main_window(self) -> Any:
        """No main window of its own: the menu parents to what it is given."""
        return None

    def mouse_buttons(self) -> Any:
        """Qt's own view of the mouse."""
        from qtpy import QtWidgets

        return QtWidgets.QApplication.mouseButtons()

    def bind_activation_key(self, menu, key: str) -> None:
        """Nothing more: the menu's application shortcut is the whole binding."""

    def adopt_window(self, widget) -> None:
        """Nothing to tie: Qt windows stack among themselves."""

    def key_event(self, menu, event) -> None:
        """No key the host handles itself."""

    def attach(self, menu) -> None:
        """Nothing to set up per menu."""


# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
