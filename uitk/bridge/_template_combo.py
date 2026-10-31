# !/usr/bin/python
# coding=utf-8
"""The template combo of a bridge panel: one part of :class:`~uitk.bridge.slots.BridgeSlotsBase`.

``cmb000``: the ``(template, mode)`` entries, the Refresh / Open Folder context
menu, and what a change re-runs (row visibility, enablement, the preset dir,
the template's description in the log).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:  # annotation only; the facade imports this module
    from uitk.bridge.slots import BridgeSlotsBase


class _TemplateCombo(object):
    """A bridge panel's template / mode combo (``cmb000``) and what a change re-runs.

    Holds no state of its own -- the entries live on ``ui.cmb000`` -- so every
    method takes the panel, and reaches its ``list_template_modes`` /
    ``template_dir`` contract, its knobs and every hook
    (``_format_combo_label``, ``select_initial_template_index``,
    ``_log_template_description`` ...) through it.
    """

    @staticmethod
    def active_template(panel: "BridgeSlotsBase") -> str:
        """Active template stem (mode-agnostic preset key)."""
        pair = panel._selected_template_mode()
        if pair:
            return pair[0]
        pairs = panel.list_template_modes()
        return pairs[0][0] if pairs else "default"

    @staticmethod
    def init_combo(panel: "BridgeSlotsBase", widget) -> None:
        """Populate *widget*, wire its change handler and its context menu."""
        panel._populate_template_combo(widget)
        widget.currentIndexChanged.connect(lambda _: panel._on_template_changed())
        if not panel.TEMPLATE_MENU:
            panel._on_template_changed()
            return
        try:
            widget.menu.add(
                "QPushButton",
                setText="Refresh Templates",
                setObjectName="btn_refresh_templates",
                setToolTip="Re-scan the templates folder and rebuild this list.",
            )
            widget.menu.btn_refresh_templates.clicked.connect(panel.refresh_templates)
            widget.menu.add(
                "QPushButton",
                setText="Open Templates Folder",
                setObjectName="btn_open_templates",
                setToolTip="Reveal the template folder in the file manager.",
            )
            widget.menu.btn_open_templates.clicked.connect(panel.open_templates_folder)
        except Exception:  # noqa: BLE001 -- menu chrome must never block the combo
            pass
        panel._on_template_changed()

    @staticmethod
    def populate(panel: "BridgeSlotsBase", widget) -> None:
        """Fill cmb000 with ``"<template> (<mode>)"`` entries.

        A mode combo (``TEMPLATE_MENU`` off) with one entry or none offers
        nothing to choose, so it hides -- still holding its entry, so the
        selection reads as before -- and comes back when a repopulate brings a
        second (the WebXR preview's Source: File on Disk alone standalone, a
        host's scopes once one is injected). A template combo stays: its
        context menu is reachable however few templates it lists.
        """
        pairs = panel.list_template_modes()
        widget.blockSignals(True)
        try:
            widget.clear()
            for template, mode in pairs:
                widget.addItem(
                    panel._format_combo_label(template, mode), (template, mode)
                )
            if pairs:
                widget.setCurrentIndex(panel.select_initial_template_index(pairs))
        finally:
            widget.blockSignals(False)
        widget.setVisible(panel.TEMPLATE_MENU or len(pairs) > 1)

    @staticmethod
    def selected_template_mode(panel: "BridgeSlotsBase") -> Optional[Tuple[str, str]]:
        """``(template, mode)`` for the active combo entry, or *None*.

        ``itemData`` stores a ``(template, mode)`` tuple, but some PySide
        bindings round-trip it back through ``QVariant`` as a *list* --
        so accept either and normalise to a tuple.
        """
        combo = panel.ui.cmb000
        idx = combo.currentIndex()
        if idx < 0:
            return None
        data = combo.itemData(idx)
        if isinstance(data, (tuple, list)) and len(data) == 2:
            return tuple(data)
        return None

    @staticmethod
    def on_template_changed(panel: "BridgeSlotsBase") -> None:
        """Re-show/-enable rows + re-point preset dir + log description on combo change.

        In semantic-preset mode the preset set is template-agnostic (one shared
        store), so the preset dir is *not* re-pointed per template — only the
        widget-state bridges keep per-template preset subdirs.
        """
        panel._refresh_param_visibility()
        panel._refresh_param_enablement()
        mgr = panel._preset_mgr
        if mgr is not None and not panel._semantic_presets:
            mgr.preset_dir = panel.PRESETS_ROOT / panel._active_template()
            refresh = getattr(mgr, "_refresh_combo", None)
            if callable(refresh):
                refresh()
        panel._log_template_description()

    @staticmethod
    def log_template_description(panel: "BridgeSlotsBase") -> None:
        """Surface the active template's docstring in the log panel."""
        pair = panel._selected_template_mode()
        if not pair:
            return
        template, mode = pair
        path = panel.template_dir / f"{template}{panel.TEMPLATE_EXTENSION}"
        desc = panel.template_description(path)
        if not desc:
            return
        label = panel._format_combo_label(template, mode)
        try:
            panel.bridge.logger.info(f"[{label}] {desc}")
        except Exception:  # noqa: BLE001
            pass
