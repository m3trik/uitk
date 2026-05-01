# !/usr/bin/python
# coding=utf-8
"""Unit tests for SwitchboardBrowser.

Covers:
- Model lists all registry entries (loaded and unloaded)
- Tag computation (filename + source + XML) without loading
- Search: scope switching, comma-delimited terms, glob support
- Tag chip AND-filter
- Hide system: per-UI, per-tag; visible/hidden/all modes
- on_ui_registered triggers row insertion
- on_ui_tags_changed triggers row refresh
- Browser is not added to switchboard registry/loaded_ui (self-exclusion)
- Launch button label switches between Launch and Focus based on visibility
"""
import os
import tempfile
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtWidgets
from uitk.switchboard import Switchboard
from uitk.widgets.editors.switchboard_browser import (
    SwitchboardBrowser,
    SwitchboardBrowserModel,
    TagEditDialog,
    SHOW_VISIBLE,
    SHOW_HIDDEN,
    SHOW_ALL,
    SCOPE_NAME,
    SCOPE_TAGS,
    SCOPE_BOTH,
)


def _write_ui(path, name, tags_csv=None):
    tag_block = ""
    if tags_csv is not None:
        tag_block = (
            f'<property name="uitk_tags" stdset="0">'
            f"<string>{tags_csv}</string></property>"
        )
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>{name.capitalize()}</class>
 <widget class="QMainWindow" name="{name}">
  {tag_block}
 </widget>
</ui>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class BrowserBase(QtBaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        _write_ui(os.path.join(self.dir, "alpha.ui"), "alpha", "anim,rig")
        _write_ui(os.path.join(self.dir, "beta.ui"), "beta", "anim")
        _write_ui(os.path.join(self.dir, "gamma.ui"), "gamma", "")
        # Fresh settings namespace per test to avoid cross-test pollution.
        # ``clear()`` removes the keys so first-time defaults take effect on
        # the next read (setting them to None would store None and override
        # the default).
        self.sb = Switchboard(ui_source=self.dir, log_level="WARNING")
        self.sb.settings.branch("ui_browser").clear()
        self.browser = SwitchboardBrowser(self.sb)

    def tearDown(self):
        self.browser.deleteLater()
        self.tmp.cleanup()
        super().tearDown()

    def proxy_names(self):
        m = self.browser._proxy
        return [m.index(i, 0).data() for i in range(m.rowCount())]


class ModelListsRegistry(BrowserBase):
    def test_lists_all_entries(self):
        self.assertEqual(self.browser._model.rowCount(), 3)
        self.assertEqual(
            sorted(self.browser._model._names), ["alpha", "beta", "gamma"]
        )

    def test_tags_without_loading(self):
        self.assertEqual(
            self.browser._model._all_tags_for("alpha"), {"anim", "rig"}
        )
        self.assertEqual(self.browser._model._all_tags_for("beta"), {"anim"})
        self.assertEqual(self.browser._model._all_tags_for("gamma"), set())
        # None of the UIs should be loaded just because the model listed them
        self.assertEqual(len(list(self.sb.loaded_ui.values())), 0)

    def test_unique_tags(self):
        self.assertEqual(self.browser._model.all_unique_tags(), ["anim", "rig"])


class SearchScope(BrowserBase):
    def test_search_substring_with_glob_wrap(self):
        self.browser._search.setText("alph")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha"])

    def test_search_comma_delimited(self):
        self.browser._search.setText("alph,bet")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha", "beta"])

    def test_search_explicit_glob(self):
        self.browser._search.setText("a*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha"])

    def test_scope_tags_only(self):
        self.browser._scope.setCurrentText(SCOPE_TAGS)
        self.browser._search.setText("rig")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha"])

    def test_scope_name_only_excludes_tag_match(self):
        self.browser._scope.setCurrentText(SCOPE_NAME)
        self.browser._search.setText("anim")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), [])

    def test_scope_both(self):
        self.browser._scope.setCurrentText(SCOPE_BOTH)
        self.browser._search.setText("anim")
        self.browser._apply_filter()
        # alpha and beta both have anim tag; haystack=name+tags so both match
        self.assertEqual(self.proxy_names(), ["alpha", "beta"])


