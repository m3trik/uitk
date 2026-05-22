# !/usr/bin/python
# coding=utf-8
import json
import logging
import os
import shutil
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Set, Union

from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk

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
          ``<QStandardPaths.AppConfigLocation>``).

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
    "extapps/map_packer": "~/.pythontk/presets/map_packer",
    "uitk/style_presets": "{APPCONFIG}/uitk/style_presets",
    "uitk/hotkey_presets": "{APPCONFIG}/uitk/hotkey_presets",
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


def _looks_like_ecosystem_wrapper(uitk_dir: Path, known_pkgs: Set[str]) -> bool:
    """True when *uitk_dir* is already in the wrapper layout.

    A *clean* wrapper layout has only known-package subdirs (uitk /
    mayatk / extapps) and possibly dotfiles. Anything else at the root
    level — ``style_presets``, ``hotkey_presets``, ``some_window``, ... —
    is pre-wrap state that needs to be moved one level deeper.

    Strict matching (vs. "any known-pkg present") also recovers from a
    *partial* wrap: if a prior wrap was interrupted after creating the
    inner ``uitk/`` subdir but before moving every stray sibling, the
    next call still detects the strays as pre-wrap and finishes the
    job.

    Empty dirs count as "already wrapped" (no data to move; treating
    them as pre-wrap would create a useless empty ``uitk/`` subdir).
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
    non-known-pkg / non-dotfile child as evidence of pre-wrap state,
    so a partial wrap (inner ``uitk/`` already created, some siblings
    not yet moved) gets finished on the next call.

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


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ...
