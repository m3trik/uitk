# !/usr/bin/python
# coding=utf-8
"""Unit tests for the tooltip mixin: the presenter, the bind surface, and the
Qt side of the DSL.

The DSL itself (``fmt`` / ``kbd`` / ``hl`` / ``wrap`` / ``display_ms`` ...) is
``pythontk.TooltipFormat`` and is tested in pythontk's ``test_tooltip_format``;
what stays here needs Qt -- that the headless plain/rich detector agrees with
``Qt.mightBeRichText``, that managed widgets show their tips through the
presenter, and that the retired import path still resolves.
"""

import sys
import types
import unittest
import importlib.util
from pathlib import Path

from qtpy import QtWidgets

from conftest import setup_qt_application
from pythontk import TooltipFormat


class TestReachability(unittest.TestCase):
    """The DSL must be reachable without importing uitk internals — consumers
    (tentacle slots, DCC panels) build tooltips off the objects they already
    hold: a registered widget, or the Switchboard."""

    def test_proxy_carries_the_format_dsl(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipProxy

        # widget.tooltip.fmt(...) alongside widget.tooltip.bind(...)
        self.assertTrue(issubclass(TooltipProxy, TooltipFormat))
        for name in (
            "fmt",
            "kbd",
            "hl",
            "placeholder_preview",
            "stored_items",
            "wrap",
            "display_ms",
            "bind",
        ):
            self.assertTrue(hasattr(TooltipProxy, name), name)

    def test_switchboard_namespace_is_the_superset(self):
        """sb owns the surface; the per-widget proxy is the convenience form.

        The switchboard namespace must carry everything the widget proxy does
        (so `sb.tooltip.<x>` never surprises), plus the batch `bind` only it can
        serve — resolving a "chk000-2" range needs the switchboard's resolver.
        """
        from uitk.switchboard import Switchboard
        from uitk.widgets.mixins.tooltip_mixin import TooltipNamespace, TooltipProxy

        self.assertTrue(issubclass(TooltipNamespace, TooltipFormat))
        proxy_surface = {n for n in dir(TooltipProxy) if not n.startswith("_")}
        ns_surface = {n for n in dir(TooltipNamespace) if not n.startswith("_")}
        self.assertTrue(
            proxy_surface <= ns_surface,
            f"widget.tooltip exposes what sb.tooltip lacks: {proxy_surface - ns_surface}",
        )
        sb = Switchboard()
        self.assertIsInstance(sb.tooltip, TooltipNamespace)
        self.assertIn("<b>Title</b>", sb.tooltip.fmt(title="Title"))


class TestModuleInvariant(unittest.TestCase):
    """The module states it carries no top-level function definitions (helpers live
    on classes, per the package standard). Pin it — it was broken once already."""

    def test_no_top_level_functions(self):
        import ast
        import inspect

        from uitk.widgets.mixins import tooltip_mixin

        tree = ast.parse(inspect.getsource(tooltip_mixin))
        offenders = [
            n.name
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(offenders, [], f"module-level def(s): {offenders}")


class TestBind(unittest.TestCase):
    """`bind` installs a lazy provider; both entry points share one installer."""

    @classmethod
    def setUpClass(cls):
        cls.app = setup_qt_application()

    def _widget(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipProxy

        w = QtWidgets.QWidget()
        w.tooltip = TooltipProxy(w)
        return w

    @staticmethod
    def _filter_of(widget):
        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        return widget.property(TooltipPresenter._FILTER_PROP)

    @staticmethod
    def _hover(widget):
        """Deliver a real QEvent.ToolTip so the installed provider(s) actually run."""
        from qtpy import QtCore, QtGui

        pos = QtCore.QPoint(0, 0)
        QtWidgets.QApplication.sendEvent(
            widget, QtGui.QHelpEvent(QtCore.QEvent.ToolTip, pos, pos)
        )

    def test_widget_bind_installs_a_provider(self):
        w = self._widget()
        w.tooltip.bind(lambda: "live")
        self.assertIsNotNone(self._filter_of(w))
        self._hover(w)
        self.assertEqual(w.toolTip(), "live")

    def test_provider_is_re_evaluated_on_every_hover(self):
        w = self._widget()
        state = {"n": 0}

        def provider():
            state["n"] += 1
            return f"call {state['n']}"

        w.tooltip.bind(provider)
        self._hover(w)
        self.assertEqual(w.toolTip(), "call 1")
        self._hover(w)
        self.assertEqual(w.toolTip(), "call 2")

    def test_rebinding_replaces_rather_than_stacks(self):
        """Regression: the filter is tracked on the WIDGET, so binding twice — by
        either route — swaps the provider instead of layering event filters.

        Qt runs event filters newest-first, so a *stacked* older provider would
        run LAST and win, leaving the stale "first" text. The widget keeps ONE
        presenter filter for life (re-installing it would also move it to the
        front of the queue); a rebind swaps the provider on it.
        """
        from uitk.switchboard import Switchboard

        w = self._widget()
        w.tooltip.bind(lambda: "first")
        first = self._filter_of(w)
        Switchboard().tooltip.bind(w, lambda: "second")
        self.assertIs(first, self._filter_of(w))
        self._hover(w)
        self.assertEqual(w.toolTip(), "second")

    def test_switchboard_bind_accepts_one_widget_or_many(self):
        from uitk.switchboard import Switchboard

        sb = Switchboard()
        a, b = self._widget(), self._widget()
        self.assertEqual(sb.tooltip.bind(a, lambda: "x"), [a])
        self.assertEqual(sb.tooltip.bind([a, b], lambda: "x"), [a, b])
        self.assertIsNotNone(self._filter_of(b))

    def test_unresolvable_name_pattern_says_what_to_do(self):
        """A range needs a UI to resolve against; the failure must name the fix
        rather than surface the resolver's bare 'expected QWidget, got NoneType'."""
        from uitk.switchboard import Switchboard

        sb = Switchboard()  # no ui_source, so current_ui resolves to None
        self.assertIsNone(sb.current_ui)
        with self.assertRaises(ValueError) as ctx:
            sb.tooltip.bind("chk000-2", lambda: "x")
        self.assertIn("ui=", str(ctx.exception))

    def test_bind_tolerates_a_dead_widget(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipProxy

        w = QtWidgets.QWidget()
        proxy = TooltipProxy(w)
        del w
        proxy.bind(lambda: "x")  # must not raise


#: 85 characters, one sentence -- over any readable soft width on its own.
_SENT = (
    "Exports the selected objects to the configured output folder using the "
    "active preset."
)


class TestWrapKeepsTheTextFormat(unittest.TestCase):
    """Qt picks plain vs rich with ``Qt.mightBeRichText`` -- and only from the
    FIRST line. ``wrap`` must land on the same side, or it would turn a plain
    tooltip holding ``<Enter>`` into HTML that swallows the key name."""

    W, S = 60, 15

    @classmethod
    def setUpClass(cls):
        setup_qt_application()

    def test_plain_with_an_unknown_tag_stays_plain(self):
        from qtpy import QtGui

        text = "Press <Enter> to confirm. " + " ".join([_SENT] * 2)
        self.assertFalse(QtGui.Qt.mightBeRichText(text))
        wrapped = TooltipFormat.wrap(text, width=self.W, slack=self.S)  # auto-detect
        self.assertFalse(QtGui.Qt.mightBeRichText(wrapped))
        self.assertIn("<Enter>", wrapped)
        self.assertIn("\n", wrapped)

    def test_rich_stays_rich(self):
        from qtpy import QtGui

        wrapped = TooltipFormat.wrap(f"<b>Export</b> {_SENT} {_SENT}")
        self.assertTrue(QtGui.Qt.mightBeRichText(wrapped))

    def test_the_qt_free_detector_agrees_with_qt(self):
        """The headless fallback (no binding) must classify exactly as Qt does."""
        from qtpy import QtGui

        corpus = [
            "",
            "plain",
            "  <b>x</b>",
            "Press <Enter> to go",
            "a\n<b>x</b>",
            "<!-- c --><b>x</b>",
            "a &lt; b",
            "<br/>x",
            "< b>x",
            "<B>x</B>",
            "<h1 >x",
            "  <!DOCTYPE html>",
            "<?xml version='1.0'?><b>x</b>",
            "<link>x",
            "<del>x",
            "<mark>x",
            "<table><tr><td>x",
            "<qt>x",
            "<nobr>x",
            "<font color=red>x",
            "<span style='a:b'>x",
            "a<b",
            "<b",
            "x <img src='a.png'>",
            "<!x>",
            "<ul><li>a",
        ]
        for text in corpus:
            self.assertEqual(
                TooltipFormat._is_rich_port(text),
                bool(QtGui.Qt.mightBeRichText(text)),
                repr(text),
            )


class TestPresenter(unittest.TestCase):
    """Managed widgets show their tooltip through the presenter -- wrapped, and up
    for the dynamic display time. Driven through real ``QEvent.ToolTip`` delivery
    and read back from ``QToolTip``, not from the presenter's own bookkeeping."""

    LONG = " ".join([_SENT] * 3)

    @classmethod
    def setUpClass(cls):
        cls.app = setup_qt_application()

    def setUp(self):
        self._widgets = []

    def tearDown(self):
        QtWidgets.QToolTip.hideText()
        for w in self._widgets:
            w.close()
            w.deleteLater()
        self.app.processEvents()

    def _show(self, widget):
        self._widgets.append(widget)
        widget.resize(240, 120)
        widget.show()
        self.app.processEvents()
        return widget

    @staticmethod
    def _hover(widget, pos=None):
        from qtpy import QtCore, QtGui

        pos = pos or QtCore.QPoint(2, 2)
        QtWidgets.QApplication.sendEvent(
            widget,
            QtGui.QHelpEvent(QtCore.QEvent.ToolTip, pos, widget.mapToGlobal(pos)),
        )

    def _capture_show_text(self):
        """Record every QToolTip.showText call while still letting it show."""
        from unittest import mock

        calls = []
        original = QtWidgets.QToolTip.showText

        def _record(*args):
            calls.append(args)
            return original(*args)

        patcher = mock.patch.object(QtWidgets.QToolTip, "showText", new=_record)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def test_an_unmanaged_widget_shows_qts_raw_text(self):
        """Control: the baseline the presenter exists to change."""
        w = self._show(QtWidgets.QPushButton("x"))
        w.setToolTip(self.LONG)
        self._hover(w)
        self.assertEqual(QtWidgets.QToolTip.text(), self.LONG)

    def test_a_managed_widget_shows_the_wrapped_text(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        w = self._show(QtWidgets.QPushButton("x"))
        w.setToolTip(self.LONG)
        TooltipPresenter.manage(w)
        self._hover(w)
        self.assertTrue(QtWidgets.QToolTip.isVisible())
        self.assertEqual(QtWidgets.QToolTip.text(), TooltipFormat.wrap(self.LONG))
        self.assertEqual(w.toolTip(), self.LONG, "the authored text is left alone")

    def test_the_display_time_scales_with_the_content(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        calls = self._capture_show_text()
        w = self._show(QtWidgets.QPushButton("x"))
        w.setToolTip(self.LONG)
        TooltipPresenter.manage(w)
        self._hover(w)
        self.assertEqual(calls[-1][-1], TooltipFormat.display_ms(self.LONG))

    def test_an_explicit_widget_duration_wins(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        calls = self._capture_show_text()
        w = self._show(QtWidgets.QPushButton("x"))
        w.setToolTip(self.LONG)
        w.setToolTipDuration(1234)
        TooltipPresenter.manage(w)
        self._hover(w)
        self.assertEqual(calls[-1][-1], 1234)

    def test_the_dynamic_display_time_can_be_switched_off(self):
        from unittest import mock

        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        calls = self._capture_show_text()
        w = self._show(QtWidgets.QPushButton("x"))
        w.setToolTip(self.LONG)
        TooltipPresenter.manage(w)
        with mock.patch.object(TooltipPresenter, "DYNAMIC_DURATION", False):
            self._hover(w)
        self.assertEqual(calls[-1][-1], -1, "-1 hands the timing back to Qt")

    def test_a_bound_provider_feeds_the_presenter(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipProxy

        w = self._show(QtWidgets.QPushButton("x"))
        TooltipProxy(w).bind(lambda: self.LONG)
        self._hover(w)
        self.assertEqual(w.toolTip(), self.LONG)
        self.assertEqual(QtWidgets.QToolTip.text(), TooltipFormat.wrap(self.LONG))

    def test_manage_is_idempotent(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        w = self._show(QtWidgets.QPushButton("x"))
        first = TooltipPresenter.manage(w)
        self.assertIs(TooltipPresenter.manage(w), first)

    def test_item_view_item_tooltips_are_wrapped(self):
        from qtpy import QtCore

        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        view = self._show(QtWidgets.QListWidget())
        view.addItem("with tip")
        view.item(0).setData(QtCore.Qt.ToolTipRole, self.LONG)
        TooltipPresenter.manage(view)
        self._hover(view.viewport(), view.visualItemRect(view.item(0)).center())
        self.assertEqual(QtWidgets.QToolTip.text(), TooltipFormat.wrap(self.LONG))

    def test_an_item_without_a_tip_falls_through_to_the_views_own(self):

        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        view = self._show(QtWidgets.QListWidget())
        view.addItem("no tip")
        view.setToolTip(self.LONG)
        TooltipPresenter.manage(view)
        self._hover(view.viewport(), view.visualItemRect(view.item(0)).center())
        self.assertEqual(QtWidgets.QToolTip.text(), TooltipFormat.wrap(self.LONG))

    def test_combo_popup_item_tooltips_are_wrapped(self):
        from qtpy import QtCore

        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        combo = self._show(QtWidgets.QComboBox())
        combo.addItems(["a", "b"])
        combo.setItemData(1, self.LONG, QtCore.Qt.ToolTipRole)
        TooltipPresenter.manage(combo)
        combo.showPopup()
        self.addCleanup(combo.hidePopup)
        self.app.processEvents()
        view = combo.view()
        rect = view.visualRect(combo.model().index(1, 0))
        self._hover(view.viewport(), rect.center())
        self.assertEqual(QtWidgets.QToolTip.text(), TooltipFormat.wrap(self.LONG))

    def test_qt_keeps_the_explicit_rich_breaks(self):
        """Sizing guard: laid out like Qt's tooltip label, the wrapped rich text is
        exactly its own lines tall -- Qt did not squeeze and re-wrap it."""
        from qtpy import QtGui

        text = f"<p>{self.LONG}</p>"
        wrapped = TooltipFormat.wrap(text)

        def height(html):
            label = QtWidgets.QLabel()
            label.setFont(QtWidgets.QToolTip.font())
            label.setWordWrap(True)  # what QTipLabel does for rich text
            label.setText(html)
            return label.sizeHint().height()

        line = QtGui.QFontMetrics(QtWidgets.QToolTip.font()).lineSpacing()
        lines = wrapped.count("<br>") + 1
        self.assertLess(height(wrapped), (lines + 1) * line)
        # Control: the same breaks WITHOUT the container are squeezed taller.
        bare = wrapped.split(">", 1)[1].rsplit("</div>", 1)[0]
        self.assertGreater(height(bare), height(wrapped))

    def test_graphics_item_tooltips_are_wrapped(self):
        """A graphics item's tooltip (the sequencer's clips and marker notes) is
        shown by the scene over the view's viewport -- managed with the view."""
        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        view = QtWidgets.QGraphicsView()
        scene = QtWidgets.QGraphicsScene(view)
        view.setScene(scene)
        item = scene.addRect(0, 0, 60, 30)
        item.setToolTip(self.LONG)
        self._show(view)
        TooltipPresenter.manage(view)
        self._hover(
            view.viewport(), view.mapFromScene(item.sceneBoundingRect().center())
        )
        self.assertEqual(QtWidgets.QToolTip.text(), TooltipFormat.wrap(self.LONG))


class TestCompositesJoinThePresenter(unittest.TestCase):
    """What uitk builds in code is never registered, so each composite hands
    its tooltip-bearing parts to the presenter where it builds them."""

    @classmethod
    def setUpClass(cls):
        cls.app = setup_qt_application()

    def assertTipsManaged(self, root):
        """Every widget under *root* that carries a tooltip is managed."""
        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        tipped = [w for w in root.findChildren(QtWidgets.QWidget) if w.toolTip()]
        self.assertTrue(tipped, "the fixture built nothing with a tooltip")
        unmanaged = [
            f"{type(w).__name__} {w.toolTip()[:40]!r}"
            for w in tipped
            if w.property(TooltipPresenter._FILTER_PROP) is None
        ]
        self.assertEqual(unmanaged, [])

    def test_footer_action_buttons(self):
        from uitk.widgets.footer import Footer

        footer = Footer()
        self.addCleanup(footer.deleteLater)
        footer.add_action_button(text="X", tooltip="Do the thing.")
        self.assertTipsManaged(footer)

    def test_option_box_options(self):
        """Every option's widget comes out of ``BaseOption.widget``."""
        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter
        from uitk.widgets.optionBox.options.browse import BrowseOption

        button = BrowseOption(tooltip="Pick a file.").widget
        self.addCleanup(button.deleteLater)
        self.assertIsNotNone(button.property(TooltipPresenter._FILTER_PROP))

    def test_tree_header_action_buttons(self):
        from uitk.widgets.treeWidget import TreeWidget

        tree = TreeWidget()
        self.addCleanup(tree.deleteLater)
        tree.header_actions.add("x", "close", tooltip="Close it.")
        self.assertTipsManaged(tree)

    def test_window_panel_rows(self):
        from uitk.widgets.windowPanel import WindowPanel

        panel = WindowPanel(title="Probe")
        self.addCleanup(panel.deleteLater)
        panel.add("QLineEdit", label="Search in", hint="Searched recursively.")
        self.assertTipsManaged(panel)

    def test_menu_action_buttons(self):
        from uitk.widgets.menu import ActionButtonManager, _ActionButtonConfig

        host = QtWidgets.QWidget()
        self.addCleanup(host.deleteLater)
        manager = ActionButtonManager(host)
        manager.add_button("apply", _ActionButtonConfig("Apply", tooltip="Run it."))
        self.addCleanup(manager.container.deleteLater)
        self.assertTipsManaged(manager.container)

    def test_form_panel_fields(self):
        from uitk.widgets.formPanel import FormPanel

        panel = FormPanel([{"name": "count", "value": 3, "hint": "How many."}])
        self.addCleanup(panel.deleteLater)
        self.assertTipsManaged(panel)

    def test_transport_controls(self):
        from uitk.widgets.sequencer import SequencerWidget
        from uitk.widgets.sequencer._transport_controls import TransportControls

        sequencer = SequencerWidget()
        self.addCleanup(sequencer.deleteLater)
        controls = TransportControls(sequencer)
        self.addCleanup(controls.deleteLater)
        self.assertTipsManaged(controls)

    def test_sequencer_timeline_items(self):
        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter
        from uitk.widgets.sequencer import SequencerWidget

        sequencer = SequencerWidget()
        self.addCleanup(sequencer.deleteLater)
        viewport = sequencer._timeline.viewport()
        self.assertIsNotNone(viewport.property(TooltipPresenter._FILTER_PROP))


class TestImportableWithoutQt(unittest.TestCase):
    """The retired DSL path must still resolve with no Qt binding available.

    ``TooltipFormat`` is a pure string builder, and the ecosystem authors its
    tooltip text on Qt-free engine surface — the mayatk/blendertk scene-exporter
    task definitions, which blendertk's suite builds under ``blender
    --background``, an interpreter with no Qt at all. It now lives in pythontk;
    until its alias here is removed (uitk 1.7.0) a caller still importing
    ``uitk.widgets.mixins.tooltip_mixin.TooltipFormat`` headless must get the
    one pythontk class (with a DeprecationWarning), not an ImportError -- so the
    optional Qt import stays a load-bearing contract for that window.

    The module is loaded from its path (not imported by name) so the real
    already-imported copy is left alone.
    """

    MODULE = (
        Path(__file__).resolve().parents[1] / "uitk/widgets/mixins/tooltip_mixin.py"
    )

    def _load_without(self, qtpy_stub):
        """Exec the module with *qtpy_stub* standing in for qtpy."""
        original = sys.modules.get("qtpy")
        if qtpy_stub is None:
            sys.modules["qtpy"] = None  # forces ModuleNotFoundError on import
        else:
            sys.modules["qtpy"] = qtpy_stub
        try:
            spec = importlib.util.spec_from_file_location(
                "tooltip_mixin_noqt", str(self.MODULE)
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        finally:
            if original is None:
                sys.modules.pop("qtpy", None)
            else:
                sys.modules["qtpy"] = original

    def _retired_dsl(self, mod):
        """``mod.TooltipFormat`` through the alias: warns, and is pythontk's."""
        with self.assertWarns(DeprecationWarning):
            fmt = mod.TooltipFormat
        self.assertIs(fmt, TooltipFormat)
        return fmt

    def test_dsl_works_with_qtpy_absent(self):
        mod = self._load_without(None)
        self.assertIsNone(mod.QtCore)
        fmt = self._retired_dsl(mod)
        self.assertIn("<b>T</b>", fmt.fmt(title="T"))
        # Nothing headless binds a provider; the filter just needs a valid base.
        self.assertIs(mod._TooltipFilter.__mro__[1], object)
        # wrap / display_ms are pure string work, so they run headless too.
        self.assertIn("\n", fmt.wrap(" ".join([_SENT] * 2)))
        self.assertGreater(fmt.display_ms(_SENT), 0)

    def test_retired_path_is_the_pythontk_class(self):
        from uitk.widgets.mixins import tooltip_mixin

        self._retired_dsl(tooltip_mixin)

    def test_dsl_works_when_qtpy_finds_no_bindings(self):
        # qtpy INSTALLED but with no binding raises QtBindingsNotFoundError,
        # which is an ImportError but NOT a ModuleNotFoundError — guarding on
        # the narrower class let this shape through.
        from qtpy import QtBindingsNotFoundError

        stub = types.ModuleType("qtpy")

        def _raise(name):
            raise QtBindingsNotFoundError()

        stub.__getattr__ = _raise
        mod = self._load_without(stub)
        self.assertIsNone(mod.QtWidgets)
        self.assertIn("<li>a</li>", self._retired_dsl(mod).fmt(bullets=["a"]))


if __name__ == "__main__":
    unittest.main()
