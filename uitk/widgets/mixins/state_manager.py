# !/usr/bin/python
# coding=utf-8
import enum
import json
import weakref
from contextlib import contextmanager
from typing import Any, Optional
from qtpy import QtWidgets, QtCore
import pythontk as ptk
from uitk.widgets.mixins.value_manager import ValueManager


class StateManager(ptk.LoggingMixin):
    """Manages widget state persistence using QSettings.

    This class has been refactored to use WidgetValueManager for all value
    getting/setting operations, eliminating code duplication and ensuring
    consistent behavior across the codebase.

    Widget Attributes:
    - restore_state (bool): If True, widget state is saved/restored. Default: True
    - block_signals_on_restore (bool): If True, signals are blocked during state
      restoration to prevent side effects. Set to True for widgets where restore
      should be cosmetic only (no slot execution). Default: False

    Protections:
    - Skips applying None values to text-based widgets to prevent clearing valid text
    - Only saves primitive types (int, float, str, bool) to prevent state corruption
    - Handles non-stateful signals (like 'clicked') by not triggering state sync
    """

    # Sentinel returned by ``_coerce_for_store`` for values QSettings can't
    # round-trip — distinct from a legitimately stored ``None``.
    _UNSUPPORTED = object()

    # Index-based widgets (combo boxes) report ``-1`` for "no selection",
    # which they briefly do while their model is being (re)populated.
    _INDEX_SIGNAL = "currentIndexChanged"
    _NO_SELECTION = -1

    # Combo persistence modes (opt in per widget via ``widget.restore_by``).
    #
    # ``"index"`` (default) stores ``currentIndexChanged``'s integer index --
    # correct only for a *static* item list. ``"text"`` / ``"data"`` store the
    # selected item's text / ``itemData`` instead -- a STABLE identity that
    # survives the list being reordered, grown, or shrunk between sessions.
    # Use them for a combo whose items are rebuilt at runtime (e.g. populated
    # from a directory scan): an index saved against one population silently
    # selects the wrong item -- or, when the list is now shorter, falls out of
    # range and resets the combo to item 0 -- on the next session's restore.
    _RESTORE_MODES = ("index", "text", "data")

    def __init__(self, qsettings: QtCore.QSettings, log_level="WARNING"):
        super().__init__()
        self.set_log_level(log_level)
        self.qsettings = qsettings
        # Weak keys: a plain dict pins every registered widget for the
        # manager's lifetime, and reset_all would then iterate wrappers
        # whose C++ object is long gone.
        self._defaults = weakref.WeakKeyDictionary()
        self._save_suppressed = 0

    def _get_settings(self, widget: QtWidgets.QWidget) -> QtCore.QSettings:
        return self.qsettings

    def _get_state_key(
        self, widget: QtWidgets.QWidget, prefix: str = ""
    ) -> Optional[str]:
        """Returns the state key for a widget based on its objectName and signal type."""
        if not getattr(widget, "restore_state", False):
            return None
        name = widget.objectName()
        signal_name = widget.derived_type and widget.default_signals()
        if not name or not signal_name:
            self.logger.debug(f"Invalid state key: name={name}, signal={signal_name}")
            return None
        return f"{prefix}{name}/{signal_name}"

    @classmethod
    def _restore_mode(cls, widget: QtWidgets.QWidget) -> str:
        """Resolve a widget's combo-persistence mode (see :data:`_RESTORE_MODES`).

        Reads ``widget.restore_by`` (default / unrecognized -> ``"index"``), so
        every existing widget keeps the prior index-based behavior unless it
        explicitly opts in.
        """
        mode = getattr(widget, "restore_by", "index") or "index"
        return mode if mode in cls._RESTORE_MODES else "index"

    def _get_current_value(self, widget: QtWidgets.QWidget) -> Any:
        """Get the current value from the widget using ValueManager."""
        # Stable-identity combo modes capture text / data, not the index, so the
        # stored value matches what :meth:`apply` looks up on restore.
        mode = self._restore_mode(widget)
        if mode == "text" and hasattr(widget, "currentText"):
            return widget.currentText()
        if mode == "data" and hasattr(widget, "currentData"):
            return widget.currentData()
        signal_name = widget.derived_type and widget.default_signals()
        if signal_name:
            # Use signal-based approach for compatibility
            return ValueManager.get_value_by_signal(widget, signal_name)
        else:
            # Fallback to direct value getting
            return ValueManager.get_value(widget)

    @contextmanager
    def _restore_signal_scope(self, widget: QtWidgets.QWidget):
        """Block/unblock *widget* per ``block_signals_on_restore`` for a value
        application, then restore the caller's prior blocked state.

        Default (``False``) leaves signals live so dependent slots fire on
        restore. Saving/restoring the prior state (rather than force-unblocking)
        keeps an outer ``blockSignals(True)`` context — e.g. ``init_slot`` —
        intact afterwards. Shared by :meth:`apply` and :meth:`_apply_combo_identity`.
        """
        block_signals = getattr(widget, "block_signals_on_restore", False)
        previously_blocked = widget.signalsBlocked()
        widget.blockSignals(block_signals)
        try:
            yield
        finally:
            widget.blockSignals(previously_blocked)

    def apply(self, widget: QtWidgets.QWidget, value: Any) -> None:
        """Apply the given value to the widget using ValueManager."""
        # Stable-identity combo modes select by text / data (not index), which
        # sidesteps the out-of-range index guard below entirely.
        mode = self._restore_mode(widget)
        if mode != "index" and hasattr(widget, "setCurrentIndex"):
            self._apply_combo_identity(widget, value, mode)
            return

        signal_name = widget.derived_type and widget.default_signals()

        # A stored index can outrun a not-yet-populated model (e.g. a
        # combobox whose items load lazily, or a surface restored before its
        # init runs). Applying it would silently clamp/no-op, and a later
        # change could then persist the wrong (lower) index. Skip until the
        # model is large enough; the value stays on disk for a fuller restore.
        if (
            signal_name == self._INDEX_SIGNAL
            and isinstance(value, int)
            and value >= 0
        ):
            count = getattr(widget, "count", None)
            if callable(count) and value >= count():
                self.logger.debug(
                    f"Skipping out-of-range index {value} for "
                    f"{widget.objectName()} (count={count()})"
                )
                return

        # Don't apply None values for text-based widgets to prevent clearing valid text
        if value is None:
            if hasattr(widget, "text") and callable(widget.text):
                # Skip applying None to widgets with text (like QPushButton, QLineEdit, etc.)
                self.logger.debug(
                    f"Skipping apply of None value to text widget {widget.objectName()}"
                )
                return

        # Honor ``block_signals_on_restore`` (default False) so an outer
        # blockSignals(True) — e.g. init_slot — can't silently suppress the
        # connected slot during state restore.
        with self._restore_signal_scope(widget):
            try:
                if signal_name:
                    # Use signal-based approach for compatibility with existing behavior
                    ValueManager.set_value_by_signal(
                        widget, value, signal_name, block_signals=False
                    )
                else:
                    # Fallback to direct value setting
                    ValueManager.set_value(widget, value, block_signals=False)

                # Force visual update since signals may be blocked
                widget.update()
            except Exception as e:
                self.logger.debug(
                    f"Could not apply value '{value}' to widget {widget}: {e}"
                )

    def _apply_combo_identity(self, widget: QtWidgets.QWidget, value: Any, mode: str) -> None:
        """Select a combo item by stable identity (``text`` / ``data``).

        The text/data counterpart of :meth:`apply`'s index path: it resolves the
        target item via ``findText`` / ``findData`` and selects it, honoring
        ``block_signals_on_restore`` exactly as the index path does (default
        ``False`` -> the selection signal fires so dependent slots run on
        restore). A value that's no longer present -- e.g. the saved preset was
        deleted between sessions -- is a no-op: the combo keeps its current
        selection rather than being forced to item 0.
        """
        # ``None`` is the *absence* of a stored selection, not a request to pick
        # an item literally named "None" (which ``findText(str(None))`` would do).
        if value is None:
            return
        with self._restore_signal_scope(widget):
            try:
                if mode == "text":
                    index = widget.findText(str(value))
                else:  # "data"
                    index = widget.findData(value)
                if index is not None and index >= 0:
                    widget.setCurrentIndex(index)
                    widget.update()
                else:
                    self.logger.debug(
                        f"Restore-by-{mode}: {value!r} not in {widget.objectName()}; "
                        "keeping current selection."
                    )
            except Exception as e:
                self.logger.debug(
                    f"Could not restore {widget.objectName()} by {mode}={value!r}: {e}"
                )

    @contextmanager
    def suppress_save(self):
        """Context manager that temporarily suppresses QSettings writes.

        Use this when applying values to widgets (e.g. loading a preset)
        without overwriting the user's session state in QSettings.

        Example::

            with state_manager.suppress_save():
                state_manager.apply(widget, preset_value)
        """
        self._save_suppressed += 1
        try:
            yield
        finally:
            self._save_suppressed -= 1

    def _coerce_for_store(self, value: Any) -> Any:
        """Coerce a value into something QSettings round-trips losslessly.

        Returns :data:`_UNSUPPORTED` for types that can't be persisted, so
        callers can distinguish "drop this write" from a stored ``None``.
        """
        # PySide6 Qt enums (e.g. Qt.CheckState from checkState()) are not
        # int subclasses — without this coercion the primitive-type gate
        # below silently dropped tri-state checkbox state.
        if isinstance(value, enum.Enum):
            value = value.value
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value)
        if isinstance(value, (int, float, str, bool)):
            return value
        return self._UNSUPPORTED

    def save(self, widget: QtWidgets.QWidget, value: Any = None) -> None:
        """Save the current value of the widget to QSettings.

        If no value is provided, it attempts to retrieve it automatically
        using the widget's default signal mapping.

        Writes are silently skipped when ``suppress_save`` is active.

        Parameters:
            widget (QtWidgets.QWidget): The widget whose state should be saved.
            value (Any, optional): The value to save. If None, it will be derived.
        """
        if self._save_suppressed:
            return

        # In a stable-identity combo mode the change signal still delivers an
        # INDEX (``currentIndexChanged``); ignore it and capture the text/data
        # identity instead, so what's stored matches what ``apply`` restores.
        mode = self._restore_mode(widget)
        if value is None or mode != "index":
            value = self._get_current_value(widget)
            # Don't persist a transient "no selection" (empty text / absent
            # data) -- the identity-mode analog of the index mode's -1 guard.
            # A repopulate that briefly empties the combo would otherwise wipe
            # the stored selection before the real value is re-applied.
            if mode != "index" and (value is None or value == ""):
                return

        key = self._get_state_key(widget)
        if not key:
            return

        self.save_value(key, value)

    def save_value(self, key: str, value: Any) -> None:
        """Serialize and persist ``value`` at an explicit state ``key``.

        Lower-level companion to :meth:`save`: it writes (and per-write
        syncs) without needing a live widget wrapper, so a value can be
        mirrored into a *related surface's* store — see
        ``MainWindow.sync_widget_values``. Shares save()'s serialization and
        the no-selection guard, keeping a single write chokepoint.

        Writes are silently skipped when ``suppress_save`` is active.
        """
        if self._save_suppressed:
            return

        # Combo/index widgets briefly report ``-1`` (no selection) while
        # their model is being (re)populated; persisting that transient
        # would wipe a valid stored index. The real selection saves on the
        # next change.
        if value == self._NO_SELECTION and key.endswith(f"/{self._INDEX_SIGNAL}"):
            self.logger.debug(f"Skipping no-selection (-1) transient for {key}")
            return

        stored = self._coerce_for_store(value)
        if stored is self._UNSUPPORTED:
            self.logger.debug(f"Unsupported type for {key}: {type(value)}")
            return

        try:
            store = self.qsettings
            store.setValue(key, stored)
            # Belt-and-braces sync alongside the canonical
            # ``MainWindow.on_close``/``on_hide`` sync wires. Some host
            # apps (notably Maya on Windows) can exit without delivering
            # closeEvent to child windows, dropping QSettings' in-memory
            # write cache. Per-save sync makes state durable regardless
            # of how the process tears down. Cheap on Windows (registry
            # writes are sub-millisecond); for high-frequency signals
            # (slider drag) on slower QSettings backends, consider
            # adding a debounce in ``sync_widget_values`` upstream
            # rather than removing this sync.
            sync = getattr(store, "sync", None)
            if callable(sync):
                sync()
            self.logger.debug(f"Stored state: {key} -> {stored}")
        except Exception as e:
            self.logger.warning(f"Failed to store state for {key}: {e}")

    def load(self, widget: QtWidgets.QWidget) -> None:
        """Load the saved value from QSettings and apply it to the widget."""
        key = self._get_state_key(widget)
        if not key:
            return

        if widget not in self._defaults:
            self._defaults[widget] = self._get_current_value(widget)

        try:
            value = self._get_settings(widget).value(key)
            if value is not None:
                # Only JSON-decode raw strings. A SettingsManager (what
                # MainWindow actually passes here, despite the QSettings type
                # hint) has *already* decoded the value, so a second
                # json.loads on the decoded result is both redundant and
                # lossy — e.g. decoding the bool ``True`` would raise and
                # silently fall back. Guarding on ``str`` keeps the raw
                # QSettings path working without double-decoding.
                #
                # Stable-identity combo modes store the item *text*/*data*
                # verbatim; skip decoding so a preset literally named "123" or
                # "true" stays that string instead of becoming int/bool.
                if isinstance(value, str) and self._restore_mode(widget) == "index":
                    try:
                        parsed_value = json.loads(value)
                    except json.JSONDecodeError:
                        parsed_value = value
                else:
                    parsed_value = value
                with self.suppress_save():
                    self.apply(widget, parsed_value)
                self.logger.debug(f"Loaded state: {key} -> {parsed_value}")
        except EOFError:
            self.logger.debug(f"EOFError reading state for {key}")

    def reset_all(self, block_signals: bool = False) -> None:
        """Reset all widgets with stored defaults to their original values.

        Parameters:
            block_signals: If True, block signals during reset. If False (default),
                signals will fire which ensures proper UI updates.

        Note:
            Widgets with `exclude_from_reset=True` attribute will be skipped.
        """
        for widget, default_value in list(self._defaults.items()):
            # A live wrapper can outlast its C++ object; touching it raises
            # RuntimeError. Drop the entry instead of crashing the reset.
            try:
                widget.objectName()
            except RuntimeError:
                self._defaults.pop(widget, None)
                continue

            # Skip widgets explicitly excluded from reset
            if getattr(widget, "exclude_from_reset", False):
                self.logger.debug(
                    f"Skipping reset for {widget.objectName()} (exclude_from_reset=True)"
                )
                continue

            # Temporarily override block_signals_on_restore if specified.
            # Default matches module-wide default (False) so widgets that
            # never had the attribute don't inherit it as True post-reset.
            had_attr = hasattr(widget, "block_signals_on_restore")
            original_block = getattr(widget, "block_signals_on_restore", False)
            widget.block_signals_on_restore = block_signals
            try:
                self.apply(widget, default_value)
                self._sync_stored_default(widget, default_value)
            finally:
                if had_attr:
                    widget.block_signals_on_restore = original_block
                else:
                    try:
                        del widget.block_signals_on_restore
                    except AttributeError:
                        widget.block_signals_on_restore = original_block

    def reset(self, widget: QtWidgets.QWidget) -> None:
        """Reset a widget to its default value."""
        if widget in self._defaults:
            default = self._defaults[widget]
            self.apply(widget, default)
            self._sync_stored_default(widget, default)

    def _sync_stored_default(self, widget: QtWidgets.QWidget, default_value: Any) -> None:
        """Let a stored-value override on the widget re-sync to the new default.

        An option-box *reset* toggle in bypass mode holds a snapshot of the
        user's value while the field shows its default; without this, a
        centralized reset-to-default would leave that snapshot stale and
        restoring the field would resurrect the old value over the reset. A
        widget advertises ``sync_stored_default(default)`` (a duck-typed hook)
        while it carries such an override; we call it right after the default is
        applied. Decoupled by design — StateManager doesn't import the option.
        """
        hook = getattr(widget, "sync_stored_default", None)
        if callable(hook):
            try:
                hook(default_value)
            except Exception as e:
                self.logger.debug(f"sync_stored_default hook failed: {e}")

    def clear(self, widget: QtWidgets.QWidget) -> None:
        """Removes the stored state for the widget from QSettings."""
        key = self._get_state_key(widget)
        if key:
            self._get_settings(widget).remove(key)
            self.logger.debug(f"Cleared stored state for: {key}")

    def has_default(self, widget: QtWidgets.QWidget) -> bool:
        """Check if a widget has a stored default value."""
        return widget in self._defaults

    def capture_default(self, widget: QtWidgets.QWidget) -> None:
        """Capture the current widget value as its default.

        This should be called early during widget registration, before any
        init methods or state restoration that might modify the value.
        Only captures for widgets with restore_state=True.
        """
        if not getattr(widget, "restore_state", False):
            return
        if widget not in self._defaults:
            value = self._get_current_value(widget)
            if value is not None:
                self._defaults[widget] = value
                self.logger.debug(
                    f"Captured default for {widget.objectName()}: {value}"
                )

    def set_default(self, widget: QtWidgets.QWidget, value: Any) -> None:
        """Explicitly set a widget's default value.

        Use this in init methods to override the .ui file default with a
        post-initialization default value.

        Parameters:
            widget: The widget to set the default for.
            value: The value to use as the default.
        """
        self._defaults[widget] = value
        self.logger.debug(f"Set explicit default for {widget.objectName()}: {value}")

    # ---- custom key/value persistence ------------------------------------

    def save_custom(self, key: str, value: Any) -> None:
        """Persist an arbitrary key/value pair through QSettings.

        Use this for non-widget data that needs to survive between sessions
        (e.g. splitter sizes, column widths, last-used paths).

        Values are JSON-encoded when they are lists, dicts, or tuples.
        Primitive types (int, float, str, bool) are stored directly.
        """
        if self._save_suppressed:
            return
        stored = self._coerce_for_store(value)
        if stored is self._UNSUPPORTED:
            self.logger.debug(f"Unsupported type for custom key {key}: {type(value)}")
            return
        self.qsettings.setValue(f"custom/{key}", stored)

    def load_custom(self, key: str, default: Any = None) -> Any:
        """Retrieve a previously stored custom key/value pair.

        Returns *default* if the key has never been set.
        """
        value = self.qsettings.value(f"custom/{key}", default)
        if value == "None":
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value

    def clear_custom(self, key: str) -> None:
        """Remove a single custom key from storage."""
        self.qsettings.remove(f"custom/{key}")


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ...


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Refactoring Notes:
==================
This StateManager has been refactored to use WidgetValueManager for all value operations.

Removed methods (now handled by WidgetValueManager):
- _set_numeric_value() -> WidgetValueManager.set_value_by_signal()
- _set_index_value() -> WidgetValueManager.set_value_by_signal()  
- _set_boolean_value() -> WidgetValueManager.set_value_by_signal()
- _set_check_state() -> WidgetValueManager.set_value_by_signal()
- Complex apply() method -> Simplified to use WidgetValueManager
- Signal-based getter dict -> WidgetValueManager.get_value_by_signal()

Benefits:
- Eliminated ~50 lines of duplicate code
- Improved error handling and type conversion
- Consistent behavior with other value management systems
- Single source of truth for widget value operations
"""
