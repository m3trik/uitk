# !/usr/bin/python
# coding=utf-8
"""Regression tests for the base uitk ComboBox widget."""
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()


class SetEditableNoneSafety(QtBaseTestCase):
    """``setEditable(False)`` on a non-editable combo must not AttributeError.

    Background: pyside6-uic-generated setupUi calls setEditable(False)
    explicitly when a .ui declares ``<property name="editable"><bool>false</bool></property>``.
    QComboBox.lineEdit() returns None when the combo is not editable, so the
    previous code raised on ``lineEdit.text()``. See
    [comboBox.py](uitk/uitk/widgets/comboBox.py).
    """

    def test_set_editable_false_on_default_combo_does_not_raise(self):
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        # Default state: editable is False, lineEdit() is None. The call
        # must be a no-op rather than crash.
        combo.setEditable(False)

    def test_set_editable_true_then_false_round_trip(self):
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        combo.addItem("alpha")
        combo.setEditable(True)
        # Now lineEdit() returns a real QLineEdit
        self.assertIsNotNone(combo.lineEdit())
        combo.setEditable(False)
        # And we can flip again without issue
        combo.setEditable(False)


class CustomStyleFocusStateStripping(QtBaseTestCase):
    """``CustomStyle._strip_focus_state_for_combobox`` must clear
    ``State_HasFocus`` for ``CC_ComboBox`` so the native Windows style
    doesn't paint a blue focus border on top of the QSS-styled combobox
    after click/leave. The visual paint can only be observed on Windows;
    here we lock the option-prep contract that ``drawComplexControl``
    delegates to."""

    def test_focus_state_stripped_for_cc_combobox(self):
        from qtpy import QtWidgets
        from uitk.widgets.comboBox import CustomStyle

        opt = QtWidgets.QStyleOptionComboBox()
        opt.state = QtWidgets.QStyle.State_HasFocus | QtWidgets.QStyle.State_Enabled

        prepared = CustomStyle._strip_focus_state_for_combobox(
            QtWidgets.QStyle.CC_ComboBox, opt
        )

        self.assertFalse(
            bool(prepared.state & QtWidgets.QStyle.State_HasFocus),
            "State_HasFocus must be stripped before the native style paints",
        )
        self.assertTrue(
            bool(prepared.state & QtWidgets.QStyle.State_Enabled),
            "Other state flags must be preserved",
        )

    def test_focus_state_preserved_for_non_combobox_controls(self):
        from qtpy import QtWidgets
        from uitk.widgets.comboBox import CustomStyle

        opt = QtWidgets.QStyleOptionComboBox()
        opt.state = QtWidgets.QStyle.State_HasFocus

        # CC_Slider should pass through untouched — we only strip for combobox.
        prepared = CustomStyle._strip_focus_state_for_combobox(
            QtWidgets.QStyle.CC_Slider, opt
        )

        self.assertTrue(
            bool(prepared.state & QtWidgets.QStyle.State_HasFocus),
            "Non-combobox controls must keep their focus state",
        )
        self.assertIs(
            prepared, opt,
            "Non-combobox path must return the original option unchanged",
        )

    def test_caller_option_is_not_mutated(self):
        from qtpy import QtWidgets
        from uitk.widgets.comboBox import CustomStyle

        opt = QtWidgets.QStyleOptionComboBox()
        opt.state = QtWidgets.QStyle.State_HasFocus

        CustomStyle._strip_focus_state_for_combobox(
            QtWidgets.QStyle.CC_ComboBox, opt
        )

        self.assertTrue(
            bool(opt.state & QtWidgets.QStyle.State_HasFocus),
            "Caller's option must not be mutated (we copy via QStyleOptionComboBox(opt))",
        )


class ComboBoxStyleConfiguration(QtBaseTestCase):
    """Lock the Win11-avoidance setup. Win11's native style paints a blue
    focus border outside QSS control and delivers ``:hover`` events to
    popup items unreliably; we sidestep both by wrapping Fusion. If a
    future refactor reverts this thinking it's cosmetic, these tests fail."""

    def test_proxy_wraps_fusion_not_app_style(self):
        from qtpy import QtWidgets
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        # The proxy's base style metadata identifies it as Fusion. We check
        # objectName because Fusion sets it on construction; falling back to
        # the app style would yield e.g. "windows11" / "windowsvista".
        base = combo.custom_style.baseStyle()
        self.assertEqual(
            base.objectName().lower(),
            "fusion",
            f"CustomStyle must wrap Fusion; got {base.objectName()!r}",
        )

    def test_show_popup_propagates_proxy_style_and_mouse_tracking(self):
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        combo.addItems(["a", "b", "c"])
        combo.show()
        try:
            combo.showPopup()
            view = combo.view()
            self.assertIs(
                view.style(), combo.custom_style,
                "Popup view must share the Fusion-based proxy so item :hover "
                "fires reliably and no native focus border is painted",
            )
            self.assertTrue(
                view.hasMouseTracking(),
                "Popup view must have mouseTracking enabled so QSS "
                "::item:hover triggers on every row, not just clicked ones",
            )
        finally:
            combo.hidePopup()

    def test_current_item_indicator_delegate_installed(self):
        """``SH_ComboBox_Popup == 0`` killed the menu-style checkmark; we
        replace it with a custom delegate that paints a left-edge accent
        strip. Without the delegate, users have no visual cue which row
        is the active selection."""
        from uitk.widgets.comboBox import ComboBox, _CurrentItemIndicatorDelegate

        combo = self.track_widget(ComboBox())
        combo.addItems(["a", "b", "c"])
        combo.show()
        try:
            combo.showPopup()
            self.assertIsInstance(
                combo.view().itemDelegate(), _CurrentItemIndicatorDelegate,
                "Popup view must use the current-item indicator delegate",
            )
        finally:
            combo.hidePopup()


if __name__ == "__main__":
    unittest.main()
