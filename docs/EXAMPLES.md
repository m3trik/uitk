# Tutorial — Build a Text Editor

A step-by-step walkthrough from empty folder to working application. By the end you'll have a working text editor with file open/save, word wrap, font selection, persistent state, and dark theme.

For recipes and real-world patterns, see the [Cookbook](COOKBOOK.md).

**Nav**: [← README](README.md) · [User Guide](USER_GUIDE.md) · [Slots](SLOTS.md) · [Widgets](WIDGETS.md) · [Cookbook](COOKBOOK.md)

---

## Prerequisites

```bash
pip install uitk PySide6
```

(PySide2 works as well; UITK uses `qtpy` for cross-compatibility.)

---

## Step 1. Project skeleton

```
text_editor/
├── ui/
│   └── editor.ui
├── slots/
│   └── editor_slots.py
└── main.py
```

---

## Step 2. Design the UI

In Qt Designer:

1. New → **Main Window** template.
2. In the central widget, add a `QVBoxLayout`.
3. Add inside the layout:
   - A `QLineEdit` — objectName `txt_path`
   - A `QPushButton` — objectName `btn_open`, text `Open`
   - A `QPushButton` — objectName `btn_save`, text `Save`
   - A `QCheckBox` — objectName `chk_wrap`, text `Wrap text`
   - A `QComboBox` — objectName `cmb_font`
   - A `QTextEdit` — objectName `txt_content`
4. Add a `QStatusBar` with a `QLabel` inside, named `lbl_status`.

Save to `ui/editor.ui`.

> **Tip**: for the polished look, promote `QMainWindow` to `MainWindow` from `uitk.widgets.mainWindow`. UITK wraps it anyway, so the promotion is optional.

---

## Step 3. Write the slots class

```python
# slots/editor_slots.py
import os
from qtpy import QtWidgets, QtGui
from uitk import Signals


class EditorSlots:
    FONTS = ["Consolas", "Courier New", "Menlo", "Monaco", "Source Code Pro"]

    def __init__(self, **kwargs):
        self.sb = kwargs["switchboard"]
        self.ui = self.sb.loaded_ui.editor
        self._current_path = None

    # ---------- path field ----------

    def txt_path_init(self, widget):
        widget.setPlaceholderText("File path...")
        # Enable a clear (x) button beside the field
        widget.option_box.enable_clear()

    def txt_path(self, text, widget):
        # QLineEdit default signal is textChanged(str); validate live.
        if not text:
            widget.set_action_color("inactive")
        elif os.path.isfile(text):
            widget.set_action_color("valid")
        else:
            widget.set_action_color("invalid")

    # ---------- open button ----------

    def btn_open_init(self, widget):
        widget.setToolTip("Ctrl+O to open")
        # Attach a menu for recent files
        widget.menu.add("QPushButton", setText="Recent...",
                        setObjectName="btn_recent")
        widget.menu.btn_recent.clicked.connect(self._show_recent)

    def btn_open(self):
        path = self.sb.file_dialog(file_types="Text (*.txt);;All (*)")
        if not path:
            return
        self._load(path)

    # ---------- save button ----------

    def btn_save(self):
        path = self.ui.txt_path.text()
        if not os.path.isfile(path):
            self.sb.message_box("Open a file first, or type a path.")
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.ui.txt_content.toPlainText())
        self.ui.lbl_status.setText(f"Saved: {path}")

    # ---------- wrap checkbox ----------

    def chk_wrap(self, checked):
        # QCheckBox default is toggled(bool)
        mode = (QtWidgets.QTextEdit.WidgetWidth if checked
                else QtWidgets.QTextEdit.NoWrap)
        self.ui.txt_content.setLineWrapMode(mode)

    # ---------- font combo ----------

    def cmb_font_init(self, widget):
        widget.add(self.FONTS, header="Font")

    def cmb_font(self, index):
        # QComboBox default is currentIndexChanged(int)
        family = self.ui.cmb_font.currentText()
        font = self.ui.txt_content.font()
        font.setFamily(family)
        self.ui.txt_content.setFont(font)

    # ---------- helpers ----------

    def _load(self, path):
        with open(path, encoding="utf-8") as f:
            self.ui.txt_content.setText(f.read())
        self.ui.txt_path.setText(path)
        self.ui.lbl_status.setText(f"Loaded: {path}")
        self._current_path = path

    def _show_recent(self):
        self.sb.message_box("Recent files coming in step 6.")
```

