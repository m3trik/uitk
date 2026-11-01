# !/usr/bin/python
# coding=utf-8
import re
import unittest
from unittest.mock import MagicMock, patch
from qtpy import QtCore, QtWidgets, QtGui
from conftest import QtBaseTestCase, setup_qt_application
from uitk.themes.style_sheet import StyleSheet

# Ensure QApplication exists
app = setup_qt_application()


class TestStyleSheetOverrides(QtBaseTestCase):
    """Tests for StyleSheet variable overrides and theme management."""

    def test_get_defaults(self):
        """Should retrieve default theme variables."""
        # Check a known variable from the 'light' theme
        bg_color = StyleSheet.get_variable("PANEL_BACKGROUND", theme="light")
        self.assertEqual(bg_color, "rgb(70,70,70)")

    def test_global_override(self):
        """Should respect theme-specific variable overrides."""
        # Set a global override (defaults to theme='light')
        StyleSheet.set_variable("BUTTON_HOVER", "#FF0000")

        # Verify it overrides the default for light theme
        val = StyleSheet.get_variable("BUTTON_HOVER", theme="light")
        self.assertEqual(val, "#FF0000")

        # Verify it DOES NOT apply to dark theme (overrides are now theme-specific)
        val_dark = StyleSheet.get_variable("BUTTON_HOVER", theme="dark")
        self.assertNotEqual(val_dark, "#FF0000")

        # Set specific override for dark theme
        StyleSheet.set_variable("BUTTON_HOVER", "#0000FF", theme="dark")
        val_dark_new = StyleSheet.get_variable("BUTTON_HOVER", theme="dark")
        self.assertEqual(val_dark_new, "#0000FF")

        # Clean up
        StyleSheet.reset_overrides()

    def test_widget_override(self):
        """Should respect widget-specific overrides."""
        widget = self.track_widget(QtWidgets.QWidget())

        # Set override for this widget only
        StyleSheet.set_variable("TEXT_COLOR", "#00FF00", widget=widget)

        # Verify widget sees the override
        val = StyleSheet.get_variable("TEXT_COLOR", theme="light", widget=widget)
        self.assertEqual(val, "#00FF00")

        # Verify global context still sees default
        global_val = StyleSheet.get_variable("TEXT_COLOR", theme="light")
        self.assertNotEqual(global_val, "#00FF00")

        # Clean up
        StyleSheet.reset_overrides()

    def test_override_resolution_order(self):
        """Should resolve overrides in correct order: Widget > Global > Theme."""
        widget = self.track_widget(QtWidgets.QWidget())

        # 1. Base Theme
        default_val = StyleSheet.get_variable("SELECTION_FG", theme="light")

        # 2. Global Override
        StyleSheet.set_variable("SELECTION_FG", "#111111")
        val = StyleSheet.get_variable("SELECTION_FG", theme="light", widget=widget)
        self.assertEqual(val, "#111111")

        # 3. Widget Override (should beat global)
        StyleSheet.set_variable("SELECTION_FG", "#222222", widget=widget)
        val = StyleSheet.get_variable("SELECTION_FG", theme="light", widget=widget)
        self.assertEqual(val, "#222222")

        # Clean up -- and the theme's own value is back.
        StyleSheet.reset_overrides()
        val = StyleSheet.get_variable("SELECTION_FG", theme="light", widget=widget)
        self.assertEqual(val, default_val)

    def test_color_object_handling(self):
        """Should handle QColor objects passed to set_variable."""
        color = QtGui.QColor(255, 0, 0)  # Red
        StyleSheet.set_variable("TEST_COLOR", color)

        val = StyleSheet.get_variable("TEST_COLOR")
        self.assertEqual(val, "#ff0000")

        StyleSheet.reset_overrides()

    def test_get_variable_px(self):
        """``get_variable_px`` parses a length token to int, honoring
        overrides and the ``default`` for missing/non-numeric values."""
        # Real px token from the theme.
        self.assertEqual(
            StyleSheet.get_variable_px("COMBOBOX_ITEM_HEIGHT", theme="light"), 19
        )
        # Missing token → default (None unless given).
        self.assertIsNone(StyleSheet.get_variable_px("NOPE_DOES_NOT_EXIST"))
        self.assertEqual(
            StyleSheet.get_variable_px("NOPE_DOES_NOT_EXIST", default=7), 7
        )
        # Non-numeric (a colour) → default.
        self.assertEqual(
            StyleSheet.get_variable_px("PANEL_BACKGROUND", theme="light", default=0), 0
        )
        # Override is resolved and parsed.
        StyleSheet.set_variable("COMBOBOX_ITEM_HEIGHT", "23px", theme="light")
        self.assertEqual(
            StyleSheet.get_variable_px("COMBOBOX_ITEM_HEIGHT", theme="light"), 23
        )
        StyleSheet.reset_overrides()

    def test_reset_overrides(self):
        """Should clear overrides correctly."""
        widget = self.track_widget(QtWidgets.QWidget())

        StyleSheet.set_variable("VAR1", "A")  # Global
        StyleSheet.set_variable("VAR2", "B", widget=widget)  # Widget

        # Reset widget only
        StyleSheet.reset_overrides(widget=widget)
        self.assertEqual(StyleSheet.get_variable("VAR2", widget=widget), "")  # Cleared
        self.assertEqual(StyleSheet.get_variable("VAR1"), "A")  # Global persists

        # Reset all
        StyleSheet.reset_overrides()
        self.assertEqual(StyleSheet.get_variable("VAR1"), "")  # Cleared


