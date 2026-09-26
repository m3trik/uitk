# !/usr/bin/python
# coding=utf-8
"""``ResetGesture`` — the click grammar every *Restore Defaults* control shares.

* **Click** — reset to the defaults (your saved defaults, else the factory ones).
* **Shift + Click** — make the current values the defaults.
* **Ctrl + Shift + Click** — back to the factory defaults (forgets saved ones).

The *factory* default is what the UI shipped with
(``StateManager.capture_default``); a *saved* default is persisted by
``StateManager.save_defaults`` and wins until it is forgotten. A per-field
``ResetOption`` uses the same grammar and adds its bypass modifier on top.

Attached to a button, the gesture also makes itself discoverable: the tooltip
lists every modifier (and says whether saved defaults are in use), the button
text previews the action while a modifier is held over it, and the result
flashes on the button after the click::

    ResetGesture(button, state=window.state, widgets=fields)
"""

from typing import List, Optional

from qtpy import QtCore, QtWidgets

from uitk.widgets.mixins.tooltip_mixin import TooltipFormat, TooltipProxy


class ResetGesture(QtCore.QObject):
    """Modifier-aware reset for a button: dispatch, tooltip, live preview.

    Parameters:
        button: The ``QAbstractButton`` that triggers the reset. The gesture is
            parented to it and lives as long as it does.
        state: The ``StateManager`` to act through, or a zero-argument callable
            returning it (resolved on every use -- a popup menu's host is only
            reachable once it is built). A stand-in exposing only ``reset_all``
            gets a plain reset and a tooltip that doesn't offer saving.
        widgets: The widgets in scope: an iterable, a zero-argument callable
            returning one, or ``None`` for every widget the state manages.
        title: Tooltip title.
        signal: Name of the button signal that triggers (default ``clicked``).
        on_performed: Optional callable receiving the action after each trigger.
        modifiers: Zero-argument callable returning the held modifiers. Defaults
            to ``QApplication.queryKeyboardModifiers``, which reads the keyboard
            itself, so a popup without key focus still previews correctly.
    """

    RESET = "reset"
    SAVE = "save"
    FACTORY = "factory"
    BYPASS = "bypass"

    #: Button text shown while an action's modifiers are held over the button.
    LABELS = {SAVE: "Save as Defaults", FACTORY: "Factory Reset"}
    #: Text flashed on the button after a trigger. Kept about as long as the
    #: button's own label, so the flash doesn't re-flow a menu.
    RESULTS = {
        RESET: "Defaults Restored",
        SAVE: "Defaults Saved",
        FACTORY: "Factory Restored",
    }
    NOTHING_SAVED = "Nothing to Save"
    FLASH_MS = 1500
    POLL_MS = 100

    _MODIFIER_KEYS = (
        ("Ctrl", QtCore.Qt.ControlModifier),
        ("Shift", QtCore.Qt.ShiftModifier),
        ("Alt", QtCore.Qt.AltModifier),
        ("Meta", QtCore.Qt.MetaModifier),
    )

    def __init__(
        self,
        button: QtWidgets.QAbstractButton,
        state,
        widgets=None,
        *,
        title: str = "Restore Defaults",
        signal: str = "clicked",
        on_performed=None,
        modifiers=None,
    ):
        super().__init__(button)
        self._button = button
        self._state = state
        self._widgets = widgets
        self._title = title
        self._on_performed = on_performed
        self._modifiers = modifiers or QtWidgets.QApplication.queryKeyboardModifiers
        self._text = button.text()
        self._can_save = False
        self._flashing = False
        self._poll = QtCore.QTimer(self)
        self._poll.setInterval(self.POLL_MS)
        self._poll.timeout.connect(self._preview)
        self._flash_timer = QtCore.QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)
        button.installEventFilter(self)
        getattr(button, signal).connect(self.trigger)
        # Rebuilt on every hover by uitk's tooltip presenter. A provider, not a
        # QEvent.ToolTip branch in eventFilter: the presenter shows the tip and
        # consumes the event, so a filter older than it would never be reached.
        TooltipProxy(button).bind(self._current_tooltip)
        self.refresh_tooltip()

    # ------------------------------------------------------------ the grammar
    @classmethod
    def action_for(cls, modifiers, bypass_modifier=None) -> str:
        """The action a click with *modifiers* held performs.

        Ctrl+Shift is tested first, so a bypass modifier that includes Ctrl
        (``ResetOption``'s default) still leaves the factory reset reachable.

        Parameters:
            modifiers: The held ``Qt.KeyboardModifier`` flags.
            bypass_modifier: Flags that select :data:`BYPASS`, for a control
                that has one; ``None`` means the control has no bypass.

        Returns:
            One of :data:`RESET`, :data:`SAVE`, :data:`FACTORY`, :data:`BYPASS`.
        """
        shift = bool(modifiers & QtCore.Qt.ShiftModifier)
        ctrl = bool(modifiers & QtCore.Qt.ControlModifier)
        if shift and ctrl:
            return cls.FACTORY
        if shift:
            return cls.SAVE
        if bypass_modifier is not None and modifiers & bypass_modifier:
            return cls.BYPASS
        return cls.RESET

    @classmethod
    def modifier_keys(cls, modifiers) -> List[str]:
        """Key names (``"Ctrl"``, ``"Alt"``...) for the flags set in *modifiers*."""
        return [name for name, flag in cls._MODIFIER_KEYS if modifiers & flag]

    @staticmethod
    def supports_saving(state) -> bool:
        """Whether *state* can persist and forget saved defaults."""
        return all(
            callable(getattr(state, name, None))
            for name in ("save_defaults", "clear_saved_defaults")
        )

    @staticmethod
    def tooltip(
        title: str = "Restore Defaults",
        *,
        saving: bool = True,
        saved: Optional[bool] = None,
        bypass: Optional[List[str]] = None,
    ) -> str:
        """The rich tooltip that teaches the grammar.

        Parameters:
            title: Tooltip title.
            saving: Offer the save / factory rows (the state supports them).
            saved: Whether saved defaults are in use for this scope. ``None``
                (unknown -- a tooltip built once, which a later save would make
                stale) omits the note.
            bypass: Key names of a bypass modifier to document, if any.
        """
        kbd = TooltipFormat.kbd
        rows = [("Click", "Reset to the defaults")]
        if saving:
            rows += [
                (f"{kbd('Shift')} + Click", "Make the current values the defaults"),
                (f"{kbd('Ctrl', 'Shift')} + Click", "Back to the factory defaults"),
            ]
        if bypass:
            keys = " / ".join(kbd(key) for key in bypass)
            rows.append((f"{keys} + Click", "Hold at the default (bypass)"))
        notes = None
        if saving and saved is not None:
            notes = [
                "Your saved defaults are in use."
                if saved
                else "The defaults are the factory values."
            ]
        return TooltipFormat.fmt(title=title, rows=rows, notes=notes)

    @classmethod
    def perform(cls, state, action: str, widgets=None) -> Optional[str]:
        """Apply *action* through *state* over *widgets*.

        A save or factory action on a state that can't save runs a plain reset.

        Returns:
            The result text to show, or ``None`` when there is no state.
        """
        if state is None:
            return None
        if action in (cls.SAVE, cls.FACTORY) and not cls.supports_saving(state):
            action = cls.RESET
        if action == cls.SAVE:
            saved = state.save_defaults(widgets)
            return cls.RESULTS[cls.SAVE] if saved else cls.NOTHING_SAVED
        if action == cls.FACTORY:
            state.reset_all(widgets=widgets, factory=True)
            return cls.RESULTS[cls.FACTORY]
        state.reset_all(widgets=widgets)
        return cls.RESULTS[cls.RESET]

    # ---------------------------------------------------------- the button
    def trigger(self, *_) -> str:
        """Run the action the held modifiers select. Returns that action."""
        state = self._resolve_state()
        action = self.action_for(self._modifiers())
        message = self.perform(state, action, self._scope())
        if message:
            self.flash(message)
        if self._on_performed is not None:
            self._on_performed(action)
        return action

    def refresh_tooltip(self) -> None:
        """Rebuild the tooltip for the current state now.

        A hover rebuilds it anyway, through the provider bound in ``__init__``.
        """
        self._button.setToolTip(self._current_tooltip())

    def _current_tooltip(self) -> str:
        state = self._resolve_state()
        saving = self.supports_saving(state)
        saved = False
        if saving and callable(getattr(state, "has_saved_defaults", None)):
            saved = bool(state.has_saved_defaults(self._scope()))
        return self.tooltip(self._title, saving=saving, saved=saved)

    def flash(self, message: str) -> None:
        """Show *message* on the button for :data:`FLASH_MS`, then its label."""
        self._flashing = True
        self._button.setText(message)
        self._flash_timer.start(self.FLASH_MS)

    def eventFilter(self, obj, event):
        if obj is self._button:
            kind = event.type()
            if kind == QtCore.QEvent.Enter:
                # Re-read the label (a consumer may rename the button), but not
                # one of ours: a Leave lost while previewing (a host mouse grab)
                # would otherwise make the preview the button's label for good.
                text = self._button.text()
                if not self._flashing and text not in self.LABELS.values():
                    self._text = text
                self._can_save = self.supports_saving(self._resolve_state())
                self._preview()
                self._poll.start()
            elif kind in (QtCore.QEvent.Leave, QtCore.QEvent.Hide):
                self._poll.stop()
                if not self._flashing:
                    self._button.setText(self._text)
        return super().eventFilter(obj, event)

    def _preview(self) -> None:
        if self._flashing:
            return
        label = self.LABELS.get(self.action_for(self._modifiers()))
        text = label if label and self._can_save else self._text
        if self._button.text() != text:
            self._button.setText(text)

    def _end_flash(self) -> None:
        self._flashing = False
        self._button.setText(self._text)
        if self._poll.isActive():  # still hovered: resume the preview
            self._preview()

    def _resolve_state(self):
        return self._state() if callable(self._state) else self._state

    def _scope(self) -> Optional[list]:
        widgets = self._widgets() if callable(self._widgets) else self._widgets
        return None if widgets is None else list(widgets)
