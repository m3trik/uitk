# !/usr/bin/python
# coding=utf-8
from typing import Union
import re
from PySide2 import QtCore, QtWidgets
import pythontk as ptk


class StyleSheet(QtCore.QObject):
    """StyleSheet class is responsible for generating, modifying, and applying CSS style sheets for various Qt widgets.
    The class also provides utility functions to adjust the appearance of widgets based on their properties or conditions.
    The StyleSheet class offers multiple theme presets (e.g., 'light' and 'dark') and allows the user to create custom
    theme presets by providing a color value dictionary.

    Methods:
    - get_color_values(cls, theme="light", **kwargs): Return the colorValues dict with any of the bracketed
                placeholders replaced by the value of any given kwargs of the same name.
    - remove_leading_whitespace(s): Remove the same amount of leading whitespace from each line in the input string
                as present in the first line.
    - get_style_sheet(cls, widget_type=None, theme="light", **kwargs): Get the styleSheet for the given widget type.
    - set_style(cls, widget, ratio=6, theme="light", hide_menu_button=False, append_to_existing=False, **kwargs): Set the
                styleSheet for the given widgets.
    - adjust_padding(widget_type): Remove padding when the text length / widget width ratio is below a given amount.
    - hide_menu_button(widget_type): Set the menu button as transparent.
    """

    themes = {
        "light": {
            "MAIN_FOREGROUND": "rgb(255,255,255)",  # Bright white for better contrast
            "MAIN_BACKGROUND": "rgb(70,70,70)",  # Slightly darker than widget background
            "MAIN_BACKGROUND_ALPHA": "rgba(70,70,70,185)",
            "WIDGET_BACKGROUND": "rgb(125,125,125)",  # As per your request
            "BUTTON_PRESSED": "rgb(120,120,120)",  # Slightly darker than widget background
            "BUTTON_HOVER": "rgb(82,133,166)",
            "TEXT_COLOR": "rgb(255,255,255)",  # Bright white for better contrast
            "TEXT_CHECKED": "rgb(255,255,255)",  # Bright white for better contrast
            "TEXT_DISABLED": "rgba(150,150,150,175)",
            "TEXT_HOVER": "rgb(255,255,255)",  # Bright white for better contrast
            "TEXT_BACKGROUND": "rgb(70,70,70)",  # Same as main background
            "BORDER_COLOR": "rgba(40,40,40)",  # Slightly darker than widget background
            "HIGHLIGHT_COLOR": "rgb(255,255,190)",
            "DISABLED_BACKGROUND": "rgb(85,85,85)",
            "PROGRESS_BAR_COLOR": "rgb(0,160,208)",
        },
        "dark": {
            "MAIN_FOREGROUND": "rgb(200,200,200)",  # Lighter color for better contrast
            "MAIN_BACKGROUND": "rgb(90,90,90)",  # Darker than widget background
            "MAIN_BACKGROUND_ALPHA": "rgba(90,90,90,185)",
            "WIDGET_BACKGROUND": "rgb(60,60,60)",  # As per your request
            "BUTTON_PRESSED": "rgb(50,50,50)",  # Slightly darker than widget background
            "BUTTON_HOVER": "rgb(82,133,166)",
            "TEXT_COLOR": "rgb(220,220,220)",  # Lighter color for better contrast
            "TEXT_CHECKED": "rgb(255,255,255)",  # Bright white for better contrast
            "TEXT_DISABLED": "rgba(150,150,150,175)",
            "TEXT_HOVER": "rgb(255,255,255)",  # Bright white for better contrast
            "TEXT_BACKGROUND": "rgb(30,30,30)",  # Same as main background
            "BORDER_COLOR": "rgb(20,20,20)",  # Slightly darker than widget background
            "HIGHLIGHT_COLOR": "rgb(255,255,190)",
            "DISABLED_BACKGROUND": "rgb(35,35,35)",  # Slightly darker than main background
            "PROGRESS_BAR_COLOR": "rgb(0,160,208)",
        },
    }

    style_sheets = {
        "QWidget": """
            QWidget {
                background-color: transparent;
                border: none;
            }
            QWidget::item:selected {
                background-color: {BUTTON_HOVER};
            }
            QWidget.centralWidget {
                background-color: {MAIN_BACKGROUND_ALPHA};
                border: 1px solid {BORDER_COLOR};
                color: {TEXT_COLOR};
            }
            QWidget.QLabel {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 1px;
                padding: 0px 1px 0px 1px; /* top, right, bottom, left */
            }
        """,
        "QStackedWidget": """
            QStackedWidget {
                background-color: {MAIN_BACKGROUND};
            }
            QStackedWidget QFrame {
                background-color: {MAIN_BACKGROUND};
            }
        """,
        "QMainWindow": """
            QMainWindow {
                background-color: {MAIN_BACKGROUND_ALPHA};
                border: 1px solid {BORDER_COLOR};
            }
        """,
        "QGroupBox": """
            QGroupBox {
                border: none;
                border-radius: 1px;
                padding: 1px 1px 1px 1px; /* top, right, bottom, left */
                margin: 12px 0px 1px 0px; /* top, right, bottom, left */
                background-color: {MAIN_BACKGROUND_ALPHA};
            }
            QGroupBox::title {
                top: -13px;
                background-color: {MAIN_BACKGROUND_ALPHA};
                color: {TEXT_COLOR};
            }
        """,
        "QMenu": """
            QMenu {
                background-color: {MAIN_BACKGROUND_ALPHA};
                border: 1px solid {BORDER_COLOR};
                margin: 0px; /* spacing around the menu */
            }
            QMenu::item {
                padding: 0px 1px 0px 1px; /* top, right, bottom, left */
                border: none; /* reserve space for selection border */
            }
            QMenu::item:selected {
                border-color: {BUTTON_HOVER};
                background-color: {MAIN_BACKGROUND};
            }
            QMenu::icon:checked { /* appearance of a 'checked' icon */
                background-color: gray;
                border: 1px inset gray;
                position: absolute;
                top: 1px;
                right: 1px;
                bottom: 1px;
                left: 1px;
            }
            QMenu::separator {
                height: 2px;
                background-color: {MAIN_BACKGROUND};
                margin: 0px 5px 0px 10px; /* top, right, bottom, left */
            }
            QMenu::indicator {
                width: 13px;
                height: 13px;
            }
        """,
        "QMenuBar": """
            QMenuBar {
                background-color: {MAIN_BACKGROUND};
                spacing: 1px; /* spacing between menu bar items */
            }
            QMenuBar::item {
                padding: 1px 4px;
                background-color: transparent;
                border-radius: 1px;
            }
            QMenuBar::item:selected { /* when selected using mouse or keyboard */
                background-color: {BUTTON_HOVER};
            }
            QMenuBar::item:pressed {
                background-color: gray;
            }
        """,
        "QLabel": """
            QLabel {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 1px;
                padding: 0px 1px 0px 1px; /* top, right, bottom, left */
            }
            QLabel::hover {
                border: 1px solid {BORDER_COLOR};
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QLabel::enabled {
                color: {TEXT_COLOR};
            }
            QLabel::disabled {
                color: {TEXT_DISABLED};
            }
        """,
        "QAbstractButton": """
            QAbstractButton {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                border-style: outset;
                border-radius: 1px;
                border: 1px solid {BORDER_COLOR};
                padding: 0px 1px 0px 1px; /* top, right, bottom, left */
                spacing: 1px;
            }
            QAbstractButton::hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QAbstractButton::hover:checked {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QAbstractButton::enabled {
                color: {TEXT_COLOR};
            }
            QAbstractButton::disabled {
                color: {TEXT_DISABLED};
            }
            QAbstractButton::checked {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QAbstractButton::checked:hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QAbstractButton::indicator {
                width: 0px;
                height: 0px;
                border: none;
            }
            QAbstractButton::indicator::unchecked {
                image: none;
            }
            QAbstractButton::indicator:unchecked:hover {
                image: none;
            }
            QAbstractButton::indicator:unchecked:pressed {
                image: none;
            }
            QAbstractButton::indicator::checked {
                image: none;
            }
            QAbstractButton::indicator:checked:hover {
                image: none;
            }
            QAbstractButton::indicator:checked:pressed {
                image: none;
            }
        """,
        "QPushButton": """
            /* Inherits from QAbstractButton */
            QPushButton#toggle_expand {
                border: none;
                padding: 0px 0px 0px 0px; /* top, right, bottom, left */
                background-color: {MAIN_BACKGROUND};
            }
            QPushButton:flat {
                border: none; /* no border for a flat push button */
            }
            QPushButton:default {
                border-color: navy; /* make the default button prominent */
            }
        """,
        "QToolButton": """
            /* Inherits from QAbstractButton */
            QToolButton[popupMode="1"] { /* only for MenuButtonPopup */
                padding-right: 2px; /* make way for the popup button */
            }
            QToolButton:open { /* when the button has its menu open */
                background-color: dark gray;
            }
            /* popupMode set to DelayedPopup or InstantPopup */
            QToolButton::menu-indicator {
                image: none;
                subcontrol-origin: padding;
                subcontrol-position: bottom right;
                padding: 0px 5px 5px 0px; /* top, right, bottom, left */
            }
            QToolButton::down-arrow, QToolButton::up-arrow, QToolButton::left-arrow, QToolButton::right-arrow {
                image: none;
                padding: 0px 15px 0px 0px; /* top, right, bottom, left */
            }
            QToolButton::down-arrow:hover, QToolButton::up-arrow:hover, QToolButton::left-arrow:hover, QToolButton::right-arrow:hover {
                padding: 0px 5px 0px 0px; /* top, right, bottom, left */
            }
            /* the subcontrols below are used only in the MenuButtonPopup mode */
            QToolButton::menu-button {
                border: 1px solid {TEXT_COLOR};
                margin: 4px 2px 4px 0px; /* top, right, bottom, left */
            }
            QToolButton::menu-button:pressed {
                background-color: transparent;
                border: none;
            }
            QToolButton::menu-arrow {
                image: none;
            }
        """,
        "QCheckBox": """
            /* Inherits from QAbstractButton */
        """,
        "QRadioButton": """
            /* Inherits from QAbstractButton */
        """,
        "QAbstractSpinBox": """
            QAbstractSpinBox {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
            }
            QAbstractSpinBox::disabled {
                color: {TEXT_DISABLED};
            }
            QAbstractSpinBox::hover {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_HOVER};
                border: 1px solid {BORDER_COLOR};
            }
            QScrollBar:left-arrow, QScrollBar::right-arrow, QScrollBar::up-arrow, QScrollBar::down-arrow {
                border: 1px solid {BUTTON_PRESSED};
                width: 3px;
                height: 3px;
            }
            QAbstractSpinBox::up-arrow, QAbstractSpinBox::down-arrow {
                width: 3px;
                height: 3px;
                border: 1px solid {BUTTON_PRESSED};
            }
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                border: 1px solid {BUTTON_PRESSED};
                background-color: {WIDGET_BACKGROUND};
                subcontrol-origin: border;
            }
        """,
        "QSpinBox": """
            /* Inherits from QAbstractSpinBox */
        """,
        "QDoubleSpinBox": """
            /* Inherits from QAbstractSpinBox */
        """,
        "QComboBox": """
            QComboBox {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                padding: 0px 1px 0px 1px; /* top, right, bottom, left */
                border-radius: 1px;
                min-width: 0em;
            }
            QComboBox::hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QComboBox::open {
                selection-background-color: {WIDGET_BACKGROUND};
                selection-color: {TEXT_CHECKED};
            }
            QComboBox:on { /* shift the text when the popup opens */
                padding-top: 3px;
            }
            QComboBox::down-arrow {
                width: 0px;
                height: 0px;
                background-color: {WIDGET_BACKGROUND};
                border: none;
                image: url(path/to/down_arrow.png);
            }
            QComboBox::drop-down {
                border: none;
                background-color: {WIDGET_BACKGROUND};
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 0px;
                height: 0px;
                border-left-width: 1px;
                border-left-color: {TEXT_CHECKED};
                border-left-style: solid; /* just a single line */
                border-top-right-radius: 1px; /* same radius as the QComboBox */
                border-bottom-right-radius: 1px;
            }
            QComboBox QAbstractItemView {
                selection-background-color: {BUTTON_HOVER};
            }
        """,
        "QFrame": """
            QFrame {
                border-radius: 1px;
            }
        """,
        "QAbstractScrollArea": """
            QAbstractScrollArea {
                background-color: {WIDGET_BACKGROUND};
                border: 1px solid {BORDER_COLOR};
                selection-background-color: {BUTTON_HOVER};
                selection-color: {TEXT_COLOR};
            }
        """,
        "QScrollArea": """
            /* Inherits from QAbstractScrollArea */
        """,
        "QGraphicsView": """
            /* Inherits from QAbstractScrollArea */
        """,
        "QMdiArea": """
            /* Inherits from QAbstractScrollArea */
        """,
        "QPlainTextEdit": """
            /* Inherits from QAbstractScrollArea */
        """,
        "QTextEdit": """
            /* Inherits from QAbstractScrollArea */
            QTextEdit {
                color: {TEXT_COLOR};
                background-attachment: fixed; /* fixed, scroll */
            }
            QTextEdit#hud_text {
                border: none;
                background-color: transparent;
                color: white;
                selection-background-color: {TEXT_BACKGROUND};
                selection-color: white;
            }
        """,
        "QLineEdit": """
            /* Inherits from QWidget */
            QLineEdit {
                background-color: {WIDGET_BACKGROUND};
                border: 1px solid {BORDER_COLOR};
                selection-background-color: {BUTTON_HOVER};
                selection-color: {TEXT_COLOR};
                border-radius: 1px;
                padding: 0 8px;
            }
            QLineEdit::disabled {
                color: {MAIN_BACKGROUND};
            }
            QLineEdit::enabled {
                color: {TEXT_COLOR};
            }
            QLineEdit:read-only {
                background-color: {MAIN_BACKGROUND};
            }
        """,
        "QAbstractItemView": """
            QAbstractItemView {
                alternate-background-color: {MAIN_BACKGROUND};
                background-attachment: fixed; /* fixed, scroll */
                color: {TEXT_COLOR};
            }
            QAbstractItemView::item:alternate {
                background-color: {MAIN_BACKGROUND};
            }
            QAbstractItemView::item:selected {
                border: 1px solid {BORDER_COLOR};
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QAbstractItemView::item:selected:!active {
                background-color: {BUTTON_HOVER};
                color: {TEXT_COLOR};
            }
            QAbstractItemView::item:selected:active {
                background-color: {BUTTON_HOVER};
                color: {TEXT_COLOR};
            }
            QAbstractItemView::item:hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
        """,
        "QListWidget": """
            /* Inherits from QAbstractItemView */
        """,
        "QListView": """
            /* Inherits from QAbstractItemView */
        """,
        "QHeaderView": """
            QHeaderView {
                border: 1px solid {BUTTON_PRESSED};
            }
            QHeaderView::section {
                background-color: {BUTTON_PRESSED};
                border: 1px solid {BUTTON_PRESSED};
                padding: 1px;
            }
            QHeaderView::section:selected, QHeaderView::section::checked {
                background-color: {MAIN_BACKGROUND};
            }
        """,
        "QTableView": """
            /* Inherits from QAbstractItemView */
        """,
        "QTreeView": """
            /* Inherits from QAbstractItemView */
            QTreeView::branch {
                background: palette(base);
                border-image: none;
                border-width: 0;
                border-style: solid;
                border-color: {MAIN_BACKGROUND};
            }
        """,
        "QAbstractSlider": """
            QAbstractSlider {
                border: 1px solid {BORDER_COLOR};
                background-color: {WIDGET_BACKGROUND};
            }
            QAbstractSlider::handle {
                width: 10px;
                margin-top: -6px;
                margin-bottom: -6px;
                border: 1px solid {BORDER_COLOR};
                border-radius: 1px;
                background-color: {MAIN_BACKGROUND};
            }
            QAbstractSlider::handle:hover {
                background-color: {BUTTON_HOVER};
            }
            QAbstractSlider::groove {
                border: 1px solid {BORDER_COLOR};
                height: 8px;
                background-color: {WIDGET_BACKGROUND};
            }
            QAbstractSlider::sub-page {
                background-color: {WIDGET_BACKGROUND};
            }
            QAbstractSlider::add-page {
                background-color: {WIDGET_BACKGROUND};
            }
        """,
        "QSlider": """
            /* Inherits from QAbstractSlider */
        """,
        "QScrollBar": """
            /* Inherits from QAbstractSlider */
            QScrollBar:vertical, QScrollBar:horizontal {
                background: {WIDGET_BACKGROUND};
                border: none;
                width: 10px;
                margin: 0px 0 0px 0;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: {MAIN_BACKGROUND};
                min-height: 20px;
                min-width: 20px;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background: {BUTTON_HOVER};
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
                height: 0px;
                width: 0px;
                subcontrol-position: top left;
                subcontrol-origin: margin;
            }
            QScrollBar::add-line:vertical:hover, QScrollBar::sub-line:vertical:hover,
            QScrollBar::add-line:horizontal:hover, QScrollBar::sub-line:horizontal:hover {
                height: 0px;
                width: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                height: 0px;
                width: 0px;
                background: none;
            }
        """,
        "QProgressBar": """
            QProgressBar {
                border: none;
                text-align: center;
                padding: 1px;
                background-color: {MAIN_BACKGROUND};
            }
            QProgressBar::chunk {
                background-color: {BUTTON_HOVER};
                width: 10px;
                margin: 0.5px;
            }
        """,
        # ... custom classes ...
        "default": """
            .default {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                border-style: outset;
                border-radius: 1px;
                border: 1px solid {BORDER_COLOR};
                padding: 0px 1px 0px 1px; /* top, right, bottom, left */
                spacing: 1px;
            }
            .default::hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            .default::hover:checked {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            .default::enabled {
                color: {TEXT_COLOR};
            }
            .default::disabled {
                color: {TEXT_DISABLED};
            }
        """,
        "transparentBgNoBorder": """
            .transparentBgNoBorder {
                background-color: transparent;
                border: none;
                color: {TEXT_COLOR};
                selection-background-color: {TEXT_BACKGROUND};
                selection-color: {HIGHLIGHT_COLOR};
            }
        """,
        "translucentBgNoBorder": """
            .translucentBgNoBorder {
                background-color: rgba(127,127,127,0.004);
                border: none;
                color: {TEXT_COLOR};
                selection-background-color: {TEXT_BACKGROUND};
                selection-color: {HIGHLIGHT_COLOR};
            }
        """,
        "translucentBgWithBorder": """
            .translucentBgWithBorder {
                background-color: {MAIN_BACKGROUND_ALPHA};
                border: 1px solid {BORDER_COLOR};
                color: {TEXT_COLOR};
                selection-background-color: {TEXT_BACKGROUND};
                selection-color: {HIGHLIGHT_COLOR};
            }
        """,
        "noBorder": """
            .noBorder {
                border: 0px none;
            }
        """,
        "withBorder": """
            .withBorder {
                border: 1px solid {BORDER_COLOR};
            }
        """,
        "noPadding": """
            .noPadding {
                padding: 0px 0px 0px 0px; /* top, right, bottom, left */
            }
        """,
        "noHover": """
            .noHover:hover {
                background-color: {WIDGET_BACKGROUND};
            }
        """,
        "textBold": """
            .textBold {
                font-weight: bold;
            }
        """,
    }

    def get_style_sheet(self, widget_type=None, style="light", **kwargs):
        """Get the styleSheet for the given widget type.
        By default it will return all stylesheets as one multi-line css string.

        Parameters:
            widget_type (str): The class name of the widget. ie. 'QLabel'
            style (str): The color value set to use. valid values are: 'light', 'dark'

        Returns:
            (str) css styleSheet
        """
        css = (
            "".join(self.style_sheets.values())
            if widget_type is None
            else self.style_sheets.get(widget_type, "")
        )

        is_valid_widget_type = bool(getattr(QtWidgets, str(widget_type), None))
        if not css and is_valid_widget_type:
            raise ValueError(
                f"# Error: {__file__} in get_style_sheet\n#\tKeyError: '{widget_type}'"
            )
            return ""

        for k, v in self.get_color_values(style=style, **kwargs).items():
            css = css.replace(f"{{{k.upper()}}}", v)

        return self.remove_leading_whitespace(css)

    @staticmethod
    def get_super_type(widget_type):
        """Get the name of the immediate superclass of a widget type"""
        widget_class = getattr(QtWidgets, widget_type, None)
        if widget_class is not None:
            super_class = widget_class.__base__
            return super_class.__name__
        return None

    def get_style_hierarchy(self, widget_type, theme="light", **kwargs):
        """Recursively find and apply styles from the most abstract class to the specific class"""
        super_type = self.get_super_type(widget_type)

        # Try to get the style for the current widget type
        try:
            style = self.get_style_sheet(widget_type, theme=theme, **kwargs)
        except KeyError:
            style = ""

        # If this widget type has a superclass and it's not QWidget (since we already have a style for QWidget),
        # get the style of its superclass
        if super_type and super_type != "QWidget":
            try:
                super_style = self.get_style_sheet(super_type, theme=theme, **kwargs)
            except KeyError:
                super_style = ""
        else:
            super_style = ""

        return super_style, style

    @ptk.listify
    def set_style(
        self,
        widget: Union[QtWidgets.QWidget, None] = None,
        theme="light",
        style_class="",
        **kwargs,
    ):
        """Set the styleSheet for the given widgets.
        Set the theme for a specific widget by using the '#' syntax and the widget's objectName. ie. QWidget#mainWindow

        Parameters:
            widget (obj/list): The widget to set the theme of.
            theme (str): Color mode. ie. 'light' or 'dark'
            style_class: Assign a custom style class to the widget.
        """
        if widget is None:
            widget = self

        if not isinstance(widget, QtWidgets.QWidget):
            raise ValueError(
                f"Invalid datatype for widget: expected QWidget, got {type(widget)}."
            )

        if style_class:
            widget.setProperty("class", style_class)

        # Check if the widget is a QMainWindow, and set the central widget class
        if isinstance(widget, QtWidgets.QMainWindow):
            widget.centralWidget().setProperty("class", style_class)

        # If the widget is a QMainWindow, apply the combined stylesheet
        if widget is self:
            final_style = self.get_style_sheet(theme=theme, **kwargs)
        else:  # Otherwise, apply the abstract style first, then the specific widget style
            widget_type = ptk.get_derived_type(
                widget, module="QtWidgets", return_name=True
            )
            super_style, style = self.get_style_hierarchy(
                widget_type, theme=theme, **kwargs
            )

            # Check for custom class style
            custom_style_class = widget.property("class")
            if custom_style_class and custom_style_class in self.style_sheets:
                style = self.get_style_sheet(custom_style_class, theme=theme, **kwargs)

            final_style = super_style + "\n" + style

        widget.setStyleSheet(final_style)

    @classmethod
    def get_color_values(cls, theme="light", **kwargs):
        """Return the colorValues dict with any of the bracketed placeholders
        replaced by the value of any given kwargs of the same name.

        Parameters:
            theme (str)(dict): The color value set to use. valid values are: 'light', 'dark'
                        or pass your own theme as a dict.
            **kwargs () = Keyword arguments matching the string of any bracketed placeholders.
                        case insensitive.  ex. alpha=255
        Returns:
            (dict) The color values with placeholder values. ex. {'MAIN_BACKGROUND_ALPHA': 'rgba(100,100,100,75)', etc..
        """
        if isinstance(theme, dict):
            return {
                k: v.format(**{k.upper(): v for k, v in kwargs.items()})
                for k, v in theme.items()
            }
        else:
            return {
                k: v.format(**{k.upper(): v for k, v in kwargs.items()})
                for k, v in cls.themes[theme].items()
            }

    @staticmethod
    def remove_leading_whitespace(style_sheet):
        """Remove the same amount of leading whitespace from each line in the input string as
        present in the first line.

        Parameters:
            style_sheet (str): Input string containing lines with leading whitespace.

        Returns:
            (str): Output string with leading whitespace removed from each line.
        """
        style_sheet = style_sheet.strip(
            "\n"
        )  # Remove leading and trailing newline characters
        lines = style_sheet.splitlines()
        if lines:
            leading_whitespace = re.match(r"^(\s*)", lines[0]).group(1)
            style_sheet = "\n".join(
                [re.sub(f"^{leading_whitespace}", "", line) for line in lines]
            )
        return style_sheet

    @staticmethod
    def adjust_padding(widget_type):
        """Remove padding when the text length / widget width ratio is below a given amount.

        Example:
            try:
                length = (  # a 'NoneType' error will be thrown if the widget does not contain text.
                    len(widget.text())
                    if hasattr(widget, "text")
                    else len(str(widget.value()))
                )
            except (AttributeError, ZeroDivisionError) as error:
                print (__name__.ljust(26), 'setStyle (adjustPadding)', widget.objectName().ljust(26), widget.__class__.__name__.ljust(25), error)

            # ratio of widget size, text length (using integer division).
            if widget.size().width() // length > ratio:
                final_style = final_style + self.adjust_padding(widget_type)
        """
        return """
            {0} {{
                padding: 0px 0px 0px 0px;
            }}""".format(
            widget_type
        )

    @staticmethod
    def hide_menu_button(widget_type):
        """Set the menu button as transparent."""
        return """
            {0}::menu-button {{
                border: none;
            }}

            {0}::menu-button::hover {{
                border: none;
            }}""".format(
            widget_type
        )


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    pass

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------

