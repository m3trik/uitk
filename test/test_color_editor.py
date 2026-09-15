"""Unit tests for the colour picker: ColorModel, GradientSlider, ColorEditor.

One file for three modules, deliberately: the model, the slider and the editor
have no independent existence -- a slider is meaningless unbound and the model
exists to be what several widgets share -- so the behaviour worth pinning is
the three of them together, which is the same call ``test_color_mapping_editor``
makes for its editor and dialog.

Run standalone: python test/test_color_editor.py
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from uitk.managers.color_model import ColorModel  # noqa: E402
from uitk.widgets.gradient_slider import STEPS, GradientSlider  # noqa: E402
from uitk.widgets.editors.color_editor import (  # noqa: E402
    ColorEditor,
    ColorEditorPopup,
)

#: hue 0.58, saturation 0.80, value 1.0 -- the blue the 8-bit round-trip was
#: measured on.
BLUE = "#339DFF"
#: A linear emission past 1, which an HDR colour attribute legitimately holds.
HOT = (1.5, 0.75, 0.1)


class TestColorModel(unittest.TestCase):
    """The shared value. Qt-free, so these need no widget."""

    def test_a_colour_round_trips_through_hex(self):
        self.assertEqual(ColorModel(BLUE).hex, BLUE)

    def test_value_dragged_to_black_and_back_keeps_the_colour(self):
        """The defect the float-HSV store exists to prevent. An 8-bit store
        returns WHITE here, because rgb states no hue at black."""
        m = ColorModel(BLUE)
        m.set_hsv(v=0.0)
        self.assertEqual(m.hex, "#000000")
        m.set_hsv(v=1.0)
        self.assertEqual(m.hex, BLUE)

    def test_the_authored_hue_survives_black(self):
        m = ColorModel(BLUE)
        authored = m.hue
        m.set_hsv(v=0.0)
        self.assertAlmostEqual(m.hue, authored, places=6)
        self.assertGreater(m.saturation, 0.0)

    def test_setting_rgb_black_does_not_erase_the_hue(self):
        """The same guarantee through the rgb door, which a red/green/blue
        slider dragged to zero goes through."""
        m = ColorModel(BLUE)
        authored = m.hue
        m.set_rgbf(0.0, 0.0, 0.0)
        self.assertAlmostEqual(m.hue, authored, places=6)

    def test_a_deliberate_grey_does_clear_saturation(self):
        """Distinct from black: grey states that saturation really is zero."""
        m = ColorModel(BLUE)
        m.set_rgbf(0.5, 0.5, 0.5)
        self.assertEqual(m.saturation, 0.0)

    def test_partial_writes_leave_the_other_components_alone(self):
        m = ColorModel(BLUE)
        h, s, _v, a = m.hsva
        m.set_hsv(v=0.3)
        self.assertEqual(m.hsva, (h, s, 0.3, a))

    def test_subscribers_are_notified_once_per_change(self):
        m = ColorModel(BLUE)
        calls = []
        m.subscribe(lambda: calls.append(1))
        m.set_hsv(v=0.5)
        m.set_hsv(v=0.5)  # no change -- must not notify
        self.assertEqual(len(calls), 1)

    def test_muted_coalesces_a_block_into_one_notification(self):
        m = ColorModel(BLUE)
        calls = []
        m.subscribe(lambda: calls.append(1))
        with m.muted():
            m.set_hsv(h=0.1)
            m.set_hsv(s=0.2)
        self.assertEqual(len(calls), 1)

    def test_a_failing_subscriber_does_not_break_the_others(self):
        m = ColorModel(BLUE)
        calls = []

        def boom():
            raise RuntimeError("presenter is broken")

        m.subscribe(boom)
        m.subscribe(lambda: calls.append(1))
        m.set_hsv(v=0.5)
        self.assertEqual(calls, [1])

    def test_mixed_seeds_and_clears_on_the_first_edit(self):
        m = ColorModel(BLUE, mixed=True)
        self.assertTrue(m.mixed)
        self.assertEqual(m.hex, BLUE, "a mixed model still carries a seed")
        m.set_hsv(v=0.5)
        self.assertFalse(m.mixed)

    def test_to_rgbaf_reads_every_shape_this_package_passes_around(self):
        cases = {
            "#FF0000": (1.0, 0.0, 0.0, 1.0),
            (1.0, 0.0, 0.0): (1.0, 0.0, 0.0, 1.0),
            (255, 0, 0): (1.0, 0.0, 0.0, 1.0),
            (255, 0, 0, 255): (1.0, 0.0, 0.0, 1.0),
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                got = ColorModel.to_rgbaf(value)
                self.assertEqual(tuple(round(c, 4) for c in got), expected)

    def test_to_rgbaf_declines_rather_than_inventing_a_colour(self):
        for bad in (None, "not a colour", (1, 2), object()):
            with self.subTest(bad=bad):
                self.assertIsNone(ColorModel.to_rgbaf(bad))


class TestGradientSlider(QtBaseTestCase):
    """The slider reads and writes the model, and states its own track."""

    def test_the_handle_starts_where_the_model_is(self):
        m = ColorModel(BLUE)
        slider = self.track_widget(GradientSlider(channel="value", model=m))
        self.assertEqual(slider.value(), STEPS)

    def test_dragging_writes_only_its_own_channel(self):
        m = ColorModel(BLUE)
        h, s, _v, a = m.hsva
        slider = self.track_widget(GradientSlider(channel="value", model=m))
        slider.setValue(STEPS // 2)
        self.assertAlmostEqual(m.value, 0.5, places=2)
        self.assertEqual((m.hue, m.saturation, m.alpha), (h, s, a))

    def test_sliders_sharing_a_model_follow_each_other(self):
        """The point of binding to a model instead of to each other."""
        m = ColorModel(BLUE)
        value = self.track_widget(GradientSlider(channel="value", model=m))
        red = self.track_widget(GradientSlider(channel="red", model=m))
        value.setValue(STEPS // 4)
        self.assertLess(red.value(), STEPS)

    def test_the_track_is_a_stylesheet_gradient_not_a_paint(self):
        """So the themed groove and page rules are overridden rather than
        fought; a paintEvent cannot see them."""
        m = ColorModel(BLUE)
        slider = self.track_widget(GradientSlider(channel="hue", model=m))
        qss = slider.styleSheet()
        self.assertIn("qlineargradient", qss)
        self.assertIn('[class="GradientSlider"]::groove', qss)
        self.assertIn("::sub-page", qss)
        self.assertIn("transparent", qss)

    def test_the_hue_track_states_a_full_turn(self):
        m = ColorModel(BLUE)
        slider = self.track_widget(GradientSlider(channel="hue", model=m))
        stops = slider._gradient_stops()
        self.assertEqual(len(stops), 7, "six segments need seven stops")
        self.assertEqual(stops[0][0], 0.0)
        self.assertEqual(stops[-1][0], 1.0)

    def test_the_saturation_track_is_drawn_at_the_models_own_hue(self):
        m = ColorModel(BLUE)
        slider = self.track_widget(GradientSlider(channel="saturation", model=m))
        _at, full = slider._gradient_stops()[-1]
        self.assertGreater(full[2], full[0], "the saturated end must read blue")

    def test_an_unknown_channel_is_refused(self):
        with self.assertRaises(ValueError):
            GradientSlider(channel="chroma")

    def test_the_track_does_not_re_trigger_its_own_refresh(self):
        """Regression: ``refresh`` sets the stylesheet, a stylesheet raises a
        StyleChange, and StyleChange queues a refresh -- so a guard that did
        not span the stylesheet write made this schedule itself forever.
        Measured before the fix: 5707 refreshes in 400 ms of an IDLE loop, one
        core pegged the whole time a picker was on screen. It needs a SPINNING
        event loop to show, which is why every other case here missed it."""
        from qtpy import QtCore

        m = ColorModel(BLUE)
        slider = self.track_widget(GradientSlider(channel="value", model=m))
        calls = []
        real = slider.refresh
        slider.refresh = lambda: (calls.append(1), real())

        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(250, loop.quit)
        loop.exec_() if hasattr(loop, "exec_") else loop.exec()

        self.assertEqual(calls, [], "an idle picker must cost nothing")

    def test_a_track_is_not_repolished_when_it_did_not_change(self):
        """Every model change refreshes every bound slider, and a stylesheet
        write forces a style re-polish. Nothing in the H/S/V or RGB tracks
        depends on ALPHA, so an alpha drag used to re-polish all of them once
        per frame for no visible difference."""
        m = ColorModel(BLUE)
        sliders = {
            name: self.track_widget(GradientSlider(channel=name, model=m))
            for name in ("hue", "saturation", "value", "red")
        }
        counts = dict.fromkeys(sliders, 0)
        for name, slider in sliders.items():
            real = slider.setStyleSheet

            def counted(qss, _n=name, _r=real):
                counts[_n] += 1
                _r(qss)

            slider.setStyleSheet = counted

        for step in range(20):
            m.set_hsv(a=step / 20.0)

        self.assertEqual(sum(counts.values()), 0, counts)

    def test_an_external_restyle_still_repairs_the_track(self):
        """The other half of the pair: the loop fix must not cost the repair
        the queued refresh exists for."""
        from qtpy import QtCore

        m = ColorModel(BLUE)
        slider = self.track_widget(GradientSlider(channel="hue", model=m))
        slider.setStyleSheet("")

        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(150, loop.quit)
        loop.exec_() if hasattr(loop, "exec_") else loop.exec()

        self.assertIn("qlineargradient", slider.styleSheet())


class TestColorEditor(QtBaseTestCase):
    """The editor composes sections over one model."""

    def test_the_default_sections_are_built(self):
        editor = self.track_widget(ColorEditor(color=BLUE))
        for name in ColorEditor.DEFAULT_SECTIONS:
            self.assertIsNotNone(editor.section(name), name)

    def test_advanced_sections_are_hidden_until_asked_for(self):
        editor = self.track_widget(ColorEditor(color=BLUE))
        self.assertTrue(editor._advanced_box.isHidden())
        editor._disclosure.setChecked(True)
        self.assertFalse(editor._advanced_box.isHidden())

    def test_an_empty_advanced_list_removes_the_disclosure(self):
        editor = self.track_widget(ColorEditor(color=BLUE, advanced=()))
        self.assertFalse(hasattr(editor, "_disclosure"))

    def test_the_disclosure_is_a_titled_section_rule(self):
        """Not a "More" button: the advanced rows open under a section header
        with a chevron, the way every other uitk section is captioned."""
        from uitk.widgets.separator import Separator

        editor = self.track_widget(ColorEditor(color=BLUE))
        self.assertIsInstance(editor._disclosure, Separator)
        self.assertEqual(editor._disclosure.title, ColorEditor.ADVANCED_TITLE)
        self.assertTrue(editor._disclosure.isCheckable())
        self.assertFalse(editor._disclosure.isChecked(), "closed until asked")

    def test_a_section_can_be_registered_without_editing_the_class(self):
        """The extension point: a consumer names its own row."""
        from qtpy import QtWidgets

        marker = {}

        def factory(editor):
            marker["editor"] = editor
            return QtWidgets.QLabel("custom", editor)

        ColorEditor.register_section("test_custom", factory)
        try:
            editor = self.track_widget(
                ColorEditor(color=BLUE, sections=("test_custom",), advanced=())
            )
            self.assertIs(marker["editor"], editor)
            self.assertIsNotNone(editor.section("test_custom"))
        finally:
            ColorEditor.SECTIONS.pop("test_custom", None)

    def test_an_unknown_section_warns_rather_than_vanishing(self):
        with self.assertWarns(RuntimeWarning):
            self.track_widget(
                ColorEditor(color=BLUE, sections=("no_such_section",), advanced=())
            )

    def test_dragging_a_slider_emits_the_live_signal(self):
        editor = self.track_widget(ColorEditor(color=BLUE, advanced=()))
        seen = []
        editor.colorChanged.connect(lambda c: seen.append(c.name()))
        editor._sliders[0].setValue(0)
        self.assertTrue(seen)

    def test_the_hex_field_writes_a_parseable_value(self):
        editor = self.track_widget(ColorEditor(color=BLUE, advanced=()))
        field = editor.section("hex")
        field.setText("#FF8800")
        field._commit()
        self.assertEqual(editor.color.hex, "#FF8800")

    def test_the_hex_field_restores_itself_on_an_unparseable_value(self):
        """Typing a partial value is normal; it must not become the colour."""
        editor = self.track_widget(ColorEditor(color=BLUE, advanced=()))
        field = editor.section("hex")
        field.setText("#GG")
        field._commit()
        self.assertEqual(editor.color.hex, BLUE)
        self.assertEqual(field.text(), BLUE)

    def test_a_mixed_editor_shows_no_value(self):
        editor = self.track_widget(ColorEditor(color=BLUE, advanced=()))
        editor.set_mixed(True)
        self.assertEqual(editor.section("hex").text(), "")
        self.assertEqual(editor.section("hex").placeholderText(), "mixed")

    def test_two_editors_sharing_a_model_edit_one_colour(self):
        model = ColorModel(BLUE)
        a = self.track_widget(ColorEditor(model=model, advanced=()))
        b = self.track_widget(ColorEditor(model=model, advanced=()))
        a._sliders[0].setValue(0)
        self.assertEqual(a.color.hex, b.color.hex)

    def test_two_editors_with_their_own_models_are_independent(self):
        """Which is what makes them the two ends of one ramp."""
        a = self.track_widget(ColorEditor(color=BLUE, advanced=()))
        b = self.track_widget(ColorEditor(color="#000000", advanced=()))
        a._sliders[0].setValue(0)
        self.assertEqual(b.color.hex, "#000000")

    def test_the_popup_answers_the_colour_on_screen(self):
        popup = self.track_widget(ColorEditorPopup(color=BLUE, advanced=()))
        self.assertEqual(popup.color.hex, BLUE)
        popup.editor.model.set_hsv(v=0.5)
        self.assertEqual(popup.qcolor().name().upper(), popup.color.hex[:7])

    def test_escape_reverts_the_popup_to_the_colour_it_opened_on(self):
        """A live picker has no OK button, so clicking away accepts. Escape is
        the only way back out of an experiment -- the dialog this replaced had
        it as Cancel, and losing it silently would be a regression."""
        from qtpy import QtCore, QtGui

        popup = self.track_widget(ColorEditorPopup(color=BLUE, advanced=()))
        popup.editor.model.set_hsv(v=0.2)
        self.assertNotEqual(popup.color.hex, BLUE)
        popup.keyPressEvent(
            QtGui.QKeyEvent(
                QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier
            )
        )
        self.assertEqual(popup.color.hex, BLUE)

    def test_dismissing_without_escape_keeps_the_edit(self):
        """The other half of the pair: clicking away is the accept path, so a
        close that is not Escape must NOT revert."""
        popup = self.track_widget(ColorEditorPopup(color=BLUE, advanced=()))
        popup.editor.model.set_hsv(v=0.2)
        edited = popup.color.hex
        popup.close()
        self.assertEqual(popup.color.hex, edited)

    # -- what get_color answers ---------------------------------------------

    @staticmethod
    def _escape(popup):
        from qtpy import QtCore, QtGui

        popup.keyPressEvent(
            QtGui.QKeyEvent(
                QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier
            )
        )

    def _answer(self, gesture, parent=None):
        """What ``get_color`` answers when *gesture* is all the user does."""
        from unittest import mock

        def run(popup):
            gesture(popup)
            return 0

        with mock.patch.object(ColorEditorPopup, "exec_", run, create=True):
            return ColorEditorPopup.get_color(BLUE, parent=parent, advanced=())

    def test_get_color_answers_none_for_an_escaped_pick(self):
        """Escape reverts, so there is nothing to write. Answering the opening
        colour made a caller that writes on an answer write it anyway: a
        cancelled marker pick emitted ``marker_changed``, which dirties a
        DCC's shot store."""

        def edit_then_escape(popup):
            popup.editor.model.set_hsv(v=0.2)
            self._escape(popup)

        self.assertIsNone(self._answer(edit_then_escape))

    def test_get_color_answers_none_when_closed_on_the_opening_colour(self):
        self.assertIsNone(self._answer(lambda popup: None))

    def test_get_color_answers_the_colour_that_was_picked(self):
        picked = self._answer(lambda popup: popup.editor.model.set_hsv(v=0.2))
        self.assertIsNotNone(picked)
        self.assertNotEqual(picked.name().upper(), BLUE)

    def test_get_color_leaves_no_popup_behind(self):
        """A popup parented to the caller outlives the pick, hidden, one per
        call -- unless it is deleted."""
        from qtpy import QtCore, QtWidgets

        host = self.track_widget(QtWidgets.QWidget())
        self._answer(lambda popup: None, parent=host)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertEqual(host.findChildren(ColorEditorPopup), [])

    # -- what commits -------------------------------------------------------

    @staticmethod
    def _commits(editor):
        seen = []
        editor.colorCommitted.connect(lambda c: seen.append(c.name().upper()))
        return seen

    def test_a_key_or_wheel_step_commits_the_colour_it_lands_on(self):
        """Regression: only a released drag committed, and a key, wheel or
        groove step sends no release -- so a consumer that writes on commit
        never saw those edits. The commit follows the landed value: Qt emits
        ``actionTriggered`` BEFORE a step is applied, so a commit there would
        hand out the colour being left."""
        from qtpy import QtCore, QtGui, QtWidgets

        editor = self.track_widget(ColorEditor(color=BLUE, advanced=()))
        slider = editor.findChild(GradientSlider, "slider_value")
        seen = self._commits(editor)
        QtWidgets.QApplication.sendEvent(
            slider,
            QtGui.QKeyEvent(
                QtCore.QEvent.KeyPress, QtCore.Qt.Key_Left, QtCore.Qt.NoModifier
            ),
        )
        self.assertEqual(seen, [editor.color.hex], "one commit, of the new colour")
        self.assertNotEqual(seen[0], BLUE)
        QtWidgets.QApplication.sendEvent(
            slider,
            QtGui.QWheelEvent(
                QtCore.QPointF(5, 5),
                QtCore.QPointF(5, 5),
                QtCore.QPoint(0, 0),
                QtCore.QPoint(0, -120),
                QtCore.Qt.NoButton,
                QtCore.Qt.NoModifier,
                QtCore.Qt.NoScrollPhase,
                False,
            ),
        )
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[-1], editor.color.hex)

    def test_a_drag_commits_once_on_release_and_a_model_change_never(self):
        editor = self.track_widget(ColorEditor(color=BLUE, advanced=()))
        slider = editor.findChild(GradientSlider, "slider_value")
        seen = self._commits(editor)
        slider.setSliderDown(True)
        slider.setSliderPosition(500)
        slider.setSliderPosition(400)
        self.assertEqual(seen, [], "nothing mid-drag")
        slider.setSliderDown(False)
        self.assertEqual(seen, [editor.color.hex])
        editor.model.set_hsv(v=0.9)
        self.assertEqual(len(seen), 1, "a value set on the model is not an edit")


