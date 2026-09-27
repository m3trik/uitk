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


class _PresetsMixin(object):
    """The preset combo + Reset to Defaults, in either preset mode.

    Reads the composed panel's param rows (``_param_widgets``,
    ``collect_param_values``, ``_write_param``), ``PRESETS_ROOT`` and the
    template combo's active template (the per-template preset dir).
    """

    def make_preset_store(self):
        """Hook: return a :class:`pythontk.PresetStore` to switch presets into
        **semantic mode**, or ``None`` (default) for **widget-state mode**.

        *Widget-state mode* (default): presets are raw widget snapshots keyed by
        ``objectName``, stored per-template under :attr:`PRESETS_ROOT`. Used by
        the DCC bridges (marmoset / substance / rizom).

        *Semantic mode*: presets are ``{param_key: value}`` run-templates keyed
        by :class:`AttributeSpec` name. A panel returns the **same** store its
        headless CLI uses (e.g. ``profile.preset_store()``), so a preset saved in
        the UI is readable by the CLI and vice-versa, and shipped built-ins show
        in the combo. The store is template-agnostic — one preset set per panel,
        captured via :meth:`collect_param_values` and applied via
        :meth:`_apply_param_dict`.
        """
        return None

    # ------------------ Preset controls -------------------------------

    def _build_preset_controls(self) -> None:
        """Insert a user-preset combobox + 'Reset to Defaults' button above b000."""
        layout = self.ui.grp_process.layout()

        combo = ComboBox(self.ui.grp_process)
        combo.setObjectName("cmb_user_presets")
        combo.setMinimumHeight(19)
        combo.setMaximumHeight(19)
        combo.setToolTip(
            "Saved user presets for the active template.\n"
            "Open the side menu to Save / Rename / Delete the current values."
        )

        reset_btn = PushButton(self.ui.grp_process)
        reset_btn.setObjectName("btn_reset_defaults")
        reset_btn.setText("Reset to Defaults")
        reset_btn.setMinimumHeight(19)
        reset_btn.setMaximumHeight(19)
        # uitk's shared reset grammar -- Click, Shift+Click saves the current
        # values as the defaults, Ctrl+Shift+Click forgets them -- with the
        # tooltip that teaches it, over the bridge's own defaults.
        self._reset_gesture = ResetGesture(
            reset_btn, state=_BridgeDefaults(self), on_performed=self._after_reset
        )

        insert_at = layout.indexOf(self.ui.b000)
        layout.insertWidget(insert_at, combo)
        layout.insertWidget(insert_at + 1, reset_btn)

        store = self.make_preset_store()
        self._preset_store = store
        self._semantic_presets = store is not None
        # A live switch acts the moment it changes, so a preset carrying one
        # would act on load: in either mode a preset neither holds nor sets it.
        live = self._live_param_keys()

        if store is not None:
            # Semantic mode: presets are {param_key: value} run-templates shared
            # with the headless CLI through one PresetStore (built-in + user
            # tiers). The callbacks own (de)serialization, so no managed widget
            # list is needed and presets are template-agnostic.
            self._preset_mgr = PresetManager(
                preset_dir=str(store.user_dir),
                builtin_dir=str(store.builtin_dir) if store.builtin_dir else None,
                value_provider=lambda: {
                    k: v
                    for k, v in self.collect_param_values().items()
                    if k not in live
                },
                value_applier=lambda data: self._apply_param_dict(
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
            managed = [w for k, w in self._param_widgets.items() if k not in live]
            if self.PRESETS_ROOT is None:
                raise ValueError(
                    f"{type(self).__name__} must set PRESETS_ROOT "
                    "(or override make_preset_store() for semantic presets)."
                )
            self._preset_mgr = PresetManager.from_widgets(
                preset_dir=self.PRESETS_ROOT / self._active_template(),
                widgets=managed,
            )
        self._preset_mgr.wire_combo(combo)

        # Live "modified" marker: any param edit re-evaluates the dirty state so
        # the combo shows e.g. "specular *". StateManager fires these same
        # change signals during session restore, so the marker self-corrects
        # regardless of whether widgets restore before or after this wiring.
        for widget in self._param_widgets.values():
            KindFactory.connect_changed(
                widget, lambda *_: self._preset_mgr.refresh_modified_state()
            )
        # Insurance against any widgets restored with signals blocked: one
        # deferred recompute once the event loop settles (no-op headless).
        try:
            QtCore.QTimer.singleShot(0, self._preset_mgr.refresh_modified_state)
        except Exception:  # noqa: BLE001
            pass

        self._preset_combo = combo
        self._reset_btn = reset_btn

    def _apply_param_dict(self, data: Dict[str, Any]) -> int:
        """Apply a semantic ``{param_key: value}`` preset to the param widgets.

        Keys absent from this panel's ``PARAMS`` are ignored (a shared CLI
        preset may carry knobs this panel doesn't surface). Keys not present in
        the preset keep their current widget values — overlay semantics matching
        the CLI's ``--preset``. Returns the number of widgets updated.
        """
        applied = 0
        for key, value in data.items():
            if key not in self._param_widgets:
                continue
            try:
                self._write_param(key, value)
                applied += 1
            except Exception:  # noqa: BLE001
                # One bad key shouldn't abort the rest of the overlay.
                continue
        return applied

    def _live_param_keys(self) -> set:
        """The params that are live switches (``AttributeSpec.preset=False``)."""
        return {
            key
            for key, spec in self.params_module.PARAMS.items()
            if not getattr(spec, "preset", True)
        }

    def _after_reset(self, action: str) -> None:
        """Let go of the active preset when a reset moved the fields off it.

        The values are the defaults now, not the preset the combo still names.
        Saving the current values as the defaults (Shift+Click) moves no field,
        so it keeps the selection.
        """
        if action == ResetGesture.SAVE:
            return
        if self._preset_combo is not None:
            self._preset_combo.blockSignals(True)
            try:
                self._preset_combo.setCurrentIndex(-1)
            finally:
                self._preset_combo.blockSignals(False)

        # Clears the pointer + the modified marker.
        if self._preset_mgr is not None:
            self._preset_mgr.active_preset = None
