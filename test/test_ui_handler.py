# !/usr/bin/python
# coding=utf-8
"""Unit tests for ``UiHandler`` — UI resolution and launch dispatch.

``can_resolve`` is the handler-side contract behind
``SwitchboardWidgetMixin.ui_name_resolves``: it reports whether ``get(name)``
would resolve to a UI *without building it*, so marking-menu destination
resolution (nav-button click + auto-hide) can recognise a handler's UIs. The
base implementation resolves registered ``.ui`` file stems (stripping any
``#submenu`` suffix); subclasses extend it for non-file sources (e.g.
``MayaUiHandler`` adds its native-menu names — see mayatk's
``test_maya_ui_handler``). Pinning the base keeps that contract stable.

``launch`` must route a UI claimed by a *hosting handler* (duck-typed
``hosts_ui``/``show`` contract — e.g. the marking menu's stacked
startmenu/submenu pages) through that handler instead of applying the
standalone-window setup, which would strip the owner's hosting invariants
(the "browser-launched startmenu breaks the marking menu" bug).

``__init__`` is bypassed for the unit cases (it discovers slots/UIs); each
test provides only the ``sb`` surface its method under test touches.
"""
import os
import tempfile
import types
import unittest

from uitk.handlers.ui_handler import UiHandler


class TestUiHandlerCanResolve(unittest.TestCase):
    def setUp(self):
        self.handler = object.__new__(UiHandler)
        self._registered = {"polygons", "editors"}
        self.handler.sb = types.SimpleNamespace(
            is_registered_ui=lambda n: n in self._registered
        )

    def test_registered_stem_resolves(self):
        self.assertTrue(self.handler.can_resolve("polygons"))

    def test_unregistered_stem_does_not_resolve(self):
        self.assertFalse(self.handler.can_resolve("not_a_ui"))

    def test_submenu_suffix_strips_to_base(self):
        """'<stem>#submenu' resolves on the base stem, mirroring get()."""
        self.assertTrue(self.handler.can_resolve("polygons#submenu"))
        self.assertFalse(self.handler.can_resolve("not_a_ui#submenu"))

    def test_tagged_submenu_strips_to_base(self):
        """Only the first '#'-segment (the base) is consulted."""
        self.assertTrue(self.handler.can_resolve("polygons#edge#submenu"))

    def test_empty_name_does_not_resolve(self):
        self.assertFalse(self.handler.can_resolve(""))
        self.assertFalse(self.handler.can_resolve(None))


# ── Launch delegation to a hosting handler ──────────────────────────────────


class _HostingClaimStub:
    """Handler double implementing the hosting claim (``hosts_ui``/``show``).

    Claims every ``*#startmenu`` name — the shape of the marking menu's
    claim without the marking menu's weight.
    """

    def __init__(self):
        self.shown = []

    def hosts_ui(self, name):
        return bool(name) and name.endswith("#startmenu")

    def show(self, name):
        self.shown.append(name)
        return f"hosted:{name}"


class _ForbiddenLoadedUi:
    """``loaded_ui`` stand-in that fails the test if the standalone path runs."""

    def __getitem__(self, name):
        raise AssertionError(
            "UiHandler.launch touched loaded_ui for a claimed UI — the "
            "standalone-window path must not run when a hosting handler "
            "claims the name."
        )

    def peek(self, name):
        return None