class TagChipFilter(BrowserBase):
    def test_chip_and_filter(self):
        # Activate "rig" chip — only alpha has it
        self.browser._on_chip_toggled("rig", True)
        self.assertEqual(self.proxy_names(), ["alpha"])

    def test_two_chips_and(self):
        self.browser._on_chip_toggled("anim", True)
        self.browser._on_chip_toggled("rig", True)
        # AND: only alpha has both
        self.assertEqual(self.proxy_names(), ["alpha"])


class HideSystem(BrowserBase):
    def test_hide_ui(self):
        self.browser._toggle_hide_ui("alpha", hide=True)
        self.assertEqual(self.proxy_names(), ["beta", "gamma"])
        # Switch to hidden mode
        self.browser._show.setCurrentText(SHOW_HIDDEN)
        self.assertEqual(self.proxy_names(), ["alpha"])

    def test_hide_by_tag(self):
        self.browser._toggle_hide_tag("anim", hide=True)
        # alpha and beta both have anim tag → hidden
        self.assertEqual(self.proxy_names(), ["gamma"])
        self.browser._show.setCurrentText(SHOW_HIDDEN)
        self.assertEqual(sorted(self.proxy_names()), ["alpha", "beta"])

    def test_show_all(self):
        self.browser._toggle_hide_ui("alpha", hide=True)
        self.browser._show.setCurrentText(SHOW_ALL)
        self.assertEqual(self.proxy_names(), ["alpha", "beta", "gamma"])

    def test_unhide_all(self):
        self.browser._toggle_hide_ui("alpha", hide=True)
        self.browser._toggle_hide_tag("anim", hide=True)
        self.browser._on_unhide_all()
        self.assertEqual(self.browser.hidden_uis, set())
        self.assertEqual(self.browser.hidden_tags, set())
        self.assertEqual(self.proxy_names(), ["alpha", "beta", "gamma"])

    def test_persistence_across_reinstantiation(self):
        self.browser._toggle_hide_ui("alpha", hide=True)
        # Re-instantiate browser with the same switchboard (shares settings)
        self.browser.deleteLater()
        self.browser = SwitchboardBrowser(self.sb)
        self.assertIn("alpha", self.browser.hidden_uis)


class LiveSignalUpdates(BrowserBase):
    def test_on_ui_registered_inserts_row(self):
        with tempfile.TemporaryDirectory() as d2:
            _write_ui(os.path.join(d2, "delta.ui"), "delta", "new_tag")
            self.sb.register(ui_location=d2)
        self.assertIn("delta", self.browser._model._names)

    def test_on_ui_tags_changed_refreshes(self):
        path = self.sb.registry.ui_registry.get(
            filename="alpha", return_field="filepath"
        )
        self.sb.save_ui_tags(path, ["fresh"])
        self.assertEqual(
            self.browser._model._all_tags_for("alpha"), {"fresh"}
        )

    def test_chip_set_updates_on_tag_change(self):
        # Add a brand-new tag to a UI; the chip filter row must surface it.
        path = self.sb.registry.ui_registry.get(
            filename="gamma", return_field="filepath"
        )
        self.sb.save_ui_tags(path, ["brand_new"])
        # Force the deferred refresh to run synchronously
        QtWidgets.QApplication.processEvents()
        self.assertIn("brand_new", self.browser._chip_buttons)

    def test_chip_set_drops_orphaned_tag(self):
        # Remove the only UI carrying a tag; chip should disappear.
        path = self.sb.registry.ui_registry.get(
            filename="alpha", return_field="filepath"
        )
        self.sb.save_ui_tags(path, [])  # alpha had anim+rig, now nothing
        # beta still has anim, so anim chip remains; rig must drop
        QtWidgets.QApplication.processEvents()
        self.assertNotIn("rig", self.browser._chip_buttons)
        self.assertIn("anim", self.browser._chip_buttons)


class SelfExclusion(BrowserBase):
    def test_browser_not_in_loaded_ui(self):
        self.assertNotIn(
            "switchboard_browser", list(self.sb.loaded_ui.keys())
        )

    def test_browser_not_in_registry(self):
        names = self.sb.registry.ui_registry.get("filename") or []
        self.assertNotIn("switchboard_browser", names)


