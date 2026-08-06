# !/usr/bin/python
# coding=utf-8
"""Unit tests for DoubleSpinBox widget.

DoubleSpinBox is the float-input widget used by the AttributeWindow factory
(see uitk.bridge.spec._build_float). It has the same
modifier-driven step semantics as SpinBox.

Modifier ladder under test (symmetric: Ctrl scales up, Alt scales down,
stacking amplifies):

    Ctrl          singleStep × 10
    Ctrl+Shift    singleStep × 100
    Alt           singleStep / 10
    Ctrl+Alt      10 ** -decimals          (smallest)

Run standalone: python -m pytest test/test_double_spin_box.py -v
"""

import unittest
from unittest.mock import MagicMock

from conftest import QtBaseTestCase, rendered_text_width, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets


class TestDoubleSpinBoxModifierSteps(QtBaseTestCase):
    """Tests for the symmetric modifier ladder on DoubleSpinBox."""

    def _make_spinbox(self, value=5.0, step=1.0, decimals=4):
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        sb = self.track_widget(DoubleSpinBox())
        sb.setDecimals(decimals)
        sb.setRange(-100, 100)
        sb.setSingleStep(step)
        sb.setValue(value)
        return sb

    def _make_wheel_event(self, delta=120, modifiers=None, axis="y"):
        event = MagicMock()
        if axis == "x":
            event.angleDelta.return_value.x.return_value = delta
            event.angleDelta.return_value.y.return_value = 0
        else:
            event.angleDelta.return_value.x.return_value = 0
            event.angleDelta.return_value.y.return_value = delta
        event.modifiers.return_value = (
            modifiers if modifiers is not None else QtCore.Qt.NoModifier
        )
        return event

    # ---- Ctrl ladder ---------------------------------------------------

    def test_ctrl_wheel_up_steps_by_10x(self):
        sb = self._make_spinbox(value=5.0, step=1.0)
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.ControlModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 15.0, places=5)

    def test_ctrl_wheel_down_steps_by_10x(self):
        sb = self._make_spinbox(value=50.0, step=1.0)
        event = self._make_wheel_event(
            delta=-120, modifiers=QtCore.Qt.ControlModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 40.0, places=5)

    def test_ctrl_shift_wheel_steps_by_100x(self):
        sb = self._make_spinbox(value=5.0, step=1.0)
        sb.setRange(-1000, 1000)  # widen so 5 + 100 doesn't clamp
        event = self._make_wheel_event(
            delta=120,
            modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier,
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 105.0, places=5)

    # ---- Alt = singleStep / 10 (fine) ---------------------------------

    def test_alt_wheel_up_steps_by_singleStep_over_10(self):
        """Alt+wheel up should step by ``singleStep / 10``."""
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.1, places=6)

    def test_alt_wheel_down_steps_by_singleStep_over_10(self):
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=-120, modifiers=QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 4.9, places=6)

    def test_alt_wheel_does_not_mutate_single_step(self):
        """Alt+wheel must step the *value*, not the widget's ``singleStep``
        setting (the original pre-symmetric-ladder behaviour).
        """
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=3)
        before_step = sb.singleStep()
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertEqual(sb.singleStep(), before_step)

    # ---- Ctrl+Alt = 10**-decimals (smallest) --------------------------

    def test_ctrl_alt_wheel_up_steps_by_smallest(self):
        """Ctrl+Alt+wheel up: step by ``10**-decimals`` (smallest)."""
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.0001, places=6)

    def test_ctrl_alt_wheel_down_steps_by_smallest(self):
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=-120, modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 4.9999, places=6)

    def test_ctrl_alt_smaller_than_alt(self):
        """Ladder ordering invariant: ``Ctrl+Alt`` must produce a step
        strictly smaller than ``Alt`` alone for any float spin-box where
        ``singleStep / 10`` exceeds ``10**-decimals``. This is what the
        user actually observes -- adding ``Ctrl`` to ``Alt`` makes the
        gesture *finer*, not the same.
        """
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        # Alt alone
        sb.setValue(5.0)
        event_alt = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event_alt)
        delta_alt = sb.value() - 5.0
        # Ctrl+Alt
        sb.setValue(5.0)
        event_ca = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
        )
        sb.wheelEvent(event_ca)
        delta_ca = sb.value() - 5.0

        self.assertGreater(delta_alt, delta_ca)

    # ---- axis-swap fallback -------------------------------------------

    def test_alt_wheel_reads_x_axis_when_y_is_zero(self):
        """Real-world regression: Alt-held wheel events on some platforms /
        Qt6 builds put the delta on ``angleDelta().x()`` instead of
        ``.y()``. The y-only check that previously gated direction would
        always read 0 and silently no-op.
        """
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=120, modifiers=QtCore.Qt.AltModifier, axis="x"
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.1, places=6)

    def test_ctrl_alt_wheel_reads_x_axis_when_y_is_zero(self):
        sb = self._make_spinbox(value=5.0, step=1.0, decimals=4)
        event = self._make_wheel_event(
            delta=120,
            modifiers=QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier,
            axis="x",
        )
        sb.wheelEvent(event)
        self.assertAlmostEqual(sb.value(), 5.0001, places=6)


