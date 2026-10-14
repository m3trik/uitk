# !/usr/bin/python
# coding=utf-8
import math
import os
import re
from html import escape
import pythontk as ptk
from qtpy import QtWidgets, QtCore, QtGui, QtSvg
from uitk.themes.style_sheet import StyleSheet
from uitk.widgets._layout_items import _LayoutItems
from uitk.widgets.mixins.attributes import AttributesMixin
from uitk.widgets.mixins.size_grip import SizeGripMixin
from uitk.widgets.mixins.text import RichText, TextOverlay
from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter
from uitk.managers.icon_manager import IconManager
from uitk.managers.cursor_manager import CursorManager
from uitk._bootstrap import Bootstrap


class _HelpCard(QtWidgets.QTextBrowser):
    """A header's help, shown at its ``?`` button.

    Laid out as a tooltip lays out the same text (:meth:`TooltipFormat.wrap`),
    but a tooltip can neither scroll nor be clicked: past *max_share* of the
    screen's height this card scrolls instead of running off the screen, and
    its documentation link opens in the browser. A tool window that never
    takes focus (the tooltip's own window type); it hides once the pointer has
    left both the button and the card.
    """

    #: Pointer polls outside the button and the card before the card hides:
    #: the grace for crossing from one to the other.
    LEAVE_SAMPLES = 2
    POLL_MS = 150

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setObjectName("helpCard")
        self.setFont(QtWidgets.QToolTip.font())
        self.setPalette(QtWidgets.QToolTip.palette())
        self.setOpenExternalLinks(True)
        self.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)  # wrap() broke the lines
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._anchor = None
        self._outside = 0
        self._poll = QtCore.QTimer(self)
        self._poll.setInterval(self.POLL_MS)
        self._poll.timeout.connect(self._check_pointer)
        StyleSheet.cast_shadow(self)

    def popup(self, anchor, html: str, max_share: float) -> None:
        """Show *html* under *anchor*, at most *max_share* of its screen tall."""
        self._anchor = anchor
        self.ensurePolished()  # the style sheet's border is in frameWidth()
        self.setHtml(html)
        screen = anchor.screen() or QtWidgets.QApplication.primaryScreen()
        avail = screen.availableGeometry()
        # Measured on a copy: the browser lays its own document out at its
        # viewport's width, which is what is being decided here.
        doc = self.document().clone()  # unparented: Python owns it
        doc.setTextWidth(-1)
        frame = 2 * self.frameWidth()
        text_w = math.ceil(doc.idealWidth())
        text_h = math.ceil(doc.size().height())
        cap = max(1, int(avail.height() * max_share))
        height = min(text_h + frame, cap)
        width = text_w + frame
        if height < text_h + frame:  # scrolls: room for the bar beside the text
            width += self.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent)
        clipped = width > avail.width()  # a screen narrower than a line
        width = min(width, avail.width())
        self.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAsNeeded if clipped else QtCore.Qt.ScrollBarAlwaysOff
        )
        top_left = anchor.mapToGlobal(QtCore.QPoint(0, anchor.height()))
        x = max(avail.left(), min(top_left.x(), avail.right() + 1 - width))
        y = top_left.y()
        if y + height > avail.bottom() + 1:  # no room below: above the button
            y = anchor.mapToGlobal(QtCore.QPoint(0, 0)).y() - height
        y = max(avail.top(), y)
        self.setGeometry(x, y, width, height)
        self.verticalScrollBar().setValue(0)
        self.show()
        self.raise_()
        self._outside = 0
        self._poll.start()

    def _pointer_over(self, pos) -> bool:
        if self.frameGeometry().contains(pos):
            return True
        try:
            anchor = self._anchor
            return bool(
                anchor is not None
                and anchor.isVisible()
                and anchor.rect().contains(anchor.mapFromGlobal(pos))
            )
        except RuntimeError:  # the button was rebuilt away
            return False

    def _check_pointer(self) -> None:
        if self._pointer_over(QtGui.QCursor.pos()):
            self._outside = 0
            return
        self._outside += 1
        if self._outside >= self.LEAVE_SAMPLES:
            self.hide()

    def hideEvent(self, event):
        self._poll.stop()
        super().hideEvent(event)


class _DragRescaleGuard(QtCore.QObject):
    """Keeps a window's size while a header drag moves it.

    Between monitors of different scale Qt's logical coordinates have a gap,
    and while a drag's ``move()`` steps cross it the window flips between the
    screens and the window system rescales it on each flip (x1.25 a step
    between 100% and 125%) -- it grew on every drag. That resize is
    spontaneous (the window system's) and lands a turn or two after the move;
    the app's own resizes are not. So a spontaneous resize is undone one
    event-loop turn later, while a non-spontaneous one is a real resize and
    becomes the size kept. A maximized or full-screen window is the window
    system's to size.
    """

    #: How long the guard outlives the drag, for a rescale still in flight
    #: from its last move.
    GRACE_MS = 250

    def __init__(self, window: QtWidgets.QWidget):
        super().__init__(window)
        self._size = window.size()  # the size kept
        self._held = None  # the size a pending undo puts back
        # Child timers rather than ``singleShot(ms, self, fn)``: PySide 6.5.3
        # (Maya 2025) has no context overload, and a child dies with the guard.
        self._undo_timer = self._timer(self._undo)
        self._detach_timer = self._timer(self._detach)
        window.installEventFilter(self)

    def _timer(self, slot) -> QtCore.QTimer:
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(slot)
        return timer

    def eventFilter(self, window, event):
        if event.type() == QtCore.QEvent.Resize and window is self.parent():
            if not event.spontaneous():
                if self._held is None:
                    self._size = event.size()
            elif self._held is None and not window.windowState() & (
                QtCore.Qt.WindowMaximized | QtCore.Qt.WindowFullScreen
            ):
                self._held = self._size
                self._undo_timer.start(0)
        return False

    def _undo(self):
        size, self._held = self._held, None
        window = self.parent()
        if size is not None and window.size() != size:
            window.resize(size)

    def release(self):
        """The drag is over: keep watching for :attr:`GRACE_MS`, then detach."""
        self._detach_timer.start(self.GRACE_MS)

    def _detach(self):
        self.parent().removeEventFilter(self)
        self.deleteLater()


