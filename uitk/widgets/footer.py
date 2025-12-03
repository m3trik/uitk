# !/usr/bin/python
# coding=utf-8
from typing import Any, Callable, Mapping, Optional

from qtpy import QtWidgets, QtCore, QtGui
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay
from uitk.widgets.mixins.size_grip import SizeGripMixin
from uitk.widgets.progressBar import ProgressBar

try:
    from pythontk.str_utils import StrUtils
except ImportError:  # Optional dependency; controller will fall back to simple slicing.
    StrUtils = None


class Footer(QtWidgets.QWidget, AttributesMixin, SizeGripMixin):
    """Footer is a widget that acts as a status bar with integrated progress bar.

    It provides a customizable footer bar with:
        - Status text display
        - Integrated progress bar (shown during tasks)
        - Optional size grip for window resizing

    The footer uses a stacked widget to switch between status text and progress bar,
    providing a clean interface for both static status and progress feedback.

    Attributes:
        progress_bar (ProgressBar): The embedded progress bar widget
        status_label (QLabel): The status text label
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
            **kwargs: Additional attributes for the footer.
        """
        super().__init__(parent)

        self._status_text = ""
        self._default_status_text = ""
        self._size_grip = None

        # Main layout
        self.main_layout = QtWidgets.QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Stacked widget for status/progress
        self._stacked_widget = QtWidgets.QStackedWidget()
        self._stacked_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        self._stacked_widget.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._stacked_widget.setContentsMargins(0, 0, 0, 0)

        # Status label (page 0)
        self._status_label = QtWidgets.QLabel()
        self._status_label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        self._status_label.setIndent(8)
        self._stacked_widget.addWidget(self._status_label)

        # Progress bar (page 1)
        self._progress_bar = ProgressBar(auto_hide=False)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.finished.connect(self._on_progress_finished)
        self._progress_bar.cancelled.connect(self._on_progress_finished)
        self._stacked_widget.addWidget(self._progress_bar)

        self.main_layout.addWidget(self._stacked_widget)

        # Style children to blend with footer background (transparent, no borders, no hover)
        self._apply_transparent_style()

        # Set up size grip
        self.setProperty("class", self.__class__.__name__)
        self.setFixedHeight(20)

        if add_size_grip:
            self._setup_size_grip()

        self.set_attributes(**kwargs)

    @property
    def container_layout(self) -> QtWidgets.QHBoxLayout:
        """Backward compatibility: return main_layout as container_layout."""
        return self.main_layout

    def alignment(self) -> QtCore.Qt.Alignment:
        """Get alignment of the status label (backward compatibility)."""
        return self._status_label.alignment()

    def update_font_size(self):
        """Public method for updating font size (backward compatibility)."""
        self._update_font_size()

    def font(self) -> QtGui.QFont:
        """Get font from status label (backward compatibility)."""
        return self._status_label.font()

    def _setup_size_grip(self):
        """Set up the size grip in the footer."""
        self._size_grip = self.create_size_grip(
            container=self,
            layout=self.main_layout,
            alignment=QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight,
        )

    @property
    def progress_bar(self) -> ProgressBar:
        """Get the embedded progress bar."""
        return self._progress_bar

    @property
    def status_label(self) -> QtWidgets.QLabel:
        """Get the status label."""
        return self._status_label

    @property
    def size_grip(self) -> Optional[QtWidgets.QSizeGrip]:
        """Get the size grip widget if it exists.

        Returns:
            QSizeGrip or None: The size grip widget, or None if not created.
        """
        return self._size_grip

    @size_grip.setter
    def size_grip(self, value: Optional[QtWidgets.QSizeGrip]) -> None:
        """Set the size grip widget (used internally by SizeGripMixin).

        Parameters:
            value: The size grip widget to set.
        """
        self._size_grip = value

    def setText(self, text: str) -> None:
        """Set the status text (convenience method matching QLabel API).

        Parameters:
            text (str): The status text to display.
        """
        self.setStatusText(text)

    def text(self) -> str:
        """Get the current displayed text (convenience method matching QLabel API).

        Returns:
            str: The text currently shown in the status label.
        """
        return self._status_label.text()

    def setStatusText(self, text: str | None = None) -> None:
        """Set the status text of the footer.

        Parameters:
            text (str): The new status text.
        """
        self._status_text = text or ""
        resolved_text = self._status_text or self._default_status_text
        self._status_label.setText(resolved_text)

        # Switch to status view if not showing progress
        if self._stacked_widget.currentIndex() != 1:
            self._stacked_widget.setCurrentIndex(0)

    def setDefaultStatusText(self, text: str | None = None) -> None:
        """Set fallback text shown when no explicit status is provided."""
        self._default_status_text = text or ""
        if not self._status_text:
            self._status_label.setText(self._default_status_text)
            # Ensure we're showing the status view
            if self._stacked_widget.currentIndex() != 1:
                self._stacked_widget.setCurrentIndex(0)

    def statusText(self) -> str:
        """Get the status text of the footer.

        Returns:
            str: The current status text.
        """
        return self._status_text

    def start_progress(
        self,
        total: int = 100,
        text: str = "",
    ) -> Callable[[int, Optional[str]], bool]:
        """Start showing progress in the footer.

        Parameters:
            total: Total number of steps
            text: Optional status text to show with progress

        Returns:
            Callable: Update function that takes (value, optional_text)

        Example:
            update = footer.start_progress(100, "Loading...")
            for i in range(100):
                if not update(i + 1):
                    break  # Cancelled
            footer.finish_progress()
        """
        self._stacked_widget.setCurrentIndex(1)
        self._progress_bar.start_task(total, text, show=True)
        return self._progress_bar.update_progress

    def update_progress(self, value: int, text: Optional[str] = None) -> bool:
        """Update the progress value.

        Parameters:
            value: Current progress value
            text: Optional new status text

        Returns:
            False if cancelled, True otherwise
        """
        return self._progress_bar.update_progress(value, text)

    def finish_progress(self, text: Optional[str] = None, delay_ms: int = 1000):
        """Finish the progress and switch back to status text.

        Parameters:
            text: Optional completion message to show briefly
            delay_ms: Delay before switching back to status (default 1000ms)
        """
        if text:
            self._progress_bar.setFormat(text)
            self._progress_bar.setValue(self._progress_bar.maximum())

        QtCore.QTimer.singleShot(delay_ms, self._on_progress_finished)

    def cancel_progress(self):
        """Cancel the current progress operation."""
        self._progress_bar.cancel()

    def progress(self, total: int = 100, text: str = "") -> "FooterProgressContext":
        """Context manager for progress tracking.

        Parameters:
            total: Total number of steps
            text: Optional status text

        Returns:
            Context manager that provides an update callback

        Example:
            with footer.progress(100, "Processing files...") as update:
                for i, file in enumerate(files):
                    process(file)
                    if not update(i + 1):
                        break  # Cancelled
        """
        return FooterProgressContext(self, total, text)

    def _on_progress_finished(self):
        """Handle progress completion - switch back to status."""
        self._stacked_widget.setCurrentIndex(0)
        self._progress_bar.reset()

    def resizeEvent(self, event):
        """Handle resize events to update font size."""
        self._update_font_size()
        super().resizeEvent(event)

    def _update_font_size(self):
        """Calculate font size for the label relative to widget's height."""
        label_font_size = self.height() * 0.4
        font = self._status_label.font()
        font.setPointSizeF(label_font_size)
        font.setBold(False)
        self._status_label.setFont(font)

    def _apply_transparent_style(self):
        """Style stacked widget and children to blend seamlessly with footer."""
        # Transparent background, no border, no hover effects
        transparent_style = """
            QStackedWidget {
                background: transparent;
                border: none;
            }
            QLabel {
                background: transparent;
                border: none;
            }
            QProgressBar {
                background: transparent;
                border: none;
            }
            QProgressBar::chunk {
                border: none;
            }
        """
        self._stacked_widget.setStyleSheet(transparent_style)
        self._status_label.setStyleSheet("background: transparent; border: none;")
        self._progress_bar.setStyleSheet(
            "QProgressBar { background: transparent; border: none; }"
            "QProgressBar::chunk { border: none; }"
        )

    def attach_to(self, widget: QtWidgets.QWidget) -> None:
        """Attach this footer to the bottom of a QWidget or QMainWindow's centralWidget."""
        if hasattr(widget, "footer") and getattr(widget, "footer") is self:
            return

        if isinstance(widget, QtWidgets.QMainWindow) and widget.centralWidget():
            widget = widget.centralWidget()

        layout = widget.layout()
        if not isinstance(layout, QtWidgets.QLayout):
            layout = QtWidgets.QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            widget.setLayout(layout)
        layout.addWidget(self)
        self.setParent(widget)
        setattr(widget, "footer", self)


class FooterProgressContext:
    """Context manager for footer progress tracking."""

    def __init__(self, footer: Footer, total: int, text: str):
        self._footer = footer
        self._total = total
        self._text = text

    def __enter__(self) -> Callable[[int, Optional[str]], bool]:
        """Start progress and return update callback."""
        return self._footer.start_progress(self._total, self._text)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finish progress."""
        if exc_type is None and not self._footer.progress_bar.is_cancelled:
            self._footer.finish_progress("Complete", delay_ms=500)
        else:
            self._footer._on_progress_finished()
        return False


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
