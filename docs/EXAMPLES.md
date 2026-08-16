# Tutorial — Build a Text Editor

A step-by-step walkthrough from empty folder to working application. By the end you'll have a working text editor with file open/save, word wrap, font selection, persistent state, and dark theme.

For recipes and real-world patterns, see the [Cookbook](COOKBOOK.md).

**Nav**: [← README](README.md) · [User Guide](USER_GUIDE.md) · [Slots](SLOTS.md) · [Widgets](WIDGETS.md) · [Cookbook](COOKBOOK.md)

---

## Prerequisites

```bash
pip install uitk PySide6
```

(UITK uses `qtpy`, so any binding it supports works; this tutorial was verified against PySide6.)

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

1. New → **Main Window** template. (You'll save it as `editor.ui` — the filename stem is the name you access it by: `sb.loaded_ui.editor`.)
2. In the central widget, add a `QVBoxLayout`.
3. Add inside the layout:
   - A `QLineEdit` — objectName `txt_path`
   - A `QPushButton` — objectName `btn_open`, text `Open`
   - A `QPushButton` — objectName `btn_save`, text `Save`
   - A `QCheckBox` — objectName `chk_wrap`, text `Wrap text`
   - A `QComboBox` — objectName `cmb_font`
   - A `QTextEdit` — objectName `txt_content`
   - A `QLabel` — objectName `lbl_status`, text `Ready` — the status line. (Designer can't place widgets inside a `QStatusBar`, so a plain label at the bottom of the layout serves the role.)
4. **Promote the widgets that will use UITK APIs** (right-click → *Promote to…*, enter the class and header, *Add*, *Promote*):

   | Widget | Promoted class | Header |
   |:--|:--|:--|
   | `txt_path` | `LineEdit` | `uitk.widgets.lineEdit` |
   | `btn_open`, `btn_save` | `PushButton` | `uitk.widgets.pushButton` |
   | `cmb_font` | `ComboBox` | `uitk.widgets.comboBox` |

   Promotion is what gives a widget its UITK surface — `widget.menu`, `set_action_color(...)`, the fluent `ComboBox.add(...)`. Unpromoted widgets load as plain Qt classes (`chk_wrap`, `txt_content`, and `lbl_status` stay plain; they don't need UITK APIs here). The `option_box` plugin stack is the one exception — Switchboard patches it onto common Qt widgets, so it works either way.

Save to `ui/editor.ui`.

> **Tip**: the window root itself needs no promotion — Switchboard wraps the `.ui`'s top-level widget in UITK's `MainWindow`, which is where `ui.style`, `ui.show(pos=...)`, and geometry persistence come from.

---

## Step 3. Write the slots class

```python
# slots/editor_slots.py
import os
from qtpy import QtWidgets


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
        path = self.sb.file_dialog(
            file_types=["*.txt"],
            title="Select a text file",
            filter_description="Text",
            allow_multiple=False,
        )
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
        widget.add(self.FONTS)

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
- `sb.file_dialog` takes `file_types` as a list of extension globs (`["*.txt"]`), a `filter_description`, and returns a single path (or `None`) with `allow_multiple=False` — the default returns a list.
- `txt_path(self, text, widget)` — the first positional is the signal argument (`QLineEdit.textChanged(str)`), `widget` is injected by UITK via introspection.
- `chk_wrap(self, checked)` receives the `toggled(bool)` argument.
- `cmb_font_init` uses the fluent `.add()` method — UITK's `ComboBox` batch-adds any iterable, with a richer popup than stock Qt. (Its `header=` option exists but turns the combo into a captioned action menu whose selection resets after each pick — leave it off for a persistent choice like this one.)

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

Relative source paths resolve against `main.py`'s own directory, so run it from anywhere:

```bash
python main.py
```

You should see a dark-themed editor window. Open a text file, type changes, check word wrap, pick a font. Close and re-open the app — your window size, position, check state, and font selection are restored automatically.

---

## Step 5. Add a menu button to the header

For the frameless-window look, promote your UI's title bar to UITK's `Header`.

In Designer, add a `QLabel` at the top of your central layout and promote it to `Header` (`uitk.widgets.header` — base class `QLabel`) with objectName `header`.

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

The `UiHandler`'s `DEFAULT_STYLE` applies these automatically for UIs launched through it (e.g. from a marking menu); for standalone apps you opt in explicitly.

---

## Step 6. Recent files with presets

Replace the "Recent..." placeholder with real recent-file tracking using UITK's preset system.

```python
def btn_open_init(self, widget):
    widget.setToolTip("Ctrl+O to open")

    # Swap the placeholder menu for a full preset bar
    widget.menu.add_presets = True
    widget.menu.add_apply_button = True
    widget.menu.presets.preset_dir = "~/.uitk_editor/recent"
    widget.menu.presets.scope = "window"   # snapshot the editor's widgets
```

The preset bar materializes the first time the menu opens: a preset combo with inline Refresh / Save buttons and a ⋯ menu (Rename / Open folder / Delete) — for free. `scope = "window"` makes each preset capture the whole editor's widget values (path, wrap, font) instead of just the menu's own contents.

For "recent files", save a preset each time a file loads:

```python
def _load(self, path):
    with open(path, encoding="utf-8") as f:
        self.ui.txt_content.setText(f.read())
    self.ui.txt_path.setText(path)
    self.ui.lbl_status.setText(f"Loaded: {path}")
    self._current_path = path
    # One preset per file; duplicates overwrite, so re-opening a file
    # just refreshes its entry.
    self.ui.btn_open.menu.presets.save(
        os.path.splitext(os.path.basename(path))[0]
    )
```

Picking an entry from the preset combo restores that snapshot — path field included. (Preset names become filenames, so punctuation like dots is sanitized to underscores.)

---

## Step 7. Keyboard shortcuts

Decorate the slot methods with `@Shortcut(...)`. When the slots are wired,
`register_slots_shortcuts` scans the class, applies any user overrides from
`ui.settings`, and live-binds them:

```python
from uitk import Shortcut

class EditorSlots:
    @Shortcut("Ctrl+O")
    def btn_open(self):
        ...

    @Shortcut("Ctrl+S")
    def btn_save(self):
        ...
```

The existing method signatures don't change — the decorator only attaches
metadata. Shortcuts are scoped to the UI — they only fire when the window has
focus. For a UI-less command (no owning widget), use `sb.register_command(...)`
+ `sb.set_command_shortcut(...)` instead.

---

## Step 8. Persist custom settings

Suppose you want to remember the last font size across sessions. Use a branch of `sb.configurable` (a `SettingsManager` backed by QSettings):

```python
def __init__(self, **kwargs):
    self.sb = kwargs["switchboard"]
    self.ui = self.sb.loaded_ui.editor

    # One branch object, stashed — reads, writes, and callbacks all
    # go through it.
    self._cfg = self.sb.configurable.branch("editor")

    # Restore persisted font size
    size = self._cfg.font_size.get(11)
    font = self.ui.txt_content.font()
    font.setPointSize(size)
    self.ui.txt_content.setFont(font)

    # React to changes
    self._cfg.font_size.changed.connect(self._on_font_size_changed)

def _on_font_size_changed(self, size):
    font = self.ui.txt_content.font()
    font.setPointSize(size)
    self.ui.txt_content.setFont(font)

# Elsewhere — e.g. a preferences dialog — setting the value through the
# same branch fires the callback:
# self._cfg.font_size.set(14)
```

Change callbacks are registered per manager object, so route writes through the stashed branch — a write from a different `branch("editor")` instance persists the value but won't fire this instance's callback.

---

## What you learned

| Feature | Mechanism |
|:---|:---|
| Open / save file dialogs | `sb.file_dialog(...)`, `sb.message_box(...)` |
| UITK widget APIs in Designer | Promote to `uitk.widgets.*` classes |
| Auto-wire widgets to methods | `objectName` ↔ slot method name |
| Widget initialization | `*_init(widget)` methods |
| Parameter injection | `(self, text, widget)` — UITK fills `widget` by introspection |
| Live validation | `widget.set_action_color("valid")` with theme palette |
| Popup menus | `widget.menu.add(...)` |
| Clear button | `widget.option_box.enable_clear()` |
| Persistent state | Automatic for widgets with `objectName` + default signal |
| Persistent geometry | `ui.restore_window_size = True` (default) |
| Theme | `ui.style.set(theme="dark", style_class="...")` |
| Frameless window with controls | Promote `QLabel` → `Header`, call `config_buttons(...)` |
| Named preset save/load | `widget.menu.add_presets = True`; `menu.presets.save(name)` |
| Custom config | `sb.configurable.branch(ns).key.get/set` + `.changed.connect` |
| Keyboard shortcuts | `@Shortcut("Ctrl+S")` on the slot method |

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

Working source ships at [uitk/examples/example.py](../uitk/examples/example.py) — a package-browser feature tour built entirely with UITK widgets (`python -m uitk.examples.example`).

---

## See also

- [User Guide](USER_GUIDE.md) — comprehensive coverage of the concepts this tutorial touches
- [Cookbook](COOKBOOK.md) — real-world patterns beyond the tutorial scope
- [Slots](SLOTS.md) — the signal and parameter-injection spec behind steps 3 and 7
- [Widgets](WIDGETS.md) — full catalog with APIs, including Designer promotion
- [Marking Menu](MARKING_MENU.md) — radial gesture shell for DCC tools
- [Architecture](ARCHITECTURE.md) — internals when you need them
