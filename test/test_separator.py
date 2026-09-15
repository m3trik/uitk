# !/usr/bin/python
# coding=utf-8
"""Unit tests for the Separator widget.

Pins the sizeHint contract added 2026: a titled Separator must advertise
enough width to render its title without cropping, so host containers
(notably QMenu) reserve room.

Run standalone: python -m test.test_separator
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets  # noqa: E402

from uitk.widgets.separator import Separator  # noqa: E402


class TestSeparatorSizeHint(QtBaseTestCase):
    """Verify width-advertisement so titles don't get clipped by parents."""

    def test_titled_sizehint_reserves_room_for_label(self):
        """A titled Separator must advertise at least label_width + 2*margin."""
        sep = Separator(title="Path Management")
        label_width = sep._title_label.sizeHint().width()
        margin = 2 * sep._TITLE_MARGIN_X
        self.assertGreaterEqual(sep.sizeHint().width(), label_width + margin)

    def test_titled_minimumsizehint_matches_sizehint(self):
        """Minimum hint must include the title too — otherwise layouts can
        squeeze the widget below its title and crop again."""
        sep = Separator(title="Resolve Missing Textures")
        label_width = sep._title_label.sizeHint().width()
        margin = 2 * sep._TITLE_MARGIN_X
        self.assertGreaterEqual(sep.minimumSizeHint().width(), label_width + margin)

    def test_longer_title_advertises_more_width(self):
        """The reserved width must track the title's actual rendered width."""
        short = Separator(title="A")
        long_ = Separator(title="A much longer separator title that needs room")
        self.assertGreater(long_.sizeHint().width(), short.sizeHint().width())

    def test_clearing_title_drops_extra_width(self):
        """Removing the title should drop back to the QFrame default width."""
        sep = Separator(title="Temporary")
        titled_width = sep.sizeHint().width()
        sep.title = ""  # hide
        self.assertLess(sep.sizeHint().width(), titled_width)

    def test_setTitle_alias_triggers_width_advertisement(self):
        """``setTitle`` (the Designer-friendly alias) must take the same path."""
        sep = Separator()
        baseline = sep.sizeHint().width()
        sep.setTitle("Selection")
        label_width = sep._title_label.sizeHint().width()
        margin = 2 * sep._TITLE_MARGIN_X
        self.assertGreaterEqual(sep.sizeHint().width(), label_width + margin)
        self.assertGreater(sep.sizeHint().width(), baseline)

    def test_title_label_has_non_zero_size_before_show(self):
        """Regression: the label must be sized + positioned at title-set time.

        Previously ``resizeEvent`` was the only place that called
        ``adjustSize()`` + ``move()``, gated by ``isVisible()`` (which is
        False until the entire ancestor chain is shown). Inside a hidden
        menu, the gate skipped, and the label stayed at 0×0 — which then
        rendered cropped on the right when the host finally showed.
        """
        sep = Separator(title="Path Management")
        # Host (sep) hasn't been shown — but the label must already have a
        # non-zero size matching its sizeHint and a non-default position.
        self.assertGreater(sep._title_label.width(), 0)
        self.assertGreater(sep._title_label.height(), 0)
        # Positioned at the configured left margin, not the default (0,0).
        self.assertEqual(sep._title_label.x(), sep._TITLE_MARGIN_X)


    def test_titled_caption_is_a_section_header(self):
        """Titled mode: taller box (breathing room above), caption uppercased
        via the font (so ``title`` round-trips as authored) and a rule painted
        from the caption's right edge — the caption must not look like a row."""
        from qtpy import QtGui

        sep = Separator(title="Materials")
        self.assertEqual(sep.height(), sep._TITLED_HEIGHT)
        self.assertGreater(sep._TITLED_HEIGHT, 9)  # untitled HLine height
        self.assertEqual(sep.title, "Materials")
        self.assertEqual(
            sep._title_label.font().capitalization(), QtGui.QFont.AllUppercase
        )
        # Bottom-aligned caption: the surplus is above it.
        self.assertEqual(
            sep._title_label.y(), sep.height() - sep._title_label.height()
        )
        # The rule is painted where the caption is not.
        sep.resize(200, sep.height())
        pixmap = sep.grab()
        img = pixmap.toImage()
        y = sep._title_label.y() + sep._title_label.height() // 2
        x = sep.width() - sep._TITLE_MARGIN_X - 2
        rule_px = QtGui.QColor(img.pixel(x, y))
        bg_px = QtGui.QColor(img.pixel(x, 1))
        self.assertNotEqual(rule_px.rgb(), bg_px.rgb())


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestSeparatorDisclosure(QtBaseTestCase):
    """A checkable separator is a section header that opens and closes."""

    def test_a_checkable_separator_toggles_on_click_and_says_so(self):
        from qtpy import QtCore, QtTest

        sep = self.track_widget(Separator(title="Advanced", checkable=True))
        sep.resize(200, sep.height())
        sep.show()
        seen = []
        sep.toggled.connect(seen.append)
        self.assertFalse(sep.isChecked())
        QtTest.QTest.mouseClick(sep, QtCore.Qt.LeftButton)
        self.assertTrue(sep.isChecked())
        QtTest.QTest.mouseClick(sep, QtCore.Qt.LeftButton)
        self.assertFalse(sep.isChecked())
        self.assertEqual(seen, [True, False])

    def test_a_plain_separator_stays_transparent_to_the_mouse(self):
        from qtpy import QtCore

        sep = self.track_widget(Separator(title="Path Management"))
        transparent = QtCore.Qt.WA_TransparentForMouseEvents
        self.assertTrue(sep.testAttribute(transparent))
        sep.setCheckable(True)
        self.assertFalse(sep.testAttribute(transparent), "a disclosure takes the click")
        sep.setCheckable(False)
        self.assertTrue(sep.testAttribute(transparent))

    def test_the_chevron_reserves_room_before_the_caption(self):
        plain = self.track_widget(Separator(title="Advanced"))
        disclosure = self.track_widget(Separator(title="Advanced", checkable=True))
        self.assertEqual(
            disclosure._title_label.x() - plain._title_label.x(), Separator._ARROW_W
        )
        self.assertEqual(
            disclosure.sizeHint().width() - plain.sizeHint().width(),
            Separator._ARROW_W,
        )

    def test_set_checked_emits_once_per_change(self):
        sep = self.track_widget(Separator(title="Advanced", checkable=True))
        seen = []
        sep.toggled.connect(seen.append)
        sep.setChecked(True)
        sep.setChecked(True)
        self.assertEqual(seen, [True])