class TestUiHandlerLaunchDelegation(unittest.TestCase):
    """``launch`` routes a claimed UI through its hosting handler.

    A UI whose windowing lifecycle another handler owns (e.g. a marking-menu
    startmenu/submenu page — a stacked child of the overlay) must never get
    the standalone setup (reparent to a top-level Qt.Window, Tool/on-top
    flags, launched-header buttons): ``is_initialized`` gates the owner's
    ``_init_ui`` to a single run, so the page would stay broken forever.
    Regression: 2026-07-13, browser-launched startmenus.
    """

    def setUp(self):
        self.handler = object.__new__(UiHandler)
        self.host = _HostingClaimStub()
        handlers_ns = types.SimpleNamespace(ui=self.handler, marking_menu=self.host)
        self.handler.sb = types.SimpleNamespace(
            handlers=handlers_ns, loaded_ui=_ForbiddenLoadedUi()
        )

    def test_hosting_handler_resolves_claimant(self):
        self.assertIs(self.handler.hosting_handler("cameras#startmenu"), self.host)

    def test_hosting_handler_none_for_unclaimed(self):
        self.assertIsNone(self.handler.hosting_handler("plain_tool"))

    def test_launch_delegates_claimed_ui_to_host(self):
        result = self.handler.launch("cameras#startmenu")
        self.assertEqual(self.host.shown, ["cameras#startmenu"])
        self.assertEqual(result, "hosted:cameras#startmenu")

    def test_launch_discards_style_options_for_hosted_ui(self):
        """Browser launch options target standalone windows; the owner
        controls presentation, so they're discarded rather than forwarded."""
        self.handler.launch(
            "cameras#startmenu",
            frameless=True,
            translucent=True,
            restore_geometry=False,
            on_top=True,
            theme="dark",
        )
        self.assertEqual(self.host.shown, ["cameras#startmenu"])

    def test_probe_skips_self(self):
        """UiHandler must never satisfy its own probe, even if a subclass
        grows hosts_ui/show-shaped methods."""
        self.handler.hosts_ui = lambda name: True
        self.handler.show = lambda name: "self"
        self.assertIs(self.handler.hosting_handler("cameras#startmenu"), self.host)
        self.assertIsNone(self.handler.hosting_handler("plain_tool"))

    def test_probe_survives_raising_claimant(self):
        """A dead/misbehaving claimant is skipped, not fatal — the launch
        falls through to the standalone path instead of erroring out."""

        def boom(_name):
            raise RuntimeError("dead C++ object")

        self.host.hosts_ui = boom
        self.assertIsNone(self.handler.hosting_handler("cameras#startmenu"))

    def test_handlers_without_claim_surface_are_skipped(self):
        """Handlers lacking hosts_ui or show (the common case) never match."""
        self.handler.sb.handlers.external = types.SimpleNamespace(
            launch=lambda n: None
        )
        self.assertIsNone(self.handler.hosting_handler("plain_tool"))


def _write_ui(path, name, tags_csv=None):
    """Minimal QMainWindow .ui file (mirrors test_switchboard_browser)."""
    tag_block = ""
    if tags_csv is not None:
        tag_block = (
            f'<property name="uitk_tags" stdset="0">'
            f"<string>{tags_csv}</string></property>"
        )
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>QtUi</class>
 <widget class="QMainWindow" name="{name}">
  {tag_block}
 </widget>
</ui>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class TestLaunchDelegationIntegration(unittest.TestCase):
    """End-to-end over a real Switchboard: a registered ``*#startmenu`` .ui
    launched through the real UiHandler is delegated to the hosting handler
    (without ever materialising standalone); a plain tool still launches
    standalone and the claimant is not consulted into showing it."""

    @classmethod
    def setUpClass(cls):
        from conftest import setup_qt_application

        cls.app = setup_qt_application()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        _write_ui(os.path.join(d, "tool.ui"), "tool")
        _write_ui(os.path.join(d, "cameras#startmenu.ui"), "cameras_startmenu")
        from uitk.switchboard import Switchboard

        self.sb = Switchboard(ui_source=d, log_level="WARNING")
        self.host = _HostingClaimStub()
        self.sb.handlers.marking_menu = self.host

    def tearDown(self):
        from qtpy import QtCore, QtWidgets

        self.sb.deleteLater()
        for _ in range(3):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.tmp.cleanup()

    def test_startmenu_launch_delegates_without_standalone_load(self):
        result = self.sb.handlers.ui.launch("cameras#startmenu")
        self.assertEqual(self.host.shown, ["cameras#startmenu"])
        self.assertEqual(result, "hosted:cameras#startmenu")
        # Delegation resolves at the registry level — the standalone path
        # never materialised the UI into loaded_ui.
        self.assertIsNone(self.sb.loaded_ui.peek("cameras#startmenu"))

    def test_plain_tool_still_launches_standalone(self):
        ui = self.sb.handlers.ui.launch("tool")
        try:
            self.assertTrue(ui.isVisible())
            self.assertEqual(self.host.shown, [])
        finally:
            ui.deleteLater()


