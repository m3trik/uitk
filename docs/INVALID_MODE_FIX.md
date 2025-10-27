# Invalid Mode Value Fix

## The Problem

After refactoring, invalid `mode` values (like the legacy `"option"` mode) were falling through validation checks and resulting in `trigger_button=None`, which means **any mouse button** could trigger the menu. This caused issues where:

1. Widgets using `mode="option"` would respond to both left AND right clicks
2. Context menus and popup menus were showing for the wrong button
3. No validation or warning for typos or deprecated values

### Root Cause

The original implementation had two issues:

**Issue 1**: `_resolve_trigger_button()` fell through invalid values
```python
# Old code
if mode == "context":
    return QtCore.Qt.RightButton
elif mode == "popup":
    return QtCore.Qt.LeftButton
# Falls through to:
return None  # ❌ Any button can trigger!
```

**Issue 2**: Mode was stored directly without validation
```python
# Old code in __init__
self.trigger_button = self._resolve_trigger_button(mode, trigger_button)
if mode is not None:
    self._mode = mode  # ❌ Stored without validation!
```

## The Solution

### 1. Added Validation in Mode Property Setter

```python
@mode.setter
def mode(self, value: Optional[str]) -> None:
    """Set mode with validation."""
    # Validate mode value
    valid_modes = ("context", "popup", None)
    if value not in valid_modes:
        self.logger.warning(
            f"Invalid mode '{value}'. Valid values are 'context', 'popup', or None. "
            f"Defaulting to 'popup' (left-click). Use trigger_button parameter for custom behavior."
        )
        value = "popup"  # ✅ Default to safe value
    
    self._mode = value
    
    # Update trigger_button based on validated mode
    if value == "context":
        self._trigger_button = QtCore.Qt.RightButton
    elif value == "popup":
        self._trigger_button = QtCore.Qt.LeftButton
    elif value is None:
        self._trigger_button = None
```

### 2. Fixed Initialization to Use Property Setter

```python
# New code in __init__
if trigger_button is not None:
    # Explicit trigger_button takes precedence
    self.trigger_button = trigger_button  # ✅ Uses property setter
elif mode is not None:
    # Use mode setter which validates
    self.mode = mode  # ✅ Goes through validation!
else:
    # No restrictions
    self._trigger_button = None
    self._mode = None
```

### 3. Added Validation in _resolve_trigger_button (Legacy Path)

```python
def _resolve_trigger_button(self, mode, trigger_button):
    """Resolve trigger button with validation."""
    if trigger_button is not None:
        return trigger_button
    
    if mode == "context":
        return QtCore.Qt.RightButton
    elif mode == "popup":
        return QtCore.Qt.LeftButton
    elif mode is None:
        return None
    else:
        # ✅ Validate and default
        self.logger.warning(f"Invalid mode '{mode}'...")
        return QtCore.Qt.LeftButton  # Safe default
```

## Invalid Modes Fixed

The following invalid mode values are now properly handled:

| Invalid Mode | Old Behavior | New Behavior |
|-------------|--------------|--------------|
| `"option"` | Any button (None) | Left-click (popup) + warning |
| `""` (empty) | Any button (None) | Left-click (popup) + warning |
| `"invalid"` | Any button (None) | Left-click (popup) + warning |
| Typos | Any button (None) | Left-click (popup) + warning |

## Updated Widget Files

All widgets using `mode="option"` have been updated to use `trigger_button=QtCore.Qt.LeftButton`:

1. ✅ **pushButton.py** - `Menu(self, trigger_button=QtCore.Qt.LeftButton, ...)`
2. ✅ **treeWidget.py** - `Menu(self, trigger_button=QtCore.Qt.LeftButton, ...)`
3. ✅ **textEdit.py** - `Menu(self, trigger_button=QtCore.Qt.LeftButton, ...)`
4. ✅ **lineEdit.py** - `Menu(self, trigger_button=QtCore.Qt.LeftButton, ...)` (3 instances)
5. ✅ **label.py** - `Menu(self, trigger_button=QtCore.Qt.LeftButton, ...)`

### Import Addition

Added `QtCore` import to `pushButton.py`:
```python
from qtpy import QtWidgets, QtCore  # ✅ Added QtCore
```

## Validation Behavior