class TestColorRampEditor(QtBaseTestCase):
    """Several ends of one ramp, and which of them a commit speaks for."""

    def _ramp(self):
        from uitk.widgets.editors.color_editor import ColorRampEditor

        return self.track_widget(ColorRampEditor(colors=(BLUE, "#000000"), advanced=()))

    def test_each_end_holds_its_own_colour(self):
        ramp = self._ramp()
        self.assertEqual([c.hex for c in ramp.colors], [BLUE, "#000000"])

    def test_editing_one_end_leaves_the_other(self):
        ramp = self._ramp()
        ramp.editor("Dim").model.set_color("#400000")
        self.assertEqual([c.hex for c in ramp.colors], [BLUE, "#400000"])

    def test_set_colors_treats_none_as_leave_alone(self):
        """``None`` is what an object that never authored an end reads as;
        overwriting it with a default would turn unstated into a choice."""
        ramp = self._ramp()
        ramp.set_colors((None, "#00FF00"))
        self.assertEqual([c.hex for c in ramp.colors], [BLUE, "#00FF00"])

    def test_a_commit_names_the_end_it_speaks_for(self):
        """Regression: a consumer that WRITES on commit had only the pair to
        go on, so a nudge to Bright pushed the untouched Dim through as well --
        silently overwriting an authored colour with the seeded default."""
        ramp = self._ramp()
        seen = []
        ramp.stopCommitted.connect(lambda i, c: seen.append((i, c.name().upper())))
        ramp.editor(0).colorCommitted.emit(ramp.editor(0).qcolor())
        self.assertEqual(seen, [(0, BLUE)])

    def test_the_pair_signal_still_carries_every_end(self):
        ramp = self._ramp()
        seen = []
        ramp.colorsCommitted.connect(lambda t: seen.append(len(t)))
        ramp.editor(1).colorCommitted.emit(ramp.editor(1).qcolor())
        self.assertEqual(seen, [2])

    def test_the_low_end_sits_left_of_the_high_end(self):
        """A ramp is read from its low end, so Dim is drawn left of Bright --
        while indices, labels and decided() keep ColorStops order (high first)."""
        ramp = self._ramp()
        ramp.show()
        ramp.layout().activate()
        self.assertLess(ramp.editor("Dim").x(), ramp.editor("Bright").x())
        self.assertEqual(ramp.labels, ("Bright", "Dim"))
        self.assertEqual([c.hex for c in ramp.colors], [BLUE, "#000000"])

    def test_a_linear_ramp_shows_values_encoded_and_hands_them_back_linear(self):
        """The channel is linear (an attribute, a glTF factor); the swatch is a
        display colour. Live report (2026-09-13): the option box showed the
        raw numbers, so the WebXR page -- which encodes them -- read brighter."""
        from uitk.widgets.editors.color_editor import ColorRampEditor

        grey = (0.3, 0.3, 0.3)  # linear; a page shows it at about 58%
        ramp = self.track_widget(
            ColorRampEditor(colors=(grey, (0.0, 0.0, 0.0)), advanced=(), linear=True)
        )
        self.assertEqual(ramp.editor("Bright").color.hex, "#959595")
        bright, dim = ramp.decided()
        self.assertEqual([round(c, 2) for c in bright], [0.3, 0.3, 0.3])
        self.assertEqual(dim, (0.0, 0.0, 0.0))
        ramp.set_colors(((1.0, 1.0, 1.0), None))
        self.assertEqual(ramp.editor("Bright").color.hex, "#FFFFFF")
        self.assertEqual(ramp.editor("Dim").color.hex, "#000000", "None leaves it")

    def test_an_additive_swatch_paints_the_board_under_nothing(self):
        """Black is not a colour an additive channel can produce; a dim end at
        nothing shows the transparency board, not a black surface."""
        editor = self.track_widget(
            ColorEditor(color="#000000", additive=True, advanced=())
        )
        swatch = editor.section("swatch")
        swatch.resize(60, 22)
        swatch.show()
        swatch.grab()  # raises if paintEvent does
        self.assertIsNotNone(swatch._checker, "the board was painted")
        plain = self.track_widget(ColorEditor(color="#000000", advanced=()))
        plain.section("swatch").grab()
        self.assertIsNone(plain.section("swatch")._checker, "a colour paints flat")

    def test_an_over_range_linear_end_is_shown_bright_not_black(self):
        """Read as bytes (anything over 1 is, to ``to_rgbaf``), a linear
        ``(1.5, 0.75, 0.1)`` became about ``(0.006, 0.003, 0.0004)`` and showed
        near-black -- and a Revise writing it back flattened every target."""
        from uitk.widgets.editors.color_editor import ColorRampEditor

        ramp = self.track_widget(
            ColorRampEditor(colors=(HOT, (0.0, 0.0, 0.0)), advanced=(), linear=True)
        )
        self.assertAlmostEqual(ramp.editor("Bright").model.value, 1.0, places=3)

    def test_an_end_nobody_edited_is_handed_back_as_authored(self):
        """Clamped to SHOW, never to write: an untouched over-range end must not
        come back from ``decided()`` clamped, or revising the other end
        flattens this one. The preview runs the value the writer reads."""
        from uitk.widgets.editors.color_editor import ColorRampEditor

        ramp = self.track_widget(
            ColorRampEditor(advanced=(), linear=True, preview=True)
        )
        ramp.set_colors((HOT, (0.0, 0.0, 0.0)))
        ramp.editor("Dim").model.set_hsv(v=0.5)  # revise the OTHER end
        self.assertEqual(ramp.decided()[0], HOT)
        self.assertEqual(ramp.preview._stops[0], HOT)
        ramp.editor("Bright").model.set_hsv(v=0.5)
        self.assertLessEqual(max(ramp.decided()[0]), 1.0, "an edit is what was picked")


