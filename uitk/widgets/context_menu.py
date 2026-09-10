# !/usr/bin/python
# coding=utf-8
"""A popup context menu whose rows can expand into sub-rows.

``ContextMenu`` is a :class:`~uitk.widgets.menu.Menu` (popup lifecycle, the
``add(x, **setter_kwargs)`` idiom) whose body is one
:class:`~uitk.widgets.expandableList.ExpandableList`: the root menu stays
compact, and any row can fan out into a flyout of finer-grained rows on
hover.  A row is an *action* (it has a callback), a *category* (it only
opens its flyout), or both -- an action that also expands, e.g. "Trim Empty
Space" whose flyout offers "Trim Leading" / "Trim Trailing".

Callbacks follow the Menu idiom (``clicked=fn`` / ``toggled=fn``), with
``callback=fn`` as sugar for ``clicked``.  Activating an action row hides
the menu first, then runs it, so a callback that opens a dialog never finds
the menu's flyouts hanging over it.

Example::

    menu = ContextMenu(parent=widget)
    trim = menu.add("Trim Empty Space", callback=trim_both)
    menu.add("Trim Leading Space", parent=trim, callback=trim_head)
    menu.add("Trim Trailing Space", parent=trim, callback=trim_tail)
    menu.add_separator("Display")
    menu.add("CheckBox", setText="Show Gaps", setChecked=True, toggled=on_gaps)
    trim.add_option_menu().add("QSpinBox", setPrefix="Reach: ")  # row settings
    menu.exec_(event.globalPos())   # blocks until dismissed; then disposes
"""

import inspect
from typing import Optional

from qtpy import QtWidgets, QtCore, QtGui

from uitk.widgets.menu import Menu
from uitk.widgets.expandableList import ExpandableList
from uitk.widgets.mixins.option_box_mixin import OptionBoxMixin

__all__ = ["ContextMenu", "MenuRow"]


