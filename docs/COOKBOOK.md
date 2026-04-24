# Cookbook

Patterns extracted from real UITK consumers — primarily [mayatk](https://github.com/m3trik/mayatk) (Maya utilities) and [tentacle](https://github.com/m3trik/tentacle) (DCC shell). Each recipe shows the setup, the code, and when to use it.

**Nav**: [← README](README.md) · [User Guide](USER_GUIDE.md) · [Slots](SLOTS.md) · [Widgets](WIDGETS.md) · [Marking Menu](MARKING_MENU.md) · [Architecture](ARCHITECTURE.md) · [API](API_REFERENCE.md)

---

## Hosted vs. standalone launch

**Problem**: your tool should run inside the tentacle DCC shell when available, but also work standalone for `__main__` testing or when tentacle isn't installed.

**Solution**: optional `sb` parameter on the launch function. If present, use the caller's Switchboard via the marking menu handler. If absent, build a private one.

```python
# mayatk/node_utils/attributes/attribute_manager/__init__.py

def launch(sb=None, targets=None, filter=None, search=None):
    """Open the Attribute Manager, optionally pre-targeted."""
    if sb is None:
        # Standalone: private Switchboard
        from uitk import Switchboard
        sb = Switchboard(
            ui_source="attribute_manager.ui",
            slot_source=AttributeManagerSlots,
        )
        ui = sb.loaded_ui.attribute_manager
        ui.show(pos="screen")
    else:
        # Hosted: delegate to tentacle's marking menu
        ui = sb.handlers.marking_menu.show("attribute_manager")

    slots = sb.get_slots_instance(ui)
    if slots is not None:
        slots.apply_launch_config(targets=targets, filter=filter, search=search)
    return ui


if __name__ == "__main__":
    launch()
```

**Why this works**: `marking_menu.show()` knows how to reparent, style, and lifecycle-manage a standalone window inside the radial shell. `Switchboard(...)` does the same for a standalone app. The slot class sees the same `self.sb` in both paths.

---

## Per-domain slot splitting

**Problem**: a 5000-line slot class file is unmaintainable, but all slots need access to shared DCC helpers.

**Solution**: one slot class per UI, all inheriting a shared DCC base.

```
tentacle/slots/maya/
├── _slots_maya.py        # class SlotsMaya
├── cameras.py            # class Cameras(SlotsMaya)
├── editors.py            # class Editors(SlotsMaya)
├── selection.py          # class Selection(SlotsMaya)
├── scene.py              # class Scene(SlotsMaya)
├── main.py               # class Main(SlotsMaya)
└── preferences.py        # class Preferences(SlotsMaya)
```

```python
# _slots_maya.py — shared base
class SlotsMaya:
    def __init__(self, switchboard):
        self.sb = switchboard
        # Common Maya setup, shared helpers
```

```python
# selection.py — one class per UI
from uitk import Signals, WidgetComboBox, ToolBox
from tentacle.slots.maya._slots_maya import SlotsMaya

class Selection(SlotsMaya):
    def __init__(self, switchboard):
        super().__init__(switchboard)
        self.ui = self.sb.loaded_ui.selection

    def list000_init(self, widget): ...

    @Signals("on_item_interacted")
    def list000(self, item): ...
```

UITK's class resolution finds `Selection` for `selection.ui` via the [class-name fallback](SLOTS.md#1-class-resolution) (without the `Slots` suffix).

---

## Debounced input with clean value commits

**Problem**: a spinbox that triggers a recalculation — you don't want the slot firing on every arrow-click, and you definitely don't want it firing mid-keystroke with a half-typed value.

**Solution**: combine `widget.debounce` with `setKeyboardTracking(False)`.

```python
class ShotsController:
    def __init__(self, slots_instance):
        self.ui = slots_instance.ui

        for name in ("spn_shot_start", "spn_shot_end"):
            w = getattr(self.ui, name, None)
            if w is not None:
                w.debounce = 400                 # coalesce rapid clicks
                w.setKeyboardTracking(False)     # no mid-edit valueChanged
```

`setKeyboardTracking(False)` makes the spinbox only emit `valueChanged` on commit (Enter / focus loss / arrow click), not on every keystroke. Without it, clearing "100" to retype "200" emits `valueChanged(0)` mid-edit. See [mayatk shots_slots.py:63-73](https://github.com/m3trik/mayatk/blob/main/mayatk/anim_utils/shots/shots_slots.py#L63-L73) for the real scenario this guards against.

---

## Cross-UI widget sync

**Problem**: `main.ui` and `main#submenu.ui` both have a `chk_hidden` checkbox. Toggling one should update the other.

**Solution**: nothing. UITK does it automatically via [MainWindow.sync_widget_values](../uitk/widgets/mainWindow.py) — when a widget's default signal fires, the value is propagated to same-named widgets in all tag-related UIs (via `get_ui_relatives(upstream=True, downstream=True)`).

The only requirements:
- Same `objectName` across UIs.
- UIs share a base name (e.g. `main` / `main#submenu`).
- `widget.restore_state` remains `True` (default).

---

## Refresh-on-show for environment-sensitive UIs

**Problem**: a workspace browser list should reflect the current working folder, not a snapshot from app launch.

**Solution**: `widget.refresh_on_show = True` in `*_init` — re-runs the init on every show.

```python
def list000_init(self, widget):
    if not widget.is_initialized:
        widget.refresh_on_show = True

    widget.clear()
    workspace = mtk.get_env_info("workspace_dir")
    if not workspace or not os.path.isdir(workspace):
        widget.setVisible(False)
        return

    w = widget.add(workspace)
    self._populate_dir_sublist(w.sublist, workspace, max_depth=2)
    widget.setVisible(True)
```

From [tentacle main.py](https://github.com/m3trik/tentacle/blob/main/tentacle/slots/maya/main.py).

---

## Per-widget slot timeouts

**Problem**: a "Render All" button might take 5 minutes. The user should see feedback and be able to cancel.

**Solution**: `widget.slot_timeout = 300.0`. UITK shows a progress indicator via `ptk.ExecutionMonitor` and listens for Esc to cancel.

```python
def btn_render_init(self, widget):
    widget.slot_timeout = 300.0

def btn_render(self):
    for frame in range(1, 241):
        render_frame(frame)   # user can press Esc to abort
```

Or UI-wide:
```python
ui.default_slot_timeout = 360.0   # applies to all slots unless widget overrides
```

Implementation in [SlotWrapper._invoke](../uitk/widgets/mixins/switchboard_slots.py).

---

## Presets — named value sets

**Problem**: let users save/load the current combination of N widgets' values by name.

**Solution**: `widget.menu.add_presets = True` on any widget's menu enables a preset bar (combo + save + load + delete). Or use `PresetManager` directly.

### Menu-embedded (zero ceremony)

```python
def btn_options_init(self, widget):
    widget.menu.add_presets = True                   # default dir (auto)
    # or:
    widget.menu.add_presets = "~/.myapp/presets"     # custom dir
```

### Programmatic

```python
# Standalone, with explicit widget list
from uitk.widgets.mixins.preset_manager import PresetManager

mgr = PresetManager.from_widgets(
    preset_dir="~/.myapp/presets",
    widgets=[self.ui.chk_a, self.ui.spn_b, self.ui.cmb_c],
)
mgr.save("my_preset")
mgr.load("my_preset")
```

### MainWindow-scoped

```python
ui.presets.save("default")
ui.presets.load("default")
ui.presets.list_presets()
```

Files are flat JSON — human-editable.

---

## Custom handler

**Problem**: you want a DCC-specific window behavior (e.g. docking into Maya's workspace) without forking UITK.

**Solution**: subclass `UiHandler`, register it at construction.

```python
from uitk.handlers.ui_handler import UiHandler

class MayaUiHandler(UiHandler):
    DEFAULT_STYLE = {
        **UiHandler.DEFAULT_STYLE,
        "flags": {"FramelessWindowHint": True, "WindowStaysOnTopHint": True},
    }

    def show(self, ui, pos=None, force=False, **kwargs):
        # Maya-specific: register as workspace control
        import maya.cmds as cmds
        if not cmds.workspaceControl(ui.objectName(), q=True, exists=True):
            cmds.workspaceControl(ui.objectName(), ...)
        return super().show(ui, pos=pos, force=force, **kwargs)


# Wire in:
sb = Switchboard(
    ui_source="./ui",
    slot_source="./slots",
    handlers={"ui": MayaUiHandler},
)
```

Access from slots: `self.sb.handlers.ui.show(...)`. Persistent config lives at `sb.configurable.ui.*`.

---

## Debounced search field

**Problem**: live search as the user types. You want to filter as they type but not hammer the filter function on every keystroke.

**Solution**: default signal for `QLineEdit` is `textChanged` — combine with `debounce`.

```python
def txt_search_init(self, widget):
    widget.debounce = 250
    widget.setPlaceholderText("Search...")

def txt_search(self, text, widget):
    self._run_filter(text)   # only fires 250ms after last keystroke
```

For Enter-to-submit (ignoring `textChanged`):
```python
@Signals("returnPressed")
def txt_search(self, widget):
    self._run_filter(widget.text())
```

---

## Option box with BrowseOption

**Problem**: a path input that should have a "..." button opening a file dialog.

**Solution**: `BrowseOption` plugin.

```python
from uitk.widgets.optionBox.options.browse import BrowseOption
from uitk.widgets.optionBox import OptionBox

def txt_file_path_init(self, widget):
    browse = BrowseOption(
        callback=lambda: self.sb.file_dialog(file_types="Audio (*.wav *.mp3)"),
        icon="folder",
    )
    container = OptionBox(options=[browse]).wrap(widget)
    # container goes into your layout in the .ui file, or add it dynamically
```

Shorthand via the auto-patched manager:
```python
def txt_file_path_init(self, widget):
    widget.option_box.set_action(
        lambda: self.sb.file_dialog(file_types="Audio (*)"),
        icon="folder",
    )
```

---

## Dynamic submenu populated from state

**Problem**: a right-click menu on a tree item with options that depend on what's selected.

**Solution**: `ContextMenuOption` or use `widget.menu` with late-bound callbacks.

```python
def tree_nodes_init(self, widget):
    widget.menu.trigger_button = "right"
    widget.menu.add("QPushButton", setText="Rename", setObjectName="btn_rename")
    widget.menu.add("QPushButton", setText="Delete", setObjectName="btn_delete")
    widget.menu.btn_rename.clicked.connect(self._rename_selected)
    widget.menu.btn_delete.clicked.connect(self._delete_selected)

    # Show/hide items based on selection before opening:
    widget.menu.on_item_added.connect(self._sync_menu_state)

def _sync_menu_state(self, _):
    item = self.ui.tree_nodes.currentItem()
    self.ui.tree_nodes.menu.btn_delete.setEnabled(
        item is not None and item.parent() is not None   # can't delete root
    )
```

---

## Log viewer inside the UI

**Problem**: route Python `logging` into a `TextEdit` in the running UI, color-coded by level.

**Solution**: `TextEditLogHandler`.

```python
import logging
from uitk.widgets.textEditLogHandler import TextEditLogHandler

class EditorSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs["switchboard"]
        self.ui = self.sb.loaded_ui.editor
        self._setup_logger()

    def _setup_logger(self):
        self.logger = logging.getLogger("my_app")
        self.logger.handlers.clear()
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(TextEditLogHandler(self.ui.txt_log))
```

The handler writes HTML with palette colors matching the active theme.

---

## Persistent config with live reaction

**Problem**: a setting that multiple UIs read, and all UIs should update when it changes.

**Solution**: `sb.configurable` namespaces with `.changed.connect()`.

```python
class EditorSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs["switchboard"]
        self.ui = self.sb.loaded_ui.editor

        # React to theme changes globally
        self.sb.configurable.app.theme.changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, theme):
        self.ui.style.set(theme=theme)

    def btn_dark_mode(self):
        self.sb.configurable.app.theme.set("dark")   # fires .changed in every listener
```

Values are persisted to QSettings automatically. No explicit save / load calls.

---

## Marking menu recipes

### Starting a bare marking menu (Maya)

```python
from uitk import MarkingMenu
import mayatk as mtk

mm = MarkingMenu(
    parent=mtk.get_main_window(),
    ui_source="./ui",
    slot_source="./slots",
    bindings={"Key_F12": "main#startmenu"},
)
mm.show()   # installs the global shortcut and waits
```

### Adding a standalone launcher button

In the startmenu UI, promote a `QPushButton` with:
- `objectName`: `i`
- `accessibleName`: `texture_editor`  (the standalone UI name)

Hover → shows submenu if one exists. Click → launches the standalone window and dismisses the marking menu.

### Launching a standalone UI from a regular slot

```python
class CamerasSlots(SlotsMaya):
    def btn_texture_editor(self, widget):
        self.sb.handlers.marking_menu.show("texture_editor")
```

Dismisses the radial overlay, shows the standalone window with `UiHandler` styling applied.

### Customizing bindings at runtime

```python
# Persisted in sb.configurable.marking_menu_bindings
mm.bindings = {
    "Key_F11":                "mytools#startmenu",
    "Key_F11|LeftButton":     "render#startmenu",
}
# MarkingMenu.bindings.setter triggers _build_bindings via the changed signal
```

---

## Packaging tips

- If you ship UIs + slots from a Python package (not filesystem paths), pass the module directly:
  ```python
  import my_app.ui
  import my_app.slots
  sb = Switchboard(ui_source=my_app.ui, slot_source=my_app.slots)
  ```
  UITK resolves module paths via `inspect.getfile` / `__file__`.

- `MANIFEST.in` must include `recursive-include my_app *.ui` for UIs to ship.

- Setuptools `package-data` in `pyproject.toml`:
  ```toml
  [tool.setuptools.package-data]
  "my_app" = ["*.ui", "*.json"]
  ```

---

## See also

- [User Guide](USER_GUIDE.md) — concepts used in every recipe
- [Slots](SLOTS.md) — the contract these recipes build on
- [Widgets](WIDGETS.md) — full widget reference
- [Marking Menu](MARKING_MENU.md) — the radial menu subsystem
