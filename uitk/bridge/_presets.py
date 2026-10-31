# !/usr/bin/python
# coding=utf-8
"""The presets of a bridge panel: one part of :class:`~uitk.bridge.slots.BridgeSlotsBase`.

The user-preset combo and the Reset to Defaults button above the send button:
widget-state presets per template (the default) or semantic presets shared with
a headless CLI through a :class:`pythontk.PresetStore` (:meth:`make_preset_store`),
plus the saved-defaults state uitk's :class:`ResetGesture` drives.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from qtpy import QtCore

from uitk.widgets.pushButton import PushButton
from uitk.widgets.comboBox import ComboBox
from uitk.managers.preset_manager import PresetManager
from uitk.managers.reset_gesture import ResetGesture
from uitk.managers.state_manager import StateManager

from uitk.bridge.spec import KindFactory

if TYPE_CHECKING:  # annotation only; the facade imports this module
    from uitk.bridge.slots import BridgeSlotsBase


class _BridgeDefaults(object):
    """A bridge panel's defaults, in the calls :class:`ResetGesture` makes.

    The window's ``StateManager`` can't be the gesture's state: a bridge's
    fields are kind-built composites it neither reads nor restores. This speaks
    the same four calls over the bridge's own param IO. A reset writes each
    field's registry default, or the value saved over it; a save records the
    current values; a factory reset forgets them. The saved values persist in
    the window's settings (``StateManager.save_custom``), one set per panel.

    A live switch (``AttributeSpec.preset=False``) is outside every action:
    Reset is about settings, and switching one would act (a share toggled Off
    takes every guest's link down).
    """

    KEY = "bridge_saved_defaults"

    def __init__(self, slots: "BridgeSlotsBase"):
        self._slots = slots

    def reset_all(self, block_signals=False, widgets=None, factory=False) -> None:
        if factory:
            self.clear_saved_defaults()
        slots = self._slots
        saved = self._saved()
        live = slots._live_param_keys()
        for key, spec in slots.params_module.PARAMS.items():
            if key not in slots._param_widgets or key in live:
                continue
            # The registry default first, the saved value over it: one the
            # widget rejects (a retired choice is ignored, a bad number
            # raises) then leaves the field at its default, not where it was.
            for value in [spec.default] + ([saved[key]] if key in saved else []):
                try:
                    slots._write_param(key, value)
                except Exception:  # noqa: BLE001
                    # A bad handler shouldn't poison the rest of the reset.
                    continue

    def save_defaults(self, widgets=None) -> int:
        store = self._store()
        if store is None:
            return 0
        live = self._slots._live_param_keys()
        values = {
            k: v for k, v in self._slots.collect_param_values().items() if k not in live
        }
        store.save_custom(self.KEY, values)
        return len(values)

    def clear_saved_defaults(self, widgets=None) -> int:
        count = len(self._saved())
        if count:
            self._store().clear_custom(self.KEY)
        return count

    def has_saved_defaults(self, widgets=None) -> bool:
        return bool(self._saved())

    def _saved(self) -> Dict[str, Any]:
        store = self._store()
        saved = store.load_custom(self.KEY) if store is not None else None
        return saved if isinstance(saved, dict) else {}

    def _store(self) -> Optional[StateManager]:
        return StateManager.for_widget(self._slots.ui.grp_process)


class _Presets(object):
    """A bridge panel's preset combo + Reset to Defaults, in either preset mode.

    Owns the preset manager, the semantic store (when the panel supplies
    one), the combo and the reset button with its gesture. Reads the panel's
    param rows through its own names (``_param_widgets``,
    ``collect_param_values``, ``_write_param``), ``PRESETS_ROOT`` and the
    active template (the per-template preset dir).
    """

    def __init__(self, panel: "BridgeSlotsBase") -> None:
        self._panel = panel
        self.mgr: Optional[PresetManager] = None
        self.store = None  # set in build_controls (semantic mode)
        self.semantic = False
        self.combo: Optional[ComboBox] = None
        self.reset_btn: Optional[PushButton] = None
        self.reset_gesture: Optional[ResetGesture] = None

    # ------------------ Preset controls -------------------------------

    def build_controls(self) -> None:
        """Insert a user-preset combobox + 'Reset to Defaults' button above b000."""
        panel = self._panel
        layout = panel.ui.grp_process.layout()

        combo = ComboBox(panel.ui.grp_process)
        combo.setObjectName("cmb_user_presets")
        combo.setMinimumHeight(19)
        combo.setMaximumHeight(19)
        combo.setToolTip(
            "Saved user presets for the active template.\n"
            "Open the side menu to Save / Rename / Delete the current values."
        )

        reset_btn = PushButton(panel.ui.grp_process)
        reset_btn.setObjectName("btn_reset_defaults")
        reset_btn.setText("Reset to Defaults")
        reset_btn.setMinimumHeight(19)
        reset_btn.setMaximumHeight(19)
        # uitk's shared reset grammar -- Click, Shift+Click saves the current
        # values as the defaults, Ctrl+Shift+Click forgets them -- with the
        # tooltip that teaches it, over the bridge's own defaults.
        self.reset_gesture = ResetGesture(
            reset_btn, state=_BridgeDefaults(panel), on_performed=self.after_reset
        )

        insert_at = layout.indexOf(panel.ui.b000)
        layout.insertWidget(insert_at, combo)
        layout.insertWidget(insert_at + 1, reset_btn)

        store = panel.make_preset_store()
        self.store = store
        self.semantic = store is not None
        # A live switch acts the moment it changes, so a preset carrying one
        # would act on load: in either mode a preset neither holds nor sets it.
        live = panel._live_param_keys()

        if store is not None:
            # Semantic mode: presets are {param_key: value} run-templates shared
            # with the headless CLI through one PresetStore (built-in + user
            # tiers). The callbacks own (de)serialization, so no managed widget
            # list is needed and presets are template-agnostic.
            self.mgr = PresetManager(
                preset_dir=str(store.user_dir),
                builtin_dir=str(store.builtin_dir) if store.builtin_dir else None,
                value_provider=lambda: {
                    k: v
                    for k, v in panel.collect_param_values().items()
                    if k not in live
                },
                value_applier=lambda data: panel._apply_param_dict(
                    {k: v for k, v in data.items() if k not in live}
                ),
            )
        else:
            # Widget-state mode (DCC bridges): raw snapshots keyed by objectName,
            # one preset subdir per template under PRESETS_ROOT.
            #
            # The kind-built widgets themselves, NOT their inner children. Each
            # carries KindFactory's `_attr_kind` stamp, which PresetManager treats
            # as the authority for read/write — so a composite is (de)serialized by
            # the handler that built it. Substituting `_line_edit` here used to be
            # the only way a `path` row survived a preset (the manager could not
            # read the container), but it drops the stamp and reaches exactly one
            # composite: `file_list` and `check_list` were silently unsaveable.
            managed = [w for k, w in panel._param_widgets.items() if k not in live]
            if panel.PRESETS_ROOT is None:
                raise ValueError(
                    f"{type(panel).__name__} must set PRESETS_ROOT "
                    "(or override make_preset_store() for semantic presets)."
                )
            self.mgr = PresetManager.from_widgets(
                preset_dir=panel.PRESETS_ROOT / panel._active_template(),
                widgets=managed,
            )
        self.mgr.wire_combo(combo)

        # Live "modified" marker: any param edit re-evaluates the dirty state so
        # the combo shows e.g. "specular *". StateManager fires these same
        # change signals during session restore, so the marker self-corrects
        # regardless of whether widgets restore before or after this wiring.
        for widget in panel._param_widgets.values():
            KindFactory.connect_changed(
                widget, lambda *_: self.mgr.refresh_modified_state()
            )
        # Insurance against any widgets restored with signals blocked: one
        # deferred recompute once the event loop settles (no-op headless).
        try:
            QtCore.QTimer.singleShot(0, self.mgr.refresh_modified_state)
        except Exception:  # noqa: BLE001
            pass

        self.combo = combo
        self.reset_btn = reset_btn

    def apply_param_dict(self, data: Dict[str, Any]) -> int:
        """Overlay a semantic preset on the param widgets (see ``_apply_param_dict``)."""
        panel = self._panel
        applied = 0
        for key, value in data.items():
            if key not in panel._param_widgets:
                continue
            try:
                panel._write_param(key, value)
                applied += 1
            except Exception:  # noqa: BLE001
                # One bad key shouldn't abort the rest of the overlay.
                continue
        return applied

    def live_param_keys(self) -> set:
        """The params that are live switches (``AttributeSpec.preset=False``)."""
        return {
            key
            for key, spec in self._panel.params_module.PARAMS.items()
            if not getattr(spec, "preset", True)
        }

    def after_reset(self, action: str) -> None:
        """Let go of the active preset when a reset moved the fields off it.

        The values are the defaults now, not the preset the combo still names.
        Saving the current values as the defaults (Shift+Click) moves no field,
        so it keeps the selection.
        """
        if action == ResetGesture.SAVE:
            return
        if self.combo is not None:
            self.combo.blockSignals(True)
            try:
                self.combo.setCurrentIndex(-1)
            finally:
                self.combo.blockSignals(False)

        # Clears the pointer + the modified marker.
        if self.mgr is not None:
            self.mgr.active_preset = None
