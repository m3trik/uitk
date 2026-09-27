# !/usr/bin/python
# coding=utf-8
"""The menu's frame: its layouts, central widget, header / footer chrome and size.

The scaffold (a translucent outer layout, a bordered frame, a central widget
holding the item grid) is built at construction; the Header and Footer -- the
heaviest part of a menu, and most option-box menus are never opened -- are
built on first show. ``sizeHint`` sums the frame's children and refreshes the
nested layouts while the menu is hidden, so a menu sized before it is shown is
sized to its real content.

One part of :class:`~uitk.widgets.menu.Menu`, which inherits it; it holds no
state of its own (``Menu.__init__`` declares every attribute used here) and
is never instantiated alone.
"""

from qtpy import QtCore, QtWidgets

from uitk.themes.style_sheet import StyleSheet
from uitk.widgets.footer import Footer
from uitk.widgets.header import Header


class _MenuLayoutMixin:
    """The menu's frame: its layouts, central widget, header / footer chrome and size."""

    def _ensure_layout_created(self):
        """Ensure layout is created (called when first item is added)."""
        if self._layout is None or self.gridLayout is None:
            self.init_layout()
            self.logger.debug("Menu._ensure_layout_created: Layout created")

    def _ensure_style_initialized(self):
        """Ensure stylesheet is initialized (called on first show)."""
        if self.style is None:
            self.style = StyleSheet(self, log_level="WARNING")
            self.logger.debug("Menu._ensure_style_initialized: StyleSheet created")

    def setCentralWidget(self, widget, overwrite=False):
        if not overwrite and getattr(self, "_central_widget", None) is widget:
            return  # skip if same

        current_central_widget = getattr(self, "_central_widget", None)
        if current_central_widget and current_central_widget is not widget:
            current_central_widget.setParent(None)  # Avoid deleteLater()

        self._central_widget = widget
        self._central_widget.setProperty("class", "centralWidget")
        self._layout.addWidget(self._central_widget)

    def centralWidget(self):
        """Return the central widget."""
        return self._central_widget

    def init_layout(self):
        """Initialize the menu layout. Called lazily on first item add."""
        # Guard against double initialization
        if self._layout is not None:
            return

        # CRITICAL OPTIMIZATION: Disable updates AND layout calculation
        updates_were_enabled = self.updatesEnabled()
        self.setUpdatesEnabled(False)

        # Also block signals to prevent event propagation during setup
        was_blocked = self.blockSignals(True)

        try:
            # Create outer layout for the translucent window (margins for frame border)
            self._layout = QtWidgets.QVBoxLayout(self)
            # Provide a 2px transparent gutter so translucent borders never touch window edges
            self._layout.setContentsMargins(2, 2, 2, 2)
            self._layout.setSpacing(0)
            self._layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
            self.setLayout(self._layout)

            # Create frame container that will have the border
            self._frame = QtWidgets.QFrame(self)
            self._frame.setObjectName("menuFrame")
            self._frame.setProperty("class", "translucentBgWithBorder")
            self._frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
            self._frame.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
            )
            self._layout.addWidget(self._frame)

            # Create inner layout inside the frame (with spacing for border).
            # Stashed on self so deferred chrome (_ensure_chrome) can insert into it on show.
            self._frame_layout = QtWidgets.QVBoxLayout(self._frame)
            frame_layout = self._frame_layout
            # One extra pixel inside the frame keeps children off the painted border
            frame_layout.setContentsMargins(1, 1, 1, 1)
            frame_layout.setSpacing(1)
            frame_layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

            # Header is deferred to first show — see _ensure_chrome().

            # Create a central widget WITHOUT parent first to avoid tree overhead
            # Parent will be assigned when added to layout
            central_widget = QtWidgets.QWidget()
            self.setCentralWidget(central_widget)

            # Create a QVBoxLayout inside the central widget
            self.centralWidgetLayout = QtWidgets.QVBoxLayout(self._central_widget)
            self.centralWidgetLayout.setContentsMargins(2, 1, 2, 1)
            self.centralWidgetLayout.setSpacing(1)
            self.centralWidgetLayout.setSizeConstraint(
                QtWidgets.QLayout.SetNoConstraint
            )

            # Create a form layout inside the QVBoxLayout
            self.gridLayout = QtWidgets.QGridLayout()
            self.gridLayout.setContentsMargins(0, 0, 0, 0)
            self.gridLayout.setSpacing(1)
            self.gridLayout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

            # Add grid layout to the central widget layout
            self.centralWidgetLayout.addLayout(self.gridLayout)

            # Push items to the top so extra vertical space stays at the bottom
            self.centralWidgetLayout.addStretch(1)

            # Add central widget to frame layout
            frame_layout.addWidget(self._central_widget)

            # Footer is deferred to first show — see _ensure_chrome().

        finally:
            # Restore signal blocking state
            self.blockSignals(was_blocked)

            # Re-enable updates after layout creation
            if updates_were_enabled:
                self.setUpdatesEnabled(True)

            # Activate layout now that setup is complete
            if self._layout:
                self._layout.activate()

    def _ensure_chrome(self):
        """Build the deferred chrome (Header + Footer) on first show.
        Idempotent — guarded per sub-widget, safe to call repeatedly.

        Header/Footer are the heaviest part of a Menu and most option-box menus
        are never opened, so they are built here — right before paint, via
        ``_prepare_for_show`` — instead of eagerly during ``register_children``.
        """
        if self._frame_layout is None:
            self._ensure_layout_created()
        fl = self._frame_layout
        if fl is None:
            return

        if self.add_header and self.header is None:
            self.header = Header(config_buttons=["pin"])
            fl.insertWidget(0, self.header)  # ABOVE the central widget
            if self._pending_title is not None:
                self.header.setText(self._pending_title)
                self._pending_title = None

        if self.add_footer and self.footer is None:
            self.footer = Footer(add_size_grip=True)
            fl.addWidget(self.footer)  # LAST → below the central widget

    def ensure_chrome(self) -> None:
        """Force-build the deferred Header/Footer now.

        For callers that read ``.header`` / ``.footer`` BEFORE the menu is shown
        (e.g. modal dialogs that configure the header up front). Normal menus do
        not need this — chrome builds automatically on first show.
        """
        self._ensure_chrome()

    def _resize_height_to_content(self) -> None:
        """Collapse stale vertical space before showing the menu again.

        Menus are often rebuilt while hidden. Without explicitly syncing the
        geometry, Qt can reuse the previous height, leaving an empty gap when
        fewer items remain. Keeping the width untouched avoids fighting the
        width-matching logic while still trimming vertical dead space.
        """

        if not self._layout:
            return

        self._layout.activate()
        hint = self.sizeHint()
        if not hint.isValid():
            return

        target_height = max(hint.height(), self.minimumHeight())
        current_width = self.width() or max(hint.width(), self.minimumWidth())

        if self.height() != target_height:
            self.resize(current_width, target_height)

    def title(self) -> str:
        """Get the menu's title text (the pending value if the header isn't built yet)."""
        if self.header is not None:
            return self.header.text()
        return self._pending_title or ""

    def setTitle(self, title="") -> None:
        """Set the menu's title to the given string.

        If the header hasn't been built yet (chrome is deferred to first show),
        the title is stashed and applied when the header is created.

        Parameters:
            title (str): Text to apply to the menu's title.
        """
        if self.header is not None:
            self.header.setText(title)
        else:
            # Chrome is deferred to first show; stash and apply when it builds.
            self._pending_title = title

    def _activate_inner_layouts(self) -> None:
        """Synchronously recompute the nested layout sizeHints.

        ``add()`` skips ``self._layout.activate()`` while the menu is
        invisible (Qt re-activates before paint, so the work is wasted for
        an off-screen widget — see the bulk-add note in ``add()``).  The
        side effect is that the *inner* QBoxLayouts (``centralWidgetLayout``
        and the frame layout) keep a cached sizeHint from when they were
        empty — collapsed to just their margins.  ``invalidate()`` only
        posts a deferred ``LayoutRequest`` that never gets processed while
        invisible, and ``sizeHint`` below reads ``self._frame.sizeHint()``
        directly, bypassing the grid's own (correct) recompute.  The net
        result: ``adjustSize()`` on a freshly-populated, not-yet-shown menu
        sizes it to the minimum width, clipping content (e.g. the
        RecentValues / PinnedValues popups, which size-then-show).

        Forcing a synchronous ``activate()`` on the inner chain refreshes
        those cached hints.  The outer ``self._layout`` is intentionally
        left alone — Qt drives its activation and may already be mid-pass.
        Only needed while invisible; once shown Qt drains the pending
        ``LayoutRequest`` and the hints stay current on their own.
        """
        if self._activating_chain:
            return
        self._activating_chain = True
        try:
            if self.centralWidgetLayout is not None:
                self.centralWidgetLayout.activate()
            frame = getattr(self, "_frame", None)
            if frame is not None and frame.layout() is not None:
                frame.layout().activate()
        finally:
            self._activating_chain = False

    def sizeHint(self):
        """Return the recommended size for the widget.

        This method calculates the total size of the widgets contained in the layout of the ExpandableList, including margins and spacing.

        Returns:
            QtCore.QSize: The recommended size for the widget.
        """
        if self._layout is None:
            return super().sizeHint()

        # While invisible the nested layouts hold a stale (collapsed) cached
        # sizeHint; refresh them so adjustSize()/width-matching see the real
        # content width. Once shown, Qt keeps them current — skip the work.
        if not self.isVisible():
            self._activate_inner_layouts()

        total_height = 0
        total_width = 0

        for i in range(self._layout.count()):
            widget = self._layout.itemAt(i).widget()
            if widget:
                total_height += widget.sizeHint().height() + self._layout.spacing()
                total_width = max(total_width, widget.sizeHint().width())

        # Adjust for layout's top and bottom margins
        total_height += (
            self._layout.contentsMargins().top()
            + self._layout.contentsMargins().bottom()
        )
        # Adjust for layout's left and right margins for width
        total_width += (
            self._layout.contentsMargins().left()
            + self._layout.contentsMargins().right()
        )

        return QtCore.QSize(total_width, total_height)