### Valid Modes (No Warning)
```python
menu = Menu(mode="context")  # ✅ No warning
menu = Menu(mode="popup")    # ✅ No warning
menu = Menu(mode=None)       # ✅ No warning
```

### Invalid Modes (Warning + Default)
```python
menu = Menu(mode="option")   # ⚠️  Warning, defaults to 'popup'
menu = Menu(mode="invalid")  # ⚠️  Warning, defaults to 'popup'
menu = Menu(mode="")         # ⚠️  Warning, defaults to 'popup'
```

### Warning Message
```
[WARNING] uitk.widgets.menu.Menu: Invalid mode 'option'. 
Valid values are 'context', 'popup', or None. 
Defaulting to 'popup' (left-click). 
Use trigger_button parameter for custom behavior.
```

## Testing

### Automated Tests

Run `test_menu_invalid_mode.py` for comprehensive validation:

```bash
python test_menu_invalid_mode.py
```

**Test Coverage:**
- ✅ Test 1: `mode="option"` during init → defaults to popup
- ✅ Test 2: `mode="invalid"` after init → defaults to popup  
- ✅ Test 3: `mode="context"` still works correctly
- ✅ Test 4: `mode="popup"` still works correctly
- ✅ Test 5: `mode=""` (empty) → defaults to popup
- ✅ Test 6: `mode="xyz"` (garbage) → defaults to popup

**All 6 tests pass!** ✅

### Manual Testing

The test app shows three buttons:
1. **Test 1**: Created with `mode="option"` → should only respond to LEFT click
2. **Test 2**: Set to `mode="invalid"` → should only respond to LEFT click
3. **Test 3**: Created with `mode="context"` → should only respond to RIGHT click

## Migration Path

### For Code Using mode="option"

**Before:**
```python
menu = Menu(parent, mode="option")  # ❌ Invalid, responds to any button
```

**After (Automatic):**
```python
menu = Menu(parent, mode="option")  # ⚠️  Warning, but works as left-click
```

**Recommended:**
```python
menu = Menu(parent, trigger_button=QtCore.Qt.LeftButton)  # ✅ Explicit, no warning
```

### For New Code

Always use `trigger_button` for clarity:

```python
# Popup menu (left-click)
menu = Menu(parent, trigger_button=QtCore.Qt.LeftButton)

# Context menu (right-click)
menu = Menu(parent, trigger_button=QtCore.Qt.RightButton)

# Multiple buttons
menu = Menu(parent, trigger_button=(QtCore.Qt.LeftButton, QtCore.Qt.RightButton))

# Any button (be explicit!)
menu = Menu(parent, trigger_button=None)
```

## Benefits

### 1. **No More Accidental "Any Button" Menus**
Invalid modes no longer silently allow any button to trigger.

### 2. **Clear Warnings**
Users are notified when using invalid modes with helpful guidance.

### 3. **Safe Defaults**
Invalid values default to 'popup' (left-click), the most common use case.

### 4. **Backward Compatibility**
Old code with `mode="option"` still works (with warning).

### 5. **Forward Guidance**
Warning messages suggest using `trigger_button` for custom behavior.

## Breaking Changes

❌ **None!** All existing code continues to work.

The only difference is:
- Invalid modes that previously triggered on **any button** now trigger on **left button** only
- Warning messages appear in logs for invalid modes

This is actually a **bug fix**, not a breaking change, since "any button" was never the intended behavior for invalid modes.

## Deprecation Path

### Current (Phase 1)
- ✅ Invalid modes logged with warning
- ✅ Default to safe behavior (popup/left-click)
- ✅ Suggest using `trigger_button` parameter

### Future (Phase 2)
- Could raise `ValueError` for invalid modes
- Would force explicit choice of valid mode or trigger_button

### Future (Phase 3)
- Could remove `mode` parameter entirely
- `trigger_button` becomes the only API

## Conclusion

This fix ensures that:
- ✅ Invalid mode values don't silently break behavior
- ✅ Users receive clear warnings about deprecated values
- ✅ Safe defaults prevent unexpected menu triggers
- ✅ All widgets are updated to use proper API
- ✅ Full backward compatibility maintained
- ✅ Clear migration path to new API

The legacy `mode="option"` is now properly rejected and defaults to sensible behavior instead of allowing any button to trigger the menu.