"""
# css commenting:
    /* multi-line */

# setting a property:
    app.setStyleSheet("QLineEdit#name[prop=true] {background-color:transparent;}") #does't effect the lineEdit with objectName 'name' if that buttons property 'styleSheet' is false (c++ lowercase).
    widget.setProperty('prop', True)

# gradients:
    background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #E0E0E0, stop: 1 #FFFFFF);

# Set multiple widgets:
    QComboBox:!editable, QComboBox::drop-down:editable { ... }

# Set the style for a specific widget:
    QWidget#mainWindow ('#' syntax, followed by the widget's objectName)

# Add multiple child widgets to a single CSS rule by separating them with a space:
    QListWidget QPushButton, QListWidget QLabel { ... }

# Use the wildcard * to match any child widget of a widget, like this:
    QListWidget * { ... }


#qt styleSheet reference
http://doc.qt.io/qt-5/stylesheet-reference.html#qtabbar-widget


List of Pseudo-States:
:active             This state is set when the widget resides in an active window.
:adjoins-item       This state is set when the ::branch of a QTreeView is adjacent to an item.
:alternate          This state is set for every alternate row whe painting the row of a QAbstractItemView when QAbstractItemView::alternatingRowColors() is set to true.
:bottom             The item is positioned at the bottom. For example, a QTabBar that has its tabs positioned at the bottom.
:checked            The item is checked. For example, the checked state of QAbstractButton.
:closable           The items can be closed. For example, the QDockWidget has the QDockWidget::DockWidgetClosable feature turned on.
:closed             The item is in the closed state. For example, an non-expanded item in a QTreeView
:default            The item is the default. For example, a default QPushButton or a default action in a QMenu.
:disabled           The item is disabled.
:editable           The QComboBox is editable.
:edit-focus         The item has edit focus (See QStyle::State_HasEditFocus). This state is available only for Qt Extended applications.
:enabled            The item is enabled.
:exclusive          The item is part of an exclusive item group. For example, a menu item in a exclusive QActionGroup.
:first              The item is the first (in a list). For example, the first tab in a QTabBar.
:flat               The item is flat. For example, a flat QPushButton.
:floatable          The items can be floated. For example, the QDockWidget has the QDockWidget::DockWidgetFloatable feature turned on.
:focus              The item has input focus.
:has-children       The item has children. For example, an item in a QTreeView that has child items.
:has-siblings       The item has siblings. For example, an item in a QTreeView that siblings.
:horizontal         The item has horizontal orientation
:hover              The mouse is hovering over the item.
:indeterminate      The item has indeterminate state. For example, a QCheckBox or QRadioButton is partially checked.
:last               The item is the last (in a list). For example, the last tab in a QTabBar.
:left               The item is positioned at the left. For example, a QTabBar that has its tabs positioned at the left.
:maximized          The item is maximized. For example, a maximized QMdiSubWindow.
:middle             The item is in the middle (in a list). For example, a tab that is not in the beginning or the end in a QTabBar.
:minimized          The item is minimized. For example, a minimized QMdiSubWindow.
:movable            The item can be moved around. For example, the QDockWidget has the QDockWidget::DockWidgetMovable feature turned on.
:no-frame           The item has no frame. For example, a frameless QSpinBox or QLineEdit.
:non-exclusive      The item is part of a non-exclusive item group. For example, a menu item in a non-exclusive QActionGroup.
:off                For items that can be toggled, this applies to items in the "off" state.
:on                 For items that can be toggled, this applies to widgets in the "on" state.
:only-one           The item is the only one (in a list). For example, a lone tab in a QTabBar.
:open               The item is in the open state. For example, an expanded item in a QTreeView, or a QComboBox or QPushButton with an open menu.
:next-selected      The next item (in a list) is selected. For example, the selected tab of a QTabBar is next to this item.
:pressed            The item is being pressed using the mouse.
:previous-selected  The previous item (in a list) is selected. For example, a tab in a QTabBar that is next to the selected tab.
:read-only          The item is marked read only or non-editable. For example, a read only QLineEdit or a non-editable QComboBox.
:right              The item is positioned at the right. For example, a QTabBar that has its tabs positioned at the right.
:selected           The item is selected. For example, the selected tab in a QTabBar or the selected item in a QMenu.
:top                The item is positioned at the top. For example, a QTabBar that has its tabs positioned at the top.
:unchecked          The item is unchecked.
:vertical           The item has vertical orientation.
:window             The widget is a window (i.e top level widget)


List of Sub-Controls:
::add-line          The button to add a line of a QScrollBar.
::add-page          The region between the handle (slider) and the add-line of a QScrollBar.
::branch            The branch indicator of a QTreeView.
::chunk             The progress chunk of a QProgressBar.
::close-button      The close button of a QDockWidget or tabs of QTabBar
::corner            The corner between two scrollbars in a QAbstractScrollArea
::down-arrow        The down arrow of a QComboBox, QHeaderView (sort indicator), QScrollBar or QSpinBox.
::down-button       The down button of a QScrollBar or a QSpinBox.
::drop-down         The drop-down button of a QComboBox.
::float-button      The float button of a QDockWidget
::groove            The groove of a QSlider.
::indicator         The indicator of a QAbstractItemView, a QCheckBox, a QRadioButton, a checkable QMenu item or a checkable QGroupBox.
::handle            The handle (slider) of a QScrollBar, a QSplitter, or a QSlider.
::icon              The icon of a QAbstractItemView or a QMenu.
::item              An item of a QAbstractItemView, a QMenuBar, a QMenu, or a QStatusBar.
::left-arrow        The left arrow of a QScrollBar.
::left-corner       The left corner of a QTabWidget. For example, this control can be used to control position the left corner widget in a QTabWidget.
::menu-arrow        The arrow of a QToolButton with a menu.
::menu-button       The menu button of a QToolButton.
::menu-indicator    The menu indicator of a QPushButton.
::right-arrow       The right arrow of a QMenu or a QScrollBar.
::pane              The pane (frame) of a QTabWidget.
::right-corner      The right corner of a QTabWidget. For example, this control can be used to control the position the right corner widget in a QTabWidget.
::scroller          The scroller of a QMenu or QTabBar.
::section           The section of a QHeaderView.
::separator         The separator of a QMenu or in a QMainWindow.
::sub-line          The button to subtract a line of a QScrollBar.
::sub-page          The region between the handle (slider) and the sub-line of a QScrollBar.
::tab               The tab of a QTabBar or QToolBox.
::tab-bar           The tab bar of a QTabWidget. This subcontrol exists only to control the position of the QTabBar inside the QTabWidget. To style the tabs using the ::tab subcontrol.
::tear              The tear indicator of a QTabBar.
::tearoff           The tear-off indicator of a QMenu.
::text              The text of a QAbstractItemView.
::title             The title of a QGroupBox or a QDockWidget.
::up-arrow          The up arrow of a QHeaderView (sort indicator), QScrollBar or a QSpinBox.
::up-button         The up button of a QSpinBox.

List of Colors (Qt namespace (ie. Qt::red)):
white
black
red
darkRed
green
darkGreen
blue
darkBlue
cyan
darkCyan
magenta
darkMagenta
yellow
darkYellow
gray
darkGray
lightGray
color0 (zero pixel value) (transparent, i.e. background)
color1 (non-zero pixel value) (opaque, i.e. foreground)





image urls:
url(menu_indicator.png);
url(vline.png) 0;
url(handle.png);
url(close.png)
url(close-hover.png)
url(rightarrow.png);
url(leftarrow.png);
url(downarrow.png);
url(down_arrow.png);
url(up_arrow.png);
url(tear_indicator.png);
url(scrollbutton.png) 2;
url(branch-closed.png);
url(branch-open.png);
url(branch-more.png) 0;
url(branch-end.png) 0;
url(branch-open.png);
url(images/splitter.png);
url(images/splitter_pressed.png);
url(:/images/up_arrow.png);
url(:/images/up_arrow_disabled.png);
url(:/images/down_arrow.png);
url(:/images/down_arrow_disabled.png);
url(:/images/spindown.png) 1;
url(:/images/spindown_hover.png) 1;
url(:/images/spindown_pressed.png) 1;
url(:/images/sizegrip.png);
url(:/images/frame.png) 4;
url(:/images/spinup.png) 1;
url(:/images/spinup_hover.png) 1;
url(:/images/spinup_pressed.png) 1;
url(:/images/checkbox_unchecked.png);
url(:/images/checkbox_unchecked_hover.png);
url(:/images/checkbox_checked.png);
url(:/images/checkbox_checked_hover.png);
url(:/images/radiobutton_unchecked.png);
url(:/images/radiobutton_unchecked_hover.png);
url(:/images/radiobutton_checked.png);
url(:/images/radiobutton_checked_hover.png);
url(:/images/checkbox_indeterminate_hover.png);
url(:/images/checkbox_indeterminate_pressed.png);



"""

