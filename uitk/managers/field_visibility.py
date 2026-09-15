# !/usr/bin/python
# coding=utf-8
"""Which fields a container shows, per named mode."""

from typing import Callable, Dict, Hashable, Iterable, List, Optional, Set

from qtpy import QtCore

from uitk.managers.window_height import WindowHeight


class FieldVisibility:
    """The fields a container shows, as named modes over one keyed registry.

    A tool with modes is the same problem every time: a set of fields, a
    decision about which of them belong right now, and the bookkeeping that
    decision drags behind it. Hand-rolled, it is the bookkeeping that gets
    forgotten -- a divider left standing over a section whose every row is
    hidden, a group box holding nothing, a panel keeping the height of the
    mode it is no longer in.

    Registration is KEYED, so the decision is a set of keys and nothing here
    cares where the set came from::

        fields.define("create", ("length", "period"))   # a stored set
        fields.mode = "create"                          # apply it by name

        fields.show(referenced_keys(template))          # or any set, computed

    That is the whole of "optionally dynamic": a named mode IS a stored key
    set, so a tool with fixed modes and a tool that derives its fields from a
    file use one mechanism. Adding a mode is adding a row; nothing in this
    class branches on which modes exist.

    A tool that has no keys of its own never has to invent any -- name the
    widgets themselves and they register under their own identity::

        fields.define("numeric", [sep_range, lbl_min, spn_min])

    Only registered widgets are touched. Anything else in the container is
    left exactly as the tool put it, which is what lets this gate part of a
    panel without owning all of it.

    This is about which fields are ON SCREEN, which is not what widget
    *state* means elsewhere in this library: ``restore_state`` and
    :class:`StateManager` are a widget's persisted VALUE. The two are
    orthogonal -- a field hidden here still saves and restores what is in it.
    Companion to :class:`IconStates`, which is one button's visuals. The
    window that has to get taller or shorter as fields come and go is
    :class:`WindowHeight`'s job, not this one's.
    """

    def __init__(
        self,
        fit: Optional[Callable[[], None]] = None,
        on_change: Optional[Callable[[Optional[str]], None]] = None,
    ):
        """
        Parameters:
            fit: How to re-fit the host after a change. ``None`` -- the usual
                case -- resolves the window the fields live in and fits it the
                way that window fits (:meth:`WindowHeight.fit_host`), so a
                tool gets height management without stating any, and a panel
                and a popup menu need no different call. Pass a callable only
                for a host that fits some other way. Either way it is deferred
                to the next turn of the event loop, because a container asked
                to re-measure while it is still hiding children measures the
                layout it is leaving. The FIRST application never fits: that
                one runs while the tool is still building, and the host has
                not been shown to have a size worth correcting.
            on_change: Called with the new mode name (``None`` for a set
                applied by :meth:`show`) once the fields have settled.
        """
        self.fit = fit
        self.on_change = on_change
        self._widgets: Dict[Hashable, object] = {}
        self._sections: Dict[Hashable, str] = {}
        self._dividers: Dict[str, object] = {}
        self._groups: List[object] = []
        self._modes: Dict[str, Set[Hashable]] = {}
        self._mode: Optional[str] = None
        self._visible: Set[Hashable] = set()
        self._settled = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self, key: Hashable, widget, section: Optional[str] = None
    ) -> "FieldVisibility":
        """Put *widget* under *key*, optionally belonging to a named section.

        *widget* is anything with ``setVisible`` -- a row, a control, a nested
        container. Left duck-typed rather than hinted as a ``QWidget``, since
        what it needs is one method and tools register all three. *key* is any
        hashable: a name out of a spec file, or the widget itself, which is
        what :meth:`define` uses for a tool that has no keys of its own.
        """
        self._widgets[key] = widget
        if section is not None:
            self._sections[key] = section
        return self

    def divider(self, section: str, widget) -> "FieldVisibility":
        """A separator that stands only while its section has something on screen.

        The thing hand-rolled versions forget: a titled rule over a group of
        rows that the current mode hides reads as an empty category rather
        than as nothing at all.
        """
        self._dividers[section] = widget
        return self

    def group(self, widget) -> "FieldVisibility":
        """A container that hides when no field registered here is showing."""
        self._groups.append(widget)
        return self

    def define(self, mode: str, fields: Iterable[Hashable]) -> "FieldVisibility":
        """Store *fields* as the mode called *mode*.

        An entry is a registered key, or a WIDGET -- which registers itself on
        the spot, so a tool whose modes are fixed writes the widgets it means,
        and one named by two modes is still one registration.
        """
        keys = set()
        for field in fields:
            if hasattr(field, "setVisible"):
                self.register(field, field)
            keys.add(field)
        self._modes[mode] = keys
        return self

    def bind(self, combo) -> "FieldVisibility":
        """Drive the mode from a combo box's current entry.

        Reads ``currentData`` and falls back to ``currentText``, because both
        spellings are in use: a combo carrying ``(label, value)`` pairs states
        its value as data, one carrying plain labels states it as text.
        """
        combo.currentIndexChanged.connect(lambda *_: self._from(combo))
        self._from(combo)
        return self

    def _from(self, combo) -> None:
        data = combo.currentData()
        try:
            hash(data)
        except TypeError:
            # An entry may carry ANY payload as its data -- a dict of settings
            # is a spelling in use here -- and one that cannot be a key cannot
            # name a mode either. Fall back to the label rather than raise out
            # of a combo box's signal.
            data = None
        self.mode = data if data is not None else combo.currentText()

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    @property
    def keys(self) -> tuple:
        """Every registered key -- what this is in a position to hide."""
        return tuple(self._widgets)

    @property
    def mode(self) -> Optional[str]:
        """The named mode currently applied, if it was applied by name."""
        return self._mode

    @mode.setter
    def mode(self, name: Optional[str]) -> None:
        # An unknown name shows nothing rather than raising: this is driven by
        # a combo box, and which fields are on screen must never be what stops
        # a panel from building.
        self._mode = name
        self._apply(self._modes.get(name, ()))

    @property
    def visible(self) -> tuple:
        """The keys currently on screen."""
        return tuple(k for k in self._widgets if k in self._visible)

    def show(self, keys: Iterable[Hashable]) -> None:
        """Show exactly *keys* -- the form for a set nobody stored in advance."""
        self._mode = None
        self._apply(keys or ())

    def set_visible(self, key: Hashable, on: bool) -> bool:
        """Show or hide ONE registered key and leave the rest as they are.

        The rule-driven form: a dependency rule (``Switchboard.show_when``)
        decides one field at a time rather than a whole mode, and still wants
        the divider and group bookkeeping that comes with the decision. Not a
        named mode -- :attr:`mode` reads ``None`` afterwards, as after
        :meth:`show`. An unregistered key is declined (``False``) rather than
        raised: a rule fires from a widget's signal, and which fields are on
        screen must never be what stops a panel.

        Only that key's widget, its section's divider and the groups are
        written. Re-applying every key cost a widget write per row per firing,
        and a ``WidgetComboBox`` row finds its model row by a scan -- so a rule
        over an option menu was quadratic in its rows.
        """
        if key not in self._widgets:
            return False
        self._mode = None
        (self._visible.add if on else self._visible.discard)(key)
        self.set_widget_visible(self._widgets[key], on)
        showing = self.visible
        section = self._sections.get(key)
        if section in self._dividers:
            live = any(self._sections.get(k) == section for k in showing)
            self.set_widget_visible(self._dividers[section], live)
        self._settle(showing)
        return True

    def _apply(self, keys: Iterable[Hashable]) -> None:
        # Copied: a stored mode hands in the set it keeps, and re-defining that
        # mode would otherwise rewrite what is reported as on screen.
        self._visible = set(keys)
        for key, widget in self._widgets.items():
            self.set_widget_visible(widget, key in self._visible)

        # One pass over what is showing, not one per divider.
        showing = self.visible
        live = {self._sections.get(key) for key in showing}
        for section, divider in self._dividers.items():
            self.set_widget_visible(divider, section in live)
        self._settle(showing)

    def _settle(self, showing: tuple) -> None:
        """The groups, the re-fit and the report every application ends with."""
        # A group hides on what is actually SHOWING, not on whether the caller
        # named anything: a mode naming only keys this registry never got is
        # an empty group, and leaving it up is the same stray-frame problem
        # the dividers have.
        for widget in self._groups:
            self.set_widget_visible(widget, bool(showing))

        self._refit()
        if self.on_change is not None:
            self.on_change(self._mode)

    # ------------------------------------------------------------------
    # The mark a hidden field carries
    # ------------------------------------------------------------------

    #: Dynamic property set on a widget hidden as a field, cleared on a show.
    HIDDEN_PROPERTY = "fieldHidden"

    @classmethod
    def set_widget_visible(cls, widget, on: bool) -> None:
        """Show or hide *widget* as a field, marked with :attr:`HIDDEN_PROPERTY`.

        The mark lets a container that shows its contents wholesale tell the
        fields it hid itself from the ones a rule hid: ``CollapsableGroup``
        re-shows every child on expand, and without the mark it brought back
        exactly the fields the current mode had hidden. ``OptionBoxContainer``
        carries its field's mark, since it stands in for the field in the
        layout, and ``Switchboard.show_when`` hides a plain widget through here
        too. Show a marked widget through here as well: a bare
        ``setVisible(True)`` leaves the mark, and the next expand of its group
        leaves the widget hidden. Anything without Qt properties (a
        ``WidgetComboBox`` row handle) is only shown or hidden.
        """
        hidden = not on
        if callable(getattr(widget, "setProperty", None)):
            if bool(widget.property(cls.HIDDEN_PROPERTY)) != hidden:
                # Before the visibility change, so whatever reacts to the Show
                # or Hide event already reads the new mark.
                widget.setProperty(cls.HIDDEN_PROPERTY, hidden)
        widget.setVisible(on)

    @classmethod
    def is_hidden_field(cls, widget) -> bool:
        """Whether *widget* carries the mark :meth:`set_widget_visible` sets."""
        getter = getattr(widget, "property", None)
        return bool(getter(cls.HIDDEN_PROPERTY)) if callable(getter) else False

    def _refit(self) -> None:
        if not self._settled:
            # The build pass. The host sizes itself when it is first shown, so
            # correcting it here fights that rather than helping it.
            self._settled = True
            return
        QtCore.QTimer.singleShot(0, self._fit_now)

    def _fit_now(self) -> None:
        """Re-measure the host, a turn of the loop after the fields settled."""
        if self.fit is not None:
            self.fit()
        else:
            # Any registered field will do: they are all in the window that
            # has to follow them.
            WindowHeight.fit_host(next(iter(self._widgets.values()), None))
