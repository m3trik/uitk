# !/usr/bin/python
# coding=utf-8
"""Generic DCC-bridge slot base class.

Centralizes the panel machinery shared by the marmoset / substance /
rizom (and any future) DCC bridges:

* Parameter widget construction via :class:`uitk.bridge.spec.KindHandler`
  -- a single shared registry powers AttributeWindow, the bridges, and
  any other consumer.
* User-preset combo + reset button (via :class:`PresetManager`).
* Log-panel redirect with clickable ``action://`` URIs.
* Optional required "Output Dir" row with browse button + fallback hook.
* Bridge-level ``STARTUP_INFO`` displayed once on load (opt-in).
* Per-template description displayed whenever the template combo changes.
* Header menu (``header_init``): a "Utilities" separator + declared menu items
  + the rich-text help button, driven by the :attr:`HEADER_MENU_ITEMS` /
  :attr:`HELP_SPEC` class-attr hooks so subclasses set *data, not code*.

Per-bridge slot subclasses contribute only DCC-specific bits:

* Their ``params_module`` (exposes ``PARAMS``, ``referenced_keys``, ``defaults``).
* Their bridge class (must expose ``.logger``, ``.send(...)``, optionally
  ``.STARTUP_INFO``).
* Their template directory + ``list_template_modes``.
* The :meth:`b000` action that wires DCC selection + bridge handoff.

Custom widget kinds (e.g. an HSV picker) plug in via the shared
:func:`uitk.bridge.spec.register_kind`; new bridges inherit every kind
the registry knows about.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from qtpy import QtCore, QtWidgets

from uitk.widgets.pushButton import PushButton
from uitk.widgets.widgetComboBox import WidgetComboBox
from uitk.widgets.separator import Separator
from uitk.widgets.mixins.preset_manager import PresetManager

from uitk.bridge.spec import (
    AttributeSpec,
    connect_changed,
    make_widget,
    read_value,
    set_value,
)
from uitk.bridge.tooltip import format_param_tooltip, template_description


# ----------------------------------------------------------------------
# Module-level utilities
# ----------------------------------------------------------------------


def _open_in_file_manager(path: str) -> None:
    """Best-effort reveal of *path* in the platform's file manager."""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 — Windows-only API
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ----------------------------------------------------------------------
# BridgeSlotsBase
# ----------------------------------------------------------------------