class TestStyleSheetTemplateEngine(QtBaseTestCase):
    """Tests for the parsed-template substitution engine."""

    def test_template_caches_by_resource(self):
        """``_get_template`` populates ``_template_cache`` once per resource."""
        StyleSheet._template_cache.clear()
        parts_a = StyleSheet._get_template()
        parts_b = StyleSheet._get_template()
        # Same list object — cache hit, not rebuilt
        self.assertIs(parts_a, parts_b)
        self.assertEqual(len(StyleSheet._template_cache), 1)

    def test_template_alternates_literals_and_tokens(self):
        """Even indices are literals, odd indices are UPPER_SNAKE token names."""
        parts = StyleSheet._token_pat.split("foo {BAR} baz {QUX_2} end")
        self.assertEqual(parts, ["foo ", "BAR", " baz ", "QUX_2", " end"])

    def test_apply_template_leaves_unknown_token_as_literal(self):
        """Missing tokens render as ``{TOKEN}`` so the gap is visible."""
        parts = ["pre ", "MISSING", " post"]
        out = StyleSheet._apply_template(parts, {})
        self.assertEqual(out, "pre {MISSING} post")

    def test_apply_template_substitutes_known_tokens(self):
        parts = ["color: ", "BG", "; border: ", "BORDER_W", " solid;"]
        out = StyleSheet._apply_template(parts, {"BG": "red", "BORDER_W": "1px"})
        self.assertEqual(out, "color: red; border: 1px solid;")

    def test_slider_handle_radius_is_literal_not_token(self):
        """Slider handle keeps a literal radius (it's width:10px — {RADIUS} > 5 distorts it)."""
        import re

        parts = StyleSheet._get_template()
        qss_high_radius = StyleSheet._apply_template(
            parts, {**StyleSheet.themes["light"], "RADIUS": "10px"}
        )
        m = re.search(
            r"QAbstractSlider::handle\s*\{[^}]*?border-radius:\s*([^;]+);",
            qss_high_radius,
        )
        self.assertIsNotNone(m, "slider handle rule must exist")
        self.assertNotIn(
            "10px",
            m.group(1),
            "slider handle picked up the {RADIUS} override — it should be a literal",
        )

    def test_slider_hover_leaves_background_handle_reads_as_grabbable(self):
        """Slider hover must not repaint the widget background; the grab
        affordance is the resting handle sitting a hair brighter than the
        panel (``PANEL_BACKGROUND_TINT``), with the blue handle-hover intact."""
        import re

        def rgb(s):
            m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", s)
            return tuple(int(m.group(i)) for i in (1, 2, 3))

        parts = StyleSheet._get_template()
        for theme_name in StyleSheet.themes:
            theme_vars = StyleSheet.themes[theme_name].copy()
            StyleSheet._derive_internal_vars(theme_vars)
            qss = StyleSheet._apply_template(parts, theme_vars)

            hover = re.search(r"(?:^|\n)QAbstractSlider:hover\s*\{([^}]*)\}", qss)
            self.assertIsNotNone(hover, "QAbstractSlider:hover rule must exist")
            self.assertNotIn(
                "background-color",
                hover.group(1),
                f"[{theme_name}] slider hover must leave the background alone",
            )

            handle = re.search(
                r"QAbstractSlider::handle\s*\{[^}]*?background-color:\s*([^;]+);", qss
            )
            self.assertIsNotNone(handle, "slider handle rule must exist")
            tint, panel = rgb(handle.group(1)), rgb(theme_vars["PANEL_BACKGROUND"])
            self.assertEqual(rgb(theme_vars["PANEL_BACKGROUND_TINT"]), tint)
            # Brighter than the panel on every channel, by at least one level.
            self.assertTrue(all(t >= p for t, p in zip(tint, panel)) and tint != panel)

    def test_text_inset_is_uniform_across_form_widgets(self):
        """Labels, comboboxes, line edits and spin boxes share the single
        ``{TEXT_INSET}`` horizontal padding so their text aligns in a layout.
        A distinctive override proves each base rule reads the token rather
        than a coincidental literal."""
        import re

        parts = StyleSheet._get_template()
        qss = StyleSheet._apply_template(
            parts, {**StyleSheet.themes["light"], "TEXT_INSET": "7px"}
        )
        for selector in ("QLabel", "QComboBox", "QLineEdit", "QAbstractSpinBox"):
            # ``selector\s*\{`` matches only the bare base rule, not the
            # ``:hover`` / ``::drop-down`` / descendant variants.
            m = re.search(rf"(?:^|\n){re.escape(selector)}\s*\{{([^}}]*)\}}", qss)
            self.assertIsNotNone(m, f"{selector} base rule must exist")
            pad = re.search(r"padding:\s*([^;]+);", m.group(1))
            self.assertIsNotNone(pad, f"{selector} must declare padding")
            self.assertIn(
                "7px",
                pad.group(1),
                f"{selector} padding must use {{TEXT_INSET}} (got {pad.group(1)!r})",
            )

    def test_chrome_background_drives_header_and_footer_only(self):
        """Header/Footer paint with ``{CHROME_BACKGROUND}``, and thinning it
        leaves the ``{PANEL_BACKGROUND}`` surfaces (scrollbar/toolbox/menubar)
        alone — the whole point of splitting the token."""
        import re

        parts = StyleSheet._get_template()
        theme_vars = {
            **StyleSheet.themes["light"],
            "CHROME_BACKGROUND": "rgba(1,2,3,4)",
        }
        StyleSheet._derive_internal_vars(theme_vars)
        qss = StyleSheet._apply_template(parts, theme_vars)

        for selector in ("Header", "Header:hover", "Footer", "Footer:hover"):
            m = re.search(rf"(?:^|\n){re.escape(selector)}\s*\{{([^}}]*)\}}", qss)
            self.assertIsNotNone(m, f"{selector} rule must exist")
            self.assertIn(
                "rgba(1,2,3,4)",
                m.group(1),
                f"{selector} must paint with {{CHROME_BACKGROUND}}",
            )

        for selector in ("QToolBox", "QStackedWidget", "QToolTip"):
            m = re.search(rf"(?:^|\n){re.escape(selector)}\s*\{{([^}}]*)\}}", qss)
            self.assertIsNotNone(m, f"{selector} rule must exist")
            self.assertNotIn(
                "rgba(1,2,3,4)",
                m.group(1),
                f"{selector} must keep {{PANEL_BACKGROUND}}, not the chrome token",
            )

    def test_chrome_background_is_translucent_except_high_contrast(self):
        """The shipped chrome is semi-transparent in the standard themes;
        high-contrast stays opaque (translucency hurts legibility there)."""

        def alpha(color_str):
            # Read with the engine's own parser so hex-format themes read the
            # same as rgb()/rgba() ones.
            color = StyleSheet._parse_color(color_str)
            self.assertIsNotNone(color, f"unparsable color {color_str!r}")
            return StyleSheet._alpha(color)

        for theme_name, theme_vars in StyleSheet.themes.items():
            chrome = theme_vars["CHROME_BACKGROUND"]
            if theme_name == "high-contrast":
                self.assertEqual(alpha(chrome), 255.0, "high-contrast must stay opaque")
            else:
                self.assertLess(
                    alpha(chrome),
                    255.0,
                    f"[{theme_name}] chrome must be semi-transparent",
                )
                self.assertLess(
                    alpha(chrome),
                    alpha(theme_vars["PANEL_BACKGROUND"]),
                    f"[{theme_name}] chrome must read glassier than the panel surface",
                )

    def test_qss_has_no_unresolved_tokens(self):
        """Every ``{TOKEN}`` in style.qss resolves against the themes dict
        (plus any internally-derived tokens injected at assembly time)."""
        parts = StyleSheet._get_template()
        used = {p for i, p in enumerate(parts) if i % 2 == 1}
        for theme_name in StyleSheet.themes:
            # Derive the same way assembly does, so any internal token
            # (``*_TINT``, ``DISABLED_CHECKED_BACKGROUND``, …) is covered.
            theme_vars = StyleSheet.themes[theme_name].copy()
            StyleSheet._derive_internal_vars(theme_vars)
            missing = used - set(theme_vars.keys())
            self.assertFalse(
                missing,
                f"theme '{theme_name}' is missing tokens used in style.qss: {sorted(missing)}",
            )

    def test_disabled_checked_background_derived_and_protected(self):
        """``DISABLED_CHECKED_BACKGROUND`` is a derived token: a slight blend of
        the disabled background toward the checked accent, and not user-settable."""
        import re

        def rgb(s):
            m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", s)
            return tuple(int(m.group(i)) for i in (1, 2, 3))

        for theme_name in StyleSheet.themes:
            theme_vars = StyleSheet.themes[theme_name].copy()
            StyleSheet._derive_internal_vars(theme_vars)
            dc = theme_vars.get("DISABLED_CHECKED_BACKGROUND")
            self.assertIsNotNone(dc)
            base = rgb(StyleSheet.themes[theme_name]["DISABLED_BACKGROUND"])
            accent = rgb(StyleSheet.themes[theme_name]["BUTTON_CHECKED"])
            got = rgb(dc)
            # Each channel sits between disabled and accent, and stays close to
            # the disabled base (a slight tint, not the full accent).
            for i in range(3):
                self.assertTrue(
                    min(base[i], accent[i]) <= got[i] <= max(base[i], accent[i])
                )
                self.assertLessEqual(
                    abs(got[i] - base[i]), abs(accent[i] - base[i]) * 0.5
                )

        # Derived token detection + override rejection.
        self.assertTrue(StyleSheet._is_derived_token("DISABLED_CHECKED_BACKGROUND"))
        self.assertFalse(StyleSheet._is_derived_token("DISABLED_BACKGROUND"))
        with self.assertRaises(ValueError):
            StyleSheet.set_variable(
                "DISABLED_CHECKED_BACKGROUND", "rgb(1,2,3)", theme="light"
            )

    def test_reload_assembles_qss_once_per_config_group(self):
        """``reload()`` should call ``_apply_template`` once per unique config,
        not once per widget. Verifies the grouping optimization."""
        # Register 5 widgets sharing the same config
        widgets = [self.track_widget(QtWidgets.QWidget()) for _ in range(5)]
        styler = StyleSheet()
        for w in widgets:
            styler.set(w, theme="light")

        # Wrap _apply_template to count invocations. Save the descriptor
        # itself (not the resolved attribute) so the restore puts the
        # staticmethod wrapper back, not a plain function that would bind
        # ``self`` on later calls and break subsequent tests.
        original_desc = StyleSheet.__dict__["_apply_template"]
        original = StyleSheet._apply_template
        call_count = [0]

        def counting(parts, vars):
            call_count[0] += 1
            return original(parts, vars)

        # Isolate the registry to just our 5 widgets — other tests in the
        # full suite leave widgets registered, which would split into
        # multiple config groups and break this assertion.
        saved_configs = StyleSheet._widget_configs
        StyleSheet._widget_configs = {w: saved_configs[w] for w in widgets}
        StyleSheet._apply_template = staticmethod(counting)
        try:
            StyleSheet.reload()
            self.assertEqual(
                call_count[0],
                1,
                "5 widgets sharing a config should trigger 1 template-apply, not 5",
            )
        finally:
            StyleSheet._apply_template = original_desc
            StyleSheet._widget_configs = saved_configs


