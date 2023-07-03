# !/usr/bin/python
# coding=utf-8
from PySide2 import QtCore, QtWidgets
from uitk.widgets.menu import Menu


class AttributeWindow(Menu):
    """A custom window for displaying and interacting with attributes.

    This class extends the Menu class and provides a way to display attributes
    with their corresponding widgets. The attributes can be checkable and the
    window can be configured to allow only one attribute to be checked at a time.

    Attributes:
        labelToggled (QtCore.Signal): Signal emitted when a label is toggled.
        valueChanged (QtCore.Signal): Signal emitted when the value of an attribute changes.
    """

    INT_MIN = -2147483648
    INT_MAX = 2147483647
    FLOAT_MIN = -1e100
    FLOAT_MAX = 1e100

    labelToggled = QtCore.Signal(str, bool)
    valueChanged = QtCore.Signal(str, object)

    def __init__(
        self,
        obj,
        attributes_dict={},
        window_title="",
        checkable=False,
        single_check=False,
        set_attribute_func=None,
        label_toggle_func=None,
        allow_unsupported_types=False,
        **kwargs,
    ):
        """Initialize an instance of AttributeWindow.

        Parameters:
            checkable (bool): Whether the labels should be checkable. Defaults to False.
            single_check (bool): Whether only one label should be checkable at a time. Defaults to False.
            unknown_datatype_handling (bool): Whether to allow unknown data types. "allow", "fail_silently", "fail_with_error"
            **kwargs: Additional keyword arguments to set attributes on the menu.
        """
        super().__init__(**kwargs)

        self.checkable = checkable
        self.single_check = single_check
        self.allow_unsupported_types = allow_unsupported_types
        self.labels = []
        self.widgets = []
        self.attribute_to_widgets = {}
        self.ignore_toggle = False

        self.label_group = None
        if self.single_check:
            self.label_group = QtWidgets.QButtonGroup(self)
            self.label_group.setExclusive(False)  # Allow all checkboxes to be unchecked
            # Connect buttonToggled signal to your slot
            self.label_group.buttonToggled.connect(self.on_button_clicked)

        self.type_to_widget = {
            bool: (QtWidgets.QCheckBox, "setChecked", "isChecked", "stateChanged"),
            int: (QtWidgets.QDoubleSpinBox, "setValue", "value", "valueChanged"),
            float: (QtWidgets.QDoubleSpinBox, "setValue", "value", "valueChanged"),
            str: (QtWidgets.QLineEdit, "setText", "text", "textChanged"),
        }

        self.setTitle(window_title)
        self.position = "cursorPos"

        for attribute_name, attribute_value in attributes_dict.items():
            self.add_attribute(attribute_name, attribute_value)

        def safe_set_attribute(obj, name, value):
            try:
                # use setattr if set_attribute_func is None
                (set_attribute_func or setattr)(obj, name, value)
            except Exception as e:
                print(e)

        # Connect the valueChanged signal to a slot that sets the attribute on the object
        self.valueChanged.connect(
            lambda name, value: safe_set_attribute(obj, name, value)
        )

        # Connect the labelToggled signal to a slot that handles the label toggled event
        if label_toggle_func is not None:
            self.labelToggled.connect(
                lambda name, state: label_toggle_func(obj, name, state)
            )

    @staticmethod
    def is_type_supported(attribute_type):
        supported_types = {
            bool,
            int,
            float,
            str,  # Update with any additional types you support
        }
        return attribute_type in supported_types

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
        widget.get_value_method = get_value_method  # Store the get_value_method
        widget.setProperty("attribute_name", attribute_name)  # Store the attribute_name

        getattr(widget, set_value_method)(widget.original_value)

        if isinstance(widget, QtWidgets.QCheckBox):
            widget.setText(str(widget.original_value))  # Set the text for QCheckBox
            # Update text on state change
            widget.stateChanged.connect(lambda: widget.setText(str(widget.isChecked())))

        if isinstance(widget, QtWidgets.QDoubleSpinBox):
            widget.setRange(self.FLOAT_MIN, self.FLOAT_MAX)
            widget.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            if isinstance(widget.original_value, float):
                decimals = len(str(widget.original_value).split(".")[-1])
                widget.setDecimals(decimals)

        if isinstance(widget.original_value, (list, set, tuple)):
            getattr(widget, signal_name).connect(
                lambda: self.emit_composite_value_changed(attribute_name)
            )
        else:
            getattr(widget, signal_name).connect(
                lambda: self.emit_value_changed(widget)
            )

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

    def add_attribute(self, attribute_name, attribute_value):
        """Add an attribute to the window."""

        # Check the type of the attribute_value here
        if not self.allow_unsupported_types and not self.is_type_supported(
            type(attribute_value)
        ):
            return

        # If attribute is a composite one
        if isinstance(attribute_value, (list, set, tuple)):
            widget_layout = QtWidgets.QVBoxLayout()
            widget_layout.setSpacing(1)
            widget_layout.setMargin(0)
            widgets = []
            for value in attribute_value:
                widget_info = self.get_widget_info(value)
                if widget_info is not None:
                    (
                        widget_class,
                        set_value_method,
                        get_value_method,
                        signal_name,
                    ) = widget_info
                    if (
                        None in widget_info
                    ):  # Skip this iteration if any value in widget_info is None
                        continue
                    widget = self.setup_widget(
                        widget_class,
                        set_value_method,
                        value,
                        get_value_method,
                        signal_name,
                        attribute_name,
                    )
                    widgets.append(widget)
                    widget_layout.addWidget(widget)
            if widgets:
                self.attribute_to_widgets[attribute_name] = widgets
                label = self.setup_label(attribute_name)
                self.add_to_layout(label, widget_layout)

        else:  # Single value attribute
            widget_info = self.get_widget_info(attribute_value)
            if widget_info is not None:
                (
                    widget_class,
                    set_value_method,
                    get_value_method,
                    signal_name,
                ) = widget_info
                if (
                    None in widget_info
                ):  # Return from the method if any value in widget_info is None
                    return
                widget = self.setup_widget(
                    widget_class,
                    set_value_method,
                    attribute_value,
                    get_value_method,
                    signal_name,
                    attribute_name,
                )
                self.attribute_to_widgets[attribute_name] = [widget]
                label = self.setup_label(attribute_name)
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
    obj = QtWidgets.QWidget()

    attrs = {
        "Name": "Cube",
        "Visible": True,
        "Opacity": 0.5,
        "Position": [0, 0, 0],
    }

    window = AttributeWindow(
        obj,
        attrs,
        checkable=0,
        single_check=1,
        allow_unsupported_types=1,
        setVisible=1,
    )

    window.add_attribute("Texture", "path/to/texture.png")

    # Unknown datatype attribute
    class UnknownType:
        pass

    unknown_attr = UnknownType()
    window.add_attribute("Unknown Attribute", unknown_attr)

    window.set_style(theme="dark")

    window.labelToggled.connect(lambda *args: print(args))
    window.valueChanged.connect(lambda *args: print(args))

    sys.exit(app.exec_())


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------


# Deprecated: -------------------------------------