# min-width: 80px;

# QComboBox:editable {
#   background: {MAIN_BACKGROUND};
# }

# QComboBox:!editable, QComboBox::drop-down:editable {
#   background: {MAIN_BACKGROUND};
# }

# /* QComboBox gets the "on" state when the popup is open */
# QComboBox:!editable:on, QComboBox::drop-down:editable:on {
#   background: {MAIN_BACKGROUND};
# }

# background-color: #ABABAB; /* sets background of the menu */
# border: 1px solid black;

# /* sets background of menu item. set this to something non-transparent
# if you want menu color and menu item color to be different */
# background-color: transparent;

# QMenu::item:selected { /* when user selects item using mouse or keyboard */
#     background-color: #654321;
# For a more advanced customization, use a style sheet as follows:

# QMenu {
#     background-color: white;
#     margin: 2px; /* some spacing around the menu */

# QMenu::item {
#     padding: 2px 25px 2px 20px;
#     border: 1px solid transparent; /* reserve space for selection border */

# QMenu::item:selected {
#     border-color: darkblue;
#     background: rgba(100, 100, 100, 150);
# }

# QMenu::icon:checked { /* appearance of a 'checked' icon */
#     background: gray;
#     border: 1px inset gray;
#     position: absolute;
#     top: 1px;
#     right: 1px;
#     bottom: 1px;
#     left: 1px;

