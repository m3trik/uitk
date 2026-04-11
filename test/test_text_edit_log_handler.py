# !/usr/bin/python
# coding=utf-8
"""Unit tests for TextEditLogHandler.

Run standalone: python -m test.test_text_edit_log_handler
"""

import unittest
from unittest.mock import MagicMock

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtCore


class TestTextEditLogHandlerLinkNavigation(QtBaseTestCase):
    """Regression: Clicking an action:// link must NOT clear the log panel.

    Bug: QTextBrowser.setOpenExternalLinks(False) prevents opening links
    in an external browser but still allows internal navigation via
    setSource(), which replaces the document content with nothing for
    unresolvable action:// URIs.
    Fix: Call setOpenLinks(False) so QTextBrowser emits anchorClicked
    without any navigation.
    Fixed: 2026-04-10
    """

    def _make_handler_and_browser(self):
        """Create a QTextBrowser wired to a TextEditLogHandler."""
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        browser = self.track_widget(QtWidgets.QTextBrowser())
        handler = TextEditLogHandler(browser)
        return handler, browser

    def test_open_links_disabled_on_qtextbrowser(self):
        """TextEditLogHandler must set openLinks=False on QTextBrowser."""
        _, browser = self._make_handler_and_browser()
        self.assertFalse(
            browser.openLinks(),
            "openLinks should be False to prevent internal navigation",
        )

    def test_open_external_links_disabled_on_qtextbrowser(self):
        """TextEditLogHandler must set openExternalLinks=False on QTextBrowser."""
        _, browser = self._make_handler_and_browser()
        self.assertFalse(
            browser.openExternalLinks(),
            "openExternalLinks should be False to prevent external navigation",
        )

    def test_action_link_click_preserves_content(self):
        """Clicking an action:// link must not clear the text browser.

        The actual failure path is QTextBrowser.setSource(url), which Qt
        calls internally when openLinks is True.  With openLinks=False
        (the fix), setSource is never called by the click — only
        anchorClicked is emitted.

        This test verifies the guard by confirming that setSource *would*
        destroy the content, but openLinks is False so it cannot fire.
        """
        _, browser = self._make_handler_and_browser()

        # Insert HTML content as a log message would
        test_html = '<span style="color:white;">Test log message</span>'
        browser.append(test_html)
        app.processEvents()
        self.assertIn("Test log message", browser.toPlainText())

        # Prove that setSource *would* clear content (the bug path)
        backup_html = browser.toHtml()
        browser.setSource(QtCore.QUrl("action://select?node=%7Cgroup1%7CpCube1"))
        app.processEvents()
        self.assertEqual(
            browser.toPlainText().strip(),
            "",
            "setSource should have cleared the document (proving the bug path exists)",
        )

        # Restore content and verify openLinks=False prevents the clear
        browser.setHtml(backup_html)
        app.processEvents()
        self.assertIn("Test log message", browser.toPlainText())

        # The actual guard: openLinks must be False
        self.assertFalse(
            browser.openLinks(),
            "openLinks must be False so Qt never calls setSource on click",
        )

    def test_handler_works_with_plain_qtextedit(self):
        """TextEditLogHandler must not crash on QTextEdit (no openLinks attr)."""
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        text_edit = self.track_widget(QtWidgets.QTextEdit())
        # Should not raise — QTextEdit has no setOpenLinks
        handler = TextEditLogHandler(text_edit)
        self.assertIsNotNone(handler)

    def test_log_link_html_rendered_as_clickable(self):
        """A log_link anchor tag must be present and clickable in the browser."""
        from pythontk.core_utils.logging_mixin import LoggerExt

        _, browser = self._make_handler_and_browser()

        link_html = LoggerExt._log_link("pCube1", "select", node="|group1|pCube1")
        browser.append(link_html)
        app.processEvents()

        html = browser.toHtml()
        self.assertIn("action://select", html)
        self.assertIn("pCube1", browser.toPlainText())


if __name__ == "__main__":
    unittest.main()
