# coding=utf-8
"""Qt-side audio scrub/playback helper for :class:`SequencerWidget`.

Plays a pre-mixed audio file (typically a composite WAV) in response
to playhead motion.  Each ``play_at_frame`` seeks the source and starts
a short grain window that auto-stops via a one-shot timer — rapid
drags stitch into continuous scrub-like audio.

Gracefully degrades to a no-op when ``QtMultimedia`` is not importable
in the host's Python environment.

Example
-------
>>> from uitk.widgets.sequencer import SequencerWidget
>>> w = SequencerWidget()
>>> w.set_audio_source("/path/to/composite.wav", fps=24.0)
>>> # Dragging the ruler now emits audible scrub automatically.
"""
from __future__ import annotations

import os
from typing import Optional

from qtpy import QtCore

try:
    from qtpy.QtMultimedia import QMediaPlayer, QAudioOutput

    _QT_MEDIA_OK = True
except Exception:
    QMediaPlayer = None
    QAudioOutput = None
    _QT_MEDIA_OK = False


class ScrubPlayer(QtCore.QObject):
    """Seek-and-grain player for NLE-style audio scrub.

    Parameters
    ----------
    parent : QObject, optional
        Qt parent (typically the :class:`SequencerWidget`).
    grain_ms : int
        Playback window per scrub event in milliseconds.  Shorter =
        tighter scrub, longer = smoother but laggier.
    """

    _GRAIN_MS_DEFAULT = 120

    def __init__(
        self,
        parent: Optional[QtCore.QObject] = None,
        grain_ms: int = _GRAIN_MS_DEFAULT,
    ):
        super().__init__(parent)
        self._grain_ms = int(grain_ms)
        self._player: Optional[QMediaPlayer] = None
        self._output: Optional[QAudioOutput] = None
        self._source_path: str = ""
        self._grain_timer: Optional[QtCore.QTimer] = None
        self._enabled = _QT_MEDIA_OK

    @property
    def available(self) -> bool:
        """True if ``QtMultimedia`` is importable in this environment."""
        return self._enabled

    @property
    def source_path(self) -> str:
        """Current source path, or empty string."""
        return self._source_path

    # ------------------------------------------------------------------
    # Source management
    # ------------------------------------------------------------------

    def set_source(self, path: str) -> bool:
        """Point the player at an audio file.  Returns True on success.

        No-op when ``path`` matches the current source, so callers can
        invoke this on every scrub without overhead.
        """
        if not self._enabled:
            return False
        path = (path or "").replace("\\", "/")
        if not path or not os.path.isfile(path):
            return False
        if path == self._source_path and self._player is not None:
            return True
        self._ensure_player()
        self._player.setSource(QtCore.QUrl.fromLocalFile(path))
        self._source_path = path
        return True

    def clear_source(self) -> None:
        """Drop the current source and stop playback."""
        self._source_path = ""
        if self._player is not None:
            try:
                self._player.stop()
                self._player.setSource(QtCore.QUrl())
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def play_at_frame(self, frame: float, fps: float) -> None:
        """Seek to ``frame`` and play a short grain for scrub feedback."""
        if not self._enabled or self._player is None or not self._source_path:
            return
        if fps <= 0:
            return
        position_ms = max(0, int(round((float(frame) / float(fps)) * 1000.0)))
        try:
            # Stop the in-flight grain so the new seek takes effect
            # promptly; otherwise overlapping grains stack audibly.
            self._player.stop()
            self._player.setPosition(position_ms)
            self._player.play()
            self._ensure_grain_timer()
            self._grain_timer.start(self._grain_ms)
        except Exception:
            pass

    def play(self, from_frame: Optional[float] = None, fps: float = 24.0) -> None:
        """Transport play from ``from_frame`` (or current position)."""
        if not self._enabled or self._player is None or not self._source_path:
            return
        try:
            if from_frame is not None and fps > 0:
                self._player.setPosition(
                    max(0, int(round((float(from_frame) / float(fps)) * 1000.0)))
                )
            self._player.play()
            if self._grain_timer is not None:
                self._grain_timer.stop()
        except Exception:
            pass

    def stop(self) -> None:
        """Stop playback and cancel any pending grain timeout."""
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass
        if self._grain_timer is not None:
            self._grain_timer.stop()

    def set_volume(self, vol: float) -> None:
        """Volume in [0.0, 1.0]."""
        if self._output is not None:
            try:
                self._output.setVolume(max(0.0, min(1.0, float(vol))))
            except Exception:
                pass

    def set_grain_ms(self, grain_ms: int) -> None:
        """Override the grain window length at runtime."""
        self._grain_ms = max(1, int(grain_ms))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_player(self) -> None:
        if self._player is not None:
            return
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        self._output.setVolume(1.0)

    def _ensure_grain_timer(self) -> None:
        if self._grain_timer is not None:
            return
        self._grain_timer = QtCore.QTimer(self)
        self._grain_timer.setSingleShot(True)
        self._grain_timer.timeout.connect(self._on_grain_timeout)

    def _on_grain_timeout(self) -> None:
        if self._player is None:
            return
        try:
            self._player.stop()
        except Exception:
            pass
