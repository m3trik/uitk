# !/usr/bin/python
# coding=utf-8
import weakref
from qtpy import QtCore, QtWidgets


class _ProviderFilter(QtCore.QObject):
    """Event filter that refreshes a widget's toolTip just before Qt shows it."""

    def __init__(self, provider, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self._provider = provider

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QtCore.QEvent.ToolTip:
            text = self._provider()
            if text is not None:
                obj.setToolTip(text)
        return False  # always propagate so Qt still shows the tooltip


class TooltipProxy:
    """Per-widget tooltip namespace stamped on each registered MainWindow widget.

    Accessed as ``widget.tooltip`` after registration.

    Example::

        # Lazy dynamic content — always current on hover
        self.ui.some_widget.tooltip.bind(lambda: f"Current value: {self._state}")

        # Rich static content built at init time
        widget.menu.add(
            "QComboBox",
            setToolTip=fmt(
                title="Export Mode",
                bullets=["<b>Composite</b> — mixed WAV", "<b>Keyed Tracks</b> — per source"],
            ),
        )
    """

    def __init__(self, widget: QtWidgets.QWidget):
        self._ref = weakref.ref(widget)
        self._filter: QtCore.QObject = None

    @staticmethod
    def _safe_provider(fn):
        """Wrap bound-method providers in a weakref to avoid retaining slot instances."""
        if hasattr(fn, "__self__") and hasattr(fn, "__func__"):
            obj_ref = weakref.ref(fn.__self__)
            func = fn.__func__

            def _wrapped():
                obj = obj_ref()
                return func(obj) if obj is not None else ""

            return _wrapped
        return fn

    def bind(self, provider) -> None:
        """Register a callable() -> str called lazily on QEvent.ToolTip hover.

        The tooltip content is computed only when the user actually hovers,
        so it is always fresh without any manual refresh calls.  Bound-method
        providers are captured via weakref so the proxy does not keep the
        slot instance alive after the UI is rebuilt.

        Parameters:
            provider: A zero-argument callable returning the tooltip string.
        """
        widget = self._ref()
        if widget is None:
            return
        if self._filter is not None:
            widget.removeEventFilter(self._filter)
        self._filter = _ProviderFilter(TooltipProxy._safe_provider(provider), widget)
        widget.installEventFilter(self._filter)


# --- Color palette ---------------------------------------------------------
# Tuned for Qt's default dark tooltip background. Kept on the cool side so
# colored fragments don't fight the bold-default text Qt renders for tooltips.

_C_MUTED = "#9a9a9a"  # de-emphasized labels (row keys, notes prefix)
_C_NOTE = "#bda36a"  # warm muted for note/tip callout body
_C_ACCENT = "#6fb5d6"  # soft cyan — keywords, headings, term highlights
_C_TITLE = "#cfe6f5"  # off-white with cool tint for the top title


class TooltipFormat:
    """Rich-text tooltip formatting DSL — ``kbd`` / ``hl`` / ``fmt``.

    Staticmethods so the module carries no top-level function *definitions*.
    Imported and called class-qualified across the ecosystem
    (``from uitk.widgets.mixins.tooltip_mixin import TooltipFormat`` then
    ``TooltipFormat.fmt(...)`` / ``TooltipFormat.kbd(...)`` /
    ``TooltipFormat.hl(...)``).
    """

    @staticmethod
    def kbd(*keys: str) -> str:
        """Render keyboard key(s) as styled ``<kbd>``-like chips.

        Multiple keys are joined with " + " between chips, matching the
        convention used in keyboard shortcut docs (e.g. ``Ctrl`` + ``Z``).

        Example::

            f"{kbd('Ctrl', 'Z')} — Undo"
            f"Press {kbd('Enter')} to confirm"
        """
        chip = (
            "<span style='background:#2f2f2f; border:1px solid #555; "
            "border-radius:3px; padding:0 4px; font-family:monospace; "
            "font-size:90%; color:#e0e0e0'>{key}</span>"
        )
        return " + ".join(chip.format(key=k) for k in keys)

    @staticmethod
    def hl(text: str, color: str = _C_ACCENT) -> str:
        """Highlight ``text`` in ``color`` (defaults to the accent color).

        Use sparingly — color highlights work best for short terms (a feature
        name, a state, a value), not whole sentences.

        Example::

            f"Status: {hl('On', color='#7c7')}"
            f"{hl('Edges')} only — vertices and faces are ignored."
        """
        return f"<span style='color:{color}'>{text}</span>"

    @staticmethod
    def fmt(
        title: str = None,
        body: str = None,
        bullets: list = None,
        steps: list = None,
        rows: list = None,
        sections: list = None,
        notes: list = None,
    ) -> str:
        """Build a rich-text HTML tooltip string.

        Any combination of parameters may be supplied; sections are stacked in
        order: title → body → bullets → steps → rows → sections → notes.

        Parameters:
            title:    Header line shown above everything else, rendered in the
                      accent title color and bold.
            body:     Paragraph of plain prose beneath the title.
            bullets:  Strings rendered as an unordered ``<ul>`` list.
                      Inline HTML (e.g. ``<b>On:</b> …``) is supported.
            steps:    Strings rendered as a numbered ``<ol>`` list.
                      Use for sequential workflow instructions.
            rows:     ``(key, value)`` pairs rendered as a compact two-column table.
                      Keys are rendered in a muted colour; values in default colour.
            sections: ``(title, [items])`` pairs for multi-section tooltips.
                      Each section renders a colored sub-heading followed by a ``<ul>``.
            notes:    Strings rendered as italic muted "note:"-style callouts after
                      the main content. Use for caveats, tips, or "see also" hints.

        Returns:
            An HTML string that Qt's tooltip engine renders as rich text.

        See also:
            :meth:`TooltipFormat.kbd` for keyboard-shortcut chips.
            :meth:`TooltipFormat.hl` for inline color highlights.

        Example::

            fmt(
                title="Export Mode",
                bullets=[
                    "<b>Composite</b> — Single mixed WAV of all keyed clips.",
                    "<b>Keyed Tracks</b> — Individual source clips keyed on the timeline.",
                ],
                notes=[f"{kbd('Shift')} while clicking to keep the previous mode."],
            )

            fmt(
                title="Image to Plane",
                body="Creates textured polygon planes from images.",
                steps=["Press Browse…", "Choose material type.", "Press Create Planes."],
            )

            fmt(
                title="Shot Manifest",
                body="Build and validate shots from a CSV file or scene animation.",
                sections=[
                    ("Quick Start", ["Check CSV and browse to a file.", "Click Build."]),
                    ("Table Columns", ["<b>Step</b> — Step ID.", "<b>Start / End</b> — Frame range."]),
                ],
            )
        """
        parts = []
        if title:
            parts.append(
                f"<p style='margin:0 0 3px 0; color:{_C_TITLE}'><b>{title}</b></p>"
            )
        if body:
            parts.append(f"<p style='margin:2px 0'>{body}</p>")
        if bullets:
            items = "".join(f"<li>{b}</li>" for b in bullets)
            parts.append(f"<ul style='margin:3px 0; padding-left:14px'>{items}</ul>")
        if steps:
            items = "".join(f"<li>{s}</li>" for s in steps)
            parts.append(f"<ol style='margin:3px 0; padding-left:16px'>{items}</ol>")
        if rows:
            cells = "".join(
                f"<tr><td style='padding-right:8px; color:{_C_MUTED}'>{k}</td>"
                f"<td>{v}</td></tr>"
                for k, v in rows
            )
            parts.append(f"<table style='margin:3px 0'>{cells}</table>")
        if sections:
            for section_title, section_items in sections:
                parts.append(
                    f"<p style='margin:6px 0 1px 0; color:{_C_ACCENT}'>"
                    f"<b>{section_title}</b></p>"
                )
                items = "".join(f"<li>{item}</li>" for item in section_items)
                parts.append(
                    f"<ul style='margin:1px 0; padding-left:14px'>{items}</ul>"
                )
        if notes:
            for note in notes:
                parts.append(
                    f"<p style='margin:3px 0 0 0; color:{_C_NOTE}; font-style:italic'>"
                    f"<span style='color:{_C_MUTED}'>note:</span> {note}</p>"
                )
        return "".join(parts)

    @staticmethod
    def placeholder_preview(
        template: str,
        context: dict,
        *,
        title: str = None,
        body: str = None,
        descriptions: dict = None,
        final: str = None,
        final_label: str = "→",
        empty_text: str = None,
        notes: list = None,
    ) -> str:
        """Build a live, self-documenting tooltip for a pattern/template field.

        Combines *instruction* (what the field does + what each placeholder means)
        with a *live preview* (each placeholder's current value + the fully-resolved
        result). Designed for ``widget.tooltip.bind`` on a pattern ``QLineEdit`` so
        the hover both teaches the syntax and reflects the current text + live
        context — no manual refresh needed. Because ``bind`` replaces the widget's
        static tooltip, fold the field's help text in here (via *title* / *body* /
        *descriptions*) rather than leaving it on ``setToolTip``.

        Table contents:
            - With *descriptions*: every supported placeholder (the *descriptions*
              keys, in order) is listed as ``{token} | meaning | value`` — so the
              user sees all available keys and what they mean even when the current
              pattern uses only some. Any token typed in *template* that isn't a
              supported key is appended and flagged ``unknown``.
            - Without *descriptions*: only the tokens actually present in *template*
              are listed as ``{token} | value`` (a terse "resolves to" view).

        Resolution goes through :meth:`pythontk.StrUtils.resolve_placeholders`.
        Placeholder values and the resolved *final* are treated as **data** and
        HTML-escaped (a path may hold ``&``; a ``<none>`` sentinel must render
        literally). *title* / *body* / *descriptions* / *notes* / *final_label* are
        caller **markup**, passed through verbatim (so ``<b>…</b>`` still works).

        Parameters:
            template:     The current pattern text (typically ``lineedit.text()``).
            context:      ``{token: value}`` for every placeholder the field
                          supports, at its current live value.
            title:        Optional heading (the field's name).
            body:         Optional purpose paragraph — what the field controls.
            descriptions: Optional ``{token: meaning}`` for the supported keys.
                          Its presence + order drive the full-key table (see above).
            final:        Optional fully-resolved string (e.g. an absolute output
                          path) shown under the table. ``None`` defaults to the
                          resolved ``result``; pass ``final=""`` to suppress it.
            final_label:  Muted label shown before *final* (default ``"→"``).
            empty_text:   Returned when *template* is blank **and** no instructional
                          content (*title* / *body* / *descriptions*) is supplied;
                          defaults to a muted "type a pattern…" hint.
            notes:        Extra caller notes (examples, a domain-specific typo
                          warning), appended after the auto unknown-token note.

        Returns:
            An HTML tooltip string (see :meth:`fmt`).

        Example::

            self.ui.txt_pattern.tooltip.bind(
                lambda: TooltipFormat.placeholder_preview(
                    self.ui.txt_pattern.text(),
                    {"scenes": self.scenes_dir, "name": self.scene_name},
                    title="Folder Structure",
                    body="Subfolder pattern for <b>Save</b>.",
                    descriptions={
                        "scenes": "workspace scenes folder",
                        "name": "scene name (excludes the suffix)",
                    },
                    final=self.resolved_dir,
                    final_label="save dir →",
                )
            )
        """
        from html import escape as _esc

        from pythontk import StrUtils

        tmpl = (template or "").strip()
        # Nothing to say and no pattern yet — just the muted hint.
        if not tmpl and not (title or body or descriptions):
            return empty_text or (
                f"<p style='margin:0; color:{_C_MUTED}; font-style:italic'>"
                f"Type a pattern to preview its resolved value.</p>"
            )

        try:
            info = StrUtils.resolve_placeholders(tmpl, **(context or {}))
        except ValueError as e:
            return TooltipFormat.fmt(
                title=title, body=body, notes=[f"invalid pattern: {e}"]
            )

        ctx = context or {}

        def _value_cell(name):
            """The colour-coded live-value cell for one placeholder. A supported key
            has a value straight from *context* (present even when the current
            pattern doesn't use it); a token typed but not supplied is flagged."""
            if name in ctx:
                val = format(ctx[name])
                return (
                    TooltipFormat.hl(_esc(val))
                    if val
                    else f"<i style='color:{_C_MUTED}'>(empty)</i>"
                )
            return TooltipFormat.hl(
                "unknown" if descriptions is not None else "unresolved",
                color=_C_NOTE,
            )

        # Which placeholders to list, and in what order.
        if descriptions is not None:
            names = list(descriptions.keys())
            for n in info["fields"]:  # surface typed-but-unsupported tokens too
                if n not in descriptions:
                    names.append(n)
        else:
            names = list(info["fields"])

        rows = []
        for name in names:
            cells = [f"<td style='padding-right:8px'>{_esc('{' + name + '}')}</td>"]
            if descriptions is not None:
                meaning = descriptions.get(name, "")  # author markup — not escaped
                cells.append(
                    f"<td style='padding-right:8px; color:{_C_MUTED}'>{meaning}</td>"
                )
            cells.append(f"<td>{_value_cell(name)}</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        table_html = (
            f"<table style='margin:3px 0'>{''.join(rows)}</table>" if rows else ""
        )

        note_list = []
        if info["unresolved"]:
            toks = ", ".join(_esc("{" + n + "}") for n in info["unresolved"])
            label = "unknown" if descriptions is not None else "unresolved"
            note_list.append(f"{label}: {toks}")
        if notes:
            note_list.extend(notes)

        resolved_final = info["result"] if final is None else final
        final_html = (
            f"<p style='margin:4px 0 0 0'>"
            f"<span style='color:{_C_MUTED}'>{final_label}</span> "
            f"<span style='color:{_C_TITLE}'>{_esc(resolved_final)}</span></p>"
            if resolved_final
            else ""
        )

        # instruction (title + body) → table → resolved-final line → warnings.
        return (
            TooltipFormat.fmt(title=title, body=body)
            + table_html
            + final_html
            + (TooltipFormat.fmt(notes=note_list) if note_list else "")
        )


class TooltipMixin:
    """Mixin for MainWindow — stamps ``widget.tooltip`` on every registered widget.

    Does not override ``__init__``; the stamp is applied inside
    ``MainWindow.register_widget`` after the widget is otherwise fully set up.
    """
