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
* Panel-level docs link (:attr:`DOCS_URL`) logged once on load as a clickable
  anchor (opt-in).
* Per-template description displayed whenever the template combo changes.
* Header menu (``header_init``): a "Utilities" separator + declared menu items
  + the rich-text help button, driven by the :attr:`HEADER_MENU_ITEMS` /
  :attr:`HELP_SPEC` class-attr hooks so subclasses set *data, not code*.

Per-bridge slot subclasses contribute only DCC-specific bits:

* Their ``params_module``: a :class:`uitk.bridge.ParamRegistry` subclass
  declaring ``PARAMS`` (it supplies ``referenced_keys`` / ``defaults``).
* Their bridge class (must expose ``.logger``, ``.send(...)``, optionally
  ``.STARTUP_INFO``).
* Their template directory + ``list_template_modes``.
* The :meth:`b000` action that wires DCC selection + bridge handoff.

Custom widget kinds (e.g. an HSV picker) plug in via the shared
:meth:`uitk.bridge.spec.KindFactory.register_kind`; new bridges inherit
every kind the registry knows about.

Layout: this module is the facade. The machinery lives in one private
collaborator per concept, each owning its state and holding the panel --
``_output_dir`` (``_OutputDirRow``: the Output Dir row), ``_param_rows``
(``_ParamRows``: the parameter rows), ``_presets`` (``_Presets``: the preset
combo + Reset to Defaults), ``_template_combo`` (``_TemplateCombo``:
``cmb000``), ``_log_panel`` (``_LogPane``: ``txt000`` and its links) and
``_header_menu`` (``_HeaderMenu``); the last three own no state, so they take
the panel per call. :class:`BridgeSlotsBase` keeps the contract
(every hook and knob, overridable on a subclass) and is the one public name;
:class:`_BridgeSlotsInternal` holds the protected hooks the parts call
through the panel and the private names that read a part's state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pythontk as ptk

from uitk.widgets.textEditLogHandler import TextEditLogHandler
from uitk.widgets.mixins.text import RichTextFormatter

from uitk._facade import _Forward, _Part
from uitk.bridge.spec import AttributeSpec
from uitk.bridge.tooltip import Tooltip
from uitk.bridge._output_dir import _OutputDirRow
from uitk.bridge._param_rows import _ParamRows
from uitk.bridge._presets import _Presets
from uitk.bridge._template_combo import _TemplateCombo
from uitk.bridge._log_panel import _LogPane
from uitk.bridge._header_menu import _HeaderMenu


