# !/usr/bin/python
# coding=utf-8
"""Qt Designer integration for uitk's custom widgets.

Exposes :class:`~uitk.designer._designer.DesignerPlugin` — the registrar that
publishes uitk widgets to Qt Designer's widget box so they can be dragged onto a
form directly (with live rendering and their own properties in the property
editor) rather than dropped as a stock Qt widget and promoted after the fact.

Access the class from the package root::

    from uitk import DesignerPlugin

Launch a Designer that sees the widgets::

    python -m uitk.designer

``register_uitk_widgets.py`` is the entry point Qt Designer itself loads: the
PySide6 Designer plugin scans every directory named in ``PYSIDE_DESIGNER_PLUGINS``
for files matching ``register*.py`` and imports them. Nothing else in this
package is imported by Designer.
"""

# Lazy-loaded via parent package - no explicit imports needed
