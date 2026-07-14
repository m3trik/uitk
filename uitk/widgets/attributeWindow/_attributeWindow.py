# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from uitk.widgets.menu import Menu

# Alias the sibling factory module so every `factory.<...>` call site
# below reads naturally without dragging in the package name.
from . import _factory as factory


class AttributeWindow(Menu):
    """Dynamic popup editor for inspecting and modifying object attributes.

    Attributes are displayed with corresponding interactive widgets, enabling users to modify values directly. The class allows for customizable widget behavior, including options for making attributes checkable and enforcing single-selection if required. A key design goal is flexibility, allowing the class to adapt to different attribute sets and object types without significant modifications.

    The window dynamically refreshes to display the current state of object attributes, either through direct user action or programmatically via signals. This ensures that the attribute window remains synchronized with the underlying object attributes, providing an up-to-date and accurate user interface for attribute manipulation.

    Attributes:
        labelToggled (QtCore.Signal): Emitted when a label's toggle state changes, providing the attribute name and the new state.
        valueChanged (QtCore.Signal): Emitted when the value of an attribute changes, indicating the attribute name and the new value.
        refreshRequested (QtCore.Signal): A signal that can be emitted to request a refresh of the attribute display, ensuring it reflects the current attributes of the object.

    Parameters:
        obj (object): The object whose attributes are to be displayed and edited.
        window_title (str, optional): The title of the attribute window.
        checkable (bool, optional): Indicates whether attribute labels should be checkable. Defaults to False.
        single_check (bool, optional): If True, enforces that only one label can be checked at a time. Defaults to False.
        get_attribute_func (callable, optional): A custom function to fetch the attributes of the object. If not provided, a default function is used that reflects all attributes of the object.
        set_attribute_func (callable, optional): A custom function called to set the value of an object's attribute. If not provided, setattr is used by default.
        label_toggle_func (callable, optional): A custom function called when an attribute label's checked state is toggled.
        allow_unsupported_types (bool, optional): If True, allows attributes of unsupported data types to be displayed using a default widget.

    This class is designed to offer a user-friendly interface for attribute editing, prioritizing clarity, ease of use, and adaptability to various usage scenarios.
    """

    labelToggled = QtCore.Signal(str, bool)
    valueChanged = QtCore.Signal(str, object)
    refreshRequested = QtCore.Signal()

    def __init__(
        self,
        obj,
        window_title="",
        checkable=False,
        single_check=False,
        get_attribute_func=None,
        set_attribute_func=None,
        label_toggle_func=None,
        allow_unsupported_types=False,
        float_precision=10,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.obj = obj
        self.window_title = window_title
        self.checkable = checkable
        self.single_check = single_check
        self.allow_unsupported_types = allow_unsupported_types
        self.labels = []
        self.widgets = []
        self.attribute_to_widgets = {}
        self.ignore_toggle = False
        self.float_precision = float_precision

        self.get_attribute_func = get_attribute_func or self.default_get_attribute_func
        self.set_attribute_func = self.create_set_attribute_func_wrapper(
            set_attribute_func
        )
        self.label_toggle_func = label_toggle_func

        # Connect signals with the new wrapper
        self.valueChanged.connect(
            lambda name, value: self.set_attribute_func(name, value)
        )

        if self.label_toggle_func:
            self.labelToggled.connect(
                lambda name, state: self.label_toggle_func(name, state)
            )
        self.refreshRequested.connect(self.refresh_attributes)

        # self.setProperty("class", self.__class__.__name__)
        self.initialize_ui()

    def initialize_ui(self):
        """Initializes the user interface components of the AttributeWindow.

        Widget construction is delegated to :mod:`uitk.bridge.spec`
        (re-exported through the back-compat ``_factory`` shim);
        AttributeWindow only orchestrates layout, labels, and signal routing.
        """
        self.label_group = None
        if self.single_check:
            self.label_group = QtWidgets.QButtonGroup(self)
            self.label_group.setExclusive(False)  # Allow all checkboxes to be unchecked
            self.label_group.buttonToggled.connect(self.on_button_clicked)

        self.setTitle(self.window_title)
        self.position = "cursorPos"

        # Initial attribute population
        self.refresh_attributes()

    def refresh_attributes(self):
        """Refreshes the window with the latest attributes."""
        attributes_dict = self.get_attribute_func()
        self.clear_ui_elements()
        added_attribute_count = 0  # Initialize a counter for added attributes
        for name, value in attributes_dict.items():
            if self._is_value_supported(value) or self.allow_unsupported_types:
                self.add_attributes(name, value)
                # Increment the counter when an attribute is added
                added_attribute_count += 1
        if added_attribute_count == 0:  # Check if no attributes were added
            print(
                "Warning: No attributes added to the AttributeWindow. Check attribute types and fetching logic."
            )

    def clear_ui_elements(self):
        """Clears existing labels and widgets from the UI."""
        for label in self.labels:
            self.gridLayout.removeWidget(label)
            label.deleteLater()
        for widget in self.widgets:
            self.gridLayout.removeWidget(widget)
            widget.deleteLater()
        self.labels.clear()
        self.widgets.clear()
        self.attribute_to_widgets.clear()

    def default_get_attribute_func(self):
        # Default method to fetch attributes; adjust as needed
        return {
            attr: getattr(self.obj, attr, None)
            for attr in dir(self.obj)
            if self.is_valid_attribute(attr)
        }

    def create_set_attribute_func_wrapper(self, set_attribute_func):
        import inspect

        if set_attribute_func is None:
            return self.default_set_attribute_func

        sig = inspect.signature(set_attribute_func)
        num_params = len(sig.parameters)

        if num_params == 2:
            # If the function accepts exactly two parameters (name, value), use as is
            return set_attribute_func
        elif num_params == 1:
            # If the function accepts a single dict, adjust accordingly
            def wrapper(name, value):
                set_attribute_func({name: value})

            return wrapper
        else:
            raise ValueError(
                "set_attribute_func must accept either one parameter (as a dict) or two parameters (name and value)."
            )

    def default_set_attribute_func(self, name, value):
        # Default method to set an attribute's value
        try:
            setattr(self.obj, name, value)
        except Exception as e:
            print(f"Error setting attribute '{name}': {e}")

    @staticmethod
    def is_valid_attribute(attr_name):
        # Implement logic to determine if an attribute name is valid for display/editing
        return not attr_name.startswith("__")

    @staticmethod
    def is_type_supported(attribute_type):
        """Return True if AttributeWindow can auto-build a widget for *attribute_type*.

        Kept as a static method on the class for backward compat. The list
        matches the kinds auto-derived by :func:`uitk.infer_kind` from a
        Python value of that type.
        """
        return attribute_type in (bool, int, float, str)

    def _is_value_supported(self, value):
        """Return True when a widget can be built for *value*.

        A scalar whose type :meth:`is_type_supported`, OR a composite
        (list/set/tuple) whose elements are each individually supported.
        This makes the documented composite support reachable independent of
        ``allow_unsupported_types`` — the plain ``is_type_supported(type(value))``
        gate returns ``False`` for a list/tuple/set and so short-circuited the
        composite branch before it could run.
        """
        if self.is_type_supported(type(value)):
            return True
        if isinstance(value, (list, set, tuple)):
            return all(self.is_type_supported(type(v)) for v in value)
        return False

    def _apply_float_precision(self, spec):
        """Bake the window's ``float_precision`` onto a float spec.

        ``AttributeSpec`` is a frozen dataclass, so this returns a copy with
        ``decimals`` set for the ``float`` kind (the DoubleSpinBox builder reads
        ``spec.decimals``); non-float specs pass through unchanged.
        """
        if self.float_precision is None or getattr(spec, "kind", None) != "float":
            return spec
        import dataclasses

        return dataclasses.replace(spec, decimals=int(self.float_precision))

    def add_attributes(self, attributes, value=None):
        """Adds a single attribute or multiple attributes to the attribute window.

        Supports three input forms:
            * ``add_attributes({name: value, ...})`` — bulk add via dict.
            * ``add_attributes(name, value)`` — single attribute; widget kind
              is inferred from ``type(value)``.
            * ``add_attributes(spec)`` where *spec* is an
              :class:`uitk.AttributeSpec` — spec-driven add
              (equivalent to :meth:`add_attribute_spec`).

        Composite attributes (whose values are lists, sets, or tuples) get
        one widget per element stacked vertically; any element change emits
        the full composite list via ``valueChanged``.

        Values whose type is not in :meth:`is_type_supported` are dropped
        silently unless ``allow_unsupported_types=True`` was passed to
        ``__init__``, in which case they're rendered as their ``str()``
        repr in a QLineEdit.
        """
        if isinstance(attributes, dict):
            for k, v in attributes.items():
                self.add_attributes(k, v)
            return

        if isinstance(attributes, factory.AttributeSpec):
            self.add_attribute_spec(attributes)
            return

        if not self.allow_unsupported_types and not self._is_value_supported(value):
            return

        if isinstance(value, (list, set, tuple)):
            self._add_composite(attributes, value)
            return

        self._add_scalar(attributes, value)

    def add_attribute_spec(self, spec):
        """Add one attribute via an explicit :class:`uitk.AttributeSpec`.

        Use this when you need min/max/step/choices/path semantics that the
        type-driven :meth:`add_attributes` form can't express. The spec's
        ``key`` becomes the attribute name; the displayed label uses
        ``spec.label`` (falling back to ``spec.key``).
        """
        widget = factory.make_widget(spec, self)
        widget.setProperty("attribute_name", spec.key)
        factory.connect_changed(
            widget, lambda _v, _w=widget: self.emit_value_changed(_w)
        )
        self.attribute_to_widgets[spec.key] = [widget]
        label = self.setup_label(spec.display_label)
        self.add_to_layout(label, widget)

    def _add_scalar(self, name, value):
        """Build + wire a single-value widget via the factory.

        Called after the :meth:`add_attributes` gate has already accepted
        *value* (either supported type, or unsupported with the flag set).
        ``infer_kind`` always returns a built-in kind, so the factory call
        cannot KeyError here.
        """
        spec = factory.AttributeSpec.from_value(name, value)
        spec = self._apply_float_precision(spec)
        widget = factory.make_widget(spec, self)
        widget.setProperty("attribute_name", spec.key)
        factory.connect_changed(
            widget, lambda _v, _w=widget: self.emit_value_changed(_w)
        )
        self.attribute_to_widgets[spec.key] = [widget]
        label = self.setup_label(spec.display_label)
        self.add_to_layout(label, widget)

    def _add_composite(self, name, values):
        """Build one widget per element; any change emits the full composite list."""
        widget_layout = QtWidgets.QVBoxLayout()
        widget_layout.setSpacing(1)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        widgets = []
        for element in values:
            if not self.allow_unsupported_types and not self.is_type_supported(type(element)):
                continue
            spec = factory.AttributeSpec.from_value(name, element)
            spec = self._apply_float_precision(spec)
            w = factory.make_widget(spec, self)
            w.setProperty("attribute_name", spec.key)
            factory.connect_changed(
                w, lambda _v, _n=spec.key: self.emit_composite_value_changed(_n)
            )
            widgets.append(w)
            widget_layout.addWidget(w)
        if widgets:
            self.attribute_to_widgets[name] = widgets
            label = self.setup_label(name)
            self.add_to_layout(label, widget_layout)

    def emit_value_changed(self, widget):
        """Emit the valueChanged signal for a widget (or composite-aware)."""
        attribute_name = widget.property("attribute_name")
        if (
            attribute_name in self.attribute_to_widgets
            and len(self.attribute_to_widgets[attribute_name]) > 1
        ):
            self.emit_composite_value_changed(attribute_name)
            return
        self.valueChanged.emit(attribute_name, factory.read_value(widget))

    def emit_composite_value_changed(self, attribute_name):
        """Construct and emit the full attribute value for a composite attribute."""
        attribute_value = [
            factory.read_value(w)
            for w in self.attribute_to_widgets[attribute_name]
        ]
        self.valueChanged.emit(attribute_name, attribute_value)

    def setup_label(self, attribute_name):
        """Set up the label for the attribute."""
        label = QtWidgets.QCheckBox(attribute_name)
        label.setCheckable(self.checkable)

        if not self.checkable:
            label.setProperty("class", "noHover")

        if self.label_group is not None:
            self.label_group.addButton(label)
        elif self.checkable:
            # single_check=False: there is no QButtonGroup to route toggles
            # through on_button_clicked, so wire each checkable label directly.
            # Without this, `labelToggled` never fired for multi-check labels.
            label.toggled.connect(
                lambda _checked, lbl=label: self.on_label_toggled(lbl)
            )

        return label

    def on_label_toggled(self, label):
        """Slot to be called when a label is toggled."""
        if self.ignore_toggle:  # If ignore_toggle is True, return immediately
            return
        self.labelToggled.emit(label.text(), label.isChecked())  # Emit the signal

    def on_button_clicked(self, button, checked):
        """Slot for buttonClicked signal of QButtonGroup.

        If the clicked button was already checked, uncheck it.
        If not, uncheck all other buttons.
        """
        if button.isChecked():
            for other_button in self.label_group.buttons():
                if other_button is not button:
                    other_button.setChecked(False)
        else:
            button.setChecked(False)

        self.labelToggled.emit(button.text(), button.isChecked())

    def add_to_layout(self, label, widget):
        """Add the label and widget to the layout."""
        label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
        )
        if isinstance(widget, QtWidgets.QLayout):
            widget.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)
        else:
            widget.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
            )

        row = 0
        while self.gridLayout.itemAtPosition(row, 0) is not None:
            row += 1

        self.labels.append(label)
        if isinstance(widget, QtWidgets.QLayout):
            for i in range(widget.count()):
                self.widgets.append(widget.itemAt(i).widget())
        else:
            self.widgets.append(widget)

        self.gridLayout.addWidget(label, row, 0)
        if isinstance(widget, QtWidgets.QLayout):
            layout_widget = QtWidgets.QWidget()
            layout_widget.setLayout(widget)
            self.gridLayout.addWidget(layout_widget, row, 1)
        else:
            self.gridLayout.addWidget(widget, row, 1)

        self.gridLayout.setColumnStretch(0, 1)
        self.gridLayout.setColumnStretch(1, 2)

    def showEvent(self, event):
        """Handle the show event for the window.

        This method is called when the window is shown. It adjusts the size of the labels
        and widgets based on their content.

        Parameters:
            event (QShowEvent): The show event.
        """
        super().showEvent(event)
        try:
            max_label_width = max(label.sizeHint().width() for label in self.labels)
            max_widget_width = max(widget.sizeHint().width() for widget in self.widgets)
            for label in self.labels:
                label.setFixedSize(max_label_width, label.size().height())
            for widget in self.widgets:
                widget.setFixedSize(max_widget_width, widget.size().height())
        except (ValueError, AttributeError):
            # ValueError: max() over an empty labels/widgets sequence (a window
            # shown with zero attributes). AttributeError: a widget without
            # sizeHint(). Either way there's nothing to size — skip.
            pass


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    obj = AttributeWindow

    window = AttributeWindow(
        obj,
        checkable=0,
        single_check=1,
        allow_unsupported_types=1,
        setVisible=1,
    )

    attrs = {
        "Name": "Cube",
        "Visible": True,
        "Opacity": 0.5,
        "Position": [0, 0, 0],
    }
    window.add_attributes(attrs)
    window.add_attributes("Texture", "path/to/texture.png")

    # Unknown datatype attribute
    class UnknownType:
        pass

    unknown_attr = UnknownType()
    window.add_attributes("Unknown Attribute", unknown_attr)

    window.style.set(theme="dark")

    window.labelToggled.connect(lambda *args: print(args))
    window.valueChanged.connect(lambda *args: print(args))

    window.show()
    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------
