# !/usr/bin/python
# coding=utf-8
"""Choice option for OptionBox -- an icon button that picks from a popup.

The facet button of a filter row. A list that narrows by several dimensions --
a collection, a lock state, a tag -- carries one glyph per dimension on its
filter field's option box, instead of a combo box of its own beside the field.
The button's popup lists the choices and marks the ones in effect; the icon
takes the active tint while the list is narrowed, so a glance at the field says
whether it is, and the tooltip says by what.

One value by default; with ``multi=True`` the popup's rows are toggles that
stay open, and the value is the tuple of values picked -- a list shows the rows
matching ANY of them.

The popup is a :class:`~uitk.widgets.context_menu.ContextMenu` built each time
it opens, from ``choices`` -- a list, or a callable returning one -- so a set
that changes behind the button (collections created, tags added) is always
current. :meth:`refresh` drops a value that is no longer offered.

Typical use (fluent, via the manager, which returns the option)::

    status = le.option_box.add_choice(
        icon="lock",
        label="Status",
        choices=[("Any status", "any"), None, ("Locked", "locked"), ("Built-in", "builtin")],
        default="any",
        multi=True,
        on_changed=lambda _value: self._apply_filter(),
        settings=self._settings,
        settings_key="filter.status",
    )
    status.value  # () | ("locked",) | ("locked", "builtin")
"""

import json
from typing import Any, Callable, Iterable, List, Optional, Tuple, Union

from qtpy import QtCore, QtGui
import pythontk as ptk

from ._options import ButtonOption

#: One popup row, in the ecosystem's choice shapes (``KindFactory``'s): a bare
#: value (its own label), ``(label, value)``, ``(label, value, tooltip)`` -- or
#: ``None`` for a separator.
Choice = Union[None, Any, Tuple[str, Any], Tuple[str, Any, str]]
Choices = Union[Iterable[Choice], Callable[[], Iterable[Choice]]]


