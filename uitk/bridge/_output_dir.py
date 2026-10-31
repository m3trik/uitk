# !/usr/bin/python
# coding=utf-8
"""The Output Dir row of a bridge panel: one part of :class:`~uitk.bridge.slots.BridgeSlotsBase`.

The optional "Output Dir" field above the parameters, its option-box buttons
(persisted recent values + a directory browse), and the chain a send resolves it
through: the typed value, a transient mode's own scratch, the host's
``default_output_dir``, an age-swept temp dir, then an error.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from qtpy import QtCore, QtWidgets

if TYPE_CHECKING:  # annotation only; the facade imports this module
    from uitk.bridge.slots import BridgeSlotsBase


class _OutputDirRow(object):
    """A bridge panel's Output Dir row and its resolution chain.

    Owns the row's widgets. The knobs (``REQUIRE_OUTPUT_DIR``,
    ``TEMP_OUTPUT_FALLBACK``, ``TRANSIENT_OUTPUT_MODES``, ``OUTPUT_DIR_*``,
    ``LOG_TAG``, ``LABEL_MIN_WIDTH``) and every hook (``default_output_dir``,
    ``_configure_output_dir_options`` ...) are read through the panel, so a
    subclass's value or override is the one in effect. The temp-dir registry
    is a class attribute: every bridge panel in the process shares one.
    """

    # One temp Output Dir per bridge tag per host process. It outlives the
    # process (a launched app's project may still read it) and is reclaimed by
    # the age sweep. Values are ``(TempArtifacts store, path)`` -- the store so
    # the folder can be reclaimed early, the path so reading it back needs
    # nothing private.
    TEMP_DIRS: Dict[str, Tuple[Any, str]] = {}
    # Days past which the sweep reclaims a temp Output Dir, judged by the
    # newest file in it.
    TEMP_MAX_AGE_DAYS: float = 7

    def __init__(self, panel: "BridgeSlotsBase") -> None:
        self._panel = panel
        self.edit: Optional[QtWidgets.QLineEdit] = None
        self.label: Optional[QtWidgets.QLabel] = None
        self.row: Optional[QtWidgets.QWidget] = None

    @staticmethod
    def remove_temp_dir(key: str) -> None:
        """Remove the temp Output Dir created for *key* (best-effort).

        Exposed for tests and for a host that wants to reclaim early; the
        ordinary path is the age sweep.
        """
        entry = _OutputDirRow.TEMP_DIRS.pop(key, None)
        if entry is not None:
            entry[0].cleanup(force=True)

    @staticmethod
    def ensure_temp_dir(tag: str) -> str:
        import pythontk as ptk

        key = tag or "bridge"
        entry = _OutputDirRow.TEMP_DIRS.get(key)
        if entry is None:
            store = ptk.TempArtifacts(
                f"uitk_bridge_{key}",
                policy="detached",
                max_age_days=_OutputDirRow.TEMP_MAX_AGE_DAYS,
            )
            entry = (store, store.dir_path())
            _OutputDirRow.TEMP_DIRS[key] = entry
        return entry[1]

    # ------------------ Output Dir row --------------------------------

    def build_row(self) -> None:
        """Insert a persistent 'Output Dir' line edit (with option-box buttons) above params.

        The path field carries uitk **option-box** icon buttons instead of a bare
        ``...`` push-button. ``_configure_output_dir_options`` decides which —
        the default is a persisted **recent-values** history + a **directory
        browse** button; subclasses override it (e.g. the Unity bridge swaps the
        browse button for an option *menu* of project actions).

        The edit is parented into the row layout (with stretch) **before** the
        option box wraps it, so the wrap reparents it in place via
        ``replaceWidget`` (preserving the stretch factor) while it is already
        layout-managed. Wrapping a *parentless* edit instead lets it briefly show
        as a top-level widget, whose ``OptionBoxContainer.showEvent`` schedules an
        ``_adjust_to_content`` that collapses + absolutely-positions the container
        — leaving the field right-shifted instead of filling the row.
        """
        panel = self._panel
        layout = panel.ui.grp_process.layout()

        row = QtWidgets.QWidget(panel.ui.grp_process)
        hbox = QtWidgets.QHBoxLayout(row)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(2)

        label = QtWidgets.QLabel(panel.OUTPUT_DIR_LABEL, row)
        label.setMinimumWidth(panel.LABEL_MIN_WIDTH)
        label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.label = label  # joins the label column (_ParamRows.fit_label_column)

        edit = QtWidgets.QLineEdit(row)
        edit.setObjectName(f"{panel.LOG_TAG}_output_dir")
        edit.setPlaceholderText(panel.OUTPUT_DIR_PLACEHOLDER)
        edit.setMinimumHeight(19)
        edit.setMaximumHeight(19)
        edit.setToolTip(panel.OUTPUT_DIR_TOOLTIP)
        # Set before the row is registered: ``register_widget`` only defaults
        # ``restore_state`` to True when the attribute is ABSENT, so this is what
        # decides whether the field is saved/restored across sessions at all.
        edit.restore_state = panel.OUTPUT_DIR_PERSISTS
        self.edit = edit

        hbox.addWidget(label)
        hbox.addWidget(edit, 1)

        # Wrap after the edit is in the layout: the option box replaces it in
        # place (keeping the stretch) instead of leaving a stale top-level geom.
        panel._configure_output_dir_options(edit)

        insert_at = layout.indexOf(panel.ui.cmb000) + 1
        layout.insertWidget(insert_at, row)
        self.row = row

    # ------------------ Output Dir option-box buttons -----------------

    def browse_title(self) -> str:
        """Window title for the output-dir browse dialog (from the row label)."""
        return self._panel.OUTPUT_DIR_LABEL.rstrip(": ") or "Select directory"

    def add_recent_option(self, edit) -> None:
        """Attach the persisted recent-values history button to *edit* (shared)."""
        edit.option_box.recent(
            settings_key=f"{self._panel.LOG_TAG}_output_dir_recent",
            auto_record=True,
            display_format="auto",
        )

    def configure_options(self, edit) -> None:
        """The default option-box buttons (see ``_configure_output_dir_options``)."""
        panel = self._panel
        panel._add_recent_output_dir_option(edit)
        edit.option_box.set_action(
            callback=panel._pick_output_dir,
            icon="folder",
            tooltip="Browse for a folder",
            settings_key=False,
        )

    def pick(self) -> None:
        """Open a directory dialog, load the choice into the field, and record it."""
        edit = self.edit
        if edit is None:
            return
        panel = self._panel
        start = panel.resolved_output_dir() or str(Path.home())
        path = QtWidgets.QFileDialog.getExistingDirectory(
            panel.ui, self.browse_title(), start
        )
        if not path:
            return
        edit.setText(path)
        panel._record_output_dir(path)

    @staticmethod
    def record_recent(edit, value) -> None:
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

    def resolved(self) -> str:
        if self.edit is None:
            return ""
        return self.edit.text().strip()

    def require(self, mode: Optional[str] = None) -> Optional[str]:
        panel = self._panel
        if not panel.REQUIRE_OUTPUT_DIR:
            return ""
        output_dir = panel.resolved_output_dir()
        if output_dir:
            return output_dir

        if mode is not None and mode in panel.TRANSIENT_OUTPUT_MODES:
            # Deliberately NOT written back into the field: a scratch path
            # parked there would read as the user's own choice on the next
            # run, and point it at a directory this one already deleted.
            return ""

        fallback = panel.default_output_dir()
        if fallback:
            self.apply_fallback(
                fallback,
                f"Output Dir not set; using scene/workspace default: "
                f'<a href="action://open?path={fallback}">{fallback}</a>',
            )
            return fallback

        if panel.TEMP_OUTPUT_FALLBACK:
            temp_dir = panel.ensure_bridge_temp_dir(panel.LOG_TAG)
            self.apply_fallback(
                temp_dir,
                "Output Dir not set and no scene/workspace default; using a "
                f"temporary folder (swept {_OutputDirRow.TEMP_MAX_AGE_DAYS:g} days "
                "after its last write): "
                f'<a href="action://open?path={temp_dir}">{temp_dir}</a>',
            )
            return temp_dir

        panel.bridge.logger.error(
            "Output Dir is required and no scene/workspace default could "
            "be resolved. Click '...' next to the Output Dir field to "
            "choose where the export artifacts land."
        )
        if self.edit is not None:
            self.edit.setFocus()
        return None

    def apply_fallback(self, path: str, message: str) -> None:
        """Write a resolved fallback *path* back into the Output Dir field and announce it."""
        if self.edit is not None:
            self.edit.setText(path)
        try:
            self._panel.bridge.logger.info(message)
        except Exception:  # noqa: BLE001
            pass
