# !/usr/bin/python
# coding=utf-8
"""The parameter rows of a bridge panel: one part of :class:`~uitk.bridge.slots.BridgeSlotsBase`.

The "Parameters" group built from the registry's :class:`AttributeSpec` rows
(sections, inline cells, action buttons), their tooltips (static and live), and
the two per-row states a panel keeps current: visibility (does the selected
template read the knob?) and enablement (is it in effect right now?) -- plus
the one the user keeps: which sections are folded.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, Optional

from qtpy import QtCore, QtWidgets

from uitk.widgets._layout_items import _LayoutItems
from uitk.widgets.separator import Separator
from uitk.managers.field_visibility import FieldVisibility
from uitk.managers.window_height import WindowHeight

from uitk.bridge.spec import AttributeSpec, KindFactory

if TYPE_CHECKING:  # annotation only; the facade imports this module
    from uitk.bridge.slots import BridgeSlotsBase


class _ParamRows(object):
    """A bridge panel's parameter rows: build, read/write, tooltips, visibility, enablement.

    Owns the rows and their index (control, row, label, section per key), the
    section dividers, the panel's :class:`FieldVisibility`, the folded sections
    and the key set on screen. Reads the panel's ``params_module``, ``ui``,
    ``sb.tooltip`` and knobs, and calls every hook a subclass may override
    (``format_param_tooltip``, ``_relevant_param_keys``, ``_fold_section``,
    ``_refresh_param_enablement`` ...) through the panel.
    """

    #: Dynamic property holding a widget's own tooltip, captured before any
    #: live provider could overwrite it (see :meth:`pristine_tooltip`).
    STATIC_TOOLTIP_PROP = "_bridge_static_tooltip"
    #: An opening tag, as opposed to a bare ``<`` used as a less-than sign.
    HTML_TAG_RE = re.compile(r"<[a-zA-Z/!]")
    #: The custom-store key the folded sections are kept under.
    FOLDED_SECTIONS_KEY = "bridge_folded_sections"

    def __init__(self, panel: "BridgeSlotsBase") -> None:
        self._panel = panel
        self.widgets: Dict[str, QtWidgets.QWidget] = {}
        self.rows: Dict[str, QtWidgets.QWidget] = {}
        # The row's caption, kept alongside its control so a live tooltip
        # provider can cover BOTH hover targets (see live_param_tooltips).
        self.labels: Dict[str, QtWidgets.QLabel] = {}
        # Category dividers: section name -> Separator, plus each param's section,
        # so a divider can hide when its whole section is hidden for the mode.
        self.section_separators: Dict[str, QtWidgets.QWidget] = {}
        self.section: Dict[str, str] = {}
        # Built in build_widgets from the dicts above; the rows stay the
        # tooltip and value code's index, this is only the visibility.
        self.fields: Optional[FieldVisibility] = None
        self.group: Optional[QtWidgets.QGroupBox] = None
        self.folded_sections: set = set()
        # The key set last shown (refresh_visibility); None before the first.
        self.rows_shown: Optional[frozenset] = None

    # ------------------ Parameter widgets -----------------------------

    def build_widgets(self) -> None:
        """Inject a 'Parameters' group between the Output Dir row and Send.

        Builds one row widget per registered :class:`AttributeSpec` via
        :meth:`uitk.bridge.spec.KindFactory.make_widget` -- the shared registry powers
        every kind including custom ones the bridge registered. A spec with
        ``inline`` set is appended to the PREVIOUS row instead of claiming one
        of its own (see :meth:`build_inline_cell`).
        """
        panel = self._panel
        grp = QtWidgets.QGroupBox("Parameters", panel.ui.grp_process)
        vbox = QtWidgets.QVBoxLayout(grp)
        vbox.setContentsMargins(2, 4, 2, 2)
        vbox.setSpacing(0)

        host_row: Optional[QtWidgets.QWidget] = None
        for key, spec in panel.params_module.PARAMS.items():
            # Start of a new category -> a titled divider above its first row.
            # (One separator per section; sections are expected contiguous.)
            section = getattr(spec, "section", "") or ""
            self.section[key] = section
            new_section = bool(section) and section not in self.section_separators
            if new_section:
                sep = Separator(grp, title=section, checkable=panel.FOLDABLE_SECTIONS)
                if panel.FOLDABLE_SECTIONS:
                    sep.setChecked(True)
                    sep.setToolTip("Click to fold or unfold this section.")
                vbox.addWidget(sep)
                self.section_separators[section] = sep

            tooltip_html = panel.format_param_tooltip(spec)
            # An inline spec joins the previous row; a section's opening spec
            # starts one regardless, so a divider is never followed by a row
            # whose first control belongs to the section above it.
            inline = getattr(spec, "inline", False) and host_row is not None
            if inline and not new_section:
                self.build_inline_cell(spec, key, host_row, tooltip_html)
                continue

            row = QtWidgets.QWidget(grp)
            hbox = QtWidgets.QHBoxLayout(row)
            hbox.setContentsMargins(0, 0, 0, 0)
            hbox.setSpacing(2)

            label = QtWidgets.QLabel(spec.display_label + ":", row)
            label.setMinimumWidth(panel.LABEL_MIN_WIDTH)
            label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            label.setToolTip(tooltip_html)
            self.labels[key] = label

            widget = self.make_param_widget(spec, key, row, tooltip_html)

            hbox.addWidget(label)
            hbox.addWidget(widget, 1)
            vbox.addWidget(row)

            self.rows[key] = row
            host_row = row

        parent_layout = panel.ui.grp_process.layout()
        insert_at = parent_layout.indexOf(panel.ui.b000)
        parent_layout.insertWidget(insert_at, grp)
        self.group = grp
        self.fit_label_column()

        # Everything the panel shows conditionally, in one registry. The
        # dividers and the group are registered WITH the rows rather than
        # chased separately at refresh time, which is the bookkeeping this
        # used to carry by hand.
        fields = FieldVisibility()
        for key, row in self.rows.items():
            fields.register(key, row, section=self.section.get(key))
        for section, sep in self.section_separators.items():
            fields.divider(section, sep)
        self.fields = fields.group(grp)
        self.build_section_folds()

    def build_section_folds(self) -> None:
        """Wire each foldable divider to its rows, and fold what was folded."""
        panel = self._panel
        self.folded_sections = set()
        if not panel.FOLDABLE_SECTIONS:
            return
        store = getattr(panel.ui, "state", None)
        folded = store.load_custom(self.FOLDED_SECTIONS_KEY, []) if store else []
        # A list as saved; anything else is no fold (a string would match by
        # substring under ``in``).
        folded = set(folded) if isinstance(folded, (list, tuple)) else set()
        for section, sep in self.section_separators.items():
            # Through the panel, so a subclass's _fold_section is the one run.
            sep.toggled.connect(
                lambda opened, s=section: panel._fold_section(s, not opened)
            )
            if section in folded:
                sep.setChecked(False)

    def fold_section(self, section: str, folded: bool) -> None:
        """Fold or unfold *section*'s rows, remember it, and re-fit the window.

        Unfolding brings back only the rows the panel shows: relevance is the
        panel's (``_refresh_param_visibility``), the fold the user's. Rows go
        through :meth:`FieldVisibility.set_widget_visible`, so a folded row
        carries the mark a container that re-shows its children respects.
        """
        (self.folded_sections.add if folded else self.folded_sections.discard)(section)
        shown = self.rows_shown
        for key, row in self.rows.items():
            if self.section.get(key) == section:
                FieldVisibility.set_widget_visible(
                    row, not folded and (shown is None or key in shown)
                )
        store = getattr(self._panel.ui, "state", None)
        if store is not None:
            store.save_custom(self.FOLDED_SECTIONS_KEY, sorted(self.folded_sections))
        WindowHeight.fit_host_later(self.group)

    def fit_label_column(self) -> None:
        """One label column: every row label takes the widest one's width.

        ``LABEL_MIN_WIDTH`` is only the floor; a label past it used to size
        itself, so the values of a panel with longer labels started at as many
        x as it had lengths. Hidden rows count, so the column holds still as
        rows come and go; an inline cell's label is a suffix, not a column, and
        is left alone. The width is kept as the panel's own
        ``LABEL_MIN_WIDTH``, so a row a subclass builds afterwards from it
        (a Model File row, say) lines up too. Measured once: the theme sets no
        row-label font, so a label keeps the font it is built with.
        """
        panel = self._panel
        # A row hangs off the group; an inline cell off the row it joined.
        labels = [
            self.labels[key]
            for key, row in self.rows.items()
            if row.parent() is self.group and key in self.labels
        ]
        output_dir = panel._output_dir_label
        if output_dir is not None:
            labels.append(output_dir)
        width = max([panel.LABEL_MIN_WIDTH] + [lb.sizeHint().width() for lb in labels])
        for label in labels:
            label.setMinimumWidth(width)
        panel.LABEL_MIN_WIDTH = width

    def make_param_widget(
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
        if spec.kind not in self._panel.TALL_KINDS:
            widget.setMinimumHeight(19)
            widget.setMaximumHeight(19)
        widget.setToolTip(tooltip_html)
        self.widgets[key] = widget
        return widget

    def build_inline_cell(
        self,
        spec: AttributeSpec,
        key: str,
        host_row: QtWidgets.QWidget,
        tooltip_html: str,
    ) -> QtWidgets.QWidget:
        """Append *spec* to the right of *host_row*'s widget, as its own cell.

        The cell (label + widget) is what gets registered as this key's "row",
        so ``set_param_enabled`` greys only this control and
        ``_refresh_param_visibility`` can hide it without taking the host
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
        self.labels[key] = label

        widget = self.make_param_widget(spec, key, cell, tooltip_html)

        hbox.addWidget(label)
        hbox.addWidget(widget)
        host_row.layout().addWidget(cell)

        self.rows[key] = cell
        return widget

    # ------------------ Tooltips --------------------------------------

    def bind_live_tooltips(self) -> None:
        """Install every live tooltip provider on its row."""
        panel = self._panel
        for key, provider in (panel.live_param_tooltips() or {}).items():
            targets = [self.widgets.get(key), self.labels.get(key)]
            panel.sb.tooltip.bind([t for t in targets if t is not None], provider)
        for key, provider in (panel.live_param_tooltip_blocks() or {}).items():
            self.bind_live_block(key, provider)

    def bind_live_block(self, key: str, provider) -> None:
        """Append *provider*'s live block to every hover target of row *key*.

        The composed providers are plain closures, so the tooltip surface stores
        them directly rather than through its bound-method weakref. That keeps
        this slot alive exactly as long as the widgets it bound -- which the
        panel owns and destroys together -- rather than beyond them.
        """
        panel = self._panel
        params = getattr(panel.params_module, "PARAMS", {}) or {}
        spec = params.get(key)
        if spec is None:
            return
        widget = self.widgets.get(key)
        static = panel.format_param_tooltip(spec)
        targets = [(t, static) for t in (widget, self.labels.get(key)) if t is not None]
        # An action row's buttons: each keeps its own per-choice description,
        # promoted to HTML first (see :meth:`as_tooltip_html`).
        for button in (getattr(widget, "_action_buttons", None) or {}).values():
            own = self.pristine_tooltip(button)
            targets.append((button, self.as_tooltip_html(own) if own else static))
        for target, base in targets:
            panel.sb.tooltip.bind(target, lambda _base=base, _p=provider: _base + _p())

    @classmethod
    def pristine_tooltip(cls, widget) -> str:
        """The widget's OWN tooltip, from before a live provider rewrote it.

        The tooltip surface writes each computed string back onto the widget as
        it renders, so ``toolTip()`` stops being the widget's own text after the
        first hover. Reading it again on a later bind would fold the previous
        live block into the new base and stack a second copy on every rebind
        (measured: two hovers, two lists). The first read is stashed as a Qt
        dynamic property and reused from then on, so binding is idempotent.
        """
        stored = widget.property(cls.STATIC_TOOLTIP_PROP)
        if stored is None:
            stored = widget.toolTip()
            widget.setProperty(cls.STATIC_TOOLTIP_PROP, stored)
        return stored

    @classmethod
    def as_tooltip_html(cls, text: str) -> str:
        """Promote a plain-text tooltip to HTML, preserving its line breaks.

        Qt renders a tooltip as rich text the moment it contains a tag, so
        appending a live HTML block to a plain-text base silently collapses
        every newline that base was relying on. Already-rich text passes
        through untouched -- detected by an opening TAG rather than a bare
        ``<``, so a tip that merely says ``width < height`` is still escaped
        instead of having the comparison swallowed as markup.
        """
        if not text or cls.HTML_TAG_RE.search(text):
            return text
        from html import escape

        return "<p style='margin:0'>" + escape(text).replace("\n", "<br>") + "</p>"

    # ------------------ Actions and enablement ------------------------

    def wire_action_params(self) -> None:
        """Connect ``action``-kind param buttons to same-named slot methods.

        An ``action`` row's container exposes ``_action_buttons``
        (``{action_id: QPushButton}``, see :mod:`uitk.bridge.spec`); each id
        that names a callable on the panel is wired to it, so a registry can
        declare panel actions as data with zero per-panel wiring code. An id
        with no matching method is disabled rather than silently inert.
        """
        panel = self._panel
        for key, widget in self.widgets.items():
            buttons = getattr(widget, "_action_buttons", None)
            if not buttons:
                continue
            for action_id, btn in buttons.items():
                handler = getattr(panel, action_id, None)
                if callable(handler):
                    btn.clicked.connect(handler)
                else:
                    btn.setEnabled(False)
                    btn.setToolTip(
                        f"No handler '{action_id}' on {type(panel).__name__}."
                    )

    def set_param_enabled(self, key: str, enabled: bool, reason: str = "") -> None:
        row = self.rows.get(key)
        if row is None:
            return
        others = {r for k, r in self.rows.items() if k != key}
        layout = row.layout()
        children = _LayoutItems.widgets(layout) if layout is not None else []
        for child in children:
            if child not in others:
                child.setEnabled(enabled)
        row.setToolTip("" if enabled else reason)

    def wire_enablement_refresh(self) -> None:
        """Re-run ``_refresh_param_enablement`` on panel show + trigger edits.

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
        panel = self._panel
        on_show = getattr(panel.ui, "on_show", None)
        if on_show is not None:
            on_show.connect(panel._refresh_param_enablement)
        for trigger, _governed, _reason in panel.param_supersessions():
            widget = self.widgets.get(trigger)
            if widget is not None:
                KindFactory.connect_changed(
                    widget, lambda *_: panel._refresh_param_enablement()
                )

    def refresh_enablement(self) -> None:
        """The declared supersessions (see ``_refresh_param_enablement``)."""
        panel = self._panel
        for trigger, governed, reason in panel.param_supersessions():
            if trigger not in self.widgets:
                continue
            active = bool(panel._read_param(trigger))
            for key in governed:
                panel.set_param_enabled(key, not active, reason if active else "")

    # ------------------ Values ----------------------------------------

    def read(self, key: str) -> Any:
        """Extract the current value via the registered KindHandler."""
        return KindFactory.read_value(self.widgets[key])

    def write(self, key: str, value: Any) -> None:
        """Push *value* into the widget for *key* via the KindHandler."""
        KindFactory.set_value(self.widgets[key], value)

    def set_choices(self, key: str, choices) -> None:
        """Repopulate the entries of a choice-driven param at runtime."""
        KindFactory.set_choices(self.widgets[key], choices)

    def collect_values(self) -> Dict[str, Any]:
        panel = self._panel
        return {
            key: panel._read_param(key)
            for key, widget in self.widgets.items()
            if not hasattr(widget, "_action_buttons")
        }

    # ------------------ Visibility ------------------------------------

    def relevant_keys(self) -> Optional[set]:
        """The default relevance: the keys the active template file references."""
        panel = self._panel
        pair = panel._selected_template_mode()
        if not pair:
            return None
        template, _mode = pair
        path = panel.template_dir / f"{template}{panel.TEMPLATE_EXTENSION}"
        if not path.is_file():
            return None
        return panel.params_module.referenced_keys(path.read_text(encoding="utf-8"))

    def refresh_visibility(self) -> None:
        """Show only the rows relevant to the current selection.

        Delegates the "which keys are relevant?" decision to the panel's
        ``_relevant_param_keys`` so subclasses can drive visibility from a
        template file (default) or a run mode; the row toggling, the dividers,
        the empty group and the height re-fit are :class:`FieldVisibility`.

        A set already on screen is not applied again: a re-show re-fits the
        window, and a panel refreshing off a live edit (a typed path) would
        snap a height the user dragged back on every keystroke. The first
        refresh always applies -- before it, every row shows.
        """
        used = self._panel._relevant_param_keys()
        if used is None or self.fields is None:
            return
        used = frozenset(used)
        if used == self.rows_shown:
            return
        self.rows_shown = used
        self.fields.show(used)
        # A folded section keeps its rows down; its divider stays to reopen it.
        for key, row in self.rows.items():
            if self.section.get(key) in self.folded_sections:
                FieldVisibility.set_widget_visible(row, False)
