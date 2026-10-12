# !/usr/bin/python
# coding=utf-8
"""Unit tests for the TextViewBox widget's link routing.

A report shown in the viewer carries two kinds of link: ``file://`` paths the
OS opens, and ``action://VERB?...`` links only the host application can act on
(a scene report's "select this mesh"). Every click used to go to
``QDesktopServices`` -- so an action link raised the OS's "no app is
associated" dialog and never reached the host.

Run standalone: python -m test.test_text_view_box
"""

import unittest
from unittest import mock

from conftest import QtBaseTestCase, setup_qt_application

# Ensure QApplication exists before importing Qt widgets
app = setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402
from uitk.widgets.textViewBox import TextViewBox  # noqa: E402

ACTION = QtCore.QUrl("action://select?node=%7Croot%7CDOOR_A")
FILE = QtCore.QUrl("file:///C:/textures/rock_Base_Color.png")


class TestTextViewBoxLinks(QtBaseTestCase):
    def click(self, box, url):
        with mock.patch.object(QtGui.QDesktopServices, "openUrl") as open_url:
            box.text_edit.anchorClicked.emit(url)
        return open_url

    def test_the_handler_sees_the_link_first(self):
        seen = []
        box = self.track_widget(
            TextViewBox(link_handler=lambda url: seen.append(url) or True)
        )
        open_url = self.click(box, ACTION)
        self.assertEqual([u.toString() for u in seen], [ACTION.toString()])
        open_url.assert_not_called()

    def test_an_unhandled_file_link_still_opens_in_the_os(self):
        box = self.track_widget(TextViewBox(link_handler=lambda url: False))
        self.click(box, FILE).assert_called_once_with(FILE)

    def test_an_action_link_never_reaches_the_os(self):
        for handler in (None, lambda url: False):
            box = self.track_widget(TextViewBox(link_handler=handler))
            self.click(box, ACTION).assert_not_called()

    def test_a_failing_handler_is_contained(self):
        def boom(url):
            raise RuntimeError("host gone")

        box = self.track_widget(TextViewBox(link_handler=boom))
        with self.assertLogs("uitk.widgets.textViewBox", level="ERROR"):
            open_url = self.click(box, FILE)
        open_url.assert_not_called()

    def test_the_handler_can_be_set_after_construction(self):
        box = self.track_widget(TextViewBox())
        seen = []
        box.link_handler = lambda url: seen.append(url) or True
        self.click(box, ACTION)
        self.assertEqual(len(seen), 1)

    def test_a_clicked_report_link_hands_over_every_param_decoded(self):
        """A report's markup, through Qt's parser, clicked: the handler parses
        the exact params back. Regression: a single-quoted href handed it
        "&amp;" (``{"text": [...], "amp;node": [...]}``)."""
        from urllib.parse import parse_qs

        from pythontk import ReportDoc
        from qtpy import QtTest, QtWidgets

        seen = []
        box = self.track_widget(
            TextViewBox(link_handler=lambda url: seen.append(url) or True)
        )
        params = {"text": "a b&c", "node": "|grp|ns:box"}
        doc = ReportDoc().text(ReportDoc.action("LINK", "copy", **params))
        box.setText(doc.to_html())
        box.show()
        QtWidgets.QApplication.processEvents()
        editor = box.text_edit
        cursor = editor.document().find("LINK")
        cursor.setPosition(cursor.selectionStart() + 2)  # inside the anchor text
        QtTest.QTest.mouseClick(
            editor.viewport(),
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            editor.cursorRect(cursor).center(),
        )
        self.assertEqual(len(seen), 1)
        self.assertEqual(
            {k: v[0] for k, v in parse_qs(seen[0].query()).items()}, params
        )


