# !/usr/bin/python
# coding=utf-8
"""OptionBox - Plugin-based container for wrapping widgets with action buttons."""

from qtpy import QtWidgets, QtCore

from .options.action import MenuOption, ActionOption
from .options.browse import BrowseOption
from .options.clear import ClearOption
from .options.reset import ResetOption
from .options.pin_values import PinValuesOption
from .options.recent_values import RecentValuesOption
from .options.toggle import ToggleOption
from .options.disable import DisableOption
from .options.filter import FilterOption
from .options.value import ValueOption
from .options.affix import AffixOption

# Concrete option type -> grouping key, consulted by OptionBox._sort_options.
# Built once at import; was previously rebuilt (with 7 local imports) on every
# wrap() / _rebuild_layout() call. The option modules never import _optionBox,
# so these top-level imports introduce no cycle.
_TYPE_TO_KEY = {
    ValueOption: "value",
    # Inline mode picker; sits next to the value field, ahead of icon buttons.
    AffixOption: "affix",
    ClearOption: "clear",
    RecentValuesOption: "recent",
    PinValuesOption: "pin",
    ResetOption: "reset",
    # ToggleOption and DisableOption are *leaf* classes (no subclasses) sharing
    # a BinaryToggleOption base. Both are keyed here directly rather than via the
    # base: isinstance() against a class that HAS subclasses triggers CPython's
    # ABCMeta __subclasses__() recursion, which cross-contaminates the abc
    # caches of these QObject/ABCMeta options. Keying off the leaves avoids it.
    ToggleOption: "toggle",
    DisableOption: "toggle",
    # FilterOption is a third leaf sibling on BinaryToggleOption (its on/off
    # button is itself a toggle). Keyed off the leaf for the same ABCMeta-cache
    # reason as ToggleOption/DisableOption. Its sibling scope ActionOption sorts
    # as "action", so the scope button naturally follows the filter toggle.
    FilterOption: "toggle",
    BrowseOption: "browse",
}


# Shared repolish primitive — see its docstring for the stale property-
# selector mechanism this package measures around.
from uitk.themes.style_sheet import repolish_tree as _repolish_tree


