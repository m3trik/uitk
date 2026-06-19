# !/usr/bin/python
# coding=utf-8
import re
from qtpy import QtWidgets, QtCore

# From this package:
from uitk.widgets.mixins.attributes import AttributesMixin


class MenuButton(QtWidgets.QPushButton, AttributesMixin):
    """A navigation button for marking menus.

    Replaces the legacy ``i``-prefixed ``QPushButton`` convention, which
    identified a navigation button by an ``i`` object-name prefix and smuggled
    its destination into ``accessibleName()`` (a screen-reader property),
    overloading one string with both the target menu *and* a tag filter.
    ``MenuButton`` is a distinct widget *type* that carries its routing as
    first-class, Designer-editable properties:

    - ``target``     — the menu/submenu UI to open, e.g. ``"polygons#submenu"``.
                       Kept clean — filter tags are *not* merged into it.
    - ``filterTags`` — optional space/comma-separated tags; the marking menu
                       passes these to ``hide_unmatched_groupboxes`` so a button
                       can reveal only part of a shared submenu (the ``face``
                       groupboxes of the polygons menu, etc.).

    The marking menu detects it by type (``isinstance(w, MenuButton)``) — no
    name prefix, no ``accessibleName`` — and reads ``target`` / ``filter_tag_list``
    directly. Breadcrumb clones carry the routing via ``clone_properties``.
    Slot-coverage tooling can exclude it cleanly: a ``MenuButton`` owns
    navigation, not a slot.

    Properties are ``QtCore.Property`` so they round-trip through ``.ui`` files
    and route to the validated setters at load (the compiled ``_ui.py`` emits
    ``setTarget`` / ``setFilterTags``). In Qt Designer set them as dynamic
    properties on the promoted widget; a Designer plugin would be needed only to
    surface them as first-class fields.

    Example:
        b = MenuButton(setText="Polygons", target="polygons#submenu", filterTags="face")
    """

    # Qt properties the marking menu's breadcrumb clones must carry across so a
    # cloned MenuButton still navigates (overlay copies these generically).
    clone_properties = ("target", "filterTags")

    def __init__(self, parent=None, target="", filterTags="", **kwargs):
        QtWidgets.QPushButton.__init__(self, parent)

        self._target = ""
        self._filter_tags = ""

        # QSS hook: styled via QPushButton[class~="MenuButton"].
        self.setProperty("class", self.__class__.__name__)

        self.setTarget(target)
        self.setFilterTags(filterTags)

        self.set_attributes(**kwargs)

    # -- target ---------------------------------------------------------------
    def getTarget(self) -> str:
        return self._target

    def setTarget(self, value: str) -> None:
        self._target = value or ""

    target = QtCore.Property(str, fget=getTarget, fset=setTarget)

    # -- filterTags -----------------------------------------------------------
    def getFilterTags(self) -> str:
        return self._filter_tags

    def setFilterTags(self, value: str) -> None:
        self._filter_tags = value or ""

    filterTags = QtCore.Property(str, fget=getFilterTags, fset=setFilterTags)

    # -- accessors ------------------------------------------------------------
    def filter_tag_list(self) -> list:
        """Return ``filterTags`` parsed to a list of tags (empty when unset)."""
        if not self._filter_tags:
            return []
        return [t for t in re.split(r"[,\s]+", self._filter_tags) if t]

    def submenu_name(self) -> str:
        """The submenu UI name this button navigates to on hover.

        Composes ``target`` with any ``filterTags`` and the ``submenu`` tag —
        ``target="render"`` → ``"render#submenu"``; ``target="polygons"`` +
        ``filterTags="edge"`` → ``"polygons#edge#submenu"``. Single source of
        truth for the hover-nav name: both the marking menu's ``child_enterEvent``
        (which opens it) and the visibility policy's resolution check (which must
        not hide a button that reaches it) read this, so the two can't drift.
        """
        return "#".join([self.target, *self.filter_tag_list(), "submenu"])

    # -- events ---------------------------------------------------------------
    def hideEvent(self, event) -> None:
        """Drop any lingering ``:hover`` state before the button is reshown.

        A marking-menu button is usually hidden *under the cursor* — the menu
        closes in place, so no ``leaveEvent`` precedes the hide. Qt leaves
        ``WA_UnderMouse`` set in that case, which keeps ``State_MouseOver`` (and
        the QSS ``:hover`` rule) live, so the next ``show()`` would paint the
        button as hovered until a real enter/leave recomputes it.

        Clearing the attribute is the whole fix: ``:hover`` is a pseudo-state Qt
        rebuilds from the style option (which reads ``WA_UnderMouse``) on every
        paint, so the next show repaints non-hovered — no repolish needed (that
        idiom is for dynamic-property selector re-cascade, not pseudo-states).
        """
        self.setAttribute(QtCore.Qt.WA_UnderMouse, False)
        super().hideEvent(event)


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = MenuButton(
        parent=None,
        setObjectName="menu_button_test",
        setText="Polygons →",
        target="polygons#submenu",
        filterTags="face",
    )
    print("target:", w.target, "| filter_tag_list:", w.filter_tag_list())
    w.show()
    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Promoting a widget in designer to use a custom class:
>   In Qt Designer, select the QPushButton(s) you want to replace,
        then right-click them and select 'Promote to...'.

>   In the dialog:
        Base Class:     QPushButton
        Promoted Class: MenuButton
        Header File:    uitk.widgets.menuButton.h

>   Set 'target' (and optionally 'filterTags') as dynamic properties in the
        property editor; they route to the QtCore.Property setters when the .ui
        is loaded.
"""