class TestTextViewBoxPreview(QtBaseTestCase):
    """``bind_preview``: option rows beside the text, every change rendering
    the text again at once -- what a tool will write, seen before it writes
    (the Shot Manifest's Export, 2026-10-11)."""

    SPECS = (
        {
            "key": "fmt",
            "label": "Format",
            "kind": "choice",
            "default": "csv",
            "choices": (("CSV", "csv"), ("JSON", "json")),
        },
        {
            "key": "cols",
            "label": "Columns",
            "kind": "check_list",
            "default": ["a", "b"],
            "choices": (("A", "a"), ("B", "b")),
            "hint": "Which columns go.",
        },
    )

    @staticmethod
    def render(values):
        return f"{values['fmt']}:{','.join(values['cols'])} <a&b>"

    def test_the_text_is_rendered_from_the_values_as_plain_text(self):
        box = self.track_widget(TextViewBox(monospace=True))
        box.bind_preview(self.render, self.SPECS, values={"fmt": "json"})
        self.assertEqual(box.preview_values, {"fmt": "json", "cols": ["a", "b"]})
        self.assertEqual(box.text_edit.toPlainText(), "json:a,b <a&b>")
        self.assertEqual(box.preview_text, "json:a,b <a&b>")

    def test_a_changed_row_renders_at_once_and_is_reported(self):
        seen = []
        box = self.track_widget(TextViewBox())
        box.bind_preview(
            self.render, self.SPECS, on_change=lambda k, v: seen.append((k, v))
        )
        fmt = box.preview_widgets["fmt"]
        fmt.setCurrentIndex(fmt.findData("json"))
        box.preview_widgets["cols"].item(0).setCheckState(QtCore.Qt.Unchecked)
        self.assertEqual(seen, [("fmt", "json"), ("cols", ["b"])])
        self.assertEqual(box.text_edit.toPlainText(), "json:b <a&b>")

    def test_the_status_names_what_is_shown(self):
        box = self.track_widget(TextViewBox())
        box.bind_preview(
            self.render, self.SPECS, status=lambda values, text: f"{len(text)} chars"
        )
        self.assertEqual(box.footer.text(), "13 chars")
        plain = self.track_widget(TextViewBox())
        plain.bind_preview(lambda values: "one\ntwo\n", ())
        self.assertEqual(plain.footer.text(), "2 lines")

    def test_refresh_renders_again_for_a_change_outside_the_rows(self):
        state = {"n": 1}
        box = self.track_widget(TextViewBox())
        box.bind_preview(lambda values: f"rows: {state['n']}", ())
        state["n"] = 2
        box.refresh_preview()
        self.assertEqual(box.text_edit.toPlainText(), "rows: 2")

    def test_the_rows_sit_beside_the_text(self):
        box = self.track_widget(TextViewBox())
        box.bind_preview(self.render, self.SPECS)
        box.resize(800, 400)
        box.show()
        QtWidgets.QApplication.processEvents()
        rows = box.preview_widgets["fmt"].mapTo(box, QtCore.QPoint(0, 0))
        text = box.text_edit.mapTo(box, QtCore.QPoint(0, 0))
        self.assertLess(rows.x(), text.x())
        # At its own width, not squeezed to its minimum: a check list's
        # labels read whole (the Shot Manifest's Columns, clipped at first).
        cols = box.preview_widgets["cols"]
        self.assertGreaterEqual(cols.viewport().width(), cols.sizeHintForColumn(0))

    def test_a_button_reports_its_name_and_an_apply_role_stays_open(self):
        clicked = []
        box = self.track_widget(TextViewBox())
        box.setStandardButtons("Copy", "SaveAs", "Close")
        box.button_clicked.connect(clicked.append)
        box.show()
        labels = [b.text() for b in box.button_box.buttons()]
        self.assertIn("Save As…", labels)
        for button in box.button_box.buttons():
            if button.text() in ("Copy", "Save As…"):
                button.click()
        self.assertEqual(sorted(clicked), ["Copy", "SaveAs"])
        self.assertTrue(box.isVisible())


if __name__ == "__main__":
    unittest.main()
