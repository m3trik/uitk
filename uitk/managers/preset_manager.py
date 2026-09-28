# !/usr/bin/python
# coding=utf-8
import json
import weakref
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union, TYPE_CHECKING

from qtpy import QtWidgets
import pythontk as ptk

# The concept parts PresetManager is built from: base classes, needed at class
# definition, so imported eagerly (the selector wiring, used by one path, is not).
from uitk.managers._preset_migration import (  # noqa: F401 -- re-exported names
    _ECOSYSTEM_WRAPPER_NAME,
    _INTERIM_STATE_ARTIFACTS,
    _LEGACY_PRESET_PATHS,
    _MIGRATION_SENTINEL_NAME,
    _RENAMED_PRESET_DOMAINS,
    _UITK_OWN_PRE_WRAP_DIRS,
    _PresetRootMigration,
)
from uitk.managers._preset_widgets import _PresetWidgetScope

if TYPE_CHECKING:
    from uitk.managers.state_manager import StateManager


class PresetManager(_PresetWidgetScope, _PresetRootMigration, ptk.LoggingMixin):
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
      under :meth:`get_presets_root` (pythontk's user-config root)

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

    #: What writing a stored value that no longer fits its widget raises: a
    #: wrong type (the setting changed kind), an index past a shrunk list, an
    #: overflow. :meth:`load` skips such a key instead of aborting -- and counts
    #: a writer that answers ``False`` instead of raising the same way
    #: (``StateManager.apply``, which never raises).
    _MISFIT_ERRORS = (TypeError, ValueError, OverflowError)

    # Every manager with a wired combo, so a change made OUTSIDE its panel (the
    # Preset Editor, a bundle import) can refresh the open selectors -- see
    # :meth:`notify`. Weak: a closed panel's manager just drops out.
    _live: "weakref.WeakSet[PresetManager]" = weakref.WeakSet()

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

        # Pending inline-edit action for wire_combo's Save/Rename flow:
        # a ("save"/"rename", subject_name) tuple, or None. The subject is
        # captured when the edit BEGINS — the combo item already carries the
        # NEW text by the time on_editing_finished fires, so reading the old
        # name back off the combo at commit time is not possible. Declared
        # here rather than created dynamically inside the closure so the
        # attribute always exists.
        self._pending_preset_action: Optional[tuple] = None

        # Repopulate-closure of the wired combo (set by ``wire_combo``);
        # exposed publicly via :meth:`refresh_combo`.
        self._refresh_combo: Optional[Callable] = None

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
          `pythontk.UserConfig.expand` (every spelling, on every OS).
        - **Relative / short name**: ``"mayatk/reference_manager"`` —
          resolved under :meth:`get_presets_root` (pythontk's user-config
          root, e.g. ``%LOCALAPPDATA%/uitk``).

        Returns:
            An absolute `Path`.
        """
        p = Path(ptk.UserConfig.expand(str(raw)))
        if not p.is_absolute():
            p = PresetManager.get_presets_root() / p
        return p

    @staticmethod
    def _resolve_builtin_dir(raw: Optional[Union[str, Path]]) -> Optional[Path]:
        """Resolve a *builtin_dir* (``~`` / env expanded), or ``None``.

        A relative value is taken as-is (relative to CWD) — built-in dirs are
        repo paths the caller knows, not consolidated-root short names.
        """
        if raw is None:
            return None
        return Path(ptk.UserConfig.expand(str(raw)))

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
            user_dir.name,
            package="uitk",
            builtin_dir=self._builtin_dir,
            user_dir=user_dir,
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
                :meth:`get_presets_root` (``<root>/uitk/<window_name>``).
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

        # Auto-create and wire a preset combo when parent is a Menu — but only
        # while none is wired yet: setup() is also the re-configuration path
        # (widgets, dirs), and repeating the add would stack a second
        # ``cmb_presets`` beside the first (likewise when ``add_presets`` /
        # a manual ``wire_combo`` already produced the selector).
        if (
            self._refresh_combo is None
            and hasattr(self.parent, "add")
            and hasattr(self.parent, "get_items")
        ):
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
                self._preset_dir = PresetManager.get_presets_root() / "uitk" / name
            else:
                raise ValueError(
                    "preset_dir must be provided for standalone PresetManager"
                )

        # Ensure (migrate + create) once per resolved path. A reassigned dir
        # has a different value than ``_ensured_dir`` and re-ensures; writes
        # self-heal the dir at the PresetStore layer (its save/active-write both
        # mkdir), so skipping the per-read FS calls is safe.
        if self._ensured_dir != self._preset_dir:
            PresetManager._maybe_migrate_legacy(self._preset_dir)
            PresetManager._maybe_migrate_renamed_domain(self._preset_dir)
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
    # Active preset + modified ("dirty") tracking
    # ------------------------------------------------------------------

    @property
    def active_preset(self) -> Optional[str]:
        """Name of the preset currently in use, or ``None``.

        Persisted (per :attr:`preset_dir`) via the backing store's ``.active``
        sidecar, so it survives between sessions. It reads back as the file
        stem the combo lists, whatever spelling was assigned (``"a (b)"`` is
        ``"a _b_"``; see ``pythontk.PresetStore.active``). Assigning a name
        updates the modified-tracking baseline **without applying any
        values** — widgets restore themselves from session state, so only the
        *selection* needs restoring. Assign ``None`` to clear.
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
        self._active_snapshot = self.read(active) if active else None
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

        Raises:
            pythontk.PresetReadOnlyError: *name* is a locked user preset.
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
        # it's the active preset the modified marker should clear. The pointer
        # holds the file stem, *name* is as typed ("a (b)" -> "a _b_").
        if self.active_preset == ptk.PresetStore.sanitize_preset_name(name):
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
                if value is not None and PresetManager._is_serializable(value):
                    values[key] = value
            return values
        for widget in self._get_widgets(scope):
            obj_name = widget.objectName()
            if not obj_name:
                continue
            value = self._read_widget(widget)
            if value is not None and PresetManager._is_serializable(value):
                values[obj_name] = value
        return values

    def _update_hint(self, name: str) -> str:
        """How the user brings preset *name* back in step with the panel.

        "Re-save" is only right for an editable user preset: saving over a
        built-in makes a user copy that hides every later shipped update, and a
        locked preset refuses the save.
        """
        if self._store.source(name) == "builtin":
            return "It ships with the tool and is updated with it."
        if self._store.is_read_only(name):
            return "It's locked: save a copy to keep an updated version."
        return "Re-save the preset to update it."

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

        Overlay semantics: only keys present in the stored preset are applied;
        managed widgets the preset does not cover keep their current values.
        A short user-facing WARNING states how many settings were uncovered
        (schema drift is otherwise invisible — ``is_modified`` compares
        overlapping keys only); the key names are logged at DEBUG. A stored
        value that no longer fits its widget (its write raises one of
        :attr:`_MISFIT_ERRORS`, or answers ``False`` as ``StateManager.apply``
        does) is skipped -- that widget keeps its value -- with one WARNING for
        the lot, in the MainWindow and standalone modes alike.

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

        # Surface schema drift: a setting added to the panel after this preset
        # was saved has no stored key, so overlay semantics leave it at whatever
        # the previous preset (or session) set — invisibly, since is_modified
        # only compares overlapping keys. The user-facing line is a plain count
        # + remedy (objectNames mean nothing to an end user); the names go to
        # the debug log for developers.
        #
        # Measured against ``_capture_values`` — what a re-save WOULD write —
        # not against every managed widget: a widget whose value ``save`` drops
        # (``_read_widget`` returns None, or a non-serializable value) can never
        # appear in a preset, so counting it here would warn on every load
        # forever and point at a remedy that cannot work. Same reason this is
        # not ``widget_map``: with a ``value_provider`` configured the stored
        # keys are the provider's, and widget objectNames would all read as
        # uncovered.
        uncovered = sorted(set(self._capture_values(scope)) - set(data))
        if uncovered:
            self.logger.warning(
                f"Preset '{name}' doesn't cover {len(uncovered)} new panel "
                f"settings. {self._update_hint(name)}"
            )
            self.logger.debug(f"Preset '{name}' uncovered keys: {', '.join(uncovered)}")

        applied = 0
        # Keys whose stored value no longer fits its widget (the setting changed
        # kind or lost choices since the save): skipped, never fatal -- one
        # misfit must not abort the load half-way.
        rejected: List[str] = []

        def fits(obj_name: str, write: Callable[[], Any]) -> bool:
            # A writer says "doesn't fit" by raising or, if it never raises
            # (StateManager.apply), by answering False; None is a write.
            try:
                written = write()
            except self._MISFIT_ERRORS as e:
                reason = str(e)
            else:
                if written is not False:
                    return True
                reason = "the widget refused it"
            rejected.append(obj_name)
            self.logger.debug(f"Preset '{name}' key '{obj_name}' skipped: {reason}")
            return False

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

                    # A kind-built widget is written by the factory that built it,
                    # not by StateManager — the same authority rule capture uses.
                    # StateManager would reach a composite (`path`, `file_list`) by
                    # guessing from its Qt type and write nothing.
                    factory = PresetManager._kind_factory()
                    if factory.kind_of(widget) is not None:
                        was_blocked = widget.signalsBlocked()
                        if block_signals:
                            widget.blockSignals(True)
                        try:
                            ok = fits(
                                obj_name,
                                lambda w=widget, v=value: factory.set_value(w, v),
                            )
                        finally:
                            if block_signals:
                                widget.blockSignals(was_blocked)
                        applied += ok
                        # Deliberately NOT added to applied_widgets: those get a
                        # `state.save()` below, and StateManager never owned these
                        # widgets. Their persistence is the preset store itself.
                        continue

                    # Mirror StateManager.reset_all: default False (the
                    # module-wide default) and restore-or-remove the attribute
                    # so a load never permanently stamps ``block_signals_on_restore``
                    # onto a widget that never had it (which would silently
                    # suppress slot execution on every future restore).
                    had_attr = hasattr(widget, "block_signals_on_restore")
                    original_block = getattr(widget, "block_signals_on_restore", False)
                    widget.block_signals_on_restore = block_signals
                    try:
                        if fits(
                            obj_name,
                            lambda w=widget, v=value: self.state.apply(w, v),
                        ):
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
                    applied += fits(
                        obj_name, lambda w=widget, v=value: self._write_widget(w, v)
                    )
            finally:
                for w in blocked:
                    w.blockSignals(False)

        if rejected:
            self.logger.warning(
                f"Preset '{name}': the panel can't use {len(rejected)} of its "
                "settings (they changed since it was saved), so those kept their "
                f"current values. {self._update_hint(name)}"
            )

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

    def is_read_only(self, name: str) -> bool:
        """True for a built-in, or a user preset locked in the Preset Editor.

        A locked preset can't be overwritten, renamed or deleted from the panel;
        Save offers ``"<name> copy"`` instead.
        """
        return self._store.is_read_only(name)

    def is_locked(self, name: str) -> bool:
        """True when *name* is a user preset that has been locked (not a built-in)."""
        store = self._store  # one build: the property rebuilds per access
        return store.source(name) == "user" and store.is_read_only(name)

    @property
    def key(self) -> Optional[str]:
        """This manager's store key under the presets root (see ``PresetStore.key``)."""
        return self._store.key

    @classmethod
    def notify(cls, keys: Optional[List[str]] = None) -> int:
        """Refresh the wired combos of live managers whose store changed.

        Called after presets were changed outside their panel -- the Preset
        Editor, a bundle import -- so an open selector shows the new list, lock
        marks and names without a manual Refresh. Values are never re-applied
        (see :meth:`refresh_combo`). *keys* limits it to those stores; ``None``
        refreshes every live combo. Returns how many combos were refreshed.

        Only this process: another running DCC catches up when its dropdown next
        opens (the combo re-lists on popup when the folder changed).
        """
        wanted = set(keys) if keys is not None else None
        count = 0
        for mgr in list(cls._live):
            try:
                if wanted is not None and mgr.key not in wanted:
                    continue
                mgr.refresh_combo()
                count += 1
            except RuntimeError:  # the combo's C++ side is gone
                cls._live.discard(mgr)
            except Exception as e:  # one broken panel must not stop the rest
                mgr.logger.debug(f"Preset notify failed: {e}")
        return count

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

    def read(self, name: str) -> Optional[Dict[str, Any]]:
        """Return preset *name*'s stored values WITHOUT applying them.

        The peek counterpart of :meth:`load`: same tier resolution (user
        shadows built-in), ``_meta`` stripped, but no widget/applier side
        effects and no active-preset bookkeeping. ``None`` when the preset
        is absent or unreadable. Lets an owner inspect the active preset at
        startup (e.g. which base theme a style preset targets) without
        triggering a full value re-apply.
        """
        try:
            return self._strip_meta(self._store.load(name))
        except (KeyError, ValueError, OSError):
            return None

    def refresh_combo(self, select_name: Optional[str] = None) -> None:
        """Repopulate the wired preset combo from disk (no-op when none).

        Public handle on :meth:`wire_combo`'s internal *refresh* closure so
        owners that change the store outside the combo's own toolbar (e.g.
        assigning :attr:`active_preset` programmatically at startup) can
        bring the display back in sync. Selection follows *select_name*,
        defaulting to the persisted active preset. Values are never applied.
        """
        if self._refresh_combo is not None:
            self._refresh_combo(select_name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _preset_path(self, name: str) -> Path:
        """Full path for a *user* preset name (sanitized).

        Kept for back-compat; the store is the tier-aware source of truth. Uses
        the shared sanitizer so a name maps to the same file as the headless path.
        """
        return self._store.path(name, "user")

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
        placeholder: Optional[str] = None,
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
            placeholder: Forwarded to :meth:`wire_combo` (no-selection text).

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
        container = self.wire_combo(combo, on_loaded=on_loaded, placeholder=placeholder)
        # Stash the combo on the container so callers don't have to dig through
        # the option-box layout to reach it.
        if container is not None:
            container.preset_combo = combo
        return container

    def wire_combo(self, combo, on_loaded=None, placeholder=None):
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
        edit" flow). A user preset *locked* in the Preset Editor is treated the
        same way, except that Save seeds ``"<name> copy"``: a locked preset can't
        be overwritten, so the save lands beside it.

        A preset *hidden* in the Preset Editor (built-ins too) is left out of
        the list -- it stays on disk and loads as before -- except the active
        one, which stays listed until the panel moves off it. An item's tooltip
        carries the preset's description, when it has one.

        The list re-reads the folder each time the dropdown opens (only
        repopulating when it changed), so presets added, locked, hidden or
        imported elsewhere -- another DCC, the Preset Editor -- show up without
        a manual Refresh.

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
            placeholder: Text shown when no preset is selected (default
                ``"Presets…"``). Lets an owner rebrand the selector — e.g.
                the style editor's ``"Themes…"``.

        Returns:
            The :attr:`option_box` container (combo + toolbar). Place this in
            your layout. When *combo* was already sitting in a layout, the
            container has already replaced it in-place and the return can be
            ignored.
        """
        from uitk.managers._preset_combo import _PresetComboWiring

        return _PresetComboWiring.wire(
            self, combo, on_loaded=on_loaded, placeholder=placeholder
        )

    # ------------------------------------------------------------------
    # Encapsulated helpers (formerly module-level functions)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_serializable(value: Any) -> bool:
        """Check if a value can be safely serialized to JSON.

        Attempts a real ``json.dumps`` rather than a shallow top-level type check,
        so a container holding a nested non-serializable element (e.g. a set or
        ``Path`` inside a dict/list) is correctly rejected. This keeps the capture
        gate consistent with the write path — ``PresetStore``'s JSON codec dumps
        with no ``default=str`` fallback, so a value that passes here must actually
        survive ``json.dumps`` or ``save()`` would raise an uncaught ``TypeError``.
        """
        try:
            json.dumps(value)
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def get_presets_root() -> Path:
        """Root directory under which every relative ``preset_dir`` is resolved.

        pythontk's ecosystem user-config root
        (:meth:`pythontk.UserConfig.user_config_root`), so the GUI store and
        the headless ``pythontk.PresetStore`` / ``UserConfig`` path can never
        disagree: one resolver, one owner. By default the host-independent
        per-user config dir plus a ``uitk`` wrapper folder that keeps the
        ecosystem's state grouped under one entry (``%LOCALAPPDATA%/uitk``,
        ``~/.config/uitk``, ``~/Library/Preferences/uitk``).

        Set ``UITK_PRESETS_ROOT`` (:data:`PRESETS_ROOT_ENV_VAR`) to redirect
        every relative preset path wholesale (network share, alternate drive,
        Documents subfolder...). The override is used as-given -- no implicit
        ``uitk/`` wrapper is appended -- and accepts ``~`` and ``%ENVVAR%``
        syntax; a relative override resolves against the working directory
        at access time, so the return is always absolute.
        """
        return ptk.UserConfig.user_config_root()


# ---------------------------------------------------------------------------
# Consolidated preset root
# ---------------------------------------------------------------------------
#
# All relative ``preset_dir`` values across the ecosystem resolve under a
# single root -- pythontk's ``UserConfig.user_config_root`` -- so a user looking
# for their saved data finds it in one place, and the GUI store and the headless
# ``PresetStore`` read the same files.
#
# Layout (Windows example; ``~/.config/...`` on Linux, ``~/Library/
# Preferences/...`` on Mac):
#
#     %LOCALAPPDATA%/uitk/         <- ecosystem wrapper folder
#     ├── uitk/                    <- uitk pkg state
#     ├── mayatk/                  <- mayatk pkg state
#     └── extapps/                 <- extapps pkg state
#
# The ``uitk/uitk/`` doubling for uitk's own state is intentional: outer
# ``uitk/`` is the wrapper namespace; inner ``uitk/`` is the package itself,
# consistent with how every other package's state lives under ``<wrapper>/<pkg>/``.
#
# Presets saved under older layouts are carried in on first access -- see
# ``uitk/managers/_preset_migration.py``.

#: Env var that redirects the whole root (pythontk owns the name; see
#: :meth:`PresetManager.get_presets_root`).
PRESETS_ROOT_ENV_VAR = ptk.UserConfig.CONFIG_ROOT_ENV_VAR


# ---------------------------------------------------------------------------
# Back-compat module-level aliases
# ---------------------------------------------------------------------------
# These were module-level functions before being encapsulated on
# PresetManager as @staticmethods. Re-exported at module scope for external
# callers/tests that import or reference them by module attribute
# (e.g. test/test_preset_manager.py). NOTE: reassigning one of these module
# attributes (monkeypatch) will NOT affect the migration's internal calls,
# which resolve via their owner, ``_preset_migration._PresetRootMigration``.
QStandardPaths_writableLocation = PresetManager.QStandardPaths_writableLocation
QStandardPaths_genericConfigLocation = (
    PresetManager.QStandardPaths_genericConfigLocation
)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ...