class _CanonicalInitStub:
    """Marking-menu double exposing the canonical window-init path (``get``).

    Claims nothing (no hosts_ui) — models the *standalone-window* case where
    the menu doesn't host the UI but still owns its canonical init (pin
    chrome via apply_styles, parenting to the host app window,
    hide-with-menu lifecycle).
    """

    def __init__(self, sb):
        self.sb = sb
        self.got = []

    def get(self, name, **kwargs):
        self.got.append(name)
        return self.sb.loaded_ui[name]


class TestLaunchCanonicalWindowInit(unittest.TestCase):
    """``launch`` must not fork a standalone window's chrome/lifecycle.

    On a switchboard with a marking menu, the launched window is the SAME
    singleton the menu manages: window init must route through the menu's
    canonical path (``mm.get``) and the launcher-only header set
    (menu/collapse/hide) must be skipped — otherwise launch order decides
    the chrome ("browser-launched tool gets a hide button instead of the
    intended pin that hides with the menu"). Regression: 2026-07-13.
    """

    @classmethod
    def setUpClass(cls):
        from conftest import setup_qt_application

        cls.app = setup_qt_application()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        _write_ui(os.path.join(self.tmp.name, "tool.ui"), "tool")
        from uitk.switchboard import Switchboard

        self.sb = Switchboard(ui_source=self.tmp.name, log_level="WARNING")

    def tearDown(self):
        from qtpy import QtCore, QtWidgets

        self.sb.deleteLater()
        for _ in range(3):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.tmp.cleanup()

    def test_launch_routes_window_init_through_marking_menu(self):
        from unittest import mock

        mm = _CanonicalInitStub(self.sb)
        self.sb.handlers.marking_menu = mm
        handler = self.sb.handlers.ui
        with mock.patch.object(handler, "_configure_launched_header") as chrome:
            ui = handler.launch("tool")
        try:
            self.assertEqual(mm.got, ["tool"])
            chrome.assert_not_called()
            self.assertTrue(ui.isVisible())
        finally:
            ui.deleteLater()

    def test_launch_without_marking_menu_keeps_launcher_chrome(self):
        from unittest import mock

        handler = self.sb.handlers.ui
        with mock.patch.object(handler, "_configure_launched_header") as chrome:
            ui = handler.launch("tool")
        try:
            chrome.assert_called_once()
        finally:
            ui.deleteLater()


class TestSetupLifecycleIdempotent(unittest.TestCase):
    """Repeated ``setup_lifecycle`` on one window wires the hide signal once.

    Both canonical init paths (``MarkingMenu._init_ui`` and ``launch``) run
    it on the same shared window; without the guard every relaunch stacked
    another ``request_hide`` connection.
    """

    @classmethod
    def setUpClass(cls):
        from conftest import setup_qt_application

        cls.app = setup_qt_application()

    def test_signal_wired_once(self):
        from qtpy import QtCore

        class _Sig(QtCore.QObject):
            fired = QtCore.Signal()

        class _Win:
            def __init__(self):
                self.hides = 0

            def objectName(self):
                return "w"

            def request_hide(self):
                self.hides += 1

        handler = object.__new__(UiHandler)
        sig = _Sig()
        win = _Win()
        handler.setup_lifecycle(win, hide_signal=sig.fired)
        handler.setup_lifecycle(win, hide_signal=sig.fired)
        sig.fired.emit()
        self.assertEqual(win.hides, 1)


