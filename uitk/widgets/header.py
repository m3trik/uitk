# !/usr/bin/python
# coding=utf-8
import os
import pythontk as ptk
from qtpy import QtWidgets, QtCore, QtGui, QtSvg
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.text import RichText, TextOverlay
from uitk.widgets.mixins.icon_manager import IconManager


class Header(
    QtWidgets.QLabel, AttributesMixin, RichText, TextOverlay, ptk.LoggingMixin
):
    """Header is a QLabel that can be dragged around the screen and can be pinned/unpinned. It provides a customizable
    header bar with buttons for common window actions such as minimizing, hiding, and pinning.

    Signals:
        toggled(bool): Emitted when the pin state is toggled.
        refresh_requested(): Emitted when the refresh button is clicked.

    Attributes:
        button_definitions (dict): Defines the properties of the buttons available in the header.
        state (str): Represents the current state of the header ("unpinned", "pinned").
    """

    toggled = QtCore.Signal(bool)
    refresh_requested = QtCore.Signal()

    MINIMIZE_WIDTH = 200  # Fixed width when minimized to corner
    MINIMIZE_STACK = "horizontal"  # "horizontal" or "vertical"
    MINIMIZE_MARGIN = 8  # Margin from screen edges and between stacked windows
    _minimized_headers = []  # Class-level registry for stacking

    # Define button properties with icon paths and callbacks
    button_definitions = {
        "refresh": ("refresh.svg", "trigger_refresh"),
        "menu": ("menu.svg", "show_menu"),
        "help": ("help.svg", "show_help"),
        "collapse": ("chevron_up.svg", "toggle_collapse"),
        "minimize": ("minimize.svg", "minimize_window"),
        "maximize": ("maximize.svg", "toggle_maximize"),
        "fullscreen": ("screen.svg", "toggle_fullscreen"),
        "hide": ("close.svg", "hide_window"),
        "pin": ("radio_empty.svg", "toggle_pin"),
    }

    def __init__(
        self,
        parent=None,
        config_buttons=None,
        pin_on_drag_only=True,
        auto_hide_with_os_frame=True,
        **kwargs,
    ):
        """Initialize the Header with buttons and layout.

        Parameters:
            parent (QWidget, optional): The parent widget. Defaults to None.
            config_buttons (list, optional): List of button names to show in order.
                Example: ['refresh', 'menu', 'pin']
                Available buttons: 'refresh', 'menu', 'help', 'collapse',
                'minimize', 'maximize', 'hide', 'pin'
            pin_on_drag_only (bool, optional): If True (default), clicking the pin button hides
                the window, and only dragging the header pins it. If False, clicking the pin
                button toggles traditional pin/unpin behavior.
                Defaults to True.
            auto_hide_with_os_frame (bool, optional): If True (default), the
                header hides itself when its top-level window has a native
                OS title bar (i.e. is not frameless), so the two title bars
                don't stack. Set False to force the header to always show.
            **kwargs: Additional attributes for the header (e.g., setTitle="My Title").
        """
        super().__init__(parent)
        self.pinned = False  # unpinned, pinned
        self.pin_on_drag_only = pin_on_drag_only
        self._auto_hide_with_os_frame = auto_hide_with_os_frame
        self._auto_hide_checked = False
        self._collapsed = False
        self._minimized = False
        self._saved_size = None
        self._saved_min_size = None
        self._saved_max_size = None
        self._saved_pos = None
        self._saved_parent_min_heights = {}  # Store min heights of ancestors
        self._saved_parent_min_widths = {}  # Store min widths of ancestors
        self._collapse_saved_pos = (
            None  # Position before collapse (for right-edge anchoring)
        )
        self.__mousePressPos = None
        self.buttons = {}  # Initialize buttons dict to avoid AttributeError
        self._full_title = ""  # Untruncated title for elision
        self._version = ""  # Optional version suffix appended to title
        # Persisted help text — survives config_buttons rebuilds so the help
        # button is re-added automatically if the layout is rebuilt later.
        self._help_text = ""

        self.container_layout = QtWidgets.QHBoxLayout(self)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(1)
        self.container_layout.addStretch(1)

        self.setLayout(self.container_layout)
        self.setCursor(QtGui.QCursor(QtCore.Qt.OpenHandCursor))

        self.setProperty("class", self.__class__.__name__)
        font = self.font()
        font.setBold(True)
        self.setFont(font)

        self.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        self.setIndent(8)  # adds left-side indentation to the text
        self.setFixedHeight(19)

        if config_buttons:
            # Unpack the list when calling the method
            if isinstance(config_buttons, (list, tuple)):
                self.config_buttons(*config_buttons)
            else:
                self.config_buttons(config_buttons)

        self.set_attributes(**kwargs)

    @property
    def menu(self):
        try:
            return self._menu
        except AttributeError:
            from uitk.widgets.menu import Menu

            self._menu = Menu(
                self,
                fixed_item_height=20,
                hide_on_leave=True,
                add_header=False,
                add_footer=False,
                add_defaults_button=False,
                match_parent_width=False,
            )
            # Auto-show the menu button as soon as real content arrives.
            self._menu.on_item_added.connect(self._sync_menu_button_visibility)
            return self._menu

    def get_icon_path(self, icon_filename):
        """Get the full path to an icon file in the uitk/icons directory."""
        # Get the directory where this module is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up one level to uitk, then into icons
        icons_dir = os.path.join(os.path.dirname(current_dir), "icons")
        return os.path.join(icons_dir, icon_filename)

    def create_svg_icon(self, icon_filename, size=16):
        """Create a QIcon from an SVG file."""
        icon_path = self.get_icon_path(icon_filename)
        if os.path.exists(icon_path):
            # Create a pixmap from SVG with proper scaling
            svg_renderer = QtSvg.QSvgRenderer(icon_path)
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            svg_renderer.render(painter)
            painter.end()
            return QtGui.QIcon(pixmap)
        else:
            # Fallback to empty icon if file not found
            return QtGui.QIcon()

    # Pixel padding subtracted from header height to size header-button icons.
    # 3 px (= 16 px icon inside a 19 px button) preserves the historical look.
    _ICON_MARGIN = 3

    def create_button(self, icon_filename, callback, button_type=None):
        """Create a button with the given icon and callback."""
        button = QtWidgets.QPushButton(self)
        if button_type:
            # Prefix with 'hdr_' to avoid conflicts with QWidget methods
            # when MainWindow's __getattr__ searches for widgets by name
            button.setObjectName(f"hdr_{button_type}")

        # Set the icon using IconManager for theme support; sized to the
        # header's current height so it tracks the widget on resize.
        icon_name = icon_filename.replace(".svg", "")
        self._set_button_icon(button, icon_name)

        button.setCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))
        button.clicked.connect(callback)
        return button

    def _set_button_icon(self, button, icon_name):
        """Render *icon_name* onto *button* at the header's current size.

        All header-button icons share one sizing rule (track the header
        height, leave ``_ICON_MARGIN`` px of breathing room) — route every
        icon swap through this helper so toggle states stay consistent
        with the initial render.
        """
        IconManager.fit_icon(
            button, icon_name, self.height(), margin=self._ICON_MARGIN
        )

    def has_buttons(self, button_type=None):
        """Check if the header has a specific button type or any button.

        Parameters:
            button_type (str or list, optional): The button type(s) to check for.
                If None, checks if any button exists.

        Returns:
            bool: True if the button exists, False otherwise.
        """
        if button_type is None:
            return bool(self.buttons)

        if isinstance(button_type, str):
            return button_type in self.buttons

        if isinstance(button_type, (list, tuple)):
            return any(btn in self.buttons for btn in button_type)

        return False

    def config_buttons(self, *button_list):
        """Configure header buttons from a list and align them to the right.

        Parameters:
            *button_list: Button names in display order (as args or single list).
                Examples:
                    config_buttons('refresh', 'menu', 'pin')
                    config_buttons(['refresh', 'menu', 'pin'])
                Available: 'refresh', 'menu', 'help', 'collapse', 'minimize',
                'maximize', 'hide', 'pin'
        """
        # Support both styles: config_buttons('a', 'b') and config_buttons(['a', 'b'])
        if len(button_list) == 1 and isinstance(button_list[0], (list, tuple)):
            button_list = button_list[0]

        # Clear layout
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        self.buttons = {}

        # Re-add left-side stretch so buttons align to the right
        self.container_layout.addStretch(1)

        # Insert buttons in order (they go to the right)
        for button_name in button_list:
            if button_name not in self.button_definitions:
                continue

            icon_filename, method_name = self.button_definitions[button_name]
            callback = getattr(self, method_name)

            button = self.create_button(
                icon_filename, callback, button_type=button_name
            )
            button.setVisible(True)

            self.container_layout.addWidget(button)
            self.buttons[button_name] = button

        # Re-add the help button when help text was previously set but
        # 'help' wasn't included in this call's button list. Keeps help
        # discoverable across config_buttons rebuilds.
        if self._help_text and "help" not in self.buttons:
            self._install_help_button(self._help_text)

        self.container_layout.invalidate()
        self.trigger_resize_event()

        # A freshly created menu button defaults to visible; reconcile it with
        # the menu's actual content so an empty menu's button stays hidden.
        self._sync_menu_button_visibility()

    def trigger_resize_event(self):
        current_size = self.size()
        resize_event = QtGui.QResizeEvent(current_size, current_size)
        self.resizeEvent(resize_event)

    def resizeEvent(self, event):
        self.resize_buttons()
        self.update_font_size()
        self._apply_elided_title()
        super().resizeEvent(event)

    def resize_buttons(self):
        button_size = self.height()
        margin = button_size * 0.05
        for button_name, button in self.buttons.items():
            button.setFixedSize(button_size - margin, button_size - margin)

    def update_font_size(self):
        # Calculate font size for the label and buttons relative to widget's height
        label_font_size = self.height() * 0.4
        button_font_size = self.height() * 0.6  # 60% of the widget's height

        # Apply font size to the label
        label_font = self.font()
        label_font.setPointSizeF(label_font_size)
        self.setFont(label_font)

        # Iterate through the widgets in the layout and update the font size for the buttons
        for i in range(self.container_layout.count()):
            widget = self.container_layout.itemAt(i).widget()
            if isinstance(widget, QtWidgets.QPushButton):
                button_font = widget.font()
                button_font.setPointSizeF(button_font_size)
                widget.setFont(button_font)

    def setTitle(self, title):
        """Set the title of the header.

        Parameters:
            title (str): The new title.
        """
        self.setText(title)

    def title(self):
        """Get the title of the header (without any version suffix).

        Returns:
            str: The current title.
        """
        return self._full_title or self.text()

    def setVersion(self, version):
        """Set an optional version string appended to the title.

        The displayed text becomes ``"<title> v<version>"`` when both are set.
        Pass ``""`` or ``None`` to clear.

        Parameters:
            version (str): The version string (e.g. ``"0.1.0"``).
        """
        self._version = (version or "").strip()
        self._apply_elided_title()

    def version(self):
        """Return the current version suffix (without the ``v`` prefix)."""
        return self._version

    def _composed_title(self):
        """Return title + version formatted for display.

        When a version is set, the version segment is wrapped in an inline
        ``<span>`` that forces ``font-weight: normal`` so the version reads as
        a quiet suffix even though the header label itself renders bold.
        """
        title = self._full_title or ""
        if self._version:
            return (
                f"{title} <span style=\"font-weight:normal\">v{self._version}</span>"
            ).strip()
        return title

    def setText(self, text):
        """Override to remember the untruncated title for elision."""
        self._full_title = text or ""
        self._apply_elided_title()

    def _apply_elided_title(self):
        """Truncate the displayed title with an ellipsis when buttons would overlap."""
        # Keep _full_title in sync when text arrived via setProperty("text", ...)
        # (e.g. uic-generated stdset="0" forms) rather than through setText().
        if not self._full_title:
            raw = super().text()
            if raw and not getattr(self, "_version", ""):
                self._full_title = raw
        title = self._full_title or ""
        version = self._version
        full = self._composed_title()
        # Pre-layout (width unknown) or RichText mixin in play: show the raw
        # composed string so tags survive and sizeHint reflects real content.
        if not full or self.width() <= 0 or getattr(self, "has_rich_text", False):
            if super().text() != full:
                super().setText(full)
            return
        spacing = self.container_layout.spacing()
        buttons_width = 0
        visible_count = 0
        for button in self.buttons.values():
            if button.isVisible():
                buttons_width += button.width()
                visible_count += 1
        if visible_count > 0:
            buttons_width += spacing * visible_count
        margins = self.container_layout.contentsMargins()
        reserved = buttons_width + margins.left() + margins.right() + self.indent() + 4
        available = max(0, self.width() - reserved)
        fm = self.fontMetrics()
        if version:
            # Measure version using the non-bold variant so the reserved width
            # matches the rendered (lighter-weight) glyphs.
            version_text = f" v{version}"
            normal_font = QtGui.QFont(self.font())
            normal_font.setBold(False)
            version_width = QtGui.QFontMetrics(normal_font).horizontalAdvance(
                version_text
            )
            title_available = max(0, available - version_width)
            elided_title = fm.elidedText(title, QtCore.Qt.ElideRight, title_available)
            displayed = (
                f"{elided_title} <span style=\"font-weight:normal\">v{version}</span>"
            )
        else:
            displayed = fm.elidedText(title, QtCore.Qt.ElideRight, available)
        if displayed != super().text():
            super().setText(displayed)

    def minimize_window(self):
        """Minimize the window: collapse to header-only, narrow to a fixed width,
        and reposition to the lower-left corner of the screen.

        The minimized geometry is never persisted to session settings.
        Calling again restores the original size and position.
        """
        if self._minimized:
            self.restore_window()
        else:
            self._do_minimize()

    def _do_minimize(self):
        """Internal: collapse + narrow + reposition to lower-left."""
        window = self.window()

        # Save position before collapse (collapse_window saves size)
        self._saved_pos = window.pos()

        # Save current pin state so we can restore it on un-minimize
        self._pin_before_minimize = self.pinned

        # Collapse first (hides siblings, shrinks height)
        w = self.MINIMIZE_WIDTH
        if not self._collapsed:
            self.collapse_window(fixed_width=w)
        elif self._saved_size:
            # Already collapsed but not yet narrowed — apply fixed width
            window.setMinimumWidth(0)
            window.setMaximumWidth(w)
            window.resize(w, window.height())

        # Pin the window so it resists hide requests (e.g. key_show_release)
        self._set_pin_state(True)

        # Suppress geometry saves while minimized
        window.setProperty("_header_minimized", True)

        # Register for stacking and compute slot position
        if self not in Header._minimized_headers:
            Header._minimized_headers.append(self)
        slot = Header._minimized_headers.index(self)

        screen = QtWidgets.QApplication.screenAt(window.geometry().center())
        if screen is None:
            screen = QtWidgets.QApplication.primaryScreen()
        avail = screen.availableGeometry()
        target = self._compute_minimize_position(window, avail, slot)
        window.move(target)

        # Update icon
        if "minimize" in self.buttons:
            self._set_button_icon(self.buttons["minimize"], "maximize")

        self._minimized = True

    def restore_window(self):
        """Restore a minimized window to its original size and position."""
        if not self._minimized:
            return

        window = self.window()

        # Restore pin state from before minimize
        pin_before = getattr(self, "_pin_before_minimize", False)
        self._set_pin_state(pin_before)
        self._pin_before_minimize = False

        # Expand (restores siblings, height, width constraints)
        if self._collapsed:
            self.expand_window()

        # Restore position
        if self._saved_pos is not None:
            window.move(self._saved_pos)
            self._saved_pos = None

        # Clear the suppression flag
        window.setProperty("_header_minimized", False)

        # Update icon
        if "minimize" in self.buttons:
            self._set_button_icon(self.buttons["minimize"], "minimize")

        self._minimized = False

        # Unregister and reflow remaining minimized windows
        if self in Header._minimized_headers:
            Header._minimized_headers.remove(self)
            Header._reflow_minimized()

    def _compute_minimize_position(self, window, avail, slot):
        """Compute the screen position for a minimized window at the given slot.

        Parameters:
            window: The window being minimized.
            avail (QRect): Available screen geometry.
            slot (int): Zero-based stacking index.

        Returns:
            QPoint: Target position in global coordinates.
        """
        m = self.MINIMIZE_MARGIN
        # Use the known collapsed height rather than querying window.height(),
        # which may not yet reflect the collapse if layout hasn't settled.
        header_h = max(self.height(), self.sizeHint().height(), 20)
        collapsed_h = header_h
        parent = self.parent()
        if parent and parent.layout():
            margins = parent.layout().contentsMargins()
            collapsed_h += margins.top() + margins.bottom()

        if self.MINIMIZE_STACK == "vertical":
            x = avail.left() + m
            y = avail.y() + avail.height() - collapsed_h * (slot + 1)
        else:  # horizontal
            x = avail.left() + m + (self.MINIMIZE_WIDTH + m) * slot
            y = avail.y() + avail.height() - collapsed_h
        return QtCore.QPoint(x, y)

    @classmethod
    def _reflow_minimized(cls):
        """Reposition remaining minimized windows to close gaps after a restore."""
        # Prune stale references (deleted widgets)
        cls._minimized_headers = [h for h in cls._minimized_headers if h._minimized]
        for i, header in enumerate(cls._minimized_headers):
            window = header.window()
            screen = QtWidgets.QApplication.screenAt(window.geometry().center())
            if screen is None:
                screen = QtWidgets.QApplication.primaryScreen()
            avail = screen.availableGeometry()
            target = header._compute_minimize_position(window, avail, i)
            window.move(target)

    def toggle_maximize(self):
        """Toggle between maximized and normal window state."""
        window = self.window()
        if window.isMaximized():
            window.showNormal()
            # Update icon to maximize
            if "maximize" in self.buttons:
                self._set_button_icon(self.buttons["maximize"], "maximize")
        else:
            window.showMaximized()
            # Update icon to restore (overlapping windows)
            if "maximize" in self.buttons:
                self._set_button_icon(self.buttons["maximize"], "restore")

    def toggle_fullscreen(self):
        """Toggle between fullscreen and normal window state."""
        window = self.window()
        if window.isFullScreen():
            window.showNormal()
            if "fullscreen" in self.buttons:
                self._set_button_icon(self.buttons["fullscreen"], "screen")
        else:
            window.showFullScreen()
            if "fullscreen" in self.buttons:
                self._set_button_icon(self.buttons["fullscreen"], "restore")

    def hide_window(self):
        """Hide the parent window."""
        if self.pinned:
            self.toggle_pin(from_drag=True)  # Programmatic toggle, not user click

        # Reset minimize/collapse state when hiding
        if self._minimized:
            self.restore_window()
        elif self._collapsed:
            self.expand_window()

        self.window().hide()

    def unhide_window(self):
        """Unhide the parent window."""
        self.window().show()
        if not self.pinned:
            self.toggle_pin(from_drag=True)  # Programmatic toggle, not user click

    def trigger_refresh(self):
        """Emit the refresh_requested signal.

        Slots connect to ``refresh_requested`` to perform the actual refresh
        (rescan a table, repopulate a tree, etc.). Calling this method directly
        is equivalent to clicking the refresh button.
        """
        self.refresh_requested.emit()

    def set_help_text(self, text):
        """Set the tool's help/instruction text and ensure the help button is shown.

        Auto-adds the help button to the header if not already present (inserted
        at the leftmost position, immediately right of the stretch). The text is
        stored as the button's tooltip — so hovering shows it, and clicking the
        button forces the tooltip to pop up (see :meth:`show_help`).

        The text persists across :meth:`config_buttons` rebuilds: if the layout
        is rebuilt later without ``"help"`` in the list, the help button is
        re-added automatically so the help text never silently disappears.

        Parameters:
            text (str): Help / instruction text. Plain text or rich-text HTML
                (e.g. built with :func:`uitk.widgets.mixins.tooltip_mixin.fmt`).
        """
        self._help_text = text or ""
        if "help" in self.buttons:
            self.buttons["help"].setToolTip(self._help_text)
        else:
            self._install_help_button(self._help_text)

    def _install_help_button(self, text):
        """Create the help button, insert it at the leftmost slot, and set its tooltip."""
        icon_filename, method_name = self.button_definitions["help"]
        callback = getattr(self, method_name)
        button = self.create_button(icon_filename, callback, button_type="help")
        button.setToolTip(text)
        # Insert at the leftmost button slot. The stretch lives at index 0,
        # so the first widget sits at index 1.
        self.container_layout.insertWidget(1, button)
        self.buttons["help"] = button
        self.trigger_resize_event()

    def help_text(self):
        """Return the current help text, or ``""``."""
        return self._help_text

    def show_help(self):
        """Pop the help tooltip up at the help button.

        Slots connect implicitly via the help button's ``clicked`` signal.
        Calling this method directly is equivalent to clicking the help button.
        """
        button = self.buttons.get("help")
        if not button:
            return
        text = button.toolTip()
        if not text:
            return
        # Anchor just below the button so the tooltip doesn't cover it.
        pos = button.mapToGlobal(QtCore.QPoint(0, button.height()))
        QtWidgets.QToolTip.showText(pos, text, button)

    def show_menu(self):
        """Show the menu."""
        self.menu.show_as_popup(position="cursorPos")

    def toggle_collapse(self):
        """Toggle between collapsed (header only) and expanded window states."""
        if self._collapsed:
            self.expand_window()
        else:
            self.collapse_window(fixed_width=self.MINIMIZE_WIDTH)

    def _set_siblings_visibility(self, visible):
        """Recursively toggle visibility of all siblings in the parent layout."""
        parent = self.parent()
        if not parent or not parent.layout():
            return

        def recursive_set_vis(layout):
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item.widget():
                    widget = item.widget()
                    if widget is not self:
                        if not visible:
                            # Only hide if currently visible
                            if widget.isVisible():
                                widget.setProperty("header_hidden_state", True)
                                widget.hide()
                        else:
                            # Only show if we hid it
                            if widget.property("header_hidden_state"):
                                widget.show()
                                widget.setProperty("header_hidden_state", None)
                elif item.layout():
                    recursive_set_vis(item.layout())

        recursive_set_vis(parent.layout())

    def collapse_window(self, fixed_width=None):
        """Collapse the parent window to show only the header.

        Parameters:
            fixed_width (int, optional): If given, also narrow the window to
                this width while collapsed.
        """
        if self._collapsed:
            return

        window = self.window()

        # Save current size and size constraints
        self._saved_size = window.size()
        self._saved_min_size = window.minimumSize()
        self._saved_max_size = window.maximumSize()

        # Hide all visible siblings recursively
        self._set_siblings_visibility(False)

        # Walk up hierarchy to window, saving and nuking minimum heights
        # (and minimum widths when collapsing to a fixed_width)
        curr = self.parent()
        self._saved_parent_min_heights = {}
        self._saved_parent_min_widths = {}
        while curr and curr is not window:
            self._saved_parent_min_heights[curr] = curr.minimumHeight()
            curr.setMinimumHeight(0)
            if fixed_width is not None:
                self._saved_parent_min_widths[curr] = curr.minimumWidth()
                curr.setMinimumWidth(0)
            curr = curr.parent()

        # Calculate exact required height based on header height + parent margins
        header_h = max(self.height(), self.sizeHint().height(), 20)
        new_height = header_h
        parent = self.parent()
        if parent and parent.layout():
            margins = parent.layout().contentsMargins()
            new_height += margins.top() + margins.bottom()

        # Save position so we can anchor the right edge in place — keeps the
        # collapse button under the cursor regardless of which way width changes.
        if fixed_width is not None:
            self._collapse_saved_pos = window.pos()

        # Use setFixedHeight to force the exact collapsed height.
        # This overrides any layout size hints that might resist the resize.
        window.setMinimumSize(0, 0)
        window.setMaximumSize(16777215, 16777215)
        window.setFixedHeight(new_height)
        if fixed_width is not None:
            window.setMaximumWidth(fixed_width)
            window.resize(fixed_width, new_height)

        # Move window so the right edge stays in place
        if fixed_width is not None and self._collapse_saved_pos is not None:
            original_right = self._collapse_saved_pos.x() + self._saved_size.width()
            window.move(original_right - fixed_width, window.y())

        # Update icon to expand (chevron down)
        if "collapse" in self.buttons:
            self._set_button_icon(self.buttons["collapse"], "chevron_down")

        self._collapsed = True

    def expand_window(self):
        """Expand the window back to its original size."""
        if not self._collapsed:
            return

        window = self.window()

        # Restore visibility of siblings
        self._set_siblings_visibility(True)

        # Restore ancestor minimum heights and widths
        for widget, min_h in self._saved_parent_min_heights.items():
            if widget:  # check validity
                try:
                    widget.setMinimumHeight(min_h)
                except RuntimeError:
                    pass  # Widget might be deleted
        self._saved_parent_min_heights = {}
        for widget, min_w in self._saved_parent_min_widths.items():
            if widget:
                try:
                    widget.setMinimumWidth(min_w)
                except RuntimeError:
                    pass
        self._saved_parent_min_widths = {}

        # Restore size constraints (this also undoes setFixedHeight)
        if self._saved_min_size:
            window.setMinimumSize(self._saved_min_size)
        else:
            window.setMinimumSize(0, 0)
        if self._saved_max_size:
            window.setMaximumSize(self._saved_max_size)
        else:
            window.setMaximumSize(16777215, 16777215)  # Qt's QWIDGETSIZE_MAX

        # Restore original size
        if self._saved_size:
            window.resize(self._saved_size)
        else:
            window.adjustSize()

        # Restore position if right-edge anchoring moved the window
        if self._collapse_saved_pos is not None:
            window.move(self._collapse_saved_pos)
            self._collapse_saved_pos = None

        # Update icon to collapse (chevron up)
        if "collapse" in self.buttons:
            self._set_button_icon(self.buttons["collapse"], "chevron_up")

        self._collapsed = False

    def toggle_pin(self, from_drag=False):
        """Toggle pinning of the window.

        Parameters:
            from_drag (bool): If True, this was triggered by dragging the header.
        """
        new_state = not self.pinned
        self._set_pin_state(new_state)

        if not new_state:
            self.window().hide()

    def _on_window_pinned_changed(self, pinned: bool):
        """Slot to handle pin state changes from the window."""
        if self.pinned != pinned:
            self._set_pin_state(pinned)

    def _set_pin_state(self, pinned: bool):
        """Internal method to update pin state and sync with window.

        Parameters:
            pinned: The new pin state
        """
        self.pinned = pinned

        # Notify the window of pin state change (if it supports set_pinned)
        window = self.window()
        if hasattr(window, "set_pinned"):
            # Avoid infinite loops / re-triggering
            if hasattr(window, "pinned") and window.pinned != pinned:
                window.set_pinned(pinned)

        # Update button icon
        icon_name = "radio" if pinned else "radio_empty"
        pin_button = self.buttons.get("pin")
        if pin_button:
            self._set_button_icon(pin_button, icon_name)

        self.toggled.emit(pinned)

    def reset_pin_state(self):
        """Force the header into an unpinned state without hiding the window."""
        if not self.pinned:
            return
        self._set_pin_state(False)

    def _refresh_button_style(self, button):
        """Force a button to refresh its stylesheet after property changes."""
        button.update()

    def mousePressEvent(self, event):
        """Handle the mouse press event. If the left button is pressed, store the global position of the mouse cursor.

        Parameters:
            event (QMouseEvent): The mouse event.
        """
        if event.button() == QtCore.Qt.LeftButton:
            self.__mousePressPos = event.globalPos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle the mouse move event."""
        if self.__mousePressPos is not None:
            moveAmount = event.globalPos() - self.__mousePressPos
            if moveAmount.manhattanLength() > 5:
                self.window().move(self.window().pos() + moveAmount)
                self.__mousePressPos = event.globalPos()
                if not self.pinned:  # Only change state if not already pinned
                    self.toggle_pin(from_drag=True)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # No need to toggle pin state here, as pinning is controlled by the button
        self.__mousePressPos = None
        super().mouseReleaseEvent(event)

    def showEvent(self, event):
        if self._minimized:
            self.restore_window()
        elif self._collapsed:
            self.expand_window()
        super().showEvent(event)
        # SYNCHRONOUS — both hooks read only flags/menu state (no post-layout
        # geometry), and a child's showEvent is delivered during the parent's
        # show cascade, i.e. BEFORE first paint. The old singleShot(0)
        # deferral pushed them past the paint: the menu button (or the whole
        # auto-hidden header) painted, then vanished a tick later — an init
        # flash. A menu populated later in the same pre-paint cascade
        # (register_children) still re-shows the button via the on_item_added
        # wiring, also pre-paint.
        self._sync_menu_button_visibility()
        if self._auto_hide_with_os_frame and not self._auto_hide_checked:
            self._auto_hide_checked = True
            self._apply_auto_hide_with_os_frame()

    def _apply_auto_hide_with_os_frame(self):
        """Hide the header if the top-level window draws a native OS title bar.

        Two title bars stacked is almost never what callers want; this keeps
        the header useful as a fallback when the window is frameless and
        invisible otherwise.
        """
        if not self._auto_hide_with_os_frame:
            return
        window = self.window()
        if window is None:
            return
        flags = window.windowFlags()
        is_frameless = bool(flags & QtCore.Qt.FramelessWindowHint)
        if not is_frameless:
            self.hide()

    def _sync_menu_button_visibility(self, *_):
        """Show the header's menu button only when its menu has real content.

        The transient "No options" placeholder is excluded — ``Menu``'s
        ``contains_items`` already ignores it — so an empty (or placeholder-
        only) menu keeps the button hidden. Wired to the menu's
        ``on_item_added`` signal so populating the menu later auto-shows the
        button; ``*_`` absorbs the added-widget argument the signal carries.
        Reads ``_menu`` directly rather than the ``menu`` property to avoid
        force-creating a menu just to hide the button.
        """
        menu_button = self.buttons.get("menu")
        if not menu_button:
            return
        menu = getattr(self, "_menu", None)
        menu_button.setVisible(bool(menu is not None and menu.contains_items))

    def attach_to(self, widget: QtWidgets.QWidget) -> None:
        """Attach this header to the top of a QWidget or QMainWindow's centralWidget if appropriate."""
        # Avoid double-attachment
        if hasattr(widget, "header") and getattr(widget, "header") is self:
            return

        # If passed a QMainWindow (or subclass), redirect to its central widget.
        if isinstance(widget, QtWidgets.QMainWindow) and widget.centralWidget():
            widget = widget.centralWidget()

        # Attach to the widget's layout
        layout = widget.layout()
        if not isinstance(layout, QtWidgets.QLayout):
            layout = QtWidgets.QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            widget.setLayout(layout)
        layout.insertWidget(0, self)
        self.setParent(widget)
        setattr(widget, "header", self)

        # Connect to window signals if available
        window = self.window()
        if hasattr(window, "on_pinned_changed"):
            try:
                window.on_pinned_changed.disconnect(self._on_window_pinned_changed)
            except (TypeError, RuntimeError):
                pass
            window.on_pinned_changed.connect(self._on_window_pinned_changed)

            # Sync initial state from window to header
            if hasattr(window, "pinned") and window.pinned != self.pinned:
                self._set_pin_state(window.pinned)

    def hideEvent(self, event):
        """Reset minimize/collapse state when header (and window) is hidden."""
        if self._minimized:
            self.restore_window()
        elif self._collapsed:
            self.expand_window()
        super().hideEvent(event)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(w)
    header = Header(
        config_buttons=["menu", "collapse", "minimize", "pin", "hide"],
        setTitle="DRAG ME!",
    )
    header.toggled.connect(lambda state: print(f"Header pinned: {state}!"))
    header.menu.add(["Menu Item A", "Menu Item B"])

    layout.addWidget(header)
    w.show()

    # sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Promoting a widget in designer to use a custom class:
>   In Qt Designer, select all the widgets you want to replace,
        then right-click them and select 'Promote to...'.

>   In the dialog:
        Base Class:     Class from which you inherit. ie. QWidget
        Promoted Class: Name of the class. ie. "MyWidget"
        Header File:    Path of the file (changing the extension .py to .h)  ie. myfolder.mymodule.mywidget.h

>   Then click "Add", "Promote",
        and you will see the class change from "QWidget" to "MyWidget" in the Object Inspector pane.
"""