class _BridgeSlotsInternal(object):
    """Private side of :class:`BridgeSlotsBase`: its parts and protected hooks.

    Each part is a collaborator holding the panel (see the module docstring),
    built fresh by ``BridgeSlotsBase.__init__`` -- and on first access, so a
    panel stubbed with ``__new__`` (or a subclass reaching a part before
    ``super().__init__``) still has one. A part calls every hook, knob and
    sibling through the panel, never through another part, so a subclass
    override (or an instance attribute a test sets) is the one in effect. The
    protected hooks below are the panel's own methods for that reason;
    ``super()`` reaches the parts' defaults. The two process-wide registries,
    the log-link handlers and the temp Output Dirs, are their parts' class
    attributes, read here under their old names.
    """

    # ------------------ The parts --------------------------------------

    _output_dir_part = _Part(_OutputDirRow)
    _params_part = _Part(_ParamRows)
    _presets_part = _Part(_Presets)

    # ------------------ Process-wide registries ------------------------

    _BRIDGE_TEMP_DIRS = _OutputDirRow.TEMP_DIRS  # the same dict
    _LOG_LINK_HANDLERS = _LogPane.LINK_HANDLERS  # the same list
    _remove_bridge_temp_dir = staticmethod(_OutputDirRow.remove_temp_dir)
    # Real static methods (not forwards): tests patch them on the class.
    _open_in_file_manager = staticmethod(_LogPane.open_in_file_manager)
    _record_recent = staticmethod(_OutputDirRow.record_recent)
    _as_tooltip_html = staticmethod(_ParamRows.as_tooltip_html)

    # ------------------ Each part's state, under its old name -----------

    _output_dir_edit = _Forward("_output_dir_part", "edit")
    _output_dir_label = _Forward("_output_dir_part", "label")
    _output_dir_row = _Forward("_output_dir_part", "row")
    _param_widgets = _Forward("_params_part", "widgets")
    _param_rows = _Forward("_params_part", "rows")
    _param_labels = _Forward("_params_part", "labels")
    _section_separators = _Forward("_params_part", "section_separators")
    _param_section = _Forward("_params_part", "section")
    _param_fields = _Forward("_params_part", "fields")
    _param_group = _Forward("_params_part", "group")
    _folded_sections = _Forward("_params_part", "folded_sections")
    _param_rows_shown = _Forward("_params_part", "rows_shown")
    _preset_mgr = _Forward("_presets_part", "mgr")
    _preset_store = _Forward("_presets_part", "store")
    _semantic_presets = _Forward("_presets_part", "semantic")
    _preset_combo = _Forward("_presets_part", "combo")
    _reset_btn = _Forward("_presets_part", "reset_btn")
    _reset_gesture = _Forward("_presets_part", "reset_gesture")
    _live_param_keys = _Forward("_presets_part", "live_param_keys")

    # ------------------ Output Dir row ----------------------------------

    def _build_output_dir_row(self) -> None:
        """Insert the persistent 'Output Dir' row above the parameters."""
        self._output_dir_part.build_row()

    def _configure_output_dir_options(self, edit) -> None:
        """Hook: option-box buttons for the output-dir field.

        Default = a persisted recent-values history + a directory-browse button.
        Subclasses override to customise (the Unity bridge uses an option menu of
        project actions instead of the lone browse button).
        """
        self._output_dir_part.configure_options(edit)

    def _add_recent_output_dir_option(self, edit) -> None:
        """Attach the persisted recent-values history button to *edit* (shared)."""
        self._output_dir_part.add_recent_option(edit)

    def _pick_output_dir(self) -> None:
        """Open a directory dialog, load the choice into the field, and record it.

        Shared by the default browse button and any subclass that surfaces the same
        'Set …' action as a menu item.
        """
        self._output_dir_part.pick()

    def _record_output_dir(self, value) -> None:
        """Record *value* into the output-dir field's recent-values history."""
        self._record_recent(self._output_dir_edit, value)

    # ------------------ Parameter rows ----------------------------------

    def _build_param_widgets(self) -> None:
        """Inject the 'Parameters' group between the Output Dir row and Send."""
        self._params_part.build_widgets()

    def _bind_live_param_tooltips(self) -> None:
        """Install every live tooltip provider on its row."""
        self._params_part.bind_live_tooltips()

    def _wire_action_params(self) -> None:
        """Connect ``action``-kind param buttons to same-named slot methods."""
        self._params_part.wire_action_params()

    def _wire_enablement_refresh(self) -> None:
        """Re-run :meth:`_refresh_param_enablement` on panel show + trigger edits."""
        self._params_part.wire_enablement_refresh()

    def _fold_section(self, section: str, folded: bool) -> None:
        """Fold or unfold *section*'s rows, remember it, and re-fit the window."""
        self._params_part.fold_section(section, folded)

    def _refresh_param_enablement(self) -> None:
        """Re-evaluate which rows are *in effect*, and grey the rest.

        Called on every template change, every panel show, and every edit of a
        supersession trigger; panels also call it themselves after an action
        that changes the state it keys off. The default applies the declared
        supersessions (:meth:`param_supersessions`); a subclass adds the
        checks that need live session state -- calling ``super()`` first, or
        the declared ones stop being applied -- driving
        :meth:`set_param_enabled` for each.

        Must not touch ``self.bridge``: this runs during panel construction,
        where the engine may be an optional package the user declined to
        install.
        """
        self._params_part.refresh_enablement()

    def _read_param(self, key: str) -> Any:
        """Extract the current value via the registered KindHandler."""
        return self._params_part.read(key)

    def _write_param(self, key: str, value: Any) -> None:
        """Push *value* into the widget for *key* via the KindHandler."""
        self._params_part.write(key, value)

    def _set_param_choices(self, key: str, choices) -> None:
        """Repopulate the entries of a choice-driven param (``choice`` /
        ``check_list``) at runtime.

        The hook for parameters whose real entry set is only knowable in the
        live session -- installed app versions, deployable scripts, scene
        contents. The registry declares the kind and any static entries; the
        panel pushes the discovered ones in here from its ``__init__``.
        """
        self._params_part.set_choices(key, choices)

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
        return self._params_part.relevant_keys()

    def _refresh_param_visibility(self) -> None:
        """Show only the rows relevant to the current selection.

        Delegates the "which keys are relevant?" decision to
        :meth:`_relevant_param_keys` so subclasses can drive visibility from a
        template file (default) or a run mode; the row toggling, the dividers,
        the empty group and the height re-fit are :class:`FieldVisibility`.
        A set already on screen is not applied again.
        """
        self._params_part.refresh_visibility()

    # ------------------ Presets -----------------------------------------

    def _build_preset_controls(self) -> None:
        """Insert a user-preset combobox + 'Reset to Defaults' button above b000."""
        self._presets_part.build_controls()

    def _apply_param_dict(self, data: Dict[str, Any]) -> int:
        """Apply a semantic ``{param_key: value}`` preset to the param widgets.

        Keys absent from this panel's ``PARAMS`` are ignored (a shared CLI
        preset may carry knobs this panel doesn't surface). Keys not present in
        the preset keep their current widget values — overlay semantics matching
        the CLI's ``--preset``. Returns the number of widgets updated.
        """
        return self._presets_part.apply_param_dict(data)

    # ------------------ Template combo ----------------------------------

    @staticmethod
    def _format_combo_label(template: str, mode: str) -> str:
        """Display string for one (template, mode) combo entry.

        Single-mode bridges (rizom) pass ``mode=""`` so the parens are
        elided -- the combo just shows the template stem.
        """
        return f"{template} ({mode})" if mode else template

    def _active_template(self) -> str:
        """Active template stem (mode-agnostic preset key)."""
        return _TemplateCombo.active_template(self)

    def _populate_template_combo(self, widget) -> None:
        """Fill cmb000 with ``"<template> (<mode>)"`` entries."""
        _TemplateCombo.populate(self, widget)

    def _selected_template_mode(self) -> Optional[Tuple[str, str]]:
        """``(template, mode)`` for the active combo entry, or *None*."""
        return _TemplateCombo.selected_template_mode(self)

    def _on_template_changed(self) -> None:
        """Re-show/-enable rows + re-point preset dir + log description on combo change."""
        _TemplateCombo.on_template_changed(self)

    def _log_template_description(self) -> None:
        """Surface the active template's docstring in the log panel."""
        _TemplateCombo.log_template_description(self)

    # ------------------ Log pane ----------------------------------------

    def _redirect_log_to_panel(self) -> None:
        """Pipe the bridge logger into ``txt000``, no-op if redirect unavailable."""
        _LogPane.redirect_log_to_panel(self)

    def _on_log_link_clicked(self, url) -> None:
        """Route ``action://`` URIs from the log panel to their handler."""
        _LogPane.on_log_link_clicked(self, url)

    def _show_startup_info(self) -> None:
        """Pipe the bridge's ``STARTUP_INFO`` into the log panel once."""
        _LogPane.show_startup_info(self)

    def _show_docs_link(self) -> None:
        """Log the panel's documentation link once at startup (opt-in)."""
        _LogPane.show_docs_link(self)


