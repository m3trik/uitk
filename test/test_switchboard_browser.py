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
        # Match production: the browser is meant to be shown. When hidden,
        # the optimisation in ``_defer_full_refresh`` short-circuits the
        # row-widget rebuild — that's correct for the "browser is closed"
        # case but would make tests of post-signal updates fail since the
        # test harness never opens a window.
        self.browser.resize(500, 300)
        self.browser.show()
        QtWidgets.QApplication.processEvents()

    def tearDown(self):
        # Disconnect any signal-driven slots that would fire on parent
        # destruction and reach into the (about-to-be-deleted) browser.
        try:
            self.sb.on_ui_tags_changed.disconnect()
        except (RuntimeError, TypeError):
            pass
        # Drop the browser cleanly: detach from any parent layout, then
        # schedule deletion, then DRAIN the Qt event queue so the deferred
        # delete fires inside tearDown rather than piling up across tests.
        # Without the drain, processEvents() inside a later test fires every
        # accumulated deleteLater plus its own — under PySide6 + offscreen
        # QPA this overwhelms Qt's event dispatch and segfaults inside C++
        # event filters that touch a not-quite-dead widget. Repeated
        # processEvents() calls flush DeferredDelete events fully.
        self.browser.setParent(None)
        self.browser.deleteLater()
        self.sb.deleteLater()
        for _ in range(3):
            QtWidgets.QApplication.processEvents(
                QtCore.QEventLoop.AllEvents, 50
            )
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
    def test_search_substring_with_explicit_wildcards(self):
        # Strict matching: a substring search needs explicit * wildcards.
        self.browser._search.setText("*alph*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha"])

    def test_search_bare_term_is_exact(self):
        # A bare term matches exactly — so a partial name against the
        # name+tags haystack finds nothing without wildcards.
        self.browser._search.setText("alph")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), [])

    def test_search_comma_delimited(self):
        self.browser._search.setText("*alph*, *bet*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha", "beta"])

    def test_search_explicit_glob(self):
        self.browser._search.setText("a*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha"])

    def test_scope_tags_only(self):
        self.browser.set_search_scope(SCOPE_TAGS)
        self.browser._search.setText("*rig*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha"])

    def test_scope_name_only_excludes_tag_match(self):
        self.browser.set_search_scope(SCOPE_NAME)
        self.browser._search.setText("*anim*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), [])

    def test_scope_both(self):
        self.browser.set_search_scope(SCOPE_BOTH)
        self.browser._search.setText("*anim*")
        self.browser._apply_filter()
        # alpha and beta both have anim tag; haystack=name+tags so both match
        self.assertEqual(self.proxy_names(), ["alpha", "beta"])

    def test_search_inline_negation_excludes(self):
        # "!term" inside the field carves out an inline exclusion: keep the anim
        # rows but drop alpha. Proves the FilterOption ->
        # filter_list(negate_prefix=...) wiring end-to-end.
        self.browser.set_search_scope(SCOPE_BOTH)
        self.browser._search.setText("*anim*, !*alpha*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["beta"])


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
    def _set_show_mode(self, mode):
        # uitk's custom ComboBox.setCurrentText is decorated with
        # @Signals.blockSignals to suppress in-flight emissions, so
        # programmatic text-set won't fire currentTextChanged. Real user
        # interaction goes through setCurrentIndex (no decorator), which
        # is what we mimic here.
        idx = self.browser._show.findText(mode)
        self.browser._show.setCurrentIndex(idx)

    def test_hide_ui(self):
        self.browser._toggle_hide_ui("alpha", hide=True)
        self.assertEqual(self.proxy_names(), ["beta", "gamma"])
        # Switch to hidden mode
        self._set_show_mode(SHOW_HIDDEN)
        self.assertEqual(self.proxy_names(), ["alpha"])

    def test_hide_by_tag(self):
        self.browser._toggle_hide_tag("anim", hide=True)
        # alpha and beta both have anim tag → hidden
        self.assertEqual(self.proxy_names(), ["gamma"])
        self._set_show_mode(SHOW_HIDDEN)
        self.assertEqual(sorted(self.proxy_names()), ["alpha", "beta"])

    def test_show_all(self):
        self.browser._toggle_hide_ui("alpha", hide=True)
        self._set_show_mode(SHOW_ALL)
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
        # alpha matches "*alph*" while the search filter is enabled
        self.browser._search.setText("*alph*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha"])
        # Disable the search filter — text query should be ignored
        self.browser._search_filter.set_on(False)
        self.assertEqual(self.proxy_names(), ["alpha", "beta", "gamma"])
        # Re-enable — query takes effect again
        self.browser._search_filter.set_on(True)
        self.assertEqual(self.proxy_names(), ["alpha"])

    def test_filter_enabled_persists(self):
        self.browser._search_filter.set_on(False)
        self.assertFalse(
            self.sb.settings.branch("ui_browser").value(
                "search.filter_enabled", True
            )
        )

    def test_disabling_filter_ignores_inline_exclusion(self):
        # An inline !exclusion is part of the text filter, so toggling the
        # filter off reveals everything (the exclusion stops applying too).
        self.browser._search.setText("!*alph*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["beta", "gamma"])
        self.browser._search_filter.set_on(False)
        self.assertEqual(self.proxy_names(), ["alpha", "beta", "gamma"])

    def test_chip_filter_still_applies_when_text_filter_disabled(self):
        # Hide-by-tag and chip filters operate independently of the text filter
        self.browser._search_filter.set_on(False)
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


class InlineExclude(BrowserBase):
    """Exclusion via the single search field's ``!term`` syntax (no exclude row)."""

    def test_exclude_substring_drops_matches(self):
        self.browser._search.setText("!*alph*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["beta", "gamma"])

    def test_exclude_glob(self):
        self.browser._search.setText("!a*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["beta", "gamma"])

    def test_exclude_combined_with_include(self):
        # Include anything containing 'a'; exclude beta — all in one field.
        self.browser._search.setText("*a*, !*beta*")
        self.browser._apply_filter()
        self.assertEqual(self.proxy_names(), ["alpha", "gamma"])


class LaunchParenting(BrowserBase):
    def test_launched_ui_is_reparented_to_switchboard_parent(self):
        # Give the switchboard a parent (acts as the host DCC main window).
        # Switchboard inherits from QObject; setParent works.
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


class DoubleClickLaunch(BrowserBase):
    """The footer Launch/Focus button was removed. Launching is now done via
    the per-row icon (or a double-click on the name column), so any
    integration tests that previously poked the button must drive the
    double-click path instead."""

    def test_double_click_on_name_column_launches(self):
        idx = self.browser._proxy.index(0, 0)  # alpha, name column
        self.browser._view.setCurrentIndex(idx)
        # Simulate the doubleClicked signal payload
        self.browser._on_double_click(idx)
        QtWidgets.QApplication.processEvents()
        self.assertIn("alpha", self.sb.loaded_ui)
        self.sb.loaded_ui.alpha.hide()

    def test_double_click_on_tags_column_does_not_launch(self):
        # Tags column is for inline edit; the double-click must not launch.
        idx = self.browser._proxy.index(0, SwitchboardBrowserModel.COL_TAGS)
        self.browser._on_double_click(idx)
        QtWidgets.QApplication.processEvents()
        self.assertNotIn("alpha", self.sb.loaded_ui)


class TableLayout(BrowserBase):
    def test_model_has_four_columns(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser
        self.assertEqual(self.browser._model.columnCount(), SwitchboardBrowserModel.COLUMN_COUNT)
        self.assertEqual(self.browser._model.columnCount(), 4)

    def test_tags_column_is_editable(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser
        idx = self.browser._model.index(0, SwitchboardBrowserModel.COL_TAGS)
        self.assertTrue(bool(self.browser._model.flags(idx) & QtCore.Qt.ItemIsEditable))

    def test_name_column_is_not_editable(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser
        idx = self.browser._model.index(0, SwitchboardBrowserModel.COL_NAME)
        self.assertFalse(bool(self.browser._model.flags(idx) & QtCore.Qt.ItemIsEditable))


class InlineTagEdit(BrowserBase):
    def test_set_data_writes_tags_to_ui_file(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser
        # alpha had file tags {"foo"}; rewrite via setData on the tags column
        idx = self.browser._model.index(0, SwitchboardBrowserModel.COL_TAGS)
        self.assertTrue(self.browser._model.setData(idx, "alpha_tag, beta_tag", QtCore.Qt.EditRole))
        # File should now contain those tags
        path = self.sb.registry.ui_registry.get(filename="alpha", return_field="filepath")
        from xml.etree import ElementTree as _ET
        widget = _ET.parse(path).getroot().find("widget")
        prop = next(
            p for p in widget.findall("property") if p.get("name") == "uitk_tags"
        )
        tags = {t.strip() for t in prop.find("string").text.split(",")}
        self.assertEqual(tags, {"alpha_tag", "beta_tag"})

    def test_set_data_rejects_non_tags_columns(self):
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser
        idx = self.browser._model.index(0, SwitchboardBrowserModel.COL_NAME)
        self.assertFalse(self.browser._model.setData(idx, "renamed", QtCore.Qt.EditRole))


class ConfigureLaunchedHeader(QtBaseTestCase):
    """Verify _configure_launched_header behavior in isolation.

    Pure unit-style tests against the static helper — no Switchboard or
    full launch flow needed.
    """

    def test_skips_when_no_header_attr(self):
        from uitk.handlers.ui_handler import UiHandler

        ui = QtWidgets.QWidget()  # no `header` attr, no `findChild` match
        # Should not raise even though there's nothing to configure
        UiHandler._configure_launched_header(ui)

    def test_skips_when_header_has_existing_buttons(self):
        from uitk.handlers.ui_handler import UiHandler
        from uitk.widgets.header import Header

        ui = QtWidgets.QWidget()
        ui.header = Header(parent=ui, config_buttons=["pin"])  # already configured
        existing = tuple(ui.header.buttons.keys())
        UiHandler._configure_launched_header(ui)
        # Existing config preserved, not replaced
        self.assertEqual(tuple(ui.header.buttons.keys()), existing)

    def test_configures_when_header_buttons_empty(self):
        from uitk.handlers.ui_handler import UiHandler
        from uitk.widgets.header import Header

        ui = QtWidgets.QWidget()
        ui.header = Header(parent=ui, config_buttons=[])  # empty
        UiHandler._configure_launched_header(ui)
        # The three browser-launched defaults: hide / collapse / menu
        self.assertEqual(
            set(ui.header.buttons.keys()), {"menu", "collapse", "hide"}
        )

    def test_falls_back_to_findChild(self):
        from uitk.handlers.ui_handler import UiHandler
        from uitk.widgets.header import Header

        ui = QtWidgets.QWidget()
        # No `.header` attribute, but findChild("header") will match
        h = Header(parent=ui, config_buttons=[])
        h.setObjectName("header")
        UiHandler._configure_launched_header(ui)
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
        from uitk.widgets.editors.switchboard_browser import SwitchboardBrowser
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

    def test_browser_is_not_always_on_top(self):
        # Regression guard. The browser is a *launcher*, not a config
        # surface that needs to sit above the windows it edits — so it
        # must not force itself above every other window. Matches
        # mayatk.reference_manager's behavior: parented to the host,
        # but not on-top.
        #
        # SwitchboardBrowser passes ``on_top=False`` explicitly at
        # construction; this test pins that decision.
        self.assertFalse(hasattr(self.browser, "_chk_always_on_top"))
        self.assertFalse(hasattr(self.browser, "_apply_always_on_top"))
        self.assertFalse(hasattr(self.browser, "_on_always_on_top_toggled"))
        flags = self.browser.windowFlags()
        self.assertFalse(
            bool(flags & QtCore.Qt.WindowStaysOnTopHint),
            "Browser must not set WindowStaysOnTopHint — it's a launcher, "
            "not an on-top utility. See SwitchboardBrowser.__init__'s "
            "on_top=False rationale.",
        )

    def test_refresh_button_is_in_header(self):
        # Refresh moved from a menu entry to a top-level header button —
        # one click instead of opening the menu first. Matches mayatk
        # reference_manager's pattern.
        self.assertIn("refresh", self.browser._header.buttons)
        # The old menu button is gone.
        self.assertFalse(hasattr(self.browser, "_btn_refresh"))

    def test_export_preset_data_round_trip(self):
        # Mutate state, export, reset, import — should round-trip.
        self.browser._search.setText("alph, !xyz")
        self.browser.set_search_scope(SCOPE_TAGS)
        self.browser._show.setCurrentText(SHOW_ALL)
        self.browser._toggle_hide_ui("alpha", hide=True)
        self.browser._toggle_hide_tag("rig", hide=True)
        self.browser._cb_on_top.setChecked(True)
        self.browser._cb_frameless.setChecked(False)

        snapshot = self.browser._export_preset_data()

        # Now reset to a different state
        self.browser._search.setText("")
        self.browser.set_search_scope(SCOPE_NAME)
        self.browser._show.setCurrentText(SHOW_VISIBLE)
        self.browser.hidden_uis = set()
        self.browser.hidden_tags = set()
        self.browser._cb_on_top.setChecked(False)
        self.browser._cb_frameless.setChecked(True)

        # Re-import the snapshot
        self.browser._import_preset_data(snapshot)

        self.assertEqual(self.browser._search.text(), "alph, !xyz")
        self.assertEqual(self.browser._search_filter.scope, SCOPE_TAGS)
        self.assertEqual(self.browser._show.currentText(), SHOW_ALL)
        self.assertIn("alpha", self.browser.hidden_uis)
        self.assertIn("rig", self.browser.hidden_tags)
        self.assertTrue(self.browser._cb_on_top.isChecked())
        self.assertFalse(self.browser._cb_frameless.isChecked())

    def test_import_preset_data_tolerates_missing_keys(self):
        # Sparse preset (only the search.text field) should not raise.
        self.browser._import_preset_data({"search": {"text": "expo"}})
        self.assertEqual(self.browser._search.text(), "expo")

    def test_import_preset_data_tolerates_legacy_exclude_section(self):
        # A pre-consolidation preset carried a separate "exclude" section; the
        # single-field browser must ignore it without raising and still apply
        # the search section.
        self.browser._import_preset_data(
            {
                "search": {"text": "keep", "filter_enabled": True},
                "exclude": {"text": "drop", "scope": SCOPE_NAME},
            }
        )
        self.assertEqual(self.browser._search.text(), "keep")
        self.assertFalse(hasattr(self.browser, "_exclude"))

    def test_preset_manager_metadata_provider_wired(self):
        # The PresetManager on the header menu must have our hooks set.
        # Bound-method identity is unstable (each ``self.method`` access
        # creates a new wrapper), so compare equality which checks the
        # underlying function + instance.
        mgr = self.browser._header.menu.presets
        self.assertEqual(mgr.metadata_provider, self.browser._export_preset_data)
        self.assertEqual(mgr.on_metadata_loaded, self.browser._import_preset_data)

    def test_state_reset_preserves_checkbox_label(self):
        # Regression: the state shim used to call ValueManager.set_value,
        # which checks setText *before* setChecked — so a QCheckBox got
        # its visible label clobbered with "True"/"False" on Restore Defaults
        # instead of having its checked state toggled. The shim now
        # dispatches by widget type to call the semantic setter.
        cb = self.browser._cb_frameless
        original_label = cb.text()
        cb.setChecked(False)  # default is True
        self.browser.state.reset(cb)
        self.assertEqual(cb.text(), original_label)
        self.assertTrue(cb.isChecked())  # default restored

    def test_state_reset_resets_combobox_value(self):
        combo = self.browser._show
        combo.setCurrentText(SHOW_ALL)
        self.browser.state.reset(combo)
        # The captured default for show_mode is SHOW_VISIBLE.
        self.assertEqual(combo.currentText(), SHOW_VISIBLE)


class ColumnLayout(BrowserBase):
    def test_action_columns_match_button_width(self):
        view = self.browser._view
        self.assertEqual(
            view.columnWidth(SwitchboardBrowserModel.COL_ACTION), 22
        )
        self.assertEqual(
            view.columnWidth(SwitchboardBrowserModel.COL_CLOSE), 22
        )

    def test_show_combobox_lists_all_modes(self):
        # The show combo lives in the header menu now; verify the items.
        combo = self.browser._show
        items = [combo.itemText(i) for i in range(combo.count())]
        self.assertEqual(set(items), {SHOW_VISIBLE, SHOW_HIDDEN, SHOW_ALL})


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
    def test_default_header_buttons_present(self):
        for name in ("menu", "minimize", "hide"):
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


class RowFollowsVisibilityFromAnyShowPath(BrowserBase):
    """The row's action icon must track ``ui.isVisible()`` regardless of
    *which* code path showed or hid the UI.

    Regression context: the icon used to flip to "Focus" only when the UI
    was launched via the browser's own action button (because that's
    where ``_wire_visibility`` ran). UIs shown by other paths — marking
    menu, ``sb.loaded_ui.<name>.show()``, slot code calling
    ``UiHandler.show()`` — never had on_show/on_hide piped through, so
    the row stayed stuck on its initial icon. Especially visible after
    closing the UI via its own header X: the model never heard about
    the hide, action button kept showing "Focus".

    The fix wires visibility centrally on ``Switchboard.on_ui_loaded``
    so every loaded UI — regardless of launch path — drives row state.
    """

    def _action_tooltip(self, name: str) -> str:
        row = next(
            i for i in range(self.browser._model.rowCount())
            if self.browser._model.index(i, 0).data(SwitchboardBrowserModel.NameRole) == name
        )
        src = self.browser._model.index(row, SwitchboardBrowserModel.COL_ACTION)
        proxy = self.browser._proxy.mapFromSource(src)
        container = self.browser._view.indexWidget(proxy)
        btn = container.findChild(QtWidgets.QPushButton) if container else None
        return btn.toolTip() if btn else ""

    def test_show_outside_browser_flips_row_to_focus(self):
        # Load + show via direct loaded_ui access (mimics what a marking
        # menu does — UiHandler.launch is never called).
        ui = self.sb.loaded_ui.alpha
        ui.show()
        for _ in range(5):
            QtWidgets.QApplication.processEvents()
        self.assertEqual(self._action_tooltip("alpha"), "Focus alpha")

    def test_hide_outside_browser_flips_row_back_to_launch(self):
        # The user's exact symptom: after the UI is hidden by a non-browser
        # path, the row must revert to "Launch ...".
        ui = self.sb.loaded_ui.alpha
        ui.show()
        for _ in range(5):
            QtWidgets.QApplication.processEvents()
        ui.hide()
        for _ in range(5):
            QtWidgets.QApplication.processEvents()
        self.assertEqual(self._action_tooltip("alpha"), "Launch alpha")


class TagCellRenderingAndPerf(BrowserBase):
    """Pin three independent fixes that together polish the table UX:

    1. Tag chips don't wrap — long content clips horizontally so the
       fixed 22px row height doesn't crop a half-rendered second line.
    2. Selection style: 1px white border, transparent background — no
       dark-theme blue overlay washing out the chip colors.
    3. While the browser is hidden, per-event ``_do_full_refresh``
       calls are skipped. Previously these fired on every UI show/hide
       in the host app, building new row buttons no one could see —
       the source of the post-browser sluggishness in tentacle.
    """

    def test_tag_doc_has_nowrap(self):
        from qtpy import QtGui
        wrap = self.browser._row_delegate._doc.defaultTextOption().wrapMode()
        self.assertEqual(wrap, QtGui.QTextOption.NoWrap)

    def test_view_inline_stylesheet_is_minimal(self):
        """Selection / hover styling lives in the global QSS now; the
        only per-view override is zero item padding so the 22px action
        cells fit their icon buttons tightly. The pre-2026 inline
        override (hardcoded background + selection colors) hid custom
        cell color coding — guard against its return."""
        ss = self.browser._view.styleSheet()
        self.assertIn("padding: 0", ss)
        self.assertNotIn("background", ss,
                         "Background should come from the theme, not inline QSS.")
        self.assertNotIn("selected", ss,
                         "Selection styling should come from the global QSS "
                         "(QAbstractItemView::item:selected), not inline.")

    def test_delegate_does_not_strip_selection_state(self):
        """The browser delegate must let the global QSS ``:selected``
        styling paint through.  Stripping ``State_Selected`` (the
        ``RowSelectionBorderDelegate`` opt-in pattern, for editors with
        colour-coded cells like ``ColorMappingEditor``) would hide the
        standard blue selection fill the user expects on the browser.
        Locked in to catch a future re-inheritance.
        """
        from uitk.widgets.delegates.row_selection import RowSelectionBorderDelegate
        self.assertNotIsInstance(
            self.browser._row_delegate, RowSelectionBorderDelegate,
            "Browser delegate must NOT inherit RowSelectionBorderDelegate "
            "— the browser uses the standard blue-fill selection from QSS, "
            "not the transparent-with-border opt-in for colour-cell editors.",
        )

    def test_view_has_mouse_tracking_for_hover_qss(self):
        """``QStyle::State_MouseOver`` (and therefore QSS ``:hover``)
        only fires on cursor moves when the view has mouse tracking
        enabled.  Without it the hover tint silently never renders —
        a regression that's invisible until you actually look at the
        browser, so lock it in here.
        """
        self.assertTrue(
            self.browser._view.hasMouseTracking(),
            "Browser view must have mouseTracking enabled for QSS "
            "item :hover styling to fire on cursor moves.",
        )

    def test_hidden_browser_skips_full_refresh(self):
        # Track refresh calls.
        calls = []
        orig = self.browser._do_full_refresh
        self.browser._do_full_refresh = lambda: calls.append(1) or orig()
        # Visible: signal -> deferred -> one refresh.
        self.browser.show()
        QtWidgets.QApplication.processEvents()
        calls.clear()
        self.sb.handlers.ui._notify_entries_changed("alpha")
        for _ in range(5):
            QtWidgets.QApplication.processEvents()
        self.assertGreaterEqual(len(calls), 1)
        # Hidden: signals batched into the dirty flag, zero refreshes.
        self.browser.hide()
        QtWidgets.QApplication.processEvents()
        calls.clear()
        for _ in range(3):
            self.sb.handlers.ui._notify_entries_changed("alpha")
        for _ in range(5):
            QtWidgets.QApplication.processEvents()
        self.assertEqual(
            len(calls), 0,
            "While hidden, the browser must not run full-refresh work.",
        )
        self.assertTrue(self.browser._dirty_while_hidden)
        # Re-show: exactly one consolidated refresh.
        self.browser.show()
        QtWidgets.QApplication.processEvents()
        self.assertGreaterEqual(len(calls), 1)
        self.assertFalse(self.browser._dirty_while_hidden)


class HideInheritedTagsToggle(BrowserBase):
    """The "Hide inherited tags" menu option drops registration-time
    tags (filename suffix, source-dir tag, entry-point extras) from
    both the row chips and the top tag-filter chip strip. Off by
    default; setting persists.
    """

    def _alpha_tags_html(self) -> str:
        row = next(
            i for i in range(self.browser._model.rowCount())
            if self.browser._model.index(i, 0).data(
                SwitchboardBrowserModel.NameRole
            ) == "alpha"
        )
        idx = self.browser._model.index(row, SwitchboardBrowserModel.COL_TAGS)
        return self.browser._row_delegate._tags_html(idx)

    def test_toggle_exists_and_off_by_default(self):
        self.assertTrue(hasattr(self.browser, "_cb_hide_inherited_tags"))
        self.assertFalse(self.browser._cb_hide_inherited_tags.isChecked())

    def test_toggle_drops_inherited_tags_from_row_chips(self):
        # alpha has file tags {"anim","rig"} from setUp. Mark them as
        # *inherited* by setting source-directory tags.
        self.sb.register(ui_location=self.dir, tags={"src_inherited"})
        QtWidgets.QApplication.processEvents()
        # Off: inherited visible.
        html = self._alpha_tags_html()
        self.assertIn("src_inherited", html)
        # On: inherited dropped.
        self.browser._cb_hide_inherited_tags.setChecked(True)
        QtWidgets.QApplication.processEvents()
        html = self._alpha_tags_html()
        self.assertNotIn("src_inherited", html)


class TagEditorEscape(BrowserBase):
    """Esc must always dismiss the tag inline editor.

    Default Qt behavior: QLineEdit consumes Esc when it has an undoable
    change (typed text) — reverting the text but *not* closing the
    editor. From the user's view that's "I can't exit edit mode
    without making an entry": they type, change their mind, hit Esc,
    text clears but the editor stays open.

    The delegate's eventFilter intercepts Esc and emits
    ``closeEditor(NoHint)`` so the editor goes away regardless of
    QLineEdit's undo state.
    """

    def _open_editor(self):
        # Showing the browser ensures the view has a real geometry, so
        # edit() actually creates the delegate's editor. Without show()
        # the view's layout is empty and QApplication.focusWidget()
        # never sees the editor.
        self.browser.resize(500, 300)
        self.browser.show()
        QtWidgets.QApplication.processEvents()
        row = next(
            i for i in range(self.browser._model.rowCount())
            if self.browser._model.index(i, 0).data(SwitchboardBrowserModel.NameRole) == "alpha"
        )
        src = self.browser._model.index(row, SwitchboardBrowserModel.COL_TAGS)
        proxy = self.browser._proxy.mapFromSource(src)
        self.browser._view.edit(proxy)
        QtWidgets.QApplication.processEvents()
        # The editor is the QLineEdit child of the view's viewport.
        return self.browser._view.viewport().findChild(QtWidgets.QLineEdit)

    def _send_escape(self, editor):
        from qtpy import QtGui
        ev = QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier
        )
        QtWidgets.QApplication.sendEvent(editor, ev)
        QtWidgets.QApplication.processEvents()

    def test_escape_closes_editor_when_empty(self):
        editor = self._open_editor()
        self.assertIsInstance(editor, QtWidgets.QLineEdit)
        self._send_escape(editor)
        self.assertEqual(
            self.browser._view.state(),
            QtWidgets.QAbstractItemView.NoState,
        )

    def test_escape_closes_editor_after_typing(self):
        # The user's specific scenario: they type, change their mind,
        # press Esc — editor must close (without committing the typed
        # change). Pre-fix: QLineEdit consumed Esc to revert, leaving
        # editor open.
        editor = self._open_editor()
        editor.setText("partial typing that won't be saved")
        self._send_escape(editor)
        self.assertEqual(
            self.browser._view.state(),
            QtWidgets.QAbstractItemView.NoState,
            "Esc with an undoable change must still close the editor.",
        )


class InlineTagEditingIsTheOnlyPath(BrowserBase):
    """Tag editing is exclusively inline — no modal popup.

    Regression guards:
      * ``TagEditDialog`` class was deleted (no longer imported).
      * Right-click ``Edit tags`` triggers ``QTableView.edit`` on the
        Tags cell, which opens the same inline QLineEdit delegate that
        double-click uses. One UX path, not two.
      * External-tool rows aren't editable (no file-backing) — the
        context-menu item simply isn't offered for those rows.
    """

    def test_tag_edit_dialog_class_removed(self):
        import uitk.widgets.editors.switchboard_browser as mod
        self.assertFalse(
            hasattr(mod, "TagEditDialog"),
            "TagEditDialog must stay deleted — inline edit is the only path.",
        )
        self.assertFalse(
            hasattr(self.browser, "_edit_tags_for"),
            "_edit_tags_for invoked the popup; it should no longer exist.",
        )

    def test_double_click_tags_cell_opens_inline_editor(self):
        # File-backed entries' tag cells must be ItemIsEditable so the
        # view's DoubleClicked trigger spawns the delegate's QLineEdit.
        src_idx = self.browser._model.index(0, SwitchboardBrowserModel.COL_TAGS)
        self.assertTrue(
            bool(self.browser._model.flags(src_idx) & QtCore.Qt.ItemIsEditable),
            "File-backed entries' tag cells must be ItemIsEditable.",
        )
        # Programmatically call edit() and verify the view entered editing
        # state. (PySide's edit() slot returns None — we check state instead.)
        proxy_idx = self.browser._proxy.mapFromSource(src_idx)
        self.browser._view.edit(proxy_idx)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(
            self.browser._view.state(),
            QtWidgets.QAbstractItemView.EditingState,
            "View should be in EditingState after edit() on the Tags cell.",
        )

    def test_view_edit_triggers_include_double_click(self):
        # The view's edit-triggers must include DoubleClicked so the user
        # gesture actually fires the inline editor (vs. requiring F2).
        # PySide6 returns flag enums that don't coerce to int; use the
        # flag bitwise-AND operation directly.
        triggers = self.browser._view.editTriggers()
        self.assertTrue(
            bool(triggers & QtWidgets.QAbstractItemView.DoubleClicked),
            "DoubleClicked must be in editTriggers — the canonical "
            "tag-editing gesture is double-click on the Tags cell.",
        )


class EntryFilterStructural(QtBaseTestCase):
    """Structural inc/exc entry filter (``SwitchboardBrowser(inc=..., exc=...)``).

    Unlike the user-curated hide lists (which filter *rows* and can be
    toggled from the Show combo), the entry filter is an embed-time policy:
    excluded entries are never materialised into the model at all — absent
    from counts, chips, presets, and (critically) from the entry-changed
    signal path. Host apps use it to keep non-standalone UIs out of the
    launcher (e.g. tentacle hides the marking menu's ``*#startmenu*`` /
    ``*#submenu*`` gesture pages). Patterns are ``pythontk.filter_list``
    shell-style wildcards.
    """

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        _write_ui(os.path.join(d, "alpha.ui"), "alpha", "anim")
        _write_ui(os.path.join(d, "delta.ui"), "delta", "")
        _write_ui(os.path.join(d, "cameras#startmenu.ui"), "cameras_startmenu")
        _write_ui(os.path.join(d, "uv#submenu.ui"), "uv_submenu")
        self.sb = Switchboard(ui_source=d, log_level="WARNING")
        self.sb.settings.branch("ui_browser").clear()
        self.browser = None

    def tearDown(self):
        try:
            self.sb.on_ui_tags_changed.disconnect()
        except (RuntimeError, TypeError):
            pass
        if self.browser is not None:
            self.browser.setParent(None)
            self.browser.deleteLater()
        self.sb.deleteLater()
        for _ in range(3):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
        self.tmp.cleanup()
        super().tearDown()

    def _make_browser(self, **kwargs):
        self.browser = SwitchboardBrowser(self.sb, **kwargs)
        self.browser.resize(500, 300)
        self.browser.show()
        QtWidgets.QApplication.processEvents()
        return self.browser

    MARKING_MENU_EXC = ["*#startmenu*", "*#submenu*"]

    def test_exc_removes_entries_structurally(self):
        browser = self._make_browser(exc=self.MARKING_MENU_EXC)
        self.assertEqual(sorted(browser._model._names), ["alpha", "delta"])

    def test_exc_removes_inherited_tags_from_chip_pool(self):
        """An excluded entry contributes nothing — not even its tags."""
        browser = self._make_browser(exc=self.MARKING_MENU_EXC)
        tags = set(browser._model.all_unique_tags())
        self.assertNotIn("startmenu", tags)
        self.assertNotIn("submenu", tags)

    def test_inc_limits_to_matching(self):
        browser = self._make_browser(inc="alpha*")
        self.assertEqual(browser._model._names, ["alpha"])

    def test_entry_changed_for_excluded_name_is_ignored(self):
        """Gesture traffic must not churn the model.

        Marking-menu pages emit ``on_handler_entry_changed`` on every
        show/hide during a gesture (visibility wiring). For a name the
        entry filter excludes, the model must short-circuit — no reset,
        no dataChanged — or an open browser makes the marking menu
        sluggish (an unknown name used to trigger a full coarse
        ``_refresh`` per signal).
        """
        browser = self._make_browser(exc=self.MARKING_MENU_EXC)
        resets, changes = [], []
        browser._model.modelReset.connect(lambda: resets.append(1))
        browser._model.dataChanged.connect(lambda *_a: changes.append(1))

        self.sb.on_handler_entry_changed.emit("ui", "cameras#startmenu")
        QtWidgets.QApplication.processEvents()

        self.assertEqual(resets, [])
        self.assertEqual(changes, [])

    def test_set_entry_filter_runtime(self):
        browser = self._make_browser()
        self.assertEqual(browser._model.rowCount(), 4)

        browser.set_entry_filter(exc=self.MARKING_MENU_EXC)
        self.assertEqual(sorted(browser._model._names), ["alpha", "delta"])

        browser.set_entry_filter()  # clear
        self.assertEqual(browser._model.rowCount(), 4)

    def test_filter_kwargs_compose_with_existing_switchboard(self):
        """inc/exc are browser-level options — they must not trip the
        'switchboard OR switchboard_kwargs' constructor guard."""
        browser = self._make_browser(exc=self.MARKING_MENU_EXC)
        self.assertIs(browser.sb, self.sb)


if __name__ == "__main__":
    unittest.main()
