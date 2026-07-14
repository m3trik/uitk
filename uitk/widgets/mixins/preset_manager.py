# !/usr/bin/python
# coding=utf-8
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union, TYPE_CHECKING

from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk

if TYPE_CHECKING:
    from uitk.widgets.mixins.state_manager import StateManager

_log = logging.getLogger(__name__)


class PresetManager(ptk.LoggingMixin):
    """Manages named presets for widget state, stored as external JSON files.

    Supports two modes:

    **MainWindow mode** (with ``StateManager``)::

        mgr = PresetManager(parent=window, state=window.state)
        mgr.save("my_preset")
        mgr.load("my_preset")

    **Standalone mode** (explicit widget list, no ``StateManager``)::

        mgr = PresetManager.from_widgets(
            preset_dir="~/.myapp/presets",
            widgets=[chk_a, spin_b, line_c],
        )
        mgr.save("my_preset")
        mgr.load("my_preset")

    **Menu mode** (zero-ceremony — just enable presets on the menu)::

        widget.menu.add_presets = True                        # auto-derived dir
        widget.menu.add_presets = "~/.myapp/presets"           # custom dir

    In all modes, ``wire_combo`` is available for advanced use-cases
    where a custom combo is needed::

        mgr.wire_combo(combo, on_loaded=refresh_callback)

    **Flexible preset_dir formats**:

    ``preset_dir`` accepts any of:

    - **Full path** (``str`` or ``Path``):
      ``Path.home() / ".myapp" / "presets"``
    - **Tilde string**: ``"~/.myapp/presets"``
    - **Environment variables**: ``"$HOME/.myapp/presets"``
    - **Relative / short name**: ``"myapp/presets"`` — resolved
      under ``QStandardPaths.writableLocation(AppConfigLocation)``

    Preset files are flat key-value JSON::

        {
            "_meta": {"version": 1},
            "myCheckBox": true,
            "mySpinBox": 42,
            "myComboBox": 2
        }

    Attributes:
        parent: The root widget (typically MainWindow) whose children are managed.
        state: The StateManager instance used for value get/set operations.
        preset_dir: Directory where preset JSON files are stored.
    """

    PRESET_VERSION = 1

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        state: Optional["StateManager"] = None,
        preset_dir: Optional[Path] = None,
        widgets: Optional[List[QtWidgets.QWidget]] = None,
        log_level: str = "WARNING",
        builtin_dir: Optional[Union[str, Path]] = None,
        value_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        value_applier: Optional[Callable[[Dict[str, Any]], int]] = None,
        modified_value_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        super().__init__()
        self.set_log_level(log_level)
        self.parent = parent
        self.state = state
        self._explicit_widgets = list(widgets) if widgets is not None else None
        self._excluded_widgets: Set[QtWidgets.QWidget] = set()

        # Semantic-preset mode (opt-in). When both callbacks are set, presets
        # are a plain ``{semantic_key: value}`` dict supplied by *value_provider*
        # on save and handed to *value_applier* on load -- NOT raw widget-state
        # keyed by ``objectName``. This lets a panel persist the SAME semantic
        # run-template the headless CLI reads (one :class:`pythontk.PresetStore`,
        # two front-ends), instead of GUI-only widget snapshots. The store
        # (built-in + user tiers) and :meth:`wire_combo` are unchanged.
        #
        # RESTORE CONTRACT: on wire, the combo restores the active preset's
        # *selection only* -- values are never re-applied automatically. In
        # widget-state mode that's complete (widgets reload from per-widget
        # QSettings session state); in semantic mode there is NO session-state
        # fallback, so if the applied values live outside the panel (a
        # registry, DCC state such as hotkeys/keymaps), the OWNING app must
        # re-apply the active preset itself at startup -- e.g. tentacle calls
        # ``Macros.apply_saved_macros()`` from its DCC entry points at launch.
        # Skipping that step yields "the combo shows the preset name but its
        # values aren't in effect until Refresh".
        self.value_provider = value_provider
        self.value_applier = value_applier
        # Optional *cheaper* capture used only by the dirty-check (``is_modified``);
        # falls back to ``value_provider`` when None. Lets an editor whose full
        # capture is expensive (e.g. the hotkey editor would build every
        # registered UI) compare "modified" against a cheap subset — typically
        # the already-loaded UIs — while ``save`` still captures everything.
        self.modified_value_provider = modified_value_provider

        if preset_dir is not None:
            self._preset_dir = self._resolve_preset_dir(preset_dir)
        else:
            self._preset_dir = None

        # Path whose legacy-migration + mkdir have already been run, so repeated
        # ``preset_dir`` reads (the ``_store`` property rebuilds per access, and
        # ``source()`` is called per preset name while marking built-ins) don't
        # re-hit the filesystem on every access. Writes self-heal the dir at the
        # PresetStore layer, so reads never need to re-ensure it.
        self._ensured_dir = None

        # Read-only, shipped presets (a panel's ``presets/`` dir by convention,
        # passed explicitly). ``None`` / a missing dir ⇒ the built-in tier is
        # simply absent and only user presets show. Layered under user presets by
        # the shared :class:`pythontk.PresetStore` (a user preset of the same name
        # shadows the built-in), so the GUI and any headless path see one set.
        self._builtin_dir = self._resolve_builtin_dir(builtin_dir)

        self.metadata_provider: Optional[Callable[[], dict]] = None
        self.on_metadata_loaded: Optional[Callable[[dict], None]] = None

        self._on_change_callbacks = []

        # Pending inline-edit action for wire_combo's Save/Rename flow
        # ("save" / "rename" / None). Declared here rather than created
        # dynamically inside the closure so the attribute always exists.
        self._pending_preset_action: Optional[str] = None

        # Active-preset / modified tracking. ``_active_snapshot`` is the stored
        # value dict (minus ``_meta``) of the active preset, captured on load
        # (or when ``active_preset`` is assigned for a session restore), and is
        # the baseline :meth:`is_modified` compares the live values against.
        # ``_modified`` caches the last computed dirty state so observers only
        # fire on a real transition. ``_value_change_widgets`` tracks widgets
        # already wired for live dirty detection (connect-once).
        self._active_snapshot: Optional[Dict[str, Any]] = None
        self._modified: Optional[bool] = None
        self._on_modified_callbacks: List[Callable[[bool], None]] = []
        self._value_change_widgets: Set[int] = set()

        # Capture scope + name-based allow/deny lists (see ``scope``, ``include``,
        # ``exclude``). ``_scope`` selects which widget set a save/load operates
        # on; ``_include_names`` (an allowlist; ``None`` = no allowlist) and
        # ``_exclude_names`` (a denylist) refine it by ``objectName``. The
        # always-excluded preset combo lives in ``_excluded_widgets`` (instances)
        # and is filtered independently. ``_window`` caches the resolved owning
        # MainWindow for ``"window"`` scope so its registered-widget set and
        # ``StateManager`` are reused across calls.
        self._scope: str = "auto"
        self._include_names: Optional[Set[str]] = None
        self._exclude_names: Set[str] = set()
        self._window: Optional[QtWidgets.QWidget] = None

    @staticmethod
    def _resolve_preset_dir(raw: Union[str, Path]) -> Path:
        """Resolve a *preset_dir* value to an absolute `Path`.

        Accepts several convenient forms:

        - **Full path** (``str`` or ``Path``): used as-is after
          environment-variable and tilde expansion.
        - **Tilde string**: ``"~/.myapp/presets"`` — ``~`` is expanded
          via `Path.expanduser`.
        - **Environment variables**: ``"$HOME/.myapp/presets"`` or
          ``"%APPDATA%/myapp/presets"`` — expanded via
          `os.path.expandvars`.
        - **Relative / short name**: ``"mayatk/reference_manager"`` —
          resolved under :func:`get_presets_root` (default:
          ``<QStandardPaths.AppConfigLocation>``).

        Returns:
            An absolute `Path`.
        """
        p = Path(os.path.expandvars(str(raw))).expanduser()
        if not p.is_absolute():
            p = get_presets_root() / p
        return p

    @staticmethod
    def _resolve_builtin_dir(raw: Optional[Union[str, Path]]) -> Optional[Path]:
        """Resolve a *builtin_dir* (``~`` / env expanded), or ``None``.

        A relative value is taken as-is (relative to CWD) — built-in dirs are
        repo paths the caller knows, not consolidated-root short names.
        """
        if raw is None:
            return None
        return Path(os.path.expandvars(str(raw))).expanduser()

    @property
    def _store(self) -> "ptk.PresetStore":
        """The two-tier backing store (built-in + user).

        Built fresh each access (construction is trivial) off the resolved
        :attr:`preset_dir` (the migrated user tier) and :attr:`_builtin_dir`, so
        discovery and file I/O share one implementation with the headless
        ``pythontk.PresetStore`` and stay correct if either dir is reassigned.
        """
        user_dir = self.preset_dir
        return ptk.PresetStore(
            user_dir.name, package="uitk",
            builtin_dir=self._builtin_dir, user_dir=user_dir,
        )

    @classmethod
    def from_widgets(
        cls,
        preset_dir,
        widgets: List[QtWidgets.QWidget],
        builtin_dir: Optional[Union[str, Path]] = None,
    ) -> "PresetManager":
        """Create a standalone PresetManager for an explicit list of widgets.

        This mode does not require a MainWindow or StateManager.  Widget
        values are read/written using standard Qt property accessors.

        Parameters:
            preset_dir: Directory for storing preset JSON files (str or Path).
            widgets: The QWidgets whose values should be captured/restored.

        Returns:
            A PresetManager instance.
        """
        return cls(preset_dir=preset_dir, widgets=widgets, builtin_dir=builtin_dir)

    def setup(
        self,
        preset_dir=None,
        widgets: Optional[List[QtWidgets.QWidget]] = None,
        on_loaded=None,
        metadata_provider: Optional[Callable[[], dict]] = None,
        on_metadata_loaded: Optional[Callable[[dict], None]] = None,
        builtin_dir: Optional[Union[str, Path]] = None,
        value_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        value_applier: Optional[Callable[[Dict[str, Any]], int]] = None,
    ) -> "PresetManager":
        """Configure and optionally auto-wire a preset combo.

        This is the post-creation counterpart of ``from_widgets``.  It is
        intended for use with the lazy ``menu.presets`` / ``window.presets``
        namespaces where the instance is created before the caller knows
        which widgets or directory to use.

        When *widgets* is omitted and the manager's parent has a
        ``get_items()`` method (e.g. a ``Menu``), widgets are
        auto-discovered at save/load time — no explicit list needed.

        When the parent is a ``Menu``, a ``ComboBox`` is automatically
        created and wired as the preset selector — no manual ``wire_combo``
        call is required.

        Parameters:
            preset_dir: Directory for storing preset JSON files
                (str or Path).  When omitted, the directory is
                auto-derived from the parent window's name under
                ``QStandardPaths.writableLocation(AppConfigLocation)``.
            widgets: Optional explicit list of QWidgets to capture/restore.
                If omitted, widgets are discovered from the parent.
            on_loaded: Optional callable (no args) invoked after a preset
                is successfully loaded.  When omitted, widget signals are
                left unblocked so normal slot handlers fire naturally.

        Returns:
            *self*, so calls can be chained.
        """
        if preset_dir is not None:
            self._preset_dir = self._resolve_preset_dir(preset_dir)
        if builtin_dir is not None:
            self._builtin_dir = self._resolve_builtin_dir(builtin_dir)
        if widgets is not None:
            self._explicit_widgets = list(widgets)
        if metadata_provider is not None:
            self.metadata_provider = metadata_provider
        if on_metadata_loaded is not None:
            self.on_metadata_loaded = on_metadata_loaded
        if value_provider is not None:
            self.value_provider = value_provider
        if value_applier is not None:
            self.value_applier = value_applier

        # Auto-create and wire a preset combo when parent is a Menu
        if hasattr(self.parent, "add") and hasattr(self.parent, "get_items"):
            from uitk.widgets.comboBox import ComboBox

            combo = self.parent.add(
                ComboBox,
                setObjectName="cmb_presets",
                setToolTip="Load a saved configuration preset.",
            )
            self.wire_combo(combo, on_loaded=on_loaded)

        return self

    @property
    def preset_dir(self) -> Path:
        """The directory where preset files are stored.

        Defaults to ``<presets_root>/uitk/<window_name>/`` where
        *presets_root* is :func:`get_presets_root`. Created on first
        access. When no *parent* is set (standalone mode), *preset_dir*
        **must** be provided explicitly.

        Can also be set to a ``str`` or ``Path``; tilde and
        environment-variable expansion are applied automatically, and
        relative values resolve under :func:`get_presets_root`.

        On first access, if the resolved directory maps to a known
        legacy location (see :data:`_LEGACY_PRESET_PATHS`), existing
        presets are copied in once so the consolidation is invisible
        to long-time users.
        """
        if self._preset_dir is None:
            if self.parent is not None:
                window = (
                    self.parent.window()
                    if hasattr(self.parent, "window")
                    else self.parent
                )
                name = (
                    (window.objectName() if window else None)
                    or self.parent.objectName()
                    or "default"
                )
                # Strip switchboard instance suffixes (e.g. "name#1")
                name = name.split("#")[0]
                self._preset_dir = get_presets_root() / "uitk" / name
            else:
                raise ValueError(
                    "preset_dir must be provided for standalone PresetManager"
                )

        # Ensure (migrate + create) once per resolved path. A reassigned dir
        # has a different value than ``_ensured_dir`` and re-ensures; writes
        # self-heal the dir at the PresetStore layer (its save/active-write both
        # mkdir), so skipping the per-read FS calls is safe.
        if self._ensured_dir != self._preset_dir:
            _maybe_migrate_legacy(self._preset_dir)
            _maybe_migrate_renamed_domain(self._preset_dir)
            self._preset_dir.mkdir(parents=True, exist_ok=True)
            self._ensured_dir = self._preset_dir
        return self._preset_dir

    @preset_dir.setter
    def preset_dir(self, value) -> None:
        """Set the preset directory (accepts str, Path, or None for auto-derive)."""
        if value is not None:
            self._preset_dir = self._resolve_preset_dir(value)
        else:
            self._preset_dir = None

    def on_change(self, callback) -> None:
        """Register a callback invoked when presets are modified.

        Parameters:
            callback: A callable with no arguments.
        """
        self._on_change_callbacks.append(callback)

    def _notify_change(self) -> None:
        """Invoke all registered change callbacks."""
        for cb in self._on_change_callbacks:
            try:
                cb()
            except Exception as e:
                self.logger.debug(f"Preset change callback error: {e}")

    # ------------------------------------------------------------------
    # Capture scope + include / exclude
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Active preset + modified ("dirty") tracking
    # ------------------------------------------------------------------

    @property
    def active_preset(self) -> Optional[str]:
        """Name of the preset currently in use, or ``None``.

        Persisted (per :attr:`preset_dir`) via the backing store's ``.active``
        sidecar, so it survives between sessions. Assigning a name updates the
        modified-tracking baseline **without applying any values** — widgets
        restore themselves from session state, so only the *selection* needs
        restoring. Assign ``None`` to clear.
        """
        return self._store.active

    @active_preset.setter
    def active_preset(self, name: Optional[str]) -> None:
        self._store.active = name
        self._resync_active()

    def _resync_active(self) -> None:
        """Re-read the active preset's stored values as the dirty baseline.

        Used after the active pointer changes for a reason *other* than a load
        (session restore, delete, rename) — values are not applied, only the
        baseline + marker are refreshed.
        """
        active = self._store.active
        if not active:
            self._active_snapshot = None
        else:
            try:
                self._active_snapshot = self._strip_meta(self._store.load(active))
            except (KeyError, ValueError, OSError):
                self._active_snapshot = None
        self.refresh_modified_state()

    def is_modified(self) -> bool:
        """True when live values diverge from the active preset's stored values.

        Compares only keys present in *both* the stored preset and the current
        snapshot (overlay semantics — a shared CLI preset may carry knobs this
        panel doesn't surface, and vice-versa). ``False`` when no preset is
        active.
        """
        if not self._active_snapshot:
            return False
        current = self._capture_values(for_modified=True)
        for key, stored in self._active_snapshot.items():
            if key in current and self._normalize(current[key]) != self._normalize(
                stored
            ):
                return True
        return False

    @staticmethod
    def _normalize(value: Any) -> str:
        """JSON-normalize for comparison (tuple/list parity, stable dict order)."""
        try:
            return json.dumps(value, sort_keys=True, default=str)
        except TypeError:
            return repr(value)

    def on_modified_changed(self, callback: Callable[[bool], None]) -> None:
        """Register *callback(bool)* invoked when the modified state flips."""
        self._on_modified_callbacks.append(callback)

    def refresh_modified_state(self) -> bool:
        """Recompute the modified state; notify observers on a transition.

        Cheap to call on every value change — observers fire only when the
        boolean actually changes. Returns the current modified flag.
        """
        modified = self.is_modified()
        if modified != self._modified:
            self._modified = modified
            for cb in self._on_modified_callbacks:
                try:
                    cb(modified)
                except Exception as e:
                    self.logger.debug(f"Modified-state callback error: {e}")
        return modified

    def connect_value_widgets(self) -> None:
        """Wire managed widgets' change signals so the dirty marker updates live.

        Best-effort and connect-once per widget. No-op in semantic mode (no
        managed widgets — the caller wires its own param widgets, e.g. the
        bridge via :func:`uitk.bridge.spec.connect_changed`). Called by
        :meth:`wire_combo` so the menu / standalone paths get a live marker for
        free.
        """
        if self.value_provider is not None:
            return
        for widget in self._get_widgets():
            wid = id(widget)
            if wid in self._value_change_widgets:
                continue
            signal = self._value_change_signal(widget)
            if signal is None:
                continue
            try:
                signal.connect(lambda *a: self.refresh_modified_state())
                self._value_change_widgets.add(wid)
            except (RuntimeError, TypeError):
                pass

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(
        self,
        name: str,
        scope: Optional[QtWidgets.QWidget] = None,
    ) -> Path:
        """Save the current widget values as a named preset.

        Parameters:
            name: The preset name (used as the filename stem).
            scope: Optional container widget to limit which children are
                captured. Defaults to the entire parent window.

        Returns:
            The Path to the saved JSON file.
        """
        data: Dict[str, Any] = {"_meta": {"version": self.PRESET_VERSION}}

        if self.metadata_provider is not None:
            data["_meta"].update(self.metadata_provider())

        # ``_capture_values`` is the single source of truth for "what the live
        # state is" -- shared with the modified-state comparison so save and the
        # dirty marker can never drift apart.
        data.update(self._capture_values(scope))

        # Delegate the write to the store — it always targets the user tier
        # (built-ins are read-only; saving a built-in's name creates a user
        # override that shadows it, i.e. the "duplicate to edit" flow).
        filepath = self._store.save(name, data)
        self.logger.debug(
            f"Saved preset '{name}' ({len(data) - 1} widgets) -> {filepath}"
        )
        self._notify_change()
        # Saving makes the just-written values the new baseline for *name*; if
        # it's the active preset the modified marker should clear.
        if self.active_preset == name:
            self._active_snapshot = self._strip_meta(data)
            self.refresh_modified_state()
        return filepath

    def _capture_values(
        self,
        scope: Optional[QtWidgets.QWidget] = None,
        *,
        for_modified: bool = False,
    ) -> Dict[str, Any]:
        """Snapshot the current managed values as a flat ``{key: value}`` dict.

        Single source of truth for what :meth:`save` persists and what
        :meth:`is_modified` compares the active preset against. In semantic mode
        the keys are :class:`AttributeSpec` names from *value_provider*;
        otherwise they are widget ``objectName`` s. Only JSON-serializable,
        non-``None`` values are kept (matching what reaches disk).

        When *for_modified* is set and a :attr:`modified_value_provider` is
        configured, that cheaper provider is used instead of *value_provider*,
        so the dirty-check can compare against a subset (e.g. only the
        already-loaded UIs) without paying *save*'s full-capture cost.
        """
        values: Dict[str, Any] = {}
        provider = self.value_provider
        if for_modified and self.modified_value_provider is not None:
            provider = self.modified_value_provider
        if provider is not None:
            for key, value in provider().items():
                if value is not None and _is_serializable(value):
                    values[key] = value
            return values
        for widget in self._get_widgets(scope):
            obj_name = widget.objectName()
            if not obj_name:
                continue
            if self.state is not None:
                value = self.state._get_current_value(widget)
            else:
                value = self._get_widget_value(widget)
            if value is not None and _is_serializable(value):
                values[obj_name] = value
        return values

    @staticmethod
    def _strip_meta(data: Dict[str, Any]) -> Dict[str, Any]:
        """Return *data* without the reserved ``_meta`` block."""
        return {k: v for k, v in data.items() if k != "_meta"}

    def load(
        self,
        name: str,
        scope: Optional[QtWidgets.QWidget] = None,
        block_signals: bool = True,
    ) -> int:
        """Load a named preset and apply its values to the matching widgets.

        In MainWindow mode the applied values are then **persisted** to the
        per-widget QSettings session state, so the loaded preset survives to the
        next session: the preset combo restores only the active *name* (see
        :meth:`wire_combo`), and the values come from session state. Saves are
        suppressed *during* the bulk apply so a mid-apply slot cascade can't
        persist a half-applied state -- the final, consistent values are written
        once afterwards. (Without this the name would restore but the widgets
        would revert to their pre-load values -- "template active, values not
        restored".)

        Parameters:
            name: The preset name to load.
            scope: Optional container widget to limit which children are
                affected. Defaults to the entire parent window.
            block_signals: Whether to block widget signals during value
                application. Defaults to True to prevent cascading slot
                execution.

        Returns:
            The number of widgets that were updated.
        """
        # Resolve via the store: a user preset shadows a built-in of the same
        # name, so the same call serves shipped defaults and user saves.
        try:
            data = self._store.load(name)
        except KeyError:
            self.logger.warning(f"Preset not found: {name}")
            return 0
        except (ValueError, OSError) as e:  # ValueError covers JSONDecodeError
            self.logger.warning(f"Invalid preset '{name}': {e}")
            return 0

        # Extract and dispatch metadata
        meta = data.pop("_meta", {})
        if self.on_metadata_loaded is not None and meta:
            self.on_metadata_loaded(meta)

        # ``data`` no longer holds ``_meta`` so it *is* the snapshot. Record the
        # active preset + baseline now; refresh the marker *after* applying so it
        # reflects the post-apply (clean) state, not the pre-apply diff.
        self._store.active = name
        self._active_snapshot = dict(data)

        if self.value_applier is not None:
            # Semantic mode: hand the whole {key: value} payload to the caller's
            # applier (e.g. a bridge's ``_apply_param_dict``), which maps keys
            # to its own widgets. Return its applied-count (default to the
            # payload size if the applier returns None).
            applied = self.value_applier(data)
            applied = applied if isinstance(applied, int) else len(data)
            self.logger.debug(f"Loaded preset '{name}': {applied} keys applied.")
            self.refresh_modified_state()
            return applied

        widgets = self._get_widgets(scope)
        widget_map = {w.objectName(): w for w in widgets if w.objectName()}

        applied = 0

        if self.state is not None:
            # MainWindow path: apply under suppress_save (so a mid-apply slot
            # cascade can't persist a half-applied state), then persist the
            # final values so the loaded preset becomes the session state.
            applied_widgets: List[QtWidgets.QWidget] = []
            with self.state.suppress_save():
                for obj_name, value in data.items():
                    widget = widget_map.get(obj_name)
                    if widget is None:
                        self.logger.debug(
                            f"Preset key '{obj_name}' has no matching widget, skipping."
                        )
                        continue

                    # Mirror StateManager.reset_all: default False (the
                    # module-wide default) and restore-or-remove the attribute
                    # so a load never permanently stamps ``block_signals_on_restore``
                    # onto a widget that never had it (which would silently
                    # suppress slot execution on every future restore).
                    had_attr = hasattr(widget, "block_signals_on_restore")
                    original_block = getattr(
                        widget, "block_signals_on_restore", False
                    )
                    widget.block_signals_on_restore = block_signals
                    try:
                        self.state.apply(widget, value)
                        applied += 1
                        applied_widgets.append(widget)
                    finally:
                        if had_attr:
                            widget.block_signals_on_restore = original_block
                        else:
                            try:
                                del widget.block_signals_on_restore
                            except AttributeError:
                                widget.block_signals_on_restore = original_block
            # Persist outside the suppression so the loaded preset survives to
            # the next session (one write per widget of its final applied value).
            for widget in applied_widgets:
                self.state.save(widget)
        else:
            # Standalone path: direct widget value set
            blocked: List[QtWidgets.QWidget] = []
            if block_signals:
                for w in widget_map.values():
                    if not w.signalsBlocked():
                        w.blockSignals(True)
                        blocked.append(w)
            try:
                for obj_name, value in data.items():
                    widget = widget_map.get(obj_name)
                    if widget is None:
                        self.logger.debug(
                            f"Preset key '{obj_name}' has no matching widget, skipping."
                        )
                        continue
                    self._set_widget_value(widget, value)
                    applied += 1
            finally:
                for w in blocked:
                    w.blockSignals(False)

        self.logger.debug(
            f"Loaded preset '{name}': {applied}/{len(data)} widgets applied."
        )
        self.refresh_modified_state()
        return applied

    def list(self) -> List[str]:
        """Return a sorted list of available preset names across both tiers.

        Union of built-in (shipped, read-only) and user presets; a user preset
        of the same name shadows the built-in, so each name appears once.
        """
        return self._store.list()

    def source(self, name: str) -> Optional[str]:
        """Which tier *name* resolves from: ``"user"``, ``"builtin"``, or ``None``.

        Lets a UI lock / relabel built-ins (they can't be renamed or deleted).
        """
        return self._store.source(name)

    def delete(self, name: str) -> bool:
        """Delete a *user* preset (built-ins are read-only).

        Returns True if a user file was removed; False if absent or the name
        exists only as a read-only built-in.
        """
        if self._store.delete(name):
            self.logger.debug(f"Deleted preset '{name}'")
            self._notify_change()
            # The store may have cleared a dangling ``.active``; re-sync cache.
            self._resync_active()
            return True
        self.logger.debug(f"Preset '{name}' not deleted (absent or built-in).")
        return False

    def rename(self, old_name: str, new_name: str) -> bool:
        """Rename a *user* preset.

        False if *old_name* isn't a user preset, or *new_name* already exists in
        either tier (won't silently shadow a built-in).
        """
        if self._store.rename(old_name, new_name):
            self.logger.debug(f"Renamed preset '{old_name}' -> '{new_name}'")
            self._notify_change()
            # The store follows ``.active`` across the rename; re-sync cache.
            self._resync_active()
            return True
        self.logger.warning(
            f"Cannot rename preset '{old_name}' -> '{new_name}' "
            "(source not a user preset, or target name already in use)."
        )
        return False

    def exists(self, name: str) -> bool:
        """Check whether a named preset exists in either tier."""
        return self._store.exists(name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _preset_path(self, name: str) -> Path:
        """Full path for a *user* preset name (sanitized).

        Kept for back-compat; the store is the tier-aware source of truth. Uses
        the shared sanitizer so a name maps to the same file as the headless path.
        """
        return self._store.path(name, "user")

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

    # ------------------------------------------------------------------
    # Standalone widget value helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_widget_value(widget: QtWidgets.QWidget) -> Any:
        """Read the current value from a standard Qt widget."""
        if isinstance(widget, (QtWidgets.QCheckBox, QtWidgets.QRadioButton)):
            return widget.isChecked()
        elif isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            return widget.value()
        elif isinstance(widget, QtWidgets.QComboBox):
            return widget.currentIndex()
        elif isinstance(widget, QtWidgets.QLineEdit):
            return widget.text()
        elif isinstance(widget, QtWidgets.QTextEdit):
            return widget.toPlainText()
        elif isinstance(widget, QtWidgets.QSlider):
            return widget.value()
        return None

    @staticmethod
    def _set_widget_value(widget: QtWidgets.QWidget, value: Any) -> None:
        """Set a value on a standard Qt widget."""
        if isinstance(widget, (QtWidgets.QCheckBox, QtWidgets.QRadioButton)):
            widget.setChecked(value)
        elif isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            widget.setValue(value)
        elif isinstance(widget, QtWidgets.QComboBox):
            widget.setCurrentIndex(value)
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(value)
        elif isinstance(widget, QtWidgets.QTextEdit):
            widget.setPlainText(value)
        elif isinstance(widget, QtWidgets.QSlider):
            widget.setValue(value)

    # ------------------------------------------------------------------
    # Combo-box wiring
    # ------------------------------------------------------------------

    # Default object name + tooltip for combos built by :meth:`make_preset_combo`.
    PRESET_COMBO_NAME = "cmb_presets"
    PRESET_COMBO_TOOLTIP = "Load a saved configuration preset."

    def make_preset_combo(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        name: Optional[str] = None,
        tooltip: Optional[str] = None,
        on_loaded: Optional[Callable[[], None]] = None,
    ) -> "QtWidgets.QWidget":
        """Create a fully-wired preset selector and return its layout container.

        The single DRY entry point for the canonical preset template: builds a
        uitk :class:`~uitk.widgets.comboBox.ComboBox`, wires it via
        :meth:`wire_combo`, and returns the :attr:`option_box` *container*
        (combo + Refresh / Save / menu toolbar) ready to drop into a layout.

        The combo itself is reachable as ``container.preset_combo`` for callers
        that need to reference it (e.g. to query the current selection).

        Parameters:
            parent: Parent for the combo (and thus the container).
            name: ``objectName`` for the combo (default :attr:`PRESET_COMBO_NAME`).
            tooltip: Combo tooltip (default :attr:`PRESET_COMBO_TOOLTIP`).
            on_loaded: Forwarded to :meth:`wire_combo`.

        Returns:
            The ``OptionBoxContainer`` holding the combo and its toolbar.
        """
        from uitk.widgets.comboBox import ComboBox

        combo = ComboBox(parent)
        combo.setObjectName(name or self.PRESET_COMBO_NAME)
        combo.setToolTip(tooltip or self.PRESET_COMBO_TOOLTIP)
        combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        container = self.wire_combo(combo, on_loaded=on_loaded)
        # Stash the combo on the container so callers don't have to dig through
        # the option-box layout to reach it.
        if container is not None:
            container.preset_combo = combo
        return container

    def wire_combo(self, combo, on_loaded=None):
        """Wire a uitk ``ComboBox`` as a fully-functional preset selector.

        Builds the canonical preset template: the combo's :attr:`option_box`
        gains a compact, icon-only toolbar -- **Refresh**, **Save**, and a
        **menu** (Rename / Open folder / Delete) -- and the combo is populated
        with the available presets and connected so a user pick loads it.
        *Refresh* re-scans the preset directory (picking up files added or
        removed by hand) and re-applies the **active** preset
        (``mgr.active_preset``), discarding any edits.

        **Inline naming (no pop-up dialogs).** *Save* and *Rename* put the combo
        into edit mode in-place: the line edit is focused and pre-filled, and
        pressing **Enter** commits (clicking away cancels). Save writes the
        current values under the typed name -- same name overwrites, a new name
        creates a new entry. Rename moves the selected user preset to the typed
        name (values unchanged).

        Built-in (shipped, read-only) presets are shown italicised in the list;
        **Rename / Delete are hidden from the menu** while one is selected (they
        can't act on a read-only preset). *Refresh / Open / Save* stay available
        -- Save writes a user preset that shadows the built-in (the "duplicate to
        edit" flow).

        The combo shows the *active preset name* as its selected item, restored
        from the persisted :attr:`active_preset` on wire (selection only -- no
        values are re-applied, since widgets restore themselves from session
        state; **semantic mode has no such fallback** -- an owner whose values
        live outside the panel must re-apply the active preset at startup, see
        the restore-contract note in ``__init__``). When the live values
        diverge from the active preset a ``" *"`` suffix is shown (see
        :meth:`is_modified`); Save / Refresh clear it. When no preset is active
        the combo shows the ``"Presets..."`` placeholder, or ``"No saved
        presets"`` when none exist.

        Parameters:
            combo: A uitk :class:`~uitk.widgets.comboBox.ComboBox` to populate
                and wire. (A ``WidgetComboBox`` works too -- it subclasses
                ``ComboBox`` -- but the plain ``ComboBox`` is canonical.)
            on_loaded: Optional callable invoked (with no arguments) after
                a preset is successfully loaded.  When omitted, widget
                signals are left unblocked so slot handlers fire naturally.

        Returns:
            The :attr:`option_box` container (combo + toolbar). Place this in
            your layout. When *combo* was already sitting in a layout, the
            container has already replaced it in-place and the return can be
            ignored.
        """
        mgr = self

        def mark_builtins(names):
            """Italicise read-only built-in presets (+ a read-only tooltip).

            Sets the model item's font/tooltip rather than its text, so
            ``itemText`` stays the raw preset name for load/rename/delete. The
            italic is via ``Qt.FontRole`` (dropdown list only) -- the collapsed
            display keeps the widget font, so the dropdown arrow is unaffected.
            """
            model = combo.model()
            if not hasattr(model, "item"):
                return
            # Resolve the read-only built-in set ONCE (two directory globs)
            # rather than probing ``source(nm)`` per name -- each call rebuilt
            # the store and stat'd both tiers, so a preset-heavy panel paid
            # O(N) store builds + stats here on every refresh. A name is a
            # read-only built-in iff it ships as a built-in AND is not shadowed
            # by a user preset of the same name (mirrors ``source`` semantics).
            store = mgr._store
            builtin_names = set(store.list(tier="builtin"))
            user_names = set(store.list(tier="user"))
            italic = QtGui.QFont(combo.font())
            italic.setItalic(True)
            for i, nm in enumerate(names):
                if nm not in builtin_names or nm in user_names:
                    continue
                item = model.item(i)
                if item is not None:
                    item.setFont(italic)
                    item.setToolTip(f"{nm} (built-in, read-only)")

        def refresh(select_name: Optional[str] = None):
            """Repopulate the combo with current preset names.

            Parameters:
                select_name: If given, select this preset after repopulating.
                    If ``None``, the persisted **active preset** is re-selected
                    (idea: restore only the *selection* -- widget values restore
                    themselves from session state). Selection is set with
                    signals blocked, so **no values are applied** (selection-load
                    is keyed off the user-only ``activated`` signal).
            """
            if select_name is None:
                select_name = mgr.active_preset
            names = mgr.list()
            combo.blockSignals(True)
            try:
                combo.clear()
                if names:
                    combo.addItems(names)
                    mark_builtins(names)
                    # findText -> -1 when the (stale) name is gone, which falls
                    # through to the placeholder rather than a silent item-0.
                    combo.setCurrentIndex(combo.findText(select_name) if select_name else -1)
                    combo.setPlaceholderText("Presets…")
                else:
                    combo.setCurrentIndex(-1)
                    combo.setPlaceholderText("No saved presets")
            finally:
                combo.blockSignals(False)
            # Selection was set with signals blocked (no value apply); sync the
            # dirty baseline from the active preset and refresh the marker.
            mgr._resync_active()

        def selected_name() -> str:
            """The currently-selected preset name (``""`` when none)."""
            idx = combo.currentIndex()
            return combo.itemText(idx) if idx >= 0 else ""

        def apply_preset(name):
            """(Re)apply preset *name*'s values to the widgets (no-op if falsy).

            When ``on_loaded`` is provided, block signals during load and fire
            the single consolidated callback afterwards. Otherwise, let signals
            propagate so normal slot handlers (e.g. checkbox -> refresh) fire.
            """
            if not name:
                return
            mgr.load(name, block_signals=on_loaded is not None)
            if on_loaded:
                on_loaded()

        def on_selected(idx):
            """User picked a preset from the dropdown -> load it.

            Wired to ``activated`` (user-only), never ``currentIndexChanged``,
            so programmatic selection during ``refresh`` / inline-edit commit
            never triggers a (potentially clobbering) reload.
            """
            if idx >= 0:
                apply_preset(combo.itemText(idx))

        def on_refresh():
            """Re-scan the preset dir, then reload the **active** preset's values.

            Repopulates the combo from disk first (via :func:`refresh`) so
            presets added to or removed from the preset directory *outside* the
            UI -- a user dropping in or deleting ``*.json`` files by hand -- are
            picked up. Then re-applies the active preset's values, discarding
            any edits.

            The value re-apply is keyed off ``mgr.active_preset`` rather than the
            combo's ``currentIndex`` so Refresh still works after a session
            restore (or any state that left the index at -1) -- the index-based
            version silently no-oped, which read as "Refresh is broken". It is
            skipped when the active preset no longer exists on disk (e.g. its
            file was just deleted by hand), so there's no spurious warning.
            """
            refresh()
            active = mgr.active_preset
            if active and mgr.exists(active):
                apply_preset(active)

        def begin_inline_edit(mode: str, seed: str):
            """Enter in-place edit mode pre-filled with *seed* for *mode*.

            *mode* (``"save"`` / ``"rename"``) is consumed by
            :func:`on_edit_committed` on the next Enter. Clicking away fires no
            commit (``ComboBox.focusOutEvent`` exits edit mode silently).
            """
            mgr._pending_preset_action = mode
            combo.setEditable(True)
            line_edit = combo.lineEdit()
            if line_edit is not None:
                line_edit.setText(seed or "")
                line_edit.selectAll()
                line_edit.setFocus()

        def on_save():
            """Start an inline Save: type a name + Enter (same name overwrites)."""
            current = selected_name()
            # A built-in blanks the seed so Save acts as duplicate-to-edit
            # rather than re-typing the read-only default's name.
            seed = "" if (current and mgr.source(current) == "builtin") else current
            begin_inline_edit("save", seed)

        def on_rename():
            """Start an inline Rename of the selected user preset."""
            current = selected_name()
            if not current or mgr.source(current) != "user":
                return
            begin_inline_edit("rename", current)

        def on_edit_committed(text: str):
            """Dispatch the committed inline-edit text per the pending action."""
            mode = getattr(mgr, "_pending_preset_action", None)
            mgr._pending_preset_action = None
            if mode is None:
                return
            name = (text or "").strip()
            if mode == "save":
                if not name:
                    return
                mgr.save(name)
                # The saved preset becomes active; its values == what we just
                # wrote, so the marker is clean.
                mgr.active_preset = name
                refresh(select_name=name)
            elif mode == "rename":
                old = selected_name() or mgr.active_preset
                if name and old and name != old and mgr.source(old) == "user":
                    if mgr.rename(old, name):
                        refresh(select_name=name)
                        return
                # Invalid / unchanged / cancelled -- restore the display.
                refresh()

        def on_delete():
            current = selected_name()
            if not current:
                return
            mgr.delete(current)
            refresh()

        def on_open_folder():
            """Open the preset directory in the system file explorer."""
            preset_dir = mgr.preset_dir
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(preset_dir)))

        def build_menu_items(_widget):
            """Menu items, rebuilt per open so built-ins hide Rename/Delete.

            A read-only built-in (or no selection) can't be renamed or deleted,
            so those entries are omitted rather than shown disabled -- cleaner
            for a short pop-up menu.
            """
            current = selected_name()
            is_user = bool(current) and mgr.source(current) == "user"
            items = []
            if is_user:
                items.append(("Rename", on_rename))
            items.append(("Open Folder", on_open_folder))
            if is_user:
                items.append(("Delete", on_delete))
            return items

        def update_marker(modified: bool):
            """Reflect the modified ('dirty') state as an asterisk on the combo's
            displayed current text (item data is left untouched)."""
            combo.current_text_suffix = " *" if modified else ""

        self._excluded_widgets.add(combo)
        self._refresh_combo = refresh

        # Bound the combo's height so the option-box icon buttons (sized to the
        # combo's height) stay compact. A combo dropped into a *stretchy*
        # container — e.g. a menu's "Menu Actions" group (``add_presets``) — has
        # no vertical limit and expands to fill it, which would balloon the
        # square icon buttons and squeeze the dropdown to nothing. Pin it to the
        # natural row height (its size hint) unless the caller already set an
        # explicit maximum (the in-panel rows that pass a fixed height).
        hint_h = combo.sizeHint().height()
        if hint_h > 0 and combo.maximumHeight() >= 16777215:  # QWIDGETSIZE_MAX
            combo.setFixedHeight(hint_h)

        # The compact option-box toolbar: Refresh, Save, then a menu holding
        # Rename / Open / Delete. ActionOptions sort before the menu option, and
        # insertion order is preserved within the action group, so the rendered
        # left-to-right order is exactly [refresh][save][menu]. The menu is a
        # cursor-centred pop-up with no header / footer / apply chrome (a plain
        # action list), matching a right-click context menu.
        from uitk.widgets.optionBox.options.option_menu import ContextMenuOption

        combo.option_box.add_action(
            callback=on_refresh,
            icon="refresh",
            tooltip="Rescan presets folder and reload the active preset (discard edits).",
        )
        combo.option_box.add_action(
            callback=on_save,
            icon="save",
            tooltip="Save the current settings as a preset (type a name, Enter).",
        )
        combo.option_box.add_option(
            ContextMenuOption(
                wrapped_widget=combo,
                menu_provider=build_menu_items,
                icon="menu",
                tooltip="Preset actions: rename, open folder, delete.",
                position="cursorPos",
                add_header=False,
                add_footer=False,
                add_apply_button=False,
                add_defaults_button=False,
                match_parent_width=False,
            )
        )

        mgr.on_modified_changed(update_marker)
        # Live marker updates for the menu / standalone (widget-state) paths;
        # no-op in semantic mode (the caller wires its own param widgets).
        mgr.connect_value_widgets()

        # Inline Save / Rename commit on Enter (see ComboBox.on_editing_finished).
        combo.on_editing_finished.connect(on_edit_committed)

        refresh()
        # ``activated`` is user-only -- programmatic selection (refresh, inline
        # commit) never reloads, so an overwrite-Save can't clobber the live
        # values with the pre-save snapshot.
        try:
            combo.activated[int].connect(on_selected)
        except (TypeError, KeyError):
            combo.activated.connect(on_selected)

        return combo.option_box.container


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _is_serializable(value: Any) -> bool:
    """Check if a value can be safely serialized to JSON."""
    return isinstance(value, (int, float, str, bool, list, dict, tuple))