# QPushButton {
#   background:rgba(127,127,127,2);
#   background-color: red;
#   color: white;
#   border-width: 2px;
#   border-radius: 10px;
#   border-color: beige;
#   border-style: outset;
#   font: bold 14px;
#   min-width: 10em;
#   padding: 5px;

# QPushButton:hover {
#   border: 1px solid black;
#   border-radius: 5px;
#   background-color:#66c0ff;

# QPushButton:pressed {
#   background-color: rgb(224, 0, 0);
#   border-style: inset;

# QPushButton:enabled {
#   color: red

# QComboBox {
#   image: url(:/none);}

# QComboBox::drop-down {
#   border-width: 0px;
#   color: transparent

# QComboBox::down-arrow {
#   border: 0px solid transparent;
#   border-width: 0px; left: 0px; top: 0px; width: 0px; height: 0px;
#   background-color: transparent;
#   color: transparent;
#   image: url(:/none);

# QTreeView {
#   alternate-background-color: rgba(35,35,35,255);
#   background: rgba(45,45,45,255);
# }

# QMenu {
#   background-color: white; /* background-color: #ABABAB; sets background of the menu */
#   margin: 2px; /* some spacing around the menu */
#   border: 1px solid black;
# }

# QMenu::item {
#   /* sets background of menu item. set this to something non-transparent
#   if you want menu color and menu item color to be different */
#   background-color: transparent;
#   padding: 2px 25px 2px 20px;
#   border: 1px solid transparent; /* reserve space for selection border */
# }