class BridgeSlotsBase(_BridgeSlotsInternal):
    """Base class for DCC-bridge slot panels.

    Subclasses **must** set:

    * :attr:`UI_NAME` -- ``self.sb.loaded_ui.<UI_NAME>`` resolves to the panel.
    * :attr:`PRESETS_ROOT` -- per-bridge preset storage root.
    * :attr:`params_module` (class attr or property) -- the bridge's registry:
      a :class:`uitk.bridge.ParamRegistry` subclass declaring ``PARAMS`` (or
      any namespace exposing ``PARAMS`` / ``referenced_keys``).
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
    * :attr:`OUTPUT_DIR_PERSISTS` -- set False so the Output Dir starts blank
      each session instead of restoring the previous one.
    * :attr:`TEMPLATE_EXTENSION` -- ``.py`` (default), ``.lua``, etc.

    Every hook and knob is declared on this class (the protected ones on
    :class:`_BridgeSlotsInternal`); the concept parts read them through the
    panel, so a subclass's value is the one in effect.
    """

    # ------------------ Required class attrs --------------------------

    UI_NAME: str = ""
    PRESETS_ROOT: Optional[Path] = None
    LOG_TAG: str = "bridge"

    # ------------------ Cosmetics -------------------------------------

    # The label column's floor, shared by the Output Dir row and the parameter
    # rows. A built panel widens it to its widest row label and keeps that as
    # the instance's value (``_ParamRows.fit_label_column``), so rows a subclass
    # builds from it afterwards line up with the rest.
    LABEL_MIN_WIDTH = 90

    # ------------------ Output Dir knobs ------------------------------

    # Whether the panel exposes a required "Output Dir" row above the
    # parameter group. Disable for bridges whose roundtrip is in-place
    # (rizom transfers UVs back onto the originals without writing
    # artifacts the user needs to locate) -- the row is then never built,
    # and ``require_output_dir()`` returns ``""`` so subclasses can call
    # it unconditionally without a None guard.
    REQUIRE_OUTPUT_DIR: bool = True

    # When True, ``require_output_dir()`` falls back to an age-swept temp
    # directory (``ensure_bridge_temp_dir``) instead of erroring when neither the
    # user's value nor ``default_output_dir()`` resolves — so an unsaved scene can
    # still hand off. Opt-in: enabled for the file-staging hand-off bridges
    # (Substance / Marmoset) whose output is transient export artifacts the launched
    # app reads once. Left False for bridges whose Output Dir must be a real,
    # user-chosen location (e.g. Unity's project ``Assets`` dir), where silently
    # writing to temp would be wrong — those keep the hard "Output Dir is required"
    # error. No effect when :attr:`REQUIRE_OUTPUT_DIR` is False.
    TEMP_OUTPUT_FALLBACK: bool = False

    # Modes whose Output Dir holds only intermediates the run itself consumes
    # and can therefore delete -- a BLOCKING roundtrip that relocates its
    # durable output elsewhere (the Marmoset bake: maps go to the project's
    # texture folder). For these, a blank field resolves to neither the
    # scene/workspace default nor the session temp dir: ``require_output_dir``
    # returns ``""`` and the bridge allocates -- and cleans up -- a scratch
    # dir of its own (``ptk.TempArtifacts``, scoped), which is the only tier
    # that removes the artifacts when the run is over. A value the user typed
    # still wins: naming a folder is a decision to keep what lands in it.
    TRANSIENT_OUTPUT_MODES: Tuple[str, ...] = ()

    # Whether the Output Dir field's text is saved to QSettings and restored on
    # the next session (the ``restore_state`` default every registered widget
    # gets). True for bridges whose Output Dir is durable project config -- a
    # Unity project root, a photogrammetry job folder -- where retyping it every
    # session is the annoyance. Set False for a hand-off bridge whose blank field
    # is the *useful* default (``default_output_dir`` / the temp fallback resolve
    # it per run): there, a path persisted from a prior scene silently outranks
    # the scene the user actually has open, and the artifacts land beside it. The
    # recent-values history is persisted either way, so last session's path stays
    # one click away.
    OUTPUT_DIR_PERSISTS: bool = True
    OUTPUT_DIR_LABEL = "Output Dir:"
    OUTPUT_DIR_PLACEHOLDER = "(blank: the bridge's default)"
    OUTPUT_DIR_TOOLTIP = (
        "Directory where the export artifacts (FBX, manifest, rendered\n"
        "scripts, baked maps) all land. Leave blank to let the bridge\n"
        "choose: hand-off intermediates go to a temp folder, and what\n"
        "is kept goes to the scene's project."
    )

    # ------------------ Parameter-row knobs ---------------------------

    # Kinds whose widgets are composite (line edit + button, list +
    # buttons, ...) or list-shaped, and must NOT have their parent row
    # clamped to 19px because they are taller than one input line.
    TALL_KINDS: Tuple[str, ...] = ("path", "file", "files", "file_list", "check_list")

    # ``(trigger key, governed keys, reason)`` triples: while *trigger* reads
    # truthy, the *governed* rows grey out with *reason* as their tooltip --
    # the "an Auto toggle takes over the controls it replaces" shape, declared
    # as data. Read from the parameter REGISTRY (``params_module.SUPERSESSIONS``)
    # when it declares them, because which knob supersedes which is a property
    # of the parameter set, not of a DCC's panel -- so both DCCs' panels
    # sharing one registry behave identically without either restating it.
    # This class attr is the fallback for a panel whose registry declares none.
    PARAM_SUPERSESSIONS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = ()

    #: Whether a section's titled divider folds its rows (a disclosure). The
    #: folded set is the user's and is remembered per panel through the
    #: window's custom store; False keeps plain section captions.
    FOLDABLE_SECTIONS: bool = True

    # ------------------ Template-combo knobs --------------------------

    # File extension of the per-template/script files under :attr:`template_dir`.
    # ``.py`` for marmoset / substance, ``.lua`` for rizom. Used by
    # :meth:`_refresh_param_visibility` to locate the placeholder source
    # and by :meth:`_log_template_description` to dispatch the extractor.
    TEMPLATE_EXTENSION: str = ".py"

    # Whether ``cmb000``'s context menu carries the template-management rows
    # (Refresh Templates / Open Templates Folder). True for the bridges that
    # really do render per-template scripts off disk.
    #
    # Set False on a panel whose combo picks a MODE rather than a template file
    # (unity's copy/manage, the WebXR preview's source). Those panels satisfy
    # ``template_dir`` with their own package directory as a stand-in for the
    # no-op description lookup, so the rows offered to re-scan it and to reveal
    # it in the file manager -- pointing an artist at a folder of .py files and
    # implying the list came from it. Both are wrong rather than merely idle:
    # Refresh re-runs a scan that reads nothing, and Open reveals source code.
    TEMPLATE_MENU: bool = True

    # ------------------ Log-pane knobs --------------------------------

    # Where the panel's detailed documentation lives (a web URL). When set,
    # :meth:`_show_docs_link` logs ``"<DOCS_LABEL>: <url>"`` into the log pane
    # once at startup as a clickable anchor, and the header's help card ends
    # in the same link (``header_init``). Empty = neither.
    # Subclasses set these (or override :meth:`docs_url` to compute the URL).
    DOCS_URL: str = ""
    DOCS_LABEL: str = "Detailed docs"

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
    #
    # Template management deliberately does NOT live here: the template combo
    # owns those tasks (it re-scans on panel open, and its context menu --
    # built in ``cmb000_init`` -- carries Refresh / Open Folder), so the
    # header stays for panel-level utilities only.
    HEADER_MENU_TITLE: str = "Utilities"
    HEADER_MENU_ITEMS: Tuple[Tuple[str, str, str, str], ...] = (
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

    def list_template_modes(self) -> List[Tuple[str, str]]:  # pragma: no cover
        raise NotImplementedError

    def b000(self):  # pragma: no cover - subclass contract
        """Implement the per-bridge send action."""
        raise NotImplementedError

    # ------------------ Optional-package provisioning ------------------
    # Policy lives in `uitk.managers.OptionalPackageManager`; the panel supplies
    # only the host wiring (how to prompt, where to log, how to install).

    @property
    def optional_packages(self):
        """This panel's :class:`OptionalPackageManager` (built once, lazily)."""
        mgr = getattr(self, "_optional_packages", None)
        if mgr is None:
            from uitk.managers.optional_package_manager import OptionalPackageManager

            # Log through the Switchboard, not ``self.logger`` -- a slots class gets
            # its logger from its BRIDGE, and this service exists precisely for the
            # window before the bridge does; touching ``self.bridge`` here would
            # recurse straight back into ``make_bridge``.
            mgr = OptionalPackageManager(
                prompt=self.sb.message_box,
                logger=self.sb.logger,
                installer=self._install_optional_package,
            )
            self._optional_packages = mgr
        return mgr

    @staticmethod
    def optional_package_available(spec: str, import_name: str = None) -> bool:
        """Is an optional package importable in THIS interpreter? Silent.

        Static and prompt-free so implicit paths (``make_bridge``, which runs from
        ``__init__``) can ask without a dialog. See
        :meth:`uitk.managers.OptionalPackageManager.available`.
        """
        from uitk.managers.optional_package_manager import OptionalPackageManager

        return OptionalPackageManager.available(spec, import_name)

    def ensure_optional_package(
        self, spec: str, import_name: str = None, *, feature: str = None
    ) -> bool:
        """Make an optional package importable, offering to install it on demand.

        **Explicit user actions only** -- it shows a modal. See
        :meth:`uitk.managers.OptionalPackageManager.ensure`.
        """
        return self.optional_packages.ensure(spec, import_name, feature=feature)

    def _install_optional_package(self, spec: str) -> None:
        """Install *spec* so it is importable in THIS interpreter.

        The DCC-specific seam: tentacle's ``HostBridge`` overrides
        this (``BridgeHost.install_package``) because Blender's bundled interpreter keeps user-site off
        ``sys.path``, so the default ``pip install --user`` would succeed and stay
        unimportable.
        """
        from uitk.managers.optional_package_manager import OptionalPackageManager

        OptionalPackageManager.default_install(spec)

    # ------------------------------------------------------------------ scope
    def resolve_scope_objects(self, scope: str):  # pragma: no cover - contract
        """Hook: turn a ``SCOPE`` value into host objects. DCC-specific.

        Implemented once, on tentacle's ``HostBridge`` (over each host's
        ``BridgeHost``), so every bridge
        that ships the shared :meth:`uitk.bridge.Parameters.scope_spec`
        parameter resolves it identically: it hands its scene reads to
        :meth:`pythontk.HandoffScope.resolve`, which owns the words and their
        fallbacks. The default returns the empty list: a base that never
        overrides this simply has no scope support, and :meth:`scoped_objects`
        then reports "nothing selected" rather than silently exporting the
        wrong set.
        """
        return []

    @staticmethod
    def empty_scope_message(scope: str) -> str:
        """The message shown when a scope resolves to nothing.

        Scope-aware on purpose: "nothing selected" is actively misleading when
        the user asked for Entire Scene and the scene is empty.
        """
        return {
            ptk.HandoffScope.ALL: "The scene contains no mesh geometry to export.",
            ptk.HandoffScope.VISIBLE: "No visible mesh geometry to export.",
        }.get(
            ptk.HandoffScope.word(scope),
            "Nothing selected. Select one or more objects, or change "
            "Scope to 'Entire Scene' / 'Visible Only'.",
        )

    def scoped_objects(self, params, warn: bool = True):
        """Objects for the ``SCOPE`` in *params*; logs when the scope is empty.

        The one call site per bridge:
        ``objects = self.scoped_objects(params)`` then bail if falsy. A panel
        that doesn't expose SCOPE resolves ``"selected"`` -- the behavior every
        bridge had before the parameter existed.
        """
        scope = (params or {}).get(ptk.HandoffScope.PARAM, ptk.HandoffScope.SELECTED)
        objects = self.resolve_scope_objects(scope)
        if not objects and warn:
            self.bridge.logger.warning(self.empty_scope_message(scope))
        return objects

    # ------------------ Init flow -------------------------------------

    def __init__(self, switchboard):
        self.sb = switchboard
        if not self.UI_NAME:
            raise ValueError(
                f"{type(self).__name__} must set UI_NAME (e.g. 'marmoset_bridge')."
            )
        self.ui = getattr(self.sb.loaded_ui, self.UI_NAME)

        self._bridge = None
        # Each part fresh, whatever was reached before this ran.
        self._output_dir_part = _OutputDirRow(self)
        self._params_part = _ParamRows(self)
        self._presets_part = _Presets(self)

        if self.REQUIRE_OUTPUT_DIR:
            self._build_output_dir_row()
        self._build_param_widgets()
        self._wire_action_params()
        self._bind_live_param_tooltips()
        self._build_preset_controls()

        self._wire_enablement_refresh()

        try:
            self._redirect_log_to_panel()
            # The handler the redirect installs already routes the pane's
            # links (no internal navigation, web anchors to the browser); do
            # it explicitly too so a panel whose optional engine is missing
            # -- no bridge, so no redirect -- still has a link-safe pane for
            # what ``panel_log`` appends by hand (the docs link, above all).
            TextEditLogHandler.route_links(self.ui.txt000)
            if hasattr(self.ui.txt000, "anchorClicked"):
                self.ui.txt000.anchorClicked.connect(self._on_log_link_clicked)
        except Exception as e:  # noqa: BLE001
            self.sb.logger.warning(
                f"[{self.LOG_TAG}] log panel wiring failed (ignored): {e}",
                exc_info=True,
            )

        self._show_startup_info()
        self._show_docs_link()

    @property
    def bridge(self):
        """Lazy-instantiated bridge (caches a single instance per slot).

        :meth:`make_bridge` may return ``None`` when the panel's engine lives in
        an optional package the user declined to install (see
        :meth:`ensure_optional_package`). That is a supported outcome, but the
        panel is then unusable — and every consumer here reaches straight for
        ``self.bridge.logger``, so letting ``None`` through would surface as
        ``AttributeError: 'NoneType' object has no attribute 'logger'``. Raise
        one actionable error instead, in the single place that can.
        """
        if self._bridge is None:
            self._bridge = self.make_bridge()
        if self._bridge is None:
            raise RuntimeError(
                f"{type(self).__name__}: this panel's engine is unavailable — "
                f"its optional package is not installed. Install it from the "
                f"panel's own controls, or install it manually and reopen."
            )
        return self._bridge

    def peek_bridge(self):
        """The bridge if it can be built, else ``None`` — never raises.

        For consumers that run during ``__init__`` (log wiring, startup info)
        or that merely *decorate* the panel: a panel whose optional engine is
        missing must still open, so its own controls can install it. Letting
        the raising :attr:`bridge` reach a constructor took the whole panel
        down with it and stranded the install dialog it had just opened.
        """
        try:
            return self.bridge
        except Exception:  # noqa: BLE001 - absence is the expected outcome here
            # Debug, not error: a missing optional engine is routine, but a
            # REAL construction bug must stay diagnosable — the old path
            # printed it; swallowing with no trace would hide regressions.
            try:
                self.sb.logger.debug(
                    f"{type(self).__name__}: engine unavailable", exc_info=True
                )
            except Exception:  # noqa: BLE001
                pass
            return None

    def panel_log(self, message: str, level: str = "info") -> None:
        """Log to the panel, working whether or not the engine exists.

        Routes through the bridge logger (the panel's normal sink) when the
        bridge is buildable; otherwise appends straight to the log text widget
        and echoes to the Switchboard logger. Panel actions that must report
        while the optional engine is MISSING — install/status flows above all —
        use this instead of ``self.bridge.logger``, which would raise.
        """
        bridge = self.peek_bridge()
        if bridge is not None:
            try:
                getattr(bridge.logger, level, bridge.logger.info)(message)
                return
            except Exception:  # noqa: BLE001 - fall through to the raw sinks
                pass
        try:
            # Linked the way the log handler links what it appends.
            self.ui.txt000.append(RichTextFormatter.linkify(message))
        except Exception:  # noqa: BLE001 - some panels have no log widget
            pass
        getattr(self.sb.logger, level, self.sb.logger.info)(message)

    # ------------------ Output Dir (_OutputDirRow) ---------------------

    def default_output_dir(self) -> str:
        """Hook: fallback path when the user leaves Output Dir blank.

        Returns the empty string by default. DCC-specific subclasses
        override -- e.g. a photogrammetry bridge returns its profile's
        output root.
        """
        return ""

    @staticmethod
    def ensure_bridge_temp_dir(tag: str) -> str:
        """Create (once per host process) and return a temp Output Dir for *tag*.

        Backs :attr:`TEMP_OUTPUT_FALLBACK`: the last-resort Output Dir when neither the
        user's value nor the DCC scene/workspace default resolves (e.g. an unsaved scene with no
        workspace), so a hand-off bridge can still export without forcing the user to pick a path.
        Reused across sends for the same *tag* within one host process.

        A ``detached`` ``ptk.TempArtifacts`` store: the folder OUTLIVES the host. A launched app's
        project (Painter, Toolbag) keeps reading what the send wrote after the host exits, so
        removing it at exit -- the old ``session`` policy -- broke that project. The age sweep
        reclaims it once its newest file is :attr:`_BRIDGE_TEMP_MAX_AGE_DAYS` old, killed host or
        not; :meth:`_remove_bridge_temp_dir` reclaims it early."""
        return _OutputDirRow.ensure_temp_dir(tag)

    def resolved_output_dir(self) -> str:
        """Return the current Output Dir text trimmed of whitespace.

        Returns the empty string when :attr:`REQUIRE_OUTPUT_DIR` is False
        (the row was never built) so subclasses can call this unconditionally.
        """
        return self._output_dir_part.resolved()

    def require_output_dir(self, mode: Optional[str] = None) -> Optional[str]:
        """Return the Output Dir for a run in *mode*, or log an error on empty.

        Resolution order:

        1. The user's typed value in the line edit.
        2. When *mode* is one of :attr:`TRANSIENT_OUTPUT_MODES`, ``""`` --
           the run's artifacts are its own scratch, so the bridge allocates
           and deletes them rather than inheriting a durable location.
        3. :meth:`default_output_dir` (DCC-side fallback) -- on hit, the
           chosen path is written back into the line edit and announced
           in the log panel so the user sees where files landed.
        4. When :attr:`TEMP_OUTPUT_FALLBACK` is set, an age-swept temp
           directory (:func:`ensure_bridge_temp_dir`) -- also written back
           and announced -- so an unsaved scene can still hand off.
        5. Log an error + focus the field, return ``None`` to signal
           the caller to abort.

        When :attr:`REQUIRE_OUTPUT_DIR` is False, returns ``""``
        unconditionally so the caller can pass the result through to
        bridges that tolerate empty output dirs.

        ``""`` and ``None`` are distinct returns: ``""`` means "no location
        chosen -- the bridge decides", ``None`` means abort.
        """
        return self._output_dir_part.require(mode)

    # ------------------ Parameter rows (_ParamRows) --------------------

    def format_param_tooltip(self, spec: AttributeSpec) -> str:
        """Hook: build the rich-text tooltip for one parameter spec."""
        return Tooltip.format_param_tooltip(spec)

    def live_param_tooltips(self) -> Dict[str, Callable[[], str]]:
        """Hook: ``{param key: provider}`` for rows whose tooltip tracks LIVE state.

        :meth:`format_param_tooltip` runs once, at build time, so a row that
        describes something the *session* owns -- a scene set the user defines
        from a selection, a path that resolves per scene -- is stale the moment
        that state moves. A provider registered here is called on every hover
        instead (:mod:`uitk.widgets.mixins.tooltip_mixin`), so the row can
        answer "what is captured right now?" with no refresh plumbing.

        A provider returns the WHOLE tooltip, so fold the static text back in
        with ``self.format_param_tooltip(spec)`` -- binding replaces the
        widget's tooltip rather than appending to it. Pair it with
        :meth:`pythontk.TooltipFormat.stored_items`
        for the usual "here is what you captured" list.

        Bound to the row's label AND its control -- both are hover targets for
        the same row. An ``action`` row's buttons keep their own per-choice
        tips: those describe the *click*, not the contents.

        Returns:
            (dict) Param key -> zero-argument callable returning tooltip HTML.
            Prefer a bound method over a closure: the tooltip surface weakrefs
            bound-method providers, so the binding can't outlive this panel.
            Unknown keys are ignored, so a shared base may offer a row that
            only some of its panels register.
        """
        return {}

    def live_param_tooltip_blocks(self) -> Dict[str, Callable[[], str]]:
        """Hook: ``{param key: provider}`` for a live block APPENDED to a row's tips.

        The composable counterpart to :meth:`live_param_tooltips`. That one owns
        the WHOLE tooltip, which is right for a row whose static text is the
        thing going stale -- and wrong for an ``action`` row, whose buttons each
        carry their own per-choice description. Replacing three specific answers
        ("what does Clear do?") with one general one is a bad trade, and the
        buttons are exactly where the user is standing when they wonder what the
        row currently holds.

        A block provider returns only the live part, so every hover target on
        the row -- label, control, and each action button -- keeps its own text
        and gains the current contents underneath it.

        Register a key in ONE of the two hooks: binding replaces a widget's
        provider rather than stacking, and blocks are installed second, so a
        key in both silently loses its whole-tooltip provider on the label and
        the control while the buttons keep only the block.

        Returns:
            (dict) Param key -> zero-argument callable returning the live HTML
            block (see
            :meth:`pythontk.TooltipFormat.stored_items`).
            Unknown keys are ignored.
        """
        return {}

    def set_param_enabled(self, key: str, enabled: bool, reason: str = "") -> None:
        """Grey out (or re-enable) one parameter row, with *reason* as its tooltip.

        For parameters whose relevance depends on live session state rather
        than on the template -- e.g. a suffix-pairing fallback that the scene's
        explicit set makes moot. Visibility already answers "does this template
        use the knob?" (:meth:`_refresh_param_visibility`); this answers "is it
        in effect right now?", which is a different question and reads better
        greyed than hidden -- the user can still see the value that *would*
        apply, and why it doesn't.

        The row container itself stays enabled and carries *reason*: Qt does
        not deliver tooltip events to disabled widgets, but a disabled child
        doesn't consume the hover either, so the parent's tooltip is what
        surfaces. Unknown keys are ignored -- a shared base can offer the row
        without every panel registering it.

        Another parameter's inline cell (see :meth:`_build_inline_cell`) lives
        inside this row but is NOT part of it, so it is skipped: greying the
        value an "Auto" toggle superseded must not grey the toggle sitting
        beside it, or the user cannot turn it back off.
        """
        self._params_part.set_param_enabled(key, enabled, reason)

    def param_supersessions(self) -> Tuple[Tuple[str, Tuple[str, ...], str], ...]:
        """The ``(trigger, governed, reason)`` triples in effect for this panel.

        The registry's own declaration wins; :attr:`PARAM_SUPERSESSIONS` is the
        fallback. Override to compute them.
        """
        declared = getattr(self.params_module, "SUPERSESSIONS", None)
        return tuple(declared if declared is not None else self.PARAM_SUPERSESSIONS)

    def collect_param_values(self) -> Dict[str, Any]:
        """Snapshot every widget's current value, regardless of visibility.

        ``action`` rows carry no value (their buttons are commands, not
        data) and are excluded, so send params stay purely value-shaped.
        """
        return self._params_part.collect_values()

    # ------------------ Presets (_Presets) -----------------------------

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

    # ------------------ Template combo (_TemplateCombo) ----------------

    def select_initial_template_index(self, pairs: List[Tuple[str, str]]) -> int:
        """Return the index of the preferred initial entry in *pairs*.

        Default: 0 (first entry). Subclasses override to bias toward
        e.g. ``("bake", "roundtrip")``.
        """
        return 0

    def template_description(self, template_path: Path) -> Optional[str]:
        """Hook: extract a brief description from a template file."""
        return Tooltip.template_description(template_path)

    def cmb000_init(self, widget) -> None:
        """Switchboard hook: populate the template combobox + wire change handler.

        Template management lives ON the template widget: its context menu
        carries Refresh / Open Folder (the header menu stays panel-level).
        """
        _TemplateCombo.init_combo(self, widget)

    def refresh_templates(self) -> None:
        """Re-scan disk and rebuild the template combo + parameter UI."""
        self._populate_template_combo(self.ui.cmb000)
        self._on_template_changed()

    def open_templates_folder(self) -> None:
        """Reveal :attr:`template_dir` in the OS file manager."""
        self.reveal_folder(self.template_dir)

    # ------------------ Log pane (_LogPane) ----------------------------

    @staticmethod
    def register_log_link_handler(handler: Callable) -> None:
        """Register a ``handler(url, logger) -> bool`` for non-``open`` log-panel
        ``action://`` links (returns True when it handled the link).

        DCC packages (mayatk / blendertk) call this from their ``UiHandler.__init__``
        so their node-dispatch runs without uitk importing them. Handlers are tried
        in registration order until one returns True. Idempotent — re-registering
        the same callable is a no-op.
        """
        _LogPane.register_link_handler(handler)

    def docs_url(self) -> str:
        """Hook: the panel's documentation URL, or ``""`` for no docs link.

        Default = :attr:`DOCS_URL` (static). Override to compute it (e.g. a
        panel that points at a per-engine page)."""
        return self.DOCS_URL

    def clear_log(self) -> None:
        """Clear the log panel (wired by subclass header menus)."""
        self.ui.txt000.clear()

    # ------------------ Header menu -----------------------------------

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
        _HeaderMenu.header_init(self, widget)

    def reveal_folder(self, path) -> bool:
        """Open *path* in the OS file manager (logs + returns False if missing).

        Shared by header-menu "Open … folder" actions so subclasses don't each
        re-implement the existence check + cross-platform reveal + error log.
        """
        return _HeaderMenu.reveal_folder(self, path)
