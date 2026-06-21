# !/usr/bin/python
# coding=utf-8
import re
from typing import Optional, Type
from qtpy import QtWidgets, QtCore, QtGui
import pythontk as ptk


class SwitchboardWidgetMixin:
    """Widget registration, resolution, and dynamic class loading for Switchboard."""

    def is_registered_ui(self, name: str) -> bool:
        """True if *name* matches a known UI file stem in the registry (no load is triggered)."""
        if not name:
            return False
        filenames = self.registry.ui_registry.get("filename") or []
        return name in filenames

    def ui_name_resolves(self, name: str) -> bool:
        """True if *name* resolves to a UI, without triggering a load.

        Broader than :meth:`is_registered_ui`: a name resolves if it is a
        registered file stem OR a name the active UI handler can build on demand
        — e.g. a mayatk native Maya menu (``"key"``), which is not a ``.ui`` file
        but is produced by ``MayaUiHandler`` from ``MayaNativeMenus.MENU_MAPPING``.
        The file-stem-only ``is_registered_ui`` missed those handler-backed,
        lazily-built UIs, which is why a nav button whose ``target`` is a native
        menu fell back to its ``#submenu`` overlay on release (instead of opening
        the menu). Resolvability is queried via the handler's ``can_resolve`` hook
        (default = file stem), so no menu is actually built here.
        """
        if not name:
            return False
        if self.is_registered_ui(name):
            return True
        handler = getattr(getattr(self, "handlers", None), "ui", None)
        can_resolve = getattr(handler, "can_resolve", None)
        try:
            return bool(can_resolve and can_resolve(name))
        except Exception:
            return False

    def menu_button_target_name(self, widget) -> Optional[str]:
        """The registered UI name a ``MenuButton`` navigates to, or ``None``.

        Single source of truth for nav-button destination resolution, shared by the
        visibility auto-hide (:meth:`menu_button_target_resolves`) and the marking menu's
        click path (``MarkingMenu._resolve_button_menu``) so they can't drift — divergence
        here is what let a click resolve a different (or dead) target than the auto-hide saw.
        Two candidates, the registered base ``target`` preferred:

        * **Base-panel launcher** — a ``target`` that itself resolves to a UI (e.g. the
          polygons component buttons → the ``"polygons"`` panel; or a category button like
          ``"key"`` → the native Maya ``key`` menu the mayatk handler builds on demand).
          This is the original click behavior; preferred so a button that has both a base
          panel and a submenu still opens the base panel on click. Resolvability uses
          :meth:`ui_name_resolves` (file stem OR handler-backed) — not the file-stem-only
          :meth:`is_registered_ui`, which missed lazily-built native menus and made ``key``
          fall back to its overlay submenu on release ("the standalone menu never opened").
        * **Submenu launcher** — a bare ``target`` like ``"cameras"`` that does *not*
          resolve composes ``submenu_name()`` (``"cameras#lower#submenu"``), matching the
          hover path (``child_enterEvent``), which always opens the submenu.
        """
        target = widget.target
        if not target:
            return None
        if self.ui_name_resolves(target):
            return target
        submenu = widget.submenu_name()
        if self.is_registered_ui(submenu):
            return submenu
        return None

    def menu_button_target_resolves(self, widget) -> bool:
        """True if a ``MenuButton``'s ``target`` resolves to a registered UI.

        See :meth:`menu_button_target_name` for the resolution rules — the visibility
        policy never hides a button that *does* go somewhere (a click would reach it).
        """
        return self.menu_button_target_name(widget) is not None

    def apply_visibility_policy(self, widget) -> bool:
        """Hide a freshly-registered widget the current context can't serve.

        Two policies, applied at widget registration (``MainWindow.register_widget``):

        1. **``requires`` tag** — a Designer dynamic string property naming the feature
           tag(s) the widget needs (``"maya"``, ``"maya|blender"``; ``|``/comma/space
           separated alternatives). Hidden when the switchboard's ``context_tags`` is
           non-empty and shares no tag. An empty ``context_tags`` disables filtering.
        2. **Nav auto-hide** — a ``MenuButton`` whose ``target`` does not resolve against
           the UI registry navigates nowhere in this context and hides itself (no manual
           tags needed; an unported submenu disappears from every nav path that points
           at it). Resolution mirrors the live nav paths — see
           :meth:`menu_button_target_resolves`.

        Returns True when the widget was hidden; the reason is recorded on
        ``widget.hidden_by_policy`` for tooling/coverage reports.
        """
        requires = widget.property("requires")
        if requires and self.context_tags:
            tags = {t for t in re.split(r"[|,\s]+", str(requires)) if t}
            if tags and not (tags & self.context_tags):
                widget.setVisible(False)
                widget.hidden_by_policy = "requires"
                return True

        from uitk.widgets.menuButton import MenuButton

        if isinstance(widget, MenuButton):
            target = widget.target
            if target and not self.menu_button_target_resolves(widget):
                widget.setVisible(False)
                widget.hidden_by_policy = "nav-unresolved"
                return True
        return False

    def resolve_widget_class(
        self, class_name: str
    ) -> Optional[Type[QtWidgets.QWidget]]:
        """Return the widget class registered under the given name."""
        return self.registry.widget_registry.get(
            classname=class_name, return_field="classobj"
        )

    def _resolve_widget(self, class_name: str) -> Optional[QtWidgets.QWidget]:
        """Resolver for dynamically loading registered widgets when accessed.

        Parameters:
            class_name (str): The name of the widget to resolve.

        Returns:
            QWidget or None: The resolved and registered widget, or None if not found.
        """
        self.logger.debug(f"Resolving widget: {class_name}")

        widget_class = self.resolve_widget_class(class_name)
        if not widget_class:
            raise AttributeError(f"Unable to resolve widget class for '{class_name}'.")

        widget = self.register_widget(widget_class)
        self.logger.debug(
            f"Widget class '{widget_class.__name__}' loaded successfully."
        )
        return widget

    def _resolve_icon(self, icon_name: str) -> Optional[QtGui.QIcon]:
        """Resolver for dynamically loading registered icons when accessed.

        Parameters:
            icon_name (str): The name of the icon to resolve (without file extension).

        Returns:
            QIcon or None: The resolved icon, or None if not found.
        """
        self.logger.debug(f"Resolving icon: {icon_name}")

        # Try to find the icon file in the registry
        icon_path = self.registry.icon_registry.get(
            filename=icon_name, return_field="filepath"
        )
        if not icon_path:
            self.logger.warning(f"Icon '{icon_name}' not found in registry.")
            return None

        # Create and return QIcon
        icon = QtGui.QIcon(icon_path)
        if icon.isNull():
            self.logger.warning(f"Failed to load icon from path: {icon_path}")
            return None

        self.logger.debug(f"Icon '{icon_name}' loaded successfully from: {icon_path}")
        return icon

    def get_icon(self, icon_name: str) -> QtGui.QIcon:
        """Get a registered icon by name.

        Parameters:
            icon_name (str): The name of the icon (without file extension).

        Returns:
            QIcon: The icon if found, or a null icon if not found.
        """
        return getattr(self.registered_icons, icon_name, QtGui.QIcon())

    @classmethod
    def _get_widgets_from_ui(
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
    def _widget_is_alive(instance) -> bool:
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
    def _get_widget_from_ui(
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
        """Register any custom widgets using the module names.
        Registered widgets can be accessed as properties. ex. sb.registered_widgets.PushButton()

        Parameters:
            widget (obj): The widget to register.

        Returns:
            (obj): The registered widget
        """
        if widget.__name__ not in self.registered_widgets.keys():
            self.registered_widgets[widget.__name__] = widget
            return widget

    def get_widget(self, name, ui=None):
        """Case insensitive. Get the widget object/s from the given UI and name.

        Parameters:
            name (str): The object name of the widget. ie. 'b000'
            ui (str/obj): UI, or name of UI. ie. 'polygons'. If no nothing is given, the current UI will be used.
                    A UI object can be passed into this parameter, which will be used to get it's corresponding name.
        Returns:
            (obj) if name:  widget object with the given name from the current UI.
                    if ui and name: widget object with the given name from the given UI name.
            (list) if ui: all widgets for the given UI.
        """
        if ui is None or isinstance(ui, str):
            ui = self.get_ui(ui)

        return next((w for w in ui.widgets if w.objectName() == name), None)

    def get_widget_from_slot(self, method):
        """Get the corresponding widget from a given method.

        Parameters:
            method (obj): The method in which to get the widget of.

        Returns:
            (obj) The widget of the same name. ie. <b000 widget> from <b000 method>.
        """
        if not method:
            return None

        return next(
            iter(
                w
                for u in self.loaded_ui.values()
                for w in u.widgets
                if w.get_slot() == method
            ),
            None,
        )

    def set_widget_attrs(self, ui, widget_names, **kwargs):
        """Set multiple properties, for multiple widgets, on multiple UI's at once.

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            widget_names (str): String of object_names. - object_names separated by ',' ie. 'b000-12,b022'
            *kwargs = keyword: - the property to modify. ex. setText, setValue, setEnabled, setDisabled, setVisible, setHidden
                        value: - intended value.
        Example:
            set_widget_attrs(<ui>, 'chk003-6', setText='Un-Crease')
        """
        # Get_widgets_from_str returns a widget list from a string of object_names.
        widgets = self.get_widgets_by_string_pattern(ui, widget_names)
        # Set the property state for each widget in the list.
        for attr, value in kwargs.items():
            for w in widgets:
                try:
                    setattr(w, attr, value)
                except AttributeError:
                    pass

    def is_widget(self, obj):
        """Returns True if the given obj is a valid widget.

        Parameters:
            obj (obj): An object to query.

        Returns:
            (bool)
        """
        try:
            return issubclass(obj, QtWidgets.QWidget)
        except TypeError:
            return issubclass(obj.__class__, QtWidgets.QWidget)

    @staticmethod
    def get_parent_widgets(widget, object_names=False):
        """Get the all parent widgets of the given widget.

        Parameters:
            widget (QWidget): The widget to get parents of.
            object_names (bool): Return as object_names.

        Returns:
            (list) Object(s) or objectName(s)
        """
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
        """Get Qt windows.

        Parameters:
            name (str): Return only windows having the given object name.

        Returns:
            (list) windows.
        """
        return [
            w
            for w in QtWidgets.QApplication.allWindows()
            if (name is None) or (w.objectName() == name)
        ]

    @staticmethod
    def get_all_widgets(name=None):
        """Get Qt widgets.

        Parameters:
            name (str): Return only widgets having the given object name.

        Returns:
            (list) widgets.
        """
        return [
            w
            for w in QtWidgets.QApplication.allWidgets()
            if (name is None) or (w.objectName() == name)
        ]

    @staticmethod
    def get_widget_at(pos, top_widget_only=True):
        """Get visible and enabled widget(s) located at the given position.
        As written, this will disable `TransparentForMouseEvents` on each widget queried.

        Parameters:
            pos (QPoint) = The global position at which to query.
            top_widget_only (bool): Return only the top-most widget,
                    otherwise widgets are returned in the order in which they overlap.
                    Disabling this option will cause overlapping windows to flash as
                    their attribute is changed and restored.
        Returns:
            (obj/list) list if not top_widget_only.

        Example:
            get_widget_at(QtGui.QCursor.pos())
        """
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