class TestStyleSheetSignals(QtBaseTestCase):
    """Tests for StyleSheet signals."""

    def test_theme_changed_signal(self):
        """Should emit theme_changed signal with resolved variables."""
        widget = self.track_widget(QtWidgets.QWidget())
        styler = StyleSheet()

        # Set an override to verify it comes through in the signal
        StyleSheet.set_variable("BUTTON_HOVER", "#123456", widget=widget)

        # Mock slot
        mock_slot = MagicMock()
        styler.theme_changed.connect(mock_slot)

        try:
            # Apply style
            styler.set(widget, theme="light")

            # Verify signal emission
            self.assertTrue(mock_slot.called)
            args = mock_slot.call_args[0]
            emitted_widget, emitted_theme, emitted_vars = args

            self.assertEqual(emitted_widget, widget)
            self.assertEqual(emitted_theme, "light")
            self.assertEqual(emitted_vars.get("BUTTON_HOVER"), "#123456")
        finally:
            # theme_changed is backed by a process-wide bus; disconnect so the
            # mock doesn't linger across the rest of the suite.
            styler.theme_changed.disconnect(mock_slot)
            StyleSheet.reset_overrides()

    def test_theme_changed_reaches_subscriber_across_instances(self):
        """Emits from the classmethod paths (set_variable/reload/set_theme),
        which run on a throwaway instance, must reach a subscriber connected
        via a *different* instance (as ``ui.style.theme_changed`` would be)."""
        widget = self.track_widget(QtWidgets.QWidget())
        StyleSheet().set(widget, theme="light")  # register so reload emits

        received = []

        def slot(w, t, v):
            received.append((w, t))

        subscriber = StyleSheet()  # a separate instance from the emitter
        subscriber.theme_changed.connect(slot)
        try:
            StyleSheet.set_variable("BUTTON_HOVER", "#0a0b0c", theme="light")
            self.assertTrue(
                received,
                "theme_changed subscriber on a different instance never fired",
            )
        finally:
            subscriber.theme_changed.disconnect(slot)
            StyleSheet.reset_overrides()


