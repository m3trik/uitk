# UITK User Guide

This guide covers how to effectively use UITK for Qt application development, from basic concepts to practical implementation patterns.

## Table of Contents
1. [Getting Started](#getting-started)
2. [Project Organization](#project-organization)
3. [Understanding Naming Conventions](#understanding-naming-conventions)
4. [Creating Slot Classes](#creating-slot-classes)
5. [Working with Enhanced Widgets](#working-with-enhanced-widgets)
6. [State Management](#state-management)
7. [Styling and Themes](#styling-and-themes)
8. [Advanced Usage](#advanced-usage)
9. [Best Practices](#best-practices)
10. [Common Issues](#common-issues)

## Getting Started

### Installation
```bash
pip install uitk
```

### Your First UITK Application

1. **Create the project structure:**
```
my_app/
├── ui/
│   └── main_window.ui
├── slots/
│   └── main_window_slots.py
└── main.py
```

2. **Design your UI in Qt Designer:**
   - Create `main_window.ui` with a button named `hello_button`
   - Save to the `ui/` directory

3. **Create the slot class:**
```python
# slots/main_window_slots.py
class MainWindowSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.main_window

    def hello_button(self, widget):
        self.sb.message_box("Hello, UITK!")
```

4. **Create the main application:**
```python
# main.py
from uitk import Switchboard

if __name__ == "__main__":
    sb = Switchboard(
        ui_source="./ui",
        slot_source="./slots"
    )
    
    ui = sb.main_window
    ui.show(app_exec=True)
```

## Project Organization

### Recommended Directory Layout
```
your_project/
├── ui/                     # Qt Designer .ui files
│   ├── main_window.ui
│   ├── settings_dialog.ui
│   └── about_dialog.ui
├── slots/                  # Slot class implementations
│   ├── main_window_slots.py
│   ├── settings_dialog_slots.py
│   └── about_dialog_slots.py
├── widgets/                # Custom widget classes (optional)
│   ├── custom_button.py
│   └── enhanced_table.py
├── resources/              # Icons, stylesheets, etc.
├── main.py                # Application entry point
└── config.py              # Configuration and settings
```

### File Naming Requirements

UITK relies on naming conventions to automatically connect components:

| UI File | Slot Class File | Slot Class Name |
|---------|----------------|-----------------|
| `main_window.ui` | `main_window_slots.py` | `MainWindowSlots` |
| `settings.ui` | `settings_slots.py` | `SettingsSlots` |
| `about.ui` | `about_slots.py` | `AboutSlots` |

## Understanding Naming Conventions

### Widget to Method Mapping

UITK automatically connects widgets to methods based on the widget's `objectName`:

```python
# Widget in UI: objectName="save_button"
# Slot class methods:

def save_button_init(self, widget):
    """Called once during UI initialization"""
    widget.setText("💾 Save")
    widget.setToolTip("Save the document")

def save_button(self, widget):
    """Called when the widget's default signal is emitted"""
    # For QPushButton, default signal is 'clicked'
    self.perform_save()
```

### Default Signals by Widget Type

UITK uses these default signals for automatic connection:

| Widget Type | Default Signal |
|-------------|----------------|
| QPushButton | clicked |
| QCheckBox | toggled |
| QLineEdit | textChanged |
| QTextEdit | textChanged |
| QComboBox | currentIndexChanged |
| QSpinBox | valueChanged |
| QSlider | valueChanged |
| QListWidget | itemClicked |
| QTreeWidget | itemClicked |
| QTableWidget | cellChanged |

### Widget Tags

Add tags to widget object names to control UITK behavior:

```python
# In Qt Designer, set objectName to: "my_button#no_signals"
# Available tags:
# #no_signals    - Skip automatic signal connection
# #no_state      - Don't save/restore widget state  
# (Other tags may be supported but are implementation dependent)
```

## Creating Slot Classes

### Basic Slot Class Structure

```python
class MyDialogSlots:
    def __init__(self, **kwargs):
        # Always include these standard attributes
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.my_dialog
        
        # Initialize any class-specific attributes
        self.data_model = None

    # Initialization methods (called once during UI setup)
    def save_button_init(self, widget):
        """Initialize the save button"""
        widget.setText("💾 Save Document")
        widget.setToolTip("Save the current document")

    # Event handler methods (called when signals are emitted)
    def save_button(self, widget):
        """Handle save button clicks"""
        if self.validate_data():
            self.save_document()
            self.sb.message_box("Document saved!")

    def filename_edit(self, text, widget):
        """Handle filename text changes"""
        # Enable save button only when filename is provided
        self.ui.save_button.setEnabled(bool(text.strip()))

    # Helper methods
    def validate_data(self):
        """Validate form data before saving"""
        return bool(self.ui.filename_edit.text().strip())

    def save_document(self):
        """Implement document saving logic"""
        pass
```

### Signal Override

Use the `@Signals()` decorator to specify different signals:

```python
from uitk import Signals

class AdvancedSlots:
    @Signals("textChanged")
    def search_edit(self, text, widget):
        """Handle real-time search as user types"""
        self.filter_results(text)

    @Signals("clicked", "returnPressed")  
    def submit_action(self, widget):
        """Handle both button click and Enter key"""
        self.submit_form()

    @Signals()  # Empty - no automatic connection
    def custom_widget(self, widget):
        """Handle manually - must connect signals yourself"""
        pass
```

### Accessing Other UI Components

```python
class MainWindowSlots:
    def open_settings(self, widget):
        """Open settings dialog"""
        settings_ui = self.sb.settings_dialog
        if settings_ui.exec_() == QtWidgets.QDialog.Accepted:
            self.apply_settings()

    def apply_settings(self):
        """Apply settings from dialog"""
        # Implementation depends on your settings structure
        pass
```

## Working with Enhanced Widgets

### Enhanced Widget Features

UITK widgets extend standard Qt widgets with additional capabilities:

```python
# Rich text support (where available)
button = PushButton(
    setText='<b>Bold</b> and <i style="color:red;">Red</i> text'
)

# Bulk attribute setting
widget.set_attributes(
    setObjectName="my_widget",
    setText="Hello World", 
    setEnabled=True,
    setVisible=True
)
```

### Creating Custom Widgets

```python
from qtpy import QtWidgets
from uitk.widgets.mixins import AttributesMixin

class CustomLineEdit(QtWidgets.QLineEdit, AttributesMixin):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        
        # Set CSS class for styling
        self.setProperty("class", self.__class__.__name__)
        
        # Apply initialization attributes
        self.set_attributes(**kwargs)

    # Add custom functionality
    def set_error_state(self, is_error=True):
        """Set visual error state"""
        style = "border: 2px solid red;" if is_error else ""
        self.setStyleSheet(style)
```

### Widget Menus

Some UITK widgets support integrated menus:

```python
def export_button_init(self, widget):
    """Setup button with menu options"""
    widget.menu.setTitle("Export Options")
    widget.menu.add("QAction", setText="Export PDF", triggered=self.export_pdf)
    widget.menu.add("QAction", setText="Export Excel", triggered=self.export_excel)

def export_pdf(self):
    """Handle PDF export"""
    pass

def export_excel(self):
    """Handle Excel export"""
    pass
```

## State Management

### Automatic State Persistence

UITK provides basic automatic state saving for common widgets:

```python
# These states are automatically managed:
# - QLineEdit.text()
# - QTextEdit.toPlainText() 
# - QCheckBox.isChecked()
# - QComboBox.currentIndex()
# - QSpinBox.value()
# - Window geometry and position
```

### Controlling State Persistence

```python
class MySlots:
    def temporary_widget_init(self, widget):
        # Disable state saving for this widget
        widget.save_state = False

    def custom_state_widget_init(self, widget):
        # Use custom state key
        widget.state_key = "custom_key"
```

### Custom State Management

For widgets with complex state, implement custom methods:

```python
class CustomWidget(QtWidgets.QWidget):
    def get_state(self):
        """Return state data for persistence"""
        return {
            "custom_property": self.custom_value,
            "view_settings": {
                "zoom_level": self.zoom_level,
                "show_grid": self.show_grid
            }
        }

    def set_state(self, state):
        """Restore from saved state"""
        self.custom_value = state.get("custom_property", "default")
        view_settings = state.get("view_settings", {})
        self.zoom_level = view_settings.get("zoom_level", 1.0)
        self.show_grid = view_settings.get("show_grid", True)
```

## Styling and Themes

### Using Built-in Themes

```python
# Apply dark theme
ui.style.set(theme="dark")

# Apply light theme  
ui.style.set(theme="light")

# Apply theme with style class
ui.style.set(theme="dark", style_class="translucentBgWithBorder")
```

### Available Style Classes

UITK provides some predefined style classes:
- `translucentBgWithBorder`
- `modernDialog` (if implemented)
- `flatButton` (if implemented)

*Note: Style class availability depends on the implementation and may vary.*

## Advanced Usage

### Event Filtering

For complex event handling, UITK provides event filtering:

```python
from uitk.events import EventFactoryFilter

class MySlots:
    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.my_dialog
        
        # Setup event filtering
        self.event_filter = EventFactoryFilter(
            forward_events_to=self,
            event_name_prefix="child_",
            event_types={"MousePress", "KeyPress"}
        )
        
        # Install on specific widgets
        self.event_filter.install([self.ui.input_area])

    def child_mousePressEvent(self, event, widget):
        """Handle mouse press events"""
        print(f"Mouse pressed on {widget.objectName()}")

    def child_keyPressEvent(self, event, widget):
        """Handle key press events"""
        if event.key() == QtCore.Qt.Key_Escape:
            self.ui.close()
```

### Multiple UI Management

```python
class MainSlots:
    def open_child_window(self, widget):
        """Open a child window"""
        child_ui = self.sb.child_dialog
        child_ui.show()

    def show_modal_dialog(self, widget):
        """Show modal dialog"""
        dialog_ui = self.sb.settings_dialog
        result = dialog_ui.exec_()
        if result == QtWidgets.QDialog.Accepted:
            self.handle_dialog_accepted()
```

## Best Practices

### Code Organization

1. **Keep slot methods focused:**
   ```python
   def save_button(self, widget):
       if self.validate_input():
           self.perform_save()
           self.update_ui_state()
   ```

2. **Use initialization methods:**
   ```python
   def complex_widget_init(self, widget):
       # Configure widget during setup
       widget.setEnabled(False)
       widget.setToolTip("Enable after selecting file")
   ```

3. **Organize related functionality:**
   ```python
   class FileManagerSlots:
       def __init__(self, **kwargs):
           self.sb = kwargs.get("switchboard")
           self.ui = self.sb.loaded_ui.file_manager
           self.current_directory = None
           
       # Group related methods together
       def open_file(self, widget): pass
       def save_file(self, widget): pass
       def close_file(self, widget): pass
   ```

### Error Handling

```python
def risky_operation(self, widget):
    """Handle operations that might fail"""
    try:
        result = self.perform_operation()
        self.display_result(result)
    except Exception as e:
        self.sb.message_box(f"Operation failed: {str(e)}", "Error")
        # Log the error for debugging
        print(f"Error in risky_operation: {e}")
```

### Performance Considerations

1. **Lazy initialization:**
   ```python
   def expensive_widget_init(self, widget):
       # Don't load heavy data during init
       widget.data_loaded = False
       
   def expensive_widget(self, widget):
       if not widget.data_loaded:
           self.load_heavy_data(widget)
           widget.data_loaded = True
   ```

2. **Debounce frequent events:**
   ```python
   def search_edit_init(self, widget):
       self.search_timer = QtCore.QTimer()
       self.search_timer.setSingleShot(True)
       self.search_timer.timeout.connect(self.perform_search)

   @Signals("textChanged")
   def search_edit(self, text, widget):
       # Debounce to avoid excessive searches
       self.search_text = text
       self.search_timer.start(300)  # 300ms delay
   ```

## Common Issues

### Widget Not Connecting

**Problem**: Widget signals not connecting to slot methods.

**Solutions**:
- Verify widget `objectName` in Qt Designer matches method name
- Check that slot class is properly named and loaded
- Ensure widget is not tagged with `#no_signals`
- Verify method signature matches expected pattern

### State Not Persisting

**Problem**: Widget states not saved between sessions.

**Solutions**:
- Ensure widget has `objectName` set in Qt Designer
- Check that `save_state` wasn't set to `False`
- Verify widget type is supported for state persistence
- Check file permissions for settings storage

### UI File Not Found

**Problem**: Cannot load UI file.

**Solutions**:
- Verify file path in `ui_source` parameter
- Check file naming matches what you're accessing
- Ensure `.ui` file is properly saved from Qt Designer
- Check file permissions and accessibility

### Slot Class Not Loading

**Problem**: Slot class cannot be imported.

**Solutions**:
- Verify slot class naming convention
- Check for Python syntax errors in slot file
- Ensure slot file is in correct directory
- Verify class name matches file naming pattern

### Rich Text Not Rendering

**Problem**: HTML text appears as plain text.

**Solutions**:
- Verify widget supports rich text (not all do)
- Check HTML syntax in text content
- Ensure you're using UITK widgets that support rich text
- Try with simple HTML tags first

## Debugging Tips

### Enable Debug Logging

```python
sb = Switchboard(
    ui_source="./ui",
    slot_source="./slots", 
    log_level="debug"
)
```

### Check Loaded Components

```python
# Verify registries are populated
print("UI files:", list(sb.registry.ui_registry.keys()))
print("Slot classes:", list(sb.registry.slot_registry.keys()))
print("Loaded UIs:", list(sb.loaded_ui.keys()))
```

### Manual Signal Connection

For troubleshooting, you can manually connect signals:

```python
def manual_connection_init(self, widget):
    # Manual connection for debugging
    widget.clicked.connect(self.manual_connection)

def manual_connection(self):
    print("Manual connection working")
```

This user guide covers the practical aspects of working with UITK based on its actual capabilities. For specific implementation details, refer to the source code and examples provided with the package.
