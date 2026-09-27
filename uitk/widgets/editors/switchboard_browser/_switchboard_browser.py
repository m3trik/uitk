# !/usr/bin/python
# coding=utf-8
"""The browser panel: search, tag chips, row actions, and the header menu.

:class:`SwitchboardBrowser` -- a plain ``EditorPanel`` (no ``.ui``). The table
model, the row painting, the row filter and the launch path are their own
modules in this package; see the package docstring.
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional, Set, TYPE_CHECKING, Union

import pythontk as ptk
from qtpy import QtCore, QtWidgets

# ``EditorPanel`` is the base class — must be a real import. ``Switchboard``
# is referenced at runtime only inside the no-arg ``__init__`` branch
# (lazy-imported there) and in type annotations (TYPE_CHECKING block).
# ``StyleSheet`` is reachable via ``sb.style`` at use sites — no direct
# import needed.
from uitk.compile import UiCompiler
from uitk.widgets.editors.editor_panel import EditorPanel
from uitk.widgets.optionBox.options.filter import FilterOption, NEGATE_PREFIX
from uitk.widgets.pushButton import PushButton
from .filtering import (
    SCOPES,
    SCOPE_BOTH,
    SCOPE_ICONS,
    SCOPE_NAME,
    SCOPE_TAGS,
    SHOW_ALL,
    SHOW_HIDDEN,
    SHOW_VISIBLE,
    _BrowserFilterProxy,
)
from .launch import (
    PERSISTENCE_CHOICES,
    PERSISTENCE_CONTEXT,
    PERSISTENCE_STICKY,
    PERSISTENCE_TRANSIENT,
    _LaunchMixin,
)
from .model import SwitchboardBrowserModel
from .row_delegate import _BrowserRowDelegate

if TYPE_CHECKING:  # pragma: no cover
    from uitk.switchboard import Switchboard


# ── Main browser ──────────────────────────────────────────────────────────────


class _BrowserState:
    """Minimal ``state`` shim for ``Menu``'s built-in *Restore Defaults* button.

    ``Menu._restore_menu_defaults`` walks parents looking for a widget that
    exposes a ``state`` attribute with a ``reset(widget)`` method (the contract
    is normally satisfied by ``MainWindow.state`` / ``StateManager``). The
    browser is an ``EditorPanel``, not a ``MainWindow``, so without this shim
    the *Restore Defaults* button silently no-ops.

    We capture each menu widget's initial value at construction time and apply
    it back through the widget's type-appropriate setter on reset. Dispatching
    by widget type rather than delegating to ``ValueManager.set_value`` is about
    the COMBO branch below, not about buttons: ``set_value`` tests
    ``isinstance(widget, QAbstractButton)`` ahead of every text branch, so a
    ``QCheckBox`` is toggled and keeps its label (measured 2026-08-29 — the
    earlier note here claimed the opposite and was stale).

    Calling the semantic setter (``setChecked`` / ``setCurrentIndex`` /
    ``setText``) also fires the widget's normal change signals, which is what
    wires the reset back into our settings + filter pipeline.

    Combos are reset **by index**, not by text: uitk's ``ComboBox.setCurrentText``
    is ``@Signals.blockSignals``-decorated, so a text reset moved the display
    without ever firing ``currentTextChanged`` — the handler that persists the
    choice (theme, window persistence) never ran, and *Restore Defaults*
    silently left the stored value behind. Text is the fallback for a value
    that isn't one of the items.
    """

    def __init__(self):
        self._defaults = {}

    def capture(self, widget, value) -> None:
        self._defaults[widget] = value

    def reset_all(self, block_signals: bool = False, widgets=None) -> None:
        """``StateManager.reset_all`` contract: reset *widgets* (default: all)."""
        for widget in list(self._defaults if widgets is None else widgets):
            self.reset(widget)

    def reset(self, widget) -> None:
        if widget not in self._defaults:
            return
        value = self._defaults[widget]
        if isinstance(widget, QtWidgets.QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QtWidgets.QComboBox):
            index = widget.findText(str(value))
            if index >= 0:
                widget.setCurrentIndex(index)
            else:
                widget.setCurrentText(str(value))
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText("" if value is None else str(value))
        else:
            from uitk.managers.value_manager import ValueManager

            ValueManager.set_value(widget, value)


class SwitchboardBrowser(_LaunchMixin, EditorPanel):
    """Searchable launcher for every UI registered with a Switchboard.

    ``switchboard`` is optional. When omitted, a fresh ``Switchboard``
    is constructed from any ``**switchboard_kwargs`` you pass (typically
    ``ui_source``). The integration pattern most callers want is to pass
    an *existing* switchboard so launched UIs land in the same
    ``loaded_ui`` namespace, share registered widgets / icons, and route
    through the same handlers (e.g. tentacle's marking menu)::

        # Integrated — preferred for application-embedded use
        browser = SwitchboardBrowser(switchboard=app.sb)

        # Standalone — auto-creates an empty Switchboard which the
        # caller can feed via switchboard_kwargs
        browser = SwitchboardBrowser(ui_source="/path/to/ui_dir")

    Mirrors the ``mayatk.MayaUiHandler`` pattern of "use what's given,
    otherwise stand one up" so the browser can be opened from anywhere
    without forcing the caller to wire a switchboard first. A browser built
    either way is its switchboard's ``browser`` editor (``sb.editors``) when
    that has none open, so the launcher's own "browser" row is this window.

    ``inc`` / ``exc`` (``pythontk.filter_list`` shell-style name patterns)
    apply a *structural* entry filter: excluded entries are never
    materialised into the model — absent from counts, chips, presets, and
    the entry-changed signal path. Distinct from the user-curated hide
    lists (row filtering the user can toggle from the Show combo). Host
    apps use it to keep non-standalone UIs out of the launcher, e.g.
    tentacle hides the marking menu's gesture pages::

        browser = SwitchboardBrowser(
            switchboard=app.sb, exc=["*#startmenu*", "*#submenu*"]
        )
    """

    def __init__(
        self,
        switchboard: Optional[Switchboard] = None,
        parent=None,
        inc: Union[str, List[str], None] = None,
        exc: Union[str, List[str], None] = None,
        **switchboard_kwargs,
    ):
        # Accept an existing Switchboard, or auto-create one. Passing
        # both is ambiguous — the kwargs would silently apply to the
        # caller's switchboard or be dropped, neither obviously right —
        # so reject the mix loudly.
        if switchboard is not None and switchboard_kwargs:
            raise ValueError(
                "SwitchboardBrowser: pass an existing 'switchboard' OR "
                "switchboard_kwargs (e.g. ui_source=...), not both."
            )
        if switchboard is None:
            # Lazy import — avoid pulling Switchboard at module load when
            # the caller is going to provide their own instance anyway.
            from uitk.switchboard import Switchboard

            switchboard = Switchboard(**switchboard_kwargs)

        # ``refresh`` is a built-in header button that emits
        # ``refresh_requested`` — we wire it post-construction (see below)
        # to drive the same re-pull as the old menu entry, but as a
        # one-click affordance instead of a buried menu item. Matches
        # the pattern used by mayatk.reference_manager.
        # ``menu`` hosts global browser options (presets, theme, hide
        # lists, …); ``minimize`` is the standard window control.
        #
        # ``on_top=False`` matches EditorPanel's default but is kept
        # explicit at the construction site as load-bearing intent: the
        # browser is a *launcher*, not a config surface for another
        # window, and mayatk's UIs (e.g. reference_manager) parent to
        # Maya without forcing themselves above every other window.
        super().__init__(
            title="UI Browser",
            header_buttons=["refresh", "menu", "minimize", "hide"],
            parent=parent,
            on_top=False,
        )
        self.sb: Switchboard = switchboard
        self.resize(420, 560)
        # Skip EditorPanel's QTableWidget-based auto-fit; we use a QTableView
        # and manage our own size.
        self._size_initialized = True

        # Browser-owned settings (hide lists, scope, last options)
        self._settings = self.sb.settings.branch("ui_browser")

        # ``state`` is the contract a Menu's *Restore Defaults* button looks
        # for — see :class:`_BrowserState`. Made public-ish so any nested
        # Menu (option-box menus, header menu) reaches it via parent walk.
        self.state = _BrowserState()

        self._model = SwitchboardBrowserModel(self.sb, parent=self, inc=inc, exc=exc)

        # ── Search row ─────────────────────────────────────────────────
        # A single filter field covers include + exclude: include terms keep
        # matching rows, and a term prefixed with ! excludes inline (honoured in
        # _row_passes_filter via filter_list(negate_prefix=…)) — so there's no
        # separate exclude row. The option-box carries a FilterOption (filter
        # on/off toggle + scope cycle + text persistence); its menu is never
        # accessed (every option is a button, so a dropdown would be empty).
        self._search = self.sb.registered_widgets.LineEdit()
        self._search.setObjectName("le_search")
        self._search.setPlaceholderText("Search (exact; * for substring; ! excludes)")
        self._search.setToolTip(
            "Search the registered UI list.\n"
            "\n"
            "• Multi-term: separate terms with commas — any matching term\n"
            "  keeps the row, e.g.  *char*, *light*  matches either.\n"
            "• Matching is exact unless you add wildcards:\n"
            "    *      any sequence  (*char* = contains, char* = starts with)\n"
            "    ?      any single character\n"
            "    [seq]  any character in the set, e.g. [abc]\n"
            "• Prefix a term with ! to exclude it, e.g.  *mesh*, !*temp*\n"
            "  keeps rows containing 'mesh' but drops any containing 'temp'.\n"
            "• Click the filter icon to toggle the filter on/off without\n"
            "  clearing the text. Click the scope icon to cycle through\n"
            "  Name / Name+Tags / Tags."
        )
        self._search.option_box.set_filter(
            settings=self._settings,
            text_key="search.text",
            on_changed=self._apply_filter,
            enabled_key="search.filter_enabled",
            on_toggled=lambda _on: self._apply_filter(),
            scopes=[{"key": k, "icon": SCOPE_ICONS[k]} for k in SCOPES],
            scope_key="search.scope",
            default_scope=SCOPE_BOTH,
            on_scope_changed=lambda _new: self._apply_filter(),
        )
        self._search_filter = self._search.option_box.find_option(FilterOption)
        self.body_layout.addWidget(self._search)

        # ── Tag chips ──────────────────────────────────────────────────
        self._chip_scroll = QtWidgets.QScrollArea()
        self._chip_scroll.setWidgetResizable(True)
        self._chip_scroll.setFixedHeight(34)
        self._chip_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self._chip_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._chip_container = QtWidgets.QWidget()
        self._chip_layout = QtWidgets.QHBoxLayout(self._chip_container)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(1)
        self._chip_layout.addStretch(1)
        self._chip_scroll.setWidget(self._chip_container)
        self.body_layout.addWidget(self._chip_scroll)

        self._active_tag_filters: Set[str] = set()
        self._chip_buttons = {}  # tag -> QPushButton

        # ── Header option menu ─────────────────────────────────────────
        # Built *before* the table view because attaching a proxy via
        # ``setSourceModel`` / ``setModel`` immediately invokes the filter
        # predicate, which reads ``self._show`` (created here).
        self._init_header_menu()

        # ── Table view ─────────────────────────────────────────────────
        self._proxy = _BrowserFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        self._view = QtWidgets.QTableView()
        self._view.setModel(self._proxy)
        self._view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        # Tags column (col 1) accepts inline editing via the delegate;
        # name column (col 0) is read-only.
        self._view.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        self._view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._on_row_context_menu)
        self._view.doubleClicked.connect(self._on_double_click)
        self._row_delegate = _BrowserRowDelegate(self)
        self._view.setItemDelegate(self._row_delegate)
        # Header configuration: name stretches, tags expand, action columns fixed
        h = self._view.horizontalHeader()
        h.setSectionResizeMode(
            SwitchboardBrowserModel.COL_NAME, QtWidgets.QHeaderView.ResizeToContents
        )
        h.setSectionResizeMode(
            SwitchboardBrowserModel.COL_TAGS, QtWidgets.QHeaderView.Stretch
        )
        h.setSectionResizeMode(
            SwitchboardBrowserModel.COL_ACTION, QtWidgets.QHeaderView.Fixed
        )
        h.setSectionResizeMode(
            SwitchboardBrowserModel.COL_CLOSE, QtWidgets.QHeaderView.Fixed
        )
        # Action columns are sized to exactly the icon button (22x22) plus
        # zero item padding, so the cell hugs the button with no dead zone
        # on either side. Padding is killed via ``QTableView::item`` QSS so
        # it doesn't reintroduce the whitespace through native styling.
        # ``setMinimumSectionSize`` is required because QHeaderView defaults
        # to a ~30px minimum that silently overrides ``setColumnWidth(22)``.
        h.setMinimumSectionSize(22)
        self._view.setColumnWidth(SwitchboardBrowserModel.COL_ACTION, 22)
        self._view.setColumnWidth(SwitchboardBrowserModel.COL_CLOSE, 22)
        # Selection / hover styling lives entirely in the global QSS
        # (uitk/themes/style.qss).  The only per-view override the
        # browser still needs is zero item padding — the action columns
        # are exactly 22px wide and any inherited cell padding would
        # squeeze the icon buttons.
        self._view.setStyleSheet("QTableView::item { padding: 0; }")
        # Mouse tracking is required for ``QStyle::State_MouseOver`` (and
        # therefore QSS ``:hover``) to fire on cursor moves without a
        # button held — the default is off, so item hover tints silently
        # never render.
        self._view.setMouseTracking(True)
        self._view.verticalHeader().setVisible(False)
        self._view.verticalHeader().setDefaultSectionSize(22)
        self._view.setShowGrid(False)
        self.body_layout.addWidget(self._view, 1)

        # ── Footer status ──────────────────────────────────────────────
        # Idle: counts (registered / visible / shown). Selected: the
        # selected UI's name + path. HTML-formatted via the footer's
        # status label (which is a QLabel under the hood).
        self.footer.setDefaultStatusText("")

        # Final wiring. Footer/chip/row-widget refresh share a single
        # debounced path (``_do_full_refresh``); per-signal connections
        # to ``_update_footer_status`` would re-fire its O(N) visible-count
        # loop on every dataChanged, which is wasteful. Selection changes
        # update only the footer (no row rebuild needed).
        self._model.dataChanged.connect(self._on_model_data_changed)
        self._model.rowsInserted.connect(self._defer_full_refresh)
        self._model.rowsRemoved.connect(self._defer_full_refresh)
        # A coarse registry change re-pulls via beginResetModel/endResetModel
        # (SwitchboardBrowserModel._refresh). A model reset drops every row's
        # setIndexWidget Launch/Close button but emits neither rowsInserted/
        # Removed nor proxy layoutChanged, so without this the buttons vanish
        # and never rebuild. Rebuild them on the deferred full refresh.
        self._model.modelReset.connect(self._defer_full_refresh)
        self._proxy.layoutChanged.connect(self._defer_full_refresh)
        self._view.selectionModel().currentChanged.connect(self._update_footer_status)
        self._refresh_chips()
        self._update_show_ui()
        self._apply_filter()
        self._refresh_row_widgets()
        self._select_first_row()
        self._update_footer_status()

        # Built directly, this is the switchboard's "browser" editor unless one
        # is already open: the launcher's row for it -- and ``sb.editors`` --
        # then reach THIS window instead of building a second. (A registry
        # build adopts here too, and the registry skips re-running the hooks.)
        editors = getattr(self.sb, "editors", None)
        if editors is not None:
            editors.adopt("browser", self)

    # ── helpers ──────────────────────────────────────────────────────────────

    @property
    def hidden_uis(self) -> Set[str]:
        raw = self._settings.value("hidden_uis", []) or []
        return set(raw)

    @hidden_uis.setter
    def hidden_uis(self, value: Iterable[str]) -> None:
        self._settings.setValue("hidden_uis", sorted(set(value)))

    @property
    def hidden_tags(self) -> Set[str]:
        raw = self._settings.value("hidden_tags", []) or []
        return set(raw)

    @hidden_tags.setter
    def hidden_tags(self, value: Iterable[str]) -> None:
        self._settings.setValue("hidden_tags", sorted(set(value)))

    def set_search_scope(self, value: str) -> None:
        """Public helper: set the search-line-edit scope to ``value``."""
        self._search_filter.set_scope(value, notify=True)

    def set_entry_filter(
        self,
        inc: Union[str, List[str], None] = None,
        exc: Union[str, List[str], None] = None,
    ) -> None:
        """Replace the structural inc/exc entry filter (see class docstring).

        Filtered entries are never materialised — absent from counts, chips,
        and the signal path — unlike the user-curated hide lists. Hosts
        typically apply this from an editors post-build hook so every build
        of the browser carries the policy::

            sb.editors.add_post_build_hook(
                "browser",
                lambda b: b.set_entry_filter(exc=["*#startmenu*", "*#submenu*"]),
            )

        Calling with no arguments clears the filter.
        """
        self._model.set_entry_filter(inc=inc, exc=exc)
        # Same post-registry-change sequence as _on_refresh_clicked: the
        # proxy invalidate (via _apply_filter) is what triggers the deferred
        # row-widget rebuild.
        self._refresh_chips()
        self._apply_filter()
        self._update_footer_status()

    # ── Header menu (Refresh + Show + Launch + Theme + Presets) ─────────────

    def _init_header_menu(self) -> None:
        """Populate the header dropdown with global browser options.

        Sections in display order:
            • "Refresh" button — re-pulls the registry.
            • "Show:" separator + show-mode combo + Unhide-All button.
            • "Launch options:" separator + frameless / restore-geometry
              checkboxes + theme combo.
            • "Presets:" separator + preset combo (Save / Rename / Delete /
              Open Folder built into the combo by ``PresetManager``).

        Defaults are captured into ``self.state`` after each widget is added,
        so the menu's built-in *Restore Defaults* button (enabled below) can
        round-trip them via :class:`_BrowserState`.

        """
        menu = self._header.menu
        menu.setTitle("Browser Options:")
        # Light-up the built-in Restore Defaults button. Without ``state`` on
        # the browser (see :class:`_BrowserState`) it would silently no-op.
        menu.add_defaults_button = True

        # Refresh is wired as a top-level header button (see
        # ``header_buttons`` in __init__) — the ``refresh_requested``
        # signal drives the same re-pull. Mirrors mayatk's reference
        # manager pattern; promotes Refresh from a buried menu entry
        # to a single-click affordance.
        self._header.refresh_requested.connect(self._on_refresh_clicked)

        # Use uitk's PushButton (not QPushButton) so the button has
        # `option_box` available for the force-compile toggle below.
        self._btn_compile_all = menu.add(
            PushButton,
            setText="Compile all",
            setObjectName="btn_compile_all",
            setToolTip=(
                "Pre-compile every registered .ui to its _ui.py.\n"
                "Stale or missing files are regenerated; up-to-date "
                "files are skipped (hash match).\n\n"
                "Toggle the option-box (refresh icon) on the right to "
                "force-recompile every file regardless of hash."
            ),
        )
        self._btn_compile_all.clicked.connect(self._on_compile_all_clicked)

        # Option-box toggle: when on (state 1), the next click force-recompiles
        # every .ui regardless of hash freshness. State 0 (off) keeps the
        # default behavior (skip files whose hash already matches). Per-state
        # callbacks flip the flag to the *will-be* value before the visual
        # advances, so flag and icon stay in lock-step.
        self._compile_force = False

        def _set_force(value: bool) -> None:
            self._compile_force = value

        self._btn_compile_all.option_box.set_action(
            states=[
                {
                    "icon": "refresh",
                    "color": "#555555",
                    "tooltip": (
                        "Force-recompile: off. Click to enable — next "
                        "'Compile all' will recompile every .ui regardless "
                        "of hash."
                    ),
                    "callback": lambda: _set_force(True),
                },
                {
                    "icon": "refresh",
                    "tooltip": (
                        "Force-recompile: on. Click to disable — next "
                        "'Compile all' will skip files whose hash already "
                        "matches."
                    ),
                    "callback": lambda: _set_force(False),
                },
            ],
            settings_key=False,  # transient: reset to off each session
        )

        self._compile_poll_timer = None

        # ── Show ──
        menu.add("Separator", setTitle="Show:")
        self._show = menu.add(
            "QComboBox",
            setObjectName="cmb_show_mode",
            setToolTip=(
                "Which UIs appear in the list:\n"
                "  visible — exclude UIs/tags from the hide lists.\n"
                "  hidden  — show only UIs/tags that are currently hidden.\n"
                "  all     — ignore the hide lists entirely."
            ),
            addItems=[SHOW_VISIBLE, SHOW_HIDDEN, SHOW_ALL],
        )
        self._show.setCurrentText(self._settings.value("show_mode", SHOW_VISIBLE))
        self._show.currentTextChanged.connect(self._on_show_changed)
        self.state.capture(self._show, SHOW_VISIBLE)

        self._unhide_all_btn = menu.add(
            "QPushButton",
            setText="Unhide all",
            setToolTip="Clear the hidden-UI and hidden-tag lists.",
        )
        self._unhide_all_btn.clicked.connect(self._on_unhide_all)

        # Hide inherited tags — those declared at registration time
        # (filename ``#tag`` suffix, source-directory tag passed to
        # ``register(tags=...)``, entry-point ``[extras]``) rather than
        # user-curated. Helps users focus on tags they've actually added.
        # Off by default to preserve current visual behavior.
        self._cb_hide_inherited_tags = menu.add(
            "QCheckBox",
            setObjectName="cb_hide_inherited_tags",
            setText="Hide inherited tags",
            setToolTip=(
                "Hide tags declared at registration time (filename "
                "suffix, source-dir tag, entry-point extras). Only "
                "user-added tags remain visible — both in row chips "
                "and in the tag chip-filter strip."
            ),
            setChecked=bool(self._settings.value("hide_inherited_tags", False)),
        )
        self._cb_hide_inherited_tags.toggled.connect(
            self._on_hide_inherited_tags_toggled
        )
        self.state.capture(self._cb_hide_inherited_tags, False)

        # ── Launch options ──
        menu.add("Separator", setTitle="Launch options:")
        self._launch_option_widgets = {}
        for key, label, default, tooltip in [
            ("frameless", "Frameless", True, "Remove window title bar."),
            (
                "translucent",
                "Translucent",
                True,
                "Use a translucent background.",
            ),
            (
                "restore_geometry",
                "Restore geometry",
                True,
                "Restore the last saved size/position.",
            ),
            (
                "on_top",
                "Always on top",
                True,
                "Keep the launched window above other windows so the on-top "
                "browser doesn't cover it.",
            ),
        ]:
            cb = menu.add(
                "QCheckBox",
                setObjectName=f"cb_launch_{key}",
                setText=label,
                setToolTip=tooltip,
                setChecked=bool(self._settings.value(f"opt_{key}", default)),
            )
            cb.toggled.connect(
                lambda v, k=key: self._settings.setValue(f"opt_{k}", bool(v))
            )
            self._launch_option_widgets[key] = cb
            self.state.capture(cb, default)
        # Backward-compatible attribute aliases used elsewhere in the class
        self._cb_frameless = self._launch_option_widgets["frameless"]
        self._cb_translucent = self._launch_option_widgets["translucent"]
        self._cb_restore = self._launch_option_widgets["restore_geometry"]
        self._cb_on_top = self._launch_option_widgets["on_top"]

        # Global default window persistence, owned by the UI handler so it
        # governs EVERY window (marking-menu popped, browser launched, already
        # open) rather than the next browser launch. "Default (context)" defers
        # to each window's own default (``UiHandler.default_persistence`` —
        # mayatk/blendertk tool panels declare themselves sticky there);
        # "sticky" forces a hide button (stays open) and "transient" a pin
        # button (auto-hides with the marking menu). Per-entry overrides (row
        # context menu) win over this.
        self._migrate_browser_persistence()
        persistence_labels = [label for _v, label in PERSISTENCE_CHOICES]
        self._cmb_persistence = menu.add(
            "QComboBox",
            setObjectName="cmb_persistence",
            setToolTip=(
                "Pin/hide behavior for every window, however it was opened. "
                "'Default' keeps each window's own default; 'Stay open' gives "
                "a hide button (persists until closed); 'Auto-hide' gives a "
                "pin button (hides when you leave the marking menu). Applies "
                "to open windows immediately. Right-click a row to override a "
                "single entry."
            ),
            addItems=persistence_labels,
        )
        self._cmb_persistence.setCurrentText(
            self._persistence_label(self._global_persistence())
        )
        self._cmb_persistence.currentTextChanged.connect(
            lambda label: self._set_global_persistence(self._persistence_value(label))
        )
        self.state.capture(self._cmb_persistence, persistence_labels[0])

        # Pin-button click behavior. Owned by the UI handler (it styles every
        # marking-menu / launched window), so the checkbox reads and writes
        # through it rather than the browser's own settings branch — that way
        # the change reaches already-open windows, not just the next launch.
        self._cb_pin_click_hides = menu.add(
            "QCheckBox",
            setObjectName="cb_pin_click_hides",
            setText="Pin button hides (1-click)",
            setToolTip=(
                "One-click dismiss: clicking the pin button hides the window "
                "in either state, so hovering it turns the button red (and "
                "shows the close icon while unpinned). Pin a window open by "
                "dragging its header.\n\n"
                "Off: click to pin, click again to unpin and hide."
            ),
            setChecked=self._pin_click_hides(),
        )
        self._cb_pin_click_hides.toggled.connect(self._on_pin_click_hides_toggled)
        self.state.capture(
            self._cb_pin_click_hides,
            bool(getattr(self._ui_handler(), "PIN_CLICK_HIDES_DEFAULT", True)),
        )

        # Tap-to-pin. Handler-owned for the same reason as the checkbox above:
        # the behavior belongs to every transient window, not just the ones
        # this browser launched.
        self._cb_pin_on_tap = menu.add(
            "QCheckBox",
            setObjectName="cb_pin_on_tap",
            setText="Tap opens, hold peeks",
            setToolTip=(
                "Let the marking-menu key do both. Let go of it right after a "
                "window opens and the window stays, pinned, like a normal "
                "window. Keep holding it and letting go still dismisses the "
                "window — a glance costs nothing.\n\n"
                "Off: letting go of the key always dismisses the window."
            ),
            setChecked=self._pin_on_tap(),
        )
        self._cb_pin_on_tap.toggled.connect(self._on_pin_on_tap_toggled)
        self.state.capture(
            self._cb_pin_on_tap,
            bool(getattr(self._ui_handler(), "PIN_ON_TAP_DEFAULT", False)),
        )

        # Theme: pulled through the switchboard's ``style`` proxy so any
        # theme added to ``StyleSheet`` shows up here automatically.
        theme_names = list(self.sb.style.themes.keys()) or ["dark", "light"]
        default_theme = "dark" if "dark" in theme_names else theme_names[0]
        self._cmb_theme = menu.add(
            "QComboBox",
            setObjectName="cmb_theme",
            setToolTip="Style template applied to the launched window.",
            addItems=theme_names,
        )
        saved_theme = self._settings.value("opt_theme", default_theme)
        if saved_theme not in theme_names:
            saved_theme = default_theme
        self._cmb_theme.setCurrentText(saved_theme)
        self._cmb_theme.currentTextChanged.connect(
            lambda v: self._settings.setValue("opt_theme", v)
        )
        self.state.capture(self._cmb_theme, default_theme)

        # ── Presets ──
        menu.add("Separator", setTitle="Presets:")
        # ``setup`` creates a ``cmb_presets`` WidgetComboBox in the menu
        # with Save / Rename / Delete / Open Folder built-in. Metadata
        # hooks pipe through our full state dict so presets carry
        # everything — not just the menu's own widgets.
        menu.presets.setup(
            preset_dir="uitk/switchboard_browser/presets",
            metadata_provider=self._export_preset_data,
            on_metadata_loaded=self._import_preset_data,
        )

    # ── Preset I/O ──────────────────────────────────────────────────────────

    def _export_preset_data(self) -> dict:
        """Serialize all browser state into a JSON-safe dict.

        Used as ``PresetManager.metadata_provider`` so the preset captures
        cross-menu state (search field, scope, filter toggle, hide lists,
        launch options, theme, …) rather than only widgets in the header menu.
        """
        return {
            "search": {
                "text": self._search.text(),
                "scope": self._search_filter.scope,
                "filter_enabled": self._search_filter.is_on,
            },
            "show_mode": self._show.currentText(),
            "active_tag_filters": sorted(self._active_tag_filters),
            "hidden_uis": sorted(self.hidden_uis),
            "hidden_tags": sorted(self.hidden_tags),
            "launch": {
                "frameless": self._cb_frameless.isChecked(),
                "translucent": self._cb_translucent.isChecked(),
                "restore_geometry": self._cb_restore.isChecked(),
                "on_top": self._cb_on_top.isChecked(),
                "theme": self._cmb_theme.currentText(),
                "persistence": self._global_persistence(),
                "pin_click_hides": self._pin_click_hides(),
                "pin_on_tap": self._pin_on_tap(),
            },
        }

    def _import_preset_data(self, data: dict) -> None:
        """Apply a loaded preset's state to all browser controls.

        Signals are blocked during application so we don't trigger a
        cascade of filter re-evaluations per widget; a single
        ``_apply_filter`` + ``_refresh_chips`` is fired at the end.
        """
        # PresetManager passes the full ``_meta`` dict (which includes
        # ``version`` and our keys). Tolerate missing keys for forward /
        # backward compat.

        # ── Search filter field ──
        # The field's text, scope, and on/off flag are owned by its
        # FilterOption. set_scope / set_on persist + sync the button visuals;
        # set_on uses emit=False so restoring the icon state doesn't re-fire the
        # toggled callback. Text is set with signals blocked (a single
        # _apply_filter runs at the end), so persist it explicitly. (A legacy
        # preset's separate "exclude" section is tolerated but ignored — the one
        # search field now covers exclusion inline via !term.)
        section = data.get("search") or {}
        filt = self._search_filter
        text = section.get("text")
        if text is not None:
            self._search.blockSignals(True)
            try:
                self._search.setText(text)
            finally:
                self._search.blockSignals(False)
            if filt.text_key is not None:
                self._settings.setValue(filt.text_key, text)
        scope = section.get("scope")
        if scope in SCOPES:
            filt.set_scope(scope)
        enabled = section.get("filter_enabled")
        if enabled is not None:
            filt.set_on(bool(enabled), emit=False)

        # ── Show combo + theme combo ──
        for combo, val in [
            (self._show, data.get("show_mode")),
            (self._cmb_theme, (data.get("launch") or {}).get("theme")),
        ]:
            if val is None:
                continue
            combo.blockSignals(True)
            try:
                combo.setCurrentText(val)
            finally:
                combo.blockSignals(False)
        self._settings.setValue("show_mode", self._show.currentText())
        # The theme combo is set with signals blocked above, so its
        # currentTextChanged->opt_theme persistence never fired. Persist it
        # explicitly (guarded on the preset carrying a theme) so the loaded
        # theme survives a restart like every other launch option.
        theme_val = (data.get("launch") or {}).get("theme")
        if theme_val is not None:
            self._settings.setValue("opt_theme", self._cmb_theme.currentText())

        # Active chip filters; cleared first so the loaded set is exact.
        self._active_tag_filters = set(data.get("active_tag_filters") or [])

        # Hide lists — these go through the property setters, which
        # persist to settings.
        if "hidden_uis" in data:
            self.hidden_uis = data["hidden_uis"]
        if "hidden_tags" in data:
            self.hidden_tags = data["hidden_tags"]

        # Launch checkboxes. ``pin_click_hides`` rides along here: its toggled
        # handler persists through the UI handler (not this browser's settings
        # branch), so a plain setChecked is the whole restore.
        launch = data.get("launch") or {}
        for key, cb in [
            ("frameless", self._cb_frameless),
            ("translucent", self._cb_translucent),
            ("restore_geometry", self._cb_restore),
            ("on_top", self._cb_on_top),
            ("pin_click_hides", self._cb_pin_click_hides),
            ("pin_on_tap", self._cb_pin_on_tap),
        ]:
            if key in launch:
                cb.setChecked(bool(launch[key]))

        # Global persistence default. The combo's change->settings write is
        # blocked, so persist explicitly (guarded on the preset carrying it).
        persistence = launch.get("persistence")
        if persistence in (
            PERSISTENCE_CONTEXT,
            PERSISTENCE_STICKY,
            PERSISTENCE_TRANSIENT,
        ):
            self._cmb_persistence.blockSignals(True)
            try:
                self._cmb_persistence.setCurrentText(
                    self._persistence_label(persistence)
                )
            finally:
                self._cmb_persistence.blockSignals(False)
            self._set_global_persistence(persistence)

        # Single consolidated refresh — chips, view filter.
        self._update_show_ui()
        self._refresh_chips()
        self._apply_filter()

    # ── Header-menu slots ───────────────────────────────────────────────────

    def _on_refresh_clicked(self) -> None:
        self._model._refresh()
        self._refresh_chips()
        self._apply_filter()
        self._update_footer_status()

    def _on_compile_all_clicked(self) -> None:
        """Pre-compile registered .ui files in a background thread.

        Default: only stale/missing _ui.py files are regenerated (hash check).
        With the option-box force toggle on, every .ui is rewritten regardless
        of hash. Footer reflects progress; the button is disabled while the
        job is running.
        """
        ui_paths = [
            entry.filepath for entry in self.sb.registry.ui_registry.named_tuples
        ]
        if not ui_paths:
            self.footer.setStatusText("Compile all: no UIs registered.")
            return

        force = self._compile_force
        job = UiCompiler.precompile_async(*ui_paths, force=force)
        if not job:
            if job.reason == "running":
                self.footer.setStatusText(
                    "Compile all: another compile is already in progress."
                )
            else:
                self.footer.setStatusText(
                    f"Compile all: nothing to do "
                    f"({len(ui_paths)} files already up-to-date — "
                    f"toggle the refresh icon to force-recompile)."
                )
            return

        import time as _time

        compile_count = job.stale
        started = _time.perf_counter()
        self._btn_compile_all.setEnabled(False)
        verb = "Force-compiling" if force else "Compiling"
        if force:
            self.footer.setStatusText(f"{verb} {compile_count} UIs…")
        else:
            self.footer.setStatusText(f"{verb} {compile_count} of {len(ui_paths)} UIs…")

        # Poll the worker thread without blocking the Qt event loop.
        # QTimer is the idiomatic choice; it stays on the GUI thread so
        # updating widgets is safe.
        timer = QtCore.QTimer(self)
        timer.setInterval(150)
        self._compile_poll_timer = timer

        def _check() -> None:
            if job.is_alive():
                return
            elapsed = _time.perf_counter() - started
            timer.stop()
            self._compile_poll_timer = None
            self._btn_compile_all.setEnabled(True)
            # Refresh — tags/metadata may have shifted during compile. Refresh
            # schedules a deferred ``_update_footer_status`` via QTimer.
            # singleShot(0) on dataChanged, so we must queue our final status
            # *after* that deferred update or it gets clobbered.
            self._on_refresh_clicked()
            done_verb = "force-recompiled" if force else "compiled"
            done_msg = (
                f"Compile all: done — {done_verb} {compile_count} "
                f"of {len(ui_paths)} UIs in {elapsed:.2f}s."
            )
            QtCore.QTimer.singleShot(
                0,
                lambda: self.footer.setStatusText(done_msg),
            )

        timer.timeout.connect(_check)
        timer.start()

    # ── Footer status ───────────────────────────────────────────────────────

    def _update_footer_status(self, *_args) -> None:
        """Refresh the footer status line.

        Two display modes:
          * No row selected → counts: registered / visible / showing.
          * Row selected → selected UI's name + path, with a "● visible"
            marker when the UI is currently shown.

        Plain text (not HTML): the Footer elides via ``QFontMetrics.elidedText``
        which doesn't understand markup — feeding it HTML risks cutting a
        tag mid-stream and breaking rendering. Visual hierarchy is carried
        by middle-dot / em-dash separators instead.
        """
        try:
            footer = self.footer
        except Exception:
            return

        idx = self._view.currentIndex() if hasattr(self, "_view") else None
        name = (
            idx.data(SwitchboardBrowserModel.NameRole)
            if idx is not None and idx.isValid()
            else None
        )

        if name:
            path = idx.data(SwitchboardBrowserModel.PathRole) or ""
            visible = bool(idx.data(SwitchboardBrowserModel.VisibleRole))
            # Editor rows have no backing file: no dangling separator.
            details = [d for d in ("● visible" if visible else "", path) if d]
            text = " — ".join([name, *details])
        else:
            registered = self._model.rowCount()
            visible_count = sum(
                1 for e in self._model._entries if self._model._is_visible(e)
            )
            shown = self._proxy.rowCount()
            text = (
                f"{registered} registered · {visible_count} visible · showing {shown}"
            )

        footer.setStatusText(text)

    # ── Slots ────────────────────────────────────────────────────────────────

    def _on_show_changed(self, value: str) -> None:
        self._settings.setValue("show_mode", value)
        self._update_show_ui()
        self._apply_filter()

    def _update_show_ui(self) -> None:
        self._unhide_all_btn.setVisible(self._show.currentText() == SHOW_HIDDEN)

    def _on_unhide_all(self) -> None:
        self.hidden_uis = set()
        self.hidden_tags = set()
        self._refresh_chips()
        self._apply_filter()

    def _on_hide_inherited_tags_toggled(self, checked: bool) -> None:
        self._settings.setValue("hide_inherited_tags", bool(checked))
        # Repaint rows (tag chips re-render) and refresh chip strip.
        if hasattr(self, "_view") and self._view.model() is not None:
            top = self._model.index(0, 0)
            bot = self._model.index(
                self._model.rowCount() - 1, self._model.COLUMN_COUNT - 1
            )
            if top.isValid() and bot.isValid():
                self._model.dataChanged.emit(top, bot)
        self._refresh_chips()

    @property
    def hide_inherited_tags(self) -> bool:
        return bool(self._settings.value("hide_inherited_tags", False))

    def _visible_tags(self) -> List[str]:
        """Tags from currently visible (post-filter) rows.

        Active tag filters are forcibly included so the user can always toggle
        them off — otherwise an active chip with no remaining matches would
        vanish from the strip and become un-removable.

        Honors the "Hide inherited tags" toggle — those tags are dropped
        from the chip strip but remain in the underlying row data
        (so filters set programmatically still work).
        """
        seen: Set[str] = set(self._active_tag_filters)
        hide_inherited = self.hide_inherited_tags
        for r in range(self._proxy.rowCount()):
            idx = self._proxy.index(r, 0)
            if hide_inherited:
                # Only user-added file tags surface in the chip strip.
                tags = idx.data(SwitchboardBrowserModel.FileTagsRole) or []
            else:
                tags = idx.data(SwitchboardBrowserModel.TagsRole) or []
            seen.update(tags)
        return sorted(seen)

    def _refresh_chips(self) -> None:
        # Clear all items (chip buttons + trailing stretch)
        while self._chip_layout.count():
            item = self._chip_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()
        self._chip_buttons.clear()
        # Chips reflect the currently visible rows so the user only sees
        # tags that are useful to refine the current view further. Active
        # filters are always included via :meth:`_visible_tags`.
        for t in self._visible_tags():
            btn = QtWidgets.QPushButton(f"#{t}")
            btn.setCheckable(True)
            btn.setChecked(t in self._active_tag_filters)
            btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, tag=t, b=btn: self._on_chip_context_menu(tag, b, pos)
            )
            btn.toggled.connect(
                lambda checked, tag=t: self._on_chip_toggled(tag, checked)
            )
            self._chip_layout.addWidget(btn)
            self._chip_buttons[t] = btn
        self._chip_layout.addStretch(1)

    def _on_chip_toggled(self, tag: str, checked: bool) -> None:
        if checked:
            self._active_tag_filters.add(tag)
        else:
            self._active_tag_filters.discard(tag)
        self._apply_filter()

    def _on_chip_context_menu(self, tag: str, btn: QtWidgets.QPushButton, pos) -> None:
        menu = QtWidgets.QMenu(self)
        # Free the menu (and its actions/lambda connections) when it closes;
        # otherwise it lingers as a child of self for the browser's lifetime.
        menu.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        if tag in self.hidden_tags:
            act = menu.addAction(f"Unhide tag #{tag}")
            act.triggered.connect(lambda: self._toggle_hide_tag(tag, hide=False))
        else:
            act = menu.addAction(f"Hide all UIs tagged #{tag}")
            act.triggered.connect(lambda: self._toggle_hide_tag(tag, hide=True))
        menu.exec_(btn.mapToGlobal(pos))

    def _toggle_hide_tag(self, tag: str, hide: bool) -> None:
        s = self.hidden_tags
        if hide:
            s.add(tag)
        else:
            s.discard(tag)
        self.hidden_tags = s
        self._apply_filter()

    def _on_row_context_menu(self, pos) -> None:
        idx = self._view.indexAt(pos)
        if not idx.isValid():
            return
        name = idx.data(SwitchboardBrowserModel.NameRole)
        tags = idx.data(SwitchboardBrowserModel.TagsRole) or []
        path = idx.data(SwitchboardBrowserModel.PathRole)

        menu = QtWidgets.QMenu(self)
        # Free the menu (and its actions/lambda connections) when it closes;
        # otherwise it lingers as a child of self for the browser's lifetime.
        menu.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        if path and path.lower().endswith(".ui") and os.path.isfile(path):
            designer_act = menu.addAction("Open in Designer")
            designer_act.triggered.connect(
                lambda _=False, p=path: self._open_in_designer(p)
            )
        # Standalone launch snippet (a Python prompt, a Maya shelf button),
        # rendered by the entry's own handler from this browser's launch
        # options. Rendered now: an entry whose handler can't spell one
        # simply gets no action.
        code = self._launch_code(name)
        if code:
            copy_act = menu.addAction("Copy launch code")
            copy_act.triggered.connect(
                lambda _=False, n=name, c=code: self._copy_launch_code(n, c)
            )
        if not menu.isEmpty():
            menu.addSeparator()

        # Tag editing happens inline — double-click the Tags cell, or
        # pick this entry to open the same inline editor programmatically.
        # No modal popup: the QLineEdit delegate is the single edit path.
        tags_idx = self._proxy.index(idx.row(), SwitchboardBrowserModel.COL_TAGS)
        if (
            self._model.flags(self._proxy.mapToSource(tags_idx))
            & QtCore.Qt.ItemIsEditable
        ):
            edit_act = menu.addAction("Edit tags")
            edit_act.triggered.connect(lambda _=False, i=tags_idx: self._view.edit(i))
            menu.addSeparator()

        # ── Open as (per-entry window persistence override) ──
        # Persistence is the UI handler's to resolve; other handlers' windows
        # (editors, external apps) ignore it, so their rows don't offer it.
        entry = self._model.entry_for_name(name)
        if entry is not None and entry.handler is self._ui_handler():
            current = self._entry_persistence_override(name)
            # The stored values ("context"/"sticky"/"transient") double as the
            # short names shown after "Default", so no separate mapping is needed.
            open_as = menu.addMenu("Open as")
            for label, mode in (
                (f"Default ({self._effective_default(name)})", None),
                ("Sticky — stays open (hide button)", PERSISTENCE_STICKY),
                ("Transient — hides on leave (pin button)", PERSISTENCE_TRANSIENT),
            ):
                act = open_as.addAction(label)
                act.setCheckable(True)
                act.setChecked(current == mode)
                act.triggered.connect(
                    lambda _=False, n=name, m=mode: self._set_entry_persistence(n, m)
                )
            menu.addSeparator()

        if name in self.hidden_uis:
            unh = menu.addAction("Unhide this UI")
            unh.triggered.connect(lambda: self._toggle_hide_ui(name, hide=False))
        else:
            h = menu.addAction("Hide this UI")
            h.triggered.connect(lambda: self._toggle_hide_ui(name, hide=True))

        if tags:
            menu.addSeparator()
            for t in tags:
                if t in self.hidden_tags:
                    a = menu.addAction(f"Unhide tag #{t}")
                    a.triggered.connect(
                        lambda _=False, tt=t: self._toggle_hide_tag(tt, hide=False)
                    )
                else:
                    a = menu.addAction(f"Hide by tag #{t}")
                    a.triggered.connect(
                        lambda _=False, tt=t: self._toggle_hide_tag(tt, hide=True)
                    )

        menu.exec_(self._view.viewport().mapToGlobal(pos))

    def _open_in_designer(self, path: str) -> None:
        """Launch Qt Designer with *path* preloaded.

        Through :meth:`uitk.DesignerPlugin.launch` first: the ``pyside6-designer``
        wrapper with uitk's widgets published (``PYSIDE_DESIGNER_PLUGINS``; on
        Linux the wrapper also preloads libpython, without which no Python
        widget plug-in loads). Else the bundled designer of the imported Qt
        binding (PySide2), then common executable names via
        :class:`pythontk.AppLauncher` -- a plain Designer, uitk widgets absent.
        """
        from uitk.designer._designer import DesignerPlugin

        try:
            DesignerPlugin.launch(path, wait=False)
            return
        except (FileNotFoundError, OSError):
            pass
        candidates: List[str] = []
        # Bundled designer next to PySide6/PySide2. Layout varies by
        # platform: Windows wheels ship designer.exe at the package
        # root; Linux wheels ship designer under Qt/bin/.
        bundled_rel = (
            "designer.exe",
            "designer",
            os.path.join("Qt", "bin", "designer"),
        )
        for mod_name in ("PySide6", "PySide2"):
            try:
                mod = __import__(mod_name)
                mod_dir = os.path.dirname(getattr(mod, "__file__", "") or "")
            except Exception:
                continue
            if not mod_dir:
                continue
            for rel in bundled_rel:
                bundled = os.path.join(mod_dir, rel)
                if os.path.isfile(bundled):
                    candidates.append(bundled)
                    break
        candidates.extend(["pyside6-designer", "pyside2-designer", "designer"])

        for app in candidates:
            if ptk.AppLauncher.find_app(app) and ptk.AppLauncher.launch(
                app, args=[path]
            ):
                return

        QtWidgets.QMessageBox.warning(
            self,
            "Designer not found",
            "Qt Designer could not be located or failed to launch. Install "
            "PySide6 (which bundles pyside6-designer) or add Designer to PATH.",
        )

    def _toggle_hide_ui(self, name: str, hide: bool) -> None:
        s = self.hidden_uis
        if hide:
            s.add(name)
        else:
            s.discard(name)
        self.hidden_uis = s
        self._apply_filter()

    def _on_double_click(self, index) -> None:
        # Double-click on Tags column kicks off inline editing — handled by
        # the view's edit triggers; don't launch in that case.
        if index.column() == SwitchboardBrowserModel.COL_TAGS:
            return
        # Action / close columns have their own buttons; ignore double-click.
        if index.column() in (
            SwitchboardBrowserModel.COL_ACTION,
            SwitchboardBrowserModel.COL_CLOSE,
        ):
            return
        # Name column: launch / focus.
        self._on_action_clicked()

    def _on_action_clicked(self) -> None:
        idx = self._view.currentIndex()
        if not idx.isValid():
            return
        name = idx.data(SwitchboardBrowserModel.NameRole)
        if not name:
            return
        if idx.data(SwitchboardBrowserModel.VisibleRole):
            self._focus(name)
        else:
            self._launch(name)

    def _on_model_data_changed(self, *_args) -> None:
        # A row's tags or visibility changed; chip set may need to add/drop
        # entries, and per-row buttons may need their enabled-state updated.
        # All deferred to coalesce bursts (registration of many UIs, rapid
        # signal volleys, etc.) into a single rebuild per event-loop turn.
        self._defer_full_refresh()

    def _defer_full_refresh(self, *_args) -> None:
        # Coalesce multiple updates within an event-loop turn into one
        # rebuild. Guard prevents stacking timers when many signals fire
        # back-to-back.
        #
        # When the browser is hidden, the work is invisible — but the
        # full refresh chain (re-pull entries, recreate every row's
        # buttons via setIndexWidget) is expensive enough to be felt
        # across the host app. Mark dirty + bail; showEvent does one
        # consolidated refresh when the user next opens us.
        if not self.isVisible():
            self._dirty_while_hidden = True
            return
        if getattr(self, "_full_refresh_pending", False):
            return
        self._full_refresh_pending = True
        QtCore.QTimer.singleShot(0, self._do_full_refresh)

    def _do_full_refresh(self) -> None:
        self._full_refresh_pending = False
        self._refresh_chips()
        self._refresh_row_widgets()
        self._update_footer_status()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # While hidden the model might have processed entries-changed
        # signals without triggering row rebuilds (see ``_defer_full_refresh``).
        # Bring the view fully up to date on show.
        if getattr(self, "_dirty_while_hidden", False):
            self._dirty_while_hidden = False
            self._do_full_refresh()

    def _select_first_row(self) -> None:
        if self._proxy.rowCount() == 0:
            return
        idx = self._proxy.index(0, 0)
        self._view.setCurrentIndex(idx)

    # ── Per-row icon buttons (Launch/Focus + Close) ──────────────────────────

    def _refresh_row_widgets(self) -> None:
        """(Re)install action + close icon buttons for every visible row.

        ``QTableView.setIndexWidget`` is keyed by proxy model index, but
        proxy filtering shifts the visible rows. Each refresh replaces any
        existing widgets with fresh instances — Qt deletes the old ones —
        so connections never accumulate.

        Each button is wrapped in a centered container so the cell's
        selection highlight looks clean around it (vs. a button anchored
        to the top-left of a wider cell).
        """
        if not hasattr(self, "_view"):
            return
        from uitk.managers.icon_manager import IconManager

        for r in range(self._proxy.rowCount()):
            proxy_idx_action = self._proxy.index(r, SwitchboardBrowserModel.COL_ACTION)
            proxy_idx_close = self._proxy.index(r, SwitchboardBrowserModel.COL_CLOSE)
            name = proxy_idx_action.data(SwitchboardBrowserModel.NameRole)
            visible = bool(proxy_idx_action.data(SwitchboardBrowserModel.VisibleRole))

            # Action icons:
            #   visible → "eye" (focus the window)
            #   not visible → "open_external" (open it as its own window),
            #     which reads more clearly than a generic transport "play"
            #     for an action that pops a new top-level window.
            action_btn = self._make_icon_btn()
            IconManager.set_icon(
                action_btn,
                "eye" if visible else "open_external",
                size=(14, 14),
            )
            action_btn.setToolTip(f"Focus {name}" if visible else f"Launch {name}")
            if visible:
                action_btn.clicked.connect(lambda _=False, n=name: self._focus(n))
            else:
                action_btn.clicked.connect(lambda _=False, n=name: self._launch(n))
            self._view.setIndexWidget(proxy_idx_action, self._wrap_centered(action_btn))

            # Close: only enabled when the UI is currently visible
            close_btn = self._make_icon_btn()
            IconManager.set_icon(close_btn, "close", size=(12, 12))
            close_btn.setToolTip(f"Hide {name}" if visible else "")
            close_btn.setEnabled(visible)
            close_btn.clicked.connect(lambda _=False, n=name: self._close_ui(n))
            self._view.setIndexWidget(proxy_idx_close, self._wrap_centered(close_btn))

    def _make_icon_btn(self) -> QtWidgets.QPushButton:
        # Delegates to EditorPanel.icon_button (shared template). Slightly
        # smaller (22 vs the 24 default) to match this table's row height.
        return self.icon_button(size=22)

    @staticmethod
    def _wrap_centered(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(widget)
        return container

    def _apply_filter(self) -> None:
        # Filter invalidates immediately so tests/clients can read row
        # state synchronously. Row-widget rebuild (which is the expensive
        # part, ~2 buttons per visible row) is debounced via
        # ``layoutChanged`` -> ``_defer_full_refresh``.
        self._proxy.invalidate()

    # ── Filter predicate (called by proxy) ───────────────────────────────────

    @staticmethod
    def _haystack(name: str, all_tags: Set[str], scope: str) -> str:
        if scope == SCOPE_NAME:
            return name
        if scope == SCOPE_TAGS:
            return " ".join(sorted(all_tags))
        return name + " " + " ".join(sorted(all_tags))

    def _row_passes_filter(self, name: str, all_tags: Set[str]) -> bool:
        # Hide-mode predicate
        mode = self._show.currentText()
        is_hidden = (name in self.hidden_uis) or bool(all_tags & self.hidden_tags)
        if mode == SHOW_VISIBLE and is_hidden:
            return False
        if mode == SHOW_HIDDEN and not is_hidden:
            return False

        # Active chip filter (AND across selected chips)
        if self._active_tag_filters and not self._active_tag_filters <= all_tags:
            return False

        # Text filter — the FilterOption returns None when its toggle is off or
        # the field is empty (match everything). ``negate_prefix`` lets a
        # ``!term`` carve out an inline exclusion, so one field covers both
        # include and exclude (e.g.  anim, !test).
        patterns = self._search_filter.patterns()
        if patterns:
            haystack = self._haystack(name, all_tags, self._search_filter.scope)
            if not ptk.filter_list(
                [haystack],
                inc=patterns,
                ignore_case=True,
                negate_prefix=NEGATE_PREFIX,
            ):
                return False

        return True
