# !/usr/bin/python
# coding=utf-8
"""Shared multi-state icon behavior for state-cycling buttons."""


class IconStates:
    """Single home for a button's multi-state visuals and click-cycling.

    A *state* is a dict with optional keys:
        icon:     Icon name rendered via ``IconManager``.
        color:    Explicit hex tint. Explicit colors are *pinned* by
                  ``IconManager``, so theme sweeps and size re-fits never
                  repaint them; omit for a state that follows the theme.
        tooltip:  Tooltip while the state is current.
        callback: Callable run when the widget is activated in this state.

    The widget always shows ``current_state``'s visuals — including at
    attach time, so a freshly-built UI is color-coded before any click.
    Assign ``current_state`` to follow externally-owned app state (applies
    visuals and fires ``on_change``, but never a state callback).

    ``activate()`` is the click path: it runs the current state's callback,
    then auto-advances to the next state — unless the callback itself
    assigned ``current_state``, which takes precedence. That exception is
    what lets one piece of app state drive several stateful widgets: the
    callback syncs them all (including the clicked one) to the app state,
    and a blind auto-advance on top would overshoot.

    Used by ``ActionOption(states=...)`` and
    ``Footer.add_action_button(states=...)``.
    """

    def __init__(self, states, widget=None, fallback_size=(15, 15), on_change=None):
        """Initialize the state set.

        Args:
            states: List of state dicts (see class docstring).
            widget: Optional widget to attach immediately (anything with
                ``setIcon``/``setToolTip``). Attaching applies the current
                state's visuals.
            fallback_size: Icon raster size used when the widget has no
                valid ``iconSize`` yet (see ``IconManager.swap_icon``).
            on_change: Optional ``callable(index)`` fired after the index
                changes and visuals are applied — persistence hooks go here.
        """
        self._states = list(states)
        self._index = 0
        self._widget = None
        self._fallback_size = tuple(fallback_size)
        self._on_change = on_change
        self._set_during_activate = False
        if widget is not None:
            self.widget = widget

    @property
    def states(self):
        """The state dicts (copy — mutate via a new IconStates).

        Each dict is itself copied, so mutating an entry of the returned
        list (``cycle.states[0]["color"] = …``) cannot reach back into the
        internal state; rebuild via a new ``IconStates`` to change behavior.
        """
        return [dict(s) for s in self._states]

    @property
    def widget(self):
        """The attached widget (None until attached)."""
        return self._widget

    @widget.setter
    def widget(self, widget):
        self._widget = widget
        if widget is not None and self._states:
            self.apply()

    @property
    def current_state(self):
        """The current 0-based state index."""
        return self._index

    @current_state.setter
    def current_state(self, index):
        self.set_current_state(index)

    def set_current_state(self, index, notify=True):
        """Set the state index and apply its visuals.

        Args:
            index: New index (wrapped modulo the state count).
            notify: When False, skip the ``on_change`` hook — used when
                restoring a persisted index so the restore isn't re-saved.
        """
        if not self._states:
            return
        self._set_during_activate = True
        self._index = int(index) % len(self._states)
        if self._widget is not None:
            self.apply()
        if notify and self._on_change is not None:
            self._on_change(self._index)

    def apply(self):
        """Apply the current state's icon/color/tooltip to the widget."""
        from uitk.managers.icon_manager import IconManager

        state = self._states[self._index]
        if "icon" in state:
            color = state.get("color")
            # Preserve the size set by the host (via fit_icon) so cycling
            # states doesn't oscillate the icon size.
            IconManager.swap_icon(
                self._widget,
                state["icon"],
                color=color,
                auto_theme=color is None,
                fallback_size=self._fallback_size,
            )
        if "tooltip" in state:
            self._widget.setToolTip(state["tooltip"])

    def resolve_callback(self, fallback=None):
        """The current state's callback, else *fallback*."""
        cb = self._states[self._index].get("callback") if self._states else None
        return cb if cb is not None else fallback

    def activate(self, fallback=None, runner=None):
        """Run the current state's callback, then advance to the next state.

        Args:
            fallback: Handler used when the current state has no callback.
            runner: Optional ``callable(handler)`` that invokes the handler.
                Hosts with richer handler semantics (e.g. ActionOption's
                object-with-``run()`` support) inject their invoker here;
                the default calls the handler directly.

        The auto-advance is skipped when the callback assigned
        ``current_state`` itself (see class docstring).
        """
        self._set_during_activate = False
        handler = self.resolve_callback(fallback)
        if handler is not None:
            if runner is not None:
                runner(handler)
            else:
                handler()
        if len(self._states) > 1 and not self._set_during_activate:
            self.set_current_state(self._index + 1)
