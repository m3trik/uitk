# !/usr/bin/python
# coding=utf-8
"""Filter option for OptionBox — turns a text widget into a filter field.

A :class:`FilterOption` is the single, reusable home for the "filter line-edit"
pattern used across the codebase (the Switchboard browser's search/exclude rows,
the Shortcut editor's action filter, and anywhere else a list needs a live text
filter). It is an *all-in-one* plugin built on the binary-toggle base, so adding
it gives a host text widget:

* a **filter on/off** toggle button (the field dims while off, so a query can be
  silenced without clearing it);
* **text persistence** — the verbatim query is saved on every edit and restored
  on construction (via the caller's settings object);
* a :meth:`patterns` accessor returning glob patterns ready for
  :func:`pythontk.filter_list` (``None`` while off or empty); and
* an optional **scope cycle** button (an N-state :class:`ActionOption`) that
  chooses which fields the text matches against.

Because the on/off button is itself the toggle, ``find_option(FilterOption)``
returns one object exposing the whole filter state — :attr:`is_on`,
:meth:`patterns`, :attr:`scope` — with no loose attributes stashed on the widget.

Compatibility is gated: :meth:`is_compatible` requires a text-bearing widget, so
the option-box manager will skip + warn rather than mis-wire a non-text host.

Typical use (fluent, via the manager)::

    le.option_box.set_filter(
        settings=self._settings,
        text_key="search.text",
        on_changed=self._apply_filter,
        enabled_key="search.filter_enabled",
        on_toggled=lambda _on: self._apply_filter(),
        scopes=[{"key": k, "icon": ICONS[k]} for k in SCOPES],  # optional
        scope_key="search.scope",
        default_scope=SCOPE_BOTH,
        on_scope_changed=lambda _new: self._apply_filter(),
    )
    filt = le.option_box.find_option(FilterOption)
"""
from typing import Callable, Mapping, Optional, Sequence

from .action import ActionOption
from .toggle import BinaryToggleOption


NEGATE_PREFIX = "!"
"""Leading marker on a term that flips it to an *exclude* — e.g. ``!*temp*``.

Honoured by :func:`to_patterns` (it keeps the marker and the remainder verbatim)
and by :func:`pythontk.filter_list` when called with ``negate_prefix=NEGATE_PREFIX``
(which moves the matching includes to its exclude set)."""


def to_patterns(text: str, *, negate_prefix: str = NEGATE_PREFIX):
    """Split comma-separated filter ``text`` into fnmatch patterns (verbatim).

    Terms pass through **verbatim** — matching is strict ``fnmatch``: a bare term
    matches exactly, and wildcards must be explicit. Use ``*`` for any run of
    characters (``*char*`` = substring, ``char*`` = startswith, ``*char`` =
    endswith), ``?`` for a single character, ``[seq]`` for a set. A term led by
    ``negate_prefix`` (default ``"!"``) is an exclude: the marker is kept and the
    remainder is its pattern, so ``!*temp*`` excludes anything containing 'temp'.
    Blank terms and a bare marker are dropped.

    Pair with :func:`pythontk.filter_list` (called with the same
    ``negate_prefix``), which moves the marked terms to its exclude set. Strict
    bare matching is deliberate: silently wrapping ``term`` → ``*term*`` would
    make a plain term *broader* than an explicit wildcard pattern, defeating the
    point of wildcards.
    """
    patterns = []
    for raw in text.split(","):
        term = raw.strip()
        if not term:
            continue
        # Preserve a leading negation marker; the remainder is the pattern,
        # verbatim. A bare marker (no remainder) is dropped — matching filter_list.
        marker = ""
        if negate_prefix and term.startswith(negate_prefix):
            remainder = term[len(negate_prefix):].strip()
            if not remainder:
                continue
            marker, term = negate_prefix, remainder
        patterns.append(f"{marker}{term}")
    return patterns


