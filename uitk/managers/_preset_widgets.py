# !/usr/bin/python
# coding=utf-8
"""Which widgets a preset covers, and how each one's value is read and written.

One part of :class:`~uitk.managers.preset_manager.PresetManager`, which
inherits it: the capture *scope* (``auto`` / ``menu`` / ``window`` /
``explicit``) and its name allow/deny lists, the candidate widget sets each
scope resolves to, and the value authority that reads and writes a widget
(``KindFactory`` for the widgets it built, the window's ``StateManager`` for
registered ones, a plain ``isinstance`` ladder otherwise). It holds no state of
its own: ``PresetManager.__init__`` declares every attribute used here.
"""

from typing import TYPE_CHECKING, Any, Optional, Set

from qtpy import QtWidgets

from uitk.managers.value_manager import ValueManager

if TYPE_CHECKING:
    from uitk.managers.preset_manager import PresetManager


class _PresetWidgetScope:
    """Capture scope, candidate widgets and the per-widget value authority."""

    _VALID_SCOPES = ("auto", "menu", "window", "explicit")

    @property
    def scope(self) -> str:
        """Which widget set a save/load operates on.

        - ``"auto"`` (default): legacy implicit resolution — explicit list, else
          the *parent* menu's items, else the parent window's registered set.
          Preserves prior behavior for every existing caller.
        - ``"menu"``: force the parent menu's ``get_items()`` (today's
          ``add_presets`` behavior, made explicit).
        - ``"window"``: capture the owning ``MainWindow``'s registered widgets
          (``restore_state=True``), regardless of where the manager's *parent*
          sits. This is what lets a header-menu preset capture panel widgets.
        - ``"explicit"``: only the widgets passed via ``widgets=`` /
          :meth:`from_widgets` / :meth:`setup`.

        Refine any scope with :meth:`include` / :meth:`exclude`.
        """
        return self._scope

    @scope.setter
    def scope(self, value: str) -> None:
        if value not in self._VALID_SCOPES:
            raise ValueError(
                f"scope must be one of {self._VALID_SCOPES}, got {value!r}"
            )
        self._scope = value

    @staticmethod
    def _as_object_names(items) -> Set[str]:
        """Coerce a mix of ``objectName`` strings / widget instances to names."""
        names: Set[str] = set()
        for item in items:
            if isinstance(item, str):
                if item:
                    names.add(item)
            else:  # assume a QWidget
                name = item.objectName() if hasattr(item, "objectName") else ""
                if name:
                    names.add(name)
        return names

    def exclude(self, *names_or_widgets) -> "PresetManager":
        """Exclude widgets (by ``objectName`` or instance) from capture/restore.

        Names are preferred — they resolve at save/load time, so widgets that
        don't exist yet at config time still match. Additive across calls.
        Returns *self* for chaining.
        """
        self._exclude_names |= self._as_object_names(names_or_widgets)
        return self

    def include(self, *names_or_widgets) -> "PresetManager":
        """Restrict capture/restore to *only* these widgets (allowlist).

        Once any ``include`` is set, everything not listed is excluded. Names or
        instances both accepted; additive across calls. Returns *self*.
        """
        if self._include_names is None:
            self._include_names = set()
        self._include_names |= self._as_object_names(names_or_widgets)
        return self

    def _passes_filters(self, name: str) -> bool:
        """True when *name* survives the include allowlist + exclude denylist."""
        if self._include_names is not None and name not in self._include_names:
            return False
        return name not in self._exclude_names

    def _resolve_window(self) -> Optional[QtWidgets.QWidget]:
        """Resolve (and cache) the owning ``MainWindow`` for ``"window"`` scope.

        Duck-typed: a window exposes both ``widgets`` and ``state``. The *parent*
        is the window itself in MainWindow mode; in menu mode it's the menu,
        which exposes :meth:`Menu.owner_window` — that resolver survives the
        live-DCC popup-reparent race a plain ``parent().window()`` walk loses to.
        """
        win = self._window
        if win is not None:
            try:
                win.objectName()  # dead C++ wrapper -> RuntimeError
                return win
            except RuntimeError:
                self._window = None

        parent = self.parent
        if parent is None:
            return None
        if hasattr(parent, "widgets") and hasattr(parent, "state"):
            self._window = parent
        elif hasattr(parent, "owner_window"):
            self._window = parent.owner_window()
        return self._window

    def _get_widgets(
        self, scope: Optional[QtWidgets.QWidget] = None
    ) -> Set[QtWidgets.QWidget]:
        """Return the set of restorable widgets the current :attr:`scope` selects.

        The source set is chosen by :attr:`scope`:

        - ``"explicit"`` — the constructor / ``setup()`` widget list.
        - ``"menu"`` — the parent menu's ``get_items()`` (only value-bearing).
        - ``"window"`` — the owning ``MainWindow``'s registered, ``restore_state``
          widgets (resolved even when the manager's *parent* is a menu).
        - ``"auto"`` (default) — legacy order: explicit list, else menu items,
          else the parent window's registered set.

        The source is then filtered by the always-excluded instance set
        (``_excluded_widgets`` — e.g. the preset combo), the name-based exclude
        denylist, and the include allowlist (see :meth:`exclude` / :meth:`include`).

        Parameters:
            scope: An optional container widget to further limit a window-scoped
                search to that subtree.

        Returns:
            A set of widgets.
        """
        candidates = self._scope_candidates(scope)
        return {
            w
            for w in candidates
            if w.objectName()
            and w not in self._excluded_widgets
            and self._passes_filters(w.objectName())
        }

    def _scope_candidates(
        self, scope: Optional[QtWidgets.QWidget]
    ) -> Set[QtWidgets.QWidget]:
        """Resolve the raw candidate widget set for the current :attr:`scope`.

        Per-source typing rules are applied here (menus: value-bearing items;
        windows: ``restore_state``, value-bearing only under explicit ``"window"``
        scope); the name/instance filters are layered on by :meth:`_get_widgets`.
        """
        mode = self._scope
        if mode == "explicit":
            return set(self._explicit_widgets or [])
        if mode == "menu":
            return self._menu_candidates()
        if mode == "window":
            # Explicit window scope is the opinionated "capture the panel's
            # state" mode: keep only value-bearing widgets (drop buttons /
            # group boxes / chrome).
            return self._window_candidates(scope, value_only=True)

        # "auto" — legacy implicit resolution order. The window branch here is
        # the back-compat MainWindow mode (``PresetManager(parent=window, …)``,
        # e.g. ``MainWindow.presets`` / curtain); it keeps the prior
        # ``restore_state``-only set, NO value-type filter, so existing presets
        # aren't silently re-scoped.
        if self._explicit_widgets is not None:
            return set(self._explicit_widgets)
        if hasattr(self.parent, "get_items"):
            return self._menu_candidates()
        return self._window_candidates(scope, value_only=False)

    def _menu_candidates(self) -> Set[QtWidgets.QWidget]:
        """Value-bearing items of the parent menu (empty if parent isn't a menu)."""
        parent = self.parent
        if not hasattr(parent, "get_items"):
            return set()
        return {w for w in parent.get_items() if self._get_widget_value(w) is not None}

    def _window_candidates(
        self, scope: Optional[QtWidgets.QWidget], value_only: bool
    ) -> Set[QtWidgets.QWidget]:
        """Registered, ``restore_state`` widgets of the owning ``MainWindow``.

        Resolving the window (vs. reading ``parent.widgets`` directly) is what
        lets a *menu*-parented manager reach the whole window. Binds the window's
        ``StateManager`` so capture/apply use the same get/set semantics as
        session state (index guards, ``currentData``, …).

        ``value_only`` keeps only *value-bearing* widgets — stateful inputs
        (checkboxes, combos, line edits, …), not action buttons, group boxes,
        header chrome, or size grips, all of which carry ``restore_state`` but no
        meaningful value. It's on for explicit ``"window"`` scope (clean panel
        capture) and off for the legacy auto/MainWindow path (back-compat).
        """
        window = self._resolve_window()
        registered = getattr(window, "widgets", None)
        if registered is None:  # fallback: parent itself is/has the set
            registered = getattr(self.parent, "widgets", set())
        registered = registered or set()

        # Adopt the window's StateManager for value get/set when available and
        # not already supplied — turns the standalone path into MainWindow mode.
        if self.state is None and window is not None:
            self.state = getattr(window, "state", None)

        if scope is not None and scope is not window and scope is not self.parent:
            scope_children = set(scope.findChildren(QtWidgets.QWidget))
            registered = registered & scope_children

        return {
            w
            for w in registered
            if getattr(w, "restore_state", False)
            and (not value_only or self._get_widget_value(w) is not None)
        }

    # ---- value authority ------------------------------------------------
    # Three readers, most-specific first. A widget's own builder always knows best:
    #
    # 1. ``KindFactory`` — for widgets IT built (stamped ``_attr_kind``). It owns a
    #    read/write pair per kind, so it reaches composites whose value lives on an
    #    inner child (``path``, ``file_list``) and list-shaped kinds (``check_list``)
    #    that neither of the readers below has any branch for. Without this those
    #    params silently vanished from a saved preset: the manager read ``None`` from
    #    the composite container and ``_capture_values`` dropped the key.
    # 2. ``StateManager`` — for plain registered widgets in MainWindow mode, so
    #    presets and session state agree on index guards / ``currentData``.
    # 3. The ``isinstance`` ladder — standalone fallback.
    #
    # Kind-first, not state-first: the stamp is proof of who built the widget,
    # whereas ``StateManager`` would answer for a composite by guessing from its Qt
    # type and get it wrong.

    @staticmethod
    def _kind_factory():
        """The ``KindFactory`` class.

        Deferred, and resolved in ONE place: ``uitk.bridge`` imports this module, so
        a module-level import would close the cycle -- and repeating the deferred
        import at each use site repeats that reasoning where it can rot.
        """
        from uitk.bridge.spec import KindFactory

        return KindFactory

    @staticmethod
    def _kind_of(widget: QtWidgets.QWidget) -> Any:
        """The kind stamped on a widget built by ``KindFactory``, else ``None``."""
        return _PresetWidgetScope._kind_factory().kind_of(widget)

    def _read_widget(self, widget: QtWidgets.QWidget) -> Any:
        """Read *widget* through the most specific authority available."""
        factory = _PresetWidgetScope._kind_factory()
        if factory.kind_of(widget) is not None:
            return factory.read_value(widget)
        if self.state is not None:
            return self.state._get_current_value(widget)
        return _PresetWidgetScope._get_plain_widget_value(widget)

    def _write_widget(self, widget: QtWidgets.QWidget, value: Any) -> Any:
        """Write *value* to *widget* through the most specific authority available.

        Returns:
            False when the authority refused *value* (``PresetManager.load``
            counts that as a misfit); anything else is a write.
        """
        factory = _PresetWidgetScope._kind_factory()
        if factory.kind_of(widget) is not None:
            return factory.set_value(widget, value)
        if self.state is not None:
            return self.state.apply(widget, value)
        return _PresetWidgetScope._set_plain_widget_value(widget, value)

    @staticmethod
    def _get_widget_value(widget: QtWidgets.QWidget) -> Any:
        """Read a widget's value without an instance (kind stamp, else the ladder).

        The *candidate filter*'s reader, not capture's: ``_window_candidates`` and
        ``_menu_candidates`` ask "does this widget bear a value at all?" of widgets
        that may not be registered with any ``StateManager``, so this deliberately
        skips the state tier :meth:`_read_widget` consults. Capture and apply go
        through ``_read_widget`` / ``_write_widget``.

        There is intentionally no static ``_set_widget_value`` counterpart -- the
        filter never writes, and a setter with no caller is dead weight that reads
        as a supported path.
        """
        factory = _PresetWidgetScope._kind_factory()
        if factory.kind_of(widget) is not None:
            return factory.read_value(widget)
        return _PresetWidgetScope._get_plain_widget_value(widget)

    @staticmethod
    def _get_plain_widget_value(widget: QtWidgets.QWidget) -> Any:
        """Read the current value from a standard Qt widget."""
        if isinstance(widget, (QtWidgets.QCheckBox, QtWidgets.QRadioButton)):
            return widget.isChecked()
        elif isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            return widget.value()
        elif isinstance(widget, QtWidgets.QComboBox):
            # By row: _set_plain_widget_value restores an index.
            return ValueManager.combo_value(widget, "index")
        elif isinstance(widget, QtWidgets.QLineEdit):
            return widget.text()
        elif isinstance(widget, QtWidgets.QTextEdit):
            return widget.toPlainText()
        elif isinstance(widget, QtWidgets.QSlider):
            return widget.value()
        return None

    @staticmethod
    def _set_plain_widget_value(widget: QtWidgets.QWidget, value: Any) -> None:
        """Set a value on a standard Qt widget."""
        if isinstance(widget, (QtWidgets.QCheckBox, QtWidgets.QRadioButton)):
            widget.setChecked(value)
        elif isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            widget.setValue(value)
        elif isinstance(widget, QtWidgets.QComboBox):
            # Qt blanks the combo for an index past its items (the list shrank
            # since the save); refuse instead, so the current choice stays.
            if not -1 <= value < widget.count():
                raise ValueError(f"index {value} outside 0..{widget.count() - 1}")
            widget.setCurrentIndex(value)
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(value)
        elif isinstance(widget, QtWidgets.QTextEdit):
            widget.setPlainText(value)
        elif isinstance(widget, QtWidgets.QSlider):
            widget.setValue(value)

    @staticmethod
    def _value_change_signal(widget: QtWidgets.QWidget):
        """Return *widget*'s value-change Signal, or ``None``."""
        # Prefer the uitk wrapper's declared default signal.
        getter = getattr(widget, "default_signals", None)
        if callable(getter):
            try:
                name = getter()
                if name:
                    sig = getattr(widget, name, None)
                    if sig is not None:
                        return sig
            except Exception:
                pass
        # Fall back to a type-based mapping for plain Qt widgets.
        for cls, attr in (
            (QtWidgets.QCheckBox, "stateChanged"),
            (QtWidgets.QRadioButton, "toggled"),
            (QtWidgets.QComboBox, "currentIndexChanged"),
            (QtWidgets.QLineEdit, "textChanged"),
            (QtWidgets.QTextEdit, "textChanged"),
            (QtWidgets.QSpinBox, "valueChanged"),
            (QtWidgets.QDoubleSpinBox, "valueChanged"),
            (QtWidgets.QSlider, "valueChanged"),
        ):
            if isinstance(widget, cls):
                return getattr(widget, attr, None)
        return None