# QMenu::item:selected {
#   /* when user selects item using mouse or keyboard */
#   background-color: #654321;
#   border-color: darkblue;
#   background: rgba(100, 100, 100, 150);
# }

# QMenu::icon:checked { /* appearance of a 'checked' icon */
#   background: gray;
#   border: 1px inset gray;
#   position: absolute;
#   top: 1px;
#   right: 1px;
#   bottom: 1px;
#   left: 1px;
# }

# /* non-exclusive indicator = check box style indicator (see QActionGroup::setExclusive) */
# QMenu::indicator:non-exclusive:unchecked {
#     image: url(:/images/checkbox_unchecked.png);
# }

# QMenu::indicator:non-exclusive:unchecked:selected {
#     image: url(:/images/checkbox_unchecked_hover.png);
# }

# QMenu::indicator:non-exclusive:checked {
#     image: url(:/images/checkbox_checked.png);
# }

# QMenu::indicator:non-exclusive:checked:selected {
#     image: url(:/images/checkbox_checked_hover.png);
# }

# /* exclusive indicator = radio button style indicator (see QActionGroup::setExclusive) */
# QMenu::indicator:exclusive:unchecked {
#     image: url(:/images/radiobutton_unchecked.png);
# }

# QMenu::indicator:exclusive:unchecked:selected {
#     image: url(:/images/radiobutton_unchecked_hover.png);
# }

# QMenu::indicator:exclusive:checked {
#     image: url(:/images/radiobutton_checked.png);
# }

# QMenu::indicator:exclusive:checked:selected {
#     image: url(:/images/radiobutton_checked_hover.png);


# QToolButton:hover, QToolButton::menu-button:hover {
#     background: #787876;
# }

# QToolButton::checked{
#     background: #484846;
#     border: 1px solid #787876;
# }

# QToolButton:pressed, QToolButton::menu-button:pressed {
#     background: #787876;
# }

# QToolButton[popupMode="1"]{
# /* only for MenuButtonPopup */
#     padding-right: 30px;
#     background: red;
# }
# QToolButton[popupMode="2"]{
# /* only for OSC Server Status */
#     padding-right: 30px;
#     background: #484846;
# }
# QToolButton[popupMode="2"]:hover{
#     background: #787876;
# }
# QToolButton::down-arrow{
# }
# /* the subcontrols below are used only in the MenuButtonPopup mode */
# QToolButton::menu-button{
# }

# QToolButton::menu-button:hover{
#     background: #787876;
# }
# QToolButton::menu-button:pressed{
# }
# QToolButton::menu-indicator{
#     bottom: 5px;
#     right: 5px;
# }