def QStandardPaths_writableLocation() -> str:
    """Return Qt's per-application writable config directory.

    On Windows this is ``<LOCALAPPDATA>/<exeName>`` (e.g.
    ``C:/Users/<u>/AppData/Local/python``) when no organisation/application
    name has been set on ``QCoreApplication`` — the ``<exeName>`` segment
    is Qt auto-naming from the executable, *not* a pre-existing dir.

    Used for *finding legacy* preset data written under previous layouts.
    The current root uses :func:`QStandardPaths_genericConfigLocation`
    instead, which is host-independent.
    """
    return QtCore.QStandardPaths.writableLocation(
        QtCore.QStandardPaths.AppConfigLocation
    )


def QStandardPaths_genericConfigLocation() -> str:
    """Return Qt's host-independent writable config directory.

    On Windows this is ``<LOCALAPPDATA>`` directly (no executable-name
    segment); on macOS ``~/Library/Preferences``; on Linux ``~/.config``.
    Same path regardless of which host process (standalone Python, Maya,
    Painter, ...) is running, so presets stay visible across hosts.
    """
    return QtCore.QStandardPaths.writableLocation(
        QtCore.QStandardPaths.GenericConfigLocation
    )


# ---------------------------------------------------------------------------
# Consolidated preset root
# ---------------------------------------------------------------------------
#
# All relative ``preset_dir`` values across the ecosystem resolve under a
# single root, so a user looking for their saved data finds it in one place
# instead of scattered across ``~/.mayatk/presets``, ``~/.pythontk/presets``,
# and ``%LOCALAPPDATA%/uitk/*-presets``.
#
# Layout (Windows example; ``~/.config/...`` on Linux, ``~/Library/
# Preferences/...`` on Mac):
#
#     %LOCALAPPDATA%/uitk/         <- ecosystem wrapper folder
#     ├── uitk/                    <- uitk pkg state
#     ├── mayatk/                  <- mayatk pkg state
#     └── extapps/                 <- extapps pkg state
#
# The base is Qt's :func:`QStandardPaths.GenericConfigLocation` (the
# host-independent user-config dir — same path whether the host is
# standalone Python, Maya, Painter, etc.) plus a ``uitk`` wrapper
# folder named after the foundation library. The wrapper keeps the
# ecosystem's state grouped under one entry in AppData/Local rather
# than scattered as siblings of Microsoft, Google, pip, npm... — the
# same shape Microsoft uses (``Microsoft/Edge/``, ``Microsoft/Windows/``).
#
# The ``uitk/uitk/`` doubling for uitk's own state is intentional:
# outer ``uitk/`` is the wrapper namespace; inner ``uitk/`` is the
# package itself, consistent with how every other package's state
# lives under ``<wrapper>/<pkg>/``.
#
# Set ``UITK_PRESETS_ROOT`` to redirect wholesale (network share,
# alternate drive, ...). The override is used as-given — no implicit
# ``uitk/`` wrapper is appended — so power users keep full control.
#
# Existing presets from legacy locations are copied in on first access
# (see ``_maybe_migrate_legacy``). Completion is recorded by an empty
# ``.migrated`` sentinel placed inside the migrated package dir itself —
# per-key files avoid the read-modify-write race a shared state file would
# have when multiple host processes (Maya + Painter + CLI) start at once,
# and the sentinel travels with its data (wipe the dir → re-migrate next
# access, which is the expected behavior).

