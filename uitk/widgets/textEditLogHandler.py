# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore, QtGui
import logging
from pythontk.core_utils.logging_mixin import LoggerExt


class TextEditLogHandler(logging.Handler):
    """Custom logging handler for Qt QTextEdit widgets."""

    def __init__(self, widget: object, monospace: bool = True):
        super().__init__()
        self.widget = widget
        self.setLevel(logging.NOTSET)  # Always receive all messages

        if monospace:
            font = self._get_monospace_font()
            self.widget.setFont(font)

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
                self.widget.repaint()  # Force immediate update
                QtWidgets.QApplication.processEvents()  # Process UI events
            else:
                print(f"Logging error: widget does not support append.")
        except Exception as e:
            print(f"QtTextEditHandler error: {e}")

    def get_color(self, level: str) -> str:
        return LoggerExt.get_color(level)


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