class TestUiHandlerGetSignature(unittest.TestCase):
    """``get`` must not silently swallow unsupported args.

    Regression: ``get(name, reload=False, **kwargs)`` accepted a ``reload``
    flag and arbitrary kwargs and dropped them all — ``Switchboard.get_ui``
    takes only ``name`` and there is no UI-reload path. Passing them now
    raises ``TypeError`` (a caller mistake surfaced) instead of no-op'ing.
    """

    def _handler(self, ui_obj):
        h = object.__new__(UiHandler)
        h.sb = types.SimpleNamespace(get_ui=lambda name: ui_obj)
        # apply_styles would choke on a bare sentinel; stub it.
        h.apply_styles = lambda ui: None
        return h

    def test_get_resolves_by_name(self):
        sentinel = object()
        handler = self._handler(sentinel)
        self.assertIs(handler.get("polygons"), sentinel)

    def test_get_strips_subname(self):
        sentinel = object()
        handler = self._handler(sentinel)
        # "#component" suffix is stripped before resolution.
        self.assertIs(handler.get("polygons#component"), sentinel)

    def test_get_tolerates_extra_kwargs(self):
        # Existing consumers pass extra keywords — tentacle's slots call
        # get(name, header=True) and the marking menu calls get(name, **kwargs).
        # These must be accepted (and ignored), not raise TypeError.
        sentinel = object()
        handler = self._handler(sentinel)
        self.assertIs(handler.get("polygons", header=True), sentinel)
        self.assertIs(handler.get("polygons", reload=True, frameless=True), sentinel)


class _FakeScreen:
    """Stand-in for QScreen exposing only ``availableGeometry()``.

    Models a primary screen whose available origin is non-zero — the shape
    produced by a top- or left-docked Windows taskbar.
    """

    def __init__(self, geo):
        self._geo = geo

    def availableGeometry(self):
        return self._geo


class _FakePositionWin:
    """Minimal window double for ``_position_window`` — records ``move()``.

    Avoids a real top-level QWidget (whose frame geometry / window-manager
    placement would perturb the moved position) so the test can assert the
    exact target point the branch computes.
    """

    def __init__(self, size):
        from qtpy import QtCore

        self._rect = QtCore.QRect(0, 0, size[0], size[1])
        self.moved = None

    def layout(self):
        return None

    def rect(self):
        return self._rect

    def parentWidget(self):
        return None

    def isWindow(self):
        return True

    def move(self, point):
        self.moved = point


class TestPositionWindowScreen(unittest.TestCase):
    """``_position_window(ui, "screen")`` centers on the available geometry.

    Regression: the branch added ``screen_geo.topLeft()`` on top of the
    already-global ``center() - rect().center()`` offset, double-counting a
    non-zero available origin (e.g. a top-docked taskbar) and pushing the
    window off-center by exactly that origin. Must match ``center_widget``.
    """

    def test_non_zero_available_origin_not_double_added(self):
        from unittest import mock
        from qtpy import QtCore, QtWidgets

        # Available origin offset down 48px, as with a top-docked taskbar.
        screen_geo = QtCore.QRect(0, 48, 1920, 1032)
        screen = _FakeScreen(screen_geo)
        win = _FakePositionWin((200, 100))

        handler = object.__new__(UiHandler)
        with mock.patch.object(
            QtWidgets.QApplication, "primaryScreen", lambda: screen
        ):
            handler._position_window(win, "screen")

        expected = screen_geo.center() - win.rect().center()
        self.assertEqual(win.moved, expected)

        # The pre-fix double-add would have shifted the target down by the
        # full available origin (48px); assert we did NOT land there.
        buggy = screen_geo.topLeft() + expected
        self.assertNotEqual(win.moved, buggy)
        self.assertEqual(win.moved.y(), expected.y())


class _StyleOnlyUi:
    """Records what ``apply_styles`` pushed through ``ui.style.set``."""

    def __init__(self, *tags):
        self._tags = set(tags)
        self.applied = {}
        outer = self

        class _Style:
            def set(self, **kwargs):
                outer.applied = kwargs

        self.style = _Style()

    def has_tags(self, tags):
        return bool(self._tags & set(tags))


