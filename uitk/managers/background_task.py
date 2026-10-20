# !/usr/bin/python
# coding=utf-8
"""Work on a background thread, its outcome read back on the UI thread."""

import threading
from typing import Any, Callable, Dict, Optional

from qtpy import QtCore


class BackgroundTask:
    """Runs *work* on a daemon thread; the UI thread reads what it returned or raised.

    For what waits seconds or minutes -- a service starting, a render, a share
    resolving -- that on the UI thread would freeze the panel and the DCC
    hosting it. Nothing crosses threads but the outcome: *work* touches no
    widget, and :meth:`when_done` calls back on the UI thread.

    Parameters:
        work: ``() -> value``, run once on the thread.
        name: The thread's name (seen in a debugger and a crash report).

    Example:
        >>> task = BackgroundTask(lambda: service.start(), name="start-service")
        >>> task.when_done(panel, lambda: label.setText(str(task.result())))
    """

    #: Milliseconds between :meth:`when_done`'s looks at the thread.
    POLL_MS = 250

    def __init__(self, work: Callable[[], Any], name: str):
        self._outcome: Dict[str, Any] = {}
        self._thread = threading.Thread(
            target=self._run, args=(work,), name=name, daemon=True
        )
        self._thread.start()

    def _run(self, work) -> None:
        try:
            self._outcome["value"] = work()
        except BaseException as error:  # noqa: BLE001 -- re-raised by result()
            self._outcome["error"] = error

    @property
    def done(self) -> bool:
        """Whether *work* has ended (returned or raised)."""
        return not self._thread.is_alive()

    def wait(self, seconds: float) -> None:
        """Block up to *seconds* for *work* to end (a test, a shutdown)."""
        self._thread.join(seconds)

    def result(self) -> Any:
        """What *work* returned; re-raises what it raised."""
        if "error" in self._outcome:
            raise self._outcome["error"]
        return self._outcome["value"]

    def when_done(
        self,
        parent: QtCore.QObject,
        callback: Callable[[], None],
        poll_ms: Optional[int] = None,
    ) -> None:
        """*callback* on the UI thread once *work* ends, off a timer *parent*
        owns (it stops with *parent*). *poll_ms*: how often to look (default
        :attr:`POLL_MS`) -- shorter for a result the user is waiting to see."""
        timer = QtCore.QTimer(parent)
        timer.setInterval(self.POLL_MS if poll_ms is None else int(poll_ms))

        def check() -> None:
            if self.done:
                timer.stop()
                timer.deleteLater()
                callback()

        timer.timeout.connect(check)
        timer.start()
