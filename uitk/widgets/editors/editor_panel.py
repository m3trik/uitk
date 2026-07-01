# !/usr/bin/python
# coding=utf-8
"""Editor panel: WindowPanel + optional preset save/load row.

Specialization of :class:`WindowPanel` for editors that need to persist
named configurations. The base provides the standard chrome (Header /
body / Footer / theme / anchoring) and this class layers on the
*canonical preset template* — a uitk :class:`~uitk.widgets.comboBox.ComboBox`
whose ``option_box`` carries the **Refresh / Save / ⋯-menu** toolbar
(Rename / Open folder / Delete, with inline naming) — plus the JSON
load/save plumbing. All of it is delegated to :class:`PresetManager`, so
an editor uses the exact same preset system as every other panel in the
ecosystem (one implementation, no per-editor duplication).

For read-only viewers and other non-editor windowed surfaces, extend
:class:`WindowPanel` directly — none of the preset machinery is forced
onto consumers that don't need it.
"""
from pathlib import Path

from qtpy import QtWidgets

from uitk.widgets.windowPanel import WindowPanel
from uitk.widgets.mixins.preset_manager import PresetManager


class EditorPanel(WindowPanel):
    """Windowed editor with optional preset management.

    Subclasses add controls and content to ``body_layout``. Preset
    support is opt-in: call :meth:`init_preset_row` from the subclass
    constructor at the desired vertical position, and override
    :meth:`export_preset_data` / :meth:`import_preset_data` to define
    what each preset persists.

    Parameters identical to :class:`WindowPanel`; forwarded unchanged.
    """

    # ── Preset management (opt-in) ───────────────────────────────

    _preset_mgr: "PresetManager | None" = None
    _cmb_preset = None

    def init_preset_row(
        self, dir_name, *, modified_value_provider=None, in_header_menu=False
    ):
        """Add the canonical preset row (combo + option-box toolbar).

        Call this from the subclass constructor at the desired vertical
        position. The subclass must also override
        :meth:`export_preset_data` and :meth:`import_preset_data` to
        define what is saved and loaded.

        The row is the shared :class:`PresetManager` template: a uitk
        ``ComboBox`` whose ``option_box`` carries **Refresh / Save** and a
        **⋯ menu** (Rename / Open folder / Delete), with inline naming.
        Save / load / rename / delete are delegated to ``PresetManager``
        (semantic mode), so the editor's presets are the same JSON any
        headless reader sees — there is no editor-specific preset code.

        Parameters
        ----------
        dir_name : str
            Relative subdirectory under :func:`get_presets_root` (the
            ecosystem-wide preset root). The editor's presets live in
            ``<presets_root>/uitk/<dir_name>/``. ``PresetManager`` handles
            root resolution, the ``M3TRIK_PRESETS_ROOT`` override, and
            legacy migration.
        modified_value_provider : callable, optional
            Cheaper capture used *only* by the dirty-check
            (:meth:`PresetManager.is_modified`); falls back to the save-time
            ``export_preset_data`` when omitted. Supply one for editors whose
            full export is expensive (e.g. the shortcut editor, which would
            otherwise build every registered UI just to test "modified").
        in_header_menu : bool, optional
            When True the preset row is tucked into the :class:`Header`'s
            ⋯-menu popup instead of occupying a row in the body — keeping
            the body focused on the editor's primary content. The header's
            ``menu`` button is added automatically if absent. Defaults to
            False (preset row in the body).
        """

        def _apply_import(data):
            self.import_preset_data(data)
            return len(data)

        # Semantic mode: a preset is the dict the subclass exports, fed back
        # to it on load — no managed-widget list, so editors persist their own
        # serialized config (theme overrides, shortcut maps, …) directly.
        self._preset_mgr = PresetManager(
            preset_dir=f"uitk/{dir_name}",
            value_provider=self.export_preset_data,
            value_applier=_apply_import,
            modified_value_provider=modified_value_provider,
        )

        # One-call build of the canonical preset row (combo + option-box
        # toolbar); the container is what goes in the layout, the combo is
        # reachable as ``container.preset_combo``.
        container = self._preset_mgr.make_preset_combo(
            name="cmb_preset", tooltip="Load a saved preset."
        )
        self._cmb_preset = container.preset_combo
        # "Preset:" rides on the combo's current item as a display-only prefix
        # (painted on the collapsed selection, absent from the dropdown items)
        # instead of a separate QLabel — mirrors the "Target UI:" combo in the
        # shortcut editor. The dirty marker keeps using current_text_suffix
        # (" *"), so a modified preset reads "Preset:  name *".
        self._cmb_preset.current_text_prefix = "Preset:  "

        preset_layout = QtWidgets.QHBoxLayout()
        preset_layout.addWidget(container)

        if in_header_menu:
            # Drop the whole row into the header's ⋯-menu popup. The menu
            # accepts a single widget, so wrap the combo row. Zero the
            # wrapper margins so the row sits flush in the compact popup (the
            # body path keeps the default layout margins). Ensure a menu button
            # exists (the default editor header is ["hide"] only); its
            # visibility auto-syncs to content via on_item_added.
            preset_layout.setContentsMargins(0, 0, 0, 0)
            row = QtWidgets.QWidget()
            row.setLayout(preset_layout)
            if "menu" not in self.header.buttons:
                self.header.config_buttons("menu", *self.header.buttons.keys())
            self.header.menu.add(row)
        else:
            self._body_layout.addLayout(preset_layout)

    # ── Preset directory ─────────────────────────────────────────

    @property
    def preset_dir(self) -> Path:
        """The directory where this editor's preset files live.

        Delegates to the underlying :class:`PresetManager`, which handles
        consolidated-root resolution (``M3TRIK_PRESETS_ROOT`` override),
        legacy migration, and directory creation.
        """
        if self._preset_mgr is None:
            raise RuntimeError(
                "preset_dir is unavailable until init_preset_row() runs."
            )
        return self._preset_mgr.preset_dir

    @preset_dir.setter
    def preset_dir(self, value) -> None:
        """Redirect this editor's preset directory.

        Accepts anything :attr:`PresetManager.preset_dir` accepts: a full
        path, a tilde string, an env-var expression, or a path relative to
        :func:`get_presets_root`.
        """
        if self._preset_mgr is None:
            raise RuntimeError(
                "preset_dir cannot be set before init_preset_row() runs."
            )
        self._preset_mgr.preset_dir = value

    # ── Preset hooks (override in subclass) ──────────────────────

    def export_preset_data(self) -> dict:
        """Override to provide data for preset saving."""
        return {}

    def import_preset_data(self, data: dict):
        """Override to apply data from a loaded preset."""

    # ── Preset save / load / delete / rename (delegated) ─────────
    #
    # Thin forwards to :class:`PresetManager` — the single implementation of the
    # preset JSON plumbing. These are the programmatic / test API; the live UI
    # goes through the option-box toolbar (wire_combo), which refreshes the combo
    # itself, so the forwards stay plumbing-only (matching the old disk-write
    # semantics).

    def save_preset(self, name: str) -> Path:
        """Save the current state under *name* and return the file path."""
        return self._preset_mgr.save(name)

    def load_preset(self, name: str) -> bool:
        """Load *name* and apply it; ``False`` if it doesn't exist."""
        if not self._preset_mgr.exists(name):
            return False
        self._preset_mgr.load(name)
        return True

    def delete_preset(self, name: str) -> bool:
        """Delete a user preset; ``False`` if absent or read-only."""
        return self._preset_mgr.delete(name)

    def rename_preset(self, old: str, new: str) -> bool:
        """Rename a user preset; ``False`` if invalid."""
        return self._preset_mgr.rename(old, new)

    def _list_presets(self) -> list:
        """Sorted preset names across both tiers (built-in + user)."""
        return self._preset_mgr.list()
