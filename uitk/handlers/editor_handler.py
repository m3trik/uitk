# !/usr/bin/python
# coding=utf-8
"""Launchable-contract front end for the Switchboard's bundled editors.

Exposes every ``sb.editors`` window -- the UI Browser, the Style, Shortcut
and Preset editors -- as :class:`HandlerEntry` rows, so the unified launcher
lists them beside the registered UIs: the UI Browser finds itself there, and
its *Copy launch code* action works on it like on any tool.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Iterable, Optional

from uitk.handlers.base_handler import BaseHandler
from uitk.handlers.handler_entry import HandlerEntry

if TYPE_CHECKING:  # pragma: no cover
    from uitk.switchboard import Switchboard


class EditorHandler(BaseHandler):
    """Lists the bundled editors (``sb.editors``) in the unified launcher.

    One entry per editor, named by its registry key -- the same name
    ``sb.editors.show(name)`` takes. Every Switchboard registers one as
    ``handlers.editor``; ``Switchboard(handlers={"editor": None})`` opts out.
    """

    CONFIG_BRANCH = "editor"
    KIND = "editor"

    def __init__(
        self,
        switchboard: "Switchboard",
        log_level: str = "WARNING",
        **_kwargs,
    ):
        super().__init__(switchboard=switchboard, log_level=log_level)
        # Row refresh is wired when an editor is BUILT, so one opened by any
        # path (a slot's ``sb.editors.show``, a menu) still updates its row.
        editors = self.sb.editors
        for name in editors.names():
            editors.add_post_build_hook(
                name, functools.partial(self._wire_widget_visibility, name=name)
            )
            built = editors.peek(name)
            if built is not None:
                self._wire_widget_visibility(built, name)

    # ── Launchable contract ──────────────────────────────────────────────

    def entries(self) -> Iterable[HandlerEntry]:
        """Yield one :class:`HandlerEntry` per bundled editor (no tag store).

        An editor whose name another handler already lists -- a registered
        ``presets.ui``, say -- is left out: the launcher keeps one row per
        name, and the host's own entry outranks a bundled editor.
        """
        taken = self._names_listed_elsewhere()
        for name in self.sb.editors.names():
            if name not in taken:
                yield HandlerEntry(name=name, kind=self.KIND, handler=self)

    def _names_listed_elsewhere(self) -> set:
        """Entry names the switchboard's OTHER launchable handlers yield."""
        names = set()
        for handler in getattr(self.sb, "_launchable_handlers", {}).values():
            if handler is self:
                continue
            try:
                names.update(entry.name for entry in handler.entries())
            except Exception:  # noqa: BLE001 -- iter_handler_entries reports it
                continue
        return names

    def launch(self, name: str, **_options):
        """Show editor *name*. Editors own their chrome: style options are ignored."""
        editor = self.sb.editors.show(name)
        self._notify_entries_changed(name)
        return editor

    def focus(self, name: str) -> None:
        """Raise editor *name* when it is already built. Optional contract method."""
        if self.sb.editors.peek(name) is not None:
            self.sb.editors.show(name)

    def close(self, name: str) -> None:
        editor = self.sb.editors.peek(name)
        if editor is not None:
            editor.hide()
        self._notify_entries_changed(name)

    def is_visible(self, name: str) -> bool:
        editor = self.sb.editors.peek(name)
        try:
            return bool(editor is not None and editor.isVisible())
        except RuntimeError:  # the editor's C++ side is already gone
            return False

    def launch_code(self, name: str, **_options) -> Optional[str]:
        """Python that opens editor *name* standalone. Optional contract method.

        An editor needs its switchboard, so the snippet stands the ``"ui"``
        handler up the way a fresh session would
        (:meth:`UiHandler.bootstrap_code`) -- carrying every registered source
        when the editor lists the registry (the UI Browser) -- and shows the
        editor on it. Under Maya that is ``MayaUiHandler.instance()``: the
        live tentacle switchboard when tentacle runs, mayatk's own otherwise.

        Returns:
            None for an unknown editor, or when the ``"ui"`` handler cannot
            spell its own bootstrap.
        """
        editors = self.sb.editors
        if name not in editors.names():
            return None
        bootstrap = getattr(
            getattr(self.sb.handlers, "ui", None), "bootstrap_code", None
        )
        boot = (
            bootstrap(sources=editors.requires_switchboard(name))
            if callable(bootstrap)
            else None
        )
        if boot is None:
            return None
        imports, body, handler = boot
        body.append(f"{handler}.sb.editors.show({name!r})")
        return self._launch_script(name, imports, body, app=f"{handler}.sb.app")
