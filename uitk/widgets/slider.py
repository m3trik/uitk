# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.menu_mixin import MenuMixin
from uitk.widgets.mixins.option_box_mixin import OptionBoxMixin


class Slider(
    QtWidgets.QSlider,
    MenuMixin,
    OptionBoxMixin,
    AttributesMixin,
):
    """QSlider with uitk's menu + option-box integration.

    Mirrors the other uitk input widgets (``ComboBox`` / ``SpinBox``): adds the
    right-click context :class:`Menu` (``MenuMixin``) and an ``.option_box``
    (``OptionBoxMixin``) so a slider can carry icon action buttons and — via
    :class:`ValueOption` — an inline editable numeric readout beside it.

    Horizontal by default (the common panel orientation). Construct bare and set
    range via the usual Qt API, or pass Qt setters as kwargs
    (``Slider(setMinimum=0, setMaximum=360)``) through ``AttributesMixin``.
    """

    # Class-level menu defaults (mirrors SpinBox / ComboBox).
    _menu_defaults = {"hide_on_leave": True}

    def __init__(self, parent=None, **kwargs):
        QtWidgets.QSlider.__init__(self, parent)
        self.setOrientation(QtCore.Qt.Horizontal)
        # Drives the `Slider { ... }` QSS rule, matching the other uitk widgets.
        self.setProperty("class", self.__class__.__name__)
        self.set_attributes(**kwargs)
