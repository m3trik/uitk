# !/usr/bin/python
# coding=utf-8
"""Tooltip presentation for managed widgets: :class:`TooltipPresenter`, the
per-widget ``widget.tooltip`` proxy and the Switchboard's ``sb.tooltip``
namespace.

The string DSL they all carry (``fmt`` / ``kbd`` / ``hl`` / ``wrap`` /
``display_ms`` ...) is :class:`pythontk.TooltipFormat`: pure string work, so it
lives below Qt where a headless engine surface can build its tooltips with it.
"""

import weakref

import pythontk as ptk

try:
    from qtpy import QtCore, QtGui, QtWidgets
except ImportError:
    # ImportError, not ModuleNotFoundError: qtpy raises QtBindingsNotFoundError
    # (RuntimeError + ImportError) when it is installed but finds no binding,
    # which ModuleNotFoundError does not catch. Both cases mean the same thing
    # here -- no Qt -- and a genuinely broken binding still fails loudly at the
    # first real Qt import (mainWindow's own `from qtpy import QtWidgets`).
    # The Qt-free DSL moved to ``pythontk.TooltipFormat``; until its alias
    # below is removed, a headless caller still importing it from this path
    # (a scene exporter's task definitions under a DCC's background mode, which
    # ships no Qt binding) must reach it here without one. Everything below
    # that actually touches Qt is inert without a binding, and nothing headless
    # binds a live provider anyway.
    QtCore = QtGui = QtWidgets = None

# ``TooltipFormat`` moved to pythontk (``str_utils/tooltip_format.py``) on
# 2026-09-26; the old import path serves it for one release.
ptk.Deprecation.attributes(
    globals(),
    {"TooltipFormat": "pythontk.TooltipFormat"},
    remove_in="1.7.0",
    since="2026-09-26",
)

#: Base for the event filter — ``object`` when there is no binding to inherit from.
_QObjectBase = QtCore.QObject if QtCore is not None else object


class _TooltipFilter(_QObjectBase):
    """Hands a managed widget's ``QEvent.ToolTip`` to :class:`TooltipPresenter`.

    One per widget for the widget's lifetime (found again through
    :attr:`TooltipPresenter._FILTER_PROP`), carrying the widget's bound
    provider, if any. Every other event returns at the type check.
    """

    #: Resolved once: this check runs for EVERY event a managed widget gets.
    _TOOLTIP = QtCore.QEvent.Type.ToolTip if QtCore is not None else None

    def __init__(self, parent: "QtWidgets.QWidget"):
        super().__init__(parent)
        self.provider = None

    def eventFilter(self, obj, event) -> bool:
        if event.type() != self._TOOLTIP:
            return False
        return TooltipPresenter._on_tooltip(obj, event, self.provider)