PRESETS_ROOT_ENV_VAR = "UITK_PRESETS_ROOT"
_ECOSYSTEM_WRAPPER_NAME = "uitk"

# =============================================================================
# DEPRECATED MIGRATION LOGIC — scheduled for removal
# =============================================================================
#
# Everything from ``_MIGRATION_SENTINEL_NAME`` through the end of
# ``_maybe_migrate_legacy`` exists solely to migrate users coming from
# older preset-path layouts. It is *not* part of the current design and
# should be deleted once no users remain on the old layouts.
#
# Removal candidates (delete together — they form one self-contained block):
#
#   - ``_MIGRATION_SENTINEL_NAME``
#   - ``_LEGACY_PRESET_PATHS``
#   - ``_resolve_legacy_template``
#   - ``_migration_sentinel_path``
#   - ``_has_migrated``
#   - ``_mark_migrated``
#   - ``_merge_move``
#   - ``_LEGACY_QT_ROOTS_CLEARED``
#   - ``_INTERIM_STATE_ARTIFACTS``
#   - ``_legacy_qt_root_candidates``
#   - ``_looks_like_ecosystem_wrapper``
#   - ``_wrap_pre_wrap_uitk_state``
#   - ``_maybe_clear_legacy_qt_roots``
#   - ``_maybe_migrate_legacy``
#   - The ``_maybe_migrate_legacy(self._preset_dir)`` call inside the
#     ``PresetManager.preset_dir`` property
#   - Test class ``TestLegacyMigration`` in ``test/test_preset_manager.py``
#
# Removal criteria (any one is sufficient):
#
#   1. No legacy preset data exists at the candidate roots on any
#      machine that runs this code — confirmed by inspection.
#   2. The deprecation review date below has passed AND the
#      ``.migrated`` sentinel files have been present in user dirs
#      long enough that any first-launch on legacy data has run.
#
# Suggested review date: **2027-05-21** (one year out from the
# introduction of GenericConfigLocation as the root). Reviewing earlier
# is fine if you're confident in (1). Reviewing later is fine too —
# the migration code is small, idempotent, and gated by a per-process
# flag so its runtime cost is negligible.
#
# =============================================================================