**What's happening:**

- `__init__` receives `switchboard=` via kwargs — we stash it and grab the UI.
- `btn_open_init` runs once when the button registers. It sets the tooltip and attaches a dropdown menu built with `widget.menu.add(...)`. Note the menu items are accessible by `objectName` — `widget.menu.btn_recent.clicked.connect(...)`.
- `btn_open` runs on every click because `clicked` is the default signal for `QPushButton`.
- `txt_path(self, text, widget)` — the first positional is the signal argument (`QLineEdit.textChanged(str)`), `widget` is injected by UITK via introspection.
- `chk_wrap(self, checked)` receives the `toggled(bool)` argument.
- `cmb_font_init` uses the fluent `.add()` method — UITK's `ComboBox` extends the standard Qt combo with header text, batch add, and a richer popup.

---

## Step 4. Bootstrap

```python
# main.py
from uitk import Switchboard

sb = Switchboard(
    ui_source="./ui",
    slot_source="./slots",
)

ui = sb.loaded_ui.editor
ui.setWindowTitle("UITK Text Editor")
ui.style.set(theme="dark", style_class="translucentBgWithBorder")
ui.show(pos="screen", app_exec=True)
```

Run it:

```bash
python main.py
```

You should see a dark-themed editor window. Open a text file, type changes, check word wrap, pick a font. Close and re-open the app — your window size, position, check state, and font selection are restored automatically.

---

## Step 5. Add a menu button to the header

For the frameless-window look, promote your UI's title bar to UITK's `Header`.

In Designer, add a `QWidget` at the top of your central layout and promote it to `Header` (`uitk.widgets.header`) with objectName `header`.

```python
def header_init(self, widget):
    widget.config_buttons("menu", "minimize", "maximize", "hide")
    # Build the menu
    widget.menu.add("QComboBox", setObjectName="cmb_theme",
                    addItems=["Dark", "Light"])
    widget.menu.add("QSeparator")
    widget.menu.add("QPushButton", setText="About",
                    setObjectName="btn_about")
    # Wire the menu items
    widget.menu.cmb_theme.currentTextChanged.connect(
        lambda t: self.ui.style.set(theme=t.lower(),
                                     style_class="translucentBgWithBorder")
    )
    widget.menu.btn_about.clicked.connect(
        lambda: self.sb.message_box("UITK Text Editor v1.0")
    )
```

Then tell the window to be frameless:

```python
# main.py
ui.set_attributes(WA_TranslucentBackground=True)
ui.set_flags(FramelessWindowHint=True)
```

The `UiHandler`'s `DEFAULT_STYLE` does this automatically when you run through a marking menu, but for standalone apps you can opt in explicitly.

---

## Step 6. Recent files with presets

Replace the "Recent coming soon..." with real recent-file tracking using UITK's preset system.

```python
def btn_open_init(self, widget):
    widget.setToolTip("Ctrl+O to open")

    # Swap the menu for a full preset bar
    widget.menu.add_presets = "~/.uitk_editor/recent"
    widget.menu.add_apply_button = True

    # Save the current path as a preset every time we load a new file
    # (Called from _load below.)
```

The preset toolbar gives users Refresh / Save inline and a ⋯ menu with Rename / Open folder / Delete — for free. For "recent files", save the current path as a preset each time:

