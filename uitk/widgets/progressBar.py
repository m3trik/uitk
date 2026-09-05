# !/usr/bin/python
# coding=utf-8
from typing import Optional, Callable
from qtpy import QtWidgets, QtCore
import pythontk as ptk
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.managers.shortcut_manager import GlobalShortcut
from uitk.managers.cancel_manager import CancelManager


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

    Cancellation
    ------------
    The bar does not own its cancelled state — a
    :class:`~pythontk.CancelScope` does, and the bar is one of several things
    that can set it. ``start_task`` **adopts the ambient scope** when one is
    active (the slot dispatcher activates one for ``@Cancelable`` slots), so
    Esc held over the bar, Esc peeked natively by the host mid-crunch, and the
    long-execution dialog's *Cancel* button all resolve to the same flag, and
    ``update()`` reports it regardless of which one the user reached for.
    Without an ambient scope the bar creates its own, so standalone use is
    unchanged.

    Which Esc actually fires depends on the host. Standalone, it is the
    ``GlobalShortcut`` below, delivered by the event pump each tick drives.
    Under a DCC provider that sets ``exclude_user_input`` (Maya, Blender) the
    pump no longer delivers key events — deliberately, so a tick cannot
    dispatch a queued click into a nested slot — and the scope's
    pump-independent sources take over: the host's own peek plus a key-hold
    probe, both polled here at the same tick. The hold duration matches, so
    the gesture is identical; only the "Hold Esc to cancel…" hint moves, from
    this widget to the host's own progress UI.

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

    # Qt Designer widget-box entry.
    designer_spec = {"icon": "activity", "object_name": "progressBar"}

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
        self._scope: Optional[ptk.CancelScope] = None
        self._task_text = ""
        self._host_label = ""
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
    def scope(self) -> Optional["ptk.CancelScope"]:
        """The :class:`~pythontk.CancelScope` governing the current task.

        ``None`` until :meth:`start_task` runs. Slots rarely need this — the
        ``update()`` return value and ``ptk.CancelScope.check()`` cover both
        consumption styles — but host code that wants to add its own pull
        source can reach it here.
        """
        return self._scope

    @property
    def is_cancelled(self) -> bool:
        """Check if the operation was cancelled.

        Flag read only: never polls the scope's sources, so it stays safe to
        call from a paint path or a non-owner thread.
        """
        return bool(self._scope is not None and self._scope.cancelled)

    @property
    def auto_hide(self) -> bool:
        """Get auto-hide setting."""
        return self._auto_hide

    @auto_hide.setter
    def auto_hide(self, value: bool):
        """Set auto-hide behavior."""
        self._auto_hide = value

    def getCancelHoldMs(self) -> int:
        """Milliseconds Escape must be held to cancel (0 disables hold-to-cancel)."""
        return self._cancel_hold_ms

    def setCancelHoldMs(self, value: int) -> None:
        """Set the hold-to-cancel duration. Negative values clamp to 0."""
        self._cancel_hold_ms = max(0, int(value))

    def setAutoHide(self, value: bool) -> None:
        """Set auto-hide (Qt-property setter for :attr:`auto_hide`).

        Named for the ``autoHide`` property: ``pyside6-uic`` compiles a ``.ui``
        property into a ``set<Name>`` call, so the pair has to exist.
        """
        self.auto_hide = bool(value)

    # Qt-property mirrors of the two construction options, so both are editable
    # in Designer and round-trip through a ``.ui`` file. ``auto_hide`` above
    # stays the Python-facing name.
    autoHide = QtCore.Property(bool, fget=lambda self: self.auto_hide, fset=setAutoHide)
    cancelHoldMs = QtCore.Property(int, fget=getCancelHoldMs, fset=setCancelHoldMs)

    def cancel(self, reason: str = "progress-bar"):
        """Cancel the current operation.

        Flags the governing scope (creating one if the bar has no task yet, so
        a pre-emptive cancel is not silently dropped) and tears down the Esc
        shortcut. Safe to call repeatedly.
        """
        if self._scope is None:
            self._scope = CancelManager.new_scope(self._task_text or "task")
        self._scope.cancel(reason)
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
            self.cancel("escape-hold")

    def reset(self):
        """Reset the progress bar state.

        Drops the scope reference rather than clearing the scope itself: the
        scope may be owned by an enclosing ``@Cancelable`` slot, and wiping a
        cancel the user already requested would restart work they stopped.

        Also releases the app-wide Esc shortcut ``start_task`` armed. A
        container that ends a task through ``reset()`` rather than
        ``finish_task`` (:class:`~uitk.widgets.footer.Footer` does) otherwise
        left it listening, and a later Esc-hold anywhere in the host fired
        ``cancel()`` on a task that was long over. ``start_task`` re-arms it
        right after resetting.
        """
        self._disable_cancel_shortcut()
        self._scope = None
        self._task_text = ""
        self.setValue(0)
        self.setFormat("%p%")

    def set_total(self, total: int) -> None:
        """Adjust the task total mid-flight.

        Used by :func:`uitk.switchboard.utils.SwitchboardUtilsMixin.progress_adapter`
        to auto-correct the bar's max when a downstream
        ``progress_callback(current, total, message)`` reports a
        ``total`` that differs from what the slot set at ``start_task``
        time. Switches out of indeterminate mode when the bar was
        pulsing, so slots can simply ``with sb.progress(text=...)``
        without pre-knowing the loop size.

        No-op when *total* is non-positive or already matches the
        bar's current state.
        """
        if total is None or total <= 0:
            return
        if self._total == total and not self._indeterminate:
            return
        self._indeterminate = False
        self._total = total
        self.setMinimum(0)
        self.setMaximum(total)
        # Skip the format swap while the user is mid-hold; the held hint
        # owns the format until release, when ``_on_escape_released``
        # restores ``_format_before_hold``. We update the saved format
        # instead so release reflects the new total.
        determinate_format = f"{self._task_text} - %p%" if self._task_text else "%p%"
        if self._escape_held:
            self._format_before_hold = determinate_format
        else:
            self.setFormat(determinate_format)

    def start_task(
        self,
        total: Optional[int] = 100,
        text: str = "",
        show: bool = True,
        scope: Optional["ptk.CancelScope"] = None,
        host_label: Optional[str] = None,
    ) -> None:
        """Start a new task.

        Parameters:
            total: Total number of steps. Pass None (or <= 0) for an
                indeterminate / busy task — the bar shows a pulsing
                animation and update_progress only affects status text.
            text: Optional status text to display
            show: Whether to show the progress bar
            scope: Explicit :class:`~pythontk.CancelScope` to report into.
                Defaults to the ambient scope (so a ``@Cancelable`` slot's
                Esc and this bar's Esc are the same cancel), and failing
                that a fresh host-wired scope of its own.
            host_label: Label to mirror into host-native progress UI.
                Defaults to *text*. Containers that show the label
                elsewhere pass ``text=""`` to keep it off the bar itself
                (:class:`Footer` does) — without this they would also
                blank it in the host, which is the one place a
                marking-menu slot's progress is still visible after its
                window closes.
        """
        self.reset()
        self._scope = (
            scope
            or ptk.CancelScope.current()
            or CancelManager.new_scope(text or host_label or "task")
        )
        self._host_label = host_label if host_label is not None else text
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
        """Update progress value — and reach a cancellation checkpoint.

        This is the ecosystem's canonical checkpoint: the tick that repaints
        the bar is the same tick that polls the host for a cancel request, so
        any loop already reporting progress is already cancellable, with no
        extra call and no scope parameter to thread through.

        Parameters:
            value: Current progress value (ignored in indeterminate mode
                except as a step counter for the emitted signal).
            text: Optional new status text

        Returns:
            False if cancelled, True otherwise
        """
        if self._scope is not None and self._scope.cancelled:
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

        provider = CancelManager.provider()
        # Mirror into host-native UI (Maya's main progress bar) before the
        # pump, so a slot whose own window has already closed — the marking
        # menu case — still shows progress somewhere visible.
        try:
            provider.tick(value, self._total, self._task_text or self._host_label)
        except Exception:
            pass

        try:
            provider.pump()
        except Exception:
            # Mirror the provider's input policy even here. A bare
            # processEvents() dispatches queued INPUT, which is precisely the
            # "click lands mid-slot and runs a second slot against half-mutated
            # scene state" hole that exclude_user_input exists to close -- so a
            # provider failing on its own pump must not silently downgrade to
            # the unsafe one under a DCC.
            app = QtWidgets.QApplication.instance()
            if app is not None:
                if getattr(provider, "exclude_user_input", False):
                    app.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
                else:
                    app.processEvents()

        # Poll last: the pump may have delivered the Esc shortcut, and the
        # host peek is cheapest right after the UI has been serviced.
        if self._scope is not None:
            return self._scope.tick()
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
        if self.is_cancelled:
            return False

        if not self.isVisible():
            self.start_task(total=length)

        # Convert 0-based index to 1-based progress
        current = progress + 1
        alive = self.update_progress(current)

        if current >= length:
            self.finish_task()

        return alive

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
        """Handle show event.

        Deliberately does *not* clear cancellation: the state lives on the
        scope, which may be the enclosing slot's, and being re-shown is not the
        user retracting a cancel. :meth:`start_task` is the reset point.
        """
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
        else:
            # Exception or cancellation: finish_task() (which tears down the
            # app-wide Esc GlobalShortcut enabled by start_task) does not run
            # here, so disable it explicitly — otherwise a later Esc-hold
            # anywhere in the host app fires cancel() on this dead task. The
            # call is idempotent, so a prior cancel() disabling it is harmless.
            self._progress_bar._disable_cancel_shortcut()
            if self._progress_bar.auto_hide:
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
