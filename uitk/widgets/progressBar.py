# !/usr/bin/python
# coding=utf-8
from typing import Optional, Callable
from qtpy import QtWidgets, QtCore
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.shortcuts import GlobalShortcut


class ProgressBar(QtWidgets.QProgressBar, AttributesMixin):
    """A feature-rich progress bar with task execution support.

    Features:
        - Hold Escape to cancel an active task (routed through
          uitk's GlobalShortcut so focus is not required)
        - Context manager support for easy task wrapping
        - Callback-based progress updates
        - Indeterminate / busy mode for tasks without progress signal
        - Auto-hide when complete
        - Optional status text display

    Example:
        # Simple iteration with step()
        for i, item in enumerate(items):
            if not progress_bar.step(i, len(items)):
                break  # Cancelled

        # Context manager with callback
        with progress_bar.task(total=100, text="Processing...") as update:
            for i in range(100):
                update(i + 1)  # Updates progress

        # Async-friendly start/finish
        progress_bar.start_task(total=50, text="Loading...")
        for i in range(50):
            progress_bar.update_progress(i + 1)
        progress_bar.finish_task()
    """

    # Signals
    cancelled = QtCore.Signal()
    started = QtCore.Signal()
    finished = QtCore.Signal()
    progressChanged = QtCore.Signal(int, int)  # current, total
    # Hold-to-cancel signals — let containers (e.g. Footer) display the
    # "Hold Esc to cancel…" hint somewhere visible since this bar might
    # have setTextVisible(False) when used as a thin indicator.
    holdStarted = QtCore.Signal(int)  # cancel_hold_ms
    holdEnded = QtCore.Signal()

    def __init__(
        self,
        parent=None,
        auto_hide=True,
        cancel_hold_ms: int = 500,
        **kwargs,
    ):
        """Initialize the progress bar.

        Parameters:
            parent: Parent widget
            auto_hide: Whether to hide when complete (default True)
            cancel_hold_ms: Time the user must hold Escape to cancel
                an active task. 0 disables hold-to-cancel.
            **kwargs: Additional widget attributes

        Thread-safety: all methods must be called from the main (GUI)
        thread. Touching a QProgressBar from a worker thread will crash.
        """
        super().__init__(parent)

        self._auto_hide = auto_hide
        self._is_cancelled = False
        self._task_text = ""
        self._total = 100
        self._indeterminate = False

        # Hold-to-cancel state. The bar can't reliably receive keyboard
        # focus (especially when embedded in a footer), so we use
        # GlobalShortcut — the same primitive used by marking menus to
        # detect press/release reliably under hosts like Maya.
        self._cancel_hold_ms = max(0, int(cancel_hold_ms))
        self._cancel_timer = QtCore.QTimer(self)
        self._cancel_timer.setSingleShot(True)
        self._cancel_timer.timeout.connect(self._on_cancel_held)
        self._escape_held = False
        self._format_before_hold: Optional[str] = None
        self._cancel_shortcut: Optional[GlobalShortcut] = None  # lazy

        self.setVisible(False)
        self.setTextVisible(True)
        self.setMinimum(0)
        self.setMaximum(100)

        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)

    @property
    def is_cancelled(self) -> bool:
        """Check if the operation was cancelled."""
        return self._is_cancelled

    @property
    def auto_hide(self) -> bool:
        """Get auto-hide setting."""
        return self._auto_hide

    @auto_hide.setter
    def auto_hide(self, value: bool):
        """Set auto-hide behavior."""
        self._auto_hide = value

    def cancel(self):
        """Cancel the current operation."""
        self._is_cancelled = True
        self._disable_cancel_shortcut()
        self.cancelled.emit()
        if self._auto_hide:
            self.hide()

    # ------------------------------------------------------------------
    # Hold-to-cancel (Esc) — routed through uitk's GlobalShortcut so the
    # bar doesn't need keyboard focus and press/release is detected
    # reliably even inside Maya.
    # ------------------------------------------------------------------
    def _enable_cancel_shortcut(self):
        if self._cancel_hold_ms <= 0:
            return
        if self._cancel_shortcut is None:
            self._cancel_shortcut = GlobalShortcut(
                "Esc",
                parent=self,
                context=QtCore.Qt.ApplicationShortcut,
            )
            self._cancel_shortcut.pressed.connect(self._on_escape_pressed)
            self._cancel_shortcut.released.connect(self._on_escape_released)
        self._cancel_shortcut.setEnabled(True)

    def _disable_cancel_shortcut(self):
        if self._cancel_shortcut is not None:
            self._cancel_shortcut.setEnabled(False)
        if self._cancel_timer.isActive():
            self._cancel_timer.stop()
        if self._escape_held and self._format_before_hold is not None:
            self.setFormat(self._format_before_hold)
        self._escape_held = False
        self._format_before_hold = None

    def _on_escape_pressed(self):
        if self._escape_held:
            return
        self._escape_held = True
        self._format_before_hold = self.format()
        # Local format hint (visible only when textVisible=True). Containers
        # using a thin bar without text should listen to holdStarted and
        # display the hint themselves (e.g. in a sibling status label).
        self.setFormat(f"Hold Esc to cancel… ({self._cancel_hold_ms} ms)")
        QtWidgets.QApplication.processEvents()
        self._cancel_timer.start(self._cancel_hold_ms)
        self.holdStarted.emit(self._cancel_hold_ms)

    def _on_escape_released(self):
        if not self._escape_held:
            return
        self._escape_held = False
        self._cancel_timer.stop()
        if self._format_before_hold is not None:
            self.setFormat(self._format_before_hold)
            self._format_before_hold = None
        self.holdEnded.emit()

    def _on_cancel_held(self):
        if self._escape_held:
            self.cancel()

    def reset(self):
        """Reset the progress bar state."""
        self._is_cancelled = False
        self._task_text = ""
        self.setValue(0)
        self.setFormat("%p%")

    def start_task(
        self,
        total: Optional[int] = 100,
        text: str = "",
        show: bool = True,
    ) -> None:
        """Start a new task.

        Parameters:
            total: Total number of steps. Pass None (or <= 0) for an
                indeterminate / busy task — the bar shows a pulsing
                animation and update_progress only affects status text.
            text: Optional status text to display
            show: Whether to show the progress bar
        """
        self.reset()
        self._task_text = text

        if total is None or total <= 0:
            # Qt's busy-indicator mode: min == max == 0.
            self._indeterminate = True
            self._total = 0
            self.setMinimum(0)
            self.setMaximum(0)
            self.setFormat(text if text else "")
        else:
            self._indeterminate = False
            self._total = total
            self.setMinimum(0)
            self.setMaximum(self._total)
            if text:
                self.setFormat(f"{text} - %p%")
            else:
                self.setFormat("%p%")

        if show:
            self.show()
        self._enable_cancel_shortcut()
        self.started.emit()

    def update_progress(
        self,
        value: int,
        text: Optional[str] = None,
    ) -> bool:
        """Update progress value.

        Parameters:
            value: Current progress value (ignored in indeterminate mode
                except as a step counter for the emitted signal).
            text: Optional new status text

        Returns:
            False if cancelled, True otherwise
        """
        if self._is_cancelled:
            return False

        if not self._indeterminate:
            self.setValue(min(value, self._total))

        if text is not None:
            self._task_text = text
            # Skip the hold-to-cancel format swap while the user is
            # mid-hold; the override is restored on key release.
            if not self._escape_held:
                if self._indeterminate:
                    self.setFormat(text)
                else:
                    self.setFormat(f"{text} - %p%")

        self.progressChanged.emit(value, self._total)
        QtWidgets.QApplication.processEvents()
        return True

    def finish_task(self, text: Optional[str] = None):
        """Complete the current task.

        Parameters:
            text: Optional completion message
        """
        self._disable_cancel_shortcut()
        if self._indeterminate:
            # Snap to a full determinate bar so the completion message
            # has somewhere to live (Qt's busy mode hides the format).
            self.setMaximum(1)
            self.setValue(1)
            self._indeterminate = False

        self.setValue(self._total if self._total > 0 else 1)

        if text:
            self.setFormat(text)
        else:
            self.setFormat("Complete")

        self.finished.emit()

        if self._auto_hide:
            # Delay hide slightly so user sees completion
            QtCore.QTimer.singleShot(500, self.hide)

    def step(self, progress: int, length: int = 100) -> bool:
        """Legacy step method for backward compatibility.

        Parameters:
            progress: Current step (0-based index)
            length: Total number of steps

        Returns:
            False if cancelled, True otherwise
        """
        if self._is_cancelled:
            return False

        if not self.isVisible():
            self.start_task(total=length)

        # Convert 0-based index to 1-based progress
        current = progress + 1
        self.update_progress(current)

        if current >= length:
            self.finish_task()

        return True

    def task(
        self,
        total: Optional[int] = 100,
        text: str = "",
    ) -> "ProgressTaskContext":
        """Context manager for progress tracking.

        Parameters:
            total: Total number of steps. None (or <= 0) → indeterminate.
            text: Optional status text

        Returns:
            Context manager that provides an update callback

        Example:
            with progress_bar.task(total=100, text="Processing") as update:
                for i in range(100):
                    if not update(i + 1):
                        break  # Cancelled
        """
        return ProgressTaskContext(self, total, text)

    def showEvent(self, event):
        """Handle show event."""
        self._is_cancelled = False
        super().showEvent(event)

    # NOTE: Escape is handled by the GlobalShortcut enabled during
    # start_task(), so keyPressEvent doesn't need to special-case it.
    # Local key handling is left to the base class.


class ProgressTaskContext:
    """Context manager for progress bar tasks."""

    def __init__(self, progress_bar: ProgressBar, total: Optional[int], text: str):
        self._progress_bar = progress_bar
        self._total = total
        self._text = text

    def __enter__(self) -> Callable[[int, Optional[str]], bool]:
        """Start the task and return update callback."""
        self._progress_bar.start_task(self._total, self._text)
        return self._update

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finish the task."""
        if exc_type is None and not self._progress_bar.is_cancelled:
            self._progress_bar.finish_task()
        elif self._progress_bar.auto_hide:
            self._progress_bar.hide()
        return False

    def _update(self, value: int, text: Optional[str] = None) -> bool:
        """Update progress."""
        return self._progress_bar.update_progress(value, text)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import time

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(window)

    progress = ProgressBar(auto_hide=False)
    layout.addWidget(progress)

    btn = QtWidgets.QPushButton("Run Task")
    layout.addWidget(btn)

    def run_task():
        with progress.task(total=50, text="Processing") as update:
            for i in range(50):
                if not update(i + 1):
                    print("Cancelled!")
                    break
                time.sleep(0.05)

    btn.clicked.connect(run_task)

    window.resize(300, 100)
    window.show()
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
