# !/usr/bin/python
# coding=utf-8
import importlib.resources
from typing import Union
from qtpy import QtWidgets, QtCore
import pythontk as ptk


class StyleSheet(QtCore.QObject, ptk.LoggingMixin):
    themes = {
        "light": {
            "MAIN_FOREGROUND": "rgb(255,255,255)",
            "MAIN_BACKGROUND": "rgb(70,70,70)",
            "MAIN_BACKGROUND_ALPHA": "rgba(70,70,70,185)",
            "HEADER_BACKGROUND": "rgba(127,127,127,200)",
            "WIDGET_BACKGROUND": "rgb(125,125,125)",
            "BUTTON_PRESSED": "rgb(120,120,120)",
            "BUTTON_HOVER": "rgb(82,133,166)",
            "TEXT_COLOR": "rgb(255,255,255)",
            "TEXT_CHECKED": "rgb(255,255,255)",
            "TEXT_DISABLED": "rgba(150,150,150,175)",
            "TEXT_HOVER": "rgb(255,255,255)",
            "TEXT_BACKGROUND": "rgb(70,70,70)",
            "BORDER_COLOR": "rgb(40,40,40)",
            "HIGHLIGHT_COLOR": "rgb(255,255,190)",
            "DISABLED_BACKGROUND": "rgb(85,85,85)",
            "PROGRESS_BAR_COLOR": "rgb(0,160,208)",
        },
        "dark": {
            "MAIN_FOREGROUND": "rgb(200,200,200)",
            "MAIN_BACKGROUND": "rgb(90,90,90)",
            "MAIN_BACKGROUND_ALPHA": "rgba(90,90,90,185)",
            "HEADER_BACKGROUND": "rgba(90,90,90,200)",
            "WIDGET_BACKGROUND": "rgb(60,60,60)",
            "BUTTON_PRESSED": "rgb(50,50,50)",
            "BUTTON_HOVER": "rgb(82,133,166)",
            "TEXT_COLOR": "rgb(220,220,220)",
            "TEXT_CHECKED": "rgb(255,255,255)",
            "TEXT_DISABLED": "rgba(150,150,150,175)",
            "TEXT_HOVER": "rgb(255,255,255)",
            "TEXT_BACKGROUND": "rgb(30,30,30)",
            "BORDER_COLOR": "rgb(20,20,20)",
            "HIGHLIGHT_COLOR": "rgb(255,255,190)",
            "DISABLED_BACKGROUND": "rgb(35,35,35)",
            "PROGRESS_BAR_COLOR": "rgb(0,160,208)",
        },
    }

    _qss_cache: dict[str, str] = {}

    def __init__(
        self, parent: Union[QtWidgets.QWidget, None] = None, log_level: str = "WARNING"
    ):
        super().__init__(parent)
        self.logger.setLevel(log_level)
        self.set = self._set_style

    def _load_qss_file(
        self, resource: str = "style.qss", package: str = "uitk.widgets.mixins"
    ) -> str:
        cache_key = f"{package}:{resource}"
        if cache_key not in self._qss_cache:
            try:
                with importlib.resources.files(package).joinpath(resource).open(
                    "r", encoding="utf-8"
                ) as f:
                    self._qss_cache[cache_key] = f.read()
                self.logger.info(f"Loaded QSS from package: {package}/{resource}")
            except Exception as e:
                self.logger.error(f"Failed to load QSS from {package}/{resource} ({e})")
                raise
        else:
            self.logger.debug(f"Using cached QSS for: {package}/{resource}")
        return self._qss_cache[cache_key]

    @staticmethod
    def _apply_theme_variables(qss: str, theme_vars: dict) -> str:
        for k, v in theme_vars.items():
            qss = qss.replace("{" + k + "}", v)
        return qss

    @staticmethod
    def _set_class_property(widget: QtWidgets.QWidget, style_class: str):
        widget.setProperty("class", style_class)
        if isinstance(widget, QtWidgets.QMainWindow) and widget.centralWidget():
            widget.centralWidget().setProperty("class", style_class)

    @ptk.listify
    def _set_style(
        self,
        widget: Union[QtWidgets.QWidget, None] = None,
        theme: str = "light",
        style_class: str = "",
        recursive: bool = False,
        resource: str = "style.qss",
        package: str = "uitk.widgets.mixins",
        **kwargs,
    ):
        if widget is None:
            if isinstance(self.parent(), QtWidgets.QWidget):
                widget = self.parent()
            else:
                raise ValueError(
                    f"No valid QWidget found for styling (self={self}, parent={self.parent()})"
                )

        if not isinstance(widget, QtWidgets.QWidget):
            self.logger.error(f"Invalid datatype for widget: {type(widget)}")
            raise ValueError(f"Expected QWidget, got {type(widget)}.")

        if style_class:
            self._set_class_property(widget, style_class)
            self.logger.debug(
                f"Set style class '{style_class}' on widget: {widget.objectName()}"
            )

        try:
            qss = self._load_qss_file(resource, package)
            qss_final = self._apply_theme_variables(qss, self.themes[theme])
            self.logger.debug(
                f"Applying QSS to widget '{widget.objectName()}':\n---BEGIN QSS---\n{qss_final}\n---END QSS---"
            )
            widget.setStyleSheet("")  # Optional clear
            widget.setStyleSheet(qss_final)
            self.logger.info(
                f"Applied QSS style to widget: {widget.objectName()} (theme='{theme}', class='{style_class}')"
            )
        except Exception as e:
            self.logger.error(
                f"Failed to apply QSS style to {widget.objectName()}: {e}"
            )
            raise

        if recursive:
            for child in widget.findChildren(QtWidgets.QWidget):
                self.logger.debug(
                    f"Recursively setting style on: {child.objectName()} ({type(child).__name__})"
                )
                self._set_style(
                    child,
                    theme=theme,
                    recursive=False,
                    resource=resource,
                    package=package,
                    **kwargs,
                )


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    ...

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
