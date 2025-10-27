# Mode Property Implementation

## Overview
The `mode` property provides backward compatibility and a convenient way to set trigger behavior after initialization, with automatic synchronization between `mode` and `trigger_button`.

## The Problem

After the refactoring, `mode` was no longer stored as an instance variable, which broke:
1. Setting mode after initialization
2. Reading the current mode
3. Backward compatibility with existing code that expected `menu.mode` to work

## The Solution

### Property-Based Synchronization

Both `mode` and `trigger_button` are now **properties** (not plain attributes) with custom getters and setters that keep them synchronized:

```python
@property
def mode(self) -> Optional[str]:
    """Get the current mode."""
    return self._mode

@mode.setter
def mode(self, value: Optional[str]) -> None:
    """Set mode and update trigger_button."""
    self._mode = value
    if value == "context":
        self._trigger_button = QtCore.Qt.RightButton
    elif value == "popup":
        self._trigger_button = QtCore.Qt.LeftButton
    # ... etc

@property
def trigger_button(self) -> Union[QtCore.Qt.MouseButton, tuple, None]:
    """Get the current trigger button(s)."""
    return self._trigger_button

@trigger_button.setter
def trigger_button(self, value: Union[QtCore.Qt.MouseButton, tuple, None]) -> None:
    """Set trigger button and update mode."""
    self._trigger_button = value
    if value == QtCore.Qt.RightButton:
        self._mode = "context"
    elif value == QtCore.Qt.LeftButton:
        self._mode = "popup"
    else:
        self._mode = None  # Custom trigger doesn't map to a mode
```

## Behavior

### Bidirectional Synchronization

#### Setting Mode → Updates Trigger Button
```python
menu = Menu()

menu.mode = "context"
# Result: menu.trigger_button == QtCore.Qt.RightButton

menu.mode = "popup"
# Result: menu.trigger_button == QtCore.Qt.LeftButton

menu.mode = None
# Result: menu.trigger_button == None
```

#### Setting Trigger Button → Updates Mode (When Possible)
```python
menu = Menu()

menu.trigger_button = QtCore.Qt.RightButton
# Result: menu.mode == "context"

menu.trigger_button = QtCore.Qt.LeftButton
# Result: menu.mode == "popup"

menu.trigger_button = QtCore.Qt.MiddleButton
# Result: menu.mode == None (no corresponding mode)

menu.trigger_button = (QtCore.Qt.LeftButton, QtCore.Qt.RightButton)
# Result: menu.mode == None (multiple buttons don't map to a mode)
```

### Mode Mapping

| mode value | trigger_button value | Description |
|-----------|---------------------|-------------|
| `"context"` | `QtCore.Qt.RightButton` | Right-click context menu |
| `"popup"` | `QtCore.Qt.LeftButton` | Left-click popup menu |
| `None` | `None` | Any button can trigger |

### Trigger Button Reverse Mapping

| trigger_button value | mode value | Description |
|---------------------|-----------|-------------|
| `QtCore.Qt.RightButton` | `"context"` | Maps to context mode |
| `QtCore.Qt.LeftButton` | `"popup"` | Maps to popup mode |
| `QtCore.Qt.MiddleButton` | `None` | No corresponding mode |
| `(multiple buttons)` | `None` | No corresponding mode |
| `None` | `None` | Any button |

## Use Cases

### 1. Dynamic Mode Switching
```python
# Create menu
menu = Menu(parent=button)

# Start as context menu (right-click)
menu.mode = "context"
menu.add("QPushButton", setText="Context Action")

# Later, switch to popup (left-click)
menu.mode = "popup"

# Now left-click shows the menu instead
```

### 2. Conditional Behavior
```python
menu = Menu(parent=widget)

if user_is_admin:
    menu.mode = "popup"  # Easy access for admins
else:
    menu.mode = "context"  # Hidden for regular users
```

### 3. Configuration-Driven
```python
# Load from config file
config = {
    "menu_mode": "context",  # or "popup"
}

menu = Menu(parent=button)
menu.mode = config["menu_mode"]
```

### 4. Backward Compatibility
```python
# Old code that expects mode to be readable/writable
menu = Menu(parent=button, mode="context")
current_mode = menu.mode  # Still works!
menu.mode = "popup"  # Still works!
```

### 5. Advanced Trigger Configuration
```python
# Can still use trigger_button directly for advanced cases
menu = Menu(parent=button)

# Use middle mouse button
menu.trigger_button = QtCore.Qt.MiddleButton
# mode automatically becomes None (no mapping)

# Use multiple buttons
menu.trigger_button = (QtCore.Qt.LeftButton, QtCore.Qt.RightButton)
# mode automatically becomes None (no mapping)

# Switch back to a standard mode
menu.mode = "context"
# trigger_button automatically becomes RightButton
```

## Implementation Details

### Internal Storage
```python
# In __init__:
self._mode = None              # Private storage for mode
self._trigger_button = None    # Private storage for trigger_button
```

### Why Properties Instead of Plain Attributes?

**Plain attributes** (before fix):
```python
self.mode = mode  # Just stores the value
self.trigger_button = trigger_button  # Just stores the value
# No synchronization, no validation
```

