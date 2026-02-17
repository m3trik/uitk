# !/usr/bin/python
# coding=utf-8
import json
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Set

from qtpy import QtWidgets, QtCore
import pythontk as ptk


class PresetManager(ptk.LoggingMixin):
    """Manages named presets for widget state, stored as external JSON files.

    This class works alongside StateManager (which handles implicit session
    persistence via QSettings) to provide explicit, user-driven preset
    save/load functionality. It delegates all widget value operations to
    StateManager to ensure consistent edge-case handling.

    Architecture:
        - PresetManager owns file I/O and preset orchestration.
        - StateManager owns widget value get/set/apply (reused, not duplicated).
        - MainWindow owns the widget registry and signal routing.

    Preset files are flat key-value JSON::

        {
            "_meta": {"version": 1},
            "myCheckBox": true,
            "mySpinBox": 42,
            "myComboBox": "Option B"
        }

    Attributes:
        parent: The root widget (typically MainWindow) whose children are managed.
        state: The StateManager instance used for value get/set operations.
        preset_dir: Directory where preset JSON files are stored.
    """

    PRESET_VERSION = 1

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        state: "StateManager",
        preset_dir: Optional[Path] = None,
    ):
        super().__init__()
        self.logger.setLevel("WARNING")
        self.parent = parent
        self.state = state

        if preset_dir is not None:
            self._preset_dir = Path(preset_dir)
        else:
            self._preset_dir = None

    @property
    def preset_dir(self) -> Path:
        """The directory where preset files are stored.

        Defaults to ``<AppConfigLocation>/<window_name>/presets/``.
        Created on first access.
        """
        if self._preset_dir is None:
            base = QStandardPaths_writableLocation()
            window_name = self.parent.objectName() or "default"
            self._preset_dir = Path(base) / window_name / "presets"

        self._preset_dir.mkdir(parents=True, exist_ok=True)
        return self._preset_dir

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

        for widget in widgets:
            obj_name = widget.objectName()
            if not obj_name:
                continue

            value = self.state._get_current_value(widget)
            if value is not None and _is_serializable(value):
                data[obj_name] = value

        filepath = self._preset_path(name)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        self.logger.debug(
            f"Saved preset '{name}' ({len(data) - 1} widgets) -> {filepath}"
        )
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

        # Strip metadata
        data.pop("_meta", None)

        widgets = self._get_widgets(scope)
        widget_map = {w.objectName(): w for w in widgets if w.objectName()}

        applied = 0
        with self.state.suppress_save():
            for obj_name, value in data.items():
                widget = widget_map.get(obj_name)
                if widget is None:
                    self.logger.debug(
                        f"Preset key '{obj_name}' has no matching widget, skipping."
                    )
                    continue

                # Temporarily override signal blocking preference
                original_block = getattr(widget, "block_signals_on_restore", True)
                widget.block_signals_on_restore = block_signals
                try:
                    self.state.apply(widget, value)
                    applied += 1
                finally:
                    widget.block_signals_on_restore = original_block

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
        safe_name = "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in name)
        return self.preset_dir / f"{safe_name}.json"

    def _get_widgets(
        self, scope: Optional[QtWidgets.QWidget] = None
    ) -> Set[QtWidgets.QWidget]:
        """Return the set of restorable widgets within the given scope.

        Parameters:
            scope: A container widget to limit the search. If None, all
                registered widgets on the parent are returned.

        Returns:
            A set of widgets that have restore_state=True.
        """
        registered = getattr(self.parent, "widgets", set())

        if scope is not None and scope is not self.parent:
            # Get all children of the scope container and intersect with
            # the registered set to ensure we only touch known widgets.
            scope_children = set(scope.findChildren(QtWidgets.QWidget))
            candidates = registered & scope_children
        else:
            candidates = registered

        return {
            w
            for w in candidates
            if getattr(w, "restore_state", False) and w.objectName()
        }


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


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ...
