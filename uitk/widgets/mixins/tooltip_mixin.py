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
        self._filter = _ProviderFilter(_safe_provider(provider), widget)
        widget.installEventFilter(self._filter)


# --- Color palette ---------------------------------------------------------
# Tuned for Qt's default dark tooltip background. Kept on the cool side so
# colored fragments don't fight the bold-default text Qt renders for tooltips.

_C_MUTED = "#9a9a9a"     # de-emphasized labels (row keys, notes prefix)
_C_NOTE = "#bda36a"      # warm muted for note/tip callout body
_C_ACCENT = "#6fb5d6"    # soft cyan — keywords, headings, term highlights
_C_TITLE = "#cfe6f5"     # off-white with cool tint for the top title


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


def hl(text: str, color: str = _C_ACCENT) -> str:
    """Highlight ``text`` in ``color`` (defaults to the accent color).

    Use sparingly — color highlights work best for short terms (a feature
    name, a state, a value), not whole sentences.

    Example::

        f"Status: {hl('On', color='#7c7')}"
        f"{hl('Edges')} only — vertices and faces are ignored."
    """
    return f"<span style='color:{color}'>{text}</span>"


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
        :func:`kbd` for keyboard-shortcut chips.
        :func:`hl` for inline color highlights.

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


class TooltipMixin:
    """Mixin for MainWindow — stamps ``widget.tooltip`` on every registered widget.

    Does not override ``__init__``; the stamp is applied inside
    ``MainWindow.register_widget`` after the widget is otherwise fully set up.
    """
