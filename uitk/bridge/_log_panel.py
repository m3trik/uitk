# !/usr/bin/python
# coding=utf-8
"""The log pane of a bridge panel: one part of :class:`~uitk.bridge.slots.BridgeSlotsBase`.

``txt000``: the bridge logger redirected into it, its ``action://`` links (the
DCC-agnostic ``open`` handled here, node actions delegated to handlers the DCC
packages register), and the lines logged once at open (``STARTUP_INFO``, the
docs link).
"""

from __future__ import annotations

from typing import Callable, List

import pythontk as ptk


class _LogPanelMixin(object):
    """The log pane: logger redirect, link dispatch, startup lines.

    The link-handler registry is a class attr, so every bridge panel in the
    process shares one (each DCC registers its dispatcher once).
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
    _LOG_LINK_HANDLERS: List[Callable] = []

    @staticmethod
    def _open_in_file_manager(path: str) -> None:
        """Reveal *path* in the platform's file manager; raises when it cannot.

        ``pythontk.FileUtils.open_explorer``: on Linux it starts ``xdg-open``
        without the host's loader overrides (Maya's ``LD_LIBRARY_PATH`` and Qt
        plug-in path), which crash or silence the file manager it starts.
        """
        if not ptk.FileUtils.open_explorer(path):
            raise OSError(f"the file manager could not open {path}")

    # Where the panel's detailed documentation lives (a web URL). When set,
    # :meth:`_show_docs_link` logs ``"<DOCS_LABEL>: <url>"`` into the log pane
    # once at startup as a clickable anchor -- the header help is a tooltip,
    # so it can't carry a clickable link; the log pane can. Empty = no line.
    # Subclasses set these (or override :meth:`docs_url` to compute the URL).
    DOCS_URL: str = ""
    DOCS_LABEL: str = "Detailed docs"

    @staticmethod
    def register_log_link_handler(handler: Callable) -> None:
        """Register a ``handler(url, logger) -> bool`` for non-``open`` log-panel
        ``action://`` links (returns True when it handled the link).

        DCC packages (mayatk / blendertk) call this from their ``UiHandler.__init__``
        so their node-dispatch runs without uitk importing them. Handlers are tried
        in registration order until one returns True. Idempotent — re-registering
        the same callable is a no-op.
        """
        if handler not in _LogPanelMixin._LOG_LINK_HANDLERS:
            _LogPanelMixin._LOG_LINK_HANDLERS.append(handler)

    # ------------------ Log panel -------------------------------------

    def _redirect_log_to_panel(self) -> None:
        """Pipe the bridge logger into ``txt000``, no-op if redirect unavailable."""
        try:
            handler_cls = self.sb.registered_widgets.TextEditLogHandler
        except AttributeError:
            return
        bridge = self.peek_bridge()
        if bridge is None:  # optional engine missing — the panel still opens
            return
        try:
            logger = bridge.logger
            logger.hide_logger_name(True)
            logger.set_text_handler(handler_cls)
            logger.setup_logging_redirect(self.ui.txt000)
        except AttributeError:
            pass

    def _on_log_link_clicked(self, url) -> None:
        """Route ``action://`` URIs from the log panel to their handler.

        The ``open`` action (reveal a file/folder) is DCC-agnostic, so it is
        handled here with the cross-platform file-manager opener — this is what
        lets output-dir links work when a panel runs as a standalone external
        app (no Maya), which is the common case for the photogrammetry bridges.
        Node-based actions (``select`` / ``reveal``) are delegated to whatever
        handler the active DCC registered (see :func:`register_log_link_handler`),
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
                    self._open_in_file_manager(path)
                return
        except Exception as e:  # noqa: BLE001
            self.bridge.logger.error(f"Could not open link: {e}")
            return
        # Non-``open`` actions: hand off to the DCC-registered dispatchers
        # (dependency inversion — uitk never imports mayatk/blendertk). Try each
        # until one reports it handled the link; an empty registry (standalone
        # app, no DCC) simply no-ops. A misbehaving handler is logged but does
        # not shadow the others.
        for handler in _LogPanelMixin._LOG_LINK_HANDLERS:
            try:
                if handler(url, self.bridge.logger):
                    return
            except Exception as e:  # noqa: BLE001
                self.bridge.logger.error(f"Could not open link: {e}")

    def _show_startup_info(self) -> None:
        """Pipe the bridge's ``STARTUP_INFO`` into the log panel once.

        No-op when the bridge doesn't declare a ``STARTUP_INFO`` constant
        (marmoset / substance / rizom all rely on per-template docstrings
        and leave this empty). Preserved as an opt-in hook for future
        bridges that want a panel-level intro.
        """
        bridge = self.peek_bridge()
        if bridge is None:  # optional engine missing — the panel still opens
            return
        info = getattr(bridge, "STARTUP_INFO", "")
        if info:
            self.panel_log(info)

    def _show_docs_link(self) -> None:
        """Log the panel's documentation link once at startup (opt-in).

        ``"<DOCS_LABEL>: <a href=url>url</a>"`` -- the same closing line the
        compositor's intro panel carries -- rendered as a clickable anchor
        that :meth:`TextEditLogHandler.route_links` opens in the browser.
        Goes through :meth:`panel_log` so it shows even when the optional
        engine is missing, which is when a user most needs the docs. No-op
        when :meth:`docs_url` is empty (the default).
        """
        url = self.docs_url()
        if not url:
            return
        self.panel_log(f'{self.DOCS_LABEL}: <a href="{url}">{url}</a>')

    def docs_url(self) -> str:
        """Hook: the panel's documentation URL, or ``""`` for no docs link.

        Default = :attr:`DOCS_URL` (static). Override to compute it (e.g. a
        panel that points at a per-engine page)."""
        return self.DOCS_URL

    def clear_log(self) -> None:
        """Clear the log panel (wired by subclass header menus)."""
        self.ui.txt000.clear()
