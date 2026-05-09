# !/usr/bin/python
# coding=utf-8
"""Switchboard delegate that loads UIs at runtime via QUiLoader.

Alternative to :mod:`uitk.loaders.compiled`. Both delegates implement the
same Switchboard-facing contract:

- ``load(file)``              builds a widget tree from a .ui XML
- ``read_ui_tags(path)``      returns uitk_tags from the .ui XML
- ``on_tags_written(path)``   notifies the loader that .ui content changed

Trade-offs vs. CompiledLoader:

- **No subprocess.** ``QtUiTools.QUiLoader`` reads the .ui XML directly
  and constructs the widget tree in C++ — no ``pyside6-uic`` invocation,
  no Python compile step, no _ui.py artifact written or imported.
- **No on-disk artifact.** Every load re-parses the .ui. The metadata
  cache below collapses repeated loads of the same unchanged file to a
  single XML read; the heavy widget-tree construction is delegated to
  Qt's C++ implementation each time.
- **Custom widget promotion** goes through ``QUiLoader.registerCustomWidget``
  (each loader instance keeps its own QUiLoader to avoid polluting any
  other loader sharing the application).
- **No header_resolver path.** Custom widgets must be importable by their
  resolved class — the same registry the CompiledLoader feeds is reused.
- **Cache freshness uses mtime, not content-hash.** Cheaper to check
  (one stat call vs. reading the whole file), and adequate for a
  Qt-Designer + filesystem-watcher workflow on NTFS / ext4 (sub-µs
  resolution). On filesystems with coarser mtime resolution (FAT32:
  2s, some network shares: 1s) two writes within the resolution window
  can collide; ``on_tags_written`` should be called after any
  programmatic write to invalidate explicitly. The CompiledLoader's
  hash-based check handles this case; pick that loader if your
  workflow regularly mutates .ui files faster than mtime resolution.
- **Not thread-safe.** ``_metadata_cache`` is a plain dict mutated
  without a lock. Qt UI code is single-threaded by convention (the GUI
  thread), and Switchboard's call sites all run there. If a future
  caller needs to read tags from a worker thread, wrap it in a
  ``QtCore.QMutex`` or call from the main thread.

Switchboard chooses between the two delegates via its ``loader`` kwarg.
"""
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional

from qtpy import QtUiTools, QtWidgets
import pythontk as ptk

from uitk import compile as compile_mod


class RuntimeLoader:
    """Switchboard delegate that loads UIs at runtime via QUiLoader."""

    def __init__(self, switchboard):
        self.sb = switchboard
        # One QUiLoader instance per RuntimeLoader so registerCustomWidget
        # state is scoped to this Switchboard and doesn't leak into any
        # other loader sharing the application.
        self._uic = QtUiTools.QUiLoader()
        # File-path → (mtime, metadata-dict) so repeated loads of the same
        # unchanged .ui collapse to a single XML parse.
        self._metadata_cache: Dict[str, tuple] = {}
        # Class names already registered with self._uic. registerCustomWidget
        # is idempotent on the Qt side, but each call still crosses the
        # Python→C++ boundary; skipping repeats saves N×M dispatches when
        # many UIs share a small set of customwidgets (typical case).
        self._registered_classes: set = set()

    # ── Public delegate API ─────────────────────────────────────────────

    def load(self, ui_file: str) -> QtWidgets.QWidget:
        """Build a widget tree from a .ui path via QUiLoader.

        Custom widgets named in the .ui's ``<customwidgets>`` block are
        resolved against the Switchboard's widget_registry, registered
        with this loader's QUiLoader instance, and registered with the
        Switchboard so downstream slot-wiring sees them.
        """
        metadata = self._get_metadata(ui_file)
        for class_name, _header in metadata["customwidgets"]:
            self._ensure_widget_registered(class_name)

        loaded = self._uic.load(ui_file)
        if loaded is None:
            err = self._uic.errorString() if hasattr(self._uic, "errorString") else ""
            detail = f": {err}" if err else ""
            raise RuntimeError(
                f"QUiLoader returned None for {ui_file}{detail}. The file "
                "may be malformed XML or reference an unregistered custom widget."
            )
        name = ptk.format_path(ui_file, "name")
        self.sb.logger.debug(f"[{name}] UI loaded via QUiLoader from {ui_file}")
        return loaded

    def read_ui_tags(self, ui_path: str) -> set:
        """Return the uitk_tags set for a .ui file via direct XML parse.

        Reads from the .ui XML; tolerant of malformed/missing files
        (returns an empty set on failure).
        """
        if not ui_path:
            return set()
        try:
            return set(self._get_metadata(ui_path)["uitk_tags"])
        except Exception:
            return set()

    def on_tags_written(self, ui_path: str) -> None:
        """Invalidate cached metadata after .ui content has changed.

        ``compile_mod.extract_metadata`` runs again on the next access.
        QUiLoader reads the .ui fresh from disk on every ``load`` call
        anyway, so widget-tree construction needs no special invalidation.
        """
        self._invalidate_cache(ui_path)

    # ── Internals ───────────────────────────────────────────────────────

    def _ensure_widget_registered(self, class_name: str) -> None:
        if class_name in self._registered_classes:
            return
        if class_name in self.sb.registered_widgets.keys():
            cls = self.sb.registered_widgets[class_name]
        else:
            cls = self.sb.registry.widget_registry.get(
                classname=class_name, return_field="classobj"
            )
            if cls is None:
                # Mirror CompiledLoader behavior: unknown classes surface
                # as the QUiLoader fallback (a plain QWidget) rather than
                # blowing up. The Switchboard logger captures the gap so
                # registry holes are diagnosable without aborting the load.
                self.sb.logger.debug(
                    f"[runtime_loader] unknown custom widget '{class_name}' — "
                    "QUiLoader will fall back to QWidget"
                )
                return
            self.sb.register_widget(cls)
        self._uic.registerCustomWidget(cls)
        self._registered_classes.add(class_name)

    def _cache_key(self, ui_path: str) -> str:
        return str(Path(ui_path).resolve())

    def _get_metadata(self, ui_path: str) -> dict:
        """Return cached metadata if .ui mtime is unchanged; otherwise reparse."""
        key = self._cache_key(ui_path)
        try:
            mtime = os.path.getmtime(ui_path)
        except OSError:
            mtime = None
        cached = self._metadata_cache.get(key)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        try:
            metadata = compile_mod.extract_metadata(ui_path)
        except (ET.ParseError, OSError):
            # Tolerant of partial/corrupt reads (e.g. cloud-sync mid-write).
            metadata = {
                "base_class": "QWidget",
                "form_class": "Form",
                "customwidgets": [],
                "uitk_tags": [],
            }
        self._metadata_cache[key] = (mtime, metadata)
        return metadata

    def _invalidate_cache(self, ui_path: str) -> None:
        self._metadata_cache.pop(self._cache_key(ui_path), None)