```python
def _load(self, path):
    with open(path, encoding="utf-8") as f:
        self.ui.txt_content.setText(f.read())
    self.ui.txt_path.setText(path)
    self.ui.lbl_status.setText(f"Loaded: {path}")
    self._current_path = path
    # Auto-save as a timestamped preset
    import time
    self.ui.presets.save(f"{os.path.basename(path)} — {time.strftime('%H:%M:%S')}")
```

---

## Step 7. Keyboard shortcuts

```python
def __init__(self, **kwargs):
    self.sb = kwargs["switchboard"]
    self.ui = self.sb.loaded_ui.editor
    self._current_path = None

    # Register shortcuts
    self.sb.register_shortcut(self.ui, "Ctrl+O", self.btn_open)
    self.sb.register_shortcut(self.ui, "Ctrl+S", self.btn_save)
```

Shortcuts are scoped to the UI — they only fire when the window has focus.

---

## Step 8. Persist custom settings

Suppose you want to remember the last font size across sessions. Use `sb.configurable`:

```python
def __init__(self, **kwargs):
    self.sb = kwargs["switchboard"]
    self.ui = self.sb.loaded_ui.editor

    # Restore persisted font size
    size = self.sb.configurable.editor.font_size.get(11)
    font = self.ui.txt_content.font()
    font.setPointSize(size)
    self.ui.txt_content.setFont(font)

    # React to changes from anywhere
    self.sb.configurable.editor.font_size.changed.connect(self._on_font_size_changed)

def _on_font_size_changed(self, size):
    font = self.ui.txt_content.font()
    font.setPointSize(size)
    self.ui.txt_content.setFont(font)

# Anywhere else — e.g. a preferences dialog — setting this value will fire the callback:
# self.sb.configurable.editor.font_size.set(14)
```

---

## What you learned

| Feature | Mechanism |
|:---|:---|
| Open / save file dialogs | `sb.file_dialog(...)`, `sb.message_box(...)` |
| Auto-wire widgets to methods | `objectName` ↔ slot method name |
| Widget initialization | `*_init(widget)` methods |
| Parameter injection | `(self, text, widget)` — UITK fills `widget` by introspection |
| Live validation | `widget.set_action_color("valid")` with theme palette |
| Popup menus | `widget.menu.add(...)` |
| Clear button | `widget.option_box.enable_clear()` |
| Persistent state | Automatic for widgets with `objectName` + default signal |
| Persistent geometry | `ui.restore_window_size = True` (default) |
| Theme | `ui.style.set(theme="dark", style_class="...")` |
| Frameless window with controls | Promote `QWidget` → `Header`, call `config_buttons(...)` |
| Named preset save/load | `widget.menu.add_presets = True` or `ui.presets.save(name)` |
| Custom config | `sb.configurable.<ns>.<key>.set/get/.changed.connect` |
| Keyboard shortcuts | `sb.register_shortcut(ui, key, callable)` |

---

## Next steps

- [User Guide](USER_GUIDE.md) — comprehensive coverage
- [Cookbook](COOKBOOK.md) — real-world patterns
- [Slots](SLOTS.md) — signal and parameter-injection spec
- [Widgets](WIDGETS.md) — full catalog with APIs
- [Marking Menu](MARKING_MENU.md) — radial gesture shell for DCC tools
- [Architecture](ARCHITECTURE.md) — internals when you need them

---

## The full example

```python
# main.py
from uitk import Switchboard
from slots.editor_slots import EditorSlots

if __name__ == "__main__":
    sb = Switchboard(ui_source="./ui", slot_source=EditorSlots)
    ui = sb.loaded_ui.editor
    ui.setWindowTitle("UITK Text Editor")
    ui.set_attributes(WA_TranslucentBackground=True)
    ui.set_flags(FramelessWindowHint=True)
    ui.style.set(theme="dark", style_class="translucentBgWithBorder")
    ui.show(pos="screen", app_exec=True)
```

Working source ships at [uitk/examples/example.py](../uitk/examples/example.py) — a UITK Package Explorer built entirely with UITK widgets.