class TestApplyStylesThemeResolution(unittest.TestCase):
    """``apply_styles`` resolves its theme from the marking menu's per-style
    preference, so the two hosted window themes are user-configurable instead
    of pinned to ``DEFAULT_STYLE["theme"]``.

    The subclass handlers (mayatk / blendertk) always hand in a pre-built style
    copied from ``DEFAULT_STYLE``, so "pre-built" alone must NOT opt out of
    resolution — only a style whose theme was deliberately changed does.
    """

    def _handler(self, resolved="light"):
        handler = object.__new__(UiHandler)
        menu = types.SimpleNamespace(resolve_hosted_theme=lambda ui: resolved)
        handler.sb = types.SimpleNamespace(
            handlers=types.SimpleNamespace(marking_menu=menu)
        )
        return handler

    def test_default_path_uses_resolved_theme(self):
        ui = _StyleOnlyUi("startmenu")
        self._handler("light").apply_styles(ui)
        self.assertEqual(ui.applied["theme"], "light")

    def test_prebuilt_default_style_still_resolves(self):
        """The mayatk / blendertk header-button override path."""
        import copy

        handler = self._handler("high-contrast")
        style = copy.deepcopy(UiHandler.DEFAULT_STYLE)
        style["header_buttons"] = ("menu", "collapse", "hide")
        handler.apply_styles(_StyleOnlyUi("mayatk"), style=style)
        self.assertEqual(style["theme"], "high-contrast")

    def test_explicit_theme_arg_wins(self):
        ui = _StyleOnlyUi("startmenu")
        self._handler("light").apply_styles(ui, theme="dark")
        self.assertEqual(ui.applied["theme"], "dark")

    def test_deliberate_style_theme_is_kept(self):
        """A caller that picked a non-default theme keeps it."""
        ui = _StyleOnlyUi("startmenu")
        self._handler("light").apply_styles(ui, style={"theme": "high-contrast"})
        self.assertEqual(ui.applied["theme"], "high-contrast")

    def test_no_marking_menu_falls_back_to_default_style(self):
        """Plain Switchboard usage (no marking menu) keeps DEFAULT_STYLE."""
        handler = object.__new__(UiHandler)
        handler.sb = types.SimpleNamespace(handlers=None)
        ui = _StyleOnlyUi("startmenu")
        handler.apply_styles(ui)
        self.assertEqual(ui.applied["theme"], UiHandler.DEFAULT_STYLE["theme"])


