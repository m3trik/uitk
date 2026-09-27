# coding=utf-8
"""Searchable, tag-filtered launcher for any handler-exposed entry.

Listed entries come from :meth:`Switchboard.iter_handler_entries`, which
unifies every launchable handler's items (e.g. .ui files from UiHandler,
registered external apps from ExternalAppHandler). Nothing is loaded
until the user clicks Launch — the browser only inspects entry metadata.

The browser itself is no ``.ui`` — a plain ``EditorPanel``, consistent with
``StyleEditor`` and ``ColorMappingDialog``. Opened through ``sb.editors`` it
is also a row of its own (``EditorHandler``'s ``browser`` entry), so *Copy
launch code* can hand out a shelf button for the browser itself.

* :mod:`~uitk.widgets.editors.switchboard_browser._switchboard_browser` —
  :class:`SwitchboardBrowser`, the panel: search, tag chips, row actions and
  the header menu.
* :mod:`~uitk.widgets.editors.switchboard_browser.model` —
  :class:`SwitchboardBrowserModel`, one row per entry, nothing loaded.
* :mod:`~uitk.widgets.editors.switchboard_browser.filtering` — the show modes
  (``SHOW_*``), the search scopes (``SCOPE_*``) and the row filter proxy.
* :mod:`~uitk.widgets.editors.switchboard_browser.row_delegate` — how a row
  paints (name, tag and kind chips) and edits its tags inline.
* :mod:`~uitk.widgets.editors.switchboard_browser.launch` —
  :class:`LaunchOptions`, the window-persistence vocabulary
  (``PERSISTENCE_*``) and the launch / focus / close path through each
  entry's handler.

The names resolve lazily (``pythontk``'s ``lazy_exports``, CODE_STANDARD
section 4), so ``import uitk`` does not load the panel.
"""

from pythontk.core_utils.module_resolver import lazy_exports

lazy_exports(
    globals(),
    {
        "_switchboard_browser": "SwitchboardBrowser",
        "model": "SwitchboardBrowserModel",
        "filtering": (
            "SHOW_VISIBLE",
            "SHOW_HIDDEN",
            "SHOW_ALL",
            "SCOPE_NAME",
            "SCOPE_TAGS",
            "SCOPE_BOTH",
            "SCOPES",
            "SCOPE_ICONS",
        ),
        "launch": (
            "LaunchOptions",
            "PERSISTENCE_STICKY",
            "PERSISTENCE_TRANSIENT",
            "PERSISTENCE_CONTEXT",
            "PERSISTENCE_DEFAULT",
            "PERSISTENCE_CHOICES",
        ),
    },
)
