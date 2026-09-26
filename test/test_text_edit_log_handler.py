# !/usr/bin/python
# coding=utf-8
"""Unit tests for TextEditLogHandler.

Run standalone: python -m test.test_text_edit_log_handler
"""

import time
import logging
import threading
import unittest
from unittest import mock

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


class TestSafeAppendHiddenWidgetNoForcePaint(QtBaseTestCase):
    """Regression: _safe_append must not force repaint/processEvents on a HIDDEN widget.

    Pumping the event queue from inside a log emit while a panel is still
    being constructed dispatches deferred events against half-built widgets —
    a native access violation (segfault), not an exception the handler's
    try/except can catch.  Reproduced by blendertk's .venv ui-handler suite:
    loading 20+ panels whose slots log during __init__ crashed in
    _safe_append's processEvents.  A hidden target needs no live repaint at
    all; only a visible widget may force-paint.
    Fixed: 2026-07-08
    """

    def _handler_with_repaint_spy(self):
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        edit = self.track_widget(QtWidgets.QTextEdit())
        handler = TextEditLogHandler(edit)
        handler._last_repaint = 0  # open the throttle window
        calls = []
        edit.repaint = lambda *a, **k: calls.append("repaint")
        return handler, edit, calls

    def test_hidden_widget_appends_without_force_paint(self):
        handler, edit, calls = self._handler_with_repaint_spy()
        handler._safe_append("hello hidden")
        self.assertFalse(edit.isVisible())
        self.assertIn("hello hidden", edit.toPlainText())
        self.assertEqual(calls, [], "hidden widget must not be force-painted")

    def test_visible_widget_keeps_live_repaint(self):
        handler, edit, calls = self._handler_with_repaint_spy()
        edit.show()
        handler._safe_append("hello visible")
        self.assertTrue(edit.isVisible())
        self.assertIn("hello visible", edit.toPlainText())
        self.assertEqual(calls, ["repaint"], "visible widget keeps the live repaint")


class TestCrossThreadEmit(QtBaseTestCase):
    """Regression: a record logged from a plain worker thread must reach the widget.

    The old worker-thread path scheduled QTimer.singleShot on a thread with no
    Qt event loop, so the timer never fired and the record was silently lost.
    The fix marshals the append onto the GUI thread via a queued signal.
    """

    def test_worker_thread_record_reaches_widget(self):
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        edit = self.track_widget(QtWidgets.QTextEdit())
        handler = TextEditLogHandler(edit)
        logger = logging.getLogger("uitk_test_cross_thread_emit")
        logger.handlers = [handler]
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        try:

            def work():
                logger.info("from worker thread")

            t = threading.Thread(target=work)
            t.start()
            t.join(timeout=5)

            # Pump the GUI event loop so the queued append is delivered.
            deadline = time.monotonic() + 2.0
            while (
                "from worker thread" not in edit.toPlainText()
                and time.monotonic() < deadline
            ):
                app.processEvents()
                time.sleep(0.005)

            self.assertIn("from worker thread", edit.toPlainText())
        finally:
            logger.handlers = []


