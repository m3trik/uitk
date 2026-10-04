# !/usr/bin/python
# coding=utf-8
"""A form any layout can hold: labelled rows built the way a Menu is built.

The form region of :class:`~uitk.widgets.windowPanel.WindowPanel`, lifted out
so it can sit inside a window rather than only BE one -- a page of a stacked
panel, a section of a Switchboard window. :meth:`FormRows.add` takes a
widget-class name, an instance or a class, applies setter-style kwargs
(``setText=``, ``setObjectName=``, a signal name to connect), places it as a
form row -- caption on the left, field on the right, every caption in one
column -- and exposes it as ``rows.<objectName>``. One idiom for a popup
(``Menu``), a window (``WindowPanel``) and a form inside either; only the
lifecycle differs.
"""

import inspect
import logging
from typing import Dict, Optional, Union

from qtpy import QtWidgets, QtCore
from uitk.widgets.mixins.attributes import AttributesMixin
from pythontk import TooltipFormat
from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

_logger = logging.getLogger(__name__)


class FormRows(QtWidgets.QWidget, AttributesMixin):
    """A ``QFormLayout`` of rows with the Menu-style :meth:`add`.

    Empty, it has no height; a row is compact (growable content -- a table, a
    log -- belongs beside it in the host layout, with a stretch).

    Parameters:
        parent: The host widget.
    """

    # Not a Designer widget-box entry: it is filled in code.
    designer_spec = {"visible": False}

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        # A QFormLayout, so a labelled row's caption sits to the LEFT of its
        # control and every caption shares one column (the fields line up).
        self._rows_layout = QtWidgets.QFormLayout(self)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setHorizontalSpacing(4)
        self._rows_layout.setVerticalSpacing(2)
        self._rows_layout.setLabelAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        self._rows_layout.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self._rows_layout.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.AllNonFixedFieldsGrow
        )
        self._rows_layout.setRowWrapPolicy(QtWidgets.QFormLayout.DontWrapRows)
        #: widget -> the widgets that grey out WITH it: its caption, then any
        #: companions sharing its cell (what a host keeping rows in step reads).
        self._row_widgets: Dict[QtWidgets.QWidget, list] = {}
        #: Every row caption, in add order -- the label column, sized as one
        #: (see :meth:`_sync_caption_widths`).
        self._captions: list = []
        #: objectNames :meth:`add` exposed as attributes -- un-exposed by
        #: :meth:`clear_rows`, so a rebuilt form holds no dead wrappers.
        self._exposed_names = set()
        #: The form this one is a section of (:meth:`add_section`), which
        #: exposes its names too; ``None`` for a top-level form.
        self._owner: Optional["FormRows"] = None

    @property
    def rows_layout(self) -> QtWidgets.QFormLayout:
        """The ``QFormLayout`` :meth:`add` places rows in."""
        return self._rows_layout

    def row_widgets(self, widget: QtWidgets.QWidget) -> list:
        """The widgets that grey out with *widget*: its caption, then its
        companions."""
        return list(self._row_widgets.get(widget, ()))

    def showEvent(self, event):
        super().showEvent(event)
        # Re-measured on show as well as at add time: a theme lands on first
        # show, and a caption measured before it is missing the plate's padding.
        self._sync_caption_widths()

    # ── Dynamic build -- the Menu idiom ─────────────────────────────

    def add(
        self,
        x: Union[str, QtWidgets.QWidget, type, list, tuple],
        label: Optional[str] = None,
        hint: Optional[str] = None,
        tooltip: Optional[str] = None,
        companions=(),
        label_align=None,
        **kwargs,
    ) -> Union[QtWidgets.QWidget, list]:
        """Add a widget as a form row the way ``Menu.add`` adds an item.

        Parameters:
            x: What to add -- a widget-class NAME (resolved through the uitk
                root registry first, so ``"CheckBox"`` is uitk's and
                ``"Separator"`` works, then ``QtWidgets``), a widget instance,
                a widget class, or a list/tuple of any of those. A string that
                names no widget class becomes a caption label carrying that
                text -- ``add("Output:")`` -- the same affordance a Menu has
                (and the same trap: a typo'd class name is a label, so the
                fallthrough is logged at DEBUG).
            label: Caption placed to the LEFT of the control, in the shared
                label column. Without one the widget spans the row.
            hint: What this row will DO. Rendered as a formatted tooltip on the
                caption, the widget and its companions alike, titled with the
                label.
            tooltip: Pre-formatted rich text used verbatim instead of the
                ``label``/``hint`` composition.
            companions: Widgets that share the field cell (a Browse button
                beside a path field, an action beside the button it belongs
                to) and grey out with it.
            label_align: Where the caption's TEXT sits inside the column its
                plate fills -- ``"left"`` (default), ``"right"``, ``"center"``,
                or a Qt alignment.
            **kwargs: Applied through :meth:`AttributesMixin.set_attributes` --
                setter-style (``setText=``, ``setObjectName=``) and any signal
                name to connect (``clicked=self.on_click``) -- exactly a Menu
                item's kwargs.

        Returns:
            The widget (a list of them for a list/tuple), exposed as
            ``self.<objectName>`` when it has one and the name does not collide
            with a real attribute of the form.

        Example::

            rows = FormRows(parent)
            rows.add("QSpinBox", label="Frames", setObjectName="spn_frames")
            rows.add("QPushButton", setText="Key", companions=[remove_button])
            rows.spn_frames.value()
        """
        if isinstance(x, (list, tuple)):
            return [
                self.add(
                    item,
                    label=label,
                    hint=hint,
                    tooltip=tooltip,
                    companions=companions,
                    label_align=label_align,
                    **kwargs,
                )
                for item in x
            ]
        widget = self._build_widget(x)
        self.set_attributes(widget, **kwargs)
        self._add_row(
            widget,
            label=label,
            hint=hint,
            tooltip=tooltip,
            companions=companions,
            label_align=label_align,
        )
        self._expose_as_attribute(widget)
        return widget

    def add_section(self, title: str, **kwargs) -> "FormRows":
        """A run of rows that folds away under *title*, added as one row.

        A :class:`~uitk.widgets.collapsableGroup.CollapsableGroup` holding a
        form of its own: what is added to the returned form folds with the
        group, and every name it exposes is exposed on THIS form too, so a
        field reads the same (``rows.spn_frames``) on either side of the fold.
        The group's one child is that form, so folding hides the form whole
        and leaves each field's own visibility -- a mode's
        :class:`~uitk.managers.field_visibility.FieldVisibility` -- alone.

        Parameters:
            title: The group's caption, which is what folds it.
            **kwargs: Applied to the group as :meth:`add` applies them. Named
                (``setObjectName=``), the group keeps its folded state per
                window, as every ``CollapsableGroup`` does.

        Returns:
            The section's :class:`FormRows`; the group is its ``parentWidget()``.
        """
        from uitk.widgets.collapsableGroup import CollapsableGroup

        group = self.add(CollapsableGroup(title), **kwargs)
        # Flush: a section is embedded in a form, and the style's default
        # margins indent its rows off the line the form's other rows keep.
        QtWidgets.QVBoxLayout(group).setContentsMargins(0, 0, 0, 0)
        section = FormRows(group)
        section._owner = self
        group.addWidget(section)
        return section

    @staticmethod
    def _resolve_widget_class(name: str):
        """The widget class *name* denotes, or None.

        The uitk root registry (``DEFAULT_INCLUDE``) is the single source of
        truth for widget names, so it is asked first -- no second table of
        names is born here -- and ``QtWidgets`` second. That registry also
        resolves NON-widgets (managers, mixins), so a hit is type-checked
        before anything is instantiated.
        """
        import uitk

        for source in (uitk, QtWidgets):
            try:
                candidate = getattr(source, name)
            except AttributeError:
                continue
            if inspect.isclass(candidate) and issubclass(candidate, QtWidgets.QWidget):
                return candidate
        return None

    @classmethod
    def _build_widget(cls, x) -> QtWidgets.QWidget:
        """Turn an :meth:`add` argument into a widget instance."""
        if isinstance(x, QtWidgets.QWidget):
            return x
        if inspect.isclass(x) and issubclass(x, QtWidgets.QWidget):
            return x()
        if isinstance(x, str):
            widget_cls = cls._resolve_widget_class(x)
            if widget_cls is not None:
                return widget_cls()
            if x.isidentifier() and x[:1].isupper():
                _logger.debug(
                    "FormRows.add: %r names no widget class; added as a caption.", x
                )
            caption = QtWidgets.QLabel(x)
            caption.setProperty("caption", True)
            return caption
        raise TypeError(
            "add() expects a widget-class name, a QWidget instance or class, "
            f"or a list/tuple of those; got {type(x).__name__}"
        )

    @staticmethod
    def _row_tooltip(title, hint, tooltip) -> str:
        """A row's tooltip: the explicit one, else the title + hint composed.

        Composed rather than concatenated so a hint reads as the answer to the
        caption beside it -- the title/body shape every other tooltip in the
        toolset uses. A row with no caption (a checkbox, whose label is its own
        text) gets the body alone.
        """
        if tooltip:
            return str(tooltip)
        if not hint:
            return ""
        return TooltipFormat.fmt(title=str(title) if title else None, body=str(hint))

    #: ``label_align`` spellings -- the caption's TEXT inside the plate that
    #: fills the label column (see :meth:`_sync_caption_widths`). Vertical
    #: centering is never optional: a caption is height-matched to the control
    #: it names.
    _LABEL_ALIGNMENTS = {
        "left": QtCore.Qt.AlignLeft,
        "right": QtCore.Qt.AlignRight,
        "center": QtCore.Qt.AlignHCenter,
    }

    @classmethod
    def _label_alignment(cls, align):
        """*align* as a Qt alignment -- a name, a flag, or None for the default."""
        if align is None:
            return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        if isinstance(align, str):
            try:
                flag = cls._LABEL_ALIGNMENTS[align.lower()]
            except KeyError:
                raise ValueError(
                    f"label_align must be one of {sorted(cls._LABEL_ALIGNMENTS)} "
                    f"or a Qt alignment; got {align!r}"
                ) from None
        else:
            flag = align
        return flag | QtCore.Qt.AlignVCenter

    def _add_row(
        self,
        widget,
        label=None,
        hint=None,
        tooltip=None,
        companions=(),
        label_align=None,
    ) -> Optional[QtWidgets.QLabel]:
        """Place *widget* as a form row; returns its caption label, if any.

        The caption carries the theme's ``caption`` hook -- a label that NAMES
        the control beside it rather than being a field of its own, so it drops
        the base QLabel's border but keeps its opaque plate (a panel body is
        translucent; a transparent caption would read against the viewport
        behind the window) -- and mirrors the control's enabled state at add
        time so a settled row greys out whole.
        """
        companions = list(companions)
        tip = self._row_tooltip(label, hint, tooltip)

        caption = None
        if label:
            caption = QtWidgets.QLabel(str(label))
            caption.setProperty("caption", True)
            caption.setAlignment(self._label_alignment(label_align))
            font = caption.font()
            font.setBold(True)
            caption.setFont(font)
            caption.setEnabled(widget.isEnabled())

        for companion in companions:
            companion.setEnabled(widget.isEnabled())
        if tip:
            for target in (caption, widget, *companions):
                if target is not None:
                    target.setToolTip(tip)
                    TooltipPresenter.manage(target)

        if companions:
            cell = QtWidgets.QHBoxLayout()
            cell.setSpacing(2)
            # The row's WIDTH belongs to the control it names: companions ride
            # at their own hint (a button, a tick), and everything left over
            # goes to the field. Without the stretch a companion carrying a
            # long caption simply outbids the control -- a Copy/Move combo
            # crushed to a few pixels by the tick box beside it.
            cell.addWidget(widget, 1)
            for companion in companions:
                cell.addWidget(companion)
            field = cell
        else:
            field = widget

        if caption is not None:
            self._rows_layout.addRow(caption, field)
        else:
            self._rows_layout.addRow(field)
        self._row_widgets[widget] = [w for w in (caption, *companions) if w is not None]
        if caption is not None:
            self._captions.append(caption)
            self._sync_caption_widths()
        return caption

    def _sync_caption_widths(self) -> None:
        """Floor every caption at the widest one: the label column, filled.

        QFormLayout sizes a label to its OWN hint and aligns it inside the
        label column, so every caption but the widest stops short of the
        control it names -- and a caption carries an opaque PLATE, so that gap
        is not whitespace, it is a ragged edge down the middle of the form.
        Flooring them all at the widest hint fills the column the layout
        already reserved: the plates end on one line, flush against the field
        column, and nothing moves (the floor is the column's own width, so no
        field loses a pixel).

        Stateless: each caption's floor is dropped before it is measured, so a
        re-sync after the theme lands (or after a row is added) measures the
        TEXT rather than the floor the last pass set.
        """
        hints = []
        live = []
        for caption in self._captions:
            try:  # a row rebuilt behind us leaves a deleted C++ wrapper here
                caption.setMinimumWidth(0)
                hints.append(caption.sizeHint().width())
            except RuntimeError:
                continue
            live.append(caption)
        self._captions = live
        if not live:
            return
        column = max(hints)
        for caption in live:
            caption.setMinimumWidth(column)

    def _expose_as_attribute(self, widget: QtWidgets.QWidget) -> None:
        """Expose a widget as ``self.<objectName>`` -- never over the form's API.

        Anything the CLASS defines is off limits, and only an instance
        attribute that is itself an exposed widget (a rebuilt row) may be
        replaced.
        """
        name = widget.objectName()
        if not name:
            return
        existing = self.__dict__.get(name)
        if hasattr(type(self), name) or not (
            existing is None or isinstance(existing, QtWidgets.QWidget)
        ):
            _logger.warning(
                "%s.add: objectName %r collides with an existing attribute; "
                "skipping attribute exposure.",
                type(self).__name__,
                name,
            )
            return
        setattr(self, name, widget)
        self._exposed_names.add(name)
        if self._owner is not None:
            self._owner._expose_as_attribute(widget)

    def _unexpose(self, name: str, widget) -> None:
        """Drop ``self.<name>`` if it is *widget* -- here and on every form
        this one is a section of."""
        if widget is not None and self.__dict__.get(name) is widget:
            del self.__dict__[name]
            self._exposed_names.discard(name)
        if self._owner is not None:
            self._owner._unexpose(name, widget)

    def clear_rows(self) -> None:
        """Drop every row :meth:`add` placed, and the attributes exposing them.

        The exposed names go too -- on the forms this one is a section of as
        well: the widgets are ``deleteLater``'d, and an attribute still
        pointing at one would hand back a dead C++ wrapper.
        """
        for name in list(self._exposed_names):
            self._unexpose(name, self.__dict__.get(name))
        self._exposed_names.clear()
        self._row_widgets.clear()
        self._captions.clear()
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                self._drop_layout(item.layout())

    @classmethod
    def _drop_layout(cls, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                cls._drop_layout(item.layout())
        layout.deleteLater()