class MenuRow(QtWidgets.QPushButton, OptionBoxMixin):
    """One clickable row of a :class:`ContextMenu`.

    A plain push button (left-aligned by the theme's ``MenuRow`` rule).  A
    row that owns a populated flyout paints a submenu arrow at its right
    edge, and :meth:`add_option_menu` gives it the settings box of the
    action it runs -- laid OVER the row, inside that arrow, rather than
    beside it (see that method).
    """

    designer_spec = {"visible": False}

    _ARROW = "▸"
    _ARROW_INSET = 6
    #: Breathing room around the overlaid option button.
    _OPTION_GAP = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "MenuRow")
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._option = None
        self._option_button = None

    @property
    def has_flyout(self) -> bool:
        """Whether this row owns a POPULATED flyout.

        Asks the O(1) ``contains_items`` rather than ``get_items()``: that
        walk recurses into every nested sublist, and this is read on every
        paint and every ``sizeHint`` -- so a deep menu paid a full walk of
        its whole tree per row per repaint.
        """
        sub = getattr(self, "sublist", None)
        return sub is not None and sub.contains_items

    # -- option menu --------------------------------------------------------

    def add_option_menu(self, tooltip: str = "Options", **menu_config):
        """Overlay a settings button on this row and return its ``Menu``.

        Deliberately NOT ``option_box.container``, the way a panel button
        wears its box: that stands a container in for the row and appends
        the button to the row's RIGHT -- which is exactly where the row's
        flyout opens, so on a row that is both an action and a category the
        settings box came up underneath the flyout and could not be clicked
        at all.  The button is a CHILD of the row instead, inset by the
        arrow's slot: it sits inside the row and to the LEFT of the arrow,
        and the flyout still opens clear of both.

        Parameters:
            tooltip: The button's tooltip.
            **menu_config: :class:`~uitk.widgets.menu.Menu` configuration for
                the popup (``position``, ``add_header``, ...).

        Returns:
            Menu: The settings menu, ready to ``add`` rows to.
        """
        from uitk.widgets.optionBox.options.option_menu import OptionMenuOption

        option = OptionMenuOption(wrapped_widget=self, tooltip=tooltip, **menu_config)
        button = option.widget
        button.setParent(self)
        self._option = option
        self._option_button = button
        self._layout_option_button()
        button.show()
        self.updateGeometry()
        return option.menu

    @property
    def option_menu(self):
        """The settings menu :meth:`add_option_menu` built, or ``None``."""
        return None if self._option is None else self._option.menu

    def _arrow_width(self) -> int:
        """Pixels the submenu arrow occupies; 0 when the row has no flyout."""
        if not self.has_flyout:
            return 0
        return self.fontMetrics().horizontalAdvance(self._ARROW)

    def _option_side(self) -> int:
        """The overlaid option button's edge length (it is square)."""
        return max(1, self.height() - 2 * self._OPTION_GAP)

    def _layout_option_button(self) -> None:
        """Place the option button inside the row, left of the arrow."""
        button = self._option_button
        if button is None:
            return
        side = self._option_side()
        arrow = self._arrow_width()
        right = self.width() - self._ARROW_INSET - arrow
        if arrow:
            right -= self._OPTION_GAP
        button.setGeometry(right - side, (self.height() - side) // 2, side, side)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_option_button()

    def sizeHint(self) -> QtCore.QSize:
        hint = super().sizeHint()
        extra = 0
        if self.has_flyout:
            extra += self.fontMetrics().horizontalAdvance(self._ARROW)
            extra += self._ARROW_INSET
        if self._option_button is not None:
            extra += hint.height() + self._OPTION_GAP
        if extra:
            hint.setWidth(hint.width() + extra)
        return hint

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.has_flyout:
            return
        painter = QtGui.QPainter(self)
        painter.setPen(self.palette().color(QtGui.QPalette.ButtonText))
        rect = self.rect().adjusted(0, 0, -self._ARROW_INSET, 0)
        painter.drawText(
            rect, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, self._ARROW
        )
        painter.end()


def _ignore_checked(fn):
    """Wrap *fn* so a button's ``clicked(bool)`` cannot fill one of its slots.

    Deliberately NOT ``functools.wraps``: PySide decides how many arguments
    to pass by inspecting the callable, and ``inspect.signature`` follows
    ``__wrapped__`` back to the original -- which would hand the bool
    straight back to the parameter this exists to protect.
    """

    def _run(*_ignored):
        return fn()

    return _run


class ContextMenu(Menu):
    """A :class:`Menu` whose rows can expand into flyouts of sub-rows.

    Parameters:
        parent: The widget the menu belongs to.  The menu is parented to
            that widget's WINDOW (as ``Menu.run_modal`` does): until it is
            shown as a popup it is a plain child widget, and a container
            that adopts children -- a ``QSplitter`` takes any new child as
            a pane -- would lay it out.  Parent it under a THEMED window:
            the menu and its flyouts inherit that stylesheet.
        activation: ``"hover"`` (flyouts open on mouse-over, the way a
            context menu's submenus do) or ``"click"``.
        **kwargs: Menu keyword arguments; the context-menu defaults
            (no chrome, cursor-positioned, hide on leave) apply underneath.
    """

    designer_spec = {"visible": False}

    _SIGNAL_KEYS = ("clicked", "toggled", "pressed", "released", "triggered")

    _DEFAULTS = dict(
        trigger_button="none",
        position="cursorPos",
        fixed_item_height=20,
        add_header=False,
        add_footer=False,
        match_parent_width=False,
        hide_on_leave=True,
        hide_on_trigger=False,
        ensure_on_screen=True,
    )

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        activation: str = "hover",
        **kwargs,
    ):
        host = parent.window() if parent is not None else None
        super().__init__(parent=host, **{**self._DEFAULTS, **kwargs})
        self._disposed = False
        self._list = ExpandableList(
            self, fixed_item_height=self.fixed_item_height, menu_surface=True
        )
        self._list.setObjectName("contextMenuList")
        self._list.apply_preset("click_menu" if activation == "click" else "hover_menu")
        self._list.on_item_interacted.connect(self._on_item_interacted)
        # The list IS the body; Menu.add wires the container's interaction
        # signal to hide-on-trigger, which stays off -- dismissal is decided
        # per row in _on_item_interacted (a category row must not close it).
        Menu.add(self, self._list)

    # -- population ---------------------------------------------------------

    @property
    def list(self) -> ExpandableList:
        """The root :class:`ExpandableList` holding the rows."""
        return self._list

    def add(
        self,
        x,
        data=None,
        *,
        parent: Optional[QtWidgets.QWidget] = None,
        callback=None,
        **kwargs,
    ) -> QtWidgets.QWidget:
        """Add a row (or a sub-row of *parent*) and return it.

        Narrows :meth:`Menu.add`: this menu's body is a LIST, so the grid
        placement arguments (``row`` / ``col`` / ``rowSpan`` / ``colSpan``)
        have no meaning here and ``parent`` -- which level the row goes on
        -- takes their place.  ``Menu.add(self, widget)`` still reaches the
        grid itself, which is how the list is seated in the first place.

        Parameters:
            x: Row text (a :class:`MenuRow` is made for it), a widget class
                name from uitk's registry (``"CheckBox"``, ``"Separator"``,
                ...), a widget class, or a widget instance.
            data: Item data, readable through ``row.item_data()``.
            parent: A row returned by an earlier :meth:`add`; the new row
                goes into its flyout.
            callback: The action to run, called with NO arguments --
                a row that captures its subject in a default
                (``lambda e=edge: ...``) keeps it.  ``clicked=`` connects the
                raw signal instead, whose ``checked`` bool would land in that
                default.
            **kwargs: Setter / signal kwargs in the Menu idiom
                (``setText=``, ``setEnabled=``, ``toggled=``...).
        """
        target = self._list if parent is None else parent.sublist
        if isinstance(x, str):
            widget_cls = self._resolve_row_class(x)
            if widget_cls is None:
                widget_cls = MenuRow
                kwargs.setdefault("setText", x)
        elif isinstance(x, QtWidgets.QWidget) or (
            inspect.isclass(x) and issubclass(x, QtWidgets.QWidget)
        ):
            widget_cls = x
        else:
            raise TypeError(
                "ContextMenu.add expects a row label, a widget class name, a "
                f"widget class or a widget; got {type(x).__name__}"
            )
        if callback is not None:
            kwargs["clicked"] = _ignore_checked(callback)
        is_action = any(key in kwargs for key in self._SIGNAL_KEYS)
        row = target.add(widget_cls, data=data, **kwargs)
        row.setProperty("contextAction", is_action)
        if isinstance(row, QtWidgets.QAbstractButton) and not isinstance(row, MenuRow):
            row.setProperty("class", "MenuRow")
        if parent is not None:
            # The arrow appears with the first sub-row -- and it is the slot an
            # overlaid option button is placed against, so the row is re-laid
            # out here rather than from its own paintEvent.
            if isinstance(parent, MenuRow):
                parent._layout_option_button()
            parent.updateGeometry()
            parent.update()
        return row

    @staticmethod
    def _resolve_row_class(name: str):
        """The widget class *name* stands for, or ``None`` for a row label.

        ``Menu``'s own cache first (Qt names, ``Separator``), then the uitk
        root registry (``CheckBox``, ``ComboBox``...), then ``QtWidgets``.
        Only an identifier-shaped, capitalised name is looked up at all, so
        any multi-word label ("Trim Empty Space") stays a label.

        A one-word capitalised label is NOT safe by construction: ``"Menu"``
        and ``"Label"`` are both real uitk widgets and resolve to them, not to
        a row reading "Menu". Pass ``setText=`` to force a label whenever the
        text could name a widget.
        """
        cls = Menu._resolve_widget_class(name)
        if cls is None and name.isidentifier() and name[:1].isupper():
            import uitk

            cls = getattr(uitk, name, None)
            if cls is None:
                cls = getattr(QtWidgets, name, None)
        if inspect.isclass(cls) and issubclass(cls, QtWidgets.QWidget):
            return cls
        return None

    def add_separator(self, title: str = "") -> QtWidgets.QWidget:
        """Add a section separator; *title* captions the rows below it."""
        sep = self.add("Separator", setTitle=title)
        sep.setProperty("contextAction", False)
        if not title:
            sep.setFixedHeight(9)
        return sep

    def add_entries(self, entries, parent=None) -> list:
        """Add rows for a widget's own context entries; return the rows.

        *entries* is the list a widget describes its right-click actions
        with -- ``{"label", "callback", "checkable", "checked"}`` dicts,
        ``None`` for a separator (see
        :meth:`~uitk.widgets.sequencer._timeline.TimelineView.default_context_entries`).
        A checkable entry becomes a ``CheckBox`` row whose ``toggled``
        carries the new state; a plain one an action row.  The counterpart
        to rendering the same list into a ``QMenu``, so a consumer folding
        a widget's entries into its own menu writes no per-entry loop.
        """
        rows = []
        for entry in entries:
            if entry is None:
                rows.append(self.add("Separator", parent=parent))
            elif entry.get("checkable"):
                rows.append(
                    self.add(
                        "CheckBox",
                        parent=parent,
                        setText=entry["label"],
                        setChecked=bool(entry.get("checked")),
                        toggled=entry["callback"],
                    )
                )
            else:
                rows.append(
                    self.add(entry["label"], parent=parent, callback=entry["callback"])
                )
        return rows

    # -- activation ---------------------------------------------------------

    def _on_item_interacted(self, item) -> None:
        """Run an action row: hide first, then click it.

        A category row (no callback) is navigation -- its flyout opened on
        hover and the click means nothing more.  The menu hides BEFORE the
        action runs so a callback that opens a dialog or moves focus does
        so over a clean screen, and the flyouts go with it.
        """
        if not item.property("contextAction"):
            return
        self.hide()
        if isinstance(item, QtWidgets.QAbstractButton):
            item.click()

    def keyPressEvent(self, event) -> None:
        if event.key() == QtCore.Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    # -- showing ------------------------------------------------------------

    def popup(self, global_pos: Optional[QtCore.QPoint] = None) -> None:
        """Show the menu at *global_pos* (the cursor by default), non-blocking."""
        if global_pos is None:
            global_pos = QtGui.QCursor.pos()
        self.show_as_popup(anchor_widget=None, position=QtCore.QPoint(global_pos))

    def exec_(
        self, global_pos: Optional[QtCore.QPoint] = None, dispose: bool = True
    ) -> None:
        """Show the menu and block until it is dismissed.

        Actions run through their callbacks while the loop spins, so there
        is no chosen-action return value (unlike ``QMenu.exec_``).  With
        *dispose* (the default) the menu tears itself down afterwards -- a
        context menu is built per right-click and never reused.
        """
        loop = QtCore.QEventLoop(self)
        self.on_hidden.connect(loop.quit)
        try:
            self.popup(global_pos)
            if self.isVisible():
                loop.exec_()
        finally:
            try:
                self.on_hidden.disconnect(loop.quit)
            except (RuntimeError, TypeError):
                pass
        if dispose:
            self.dispose()

    def dispose(self) -> None:
        """Tear the menu down: flyouts are reparented top-levels, so they
        must be cleared explicitly or they outlive the menu on the window."""
        if self._disposed:
            return
        self._disposed = True
        try:
            self._list.clear()
            self.deleteLater()
        except RuntimeError:
            pass  # already torn down with its parent
