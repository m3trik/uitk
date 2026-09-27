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

Layout: this module is the facade. The machinery lives in one private base per
concept, composed through :class:`_BridgeSlotsInternal` -- ``_output_dir`` (the
Output Dir row), ``_param_rows`` (the parameter rows), ``_presets`` (the preset
combo + Reset to Defaults), ``_template_combo`` (``cmb000``), ``_log_panel``
(``txt000`` and its links) and ``_header_menu``. They split the source, not the
contract: every hook stays overridable on a subclass, and
:class:`BridgeSlotsBase` is the one public name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pythontk as ptk
from qtpy import QtWidgets

from uitk.widgets.comboBox import ComboBox
from uitk.widgets.textEditLogHandler import TextEditLogHandler
from uitk.widgets.mixins.text import RichTextFormatter
from uitk.managers.preset_manager import PresetManager
from uitk.managers.field_visibility import FieldVisibility

from uitk.bridge._output_dir import _OutputDirMixin
from uitk.bridge._param_rows import _ParamRowsMixin
from uitk.bridge._presets import _PresetsMixin
from uitk.bridge._template_combo import _TemplateComboMixin
from uitk.bridge._log_panel import _LogPanelMixin
from uitk.bridge._header_menu import _HeaderMenuMixin


class _BridgeSlotsInternal(
    _OutputDirMixin,
    _ParamRowsMixin,
    _PresetsMixin,
    _TemplateComboMixin,
    _LogPanelMixin,
    _HeaderMenuMixin,
):
    """Private implementation of :class:`BridgeSlotsBase`: one base per panel concept.

    Each base is a part of ONE class, not a reusable mixin (the scene
    exporter's ``_task_*`` phase mixins are the precedent): it reads what the
    composed panel provides -- ``self.ui``, ``self.sb``, ``self.bridge`` and the
    subclass contract below. No member is defined on two of them, so their
    order decides nothing. The two process-wide registries, the log-link
    handlers (``_log_panel``) and the temp Output Dirs (``_output_dir``), live
    on their parts and read through this class as before.
    """


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

    Those hooks live on the concept parts (see :class:`_BridgeSlotsInternal`);
    this class keeps the contract, the init flow, bridge access and scope.
    """

    # ------------------ Required class attrs --------------------------

    UI_NAME: str = ""
    PRESETS_ROOT: Optional[Path] = None
    LOG_TAG: str = "bridge"

    # ------------------ Cosmetics -------------------------------------

    # Label column width, shared by the Output Dir row and the parameter rows.
    LABEL_MIN_WIDTH = 90

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

        The DCC-specific seam: ``blendertk``'s :class:`BlenderBridgeSlotsBase`
        overrides this because Blender's bundled interpreter keeps user-site off
        ``sys.path``, so the default ``pip install --user`` would succeed and stay
        unimportable.
        """
        from uitk.managers.optional_package_manager import OptionalPackageManager

        OptionalPackageManager.default_install(spec)

    # ------------------------------------------------------------------ scope
    def resolve_scope_objects(self, scope: str):  # pragma: no cover - contract
        """Hook: turn a ``SCOPE`` value into host objects. DCC-specific.

        Implemented once per package on the DCC bridge-slots base
        (``MayaBridgeSlotsBase`` / ``BlenderBridgeSlotsBase``), so every bridge
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
        self._param_widgets: Dict[str, QtWidgets.QWidget] = {}
        self._param_rows: Dict[str, QtWidgets.QWidget] = {}
        # The row's caption, kept alongside its control so a live tooltip
        # provider can cover BOTH hover targets (see live_param_tooltips).
        self._param_labels: Dict[str, QtWidgets.QLabel] = {}
        # Category dividers: section name -> Separator, plus each param's section,
        # so a divider can hide when its whole section is hidden for the mode.
        self._section_separators: Dict[str, QtWidgets.QWidget] = {}
        self._param_section: Dict[str, str] = {}
        self._preset_mgr: Optional[PresetManager] = None
        self._preset_store = None  # set in _build_preset_controls (semantic mode)
        self._semantic_presets = False
        self._preset_combo: Optional[ComboBox] = None
        self._output_dir_edit: Optional[QtWidgets.QLineEdit] = None
        # Built in _build_param_widgets from the dicts above; the rows stay
        # the tooltip and value code's index, this is only the visibility.
        self._param_fields: Optional[FieldVisibility] = None
        self._param_group: Optional[QtWidgets.QGroupBox] = None

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
            print(f"[{self.LOG_TAG}] log panel wiring failed (ignored): {e}")

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