_MIGRATION_SENTINEL_NAME = ".migrated"

# Map: new relative path under the consolidated root → legacy absolute path
# template. ``{APPCONFIG}`` is substituted with QStandardPaths.AppConfigLocation
# at resolution time so the table itself stays declarative.
#
# Each entry represents a *package boundary*: when a request resolves to a
# path under one of these keys (e.g. ``mayatk/substance_bridge/<template>``),
# the *entire* legacy tree for that key is copied so sibling subdirs (other
# bridge templates) come along for the ride — not just the requested leaf.
_LEGACY_PRESET_PATHS: Dict[str, str] = {
    "mayatk/substance_bridge": "~/.mayatk/presets/substance_bridge",
    "mayatk/marmoset_bridge": "~/.mayatk/presets/marmoset_bridge",
    "mayatk/rizom_bridge": "~/.mayatk/presets/rizom_bridge",
    "mayatk/scene_exporter": "~/.mayatk/presets/scene_exporter",
    "mayatk/reference_manager": "~/.mayatk/presets/reference_manager",
    "mayatk/color_manager": "~/.mayatk/presets/color_manager",
    "mayatk/shot_manifest_colors": "~/.mayatk/presets/shot_manifest_colors",
    "extapps/texture_maps/packer": "~/.pythontk/presets/map_packer",
    "uitk/style_presets": "{APPCONFIG}/uitk/style_presets",
    "uitk/shortcut_presets": "{APPCONFIG}/uitk/hotkey_presets",
    "uitk/switchboard_browser/presets": "{APPCONFIG}/uitk/switchboard_browser/presets",
}