class TestStyleSheetPlates(QtBaseTestCase):
    """What a translucent window's children actually paint -- rendered and
    sampled, since a rule can lose to a more specific one it never names."""

    def render(self, *pages):
        """A translucent panel, dark-themed, each page in a stack of its own;
        returns the rendered window and the panel."""
        from uitk.widgets.windowPanel import WindowPanel

        panel = self.track_widget(WindowPanel(title="plates"))
        for page in pages:
            stack = QtWidgets.QStackedWidget()
            stack.addWidget(page)
            panel.body_layout.addWidget(stack, 1)
        panel.resize(300, 120 * len(pages))
        panel.show()
        QtWidgets.QApplication.processEvents()
        return panel.grab().toImage(), panel

    def alpha_in(self, image, panel, widget):
        point = widget.mapTo(panel, widget.rect().center())
        return image.pixelColor(point).alpha()

    def test_an_item_view_on_a_stacked_page_keeps_its_opaque_plate(self):
        """Rows read against the view's own ground, never the desktop behind
        the window -- a page of a stack (an editor's table beside its import
        review) included."""
        table = QtWidgets.QTableWidget(0, 2)
        tree = QtWidgets.QTreeWidget()
        listing = QtWidgets.QListWidget()
        image, panel = self.render(table, tree, listing)
        for view in (table, tree, listing):
            self.assertEqual(
                self.alpha_in(image, panel, view.viewport()),
                255,
                f"{type(view).__name__} on a stacked page shows through",
            )

    def test_a_plain_stacked_page_stays_translucent(self):
        """The panel ground a stack gives its bare pages is the window's glass."""
        page = QtWidgets.QFrame()
        image, panel = self.render(page)
        self.assertLess(self.alpha_in(image, panel, page), 255)

    def icon_grounds(self, *specs):
        """Paint one ``icon_button(**kwargs)`` per *spec* in a themed panel
        (``hovered`` / ``enabled`` keys set that state) and return each one's
        ground color name, sampled at a corner clear of the glyph.

        Painted through the button's own style, as its ``paintEvent`` does,
        with the hover state put in the option: Qt 6's QPushButton reads hover
        from its private enter tracking, which no synthetic event sets offscreen.
        """
        row = QtWidgets.QWidget()
        QtWidgets.QHBoxLayout(row)
        _, panel = self.render(row)
        buttons = []
        for spec in specs:
            spec = dict(spec)
            hovered = spec.pop("hovered", False)
            enabled = spec.pop("enabled", True)
            button = panel.icon_button("close", size=22, **spec)
            button.setEnabled(enabled)
            row.layout().addWidget(button)
            buttons.append((button, hovered))
        QtWidgets.QApplication.processEvents()
        grounds = []
        for button, hovered in buttons:
            option = QtWidgets.QStyleOptionButton()
            button.initStyleOption(option)
            if hovered:
                option.state |= QtWidgets.QStyle.State_MouseOver
            image = QtGui.QImage(button.size(), QtGui.QImage.Format_ARGB32)
            image.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(image)
            button.style().drawControl(
                QtWidgets.QStyle.CE_PushButton, option, painter, button
            )
            painter.end()
            grounds.append(image.pixelColor(2, 2).name())
        return grounds

    def test_a_disabled_icon_button_keeps_the_enabled_ground(self):
        """Only the glyph recedes: a disabled icon button paints the ground an
        enabled one does, not the raised disabled plate that reads as live."""
        enabled, disabled = self.icon_grounds({}, {"enabled": False})
        self.assertEqual(disabled, enabled)

    def test_a_close_icon_button_hovers_red_like_a_windows_close(self):
        """``closes=True``: the header hide button's red hover; a plain icon
        button keeps the theme's hover."""
        closing, plain, resting = self.icon_grounds(
            {"closes": True, "hovered": True}, {"hovered": True}, {"closes": True}
        )
        self.assertEqual(closing, "#ff0000")
        self.assertNotEqual(plain, "#ff0000")
        self.assertNotEqual(resting, "#ff0000", "red only under the cursor")