class FilterEnableToggle(BrowserBase):
    def test_filter_disabled_ignores_text_query(self):
        # alpha matches "alph" while filter is enabled
        self.browser._search.setText("alph")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha"])
        # Disable the filter — text query should be ignored
        self.browser._set_filter_enabled(False)
        self.assertEqual(self.proxy_names(), ["alpha", "beta", "gamma"])
        # Re-enable — query takes effect again
        self.browser._set_filter_enabled(True)
        self.assertEqual(self.proxy_names(), ["alpha"])

    def test_filter_enabled_persists(self):
        self.browser._set_filter_enabled(False)
        self.assertFalse(
            self.sb.settings.branch("ui_browser").value("filter_enabled", True)
        )

    def test_chip_filter_still_applies_when_text_filter_disabled(self):
        # Hide-by-tag and chip filters operate independently of the text filter
        self.browser._set_filter_enabled(False)
        self.browser._on_chip_toggled("rig", True)  # only alpha has rig
        self.assertEqual(self.proxy_names(), ["alpha"])


class LaunchDefaults(BrowserBase):
    def test_marking_menu_style_defaults(self):
        # Frameless / Translucent / Restore-geometry default ON.
        self.assertTrue(self.browser._cb_frameless.isChecked())
        self.assertTrue(self.browser._cb_translucent.isChecked())
        self.assertTrue(self.browser._cb_restore.isChecked())
        # On-top defaults ON so the launched UI shares the browser's
        # z-class — otherwise the on-top browser covers it.
        self.assertTrue(self.browser._cb_on_top.isChecked())
        # No "Start pinned" option — pinning is the launched window's own
        # header concern, replaced here by an explicit hide button.
        self.assertFalse(hasattr(self.browser, "_cb_pinned"))

    def test_theme_combobox_lists_registered_themes(self):
        from uitk.widgets.mixins.style_sheet import StyleSheet

        items = [
            self.browser._cmb_theme.itemText(i)
            for i in range(self.browser._cmb_theme.count())
        ]
        # Every theme registered with StyleSheet must appear in the combobox
        for theme_name in StyleSheet.themes:
            self.assertIn(theme_name, items)
        # Default theme is "dark"
        self.assertEqual(self.browser._cmb_theme.currentText(), "dark")