def get_presets_root() -> Path:
    """Root directory under which every relative ``preset_dir`` is resolved.

    Defaults to ``<GenericConfigLocation>/uitk/`` — the host-independent
    user config dir plus a ``uitk`` wrapper folder that keeps the
    ecosystem's state grouped under one entry in AppData/Local rather
    than scattered as siblings of Microsoft, Google, pip, etc. The
    wrapper is named after the foundation library that owns the preset
    system.

    Set ``UITK_PRESETS_ROOT`` to redirect every relative preset path
    wholesale (network share, alternate drive, Documents subfolder…).
    The override is used as-given — no implicit ``uitk/`` wrapper is
    appended — so a power-user override has full control. It accepts
    ``~`` and ``%ENVVAR%`` syntax; relative overrides resolve against
    the process working directory at access time so the return is
    always absolute.
    """
    override = os.environ.get(PRESETS_ROOT_ENV_VAR)
    if override:
        p = Path(os.path.expandvars(override)).expanduser()
    else:
        p = Path(QStandardPaths_genericConfigLocation()) / _ECOSYSTEM_WRAPPER_NAME
    return p if p.is_absolute() else p.absolute()


def _resolve_legacy_template(template: str) -> Path:
    """Expand ``{APPCONFIG}``, environment variables, and ``~`` in *template*."""
    if "{APPCONFIG}" in template:
        template = template.replace("{APPCONFIG}", QStandardPaths_writableLocation())
    return Path(os.path.expandvars(template)).expanduser()


