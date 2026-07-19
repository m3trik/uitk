# !/usr/bin/python
# coding=utf-8
"""Deprecated shim — this module moved to :mod:`uitk.managers.registry_manager`.

``FileManager`` is now :class:`~uitk.managers.registry_manager.RegistryManager`
and ``FileContainer`` is now
:class:`~uitk.managers.registry_manager.FileRegistry`.  Update imports; this
alias module will be removed in a future release.
"""
import warnings

from uitk.managers.registry_manager import (  # noqa: F401
    FileRegistry as FileContainer,
    RegistryManager as FileManager,
)

__all__ = ["FileContainer", "FileManager"]

warnings.warn(
    "uitk.file_manager is deprecated; use uitk.managers.registry_manager "
    "(FileManager -> RegistryManager, FileContainer -> FileRegistry).",
    DeprecationWarning,
    stacklevel=2,
)