class OptionBoxContainer(QtWidgets.QWidget):
    """Container widget that wraps a widget with option buttons.

    Styled via style.qss rule: `OptionBoxContainer { ... }`.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        if not self.objectName():
            self.setObjectName("optionBoxContainer")
        self.setProperty("class", "withBorder")
        # Mirrors the effective enabled state of the wrapped widget so QSS
        # can suppress :hover highlighting when the row is disabled. Synced
        # by _sync_option_buttons_enabled; initialized true for the pre-wrap
        # window before the first sync runs.
        self.setProperty("wrappedEnabled", "true")
        # The wrapped widget's authored center (parent coords) and width,
        # captured by OptionBox.wrap for an absolute-positioned container.
        # Every content re-fit re-centers on the anchor, not on the
        # container's current geometry — the container starts life at Qt's
        # default widget size, so its current center is offset from the
        # widget it replaced, and preserving it drifted the wrapped button
        # off its .ui position. The authored width feeds the seam-overlap
        # calculation (OptionBox._seam_overlap). None/0 for layout-managed
        # containers (the parent layout owns geometry) and for containers
        # built outside wrap().
        self._anchor_center = None
        self._authored_width = 0

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.EnabledChange:
            self._sync_option_buttons_enabled()

    def showEvent(self, event):
        """Re-fit to content when shown without a managing parent layout.

        In a layout (e.g. a docked panel) the parent owns this container's
        size — leave it alone. But in an absolute-positioned context (the
        marking-menu overlay), the wrapped widget can have been sized from a
        *pre-polish* size hint — before the theme QSS collapsed it — and that
        inflated geometry then freezes, leaving the option-box button far wider
        than its text (the option-box square pushed away from the label). The
        symptom is host-specific: styles whose un-polished button minimum is
        already tight (e.g. Maya's) never inflate, while Windows' native style
        does. Deferring one tick lets the QSS settle, then we re-fit to the
        now-correct hint and keep the container centered where it was placed.
        """
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None and parent.layout() is not None:
            return  # layout-managed — sizing is the parent's responsibility
        # Safety net, CONDITIONAL: schedule the one-tick refit only when the
        # current geometry differs from the content fit. Since wrap() now
        # repolishes before measuring, the routine case is already final at
        # show — scheduling an unconditional post-show adjustSize+move here
        # was a visible correction (the init flash) whenever the wrap-time
        # measurement had been stale, and a wasted timer when it hadn't.
        # A genuinely wrong size (host style resolved QSS later than wrap,
        # or an externally perturbed container) still schedules and corrects.
        if self._content_fit_pending():
            QtCore.QTimer.singleShot(0, self._adjust_to_content)

    def _content_fit_pending(self) -> bool:
        """True when a content re-fit would actually change geometry.

        Mirrors what :meth:`_adjust_to_content` would do — ``adjustSize`` to
        the (activated) layout hint, re-centered on the anchor — without
        performing it. Kept cheap: one layout activation + hint read.
        """
        layout = self.layout()
        if layout is None:
            return False
        layout.activate()
        hint = self.sizeHint()
        if hint.isValid() and hint != self.size():
            return True
        anchor = self._anchor_center
        if anchor is not None:
            target = QtCore.QPoint(
                anchor.x() - hint.width() // 2, anchor.y() - hint.height() // 2
            )
            if target != self.pos():
                return True
        return False

    def _adjust_to_content(self):
        """Fit a *self-positioned* container to its content, centered on the
        wrapped widget's authored position.

        Only an absolute-positioned container (the marking-menu overlay) is
        resized here: ``adjustSize`` collapses it to the content hint, then the
        container is re-centered on ``_anchor_center`` — the wrapped widget's
        .ui-authored center captured at wrap time — so a re-fit (first show, or
        a later height change routed through ``_update_sizing``) always lands
        the row where the Designer placed the widget. Falling back to the
        container's *current* center (pre-anchor behavior) is kept only for
        containers built outside ``wrap()``: the container starts life at Qt's
        default widget size, so its current center sits offset from the widget
        it replaced and preserving it drifted the wrapped button off its .ui
        position by half that size delta.

        A **layout-managed** container is left untouched: its parent layout owns
        its width and position, so calling ``adjustSize`` here would fight the
        layout and leave the field short of the cell edge. Both the show-time
        refit and the post-wrap resizing share this method, so the rule lives in
        one place.
        """
        try:
            parent = self.parentWidget()
            if parent is not None and parent.layout() is not None:
                return  # layout-managed — parent owns geometry; don't fight it
            layout = self.layout()
            if layout is None:
                return
            layout.activate()
            # Explicit None check: a QPoint at the origin must not be treated
            # as "no anchor".
            anchor = self._anchor_center
            center = anchor if anchor is not None else self.geometry().center()
            self.adjustSize()
            new = self.size()
            target = QtCore.QPoint(
                center.x() - new.width() // 2, center.y() - new.height() // 2
            )
            # No-op guard: a refit that lands exactly where the container
            # already sits must not issue a move (Qt would still process it).
            if target != self.pos():
                self.move(target)
        except RuntimeError:
            pass  # underlying C++ object already deleted

    def eventFilter(self, obj, event):
        """Watch the wrapped widget for enabled-state and height changes."""
        etype = event.type()
        if etype == QtCore.QEvent.EnabledChange:
            self._sync_option_buttons_enabled()
        elif etype == QtCore.QEvent.Resize:
            # Re-square the option buttons to the wrapped widget's new height so
            # they track a height change applied *after* wrap (e.g. a later
            # ``setFixedHeight`` on the wrapped combo). Only on an actual height
            # change — width-only resizes leave the square buttons untouched, and
            # re-fitting their icons on every resize would be wasteful.
            if event.oldSize().height() != event.size().height():
                mgr = getattr(self, "_option_box", None)
                if mgr is not None:
                    mgr._update_sizing()
        return super().eventFilter(obj, event)

    def _sync_option_buttons_enabled(self):
        """Sync option button enabled state with the wrapped widget."""
        layout = self.layout()
        if not layout or layout.count() < 2:
            return
        wrapped = layout.itemAt(0).widget()
        if not wrapped:
            return
        enabled = wrapped.isEnabled() and self.isEnabled()
        prop_val = "true" if enabled else "false"
        if self.property("wrappedEnabled") != prop_val:
            self.setProperty("wrappedEnabled", prop_val)
            self.style().unpolish(self)
            self.style().polish(self)
        for i in range(1, layout.count()):
            btn = layout.itemAt(i).widget()
            if not btn:
                continue
            # An option may opt out of cascade-disabling — e.g. the
            # ResetOption's bypass toggle, which greys out the wrapped widget
            # itself and so must stay clickable for the user to restore it.
            if btn.property("keepEnabledWhenWrappedDisabled"):
                continue
            btn.setEnabled(enabled)


class OptionBox:
    """Plugin-based option manager that wraps widgets with action buttons.

    Wraps any widget in an OptionBoxContainer with optional action buttons
    (clear, pin, menu, etc.) provided by the plugin system. Each plugin
    creates its own button widget.

    This class is NOT a widget itself - it only manages the container and plugins.
    """

    def __init__(
        self,
        show_clear=False,
        options=None,
        option_order=None,
    ):
        self._show_clear_button = show_clear
        self._options = []
        self._option_order = option_order or [
            # The inline value field sits flush against the wrapped widget,
            # ahead of the icon buttons.
            "value",
            "affix",
            "clear",
            "recent",
            "pin",
            "reset",
            "toggle",
            "action",
            "browse",
            "menu",
        ]
        self.wrapped_widget = None
        self.container = None

        # Register options if provided
        if options:
            for option in options:
                self.add_option(option)

    # ------------------------------------------------------------------
    # Option plugin management
    # ------------------------------------------------------------------

    def add_option(self, option):
        """Add an option plugin instance.

        Args:
            option: An option plugin instance (must have a widget property)
        """
        if option not in self._options:
            self._options.append(option)
            if self.container:
                self._rebuild_layout()

    def remove_option(self, option):
        """Remove an option plugin instance."""
        if option in self._options:
            self._options.remove(option)
            if self.container:
                self._rebuild_layout()

    def get_options(self):
        """Get all registered option plugins."""
        return list(self._options)

    def set_option_order(self, order):
        """Update the sort order and re-lay-out existing options in place.

        Only the left-to-right ordering changes — every registered option is
        preserved. This is the non-destructive counterpart to recreating the
        box (which would drop all options).
        """
        self._option_order = list(order)
        if self.container:
            self._rebuild_layout()

    # Fraction of the wrapped button's perceived side padding that the adjacent
    # option square overlaps at the seam (see _seam_overlap). The button centers
    # its text, so the padding is (authored_width - text_width) / 2 per side;
    # overlapping this fraction of it leaves (1 - fraction) of the normal padding
    # at the text-to-option seam, without touching the theme QSS. 0.75 keeps a
    # quarter of the padding — half the gap of the initial 0.5 tuning.
    _SEAM_OVERLAP_FRACTION = 0.75

    def _seam_overlap(self, container, first_option) -> int:
        """Pixels the first option button tucks in over the wrapped button's edge.

        The wrapped button centers its text, so its authored width leaves the
        same padding on both sides. Butting an option square straight onto that
        edge reads too airy — the text-to-option seam gets the FULL side
        padding. The intended look is a FRACTION of the normal padding at the
        seam (``_SEAM_OVERLAP_FRACTION``; outer side unchanged), without touching
        the theme's padding QSS. The adjacent option therefore overlaps the
        button edge by that fraction of the perceived padding, expressed as a
        *negative layout spacer* so the layout itself owns the overlap — a
        manual ``move()`` nudge would be undone on every re-layout, and the
        container's size hint shrinks with it automatically. Option widgets are
        added after the wrapped widget, so they stack on top across the overlap
        strip. Were an option ever placed on the LEFT of the wrapped widget, the
        same spacer would apply at that seam (today all options sit to the right).

        Applies only where the seam is button-like and the geometry stable:
        an anchored absolute wrap (authored .ui width — a layout-managed
        width stretches, making "padding" meaningless), a text QPushButton
        host (centered label), and a square icon button as the adjacent
        option (a ValueOption field keeps its flush seam). Returns 0
        otherwise, including when the text already fills the authored width.
        """
        if container is None or container._anchor_center is None:
            return 0
        if not getattr(first_option, "square", True):
            return 0
        w = self.wrapped_widget
        if not isinstance(w, QtWidgets.QPushButton) or not w.text():
            return 0
        text_w = w.fontMetrics().horizontalAdvance(w.text())
        pad = (container._authored_width - text_w) // 2
        return max(0, round(pad * self._SEAM_OVERLAP_FRACTION))

    def _add_option_widget(self, layout, container, option, is_first):
        """Parent, wire, and add *option*'s widget to *layout*, returning it.

        The first option also gets the negative seam spacer inserted before it
        (see :meth:`_seam_overlap`, which tucks it over the button edge by a
        fraction of the perceived padding) — kept as a layout item so a re-fit
        preserves it. Shared by :meth:`_rebuild_layout` and :meth:`wrap`.
        """
        widget = option.widget
        widget.setParent(container)
        self._wire_option_widget(widget, option, container)
        if is_first:
            overlap = self._seam_overlap(container, option)
            if overlap:
                layout.addSpacing(-overlap)
        layout.addWidget(widget)
        return widget

    def _rebuild_layout(self):
        """Rebuild the layout with all current options."""
        if not self.container or not self.wrapped_widget:
            return

        layout = self.container.layout()

        # Clear all widgets except the wrapped widget (drops any seam spacer
        # too — it is re-inserted with the first option below)
        while layout.count() > 1:
            item = layout.takeAt(1)
            if item.widget():
                item.widget().setParent(None)

        # Sort and add option widgets
        sorted_options = self._sort_options()
        first = True
        for option in sorted_options:
            if hasattr(option, "widget"):
                self._add_option_widget(layout, self.container, option, first)
                first = False

        self._update_sizing()
        self.container._sync_option_buttons_enabled()

    def _sort_options(self):
        """Sort options based on explicit order or type-based option_order.

        Options with an explicit ``order`` attribute (int) are sorted by that
        value first.  Options without one fall back to the type-based grouping
        defined by ``_option_order``.  Stable sort preserves insertion order
        among options that share the same priority.

        The default order places menu buttons after action buttons so the
        option-box dropdown is always the rightmost control.
        """
        _fallback = len(self._option_order)

        def _type_priority(option):
            for cls, key in _TYPE_TO_KEY.items():
                if isinstance(option, cls):
                    try:
                        return self._option_order.index(key)
                    except ValueError:
                        return _fallback
            # MenuOption (subclass of ActionOption) gets its own slot so
            # the dropdown menu always appears after action buttons.
            if isinstance(option, MenuOption):
                key = "menu" if "menu" in self._option_order else "action"
                try:
                    return self._option_order.index(key)
                except ValueError:
                    return _fallback
            if isinstance(option, ActionOption):
                try:
                    return self._option_order.index("action")
                except ValueError:
                    return _fallback
            return _fallback + 1

        def get_priority(option):
            explicit = getattr(option, "order", None)
            if explicit is not None:
                return (0, explicit)
            return (1, _type_priority(option))

        return sorted(self._options, key=get_priority)

    # Pixel padding subtracted from the host height to size option-button
    # icons. 6 px leaves more breathing room than the table's default
    # margin (4) because option-boxes sit flush against text-edit borders
    # and benefit from a quieter glyph.
    _ICON_MARGIN = 6

    def _update_sizing(self):
        """Update sizing for all option widgets.

        Each option button is forced to a height-square (h x h). Icons are
        re-rendered via :meth:`IconManager.fit_icon` so the SVG rasterizes
        crisply at the displayed size (instead of being scaled down from a
        fixed placeholder).
        """
        if not self.wrapped_widget:
            return
        from uitk.managers.icon_manager import IconManager

        h = self.wrapped_widget.height() or self.wrapped_widget.sizeHint().height()
        for option in self._options:
            if not hasattr(option, "widget"):
                continue
            w = option.widget
            # Most options are icon buttons forced to an h x h square. A
            # non-square option (e.g. ValueOption's editable field) keeps its
            # own width and is only height-matched to the row.
            if getattr(option, "square", True):
                w.setFixedSize(h, h)
            else:
                w.setFixedHeight(h)
            if not hasattr(w, "setIcon"):
                continue
            # Use whatever icon name/color IconManager has on record (handles
            # state-cycling ActionOptions that swapped the icon after
            # creation — a pinned state color must survive the re-fit);
            # fall back to the option's initial icon.
            info = IconManager.registered_info(w)
            icon_name = info["name"] if info else getattr(option, "icon", None)
            pinned = info.get("color") if info else None
            if icon_name:
                IconManager.fit_icon(
                    w,
                    icon_name,
                    h,
                    margin=self._ICON_MARGIN,
                    color=pinned,
                    auto_theme=pinned is None,
                )
            elif not w.icon().isNull():
                extent = IconManager.fit_size(h, margin=self._ICON_MARGIN)
                w.setIconSize(QtCore.QSize(extent, extent))
        if self.container:
            # Center-preserving so re-squaring on a post-wrap height change
            # doesn't drift an absolute-positioned (overlay) container left.
            self.container._adjust_to_content()

    def _assign_option_object_name(self, option_widget, option):
        """Ensure option widgets have stable, descriptive object names."""
        if option_widget is None:
            return

        parent_name = "optionHost"
        if self.wrapped_widget is not None:
            parent_name = (
                self.wrapped_widget.objectName()
                or self.wrapped_widget.__class__.__name__
            )

        option_type = option.__class__.__name__ if option is not None else "Option"
        option_widget.setObjectName(f"{parent_name}_{option_type}")

    def _propagate_option_context(self, option_widget):
        """Copy contextual attributes from the wrapped widget to option widgets."""
        if option_widget is None or not self.wrapped_widget:
            return

        host = self.wrapped_widget

        # Provide UI + Switchboard references when available
        for attr in ("ui", "sb"):
            if hasattr(host, attr):
                setattr(option_widget, attr, getattr(host, attr, None))

        # Mirror helper lambdas that the main window injects
        if hasattr(host, "base_name"):
            option_widget.base_name = host.base_name
        else:
            option_widget.base_name = lambda: option_widget.objectName()

        if hasattr(host, "legal_name"):
            option_widget.legal_name = host.legal_name
        else:
            option_widget.legal_name = lambda: option_widget.objectName()

        # Allow downstream code to find the originating widget if needed
        option_widget.option_host = host

    def _wire_option_widget(self, option_widget, option, container):
        """Wire up an option widget with naming, context, and callbacks."""
        if option_widget is None:
            return

        self._assign_option_object_name(option_widget, option)
        self._propagate_option_context(option_widget)

        if hasattr(option, "on_wrap"):
            option.on_wrap(self, container)

    # ------------------------------------------------------------------
    # Clear button helpers
    # ------------------------------------------------------------------

    @property
    def show_clear(self):
        """Get clear button state."""
        return self._show_clear_button

    @show_clear.setter
    def show_clear(self, value):
        """Set clear button visibility."""
        self._show_clear_button = value
        from .options.clear import ClearOption

        for option in self._options:
            if isinstance(option, ClearOption):
                # Honor an explicit disable so it STICKS. The ClearOption's own
                # textChanged handler (_update_visibility) re-shows the button
                # on the next edit, so a bare setVisible(False) is undone by the
                # very next keystroke. Gate that auto-show by toggling the
                # option's _auto_hide (its _update_visibility early-returns when
                # auto_hide is off), then set the final visibility: hidden while
                # disabled, text-driven once re-enabled.
                option._auto_hide = bool(value)
                if value:
                    option._update_visibility()
                else:
                    w = option.widget
                    if w is not None:
                        w.setVisible(False)
                return

        # Self-heal when show_clear is enabled after wrap (e.g. `.menu.add(...)`
        # then `.clear_option = True` — the synchronous wrap has already run).
        if value and self.wrapped_widget and self._is_text_widget(self.wrapped_widget):
            clear_option = ClearOption(self.wrapped_widget)
            clear_option.set_wrapped_widget(self.wrapped_widget)
            self.add_option(clear_option)

    def set_clear_button_visible(self, visible=True):
        """Enable or disable the clear button."""
        self.show_clear = visible

    def _is_text_widget(self, widget):
        """Check if the widget can benefit from a clear button."""
        text_widget_types = (
            QtWidgets.QLineEdit,
            QtWidgets.QTextEdit,
            QtWidgets.QPlainTextEdit,
            QtWidgets.QSpinBox,
            QtWidgets.QDoubleSpinBox,
            QtWidgets.QComboBox,
        )
        return isinstance(widget, text_widget_types)

    # ------------------------------------------------------------------
    # Wrapping
    # ------------------------------------------------------------------

    def wrap(self, wrapped_widget: QtWidgets.QWidget, frameless=False):
        """Wrap target widget with option buttons.

        Args:
            wrapped_widget: The widget to wrap
            frameless: If True, the container will not have a border.

        Returns:
            OptionBoxContainer: The container holding the widget and buttons
        """
        self.wrapped_widget = wrapped_widget
        parent = wrapped_widget.parent()
        # Suppress repaints for the whole wrap. Normally the immediate parent
        # suffices (the fast path wraps pre-paint, inside register_children).
        # But the slow-path retry (OptionBoxManager._attempt_wrap_when_ready)
        # can wrap a widget whose window is ALREADY VISIBLE — the reparent
        # swap (replaceWidget/addWidget) then flickers unless the suppression
        # covers the top-level window: one repaint replaces several.
        suppress_root = parent
        if parent is not None:
            window = wrapped_widget.window()
            if window is not None and window.isVisible():
                suppress_root = window
        prev_updates = suppress_root.updatesEnabled() if suppress_root else True

        if suppress_root:
            suppress_root.setUpdatesEnabled(False)

        try:
            # Create container
            container = OptionBoxContainer(parent)
            if frameless:
                container.setProperty("class", "frameless")
                # Apply direct inline style for frameless - no selector needed
                container.setStyleSheet(
                    "border: none; background: transparent; margin: 0px; padding: 0px;"
                )

            # The container stands in for the wrapped widget in its parent
            # layout, so it must size the same way: inherit the wrapped widget's
            # size policy in both axes. An Expanding LineEdit that filled its cell
            # would otherwise become a Preferred container that sits at content
            # width and no longer reaches the cell edge — and likewise an
            # Expanding QTextEdit would stop filling vertically. Only the policy
            # types are mirrored (the container keeps its own control type).
            wrapped_policy = wrapped_widget.sizePolicy()
            policy = container.sizePolicy()
            policy.setHorizontalPolicy(wrapped_policy.horizontalPolicy())
            policy.setVerticalPolicy(wrapped_policy.verticalPolicy())
            container.setSizePolicy(policy)

            # Replace original widget in parent layout
            if parent and parent.layout():
                parent.layout().replaceWidget(wrapped_widget, container)
            else:
                authored = wrapped_widget.geometry()
                container.move(authored.topLeft())
                container.resize(authored.size())
                # Absolute-positioned (the marking-menu overlay): the container
                # stands in at the wrapped widget's authored spot. Capture the
                # authored geometry BEFORE the layout below reparents/resizes
                # the widget:
                # - the CENTER anchors every content re-fit
                #   (see OptionBoxContainer._adjust_to_content) so the row
                #   stays centered on the .ui position;
                # - the WIDTH becomes the wrapped widget's minimum so the
                #   layout's collapse-to-hint never crushes a Designer-padded
                #   label to its bare text hint (text jammed against the
                #   edges). The content fit is a floor, not a ceiling: a hint
                #   wider than the authored width still wins.
                # Only for a PARENTED widget — there the geometry is authored
                # placement. A parentless wrap's geometry is just Qt's default
                # (100x30): anchoring or flooring on it would pin a meaningless
                # position/minimum onto a widget that hasn't been placed yet.
                # Layout-managed wraps get neither — the parent layout owns
                # geometry there.
                if parent is not None:
                    container._anchor_center = authored.center()
                    container._authored_width = authored.width()
                    if authored.width() > wrapped_widget.minimumWidth():
                        wrapped_widget.setMinimumWidth(authored.width())

            # Create layout
            layout = QtWidgets.QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(wrapped_widget)

            # Add clear option if needed
            if self._show_clear_button and self._is_text_widget(wrapped_widget):
                from .options.clear import ClearOption

                self.add_option(ClearOption(wrapped_widget))

            # Sort and add option widgets
            sorted_options = self._sort_options()
            option_widgets = []
            for option in sorted_options:
                if hasattr(option, "set_wrapped_widget"):
                    option.set_wrapped_widget(wrapped_widget)

                if hasattr(option, "widget"):
                    widget = self._add_option_widget(
                        layout, container, option, not option_widgets
                    )
                    option_widgets.append(widget)

            # Apply border styling
            self._apply_border_styling(wrapped_widget, option_widgets)

            # Re-evaluate property-selector QSS BEFORE measuring. Dynamic-
            # property rules ([class="..."]) stamped after a widget's first
            # polish stay un-applied until an unpolish/polish cycle, so the
            # height/size reads below (and _update_sizing's square fit) would
            # otherwise measure the pre-stamp metrics — geometry then freezes
            # wrong (or a post-show refit visibly corrects it: the init
            # flash). On hosts whose Qt resolves the border-trim setStyleSheet
            # above eagerly this is nearly free (already resolved); on hosts
            # that resolve lazily it is load-bearing (the Blender ~80px
            # CT_PushButton inflation).
            _repolish_tree(container)

            # Finalize
            h = wrapped_widget.height() or wrapped_widget.sizeHint().height()
            wrapped_widget.setMinimumHeight(h)
            self.container = container
            # Back-reference so the container's event filter can re-square the
            # option buttons when the wrapped widget's height changes later.
            container._option_box = self
            # Render icons at their display size now that final geometry is known.
            self._update_sizing()
            # Propagate wrapped widget disabled state + height changes to the
            # option buttons.
            wrapped_widget.installEventFilter(container)
            container._sync_option_buttons_enabled()
            container.show()
        finally:
            if suppress_root:
                suppress_root.setUpdatesEnabled(prev_updates)

        return container

    # Border-trim fragments that collapse the seam between the wrapped widget
    # and its option buttons. Appended idempotently (see _append_style_once):
    # re-wrapping a widget (remove() then re-create) would otherwise accumulate
    # duplicate fragments on its styleSheet, and each redundant setStyleSheet
    # forces a style re-polish.
    _TRIM_HOST = "border-right-width: 0px; border-right-style: none;"
    _TRIM_FIRST = (
        "border-left-width: 0px; border-left-style: none; "
        "border-left-color: transparent;"
    )
    _TRIM_MID = (
        "border-right-width: 0px; border-right-style: none; "
        "border-right-color: transparent;"
    )

    @staticmethod
    def _append_style_once(widget, fragment):
        """Append *fragment* to *widget*'s styleSheet only if not already present."""
        existing = widget.styleSheet()
        if fragment in existing:
            return
        widget.setStyleSheet(f"{existing}; {fragment}" if existing else fragment)

    def _apply_border_styling(self, wrapped_widget, option_widgets=None):
        """Apply border styling to prevent double borders."""
        self._append_style_once(wrapped_widget, self._TRIM_HOST)

        if option_widgets:
            # Remove left border from the first option widget.
            self._append_style_once(option_widgets[0], self._TRIM_FIRST)
            # Remove right border from all except the last.
            for widget in option_widgets[:-1]:
                self._append_style_once(widget, self._TRIM_MID)
