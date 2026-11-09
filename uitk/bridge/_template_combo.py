# !/usr/bin/python
# coding=utf-8
"""The template combo of a parameter panel: one part of :class:`~uitk.bridge.slots.ParamPanelSlots`.

``cmb000``: the ``(template, mode)`` entries, the Refresh / Open Folder context
menu, and what a change re-runs (row visibility, enablement, the preset dir,
the template's description in the log).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:  # annotation only; the facade imports this module
    from uitk.bridge.slots import ParamPanelSlots


class _TemplateCombo(object):
    """A bridge panel's template / mode combo (``cmb000``) and what a change re-runs.

    Holds no state of its own -- the entries live on ``ui.cmb000`` -- so every
    method takes the panel, and reaches its ``list_template_modes`` /
    ``template_dirs`` contract, its knobs and every hook
    (``_format_combo_label``, ``select_initial_template_index``,
    ``_log_template_description`` ...) through it.
    """

    @staticmethod
    def active_template(panel: "ParamPanelSlots") -> str:
        """Active template stem (mode-agnostic preset key)."""
        pair = panel._selected_template_mode()
        if pair:
            return pair[0]
        pairs = panel.list_template_modes()
        return pairs[0][0] if pairs else "default"

    @staticmethod
    def init_combo(panel: "ParamPanelSlots", widget) -> None:
        """Populate *widget*, wire its change handler and its context menu.

        The selection persists by its label (``restore_by``), not its row: the
        list is the person's scripts beside the bundled ones, sorted, so one
        added, removed or renamed between sessions would shift a saved row onto
        another script.
        """
        widget.restore_by = "text"
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
            if panel.user_scripts_dir is not None:
                widget.menu.btn_open_templates.setText("Open My Scripts Folder")
                widget.menu.btn_open_templates.setToolTip(
                    "Reveal your own scripts folder: a script dropped there shows in this "
                    "list after a Refresh, and one named like a built-in runs in its place."
                )
                widget.menu.add(
                    "QPushButton",
                    setText="Copy to My Scripts",
                    setObjectName="btn_copy_to_my_scripts",
                    setToolTip="Copy the selected script into your own folder to edit; "
                    "your copy then runs in its place.",
                )
                widget.menu.btn_copy_to_my_scripts.clicked.connect(panel.copy_to_my_scripts)
        except Exception:  # noqa: BLE001 -- menu chrome must never block the combo
            pass
        panel._on_template_changed()

    @staticmethod
    def populate(panel: "ParamPanelSlots", widget) -> None:
        """Fill cmb000 with ``"<template> (<mode>)"`` entries.

        A mode combo (``TEMPLATE_MENU`` off) with one entry or none offers
        nothing to choose, so it hides -- still holding its entry, so the
        selection reads as before -- and comes back when a repopulate brings a
        second (the WebXR preview's Source: File on Disk alone standalone, a
        host's scopes once one is injected). A template combo stays: its
        context menu is reachable however few templates it lists.

        A repopulate (Refresh, Copy to My Scripts) keeps the entry selected
        when it is still listed, so the next Run runs the script the person
        picked, not the default. A person's own script is marked in italics
        with a tooltip, never in its label: the selection persists by label
        (``restore_by``), and a copy appearing must not rename the entry.
        """
        pairs = panel.list_template_modes()
        try:  # a panel with no folder yet (a stub) marks nothing
            tiered = panel.TEMPLATE_MENU and panel.user_scripts_dir is not None
        except NotImplementedError:
            tiered = False
        current = _TemplateCombo.pair_of(widget)
        widget.blockSignals(True)
        try:
            widget.clear()
            for index, (template, mode) in enumerate(pairs):
                widget.addItem(panel._format_combo_label(template, mode), (template, mode))
                if tiered and panel.template_tier(template) == "user":
                    _TemplateCombo.mark_mine(widget, index, panel.template_path(template))
            if pairs:
                keep = current in pairs
                widget.setCurrentIndex(
                    pairs.index(current) if keep else panel.select_initial_template_index(pairs)
                )
        finally:
            widget.blockSignals(False)
        widget.setVisible(panel.TEMPLATE_MENU or len(pairs) > 1)

    @staticmethod
    def mark_mine(widget, index: int, path) -> None:
        """Mark entry *index* as the person's own script (at *path*): italics
        and a tooltip, the label left as it is."""
        from qtpy import QtCore

        font = widget.font()
        font.setItalic(True)
        widget.setItemData(index, font, QtCore.Qt.FontRole)
        widget.setItemData(
            index,
            f"Your own script, run in place of any built-in of its name: {path}",
            QtCore.Qt.ToolTipRole,
        )

    @staticmethod
    def pair_of(widget) -> Optional[Tuple[str, str]]:
        """``(template, mode)`` of *widget*'s current entry, or *None*.

        ``itemData`` stores a ``(template, mode)`` tuple, but some PySide
        bindings round-trip it back through ``QVariant`` as a *list* --
        so accept either and normalise to a tuple.
        """
        idx = widget.currentIndex()
        if idx < 0:
            return None
        data = widget.itemData(idx)
        if isinstance(data, (tuple, list)) and len(data) == 2:
            return tuple(data)
        return None

    @staticmethod
    def selected_template_mode(panel: "ParamPanelSlots") -> Optional[Tuple[str, str]]:
        """``(template, mode)`` for the active combo entry, or *None* (:meth:`pair_of`)."""
        return _TemplateCombo.pair_of(panel.ui.cmb000)

    @staticmethod
    def on_template_changed(panel: "ParamPanelSlots") -> None:
        """Re-show/-enable rows + re-point preset dir + log description on combo change.

        In semantic-preset mode the preset set is template-agnostic (one shared
        store), so the preset dir is *not* re-pointed per template — only the
        widget-state bridges keep per-template preset subdirs. A person's own
        script brings the rows it declares (``add_script_rows``) first.
        """
        panel.add_script_rows()
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
    def log_template_description(panel: "ParamPanelSlots") -> None:
        """Surface the active template's docstring in the log panel."""
        pair = panel._selected_template_mode()
        if not pair:
            return
        template, mode = pair
        desc = panel.template_description(panel.template_path(template))
        if not desc:
            return
        label = panel._format_combo_label(template, mode)
        try:
            panel.bridge.logger.info(f"[{label}] {desc}")
        except Exception:  # noqa: BLE001
            pass
