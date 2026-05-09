# !/usr/bin/python
# coding=utf-8
"""Switchboard delegate that loads UIs via compiled _ui.py modules.

Alternative to :mod:`uitk.loaders.runtime`. Pairs with :mod:`uitk.compile`
for the build/CLI side.


The Switchboard instantiates one of these unconditionally and dispatches
three operations through it:

- ``load(file)``              builds a widget tree from a .ui via its _ui.py
- ``read_ui_tags(path)``      returns uitk_tags from the .ui XML directly
- ``on_tags_written(path)``   regenerates _ui.py after save_ui_tags

The .ui remains the canonical source-of-truth; this loader auto-compiles a
fresh _ui.py whenever one is missing or its embedded hash diverges from the
.ui contents.
"""
import hashlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict

import pythontk as ptk
from qtpy import QtWidgets

from uitk import compile as compile_mod


def _module_name_for(py_path: Path) -> str:
    """Stable module name keyed on the file's resolved path."""
    digest = hashlib.md5(str(py_path.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"_uitk_compiled_{digest}"


def _import_compiled_module(py_path: Path):
    """Import a _ui.py file as a uniquely-named module, returning the module.

    Re-executes the module on every call so a regenerated _ui.py is picked up
    immediately without an importlib.reload. On exec failure (e.g. a custom
    widget header path that does not resolve), the half-broken module is
    removed from sys.modules so the next attempt starts clean.
    """
    py_path = Path(py_path)
    mod_name = _module_name_for(py_path)
    spec = importlib.util.spec_from_file_location(mod_name, str(py_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {py_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(mod_name, None)
        raise
    return module


def _resolve_qt_class(name: str):
    """Resolve a Qt class name like 'QMainWindow' to the QtWidgets class.

    Raises AttributeError for unknown names so a corrupted ``__base_class__``
    surfaces as a clear error rather than as a downstream call to a method
    that ``QWidget`` does not have (e.g. ``setCentralWidget``).
    """
    cls = getattr(QtWidgets, name, None)
    if cls is None:
        raise AttributeError(
            f"Unknown form base class '{name}' — not in QtWidgets"
        )
    return cls


def _find_form_class(module):
    """Find the Ui_<Name> class inside a compiled _ui.py module."""
    target = getattr(module, "__form_class__", None)
    if target:
        cls = getattr(module, f"Ui_{target}", None)
        if cls is not None:
            return cls
    for name in dir(module):
        if name.startswith("Ui_"):
            cls = getattr(module, name)
            if isinstance(cls, type):
                return cls
    raise AttributeError(
        f"No Ui_* class found in compiled module {getattr(module, '__file__', '?')}"
    )


class CompiledLoader:
    """Switchboard delegate that loads UIs via compiled _ui.py modules."""

    def __init__(self, switchboard):
        self.sb = switchboard
        # ui_path → (ui_mtime, py_path, module). Set after a successful
        # load so subsequent loads of the same .ui (with unchanged mtime)
        # skip both ``ensure_compiled`` (freshness re-check) and
        # ``_import_compiled_module`` (Python module re-exec). The module
        # is reused; only ``Ui_*().setupUi(form)`` runs per load to build
        # a fresh widget tree.
        self._load_cache: Dict[str, tuple] = {}
        # Class names already promoted to Switchboard.registered_widgets
        # via this loader. registered_widgets membership is the source of
        # truth, but caching the answer collapses the per-load
        # ``in self.sb.registered_widgets.keys()`` membership scan into
        # a single set check when many UIs share the same customwidgets.
        self._registered_classes: set = set()

    def _resolve_header(self, class_name: str, original_header: str):
        """Look up a customwidget's canonical Python module via the widget registry.

        Returns ``cls.__module__`` for the registered class, or None if the
        class isn't registered. Passed to compile_ui as the
        ``header_resolver`` so legacy .ui files with malformed C++-style
        ``<header>`` paths (e.g. ``widgets.foo.h``) compile to working
        Python imports.
        """
        cls = self.sb.registry.widget_registry.get(
            classname=class_name, return_field="classobj"
        )
        if cls is None:
            return None
        return getattr(cls, "__module__", None)

    def read_ui_tags(self, ui_path: str) -> set:
        """Return the uitk_tags set for a .ui file via direct XML extraction.

        Reads from the .ui XML rather than from a compiled _ui.py header so
        registration is tolerant of malformed or stub fixtures and never
        spawns a uic subprocess just to enumerate tags. The compiled module
        is only built when a UI is actually loaded.
        """
        if not ui_path:
            return set()
        try:
            return set(compile_mod.extract_metadata(ui_path)["uitk_tags"])
        except Exception:
            return set()

    def load(self, ui_file: str):
        """Build a widget tree from a .ui path via its compiled _ui.py module.

        If an existing _ui.py (e.g. one previously emitted by raw pyside6-uic
        with malformed C++-style <header> imports) fails to import, the file
        is force-regenerated through our resolver and the import is retried
        once. Persistent ImportError after regen surfaces to the caller.

        Repeat loads of the same .ui in this Switchboard session reuse the
        already-imported module (via ``_load_cache``) — only setupUi runs
        per load to build a fresh widget tree. Cache invalidates when the
        .ui's mtime changes.
        """
        ui_path = Path(ui_file)
        cache_key = str(ui_path.resolve())
        try:
            ui_mtime = os.path.getmtime(ui_path)
        except OSError:
            ui_mtime = None

        cached = self._load_cache.get(cache_key)
        if cached is not None and cached[0] == ui_mtime:
            _, py_path, module = cached
        else:
            py_path = compile_mod.ensure_compiled(
                ui_path, header_resolver=self._resolve_header
            )
            try:
                module = _import_compiled_module(py_path)
            except ImportError:
                self.sb.logger.info(
                    f"[{py_path.name}] import failed; regenerating with resolver"
                )
                compile_mod.compile_ui(
                    ui_path, py_path, header_resolver=self._resolve_header
                )
                module = _import_compiled_module(py_path)
            self._load_cache[cache_key] = (ui_mtime, py_path, module)

        for cls_name, _header in getattr(module, "__customwidgets__", []):
            if cls_name in self._registered_classes:
                continue
            if cls_name not in self.sb.registered_widgets.keys():
                widget_class_info = self.sb.registry.widget_registry.get(
                    classname=cls_name, return_field="classobj"
                )
                if widget_class_info:
                    self.sb.register_widget(widget_class_info)
            self._registered_classes.add(cls_name)

        base_cls = _resolve_qt_class(getattr(module, "__base_class__", "QWidget"))
        form = base_cls()

        ui_cls = _find_form_class(module)
        ui_cls().setupUi(form)

        name = ptk.format_path(ui_file, "name")
        self.sb.logger.debug(
            f"[{name}] UI loaded via compiled module {py_path.name}"
        )
        return form

    def on_tags_written(self, ui_path: str) -> None:
        """Regenerate _ui.py after the .ui has been written with new tags.

        Invalidates the load cache so the next ``load(ui_path)`` re-imports
        the regenerated module instead of reusing the stale one.
        """
        compile_mod.compile_ui(ui_path, header_resolver=self._resolve_header)
        self._load_cache.pop(str(Path(ui_path).resolve()), None)