class BridgeSlotsBase:
    """Base class for DCC-bridge slot panels.

    Subclasses **must** set:

    * :attr:`UI_NAME` -- ``self.sb.loaded_ui.<UI_NAME>`` resolves to the panel.
    * :attr:`PRESETS_ROOT` -- per-bridge preset storage root.
    * :attr:`params_module` (class attr or property) -- the per-bridge
      ``parameters`` module exposing ``PARAMS`` / ``referenced_keys`` /
      ``defaults``.
    * :attr:`template_dir` (class attr or property) -- per-bridge
      template directory.
    * :meth:`make_bridge` -- factory returning the per-bridge bridge instance.
    * :meth:`list_template_modes` -- ``[(stem, mode), ...]`` for the combo.
    * :meth:`b000` -- the DCC-specific send action.

    Optional overrides:

    * :meth:`select_initial_template_index` -- bias toward a default
      starting template entry.
    * :meth:`default_output_dir` -- DCC-side fallback used when the
      user leaves the Output Dir field blank.
    * :attr:`REQUIRE_OUTPUT_DIR` -- set False for bridges with no
      user-visible output (e.g. rizom's in-place UV roundtrip).
    * :attr:`TEMPLATE_EXTENSION` -- ``.py`` (default), ``.lua``, etc.
    """

    # ------------------ Required class attrs --------------------------

    UI_NAME: str = ""
    PRESETS_ROOT: Optional[Path] = None
    LOG_TAG: str = "bridge"

    # File extension of the per-template/script files under :attr:`template_dir`.
    # ``.py`` for marmoset / substance, ``.lua`` for rizom. Used by
    # :meth:`_refresh_param_visibility` to locate the placeholder source
    # and by :meth:`_log_template_description` to dispatch the extractor.
    TEMPLATE_EXTENSION: str = ".py"

    # Whether the panel exposes a required "Output Dir" row above the
    # parameter group. Disable for bridges whose roundtrip is in-place
    # (rizom transfers UVs back onto the originals without writing
    # artifacts the user needs to locate) -- the row is then never built,
    # and ``require_output_dir()`` returns ``""`` so subclasses can call
    # it unconditionally without a None guard.
    REQUIRE_OUTPUT_DIR: bool = True

    # ------------------ Cosmetics -------------------------------------

    LABEL_MIN_WIDTH = 90
    OUTPUT_DIR_LABEL = "Output Dir:"
    OUTPUT_DIR_PLACEHOLDER = "(defaults to scene dir / workspace)"
    OUTPUT_DIR_TOOLTIP = (
        "Directory where the export artifacts (FBX, manifest, rendered\n"
        "scripts, baked maps) all land. Leave blank to default to the\n"
        "current scene's directory (or the active workspace if the\n"
        "scene hasn't been saved)."
    )

    # ------------------ Widget kind -- composite types ----------------
    # Kinds whose widgets are composite (line edit + button, list +
    # buttons, ...) and must NOT have their parent row clamped to 19px
    # because the embedded layout is taller than one input line.
    PATH_LIKE_KINDS: Tuple[str, ...] = ("path", "file_list")

    # ------------------ Header menu (declarative) ---------------------
    # The default :meth:`header_init` builds a "Utilities" separator, the
    # declared menu items, and the rich-text help -- so subclasses set
    # *data*, not code. Each item is
    # ``(label, objectName, tooltip, handler_method_name)``; the handler is
    # resolved on the slot via ``getattr`` and connected to ``clicked``.
    #
    # The default item set is the script-template bridges' menu (marmoset /
    # substance / blender / maya). Bridges with a different menu shape
    # (rizom's UV-editor + scripts, unity's project folder, the
    # photogrammetry panels' cancel/output) override ``HEADER_MENU_ITEMS``;
    # the handlers they name live on the subclass.
    HEADER_MENU_TITLE: str = "Utilities"
    HEADER_MENU_ITEMS: Tuple[Tuple[str, str, str, str], ...] = (
        (
            "Open Templates Folder", "btn_open_templates",
            "Reveal the bundled template folder in Explorer.",
            "open_templates_folder",
        ),
        (
            "Refresh Templates", "btn_refresh_templates",
            "Re-scan the templates folder and rebuild the template combo.",
            "refresh_templates",
        ),
        ("Clear Log", "btn_clear_log", "Clear the log panel below.", "clear_log"),
    )
    # ``fmt()`` keyword dict (``title`` / ``body`` / ``steps`` / ``sections`` /
    # ``notes``) for the header help button, or ``None`` for no help.
    # Subclasses set this (or override :meth:`help_spec` to compute it).
    HELP_SPEC: Optional[Dict[str, Any]] = None

    # ------------------ Subclass hooks --------------------------------

    @property
    def params_module(self):  # pragma: no cover - subclass contract
        raise NotImplementedError

    @property
    def template_dir(self) -> Path:  # pragma: no cover - subclass contract
        raise NotImplementedError

    def make_bridge(self):  # pragma: no cover - subclass contract
        """Return a fresh bridge instance. Called once, lazily."""
        raise NotImplementedError

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

    def list_template_modes(self) -> List[Tuple[str, str]]:  # pragma: no cover
        raise NotImplementedError

    def b000(self):  # pragma: no cover - subclass contract
        """Implement the per-bridge send action."""
        raise NotImplementedError

    def select_initial_template_index(self, pairs: List[Tuple[str, str]]) -> int:
        """Return the index of the preferred initial entry in *pairs*.

        Default: 0 (first entry). Subclasses override to bias toward
        e.g. ``("bake", "roundtrip")``.
        """
        return 0

    def default_output_dir(self) -> str:
        """Hook: fallback path when the user leaves Output Dir blank.

        Returns the empty string by default. DCC-specific subclasses
        override -- e.g. ``MayaBridgeSlotsBase`` returns
        ``EnvUtils.default_artifact_dir()`` (scene dir, then workspace).
        """
        return ""

    def template_description(self, template_path: Path) -> Optional[str]:
        """Hook: extract a brief description from a template file."""
        return template_description(template_path)

    def format_param_tooltip(self, spec: AttributeSpec) -> str:
        """Hook: build the rich-text tooltip for one parameter spec."""
        return format_param_tooltip(spec)

    # ------------------ Init flow -------------------------------------

    def __init__(self, switchboard):
        self.sb = switchboard
        if not self.UI_NAME:
            raise ValueError(
                f"{type(self).__name__} must set UI_NAME (e.g. 'marmoset_bridge')."
            )
        self.ui = getattr(self.sb.loaded_ui, self.UI_NAME)

        self._bridge = None
        self._param_widgets: Dict[str, QtWidgets.QWidget] = {}
        self._param_rows: Dict[str, QtWidgets.QWidget] = {}
        # Category dividers: section name -> Separator, plus each param's section,
        # so a divider can hide when its whole section is hidden for the mode.
        self._section_separators: Dict[str, QtWidgets.QWidget] = {}
        self._param_section: Dict[str, str] = {}
        self._preset_mgr: Optional[PresetManager] = None
        self._preset_store = None  # set in _build_preset_controls (semantic mode)
        self._semantic_presets = False
        self._preset_combo: Optional[WidgetComboBox] = None
        self._output_dir_edit: Optional[QtWidgets.QLineEdit] = None
        self._param_visibility_settled = False
        self._param_group: Optional[QtWidgets.QGroupBox] = None

        if self.REQUIRE_OUTPUT_DIR:
            self._build_output_dir_row()
        self._build_param_widgets()
        self._build_preset_controls()

        try:
            self._redirect_log_to_panel()
            if hasattr(self.ui.txt000, "anchorClicked"):
                self.ui.txt000.anchorClicked.connect(self._on_log_link_clicked)
        except Exception as e:  # noqa: BLE001
            print(f"[{self.LOG_TAG}] log panel wiring failed (ignored): {e}")

        self._show_startup_info()

    @property
    def bridge(self):
        """Lazy-instantiated bridge (caches a single instance per slot)."""
        if self._bridge is None:
            self._bridge = self.make_bridge()
        return self._bridge

    # ------------------ Output Dir row --------------------------------

    def _build_output_dir_row(self) -> None:
        """Insert a persistent 'Output Dir' line edit (with option-box buttons) above params.

        The path field carries uitk **option-box** icon buttons instead of a bare
        ``...`` push-button. :meth:`_configure_output_dir_options` decides which —
        the default is a persisted **recent-values** history + a **directory
        browse** button; subclasses override it (e.g. the Unity bridge swaps the
        browse button for an option *menu* of project actions).

        The edit is parented into the row layout (with stretch) **before** the
        option box wraps it, so the wrap reparents it in place via
        ``replaceWidget`` (preserving the stretch factor) while it is already
        layout-managed. Wrapping a *parentless* edit instead lets it briefly show
        as a top-level widget, whose ``OptionBoxContainer.showEvent`` schedules a
        ``_refit_to_content`` that collapses + absolutely-positions the container
        — leaving the field right-shifted instead of filling the row.
        """
        layout = self.ui.grp_process.layout()

        row = QtWidgets.QWidget(self.ui.grp_process)
        hbox = QtWidgets.QHBoxLayout(row)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(2)

        label = QtWidgets.QLabel(self.OUTPUT_DIR_LABEL, row)
        label.setMinimumWidth(self.LABEL_MIN_WIDTH)
        label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        edit = QtWidgets.QLineEdit(row)
        edit.setObjectName(f"{self.LOG_TAG}_output_dir")
        edit.setPlaceholderText(self.OUTPUT_DIR_PLACEHOLDER)
        edit.setMinimumHeight(19)
        edit.setMaximumHeight(19)
        edit.setToolTip(self.OUTPUT_DIR_TOOLTIP)
        self._output_dir_edit = edit

        hbox.addWidget(label)
        hbox.addWidget(edit, 1)

        # Wrap after the edit is in the layout: the option box replaces it in
        # place (keeping the stretch) instead of leaving a stale top-level geom.
        self._configure_output_dir_options(edit)

        insert_at = layout.indexOf(self.ui.cmb000) + 1
        layout.insertWidget(insert_at, row)
        self._output_dir_row = row

    # ------------------ Output Dir option-box buttons -----------------

    def _output_dir_browse_title(self) -> str:
        """Window title for the output-dir browse dialog (from the row label)."""
        return self.OUTPUT_DIR_LABEL.rstrip(": ") or "Select directory"

    def _add_recent_output_dir_option(self, edit) -> None:
        """Attach the persisted recent-values history button to *edit* (shared)."""
        edit.option_box.recent(
            settings_key=f"{self.LOG_TAG}_output_dir_recent",
            auto_record=True,
            display_format="auto",
        )

    def _configure_output_dir_options(self, edit) -> None:
        """Hook: option-box buttons for the output-dir field.

        Default = a persisted recent-values history + a directory-browse button.
        Subclasses override to customise (the Unity bridge uses an option menu of
        project actions instead of the lone browse button).
        """
        self._add_recent_output_dir_option(edit)
        edit.option_box.set_action(
            callback=self._pick_output_dir,
            icon="folder",
            tooltip="Browse for a folder",
            settings_key=False,
        )

    def _pick_output_dir(self) -> None:
        """Open a directory dialog, load the choice into the field, and record it.

        Shared by the default browse button and any subclass that surfaces the same
        'Set …' action as a menu item.
        """
        edit = self._output_dir_edit
        if edit is None:
            return
        start = self.resolved_output_dir() or str(Path.home())
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self.ui, self._output_dir_browse_title(), start
        )
        if not path:
            return
        edit.setText(path)
        self._record_output_dir(path)

    @staticmethod
    def _record_recent(edit, value) -> None:
        """Record *value* into *edit*'s option-box recent-values history (no-op if none).

        Programmatic ``setText`` doesn't fire the ``auto_record`` (editingFinished)
        path, so any code that sets a recent-backed field in code (browse, a
        subclass 'New Project' action, a host hand-off) calls this to keep the
        history in sync. Shared by every recent-backed field — the base output-dir
        row and any subclass row (e.g. the Unity workflow's Model File).
        """
        if edit is None:
            return
        from uitk.widgets.optionBox.options.recent_values import RecentValuesOption

        recent = edit.option_box.find_option(RecentValuesOption)
        if recent is not None:
            recent.record(value)

    def _record_output_dir(self, value) -> None:
        """Record *value* into the output-dir field's recent-values history."""
        self._record_recent(self._output_dir_edit, value)

    def resolved_output_dir(self) -> str:
        """Return the current Output Dir text trimmed of whitespace.

        Returns the empty string when :attr:`REQUIRE_OUTPUT_DIR` is False
        (the row was never built) so subclasses can call this unconditionally.
        """
        if self._output_dir_edit is None:
            return ""
        return self._output_dir_edit.text().strip()

    def require_output_dir(self) -> Optional[str]:
        """Return the Output Dir or log an error on empty.

        Resolution order:

        1. The user's typed value in the line edit.
        2. :meth:`default_output_dir` (DCC-side fallback) -- on hit, the
           chosen path is written back into the line edit and announced
           in the log panel so the user sees where files landed.
        3. Log an error + focus the field, return ``None`` to signal
           the caller to abort.

        When :attr:`REQUIRE_OUTPUT_DIR` is False, returns ``""``
        unconditionally so the caller can pass the result through to
        bridges that tolerate empty output dirs.
        """
        if not self.REQUIRE_OUTPUT_DIR:
            return ""
        output_dir = self.resolved_output_dir()
        if output_dir:
            return output_dir

        fallback = self.default_output_dir()
        if fallback:
            if self._output_dir_edit is not None:
                self._output_dir_edit.setText(fallback)
            try:
                self.bridge.logger.info(
                    f"Output Dir not set; using scene/workspace default: "
                    f'<a href="action://open?path={fallback}">{fallback}</a>'
                )
            except Exception:  # noqa: BLE001
                pass
            return fallback

        self.bridge.logger.error(
            "Output Dir is required and no scene/workspace default could "
            "be resolved. Click '...' next to the Output Dir field to "
            "choose where the export artifacts land."
        )
        if self._output_dir_edit is not None:
            self._output_dir_edit.setFocus()
        return None

    # ------------------ Parameter widgets -----------------------------

    def _build_param_widgets(self) -> None:
        """Inject a 'Parameters' group between the Output Dir row and Send.

        Builds one row widget per registered :class:`AttributeSpec` via
        :func:`uitk.bridge.spec.make_widget` -- the shared registry powers
        every kind including custom ones the bridge registered.
        """
        grp = QtWidgets.QGroupBox("Parameters", self.ui.grp_process)
        vbox = QtWidgets.QVBoxLayout(grp)
        vbox.setContentsMargins(2, 4, 2, 2)
        vbox.setSpacing(0)

        for key, spec in self.params_module.PARAMS.items():
            # Start of a new category -> a titled divider above its first row.
            # (One separator per section; sections are expected contiguous.)
            section = getattr(spec, "section", "") or ""
            self._param_section[key] = section
            if section and section not in self._section_separators:
                sep = Separator(grp, title=section)
                vbox.addWidget(sep)
                self._section_separators[section] = sep

            row = QtWidgets.QWidget(grp)
            hbox = QtWidgets.QHBoxLayout(row)
            hbox.setContentsMargins(0, 0, 0, 0)
            hbox.setSpacing(2)

            tooltip_html = self.format_param_tooltip(spec)

            label = QtWidgets.QLabel(spec.display_label + ":", row)
            label.setMinimumWidth(self.LABEL_MIN_WIDTH)
            label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            label.setToolTip(tooltip_html)

            widget = make_widget(spec, row)
            # Prefix the registry key so two panels in the same window
            # can host the same AttributeSpec without objectName clashes.
            widget.setObjectName(f"param_{key.lower()}")
            if spec.kind not in self.PATH_LIKE_KINDS:
                widget.setMinimumHeight(19)
                widget.setMaximumHeight(19)
            widget.setToolTip(tooltip_html)

            hbox.addWidget(label)
            hbox.addWidget(widget, 1)
            vbox.addWidget(row)

            self._param_widgets[key] = widget
            self._param_rows[key] = row

        parent_layout = self.ui.grp_process.layout()
        insert_at = parent_layout.indexOf(self.ui.b000)
        parent_layout.insertWidget(insert_at, grp)
        self._param_group = grp

    def _read_param(self, key: str) -> Any:
        """Extract the current value via the registered KindHandler."""
        return read_value(self._param_widgets[key])

    def _write_param(self, key: str, value: Any) -> None:
        """Push *value* into the widget for *key* via the KindHandler."""
        set_value(self._param_widgets[key], value)

    def collect_param_values(self) -> Dict[str, Any]:
        """Snapshot every widget's current value, regardless of visibility."""
        return {key: self._read_param(key) for key in self._param_widgets}

    def _relevant_param_keys(self) -> Optional[set]:
        """Hook: the param keys whose rows should be visible for the current
        selection, or ``None`` to skip the visibility update entirely (no
        template selected / unreadable source).

        Default: the placeholder keys referenced by the active template file
        (the script-substitution bridges). Run-mode panels — e.g. a single
        runner driven by a ``--stop-after``-style mode rather than per-template
        files — override this to gate visibility on the selected mode, so the
        parameter UI stays dynamic the same way the DCC bridges' does.
        """
        pair = self._selected_template_mode()
        if not pair:
            return None
        template, _mode = pair
        path = self.template_dir / f"{template}{self.TEMPLATE_EXTENSION}"
        if not path.is_file():
            return None
        return self.params_module.referenced_keys(path.read_text(encoding="utf-8"))

    def _refresh_param_visibility(self) -> None:
        """Show only the rows relevant to the current selection.

        Delegates the "which keys are relevant?" decision to
        :meth:`_relevant_param_keys` so subclasses can drive visibility from a
        template file (default) or a run mode without re-implementing the
        row-toggling + height-fit bookkeeping.
        """
        used = self._relevant_param_keys()
        if used is None:
            return

        for key, row in self._param_rows.items():
            row.setVisible(key in used)
        # A category divider shows only while at least one of its params does,
        # so a section that's fully hidden for the mode doesn't leave a stray rule.
        for section, sep in self._section_separators.items():
            sep.setVisible(any(
                self._param_section.get(k) == section and k in used
                for k in self._param_rows
            ))
        if self._param_group is not None:
            self._param_group.setVisible(bool(used))

        if self._param_visibility_settled:
            fit = getattr(self.ui, "fit_height_to_content", None)
            if callable(fit):
                QtCore.QTimer.singleShot(0, fit)
        self._param_visibility_settled = True

    # ------------------ Preset controls -------------------------------

    def _build_preset_controls(self) -> None:
        """Insert a user-preset combobox + 'Reset to Defaults' button above b000."""
        layout = self.ui.grp_process.layout()

        combo = WidgetComboBox(self.ui.grp_process)
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
        reset_btn.setToolTip("Restore every parameter widget to its registry default.")
        reset_btn.clicked.connect(self._reset_to_defaults)

        insert_at = layout.indexOf(self.ui.b000)
        layout.insertWidget(insert_at, combo)
        layout.insertWidget(insert_at + 1, reset_btn)

        store = self.make_preset_store()
        self._preset_store = store
        self._semantic_presets = store is not None

        if store is not None:
            # Semantic mode: presets are {param_key: value} run-templates shared
            # with the headless CLI through one PresetStore (built-in + user
            # tiers). The callbacks own (de)serialization, so no managed widget
            # list is needed and presets are template-agnostic.
            self._preset_mgr = PresetManager(
                preset_dir=str(store.user_dir),
                builtin_dir=str(store.builtin_dir) if store.builtin_dir else None,
                value_provider=self.collect_param_values,
                value_applier=self._apply_param_dict,
            )
        else:
            # Widget-state mode (DCC bridges): raw snapshots keyed by objectName,
            # one preset subdir per template under PRESETS_ROOT.
            managed = [
                getattr(w, "_line_edit", w) for w in self._param_widgets.values()
            ]
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
            connect_changed(
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

    def _active_template(self) -> str:
        """Active template stem (mode-agnostic preset key)."""
        pair = self._selected_template_mode()
        if pair:
            return pair[0]
        pairs = self.list_template_modes()
        return pairs[0][0] if pairs else "default"

    def _reset_to_defaults(self) -> None:
        """Restore every parameter widget to its registry default via KindHandler."""
        for key, spec in self.params_module.PARAMS.items():
            if key not in self._param_widgets:
                continue
            try:
                self._write_param(key, spec.default)
            except Exception:  # noqa: BLE001
                # A bad handler shouldn't poison the rest of the reset --
                # keep going so the user gets as close to "defaults" as
                # possible even if one kind misbehaves.
                continue

        if self._preset_combo is not None:
            self._preset_combo.blockSignals(True)
            try:
                self._preset_combo.setCurrentIndex(-1)
            finally:
                self._preset_combo.blockSignals(False)

        # Reset abandons the active preset (values are now registry defaults,
        # not any saved preset); clears the pointer + modified marker.
        if self._preset_mgr is not None:
            self._preset_mgr.active_preset = None

    # ------------------ Template combo --------------------------------

    @staticmethod
    def _format_combo_label(template: str, mode: str) -> str:
        """Display string for one (template, mode) combo entry.

        Single-mode bridges (rizom) pass ``mode=""`` so the parens are
        elided -- the combo just shows the template stem.
        """
        return f"{template} ({mode})" if mode else template

    def cmb000_init(self, widget) -> None:
        """Switchboard hook: populate the template combobox + wire change handler."""
        self._populate_template_combo(widget)
        widget.currentIndexChanged.connect(lambda _: self._on_template_changed())
        self._on_template_changed()

    def _populate_template_combo(self, widget) -> None:
        """Fill cmb000 with ``"<template> (<mode>)"`` entries."""
        pairs = self.list_template_modes()
        widget.blockSignals(True)
        try:
            widget.clear()
            for template, mode in pairs:
                widget.addItem(
                    self._format_combo_label(template, mode), (template, mode)
                )
            if pairs:
                widget.setCurrentIndex(self.select_initial_template_index(pairs))
        finally:
            widget.blockSignals(False)

    def refresh_templates(self) -> None:
        """Re-scan disk and rebuild the template combo + parameter UI."""
        self._populate_template_combo(self.ui.cmb000)
        self._on_template_changed()

    def _selected_template_mode(self) -> Optional[Tuple[str, str]]:
        """``(template, mode)`` for the active combo entry, or *None*.

        ``itemData`` stores a ``(template, mode)`` tuple, but some PySide
        bindings round-trip it back through ``QVariant`` as a *list* --
        so accept either and normalise to a tuple.
        """
        idx = self.ui.cmb000.currentIndex()
        if idx < 0:
            return None
        data = self.ui.cmb000.itemData(idx)
        if isinstance(data, (tuple, list)) and len(data) == 2:
            return tuple(data)
        return None

    def _on_template_changed(self) -> None:
        """Re-show rows + re-point preset dir + log description on combo change.

        In semantic-preset mode the preset set is template-agnostic (one shared
        store), so the preset dir is *not* re-pointed per template — only the
        widget-state bridges keep per-template preset subdirs.
        """
        self._refresh_param_visibility()
        if self._preset_mgr is not None and not self._semantic_presets:
            self._preset_mgr.preset_dir = (
                self.PRESETS_ROOT / self._active_template()
            )
            refresh = getattr(self._preset_mgr, "_refresh_combo", None)
            if callable(refresh):
                refresh()
        self._log_template_description()

    def _log_template_description(self) -> None:
        """Surface the active template's docstring in the log panel."""
        pair = self._selected_template_mode()
        if not pair:
            return
        template, mode = pair
        path = self.template_dir / f"{template}{self.TEMPLATE_EXTENSION}"
        desc = self.template_description(path)
        if not desc:
            return
        label = self._format_combo_label(template, mode)
        try:
            self.bridge.logger.info(f"[{label}] {desc}")
        except Exception:  # noqa: BLE001
            pass

    # ------------------ Log panel -------------------------------------

    def _redirect_log_to_panel(self) -> None:
        """Pipe the bridge logger into ``txt000``, no-op if redirect unavailable."""
        try:
            handler_cls = self.sb.registered_widgets.TextEditLogHandler
        except AttributeError:
            return
        try:
            logger = self.bridge.logger
            logger.hide_logger_name(True)
            logger.set_text_handler(handler_cls)
            logger.setup_logging_redirect(self.ui.txt000)
        except AttributeError:
            pass

    def _on_log_link_clicked(self, url) -> None:
        """Route ``action://`` URIs from the log panel to their handler.

        The ``open`` action (reveal a file/folder) is DCC-agnostic, so it is
        handled here with the cross-platform file-manager opener — this is what
        lets output-dir links work when a panel runs as a standalone external
        app (no Maya), which is the common case for the photogrammetry bridges.
        Node-based actions (``select`` / ``reveal`` in the Maya Outliner) are
        delegated to the Maya-side dispatcher, imported lazily so uitk stays
        DCC-agnostic at module-import time.
        """
        try:
            if url.scheme() == "action" and url.host() == "open":
                from urllib.parse import parse_qs

                params = parse_qs(url.query())
                path = (
                    params.get("path", [""])[0]
                    or params.get("filepath", [""])[0]
                )
                if path:
                    _open_in_file_manager(path)
                return
        except Exception as e:  # noqa: BLE001
            self.bridge.logger.error(f"Could not open link: {e}")
            return
        # Node-based actions live in mayatk; import lazily so uitk has no
        # hard DCC dependency.
        try:
            from mayatk.ui_utils._ui_utils import UiUtils
        except Exception:  # noqa: BLE001
            return
        try:
            UiUtils.dispatch_log_link(url, self.bridge.logger)
        except Exception as e:  # noqa: BLE001
            self.bridge.logger.error(f"Could not open link: {e}")

    def _show_startup_info(self) -> None:
        """Pipe the bridge's ``STARTUP_INFO`` into the log panel once.

        No-op when the bridge doesn't declare a ``STARTUP_INFO`` constant
        (marmoset / substance / rizom all rely on per-template docstrings
        and leave this empty). Preserved as an opt-in hook for future
        bridges that want a panel-level intro.
        """
        info = getattr(self.bridge, "STARTUP_INFO", "")
        if not info:
            return
        try:
            self.bridge.logger.info(info)
        except Exception:  # noqa: BLE001
            try:
                self.ui.txt000.append(info)
            except Exception:  # noqa: BLE001
                pass

    # ------------------ Header menu utilities -------------------------

    def header_menu_items(self) -> Tuple[Tuple[str, str, str, str], ...]:
        """Hook: the header-menu items. Default = :attr:`HEADER_MENU_ITEMS`."""
        return self.HEADER_MENU_ITEMS

    def help_spec(self) -> Optional[Dict[str, Any]]:
        """Hook: the ``fmt()`` keyword dict for the header help, or ``None``.

        Default = :attr:`HELP_SPEC` (static). Override to compute it (e.g. a
        panel whose help depends on runtime state)."""
        return self.HELP_SPEC

    def header_init(self, widget) -> None:
        """Default header menu: a "Utilities" separator, the declared
        :meth:`header_menu_items` (each wired to a handler method on this slot),
        and the rich-text help from :meth:`help_spec`.

        Subclasses customise by setting :attr:`HEADER_MENU_ITEMS` /
        :attr:`HELP_SPEC` (or overriding the two hooks) -- *data, not code*. A
        bridge that needs extra wiring can still override this method wholesale.
        """
        widget.menu.add("Separator", setTitle=self.HEADER_MENU_TITLE)
        for label, name, tooltip, handler in self.header_menu_items():
            widget.menu.add(
                "QPushButton", setText=label, setObjectName=name,
                setToolTip=tooltip,
            )
            getattr(widget.menu, name).clicked.connect(getattr(self, handler))

        spec = self.help_spec()
        if spec:
            try:
                from uitk.widgets.mixins.tooltip_mixin import fmt

                widget.set_help_text(fmt(**spec))
            except Exception:  # noqa: BLE001 - help is non-essential chrome
                pass

    def reveal_folder(self, path) -> bool:
        """Open *path* in the OS file manager (logs + returns False if missing).

        Shared by header-menu "Open … folder" actions so subclasses don't each
        re-implement the existence check + cross-platform reveal + error log.
        """
        if not path or not os.path.isdir(str(path)):
            self.bridge.logger.info(f"Folder not found: {path or '(unset)'}")
            return False
        try:
            _open_in_file_manager(str(path))
            return True
        except Exception as e:  # noqa: BLE001
            self.bridge.logger.error(f"Could not open folder: {e}")
            return False

    def open_templates_folder(self) -> None:
        """Reveal :attr:`template_dir` in the OS file manager."""
        self.reveal_folder(self.template_dir)

    def clear_log(self) -> None:
        """Clear the log panel (wired by subclass header menus)."""
        self.ui.txt000.clear()
