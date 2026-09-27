# !/usr/bin/python
# coding=utf-8
"""The Output Dir row of a bridge panel: one part of :class:`~uitk.bridge.slots.BridgeSlotsBase`.

The optional "Output Dir" field above the parameters, its option-box buttons
(persisted recent values + a directory browse), and the chain a send resolves it
through: the typed value, a transient mode's own scratch, the host's
``default_output_dir``, a self-cleaning session temp dir, then an error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from qtpy import QtCore, QtWidgets


class _OutputDirMixin(object):
    """The Output Dir row and its resolution chain.

    Reads the composed panel's ``ui`` (``grp_process`` / ``cmb000``),
    ``bridge.logger``, :attr:`LOG_TAG` and :attr:`LABEL_MIN_WIDTH`. The temp-dir
    registry is a class attr, so every bridge panel in the process shares one.
    """

    # One temp Output Dir per bridge tag per host process, removed at process exit.
    # Values are ``(TempArtifacts store, path)`` -- the store so a killed host's
    # leftovers have a swept namespace to be reclaimed from, the path so reading
    # it back needs nothing private.
    _BRIDGE_TEMP_DIRS: Dict[str, Tuple[Any, str]] = {}

    @staticmethod
    def _remove_bridge_temp_dir(key: str) -> None:
        """Remove the temp Output Dir created for *key* (best-effort).

        Exposed for tests and for a host that wants to reclaim early; the
        ordinary path is the store's own ``atexit``.
        """
        entry = _OutputDirMixin._BRIDGE_TEMP_DIRS.pop(key, None)
        if entry is not None:
            entry[0].cleanup(force=True)

    # Whether the panel exposes a required "Output Dir" row above the
    # parameter group. Disable for bridges whose roundtrip is in-place
    # (rizom transfers UVs back onto the originals without writing
    # artifacts the user needs to locate) -- the row is then never built,
    # and ``require_output_dir()`` returns ``""`` so subclasses can call
    # it unconditionally without a None guard.
    REQUIRE_OUTPUT_DIR: bool = True

    # When True, ``require_output_dir()`` falls back to a self-cleaning temp
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
    OUTPUT_DIR_PLACEHOLDER = "(defaults to scene dir / workspace)"
    OUTPUT_DIR_TOOLTIP = (
        "Directory where the export artifacts (FBX, manifest, rendered\n"
        "scripts, baked maps) all land. Leave blank to default to the\n"
        "current scene's directory (or the active workspace if the\n"
        "scene hasn't been saved)."
    )

    def default_output_dir(self) -> str:
        """Hook: fallback path when the user leaves Output Dir blank.

        Returns the empty string by default. DCC-specific subclasses
        override -- e.g. ``MayaBridgeSlotsBase`` returns
        ``EnvUtils.default_artifact_dir()`` (scene dir, then workspace).
        """
        return ""

    @staticmethod
    def ensure_bridge_temp_dir(tag: str) -> str:
        """Create (once per host process) and return a temp Output Dir for *tag*.

        Backs :attr:`TEMP_OUTPUT_FALLBACK`: the last-resort Output Dir when neither the
        user's value nor the DCC scene/workspace default resolves (e.g. an unsaved scene with no
        workspace), so a hand-off bridge can still export without forcing the user to pick a path. The
        directory lives for the whole session (long enough for the launched external app to read the
        exported files) and is removed at process exit. Reused across sends for the same *tag*.

        Allocated through ``ptk.TempArtifacts`` (``session`` policy) rather than a hand-rolled
        ``tempfile.gettempdir()`` join: the exit hook alone is not cleanup here. DCC hosts are
        routinely killed, and an ``atexit`` that never fires used to leave the directory behind
        with nothing left to reclaim it — one per killed session, forever. Every allocation now
        joins a swept prefix namespace, so the worst case is delayed collection. The unique tag
        also retires the PID that was keeping concurrent DCCs off a shared path."""
        import pythontk as ptk

        key = tag or "bridge"
        entry = _OutputDirMixin._BRIDGE_TEMP_DIRS.get(key)
        if entry is None:
            store = ptk.TempArtifacts(f"uitk_bridge_{key}", policy="session")
            entry = (store, store.dir_path())
            _OutputDirMixin._BRIDGE_TEMP_DIRS[key] = entry
        return entry[1]

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
        as a top-level widget, whose ``OptionBoxContainer.showEvent`` schedules an
        ``_adjust_to_content`` that collapses + absolutely-positions the container
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
        # Set before the row is registered: ``register_widget`` only defaults
        # ``restore_state`` to True when the attribute is ABSENT, so this is what
        # decides whether the field is saved/restored across sessions at all.
        edit.restore_state = self.OUTPUT_DIR_PERSISTS
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
        4. When :attr:`TEMP_OUTPUT_FALLBACK` is set, a self-cleaning temp
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
        if not self.REQUIRE_OUTPUT_DIR:
            return ""
        output_dir = self.resolved_output_dir()
        if output_dir:
            return output_dir

        if mode is not None and mode in self.TRANSIENT_OUTPUT_MODES:
            # Deliberately NOT written back into the field: a scratch path
            # parked there would read as the user's own choice on the next
            # run, and point it at a directory this one already deleted.
            return ""

        fallback = self.default_output_dir()
        if fallback:
            self._apply_output_dir_fallback(
                fallback,
                f"Output Dir not set; using scene/workspace default: "
                f'<a href="action://open?path={fallback}">{fallback}</a>',
            )
            return fallback

        if self.TEMP_OUTPUT_FALLBACK:
            temp_dir = self.ensure_bridge_temp_dir(self.LOG_TAG)
            self._apply_output_dir_fallback(
                temp_dir,
                "Output Dir not set and no scene/workspace default; using a "
                "temporary folder (removed when this session exits): "
                f'<a href="action://open?path={temp_dir}">{temp_dir}</a>',
            )
            return temp_dir

        self.bridge.logger.error(
            "Output Dir is required and no scene/workspace default could "
            "be resolved. Click '...' next to the Output Dir field to "
            "choose where the export artifacts land."
        )
        if self._output_dir_edit is not None:
            self._output_dir_edit.setFocus()
        return None

    def _apply_output_dir_fallback(self, path: str, message: str) -> None:
        """Write a resolved fallback *path* back into the Output Dir field and announce it."""
        if self._output_dir_edit is not None:
            self._output_dir_edit.setText(path)
        try:
            self.bridge.logger.info(message)
        except Exception:  # noqa: BLE001
            pass