def _migration_sentinel_path(key: str) -> Path:
    """Path to the per-package sentinel marking a completed migration.

    The sentinel lives *inside* the migrated package dir itself (as a
    dotfile that ``glob('*.json')`` ignores) so it travels with its
    data — if the user wipes the package dir, the sentinel goes too
    and the next access re-migrates from legacy, which is normally
    what they want.
    """
    return get_presets_root().joinpath(*key.split("/")) / _MIGRATION_SENTINEL_NAME


def _has_migrated(key: str) -> bool:
    return _migration_sentinel_path(key).exists()


def _mark_migrated(key: str) -> None:
    p = _migration_sentinel_path(key)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch(exist_ok=True)
    except OSError as e:
        _log.warning("preset migration: could not mark %s migrated: %s", key, e)


def _merge_move(src: Path, dst: Path) -> None:
    """Move *src* tree into *dst*, never overwriting existing destination files.

    Unlike ``shutil.move`` (which fails or overwrites on collisions), this
    walks the source tree and moves each file into place only if the
    corresponding destination doesn't exist. Empty source dirs are removed
    as the walk unwinds so a fully-merged subtree leaves nothing behind.
    Collisions silently keep the destination version — the assumption is
    that whatever the live code wrote is the user's intent.
    """
    if not dst.exists():
        try:
            shutil.move(str(src), str(dst))
        except (OSError, shutil.Error) as e:
            _log.warning("preset merge: could not move %s -> %s: %s", src, dst, e)
        return
    if src.is_file():
        # Collision at a leaf file. Keep the destination (whatever the
        # live code wrote is the user's intent) and leave the source in
        # place as evidence — a user investigating "missing preset"
        # symptoms can find it via the debug log and the on-disk copy.
        _log.debug("preset merge: collision at %s, kept destination", dst)
        return
    for item in list(src.iterdir()):
        _merge_move(item, dst / item.name)
    try:
        src.rmdir()
    except OSError:
        pass