class TestStyleSheetPublicApi(QtBaseTestCase):
    """The flagship apply method and icon-color resolution."""

    def test_set_is_a_real_public_class_method(self):
        # ``set`` must be a real method on the class (visible to the registry /
        # IDEs), not a per-instance attribute alias assigned in __init__.
        self.assertTrue(callable(getattr(StyleSheet, "set", None)))
        widget = self.track_widget(QtWidgets.QWidget())
        StyleSheet().set(widget, theme="light")
        self.assertTrue(widget.styleSheet())

    def test_get_icon_color_respects_global_override(self):
        widget = self.track_widget(QtWidgets.QWidget())
        StyleSheet().set(widget, theme="light")  # register widget's theme
        try:
            StyleSheet.set_variable("ICON_COLOR", "#abcdef", theme="light")
            self.assertEqual(StyleSheet.get_icon_color(widget), "#abcdef")
        finally:
            StyleSheet.reset_overrides()

    def test_get_icon_color_respects_widget_override(self):
        widget = self.track_widget(QtWidgets.QWidget())
        StyleSheet().set(widget, theme="light")
        try:
            StyleSheet.set_variable("ICON_COLOR", "#123456", widget=widget)
            self.assertEqual(StyleSheet.get_icon_color(widget), "#123456")
        finally:
            StyleSheet.reset_overrides()


