# coding=utf-8
"""Reusable Maya-style transport controls for :class:`SequencerWidget`.

Provides an 8-button row (go-to-start, prev key, step back, play back,
play forward, step forward, next key, go-to-end) that mirrors Maya's
Time Slider transport.  Frame/key navigation routes through the host
:class:`SequencerWidget` so its ``playhead_moved`` signal fires — which
in turn drives scrub audio via :class:`ScrubPlayer`.

Play/stop are delegated to a pluggable *play controller*: a small
object exposing ``is_playing()``, ``play(forward: bool)`` and
``stop()``.  Hosts with their own playback engine (Maya, Houdini, …)
supply one; in pure-Qt use, a :class:`ScrubPlayerPlayController` wraps
the widget's :class:`ScrubPlayer` for stand-alone audio playback.

``interrupt_mode`` controls what happens when the user hits step/key/
go-to while playback is running:

- ``"stop"``   — stop playback, perform the action. (default)
- ``"resume"`` — stop, perform the action, resume in the same
                 direction from the new frame.
- ``"none"``   — do the action without touching playback.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional, Protocol

from qtpy import QtCore, QtGui, QtWidgets


class PlayController(Protocol):
    """Minimal transport API the controls drive."""

    def is_playing(self) -> bool: ...
    def play(self, forward: bool) -> None: ...
    def stop(self) -> None: ...


class ScrubPlayerPlayController:
    """Default :class:`PlayController` backed by the sequencer's ScrubPlayer.

    Used when the sequencer is running stand-alone (no DCC).  Plays the
    currently bound audio source forward from the widget's playhead.
    Backward "play" is not audibly supported by Qt media — it falls
    back to a silent no-op transport state tracked by this adapter so
    the UI still toggles consistently.
    """

    def __init__(self, sequencer, fps: float = 24.0):
        self._sequencer = sequencer
        self._fps = float(fps) if fps and fps > 0 else 24.0
        self._playing = False
        self._forward = True

    def set_fps(self, fps: float) -> None:
        if fps and fps > 0:
            self._fps = float(fps)

    def _fps_now(self) -> float:
        """The widget's live audio fps wins over the constructor default —
        ``set_audio_source(path, fps=30)`` must drive seek math too, or
        the playhead frame maps to the wrong audio position."""
        fps = getattr(self._sequencer, "_audio_fps", None)
        return float(fps) if fps and fps > 0 else self._fps

    def is_playing(self) -> bool:
        if not self._playing:
            return False
        # Reconcile with the actual media state — end-of-media stops the
        # player without notifying this adapter; a latched True keeps
        # the play button tinted and turns the next press into a no-op
        # stop().
        player = getattr(self._sequencer, "_scrub_player", None)
        if player is not None and self._forward:
            probe = getattr(player, "is_playing", None)
            if callable(probe):
                self._playing = bool(probe())
        return self._playing

    def play(self, forward: bool) -> None:
        player = getattr(self._sequencer, "_scrub_player", None)
        t = self._current_frame()
        if player is not None and forward:
            player.play(from_frame=t, fps=self._fps_now())
        self._playing = True
        self._forward = forward

    def stop(self) -> None:
        player = getattr(self._sequencer, "_scrub_player", None)
        if player is not None:
            player.stop()
        self._playing = False

    def _current_frame(self) -> float:
        try:
            return float(self._sequencer._timeline._scene.playhead.time)
        except Exception:
            return 0.0


def _remove_play_shortcuts(mgr, owned) -> None:
    """Remove the Space / Alt+Space bindings in *owned* (``{seq: QShortcut}``)
    from *mgr*, but only where the manager still holds that exact shortcut —
    a newer transport may have replaced it.  Free function (not a bound
    method) so a ``destroyed`` connection forms no reference cycle through
    the transport widget.
    """
    if mgr is None:
        return
    for key, sc in owned.items():
        try:
            entry = mgr.shortcuts.get(key)
            if entry is not None and entry.get("shortcut") is sc:
                mgr.remove_shortcut(key)
        except (RuntimeError, TypeError):
            pass


class TransportControls(QtWidgets.QWidget):
    """Maya-style 8-button transport row bound to a :class:`SequencerWidget`.

    Parameters
    ----------
    sequencer : SequencerWidget
        Timeline whose playhead the controls drive.
    play_controller : PlayController, optional
        Play/stop backend.  Defaults to :class:`ScrubPlayerPlayController`.
    parent : QWidget, optional
    button_height : int, optional
        Uniform button height.  Width is ``height + 2``; icons are
        ``int(height * 0.7)``.  Defaults to 20.
    interrupt_mode : {"stop", "resume", "none"}
        How step/key/go-to behave while playback is running.
    """

    INTERRUPT_STOP = "stop"
    INTERRUPT_RESUME = "resume"
    INTERRUPT_NONE = "none"

    ACTIVE_COLOR = "#55cc55"  # green tint applied to the active play button

    play_state_changed = QtCore.Signal(bool)

    def __init__(
        self,
        sequencer,
        play_controller: Optional[PlayController] = None,
        parent: Optional[QtWidgets.QWidget] = None,
        button_height: int = 20,
        interrupt_mode: str = INTERRUPT_STOP,
        range_fn: Optional[Callable[[], tuple]] = None,
        button_names: Optional[Iterable[str]] = None,
    ):
        super().__init__(parent)
        self._sequencer = sequencer
        self._play_controller: PlayController = (
            play_controller or ScrubPlayerPlayController(sequencer)
        )
        self._interrupt_mode = interrupt_mode
        self._range_fn = range_fn
        self._button_names = (
            tuple(button_names)
            if button_names is not None
            else tuple(k for k, *_ in self._SPECS)
        )
        unknown = set(self._button_names) - {k for k, *_ in self._SPECS}
        if unknown:
            raise ValueError(f"unknown button names: {sorted(unknown)}")
        self._buttons: dict[str, QtWidgets.QToolButton] = {}
        self._icon_size: tuple = (16, 16)
        self._button_height = button_height
        self._last_play_forward = True  # direction of most recent play(...)
        self._active_play_key: Optional[str] = None
        self._build(button_height)

        # Poll the play controller so external play/stop (e.g. Maya's
        # own time slider) keeps the active-button tint in sync.  The
        # timer runs only while visible (see show/hideEvent) — a hidden
        # panel must not keep polling the host app every 400ms.
        self._sync_timer = QtCore.QTimer(self)
        self._sync_timer.setInterval(400)
        self._sync_timer.timeout.connect(self._sync_active_from_controller)

        # QShortcut objects this row registered on the host sequencer's
        # manager, keyed by sequence.  Tracked so recreating the row (or
        # destroying it) can tear its own bindings down instead of leaving
        # a stale, ambiguous QShortcut alive on the sequencer.
        self._play_shortcuts: dict = {}
        self._register_play_shortcuts()
        # Drop our bindings if this row is destroyed without a replacement,
        # so the sequencer isn't left with a Space shortcut whose callback
        # points into a deleted transport.  Capture the manager + owned
        # shortcuts (not ``self``) so the connection forms no reference
        # cycle through the widget.
        _mgr = getattr(self._sequencer, "_shortcut_mgr", None)
        _owned = dict(self._play_shortcuts)
        self.destroyed.connect(lambda *_: _remove_play_shortcuts(_mgr, _owned))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._sync_timer.stop()

    # ------------------------------------------------------------------ API

    @property
    def play_controller(self) -> PlayController:
        return self._play_controller

    def set_play_controller(self, pc: PlayController) -> None:
        self._play_controller = pc

    def set_interrupt_mode(self, mode: str) -> None:
        if mode not in (self.INTERRUPT_STOP, self.INTERRUPT_RESUME, self.INTERRUPT_NONE):
            raise ValueError(f"invalid interrupt_mode: {mode!r}")
        self._interrupt_mode = mode

    def interrupt_mode(self) -> str:
        return self._interrupt_mode

    def button(self, name: str) -> Optional[QtWidgets.QToolButton]:
        """Lookup a button by name (e.g. ``'play_forward'``)."""
        return self._buttons.get(name)

    # --------------------------------------------------------------- build

    _SPECS = (
        ("go_to_start",   "transport_start",        "Go to start of playback range"),
        ("prev_key",      "transport_prev_key",     "Previous key"),
        ("step_back",     "transport_step_back",    "Step back one frame"),
        ("play_back",     "transport_play_back",    "Play backwards"),
        ("play_forward",  "transport_play_forward", "Play forwards"),
        ("step_forward",  "transport_step_forward", "Step forward one frame"),
        ("next_key",      "transport_next_key",     "Next key"),
        ("go_to_end",     "transport_end",          "Go to end of playback range"),
    )

    def _build(self, h: int) -> None:
        from uitk.widgets.mixins.icon_manager import IconManager

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        icon_size = max(8, int(h * 0.7))
        self._icon_size = (icon_size, icon_size)
        dispatch: dict[str, Callable[[], None]] = {
            "go_to_start":  self._on_go_to_start,
            "prev_key":     self._on_prev_key,
            "step_back":    self._on_step_back,
            "play_back":    self._on_play_back,
            "play_forward": self._on_play_forward,
            "step_forward": self._on_step_forward,
            "next_key":     self._on_next_key,
            "go_to_end":    self._on_go_to_end,
        }

        spec_by_key = {k: (icon_name, tip) for k, icon_name, tip in self._SPECS}
        for key in self._button_names:
            icon_name, tip = spec_by_key[key]
            btn = QtWidgets.QToolButton(self)
            btn.setAutoRaise(True)
            btn.setFixedSize(h + 2, h)
            btn.setCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))
            btn.setToolTip(tip)
            IconManager.set_icon(btn, icon_name, size=(icon_size, icon_size))
            btn.setProperty("_icon_name", icon_name)
            btn.clicked.connect(dispatch[key])
            layout.addWidget(btn)
            self._buttons[key] = btn

    # ----------------------------------------------------- nav primitives

    def _with_interrupt(self, action: Callable[[], None]) -> None:
        """Run *action*, optionally stopping/resuming playback around it."""
        pc = self._play_controller
        try:
            was_playing = bool(pc.is_playing())
        except Exception:
            was_playing = False

        mode = self._interrupt_mode
        forward = self._last_play_forward
        if was_playing and mode != self.INTERRUPT_NONE:
            try:
                pc.stop()
            except Exception:
                pass
            self._set_play_active(None)
            self.play_state_changed.emit(False)

        action()

        if was_playing and mode == self.INTERRUPT_RESUME:
            try:
                pc.play(forward=forward)
            except Exception:
                pass
            self._set_play_active("play_forward" if forward else "play_back")
            self.play_state_changed.emit(True)

    # ------------------------------------------------------------ handlers

    def _on_go_to_start(self) -> None:
        def action():
            if self._range_fn is not None:
                try:
                    lo, _ = self._range_fn()
                    self._sequencer._move_playhead(float(lo))
                    return
                except Exception:
                    pass
            self._sequencer.go_to_start()
        self._with_interrupt(action)

    def _on_go_to_end(self) -> None:
        def action():
            if self._range_fn is not None:
                try:
                    _, hi = self._range_fn()
                    self._sequencer._move_playhead(float(hi))
                    return
                except Exception:
                    pass
            self._sequencer.go_to_end()
        self._with_interrupt(action)

    def _on_step_back(self) -> None:
        self._with_interrupt(lambda: self._sequencer.step_backward())

    def _on_step_forward(self) -> None:
        self._with_interrupt(lambda: self._sequencer.step_forward())

    def _on_prev_key(self) -> None:
        self._with_interrupt(lambda: self._sequencer.go_to_prev_key())

    def _on_next_key(self) -> None:
        self._with_interrupt(lambda: self._sequencer.go_to_next_key())

    def _on_play_forward(self) -> None:
        self._toggle_play(forward=True)

    def _on_play_back(self) -> None:
        self._toggle_play(forward=False)

    def _toggle_play(self, forward: bool) -> None:
        pc = self._play_controller
        try:
            playing = bool(pc.is_playing())
        except Exception:
            playing = False
        try:
            if playing:
                pc.stop()
                self._set_play_active(None)
                self.play_state_changed.emit(False)
            else:
                pc.play(forward=forward)
                self._last_play_forward = bool(forward)
                self._set_play_active("play_forward" if forward else "play_back")
                self.play_state_changed.emit(True)
        except Exception:
            pass

    def _set_play_active(self, active_key: Optional[str]) -> None:
        """Tint the active play button green; restore the other."""
        from uitk.widgets.mixins.icon_manager import IconManager

        self._active_play_key = active_key
        for key in ("play_forward", "play_back"):
            btn = self._buttons.get(key)
            if btn is None:
                continue
            icon_name = btn.property("_icon_name")
            if not icon_name:
                continue
            if key == active_key:
                IconManager.set_icon(
                    btn, icon_name, size=self._icon_size,
                    color=self.ACTIVE_COLOR, auto_theme=False,
                )
            else:
                # Re-resolve theme color
                IconManager.set_icon(btn, icon_name, size=self._icon_size)

    def _sync_active_from_controller(self) -> None:
        """Reconcile tint with the play controller's actual state."""
        try:
            playing = bool(self._play_controller.is_playing())
        except Exception:
            return
        if not playing:
            if self._active_play_key is not None:
                self._set_play_active(None)
            return
        # Playing externally — keep whichever direction we last saw.
        expected = "play_forward" if self._last_play_forward else "play_back"
        if self._active_play_key != expected:
            self._set_play_active(expected)

    # ----------------------------------------------------------- shortcuts

    _PLAY_KEYS = ("Space", "Alt+Space")

    def _register_play_shortcuts(self) -> None:
        """Register Space / Alt+Space on the sequencer's shortcut manager.

        Space toggles play-forward; Alt+Space toggles play-backward.  If the
        sequencer has no ``_shortcut_mgr`` attribute, this is a no-op.

        Idempotent: any existing Space / Alt+Space binding is disposed first
        — whether this row's own from a prior call, or one a previously
        created transport left behind.  Without that teardown, recreating the
        transport stacks a second ``QShortcut`` on the same sequence and Qt
        marks it ambiguous ("Ambiguous shortcut overload") and fires neither.
        """
        mgr = getattr(self._sequencer, "_shortcut_mgr", None)
        if mgr is None:
            self._play_shortcuts = {}
            return
        for key in self._PLAY_KEYS:
            try:
                mgr.remove_shortcut(key)
            except (RuntimeError, TypeError):
                pass
        ctx = QtCore.Qt.WidgetWithChildrenShortcut
        specs = {
            "Space": (lambda: self._toggle_play(forward=True), "Play / stop playback"),
            "Alt+Space": (
                lambda: self._toggle_play(forward=False),
                "Play / stop backward",
            ),
        }
        self._play_shortcuts = {}
        for key in self._PLAY_KEYS:
            action, desc = specs[key]
            try:
                self._play_shortcuts[key] = mgr.add_shortcut(key, action, desc, ctx)
            except Exception:
                pass

    # ----------------------------------------------------------- integration

    def attach_to_footer(self, footer, side: str = "right") -> None:
        """Insert this row into *footer*'s main layout on the given side."""
        attach = getattr(footer, "add_widget", None)
        if callable(attach):
            attach(self, side=side)
            return
        # Fallback: raw insert into main_layout.
        if side == "left":
            footer.main_layout.insertWidget(0, self)
        else:
            footer.main_layout.addWidget(self)
