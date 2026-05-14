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
    """Footer is a widget that acts as a status bar with an integrated
    thin progress indicator across the bottom edge.

    Layout: a QStackedWidget hosts the visible page (extensible for
    future modes like search/filter). Page 0 stacks the status label
    above a slim QProgressBar (textless, hidden when idle). The status
    label carries all human-readable text — including the "Hold Esc to
    cancel…" hint relayed from the progress bar via signals. The
    progress affordance stays minimal while the footer remains the
    single source of truth for text.

    Attributes:
        progress_bar (ProgressBar): The embedded progress bar widget
        status_label (QLabel): The status text label
    """

    # Pixel height of the slim progress indicator at the bottom edge.
    PROGRESS_BAR_HEIGHT = 3

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

        # Hold-to-cancel relay: ProgressBar emits holdStarted/holdEnded;
        # we swap the status text and restore it on release.
        self._status_before_hold: Optional[str] = None

        # Main outer layout (horizontal — leaves room for the size grip on the right)
        self.main_layout = QtWidgets.QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Stacked widget keeps room for future alternate pages (search,
        # filter, etc.) without restructuring the footer.
        self._stacked_widget = QtWidgets.QStackedWidget()
        self._stacked_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        self._stacked_widget.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._stacked_widget.setContentsMargins(0, 0, 0, 0)

        # Page 0 — status label (top, fills available space) + slim
        # progress bar pinned to the bottom edge.
        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._status_label = QtWidgets.QLabel()
        self._status_label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        self._status_label.setIndent(8)
        self._status_label.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Expanding
        )
        content_layout.addWidget(self._status_label)

        self._progress_bar = ProgressBar(auto_hide=True)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(self.PROGRESS_BAR_HEIGHT)
        self._progress_bar.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self._progress_bar.finished.connect(self._on_progress_finished)
        self._progress_bar.cancelled.connect(self._on_progress_finished)
        self._progress_bar.holdStarted.connect(self._on_hold_started)
        self._progress_bar.holdEnded.connect(self._on_hold_ended)
        content_layout.addWidget(self._progress_bar)

        self._stacked_widget.addWidget(content)
        self.main_layout.addWidget(self._stacked_widget)

        # Style children to blend with footer background (transparent, no borders, no hover)
        self._apply_transparent_style()

        # Set up size grip
        self.setProperty("class", self.__class__.__name__)
        self.setFixedHeight(19)

        if add_size_grip:
            self._setup_size_grip()

        # Debounce timer: re-evaluate text only after resize settles
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._on_resize_settled)

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
        self._grip_spacer = QtWidgets.QSpacerItem(
            6, 0, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum
        )
        self.main_layout.addItem(self._grip_spacer)
        self._size_grip = self.create_size_grip(
            container=self,
            layout=self.main_layout,
            alignment=QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight,
        )

    # ── Action buttons ───────────────────────────────────────────

    def add_widget(
        self,
        widget: QtWidgets.QWidget,
        side: str = "right",
        background: bool = False,
    ) -> QtWidgets.QWidget:
        """Insert an arbitrary widget into the footer on the given side.

        ``side="right"`` places the widget on the right, before the size
        grip (if present).  ``side="left"`` places it at the left edge,
        before the status/progress stack.  Returns *widget* for chaining.

        ``background=False`` (default) makes the widget transparent so it
        blends with the footer; set to ``True`` for normal styled background.
        """
        if side not in ("left", "right"):
            raise ValueError(f"side must be 'left' or 'right', got {side!r}")

        widget.setProperty("footerWidget", not background)
        widget.setParent(self)
        if side == "left":
            self.main_layout.insertWidget(0, widget)
        else:
            if self._size_grip:
                idx = self.main_layout.indexOf(self._grip_spacer)
                self.main_layout.insertWidget(idx, widget)
            else:
                self.main_layout.addWidget(widget)

        # Grow the footer's fixed height if the new child is taller, so
        # callers can drop in prebuilt widgets without clipping.
        try:
            needed = max(widget.minimumHeight(), widget.sizeHint().height())
        except Exception:
            needed = 0
        if needed and needed > self.height():
            self.setFixedHeight(needed)
        return widget

    def add_action_button(
        self,
        text: str = "",
        icon_name: str = None,
        tooltip: str = "",
        callback=None,
    ) -> QtWidgets.QPushButton:
        """Add an action button to the right side of the footer.

        Buttons are inserted before the size grip (if present) and after
        the status/progress area, similar to how :class:`Header` hosts
        icon buttons.

        Parameters:
            text: Button label text.
            icon_name: Icon name (without extension) for ``IconManager``.
            tooltip: Tooltip text.
            callback: Callable connected to the button's ``clicked`` signal.

        Returns:
            The created QPushButton.
        """
        btn = QtWidgets.QPushButton(text, self)
        btn.setProperty("footerWidget", True)
        h = self.height()
        btn_h = max(h - 2, 1)  # 1px clearance top and bottom
        if icon_name and not text:
            btn.setFixedSize(btn_h, btn_h)  # square for icon-only
        else:
            btn.setFixedHeight(btn_h)  # flexible width for text
        btn.setCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))

        if icon_name:
            from uitk.widgets.mixins.icon_manager import IconManager

            icon_size = int(h * 0.7)
            IconManager.set_icon(btn, icon_name, size=(icon_size, icon_size))

        if tooltip:
            btn.setToolTip(tooltip)

        if callback:
            btn.clicked.connect(callback)

        # Insert before grip spacer if present, otherwise append
        if self._size_grip:
            idx = self.main_layout.indexOf(self._grip_spacer)
            self.main_layout.insertWidget(idx, btn)
        else:
            self.main_layout.addWidget(btn)

        return btn

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
        self._elide_status_text()

    def setDefaultStatusText(self, text: str | None = None) -> None:
        """Set fallback text shown when no explicit status is provided."""
        self._default_status_text = text or ""
        if not self._status_text:
            self._elide_status_text()

    def statusText(self) -> str:
        """Get the status text of the footer.

        Returns:
            str: The current status text.
        """
        return self._status_text

    def start_progress(
        self,
        total: Optional[int] = 100,
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
        # Status text lives on the footer's label; the slim bar itself
        # carries no visible text (setTextVisible=False).
        if text:
            self.setStatusText(text)
        self._progress_bar.start_task(total, text="", show=True)
        return self.update_progress

    def update_progress(self, value: int, text: Optional[str] = None) -> bool:
        """Update the progress value and optionally the status text.

        Parameters:
            value: Current progress value
            text: Optional new status text (shown in the footer label,
                not on the bar itself).

        Returns:
            False if cancelled, True otherwise
        """
        if text is not None and self._status_before_hold is None:
            # Skip status updates during a hold; the held hint stays put,
            # and we restore the pre-hold text on release.
            self.setStatusText(text)
        return self._progress_bar.update_progress(value)

    def finish_progress(self, text: Optional[str] = None, delay_ms: int = 1000):
        """Finish the progress and hide the bar.

        Parameters:
            text: Optional completion message to show briefly in the
                footer label.
            delay_ms: Delay before hiding the bar (default 1000ms).
        """
        if text:
            self.setStatusText(text)
        QtCore.QTimer.singleShot(delay_ms, self._on_progress_finished)

    def cancel_progress(self):
        """Cancel the current progress operation."""
        self._progress_bar.cancel()

    def progress(self, total: Optional[int] = 100, text: str = "") -> "FooterProgressContext":
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
        """Handle progress completion - hide the slim bar."""
        self._progress_bar.hide()
        self._progress_bar.reset()

    def _on_hold_started(self, hold_ms: int):
        """Relay the bar's hold hint into the status label."""
        if self._status_before_hold is None:
            self._status_before_hold = self._status_text
        self.setStatusText(f"Hold Esc to cancel… ({hold_ms} ms)")

    def _on_hold_ended(self):
        """Restore the pre-hold status text when Escape is released."""
        if self._status_before_hold is None:
            return
        prior = self._status_before_hold
        self._status_before_hold = None
        self.setStatusText(prior)

    def resizeEvent(self, event):
        """Debounce resize: restart timer on each event so we only
        recalculate font + elision once the user finishes resizing."""
        self._resize_timer.start()
        super().resizeEvent(event)

    def showEvent(self, event):
        """Ensure text is properly sized and elided on first show."""
        super().showEvent(event)
        self._update_font_size()
        self._elide_status_text()

    def _on_resize_settled(self):
        """Called once after resize events stop (debounced)."""
        self._update_font_size()
        self._elide_status_text()

    def _update_font_size(self):
        """Calculate font size for the label relative to widget's height."""
        label_font_size = self.height() * 0.35
        font = self._status_label.font()
        font.setPointSizeF(label_font_size)
        font.setBold(False)
        self._status_label.setFont(font)

    def _elide_status_text(self):
        """Elide the displayed status text to fit available label width."""
        text = self._status_text or self._default_status_text
        if not text:
            self._status_label.setText("")
            return

        fm = QtGui.QFontMetrics(self._status_label.font())
        indent = self._status_label.indent()
        margin = (indent if indent > 0 else 8) * 2
        if self._size_grip:
            margin += self._size_grip.width()
        available = self._stacked_widget.width() - margin

        if available <= 0:
            # Widget not laid out yet; show full text (will be elided on show)
            self._status_label.setText(text)
            return

        elided = fm.elidedText(text, QtCore.Qt.ElideMiddle, available)
        self._status_label.setText(elided)

    def _apply_transparent_style(self):
        """Style children to blend seamlessly with the footer.

        The theme stylesheet (style.qss) sets `padding-right: 10000px`
        and `text-align: right` on horizontal QProgressBars, which
        collapses the chunk's drawable area to zero. The slim indicator
        carries no text and only needs the chunk visible, so we override
        padding/margin and let the theme's chunk color come through.
        """
        bar_style = (
            "QProgressBar {"
            "  background: transparent;"
            "  border: none;"
            "  padding: 0;"
            "  margin: 0;"
            "}"
            "QProgressBar::chunk {"
            "  border: none;"
            "  margin: 0;"
            "}"
        )
        self._stacked_widget.setStyleSheet(
            "QStackedWidget { background: transparent; border: none; }"
        )
        self._status_label.setStyleSheet("background: transparent; border: none;")
        self._progress_bar.setStyleSheet(bar_style)

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

    def __init__(self, footer: Footer, total: Optional[int], text: str):
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
