# !/usr/bin/python
# coding=utf-8
from typing import Optional
from qtpy import QtWidgets, QtCore, QtGui

# From this package:
from uitk.widgets.mixins.attributes import AttributesMixin


class Separator(QtWidgets.QFrame, AttributesMixin):
    """A simple horizontal separator with optional title and styling."""

    # Qt Designer widget-box entry.
    designer_spec = {"icon": "tree_horizontal", "object_name": "separator"}

    def __init__(
        self, parent: Optional[QtWidgets.QWidget] = None, title: str = "", **kwargs
    ):
        super().__init__(parent)

        self.setProperty("class", "separator")
        self.setFrameShape(QtWidgets.QFrame.HLine)
        self.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.setFixedHeight(9)  # Total height including padding
        self.setLineWidth(1)
        self.setMidLineWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        # Disable mouse interaction - separators are purely visual
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        # Title label (hidden by default)
        self._title_label: Optional[QtWidgets.QLabel] = None

        if title:
            self.title = title

        self.set_attributes(self, **kwargs)

    # Horizontal margin around the title label (left + right). Used by both
    # ``resizeEvent`` (positioning) and ``sizeHint`` (advertised width).
    _TITLE_MARGIN_X = 4
    #: Fixed height of a titled separator. Taller than the untitled 9px so a
    #: section caption carries breathing room ABOVE it: the label sits at the
    #: bottom of the box, and the surplus reads as the gap between groups.
    _TITLED_HEIGHT = 18
    #: Gap between the caption's right edge and the start of the section rule.
    _RULE_GAP_X = 6
    #: Alpha (0-255) of the section rule, drawn in the caption's text colour.
    _RULE_ALPHA = 70

    def getTitle(self) -> str:
        """Get the separator title."""
        if self._title_label:
            return self._title_label.text()
        return ""

    def setTitle(self, value: str) -> None:
        """Set the separator title. Empty string hides the title."""
        if value:
            if not self._title_label:
                self._create_title_label()
            self._title_label.setText(value)
            self._title_label.show()
            # Adjust height to accommodate title
            self.setFixedHeight(self._TITLED_HEIGHT)
            # Change to NoFrame when showing title: the section rule is
            # painted by ``paintEvent`` (from the caption's edge to the right
            # margin) instead of QFrame's full-width HLine, so it never runs
            # behind the text.
            self.setFrameShape(QtWidgets.QFrame.NoFrame)
            # Size + position the label immediately. Don't rely on
            # resizeEvent firing while the host is still hidden — at that
            # point the gate inside resizeEvent skips, and the label stays
            # at its default 0×0 geometry, which then renders cropped
            # when the host finally shows.
            self._position_title_label()
        elif self._title_label:
            self._title_label.hide()
            self.setFixedHeight(9)
            self.setFrameShape(QtWidgets.QFrame.HLine)
        # Title presence changes our advertised width; tell parent layouts to
        # re-query sizeHint so the title can't be cropped by a too-narrow host.
        self.updateGeometry()

    #: A Qt property rather than a Python one, so the title is editable in Qt
    #: Designer and round-trips through a ``.ui`` file. ``separator.title``
    #: reads and assigns exactly as it did before.
    title = QtCore.Property(str, fget=getTitle, fset=setTitle)

    def _create_title_label(self) -> None:
        """Create the title label widget.

        The caption is a *section header*, not another row: rendered
        small-caps (``QFont.AllUppercase`` — the theme's ``Separator > QLabel``
        rule sets colour / size / weight and leaves capitalization alone) so
        it reads as a group label even when it sits among rows of the same
        font, e.g. inside a ``WidgetComboBox`` popup or a ``Menu`` column.
        Capitalization is a font property so :meth:`getTitle` still returns
        the text as authored.
        """
        self._title_label = QtWidgets.QLabel(self)
        self._title_label.setProperty("class", "separator-title")
        self._title_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        font = self._title_label.font()
        font.setCapitalization(QtGui.QFont.AllUppercase)
        self._title_label.setFont(font)

    def _titled_width_hint(self) -> int:
        """Width needed to render the title without cropping (0 if untitled).

        Uses ``not isHidden()`` (not ``isVisible()``) because ``sizeHint`` is
        queried by the layout system before the widget tree is shown, when
        ``isVisible()`` is still False even for un-hidden children.
        """
        if self._title_label and not self._title_label.isHidden():
            return self._title_label.sizeHint().width() + 2 * self._TITLE_MARGIN_X
        return 0

    def sizeHint(self) -> QtCore.QSize:
        """Advertise enough width for the title so parent layouts reserve room.

        Without this, ``QFrame``'s HLine-derived sizeHint reports near-zero
        width and host containers (notably ``QMenu``) size the separator
        purely off sibling widgets — the title label is then clipped by the
        separator's bounds when the host is narrower than the text.
        """
        hint = super().sizeHint()
        title_w = self._titled_width_hint()
        if title_w > hint.width():
            hint.setWidth(title_w)
        return hint

    def minimumSizeHint(self) -> QtCore.QSize:
        """Match ``sizeHint`` so the widget can't be squeezed below its title."""
        hint = super().minimumSizeHint()
        title_w = self._titled_width_hint()
        if title_w > hint.width():
            hint.setWidth(title_w)
        return hint

    def _position_title_label(self) -> None:
        """Size the label to its natural width and bottom-align it.

        Used by both the title setter (so positioning happens immediately,
        even before the widget tree is shown) and ``resizeEvent`` (so the
        label re-centers when the separator's height changes). The guard
        uses ``not isHidden()`` rather than ``isVisible()`` because the
        latter requires the entire ancestor chain to be visible — which
        isn't true while a host menu is still in its pre-show state.
        """
        if self._title_label is None or self._title_label.isHidden():
            return
        self._title_label.adjustSize()
        # Bottom-aligned: the surplus height of a titled separator is the
        # breathing room above the caption (see ``_TITLED_HEIGHT``).
        y = max(0, self.height() - self._title_label.height())
        self._title_label.move(self._TITLE_MARGIN_X, y)

    def resizeEvent(self, event) -> None:
        """Position the title label on resize."""
        super().resizeEvent(event)
        self._position_title_label()

    def paintEvent(self, event) -> None:
        """Untitled: QFrame's HLine. Titled: a rule from the caption to the edge.

        The rule is drawn in the caption's own text colour at reduced alpha,
        so it follows whatever the theme gives ``Separator > QLabel`` (light or
        dark) without a second token, and it starts AFTER the label so no
        text ever sits on the line — which is why the label needs no opaque
        background (it used to carry ``PANEL_BACKGROUND``, which mismatched
        hosts painted in ``WIDGET_BACKGROUND`` such as a combo popup).
        """
        super().paintEvent(event)
        label = self._title_label
        if label is None or label.isHidden():
            return
        x0 = label.x() + label.width() + self._RULE_GAP_X
        x1 = self.width() - self._TITLE_MARGIN_X
        if x1 <= x0:
            return
        y = label.y() + label.height() // 2
        color = QtGui.QColor(label.palette().color(QtGui.QPalette.WindowText))
        color.setAlpha(self._RULE_ALPHA)
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QPen(color, 1))
        painter.drawLine(x0, y, x1, y)
        painter.end()


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from qtpy.QtCore import QSize

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv
    )  # return the existing QApplication object, or create a new one if none exists.

    w = Separator(setStyleSheet="background-color: red;", setMinimumSize=QSize(200, 1))
    w.show()
    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Promoting a widget in designer to use a custom class:
>   In Qt Designer, select all the widgets you want to replace, 
        then right-click them and select 'Promote to...'. 

>   In the dialog:
        Base Class:     Class from which you inherit. ie. QWidget
        Promoted Class: Name of the class. ie. "MyWidget"
        Header File:    Path of the file (changing the extension .py to .h)  ie. myfolder.mymodule.mywidget.h

>   Then click "Add", "Promote", 
        and you will see the class change from "QWidget" to "MyWidget" in the Object Inspector pane.
"""
