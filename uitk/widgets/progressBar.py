# !/usr/bin/python
# coding=utf-8
from typing import Optional, Callable
from qtpy import QtWidgets, QtCore
from uitk.widgets.mixins.attributes import AttributesMixin


class ProgressBar(QtWidgets.QProgressBar, AttributesMixin):
    """A feature-rich progress bar with task execution support.

    Features:
        - Cancellable operations via Escape key
        - Context manager support for easy task wrapping
        - Callback-based progress updates
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

    def __init__(self, parent=None, auto_hide=True, **kwargs):
        """Initialize the progress bar.

        Parameters:
            parent: Parent widget
            auto_hide: Whether to hide when complete (default True)
            **kwargs: Additional widget attributes
        """
        super().__init__(parent)

        self._auto_hide = auto_hide
        self._is_cancelled = False
        self._task_text = ""
        self._total = 100

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
        self.cancelled.emit()
        if self._auto_hide:
            self.hide()

    def reset(self):
        """Reset the progress bar state."""
        self._is_cancelled = False
        self._task_text = ""
        self.setValue(0)
        self.setFormat("%p%")

    def start_task(
        self,
        total: int = 100,
        text: str = "",
        show: bool = True,
    ) -> None:
        """Start a new task.

        Parameters:
            total: Total number of steps
            text: Optional status text to display
            show: Whether to show the progress bar
        """
        self.reset()
        self._total = max(1, total)
        self._task_text = text
        self.setMaximum(self._total)

        if text:
            self.setFormat(f"{text} - %p%")
        else:
            self.setFormat("%p%")

        if show:
            self.show()
        self.started.emit()

    def update_progress(
        self,
        value: int,
        text: Optional[str] = None,
    ) -> bool:
        """Update progress value.

        Parameters:
            value: Current progress value
            text: Optional new status text

        Returns:
            False if cancelled, True otherwise
        """
        if self._is_cancelled:
            return False

        self.setValue(min(value, self._total))

        if text is not None:
            self._task_text = text
            self.setFormat(f"{text} - %p%")

        self.progressChanged.emit(value, self._total)
        QtWidgets.QApplication.processEvents()
        return True

    def finish_task(self, text: Optional[str] = None):
        """Complete the current task.

        Parameters:
            text: Optional completion message
        """
        self.setValue(self._total)

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
        total: int = 100,
        text: str = "",
    ) -> "ProgressTaskContext":
        """Context manager for progress tracking.

        Parameters:
            total: Total number of steps
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

    def keyPressEvent(self, event):
        """Handle key press - Escape to cancel."""
        if event.key() == QtCore.Qt.Key_Escape:
            self.cancel()
        else:
            super().keyPressEvent(event)


class ProgressTaskContext:
    """Context manager for progress bar tasks."""

    def __init__(self, progress_bar: ProgressBar, total: int, text: str):
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
        elif self._progress_bar._auto_hide:
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
