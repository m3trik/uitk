# !/usr/bin/python
# coding=utf-8
import time
from qtpy import QtWidgets, QtCore, QtGui
import logging
from pythontk.core_utils.logging_mixin import LoggerExt


class TextEditLogHandler(logging.Handler):
    """Custom logging handler for Qt QTextEdit widgets."""

    def __init__(self, widget: object, monospace: bool = True):
        super().__init__()
        self.widget = widget
        self.setLevel(logging.NOTSET)  # Always receive all messages

        # Ensure custom action:// links fire anchorClicked instead of
        # being opened in an external browser (QTextBrowser only).
        # setOpenLinks(False) prevents QTextBrowser from navigating
        # internally (which would clear the document).
        # setOpenExternalLinks(False) prevents delegation to QDesktopServices.
        if hasattr(widget, "setOpenLinks"):
            widget.setOpenLinks(False)
        if hasattr(widget, "setOpenExternalLinks"):
            widget.setOpenExternalLinks(False)

        # Set palette link colours so <a> tags are readable against the
        # dark background.  Uses the theme's LINK_COLOR when available,
        # otherwise falls back to a soft desaturated blue pastel.
        self._apply_link_palette(widget)

        if monospace:
            font = self._get_monospace_font()
            self.widget.setFont(font)

    @staticmethod
    def _apply_link_palette(widget):
        """Set QPalette.Link / LinkVisited so <a> tags are readable."""
        try:
            from uitk.widgets.mixins.style_sheet import StyleSheet

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

    @staticmethod
    def _get_monospace_font() -> QtGui.QFont:
        """Try to get a safe monospace font across platforms."""
        for family in ("Consolas", "Courier New", "Monospace"):
            font = QtGui.QFont(family)
            font.setStyleHint(QtGui.QFont.Monospace)
            if font.exactMatch() or family == "Monospace":
                return font
        # fallback — still force Monospace style
        fallback = QtGui.QFont()
        fallback.setStyleHint(QtGui.QFont.Monospace)
        return fallback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if getattr(record, "raw", False):
                msg = record.getMessage()
                # Use white-space:pre (not pre-wrap) so box-drawing lines
                # are never broken by word-wrap — clipping is preferable
                # to misaligned box characters.
                msg = f'<span style="font-family:monospace; white-space:pre;">{msg}</span>'
            else:
                msg = self.format(record)
                color = self.get_color(record.levelname)
                # Use span tag to preserve whitespace alignment without extra block spacing
                msg = f'<span style="color:{color}; font-family:monospace; white-space:pre-wrap;">{msg}</span>'

            # Check if we're on the main GUI thread
            app = QtWidgets.QApplication.instance()
            if app and app.thread() == QtCore.QThread.currentThread():
                # Direct call on main thread with immediate processEvents
                self._safe_append(msg)
            else:
                # Thread-safe deferred call from worker thread
                QtCore.QTimer.singleShot(0, lambda: self._safe_append(msg))

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
                now = time.monotonic()
                if now - getattr(self, "_last_repaint", 0) > 0.05:
                    self._last_repaint = now
                    self.widget.repaint()
                    QtWidgets.QApplication.processEvents()
            else:
                print("Logging error: widget does not support append.")
        except Exception as e:
            print(f"QtTextEditHandler error: {e}")

    def get_color(self, level: str) -> str:
        return LoggerExt.get_color(level)

    def available_columns(self) -> int:
        """Return the number of monospace columns that fit in the viewport.

        Used by ``LoggerExt._log_box`` so boxes shrink to fit the redirect
        target instead of being clipped or wrapped. Returns ``0`` when the
        widget is not yet sized or too narrow to host a usable box, in
        which case callers should fall back to ``DEFAULT_BOX_WIDTH``.
        """
        try:
            mono = self._get_monospace_font()
            # Box markup forces font-family:monospace inline but inherits
            # the widget's point size — match that so measurement tracks
            # any user-customized font size.
            widget_font = self.widget.font()
            pt = widget_font.pointSizeF()
            if pt > 0:
                mono.setPointSizeF(pt)
            else:
                px = widget_font.pixelSize()
                if px > 0:
                    mono.setPixelSize(px)
            char_w = QtGui.QFontMetrics(mono).horizontalAdvance(" ")
            if not char_w:
                return 0
            viewport = self.widget.viewport() if hasattr(self.widget, "viewport") else None
            avail_px = viewport.width() if viewport else self.widget.width()
            # viewport() already excludes the scrollbar; reserve one char
            # for cursor padding so the box never touches the right edge.
            usable = avail_px - char_w
            if usable <= 0:
                return 0
            cols = usable // char_w
            # Anything below ~20 cols produces a degenerate box; defer to
            # the caller's default instead.
            return cols if cols >= 20 else 0
        except Exception:
            return 0


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
