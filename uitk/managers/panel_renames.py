# !/usr/bin/python
# coding=utf-8
"""Carry a renamed panel's saved values to the panel that took its name.

A panel's user state lives under its name: its host-namespaced settings branch
(``<panel><host suffix>``, ``Switchboard.add_ui``) holds its widget states
(``<objectName>/<signal>``, ``StateManager``), its own settings keys and the
shortcut overrides on its slots (``shortcuts<host suffix>.<Slots class>.<slot>``);
its window-persistence override lives with the UI handler. A panel renamed, or
merged into another, would start from defaults: :meth:`PanelRenames.carry` copies
each former panel's values into the new one first, once per host.
"""

from typing import Callable, Dict, List, Mapping, Optional, Sequence

from uitk.managers.shortcut_manager import ShortcutManager
from uitk.managers.state_manager import StateManager

#: ``{panel: {former panel: {former widget name: its name now}}}``.
RenamedFrom = Mapping[str, Mapping[str, Mapping[str, str]]]


class PanelRenames(object):
    """The one-shot carry of renamed panels' saved values (module docstring)."""

    #: The ``configurable`` key (host-namespaced) listing the former panels whose
    #: values this host has carried.
    CARRIED_KEY = "renamed_panels_carried"

    @classmethod
    def carry(
        cls,
        switchboard,
        renamed_from: RenamedFrom,
        slot_class_names: Optional[Callable[[str], Sequence[str]]] = None,
    ) -> List[str]:
        """Copy each former panel's saved values into the panel that took its name.

        Run it as the host registers its panels, before any of them loads. Per
        former panel: its settings branch is copied key by key to the new
        panel's, a renamed widget's keys under its name now and a shortcut
        override under the new panel's Slots class (the slot renamed as its
        widget is; an override under the class's current spelling wins over one
        under an older one), and its window-persistence override when the new
        panel has none. A value the new panel already holds wins. The former
        branch is left in place (as the shortcut host-namespacing migration
        leaves its sources), and the host's ``configurable`` store records each
        former panel as soon as it is carried, so a value the user clears
        afterwards stays cleared and one panel that fails is retried alone.
        Best-effort: a store that cannot be read leaves the panels on their
        defaults, logged at debug, and never raises into a launch.

        Parameters:
            switchboard: The host's switchboard: its ``settings`` (the root
                ``SettingsManager``), ``configurable``, ``context_tags``,
                ``get_slot_class_names`` and, when a UI handler is registered,
                ``handlers.ui`` (``persistence_override`` /
                ``set_persistence_override``).
            renamed_from: ``{panel: {former panel: {former widget name: its
                name now}}}``; a widget kept by name needs no entry.
            slot_class_names: ``(panel) -> [Slots class names]``, the panel's
                class first (older spellings after it, carried too). Default:
                ``switchboard.get_slot_class_names``.

        Returns:
            list: The former panels carried by this call.
        """
        names = slot_class_names or switchboard.get_slot_class_names
        try:
            suffix = ShortcutManager.host_namespace_suffix(
                getattr(switchboard, "context_tags", None)
            )
            marker = cls.CARRIED_KEY + suffix
            carried = list(switchboard.configurable.value(marker) or [])
        except Exception as error:  # noqa: BLE001 - a launch never fails on it
            cls._debug(switchboard, f"renamed panels not carried: {error}")
            return []
        done = []
        for panel, formers in renamed_from.items():
            for former, widgets in formers.items():
                if former in carried:
                    continue
                try:
                    cls._carry_panel(switchboard, suffix, panel, former, widgets, names)
                    carried.append(former)
                    switchboard.configurable.setValue(marker, carried)
                except Exception as error:  # noqa: BLE001 - retried next launch
                    cls._debug(switchboard, f"{former} not carried: {error}")
                    continue
                done.append(former)
        return done

    @staticmethod
    def _debug(switchboard, message: str) -> None:
        logger = getattr(switchboard, "logger", None)
        if logger is not None:
            logger.debug(f"[PanelRenames] {message}")

    @classmethod
    def _carry_panel(cls, switchboard, suffix, panel, former, widgets, names) -> None:
        """Copy *former*'s branch and persistence override into *panel*'s."""
        source = switchboard.settings.branch(former + suffix)
        target = switchboard.settings.branch(panel + suffix)
        new_class = list(names(panel))[0]
        former_classes = list(names(former))
        classes = dict.fromkeys(former_classes, new_class)
        older = set(former_classes[1:])
        # An override under an older class spelling yields to one under the
        # current spelling: copied last, it finds the slot held already.
        for key in sorted(source.keys(), key=lambda k: cls._class_of(k) in older):
            new_key = cls.renamed_key(key, widgets, classes)
            if target.value(new_key) is None:
                target.setValue(new_key, source.value(key))
        handlers = getattr(switchboard, "handlers", None)
        handler = getattr(handlers, "ui", None)
        if handler is not None and handler.persistence_override(panel) is None:
            mode = handler.persistence_override(former)
            if mode is not None:
                handler.set_persistence_override(panel, mode)

    @staticmethod
    def _class_of(key: str) -> str:
        """The Slots class a shortcut-override key names ('' for any other key)."""
        parts = key.split(".")
        return parts[1] if len(parts) >= 3 and parts[0].startswith("shortcuts") else ""

    @staticmethod
    def renamed_key(
        key: str, widgets: Mapping[str, str], classes: Dict[str, str]
    ) -> str:
        """*key* as the new panel stores it.

        Parameters:
            key: A key of the former panel's branch.
            widgets: ``{former widget name: its name now}``.
            classes: ``{former Slots class name: the new panel's}``.

        Returns:
            str: A widget state (``<objectName>/<signal>``, its saved default
            ``defaults/...``) under the widget's name now
            (``StateManager.rename_widget_key``); a shortcut override
            ``shortcuts<ns>.<class>.<slot>[.<twin>]`` under the new class and the
            slot's widget name now; any other key as it is.
        """
        if "/" in key:
            return StateManager.rename_widget_key(key, widgets)
        parts = key.split(".")
        if len(parts) >= 3 and parts[0].startswith("shortcuts") and parts[1] in classes:
            parts[1] = classes[parts[1]]
            parts[2] = widgets.get(parts[2], parts[2])
            return ".".join(parts)
        return key


# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
