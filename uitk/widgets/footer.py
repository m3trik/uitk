# !/usr/bin/python
# coding=utf-8
from typing import Any, Callable, Mapping, Optional

from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay
from uitk.widgets.mixins.size_grip import SizeGripMixin

try:
    from pythontk.str_utils import StrUtils
except ImportError:  # Optional dependency; controller will fall back to simple slicing.
    StrUtils = None


class Footer(QtWidgets.QLabel, AttributesMixin, RichText, TextOverlay, SizeGripMixin):
    """Footer is a QLabel that acts as a status bar and can contain a size grip.

    It provides a customizable footer bar with optional status text and a size grip
    for resizing the parent window.

    Attributes:
        _status_text (str): The current status text displayed in the footer.
    """

    def __init__(
        self,
        parent=None,
        add_size_grip=True,
        **kwargs,
    ):
        """Initialize the Footer with optional size grip.

        Parameters:
            parent (QWidget, optional): The parent widget. Defaults to None.
            add_size_grip (bool, optional): Whether to add a size grip. Defaults to True.
            **kwargs: Additional attributes for the footer (e.g., setStatusText="Ready").
        """
        super().__init__(parent)

        self._status_text = ""
        self._default_status_text = ""
        self._size_grip = None

        # Container layout for footer elements
        self.container_layout = QtWidgets.QHBoxLayout(self)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(1)

        self.setLayout(self.container_layout)

        self.setProperty("class", self.__class__.__name__)
        font = self.font()
        font.setBold(False)
        self.setFont(font)

        self.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        self.setIndent(8)  # adds left-side indentation to the text
        self.setFixedHeight(20)

        if add_size_grip:
            self._setup_size_grip()

        self.set_attributes(**kwargs)

    def _setup_size_grip(self):
        """Set up the size grip in the footer."""
        # Create size grip using the mixin
        self._size_grip = self.create_size_grip(
            container=self,
            layout=self.container_layout,
            alignment=QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight,
        )

    def setStatusText(self, text: str | None = None) -> None:
        """Set the status text of the footer.

        Parameters:
            text (str): The new status text.
        """
        self._status_text = text or ""
        resolved_text = self._status_text or self._default_status_text
        self.setText(resolved_text)

    def setDefaultStatusText(self, text: str | None = None) -> None:
        """Set fallback text shown when no explicit status is provided."""
        self._default_status_text = text or ""
        if not self._status_text:
            self.setText(self._default_status_text)

    def statusText(self) -> str:
        """Get the status text of the footer.

        Returns:
            str: The current status text.
        """
        return self._status_text

    def resizeEvent(self, event):
        """Handle resize events to update font size."""
        self.update_font_size()
        super().resizeEvent(event)

    def update_font_size(self):
        """Calculate font size for the label relative to widget's height."""
        label_font_size = self.height() * 0.4
        label_font = self.font()
        label_font.setPointSizeF(label_font_size)
        self.setFont(label_font)

    def attach_to(self, widget: QtWidgets.QWidget) -> None:
        """Attach this footer to the bottom of a QWidget or QMainWindow's centralWidget if appropriate."""
        # Avoid double-attachment
        if hasattr(widget, "footer") and getattr(widget, "footer") is self:
            return

        # If passed a QMainWindow (or subclass), redirect to its central widget.
        if isinstance(widget, QtWidgets.QMainWindow) and widget.centralWidget():
            widget = widget.centralWidget()

        # Attach to the widget's layout
        layout = widget.layout()
        if not isinstance(layout, QtWidgets.QLayout):
            layout = QtWidgets.QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            widget.setLayout(layout)
        layout.addWidget(self)
        self.setParent(widget)
        setattr(widget, "footer", self)


class FooterStatusController:
    """Helper that keeps a footer in sync with a resolver function."""

    def __init__(
        self,
        footer: Footer,
        resolver: Optional[Callable[[], str]] = None,
        default_text: str | None = "",
        truncate_kwargs: Optional[Mapping[str, Any]] = None,
    ):
        self._footer = footer
        self._resolver = resolver or (lambda: "")
        self._truncate_kwargs = self._sanitize_truncate_kwargs(truncate_kwargs)
        if default_text is not None:
            self._footer.setDefaultStatusText(default_text)
        self.update()

    def set_resolver(self, resolver: Callable[[], str]) -> None:
        self._resolver = resolver or (lambda: "")
        self.update()

    def set_truncation(
        self,
        truncate_kwargs: Optional[Mapping[str, Any]] = None,
        **extra_kwargs: Any,
    ) -> None:
        """Configure truncation behavior for footer updates via StrUtils.truncate kwargs."""
        combined: dict[str, Any] = {}
        if truncate_kwargs:
            combined.update(dict(truncate_kwargs))
        if extra_kwargs:
            combined.update(extra_kwargs)
        self._truncate_kwargs = self._sanitize_truncate_kwargs(combined)
        self.update()

    def update(self) -> None:
        if not self._footer:
            return
        value = self._resolver() if self._resolver else ""
        value = self._truncate_value(value)
        self._footer.setStatusText(value)

    def _truncate_value(self, value: str) -> str:
        """Apply optional truncation using StrUtils when available."""
        if not value:
            return value

        kwargs = self._truncate_kwargs
        if not kwargs:
            return value

        length = kwargs.get("length")
        if not isinstance(length, int) or length <= 0 or len(value) <= length:
            return value

        if StrUtils:
            try:
                return StrUtils.truncate(
                    value,
                    **kwargs,
                )
            except Exception:
                pass  # Fall back to a simplified truncation strategy.

        return self._fallback_truncate(value, kwargs)

    def _fallback_truncate(self, value: str, kwargs: Mapping[str, Any]) -> str:
        insert = kwargs.get("insert", "..") or ""
        mode = (kwargs.get("mode") or "start").lower()
        length = kwargs.get("length")
        if not isinstance(length, int) or length <= 0:
            return value

        if mode in ("end", "right"):
            return value[:length] + insert

        if mode == "middle" and length > len(insert):
            visible = max(1, length - len(insert))
            left = visible // 2
            right = visible - left
            return value[:left] + insert + value[-right:]

        tail_length = max(1, length - len(insert)) if insert else length
        return insert + value[-tail_length:]

    @staticmethod
    def _sanitize_truncate_kwargs(
        truncate_kwargs: Optional[Mapping[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if not truncate_kwargs:
            return None
        try:
            candidate = dict(truncate_kwargs)
        except Exception:
            return None
        length = candidate.get("length")
        if not isinstance(length, int) or length <= 0:
            return None
        return candidate


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(w)

    # Add some content
    label = QtWidgets.QLabel("Main Content Area")
    label.setAlignment(QtCore.Qt.AlignCenter)
    layout.addWidget(label)

    # Add footer
    footer = Footer(setStatusText="Ready")
    layout.addWidget(footer)

    w.resize(400, 300)
    w.show()

    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Promoting a widget in designer to use a custom class:
>   In Qt Designer, select all the widgets you want to replace,
        then right-click them and select 'Promote to...'.

>   In the dialog:
        Base Class:     Class from which you inherit. ie. QWidget
        Promoted Class: Name of the class. ie. "MyWidget"
        Header File:    Path of the file (changing the extension .py to .h)  ie. myfolder.mymodule.mywidget.h

>   Then click "Add", "Promote",
        and you will see the class change from "QWidget" to "MyWidget" in the Object Inspector pane.
"""