class TestRampPreview(QtBaseTestCase):
    """The preview must BE the deliverable's value, not resemble it."""

    def _preview(self, **kw):
        from uitk.widgets.editors.color_editor import RampPreview

        kw.setdefault("stops", [(0.2, 0.5, 1.0), (0.4, 0.0, 0.0)])
        kw.setdefault("period", 2.0)
        kw.setdefault("duty", 0.5)
        return self.track_widget(RampPreview(**kw))

    def test_the_composite_matches_the_exporters_own_function(self):
        """The whole case for a flat 2D fill over a shaded 3D one: this is not
        an approximation of what ships, it is the arithmetic that ships."""
        from pythontk.file_utils.mesh_convert.glb_fades import CHANNELS

        preview = self._preview()
        spec = CHANNELS["highlight"]
        stops = spec.color_stops.resolve([(0.2, 0.5, 1.0), (0.4, 0.0, 0.0)])
        for sample in (0.0, 0.25, 0.5, 0.75, 1.0):
            with self.subTest(sample=sample):
                self.assertEqual(
                    [round(c, 6) for c in preview.composite(sample)],
                    [round(c, 6) for c in spec.values([0.0, 0.0, 0.0], sample, stops)],
                )

    def test_the_waveform_holds_at_both_ends_and_repeats(self):
        preview = self._preview()
        self.assertEqual(preview.sample(0.0), 1.0, "opens on the bright hold")
        self.assertEqual(preview.sample(1.5), 0.0, "reaches the dim hold")
        self.assertEqual(preview.sample(0.3), preview.sample(2.3), "one period on")

    def test_it_composes_over_the_materials_own_emissive(self):
        preview = self._preview()
        preview.set_base((0.1, 0.0, 0.0))
        self.assertEqual([round(c, 3) for c in preview.composite(0.0)], [0.5, 0.0, 0.0])

    def test_a_linear_additive_preview_paints_brightness_as_alpha(self):
        """What is PAINTED, next to what is composed: the composite stays the
        exporter's linear number; the paint encodes it and, for light added
        over an object, spends the brightness as alpha over the board."""
        grey = (0.214, 0.214, 0.214)  # linear mid grey
        preview = self._preview(
            stops=[grey, (0.0, 0.0, 0.0)], linear=True, additive=True
        )
        self.assertEqual([round(c, 3) for c in preview.composite(1.0)], [0.214] * 3)
        r, g, b, a = preview.display(1.0)
        self.assertEqual(
            [round(c, 2) for c in (r, g, b)], [1.0, 1.0, 1.0], "the hue, full"
        )
        self.assertAlmostEqual(a, 0.5, places=2, msg="half the light, half the alpha")
        self.assertEqual(preview.display(0.0)[3], 0.0, "no glow shows only the board")
        plain = self._preview(stops=[grey, (0.0, 0.0, 0.0)])
        self.assertEqual([round(c, 3) for c in plain.display(1.0)], [0.214] * 3 + [1.0])

    def test_a_hidden_preview_runs_no_timer(self):
        """An animation behind a closed option box is a timer nobody asked
        for -- and this one repaints 30 times a second."""
        preview = self._preview()
        preview.show()
        self.assertTrue(preview._timer.isActive())
        preview.hide()
        self.assertFalse(preview._timer.isActive())

    def test_a_preview_whose_HOST_closes_runs_no_timer(self):
        """The preview lives in an option-box popup now, not in a dialog that
        is destroyed on close -- so the case that matters is the parent being
        hidden, which does NOT call the child's ``hide()``. Qt propagates Show
        and Hide down, so the timer stops and restarts on its own; this pins
        that, because a 30 FPS repaint left running per popup open is exactly
        the idle burn this module has already paid for once."""
        from qtpy import QtWidgets

        host = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(host)
        preview = self._preview()
        layout.addWidget(preview)

        host.show()
        self.assertTrue(preview._timer.isActive(), "an open popup animates")
        host.hide()
        self.assertFalse(preview._timer.isActive(), "a closed popup must not")
        host.show()
        self.assertTrue(preview._timer.isActive(), "and it comes back")

    def test_editing_a_stop_reaches_the_preview(self):
        from uitk.widgets.editors.color_editor import ColorRampEditor

        ramp = self.track_widget(
            ColorRampEditor(colors=(BLUE, "#000000"), preview=True, advanced=())
        )
        ramp.editor("Bright").model.set_color("#FF0000")
        self.assertEqual(
            [round(c, 3) for c in ramp.preview.composite(1.0)], [1.0, 0.0, 0.0]
        )


