# !/usr/bin/python
# coding=utf-8
import time
from qtpy import QtWidgets, QtCore, QtGui
import logging
from pythontk.core_utils.logging_mixin import LoggerExt
from uitk.widgets.mixins.text import RichTextFormatter


class _CrossThreadAppender(QtCore.QObject):
    """Marshals a formatted message onto the GUI thread for appending.

    A logging call from a plain worker thread has no Qt event loop, so a
    ``QTimer.singleShot`` scheduled there never fires and the record is lost.
    Emitting a signal is thread-safe, and — because this object lives in the
    widget's (GUI) thread — a queued connection delivers the append there.
    """

    posted = QtCore.Signal(str)

    def __init__(self, append_fn):
        super().__init__()
        self._append_fn = append_fn
        self.posted.connect(self._deliver)

    @QtCore.Slot(str)
    def _deliver(self, msg):
        self._append_fn(msg)


class TextEditLogHandler(logging.Handler):
    """Custom logging handler for Qt QTextEdit widgets."""

    def __init__(self, widget: object, monospace: bool = True):
        super().__init__()
        self.widget = widget
        self.setLevel(logging.NOTSET)  # Always receive all messages

        # Bridge for records emitted off the GUI thread (see emit()). Pinned to
        # the widget's thread so its queued slot runs where the widget lives.
        self._appender = _CrossThreadAppender(self._safe_append)
        try:
            if hasattr(widget, "thread"):
                self._appender.moveToThread(widget.thread())
        except Exception:  # pragma: no cover - defensive
            pass

        # action:// links must fire anchorClicked (for the panel's own
        # dispatcher) and web links must still reach the browser -- see
        # route_links() for the three settings that make that so.
        self.route_links(widget)

        # Set palette link colours so <a> tags are readable against the
        # dark background.  Uses the theme's LINK_COLOR when available,
        # otherwise falls back to a soft desaturated blue pastel.
        self._apply_link_palette(widget)

        mono = self._get_monospace_font()
        if monospace:
            self.widget.setFont(mono)

        # The ONE family records are marked up in and available_columns()
        # counts in. Never CSS's generic ``monospace``: Windows has no family
        # by that name, so Qt substitutes by the widget font's style hint --
        # Courier New, ~9% wider than the Consolas the columns were counted
        # in, or the proportional UI font when there is no hint -- and a box
        # sized to the pane overflowed it.
        self._font_family = self._resolved_family(mono)

    #: Dynamic-property flag stamped on a widget once :meth:`route_links` has
    #: wired it, so a handler rebuilt on the same live widget (a re-created
    #: panel, a second logger redirected to one pane) doesn't stack a second
    #: ``anchorClicked`` connection -- which would open two browser tabs per
    #: click.
    _LINKS_ROUTED_PROP = "uitk_links_routed"

    @classmethod
    def route_links(cls, widget) -> None:
        """Make *widget*'s anchors behave like a log pane's (idempotent).

        Three settings, applied once per widget (QTextBrowser only -- a plain
        QTextEdit has none of them and is left alone):

        * ``setOpenLinks(False)`` -- QTextBrowser must never navigate to a
          clicked URL: an unresolvable ``action://`` target replaces the
          document with nothing, wiping the log.
        * ``setOpenExternalLinks(False)`` -- Qt's own delegation would hand
          ``action://`` links to the OS (no protocol handler) instead of the
          panel's ``anchorClicked`` dispatcher.
        * ``anchorClicked`` -> :meth:`open_web_link` -- the one thing the
          previous setting also silenced: ordinary ``http(s)`` anchors (a
          docs link logged at startup, a release page in a warning). Web
          links open in the default browser; every other scheme is ignored
          here and left to the panel's own handler, so nothing double-fires.

        Called from the constructor; also safe to call directly for a pane
        that receives links without a handler attached (a panel whose
        optional engine is missing appends to its log widget by hand).
        """
        if hasattr(widget, "setOpenLinks"):
            widget.setOpenLinks(False)
        if hasattr(widget, "setOpenExternalLinks"):
            widget.setOpenExternalLinks(False)
        signal = getattr(widget, "anchorClicked", None)
        if signal is None or widget.property(cls._LINKS_ROUTED_PROP):
            return
        signal.connect(cls.open_web_link)
        widget.setProperty(cls._LINKS_ROUTED_PROP, True)

    @staticmethod
    def open_web_link(url) -> bool:
        """Open an ``http``/``https`` :class:`QUrl` in the default browser.

        Returns True when the link was a web link (and was handed to
        ``QDesktopServices``), False for any other scheme -- ``action://``
        and friends belong to the panel's own ``anchorClicked`` handler.
        """
        try:
            if url.scheme() in ("http", "https"):
                QtGui.QDesktopServices.openUrl(url)
                return True
        except Exception:  # pragma: no cover - defensive; a click must not raise
            pass
        return False

    @staticmethod
    def _apply_link_palette(widget):
        """Set QPalette.Link / LinkVisited so <a> tags are readable."""
        try:
            from uitk.themes.style_sheet import StyleSheet

            theme_name = StyleSheet._widget_themes.get(widget, "dark")
            theme_vars = StyleSheet.themes.get(theme_name, {})
        except Exception:
            theme_vars = {}

        link_str = theme_vars.get("LINK_COLOR", "rgb(130,170,210)")
        visited_str = theme_vars.get("LINK_VISITED_COLOR", "rgb(160,150,190)")

        def _parse_rgb(s):
            s = s.strip()
            if s.startswith("rgb(") and s.endswith(")"):
                parts = s[4:-1].split(",")
                if len(parts) == 3:
                    return QtGui.QColor(*(int(p.strip()) for p in parts))
            return QtGui.QColor(s)

        pal = widget.palette()
        pal.setColor(QtGui.QPalette.Link, _parse_rgb(link_str))
        pal.setColor(QtGui.QPalette.LinkVisited, _parse_rgb(visited_str))
        widget.setPalette(pal)

    #: Monospace families, first installed wins: read from the stack pythontk's
    #: ``log_box`` pins its tinted rows to, so those rows render in the family
    #: available_columns() counts in. The trailing generic resolves through
    #: fontconfig on Linux.
    _MONOSPACE_FAMILIES = tuple(
        family.strip("'\" ") for family in LoggerExt.MONOSPACE_FAMILIES.split(",")
    )

    @classmethod
    def _get_monospace_font(cls) -> QtGui.QFont:
        """The monospace font, resolved the way Qt resolves a CSS
        ``font-family`` list."""
        font = QtGui.QFont()
        font.setFamilies(list(cls._MONOSPACE_FAMILIES))
        font.setStyleHint(QtGui.QFont.Monospace)
        return font

    @staticmethod
    def _resolved_family(font: QtGui.QFont) -> str:
        """The installed family Qt renders *font* in -- or the requested one
        when no font database is loaded to say (a font-less offscreen QPA)."""
        return QtGui.QFontInfo(font).family() or font.family()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            family = self._font_family
            if getattr(record, "raw", False):
                msg = record.getMessage()
                # white-space:pre keeps the runs of spaces and the line breaks
                # a box is built from. It does NOT stop Qt wrapping a row that
                # is too long (only a block format can; this span is inline),
                # so a box stays whole only because available_columns() sized
                # it to the pane.
                msg = f"<span style=\"font-family:'{family}'; white-space:pre;\">{msg}</span>"
            else:
                msg = self.format(record)
                color = self.get_color(record.levelname)
                # Use span tag to preserve whitespace alignment without extra block spacing
                msg = f"<span style=\"color:{color}; font-family:'{family}'; white-space:pre-wrap;\">{msg}</span>"
            # An address a line gives opens when clicked (route_links); the
            # record itself stays plain, so a console handler prints it as is.
            msg = RichTextFormatter.linkify(msg)

            # Check if we're on the main GUI thread
            app = QtWidgets.QApplication.instance()
            if app and app.thread() == QtCore.QThread.currentThread():
                # Direct call on main thread with immediate processEvents
                self._safe_append(msg)
            else:
                # From a worker thread: a QTimer scheduled here would never fire
                # (no event loop on this thread). Emitting the bridge's signal is
                # thread-safe and, via its queued connection, appends on the GUI
                # thread where the widget lives.
                self._appender.posted.emit(msg)

        except Exception as e:
            print(f"QtTextEditHandler error: {e}")

    def _safe_append(self, formatted_msg: str) -> None:
        try:
            if hasattr(self.widget, "append"):
                self.widget.append(formatted_msg)
                # Auto-scroll to the latest entry
                scrollbar = self.widget.verticalScrollBar()
                if scrollbar:
                    scrollbar.setValue(scrollbar.maximum())
                # Force-paint only a VISIBLE widget.  A hidden target needs no
                # live repaint, and pumping the event queue from inside a log
                # emit while its panel is still being constructed dispatches
                # deferred events against half-built widgets — a native crash
                # (access violation), not an exception this except can catch.
                now = time.monotonic()
                if now - getattr(self, "_last_repaint", 0) > 0.05:
                    self._last_repaint = now
                    if self.widget.isVisible():
                        self.widget.repaint()
                        QtWidgets.QApplication.processEvents()
            else:
                print("Logging error: widget does not support append.")
        except Exception as e:
            print(f"QtTextEditHandler error: {e}")

    def get_color(self, level: str) -> str:
        return LoggerExt.get_color(level)

    def available_columns(self) -> int:
        """Return how many monospace columns fit on one line of the pane.

        ``LoggerExt`` sizes boxes, dividers and tables to this, so it has to
        be exact: Qt wraps a row one column too wide, and a wrapped row is a
        broken box. Counts in the family records are marked up in, at the
        document's font and with fractional advances, against the width a
        line really gets: the viewport, less the document margins, less a
        vertical scrollbar that is not showing yet (see
        :meth:`_scrollbar_to_come`).

        Returns:
            The column count, however narrow the pane (a narrow box stays
            whole where the default-width one would wrap); ``0`` -- width
            unknown, so callers fall back to ``DEFAULT_BOX_WIDTH`` -- until
            the widget has been shown, since before its first layout the
            viewport is Qt's placeholder geometry, not the pane.
        """
        try:
            widget = self.widget
            if widget.testAttribute(QtCore.Qt.WA_PendingResizeEvent):
                return 0
            document = widget.document() if hasattr(widget, "document") else None
            font = QtGui.QFont(
                document.defaultFont() if document is not None else widget.font()
            )
            font.setFamily(self._font_family)
            metrics = QtGui.QFontMetricsF(font)
            # Rows are box-drawing glyphs and (no-break) spaces: the widest
            # advance counts, so a glyph borrowed from a fallback font cannot
            # overrun.
            char_w = max(metrics.horizontalAdvance(ch) for ch in " ═║")
            if char_w <= 0:
                return 0
            viewport = widget.viewport() if hasattr(widget, "viewport") else widget
            width = viewport.width() - self._scrollbar_to_come()
            if document is not None:
                width -= 2 * document.documentMargin()
            return max(int(width // char_w), 0)
        except Exception:
            return 0

    def _scrollbar_to_come(self) -> int:
        """Pixels a vertical scrollbar not showing yet will take from a line.

        ``viewport()`` already excludes a scrollbar that is showing, but one
        that is not can arrive with the very rows being sized: a box long
        enough to overflow the pane narrows it under the box laid out for
        it. Nothing to reserve when it can never show, or when the style
        overlays it on the text (transient scrollbars take no width).
        """
        widget = self.widget
        if not hasattr(widget, "verticalScrollBar"):
            return 0
        bar = widget.verticalScrollBar()
        if bar.isVisibleTo(widget):
            return 0
        if widget.verticalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff:
            return 0
        if bar.style().styleHint(QtWidgets.QStyle.SH_ScrollBar_Transient, None, bar):
            return 0
        return bar.sizeHint().width()


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = TextEditLogHandler(QtWidgets.QTextEdit())
    w.widget.setWindowTitle("TextEditLogHandler Example")
    w.widget.setGeometry(100, 100, 400, 300)
    w.widget.setReadOnly(True)
    w.widget.setStyleSheet("background-color: black; color: white;")
    w.widget.show()
    w.widget.append("This is a test message.")
    sys.exit(app.exec_())
