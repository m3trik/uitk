# !/usr/bin/python
# coding=utf-8
import re
from typing import Optional, Type
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk


class _Gates:
    """How a widget whose requirement is unmet is presented, behind the
    Switchboard's ``gate`` / ``recheck_gates`` / ``unmet_policy``. Owns the live
    gates; reads the persisted policy from the Switchboard's ``configurable``.
    """

    # ------------------------------------------------------------------ gating
    #: How a widget whose requirement is unmet is presented. ``"hide"`` removes it
    #: (the shipped default -- an unusable tool is clutter), ``"disable"`` greys it
    #: and explains why in the tooltip (discoverable: the user learns the tool
    #: exists and what to install), ``"show"`` leaves it alone (dev/passthrough).
    UNMET_POLICIES = ("hide", "disable", "show")
    UNMET_POLICY_DEFAULT = "hide"
    UNMET_POLICY_KEY = "unmet_policy"

    #: Marker stamped on a widget while a gate holds it: the FULL pre-gate
    #: presentation (tooltip, visibility, enabled), so the restore branch knows
    #: there is something to undo and exactly what to put back. Storing only the
    #: tooltip made `_ungate` assume the other two were on, so a widget that was
    #: already hidden or disabled before its first gate came back visible.
    _GATE_STATE_ATTR = "_gate_restore"

    def __init__(self, sb):
        self._sb = sb
        # Live gates, as ``(widget-ref, availability, reason)`` -- see
        # :meth:`recheck_gates`. Entries hold a weak reference where the binding
        # allows one, so a registered widget is never kept alive by being gated.
        self.registry = []

    @property
    def unmet_policy(self) -> str:
        value = self._sb.configurable.value(
            self.UNMET_POLICY_KEY, self.UNMET_POLICY_DEFAULT
        )
        return value if value in self.UNMET_POLICIES else self.UNMET_POLICY_DEFAULT

    @unmet_policy.setter
    def unmet_policy(self, value) -> None:
        if value not in self.UNMET_POLICIES:
            value = self.UNMET_POLICY_DEFAULT
        self._sb.configurable.setValue(self.UNMET_POLICY_KEY, value)

    def gate(self, widget, available, reason: str = "") -> bool:
        if widget is None:
            return bool(available() if callable(available) else available)

        self._remember_gate(widget, available, reason)
        if callable(available):
            available = available()

        if available:
            self._ungate(widget)
            return True

        # A HARD context exclusion outranks this soft one. ``register_widget``
        # applies ``apply_visibility_policy`` and only then calls ``init_slot``, so
        # a widget hidden for the wrong host (``requires``) or because its nav
        # target doesn't exist (``nav-unresolved``) still reaches the panel's
        # ``*_init`` and gets gated. The two policies are not equal partners:
        # ``requires`` says this host must NEVER show the widget, while the gate
        # only says the app behind it is missing — so the full-presentation write
        # below (``setVisible(policy != "hide")``) would un-hide, under
        # ``disable``/``show``, a button this DCC has no implementation for.
        # Reporting unmet is still correct; overriding the exclusion is not.
        existing = getattr(widget, "hidden_by_policy", None)
        if existing not in (None, "unmet"):
            return False

        # Stash the pre-gate presentation ONCE. A second gate call (the *_init
        # re-fire) must not capture the gated state as if it were the original.
        if not hasattr(widget, self._GATE_STATE_ATTR):
            setattr(widget, self._GATE_STATE_ATTR, self._presentation(widget))
        stashed = getattr(widget, self._GATE_STATE_ATTR)
        original = stashed["tooltip"] or ""

        # Every branch specifies visibility, enabled-ness AND tooltip in full,
        # rather than only the attributes its own policy cares about. Anything
        # left implicit becomes stale when the policy CHANGES between two gate
        # calls -- which it does, because the preference is user-facing and
        # ``*_init`` re-fires on the next show: a partial ``hide`` branch left the
        # widget invisible after a switch to ``show``, and a partial ``disable``
        # branch left its appended reason on the tooltip after a switch to
        # ``hide``. Declaring the whole presentation makes each call idempotent
        # and every transition correct without tracking the previous policy.
        #
        # Declared relative to the STASHED baseline, not to True: a gate may only
        # ever take presentation AWAY. `disable`/`show` writing a bare True would
        # REVEAL a widget its panel had deliberately hidden (and re-enable one it
        # had disabled) -- the app being missing is no reason to show a tool the
        # panel decided against, and the reveal happened at gate time, before
        # `_ungate` ever got the chance to put it back.
        policy = self._sb.unmet_policy
        explanation = reason or "This tool's requirements are not installed."
        widget.hidden_by_policy = "unmet"
        widget.setVisible(stashed["visible"] and policy != "hide")
        widget.setEnabled(stashed["enabled"] and policy != "disable")
        widget.setToolTip(
            f"{original}\n\n{explanation}".strip() if policy == "disable" else original
        )
        return False

    def _remember_gate(self, widget, available, reason: str) -> None:
        """Record (or refresh) *widget*'s gate so :meth:`recheck_gates` can re-apply it.

        Keyed by widget identity, so the ``*_init`` re-fire updates the entry
        rather than growing a duplicate for every panel show.
        """
        import weakref

        try:
            ref = weakref.ref(widget)
        except TypeError:  # not weak-referenceable -- hold it directly

            def ref(_w=widget):
                return _w

        registry = self.registry
        for i, (existing, _, _) in enumerate(registry):
            if existing() is widget:
                registry[i] = (ref, available, reason)
                return
        registry.append((ref, available, reason))

    def recheck_gates(self) -> int:
        live, applied = [], 0
        for ref, available, reason in self.registry:
            widget = ref()
            if widget is None:
                continue
            try:
                self._sb.gate(widget, available, reason)
            except RuntimeError:  # wrapped C++ object already deleted
                continue
            live.append((ref, available, reason))
            applied += 1
        # gate() re-registers each surviving widget, so rebuild from the survivors
        # rather than appending -- otherwise a pruned entry could come back.
        self.registry[:] = live
        return applied

    @staticmethod
    def _presentation(widget) -> dict:
        """The three properties a gate overwrites, as found.

        Visibility is read with ``isVisibleTo(parent)``, never ``isVisible()``:
        a gate runs from ``*_init``, which fires while the panel is still being
        built, so ``isVisible()`` is False for every widget on it and the stash
        would record "hidden" for the whole panel. ``isVisibleTo`` answers the
        question actually being asked -- would this widget show if its parent
        did -- which is the property a gate later has to give back.
        """
        parent = widget.parentWidget() if hasattr(widget, "parentWidget") else None
        try:
            visible = (
                widget.isVisibleTo(parent) if parent is not None else widget.isVisible()
            )
        except (AttributeError, RuntimeError):  # a non-QWidget item, or a dead one
            visible = True
        return {
            "tooltip": widget.toolTip(),
            "visible": visible,
            "enabled": widget.isEnabled(),
        }

    def _ungate(self, widget) -> None:
        """Undo a gate, restoring the widget's pre-gate presentation exactly.

        A no-op on a widget that was never gated, so the available branch of
        :meth:`gate` can call it unconditionally — and, critically, so it never
        clobbers a widget hidden by a DIFFERENT policy (``requires`` /
        ``nav-unresolved``), whose marker it leaves alone.

        Restores from the stash rather than to ``True``: a widget that was
        already hidden or disabled before it was ever gated must come back that
        way, and assuming "on" silently un-hid it the first time its app showed up.
        """
        stashed = getattr(widget, self._GATE_STATE_ATTR, None)
        if stashed is None:
            return
        widget.setToolTip(stashed["tooltip"])
        delattr(widget, self._GATE_STATE_ATTR)
        widget.setEnabled(stashed["enabled"])
        widget.setVisible(stashed["visible"])
        if getattr(widget, "hidden_by_policy", None) == "unmet":
            widget.hidden_by_policy = None