class TestFadeWaveform(QtBaseTestCase):
    """A two-key fade: one linear ramp between two holds."""

    def _wave(self, **kw):
        from uitk.widgets.editors.color_editor import FadeWaveform

        kw.setdefault("duration", 1.0)
        kw.setdefault("hold", 0.5)
        return FadeWaveform(**kw)

    def test_it_holds_at_both_ends_of_the_ramp(self):
        """Regression: the period counted ONE hold, so the destination hold had
        zero length and a fade-in never showed the state it fades in TO."""
        wave = self._wave(direction="in")
        self.assertEqual(wave.period, 2.0, "hold + ramp + hold")
        self.assertEqual(wave(0.0), 0.0, "held at the origin")
        self.assertAlmostEqual(wave(1.0), 0.5, places=3, msg="halfway up")
        self.assertEqual(wave(1.9), 1.0, "held at the destination")

    def test_out_is_the_same_shape_inverted(self):
        wave = self._wave(direction="out")
        self.assertEqual(wave(0.0), 1.0)
        self.assertAlmostEqual(wave(1.0), 0.5, places=3)
        self.assertEqual(wave(1.9), 0.0)

    def test_auto_ramps_both_ways(self):
        """Auto resolves per object from that object's last key, so a preview
        that picked one direction would claim to know what it has not read."""
        wave = self._wave(direction="auto")
        self.assertEqual(wave.period, 3.0, "two holds and two ramps")
        self.assertEqual(wave(0.0), 0.0)
        self.assertEqual(wave(1.5), 1.0, "up, then held")
        self.assertLess(wave(2.9), 0.2, "and back down")

    def test_the_ramp_is_linear(self):
        """The keyer writes linear tangents; a curve here would show a shape
        the deliverable does not have."""
        wave = self._wave(direction="in")
        quarter, half, three = wave(0.75), wave(1.0), wave(1.25)
        self.assertAlmostEqual(half - quarter, three - half, places=6)

    def test_an_unknown_direction_reads_as_auto(self):
        """It is driven by a combo box, and a preview must never be what stops
        an option box from building."""
        self.assertEqual(self._wave(direction="sideways").shape["direction"], "auto")

    def test_the_shape_round_trips_through_set_shape(self):
        wave = self._wave()
        wave.set_shape(duration=2.0, hold=0.25, direction="out")
        self.assertEqual(
            wave.shape, {"duration": 2.0, "hold": 0.25, "direction": "out"}
        )


