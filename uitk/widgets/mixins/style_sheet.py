# !/usr/bin/python
# coding=utf-8
from typing import Union
import re
from PySide2 import QtCore, QtWidgets
from pythontk import makeList, getDerivedType, listify


class StyleSheetMixin(QtCore.QObject):
    """StyleSheetMixin class is responsible for generating, modifying, and applying CSS style sheets for various Qt widgets.
    The class also provides utility functions to adjust the appearance of widgets based on their properties or conditions.
    The StyleSheetMixin class offers multiple style presets (e.g., 'standard' and 'dark') and allows the user to create custom
    style presets by providing a color value dictionary.

    Methods:
    - get_color_values(cls, style="standard", **kwargs): Return the colorValues dict with any of the bracketed
                placeholders replaced by the value of any given kwargs of the same name.
    - remove_leading_whitespace(s): Remove the same amount of leading whitespace from each line in the input string
                as present in the first line.
    - get_style_sheet(cls, widget_type=None, style="standard", **kwargs): Get the styleSheet for the given widget type.
    - set_style(cls, widget, ratio=6, style="standard", hide_menu_button=False, append_to_existing=False, **kwargs): Set the
                styleSheet for the given widgets.
    - adjust_padding(widget_type): Remove padding when the text length / widget width ratio is below a given amount.
    - hide_menu_button(widget_type): Set the menu button as transparent.
    """

    themes = {
        "standard": {
            "MAIN_FOREGROUND": "rgb(75,75,75)",
            "MAIN_BACKGROUND": "rgb(100,100,100)",
            "MAIN_BACKGROUND_ALPHA": "rgba(100,100,100,185)",
            "WIDGET_BACKGROUND": "rgb(125,125,125)",
            "BUTTON_PRESSED": "rgb(127,127,127)",
            "BUTTON_HOVER": "rgb(82,133,166)",
            "TEXT_COLOR": "rgb(255,255,255)",
            "TEXT_CHECKED": "rgb(0,0,0)",
            "TEXT_DISABLED": "rgba(150,150,150,175)",
            "TEXT_HOVER": "rgb(255,255,255)",
            "TEXT_BACKGROUND": "rgb(50,50,50)",
            "BORDER_COLOR": "rgb(50,50,50)",
            "HIGHLIGHT_COLOR": "rgb(255,255,190)",
            "DISABLED_BACKGROUND": "rgb(85,85,85)",
            "PROGRESS_BAR_COLOR": "rgb(0,160,208)",
        },
        "dark": {
            "MAIN_FOREGROUND": "rgb(50,50,50)",
            "MAIN_BACKGROUND": "rgb(100,100,100)",
            "MAIN_BACKGROUND_ALPHA": "rgba(70,70,70,185)",
            "WIDGET_BACKGROUND": "rgb(60,60,60)",
            "BUTTON_PRESSED": "rgb(127,127,127)",
            "BUTTON_HOVER": "rgb(82,133,166)",
            "TEXT_COLOR": "rgb(200,200,200)",
            "TEXT_CHECKED": "rgb(0,0,0)",
            "TEXT_DISABLED": "rgba(185,185,185,175)",
            "TEXT_HOVER": "rgb(255,255,255)",
            "TEXT_BACKGROUND": "rgb(50,50,50)",
            "BORDER_COLOR": "rgb(40,40,40)",
            "HIGHLIGHT_COLOR": "rgb(255,255,190)",
            "DISABLED_BACKGROUND": "rgb(45,45,45)",
            "PROGRESS_BAR_COLOR": "rgb(0,160,208)",
        },
    }

    style_sheets = {
        "QMainWindow": """
            QMainWindow {
                background-color: {MAIN_BACKGROUND_ALPHA};
                border: 1px solid {BORDER_COLOR};
            }
            QMainWindow#translucent_window {
                background-color: rgba(127,127,127,0.005);
                border: none;
            }
            """,
        "QWidget": """
            QWidget {
                background-color: transparent;
            }
            QWidget::item:selected {
                background-color: {BUTTON_HOVER};
            }
            QWidget#hud_widget {
                background-color: rgba(127,127,127,0.01);
            }
            QWidget#main_widget {
                background-color: {MAIN_BACKGROUND_ALPHA};
                border: 1px solid {BORDER_COLOR};
            }
            """,
        "QStackedWidget": """
            QStackedWidget {
                background-color: {MAIN_BACKGROUND};
            }
            QStackedWidget QFrame {
                background-color: {MAIN_BACKGROUND};
            }
            QStackedWidget QFrame QLabel {
                color: {TEXT_COLOR};
                font-size: 8;
            }
            QStackedWidget QPushButton {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                font-size: 8;
                border: 1px solid {BORDER_COLOR};
            }
            """,
        "QPushButton": """
            QPushButton {
                border-style: outset;
                border-radius: 1px;
                border: 1px solid {BORDER_COLOR};
                padding: 0px 5px 0px 5px; /* top, right, bottom, left */
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
            }
            QPushButton#toggle_expand {
                border-style: outset;
                border-radius: 1px;
                border: none;
                padding: 0px 0px 0px 0px; /* top, right, bottom, left */
                background-color: {MAIN_BACKGROUND};
                color: {TEXT_COLOR};
            }
            QPushButton::enabled {
                color: {TEXT_COLOR};
            }
            QPushButton::disabled {
                color: {TEXT_DISABLED};
            }
            QPushButton::checked {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QPushButton::hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QPushButton::checked::hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QPushButton::pressed {
                background-color: {BUTTON_PRESSED};
                color: {TEXT_COLOR};
            }
            QPushButton:flat {
                border: none; /* no border for a flat push button */
            }
            QPushButton:default {
                border-color: navy; /* make the default button prominent */
            }
            """,
        "QToolButton": """
            QToolButton {
                border-style: outset;
                border-radius: 1px;
                border: 1px solid {BORDER_COLOR};
                padding: 0px 5px 0px 5px; /* top, right, bottom, left */
                background-color: {WIDGET_BACKGROUND}; /* The background will not appear unless you set the border property. */
                color: {TEXT_COLOR};
            }
            QToolButton::enabled {
                color: {TEXT_COLOR};
            }
            QToolButton::disabled {
                color: {TEXT_DISABLED};
            }
            QToolButton::hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QToolButton::checked {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QToolButton::checked::hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QToolButton::pressed, QToolButton::menu-button:pressed {
                background-color: {BUTTON_PRESSED};
                color: {TEXT_COLOR};
            }
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
            QToolButton::menu-indicator:pressed, QToolButton::menu-indicator:open {
                position: relative;
                top: 2px; left: 2px; /* shift the arrow by 2 px */
            }
            /* When the Button displays arrows, the ::up-arrow, ::down-arrow, ::left-arrow and ::right-arrow subcontrols are used. */
            QToolButton::down-arrow, QToolButton::up-arrow, QToolButton::left-arrow, QToolButton::right-arrow {
                image: none;
                padding: 0px 15px 0px 0px; /* top, right, bottom, left */
            }
            QToolButton::down-arrow:hover, QToolButton::up-arrow:hover, QToolButton::left-arrow:hover, QToolButton::right-arrow:hover {
                background-color: {BUTTON_HOVER};
                padding: 0px 5px 0px 0px; /* top, right, bottom, left */
            }
            /* the subcontrols below are used only in the MenuButtonPopup mode */
            QToolButton::menu-button {
                border: 1px solid {TEXT_COLOR};
                margin: 4px 2px 4px 0px; /* top, right, bottom, left */
            }
            QToolButton::menu-button::enabled {
                color: {TEXT_COLOR};
            }
            QToolButton::menu-button::disabled {
                color: {TEXT_DISABLED};
                border: 1px solid transparent;
            }
            QToolButton::menu-button:hover{
                border: 1px solid {TEXT_HOVER};
            }
            QToolButton::menu-button:pressed {
                background-color: transparent;
                border: 1px solid transparent;
            }
            QToolButton::menu-arrow {
                image: none;
            }
            QToolButton::menu-arrow:open {
            }
            """,
        "QAbstractButton": """
            QAbstractButton {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                padding: 1px;
            }
            QAbstractButton:hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QAbstractButton:pressed {
                background-color: {BUTTON_PRESSED};
            }
            QAbstractButton:checked {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QAbstractButton:disabled {
                background-color: {DISABLED_BACKGROUND};
                color: {TEXT_DISABLED};
            }
            QAbstractButton:focus {
                border-color: {BORDER_COLOR};
            }
        """,
        "QComboBox": """
            QComboBox {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                padding: 1px;
                border-radius: 1px;
                min-width: 0em;
            }
            QComboBox:hover {
                background-color: {BUTTON_HOVER};
            }
            QComboBox::hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
                border: 1px solid {BORDER_COLOR};
            }
            QComboBox::open {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_DISABLED};
                border: 1px solid {BORDER_COLOR};
                selection-background-color: {BUTTON_HOVER};
                selection-color: {TEXT_CHECKED};
            }
            QComboBox:on { /* shift the text when the popup opens */
                padding-top: 3px;
                padding-left: 1px;
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
                border: 1px solid {BORDER_COLOR};
                border-radius: 1px;
                padding: 0px;
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                font-size: 8;
                margin: 0px;
            }
            QFrame QLabel:hover {
                background: {BUTTON_HOVER};
            }
            """,
        "QListView": """
            QListView {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                alternate-background-color: {MAIN_BACKGROUND};
                background-attachment: fixed; /* fixed, scroll */
                border: 1px solid {BORDER_COLOR};
            }
            QListView::item {
                background-color: {MAIN_BACKGROUND};
                color: {TEXT_COLOR};
            }
            QListView::item:alternate {
                background-color: {MAIN_BACKGROUND};
            }
            QListView::item:selected {
                border: 1px solid {BORDER_COLOR};
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QListView::item:selected:!active {
                background-color: {BUTTON_HOVER};
                color: {TEXT_COLOR};
            }
            QListView::item:selected:active {
                background-color: {BUTTON_HOVER};
                color: {TEXT_COLOR};
            }
            QListView::item:hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            """,
        "QSpinBox": """
            QSpinBox {
            background-color: {WIDGET_BACKGROUND};
            color: {TEXT_COLOR};
            border: 1px solid {BORDER_COLOR};
            }
            QSpinBox::disabled {
                color: {TEXT_DISABLED};
            }
            QSpinBox::hover {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_HOVER};
                border: 1px solid {BORDER_COLOR};
            }
            """,
        "QDoubleSpinBox": """
            QDoubleSpinBox {
            background-color: {WIDGET_BACKGROUND};
            color: {TEXT_COLOR};
            border: 1px solid {BORDER_COLOR};
            }
            QDoubleSpinBox::disabled {
                color: {TEXT_DISABLED};
            }
            QDoubleSpinBox::hover {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_HOVER};
                border: 1px solid {BORDER_COLOR};
            }
            """,
        "QAbstractSpinBox": """
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
        "QCheckBox": """
            QCheckBox {
                border-style: outset;
                border-radius: 1px;
                border: 1px solid {BORDER_COLOR};
                padding: 0px 5px 0px 5px; /* top, right, bottom, left */
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                spacing: 5px;
            }
            QCheckBox::hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QCheckBox::hover:checked {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QCheckBox::enabled {
                color: {TEXT_COLOR};
            }
            QCheckBox::disabled {
                color: {TEXT_DISABLED};
            }
            QCheckBox::disabled:checked {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_DISABLED};
            }
            QCheckBox::checked {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QCheckBox::checked:hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QCheckBox::indeterminate {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QCheckBox::indeterminate:hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QCheckBox::indicator {
                width: 0px;
                height: 0px;
                border: none;
            }
            QCheckBox::indicator::unchecked {
                image: none;
            }
            QCheckBox::indicator:unchecked:hover {
                image: none;
            }
            QCheckBox::indicator:unchecked:pressed {
                image: none;
            }
            QCheckBox::indicator::checked {
                image: none;
            }
            QCheckBox::indicator:checked:hover {
                image: none;
            }
            QCheckBox::indicator:checked:pressed {
                image: none;
            }
            QCheckBox::indicator:indeterminate:checked {
                image: none;
            }
            QCheckBox::indicator:indeterminate:hover {
                image: none;
            }
            QCheckBox::indicator:indeterminate:pressed {
                image: none;
            }
            """,
        "QRadioButton": """
            QRadioButton {
                border-style: outset;
                border-radius: 1px;
                border: 1px solid {BORDER_COLOR};
                padding: 0px 5px 0px 5px; /* top, right, bottom, left */
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
            }
            QRadioButton::hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QRadioButton::hover:checked {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QRadioButton::enabled {
                color: {TEXT_COLOR};
            }
            QRadioButton::disabled {
                color: {TEXT_DISABLED};
            }
            QRadioButton::checked {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QRadioButton::checked:hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_CHECKED};
            }
            QRadioButton::indicator {
                width: 0px;
                height: 0px;
                border: none;
            }
            QRadioButton::indicator::unchecked {
                image: none;
            }
            QRadioButton::indicator:unchecked:hover {
                image: none;
            }
            QRadioButton::indicator::checked {
                image: none;
            }
            QRadioButton::indicator:checked:hover {
                image: none;
            }
            """,
        "QAbstractItemView": """
            QAbstractItemView {
                show-decoration-selected: 1;
                selection-background-color: {BUTTON_HOVER};
                selection-color: {MAIN_BACKGROUND};
                alternate-background-color: {MAIN_BACKGROUND};
                min-width: 150px;
            }
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
            QTableView {
                gridline-color: {BUTTON_PRESSED};
            }
            """,
        "QLineEdit": """
            QLineEdit {
                border: 1px solid {BORDER_COLOR};
                border-radius: 1px;
                padding: 0 8px;
                background-color: {MAIN_FOREGROUND};
                color: {TEXT_COLOR};
                selection-background-color: {BUTTON_HOVER};
                selection-color: {TEXT_COLOR};
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
        "QTextEdit": """
            QTextEdit {
                border: 1px solid {BORDER_COLOR};
                background-color: {MAIN_FOREGROUND};
                color: {TEXT_COLOR};
                selection-background-color: {BUTTON_HOVER};
                selection-color: {TEXT_COLOR};
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
        "QPlainTextEdit": """
            QPlainTextEdit {
            }
            """,
        "QListWidget": """
            QListWidget {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                alternate-background-color: {WIDGET_BACKGROUND};
                background-attachment: fixed; /* fixed, scroll */
            }
            QListWidget::item:alternate {
                background-color: {WIDGET_BACKGROUND};
            }
            QListWidget::item:selected {
                border: 1px solid {BORDER_COLOR};
            }
            QListWidget::item:selected:!active {
                background-color: {BUTTON_HOVER};
                color: {TEXT_COLOR};
            }
            QListWidget::item:selected:active {
                background-color: {BUTTON_HOVER};
                color: {TEXT_COLOR};
            }
            QListWidget::item:hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QListWidget * {
                border: none;
            }
            """,
        "QTreeWidget": """
            QTreeWidget {
                background-color: transparent;
                border:none;
            }
            QTreeWidget::item {
                height: 20px;
            }
            QTreeWidget::item:enabled {
                color: {TEXT_COLOR};
            }
            QTreeWidget::item:disabled {
                color: {TEXT_DISABLED};
            }
            QTreeView::item:hover {
                background-color: {BUTTON_HOVER};
                color: {TEXT_HOVER};
            }
            QTreeView::item:selected {
                background-color: none;
            }
            """,
        "QToolBox": """
            QToolBox {
                background-color: {MAIN_BACKGROUND};
                color: {TEXT_COLOR};
                alternate-background-color: {MAIN_BACKGROUND};
                background-attachment: fixed; /* fixed, scroll */
                icon-size: 0px;
            }
            QToolBox QScrollArea QWidget {
                background-color: transparent;
            }
            QToolBox QToolBoxButton {
                image: url(:/none);
            }
            QToolBox QAbstractButton {
                background-image: url(:/none);
                image: url(:/none);
            }
            QToolBox::tab {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                             stop: 0 {MAIN_BACKGROUND}, stop: 1 {MAIN_BACKGROUND});
                color: {TEXT_COLOR};
                border-radius: 1px;
            }
            QToolBox::tab:selected {
                /* font: italic; */ /* italicize selected tabs */
                color: {TEXT_COLOR};
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                             stop: 0 {MAIN_BACKGROUND}, stop: 1 {MAIN_BACKGROUND});
            }
            """,
        "QAbstractSpinBox": """
            QAbstractSpinBox {
                padding-right: 0px;
            }
            """,
        "QSlider": """
            QSlider {
                border: 1px solid black;
                background-color: {MAIN_BACKGROUND};
            }
            QSlider::groove:horizontal {
                height: 18px;
                margin: 0px 0px 0px 0px;
                background-color: {MAIN_BACKGROUND};
            }
            QSlider::groove:vertical {
                width: 0px;
                margin: 0px 0px 0px 0px;
                background-color: {MAIN_BACKGROUND};
            }
            QSlider::handle {
                width: 10px;
                height: 15px;
                border: 1px solid black;
                background-color: gray;
                margin: -1px 0px -1px 0px;
                border-radius: 1px;
            }
            QSlider::handle:hover {
                background-color: darkgray;
            }
            QSlider::add-page:vertical, QSlider::sub-page:horizontal {
                background-color: {BUTTON_HOVER};
            }
            QSlider::sub-page:vertical, QSlider::add-page:horizontal {
                background-color: {MAIN_BACKGROUND};
            }
            QSlider::tickmark {
                width: 5px;
                height: 5px;
                margin: 0px -3px 0px 0px;
                border-radius: 2.5px;
                background-color: black;
            }
            QSlider::tickmark:not(sub-page) {
                width: 10px;
                height: 10px;
                margin: 0px -5px 0px 0px;
                border-radius: 5px;
                background-color: black;
            }
            QSlider::tickmark:sub-page {
                width: 5px;
                height: 5px;
                margin: 0px -3px 0px 0px;
                border-radius: 2.5px;
                background-color: lightgray;
            }
            """,
        "QScrollBar": """
            QScrollBar {
                border: 1px solid transparent;
                background-color: {MAIN_BACKGROUND};
            }
            QScrollBar:horizontal {
                height: 15px;
                margin: 0px 0px 0px 32px; /* top, right, bottom, left */
            }
            QScrollBar:vertical {
                width: 15px;
                margin: 32px 0px 0px 0px; /* top, right, bottom, left */
            }
            QScrollBar::handle {
                background-color: {BUTTON_PRESSED};
                border: 1px solid transparent;
            }
            QScrollBar::handle:horizontal {
                border-width: 0px 1px 0px 1px;
            }
            QScrollBar::handle:vertical {
                border-width: 1px 0px 1px 0px;
            }
            QScrollBar::handle:horizontal {
                min-width: 20px;
            }
            QScrollBar::handle:vertical {
                min-height: 20px;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                background-color:{MAIN_BACKGROUND};
                border: 1px solid {BUTTON_PRESSED};
                subcontrol-origin: margin;
            }
            QScrollBar::add-line {
                position: absolute;
            }
            QScrollBar::add-line:horizontal {
                width: 15px;
                subcontrol-position: left;
                left: 15px;
            }
            QScrollBar::add-line:vertical {
                height: 15px;
                subcontrol-position: top;
                top: 15px;
            }
            QScrollBar::sub-line:horizontal {
                width: 15px;
                subcontrol-position: top left;
            }
            QScrollBar::sub-line:vertical {
                height: 15px;
                subcontrol-position: top;
            }
            QScrollBar::add-page, QScrollBar::sub-page {
                background-color: none;
            }
            """,
        "QGroupBox": """
            QGroupBox {
                border: 2px transparent;
                border-radius: 1px;
                margin: 10px 0px 0px 0px; /* top, right, bottom, left */ /* leave space at the top for the title */
                background-color: rgba(75,75,75,125);
            }
            QGroupBox::title {
                top: -12px;
                left: 2px;
                subcontrol-position: top left; /* position at the top center */
                background-color: transparent;
                color: {TEXT_COLOR};
            }
            """,
        "QTabBar": """
            QTabBar {
                margin: 0px 0px 0px 2px; /* top, right, bottom, left */
            }
            QTabBar::tab {
                border-radius: 1px;
                padding-top: 1px;
                margin-top: 1px;
            }
            QTabBar::tab:selected {
                background-color: {MAIN_BACKGROUND};
            }
            """,
        "QMenu": """
            QMenu {
                background-color: transparent;
                border: 1px solid {BORDER_COLOR};
                margin: 0px; /* spacing around the menu */
            }
            QMenu::item {
                padding: 2px 2px 2px 2px; /* top, right, bottom, left */
                border: 1px solid transparent; /* reserve space for selection border */
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
                background-color: {TEXT_HOVER};
            }
            """,
        "QLabel": """
            QLabel {
                background-color: {WIDGET_BACKGROUND};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 1px;
                margin: 0px 0px 0px 0px; /* top, right, bottom, left */
                padding: 0px 5px 0px 5px; /* top, right, bottom, left */
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
        "QToolTip": """
            QToolTip {
                background-color: {MAIN_BACKGROUND};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
            }
            """,
        "QProgressBar": """
            QProgressBar {
                border: none;
                border-radius: 5px;
                text-align: center;
                margin: 0px 0px 0px 0px; /* top, right, bottom, left */
            }
            QProgressBar::chunk {
                width: 1px;
                margin: 0px;
                background-color: {BUTTON_HOVER};
            }
            """,
        "QSplitter": """
            QSplitter::handle {
                image: url(images/splitter.png);
            }
            QSplitter::handle:horizontal {
                width: 2px;
            }
            QSplitter::handle:vertical {
                height: 2px;
            }
            QSplitter::handle:pressed {
                url(images/splitter_pressed.png);
            }
            """,
        "QSplitterHandle": """
            QSplitter::handle:horizontal {
                border-left: 1px solid lightGray;
            }
            QSplitter::handle:vertical {
                border-bottom: 1px solid lightGray;
            }
            """,
        "QTabWidget": """
            QTabWidget {
            }
            """,
        "QRubberBand": """
            QRubberBand {
                color: 0px solid gray;
            }
            """,
        "QVBoxLayout": """
            'QVBoxLayout' {
            }
            """,
        "QHBoxLayout": """
            'QHBoxLayout' {
            }
            """,
        "QGridLayout": """
            'QGridLayout' {
            }
            """,
    }

    @listify
    def set_style(
        self,
        style="standard",
        widget: Union[QtWidgets.QWidget, None] = None,
        ratio=6,
        hide_menu_button=False,
        append_to_existing=False,
        **kwargs,
    ):
        """Set the styleSheet for the given widgets.
        Set the style for a specific widget by using the '#' syntax and the widget's objectName. ie. QWidget#mainWindow

        Parameters:
            widgets (obj/list): A widget or list of widgets.
            ratio (int): The ratio of widget size, text length in relation to the amount of padding applied.
            style (str): Color mode. ie. 'standard' or 'dark'
            hide_menu_button (boool) = Hide the menu button of a widget that has one.
            append_to_existing (bool) = Append the new stylesheet to the widget's existing stylesheet.
        """
        if widget is None:
            if isinstance(self, QtWidgets.QWidget):
                widget = self
            else:
                raise ValueError(
                    "A 'widget' argument is required when 'StyleSheetMixin' is not inherited by a custom widget class."
                )

        widget_type = getDerivedType(widget, module="QtWidgets", return_name=True)

        # If the widget is a QMainWindow, apply the combined stylesheet
        if widget_type == "QMainWindow":
            s = self.get_style_sheet(style=style, **kwargs)
        else:
            try:
                s = self.get_style_sheet(widget_type, style=style, **kwargs)
            except KeyError as error:  # given widget has no attribute 'styleSheet'.
                # print (__name__.ljust(26), 'setStyle (get_style_sheet)', widget.objectName().ljust(26), widget.__class__.__name__.ljust(25), error)
                return

        if hide_menu_button:
            s = s + self.hide_menu_button(widget_type)

        try:
            length = (  # a 'NoneType' error will be thrown if the widget does not contain text.
                len(widget.text())
                if hasattr(widget, "text")
                else len(str(widget.value()))
            )
            # ratio of widget size, text length (using integer division).
            if widget.size().width() // length > ratio:
                s = s + self.adjust_padding(widget_type)
        except (AttributeError, ZeroDivisionError) as error:
            # print (__name__.ljust(26), 'setStyle (adjustPadding)', widget.objectName().ljust(26), widget.__class__.__name__.ljust(25), error)
            pass

        # append_to_existing style changes to an existing style sheet.
        if append_to_existing and widget.styleSheet():
            s = s + widget.styleSheet()

        widget.setStyleSheet(s)

    @classmethod
    def get_color_values(cls, style="standard", **kwargs):
        """Return the colorValues dict with any of the bracketed placeholders
        replaced by the value of any given kwargs of the same name.

        Parameters:
            style (str)(dict): The color value set to use. valid values are: 'standard', 'dark'
                        or pass your own style as a dict.
            **kwargs () = Keyword arguments matching the string of any bracketed placeholders.
                        case insensitive.  ex. alpha=255
        Returns:
            (dict) The color values with placeholder values. ex. {'MAIN_BACKGROUND_ALPHA': 'rgba(100,100,100,75)', etc..
        """
        if isinstance(style, dict):
            return {
                k: v.format(**{k.upper(): v for k, v in kwargs.items()})
                for k, v in style.items()
            }
        else:
            return {
                k: v.format(**{k.upper(): v for k, v in kwargs.items()})
                for k, v in cls.themes[style].items()
            }

    @staticmethod
    def remove_leading_whitespace(s):
        """Remove the same amount of leading whitespace from each line in the input string as
        present in the first line.

        Parameters:
            s (str): Input string containing lines with leading whitespace.

        Returns:
            (str): Output string with leading whitespace removed from each line.
        """
        s = s.strip("\n")  # Remove leading and trailing newline characters
        lines = s.splitlines()
        if lines:
            leading_whitespace = re.match(r"^(\s*)", lines[0]).group(1)
            s = "\n".join(
                [re.sub(f"^{leading_whitespace}", "", line) for line in lines]
            )
        return s

    @classmethod
    def get_style_sheet(cls, widget_type=None, style="standard", **kwargs):
        """Get the styleSheet for the given widget type.
        By default it will return all stylesheets as one multi-line css string.

        Parameters:
            widget_type (str): The class name of the widget. ie. 'QLabel'
            style (str): The color value set to use. valid values are: 'standard', 'dark'

        Returns:
            (str) css styleSheet
        """
        css = (
            "".join(cls.style_sheets.values())
            if widget_type is None
            else cls.style_sheets.get(widget_type, "")
        )

        if not css:
            print(
                f"# Error: {__file__} in get_style_sheet\n#\tKeyError: '{widget_type}'"
            )
            return ""

        for k, v in cls.get_color_values(style=style, **kwargs).items():
            css = css.replace(f"{{{k.upper()}}}", v)

        return cls.remove_leading_whitespace(css)

    @staticmethod
    def adjust_padding(widget_type):
        """Remove padding when the text length / widget width ratio is below a given amount."""
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
                border: 1px solid transparent;
            }}

            {0}::menu-button::hover {{
                border: 1px solid transparent;
            }}""".format(
            widget_type
        )


if __name__ == "__main__":
    pass

# else:
#   styleSheet = StyleSheetMixin()

# module name
# print (__name__)
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
