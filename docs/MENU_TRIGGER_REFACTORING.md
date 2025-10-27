# Menu Trigger Button Refactoring

## Overview
This document explains the refactoring of the Menu widget's trigger button logic to improve maintainability, extensibility, and separation of concerns.

## Problems with the Old Design

### 1. **Magic Strings**
```python
# Old way - not self-documenting
menu = Menu(mode="context")  # What does "context" mean?
menu = Menu(mode="popup")    # What does "popup" mean?
```

### 2. **Coupled Logic**
The `mode` parameter implicitly determined which mouse button would trigger the menu, but this relationship was hidden in implementation details:
- `mode="context"` → Right mouse button
- `mode="popup"` → Left mouse button

### 3. **Code Duplication**
The same button-checking logic appeared in two places:
- `eventFilter()` method
- `trigger_from_widget()` method

### 4. **Limited Flexibility**
- No way to support multiple trigger buttons
- No way to support middle mouse button
- Couldn't disable button restrictions

## The New Design

### Core Principles

1. **Single Responsibility**: Each method has one clear purpose
2. **DRY (Don't Repeat Yourself)**: Button logic centralized in one place
3. **Open/Closed**: Easy to extend without modifying existing code
4. **Explicit over Implicit**: Clear parameter names and behavior

### Key Changes

#### 1. New `trigger_button` Parameter
```python
# Explicit single button
menu = Menu(trigger_button=QtCore.Qt.RightButton)

# Multiple buttons
menu = Menu(trigger_button=(QtCore.Qt.LeftButton, QtCore.Qt.RightButton))

# No restrictions (any button)
menu = Menu(trigger_button=None)
```

#### 2. Centralized Logic Methods

##### `_resolve_trigger_button(mode, trigger_button)`
**Purpose**: Handle backward compatibility and parameter resolution.

**Separation of Concern**: Isolates the legacy `mode` to `trigger_button` mapping logic.

```python
def _resolve_trigger_button(self, mode, trigger_button):
    """Resolve trigger button from mode or explicit trigger_button parameter."""
    # New parameter takes precedence
    if trigger_button is not None:
        return trigger_button
    
    # Map legacy mode to button
    if mode == "context":
        return QtCore.Qt.RightButton
    elif mode == "popup":
        return QtCore.Qt.LeftButton
    
    return None  # No restrictions
```

##### `_should_trigger(button)`
**Purpose**: Single source of truth for button validation.

**Separation of Concern**: All button-checking logic in one place.

```python
def _should_trigger(self, button):
    """Check if the given button should trigger the menu."""
    if self.trigger_button is None:
        return True  # Any button allowed
    
    if isinstance(self.trigger_button, QtCore.Qt.MouseButton):
        return button == self.trigger_button  # Single button
    
    if isinstance(self.trigger_button, (tuple, list)):
        return button in self.trigger_button  # Multiple buttons
    
    return False
```

#### 3. Simplified Client Code

##### eventFilter (Before)
```python
def eventFilter(self, widget, event):
    if event.type() == QtCore.QEvent.MouseButtonPress:
        if widget is self.parent():
            if (self.mode == "context" and event.button() == QtCore.Qt.RightButton) or \
               (self.mode == "popup" and event.button() == QtCore.Qt.LeftButton):
                self.setVisible(not self.isVisible())
```

##### eventFilter (After)
```python
def eventFilter(self, widget, event):
    if event.type() == QtCore.QEvent.MouseButtonPress:
        if widget is self.parent():
            if self._should_trigger(event.button()):
                self.setVisible(not self.isVisible())
```

##### trigger_from_widget (Before)
```python
def trigger_from_widget(self, widget=None, *, button=QtCore.Qt.LeftButton):
    if self.prevent_hide:
        return
    
    # Duplicated button checking logic
    if self.mode == "context" and button != QtCore.Qt.RightButton:
        return
    if self.mode == "popup" and button != QtCore.Qt.LeftButton:
        return
    
    # ... rest of method
```

##### trigger_from_widget (After)
```python
def trigger_from_widget(self, widget=None, *, button=QtCore.Qt.LeftButton):
    if self.prevent_hide:
        return
    
    # Uses same validation as eventFilter
    if not self._should_trigger(button):
        return
    
    # ... rest of method
```

## Benefits

### 1. **Maintainability**
- Button logic in one place (`_should_trigger`)
- Changes only need to be made once
- Easier to understand and debug

### 2. **Extensibility**
- Easy to add new button types (e.g., middle button, back button)
- Can support complex trigger combinations
- No need to modify existing code

### 3. **Testability**
- `_should_trigger()` can be unit tested in isolation
- Clear separation between validation and action

### 4. **Backward Compatibility**
- Old `mode` parameter still works
- No breaking changes for existing code
- Smooth migration path

### 5. **Explicit API**
- Clear what each parameter does
- Self-documenting code
- Better IDE autocomplete and type hints

## Migration Guide

### For New Code
Use the explicit `trigger_button` parameter:

```python
# Old way (still works)
menu = Menu(mode="context")

# New way (recommended)
menu = Menu(trigger_button=QtCore.Qt.RightButton)
```

### For Existing Code
No changes required! The old `mode` parameter continues to work:

```python
# This still works exactly as before
menu = Menu(mode="context")      # Right-click
menu = Menu(mode="popup")        # Left-click
```

### Advanced Use Cases

#### Multiple Buttons
```python
menu = Menu(
    trigger_button=(QtCore.Qt.LeftButton, QtCore.Qt.RightButton),
    position="cursorPos"
)
```

#### Any Button
```python
menu = Menu(
    trigger_button=None,  # Any button works
    position="bottom"
)
```

#### Middle Button
```python
menu = Menu(
    trigger_button=QtCore.Qt.MiddleButton,
    position="cursorPos"
)
```

## Testing

Run the test script to see all configurations in action:

```bash
python test_menu_trigger_buttons.py
```

This demonstrates:
- Legacy `mode` parameter backward compatibility
- New `trigger_button` parameter usage
- Multiple button triggers
- Programmatic triggering with validation

## Future Enhancements

The new design makes these enhancements trivial to add:

1. **Keyboard Modifiers**: Trigger on Ctrl+Click, Shift+Click, etc.
2. **Button Combinations**: Trigger on Left+Right simultaneous press
3. **Gesture Support**: Touch gestures, long press, etc.
4. **Custom Validators**: User-provided lambda for complex logic

Example of future enhancement:
```python
# Easy to add in the future
menu = Menu(
    trigger_button=QtCore.Qt.LeftButton,
    trigger_modifiers=QtCore.Qt.ControlModifier,  # Ctrl+Click
    position="cursorPos"
)
```

## Conclusion

This refactoring demonstrates core software engineering principles:
- **DRY**: One source of truth for button validation
- **SRP**: Each method has a single, well-defined purpose
- **OCP**: Open for extension, closed for modification
- **ISP**: Clear, focused interfaces

The result is code that's easier to maintain, extend, test, and understand.