class TestInjectedChannelArithmetic(QtBaseTestCase):
    """The preview runs the channel's OWN function, so it cannot drift."""

    def _preview(self, channel, **kw):
        from pythontk.file_utils.mesh_convert.glb_fades import CHANNELS
        from uitk.widgets.editors.color_editor import RampPreview

        spec = CHANNELS[channel]
        return spec, self.track_widget(RampPreview(values=spec.values, **kw))

    def test_the_fade_is_alpha_on_the_fourth_lane(self):
        """What ships for opacity is the material's own RGB with alpha set to
        the sample -- four components, which is also what tells the widget to
        draw a transparency board rather than an opaque fill."""
        spec, preview = self._preview("opacity")
        preview.set_base((0.8, 0.8, 0.85))
        for sample in (0.0, 0.4, 1.0):
            with self.subTest(sample=sample):
                self.assertEqual(
                    [round(c, 6) for c in preview.composite(sample)],
                    [round(c, 6) for c in spec.values([0.8, 0.8, 0.85], sample, ())],
                )
        self.assertEqual(len(preview.composite(0.5)), 4)

    def test_the_pulse_is_three_components(self):
        spec, preview = self._preview("highlight")
        preview.set_stops([(0.2, 0.5, 1.0), (0.0, 0.0, 0.0)])
        stops = spec.color_stops.resolve([(0.2, 0.5, 1.0), (0.0, 0.0, 0.0)])
        self.assertEqual(
            [round(c, 6) for c in preview.composite(0.6)],
            [round(c, 6) for c in spec.values([0.0, 0.0, 0.0], 0.6, stops)],
        )
        self.assertEqual(len(preview.composite(0.5)), 3)

    def test_an_alpha_preview_actually_paints_its_board(self):
        """Painted, not inspected. The transparency helper was first written
        onto the wrong class -- every attribute check still passed and the
        widget raised only when Qt asked it to paint.

        The board is asserted through its cache rather than by sampling
        pixels: what is on screen depends where in the cycle the clock is, and
        a fully opaque frame legitimately covers the board.
        """
        _spec, preview = self._preview("opacity")
        self.assertIsNone(preview._checker, "nothing is built before a paint")
        preview.set_base((0.78, 0.80, 0.84))
        preview.resize(200, 46)
        preview.show()

        image = preview.grab().toImage()  # raises if paintEvent does

        self.assertEqual(image.width(), 200, "the widget painted at all")
        self.assertIsNotNone(
            preview._checker, "four components must be drawn over a board"
        )

    def test_an_opaque_preview_draws_no_board(self):
        """Three components are a colour, not a transparency."""
        _spec, preview = self._preview("highlight")
        preview.resize(200, 46)
        preview.show()
        preview.grab()

        self.assertIsNone(preview._checker)

    def test_the_board_belongs_to_the_preview_that_built_it(self):
        """Held per instance, not on the class: a QPixmap belongs to the
        QApplication that was running when it was built, and one cached on the
        class outlives that app."""
        _spec, one = self._preview("opacity")
        _spec, two = self._preview("opacity")
        for widget in (one, two):
            widget.resize(40, 20)
            widget.show()
        one.grab()

        self.assertIsNotNone(one._checker)
        self.assertIsNone(two._checker, "a sibling must not inherit the board")

    def test_a_ramp_editor_hands_its_arithmetic_to_both_previews(self):
        """Or the before/after compares two different channels."""
        from pythontk.file_utils.mesh_convert.glb_fades import CHANNELS
        from uitk.widgets.editors.color_editor import ColorRampEditor

        values = CHANNELS["highlight"].values
        ramp = self.track_widget(
            ColorRampEditor(preview=True, advanced=(), values=values)
        )
        self.assertEqual(ramp.preview._values, values)
        self.assertEqual(ramp.reference._values, values)