class TooltipPresenter:
    """The one path a managed widget's tooltip is shown through.

    Qt shows a tooltip from inside the widget's own ``event()`` (or an item
    view's delegate), handing ``QToolTip`` the raw text: a plain tooltip is
    never wrapped below the screen width, and the display timer is Qt's fixed
    formula. Nothing in Qt lets that be overridden for every widget at once,
    and the process-wide route -- an application event filter -- is ruled out:
    it puts every event in the process through Python (measured ~3x slower
    suite) and faults natively on half-built widgets (PySide 6.9).

    So the override is per widget, at uitk's chokepoint: ``MainWindow.
    register_widget`` hands every widget of every UI to :meth:`manage`, which
    installs one small filter that takes the ``QEvent.ToolTip`` and shows the
    text through :meth:`show_text` -- wrapped (:meth:`TooltipFormat.wrap`) and
    up for a time that scales with it (:attr:`DYNAMIC_DURATION`). An item
    view's viewport, and a combo box's popup list, are managed with it, so
    their items' ``ToolTipRole`` text is shown the same way.

    Anything uitk does not register -- a widget a composite builds for itself,
    a direct ``QToolTip.showText`` call -- joins by calling :meth:`manage` or
    :meth:`show_text`. Text that must be computed at hover time is a bound
    provider (``widget.tooltip.bind``), which the same filter calls first; a
    separate filter that rewrites the tooltip on ``QEvent.ToolTip`` would run
    after this one (Qt runs filters newest-first) and never be seen.
    """

    #: Scale each tooltip's display time with its content
    #: (:meth:`TooltipFormat.display_ms`). ``False`` hands the timing back to
    #: Qt. A widget's own ``setToolTipDuration`` wins either way.
    DYNAMIC_DURATION = True

    #: Dynamic property holding a widget's filter. Kept on the WIDGET, so every
    #: entry point finds the same one: a widget keeps one filter for life, and a
    #: re-bind only swaps the provider on it (a second filter would stack, and
    #: re-installing would move it to the front of Qt's newest-first queue).
    _FILTER_PROP = "_uitk_tooltip_filter"

    #: Views whose tooltips belong to what is drawn in them -- items, graphics
    #: items -- and are shown over their viewport, which manage() covers too.
    _VIEW_TYPES = (
        (QtWidgets.QAbstractItemView, QtWidgets.QGraphicsView)
        if QtWidgets is not None
        else ()
    )

    @classmethod
    def manage(cls, widget) -> "_TooltipFilter":
        """Show *widget*'s tooltips through the presenter. Idempotent.

        Covers what a view draws, too: an item view's items, a combo box's
        popup list, a graphics view's items. A widget that is already managed
        keeps its filter (and its provider).

        Parameters:
            widget: The widget (any ``QObject``); ``None`` is ignored.

        Returns:
            The widget's filter, or ``None`` when there is nothing to manage.
        """
        if widget is None or QtCore is None:
            return None
        filt = cls._install(widget)
        view = widget.view() if isinstance(widget, QtWidgets.QComboBox) else widget
        if isinstance(view, cls._VIEW_TYPES):
            cls._install(view.viewport())
        return filt

    @classmethod
    def show_text(cls, pos, text: str, widget=None, rect=None, duration=None) -> None:
        """Show *text* as a tooltip the way every managed tooltip is shown.

        The drop-in for ``QToolTip.showText``: wrapped at a readable width and
        up for its dynamic display time. Empty *text* hides the current tip.

        Parameters:
            pos: Global position (``QPoint``).
            text: Tooltip text, plain or rich.
            widget: The widget the tip belongs to (Qt hides it on leaving it).
            rect: Area of *widget* (its coordinates) the tip stays up within.
            duration: Display time in ms. ``None`` resolves it: *widget*'s own
                ``toolTipDuration`` when set, else the dynamic time.
        """
        if not text:
            QtWidgets.QToolTip.hideText()
            return
        rich = ptk.TooltipFormat.is_rich(text)
        if duration is None:
            duration = cls._duration_for(text, widget, rich)
        QtWidgets.QToolTip.showText(
            pos,
            ptk.TooltipFormat.wrap(text, rich=rich),
            widget,
            rect if rect is not None else QtCore.QRect(),
            duration,
        )

    @classmethod
    def _duration_for(cls, text: str, widget, rich: bool) -> int:
        explicit = widget.toolTipDuration() if widget is not None else -1
        if explicit > 0:
            return explicit
        return (
            ptk.TooltipFormat.display_ms(text, rich=rich)
            if cls.DYNAMIC_DURATION
            else -1
        )

    @classmethod
    def _install(cls, obj) -> "_TooltipFilter":
        filt = obj.property(cls._FILTER_PROP)
        if filt is None:
            filt = _TooltipFilter(obj)
            obj.installEventFilter(filt)
            obj.setProperty(cls._FILTER_PROP, filt)
        return filt

    @classmethod
    def _bind(cls, widget, provider) -> None:
        """Manage *widget* and make *provider* its hover-time text source."""
        filt = cls.manage(widget)
        if filt is not None:
            filt.provider = cls._safe_provider(provider)

    @staticmethod
    def _safe_provider(fn):
        """Wrap bound-method providers in a weakref to avoid retaining slot instances."""
        if hasattr(fn, "__self__") and hasattr(fn, "__func__"):
            obj_ref = weakref.ref(fn.__self__)
            func = fn.__func__

            def _wrapped():
                obj = obj_ref()
                return func(obj) if obj is not None else ""

            return _wrapped
        return fn

    @classmethod
    def _on_tooltip(cls, obj, event, provider) -> bool:
        """Show *obj*'s tooltip for *event*; ``False`` leaves it to Qt."""
        if not isinstance(obj, QtWidgets.QWidget):
            return False
        view, rect = obj.parentWidget(), None
        if isinstance(view, QtWidgets.QAbstractItemView) and view.viewport() is obj:
            index = view.indexAt(event.pos())
            text = index.data(QtCore.Qt.ToolTipRole) if index.isValid() else None
            # A view may compose an item's tooltip at hover time (TreeWidget's
            # elided-cell text): ``item_tooltip(index, text) -> text``.
            refine = getattr(view, "item_tooltip", None)
            if index.isValid() and callable(refine):
                text = refine(index, text)
            rect = view.visualRect(index)
        elif isinstance(view, QtWidgets.QGraphicsView) and view.viewport() is obj:
            # The topmost item under the pointer that has one, as the scene picks.
            tips = (item.toolTip() for item in view.items(event.pos()))
            text = next((tip for tip in tips if tip), None)
        else:
            if provider is not None:
                text = provider()
                if text is not None:
                    obj.setToolTip(text)
            text = obj.toolTip()
        if not isinstance(text, str) or not text:
            # Nothing here: Qt's own path hides a stale tip and hands the event
            # on -- to the view, or up to the parent.
            return False
        cls.show_text(event.globalPos(), text, obj, rect)
        event.accept()
        return True