class ChoiceOption(ButtonOption):
    """An icon button that picks one value -- or several -- from a popup.

    Parameters:
        wrapped_widget: The field the button sits on.
        icon: The glyph (one per facet: ``"stack"``, ``"lock"``, ``"tag"``).
        label: The facet's name; the tooltip reads ``"<label>: <choice text>"``
            and the popup is captioned with it.
        choices: Bare values, ``(label, value)`` or ``(label, value, tooltip)``
            entries (``None`` = separator) -- the shapes a bridge ``choice``
            spec takes -- or a callable returning them, evaluated each time
            the popup opens.
        default: The value that means "not narrowed". The icon is tinted while
            the value differs from it. With *multi*, the row holding it is the
            one that clears every pick (marked while nothing is picked).
        multi: Rows are toggles and the popup stays open while they are
            flipped; :attr:`value` is the tuple of values picked, ``()`` when
            not narrowed.
        on_changed: Connected to :attr:`changed` (receives the new value).
        settings: Optional ``QSettings``-like store (``value`` / ``setValue``)
            persisting the value under *settings_key* -- the caller's own, so a
            filter row's text, toggle and facets share one namespace. Values
            should be strings; a multi value is stored as a list of them.
        settings_key: The key the value is persisted under.
        active_color: Tint while narrowed; defaults to :attr:`ACTIVE_COLOR`.
        order: Explicit sort position. See :class:`BaseOption`.
    """

    #: Emitted with the new value after a pick, a fallback on :meth:`refresh`,
    #: a :meth:`restore_default`, or ``set_value(..., notify=True)``.
    changed = QtCore.Signal(object)

    #: The narrowed tint: the status palette's informational blue. Not the
    #: error red a gating toggle shows while OFF -- a narrowed list is a
    #: choice in effect, not a control switched off.
    ACTIVE_COLOR: str = ptk.Palette.status()["info"][0]

    #: Side of the check mark on a picked row (and the blank that keeps the
    #: other rows' text aligned with it).
    _MARK_SIZE = 12

    def __init__(
        self,
        wrapped_widget=None,
        *,
        icon: str = "filter",
        label: str = "Filter",
        choices: Choices = (),
        default: Any = None,
        multi: bool = False,
        on_changed: Optional[Callable[[Any], None]] = None,
        settings=None,
        settings_key: Optional[str] = None,
        active_color: Optional[str] = None,
        order: Optional[int] = None,
    ):
        super().__init__(
            wrapped_widget=wrapped_widget,
            icon=icon,
            tooltip=label,
            callback=self.show_menu,
            order=order,
        )
        self.label = label
        self._choices = choices
        self._default = default
        self._multi = multi
        self._settings = settings
        self._settings_key = settings_key
        self._active_color = active_color or self.ACTIVE_COLOR
        self._value = () if multi else default
        if settings is not None and settings_key:
            saved = settings.value(settings_key, None)
            if saved is not None:
                self._value = self._coerce(saved)
        if on_changed is not None:
            self.changed.connect(on_changed)

    # ------------------------------------------------------------------ value
    @property
    def value(self) -> Any:
        """The value in effect -- with *multi*, the tuple of values picked."""
        return self._value

    @property
    def is_active(self) -> bool:
        """True while the list is narrowed (a pick other than the default)."""
        return bool(self._value) if self._multi else self._value != self._default

    def _coerce(self, value: Any) -> Any:
        """*value* in this option's form: a multi value is a tuple of picks.

        A stored multi value reads back as a list, or as its JSON (from a store
        that does not decode it), or -- written before the facet took several
        -- as one bare value.
        """
        if not self._multi:
            return value
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except ValueError:
                decoded = None
            if isinstance(decoded, list):  # never "5" -> 5: a pick stays a str
                value = decoded
        if isinstance(value, (list, tuple)):
            picks = value
        else:
            picks = () if value in (None, "") else (value,)
        return tuple(dict.fromkeys(v for v in picks if v != self._default))

    def set_value(self, value: Any, *, notify: bool = False) -> None:
        """Put *value* in effect: persist it and update the glyph and tooltip.

        With *multi*, *value* is the values to pick (any iterable; one bare
        value picks just that). Silent by default -- a restore or a host-driven
        sync that re-filters once itself. *notify* emits :attr:`changed` when
        the value changed.
        """
        value = self._coerce(value)
        if self._multi:
            changed = set(value) != set(self._value)
        else:
            changed = value != self._value
        self._value = value
        if self._settings is not None and self._settings_key:
            stored = list(value) if self._multi else value
            self._settings.setValue(self._settings_key, stored)
        self._apply_visuals()
        if notify and changed:
            self.changed.emit(value)

    def toggle(self, value: Any) -> None:
        """Flip *value* in or out of a multi pick; the default's row clears it.

        Without *multi*, picks *value*.
        """
        if not self._multi:
            picks = value
        elif value == self._default:
            picks = ()
        elif value in self._value:
            picks = tuple(v for v in self._value if v != value)
        else:
            picks = self._value + (value,)
        self.set_value(picks, notify=True)

    def restore_default(self) -> None:
        """Back to the default -- a sibling reset clears the facet too."""
        self.set_value(() if self._multi else self._default, notify=True)

    def refresh(self) -> None:
        """Drop picks no longer offered; re-read the text.

        Called on every show of the option box, and by a host after the data
        its choices come from changed (a collection deleted, a tag cleared).
        """
        offered = self.choice_values()
        if self._multi:
            kept = tuple(v for v in self._value if v in offered)
            if kept != self._value:
                self.set_value(kept, notify=True)
                return
        elif self.is_active and self._value not in offered:
            self.set_value(self._default, notify=True)
            return
        self._apply_visuals()

    # ---------------------------------------------------------------- choices
    def choices(self) -> List[Optional[Tuple[str, Any, str]]]:
        """The current rows as ``(label, value, tooltip)``, ``None`` separators."""
        source = self._choices() if callable(self._choices) else self._choices
        return [None if c is None else self._split(c) for c in source or ()]

    @staticmethod
    def _split(entry) -> Tuple[str, Any, str]:
        if isinstance(entry, tuple) and len(entry) in (2, 3):
            tip = entry[2] if len(entry) == 3 else ""
            return str(entry[0]), entry[1], str(tip or "")
        return str(entry), entry, ""

    def choice_values(self) -> List[Any]:
        """The values currently offered, in popup order."""
        return [c[1] for c in self.choices() if c is not None]

    def text_of(self, value: Any) -> Optional[str]:
        """The popup label of *value*, or ``None`` when it is not offered."""
        for choice in self.choices():
            if choice is not None and choice[1] == value:
                return choice[0]
        return None

    def is_marked(self, value: Any) -> bool:
        """Whether *value*'s row reads as picked (with *multi*, the default's
        row does while nothing is)."""
        if not self._multi:
            return value == self._value
        if value == self._default:
            return not self._value
        return value in self._value

    # ------------------------------------------------------------------ popup
    def build_menu(self):
        """The popup, built but not shown (a test reads and clicks its rows).

        Each row carries a ``marked`` property beside its check mark. With
        *multi* the rows are ``keep_open`` toggles and re-mark in place.
        """
        from uitk.managers.icon_manager import IconManager
        from uitk.widgets.context_menu import ContextMenu

        menu = ContextMenu(parent=self._widget or self.wrapped_widget)
        menu.add_separator(self.label)
        size = QtCore.QSize(self._MARK_SIZE, self._MARK_SIZE)
        blank = QtGui.QPixmap(size)
        blank.fill(QtCore.Qt.transparent)
        check = IconManager.get("check", size=(self._MARK_SIZE, self._MARK_SIZE))
        rows = []

        def mark() -> None:
            for row, value in rows:
                marked = self.is_marked(value)
                row.setProperty("marked", marked)
                row.setIcon(check if marked else QtGui.QIcon(blank))

        def pick(value) -> None:
            if self._multi:
                self.toggle(value)
                mark()
            else:
                self.set_value(value, notify=True)

        for choice in self.choices():
            if choice is None:
                menu.add_separator()
                continue
            text, value, tip = choice
            row = menu.add(
                text,
                callback=lambda v=value: pick(v),
                keep_open=self._multi,
                setToolTip=tip,
            )
            row.setIconSize(size)
            rows.append((row, value))
        mark()
        return menu

    def show_menu(self) -> None:
        """Open the popup under the button; blocks until it is dismissed."""
        if self._widget is None:
            return
        menu = self.build_menu()
        menu.exec_(self._widget.mapToGlobal(QtCore.QPoint(0, self._widget.height())))

    # ----------------------------------------------------------------- visual
    def setup_widget(self):
        super().setup_widget()
        self._apply_visuals()

    def _apply_visuals(self) -> None:
        if self._widget is None:
            return
        self._swap_state_icon(self.icon, self._active_color if self.is_active else None)
        if self._multi and self._value:
            text = ", ".join(self.text_of(v) or str(v) for v in self._value)
        else:
            text = self.text_of(self._default if self._multi else self._value)
        self._widget.setToolTip(
            f"{self.label}: {text}" if text is not None else self.label
        )