class _Widgets:
    """Widget registration, resolution and dynamic class loading behind the
    Switchboard, and the visibility policy a widget meets at registration. Reads the
    Switchboard (registries, handlers, ``context_tags``) at call time: a host sets
    its context tags after construction.
    """

    def __init__(self, sb):
        self._sb = sb

    def is_registered_ui(self, name: str) -> bool:
        if not name:
            return False
        filenames = self._sb.registry.ui_registry.get("filename") or []
        return name in filenames

    def ui_name_resolves(self, name: str) -> bool:
        if not name:
            return False
        if self._sb.is_registered_ui(name):
            return True
        handler = getattr(getattr(self._sb, "handlers", None), "ui", None)
        can_resolve = getattr(handler, "can_resolve", None)
        try:
            return bool(can_resolve and can_resolve(name))
        except Exception:
            return False

    def resolve_handler_ui(self, name: str) -> Optional[QtWidgets.QWidget]:
        """The UI the active UI handler builds on demand for *name*, or ``None``
        when the handler does not claim it.

        The build half of :meth:`ui_name_resolves`: a name no ``.ui`` file names
        that the handler claims (``can_resolve``) is built by its ``get``, the
        contract ``can_resolve`` states (mayatk's native Maya menus). A name whose
        base is a ``.ui`` file stays the file registry's to answer, so the base
        handler (which claims exactly those) is never asked.

        Raises:
            AttributeError: The handler claims *name* but its ``get`` raised or
                built nothing -- a failed build, named as one and logged as a
                warning (a marking-menu release swallows the error and opens
                nothing). A ``get`` that resolves the name back through the
                switchboard lands here too: the name lookup's own recursion guard
                stops it.
        """
        if not name:
            return None
        if self._sb.is_registered_ui(name.split(self._sb.tag_delimiter)[0]):
            return None
        handler = getattr(getattr(self._sb, "handlers", None), "ui", None)
        can_resolve = getattr(handler, "can_resolve", None)
        try:
            claimed = bool(can_resolve and can_resolve(name))
        except Exception:  # noqa: BLE001 - a failing claim is no claim (ui_name_resolves)
            claimed = False
        if not claimed:
            return None
        owner = type(handler).__name__
        try:
            ui = handler.get(name)
        except Exception as exc:
            self._sb.logger.warning(
                f"[resolve_handler_ui] {owner} claims {name!r} but failed to build "
                f"it: {type(exc).__name__}: {exc}",
                exc_info=True,
            )
            raise AttributeError(
                f"{owner} claims UI {name!r} but failed to build it: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        if ui is None:
            self._sb.logger.warning(
                f"[resolve_handler_ui] {owner} claims {name!r} but built nothing"
            )
            raise AttributeError(f"{owner} claims UI {name!r} but built nothing.")
        return ui

    def menu_button_target_name(self, widget) -> Optional[str]:
        target = widget.target
        if not target:
            return None
        if self._sb.ui_name_resolves(target):
            return target
        submenu = widget.submenu_name()
        if self._sb.is_registered_ui(submenu):
            return submenu
        return None

    def menu_button_target_resolves(self, widget) -> bool:
        return self._sb.menu_button_target_name(widget) is not None

    def apply_visibility_policy(self, widget) -> bool:
        from uitk.managers.field_visibility import FieldVisibility

        requires = widget.property("requires")
        if requires and self._sb.context_tags:
            tags = {t for t in re.split(r"[|,\s]+", str(requires)) if t}
            if tags and not (tags & self._sb.context_tags):
                # As a field, so a container that re-shows its contents
                # wholesale (CollapsableGroup's expand) leaves it hidden.
                FieldVisibility.set_widget_visible(widget, False)
                widget.hidden_by_policy = "requires"
                return True

        from uitk.widgets.menuButton import MenuButton

        if isinstance(widget, MenuButton):
            target = widget.target
            if target and not self._sb.menu_button_target_resolves(widget):
                FieldVisibility.set_widget_visible(widget, False)
                widget.hidden_by_policy = "nav-unresolved"
                return True
        return False

    def resolve_widget_class(
        self, class_name: str
    ) -> Optional[Type[QtWidgets.QWidget]]:
        return self._sb.registry.widget_registry.get(
            classname=class_name, return_field="classobj"
        )

    def resolve_widget(self, class_name: str) -> Optional[QtWidgets.QWidget]:
        """Resolver for dynamically loading registered widgets when accessed.

        Parameters:
            class_name (str): The name of the widget to resolve.

        Returns:
            QWidget or None: The resolved and registered widget, or None if not found.
        """
        self._sb.logger.debug(f"Resolving widget: {class_name}")

        widget_class = self._sb.resolve_widget_class(class_name)
        if not widget_class:
            raise AttributeError(f"Unable to resolve widget class for '{class_name}'.")

        widget = self._sb.register_widget(widget_class)
        self._sb.logger.debug(
            f"Widget class '{widget_class.__name__}' loaded successfully."
        )
        return widget

    def resolve_icon(self, icon_name: str) -> Optional[QtGui.QIcon]:
        """Resolver for dynamically loading registered icons when accessed.

        Parameters:
            icon_name (str): The name of the icon to resolve (without file extension).

        Returns:
            QIcon or None: The resolved icon, or None if not found.
        """
        self._sb.logger.debug(f"Resolving icon: {icon_name}")

        # Try to find the icon file in the registry
        icon_path = self._sb.registry.icon_registry.get(
            filename=icon_name, return_field="filepath"
        )
        if not icon_path:
            self._sb.logger.warning(f"Icon '{icon_name}' not found in registry.")
            return None

        # Create and return QIcon
        icon = QtGui.QIcon(icon_path)
        if icon.isNull():
            self._sb.logger.warning(f"Failed to load icon from path: {icon_path}")
            return None

        self._sb.logger.debug(
            f"Icon '{icon_name}' loaded successfully from: {icon_path}"
        )
        return icon

    def get_icon(self, icon_name: str) -> QtGui.QIcon:
        return getattr(self._sb.registered_icons, icon_name, QtGui.QIcon())

    @classmethod
    def get_widgets_from_ui(
        cls, ui: QtWidgets.QWidget, inc=[], exc="_*", object_names_only=False
    ) -> dict:
        """Find widgets in a qtpy UI object.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            inc (str)(tuple): Widget names to include.
            exc (str)(tuple): Widget names to exclude.
            object_names_only (bool): Only include widgets with object names.

        Returns:
            (dict) {<widget>:'objectName'}
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: {type(ui)}")

        dct = {
            c: c.objectName()
            for c in ui.findChildren(QtWidgets.QWidget, None)
            if (not object_names_only or c.objectName())
        }

        return ptk.filter_dict(dct, inc=inc, exc=exc, keys=True, values=True)

    @staticmethod
    def widget_is_alive(instance) -> bool:
        """Probe a Qt object to detect a deleted C++ underlying.

        Catches both ``RuntimeError`` (the standard PySide signal that the
        wrapped C++ object has been deleted) and ``AttributeError`` (which some
        shiboken builds raise for partially-disposed wrappers). Anything else is
        unexpected and propagates. Shared switchboard liveness probe — used by
        the deferred-widget revival path and the editor cache.
        """
        try:
            instance.objectName()
            return True
        except (RuntimeError, AttributeError):
            return False

    @staticmethod
    def get_widget_from_ui(
        ui: QtWidgets.QWidget, object_name: str
    ) -> QtWidgets.QWidget:
        """Find a widget in a qtpy UI object by its object name.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            object_name (str): The object name of the widget to find.

        Returns:
            (QWidget)(None) The widget object if it's found, or None if it's not found.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: {type(ui)}")

        return ui.findChild(QtWidgets.QWidget, object_name)

    def register_widget(self, widget):
        if widget.__name__ not in self._sb.registered_widgets.keys():
            self._sb.registered_widgets[widget.__name__] = widget
            return widget

    def get_widget(self, name, ui=None):
        if ui is None or isinstance(ui, str):
            ui = self._sb.get_ui(ui)

        return next((w for w in ui.widgets if w.objectName() == name), None)

    def get_widget_from_slot(self, method):
        if not method:
            return None

        return next(
            iter(
                w
                for u in self._sb.loaded_ui.values()
                for w in u.widgets
                if w.get_slot() == method
            ),
            None,
        )

    def is_widget(self, obj):
        try:
            return issubclass(obj, QtWidgets.QWidget)
        except TypeError:
            return issubclass(obj.__class__, QtWidgets.QWidget)

    @staticmethod
    def get_parent_widgets(widget, object_names=False):
        parentWidgets = []
        w = widget
        while w:
            parentWidgets.append(w)
            w = w.parentWidget()
        if object_names:
            return [w.objectName() for w in parentWidgets]
        return parentWidgets

    @staticmethod
    def get_all_windows(name=None):
        return [
            w
            for w in QtWidgets.QApplication.allWindows()
            if (name is None) or (w.objectName() == name)
        ]

    @staticmethod
    def get_all_widgets(name=None):
        # isinstance: allWidgets() can answer a widget with a stale wrapper of
        # another type -- a layout item is no QObject, so shiboken never learns
        # C++ deleted it, and a widget that reuses its address comes back as the
        # old QWidgetItem (Linux CI, PySide6 6.10). It can't be asked anything.
        return [
            w
            for w in QtWidgets.QApplication.allWidgets()
            if isinstance(w, QtWidgets.QWidget)
            and ((name is None) or (w.objectName() == name))
        ]

    @staticmethod
    def get_widget_at(pos, top_widget_only=True):
        w = QtWidgets.QApplication.widgetAt(pos)
        if top_widget_only:
            return w

        widgets = []
        while w:
            widgets.append(w)

            w.setAttribute(
                QtCore.Qt.WA_TransparentForMouseEvents
            )  # make widget invisible to further enquiries.
            w = QtWidgets.QApplication.widgetAt(pos)

        for w in widgets:  # restore attribute.
            w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)

        return widgets


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    ...

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
