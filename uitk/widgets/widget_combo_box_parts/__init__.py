# !/usr/bin/python
# coding=utf-8
"""The collaborators :class:`~uitk.widgets.widgetComboBox.WidgetComboBox` is built from.

``WidgetComboBox`` stays defined in ``uitk/widgets/widgetComboBox.py`` --
``.ui`` headers and every consumer name that path, so it is frozen -- and holds
one of each of these, every one owning its own state and holding the combo:

* ``_actions`` -- ``_ActionsNamespace`` (the public ``combo.actions``) and
  ``_ActionsSection``, the separator and button grid it renders below the rows.
* ``_arrow_affordance`` -- ``_ArrowAffordance``: the optional chevron or icon
  drawn after the displayed text.
* ``_widget_defaults`` -- ``_WidgetDefaults``: each embedded widget's value as
  added, and the "Restore Defaults" action that puts them back.

Internal: nothing here is registered at the package root; import ``WidgetComboBox``.
"""