**Properties** (current implementation):
```python
@property
def mode(self):
    return self._mode

@mode.setter
def mode(self, value):
    self._mode = value
    self._update_trigger_button_from_mode()  # Synchronization!
```

**Benefits:**
- ✅ Automatic synchronization
- ✅ Validation in one place
- ✅ Can add logging/debugging
- ✅ Can evolve without breaking API
- ✅ Maintains backward compatibility

### Initialization Order
```python
def __init__(self, ..., mode=None, trigger_button=None, ...):
    # 1. Initialize private storage
    self._mode = None
    self._trigger_button = None
    
    # 2. Use property setter (triggers synchronization)
    self.trigger_button = self._resolve_trigger_button(mode, trigger_button)
    
    # 3. Store original mode if provided
    if mode is not None:
        self._mode = mode
```

## Testing

### Test Coverage

Run the comprehensive test suite:
```bash
python test_menu_mode_property.py
```

This tests:
- ✅ Setting mode updates trigger_button
- ✅ Setting trigger_button updates mode (when mappable)
- ✅ Custom trigger buttons clear mode
- ✅ Dynamic changes work correctly
- ✅ Round-trip conversions maintain consistency

### Test Results
All 8 automated tests should pass:
1. mode='context' → trigger_button=RightButton ✅
2. mode='popup' → trigger_button=LeftButton ✅
3. trigger_button=RightButton → mode='context' ✅
4. trigger_button=LeftButton → mode='popup' ✅
5. trigger_button=MiddleButton → mode=None ✅
6. Mode can be changed dynamically ✅
7. Trigger button can be changed dynamically ✅
8. Multiple buttons → mode=None ✅

## Edge Cases

### Case 1: Conflicting Initial Values
```python
# What happens if both are set?
menu = Menu(mode="context", trigger_button=QtCore.Qt.LeftButton)

# Resolution: trigger_button takes precedence (via _resolve_trigger_button)
# But mode is still stored if provided
```

### Case 2: Setting Mode to Same Value
```python
menu = Menu(mode="context")
menu.mode = "context"  # Set to same value

# Result: Property setter still runs, but no visible change
# This is idempotent and safe
```

### Case 3: None Values
```python
menu = Menu()
menu.mode = None
menu.trigger_button = None

# Result: Any button can trigger the menu
# Both None values are valid and consistent
```

### Case 4: Invalid Mode Values
```python
menu = Menu()
menu.mode = "invalid"

# Result: _trigger_button remains None (falls through if/elif)
# Menu won't have trigger restrictions
```

## Backward Compatibility

### What Still Works

✅ **Reading mode:**
```python
menu = Menu(mode="context")
print(menu.mode)  # "context"
```

✅ **Writing mode:**
```python
menu = Menu()
menu.mode = "popup"
```

✅ **Mode as constructor parameter:**
```python
menu = Menu(mode="context")
```

✅ **Switching modes:**
```python
menu = Menu(mode="context")
menu.mode = "popup"
```

### What's New

✨ **Can read/write trigger_button:**
```python
menu = Menu()
menu.trigger_button = QtCore.Qt.MiddleButton
print(menu.trigger_button)
```

✨ **Mode and trigger_button stay synchronized:**
```python
menu.mode = "context"
print(menu.trigger_button)  # RightButton

menu.trigger_button = QtCore.Qt.LeftButton
print(menu.mode)  # "popup"
```

## Design Principles

### 1. Transparency
Users don't need to know about the internal synchronization - it "just works."

### 2. Consistency
No matter how you set the values (mode or trigger_button), the behavior is consistent.

### 3. Backward Compatibility
All existing code using `mode` continues to work unchanged.

### 4. Forward Compatibility
New code can use `trigger_button` for more flexibility while still being able to use `mode` when convenient.

### 5. Fail-Safe
Invalid values don't crash - they fall back to reasonable defaults.

## Future Enhancements

### Potential Improvements

1. **Validation:**
```python
@mode.setter
def mode(self, value):
    if value not in ("context", "popup", None):
        raise ValueError(f"Invalid mode: {value}")
    # ...
```

2. **Change Notification:**
```python
mode_changed = QtCore.Signal(str)  # Emit when mode changes
trigger_button_changed = QtCore.Signal(object)  # Emit when button changes
```

3. **Mode Enum:**
```python
class MenuMode(Enum):
    CONTEXT = "context"
    POPUP = "popup"
    CUSTOM = None

menu.mode = MenuMode.CONTEXT
```

## Conclusion

The property-based implementation provides:
- ✅ **Full backward compatibility** with `mode` parameter
- ✅ **Bidirectional synchronization** between mode and trigger_button
- ✅ **Dynamic updates** - change mode/button after initialization
- ✅ **Clean API** - use whichever is more convenient
- ✅ **Type safety** - properties can validate values
- ✅ **Debuggability** - can add logging in setters
- ✅ **Future-proof** - easy to extend without breaking changes

Users can now use `mode` for simple cases and `trigger_button` for advanced cases, with full confidence that they'll stay synchronized.