class TestDoubleSpinBoxPrefix(QtBaseTestCase):
    def test_prefix_adds_tab(self):
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        sb = self.track_widget(DoubleSpinBox())
        sb.setPrefix("Value:")
        self.assertEqual(sb.prefix(), "Value:\t")


class TestPrefixColumn(QtBaseTestCase):
    """PrefixColumnMixin — the label/value column must not hide the value.

    A tab in a QLineEdit is a *fixed* 80 px stop. On a half-width field (two
    parameters sharing a row) with an option-box icon button beside it, the
    value was laid out past the right edge and scrolled out of view — reading
    as the icon button covering the value (mayatk cut_on_axis Bias / Curve).
    """

    def _make(
        self, prefix="Bias:", value=0.5, decimals=3, rng=(0.0, 1.0), raw_prefix=None
    ):
        """A field in a layout-managed host, started wide — as a panel builds it.

        Deliberately NOT top-level: a top-level widget's size is negotiated with
        the platform window, which the offscreen plugin honors only sometimes —
        a resize silently clamped to the window minimum made these tests pass or
        fail on run order. A child's geometry is Qt's alone. The host carries a
        real **layout** for the same fidelity reason: ``OptionBox.wrap`` treats a
        parent without one as an absolute-positioned overlay and pins the field's
        authored width as a minimum, so a field wrapped there cannot narrow at
        all. It also starts wide, so every ``_set_text_width`` below is a real
        narrowing rather than a no-op resize that fires no event.

        Pass *raw_prefix* to set the prefix through the meta-object **before the
        first layout**, which is exactly what ``QUiLoader`` does.
        """
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        host = self.track_widget(QtWidgets.QWidget())
        host.resize(600, 80)
        layout = QtWidgets.QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        sb = DoubleSpinBox(host)
        sb.setDecimals(decimals)
        sb.setRange(*rng)
        sb.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        if raw_prefix is None:
            sb.setPrefix(prefix)
        else:
            QtWidgets.QDoubleSpinBox.setPrefix(sb, raw_prefix)
        sb.setValue(value)
        layout.addWidget(sb)
        host.show()
        app.processEvents()
        return sb

    @staticmethod
    def _rendered_width(sb):
        """Natural px width of the editor text, tab stops included."""
        return rendered_text_width(sb.lineEdit().text(), sb.font())

    def _set_text_width(self, sb, width):
        """Resize so the editor has *width* px of drawable room."""
        chrome = sb.width() - sb.lineEdit().width()
        sb.setFixedWidth(int(chrome + width))
        app.processEvents()
        # The premise of every width-driven assertion below; a clamped resize
        # would otherwise read as a passing test that measured nothing.
        self.assertEqual(sb.lineEdit().width(), int(width))

    def test_narrow_field_keeps_the_value_visible(self):
        sb = self._make()
        compact = sb.fontMetrics().horizontalAdvance("Bias: 0.5")
        # Wide enough for the compact form, far too narrow for the 80 px stop.
        self._set_text_width(sb, compact + 6)
        self.assertLessEqual(self._rendered_width(sb), sb.lineEdit().width())

    def test_wide_field_keeps_the_aligned_column(self):
        sb = self._make()
        compact = sb.fontMetrics().horizontalAdvance("Bias: 0.5")
        self._set_text_width(sb, compact + 240)
        self.assertTrue(sb.prefix().endswith("\t"))
        self.assertGreater(self._rendered_width(sb), compact)

    def test_column_is_restored_when_the_field_grows_back(self):
        sb = self._make()
        compact = sb.fontMetrics().horizontalAdvance("Bias: 0.5")
        self._set_text_width(sb, compact + 6)
        self.assertFalse(sb.prefix().endswith("\t"))
        self._set_text_width(sb, compact + 240)
        self.assertTrue(sb.prefix().endswith("\t"))

    def test_set_prefix_is_idempotent(self):
        """``pyside6-uic`` replays the stored (already tab-suffixed) string
        through ``setPrefix``; a naive append grew a stop per round-trip."""
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        sb = self.track_widget(DoubleSpinBox())
        sb.setPrefix("Bias:")
        sb.setPrefix(sb.prefix())  # the .ui round-trip
        self.assertEqual(sb.prefix(), "Bias:\t")
        self.assertEqual(sb.prefix_label(), "Bias:")

    def test_ui_authored_prefix_is_adopted_through_the_meta_object(self):
        """QUiLoader applies <property name="prefix"> through the meta-object,
        which reaches the C++ setter and never the Python override — every
        runtime-loaded panel arrives this way, tab already stored."""
        sb = self._make(raw_prefix="Bias:\t")
        compact = sb.fontMetrics().horizontalAdvance("Bias: 0.5")
        self._set_text_width(sb, compact + 6)
        self.assertEqual(sb.prefix_label(), "Bias:")
        self.assertLessEqual(self._rendered_width(sb), sb.lineEdit().width())

    def test_hand_composed_prefix_is_left_verbatim(self):
        """A caller reaching past setPrefix owns the exact string: mayatk's
        curtain panel space-pads a group of labels to a shared width, and
        re-separating that would undo the alignment it computed."""
        sb = self._make(raw_prefix="Bias:     ")
        self._set_text_width(sb, 40)  # narrow enough to force a re-evaluation
        self.assertEqual(sb.prefix(), "Bias:     ")
        self.assertEqual(sb.prefix_label(), "")

    def test_size_hints_do_not_shrink_with_the_displayed_prefix(self):
        """The hints must describe the FULL label, whatever is displayed.

        Qt derives both hints from the prefix string, so a collapsed/elided
        prefix reported a narrower hint, the layout handed the field less
        width, and the narrower field elided further — measured before the fix
        as a half-row field collapsing to its bare value width with the label
        gone and its neighbour absorbing the slack. The label choice must be an
        *output* of the allocated width, never an input to it.
        """
        sb = self._make()
        before = (sb.sizeHint().width(), sb.minimumSizeHint().width())

        compact = sb.fontMetrics().horizontalAdvance("Bias: 0.5")
        self._set_text_width(sb, compact + 6)
        self.assertFalse(sb.prefix().endswith("\t"))  # precondition: collapsed

        # Not-shrinking is the load-bearing half; exact equality isn't
        # guaranteed, since the style can clamp the base hint to its own floor.
        after = (sb.sizeHint().width(), sb.minimumSizeHint().width())
        self.assertGreaterEqual(after[0], before[0])
        self.assertGreaterEqual(after[1], before[1])

    def test_label_choice_does_not_destabilize_the_layout(self):
        """Repeated layout passes over a narrow row must converge."""
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        root = self.track_widget(QtWidgets.QWidget())
        grid = QtWidgets.QGridLayout(root)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setSpacing(1)
        fields = []
        # The real cut_on_axis pair: different labels and ranges, so an
        # unstable hint lets one field starve the other rather than both
        # collapsing evenly.
        specs = (("Bias:", 0.5, 3, (0.0, 1.0)), ("Curve:", 2.0, 2, (0.1, 20.0)))
        for col, (label, value, decimals, rng) in enumerate(specs):
            sb = DoubleSpinBox()
            sb.setDecimals(decimals)
            sb.setRange(*rng)
            sb.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            sb.setPrefix(label)
            sb.setValue(value)
            grid.addWidget(sb, 0, col)
            fields.append(sb)

        root.show()
        root.setFixedWidth(200)  # a half-width row, as cut_on_axis.ui authors it
        app.processEvents()
        settled = [(sb.prefix(), sb.width()) for sb in fields]

        for _ in range(8):  # further layout passes must change nothing
            app.processEvents()
            root.updateGeometry()
            root.layout().activate()
        self.assertEqual([(sb.prefix(), sb.width()) for sb in fields], settled)
        # …and neither field may have been starved by the other: both share one
        # row of two equal columns, so neither can end up a sliver.
        for sb in fields:
            self.assertGreater(sb.width(), root.width() * 0.35)

    def test_special_value_text_is_not_padded_by_the_label(self):
        """``specialValueText`` replaces the whole string, prefix included.

        A hint sized from it carries no prefix contribution, so correcting one
        in would demand width for a label that isn't drawn at the minimum.
        """
        sb = self._make()
        sb.setSpecialValueText("Collapsed Dist:  Auto, and then some more")
        before = sb.sizeHint().width()

        compact = sb.fontMetrics().horizontalAdvance("Bias: 0.5")
        self._set_text_width(sb, compact + 6)
        self.assertFalse(sb.prefix().endswith("\t"))  # precondition: collapsed
        self.assertEqual(sb.sizeHint().width(), before)

    def test_special_value_narrower_than_the_label_cannot_stack_on_it(self):
        """The awkward middle: a special value wider than the *elided* string
        but narrower than the full-label one.

        Only the no-spiral floor is asserted exactly. Qt runs both candidates
        through ``QStyle::sizeFromContents``, whose rounding is not affine, so
        no arithmetic recovers the reference to the pixel here — and a tolerance
        picked to paper over that would be the fudge, not the fix. What must
        hold is that the two widths do not *stack*: the label's width is not
        added on top of a special value that already drives the hint.
        """
        sb = self._make()
        fm = sb.fontMetrics()
        plain = sb.sizeHint().width()  # no special text, full-label reference
        probe = sb._widest_value_text()

        # Squeeze until the label ELIDES — only then is the displayed string
        # strictly narrower than the full-label one, which opens this window.
        self._set_text_width(sb, fm.horizontalAdvance(f"Bias {probe}") // 2)
        shown_w = fm.horizontalAdvance(f"{sb.prefix()}{probe}")
        full_w = fm.horizontalAdvance(f"Bias: {probe}")
        self.assertLess(shown_w, full_w, "precondition: the label must be elided")

        # One character short of the full-label string: narrower than it, wider
        # than the elided one — the awkward middle, not one of the easy cases.
        special = f"Bias: {probe}"[:-1]
        sb.setSpecialValueText(special)
        special_w = fm.horizontalAdvance(special)
        self.assertGreater(special_w, shown_w)
        self.assertLess(special_w, full_w)

        got = sb.sizeHint().width()
        self.assertGreaterEqual(got, plain)  # the floor that prevents the spiral
        # Stacking would land near plain + (special_w - shown_w); the correction
        # must stay far below that.
        self.assertLess(got, plain + (special_w - shown_w))

    def test_empty_prefix_stays_empty(self):
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        sb = self.track_widget(DoubleSpinBox())
        sb.setPrefix("")
        self.assertEqual(sb.prefix(), "")

    def test_option_box_button_does_not_hide_the_value(self):
        """End-to-end: the field the option box leaves behind still shows it."""
        from uitk.widgets.optionBox.utils import OptionBoxManager

        sb = self._make()
        compact = sb.fontMetrics().horizontalAdvance("Bias: 0.5")
        # DoubleSpinBox has no OptionBoxMixin — a live panel reaches the same
        # manager through the autopatched QWidget.option_box property.
        manager = OptionBoxManager(sb)
        manager.set_reset()
        container = manager.container
        self.assertIsNotNone(container)
        app.processEvents()

        # Size the ROW so the FIELD lands just over the compact width. The
        # difference between the two is what the icon button took, which is the
        # whole point: the value has to survive that bite.
        target = compact + 6
        container.setFixedWidth(container.width() - sb.lineEdit().width() + target)
        app.processEvents()
        self.assertEqual(sb.lineEdit().width(), target)  # the resize landed
        self.assertLess(sb.width(), container.width())  # the button took room
        self.assertLessEqual(self._rendered_width(sb), sb.lineEdit().width())


class TestDoubleSpinBoxTextColor(QtBaseTestCase):
    """SpinBoxTextColorMixin.set_text_color — tints the value text (e.g. X/Y/Z)."""

    def _make(self):
        from uitk.widgets.doubleSpinBox import DoubleSpinBox

        return self.track_widget(DoubleSpinBox())

    def test_default_is_unset(self):
        sb = self._make()
        self.assertIsNone(sb.text_color())
        self.assertEqual(sb.styleSheet(), "")

    def test_set_text_color_applies_to_spinbox(self):
        sb = self._make()
        sb.set_text_color("#ff5555")
        self.assertEqual(sb.text_color(), "#ff5555")
        # Applied on the spin box itself — under the theme the QAbstractSpinBox
        # color governs the displayed value, so a line-edit color is overridden.
        self.assertIn("color: #ff5555;", sb.styleSheet())

    def test_clear_with_none_resets_to_theme(self):
        sb = self._make()
        sb.set_text_color("#ff5555")
        sb.set_text_color(None)
        self.assertIsNone(sb.text_color())
        self.assertEqual(sb.styleSheet(), "")

    def test_empty_string_clears(self):
        sb = self._make()
        sb.set_text_color("#ff5555")
        sb.set_text_color("")  # falsy -> treated as clear
        self.assertIsNone(sb.text_color())
        self.assertEqual(sb.styleSheet(), "")

    def test_color_merges_with_existing_inline_style(self):
        # set_text_color must not clobber other inline styling (e.g. option-box
        # border tweaks); changing/clearing the color leaves the rest intact.
        sb = self._make()
        sb.setStyleSheet("border-right-width: 0px;")
        sb.set_text_color("#ff5555")
        self.assertIn("border-right-width: 0px;", sb.styleSheet())
        self.assertIn("color: #ff5555;", sb.styleSheet())
        sb.set_text_color("#00b000")  # change color
        self.assertIn("border-right-width: 0px;", sb.styleSheet())
        self.assertNotIn("#ff5555", sb.styleSheet())
        sb.set_text_color(None)  # clear color
        self.assertEqual(sb.styleSheet().strip(), "border-right-width: 0px;")


if __name__ == "__main__":
    unittest.main()