class TooltipProxy(ptk.TooltipFormat):
    """Per-widget tooltip namespace stamped on each registered MainWindow widget.

    Accessed as ``widget.tooltip`` after registration. Inherits the whole
    :class:`TooltipFormat` DSL (``fmt`` / ``kbd`` / ``hl`` /
    ``placeholder_preview``) and adds :meth:`bind`, so a slot never has to
    import anything to build a rich tooltip — the namespace is reachable from
    any registered widget (``widget.tooltip.fmt(...)``) and, for code that has
    no widget in hand yet, from the Switchboard (``self.sb.tooltip.fmt(...)``).

    Example::

        # Lazy dynamic content — always current on hover
        self.ui.some_widget.tooltip.bind(lambda: f"Current value: {self._state}")

        # Rich static content built at init time
        widget.menu.add(
            "QComboBox",
            setToolTip=self.sb.tooltip.fmt(
                title="Export Mode",
                bullets=["<b>Composite</b> — mixed WAV", "<b>Keyed Tracks</b> — per source"],
            ),
        )
    """

    def __init__(self, widget: "QtWidgets.QWidget"):
        self._ref = weakref.ref(widget)

    def bind(self, provider) -> None:
        """Register a callable() -> str called lazily on QEvent.ToolTip hover.

        The single-widget convenience form of :meth:`TooltipNamespace.bind` —
        the same relationship ``widget.call_slot`` has to ``sb.call_slot``.
        Both funnel into one installer, so binding a widget twice (by either
        route) replaces its provider instead of stacking event filters.

        The content is computed only when the user actually hovers, so it is
        always fresh without any manual refresh. Bound-method providers are
        captured via weakref so the binding does not keep the slot instance
        alive after the UI is rebuilt.

        Parameters:
            provider: A zero-argument callable returning the tooltip string.
        """
        TooltipPresenter._bind(self._ref(), provider)


class TooltipNamespace(ptk.TooltipFormat):
    """The Switchboard's ``sb.tooltip`` namespace — owner of the tooltip surface.

    Carries the whole :class:`TooltipFormat` DSL (``fmt`` / ``kbd`` / ``hl`` /
    ``placeholder_preview``) plus :meth:`bind` and :meth:`manage`, whose *batch*
    forms only the Switchboard can serve: resolving a shorthand widget range like
    ``"chk000-2"`` against a UI needs ``get_widgets_by_string_pattern``, which
    lives here.

    This is the same ownership split the rest of the Switchboard uses — the
    implementation lives on ``sb``, and ``MainWindow.register_widget`` stamps a
    per-widget convenience (``widget.tooltip``) that delegates back to it, exactly
    as ``widget.call_slot`` delegates to ``sb.call_slot``.

    Example::

        self.sb.tooltip.bind(self.ui.txt000, self._preview)        # one widget
        self.sb.tooltip.bind("chk000-2", self._state, ui=self.ui)  # a range
    """

    def __init__(self, switchboard):
        self._sb = weakref.ref(switchboard)

    def bind(self, widgets, provider, ui=None) -> list:
        """Bind a lazy tooltip *provider* to one widget, several, or a name range.

        Parameters:
            widgets: A widget, an iterable of widgets, or a shorthand name string
                     (``"chk000-2"``) resolved against *ui*.
            provider: A zero-argument callable returning the tooltip string. It is
                     shared by every resolved widget — pass a closure over the
                     widget if each needs its own text.
            ui: The UI to resolve a name string against. Defaults to the
                switchboard's current UI.

        Returns:
            (list) The widgets actually bound.
        """
        bound = self._resolve(widgets, ui)
        for widget in bound:
            TooltipPresenter._bind(widget, provider)
        return bound

    def manage(self, widgets, ui=None) -> list:
        """Show these widgets' tooltips through :class:`TooltipPresenter`.

        Every registered widget already is; this is for the ones uitk never
        registers -- unnamed widgets a slot builds itself, a host's widgets.

        Parameters:
            widgets: A widget, an iterable of widgets, or a shorthand name string
                     (``"chk000-2"``) resolved against *ui*.
            ui: The UI to resolve a name string against. Defaults to the
                switchboard's current UI.

        Returns:
            (list) The widgets managed.
        """
        managed = self._resolve(widgets, ui)
        for widget in managed:
            TooltipPresenter.manage(widget)
        return managed

    def _resolve(self, widgets, ui) -> list:
        """*widgets* as a list: a lone object, an iterable, or a name range."""
        if isinstance(widgets, str):
            sb = self._sb()
            if sb is None:
                return []
            target = ui if ui is not None else sb.current_ui
            if target is None:
                raise ValueError(
                    f"Cannot resolve {widgets!r}: no UI to resolve it against. "
                    f"Pass ui=<your ui>, or bind the widget objects directly."
                )
            widgets = sb.get_widgets_by_string_pattern(target, widgets)
        elif isinstance(widgets, QtCore.QObject):
            # A lone widget/action — every install target is a QObject, since
            # that is what carries installEventFilter + dynamic properties.
            widgets = [widgets]
        return [w for w in (widgets or []) if w is not None]


class TooltipMixin:
    """Mixin for MainWindow — stamps ``widget.tooltip`` on every registered widget.

    Does not override ``__init__``; ``MainWindow.register_widget`` applies the
    stamp, and hands the widget to :meth:`TooltipPresenter.manage`, after the
    widget is otherwise fully set up.
    """