class FilterOption(BinaryToggleOption):
    """All-in-one filter option: on/off toggle + text persistence + scope.

    A *leaf* sibling of :class:`ToggleOption` / :class:`DisableOption` on the
    shared :class:`BinaryToggleOption` base — the on/off button *is* a binary
    toggle (filter icon, dimmed-red when off). On top of the toggle it wires the
    wrapped text field's persistence and, optionally, a scope-cycle button.

    Persistence is intentionally routed through the caller-provided ``settings``
    object (not the base's private :class:`SettingsManager`) so the field text,
    the on/off flag, and the scope all live in **one** store the consumer also
    owns — presets and external readers see a single namespace.

    Args:
        wrapped_widget: The text widget to filter (needs ``text`` / ``setText``
            / ``textChanged``). Usually a uitk ``LineEdit``.
        settings: A ``QSettings``-like object (``value`` / ``setValue``) backing
            text/scope/enabled persistence.
        text_key: Key under which the verbatim text is persisted on each edit.
        on_changed: Called (no args) after each edit — wire it to the re-filter.
        enabled_key: Optional key persisting the on/off flag. ``None`` leaves
            on/off non-persistent (the consumer may own it externally).
        initial_enabled: Starting on/off state. Overridden by any persisted
            ``enabled_key`` value.
        on_toggled: Optional callable connected to :attr:`toggled` (the on/off
            flip). Receives the new bool.
        tooltip_on / tooltip_off: Toggle-button tooltips for the two states.
        scopes: Optional sequence of ``{"key": str, "icon": str}`` describing an
            N-state scope cycle. Omit for a field with no scope button.
        scope_key / default_scope / on_scope_changed: Required when ``scopes`` is
            given — persistence key, fallback value, and a callback receiving the
            new scope key after each cycle.
        order: Explicit sort position. See :class:`BaseOption`.
    """

    # Routed to the shared ``settings`` object instead, but declared for parity
    # with the persistence-bearing siblings.
    SETTINGS_APP = "FilterOption"

    @classmethod
    def is_compatible(cls, widget) -> bool:
        """A filter needs a text-bearing host (read/write text + change signal)."""
        return (
            widget is not None
            and hasattr(widget, "text")
            and hasattr(widget, "setText")
            and hasattr(widget, "textChanged")
        )

    def __init__(
        self,
        wrapped_widget=None,
        *,
        settings=None,
        text_key: Optional[str] = None,
        on_changed: Optional[Callable[[], None]] = None,
        enabled_key: Optional[str] = None,
        initial_enabled: bool = True,
        on_toggled: Optional[Callable[[bool], None]] = None,
        tooltip_on: str = "Filter enabled. Click to disable.",
        tooltip_off: str = "Filter disabled. Click to enable.",
        scopes: Optional[Sequence[Mapping[str, str]]] = None,
        scope_key: Optional[str] = None,
        default_scope: Optional[str] = None,
        on_scope_changed: Optional[Callable[[str], None]] = None,
        order: Optional[int] = None,
    ):
        # Persistence handles must exist BEFORE super().__init__, because
        # BinaryToggleOption.__init__ calls self._load_state() (our override,
        # which reads them) to apply any persisted on/off flag.
        self._ext_settings = settings
        self._text_key = text_key
        self._enabled_key = enabled_key
        self._on_changed = on_changed

        super().__init__(
            wrapped_widget=wrapped_widget,
            icon="filter",
            tooltip_on=tooltip_on,
            tooltip_off=tooltip_off,
            initial=initial_enabled,
            # gate_wrapped greys out the field itself while the filter is off —
            # the disabled (red) icon then matches a disabled field, and the
            # toggle button stays clickable (keep-enabled) to re-enable it.
            gate_wrapped=True,
            # We own persistence via the shared ``settings`` object, so the
            # base's private SettingsManager is disabled.
            settings_key=False,
            order=order,
        )
        if on_toggled is not None:
            self.toggled.connect(on_toggled)

        # ── Optional scope cycle ───────────────────────────────────────────
        # Built eagerly (widget lazily) and exposed via ``scope_action`` so the
        # manager can add it as a sibling button. Each click cycles to the next
        # scope; the per-state callback persists the *new* scope before the
        # visual advances, keeping icon and active scope in lock-step.
        self._scopes = list(scopes) if scopes else None
        self._scope_key = scope_key
        self._default_scope = default_scope
        self._on_scope_changed = on_scope_changed
        self._scope_keys = [s["key"] for s in self._scopes] if self._scopes else []
        self._scope_action = None
        if self._scopes:
            self._scope_action = self._build_scope_action()

        # Restore + wire the wrapped field's text persistence.
        self._wire_text()

    # ------------------------------------------------------------------
    # Text persistence
    # ------------------------------------------------------------------

    def _wire_text(self) -> None:
        le = self.wrapped_widget
        # Defensive: construction must not hard-crash on a non-text host. The
        # option-box manager builds the option before its add_option compatibility
        # gate runs (and skips it there), so a momentarily-mismatched host must
        # construct cleanly rather than raise on the missing text API.
        if le is None or not hasattr(le, "textChanged"):
            return
        if (
            self._ext_settings is not None
            and self._text_key is not None
            and hasattr(le, "setText")
        ):
            saved = self._ext_settings.value(self._text_key, "") or ""
            if saved:
                le.setText(saved)
        # textChanged drives the re-filter and persists verbatim text in one
        # slot — persisting here avoids a second slot just for the save.
        le.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, value) -> None:
        if self._ext_settings is not None and self._text_key is not None:
            self._ext_settings.setValue(self._text_key, value)
        if self._on_changed is not None:
            self._on_changed()

    # ------------------------------------------------------------------
    # On/off persistence — routed to the shared settings object
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        if self._ext_settings is not None and self._enabled_key is not None:
            self._ext_settings.setValue(self._enabled_key, bool(self._is_on))

    def _load_state(self) -> None:
        # getattr-guarded: BinaryToggleOption.__init__ calls this; the attrs are
        # set just before super(), but stay defensive against MRO surprises.
        settings = getattr(self, "_ext_settings", None)
        key = getattr(self, "_enabled_key", None)
        if settings is None or key is None:
            return
        saved = settings.value(key, None)
        if saved is None:
            return
        if isinstance(saved, str):  # QSettings stringifies bools on some backends
            saved = saved.lower() in ("1", "true", "yes")
        self._is_on = bool(saved)

    # ------------------------------------------------------------------
    # Patterns
    # ------------------------------------------------------------------

    def patterns(self):
        """Active glob patterns, or ``None`` when the filter is off or empty.

        ``None`` means "match everything" (filter disabled or no text). Otherwise
        returns :func:`to_patterns` of the field text — ready for
        :func:`pythontk.filter_list`.
        """
        if not self._is_on:
            return None
        le = self.wrapped_widget
        text = le.text().strip() if le is not None else ""
        if not text:
            return None
        return to_patterns(text)

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------

    def _build_scope_action(self) -> ActionOption:
        saved = (
            self._ext_settings.value(self._scope_key, self._default_scope)
            if self._ext_settings is not None
            else self._default_scope
        )
        if saved not in self._scope_keys:
            saved = self._default_scope

        states = []
        for i, spec in enumerate(self._scopes):
            nxt = self._scope_keys[(i + 1) % len(self._scope_keys)]
            states.append(
                {
                    "icon": spec["icon"],
                    "tooltip": (
                        f"Scope: matches {spec['key']}. Click to switch to '{nxt}'."
                    ),
                    "callback": self._make_scope_cb(nxt),
                }
            )
        # settings_key=False: the FilterOption persists the scope via the shared
        # settings object (below), not the ActionOption's own SettingsManager.
        action = ActionOption(
            wrapped_widget=self.wrapped_widget, states=states, settings_key=False
        )
        # Sync the visible state to the persisted scope before it is added so the
        # initial render shows the correct icon.
        if saved in self._scope_keys:
            action.current_state = self._scope_keys.index(saved)
        return action

    def _make_scope_cb(self, new_scope: str):
        def _cb():
            if self._ext_settings is not None and self._scope_key is not None:
                self._ext_settings.setValue(self._scope_key, new_scope)
            if self._on_scope_changed is not None:
                self._on_scope_changed(new_scope)

        return _cb

    @property
    def scope_action(self) -> Optional[ActionOption]:
        """The sibling scope-cycle :class:`ActionOption`, or ``None`` if scopeless.

        The manager adds this to the same option box so the scope button sits
        beside the filter toggle.
        """
        return self._scope_action

    @property
    def scope(self) -> Optional[str]:
        """The active scope key, or ``None`` when the field has no scope cycle."""
        if not self._scope_action or not self._scope_keys:
            return None
        return self._scope_keys[self._scope_action.current_state]

    def set_scope(self, key: str, *, notify: bool = False) -> None:
        """Programmatically set the active scope, syncing the button visual.

        Persists the new scope. Pass ``notify=True`` to also invoke
        ``on_scope_changed`` (e.g. an external setter that should re-filter);
        leave it ``False`` for silent restoration (preset load) where the caller
        re-filters once at the end.
        """
        if not self._scope_action or key not in self._scope_keys:
            return
        # The setter applies the visuals itself when a widget is attached.
        self._scope_action.current_state = self._scope_keys.index(key)
        if self._ext_settings is not None and self._scope_key is not None:
            self._ext_settings.setValue(self._scope_key, key)
        if notify and self._on_scope_changed is not None:
            self._on_scope_changed(key)

    # ------------------------------------------------------------------
    # Keys (for callers that persist alongside, e.g. preset I/O)
    # ------------------------------------------------------------------

    @property
    def text_key(self) -> Optional[str]:
        """Settings key under which the field text is persisted."""
        return self._text_key

    @property
    def scope_key(self) -> Optional[str]:
        """Settings key under which the scope is persisted (``None`` if scopeless)."""
        return self._scope_key
