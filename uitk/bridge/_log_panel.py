# !/usr/bin/python
# coding=utf-8
"""The log pane of a bridge panel: one part of :class:`~uitk.bridge.slots.BridgeSlotsBase`.

``txt000``: the bridge logger redirected into it, its ``action://`` links (the
DCC-agnostic ``open`` handled here, node actions delegated to handlers the DCC
packages register), and the lines logged once at open (``STARTUP_INFO``, the
docs link).
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Callable, List

import pythontk as ptk

if TYPE_CHECKING:  # annotation only; the facade imports this module
    from uitk.bridge.slots import BridgeSlotsBase


class _LogPane(object):
    """A bridge panel's log pane: logger redirect, link dispatch, startup lines.

    Its one piece of state is process-wide: the link-handler registry, a class
    attribute every bridge panel shares (each DCC registers its dispatcher
    once). The pane widget is the panel's ``ui.txt000``, so every method takes
    the panel -- any object with the names it reads -- and reaches the
    file-manager reveal through the panel's ``_open_in_file_manager``.
    """

    # --- Log-panel link dispatch (dependency inversion) --------------------
    # uitk handles the DCC-agnostic ``action://open`` link itself; the DCC-specific
    # actions (``select`` / ``reveal`` a node) are delegated to handlers the DCC
    # package registers via ``BridgeSlotsBase.register_log_link_handler``. This keeps
    # the dependency direction honest: uitk sits ABOVE pythontk and BELOW
    # mayatk/blendertk, so it must not import them — each DCC registers its
    # ``dispatch_log_link`` from its ``UiHandler.__init__`` instead. (Before this,
    # uitk hard-imported ``mayatk``, which both inverted the layering AND left node
    # links dead in a Blender session, where the mayatk import fails even though
    # ``blendertk.dispatch_log_link`` exists.)
    LINK_HANDLERS: List[Callable] = []

    @staticmethod
    def open_in_file_manager(path: str) -> None:
        """Reveal *path* in the platform's file manager; raises when it cannot.

        ``pythontk.FileUtils.open_explorer``: on Linux it starts ``xdg-open``
        without the host's loader overrides (Maya's ``LD_LIBRARY_PATH`` and Qt
        plug-in path), which crash or silence the file manager it starts.
        """
        if not ptk.FileUtils.open_explorer(path):
            raise OSError(f"the file manager could not open {path}")

    @staticmethod
    def register_link_handler(handler: Callable) -> None:
        if handler not in _LogPane.LINK_HANDLERS:
            _LogPane.LINK_HANDLERS.append(handler)

    # ------------------ Log panel -------------------------------------

    @staticmethod
    def redirect_log_to_panel(panel: "BridgeSlotsBase") -> None:
        """Pipe the bridge logger into ``txt000``, no-op if redirect unavailable."""
        try:
            handler_cls = panel.sb.registered_widgets.TextEditLogHandler
        except AttributeError:
            return
        bridge = panel.peek_bridge()
        if bridge is None:  # optional engine missing — the panel still opens
            return
        try:
            logger = bridge.logger
            logger.hide_logger_name(True)
            logger.set_text_handler(handler_cls)
            logger.setup_logging_redirect(panel.ui.txt000)
        except AttributeError:
            pass

    @staticmethod
    def on_log_link_clicked(panel: "BridgeSlotsBase", url) -> None:
        """Route ``action://`` URIs from the log panel to their handler.

        The ``open`` action (reveal a file/folder) is DCC-agnostic, so it is
        handled here with the cross-platform file-manager opener — this is what
        lets output-dir links work when a panel runs as a standalone external
        app (no Maya), which is the common case for the photogrammetry bridges.
        So is ``copy`` (``log_link("[copy]", "copy", text=...)``): its *text*
        goes on the clipboard, and the log says so.
        Node-based actions (``select`` / ``reveal``) are delegated to whatever
        handler the active DCC registered (see ``register_log_link_handler``),
        so uitk never imports a DCC package. Plain ``http(s)`` anchors (the
        docs link) never reach here -- :meth:`TextEditLogHandler.route_links`
        opens them in the browser off the same ``anchorClicked`` signal.
        """
        try:
            if url.scheme() == "action" and url.host() == "open":
                from urllib.parse import parse_qs

                params = parse_qs(url.query())
                path = params.get("path", [""])[0] or params.get("filepath", [""])[0]
                if path:
                    panel._open_in_file_manager(path)
                return
            if url.scheme() == "action" and url.host() == "copy":
                text = _LogPane.copy_link_text(url)
                if text:
                    panel.panel_log(f"Copied to the clipboard: {html.escape(text)}")
                return
        except Exception as e:  # noqa: BLE001
            panel.bridge.logger.error(f"Could not open link: {e}")
            return
        # Non-``open`` actions: hand off to the DCC-registered dispatchers
        # (dependency inversion — uitk never imports mayatk/blendertk). Try each
        # until one reports it handled the link; an empty registry (standalone
        # app, no DCC) simply no-ops. A misbehaving handler is logged but does
        # not shadow the others.
        for handler in _LogPane.LINK_HANDLERS:
            try:
                if handler(url, panel.bridge.logger):
                    return
            except Exception as e:  # noqa: BLE001
                panel.bridge.logger.error(f"Could not open link: {e}")

    @staticmethod
    def copy_link_text(url) -> str:
        """Put a ``copy`` link's *text* on the clipboard; return it (``""``: none).

        Read from the fully encoded URL -- the query exactly as ``log_link``
        urlencoded it, which ``parse_qs`` inverts. A decoded rendering is not
        that string: ``url.query()`` turns ``%23`` into ``#``, and
        ``QUrl.FullyDecoded`` turns ``%2B`` into ``+``, which ``parse_qs``
        then reads as a space.
        """
        from urllib.parse import parse_qs, urlsplit

        from qtpy import QtWidgets

        query = urlsplit(bytes(url.toEncoded()).decode("ascii")).query
        text = parse_qs(query).get("text", [""])[0]
        if text:
            QtWidgets.QApplication.clipboard().setText(text)
        return text

    @staticmethod
    def show_startup_info(panel: "BridgeSlotsBase") -> None:
        """Pipe the bridge's ``STARTUP_INFO`` into the log panel once.

        No-op when the bridge doesn't declare a ``STARTUP_INFO`` constant
        (marmoset / substance / rizom all rely on per-template docstrings
        and leave this empty). Preserved as an opt-in hook for future
        bridges that want a panel-level intro.
        """
        bridge = panel.peek_bridge()
        if bridge is None:  # optional engine missing — the panel still opens
            return
        info = getattr(bridge, "STARTUP_INFO", "")
        if info:
            panel.panel_log(info)

    @staticmethod
    def show_docs_link(panel: "BridgeSlotsBase") -> None:
        """Log the panel's documentation link once at startup (opt-in).

        ``"<DOCS_LABEL>: <a href=url>url</a>"`` -- the same closing line the
        compositor's intro panel carries -- rendered as a clickable anchor
        that :meth:`TextEditLogHandler.route_links` opens in the browser.
        Goes through ``panel_log`` so it shows even when the optional engine
        is missing, which is when a user most needs the docs. No-op when
        ``docs_url`` is empty (the default).
        """
        url = panel.docs_url()
        if not url:
            return
        panel.panel_log(f'{panel.DOCS_LABEL}: <a href="{url}">{url}</a>')