class TestWindowBlur(QtBaseTestCase):
    """``WINDOW_BLUR``: a switch token the engine hands to ``Bootstrap.set_blur``
    for the windows it styles."""

    def setUp(self):
        super().setUp()
        self.calls = []
        patcher = patch(
            "uitk.themes.style_sheet.Bootstrap.set_blur",
            side_effect=lambda w, on=True: self.calls.append((w, on)) or on,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        StyleSheet.reset_overrides()
        super().tearDown()

    def test_uitk_ships_it_on_where_the_window_is_translucent(self):
        """On in the translucent themes (frosted menus by default); off in
        high-contrast, whose surfaces are opaque."""
        shipped = {
            theme: StyleSheet.is_on(StyleSheet.themes[theme]["WINDOW_BLUR"])
            for theme in ("light", "dark", "high-contrast")
        }
        self.assertEqual(shipped, {"light": True, "dark": True, "high-contrast": False})
        for theme, tokens in StyleSheet.themes.items():  # and every other theme
            self.assertEqual(
                StyleSheet.is_on(tokens["WINDOW_BLUR"]),
                theme != "high-contrast",
                theme,
            )

    def test_a_styled_window_follows_the_token(self):
        window = self.track_widget(QtWidgets.QWidget())
        StyleSheet().set(window, theme="dark")
        self.assertEqual(self.calls[-1], (window, True))
        StyleSheet.set_variable("WINDOW_BLUR", "off", theme="dark")
        self.assertEqual(self.calls[-1], (window, False))

    def test_a_child_widget_is_left_alone(self):
        parent = self.track_widget(QtWidgets.QWidget())
        child = QtWidgets.QWidget(parent)
        StyleSheet().set(child, theme="dark")
        self.assertNotIn(child, [w for w, _ in self.calls])

    def test_a_popup_window_resolves_its_owners_setting(self):
        """A translucent popup (``PopupWindow.promote``) is never registered
        itself; it follows the WINDOW_BLUR of the window it pops from."""
        from uitk.widgets.popup.window import PopupWindow

        owner = self.track_widget(QtWidgets.QWidget())
        StyleSheet().set(owner, theme="dark")
        popup = QtWidgets.QWidget(owner)
        PopupWindow.promote(
            popup, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint, translucent=True
        )
        resolver = self.calls[-1][1]
        self.assertIs(self.calls[-1][0], popup)
        self.assertTrue(resolver(popup))
        StyleSheet.set_variable("WINDOW_BLUR", "off", theme="dark")
        self.assertFalse(resolver(popup))

    def _fill_alpha(self, theme: str, **kwargs) -> int:
        """The alpha a styled window body (``QWidget.centralWidget``) paints,
        read off a render of its own stylesheet background."""
        body = self.track_widget(QtWidgets.QWidget())
        body.setAttribute(QtCore.Qt.WA_StyledBackground)
        StyleSheet().set(body, theme=theme, style_class="centralWidget", **kwargs)
        return self._painted(body).alpha()

    @staticmethod
    def _painted(widget) -> QtGui.QColor:
        """The color *widget*'s own background paints at its center."""
        widget.resize(40, 40)
        img = QtGui.QImage(40, 40, QtGui.QImage.Format_ARGB32_Premultiplied)
        img.fill(QtCore.Qt.transparent)
        widget.render(
            img,
            QtCore.QPoint(),
            QtGui.QRegion(),
            QtWidgets.QWidget.RenderFlag.DrawChildren,
        )
        return img.pixelColor(20, 20)

    def test_a_context_menu_is_opaque(self):
        """A plain QMenu is a popup over the desktop: nothing blurs behind it
        (no window this engine styles) and a translucent ground read as
        see-through. It paints MENU_BACKGROUND, the opaque context-menu
        ground ContextMenu paints, so Qt never makes it translucent."""
        with patch("uitk.themes.style_sheet.Bootstrap.blurs", return_value=True):
            for theme in StyleSheet.themes:
                owner = self.track_widget(QtWidgets.QWidget())
                StyleSheet().set(owner, theme=theme)
                menu = QtWidgets.QMenu(owner)
                menu.ensurePolished()
                rgb = re.findall(r"\d+", StyleSheet.themes[theme]["MENU_BACKGROUND"])
                expected = QtGui.QColor(*map(int, rgb[:3]))
                self.assertEqual(self._painted(menu), expected, theme)
                self.assertFalse(
                    menu.testAttribute(QtCore.Qt.WA_TranslucentBackground), theme
                )

    def test_a_blurred_window_paints_a_thinner_fill(self):
        """While the desktop blurs behind it, the body paints WINDOW_BACKGROUND
        at WINDOW_BLUR_OPACITY of its alpha, so more of the frosted backdrop
        shows (the blur itself has no strength to turn down)."""
        with patch("uitk.themes.style_sheet.Bootstrap.blurs", return_value=True):
            self.assertEqual(self._fill_alpha("dark"), 75)  # 125 at 60%
            self.assertEqual(self._fill_alpha("light"), 102)  # 170 at 60%

    def test_the_fill_keeps_its_alpha_where_nothing_blurs(self):
        """Unblurred, the desktop behind is sharp: the fill stays as authored
        on a desktop without blur, under WINDOW_BLUR off, and in a window
        that opts out of the blur (``MessageBox``)."""
        with patch("uitk.themes.style_sheet.Bootstrap.blurs", return_value=False):
            self.assertEqual(self._fill_alpha("dark"), 125)
        with patch("uitk.themes.style_sheet.Bootstrap.blurs", return_value=True):
            self.assertEqual(self._fill_alpha("dark", WINDOW_BLUR="off"), 125)
            StyleSheet.set_variable("WINDOW_BLUR", "off", theme="dark")
            self.assertEqual(self._fill_alpha("dark"), 125)

    def test_the_opacity_is_a_theme_token(self):
        with patch("uitk.themes.style_sheet.Bootstrap.blurs", return_value=True):
            StyleSheet.set_variable("WINDOW_BLUR_OPACITY", "40%", theme="dark")
            self.assertEqual(self._fill_alpha("dark"), 50)
            StyleSheet.set_variable("WINDOW_BLUR_OPACITY", "100%", theme="dark")
            self.assertEqual(self._fill_alpha("dark"), 125)

    def test_scaling_reads_the_alpha_the_way_qt_does(self):
        """Qt reads a decimal rgba() alpha as a fraction (``0.5`` paints 127),
        an integer as 0-255; a color without alpha is opaque."""
        scale = StyleSheet._scale_alpha
        self.assertEqual(scale("rgba(100,100,100,0.5)", 0.8), "rgba(100,100,100,102)")
        self.assertEqual(scale("rgba(100,100,100,125)", 0.8), "rgba(100,100,100,100)")
        self.assertEqual(scale("rgb(100,100,100)", 0.8), "rgba(100,100,100,204)")
        self.assertEqual(scale("#646464", 0.5), "rgba(100,100,100,128)")
        self.assertEqual(scale("not a color", 0.5), "not a color")

    def test_an_alpha_of_one_reads_and_writes_the_way_qt_does(self):
        """Qt reads an rgba() alpha of 1 as a fraction -- opaque -- so 1%
        of a 125 fill (1) can't be written ``rgba(...,1)``: that painted
        the window solid where 0% and 2% were all but clear."""
        scale = StyleSheet._scale_alpha
        self.assertEqual(scale("rgba(100,100,100,1)", 0.5), "rgba(100,100,100,128)")
        self.assertEqual(
            scale("rgba(100,100,100,125)", 0.01), "rgba(100,100,100,0.004)"
        )
        self.assertEqual(scale("rgba(100,100,100,125)", 0.02), "rgba(100,100,100,2)")

    def test_eight_digit_hex_is_alpha_first_the_way_qt_reads_it(self):
        """Qt reads ``#aarrggbb``; a color it names any other way (``#rgb``,
        a name) scales and blends too, rather than passing through."""
        scale, blend = StyleSheet._scale_alpha, StyleSheet._blend
        self.assertEqual(scale("#80112233", 0.5), "rgba(17,34,51,64)")
        self.assertEqual(blend("#80000000", "#ffffff", 0.5), "#80808080")
        self.assertEqual(scale("#123", 0.5), "rgba(17,34,51,128)")
        self.assertEqual(scale("white", 0.5), "rgba(255,255,255,128)")
        self.assertEqual(blend("#000", "#ffffff", 0.5), "#808080")

    def test_percent(self):
        self.assertEqual(StyleSheet.percent("80%"), 80.0)
        self.assertEqual(StyleSheet.percent(" 62.5 %"), 62.5)
        for value in ("", None, "half"):
            self.assertEqual(StyleSheet.percent(value), 100.0, value)
        self.assertEqual(StyleSheet.percent("half", default=0.0), 0.0)

    def test_is_on(self):
        for value in ("on", "ON", " true", "yes", "1"):
            self.assertTrue(StyleSheet.is_on(value), value)
        for value in ("off", "", None, "0", "rgb(0,0,0)"):
            self.assertFalse(StyleSheet.is_on(value), value)


class TestWindowShadow(QtBaseTestCase):
    """``WINDOW_SHADOW`` (on/off), ``WINDOW_SHADOW_SIZE``,
    and ``WINDOW_SHADOW_OPACITY``: the one source of
    truth for the drop shadow under every floating surface
    (``StyleSheet.cast_shadow``)."""

    def tearDown(self):
        StyleSheet.reset_overrides()
        super().tearDown()

    def _window(self, **style):
        window = self.track_widget(
            QtWidgets.QWidget(None, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        )
        StyleSheet().set(window, **style)
        return window

    def test_every_theme_defines_its_tokens(self):
        for theme, tokens in StyleSheet.themes.items():
            for name in (
                "WINDOW_SHADOW",
                "WINDOW_SHADOW_SIZE",
                "WINDOW_SHADOW_OPACITY",
            ):
                self.assertIn(name, tokens, theme)

    def test_the_resolver_reads_the_windows_theme(self):
        window = self._window(theme="dark")
        color, size, radius = StyleSheet.window_shadow(window)
        self.assertEqual(color.getRgb(), (0, 0, 0, 209), "black at 82%")
        self.assertEqual((size, radius), (18, 0), "square, like every uitk window")
        StyleSheet.set_variable("WINDOW_SHADOW_SIZE", "24px", theme="dark")
        self.assertEqual(StyleSheet.window_shadow(window)[1], 24)

    def test_opacity_and_size_are_independent(self):
        """A fainter shadow keeps its reach, and a wider one its darkness."""
        faint = self._window(theme="dark", WINDOW_SHADOW_OPACITY="20%")
        color, size, _radius = StyleSheet.window_shadow(faint)
        self.assertEqual((color.alpha(), size), (51, 18))
        wide = self._window(theme="dark", WINDOW_SHADOW_SIZE="40px")
        color, size, _radius = StyleSheet.window_shadow(wide)
        self.assertEqual((color.alpha(), size), (209, 40))

    def test_a_popup_resolves_its_owners_theme(self):
        owner = self._window(theme="light")
        popup = QtWidgets.QWidget(owner, QtCore.Qt.Popup)
        color, size, _radius = StyleSheet.window_shadow(popup)
        self.assertEqual((color.alpha(), size), (171, 18))
        self.assertIsNone(StyleSheet.window_shadow(QtWidgets.QWidget()), "unthemed")

    def test_off_or_nothing_to_show_casts_none(self):
        """high-contrast ships it off: its white outlines do the separating."""
        self.assertIsNone(StyleSheet.window_shadow(self._window(theme="high-contrast")))
        for tokens in (
            {"WINDOW_SHADOW": "off"},
            {"WINDOW_SHADOW_SIZE": "0px"},
            {"WINDOW_SHADOW_OPACITY": "0%"},
        ):
            window = self._window(theme="dark", **tokens)
            self.assertIsNone(StyleSheet.window_shadow(window), tokens)

    def test_a_per_call_token_is_honored(self):
        """MessageBox styles itself with WINDOW_SHADOW="off": its window is a
        transparent host around an inset card."""
        window = self._window(theme="dark", WINDOW_SHADOW="off")
        self.assertIsNone(StyleSheet.window_shadow(window))
        self.assertEqual(StyleSheet.resolve_variable("WINDOW_SHADOW", window), "off")

    def test_a_surfaceless_window_casts_none(self):
        """A gesture page's buttons float over the desktop; a shadow would
        outline an invisible rectangle."""
        for style_class in StyleSheet._shadowless_classes:
            window = self._window(theme="dark", style_class=style_class)
            self.assertIsNone(StyleSheet.window_shadow(window), style_class)

    def test_a_context_menus_submenus_cast_it_too(self):
        """A submenu is a popup of its own, over the menu and the window."""
        from uitk._window_shadow import _ShadowKeeper

        owner = self._window(theme="dark")
        menu = QtWidgets.QMenu(owner)
        StyleSheet.cast_shadow(menu)
        sub = menu.addMenu("More")
        sub.addAction("x")
        menu.aboutToShow.emit()
        self.assertIsNotNone(sub.findChild(_ShadowKeeper, _ShadowKeeper.NAME))
        self.assertIsNotNone(StyleSheet.window_shadow(sub), "themed via its owner")

    def test_a_styled_window_casts_it_and_follows_a_theme_change(self):
        from uitk._window_shadow import _ShadowKeeper

        window = self._window(theme="dark")
        keeper = window.findChild(_ShadowKeeper, _ShadowKeeper.NAME)
        self.assertIsNotNone(keeper)
        window.show()
        for _ in range(3):
            QtWidgets.QApplication.processEvents()
        self.assertTrue(keeper.window.isVisible())
        StyleSheet.set_variable("WINDOW_SHADOW", "off", theme="dark")
        for _ in range(3):
            QtWidgets.QApplication.processEvents()
        self.assertFalse(keeper.window.isVisible())


# Renders one styled window under a given HOST application style and palette,
# in a child process (the application style is process-wide), and prints the
# image's digest.
_HOST_RENDER = r"""
import hashlib, sys
from qtpy import QtCore, QtGui, QtWidgets as W
app = W.QApplication([])
app.setStyle(W.QStyleFactory.create(sys.argv[1]))
pal = app.style().standardPalette()
if sys.argv[2] == "dark":
    for role, c in (("Window", 68), ("WindowText", 200), ("Base", 43), ("Text", 200),
                    ("Button", 93), ("ButtonText", 238), ("Highlight", 120), ("Mid", 50),
                    ("Dark", 35), ("Light", 110), ("AlternateBase", 60)):
        pal.setColor(getattr(QtGui.QPalette, role), QtGui.QColor(c, c, c))
app.setPalette(pal)
app.setFont(QtGui.QFont("Arial", 9))
from uitk.themes.style_sheet import StyleSheet
from uitk.widgets.treeWidget import TreeWidget
from uitk.widgets.sequencer._data import MenuUtils
win = W.QWidget(None, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
lay = W.QVBoxLayout(win)
tabs = W.QTabWidget(); tabs.addTab(W.QLabel("one"), "One"); tabs.addTab(W.QLabel("two"), "Two")
group = W.QGroupBox("Group"); group.setCheckable(True)
line = W.QLineEdit(); line.setPlaceholderText("placeholder")
bar = W.QProgressBar(); bar.setValue(60)
table = W.QTableWidget(2, 2); table.setSortingEnabled(True)
tree = TreeWidget(); tree.enable_hierarchy_icons(True)
top = W.QTreeWidgetItem(["parent"]); top.addChild(W.QTreeWidgetItem(["child"]))
tree.addTopLevelItem(top); top.setExpanded(True)
for w in (tabs, group, line, bar, table, tree):
    lay.addWidget(w)
StyleSheet().set(win, theme="dark")
win.resize(300, 420)
images = [win.grab().toImage()]
for menu in (W.QMenu(win), MenuUtils.styled_menu(win)):
    act = menu.addAction("checked"); act.setCheckable(True); act.setChecked(True)
    menu.addMenu("sub").addAction("x")
    menu.ensurePolished(); menu.adjustSize()
    images.append(menu.grab().toImage())
digest = hashlib.md5()
for img in images:
    img = img.convertToFormat(QtGui.QImage.Format_ARGB32)
    digest.update(bytes(img.constBits())[: img.sizeInBytes()])
print("DIGEST", digest.hexdigest())
"""


class TestHostIndependence(QtBaseTestCase):
    """What the sheet leaves undefined must not fall to the HOST: Maya runs its
    own style and palette, Blender and a standalone app the OS's. The same
    window renders pixel-identical under two different host styles and
    palettes (``StyleSheet.pin_base_style`` + the root palette rule)."""

    @staticmethod
    def _render(style: str, tone: str) -> str:
        import os
        import subprocess
        import sys

        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
        out = subprocess.run(
            [sys.executable, "-c", _HOST_RENDER, style, tone],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        digests = [
            ln.split()[1] for ln in out.stdout.splitlines() if ln.startswith("DIGEST")
        ]
        if not digests:
            raise AssertionError(
                f"render failed (rc={out.returncode}): {out.stderr[-3000:]}"
            )
        return digests[0]

    def test_a_styled_window_renders_the_same_under_any_host(self):
        self.assertEqual(
            self._render("Windows", "light"), self._render("Fusion", "dark")
        )

    def test_a_widget_drawn_by_the_sheet_takes_no_host_palette(self):
        """The root rule sets every palette role a sheet can: text, selection
        and alternate rows read the theme's, not the application's."""
        app = QtWidgets.QApplication.instance()
        original = app.palette()
        try:
            host = QtGui.QPalette(original)
            for role in (
                QtGui.QPalette.WindowText,
                QtGui.QPalette.Text,
                QtGui.QPalette.Highlight,
            ):
                host.setColor(role, QtGui.QColor(255, 0, 255))
            app.setPalette(host)
            window = self.track_widget(QtWidgets.QWidget())
            child = QtWidgets.QTreeView(window)
            StyleSheet().set(window, theme="dark")
            child.ensurePolished()
            pal = child.palette()
            magenta = QtGui.QColor(255, 0, 255)
            for role in (
                QtGui.QPalette.WindowText,
                QtGui.QPalette.Text,
                QtGui.QPalette.Highlight,
            ):
                self.assertNotEqual(pal.color(role), magenta, role)
        finally:
            app.setPalette(original)

    def test_a_styled_window_is_drawn_over_the_pinned_base_style(self):
        window = self.track_widget(QtWidgets.QWidget())
        StyleSheet().set(window, theme="dark")
        self.assertTrue(window.testAttribute(QtCore.Qt.WA_SetStyle))
        # A style a widget set itself is kept (ComboBox's Fusion proxy).
        own = QtWidgets.QStyleFactory.create("Windows")
        keeper = self.track_widget(QtWidgets.QWidget())
        keeper.setStyle(own)
        StyleSheet.pin_base_style(keeper)
        self.assertTrue(keeper.testAttribute(QtCore.Qt.WA_SetStyle))
        self.assertIs(StyleSheet.base_style(), StyleSheet.base_style())


if __name__ == "__main__":
    unittest.main()
