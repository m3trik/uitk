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

    def test_strips_focus_on_base_complex_option_without_raising(self):
        """Regression (PySide6): ``drawComplexControl`` receives the option
        statically typed as the base ``QStyleOptionComplex``. The old copy
        (``QStyleOptionComboBox(opt)``) raised ``TypeError: ... called with
        wrong argument types: (QStyleOptionComplex)`` under PySide6 (PySide2
        accepted it), crashing every combobox paint. The flag is now cleared
        in place, which works for either option type."""
        from qtpy import QtWidgets
        from uitk.widgets.comboBox import CustomStyle

        opt = QtWidgets.QStyleOptionComplex()
        opt.state = QtWidgets.QStyle.State_HasFocus | QtWidgets.QStyle.State_Enabled

        prepared = CustomStyle._strip_focus_state_for_combobox(
            QtWidgets.QStyle.CC_ComboBox, opt
        )

        self.assertFalse(
            bool(prepared.state & QtWidgets.QStyle.State_HasFocus),
            "State_HasFocus must be stripped even from a base QStyleOptionComplex",
        )
        self.assertTrue(
            bool(prepared.state & QtWidgets.QStyle.State_Enabled),
            "Other state flags must be preserved",
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


class ComboBoxPopupRowHeight(QtBaseTestCase):
    """Popup rows must equal ``COMBOBOX_ITEM_HEIGHT`` exactly.

    Regression: the token was applied as ``min-height`` while the item rules
    kept 1px top/bottom padding, which Qt adds on top of the content
    min-height — so rows rendered 2px taller than configured (21px vs 19px).
    Vertical item padding is now zero, making the token the true row height.
    """

    def setUp(self):
        super().setUp()
        from uitk.widgets.mixins.style_sheet import StyleSheet

        StyleSheet.reset_overrides()

    def tearDown(self):
        from uitk.widgets.mixins.style_sheet import StyleSheet

        StyleSheet.reset_overrides()
        super().tearDown()

    def _row_height(self, theme="light"):
        from uitk.widgets.comboBox import ComboBox, _CurrentItemIndicatorDelegate
        from uitk.widgets.mixins.style_sheet import StyleSheet

        combo = self.track_widget(ComboBox())
        StyleSheet().set(combo, theme=theme)
        combo.addItems(["a", "b", "c"])
        # Mirror showPopup()'s style + delegate install (offscreen showPopup
        # is flaky); the QSS-driven row height is governed by these alone.
        view = combo.view()
        view.setStyle(combo.custom_style)
        view.setItemDelegate(_CurrentItemIndicatorDelegate(combo))
        return view.sizeHintForRow(0)

    def test_default_row_height_equals_token(self):
        from uitk.widgets.mixins.style_sheet import StyleSheet

        token = int(
            StyleSheet.get_variable("COMBOBOX_ITEM_HEIGHT", theme="light").rstrip("px")
        )
        self.assertEqual(self._row_height("light"), token)

    def test_row_height_tracks_token_without_padding_inflation(self):
        """A custom height well above the font floor must be matched exactly,
        not exceeded by a constant padding offset (the +2px bug)."""
        from uitk.widgets.mixins.style_sheet import StyleSheet

        StyleSheet.set_variable("COMBOBOX_ITEM_HEIGHT", "30px", theme="light")
        self.assertEqual(self._row_height("light"), 30)

    def test_row_height_clamps_down_with_large_font(self):
        """QSS ``min-height`` is only a floor; the delegate must force the row
        height DOWN when the natural row (large UI font / the combobox's icon
        reservation) would exceed the token. Regression: dropdown rows
        rendered taller than ``COMBOBOX_ITEM_HEIGHT``."""
        from qtpy import QtGui, QtWidgets
        from uitk.widgets.mixins.style_sheet import StyleSheet

        app = QtWidgets.QApplication.instance()
        prev_font = app.font()
        big = QtGui.QFont(prev_font)
        big.setPointSize(20)
        app.setFont(big)
        try:
            token = int(
                StyleSheet.get_variable(
                    "COMBOBOX_ITEM_HEIGHT", theme="light"
                ).rstrip("px")
            )
            # The font alone would otherwise produce a taller row.
            self.assertGreater(QtGui.QFontMetrics(big).height(), token)
            self.assertEqual(self._row_height("light"), token)
        finally:
            app.setFont(prev_font)

    def test_explicit_row_size_hint_is_respected(self):
        """A row carrying an explicit ``Qt.SizeHintRole`` (WidgetComboBox rows
        embed a taller widget via ``_apply_uniform_height``) keeps its height;
        the token only governs plain text rows."""
        from qtpy import QtCore, QtWidgets
        from uitk.widgets.comboBox import ComboBox, _CurrentItemIndicatorDelegate
        from uitk.widgets.mixins.style_sheet import StyleSheet

        combo = self.track_widget(ComboBox())
        StyleSheet().set(combo, theme="light")
        combo.addItems(["a", "b"])
        combo.model().item(1).setSizeHint(QtCore.QSize(80, 40))
        deleg = _CurrentItemIndicatorDelegate(combo)
        opt = QtWidgets.QStyleOptionViewItem()
        token = int(
            StyleSheet.get_variable("COMBOBOX_ITEM_HEIGHT", theme="light").rstrip("px")
        )
        self.assertEqual(
            deleg.sizeHint(opt, combo.model().index(1, 0)).height(), 40
        )
        self.assertEqual(
            deleg.sizeHint(opt, combo.model().index(0, 0)).height(), token
        )


class ActivateHostWindowBeforePopup(QtBaseTestCase):
    """``showPopup`` activates a non-active host window first, so the first click
    in the popup selects an item instead of being swallowed activating the window.

    Bug (2026-06-21): combos in option-box / dropdown menus
    (``Qt.Tool | WA_ShowWithoutActivating``) and DCC-hosted panels are commonly
    shown without activation; on Windows the first click into their popup
    re-activated the host window instead of selecting a row — the "I clicked a
    value but nothing happened; I had to re-focus the window / reopen the list"
    symptom. These assert the deterministic product behavior (``activateWindow``
    is / isn't called) rather than the OS focus outcome, which is unreliable under
    the offscreen QPA.
    """

    def _combo_with_fake_window(self, *, active):
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        self.calls = []
        self.fake_window = type(
            "FakeWindow",
            (),
            {
                "isActiveWindow": lambda _self: active,
                "activateWindow": lambda _self: self.calls.append(1),
            },
        )()
        combo.window = lambda: self.fake_window
        return combo

    def test_activates_when_host_inactive(self):
        combo = self._combo_with_fake_window(active=False)
        combo._activate_host_window()
        self.assertEqual(self.calls, [1], "must activate a non-active host window")

    def test_noop_when_host_active(self):
        combo = self._combo_with_fake_window(active=True)
        combo._activate_host_window()
        self.assertEqual(self.calls, [], "must not churn focus when already active")

    def test_no_window_is_safe(self):
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        combo.window = lambda: None
        combo._activate_host_window()  # must not raise


class SetCurrentIndexNegativePreservesBlockState(QtBaseTestCase):
    """``setCurrentIndex(index<0)`` must RESTORE the caller's prior blockSignals
    state, not force-unblock.

    Pre-existing latent bug: the override unconditionally called
    ``blockSignals(False)`` after a negative-index reset, so a header reset nested
    inside an outer ``blockSignals(True)`` (populate / restore batch) silently
    unblocked signals for the rest of that batch — letting transient changes fire
    slots / persist state. The fix mirrors the ``_silenced`` save/restore.
    """

    def _combo(self):
        from uitk.widgets.comboBox import ComboBox

        combo = self.track_widget(ComboBox())
        combo.add(["a", "b"])  # add() is @blockSignals → leaves signals unblocked
        return combo

    def test_preserves_blocked_true(self):
        combo = self._combo()
        combo.blockSignals(True)
        combo.setCurrentIndex(-1)
        self.assertTrue(
            combo.signalsBlocked(), "must preserve the caller's blockSignals(True)"
        )
        combo.blockSignals(False)

    def test_preserves_blocked_false(self):
        combo = self._combo()
        combo.setCurrentIndex(-1)  # prior state is unblocked
        self.assertFalse(combo.signalsBlocked())


class ItemClickCommitsWithinBlockWindow(QtBaseTestCase):
    """A click on a popup row commits even within QComboBox's
    ``blockMouseReleaseTimer`` window (~``doubleClickInterval`` after open).

    Bug (live, option-box combo opened during a marking-menu gesture): the user
    clicks a row fast — within the window where ``QComboBoxPrivateContainer``
    blocks the *selecting* release so the opening click doesn't auto-pick a row.
    The first item click was silently dropped (press registered + row
    highlighted, but no commit; the popup just sat open). Reproduced headlessly:
    open via a real click, then click a row immediately -> ``currentIndex``
    unchanged. ``_PopupItemClickCommitter`` commits a deliberate press+release on
    a valid row, bypassing the timer, while the opening click and drag-select
    still fall through to Qt.
    """

    def _shown_combo(self):
        from qtpy import QtWidgets
        from qtpy.QtTest import QTest
        from uitk.widgets.comboBox import ComboBox

        host = self.track_widget(QtWidgets.QWidget())
        host.resize(300, 200)
        combo = ComboBox(host)
        combo.addItems(["a", "b", "c"])
        combo.move(10, 10)
        combo.resize(120, 24)
        host.show()
        QTest.qWaitForWindowExposed(host)
        combo.setCurrentIndex(0)
        return combo

    def _open(self, combo):
        from qtpy import QtCore, QtWidgets
        from qtpy.QtTest import QTest

        QTest.mouseClick(combo, QtCore.Qt.LeftButton)
        QtWidgets.QApplication.processEvents()
        return combo.view().isVisible()

    def _click_row(self, combo, row):
        from qtpy import QtCore, QtWidgets
        from qtpy.QtTest import QTest

        view = combo.view()
        rect = view.visualRect(combo.model().index(row, 0))
        QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, pos=rect.center())
        QtWidgets.QApplication.processEvents()

    def test_immediate_item_click_commits(self):
        combo = self._shown_combo()
        if not self._open(combo):
            self.skipTest("offscreen QPA did not display the popup")
        fired = []
        combo.activated.connect(fired.append)
        self._click_row(combo, 2)  # no wait -> inside the block-timer window
        self.assertEqual(
            combo.currentIndex(), 2, "a fast item click must still commit"
        )
        self.assertEqual(
            fired, [2], "activated must fire on the bypassed selection"
        )

    def test_opening_click_does_not_autoselect(self):
        """The fix must NOT turn the popup-opening click into a selection — only
        a press AND release that both land on the list commit."""
        combo = self._shown_combo()
        if not self._open(combo):
            self.skipTest("offscreen QPA did not display the popup")
        self.assertEqual(combo.currentIndex(), 0, "opening click must not select")
        self.assertTrue(combo.view().isVisible(), "popup must stay open")

    def test_popup_show_disarms_stale_press(self):
        """A press left armed by a prior popup session (press then drag-off/Esc,
        no release on the list) must be cleared when the popup re-opens, so the
        next *opening* click — whose release lands on the row under the cursor —
        isn't mistaken for a selection."""
        from qtpy import QtCore
        from uitk.widgets.comboBox import ComboBox, _PopupItemClickCommitter

        combo = self.track_widget(ComboBox())
        combo.addItems(["a", "b", "c"])
        committer = _PopupItemClickCommitter(combo)
        committer._armed = True
        committer.eventFilter(None, QtCore.QEvent(QtCore.QEvent.Show))
        self.assertFalse(committer._armed, "popup Show must disarm a stale press")


if __name__ == "__main__":
    unittest.main()
