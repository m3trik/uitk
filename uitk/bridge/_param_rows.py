# !/usr/bin/python
# coding=utf-8
"""The parameter rows of a bridge panel: one part of :class:`~uitk.bridge.slots.BridgeSlotsBase`.

The "Parameters" group built from the registry's :class:`AttributeSpec` rows
(sections, inline cells, action buttons), their tooltips (static and live), and
the two per-row states a panel keeps current: visibility (does the selected
template read the knob?) and enablement (is it in effect right now?).
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional, Tuple

from qtpy import QtCore, QtWidgets

from uitk.widgets._layout_items import _LayoutItems
from uitk.widgets.separator import Separator
from uitk.managers.field_visibility import FieldVisibility

from uitk.bridge.spec import AttributeSpec, KindFactory
from uitk.bridge.tooltip import Tooltip


class _ParamRowsMixin(object):
    """Parameter rows: build, read/write, tooltips, visibility and enablement.

    Reads the composed panel's ``params_module`` (``PARAMS`` /
    ``referenced_keys`` / ``SUPERSESSIONS``), ``ui``, ``sb.tooltip`` and the
    template combo's selection (for the default relevance hook).
    """

    # ------------------ Widget kind -- multi-line types ---------------
    # Kinds whose widgets are composite (line edit + button, list +
    # buttons, ...) or list-shaped, and must NOT have their parent row
    # clamped to 19px because they are taller than one input line.
    TALL_KINDS: Tuple[str, ...] = ("path", "file", "files", "file_list", "check_list")

    # ------------------ Supersessions ---------------------------------
    # ``(trigger key, governed keys, reason)`` triples: while *trigger* reads
    # truthy, the *governed* rows grey out with *reason* as their tooltip --
    # the "an Auto toggle takes over the controls it replaces" shape, declared
    # as data. Read from the parameter REGISTRY (``params_module.SUPERSESSIONS``)
    # when it declares them, because which knob supersedes which is a property
    # of the parameter set, not of a DCC's panel -- so both DCCs' panels
    # sharing one registry behave identically without either restating it.
    # This class attr is the fallback for a panel whose registry declares none.
    PARAM_SUPERSESSIONS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = ()

    def format_param_tooltip(self, spec: AttributeSpec) -> str:
        """Hook: build the rich-text tooltip for one parameter spec."""
        return Tooltip.format_param_tooltip(spec)

    # ------------------ Parameter widgets -----------------------------

    def _build_param_widgets(self) -> None:
        """Inject a 'Parameters' group between the Output Dir row and Send.

        Builds one row widget per registered :class:`AttributeSpec` via
        :meth:`uitk.bridge.spec.KindFactory.make_widget` -- the shared registry powers
        every kind including custom ones the bridge registered. A spec with
        ``inline`` set is appended to the PREVIOUS row instead of claiming one
        of its own (see :meth:`_build_inline_cell`).
        """
        grp = QtWidgets.QGroupBox("Parameters", self.ui.grp_process)
        vbox = QtWidgets.QVBoxLayout(grp)
        vbox.setContentsMargins(2, 4, 2, 2)
        vbox.setSpacing(0)

        host_row: Optional[QtWidgets.QWidget] = None
        for key, spec in self.params_module.PARAMS.items():
            # Start of a new category -> a titled divider above its first row.
            # (One separator per section; sections are expected contiguous.)
            section = getattr(spec, "section", "") or ""
            self._param_section[key] = section
            new_section = bool(section) and section not in self._section_separators
            if new_section:
                sep = Separator(grp, title=section)
                vbox.addWidget(sep)
                self._section_separators[section] = sep

            tooltip_html = self.format_param_tooltip(spec)
            # An inline spec joins the previous row; a section's opening spec
            # starts one regardless, so a divider is never followed by a row
            # whose first control belongs to the section above it.
            inline = getattr(spec, "inline", False) and host_row is not None
            if inline and not new_section:
                self._build_inline_cell(spec, key, host_row, tooltip_html)
                continue

            row = QtWidgets.QWidget(grp)
            hbox = QtWidgets.QHBoxLayout(row)
            hbox.setContentsMargins(0, 0, 0, 0)
            hbox.setSpacing(2)

            label = QtWidgets.QLabel(spec.display_label + ":", row)
            label.setMinimumWidth(self.LABEL_MIN_WIDTH)
            label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            label.setToolTip(tooltip_html)
            self._param_labels[key] = label

            widget = self._make_param_widget(spec, key, row, tooltip_html)

            hbox.addWidget(label)
            hbox.addWidget(widget, 1)
            vbox.addWidget(row)

            self._param_rows[key] = row
            host_row = row

        parent_layout = self.ui.grp_process.layout()
        insert_at = parent_layout.indexOf(self.ui.b000)
        parent_layout.insertWidget(insert_at, grp)
        self._param_group = grp

        # Everything the panel shows conditionally, in one registry. The
        # dividers and the group are registered WITH the rows rather than
        # chased separately at refresh time, which is the bookkeeping this
        # used to carry by hand.
        fields = FieldVisibility()
        for key, row in self._param_rows.items():
            fields.register(key, row, section=self._param_section.get(key))
        for section, sep in self._section_separators.items():
            fields.divider(section, sep)
        self._param_fields = fields.group(grp)

    def _make_param_widget(
        self,
        spec: AttributeSpec,
        key: str,
        parent: QtWidgets.QWidget,
        tooltip_html: str,
    ) -> QtWidgets.QWidget:
        """Build, name, clamp and register one spec's widget."""
        widget = KindFactory.make_widget(spec, parent)
        # Prefix the registry key so two panels in the same window
        # can host the same AttributeSpec without objectName clashes.
        widget.setObjectName(f"param_{key.lower()}")
        if spec.kind not in self.TALL_KINDS:
            widget.setMinimumHeight(19)
            widget.setMaximumHeight(19)
        widget.setToolTip(tooltip_html)
        self._param_widgets[key] = widget
        return widget

    def _build_inline_cell(
        self,
        spec: AttributeSpec,
        key: str,
        host_row: QtWidgets.QWidget,
        tooltip_html: str,
    ) -> QtWidgets.QWidget:
        """Append *spec* to the right of *host_row*'s widget, as its own cell.

        The cell (label + widget) is what gets registered as this key's "row",
        so :meth:`set_param_enabled` greys only this control and
        :meth:`_refresh_param_visibility` can hide it without taking the host
        control with it. The label carries no minimum width -- an inline
        modifier reads as a suffix to the value beside it, not as a second
        left-aligned column -- and the cell takes no stretch, so the host
        widget keeps the row's free space.
        """
        cell = QtWidgets.QWidget(host_row)
        hbox = QtWidgets.QHBoxLayout(cell)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(2)

        label = QtWidgets.QLabel(spec.display_label + ":", cell)
        label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        label.setToolTip(tooltip_html)
        self._param_labels[key] = label

        widget = self._make_param_widget(spec, key, cell, tooltip_html)

        hbox.addWidget(label)
        hbox.addWidget(widget)
        host_row.layout().addWidget(cell)

        self._param_rows[key] = cell
        return widget

    def live_param_tooltips(self) -> Dict[str, Callable[[], str]]:
        """Hook: ``{param key: provider}`` for rows whose tooltip tracks LIVE state.

        :meth:`format_param_tooltip` runs once, at build time, so a row that
        describes something the *session* owns -- a scene set the user defines
        from a selection, a path that resolves per scene -- is stale the moment
        that state moves. A provider registered here is called on every hover
        instead (:mod:`uitk.widgets.mixins.tooltip_mixin`), so the row can
        answer "what is captured right now?" with no refresh plumbing.

        A provider returns the WHOLE tooltip, so fold the static text back in
        with ``self.format_param_tooltip(spec)`` -- binding replaces the
        widget's tooltip rather than appending to it. Pair it with
        :meth:`pythontk.TooltipFormat.stored_items`
        for the usual "here is what you captured" list.

        Bound to the row's label AND its control -- both are hover targets for
        the same row. An ``action`` row's buttons keep their own per-choice
        tips: those describe the *click*, not the contents.

        Returns:
            (dict) Param key -> zero-argument callable returning tooltip HTML.
            Prefer a bound method over a closure: the tooltip surface weakrefs
            bound-method providers, so the binding can't outlive this panel.
            Unknown keys are ignored, so a shared base may offer a row that
            only some of its panels register.
        """
        return {}

    def live_param_tooltip_blocks(self) -> Dict[str, Callable[[], str]]:
        """Hook: ``{param key: provider}`` for a live block APPENDED to a row's tips.

        The composable counterpart to :meth:`live_param_tooltips`. That one owns
        the WHOLE tooltip, which is right for a row whose static text is the
        thing going stale -- and wrong for an ``action`` row, whose buttons each
        carry their own per-choice description. Replacing three specific answers
        ("what does Clear do?") with one general one is a bad trade, and the
        buttons are exactly where the user is standing when they wonder what the
        row currently holds.

        A block provider returns only the live part, so every hover target on
        the row -- label, control, and each action button -- keeps its own text
        and gains the current contents underneath it.

        Register a key in ONE of the two hooks: binding replaces a widget's
        provider rather than stacking, and blocks are installed second, so a
        key in both silently loses its whole-tooltip provider on the label and
        the control while the buttons keep only the block.

        Returns:
            (dict) Param key -> zero-argument callable returning the live HTML
            block (see
            :meth:`pythontk.TooltipFormat.stored_items`).
            Unknown keys are ignored.
        """
        return {}

    def _bind_live_param_tooltips(self) -> None:
        """Install every live tooltip provider on its row."""
        for key, provider in (self.live_param_tooltips() or {}).items():
            targets = [self._param_widgets.get(key), self._param_labels.get(key)]
            self.sb.tooltip.bind([t for t in targets if t is not None], provider)
        for key, provider in (self.live_param_tooltip_blocks() or {}).items():
            self._bind_live_param_block(key, provider)

    def _bind_live_param_block(self, key: str, provider) -> None:
        """Append *provider*'s live block to every hover target of row *key*.

        The composed providers are plain closures, so the tooltip surface stores
        them directly rather than through its bound-method weakref. That keeps
        this slot alive exactly as long as the widgets it bound -- which the
        panel owns and destroys together -- rather than beyond them.
        """
        params = getattr(self.params_module, "PARAMS", {}) or {}
        spec = params.get(key)
        if spec is None:
            return
        widget = self._param_widgets.get(key)
        static = self.format_param_tooltip(spec)
        targets = [
            (t, static) for t in (widget, self._param_labels.get(key)) if t is not None
        ]
        # An action row's buttons: each keeps its own per-choice description,
        # promoted to HTML first (see :meth:`_as_tooltip_html`).
        for button in (getattr(widget, "_action_buttons", None) or {}).values():
            own = self._pristine_tooltip(button)
            targets.append((button, self._as_tooltip_html(own) if own else static))
        for target, base in targets:
            self.sb.tooltip.bind(target, lambda _base=base, _p=provider: _base + _p())

    #: Dynamic property holding a widget's own tooltip, captured before any
    #: live provider could overwrite it (see :meth:`_pristine_tooltip`).
    _STATIC_TOOLTIP_PROP = "_bridge_static_tooltip"

    @classmethod
    def _pristine_tooltip(cls, widget) -> str:
        """The widget's OWN tooltip, from before a live provider rewrote it.

        The tooltip surface writes each computed string back onto the widget as
        it renders, so ``toolTip()`` stops being the widget's own text after the
        first hover. Reading it again on a later bind would fold the previous
        live block into the new base and stack a second copy on every rebind
        (measured: two hovers, two lists). The first read is stashed as a Qt
        dynamic property and reused from then on, so binding is idempotent.
        """
        stored = widget.property(cls._STATIC_TOOLTIP_PROP)
        if stored is None:
            stored = widget.toolTip()
            widget.setProperty(cls._STATIC_TOOLTIP_PROP, stored)
        return stored

    #: An opening tag, as opposed to a bare ``<`` used as a less-than sign.
    _HTML_TAG_RE = re.compile(r"<[a-zA-Z/!]")

    @classmethod
    def _as_tooltip_html(cls, text: str) -> str:
        """Promote a plain-text tooltip to HTML, preserving its line breaks.

        Qt renders a tooltip as rich text the moment it contains a tag, so
        appending a live HTML block to a plain-text base silently collapses
        every newline that base was relying on. Already-rich text passes
        through untouched -- detected by an opening TAG rather than a bare
        ``<``, so a tip that merely says ``width < height`` is still escaped
        instead of having the comparison swallowed as markup.
        """
        if not text or cls._HTML_TAG_RE.search(text):
            return text
        from html import escape

        return "<p style='margin:0'>" + escape(text).replace("\n", "<br>") + "</p>"

    def _wire_action_params(self) -> None:
        """Connect ``action``-kind param buttons to same-named slot methods.

        An ``action`` row's container exposes ``_action_buttons``
        (``{action_id: QPushButton}``, see :mod:`uitk.bridge.spec`); each id
        that names a callable on this slot is wired to it, so a registry can
        declare panel actions as data with zero per-panel wiring code. An id
        with no matching method is disabled rather than silently inert.
        """
        for key, widget in self._param_widgets.items():
            buttons = getattr(widget, "_action_buttons", None)
            if not buttons:
                continue
            for action_id, btn in buttons.items():
                handler = getattr(self, action_id, None)
                if callable(handler):
                    btn.clicked.connect(handler)
                else:
                    btn.setEnabled(False)
                    btn.setToolTip(
                        f"No handler '{action_id}' on {type(self).__name__}."
                    )

    def set_param_enabled(self, key: str, enabled: bool, reason: str = "") -> None:
        """Grey out (or re-enable) one parameter row, with *reason* as its tooltip.

        For parameters whose relevance depends on live session state rather
        than on the template -- e.g. a suffix-pairing fallback that the scene's
        explicit set makes moot. Visibility already answers "does this template
        use the knob?" (:meth:`_refresh_param_visibility`); this answers "is it
        in effect right now?", which is a different question and reads better
        greyed than hidden -- the user can still see the value that *would*
        apply, and why it doesn't.

        The row container itself stays enabled and carries *reason*: Qt does
        not deliver tooltip events to disabled widgets, but a disabled child
        doesn't consume the hover either, so the parent's tooltip is what
        surfaces. Unknown keys are ignored -- a shared base can offer the row
        without every panel registering it.

        Another parameter's inline cell (see :meth:`_build_inline_cell`) lives
        inside this row but is NOT part of it, so it is skipped: greying the
        value an "Auto" toggle superseded must not grey the toggle sitting
        beside it, or the user cannot turn it back off.
        """
        row = self._param_rows.get(key)
        if row is None:
            return
        others = {r for k, r in self._param_rows.items() if k != key}
        layout = row.layout()
        children = _LayoutItems.widgets(layout) if layout is not None else []
        for child in children:
            if child not in others:
                child.setEnabled(enabled)
        row.setToolTip("" if enabled else reason)

    def _wire_enablement_refresh(self) -> None:
        """Re-run :meth:`_refresh_param_enablement` on panel show + trigger edits.

        Enablement keys off LIVE session state, which can change while the
        panel is closed (a new scene, a set deleted from the outliner). The
        template-change trigger alone would leave a row greyed for the
        PREVIOUS scene locked out in the next one -- worse than merely stale,
        because the control it hides is the one now in effect.

        The supersession triggers are the other source: a parameter whose own
        value decides whether OTHER rows apply has to re-evaluate on the
        click, not on the next show, or the rows it governs stay live for a
        mode that no longer reads them.

        A panel whose root widget isn't a uitk ``MainWindow`` has no
        ``on_show`` to hook; that's a no-op, not an error.
        """
        on_show = getattr(self.ui, "on_show", None)
        if on_show is not None:
            on_show.connect(self._refresh_param_enablement)
        for trigger, _governed, _reason in self.param_supersessions():
            widget = self._param_widgets.get(trigger)
            if widget is not None:
                KindFactory.connect_changed(
                    widget, lambda *_: self._refresh_param_enablement()
                )

    def param_supersessions(self) -> Tuple[Tuple[str, Tuple[str, ...], str], ...]:
        """The ``(trigger, governed, reason)`` triples in effect for this panel.

        The registry's own declaration wins; :attr:`PARAM_SUPERSESSIONS` is the
        fallback. Override to compute them.
        """
        declared = getattr(self.params_module, "SUPERSESSIONS", None)
        return tuple(declared if declared is not None else self.PARAM_SUPERSESSIONS)

    def _refresh_param_enablement(self) -> None:
        """Re-evaluate which rows are *in effect*, and grey the rest.

        Called on every template change, every panel show, and every edit of a
        supersession trigger; panels also call it themselves after an action
        that changes the state it keys off. The default applies the declared
        supersessions (:meth:`param_supersessions`); a subclass adds the
        checks that need live session state -- calling ``super()`` first, or
        the declared ones stop being applied -- driving
        :meth:`set_param_enabled` for each.

        Must not touch ``self.bridge``: this runs during panel construction,
        where the engine may be an optional package the user declined to
        install.
        """
        for trigger, governed, reason in self.param_supersessions():
            if trigger not in self._param_widgets:
                continue
            active = bool(self._read_param(trigger))
            for key in governed:
                self.set_param_enabled(key, not active, reason if active else "")

    def _read_param(self, key: str) -> Any:
        """Extract the current value via the registered KindHandler."""
        return KindFactory.read_value(self._param_widgets[key])

    def _write_param(self, key: str, value: Any) -> None:
        """Push *value* into the widget for *key* via the KindHandler."""
        KindFactory.set_value(self._param_widgets[key], value)

    def _set_param_choices(self, key: str, choices) -> None:
        """Repopulate the entries of a choice-driven param (``choice`` /
        ``check_list``) at runtime.

        The hook for parameters whose real entry set is only knowable in the
        live session -- installed app versions, deployable scripts, scene
        contents. The registry declares the kind and any static entries; the
        panel pushes the discovered ones in here from its ``__init__``.
        """
        KindFactory.set_choices(self._param_widgets[key], choices)

    def collect_param_values(self) -> Dict[str, Any]:
        """Snapshot every widget's current value, regardless of visibility.

        ``action`` rows carry no value (their buttons are commands, not
        data) and are excluded, so send params stay purely value-shaped.
        """
        return {
            key: self._read_param(key)
            for key, widget in self._param_widgets.items()
            if not hasattr(widget, "_action_buttons")
        }

    def _relevant_param_keys(self) -> Optional[set]:
        """Hook: the param keys whose rows should be visible for the current
        selection, or ``None`` to skip the visibility update entirely (no
        template selected / unreadable source).

        Default: the placeholder keys referenced by the active template file
        (the script-substitution bridges). Run-mode panels — e.g. a single
        runner driven by a ``--stop-after``-style mode rather than per-template
        files — override this to gate visibility on the selected mode, so the
        parameter UI stays dynamic the same way the DCC bridges' does.
        """
        pair = self._selected_template_mode()
        if not pair:
            return None
        template, _mode = pair
        path = self.template_dir / f"{template}{self.TEMPLATE_EXTENSION}"
        if not path.is_file():
            return None
        return self.params_module.referenced_keys(path.read_text(encoding="utf-8"))

    def _refresh_param_visibility(self) -> None:
        """Show only the rows relevant to the current selection.

        Delegates the "which keys are relevant?" decision to
        :meth:`_relevant_param_keys` so subclasses can drive visibility from a
        template file (default) or a run mode; the row toggling, the dividers,
        the empty group and the height re-fit are :class:`FieldVisibility`.
        """
        used = self._relevant_param_keys()
        if used is None or self._param_fields is None:
            return
        self._param_fields.show(used)