class Header(
    QtWidgets.QLabel, AttributesMixin, RichText, TextOverlay, ptk.LoggingMixin
):
    """Header is a QLabel that can be dragged around the screen and can be pinned/unpinned. It provides a customizable
    header bar with buttons for common window actions such as minimizing, hiding, and pinning.

    The pin button has two click behaviors, selected by :attr:`pin_on_drag_only`
    (headers that don't choose explicitly follow the process-wide default —
    :meth:`set_default_pin_on_drag_only`, driven by ``UiHandler.pin_click_hides``):

    * ``False`` — classic toggle: click to pin, click again to
      unpin (which hides the window).
    * ``True`` — one-click dismiss: the button always hides the window, and
      pinning is reached by dragging the header. Hovering it advertises that:
      the background turns red, and while unpinned the icon swaps to the close
      glyph, so the button reads as the hide button it acts as.

    A separate opt-in, :attr:`pin_on_tap`, decides what an *auto-hide* request
    means for a window that just appeared — see :meth:`claim_hide_as_tap`.

    Signals:
        toggled(bool): Emitted when the pin state is toggled.
        refresh_requested(): Emitted when the refresh button is clicked.

    Attributes:
        button_definitions (dict): Defines the properties of the buttons available in the header.
        state (str): Represents the current state of the header ("unpinned", "pinned").
    """

    # Qt Designer widget-box entry.
    designer_spec = {
        "icon": "window",
        "object_name": "header",
        "string_properties": {"text": "richtext", "helpText": "richtext"},
    }

    toggled = QtCore.Signal(bool)
    refresh_requested = QtCore.Signal()

    #: The help card's height cap, as a share of the screen's available
    #: height: longer help scrolls inside it rather than filling the screen.
    HELP_MAX_SCREEN_SHARE = 0.6

    #: The buttons that dismiss the window. One header carries one of them:
    #: the pin button hides the window too, so the two are alternative
    #: answers to how the window goes away (see :meth:`config_buttons`).
    DISMISS_BUTTONS = ("pin", "hide")

    MINIMIZE_WIDTH = 200  # Fixed width when minimized to corner
    MINIMIZE_STACK = "horizontal"  # "horizontal" or "vertical"
    MINIMIZE_MARGIN = 8  # Margin from screen edges and between stacked windows
    _minimized_headers = []  # Class-level registry for stacking

    # Process-wide default for headers that don't choose a pin-click mode
    # explicitly (constructor kwarg / property left at None) — which is every
    # header built by generic chrome: .ui-embedded headers, Menu's option-box
    # chrome, persistent-mode menus. ``UiHandler`` seeds and updates it from
    # its ``pin_click_hides`` preference, so ONE user switch reaches headers
    # the handler never styles. Live default-following headers re-sync their
    # visuals on next show (see ``showEvent``).
    _pin_on_drag_only_default = False

    # Process-wide default for tap-to-pin (see ``pin_on_tap``). Off by default:
    # the shipped behavior is that a transient window dismisses on every
    # auto-hide request. ``UiHandler.pin_on_tap`` owns this the same way
    # ``pin_click_hides`` owns the mode default above.
    _pin_on_tap_default = False

    # Tap-to-pin window, in milliseconds. An auto-hide request that lands
    # within this long of the window becoming visible reads as a *tap* of the
    # activation key rather than a *hold* — see ``claim_hide_as_tap``. Sized
    # for the natural gap between clicking a marking-menu item and letting the
    # key go (~150-300ms), well under a deliberate peek (~1s+).
    PIN_ON_TAP_MS = 500

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
        pin_on_drag_only=None,
        pin_on_tap=None,
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
            pin_on_drag_only (bool, optional): If True, clicking the pin button hides
                the window outright (and hovering it shows the red hide affordance);
                the window is pinned by dragging the header. If False,
                clicking the pin button toggles traditional pin/unpin behavior.
                If None (default), the header follows the process-wide default
                (:meth:`set_default_pin_on_drag_only` — driven by
                ``UiHandler.pin_click_hides``). Settable after construction —
                see :attr:`pin_on_drag_only`.
            pin_on_tap (bool, optional): If True, an auto-hide request that
                arrives within :attr:`PIN_ON_TAP_MS` of the window becoming
                visible pins the window open instead of dismissing it — the
                user tapped the activation key rather than holding it. If None
                (default), the header follows the process-wide default
                (:meth:`set_default_pin_on_tap` — driven by
                ``UiHandler.pin_on_tap``). See :meth:`claim_hide_as_tap`.
            auto_hide_with_os_frame (bool, optional): If True (default), the
                header hides itself when its top-level window has a native
                OS title bar (i.e. is not frameless), so the two title bars
                don't stack. Set False to force the header to always show.
            **kwargs: Additional attributes for the header (e.g., setTitle="My Title").
        """
        super().__init__(parent)
        self.pinned = False  # unpinned, pinned
        # None = follow the class-level default (see _pin_on_drag_only_default)
        self._pin_on_drag_only = (
            None if pin_on_drag_only is None else bool(pin_on_drag_only)
        )
        # None = follow the class-level default (see _pin_on_tap_default)
        self._pin_on_tap = None if pin_on_tap is None else bool(pin_on_tap)
        self._pin_hovered = False
        self._auto_hide_with_os_frame = auto_hide_with_os_frame
        self._auto_hide_checked = False
        self._collapsed = False
        # Re-entrancy guard for the collapsed-state re-assert in eventFilter:
        # re-hiding a sibling posts the very LayoutRequest that triggered it.
        self._reasserting_collapse = False
        # The container being watched while collapsed. Held rather than
        # re-derived from parent(), so the expand removes the filter from the
        # object it was installed on even if the header was reparented in
        # between (re-deriving would strand the filter on the old container).
        self._collapse_watch = None
        self._minimized = False
        self._saved_size = None
        self._saved_min_size = None
        self._saved_max_size = None
        self._saved_pos = None
        self._saved_parent_min_heights = {}  # Store min heights of ancestors
        self._saved_parent_min_widths = {}  # Store min widths of ancestors
        self._collapse_anchor_right = (
            False  # Collapse narrowed the window (expand re-anchors right edge)
        )
        self.__mousePressPos = None
        self.buttons = {}  # Initialize buttons dict to avoid AttributeError
        self._full_title = ""  # Untruncated title for elision
        self._version = ""  # Optional version suffix appended to title
        # Persisted help text — survives config_buttons rebuilds so the help
        # button is re-added automatically if the layout is rebuilt later.
        self._help_text = ""
        self._help_url = ""
        self._help_card = None  # built on first show

        self.container_layout = QtWidgets.QHBoxLayout(self)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(1)
        self.container_layout.addStretch(1)

        self.setLayout(self.container_layout)
        self.setCursor(QtGui.QCursor(QtCore.Qt.OpenHandCursor))
        # HoverMove is the hook for the stale-hover heal (see event()). Hover
        # events need no mouse tracking and never propagate to the parent —
        # a tracked MouseMove would, and would flood the marking menu's hover
        # tracker with button-less moves.
        self.setAttribute(QtCore.Qt.WA_Hover, True)
        self._dragging = False  # a press that has moved far enough to drag
        self._drag_guard = None  # a _DragRescaleGuard while a drag moves the window

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
    def pin_on_drag_only(self) -> bool:
        """Whether a pin-button click dismisses the window instead of pinning it.

        See the class docstring for the two behaviors. Resolves to the
        process-wide default while unset (the common case — generic chrome
        never sets it), so ``UiHandler.pin_click_hides`` governs every such
        header through :meth:`set_default_pin_on_drag_only`. Assigning a bool
        pins THIS header to a mode and re-syncs the pin button's visuals;
        assigning ``None`` re-follows the default.
        """
        if self._pin_on_drag_only is None:
            return type(self)._pin_on_drag_only_default
        return self._pin_on_drag_only

    @pin_on_drag_only.setter
    def pin_on_drag_only(self, value) -> None:
        before = self.pin_on_drag_only
        self._pin_on_drag_only = None if value is None else bool(value)
        if self.pin_on_drag_only != before:
            self._sync_pin_affordance()

    @classmethod
    def set_default_pin_on_drag_only(cls, value: bool) -> None:
        """Set the process-wide pin-click mode for default-following headers.

        Owned by ``UiHandler.pin_click_hides`` (seeded at handler init,
        updated when the preference flips). No live registry of headers is
        needed: click behavior resolves the default at click time, and the
        visuals re-sync on the next Enter/show — before hover styling or a
        tooltip could show stale state.
        """
        cls._pin_on_drag_only_default = bool(value)

    @property
    def pin_on_tap(self) -> bool:
        """Whether a just-shown window pins itself instead of auto-hiding.

        The user-facing choice between the two ways an activation key can
        behave (see :meth:`claim_hide_as_tap`): hold-to-peek only (``False``,
        the shipped behavior) or hold-to-peek *and* tap-to-keep (``True``).
        Resolves to the process-wide default while unset — the common case,
        so ``UiHandler.pin_on_tap`` governs every generic header through
        :meth:`set_default_pin_on_tap`. Assigning a bool pins THIS header to a
        behavior; assigning ``None`` re-follows the default.
        """
        if self._pin_on_tap is None:
            return type(self)._pin_on_tap_default
        return self._pin_on_tap

    @pin_on_tap.setter
    def pin_on_tap(self, value) -> None:
        self._pin_on_tap = None if value is None else bool(value)

    @classmethod
    def set_default_pin_on_tap(cls, value: bool) -> None:
        """Set the process-wide tap-to-pin behavior for default-following headers.

        Owned by ``UiHandler.pin_on_tap``. Nothing visual depends on it (the
        pin button looks and acts the same either way), so unlike
        :meth:`set_default_pin_on_drag_only` there is no affordance to re-sync
        — the behavior resolves at hide-request time.
        """
        cls._pin_on_tap_default = bool(value)

    def claim_hide_as_tap(self, elapsed_ms) -> bool:
        """Pin the window open instead of letting an auto-hide request through.

        This is the tap-vs-hold split, and *elapsed_ms* — how long the window
        has been visible when the hide request lands — is the whole signal.
        The activation key itself is not observable from here (the marking
        menu's key state is on the far side of ``MainWindow.request_hide``),
        but it doesn't need to be: an auto-hide fires on key *release*, so the
        gap between the window appearing and the request arriving IS how long
        the key was held after the window came up.

        * Released almost immediately (< :attr:`PIN_ON_TAP_MS`) — the user
          opened the tool to use it. Pin it open like a standard window.
        * Held longer — the user was peeking. Let the hide through.

        Off unless :attr:`pin_on_tap` is set, so the default behavior is
        unchanged: every auto-hide request dismisses. A header with no pin
        button never claims either: it has no way to show the pinned state or
        to let the user undo it, and a pinned window refuses ``hide()``
        outright (``MainWindow.setVisible``) — so pinning one would strand it
        on screen. That's the same ``"pin" in self.buttons`` precondition
        :meth:`toggle_collapse` applies before auto-pinning.

        Parameters:
            elapsed_ms (int): Milliseconds the window has been visible, or a
                negative value if it has never been shown (never a tap).

        Returns:
            bool: True if the request was consumed by pinning instead.
        """
        if self.pinned or not self.pin_on_tap or "pin" not in self.buttons:
            return False
        if elapsed_ms is None or elapsed_ms < 0 or elapsed_ms >= self.PIN_ON_TAP_MS:
            return False
        self._set_pin_state(True)
        return True

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
        # Built here and never registered, so join the tooltip presenter directly.
        TooltipPresenter.manage(button)
        return button

    def _set_button_icon(self, button, icon_name):
        """Render *icon_name* onto *button* at the header's current size.

        All header-button icons share one sizing rule (track the header
        height, leave ``_ICON_MARGIN`` px of breathing room) — route every
        icon swap through this helper so toggle states stay consistent
        with the initial render.
        """
        IconManager.fit_icon(button, icon_name, self.height(), margin=self._ICON_MARGIN)

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

        A header carries ONE of :attr:`DISMISS_BUTTONS`: the pin button hides
        the window too, so a list naming both keeps the first named.

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
        button_list = self._one_dismiss_button(button_list)

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

        # Re-add the help button when help was previously set but 'help'
        # wasn't included in this call's button list. Keeps help
        # discoverable across config_buttons rebuilds.
        if "help" in self.buttons:
            self.buttons["help"].installEventFilter(self)  # hover shows the card
        elif self._help_text or self._help_url:
            self._install_help_button()

        self.container_layout.invalidate()
        self.trigger_resize_event()

        # A rebuilt pin button is a fresh QPushButton that has received no
        # Enter yet — drop stale hover state, then re-apply the mode's icon /
        # QSS hook / hover wiring to it.
        self._pin_hovered = False
        self._sync_pin_affordance()

        # A freshly created menu button defaults to visible; reconcile it with
        # the menu's actual content so an empty menu's button stays hidden.
        self._sync_menu_button_visibility()

    @classmethod
    def _one_dismiss_button(cls, names) -> list:
        """*names* with every dismissal button after the first one dropped."""
        out, dismiss = [], None
        for name in names:
            if name in cls.DISMISS_BUTTONS:
                if dismiss is not None:
                    continue
                dismiss = name
            out.append(name)
        return out

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
        for widget in _LayoutItems.widgets(self.container_layout):
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
                f'{title} <span style="font-weight:normal">v{self._version}</span>'
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
        #
        # Design time is the third case, for a different reason: Qt Designer
        # reads the title back through the ``text`` property, which resolves to
        # QLabel's C++ getter and so returns whatever is *painted*. Eliding
        # there would write the ellipsis into the .ui file as the real title —
        # the form would lose a character of its name on every save.
        if (
            not full
            or self.width() <= 0
            or getattr(self, "has_rich_text", False)
            or self.is_design_time()
        ):
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
                f'{elided_title} <span style="font-weight:normal">v{version}</span>'
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
        """Reposition remaining minimized windows to close gaps after a restore.

        Prunes dead entries defensively: a window destroyed while minimized
        never runs ``restore_window``, so its Header lingers in the registry
        with a dangling C++ object. Touching such a header (``window()`` below,
        or even its ``_minimized`` flag) raises ``RuntimeError: Internal C++
        object already deleted`` and would otherwise break the restore of an
        unrelated live window. Any header that raises — or is no longer
        minimized — is dropped, and slot indices are recomputed from the
        surviving (live) headers so the stack stays gap-free.
        """
        live = []
        for header in cls._minimized_headers:
            try:
                if not header._minimized:
                    continue
                window = header.window()
                screen = QtWidgets.QApplication.screenAt(window.geometry().center())
                if screen is None:
                    screen = QtWidgets.QApplication.primaryScreen()
                avail = screen.availableGeometry()
                # len(live) is the compacted slot index for this live header.
                target = header._compute_minimize_position(window, avail, len(live))
                window.move(target)
                live.append(header)
            except RuntimeError:
                # C++ object for this header/window was deleted; drop it.
                continue
        cls._minimized_headers = live

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
        """Hide the parent window, unpinning it first.

        The window's own pin counts too: a pinned ``MainWindow`` vetoes
        ``hide()``, so a pin the header never heard of left the hide button
        dead.
        """
        if self.pinned or getattr(self.window(), "pinned", False):
            self._set_pin_state(False)

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

    def set_help_text(self, text, url=None):
        """Set the tool's help/instruction text and ensure the help button is shown.

        Auto-adds the help button to the header if not already present (inserted
        at the leftmost position, immediately right of the stretch). Hovering or
        clicking the button shows the help card (see :meth:`show_help`): laid
        out as a tooltip, capped at :attr:`HELP_MAX_SCREEN_SHARE` of the
        screen's height (longer help scrolls), and ending in a link to *url*.

        Keep the text to what a user needs at the panel and put the rest in
        the document *url* points at: a card is read at a glance.

        The text persists across :meth:`config_buttons` rebuilds: if the layout
        is rebuilt later without ``"help"`` in the list, the help button is
        re-added automatically so the help text never silently disappears.

        Parameters:
            text (str): Help / instruction text. Plain text or rich-text HTML
                (e.g. built with :meth:`pythontk.TooltipFormat.fmt`).
            url (str, optional): The tool's full documentation, linked at the
                card's foot. ``None`` keeps the current link; ``""`` clears it.
        """
        self._help_text = text or ""
        if url is not None:
            self._help_url = url
        if "help" not in self.buttons:
            self._install_help_button()

    def _install_help_button(self):
        """Create the help button and insert it at the leftmost slot."""
        icon_filename, method_name = self.button_definitions["help"]
        callback = getattr(self, method_name)
        button = self.create_button(icon_filename, callback, button_type="help")
        button.installEventFilter(self)  # hover shows the card
        # Insert at the leftmost button slot. The stretch lives at index 0,
        # so the first widget sits at index 1.
        self.container_layout.insertWidget(1, button)
        self.buttons["help"] = button
        self.trigger_resize_event()

    def help_text(self):
        """Return the current help text, or ``""``."""
        return self._help_text

    def help_url(self):
        """Return the help's documentation link, or ``""``."""
        return self._help_url

    def help_html(self) -> str:
        """The help card's content: the help text, then the documentation link.

        Laid out as a tooltip lays the same text out
        (:meth:`TooltipFormat.wrap`), so hover and click read alike.
        """
        text, url = self._help_text, self._help_url
        if text and not ptk.TooltipFormat.is_rich(text):
            text = escape(text).replace("\n", "<br>")
        if url:
            text += (
                f"<p style='margin:6px 0 0 0'><a href='{escape(url, quote=True)}'>"
                "Full documentation</a></p>"
            )
        return ptk.TooltipFormat.wrap(text, rich=True) if text else ""

    def show_help(self):
        """Show the help card at the help button.

        Slots connect implicitly via the help button's ``clicked`` signal, and
        the button's hover shows it too. Calling this method directly is
        equivalent to clicking the help button.
        """
        button = self.buttons.get("help")
        html = self.help_html()
        if not button or not html:
            return
        if self._help_card is None:
            self._help_card = _HelpCard(self)
        self._help_card.popup(button, html, self.HELP_MAX_SCREEN_SHARE)

    def show_menu(self):
        """Show the menu."""
        self.menu.show_as_popup(position="cursorPos")

    def toggle_collapse(self):
        """Toggle between collapsed (header only) and expanded window states.

        Collapsing auto-pins the window when a pin button is present and the
        window is unpinned — a collapsed strip that still dismisses itself on
        focus loss (or a hide request) is unusable, since nothing but the
        header is left to interact with.
        """
        if self._collapsed:
            self.expand_window()
        else:
            self.collapse_window(fixed_width=self.MINIMIZE_WIDTH)
            if "pin" in self.buttons and not self.pinned:
                self._set_pin_state(True)

    def _set_siblings_visibility(self, visible):
        """Recursively toggle visibility of all siblings in the parent layout.

        Hiding is gated on ``isHidden()``, NOT ``isVisible()``. The two differ
        exactly when the window itself is off screen: ``isVisible()`` is False
        for every child of an unshown window, so the old gate hid *nothing*
        when a collapse ran before the first show (or while the window was
        hidden) — the window was then pinned to the header's height with all
        its content still shown, which draws the content up inside the header
        strip. ``isHidden()`` reports the widget's OWN state, so it stays True
        only for a widget something else deliberately hid — which must survive
        the round trip untouched, since ``expand_window`` restores only what
        carries ``header_hidden_state``.

        Re-entrant by design: calling it again while collapsed re-hides any
        sibling that has since been shown (see :meth:`eventFilter`).
        """
        parent = self.parent()
        if not parent or not parent.layout():
            return

        def recursive_set_vis(layout):
            for entry in _LayoutItems.entries(layout):
                if isinstance(entry, QtWidgets.QWidget):
                    widget = entry
                    if widget is not self:
                        if not visible:
                            # Only hide what isn't already hidden
                            if not widget.isHidden():
                                widget.setProperty("header_hidden_state", True)
                                widget.hide()
                        else:
                            # Only show if we hid it
                            if widget.property("header_hidden_state"):
                                widget.show()
                                widget.setProperty("header_hidden_state", None)
                elif isinstance(entry, QtWidgets.QLayout):
                    recursive_set_vis(entry)

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

        # Hide all visible siblings recursively, then watch the container so
        # anything shown later while collapsed is hidden again (see
        # :meth:`eventFilter`). ``installEventFilter`` de-dupes.
        self._set_siblings_visibility(False)
        self._collapse_watch = self.parent()
        if self._collapse_watch is not None:
            self._collapse_watch.installEventFilter(self)

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

        # Use setFixedHeight to force the exact collapsed height.
        # This overrides any layout size hints that might resist the resize.
        window.setMinimumSize(0, 0)
        window.setMaximumSize(16777215, 16777215)
        window.setFixedHeight(new_height)
        if fixed_width is not None:
            window.setMaximumWidth(fixed_width)
            window.resize(fixed_width, new_height)
            # Anchor the right edge in place — keeps the collapse button under
            # the cursor regardless of which way width changes. (Resizes never
            # move the top-left, so x() still reads the pre-collapse position.)
            original_right = window.x() + self._saved_size.width()
            window.move(original_right - fixed_width, window.y())
            self._collapse_anchor_right = True

        # Suppress geometry persistence while collapsed — the strip geometry
        # must never be what a later session restores (see MainWindow.
        # save_window_geometry; mirrors the _header_minimized suppression).
        window.setProperty("_header_collapsed", True)

        # Update icon to expand (chevron down)
        if "collapse" in self.buttons:
            self._set_button_icon(self.buttons["collapse"], "chevron_down")

        self._collapsed = True

    def expand_window(self):
        """Expand the window back to its original size."""
        if not self._collapsed:
            return

        window = self.window()

        # Strip width BEFORE the restores below widen the window in place —
        # the expand re-anchors the right edge against where the strip sits
        # NOW, since the user may have dragged it while collapsed (restoring
        # the collapse-time position would teleport it back).
        collapsed_width = window.width()

        # Stop re-asserting the collapse before restoring anything, or the
        # watch would immediately re-hide what the restore shows.
        if self._collapse_watch is not None:
            try:
                self._collapse_watch.removeEventFilter(self)
            except RuntimeError:  # container already deleted
                pass
            self._collapse_watch = None

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

        # Undo the collapse's right-edge anchoring: keep the right edge where
        # the strip's right edge is now. When the strip was never moved this
        # lands exactly on the pre-collapse position; when the user dragged it,
        # the window expands in place instead of teleporting back.
        if self._collapse_anchor_right:
            window.move(window.x() + collapsed_width - window.width(), window.y())
            self._collapse_anchor_right = False
            # A strip dragged near the screen edge can expand off-screen;
            # clamp when the window supports it (same contract as
            # UiHandler._position_window).
            if getattr(window, "ensure_on_screen", False) and hasattr(
                window, "_ensure_on_screen"
            ):
                window._ensure_on_screen()

        # Re-enable geometry persistence now that real geometry is back.
        window.setProperty("_header_collapsed", False)

        # Update icon to collapse (chevron up)
        if "collapse" in self.buttons:
            self._set_button_icon(self.buttons["collapse"], "chevron_up")

        self._collapsed = False

    def toggle_pin(self, from_drag=False):
        """Toggle pinning of the window.

        Parameters:
            from_drag (bool): True when the call is internal (a header drag, or
                another programmatic pin change) rather than a pin-button click.
                In :attr:`pin_on_drag_only` mode only these calls toggle the pin
                state; a click hides the window outright.
        """
        if self.pin_on_drag_only and not from_drag:
            # One-click dismissal — the button acts as the hide button its
            # hover visuals advertise. Pinning is reached by dragging.
            self.hide_window()
            return

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

        # Icon (and, in click-to-hide mode, tooltip) follow the new state.
        self._sync_pin_affordance()

        self.toggled.emit(pinned)

    def reset_pin_state(self):
        """Force the header into an unpinned state without hiding the window."""
        if not self.pinned:
            return
        self._set_pin_state(False)

    def _refresh_button_style(self, button):
        """Force a button to refresh its stylesheet after property changes.

        A dynamic property stamped after the widget's first polish doesn't
        re-run the QSS selectors on its own — only an unpolish/polish cycle
        does (same contract as ``StyleSheet``'s property sweep).
        """
        style = button.style()
        style.unpolish(button)
        style.polish(button)
        button.update()

    # Dynamic property the QSS keys the red hover background on. Stamped on
    # the pin button whenever ``pin_on_drag_only`` is active.
    _PIN_HIDES_PROPERTY = "pinHides"

    def _sync_pin_affordance(self):
        """Sync the pin button's visuals with the current mode and pin state.

        Single home for everything mode-dependent about the pin button:

        * the ``pinHides`` dynamic property the stylesheet keys the red hover
          background on,
        * the icon — hovering an *unpinned* pin button in click-to-hide mode
          shows the close glyph, because that's what the click does,
        * the tooltip,
        * the hover wiring (this header filters the button's enter/leave
          events rather than subclassing QPushButton).

        No-ops when the header has no pin button.
        """
        button = self.buttons.get("pin")
        if button is None:
            return

        hides_on_click = self.pin_on_drag_only  # resolves the class default
        # ``installEventFilter`` de-dupes (Qt removes any existing instance
        # first), so re-syncing a live header can't stack filters.
        button.installEventFilter(self)

        if button.property(self._PIN_HIDES_PROPERTY) != hides_on_click:
            button.setProperty(self._PIN_HIDES_PROPERTY, hides_on_click)
            self._refresh_button_style(button)

        # Hover only reads as "will hide" while the affordance is active.
        if hides_on_click and self._pin_hovered and not self.pinned:
            icon_name = "close"
        else:
            icon_name = "radio" if self.pinned else "radio_empty"
        # Sync runs on every Enter/Leave/show — skip the SVG re-raster when
        # the glyph is already current (IconManager tracks the name).
        info = IconManager.registered_info(button)
        if info is None or info.get("name") != icon_name:
            self._set_button_icon(button, icon_name)

        if self.pinned:
            button.setToolTip("Unpin and hide the window.")
        elif hides_on_click:
            button.setToolTip("Hide the window.\nDrag the header to pin it open.")
        else:
            button.setToolTip("Pin the window open.")

    def eventFilter(self, watched, event):
        """Track pin-button hover, show the help card for the help button's
        tooltip, and keep a collapsed window's content hidden."""
        if event.type() == QtCore.QEvent.ToolTip and watched is self.buttons.get(
            "help"
        ):
            self.show_help()
            return True
        if watched is self.buttons.get("pin"):
            event_type = event.type()
            if event_type == QtCore.QEvent.Enter:
                self._pin_hovered = True
                self._sync_pin_affordance()
            elif event_type == QtCore.QEvent.Leave:
                self._pin_hovered = False
                self._sync_pin_affordance()
        elif (
            self._collapsed
            and not self._reasserting_collapse
            and watched is self._collapse_watch
            and event.type() == QtCore.QEvent.LayoutRequest
        ):
            # A collapsed window is only as tall as its header, so ANY content
            # that becomes visible again while collapsed is laid out inside the
            # header strip and paints over it — the "layout moves up into the
            # header" symptom. Content comes back on its own all the time (a
            # table repopulating on a selection change, a status row appearing,
            # a group expanding), and each such show posts a LayoutRequest to
            # the container, so that is where the collapse invariant is
            # re-asserted. Re-hiding posts another LayoutRequest, hence the
            # guard.
            self._reasserting_collapse = True
            try:
                self._set_siblings_visibility(False)
            finally:
                self._reasserting_collapse = False
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        """Handle the mouse press event. If the left button is pressed, store the global position of the mouse cursor.

        Parameters:
            event (QMouseEvent): The mouse event.
        """
        if event.button() == QtCore.Qt.LeftButton:
            self.__mousePressPos = event.globalPos()
        super().mousePressEvent(event)

    def event(self, event):
        # A hover move is proof the pointer is over the header. If Qt still
        # says it is not, its enter/leave bookkeeping is stale and the open
        # hand set in __init__ never applies (the "cursor never changes until
        # I click somewhere" report) — re-dispatch the Enter so it does.
        if event.type() == QtCore.QEvent.HoverMove and self.__mousePressPos is None:
            CursorManager.heal_hover(self, event.globalPosition().toPoint())
        return super().event(event)

    def mouseMoveEvent(self, event):
        """Handle the mouse move event."""
        if self.__mousePressPos is not None:
            moveAmount = event.globalPos() - self.__mousePressPos
            if moveAmount.manhattanLength() > 5:
                if not self._dragging:
                    self._dragging = True
                    CursorManager.push(self, QtCore.Qt.ClosedHandCursor)
                    if self._start_system_move():
                        if not self.pinned:
                            self.toggle_pin(from_drag=True)
                        return super().mouseMoveEvent(event)
                    self._drag_guard = _DragRescaleGuard(self.window())
                self.window().move(self.window().pos() + moveAmount)
                self.__mousePressPos = event.globalPos()
                if not self.pinned:  # Only change state if not already pinned
                    self.toggle_pin(from_drag=True)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # No need to toggle pin state here, as pinning is controlled by the button
        self.__mousePressPos = None
        self._end_drag_cursor()
        super().mouseReleaseEvent(event)

    def _start_system_move(self) -> bool:
        """Hand the drag to the compositor where a client cannot move its own
        window (native Wayland ignores ``move()`` on a top-level): True when it
        took over. The compositor then owns the pointer until the button comes
        up, so no release reaches us -- the drag state ends here."""
        if Bootstrap.positions_windows():
            return False
        handle = self.window().windowHandle()
        if handle is None or not handle.startSystemMove():
            return False
        self.__mousePressPos = None
        self._end_drag_cursor()
        return True

    def _end_drag_cursor(self):
        """Put the open hand back after a drag — from the release, or from a
        hide that lands mid-drag and swallows the release."""
        if self._dragging:
            self._dragging = False
            if self._drag_guard is not None:
                self._drag_guard.release()
                self._drag_guard = None
            CursorManager.pop(self)

    def showEvent(self, event):
        if self._minimized:
            self.restore_window()
        elif self._collapsed:
            self.expand_window()
        self._follow_window_pin()
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
        # Re-adopt the (possibly flipped) process-wide pin-click default —
        # this is how a default change reaches an already-built menu header:
        # menus rebuild their visuals on every open.
        self._pin_hovered = False  # fresh show → no Enter delivered yet
        self._sync_pin_affordance()
        if self._auto_hide_with_os_frame and not self._auto_hide_checked:
            self._auto_hide_checked = True
            self._apply_auto_hide_with_os_frame()

    def _apply_auto_hide_with_os_frame(self):
        """Hide the header if the top-level window draws a native OS title bar.

        Two title bars stacked is almost never what callers want; this keeps
        the header useful as a fallback when the window is frameless and
        invisible otherwise.

        Never fires while a form is being authored: a Designer form is an
        ordinary framed window, so the rule would hide the header the instant
        it is dropped — the widget would look broken rather than configurable.
        """
        if not self._auto_hide_with_os_frame or self.is_design_time():
            return
        window = self.window()
        if window is None:
            return
        flags = window.windowFlags()
        is_frameless = bool(flags & QtCore.Qt.FramelessWindowHint)
        if not is_frameless:
            self.hide()
            # The hide is a content-visibility change: on a fully-fixed
            # window the header's row is now pure dead space. End with the
            # same content-max sync the CollapsableGroup toggles use — it
            # snaps the window to the new cap and no-ops when the content is
            # growable. Without it, a geometry-restored window (whose
            # show-time sync ran while the header was still visible) kept a
            # header-high dead band until the next grip press.
            if window.layout() is not None:
                window.layout().activate()  # hints reflect the hidden header
            SizeGripMixin.sync_window_max_to_content(window)

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

        self._follow_window_pin(always=True)

    def _follow_window_pin(self, always: bool = False) -> None:
        """Follow the pin of the window this header sits in (its
        ``on_pinned_changed``), taking its current state.

        :meth:`attach_to` re-targets *always*; a show (``always=False``) only
        picks up a window with the signal that it doesn't follow yet -- a
        ``.ui`` header is laid out, never attached, and otherwise never heard
        of a pin set on its window.
        """
        window = self.window()
        previous = getattr(self, "_pin_signal_source", None)
        if not always and (
            previous is window or not hasattr(window, "on_pinned_changed")
        ):
            return
        # Only disconnect the connection WE made previously (tracked in
        # _pin_signal_source) — blindly disconnecting on a fresh window makes
        # libpyside emit a "Failed to disconnect" RuntimeWarning. The disconnect
        # runs regardless of whether the NEW window has the signal: re-attaching
        # to a signal-less window must not leave the header reacting to the old
        # window's pin toggles.
        if previous is not None:
            try:
                previous.on_pinned_changed.disconnect(self._on_window_pinned_changed)
            except (TypeError, RuntimeError):
                pass  # previous window already deleted / connection gone
            self._pin_signal_source = None
        if hasattr(window, "on_pinned_changed"):
            window.on_pinned_changed.connect(self._on_window_pinned_changed)
            self._pin_signal_source = window

            # Sync initial state from window to header
            if hasattr(window, "pinned") and window.pinned != self.pinned:
                self._set_pin_state(window.pinned)

    def hideEvent(self, event):
        """Reset minimize/collapse state when header (and window) is hidden."""
        self._end_drag_cursor()
        if self._help_card is not None:
            self._help_card.hide()
        if self._minimized:
            self.restore_window()
        elif self._collapsed:
            self.expand_window()
        super().hideEvent(event)

    # -- Qt Designer properties ----------------------------------------------
    # Everything a header is configured with at construction, restated as Qt
    # properties so it is editable in Designer's property editor and stored in
    # the ``.ui`` file. The Python-facing API (``config_buttons()``,
    # ``set_help_text()``, ``pin_on_drag_only``) is unchanged; these delegate to
    # it, so a value set in Designer and one set in a slot take the same path.
    #
    # Each property has a matching ``set<Name>`` method because that is what
    # ``pyside6-uic`` emits for it — a property with only an fset lambda loads
    # fine through QUiLoader and raises AttributeError in a compiled form.

    def setHelpText(self, value: str) -> None:
        """Set the help text (Qt-property setter for :meth:`set_help_text`)."""
        self.set_help_text(value)

    def setPinOnDragOnly(self, value: bool) -> None:
        """Set the pin-click mode (Qt-property setter for the attribute)."""
        self.pin_on_drag_only = value

    def getConfigButtons(self) -> str:
        """Return the configured header buttons as a space-separated string."""
        return " ".join(self.buttons)

    def setConfigButtons(self, value: str) -> None:
        """Configure header buttons from a comma- or space-separated string.

        The list form (:meth:`config_buttons`) can't be typed into a property
        editor, so Designer edits the same thing as text — ``"menu help pin"``.
        """
        names = [name for name in re.split(r"[,\s]+", value or "") if name]
        self.config_buttons(*names)

    def getAutoHideWithOsFrame(self) -> bool:
        """Whether the header hides itself beside a native OS title bar."""
        return self._auto_hide_with_os_frame

    def setAutoHideWithOsFrame(self, value: bool) -> None:
        """Set whether the header hides itself beside a native OS title bar."""
        self._auto_hide_with_os_frame = bool(value)

    # Two deliberate omissions:
    #
    # ``title`` — ``title()`` is an established method, and the inherited
    # ``text`` property already carries the title into the .ui file.
    #
    # ``version`` — a runtime value (every call site is
    # ``header.setVersion(__version__)``), and exposing it would poison that
    # ``text`` round-trip: the version is composed into the painted label, and
    # Designer reads ``text`` through QLabel's C++ getter, so it would save
    # "My Tool <span…>v1.2</span>" back as the title.
    helpText = QtCore.Property(str, fget=help_text, fset=setHelpText)
    configButtons = QtCore.Property(str, fget=getConfigButtons, fset=setConfigButtons)
    pinOnDragOnly = QtCore.Property(
        bool, fget=lambda self: self.pin_on_drag_only, fset=setPinOnDragOnly
    )
    autoHideWithOsFrame = QtCore.Property(
        bool, fget=getAutoHideWithOsFrame, fset=setAutoHideWithOsFrame
    )


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    w = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(w)
    header = Header(
        config_buttons=["menu", "collapse", "minimize", "pin"],
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