class ExcludeFilter(BrowserBase):
    def test_exclude_substring_drops_matches(self):
        self.browser._exclude.setText("alph")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["beta", "gamma"])

    def test_exclude_glob(self):
        self.browser._exclude.setText("a*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["beta", "gamma"])

    def test_exclude_combined_with_include(self):
        # Include any of {alpha, beta, gamma}; exclude beta
        self.browser._search.setText("a")  # matches alpha + beta + gamma
        self.browser._exclude.setText("beta")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha", "gamma"])

    def test_exclude_persisted(self):
        self.browser._exclude.setText("foo")
        self.assertEqual(
            self.sb.settings.branch("ui_browser").value("exclude"), "foo"
        )


class LaunchParenting(BrowserBase):
    def test_launched_ui_is_reparented_to_switchboard_parent(self):
        # Give the switchboard a parent (acts as the host DCC main window).
        # Switchboard inherits from QUiLoader (a QObject); setParent works.
        host = QtWidgets.QWidget()
        host.setObjectName("host_main_window")
        self.sb.setParent(host)
        try:
            # Launch alpha
            idx = self.browser._proxy.index(0, 0)
            self.browser._view.setCurrentIndex(idx)
            self.browser._on_action_clicked()
            QtWidgets.QApplication.processEvents()
            ui = self.sb.loaded_ui.alpha
            self.assertIs(ui.parent(), host)
        finally:
            ui.hide()
            host.deleteLater()


class ActionButton(BrowserBase):
    def test_label_is_launch_when_not_visible(self):
        # Select alpha — not visible
        idx = self.browser._proxy.index(0, 0)
        self.browser._view.setCurrentIndex(idx)
        self.browser._update_action_button()
        self.assertEqual(self.browser._action_btn.text(), "Launch")

    def test_label_switches_to_focus_when_visible(self):
        # Lazy-load alpha and force visible state via a stub override
        ui = self.sb.loaded_ui.alpha
        # The MainWindow's isVisible is what the model checks; show then verify.
        ui.show()
        self.browser._model.refresh_after_launch("alpha")

        idx = self.browser._proxy.index(
            self.proxy_names().index("alpha"), 0
        )
        self.browser._view.setCurrentIndex(idx)
        self.browser._update_action_button()
        self.assertEqual(self.browser._action_btn.text(), "Focus")
        ui.hide()


class TableLayout(BrowserBase):
    def test_model_has_four_columns(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowserModel
        self.assertEqual(self.browser._model.columnCount(), SwitchboardBrowserModel.COLUMN_COUNT)
        self.assertEqual(self.browser._model.columnCount(), 4)

    def test_tags_column_is_editable(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowserModel
        idx = self.browser._model.index(0, SwitchboardBrowserModel.COL_TAGS)
        self.assertTrue(bool(self.browser._model.flags(idx) & QtCore.Qt.ItemIsEditable))

    def test_name_column_is_not_editable(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowserModel
        idx = self.browser._model.index(0, SwitchboardBrowserModel.COL_NAME)
        self.assertFalse(bool(self.browser._model.flags(idx) & QtCore.Qt.ItemIsEditable))


class InlineTagEdit(BrowserBase):
    def test_set_data_writes_tags_to_ui_file(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowserModel
        # alpha had file tags {"foo"}; rewrite via setData on the tags column
        idx = self.browser._model.index(0, SwitchboardBrowserModel.COL_TAGS)
        self.assertTrue(self.browser._model.setData(idx, "alpha_tag, beta_tag", QtCore.Qt.EditRole))
        # File should now contain those tags
        path = self.sb.registry.ui_registry.get(filename="alpha", return_field="filepath")
        from uitk.switchboard import Switchboard
        self.assertEqual(Switchboard._parse_ui_tags(path), {"alpha_tag", "beta_tag"})

    def test_set_data_rejects_non_tags_columns(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowserModel
        idx = self.browser._model.index(0, SwitchboardBrowserModel.COL_NAME)
        self.assertFalse(self.browser._model.setData(idx, "renamed", QtCore.Qt.EditRole))


class ConfigureLaunchedHeader(QtBaseTestCase):
    """Verify _configure_launched_header behavior in isolation.

    Pure unit-style tests against the static helper — no Switchboard or
    full launch flow needed.
    """

    def test_skips_when_no_header_attr(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser

        ui = QtWidgets.QWidget()  # no `header` attr, no `findChild` match
        # Should not raise even though there's nothing to configure
        SwitchboardBrowser._configure_launched_header(ui)

    def test_skips_when_header_has_existing_buttons(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser
        from uitk.widgets.header import Header

        ui = QtWidgets.QWidget()
        ui.header = Header(parent=ui, config_buttons=["pin"])  # already configured
        existing = tuple(ui.header.buttons.keys())
        SwitchboardBrowser._configure_launched_header(ui)
        # Existing config preserved, not replaced
        self.assertEqual(tuple(ui.header.buttons.keys()), existing)

    def test_configures_when_header_buttons_empty(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser
        from uitk.widgets.header import Header

        ui = QtWidgets.QWidget()
        ui.header = Header(parent=ui, config_buttons=[])  # empty
        SwitchboardBrowser._configure_launched_header(ui)
        # The three browser-launched defaults: hide / collapse / menu
        self.assertEqual(
            set(ui.header.buttons.keys()), {"menu", "collapse", "hide"}
        )

    def test_falls_back_to_findChild(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser
        from uitk.widgets.header import Header

        ui = QtWidgets.QWidget()
        # No `.header` attribute, but findChild("header") will match
        h = Header(parent=ui, config_buttons=[])
        h.setObjectName("header")
        SwitchboardBrowser._configure_launched_header(ui)
        self.assertEqual(
            set(h.buttons.keys()), {"menu", "collapse", "hide"}
        )


class CloseButton(BrowserBase):
    def test_close_hides_visible_ui(self):
        # Launch alpha so it becomes visible
        idx = self.browser._proxy.index(0, 0)
        self.browser._view.setCurrentIndex(idx)
        self.browser._on_action_clicked()
        QtWidgets.QApplication.processEvents()
        ui = self.sb.loaded_ui.alpha
        self.assertTrue(ui.isVisible())
        # Close via the public API
        self.browser._close_ui("alpha")
        QtWidgets.QApplication.processEvents()
        self.assertFalse(ui.isVisible())

    def test_close_no_op_for_unloaded_ui(self):
        # Should not raise
        self.browser._close_ui("never_loaded_name")


class TagsRenderingHtml(BrowserBase):
    def test_inherited_tags_rendered_italic(self):
        # Register a directory with a source-tag that becomes inherited
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowserModel
        # alpha's existing tags are file-only ("foo"); we add a source tag.
        self.sb.register(ui_location=self.dir, tags={"src_tag"})
        QtWidgets.QApplication.processEvents()
        # Render the tags HTML for alpha
        idx = self.browser._proxy.index(
            self.proxy_names().index("alpha"), SwitchboardBrowserModel.COL_TAGS
        )
        html = self.browser._row_delegate._tags_html(idx)
        # Inherited tag uses italic style
        self.assertIn("font-style:italic", html)
        self.assertIn("#src_tag", html)
        # File tag does not have italic in its span
        # (the inherited italic span is closed before the file-tag span)
        file_span_start = html.find("#foo")
        file_span_open = html.rfind("<span", 0, file_span_start)
        self.assertNotIn("font-style:italic", html[file_span_open:file_span_start])


class HeaderMenuAndPresets(BrowserBase):
    def test_header_has_menu_button(self):
        # The browser configures its EditorPanel header with menu+hide
        self.assertIn("menu", self.browser._header.buttons)
        self.assertIn("hide", self.browser._header.buttons)

    def test_no_always_on_top_toggle(self):
        # The "Always on top" toggle was removed — the symptom it was
        # working around (browser disappearing when the launching popup
        # closed) is fixed at the registry level instead. The browser
        # just inherits ``EditorPanel``'s default on-top flag.
        self.assertFalse(hasattr(self.browser, "_chk_always_on_top"))
        self.assertFalse(hasattr(self.browser, "_apply_always_on_top"))
        self.assertFalse(hasattr(self.browser, "_on_always_on_top_toggled"))
        flags = self.browser.windowFlags()
        self.assertTrue(bool(flags & QtCore.Qt.WindowStaysOnTopHint))

    def test_refresh_button_exists(self):
        self.assertTrue(hasattr(self.browser, "_btn_refresh"))

    def test_export_preset_data_round_trip(self):
        # Mutate state, export, reset, import — should round-trip.
        self.browser._search.setText("alph")
        self.browser._exclude.setText("xyz")
        self.browser._scope.setCurrentText(SCOPE_TAGS)
        self.browser._show.setCurrentText(SHOW_ALL)
        self.browser._toggle_hide_ui("alpha", hide=True)
        self.browser._toggle_hide_tag("rig", hide=True)
        self.browser._cb_on_top.setChecked(True)
        self.browser._cb_frameless.setChecked(False)

        snapshot = self.browser._export_preset_data()

        # Now reset to a different state
        self.browser._search.setText("")
        self.browser._exclude.setText("")
        self.browser._scope.setCurrentText(SCOPE_NAME)
        self.browser._show.setCurrentText(SHOW_VISIBLE)
        self.browser.hidden_uis = set()
        self.browser.hidden_tags = set()
        self.browser._cb_on_top.setChecked(False)
        self.browser._cb_frameless.setChecked(True)

        # Re-import the snapshot
        self.browser._import_preset_data(snapshot)

        self.assertEqual(self.browser._search.text(), "alph")
        self.assertEqual(self.browser._exclude.text(), "xyz")
        self.assertEqual(self.browser._scope.currentText(), SCOPE_TAGS)
        self.assertEqual(self.browser._show.currentText(), SHOW_ALL)
        self.assertIn("alpha", self.browser.hidden_uis)
        self.assertIn("rig", self.browser.hidden_tags)
        self.assertTrue(self.browser._cb_on_top.isChecked())
        self.assertFalse(self.browser._cb_frameless.isChecked())

    def test_import_preset_data_tolerates_missing_keys(self):
        # Sparse preset (only some fields) should not raise
        self.browser._import_preset_data({"search_text": "expo"})
        self.assertEqual(self.browser._search.text(), "expo")

    def test_preset_manager_metadata_provider_wired(self):
        # The PresetManager on the header menu must have our hooks set.
        # Bound-method identity is unstable (each ``self.method`` access
        # creates a new wrapper), so compare equality which checks the
        # underlying function + instance.
        mgr = self.browser._header.menu.presets
        self.assertEqual(mgr.metadata_provider, self.browser._export_preset_data)
        self.assertEqual(mgr.on_metadata_loaded, self.browser._import_preset_data)


class ColumnLayout(BrowserBase):
    def test_action_columns_match_button_width(self):
        view = self.browser._view
        self.assertEqual(
            view.columnWidth(SwitchboardBrowserModel.COL_ACTION), 22
        )
        self.assertEqual(
            view.columnWidth(SwitchboardBrowserModel.COL_CLOSE), 22
        )

    def test_show_combobox_minimum_width_fits_longest_item(self):
        # The combobox + popup view minimum width must accommodate the
        # longest item ("visible") so first-show doesn't truncate.
        combo = self.browser._show
        fm = combo.fontMetrics()
        max_w = max(
            fm.horizontalAdvance(combo.itemText(i))
            for i in range(combo.count())
        )
        self.assertGreaterEqual(combo.minimumWidth(), max_w)
        self.assertGreaterEqual(combo.view().minimumWidth(), max_w)


class SwitchboardConstruction(QtBaseTestCase):
    """Verify the browser's flexible Switchboard construction.

    The constructor follows the mayatk MayaUiHandler pattern: use the
    provided switchboard, else stand one up from forwarded kwargs.
    """

    def test_uses_provided_switchboard(self):
        with tempfile.TemporaryDirectory() as d:
            _write_ui(os.path.join(d, "alpha.ui"), "alpha")
            sb = Switchboard(ui_source=d, log_level="WARNING")
            sb.settings.branch("ui_browser").clear()
            browser = SwitchboardBrowser(switchboard=sb)
            try:
                # Browser must keep the same instance, not clone it
                self.assertIs(browser.sb, sb)
                self.assertIn("alpha", browser._model._names)
            finally:
                browser.deleteLater()

    def test_creates_switchboard_when_none_provided(self):
        # Bare construction yields an empty (but valid) Switchboard
        browser = SwitchboardBrowser()
        try:
            self.assertIsInstance(browser.sb, Switchboard)
            self.assertEqual(browser._model.rowCount(), 0)
        finally:
            browser.deleteLater()

    def test_forwards_kwargs_to_new_switchboard(self):
        # ``ui_source`` (and any other Switchboard kwarg) flows through
        # to the auto-created instance.
        with tempfile.TemporaryDirectory() as d:
            _write_ui(os.path.join(d, "beta.ui"), "beta")
            browser = SwitchboardBrowser(ui_source=d, log_level="WARNING")
            try:
                browser.sb.settings.branch("ui_browser").clear()
                self.assertIn("beta", browser._model._names)
            finally:
                browser.deleteLater()

    def test_rejects_both_switchboard_and_kwargs(self):
        # Mixing an existing instance with construction kwargs is
        # ambiguous — must raise rather than silently drop the kwargs.
        sb = Switchboard(log_level="WARNING")
        try:
            with self.assertRaises(ValueError):
                SwitchboardBrowser(switchboard=sb, ui_source="/tmp/whatever")
        finally:
            # No browser was created, just clean up the switchboard
            pass


class TableHeaderAlignment(BrowserBase):
    def test_horizontal_header_titles_left_aligned(self):
        # Both titled columns should report left-aligned text via the
        # TextAlignmentRole on the model's headerData.
        for col in (
            SwitchboardBrowserModel.COL_NAME,
            SwitchboardBrowserModel.COL_TAGS,
        ):
            alignment = self.browser._model.headerData(
                col, QtCore.Qt.Horizontal, QtCore.Qt.TextAlignmentRole
            )
            self.assertIsNotNone(alignment, f"col {col} returned no alignment")
            self.assertTrue(int(alignment) & int(QtCore.Qt.AlignLeft))


class HeaderButtons(BrowserBase):
    def test_collapse_and_minimize_present(self):
        # The browser's header should expose the four window-management
        # buttons we rely on for parity with launched UIs.
        for name in ("menu", "collapse", "minimize", "hide"):
            self.assertIn(name, self.browser._header.buttons, name)


class CloseButtonRoutesThroughHeader(BrowserBase):
    def test_close_uses_header_hide_window_when_available(self):
        # Launch alpha so it becomes loaded, then attach a uitk Header so
        # we can verify _close_ui routes through Header.hide_window.
        # The test fixtures produce headerless QMainWindows; configuring
        # one explicitly gives us a faithful production-like target.
        from uitk.widgets.header import Header

        idx = self.browser._proxy.index(0, 0)
        self.browser._view.setCurrentIndex(idx)
        self.browser._on_action_clicked()
        QtWidgets.QApplication.processEvents()
        ui = self.sb.loaded_ui.alpha

        # Inject a header. _configure_launched_header normally does this
        # for us, but our test fixtures have no header in the .ui XML.
        ui.header = Header(parent=ui, config_buttons=["hide"])

        called = {"count": 0}
        original = ui.header.hide_window

        def spy():
            called["count"] += 1
            return original()

        ui.header.hide_window = spy
        try:
            self.browser._close_ui("alpha")
            QtWidgets.QApplication.processEvents()
            self.assertEqual(called["count"], 1)
            self.assertFalse(ui.isVisible())
        finally:
            ui.header.hide_window = original

    def test_close_falls_back_to_hide_for_headerless_ui(self):
        # gamma has no XML <Header> child, just a plain QMainWindow
        ui = self.sb.loaded_ui.gamma
        ui.show()
        QtWidgets.QApplication.processEvents()
        self.assertTrue(ui.isVisible())
        self.browser._close_ui("gamma")
        QtWidgets.QApplication.processEvents()
        self.assertFalse(ui.isVisible())


class FooterStatus(BrowserBase):
    def test_footer_shows_counts_when_no_selection(self):
        self.browser._view.clearSelection()
        self.browser._view.setCurrentIndex(QtCore.QModelIndex())
        self.browser._update_footer_status()
        text = self.browser.footer.statusText()
        self.assertIn("registered", text)
        self.assertIn("visible", text)
        self.assertIn("showing", text)

    def test_footer_shows_selected_ui_name_and_path(self):
        idx = self.browser._proxy.index(0, 0)  # alpha
        self.browser._view.setCurrentIndex(idx)
        self.browser._update_footer_status()
        text = self.browser.footer.statusText()
        self.assertIn("alpha", text)
        # Path of the selected UI is dimmed but present
        path = self.sb.registry.ui_registry.get(
            filename="alpha", return_field="filepath"
        )
        # Path may be HTML-escaped; check just the basename
        self.assertIn(os.path.basename(path), text)

    def test_footer_visibility_indicator_appears_on_visible_ui(self):
        # Launch alpha and verify the footer marks it visible
        idx = self.browser._proxy.index(0, 0)
        self.browser._view.setCurrentIndex(idx)
        self.browser._on_action_clicked()
        QtWidgets.QApplication.processEvents()
        self.browser._update_footer_status()
        text = self.browser.footer.statusText()
        self.assertIn("visible", text)
        # Cleanup
        self.sb.loaded_ui.alpha.hide()

    def test_footer_updates_on_selection_change(self):
        # Selecting different rows should change the footer text
        idx_alpha = self.browser._proxy.index(0, 0)
        idx_beta = self.browser._proxy.index(1, 0)
        self.browser._view.setCurrentIndex(idx_alpha)
        text_alpha = self.browser.footer.statusText()
        self.browser._view.setCurrentIndex(idx_beta)
        text_beta = self.browser.footer.statusText()
        self.assertNotEqual(text_alpha, text_beta)
        self.assertIn("alpha", text_alpha)
        self.assertIn("beta", text_beta)


class TagEditDialogTest(QtBaseTestCase):
    def test_add_and_remove(self):
        dlg = TagEditDialog("x", inherited_tags={"i1"}, file_tags={"f1"})
        self.assertEqual(dlg.tags(), {"f1"})
        dlg._line.setText("new")
        dlg._on_add()
        self.assertEqual(dlg.tags(), {"f1", "new"})
        # Select first item and remove
        dlg._list.setCurrentRow(0)
        dlg._on_remove()
        self.assertEqual(len(dlg.tags()), 1)

    def test_no_duplicates_no_commas(self):
        dlg = TagEditDialog("x", inherited_tags=set(), file_tags={"a"})
        dlg._line.setText("a")
        dlg._on_add()
        self.assertEqual(dlg.tags(), {"a"})  # unchanged
        dlg._line.setText("has,comma")
        dlg._on_add()
        self.assertEqual(dlg.tags(), {"a"})  # rejected


if __name__ == "__main__":
    unittest.main()
