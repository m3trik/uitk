# !/usr/bin/python
# coding=utf-8
"""The template combo of a bridge panel: one part of :class:`~uitk.bridge.slots.BridgeSlotsBase`.

``cmb000``: the ``(template, mode)`` entries, the Refresh / Open Folder context
menu, and what a change re-runs (row visibility, enablement, the preset dir,
the template's description in the log).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from uitk.bridge.tooltip import Tooltip


class _TemplateComboMixin(object):
    """The template / mode combo (``cmb000``) and what a change re-runs.

    Reads the composed panel's ``list_template_modes`` / ``template_dir``
    contract, ``ui.cmb000`` and the preset manager the presets part builds.
    """

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

    def select_initial_template_index(self, pairs: List[Tuple[str, str]]) -> int:
        """Return the index of the preferred initial entry in *pairs*.

        Default: 0 (first entry). Subclasses override to bias toward
        e.g. ``("bake", "roundtrip")``.
        """
        return 0

    def template_description(self, template_path: Path) -> Optional[str]:
        """Hook: extract a brief description from a template file."""
        return Tooltip.template_description(template_path)

    def _active_template(self) -> str:
        """Active template stem (mode-agnostic preset key)."""
        pair = self._selected_template_mode()
        if pair:
            return pair[0]
        pairs = self.list_template_modes()
        return pairs[0][0] if pairs else "default"

    # ------------------ Template combo --------------------------------

    @staticmethod
    def _format_combo_label(template: str, mode: str) -> str:
        """Display string for one (template, mode) combo entry.

        Single-mode bridges (rizom) pass ``mode=""`` so the parens are
        elided -- the combo just shows the template stem.
        """
        return f"{template} ({mode})" if mode else template

    def cmb000_init(self, widget) -> None:
        """Switchboard hook: populate the template combobox + wire change handler.

        Template management lives ON the template widget: its context menu
        carries Refresh / Open Folder (the header menu stays panel-level).
        """
        self._populate_template_combo(widget)
        widget.currentIndexChanged.connect(lambda _: self._on_template_changed())
        if not self.TEMPLATE_MENU:
            self._on_template_changed()
            return
        try:
            widget.menu.add(
                "QPushButton",
                setText="Refresh Templates",
                setObjectName="btn_refresh_templates",
                setToolTip="Re-scan the templates folder and rebuild this list.",
            )
            widget.menu.btn_refresh_templates.clicked.connect(self.refresh_templates)
            widget.menu.add(
                "QPushButton",
                setText="Open Templates Folder",
                setObjectName="btn_open_templates",
                setToolTip="Reveal the template folder in the file manager.",
            )
            widget.menu.btn_open_templates.clicked.connect(self.open_templates_folder)
        except Exception:  # noqa: BLE001 -- menu chrome must never block the combo
            pass
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
        """Re-show/-enable rows + re-point preset dir + log description on combo change.

        In semantic-preset mode the preset set is template-agnostic (one shared
        store), so the preset dir is *not* re-pointed per template — only the
        widget-state bridges keep per-template preset subdirs.
        """
        self._refresh_param_visibility()
        self._refresh_param_enablement()
        if self._preset_mgr is not None and not self._semantic_presets:
            self._preset_mgr.preset_dir = self.PRESETS_ROOT / self._active_template()
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

    def open_templates_folder(self) -> None:
        """Reveal :attr:`template_dir` in the OS file manager."""
        self.reveal_folder(self.template_dir)