class TestComparisonPreview(QtBaseTestCase):
    """The before/after: what is being replaced, held up beside what replaces it."""

    def _ramp(self, **kw):
        from uitk.widgets.editors.color_editor import ColorRampEditor

        kw.setdefault("colors", (BLUE, "#400000"))
        kw.setdefault("advanced", ())
        kw.setdefault("preview", True)
        return self.track_widget(ColorRampEditor(**kw))

    def test_there_is_no_before_until_one_is_given(self):
        """On its own the live preview is simply THE preview, and a 'Revised'
        caption would claim a comparison that is not on screen."""
        ramp = self._ramp()
        ramp.show()
        self.assertFalse(ramp._before.isVisible())
        self.assertFalse(ramp._after_caption.isVisible())

    def test_a_reference_brings_both_captions_up(self):
        ramp = self._ramp()
        ramp.show()
        ramp.set_reference([(1.0, 0.0, 0.0), (0.0, 0.0, 0.0)])
        self.assertTrue(ramp._before.isVisible())
        self.assertTrue(ramp._after_caption.isVisible())
        self.assertEqual(
            [round(c, 3) for c in ramp.reference.composite(1.0)], [1.0, 0.0, 0.0]
        )

    def test_clearing_the_reference_puts_it_away(self):
        """``None`` is the right answer twice: nothing is being replaced, or the
        targets disagree and there is no single current look to hold up."""
        ramp = self._ramp()
        ramp.show()
        ramp.set_reference([(1.0, 0.0, 0.0)])
        ramp.set_reference(None)
        self.assertFalse(ramp._before.isVisible())
        self.assertFalse(ramp._after_caption.isVisible())

    def test_both_halves_run_the_same_cadence(self):
        """A comparison whose halves run at different tempos is showing two
        effects rather than two colourways of one."""
        ramp = self._ramp()
        ramp.set_shape(period=5.0, duty=0.25)
        ramp.set_reference([(1.0, 0.0, 0.0)])
        self.assertEqual(ramp.reference.shape, ramp.preview.shape)

    def test_both_halves_read_the_same_clock(self):
        """Two previews accumulating their own elapsed time drift apart, and a
        before/after caught at two different moments of the cycle says nothing.
        Their clock is shared, so the phase is identical by construction."""
        ramp = self._ramp()
        ramp.set_reference([(1.0, 0.0, 0.0)])
        self.assertAlmostEqual(ramp.reference.elapsed, ramp.preview.elapsed, places=3)

    def test_the_clock_is_real_time_not_ticks(self):
        """An accumulating counter advanced by a nominal frame however late the
        timer fired, so a preview in a busy DCC ran slower than the seconds the
        artist typed."""
        import time

        from uitk.widgets.editors.color_editor import RampPreview

        preview = self.track_widget(RampPreview(period=2.0))
        first = preview.elapsed
        time.sleep(0.05)
        self.assertGreaterEqual(preview.elapsed - first, 0.04)

    def test_a_ramp_without_a_preview_ignores_a_reference(self):
        """The embedded row may be built preview-less; asking it for a
        comparison must be a no-op rather than an AttributeError."""
        ramp = self._ramp(preview=False)
        ramp.set_reference([(1.0, 0.0, 0.0)])
        self.assertIsNone(ramp.preview)


class TestRampDecisions(QtBaseTestCase):
    """What a WRITER reads off the editor."""

    def _ramp(self, **kw):
        from uitk.widgets.editors.color_editor import ColorRampEditor

        kw.setdefault("colors", (BLUE, "#400000"))
        kw.setdefault("advanced", ())
        return self.track_widget(ColorRampEditor(**kw))

    def test_decided_reports_every_end_that_was_settled(self):
        decided = self._ramp().decided()
        self.assertEqual(len(decided), 2)
        self.assertTrue(all(c is not None for c in decided))

    def test_an_end_left_mixed_is_reported_as_undecided(self):
        """So a caller writes nothing for it, rather than flattening it."""
        ramp = self._ramp()
        ramp.set_mixed(1, True)
        bright, dim = ramp.decided()
        self.assertIsNotNone(bright)
        self.assertIsNone(dim)


if __name__ == "__main__":
    unittest.main()
