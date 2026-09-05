# !/usr/bin/python
# coding=utf-8
"""Affix-mode picker option for OptionBox.

An :class:`AffixOption` turns a text field into an affix entry with a compact
icon button sitting flush beside it — the single, reusable home for the pattern
previously duplicated across the DCC toolkits (mayatk / blendertk ``mat_utils``).
Clicking the button cycles the mode, which declares how the field's text is
applied to a base name.

**The mode set is configurable.** Three modes ship built in and form the default
cycle, but a caller may ask for fewer, reorder them, or add its own:

* **Auto** — placement inferred from the delimiter: a leading ``_`` (``"_MAT"``)
  is treated as a suffix; a trailing ``_`` (``"MAT_"``) is treated as a prefix.
* **Suffix** — always appended (``"brick" + "_MAT" -> "brick_MAT"``).
* **Prefix** — always prepended (``"MAT_" + "brick" -> "MAT_brick"``).

A **custom mode** is an :class:`AffixMode` describing its own glyph, tooltip and
resolution — and, optionally, that it *supplies* the field's text and locks it
while active. :meth:`AffixMode.convention` is the one this ecosystem ships:
it binds the field to ``pythontk.NamingConvention``, the shared answer to "what
affix marks a material?", so a tool can offer "use the studio convention"
alongside the three manual modes without any of that leaking into the built-ins.

The manual parsing is the widget-free :py:meth:`pythontk.StrUtils.split_affix`
primitive; this option only wires the picker button and exposes the selection.

Usage — the ``option_box`` manager form works on any widget (``.option_box`` is
autopatched onto plain ``QLineEdit``/etc.), so prefer it in slot code; the
``.options`` fluent sugar exists only on ``OptionBoxMixin`` widgets::

    le.option_box.set_affix(default="auto", on_change=on_mode_changed)
    le.options.affix(default="auto")                       # fluent equiv (mixin widgets)

    mode = le.option_box.affix_mode                        # 'auto'|'suffix'|'prefix'|...
    prefix, suffix = le.option_box.resolve_affix(default="suffix")

    # Two modes only — a field that is always one side or the other:
    le.option_box.set_affix(modes=("suffix", "prefix"), default="suffix")

    # Four modes: the three manual ones plus "use the shared convention",
    # which fills the field from the SSoT and makes it read-only while active.
    le.option_box.set_affix(default="auto", convention_key="material")

    # Same fourth state for a field whose target type is not fixed: the key is
    # resolved per read, so the field previews what the CURRENT selection would
    # get, and a slot whose engine resolves per object passes its sentinel.
    le.option_box.set_affix(
        default="convention", convention_key=lambda: type_key(selection())
    )
"""

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

import pythontk as ptk

from ._options import ButtonOption
from ._persistence import PersistedOption

logger = logging.getLogger(__name__)


#: The built-in mode keys, in the click-cycle order. Kept as a module constant
#: for callers that predate configurable mode sets.
AFFIX_MODE_VALUES: Tuple[str, str, str] = ("auto", "suffix", "prefix")


