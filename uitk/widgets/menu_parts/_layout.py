# !/usr/bin/python
# coding=utf-8
"""The menu's frame: its layouts, central widget, header / footer chrome and size.

The scaffold (a translucent outer layout, a bordered frame, a central widget
holding the item grid) is built at construction; the Header and Footer -- the
heaviest part of a menu, and most option-box menus are never opened -- are
built on first show. ``sizeHint`` sums the frame's children and refreshes the
nested layouts while the menu is hidden, so a menu sized before it is shown is
sized to its real content.

One part of :class:`~uitk.widgets.menu.Menu` (see ``menu_parts``).
"""

from typing import TYPE_CHECKING, Optional

from qtpy import QtCore, QtWidgets

from uitk.themes.style_sheet import StyleSheet
from uitk.widgets._layout_items import _LayoutItems
from uitk.widgets.footer import Footer
from uitk.widgets.header import Header

if TYPE_CHECKING:
    from uitk.widgets.menu import Menu


class _MenuFrame:
    """A :class:`Menu`'s frame: its layouts, central widget, chrome and size.

    Owns the private layout handles and the title stashed before the header
    exists; the public handles (``gridLayout``, ``centralWidgetLayout``,
    ``header``, ``footer``, ``style``) stay attributes of the menu it holds.
    """

    def __init__(self, menu: "Menu") -> None:
        self._menu = menu
        self.layout: Optional[QtWidgets.QVBoxLayout] = None
        self.frame: Optional[QtWidgets.QFrame] = None
        self.frame_layout: Optional[QtWidgets.QVBoxLayout] = None
        self.central_widget: Optional[QtWidgets.QWidget] = None
        self.pending_title: Optional[str] = None
        # Re-entrancy guard for the sizeHint activation (activate_inner_layouts).
        self.activating_chain = False

    def ensure_layout_created(self):
        """Ensure layout is created (called when first item is added)."""
        menu = self._menu
        if self.layout is None or menu.gridLayout is None:
            menu.init_layout()
            menu.logger.debug("Menu._ensure_layout_created: Layout created")

    def ensure_style_initialized(self):
        """Ensure stylesheet is initialized (called on first show)."""
        menu = self._menu
        if menu.style is None:
            menu.style = StyleSheet(menu, log_level="WARNING")
            menu.logger.debug("Menu._ensure_style_initialized: StyleSheet created")

    def set_central_widget(self, widget, overwrite=False):
        if not overwrite and self.central_widget is widget:
            return  # skip if same

        current_central_widget = self.central_widget
        if current_central_widget and current_central_widget is not widget:
            current_central_widget.setParent(None)  # Avoid deleteLater()

        self.central_widget = widget
        self.central_widget.setProperty("class", "centralWidget")
        self.layout.addWidget(self.central_widget)

    def init_layout(self):
        # Guard against double initialization
        if self.layout is not None:
            return
        menu = self._menu

        # CRITICAL OPTIMIZATION: Disable updates AND layout calculation
        updates_were_enabled = menu.updatesEnabled()
        menu.setUpdatesEnabled(False)

        # Also block signals to prevent event propagation during setup
        was_blocked = menu.blockSignals(True)

        try:
            # Create outer layout for the translucent window (margins for frame border)
            self.layout = QtWidgets.QVBoxLayout(menu)
            # Provide a 2px transparent gutter so translucent borders never touch window edges
            self.layout.setContentsMargins(2, 2, 2, 2)
            self.layout.setSpacing(0)
            self.layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
            menu.setLayout(self.layout)

            # Create frame container that will have the border
            self.frame = QtWidgets.QFrame(menu)
            self.frame.setObjectName("menuFrame")
            self.frame.setProperty("class", "translucentBgWithBorder")
            self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
            self.frame.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
            )
            self.layout.addWidget(self.frame)

            # Create inner layout inside the frame (with spacing for border).
            # Kept so the deferred chrome (ensure_chrome) can insert into it on show.
            self.frame_layout = QtWidgets.QVBoxLayout(self.frame)
            frame_layout = self.frame_layout
            # One extra pixel inside the frame keeps children off the painted border
            frame_layout.setContentsMargins(1, 1, 1, 1)
            frame_layout.setSpacing(1)
            frame_layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

            # Header is deferred to first show — see ensure_chrome().

            # Create a central widget WITHOUT parent first to avoid tree overhead
            # Parent will be assigned when added to layout
            central_widget = QtWidgets.QWidget()
            menu.setCentralWidget(central_widget)

            # Create a QVBoxLayout inside the central widget
            menu.centralWidgetLayout = QtWidgets.QVBoxLayout(self.central_widget)
            menu.centralWidgetLayout.setContentsMargins(2, 1, 2, 1)
            menu.centralWidgetLayout.setSpacing(1)
            menu.centralWidgetLayout.setSizeConstraint(
                QtWidgets.QLayout.SetNoConstraint
            )

            # Create a form layout inside the QVBoxLayout
            menu.gridLayout = QtWidgets.QGridLayout()
            menu.gridLayout.setContentsMargins(0, 0, 0, 0)
            menu.gridLayout.setSpacing(1)
            menu.gridLayout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

            # Add grid layout to the central widget layout
            menu.centralWidgetLayout.addLayout(menu.gridLayout)

            # Push items to the top so extra vertical space stays at the bottom
            menu.centralWidgetLayout.addStretch(1)

            # Add central widget to frame layout
            frame_layout.addWidget(self.central_widget)

            # Footer is deferred to first show — see ensure_chrome().

        finally:
            # Restore signal blocking state
            menu.blockSignals(was_blocked)

            # Re-enable updates after layout creation
            if updates_were_enabled:
                menu.setUpdatesEnabled(True)

            # Activate layout now that setup is complete
            if self.layout:
                self.layout.activate()

    def ensure_chrome(self):
        """Build the deferred chrome (Header + Footer) on first show.
        Idempotent — guarded per sub-widget, safe to call repeatedly.

        Header/Footer are the heaviest part of a Menu and most option-box menus
        are never opened, so they are built here — right before paint, via
        ``_prepare_for_show`` — instead of eagerly during ``register_children``.
        """
        menu = self._menu
        if self.frame_layout is None:
            menu._ensure_layout_created()
        fl = self.frame_layout
        if fl is None:
            return

        if menu.add_header and menu.header is None:
            menu.header = Header(config_buttons=["pin"])
            fl.insertWidget(0, menu.header)  # ABOVE the central widget
            if self.pending_title is not None:
                menu.header.setText(self.pending_title)
                self.pending_title = None

        if menu.add_footer and menu.footer is None:
            menu.footer = Footer(add_size_grip=True)
            fl.addWidget(menu.footer)  # LAST → below the central widget

    def resize_height_to_content(self) -> None:
        """Collapse stale vertical space before showing the menu again.

        Menus are often rebuilt while hidden. Without explicitly syncing the
        geometry, Qt can reuse the previous height, leaving an empty gap when
        fewer items remain. Keeping the width untouched avoids fighting the
        width-matching logic while still trimming vertical dead space.
        """
        if not self.layout:
            return
        menu = self._menu

        self.layout.activate()
        hint = menu.sizeHint()
        if not hint.isValid():
            return

        target_height = max(hint.height(), menu.minimumHeight())
        current_width = menu.width() or max(hint.width(), menu.minimumWidth())

        if menu.height() != target_height:
            menu.resize(current_width, target_height)

    def title(self) -> str:
        menu = self._menu
        if menu.header is not None:
            return menu.header.text()
        return self.pending_title or ""

    def set_title(self, title="") -> None:
        menu = self._menu
        if menu.header is not None:
            menu.header.setText(title)
        else:
            # Chrome is deferred to first show; stash and apply when it builds.
            self.pending_title = title

    def activate_inner_layouts(self) -> None:
        """Synchronously recompute the nested layout sizeHints.

        ``add()`` skips ``layout.activate()`` while the menu is invisible (Qt
        re-activates before paint, so the work is wasted for an off-screen
        widget — see the bulk-add note in ``add()``).  The side effect is that
        the *inner* QBoxLayouts (``centralWidgetLayout`` and the frame layout)
        keep a cached sizeHint from when they were empty — collapsed to just
        their margins.  ``invalidate()`` only posts a deferred
        ``LayoutRequest`` that never gets processed while invisible, and
        :meth:`size_hint` reads the frame's sizeHint directly, bypassing the
        grid's own (correct) recompute.  The net result: ``adjustSize()`` on a
        freshly-populated, not-yet-shown menu sizes it to the minimum width,
        clipping content (e.g. the RecentValues / PinnedValues popups, which
        size-then-show).

        Forcing a synchronous ``activate()`` on the inner chain refreshes
        those cached hints.  The outer layout is intentionally left alone — Qt
        drives its activation and may already be mid-pass.  Only needed while
        invisible; once shown Qt drains the pending ``LayoutRequest`` and the
        hints stay current on their own.
        """
        if self.activating_chain:
            return
        self.activating_chain = True
        try:
            central_layout = self._menu.centralWidgetLayout
            if central_layout is not None:
                central_layout.activate()
            frame = self.frame
            if frame is not None and frame.layout() is not None:
                frame.layout().activate()
        finally:
            self.activating_chain = False

    def size_hint(self) -> QtCore.QSize:
        """The menu's sizeHint once its layout exists (see :meth:`Menu.sizeHint`)."""
        # While invisible the nested layouts hold a stale (collapsed) cached
        # sizeHint; refresh them so adjustSize()/width-matching see the real
        # content width. Once shown, Qt keeps them current — skip the work.
        if not self._menu.isVisible():
            self.activate_inner_layouts()

        layout = self.layout
        total_height = 0
        total_width = 0

        for widget in _LayoutItems.widgets(layout):
            total_height += widget.sizeHint().height() + layout.spacing()
            total_width = max(total_width, widget.sizeHint().width())

        # Adjust for layout's top and bottom margins
        total_height += (
            layout.contentsMargins().top() + layout.contentsMargins().bottom()
        )
        # Adjust for layout's left and right margins for width
        total_width += (
            layout.contentsMargins().left() + layout.contentsMargins().right()
        )

        return QtCore.QSize(total_width, total_height)
