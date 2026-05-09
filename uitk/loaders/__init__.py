# !/usr/bin/python
# coding=utf-8
"""Switchboard UI loader delegates.

Two implementations of the same three-method contract — pick via
``Switchboard(loader=...)``:

- :class:`uitk.loaders.runtime.RuntimeLoader` (default) —
  ``QtUiTools.QUiLoader`` reads .ui XML directly. No on-disk artifact.
- :class:`uitk.loaders.compiled.CompiledLoader` — pyside6-uic emits a
  hashed ``_ui.py`` per .ui; loaded through Python imports. Pairs with
  :mod:`uitk.compile` for the build/CLI side.

Both expose: ``load(file)``, ``read_ui_tags(path)``, ``on_tags_written(path)``.
"""
from uitk.loaders.compiled import CompiledLoader
from uitk.loaders.runtime import RuntimeLoader

__all__ = ["CompiledLoader", "RuntimeLoader"]
