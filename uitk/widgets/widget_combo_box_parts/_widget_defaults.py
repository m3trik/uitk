# !/usr/bin/python
# coding=utf-8
"""A combo's "Restore Defaults" snapshots -- one part of
:class:`~uitk.widgets.widgetComboBox.WidgetComboBox` (see
``widget_combo_box_parts``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from qtpy import QtWidgets

if TYPE_CHECKING:
    from uitk.widgets.widgetComboBox import WidgetComboBox


class _WidgetDefaults:
    """A :class:`WidgetComboBox`'s optional "Restore Defaults" action: each
    embedded option widget's value as it was added, and the action that puts
    them all back.

    Owns the snapshots and the action's switch and label; holds the combo and
    adds or removes the action through its :attr:`WidgetComboBox.actions`.
    """

    def __init__(self, combo: "WidgetComboBox") -> None:
        self._combo = combo
        # Snapshots of embedded-widget initial values, keyed by widget id.
        # Captured lazily on first ``_add_widget_item`` so defaults reflect the
        # widget's seeded state.
        self.snapshots: dict[int, tuple] = {}
        self.add_button: bool = False
        self.action_label: str = "Restore Defaults"

    def set_add_button(self, value: bool) -> None:
        value = bool(value)
        if value == self.add_button:
            return
        self.add_button = value
        actions = self._combo.actions
        if value:
            if self.action_label not in actions:
                actions.add(self.action_label, self.restore)
        else:
            actions.remove(self.action_label)

    def capture(self, widget: QtWidgets.QWidget) -> None:
        """Snapshot *widget*'s current value for later defaults reset.

        Idempotent — the first captured value wins, so callers can re-add
        items without losing the original default.
        """
        wid = id(widget)
        if wid in self.snapshots:
            return
        snapshot = self.snapshot_value(widget)
        if snapshot is not None:
            self.snapshots[wid] = snapshot

    @staticmethod
    def snapshot_value(widget: QtWidgets.QWidget) -> Optional[tuple]:
        """Return a (kind, value) tuple describing the widget's current value,
        or None if the widget has no resettable value.
        """
        if isinstance(widget, QtWidgets.QCheckBox):
            return ("checked", widget.isChecked())
        if isinstance(widget, QtWidgets.QComboBox):
            from uitk.managers.value_manager import ValueManager

            return ("currentIndex", ValueManager.combo_value(widget, "index"))
        if isinstance(widget, QtWidgets.QLineEdit):
            return ("text", widget.text())
        if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            return ("value", widget.value())
        if isinstance(widget, (QtWidgets.QSlider, QtWidgets.QDial)):
            return ("value", widget.value())
        if isinstance(widget, QtWidgets.QRadioButton):
            return ("checked", widget.isChecked())
        return None

    @staticmethod
    def apply_snapshot(widget: QtWidgets.QWidget, snapshot: tuple) -> None:
        kind, value = snapshot
        if kind == "checked":
            widget.setChecked(value)
        elif kind == "currentIndex":
            widget.setCurrentIndex(value)
        elif kind == "text":
            widget.setText(value)
        elif kind == "value":
            widget.setValue(value)

    def restore(self) -> None:
        """Reset every embedded option widget to its captured default."""
        for widget in self._combo._widget_items.values():
            snapshot = self.snapshots.get(id(widget))
            if snapshot is not None:
                self.apply_snapshot(widget, snapshot)
