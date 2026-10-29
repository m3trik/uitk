# !/usr/bin/python
# coding=utf-8
"""A table's context menu -- one part of
:class:`~uitk.widgets.tableWidget.TableWidget` (see ``table_widget_parts``)."""

import inspect
from typing import TYPE_CHECKING, Any, Dict

from qtpy import QtWidgets

if TYPE_CHECKING:
    from uitk.widgets.tableWidget import TableWidget


class _ContextMenu:
    """A :class:`TableWidget`'s context menu: opening it, and the actions
    registered to receive the selection when picked
    (:meth:`TableWidget.register_menu_action`).

    Owns that registry and whether the menu's dispatch is hooked up yet.
    """

    def __init__(self, table: "TableWidget"):
        self._table = table
        self.registry: Dict[str, Dict[str, Any]] = {}
        self._dispatch_connected = False

    def show_at(self, position):
        """Show the context menu at the given position."""
        table = self._table
        # Only show if menu exists and has items (avoid creating empty menu)
        if table.has_menu and table.menu.contains_items:
            table.context_menu_about_to_show.emit()
            # Set the position before showing
            global_pos = table.mapToGlobal(position)
            table.menu.position = global_pos
            table.menu.show()

    def register(
        self,
        object_name,
        handler,
        columns,
        include_current,
        allow_empty,
        transform,
        pass_widget,
    ):
        if not object_name:
            raise ValueError("object_name is required")
        if not callable(handler):
            raise TypeError("handler must be callable")

        normalized = self._table._normalize_column_targets(columns)
        self.registry[object_name] = {
            "handler": handler,
            "columns": normalized,
            "include_current": bool(include_current),
            "allow_empty": bool(allow_empty),
            "transform": transform,
            "pass_widget": bool(pass_widget),
        }
        self._ensure_dispatch_hook()

    def unregister(self, object_name: str):
        self.registry.pop(object_name, None)

    def _ensure_dispatch_hook(self):
        if self._dispatch_connected:
            return
        menu = getattr(self._table, "menu", None)
        signal = getattr(menu, "on_item_interacted", None)
        if signal is None:
            return
        # A method of the table, not of this object: the menu may outlive the
        # table, and Qt drops the connection only with a destroyed receiver.
        signal.connect(self._table._dispatch_registered_menu_action)
        self._dispatch_connected = True

    def dispatch(self, widget: QtWidgets.QWidget):
        if widget is None:
            return
        object_name = widget.objectName()
        if not object_name:
            return
        payload = self.registry.get(object_name)
        if not payload:
            return

        selections = self._table._build_selection_payload(
            payload["columns"], payload["include_current"]
        )
        if not selections and not payload["allow_empty"]:
            return

        data = selections
        transform = payload.get("transform")
        if transform:
            data = transform(selections)

        handler = payload["handler"]

        def _call_handler_with_compatible_arity(func, argv):
            """Call handler with as many args as it can accept.

            Supports legacy handlers that take no args (besides bound self),
            and newer handlers that accept (data) or (data, widget).
            """

            try:
                sig = inspect.signature(func)
            except (TypeError, ValueError):
                return func(*argv)

            params = list(sig.parameters.values())

            # If this is an unbound method/function, ignore explicit 'self'
            if params and params[0].name == "self":
                params = params[1:]

            has_var_positional = any(
                p.kind == inspect.Parameter.VAR_POSITIONAL for p in params
            )
            if has_var_positional:
                return func(*argv)

            positional = [
                p
                for p in params
                if p.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            max_positional = len(positional)

            # Try to pass as much as possible, but degrade gracefully.
            if len(argv) >= 2:
                if max_positional >= 2:
                    return func(argv[0], argv[1])
                if max_positional >= 1:
                    return func(argv[0])
                return func()

            if len(argv) == 1:
                if max_positional >= 1:
                    return func(argv[0])
                return func()

            return func()

        if payload["pass_widget"]:
            _call_handler_with_compatible_arity(handler, (data, widget))
        else:
            _call_handler_with_compatible_arity(handler, (data,))