_LEGACY_QT_ROOTS_CLEARED = False
_INTERIM_STATE_ARTIFACTS = (".migrated", ".migration")


def _legacy_qt_root_candidates() -> List[Path]:
    """Old preset root locations to drain into the current root.

    Three prior layouts existed:

    A. ``<AppConfigLocation>/m3trik/presets/<pkg>/...`` — an interim
       revision wrapped every relative preset in an unsolicited
       ``m3trik/presets`` segment.
    B. ``<AppConfigLocation>/<pkg>/...`` — used Qt's
       ``AppConfigLocation`` directly. That path embeds the host
       application name (``python/`` standalone, ``maya/`` from Maya,
       etc.), making presets invisible across hosts.
    C. ``<GenericConfigLocation>/<pkg>/...`` — used the host-independent
       config dir but as a bare root, so the ecosystem's packages were
       siblings of unrelated apps (pip, npm, Microsoft, ...). The
       current layout wraps everything in a single ``uitk/`` folder.

    Order matters: deepest layouts first so their contents don't get
    re-processed by outer passes. Pulled out as a function so tests can
    monkey-patch it to point at tmp dirs (essential — without the patch
    the cleanup would touch the real developer machine's data).
    """
    appconfig = Path(QStandardPaths_writableLocation())
    generic = Path(QStandardPaths_genericConfigLocation())
    return [appconfig / "m3trik" / "presets", appconfig, generic]


def _dir_has_preset_data(directory: Path) -> bool:
    """True when *directory* holds at least one preset file (``*.json``).

    Distinguishes a *husk* — an empty shell a prior wrap left behind,
    holding only a ``.migrated`` sentinel (the merge keeps the destination
    on a sentinel collision, so the source dir survives) — from genuine
    pre-wrap state that still carries presets to relocate. A husk must not
    count as pre-wrap evidence, or it re-triggers the wrap on every launch
    and keeps reburying correctly-placed packages (the "saved preset gone
    next session" bug).
    """
    try:
        return any(directory.rglob("*.json"))
    except OSError:
        return False


def _looks_like_ecosystem_wrapper(uitk_dir: Path, known_pkgs: Set[str]) -> bool:
    """True when *uitk_dir* is already in the wrapper layout.

    A *clean* wrapper layout has only known-package subdirs (uitk /
    mayatk / extapps) and possibly dotfiles. A non-known root-level dir
    carrying preset data — ``style_presets``, ``hotkey_presets``,
    ``some_window``, ... — is pre-wrap state that needs to be moved one
    level deeper.

    Strict matching (vs. "any known-pkg present") also recovers from a
    *partial* wrap: if a prior wrap was interrupted after creating the
    inner ``uitk/`` subdir but before moving every stray sibling, the
    next call still detects the data-bearing strays as pre-wrap and
    finishes the job.

    Empty dirs — and data-less *husks* (only a ``.migrated`` sentinel,
    no ``*.json``) — count as "already wrapped": there is nothing to
    move, and treating them as pre-wrap would re-fire the wrap forever,
    burying any package freshly re-created at the root in between.
    """
    if not uitk_dir.is_dir():
        return False
    try:
        child_dirs = [p for p in uitk_dir.iterdir() if p.is_dir()]
    except OSError:
        return False
    if not child_dirs:
        return True
    for child in child_dirs:
        if child.name in known_pkgs:
            continue
        if child.name.startswith("."):
            continue
        if not _dir_has_preset_data(child):
            continue  # husk left by a prior wrap — not real pre-wrap state
        return False
    return True


def _wrap_pre_wrap_uitk_state(uitk_dir: Path, known_pkgs: Set[str]) -> None:
    """Restructure ``<generic>/uitk/`` from pre-wrap to wrapper layout.

    Before this code: ``<generic>/uitk/`` held uitk-package state
    directly (``style_presets/``, ``hotkey_presets/``, ...). The
    current layout uses ``<generic>/uitk/`` as the *ecosystem wrapper*
    with uitk's own state nested at ``<generic>/uitk/uitk/``. This
    function detects the pre-wrap state and moves the existing contents
    one level deeper, in place, without a sibling temp dir.

    Robust to a previously-interrupted wrap: the detector treats any
    *data-bearing* non-known-pkg / non-dotfile child as evidence of
    pre-wrap state, so a partial wrap (inner ``uitk/`` already created,
    some siblings not yet moved) gets finished on the next call.

    Only uitk's own pre-wrap dirs move down. A known-package sibling
    (``mayatk/``, ``extapps/``, and the inner ``uitk/`` itself) already
    lives at the correct level, so it is left in place — relocating it
    would bury presets saved under it where the live load path can't
    find them (the "saved preset gone next session" bug).

    Interim migration-state artifacts (``.migrated``, ``.migration/``)
    that survive from older revisions of this module are dropped
    rather than carried into the new layout.

    No-op if *uitk_dir* doesn't exist or is already in the wrapper
    layout.
    """
    if not uitk_dir.exists() or not uitk_dir.is_dir():
        return
    if _looks_like_ecosystem_wrapper(uitk_dir, known_pkgs):
        return

    # Snapshot children BEFORE creating the target so the target itself
    # (created below) doesn't appear in our iteration.
    try:
        children = list(uitk_dir.iterdir())
    except OSError as e:
        _log.warning("preset wrap: could not iterate %s: %s", uitk_dir, e)
        return

    target = uitk_dir / _ECOSYSTEM_WRAPPER_NAME
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _log.warning("preset wrap: could not create %s: %s", target, e)
        return

    for child in children:
        # Drop interim migration-state artifacts; they're dead state
        # from older revisions and shouldn't be preserved.
        if child.name in _INTERIM_STATE_ARTIFACTS:
            try:
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
            except OSError as e:
                _log.warning("preset wrap: could not remove %s: %s", child, e)
            continue
        # A correctly-placed known-package sibling (mayatk/, extapps/, and
        # the inner uitk/ itself) already lives at the right level — never
        # relocate it into the wrapper, or presets saved under it get buried
        # where the live load path won't find them. Only uitk's own pre-wrap
        # state (the non-known root-level dirs) moves down.
        if child.is_dir() and child.name in known_pkgs:
            continue
        # The inner target itself shows up in the snapshot only if it
        # pre-existed; skip it so we don't try to move it into itself.
        if child.resolve() == target.resolve():
            continue
        dest = target / child.name
        if dest.exists():
            _merge_move(child, dest)
        else:
            try:
                shutil.move(str(child), str(dest))
                _log.debug("preset wrap: moved %s -> %s", child, dest)
            except (OSError, shutil.Error) as e:
                _log.warning("preset wrap: could not move %s -> %s: %s",
                             child, dest, e)


