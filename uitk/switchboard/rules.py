# !/usr/bin/python
# coding=utf-8
from typing import Any, Callable, Dict, List, Optional, Union
from qtpy import QtWidgets, QtCore
from uitk.managers.field_visibility import FieldVisibility


class SwitchboardRulesMixin:
    """Declarative widget rules: ``enable_when`` / ``show_when`` / ``text_from`` /
    ``value_from`` on one shared wiring core, plus ``refresh_dependencies``."""

    @staticmethod
    def _enable_when_key(condition, invert):
        """Comparable identity of a non-callable ``enable_when`` rule.

        A set / list / tuple is normalized the way the membership branch itself
        normalizes it, so the same rule spelled ``{1, 2}`` and ``[1, 2]`` compares
        equal and is not reported as a conflict. Callables have no usable identity
        here (a re-run ``_init`` builds a fresh lambda every time), so the caller
        only compares when both conditions are non-callable.
        """
        if isinstance(condition, (set, frozenset, list, tuple)):
            return ("membership", frozenset(condition), invert)
        return ("value", condition, invert)

    @staticmethod
    def _rule_ref_name(ref) -> str:
        """A rule reference's stable identity: a widget's objectName, or the name
        as given. Rules key on these, so re-wiring the same pair is recognisable."""
        return ref.objectName() if isinstance(ref, QtWidgets.QWidget) else str(ref)

    @staticmethod
    def _is_name_pattern(ref: str) -> bool:
        """True when *ref* is shorthand for several widgets — ``'b000-3'``, ``'a,b'``."""
        return any(c in ref for c in ",-")

    def _resolve_rule_refs(self, ui, refs) -> list:
        """Widgets for a rule's references: widget instances pass through, strings
        (single names or patterns) resolve against *ui*. A name that has not been
        registered yet simply contributes nothing — the caller decides whether that
        means "wait" or "wrong container"."""
        out = []
        for ref in refs:
            if isinstance(ref, QtWidgets.QWidget):
                out.append(ref)
            elif isinstance(ref, str):
                out.extend(self.get_widgets_by_string_pattern(ui, ref))
        return out

    def _watched_rule_names(self, *ref_groups) -> set:
        """Every objectName a rule cares about, patterns unpacked — the set an
        ``on_child_registered`` handler filters against before re-applying."""
        watched = set()
        for group in ref_groups:
            for name in group:
                watched.update(
                    self.unpack_names(name) if self._is_name_pattern(name) else [name]
                )
        return watched

    @staticmethod
    def _registration_signal(ui):
        """``ui``'s "a child registered" signal, or None if it has none.

        A ``MainWindow`` has one, so a declarative rule can wait for a name that has
        not arrived yet. An option box's ``Menu`` does not: whatever is on it at wire
        time is all there will ever be.
        """
        signal = getattr(ui, "on_child_registered", None)
        return signal if callable(getattr(signal, "connect", None)) else None

    def _warn_if_rule_is_dead(self, ui, rule, **roles):
        """Warn when a declarative rule can never fire.

        Resolving nothing is normal *while* a name is still unregistered — that is
        the order-independence :meth:`enable_when` and :meth:`text_from` are built
        on, and :meth:`_registration_signal` is what eventually delivers. Against a
        container with no such signal there is nothing left to arrive, so a rule that
        resolved nothing is not waiting, it is pointed at the wrong container.

        Worth a warning rather than silence because the failure has no symptom to
        follow: tentacle's Constrain / Snap buttons named ``widget.menu`` (the
        ``MenuMixin`` context menu) where their checkboxes were on
        ``widget.option_box.menu``, resolved to nothing, and relabelled never — with
        no exception, and nothing above DEBUG to say why.
        """
        if self._registration_signal(ui) is not None:
            return
        for role, widgets in roles.items():
            if not widgets:
                self.logger.warning(
                    f"[{rule}] could not resolve its {role} against "
                    f"{ui.objectName() or type(ui).__name__}, which has no "
                    f"on_child_registered — nothing further can arrive, so this rule "
                    f"can never fire. Are the names on a different container "
                    f"(widget.menu vs widget.option_box.menu)?"
                )

    def _rule_value_reader(self, value):
        """``read(widget) -> value`` for a declarative rule, honouring *value*.

        Shared by :meth:`enable_when`, :meth:`text_from` and :meth:`value_from`
        so "what does this control's value mean" keeps ONE answer: the
        ``_WIDGET_VALUE_READERS`` table, overridable per rule with a callable
        (applied to every source) or a ``{objectName: callable}`` mapping (for a
        mixed set — unlisted sources keep the default reader).
        """

        def read(widget):
            reader = (
                value.get(widget.objectName()) if isinstance(value, dict) else value
            )
            if callable(reader):
                return reader(widget)
            getter = self._widget_value_reader(widget)
            return getter(widget) if getter is not None else None

        return read

    def _rule_source_resolver(self, ui, refs, unpack: bool):
        """``resolve() -> [widget] | None`` for a rule's source references.

        Widget instances pass through; a string resolves against *ui*. An exact
        name that has not been registered yet returns ``None`` — the whole rule
        HOLDS rather than deciding on a partial reading — and so does a
        reference that is neither a widget nor a name.

        *unpack* decides what a pattern (``'chk024-26'``) means: one value per
        matched widget (:meth:`text_from`, :meth:`value_from`, whose sources
        feed a callable positionally), or a single lookup that simply will not
        resolve (:meth:`enable_when`, whose triggers are one-ref-one-value).
        """

        def resolve():
            out = []
            for ref in refs:
                if isinstance(ref, QtWidgets.QWidget):
                    out.append(ref)
                elif isinstance(ref, str) and unpack and self._is_name_pattern(ref):
                    out.extend(self.get_widgets_by_string_pattern(ui, ref))
                elif isinstance(ref, str):
                    widget = self._resolve_ui_widget(ui, ref)
                    if widget is None:
                        return None
                    out.append(widget)
                else:
                    return None
            return out

        return resolve

    def _wire_rule(
        self,
        ui,
        rule: str,
        registry: str,
        key,
        resolve_sources: Callable[[], Optional[list]],
        resolve_targets: Callable[[], list],
        apply: Callable[..., None],
        signal: Optional[str] = None,
        role: str = "sources",
    ):
        """Connect *apply* to its sources, keep it order-independent, register it.

        The machinery every declarative rule shares. :meth:`enable_when`,
        :meth:`text_from` and :meth:`value_from` differ only in what ``apply``
        READS its verdict from and what it WRITES; the wiring around that is
        identical, and lives here once:

          * connect each source's natural change signal (or *signal*, for a
            single source) to ``apply``, then apply immediately — a rule that is
            only connected leaves whatever the ``.ui`` shipped standing until the
            user touches something, which is already wrong for a source that
            starts non-default or was restored from session state;
          * re-connect and re-apply when ``ui.on_child_registered`` announces a
            watched name, plus once more after the current event (registration
            restores session state with signals blocked, so the first read can be
            pre-restore);
          * report a rule that can never fire (:meth:`_warn_if_rule_is_dead`);
          * store it in *registry* so :meth:`refresh_dependencies` re-applies it
            for bulk changes no signal announced.

        *role* names the sources in that report ("triggers" for
        :meth:`enable_when`), so the warning reads in the caller's own vocabulary.

        Returns:
            The rule's ``apply`` callable.
        """
        connected = set()

        def connect_sources():
            widgets = resolve_sources()
            if widgets is None:
                return
            for widget in widgets:
                if id(widget) in connected:
                    continue
                name = signal if (signal and len(widgets) == 1) else None
                name = name or self._value_change_signal(widget)
                sig = getattr(widget, name, None) if name else None
                if sig is None or not callable(getattr(sig, "connect", None)):
                    self.logger.warning(
                        f"[{rule}] no change signal for {widget.objectName()!r}"
                    )
                    continue
                sig.connect(apply)
                connected.add(id(widget))
            apply()

        # Pattern refs ('b000-3') can't be matched by exact name — unpack them.
        watched = self._watched_rule_names(*key)

        def on_registered(widget):
            if widget.objectName() not in watched:
                return
            connect_sources()
            apply()
            QtCore.QTimer.singleShot(0, apply)

        connect_sources()
        on_reg = self._registration_signal(ui)
        if on_reg is not None:
            on_reg.connect(on_registered)
        self._warn_if_rule_is_dead(
            ui, rule, **{role: resolve_sources(), "targets": resolve_targets()}
        )

        ui.__dict__.setdefault(registry, {})[key] = apply
        return apply

    def enable_when(
        self,
        ui,
        targets,
        trigger,
        condition=True,
        signal=None,
        value=None,
        invert=False,
    ):
        """Keep *targets* enabled exactly while *trigger*'s value satisfies
        *condition* — a declarative dependency, wired once.

        The one-line answer to "grey this out when it can't apply": a lower-level
        choice (output format, a master checkbox, a mode combo) makes some other
        control irrelevant, and the panel should say so instead of leaving a
        live dial the export ignores. Replaces the pattern of a per-trigger slot
        + a ``_sync_*`` helper + a mirrored ``toggle_multi`` ``on_True`` /
        ``on_False`` pair with one rule that reads as the sentence it encodes::

            sb.enable_when(ui, "cmb006", "cmb004", lambda fmt: fmt != "fbx")
            sb.enable_when(ui, "texture_max_size", "optimize_textures")
            sb.enable_when(ui, "s001,chk002", "cmb035", 0)           # index / data == 0
            sb.enable_when(ui, "d000", "cmb035", 0, invert=True)     # the other branch
            sb.enable_when(ui, "texture_write_back",
                           ["optimize_textures", "cmb005"], lambda opt, tpl: opt or tpl)

        Parameters:
            ui: The loaded UI (widgets resolve by objectName on it).
            targets: Widget(s) to enable/disable — an objectName pattern string
                (``'s000,b004-7'``), a widget, or a list of either.
            trigger: The controlling widget(s) — objectName / widget, or a list
                (the condition then receives one value per trigger, in order).
            condition: What "on" means for the trigger's value: a callable
                ``(value, …) -> bool``; a plain value (equality); a set / list /
                tuple of values (membership); or ``True`` (default: truthiness —
                the master-checkbox case). With MULTIPLE triggers every
                non-callable form is **all-of**: equality, membership and
                truthiness each have to hold for every trigger. A callable is
                handed one value per trigger and decides for itself, which is
                where any-of lives.
            signal: Change signal name (single trigger). Default: the widget's
                natural signal from the value table.
            value: Reader override — a callable ``(widget) -> value`` used for
                every trigger, or a ``{objectName: callable}`` mapping for a
                mixed set (unlisted triggers keep the default reader, which
                reads a combo's ``currentData`` when items carry data, else
                ``currentIndex``; buttons ``isChecked``; …).
            invert: Enable when the condition is NOT met.

        A rule that resolves nothing against a container that HAS no
        ``on_child_registered`` is reported (see :meth:`_warn_if_rule_is_dead`):
        nothing further can arrive there, so it is not waiting — the names are on
        another container.

        Order-independent by design: a target (or trigger) that isn't
        registered on *ui* yet — a ``WidgetComboBox`` row, an option-box menu
        item — is picked up when ``ui.on_child_registered`` announces it, and
        the rule is (re)applied then and once more after the current event
        (registration restores session state with signals blocked, so the
        first read can be pre-restore). Every rule is also re-applied by
        :meth:`refresh_dependencies` for bulk state changes made with signals
        blocked (a preset load). Wiring the same targets to the same triggers
        twice is a no-op, so an ``_init`` slot that re-runs can't stack rules.

        Returns:
            The rule's ``apply`` callable (handy as an ``on_loaded`` hook).
        """
        return self._gate_when(
            ui,
            targets,
            trigger,
            condition,
            signal,
            value,
            invert,
            rule="enable_when",
            registry="_enable_when_rules",
            effect=lambda widget, on: widget.setEnabled(on),
        )

    def show_when(
        self,
        ui,
        targets,
        trigger,
        condition=True,
        signal=None,
        value=None,
        invert=False,
    ):
        """Keep *targets* on screen exactly while *trigger*'s value satisfies
        *condition* -- :meth:`enable_when`'s visibility twin.

        Greying out says "this exists but does not apply"; hiding says "this
        does not exist for what you chose". A KTX2 encoder dial with PNG
        selected, a GLB-only optimisation with no GLB being written, an FBX
        preset on a USD export: the panel is smaller and reads truer without
        them. Same rule grammar, same order-independence, same bulk refresh
        (:meth:`refresh_dependencies`), same conflict report::

            sb.show_when(ui, "uastc_rdo", "texture_file_type", "ktx2")
            sb.show_when(ui, "secondary_max_size,glb_key_tolerance", "cmb004",
                         {"glb", "fbx_glb"})

        A plain widget hides itself. A row of a :class:`WidgetComboBox` (an
        option menu) goes through the combo's own
        :class:`~uitk.managers.field_visibility.FieldVisibility` instead, so
        the model row leaves the popup and the titled separator over a section
        whose every row is hidden stands down with them. Either way the
        widget's VALUE is untouched: a hidden field still saves, restores and
        reads -- the run reads what the panel holds, so a hidden dial must be
        one the run ignores (or one the caller resolves as off).

        Parameters and return value as :meth:`enable_when`.
        """
        return self._gate_when(
            ui,
            targets,
            trigger,
            condition,
            signal,
            value,
            invert,
            rule="show_when",
            registry="_show_when_rules",
            effect=self._set_field_visible,
        )

    @staticmethod
    def _set_field_visible(widget, on: bool) -> None:
        """:meth:`show_when`'s effect: the row's registry when *widget* is an
        option-menu row (:meth:`WidgetComboBox.host_of`), else the widget
        itself, marked as a field so a collapsing group leaves it hidden
        (:meth:`FieldVisibility.set_widget_visible`).

        ``host_of`` tests each ancestor's type. Asking each for ``fields``
        reached the MainWindow, whose ``__getattr__`` answers an unknown name
        with a whole-UI search -- per target, per firing.
        """
        # Deferred: widgetComboBox imports the switchboard.
        from uitk.widgets.widgetComboBox import WidgetComboBox

        host = WidgetComboBox.host_of(widget)
        if host is not None and host.fields.set_visible(host.field_key(widget), on):
            return
        FieldVisibility.set_widget_visible(widget, on)

    def _gate_when(
        self,
        ui,
        targets,
        trigger,
        condition,
        signal,
        value,
        invert,
        *,
        rule: str,
        registry: str,
        effect,
    ):
        """The rule :meth:`enable_when` and :meth:`show_when` share: predicate
        forms, the duplicate-key no-op and conflict report, the apply closure
        (*effect* is what it writes to each target) and the wiring."""
        trigger_refs = (
            list(trigger) if isinstance(trigger, (list, tuple)) else [trigger]
        )
        target_refs = list(targets) if isinstance(targets, (list, tuple)) else [targets]

        key = (
            tuple(map(self._rule_ref_name, trigger_refs)),
            tuple(map(self._rule_ref_name, target_refs)),
        )
        rules = ui.__dict__.setdefault(registry, {})
        if key in rules:
            # Re-wiring the same pair is a deliberate no-op so an ``_init`` slot
            # that re-runs cannot stack rules. A rule with DIFFERENT semantics
            # is a different matter: it used to vanish silently, leaving the
            # first rule in force and the caller none the wiser. Only report
            # when the difference is PROVABLE -- a re-run ``_init`` builds a new
            # lambda every time, so comparing callables by identity would cry
            # wolf on the very case the no-op exists for.
            prior = getattr(rules[key], "_enable_when_spec", None)
            if prior is not None and not callable(condition) and not callable(prior[0]):
                if self._enable_when_key(*prior) != self._enable_when_key(
                    condition, invert
                ):
                    self.logger.warning(
                        f"{rule}: a rule for {key[1]} on {key[0]} already "
                        f"exists with condition={prior[0]!r} invert={prior[1]}; "
                        f"the new condition={condition!r} invert={invert} was "
                        f"DROPPED. Wire one rule per (trigger, target) pair, or "
                        f"express both in a single callable condition."
                    )
            return rules[key]

        if callable(condition):
            predicate = condition
        elif isinstance(condition, (set, frozenset, list, tuple)):
            allowed = set(condition)
            # All-of, one value per trigger. This branch (and the equality one
            # below) used to read `v` and discard `*rest`, so a multi-trigger
            # rule was decided by the FIRST trigger alone. `condition is True`
            # was already all-of, so all-of is what makes the non-callable
            # family consistent; any-of stays expressible as a callable.
            predicate = lambda *vals: all(v in allowed for v in vals)  # noqa: E731
        elif condition is True:
            predicate = lambda *vals: all(bool(v) for v in vals)  # noqa: E731
        else:
            predicate = lambda *vals: all(v == condition for v in vals)  # noqa: E731

        resolve_triggers = self._rule_source_resolver(ui, trigger_refs, unpack=False)

        def resolve_targets():
            return self._resolve_rule_refs(ui, target_refs)

        read = self._rule_value_reader(value)

        def apply(*_):
            triggers = resolve_triggers()
            if triggers is None:
                return
            try:
                on = bool(predicate(*[read(w) for w in triggers]))
            except Exception as e:  # a half-built trigger; try again on the next signal
                self.logger.debug(f"[{rule}] condition raised: {e}")
                return
            if invert:
                on = not on
            for w in resolve_targets():
                effect(w, on)

        # Carried so a later conflicting wire-up can be named rather than
        # dropped in silence (see the duplicate-key branch above).
        apply._enable_when_spec = (condition, invert)
        return self._wire_rule(
            ui,
            rule,
            registry,
            key,
            resolve_triggers,
            resolve_targets,
            apply,
            signal,
            role="triggers",
        )

    def text_from(
        self,
        ui,
        targets: Union[str, Any, List[Any]],
        sources: Union[str, Any, List[Any]],
        formatter: Callable[..., str],
        signal: Optional[str] = None,
        value: Optional[
            Union[Callable[[Any], Any], Dict[str, Callable[[Any], Any]]]
        ] = None,
    ) -> Callable[[], None]:
        """Keep *targets*' text derived from *sources* — a self-labelling widget,
        wired once.

        The text counterpart of :meth:`enable_when`: that one answers "grey this out
        when it can't apply", this one answers "say what this will do". A control
        whose behaviour is configured elsewhere — an option box, a mode combo —
        reads as a mystery until it names its own outcome, and on a marking menu
        there is no dialog to read first::

            sb.text_from(menu, widget, "s003", "Crease {}".format)
            sb.text_from(menu, widget, "chk024-26",
                         lambda *on: f"Constrain: {'ON' if any(on) else 'OFF'}")
            sb.text_from(menu, widget, ["cmb_scope", "cmb_save", "cmb_format"],
                         self._export_button_text,
                         value={"cmb_format": lambda w: w.currentText()})

        Hand-wiring this is three steps — read, format, ``setText`` — plus a fourth
        that is easy to forget: applying it at WIRE TIME. A rule that is only
        connected leaves whatever text the ``.ui`` shipped standing until the user
        touches something, which is already wrong whenever a source starts
        non-default or was restored from session state.

        Parameters:
            ui: The loaded UI, or whatever the names resolve against — an option
                box's ``menu`` is the common one.
            targets: Widget(s) to relabel — an objectName pattern string
                (``'tb003'``, ``'b004-7'``), a widget, or a list of either. Every
                resolved target gets the same text.
            sources: The widget(s) the text is derived from — objectName / pattern
                / widget, or a list of those. Patterns UNPACK here (unlike
                :meth:`enable_when`'s trigger), so ``'chk024-26'`` feeds the
                formatter three values.
            formatter: ``callable(*values) -> str``, one value per resolved source
                in order. ``"Crease {}".format`` is a formatter.
            signal: Change signal name (single source). Default: the widget's
                natural signal from the value table.
            value: Reader override — a callable ``(widget) -> value`` used for every
                source, or a ``{objectName: callable}`` mapping for a mixed set
                (unlisted sources keep the default reader). The default reads a
                combo's ``currentData`` when its items carry data, else
                ``currentIndex``; pass ``currentText`` when the item's LABEL is what
                the text should say.

        Order-independent, idempotent and bulk-refreshable exactly as
        :meth:`enable_when` — they share the machinery and the notes there apply,
        including the report when a rule can never fire. A source named EXACTLY that
        hasn't been registered yet holds the whole rule rather than formatting a
        partial reading; a pattern contributes whatever it matches so far, and is
        re-applied when the rest arrive.

        A target that is also a source is safe: the write-back cannot re-enter the
        rule. A formatter that raises leaves the current text standing rather than
        blanking it, so a half-built source costs nothing.

        Returns:
            The rule's ``apply`` callable (handy as an ``on_loaded`` hook).
        """
        source_refs = list(sources) if isinstance(sources, (list, tuple)) else [sources]
        target_refs = list(targets) if isinstance(targets, (list, tuple)) else [targets]

        key = (
            tuple(map(self._rule_ref_name, source_refs)),
            tuple(map(self._rule_ref_name, target_refs)),
        )
        rules = ui.__dict__.setdefault("_text_from_rules", {})
        if key in rules:
            # Re-wiring the same pair is a deliberate no-op so an ``_init`` slot that
            # re-runs cannot stack rules. No conflict warning like enable_when's: a
            # formatter is a fresh callable every run, so a genuine difference is
            # never provable and the check could only cry wolf.
            return rules[key]

        resolve_sources = self._rule_source_resolver(ui, source_refs, unpack=True)

        def resolve_targets():
            return self._resolve_rule_refs(ui, target_refs)

        read = self._rule_value_reader(value)

        # A target that is ALSO a source (a line edit that reformats itself) would
        # have setText re-enter apply through textChanged and never stop. A hang is
        # the one failure mode a UI helper must not have, so the write is fenced.
        writing = []

        def apply(*_):
            if writing:
                return
            widgets = resolve_sources()
            if not widgets:
                return
            try:
                text = formatter(*[read(w) for w in widgets])
            except Exception as e:  # a half-built source; try again on the next signal
                self.logger.debug(f"[text_from] formatter raised: {e}")
                return
            writing.append(True)
            try:
                for widget in resolve_targets():
                    setter = getattr(widget, "setText", None)
                    if callable(setter):
                        setter(text)
                    else:
                        self.logger.warning(
                            f"[text_from] {widget.objectName()!r} has no setText"
                        )
            finally:
                writing.clear()

        return self._wire_rule(
            ui,
            "text_from",
            "_text_from_rules",
            key,
            resolve_sources,
            resolve_targets,
            apply,
            signal,
        )

    def value_from(
        self,
        ui,
        targets: Union[str, Any, List[Any]],
        sources: Union[str, Any, List[Any]],
        resolver: Callable[..., Any],
        signal: Optional[str] = None,
        value: Optional[
            Union[Callable[[Any], Any], Dict[str, Callable[[Any], Any]]]
        ] = None,
    ) -> Callable[[], None]:
        """Keep *targets*' VALUE derived from *sources* — a control that follows
        the dials it stands for, wired once.

        The third of the declarative family: :meth:`enable_when` answers "grey
        this out when it can't apply", :meth:`text_from` "say what this will
        do", and this one "say WHICH of my presets you are on". The case it
        exists for is a summary control the user can also drive around: a
        Quality combo that fills Resolution / Samples has to fall back to
        *Custom* the moment either dial stops matching a preset, or it keeps
        naming a tier the bake is no longer using::

            sb.value_from(ui, "cmb000", ["cmb_resolution", "spn_samples"],
                          self._preset_for_dials)      # -> "mobile" | "Custom"

            sb.value_from(m, "cmb_mode", "chk_advanced",
                          lambda on: "advanced" if on else "basic")

        Hand-wiring this is the same four steps as :meth:`text_from` — read,
        resolve, write, and apply at WIRE TIME — plus a fifth that only bites
        here: a naive write-back re-enters through the target's own change
        signal. The write is fenced, so a target may be its own source.

        Parameters:
            ui: The loaded UI, or whatever the names resolve against — an option
                box's ``menu`` is the common one.
            targets: Widget(s) to drive — an objectName pattern string
                (``'cmb000'``, ``'s004-7'``), a widget, or a list of either.
                Every resolved target gets the same value.
            sources: The widget(s) the value is derived from — objectName /
                pattern / widget, or a list of those. Patterns UNPACK (as in
                :meth:`text_from`), so ``'chk024-26'`` feeds three values.
            resolver: ``callable(*values) -> value``, one value per resolved
                source in order. Returning ``None`` DECLINES — the target is
                left exactly as the user left it — so "I have no opinion about
                this combination" needs no sentinel.
            signal: Change signal name (single source). Default: the widget's
                natural signal from the value table.
            value: Reader override for the SOURCES — a callable ``(widget) ->
                value`` for every one, or a ``{objectName: callable}`` mapping
                for a mixed set. (Writes are dispatched by widget type; see
                :meth:`_widget_value_writer`.)

        The write is the mirror of the read: a combo takes the item whose DATA,
        then whose LABEL, then whose ROW matches (a value matching none of the
        three is reported and skipped, never coerced to row 0); every other type
        goes to ``ValueManager.set_value``, which coerces where that is
        unambiguous (``"8"`` into a spin box) and leaves the widget alone where
        it is not. Writes are NOT signal-blocked — a derived value is a real
        change and the target's own slot is entitled to see it (that is what
        lets a preset combo re-apply the rest of its preset).

        Order-independent, idempotent and bulk-refreshable exactly as
        :meth:`enable_when` and :meth:`text_from` — they share the machinery
        (:meth:`_wire_rule`) and the notes there apply, including the report
        when a rule can never fire.

        Returns:
            The rule's ``apply`` callable (handy as an ``on_loaded`` hook).
        """
        source_refs = list(sources) if isinstance(sources, (list, tuple)) else [sources]
        target_refs = list(targets) if isinstance(targets, (list, tuple)) else [targets]

        key = (
            tuple(map(self._rule_ref_name, source_refs)),
            tuple(map(self._rule_ref_name, target_refs)),
        )
        rules = ui.__dict__.setdefault("_value_from_rules", {})
        if key in rules:
            # Re-wiring the same pair is a deliberate no-op so an ``_init`` slot
            # that re-runs cannot stack rules (no conflict warning, for the same
            # reason as text_from's: a resolver is a fresh callable every run).
            return rules[key]

        resolve_sources = self._rule_source_resolver(ui, source_refs, unpack=True)

        def resolve_targets():
            return self._resolve_rule_refs(ui, target_refs)

        read = self._rule_value_reader(value)

        # A target is very often ALSO the thing whose change re-enters here (a
        # preset combo that writes its dials back), and writes are deliberately
        # not signal-blocked — so the fence, not silence, is what bounds it.
        writing = []

        def apply(*_):
            if writing:
                return
            widgets = resolve_sources()
            if not widgets:
                return
            try:
                derived = resolver(*[read(w) for w in widgets])
            except Exception as e:  # a half-built source; retry on the next signal
                self.logger.debug(f"[value_from] resolver raised: {e}")
                return
            if derived is None:  # the resolver declined — leave the target alone
                return
            writing.append(True)
            try:
                for widget in resolve_targets():
                    writer = self._widget_value_writer(widget)
                    if writer is None:
                        self.logger.warning(
                            f"[value_from] no value setter for "
                            f"{widget.objectName()!r} ({type(widget).__name__})"
                        )
                        continue
                    try:
                        writer(widget, derived)
                    except Exception as e:
                        self.logger.warning(
                            f"[value_from] {widget.objectName()!r} rejected "
                            f"{derived!r}: {e}"
                        )
            finally:
                writing.clear()

        return self._wire_rule(
            ui,
            "value_from",
            "_value_from_rules",
            key,
            resolve_sources,
            resolve_targets,
            apply,
            signal,
        )

    #: The declarative-rule registries :meth:`refresh_dependencies` re-applies.
    _DEPENDENCY_REGISTRIES = (
        "_enable_when_rules",
        "_show_when_rules",
        "_text_from_rules",
        "_value_from_rules",
    )

    def refresh_dependencies(self, ui) -> None:
        """Re-apply every declarative rule on *ui* — :meth:`enable_when`'s,
        :meth:`show_when`'s, :meth:`text_from`'s and :meth:`value_from`'s — for bulk value changes
        made with signals blocked (a preset load, a programmatic restore) that
        no trigger signal announced."""
        for registry in self._DEPENDENCY_REGISTRIES:
            for apply in list(ui.__dict__.get(registry, {}).values()):
                apply()
