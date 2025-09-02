# UITK Examples and Tutorials

This document provides practical examples demonstrating UITK's actual capabilities, from basic usage to more advanced patterns.

## Table of Contents
1. [Hello World Example](#hello-world-example)
2. [File Manager Application](#file-manager-application)
3. [Settings Dialog with State Persistence](#settings-dialog-with-state-persistence)
4. [Custom Widget Development](#custom-widget-development)
5. [Event Handling](#event-handling)
6. [Working with the Example](#working-with-the-example)

## Hello World Example

### Project Structure
```
hello_world/
├── ui/
│   └── main_window.ui
├── slots/
│   └── main_window_slots.py
└── main.py
```

### 1. UI Design (main_window.ui)
Create in Qt Designer with:
- QMainWindow as base
- Central widget with QVBoxLayout
- QLabel named `title_label`
- QPushButton named `hello_button`
- QPushButton named `exit_button`

### 2. Slot Implementation
```python
# slots/main_window_slots.py
from qtpy import QtCore

class MainWindowSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.main_window
        self.click_count = 0

    def title_label_init(self, widget):
        """Initialize the title label"""
        widget.setText("Welcome to UITK!")
        widget.setAlignment(QtCore.Qt.AlignCenter)

    def hello_button_init(self, widget):
        """Initialize the hello button"""
        widget.setText("Say Hello")
        widget.setToolTip("Click to greet the world")

    def hello_button(self, widget):
        """Handle hello button clicks"""
        self.click_count += 1
        message = f"Hello, World! (Clicked {self.click_count} times)"
        self.sb.message_box(message, "Greeting")

    def exit_button_init(self, widget):
        """Initialize the exit button"""
        widget.setText("Exit")
        widget.setToolTip("Close the application")

    def exit_button(self, widget):
        """Handle exit button clicks"""
        self.ui.close()
```

### 3. Main Application
```python
# main.py
import sys
from qtpy import QtWidgets
from uitk import Switchboard

def main():
    app = QtWidgets.QApplication(sys.argv)
    
    # Create switchboard
    sb = Switchboard(
        ui_source="./ui",
        slot_source="./slots"
    )
    
    # Load and configure main window
    ui = sb.main_window
    ui.setWindowTitle("UITK Hello World")
    
    # Apply basic styling
    if hasattr(ui, 'style'):
        ui.style.set(theme="dark")
    
    # Show window
    ui.show(pos="center", app_exec=True)

if __name__ == "__main__":
    main()
```

## File Manager Application

A more realistic example showing file operations and state management.

### Project Structure
```
file_manager/
├── ui/
│   ├── main_window.ui
│   └── file_dialog.ui
├── slots/
│   ├── main_window_slots.py
│   └── file_dialog_slots.py
└── main.py
```

### 1. Main Window Slots
```python
# slots/main_window_slots.py
import os
from qtpy import QtWidgets, QtCore
from uitk import Signals

class MainWindowSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.main_window
        self.current_path = os.path.expanduser("~")

    def path_edit_init(self, widget):
        """Initialize path editor"""
        widget.setText(self.current_path)

    def path_edit(self, text, widget):
        """Handle path changes"""
        if os.path.exists(text) and os.path.isdir(text):
            self.current_path = text
            self.refresh_file_list()

    def refresh_button(self, widget):
        """Handle refresh button"""
        self.refresh_file_list()

    def refresh_file_list(self):
        """Refresh the file list widget"""
        if hasattr(self.ui, 'file_list'):
            self.ui.file_list.clear()
            try:
                for item in sorted(os.listdir(self.current_path)):
                    item_path = os.path.join(self.current_path, item)
                    if os.path.isdir(item_path):
                        item = f"📁 {item}"
                    else:
                        item = f"📄 {item}"
                    self.ui.file_list.addItem(item)
            except PermissionError:
                self.ui.file_list.addItem("Permission Denied")

    def file_list(self, item, widget):
        """Handle file list selection"""
        if item:
            item_name = item.text().replace("📁 ", "").replace("📄 ", "")
            item_path = os.path.join(self.current_path, item_name)
            
            if os.path.isdir(item_path):
                self.current_path = item_path
                self.ui.path_edit.setText(item_path)
                self.refresh_file_list()
            else:
                # Show file info
                try:
                    size = os.path.getsize(item_path)
                    info = f"File: {item_name}\nSize: {size} bytes"
                    self.sb.message_box(info, "File Information")
                except OSError as e:
                    self.sb.message_box(f"Error: {e}", "Error")

    def open_file_dialog(self, widget):
        """Open custom file dialog"""
        dialog_ui = self.sb.file_dialog
        dialog_ui.exec_()
```

### 2. File Dialog Slots  
```python
# slots/file_dialog_slots.py
from qtpy import QtWidgets

class FileDialogSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.file_dialog
        self.selected_file = None

    def file_list_init(self, widget):
        """Initialize file list"""
        # Add some example files
        widget.addItems(["document.txt", "image.png", "data.csv"])

    def file_list(self, item, widget):
        """Handle file selection"""
        if item:
            self.selected_file = item.text()
            if hasattr(self.ui, 'selected_label'):
                self.ui.selected_label.setText(f"Selected: {self.selected_file}")

    def ok_button(self, widget):
        """Accept dialog"""
        if self.selected_file:
            self.ui.accept()
        else:
            self.sb.message_box("Please select a file", "Warning")

    def cancel_button(self, widget):
        """Cancel dialog"""
        self.ui.reject()
```

## Settings Dialog with State Persistence

### Settings Dialog Slots
```python
# slots/settings_dialog_slots.py
class SettingsDialogSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.settings_dialog

    def theme_combo_init(self, widget):
        """Initialize theme selection"""
        widget.addItems(["Light", "Dark"])
        # Restore saved theme if settings manager is available
        if hasattr(self.sb, 'settings'):
            saved_theme = self.sb.settings.value("theme", "Dark")
            widget.setCurrentText(saved_theme)

    def auto_save_checkbox_init(self, widget):
        """Initialize auto save option"""
        widget.setText("Enable auto-save")
        # Restore saved setting
        if hasattr(self.sb, 'settings'):
            auto_save = self.sb.settings.value("auto_save", True, type=bool)
            widget.setChecked(auto_save)

    def save_interval_spinbox_init(self, widget):
        """Initialize save interval"""
        widget.setRange(1, 60)
        widget.setSuffix(" minutes")
        # Restore saved setting
        if hasattr(self.sb, 'settings'):
            interval = self.sb.settings.value("save_interval", 5, type=int)
            widget.setValue(interval)

    def ok_button(self, widget):
        """Save settings and accept dialog"""
        # Save all settings if settings manager is available
        if hasattr(self.sb, 'settings'):
            self.sb.settings.setValue("theme", self.ui.theme_combo.currentText())
            self.sb.settings.setValue("auto_save", self.ui.auto_save_checkbox.isChecked())
            self.sb.settings.setValue("save_interval", self.ui.save_interval_spinbox.value())
        
        # Apply theme if supported
        if hasattr(self.sb.loaded_ui.main_window, 'style'):
            theme = "dark" if self.ui.theme_combo.currentText() == "Dark" else "light"
            self.sb.loaded_ui.main_window.style.set(theme=theme)
        
        self.ui.accept()

    def cancel_button(self, widget):
        """Cancel dialog without saving"""
        self.ui.reject()

    def reset_button(self, widget):
        """Reset to default settings"""
        self.ui.theme_combo.setCurrentText("Dark")
        self.ui.auto_save_checkbox.setChecked(True)
        self.ui.save_interval_spinbox.setValue(5)
```

## Custom Widget Development

### Basic Custom Widget
```python
# widgets/enhanced_line_edit.py
from qtpy import QtWidgets, QtCore
from uitk.widgets.mixins import AttributesMixin

class EnhancedLineEdit(QtWidgets.QLineEdit, AttributesMixin):
    # Custom signal
    validationChanged = QtCore.Signal(bool)
    
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        
        # Set CSS class for styling
        self.setProperty("class", self.__class__.__name__)
        
        # Initialize validation
        self.is_valid = True
        self.validation_func = None
        
        # Apply initialization attributes
        self.set_attributes(**kwargs)
        
        # Connect to text changes
        self.textChanged.connect(self._validate)

    def set_validation(self, validation_func):
        """Set custom validation function"""
        self.validation_func = validation_func
        self._validate()

    def _validate(self):
        """Internal validation"""
        text = self.text()
        was_valid = self.is_valid
        
        if self.validation_func:
            self.is_valid = self.validation_func(text)
        else:
            self.is_valid = True
        
        # Update styling
        if self.is_valid:
            self.setStyleSheet("")
        else:
            self.setStyleSheet("border: 2px solid red;")
        
        # Emit signal if validity changed
        if was_valid != self.is_valid:
            self.validationChanged.emit(self.is_valid)

    def get_state(self):
        """Return state for persistence"""
        return {
            "text": self.text(),
            "cursor_position": self.cursorPosition()
        }

    def set_state(self, state):
        """Restore state from saved data"""
        if "text" in state:
            self.setText(state["text"])
        if "cursor_position" in state:
            self.setCursorPosition(state["cursor_position"])
```

### Using Custom Widget in Slots
```python
# slots/validation_example_slots.py
class ValidationExampleSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.validation_example

    def email_edit_init(self, widget):
        """Initialize email validation"""
        widget.setPlaceholderText("Enter email address")
        
        # Set validation if it's our custom widget
        if hasattr(widget, 'set_validation'):
            widget.set_validation(self.validate_email)
            widget.validationChanged.connect(self.on_email_validation_changed)

    def validate_email(self, text):
        """Simple email validation"""
        return "@" in text and "." in text and len(text) > 5

    def on_email_validation_changed(self, is_valid):
        """Handle email validation changes"""
        if hasattr(self.ui, 'submit_button'):
            self.ui.submit_button.setEnabled(is_valid)

    def submit_button_init(self, widget):
        """Initialize submit button"""
        widget.setEnabled(False)  # Start disabled

    def submit_button(self, widget):
        """Handle form submission"""
        email = self.ui.email_edit.text()
        self.sb.message_box(f"Form submitted with email: {email}", "Success")
```

## Event Handling

### Basic Event Handling
```python
# slots/event_example_slots.py
from uitk import Signals
from qtpy import QtCore

class EventExampleSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.event_example

    # Default signal connection (clicked for QPushButton)
    def action_button(self, widget):
        """Handle button click"""
        self.sb.message_box("Button clicked!", "Event")

    # Override to use different signal
    @Signals("pressed")
    def special_button(self, widget):
        """Handle button press (not release)"""
        self.sb.message_box("Button pressed!", "Event")

    # Multiple signals to one handler
    @Signals("textChanged", "returnPressed")
    def search_field(self, widget):
        """Handle both text changes and Enter key"""
        text = widget.text()
        if text:
            self.perform_search(text)

    # No automatic connection
    @Signals()
    def manual_widget(self, widget):
        """This won't be automatically connected"""
        pass

    def manual_widget_init(self, widget):
        """Manually connect signals for full control"""
        widget.clicked.connect(self.handle_manual_click)
        widget.doubleClicked.connect(self.handle_manual_double_click)

    def handle_manual_click(self):
        """Handle manual click"""
        self.sb.message_box("Manual click handler", "Event")

    def handle_manual_double_click(self):
        """Handle manual double click"""
        self.sb.message_box("Manual double click handler", "Event")

    def perform_search(self, text):
        """Perform search operation"""
        # Implement search logic here
        print(f"Searching for: {text}")
```

### Advanced Event Filtering
```python
# slots/advanced_events_slots.py
from uitk.events import EventFactoryFilter
from qtpy import QtCore, QtGui

class AdvancedEventsSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.advanced_events
        
        # Setup event filtering for drawing area
        if hasattr(self.ui, 'drawing_area'):
            self.setup_drawing_events()

    def setup_drawing_events(self):
        """Setup event filtering for drawing"""
        self.drawing_filter = EventFactoryFilter(
            forward_events_to=self,
            event_name_prefix="drawing_",
            event_types={"MousePress", "MouseMove", "MouseRelease"}
        )
        self.drawing_filter.install(self.ui.drawing_area)
        
        self.drawing = False
        self.last_point = None

    def drawing_mousePressEvent(self, event, widget):
        """Handle mouse press in drawing area"""
        self.last_point = event.pos()
        self.drawing = True

    def drawing_mouseMoveEvent(self, event, widget):
        """Handle mouse move in drawing area"""
        if self.drawing and self.last_point:
            # Simple line drawing
            painter = QtGui.QPainter(widget)
            painter.setPen(QtGui.QPen(QtCore.Qt.black, 2))
            painter.drawLine(self.last_point, event.pos())
            self.last_point = event.pos()
            widget.update()

    def drawing_mouseReleaseEvent(self, event, widget):
        """Handle mouse release in drawing area"""
        self.drawing = False

    def clear_button(self, widget):
        """Clear the drawing area"""
        if hasattr(self.ui, 'drawing_area'):
            self.ui.drawing_area.update()
```

## Working with the Example

UITK includes a complete working example. Here's how to use and understand it:

### Running the Example
```python
from uitk import Switchboard
from uitk import example

# Create switchboard with example UI and slots
sb = Switchboard(ui_source=example, slot_source=example.ExampleSlots)
ui = sb.example

# Configure the example UI
ui.set_attributes(WA_TranslucentBackground=True)
ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)

# Apply styling
ui.style.set(theme="dark", style_class="translucentBgWithBorder")

# Show the example
ui.show(pos="screen", app_exec=True)
```

### Understanding the Example Code

The example demonstrates several key UITK features:

1. **Header with Menu**: Shows how to create draggable headers with menus
2. **Button Menus**: Demonstrates buttons with integrated option menus
3. **Signal Override**: Uses `@Signals()` decorator to specify custom signals
4. **Rich Text**: Shows HTML content in message boxes
5. **State Persistence**: Text content is restored when reopening

### Key Patterns from the Example

```python
# Widget initialization
def button_b_init(self, widget):
    widget.menu.setTitle("OPTION MENU")
    widget.menu.add("QRadioButton", setObjectName="radio_a", setText="Option A", setChecked=True)

# Signal override  
@Signals("released")
def button_b(self, widget):
    # Custom signal instead of default 'clicked'
    pass

# Rich text in messages
def checkbox(self, state):
    self.sb.message_box(
        f'CheckBox State: <hl style="color:yellow;">{bool(state)}</hl>'
    )

# Multiple signals
@Signals("textChanged", "returnPressed")
def textedit(self, widget):
    text = widget.toPlainText()
    print(text)
```

This example collection shows UITK's practical capabilities and demonstrates real-world usage patterns. The examples progress from simple concepts to more advanced features, showing how UITK can simplify Qt application development while providing flexibility for complex scenarios.