@dataclass(frozen=True)
class AffixMode:
    """One selectable state of the picker.

    The three built-ins are instances of this; so is anything a caller adds.
    Everything the button needs to render a state and everything the field
    needs to behave in it lives here, which is what keeps the option itself
    free of any particular mode's semantics.

    Attributes:
        key: Stable identifier — what :attr:`AffixOption.mode` reports and what
            is persisted. Never user-visible; never renumber or rename one that
            has shipped.
        label: Display name for the tooltip (``"Prefix"``, ``"Scene"``).
        icon: IconManager glyph name for the button in this state.
        description: Short "what this does to the name" clause, shown in the
            per-state tooltip after the label.
        resolver: ``(text, default) -> (prefix, suffix)``. ``None`` falls back
            to :py:meth:`pythontk.StrUtils.split_affix` with ``mode=key`` —
            exact for the built-ins, and a sane "auto" for a custom key that
            does not need its own parsing.
        provider: ``() -> str`` supplying the field's text while this mode is
            active. ``None`` (the built-ins) means the user's own text stands.
        locks_text: Make the field read-only while this mode is active. The
            widget stays *enabled* — the value is still visible, selectable and
            readable by the slot; only typing into it is refused.
    """

    key: str
    label: str
    icon: str
    description: str = ""
    resolver: Optional[Callable[[str, str], Tuple[str, str]]] = None
    provider: Optional[Callable[[], str]] = None
    locks_text: bool = False

    def resolve(self, text: str, default: str = "prefix") -> Tuple[str, str]:
        """``(prefix, suffix)`` for *text* under this mode."""
        if self.resolver is not None:
            return self.resolver(text, default)
        return ptk.StrUtils.split_affix(text, mode=self.key, default=default)

    def text(self) -> Optional[str]:
        """The text this mode supplies, or ``None`` when the user's own stands."""
        return None if self.provider is None else self.provider()

    # ------------------------------------------------------------------
    # Shipped custom modes
    # ------------------------------------------------------------------

    @classmethod
    def convention(
        cls,
        convention_key: Union[str, Callable[[], str]],
        *,
        key: str = "convention",
        label: str = "Scene",
        icon: str = "link",
        description: str = "",
    ) -> "AffixMode":
        """A mode bound to ``pythontk.NamingConvention`` for *convention_key*.

        While selected, the field shows the convention's affix for that type and
        is read-only: the spelling AND the side it lands on both come from the
        one shared definition, so changing the convention moves every tool that
        offers this mode at once.

        This is a *custom* mode, deliberately not one of the built-ins — most
        fields want the three manual states and nothing else, and a field whose
        text has no type key (a version stamp, a user's own tag) has nothing to
        bind to. Opt in per call site via ``set_affix(convention_key=...)``.

        **The key may be a callable**, for a field whose target type is not
        fixed: a tool that names whatever the user selected cannot know up front
        whether that is a mesh (``_GEO``) or a camera (``_CAM``). It is resolved
        on every read, and the option box re-pulls when it is shown, so the
        field previews the affix the CURRENT target would get. Deliberately the
        same state rather than a second one: "follow the shared convention" is
        one idea, and it must look and persist identically everywhere it is
        offered. A caller whose operation resolves per object (a mixed selection
        has no single answer) reads :attr:`AffixOption.mode`, sees
        ``"convention"``, and passes its engine's "use the convention" sentinel
        instead of the previewed text.

        Parameters:
            convention_key: The type key to read — ``"material"``, ``"mesh"``,
                ``"group"``… See ``NamingConvention.keys()``. Or a
                ``() -> key`` callable for a target-dependent type; it must
                always answer a key (fall back to the tool's usual type rather
                than returning nothing, which would empty the field).
            key: Stable persisted identifier for this state.
            label: Display name in the tooltip.
            icon: Glyph for the button (a link: bound to the shared definition).
            description: Overrides the generated "follows the convention" clause.
        """
        from pythontk import NamingConvention

        dynamic = callable(convention_key)
        if not dynamic and convention_key not in NamingConvention.resolve():
            # Not fatal (a key can be added later), but say so: a typo here
            # otherwise produces a state that empties the field, locks it, and
            # applies nothing — with no visible cause. A callable is exempt:
            # its answer depends on the scene, so there is nothing to check yet.
            logger.warning(
                "[AffixOption] convention key %r is not in NamingConvention; "
                "the mode will supply nothing.",
                convention_key,
            )

        def resolve_key(k=convention_key) -> str:
            return k() if dynamic else k

        title = (
            "each object's own type"
            if dynamic
            else NamingConvention.label(convention_key).lower()
        )
        return cls(
            key=key,
            label=label,
            icon=icon,
            description=(
                description
                or f"follows the shared naming convention for {title} "
                f"(read-only here — edit it in the Naming panel)"
            ),
            resolver=lambda _text, default: NamingConvention.affix_parts(
                resolve_key(), default=default
            ),
            provider=lambda: NamingConvention.affix(resolve_key()),
            locks_text=True,
        )


#: The three manual modes, by key. The default cycle for every picker that does
#: not ask for something else.
BUILTIN_AFFIX_MODES: Dict[str, AffixMode] = {
    "auto": AffixMode(
        key="auto",
        label="Auto",
        icon="asterisk",
        description=(
            "leading '_' (e.g. '_MAT') is a suffix; trailing '_' (e.g. 'MAT_') "
            "is a prefix"
        ),
    ),
    "suffix": AffixMode(
        key="suffix",
        label="Suffix",
        icon="arrow_right",
        description="always appended (e.g. 'brick' + '_MAT' -> 'brick_MAT')",
    ),
    "prefix": AffixMode(
        key="prefix",
        label="Prefix",
        icon="arrow_left",
        description="always prepended (e.g. 'MAT_' + 'brick' -> 'MAT_brick')",
    ),
}


