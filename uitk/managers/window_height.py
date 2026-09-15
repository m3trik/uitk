# !/usr/bin/python
# coding=utf-8
"""How a window follows the height of what it is holding."""

from typing import List, Optional

from qtpy import QtWidgets

from uitk.widgets.mixins.size_grip import SizeGripMixin


class WindowHeight:
    """One implementation of "my content changed -- follow it".

    Anything that adds, removes, shows or hides widgets changes how tall its
    window wants to be: a group collapsing, a tool switching modes, a form
    growing rows. Resizing directly is never the whole job, and it is the
    rest of the job that gets forgotten -- layouts activated in the wrong
    order report a STALE hint, a cached minimum clamps the shrink away, and a
    layout whose every visible child is height-fixed keeps dead space nobody
    asked for. That bookkeeping lives here, once, so a caller only has to say
    which of the two shapes it means:

        WindowHeight.adjust_by(window, delta, baseline=before)  # keeps extra
        WindowHeight.fit_to_content(window)                     # snaps to fit

    The difference between them is what happens to height the USER added by
    hand. :meth:`adjust_by` applies a signed delta, so an expanded window
    stays expanded; :meth:`fit_to_content` snaps to what the content needs
    and that extra height is gone. Prefer the delta whenever the caller knows
    the before/after change in pixels.

    :meth:`fit_host` is the form for a caller that holds a widget rather than
    a window -- it resolves the window and picks that window's own way of
    fitting, which is how a panel and a popup menu can share one call site.

    Companion to :class:`SizeGripMixin`, which owns what the content's real
    minimum and maximum ARE (and the grip that drags between them); this owns
    what a window does about them when its content changes.
    """

    # ------------------------------------------------------------------
    # Measuring
    # ------------------------------------------------------------------

    @staticmethod
    def activate_layouts(window: QtWidgets.QWidget) -> None:
        """Invalidate + re-activate every layout in *window*'s tree so size
        hints reflect the latest visibility/content state before we resize.

        Pure ``activate()`` is not enough on its own -- Qt caches sizeHints
        aggressively and visibility changes on form layouts won't propagate
        without an explicit invalidate.
        """
        layouts: List[QtWidgets.QLayout] = []
        own_layout = WindowHeight._layout_of(window)
        if own_layout:
            layouts.append(own_layout)
        # Walk descendants and collect each owned layout. The callable check
        # in _layout_of guards against widgets that shadowed Qt's layout()
        # method with an instance attribute (legacy pattern in some uitk
        # widgets).
        for child in window.findChildren(QtWidgets.QWidget):
            child_layout = WindowHeight._layout_of(child)
            if child_layout:
                layouts.append(child_layout)
        # Two-pass: invalidate first (drops cached sizes everywhere), then
        # activate from the LEAVES UP.
        #
        # The order of the second pass is load-bearing, and the collection
        # above produces the wrong one: the window's own layout goes in
        # first, then ``findChildren`` walks the tree parent-first. Activating
        # a parent before the layouts nested inside it recomputes it from
        # child hints that have not refreshed yet, so the window's own
        # ``minimumSizeHint`` comes back STALE for one more event cycle.
        # Reading it in the same call frame -- which is exactly what
        # :meth:`fit_to_content` does -- then snaps the window to the PREVIOUS
        # content's height: a bridge panel switched to a template with fewer
        # parameter rows kept the taller window until some later change
        # happened to fit it again (measured on the substance panel: content
        # 265px, window stuck at 341px, every time).
        #
        # Sorted by depth rather than merely reversed: ``findChildren``'s order
        # is not a documented contract, and "every layout is activated after
        # everything nested inside it" is the property that actually matters.
        for layout in layouts:
            layout.invalidate()
        for layout in sorted(
            layouts, key=lambda lay: WindowHeight._depth(window, lay), reverse=True
        ):
            layout.activate()
        # Mark the window's size hint dirty so the next call returns the
        # recomputed value, not the cached one.
        window.updateGeometry()

    @staticmethod
    def _layout_of(widget) -> Optional[QtWidgets.QLayout]:
        """*widget*'s own layout, tolerating a shadowed ``layout`` attribute."""
        layout_attr = getattr(widget, "layout", None)
        if callable(layout_attr):
            return layout_attr()
        if isinstance(layout_attr, QtWidgets.QLayout):
            return layout_attr
        return None

    @staticmethod
    def _depth(window: QtWidgets.QWidget, layout: QtWidgets.QLayout) -> int:
        """How many widgets separate *layout*'s owner from *window* (0 = own).

        The sort key for the leaves-up activation above. Only the ORDER
        matters, so the two degenerate cases are both harmless: a layout with
        no owner yet reads as 0 and activates alongside the window's own
        layout (last), and one owned outside the window's tree counts its own
        ancestors and activates early -- neither can displace a real
        descendant from behind its parent.
        """
        widget = layout.parentWidget()
        depth = 0
        while widget is not None and widget is not window:
            widget = widget.parentWidget()
            depth += 1
        return depth

    @staticmethod
    def sync_min(window: QtWidgets.QWidget, hint: int) -> None:
        """Align *window*'s ``minimumHeight`` with a freshly-computed hint.

        QMainWindow's auto-cached ``minimumSize`` follows ``minimumSizeHint``
        UP automatically when content grows, but does NOT follow it BACK DOWN
        when content shrinks (e.g. a CollapsableGroup hides its body). The
        stale-high minimum then clamps the next ``resize()`` and masks the
        requested shrink.

        The first explicit ``setMinimumHeight()`` also disables Qt's auto-grow
        on the *same* widget -- so once we've taken over the min, we have to
        keep it in sync in BOTH directions, not just lower it on shrink.
        Always tracking the hint is what Qt was trying to do automatically;
        we're just doing it deterministically and in the same call-frame as
        the resize that needs it.
        """
        if hint < 0:
            return
        if window.minimumHeight() != hint:
            window.setMinimumHeight(hint)

    # ------------------------------------------------------------------
    # Resizing
    # ------------------------------------------------------------------

    @staticmethod
    def adjust_by(
        window: QtWidgets.QWidget, delta: int, baseline: Optional[int] = None
    ) -> None:
        """Apply a signed pixel delta to *window*'s height.

        Use when a widget knows the before/after change in pixels and wants
        the window to follow gracefully -- preserving any extra height the
        user previously expanded into, as long as the content can still use
        it. Width is preserved. Result is clamped to the true content minimum
        (``SizeGripMixin.content_min_height``, which owns the rule and
        explains why a bare ``minimumSizeHint`` is not a safe floor), so it
        can't shrink into overlap, and to the
        content maximum (via ``sync_window_max_to_content``) so it can't
        preserve or create dead space once every visible child is
        height-fixed (e.g. a CollapsableGroup hiding the only growable
        widget).

        Parameters:
            window: The window to resize.
            delta: Signed pixel delta. Positive grows, negative shrinks.
            baseline: The window height measured BEFORE the caller changed its
                content. Pass it whenever it is known -- reading ``height()``
                here instead races Qt's automatic minimum tracking: revealing
                content raises the layout minimum, and a QMainWindow sitting
                below its fresh minimum is grown to meet it, sometimes before
                this call is even reached. That growth *is* the caller's delta
                already applied, so adding delta to the grown height
                double-counts it. The surplus then lands in whatever absorbs
                slack (a trailing Expanding spacer) and reads as dead space
                above the footer once the content collapses again. Whether the
                auto-grow lands before or after entry is timing-dependent, so
                the caller's own baseline is the only stable reference.
        """
        if delta == 0:
            return
        old_height = window.height() if baseline is None else baseline
        WindowHeight.activate_layouts(window)
        min_h = SizeGripMixin.content_min_height(window)
        # Also BEFORE the max-sync: syncing may itself shrink the window
        # (snapping off dead space), and the delta applies to the old height.
        new_height = max(old_height + delta, min_h)
        WindowHeight.sync_min(window, min_h)
        SizeGripMixin.sync_window_max_to_content(window)
        window.resize(window.width(), new_height)  # Qt clamps to the synced max

    @staticmethod
    def fit_to_content(window: QtWidgets.QWidget) -> None:
        """Snap *window*'s height to its layout's natural content size.

        Use after bulk visibility changes (dynamic form rows, populated
        lists, ...) where computing a delta is awkward. Width is preserved.

        Loses any "extra" vertical space the user had manually expanded into.
        Use :meth:`adjust_by` when that preservation matters.
        """
        WindowHeight.activate_layouts(window)
        # Target the layout's natural content height, falling back to sizeHint.
        # When BOTH are 0 the layout exposes no height at all (e.g. marking-menu
        # submenus whose content — an ExpandableList, nested Regions — is
        # absolutely positioned in a layout-less central): leave the window at
        # its natural size rather than resize. The content floor must NOT override
        # this early return — it reports only the tiny *laid-out* part (~18px
        # for a lone nav button), and resizing to that collapsed such submenus
        # to a sliver with their real content rendered detached ("submenu shows
        # in the wrong location").
        target = window.minimumSizeHint().height()
        if target <= 0:
            target = window.sizeHint().height()
        if target <= 0:
            return
        # We have a positive content target: floor it by the true content
        # minimum so an under-reporting central (a layout min smaller than the
        # space its fixed-height children need) can't pack them into overlap.
        floor = SizeGripMixin.content_min_height(window)
        target = max(target, floor)
        WindowHeight.sync_min(window, floor)
        # Lock/free the window max to match the content so a fully-fixed
        # layout can't be stretched into dead space afterwards (and a stale
        # lock clears once the content is growable again).
        SizeGripMixin.sync_window_max_to_content(window)
        window.resize(window.width(), target)

    @staticmethod
    def fit_host(widget) -> None:
        """Fit the window *widget* lives in, however that window fits.

        The form for a caller that holds a widget rather than a window -- a
        registry of rows it has just shown or hidden, say. A host that states
        its own ``fit_height_to_content`` (any :class:`MainWindow`, and
        anything that overrides it) is asked in its own terms, so a panel
        that fits differently keeps doing so; anything else is asked to
        ``adjustSize``, which is how a popup menu re-measures. Resolved at
        call time rather than bound once, because the window a widget is in
        is not necessarily the one it was built in.
        """
        if widget is None:
            return
        host = widget.window() if hasattr(widget, "window") else None
        if host is None:
            return
        fit = getattr(host, "fit_height_to_content", None)
        if callable(fit):
            fit()
        elif callable(getattr(host, "adjustSize", None)):
            host.adjustSize()
