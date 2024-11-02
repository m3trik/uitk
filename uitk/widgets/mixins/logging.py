# !/usr/bin/python
# coding=utf-8
import logging
from qtpy import QtCore, QtWidgets


class TextEditRedirect(logging.Handler, QtCore.QObject):
    def __init__(self, widget: QtWidgets.QTextEdit):
        logging.Handler.__init__(self)
        QtCore.QObject.__init__(self)
        self.widget = widget

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        level = record.levelname
        color = self.get_color(level)
        formatted_msg = f'<span style="color:{color}">{msg}</span>'
        QtCore.QMetaObject.invokeMethod(
            self.widget,
            "append",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, formatted_msg),
        )

    def get_color(self, level: str) -> str:
        colors = {
            "DEBUG": "gray",
            "INFO": "white",
            "WARNING": "#FFFF99",  # pastel yellow
            "ERROR": "#FF9999",  # pastel red
            "CRITICAL": "#CC6666",  # dark pastel red
        }
        return colors.get(level, "white")


class LoggingMixin(QtCore.QObject):
    def __init__(self, text_edit: QtWidgets.QTextEdit = None, log_level=logging.INFO):
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(log_level)
        self.setup_logging(text_edit, log_level)

    def setup_logging(self, text_edit: QtWidgets.QTextEdit, log_level: int):
        # Create console handler with a higher log level
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        self.logger.addHandler(console_handler)

        # Optionally add a QTextEdit handler
        if text_edit:
            text_edit_handler = TextEditRedirect(text_edit)
            text_edit_handler.setFormatter(
                logging.Formatter("%(levelname)s - %(message)s")
            )
            self.logger.addHandler(text_edit_handler)

    def get_log_handler(self, level: str = "INFO"):
        level_method = {
            "DEBUG": self.logger.debug,
            "INFO": self.logger.info,
            "WARNING": self.logger.warning,
            "ERROR": self.logger.error,
            "CRITICAL": self.logger.critical,
        }
        return level_method.get(level.upper(), self.logger.info)


# Usage example
if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