def _maybe_clear_legacy_qt_roots() -> None:
    """Hoist preset data from older root layouts to the current root.

    Runs two passes:

    1. **Pre-wrap detection.** If the new root (``<generic>/uitk/``)
       already exists but holds *uitk-package* state directly (the
       pre-wrap layout where ``<generic>/uitk/style_presets/`` lived
       at the root level), restructure it in place into the wrapper
       layout (``<generic>/uitk/uitk/style_presets/``). See
       :func:`_wrap_pre_wrap_uitk_state`.

    2. **Candidate drain.** Iterates :func:`_legacy_qt_root_candidates`
       in nesting order and, for each candidate, hoists only the
       *known package* subdirs (uitk / mayatk / extapps — derived from
       ``_LEGACY_PRESET_PATHS`` keys) into the new root. Other contents
       — pip's cache, other Python tools' configs, unrelated apps'
       data — are left strictly alone.

    Before each drain, interim migration-state artifacts
    (``.migrated``, ``.migration/``) are deleted so they don't leak up.
    Empty ``m3trik`` shells are removed afterward; bare
    AppConfigLocation / GenericConfigLocation dirs are never removed
    since they usually hold other apps' data.

    Guarded by a process-global flag so subsequent ``preset_dir``
    accesses are zero-cost.
    """
    global _LEGACY_QT_ROOTS_CLEARED
    if _LEGACY_QT_ROOTS_CLEARED:
        return
    _LEGACY_QT_ROOTS_CLEARED = True

    new_root = get_presets_root()
    known_pkgs = {key.split("/")[0] for key in _LEGACY_PRESET_PATHS}

    # Pass 1: handle the pre-wrap collision at the new root itself.
    _wrap_pre_wrap_uitk_state(new_root, known_pkgs)

    # Pass 2: drain candidates.
    candidates = _legacy_qt_root_candidates()
    for old_root in candidates:
        # Skip when old_root *is* the new root — pass 1 already handled it.
        try:
            if old_root.resolve() == new_root.resolve():
                continue
        except OSError:
            continue
        if not old_root.exists() or not old_root.is_dir():
            continue

        # Drop interim migration-state artifacts so they don't litter
        # the new root.
        for artifact in _INTERIM_STATE_ARTIFACTS:
            artifact_path = old_root / artifact
            try:
                if artifact_path.is_file():
                    artifact_path.unlink()
                elif artifact_path.is_dir():
                    shutil.rmtree(artifact_path)
            except OSError as e:
                _log.warning("preset cleanup: could not remove %s: %s",
                             artifact_path, e)

        # Hoist only known package subdirs. If a candidate *contains*
        # the new root (e.g. old_root == <generic>, new_root ==
        # <generic>/uitk), the uitk subdir IS the new root — pass 1
        # already handled it, so skip that single pkg here.
        for pkg in known_pkgs:
            src = old_root / pkg
            if not src.exists() or not src.is_dir():
                continue
            try:
                if src.resolve() == new_root.resolve():
                    continue  # pass 1 territory
            except OSError:
                continue
            dst = new_root / pkg
            _log.debug("preset cleanup: hoisting %s -> %s", src, dst)
            _merge_move(src, dst)

    # Clean up the m3trik shell if it's now empty. Identified by the path
    # shape ``.../m3trik/presets`` so the cleanup works whether candidates
    # come from the real QStandardPaths or a test monkey-patch. The bare
    # AppConfigLocation / GenericConfigLocation candidates are never
    # removed — they hold unrelated apps' data.
    for cand in candidates:
        if cand.name == "presets" and cand.parent.name == "m3trik":
            for p in (cand, cand.parent):
                try:
                    p.rmdir()
                except OSError:
                    pass


def _maybe_migrate_legacy(new_dir: Path) -> None:
    """Copy a legacy preset tree into the consolidated root once.

    Finds the longest prefix of *new_dir*'s relative path that maps to a
    known legacy location in :data:`_LEGACY_PRESET_PATHS`. When such a
    package boundary is found and the migration sentinel does not yet
    exist, copies the *entire* legacy tree (every subdir, every preset)
    so sibling subdirs not yet requested are present too — this matters
    for bridges that switch active template at runtime.

    Existing files at the destination are never overwritten; if the user
    already has presets in the new location, the legacy contents merge
    in beside them. Marks the package migrated either way so subsequent
    accesses are no-ops. Best-effort: I/O failures swallow rather than
    propagate to keep preset loading robust at runtime.
    """
    _maybe_clear_legacy_qt_roots()
    presets_root = get_presets_root()
    try:
        rel = new_dir.relative_to(presets_root)
    except ValueError:
        return  # absolute path outside the consolidated root

    matched_key: Optional[str] = None
    for length in range(len(rel.parts), 0, -1):
        candidate = "/".join(rel.parts[:length])
        if candidate in _LEGACY_PRESET_PATHS:
            matched_key = candidate
            break
    if matched_key is None or _has_migrated(matched_key):
        return

    # Migrate the whole package, not the requested leaf — sibling subdirs
    # (e.g. other bridge templates) would otherwise be silently orphaned
    # once the package is marked migrated.
    legacy_pkg_root = _resolve_legacy_template(_LEGACY_PRESET_PATHS[matched_key])
    new_pkg_root = presets_root.joinpath(*matched_key.split("/"))

    if legacy_pkg_root.exists() and legacy_pkg_root.is_dir():
        try:
            new_pkg_root.mkdir(parents=True, exist_ok=True)
            for item in legacy_pkg_root.iterdir():
                _merge_move(item, new_pkg_root / item.name)
            # Drop the legacy package root if empty after the merge.
            # Non-empty means collisions left files in place (forensic
            # preservation — see _merge_move docs); leaving the dir
            # gives the user something to inspect.
            try:
                legacy_pkg_root.rmdir()
            except OSError:
                pass
        except OSError as e:
            # see docstring: best-effort. Logged so users can opt into
            # diagnostics; default is silent.
            _log.warning("preset migration: %s from %s failed: %s",
                         matched_key, legacy_pkg_root, e)

    _mark_migrated(matched_key)


# Intra-root preset-domain renames: { new_leaf_dir: prior_leaf_dir } under the
# same parent. When the new domain dir is first ensured, presets saved under the
# prior name (same parent) are carried across so *renaming* a preset domain keeps
# the user's snapshots. Distinct from _LEGACY_PRESET_PATHS (which pulls from
# external pre-consolidation roots); this is a same-root rename.
_RENAMED_PRESET_DOMAINS: Dict[str, str] = {
    # 2026-06: the global key-binding editor's domain was renamed from
    # "hotkey_presets" to "shortcut_presets" (hotkey -> shortcut terminology).
    "shortcut_presets": "hotkey_presets",
}


def _maybe_migrate_renamed_domain(new_dir: Path) -> None:
    """Move presets from a renamed sibling domain into *new_dir*, once.

    Looks up *new_dir*'s leaf name in :data:`_RENAMED_PRESET_DOMAINS`; when it
    was renamed from a prior leaf, a same-parent dir under that prior name is
    merged in via :func:`_merge_move` (which never overwrites an existing
    destination file, so a post-rename edit always wins). Interim migration
    artifacts are dropped rather than carried. Best-effort: I/O failures are
    swallowed so preset loading stays robust.
    """
    old_name = _RENAMED_PRESET_DOMAINS.get(new_dir.name)
    if not old_name:
        return
    old_dir = new_dir.with_name(old_name)
    if old_dir == new_dir or not old_dir.is_dir():
        return
    try:
        new_dir.mkdir(parents=True, exist_ok=True)
        for item in list(old_dir.iterdir()):
            if item.name in _INTERIM_STATE_ARTIFACTS:
                try:
                    item.unlink()
                except OSError:
                    pass
                continue
            _merge_move(item, new_dir / item.name)
        try:
            old_dir.rmdir()  # removed only if fully carried (no collisions left)
        except OSError:
            pass
    except OSError as e:
        _log.warning(
            "preset domain rename %s -> %s failed: %s", old_name, new_dir.name, e
        )


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ...
