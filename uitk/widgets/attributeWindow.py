# !/usr/bin/python
# coding=utf-8
from qtpy import QtWidgets, QtCore
from uitk.widgets.menu import Menu
from uitk.widgets.doubleSpinBox import DoubleSpinBox


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

    INT_MIN = -2147483648
    INT_MAX = 2147483647
    FLOAT_MIN = -1e100
    FLOAT_MAX = 1e100

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
        """Initializes the user interface components of the AttributeWindow."""
        self.label_group = None
        if self.single_check:
            self.label_group = QtWidgets.QButtonGroup(self)
            self.label_group.setExclusive(False)  # Allow all checkboxes to be unchecked
            self.label_group.buttonToggled.connect(self.on_button_clicked)

        self.type_to_widget = {
            bool: (QtWidgets.QCheckBox, "setChecked", "isChecked", "stateChanged"),
            int: (QtWidgets.QSpinBox, "setValue", "value", "valueChanged"),
            float: (DoubleSpinBox, "setValue", "value", "valueChanged"),
            str: (QtWidgets.QLineEdit, "setText", "text", "textChanged"),
        }

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
            if self.is_type_supported(type(value)) or self.allow_unsupported_types:
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
        return attribute_type in [bool, int, float, str]

    def get_widget_info(self, attribute_value):
        """Get the widget class and methods based on the attribute value type."""
        if (
            not self.allow_unsupported_types
            and type(attribute_value) not in self.type_to_widget
        ):
            raise ValueError(f"Unknown data type: {type(attribute_value)}")
        elif (
            self.allow_unsupported_types
            and type(attribute_value) not in self.type_to_widget
        ):
            return None
        else:
            return self.type_to_widget.get(
                type(attribute_value),
                (QtWidgets.QLineEdit, "setText", "text", "textChanged"),
            )

    def create_widget(self, widget_class, attribute_value):
        """Create an instance of a widget.

        Parameters:
            widget_class (type): The class of the widget to create.
            attribute_value (type): The initial value of the attribute.

        Returns:
            QtWidgets.QWidget: The created widget.
        """
        widget = widget_class(self)
        widget.original_value = attribute_value  # Store the original value
        # Convert the attribute value to a string if it's not a boolean
        if widget_class is QtWidgets.QLineEdit and not isinstance(
            attribute_value, bool
        ):
            attribute_value = str(attribute_value)

        return widget

    def configure_widget(
        self,
        widget,
        set_value_method,
        get_value_method,
        signal_name,
        attribute_name,
    ):
        """Configure a widget for the attribute.

        Parameters:
            widget (QtWidgets.QWidget): The widget to configure.
            set_value_method (str): The name of the method to set the value on the widget.
            get_value_method (str): The name of the method to get the value from the widget.
            signal_name (str): The name of the signal to connect to the valueChanged slot.
            attribute_name (str): The name of the attribute the widget is associated with.
        """
        # Configure QCheckBox
        if isinstance(widget, QtWidgets.QCheckBox):
            widget.setText(str(widget.original_value))  # Set the text for QCheckBox
            # Update text on state change
            widget.stateChanged.connect(lambda: widget.setText(str(widget.isChecked())))

        # Configure QSpinBox (for integer values)
        if isinstance(widget, QtWidgets.QSpinBox):
            widget.setRange(self.INT_MIN, self.INT_MAX)
            widget.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)

        # Configure QDoubleSpinBox
        if isinstance(widget, QtWidgets.QDoubleSpinBox):
            widget.setRange(self.FLOAT_MIN, self.FLOAT_MAX)
            widget.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            widget.setDecimals(self.float_precision)

        # Connect signals for value changes
        if isinstance(widget.original_value, (list, set, tuple)):
            getattr(widget, signal_name).connect(
                lambda: self.emit_composite_value_changed(attribute_name)
            )
        else:
            getattr(widget, signal_name).connect(
                lambda: self.emit_value_changed(widget)
            )

        widget.get_value_method = get_value_method  # Store the get_value_method
        widget.setProperty("attribute_name", attribute_name)  # Store the attribute_name

        # Set the original value
        getattr(widget, set_value_method)(widget.original_value)

    def setup_widget(
        self,
        widget_class,
        set_value_method,
        attribute_value,
        get_value_method,
        signal_name,
        attribute_name,
    ):
        """Set up the widget for the attribute."""
        widget = self.create_widget(widget_class, attribute_value)
        self.configure_widget(
            widget,
            set_value_method,
            get_value_method,
            signal_name,
            attribute_name,
        )

        return widget

    def add_attributes(self, attributes, value=None):
        """Adds a single attribute or multiple attributes to the attribute window for display and interaction.
        This method supports both direct attribute-value pairs and dictionary inputs for bulk additions.

        If `attributes` is a dictionary, it iterates over its items, treating each key-value pair as an attribute name
        and its corresponding value. This allows for bulk attribute additions in a single call.

        For individual attribute additions, `attributes` is expected to be the attribute's name with its `value`.
        The method checks if the attribute's type is supported or if unsupported types are allowed
        (based on `allow_unsupported_types`). It then proceeds to create a widget based on the attribute's type and value,
        adding it to the UI layout for user interaction.

        Composite attributes (those whose values are lists, sets, or tuples) are handled by creating multiple widgets,
        one for each composite value, and arranging them within a vertical layout.

        Parameters:
            attributes (str, dict): The name of the attribute to add, or a dictionary of attribute names and values for bulk addition.
            value (optional): The value of the attribute if `attributes` is a string. Defaults to None.

        Returns:
            None: This method does not return a value but updates the UI elements of the attribute window.

        Raises:
            ValueError: If an unsupported attribute type is encountered and `allow_unsupported_types` is False.
        """
        if isinstance(attributes, dict):
            for k, v in attributes.items():
                self.add_attributes(k, v)

        # Check the type of the value here
        if not self.allow_unsupported_types and not self.is_type_supported(type(value)):
            return

        # If attribute is a composite one
        if isinstance(value, (list, set, tuple)):
            widget_layout = QtWidgets.QVBoxLayout()
            widget_layout.setSpacing(1)
            widget_layout.setMargin(0)
            widgets = []
            for value in value:
                widget_info = self.get_widget_info(value)
                if widget_info is not None:
                    (
                        widget_class,
                        set_value_method,
                        get_value_method,
                        signal_name,
                    ) = widget_info
                    # Skip this iteration if any value in widget_info is None
                    if None in widget_info:
                        continue
                    widget = self.setup_widget(
                        widget_class,
                        set_value_method,
                        value,
                        get_value_method,
                        signal_name,
                        attributes,
                    )
                    widgets.append(widget)
                    widget_layout.addWidget(widget)
            if widgets:
                self.attribute_to_widgets[attributes] = widgets
                label = self.setup_label(attributes)
                self.add_to_layout(label, widget_layout)

        else:  # Single value attribute
            widget_info = self.get_widget_info(value)
            if widget_info is not None:
                (
                    widget_class,
                    set_value_method,
                    get_value_method,
                    signal_name,
                ) = widget_info
                # Return from the method if any value in widget_info is None
                if None in widget_info:
                    return
                widget = self.setup_widget(
                    widget_class,
                    set_value_method,
                    value,
                    get_value_method,
                    signal_name,
                    attributes,
                )
                self.attribute_to_widgets[attributes] = [widget]
                label = self.setup_label(attributes)
                self.add_to_layout(label, widget)

    def emit_value_changed(self, widget):
        """Emit the valueChanged signal for a widget."""
        attribute_name = widget.property("attribute_name")
        if (
            attribute_name in self.attribute_to_widgets
            and len(self.attribute_to_widgets[attribute_name]) > 1
        ):
            self.emit_composite_value_changed(attribute_name)
        else:
            attribute_value = getattr(widget, widget.get_value_method)()
            self.valueChanged.emit(attribute_name, attribute_value)

    def emit_composite_value_changed(self, attribute_name):
        """Construct and emit the full attribute value for a composite attribute."""
        attribute_value = [
            getattr(widget, widget.get_value_method)()
            for widget in self.attribute_to_widgets[attribute_name]
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
        except AttributeError:
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
