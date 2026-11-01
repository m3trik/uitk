# !/usr/bin/python
# coding=utf-8
from typing import Any, Callable, Dict, List, Optional, Union
from qtpy import QtWidgets, QtCore
from uitk.managers.field_visibility import FieldVisibility


class _Rules:
    """Declarative widget rules behind the Switchboard: ``enable_when`` /
    ``show_when`` / ``text_from`` / ``value_from`` on one shared wiring core, plus
    ``refresh_dependencies``. Stateless: a rule lives in its UI's ``__dict__``.
    """

    def __init__(self, logger, names, values):
        self._logger = logger  # () -> the Switchboard's logger, read per call
        self._names = names  # name patterns ('b000-3') resolve against a UI
        self._values = values  # the value / change-signal tables every rule reads

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
                out.extend(self._names.get_widgets_by_string_pattern(ui, ref))
        return out

    def _watched_rule_names(self, *ref_groups) -> set:
        """Every objectName a rule cares about, patterns unpacked — the set an
        ``on_child_registered`` handler filters against before re-applying."""
        watched = set()
        for group in ref_groups:
            for name in group:
                watched.update(
                    self._names.unpack_names(name)
                    if self._is_name_pattern(name)
                    else [name]
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
                self._logger().warning(
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
            getter = self._values.widget_value_reader(widget)
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
                    out.extend(self._names.get_widgets_by_string_pattern(ui, ref))
                elif isinstance(ref, str):
                    widget = self._values.resolve_ui_widget(ui, ref)
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
                name = name or self._values.value_change_signal(widget)
                sig = getattr(widget, name, None) if name else None
                if sig is None or not callable(getattr(sig, "connect", None)):
                    self._logger().warning(
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
                    self._logger().warning(
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
                self._logger().debug(f"[{rule}] condition raised: {e}")
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
                self._logger().debug(f"[text_from] formatter raised: {e}")
                return
            writing.append(True)
            try:
                for widget in resolve_targets():
                    setter = getattr(widget, "setText", None)
                    if callable(setter):
                        setter(text)
                    else:
                        self._logger().warning(
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
                self._logger().debug(f"[value_from] resolver raised: {e}")
                return
            if derived is None:  # the resolver declined — leave the target alone
                return
            writing.append(True)
            try:
                for widget in resolve_targets():
                    writer = self._values.widget_value_writer(widget)
                    if writer is None:
                        self._logger().warning(
                            f"[value_from] no value setter for "
                            f"{widget.objectName()!r} ({type(widget).__name__})"
                        )
                        continue
                    try:
                        writer(widget, derived)
                    except Exception as e:
                        self._logger().warning(
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
        for registry in self._DEPENDENCY_REGISTRIES:
            for apply in list(ui.__dict__.get(registry, {}).values()):
                apply()