class AffixOption(PersistedOption, ButtonOption):
    """Cycling affix-mode picker for a text widget.

    Renders one icon button whose glyph is the current mode; clicking advances
    through :attr:`modes`. Defaults to the three built-in manual modes; pass
    ``modes`` for two, or for a set including custom :class:`AffixMode` states.

    The mode is **persisted** (like :class:`ToggleOption`'s on/off): it is the
    user's standing declaration about a field whose text they also keep across
    sessions, so restoring the text while resetting the placement would apply
    that text to the wrong side of the name. ``settings_key`` follows the usual
    :class:`PersistedOption` contract — ``None`` auto-derives from the wrapped
    widget's ``objectName``, ``False`` disables persistence.
    """

    SETTINGS_APP = "AffixOption"

    #: QSettings keys: the selected mode, and the user's own text parked while
    #: a text-supplying mode occupies the field.
    _MODE_KEY = "mode"
    _HELD_KEY = "held_text"

    def __init__(
        self,
        wrapped_widget=None,
        *,
        default: str = "auto",
        modes: Optional[Sequence[Union[str, AffixMode]]] = None,
        convention_key: Optional[Union[str, Callable[[], str]]] = None,
        on_change: Optional[Callable[[str], None]] = None,
        tooltip: Optional[str] = None,
        settings_key: Optional[Union[str, bool]] = None,
        order: Optional[int] = None,
    ):
        """Initialize the affix option.

        Args:
            wrapped_widget: The text field this picker is attached to.
            default: Initial mode key. Falls back to the first available mode if
                unknown. A previously persisted mode overrides it.
            modes: The cycle, as mode keys (built-ins) and/or :class:`AffixMode`
                instances. ``None`` uses the three built-ins — plus the
                convention mode when *convention_key* is given. Pass e.g.
                ``("suffix", "prefix")`` for a two-state picker.
            convention_key: Shorthand for appending
                :meth:`AffixMode.convention` to the default cycle. Ignored when
                *modes* is given explicitly (list the mode there instead).
                A ``() -> key`` callable binds the state to the CURRENT
                target's type instead of a fixed one — see that method.
            on_change: Optional callable invoked with the new mode key whenever
                the mode changes on the built button (click or programmatic
                :meth:`set_mode`). Not fired for the restore of a persisted mode.
            tooltip: Static tooltip override. ``None`` (default) shows a
                per-state tooltip naming the current mode and the cycle hint.
            settings_key: Persistence namespace. ``None`` auto-derives from the
                wrapped widget's ``objectName``; an explicit string pins it
                (prefer one for a generic name like ``txt000``, which two panels
                in the same host would otherwise share); ``False`` disables
                persistence — pass it when an outer store already owns the mode
                (uitk's bridge presets do) or in unit tests.
            order: Explicit sort position. See :class:`BaseOption`.
        """
        self._modes = self._build_modes(modes, convention_key)
        self._order: List[str] = list(self._modes)
        self._mode = default if default in self._modes else self._order[0]
        self._initial = self._mode
        self._on_change = on_change
        self._tooltip_override = tooltip
        self._held: Optional[str] = None
        self._locked = False
        super().__init__(
            wrapped_widget,
            icon=self._modes[self._mode].icon,
            tooltip=tooltip,
            callback=self._cycle,
            order=order,
        )
        # After super(): ``_init_persistence`` reads ``self.wrapped_widget``,
        # which ``BaseOption.__init__`` sets. Loading may move ``_mode`` before
        # any widget exists — ``create_widget`` re-reads it for the glyph, and
        # ``setup_widget`` applies the restored mode's field effects.
        self._init_persistence(settings_key)
        self._load_state()

    # ------------------------------------------------------------------
    # Mode set
    # ------------------------------------------------------------------

    @staticmethod
    def _build_modes(
        modes: Optional[Sequence[Union[str, AffixMode]]],
        convention_key: Optional[Union[str, Callable[[], str]]],
    ) -> "Dict[str, AffixMode]":
        """Normalize the requested cycle to an ordered ``{key: AffixMode}``.

        Accepts built-in keys and :class:`AffixMode` instances interchangeably.
        Unknown strings are dropped with a warning rather than raising — a
        picker with one usable mode is a far better failure than a panel that
        will not build.
        """
        if modes is None:
            resolved = [BUILTIN_AFFIX_MODES[k] for k in AFFIX_MODE_VALUES]
            if convention_key:
                # Skip an unknown key rather than offering a state that empties
                # the field and locks it: a picker missing its fourth state is
                # diagnosable (the warning names the key), a dead field is not.
                # A callable key answers from the scene, so there is nothing to
                # check here -- it is taken on trust.
                from pythontk import NamingConvention

                if callable(convention_key) or convention_key in (
                    NamingConvention.resolve()
                ):
                    resolved.append(AffixMode.convention(convention_key))
                else:
                    logger.warning(
                        "[AffixOption] unknown convention key %r; the shared-"
                        "convention state was not added.",
                        convention_key,
                    )
        else:
            resolved = []
            for entry in modes:
                if isinstance(entry, AffixMode):
                    resolved.append(entry)
                elif entry in BUILTIN_AFFIX_MODES:
                    resolved.append(BUILTIN_AFFIX_MODES[entry])
                else:
                    logger.warning("[AffixOption] unknown mode %r; skipped.", entry)
        out: "Dict[str, AffixMode]" = {}
        for mode in resolved:
            out.setdefault(mode.key, mode)
        if not out:  # every entry was bogus — never leave the picker stateless
            out = {k: BUILTIN_AFFIX_MODES[k] for k in AFFIX_MODE_VALUES}
        return out

    @property
    def modes(self) -> List[str]:
        """The mode keys in cycle order."""
        return list(self._order)

    def mode_spec(self, key: Optional[str] = None) -> AffixMode:
        """The :class:`AffixMode` for *key* (the current mode by default)."""
        return self._modes[key or self._mode]

    # ------------------------------------------------------------------
    # Compatibility
    # ------------------------------------------------------------------

    @classmethod
    def is_compatible(cls, widget) -> bool:
        """Attach only to text-bearing hosts (``resolve`` reads ``text()``)."""
        return widget is not None and hasattr(widget, "text")

    # ------------------------------------------------------------------
    # ButtonOption overrides
    # ------------------------------------------------------------------

    def create_widget(self):
        """Create the standard option button, seeded with the current mode's glyph."""
        # set_mode / _load_state may have moved the mode since __init__.
        self.icon = self._modes[self._mode].icon
        return super().create_widget()

    def setup_widget(self):
        """Wire the cycle click, show the tooltip, apply the mode's field effects."""
        super().setup_widget()
        self._widget.setToolTip(self._tooltip_for(self._mode))
        # A restored text-supplying mode has to reach the field too, not just
        # the glyph — otherwise the picker says "Scene" beside stale text.
        self._apply_field_effects(capture=False)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        """Current mode key.

        A pure read: the mode is plugin-owned, so reading it never forces
        widget construction.
        """
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Select *mode* if it is one of :attr:`modes` (else no-op).

        On the built button this swaps the glyph/tooltip, applies the mode's
        field effects and fires ``on_change``; before build it just re-seeds the
        state. Either way the selection is persisted.
        """
        if mode not in self._modes or mode == self._mode:
            return
        self._mode = mode
        self._apply_field_effects(capture=True)
        self._save_state()
        if self._widget is not None:
            self._apply_mode_visual()
            if self._on_change is not None:
                self._on_change(mode)

    def restore_default(self) -> None:
        """Return the picker to its constructed ``default`` mode.

        Called by a sibling ``ResetOption`` when the user resets the field —
        without it, a persisted mode would be the one part of the field a reset
        could not reach. Routed through :meth:`set_mode`, so the cleared mode
        persists and ``on_change`` fires exactly as a click would.
        """
        self.set_mode(self._initial)

    def refresh(self) -> None:
        """Re-pull a text-supplying mode's value into the field.

        Cheap and idempotent; a no-op in a manual mode. Call it when the source
        a custom mode reads may have changed — the Naming panel edits the shared
        convention, and every field bound to it should follow.
        """
        self._apply_field_effects(capture=False)

    def resolve(
        self, text: Optional[str] = None, *, default: str = "prefix"
    ) -> Tuple[str, str]:
        """Return ``(prefix, suffix)`` for *text* under the current mode.

        *text* defaults to the wrapped widget's current text. *default* is the
        fallback mode used when Auto is selected but *text* has no boundary
        delimiter (matches :py:meth:`pythontk.StrUtils.split_affix`).

        A text-supplying mode ignores *text* entirely and answers from its own
        source, so the result is right even if something wrote over the field
        after the mode was applied.
        """
        spec = self._modes[self._mode]
        if text is None:
            w = self.wrapped_widget
            text = w.text() if (w is not None and hasattr(w, "text")) else ""
        return spec.resolve(text, default)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cycle(self) -> None:
        """Advance to the next mode (button click)."""
        i = self._order.index(self._mode)
        self.set_mode(self._order[(i + 1) % len(self._order)])

    def _apply_mode_visual(self) -> None:
        """Swap the built button's glyph and tooltip to the current mode."""
        self._swap_state_icon(self._modes[self._mode].icon, fallback_size=(15, 15))
        self._widget.setToolTip(self._tooltip_for(self._mode))

    def _tooltip_for(self, mode: str) -> str:
        """Per-state tooltip (or the static override when one was given)."""
        if self._tooltip_override is not None:
            return self._tooltip_override
        spec = self._modes[mode]
        cycle = " -> ".join(self._modes[k].label for k in self._order)
        head = f"Affix mode: {spec.label}"
        if spec.description:
            head = f"{head} — {spec.description}"
        return f"{head}.\nClick to cycle: {cycle}."

    # -------------------------------------------------- field effects
    def _text_host(self):
        """The wrapped widget when it can carry text, else ``None``."""
        w = self.wrapped_widget
        return w if (w is not None and hasattr(w, "setText")) else None

    def _apply_field_effects(self, *, capture: bool) -> None:
        """Put the field into (or out of) the current mode's text state.

        *capture* parks the user's own text before a supplying mode takes the
        field over. It is ``True`` for a real mode CHANGE and ``False`` for a
        restore/refresh — on a restore the parked text came from the persisted
        value, and re-capturing would overwrite it with the convention text the
        field is already showing.
        """
        host = self._text_host()
        if host is None:
            return
        spec = self._modes[self._mode]

        if spec.locks_text or spec.provider is not None:
            supplied = spec.text()
            if capture and not self._locked:
                self._held = host.text()
                self._save_state()
            elif self._held is None and not self._locked:
                # A restore with NOTHING parked — a picker whose default IS a
                # supplying mode, over a field the panel seeded (setText="_GEO").
                # Without this the seed is overwritten and lost, so leaving the
                # mode hands the slot an empty field, or this mode's own token
                # as if it were a literal affix. Never park the supplied text
                # itself: that is the mode's, not the user's.
                current = host.text()
                if current and current != supplied:
                    self._held = current
                    self._save_state()
            if supplied is not None:
                host.setText(supplied)
            if spec.locks_text and hasattr(host, "setReadOnly"):
                # Read-only, NOT disabled: the value must stay visible and
                # readable by the slot — only typing into it is refused.
                host.setReadOnly(True)
            self._locked = True
            return

        if self._locked:
            if hasattr(host, "setReadOnly"):
                host.setReadOnly(False)
            if self._held is not None:
                host.setText(self._held)
                self._held = None
                self._save_state()
            self._locked = False

    # -------------------------------------------------- persistence
    def _save_state(self) -> None:
        if not self._settings:
            return
        self._settings.setValue(self._MODE_KEY, self._mode)
        self._settings.setValue(self._HELD_KEY, self._held)
        self._settings.sync()

    def _load_state(self) -> None:
        """Adopt the persisted mode and parked text, silently.

        Runs before the button exists, so there is nothing to repaint and no
        user action to report — a consumer that mirrors the mode into a
        placeholder re-reads :attr:`mode` right after ``set_affix`` returns, and
        ``setup_widget`` applies the restored mode to the field.
        """
        if not self._settings:
            return
        saved = self._settings.value(self._MODE_KEY)
        if saved in self._modes:
            self._mode = saved
        held = self._settings.value(self._HELD_KEY)
        self._held = None if held is None else str(held)