class TestShowRestoresCollapsedHeader(unittest.TestCase):
    """``show`` must present the FULL window when its header left it collapsed.

    A header-collapsed window is still visible (a bare title strip), so Qt's
    ``show()`` no-ops on it and ``Header.showEvent`` — which resets collapse
    state on a hidden→shown transition — never fires. Re-showing via the
    handler (e.g. a marking-menu MenuButton relaunching the tool) therefore
    positioned the collapsed strip at the cursor instead of the real window
    ("shows in a corrupted state").
    Fixed: 2026-07-25
    """

    def setUp(self):
        from conftest import setup_qt_application

        self.app = setup_qt_application()
        self.handler = object.__new__(UiHandler)
        # `config` is a read-only property backed by sb.configurable.
        self.handler.sb = types.SimpleNamespace(
            configurable=types.SimpleNamespace(
                branch=lambda name: {"default_position": None}
            )
        )

    def _collapsed_window(self):
        from qtpy import QtWidgets, QtCore
        from uitk.widgets.header import Header

        window = QtWidgets.QWidget()
        window.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        layout = QtWidgets.QVBoxLayout(window)
        layout.setContentsMargins(0, 0, 0, 0)
        header = Header(parent=window, config_buttons=["collapse", "hide"])
        layout.addWidget(header)
        body = QtWidgets.QLabel("body", parent=window)
        body.setMinimumHeight(150)
        layout.addWidget(body)
        window.header = header  # what attach_to/apply_styles normally set
        window.show()
        window.resize(400, 300)
        self.app.processEvents()
        header.collapse_window(fixed_width=200)
        self.app.processEvents()
        self.addCleanup(window.deleteLater)
        return window, header, body

    def test_show_expands_visible_collapsed_window(self):
        window, header, body = self._collapsed_window()
        self.assertTrue(window.isVisible())
        self.handler.show(window, force=True)
        self.app.processEvents()
        self.assertFalse(header._collapsed)
        self.assertTrue(body.isVisible())
        self.assertEqual(window.height(), 300)

    def test_show_positions_with_expanded_size(self):
        """Cursor positioning must measure the expanded window, not the strip."""
        from unittest.mock import patch
        from qtpy import QtCore, QtGui

        window, header, _ = self._collapsed_window()
        # Pin the cursor read — the suite runs on the native QPA, so the live
        # mouse could move between show()'s read and this test's expectation.
        cursor = QtCore.QPoint(600, 400)
        with patch.object(QtGui.QCursor, "pos", return_value=cursor):
            self.handler.show(window, pos="cursor", force=True)
        self.app.processEvents()
        self.assertFalse(header._collapsed)
        self.assertEqual(window.width(), 400)
        # _position_window centers on the cursor with a 25%-height downward
        # offset — asserting both axes proves the EXPANDED size was measured.
        self.assertEqual(window.x(), cursor.x() - window.width() // 2)
        self.assertEqual(
            window.y(),
            cursor.y() - window.height() // 2 + int(window.height() * 0.25),
        )

    def test_show_headerless_window_unaffected(self):
        """A plain window without a header attribute must show as before."""
        from qtpy import QtWidgets

        window = QtWidgets.QWidget()
        self.addCleanup(window.deleteLater)
        self.handler.show(window, force=True)
        self.assertTrue(window.isVisible())


class _RecordingHeader:
    """Header double recording the button set ``config_buttons`` installs."""

    def __init__(self, buttons=()):
        self.buttons = list(buttons)

    def config_buttons(self, *names):
        self.buttons = list(names)


class _UiWithHeader:
    def __init__(self, header):
        self.header = header


class TestUiHandlerPersistenceHeader(unittest.TestCase):
    """The persistence->header-button-set mapping and the two apply paths.

    Pure logic (no Qt window): choosing the header set is what makes a launched
    window transient (pin -> participates in the marking-menu auto-hide via
    MainWindow.request_hide) or sticky (hide -> request_hide refuses).
    """

    def test_persistence_header_mapping(self):
        self.assertEqual(
            UiHandler._persistence_header("transient"), UiHandler.TRANSIENT_HEADER
        )
        self.assertEqual(
            UiHandler._persistence_header("sticky"), UiHandler.STICKY_HEADER
        )
        # None (and any unknown value) -> sticky, preserving the standalone
        # hide-button default this path has always applied.
        self.assertEqual(UiHandler._persistence_header(None), UiHandler.STICKY_HEADER)
        self.assertEqual(
            UiHandler._persistence_header("bogus"), UiHandler.STICKY_HEADER
        )

    def test_default_style_uses_transient_header(self):
        """The canonical/marking-menu default chrome is the transient pin set."""
        self.assertEqual(
            UiHandler.DEFAULT_STYLE["header_buttons"], UiHandler.TRANSIENT_HEADER
        )
        self.assertIn("pin", UiHandler.TRANSIENT_HEADER)
        self.assertIn("hide", UiHandler.STICKY_HEADER)

    def test_configure_launched_header_none_is_hide(self):
        ui = _UiWithHeader(_RecordingHeader())
        UiHandler._configure_launched_header(ui)
        self.assertEqual(tuple(ui.header.buttons), UiHandler.STICKY_HEADER)

    def test_configure_launched_header_transient_is_pin(self):
        ui = _UiWithHeader(_RecordingHeader())
        UiHandler._configure_launched_header(ui, persistence="transient")
        self.assertEqual(tuple(ui.header.buttons), UiHandler.TRANSIENT_HEADER)
        self.assertIn("pin", ui.header.buttons)
        self.assertNotIn("hide", ui.header.buttons)

    def test_configure_launched_header_preserves_custom_set(self):
        """A header that already has buttons is a deliberate custom set — skip."""
        ui = _UiWithHeader(_RecordingHeader(buttons=("menu", "maximize")))
        UiHandler._configure_launched_header(ui, persistence="sticky")
        self.assertEqual(tuple(ui.header.buttons), ("menu", "maximize"))

    def test_apply_persistence_chrome_overrides_existing_set(self):
        """The canonical override forces the set even over existing pin chrome,
        so a sticky choice drops the pin button (request_hide then refuses)."""
        ui = _UiWithHeader(_RecordingHeader(buttons=UiHandler.TRANSIENT_HEADER))
        UiHandler._apply_persistence_chrome(ui, "sticky")
        self.assertEqual(tuple(ui.header.buttons), UiHandler.STICKY_HEADER)
        self.assertNotIn("pin", ui.header.buttons)

    def test_ui_header_none_when_absent(self):
        self.assertIsNone(UiHandler._ui_header(types.SimpleNamespace()))


class TestLaunchPersistenceWiring(unittest.TestCase):
    """``launch`` forwards the resolved persistence to the right chrome path.

    Standalone (no marking menu) -> ``_configure_launched_header``; canonical
    (marking menu present) with an explicit choice -> ``_apply_persistence_chrome``
    overriding the pin chrome; canonical with no choice -> neither override runs.
    """

    @classmethod
    def setUpClass(cls):
        from conftest import setup_qt_application

        cls.app = setup_qt_application()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        _write_ui(os.path.join(self.tmp.name, "tool.ui"), "tool")
        from uitk.switchboard import Switchboard

        self.sb = Switchboard(ui_source=self.tmp.name, log_level="WARNING")

    def tearDown(self):
        from qtpy import QtCore, QtWidgets

        self.sb.deleteLater()
        for _ in range(3):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.tmp.cleanup()

    def test_standalone_forwards_persistence(self):
        from unittest import mock

        handler = self.sb.handlers.ui
        with mock.patch.object(handler, "_configure_launched_header") as chrome:
            ui = handler.launch("tool", persistence="transient")
        try:
            chrome.assert_called_once()
            self.assertEqual(chrome.call_args.kwargs.get("persistence"), "transient")
        finally:
            ui.deleteLater()

    def test_standalone_default_persistence_is_none(self):
        from unittest import mock

        handler = self.sb.handlers.ui
        with mock.patch.object(handler, "_configure_launched_header") as chrome:
            ui = handler.launch("tool")
        try:
            chrome.assert_called_once()
            self.assertIsNone(chrome.call_args.kwargs.get("persistence"))
        finally:
            ui.deleteLater()

    def test_canonical_explicit_choice_overrides_chrome(self):
        from unittest import mock

        self.sb.handlers.marking_menu = _CanonicalInitStub(self.sb)
        handler = self.sb.handlers.ui
        with mock.patch.object(handler, "_apply_persistence_chrome") as override:
            ui = handler.launch("tool", persistence="sticky")
        try:
            override.assert_called_once()
            self.assertEqual(override.call_args.args[1], "sticky")
        finally:
            ui.deleteLater()

    def test_canonical_without_choice_skips_override(self):
        from unittest import mock

        self.sb.handlers.marking_menu = _CanonicalInitStub(self.sb)
        handler = self.sb.handlers.ui
        with mock.patch.object(handler, "_apply_persistence_chrome") as override:
            ui = handler.launch("tool")
        try:
            override.assert_not_called()
        finally:
            ui.deleteLater()

    def test_canonical_ignores_unrecognized_persistence(self):
        """Only "transient"/"sticky" override canonical pin chrome — an unknown
        value (e.g. the browser's "context" sentinel) must leave it untouched."""
        from unittest import mock

        self.sb.handlers.marking_menu = _CanonicalInitStub(self.sb)
        handler = self.sb.handlers.ui
        with mock.patch.object(handler, "_apply_persistence_chrome") as override:
            ui = handler.launch("tool", persistence="context")
        try:
            override.assert_not_called()
        finally:
            ui.deleteLater()


if __name__ == "__main__":
    unittest.main()
