# !/usr/bin/python
# coding=utf-8
import json
import os
import shutil
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Set, Union

from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk


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
    ):
        super().__init__()
        self.set_log_level(log_level)
        self.parent = parent
        self.state = state
        self._explicit_widgets = list(widgets) if widgets is not None else None
        self._excluded_widgets: Set[QtWidgets.QWidget] = set()

        if preset_dir is not None:
            self._preset_dir = self._resolve_preset_dir(preset_dir)
        else:
            self._preset_dir = None

        self.metadata_provider: Optional[Callable[[], dict]] = None
        self.on_metadata_loaded: Optional[Callable[[dict], None]] = None

        self._on_change_callbacks = []

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
          ``<AppConfigLocation>/m3trik/presets``).

        Returns:
            An absolute `Path`.
        """
        p = Path(os.path.expandvars(str(raw))).expanduser()
        if not p.is_absolute():
            p = get_presets_root() / p
        return p

    @classmethod
    def from_widgets(
        cls,
        preset_dir,
        widgets: List[QtWidgets.QWidget],
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
        return cls(preset_dir=preset_dir, widgets=widgets)

    def setup(
        self,
        preset_dir=None,
        widgets: Optional[List[QtWidgets.QWidget]] = None,
        on_loaded=None,
        metadata_provider: Optional[Callable[[], dict]] = None,
        on_metadata_loaded: Optional[Callable[[dict], None]] = None,
    ) -> "PresetManager":
        """Configure and optionally auto-wire a preset combo.

        This is the post-creation counterpart of ``from_widgets``.  It is
        intended for use with the lazy ``menu.presets`` / ``window.presets``
        namespaces where the instance is created before the caller knows
        which widgets or directory to use.

        When *widgets* is omitted and the manager's parent has a
        ``get_items()`` method (e.g. a ``Menu``), widgets are
        auto-discovered at save/load time — no explicit list needed.

        When the parent is a ``Menu``, a ``WidgetComboBox`` is
        automatically created and wired as the preset selector — no
        manual ``wire_combo`` call is required.

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
        if widgets is not None:
            self._explicit_widgets = list(widgets)
        if metadata_provider is not None:
            self.metadata_provider = metadata_provider
        if on_metadata_loaded is not None:
            self.on_metadata_loaded = on_metadata_loaded

        # Auto-create and wire a preset combo when parent is a Menu
        if hasattr(self.parent, "add") and hasattr(self.parent, "get_items"):
            from uitk.widgets.widgetComboBox import WidgetComboBox

            combo = self.parent.add(
                WidgetComboBox,
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

        _maybe_migrate_legacy(self._preset_dir)
        self._preset_dir.mkdir(parents=True, exist_ok=True)
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
        widgets = self._get_widgets(scope)
        data: Dict[str, Any] = {"_meta": {"version": self.PRESET_VERSION}}

        if self.metadata_provider is not None:
            data["_meta"].update(self.metadata_provider())

        for widget in widgets:
            obj_name = widget.objectName()
            if not obj_name:
                continue

            if self.state is not None:
                value = self.state._get_current_value(widget)
            else:
                value = self._get_widget_value(widget)

            if value is not None and _is_serializable(value):
                data[obj_name] = value

        filepath = self._preset_path(name)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        self.logger.debug(
            f"Saved preset '{name}' ({len(data) - 1} widgets) -> {filepath}"
        )
        self._notify_change()
        return filepath

    def load(
        self,
        name: str,
        scope: Optional[QtWidgets.QWidget] = None,
        block_signals: bool = True,
    ) -> int:
        """Load a named preset and apply its values to the matching widgets.

        Session auto-save is suppressed during application so that loading
        a preset does not overwrite the user's QSettings session state.

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
        filepath = self._preset_path(name)
        if not filepath.exists():
            self.logger.warning(f"Preset file not found: {filepath}")
            return 0

        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                self.logger.warning(f"Invalid preset file '{name}': {e}")
                return 0

        # Extract and dispatch metadata
        meta = data.pop("_meta", {})
        if self.on_metadata_loaded is not None and meta:
            self.on_metadata_loaded(meta)

        widgets = self._get_widgets(scope)
        widget_map = {w.objectName(): w for w in widgets if w.objectName()}

        applied = 0

        if self.state is not None:
            # MainWindow path: delegate to StateManager with suppress_save
            with self.state.suppress_save():
                for obj_name, value in data.items():
                    widget = widget_map.get(obj_name)
                    if widget is None:
                        self.logger.debug(
                            f"Preset key '{obj_name}' has no matching widget, skipping."
                        )
                        continue

                    original_block = getattr(widget, "block_signals_on_restore", True)
                    widget.block_signals_on_restore = block_signals
                    try:
                        self.state.apply(widget, value)
                        applied += 1
                    finally:
                        widget.block_signals_on_restore = original_block
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
        return applied

    def list(self) -> List[str]:
        """Return a sorted list of available preset names.

        Returns:
            List of preset name strings (without file extension).
        """
        if not self.preset_dir.exists():
            return []
        return sorted(p.stem for p in self.preset_dir.glob("*.json"))

    def delete(self, name: str) -> bool:
        """Delete a named preset file.

        Parameters:
            name: The preset name to delete.

        Returns:
            True if the file was deleted, False if it did not exist.
        """
        filepath = self._preset_path(name)
        if filepath.exists():
            filepath.unlink()
            self.logger.debug(f"Deleted preset '{name}': {filepath}")
            self._notify_change()
            return True
        self.logger.debug(f"Preset '{name}' does not exist.")
        return False

    def rename(self, old_name: str, new_name: str) -> bool:
        """Rename an existing preset.

        Parameters:
            old_name: The current preset name.
            new_name: The desired new name.

        Returns:
            True if renamed successfully, False otherwise.
        """
        old_path = self._preset_path(old_name)
        new_path = self._preset_path(new_name)

        if not old_path.exists():
            self.logger.warning(f"Cannot rename: preset '{old_name}' not found.")
            return False
        if new_path.exists():
            self.logger.warning(f"Cannot rename: preset '{new_name}' already exists.")
            return False

        old_path.rename(new_path)
        self.logger.debug(f"Renamed preset '{old_name}' -> '{new_name}'")
        self._notify_change()
        return True

    def exists(self, name: str) -> bool:
        """Check whether a named preset exists on disk."""
        return self._preset_path(name).exists()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _preset_path(self, name: str) -> Path:
        """Return the full file path for a preset name."""
        # Sanitize name: replace path separators and other unsafe chars
        safe_name = "".join(
            c if c.isalnum() or c in ("-", "_", " ") else "_" for c in name
        )
        return self.preset_dir / f"{safe_name}.json"

    def _get_widgets(
        self, scope: Optional[QtWidgets.QWidget] = None
    ) -> Set[QtWidgets.QWidget]:
        """Return the set of restorable widgets within the given scope.

        Resolution order:

        1. **Explicit list** — if *widgets* was provided via constructor or
           ``setup()``, use that list directly.
        2. **Menu auto-discovery** — if the *parent* has a ``get_items()``
           method (e.g. a ``Menu``), iterate its items and keep only those
           whose type is supported by ``_get_widget_value``.
        3. **MainWindow registered set** — filter by ``restore_state`` and
           optional *scope* containment.

        In all cases, widgets in ``_excluded_widgets`` (e.g. the preset
        combo wired via ``wire_combo``) are omitted.

        Parameters:
            scope: A container widget to limit the search. If None, all
                registered widgets on the parent are returned.

        Returns:
            A set of widgets.
        """
        if self._explicit_widgets is not None:
            return {
                w
                for w in self._explicit_widgets
                if w.objectName() and w not in self._excluded_widgets
            }

        # Menu auto-discovery
        if hasattr(self.parent, "get_items"):
            return {
                w
                for w in self.parent.get_items()
                if w.objectName()
                and w not in self._excluded_widgets
                and self._get_widget_value(w) is not None
            }

        # MainWindow registered set
        registered = getattr(self.parent, "widgets", set())

        if scope is not None and scope is not self.parent:
            scope_children = set(scope.findChildren(QtWidgets.QWidget))
            candidates = registered & scope_children
        else:
            candidates = registered

        return {
            w
            for w in candidates
            if getattr(w, "restore_state", False)
            and w.objectName()
            and w not in self._excluded_widgets
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

    def wire_combo(self, combo, on_loaded=None) -> None:
        """Wire a ``WidgetComboBox`` as a fully-functional preset selector.

        Adds **Save / Rename / Delete / Open Folder** actions to the
        combo's action section, populates it with existing presets, and
        connects selection changes to ``load()``.

        The combo shows the *current preset name* as its selected item.
        When no presets exist the combo is empty and displays
        placeholder text (``"No saved presets"``).

        Parameters:
            combo: A ``WidgetComboBox`` to populate and wire.
            on_loaded: Optional callable invoked (with no arguments) after
                a preset is successfully loaded.  When omitted, widget
                signals are left unblocked so slot handlers fire naturally.
        """
        mgr = self

        def refresh(select_name: Optional[str] = None):
            """Repopulate the combo with current preset names.

            Parameters:
                select_name: If given, select this preset after repopulating.
                    If None, no item is pre-selected.
            """
            names = mgr.list()
            combo.blockSignals(True)
            try:
                combo.clear()
                if names:
                    combo.addItems(names)
                    if select_name:
                        idx = combo.findText(select_name)
                        if idx >= 0:
                            combo.setCurrentIndex(idx)
                        else:
                            combo.setCurrentIndex(0)
                    else:
                        combo.setCurrentIndex(-1)
                    combo.setPlaceholderText("Select a preset\u2026")
                else:
                    combo.setPlaceholderText("No saved presets")
            finally:
                combo.blockSignals(False)
            # clear() destroys all model rows including the action section;
            # rebuild so Save/Rename/Delete/Open Folder appear at the bottom.
            combo._rebuild_actions_section()

        def on_selected(idx):
            if idx < 0:
                return
            name = combo.itemText(idx)
            if name:
                # When on_loaded is provided, block signals during load
                # and fire the single consolidated callback afterwards.
                # Otherwise, let signals propagate so normal slot handlers
                # (e.g. checkbox → refresh) fire automatically.
                mgr.load(name, block_signals=on_loaded is not None)
                if on_loaded:
                    on_loaded()

        def on_save():
            parent_w = combo.window() or combo
            name, ok = QtWidgets.QInputDialog.getText(
                parent_w, "Save Preset", "Preset name:"
            )
            if ok and name.strip():
                name = name.strip()
                mgr.save(name)
                refresh(select_name=name)

        def on_rename():
            idx = combo.currentIndex()
            if idx < 0:
                return
            current = combo.itemText(idx)
            if not current:
                return
            parent_w = combo.window() or combo
            new_name, ok = QtWidgets.QInputDialog.getText(
                parent_w, "Rename Preset", "New name:", text=current
            )
            if ok and new_name.strip() and new_name.strip() != current:
                new_name = new_name.strip()
                mgr.rename(current, new_name)
                refresh(select_name=new_name)

        def on_delete():
            idx = combo.currentIndex()
            if idx < 0:
                return
            current = combo.itemText(idx)
            if not current:
                return
            mgr.delete(current)
            refresh()

        def on_open_folder():
            """Open the preset directory in the system file explorer."""
            preset_dir = mgr.preset_dir
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(preset_dir)))

        self._excluded_widgets.add(combo)
        self._refresh_combo = refresh

        actions = combo.actions.add(
            {
                "Save": on_save,
                "Rename": on_rename,
                "Delete": on_delete,
                "Open Folder": on_open_folder,
            }
        )
        # Apply SVG icons (save / edit / trash / folder).
        try:
            from uitk.widgets.mixins.icon_manager import IconManager

            for action, icon_name in zip(actions, ("save", "edit", "trash", "folder")):
                action.setIcon(IconManager.get(icon_name, size=(14, 14)))
            combo._rebuild_actions_section()
        except Exception:
            pass

        refresh()
        combo.currentIndexChanged.connect(on_selected)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _is_serializable(value: Any) -> bool:
    """Check if a value can be safely serialized to JSON."""
    return isinstance(value, (int, float, str, bool, list, dict, tuple))


def QStandardPaths_writableLocation() -> str:
    """Return the platform-appropriate writable config directory."""
    return QtCore.QStandardPaths.writableLocation(
        QtCore.QStandardPaths.AppConfigLocation
    )


# ---------------------------------------------------------------------------
# Consolidated preset root
# ---------------------------------------------------------------------------
#
# All relative ``preset_dir`` values across the ecosystem resolve under a
# single root, so a user looking for their saved data finds it in one place
# instead of three (``~/.mayatk/presets``, ``~/.pythontk/presets``,
# ``%LOCALAPPDATA%/uitk/*-presets``). The default lives under Qt's
# AppConfigLocation (platform-native, not sync'd) and can be redirected
# wholesale by setting ``M3TRIK_PRESETS_ROOT``.
#
# Existing presets from the legacy locations are copied in on first access
# (see ``_maybe_migrate_legacy``). Completion is recorded by writing an
# empty sentinel file per migrated package under ``<root>/.migration/`` —
# per-key files avoid the read-modify-write race that a shared state file
# would have when multiple host processes (Maya + Painter + CLI) start at
# once.

PRESETS_ROOT_ENV_VAR = "M3TRIK_PRESETS_ROOT"
_PRESETS_ROOT_DEFAULT_SUBDIR = ("m3trik", "presets")
_MIGRATION_DIR_NAME = ".migration"

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
    "extapps/map_packer": "~/.pythontk/presets/map_packer",
    "uitk/style_presets": "{APPCONFIG}/uitk/style_presets",
    "uitk/hotkey_presets": "{APPCONFIG}/uitk/hotkey_presets",
    "uitk/switchboard_browser/presets": "{APPCONFIG}/uitk/switchboard_browser/presets",
}


def get_presets_root() -> Path:
    """Root directory under which every relative ``preset_dir`` is resolved.

    Defaults to ``<QStandardPaths.AppConfigLocation>/m3trik/presets``
    (e.g. ``%LOCALAPPDATA%/m3trik/presets`` on Windows). Set the
    ``M3TRIK_PRESETS_ROOT`` environment variable to redirect every
    relative preset path wholesale (network share, alternate drive,
    Documents subfolder, etc.). The override accepts ``~`` and
    ``%ENVVAR%`` syntax; relative overrides are resolved against the
    process working directory at access time so the return is always
    absolute.
    """
    override = os.environ.get(PRESETS_ROOT_ENV_VAR)
    if override:
        p = Path(os.path.expandvars(override)).expanduser()
    else:
        p = Path(QStandardPaths_writableLocation()).joinpath(
            *_PRESETS_ROOT_DEFAULT_SUBDIR
        )
    return p if p.is_absolute() else p.absolute()


def _resolve_legacy_template(template: str) -> Path:
    """Expand ``{APPCONFIG}``, environment variables, and ``~`` in *template*."""
    if "{APPCONFIG}" in template:
        template = template.replace("{APPCONFIG}", QStandardPaths_writableLocation())
    return Path(os.path.expandvars(template)).expanduser()


def _migration_sentinel_path(key: str) -> Path:
    """Path to the per-key sentinel file marking a completed migration."""
    safe = key.replace("/", "__").replace("\\", "__")
    return get_presets_root() / _MIGRATION_DIR_NAME / safe


def _has_migrated(key: str) -> bool:
    return _migration_sentinel_path(key).exists()


def _mark_migrated(key: str) -> None:
    p = _migration_sentinel_path(key)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch(exist_ok=True)
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
                dest = new_pkg_root / item.name
                if dest.exists():
                    continue
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
        except (OSError, shutil.Error):
            pass  # see docstring: best-effort

    _mark_migrated(matched_key)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ...