class TestTextEditLogHandlerWebLinks(QtBaseTestCase):
    """Web anchors in a log pane open in the browser; ``action://`` ones don't.

    ``setOpenExternalLinks(False)`` -- needed so ``action://`` links reach the
    panel's own ``anchorClicked`` dispatcher instead of the OS -- also silenced
    ordinary ``http(s)`` anchors, so a docs link logged at startup was dead
    unless each panel re-opened it by hand (only the extapps compositor did).
    ``route_links`` now routes just those schemes to ``QDesktopServices``, once
    per widget, and leaves every other scheme to the panel.
    """

    def _browser(self):
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        browser = self.track_widget(QtWidgets.QTextBrowser())
        TextEditLogHandler(browser)
        return browser

    def test_http_anchor_opens_in_the_default_browser(self):
        from qtpy import QtGui

        browser = self._browser()
        url = QtCore.QUrl("https://github.com/m3trik/extapps#readme")
        with mock.patch.object(QtGui.QDesktopServices, "openUrl") as opener:
            browser.anchorClicked.emit(url)
        opener.assert_called_once_with(url)

    def test_action_anchor_is_left_to_the_panel_dispatcher(self):
        from qtpy import QtGui

        browser = self._browser()
        with mock.patch.object(QtGui.QDesktopServices, "openUrl") as opener:
            browser.anchorClicked.emit(QtCore.QUrl("action://open?path=C:/x"))
        opener.assert_not_called()

    def test_rewiring_the_same_widget_opens_the_link_once(self):
        """A rebuilt handler / an explicit route_links() must not stack a
        second connection -- that would open two browser tabs per click."""
        from qtpy import QtGui
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        browser = self._browser()
        TextEditLogHandler(browser)  # a second handler on the same pane
        TextEditLogHandler.route_links(browser)  # and a direct call
        with mock.patch.object(QtGui.QDesktopServices, "openUrl") as opener:
            browser.anchorClicked.emit(QtCore.QUrl("https://example.invalid/d"))
        self.assertEqual(opener.call_count, 1)

    def test_clicking_an_address_in_a_log_line_opens_it(self):
        """The reported case: a warning names the page that enables Tailscale
        Funnel, as plain text -- the pane showed it, and a click did nothing.
        Logged the way every panel logs, then clicked where it shows."""
        from qtpy import QtGui, QtTest
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        page = "https://login.example.test/f/funnel?node=abc123"
        browser = self.track_widget(QtWidgets.QTextBrowser())
        browser.resize(900, 200)
        browser.show()
        logger = logging.getLogger("uitk_test_log_addresses")
        logger.handlers = [TextEditLogHandler(browser)]
        logger.propagate = False
        self.addCleanup(setattr, logger, "handlers", [])

        logger.warning(
            f"Funnel needs a one-time step first: enable it at {page}, then share."
        )
        app.processEvents()
        self.assertIn(f"{page}, then share", browser.toPlainText())

        found = browser.document().find(page)
        self.assertFalse(found.isNull(), "the address is not in the pane")
        cursor = QtGui.QTextCursor(browser.document())
        cursor.setPosition((found.selectionStart() + found.selectionEnd()) // 2)
        point = browser.cursorRect(cursor).center()
        with mock.patch.object(QtGui.QDesktopServices, "openUrl") as opener:
            QtTest.QTest.mouseClick(
                browser.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, point
            )
        opener.assert_called_once_with(QtCore.QUrl(page))

    def test_route_links_disables_navigation_without_a_handler(self):
        """The direct entry point is enough on its own (a panel whose optional
        engine is missing appends links by hand, with no handler built)."""
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        browser = self.track_widget(QtWidgets.QTextBrowser())
        TextEditLogHandler.route_links(browser)
        self.assertFalse(browser.openLinks())
        self.assertFalse(browser.openExternalLinks())


class TestBoxesFitThePane(QtBaseTestCase):
    """Regression: a ``log_box`` redirected into a pane came out wider than
    the pane, so Qt wrapped its rows and the borders fell apart.

    ``LoggerExt`` sizes boxes, dividers and tables to ``available_columns``,
    which was wrong four ways. It counted columns in the handler's monospace
    font while records were marked up ``font-family:monospace`` -- no family
    of that name exists on Windows, so Qt fell back to Courier New, ~9% wider
    than the Consolas measured (to Tahoma, proportional, when the widget font
    carries no monospace hint). It reserved one character where the document
    margins take 8px. It ignored the vertical scrollbar a box's own rows bring
    on, which narrows the pane under the box just sized for it. And below 20
    columns it answered 0 ("unknown"), so a narrow pane got a 100-column box.
    The span's ``white-space:pre`` never stopped the wrap: Qt keeps an
    over-long line whole only for a BLOCK format, and a record is inline.
    Fixed: 2026-09-24
    """

    BOX_EDGES = "╔║╟╚─"

    def _pane(self, width, height=160):
        """A shown log pane *width* px wide, and a logger redirected into it."""
        import pythontk as ptk
        from conftest import QtWait
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        class _Panel(ptk.LoggingMixin):
            pass

        pane = self.track_widget(QtWidgets.QTextBrowser())
        pane.resize(width, height)
        pane.show()
        QtWait.until(
            lambda: (
                not pane.testAttribute(QtCore.Qt.WA_PendingResizeEvent)
                and pane.width() == width
            ),
            "the pane was never laid out at its width",
        )
        logger = _Panel.logger
        logger.handlers = []  # only the pane: a TTY stderr would also cap widths
        logger.set_text_handler(TextEditLogHandler)
        logger.setup_logging_redirect(pane)
        self.addCleanup(setattr, logger, "handlers", [])
        return pane, logger

    def _broken_rows(self, pane):
        """The box/divider rows Qt laid out on more than one line."""
        document = pane.document()
        layout = document.documentLayout()
        broken = []
        block = document.begin()
        while block.isValid():
            layout.blockBoundingRect(block)  # lay the block out now
            text = block.text()
            if text and text[0] in self.BOX_EDGES and block.layout().lineCount() > 1:
                broken.append(text)
            block = block.next()
        return broken

    def test_a_box_fits_the_pane_at_every_width(self):
        """Short on purpose: the box's own rows push the log past one screen,
        so the scrollbar arrives AFTER the width was read."""
        for width in range(260, 1000, 53):
            with self.subTest(width=width):
                pane, logger = self._pane(width)
                logger.log_box("Scene export summary " * 4, ["word " * 60, "done"])
                logger.log_divider()
                self.assertEqual(self._broken_rows(pane), [])

    def test_every_glyph_pythontk_draws_is_measured(self):
        """available_columns counts in the widest glyph it measures, so one it
        skips can be wider and wrap its row: the divider's was, under Linux
        fontconfig (CI, 2026-09-26). Drift guard over pythontk's source."""
        import inspect

        from pythontk.core_utils import logging_mixin
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        drawn = {
            ch for ch in inspect.getsource(logging_mixin) if 0x2500 <= ord(ch) <= 0x259F
        }
        self.assertTrue(drawn)
        self.assertEqual(drawn - set(TextEditLogHandler._BOX_GLYPHS), set())

    def test_a_narrow_pane_gets_a_narrow_box(self):
        pane, logger = self._pane(150)
        self.assertGreater(logger.handlers[0].available_columns(), 0)
        logger.log_box("Narrow", ["words that wrap inside the box"])
        self.assertEqual(self._broken_rows(pane), [])

    def test_a_pane_no_layout_has_sized_reports_unknown(self):
        """Until its first show a pane's viewport is Qt's placeholder (638px
        here), not the pane: 0 sends the caller to its default instead."""
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        pane = self.track_widget(QtWidgets.QTextBrowser())
        pane.resize(300, 100)  # sized, but never shown -- no layout has run
        self.assertEqual(TextEditLogHandler(pane).available_columns(), 0)

    def test_every_record_asks_for_the_family_that_is_measured(self):
        """Columns are counted in ONE family, so every record must request
        exactly that one -- never the generic ``monospace``, which each
        platform resolves differently. A tinted box carries ``log_box``'s own
        stack instead, which must list the handler's families in the handler's
        order, or it renders in a font the columns were not counted in."""
        from uitk.widgets.textEditLogHandler import TextEditLogHandler

        pane, logger = self._pane(600)
        logger.log_box("Title", ["row"], level="SUCCESS")
        logger.log_box("Plain", ["row"])
        logger.log_divider()
        logger.warning("a regular record")
        requested = set()
        block = pane.document().begin()
        while block.isValid():
            fragments = block.begin()
            while not fragments.atEnd():
                fragment = fragments.fragment()
                if fragment.isValid() and fragment.text().strip():
                    requested.add(tuple(fragment.charFormat().fontFamilies() or ()))
                fragments += 1
            block = block.next()
        measured = getattr(logger.handlers[0], "_font_family", None)
        plain = {families for families in requested if len(families) == 1}
        self.assertEqual(plain, {(measured,)})
        self.assertEqual(requested - plain, {TextEditLogHandler._MONOSPACE_FAMILIES})


if __name__ == "__main__":
    unittest.main()
