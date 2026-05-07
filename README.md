[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![PyPI](https://img.shields.io/pypi/v/uitk.svg)](https://pypi.org/project/uitk/)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide2%20|%20PySide6-green.svg)](https://doc.qt.io/)

# uitk

> **Name it, and it connects.**
> A convention-driven Qt framework that turns Qt Designer files + Python slot classes into working applications with zero glue code.

Design the UI in Qt Designer, name your widgets, write matching Python methods. UITK discovers the files, wires signals to slots, persists state, applies themes, and manages the window lifecycle. When you need control, every convention is overridable.

## Install

```bash
pip install uitk
```

## Quickstart

```python
# main.py
from uitk import Switchboard

class EditorSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs["switchboard"]
        self.ui = self.sb.loaded_ui.editor

    def btn_save_init(self, widget):   # runs once on registration
        widget.setText("Save")

    def btn_save(self):                # runs on clicked (the QPushButton default signal)
        self.sb.message_box("Saved")

sb = Switchboard(ui_source="editor.ui", slot_source=EditorSlots)
sb.loaded_ui.editor.show(pos="screen", app_exec=True)
```

No `.connect()` calls. No `findChild()`. No manual state restore. Widget `btn_save` in `editor.ui` is connected to `EditorSlots.btn_save` because the names match.

## Design philosophy

- **Convention over configuration.** Names do the wiring. UI files map to slot classes; widget `objectName`s map to methods; tags (`#submenu`) map to UI hierarchy. Every convention can be overridden with a decorator, attribute, or handler.
- **Composable primitives.** Public APIs take plain values (`str`, `dict`, callable). Widgets gain capabilities through mixins (`.menu`, `.option_box`, `.state`, `.style`) rather than deep inheritance.
- **DCC-agnostic.** Built on `qtpy` for PySide2/PySide6 compatibility. Runs standalone or hosted inside Maya / Blender / 3ds Max via a pluggable handler ecosystem.
- **Extensible where it matters.** Handlers, mixins, and widgets register through `DEFAULT_INCLUDE` and `Switchboard.register()`. Extending UITK does not require editing it.

## Documentation

| Doc | Audience |
|:---|:---|
| [User Guide](docs/USER_GUIDE.md) | Building your first real app — project layout, conventions, patterns |
| [Slots Contract](docs/SLOTS.md) | The slot method spec — naming, signals, `@Signals`, parameter injection, debounce, timeout |
| [Widgets](docs/WIDGETS.md) | Every enhanced widget — `.menu`, `.option_box`, sequencer, editors, marking menu |
| [Marking Menu](docs/MARKING_MENU.md) | Radial gesture menus — bindings, chords, DCC integration |
| [Architecture](docs/ARCHITECTURE.md) | Internals — Switchboard mixins, registries, MainWindow lifecycle, handler ecosystem |
| [Cookbook](docs/COOKBOOK.md) | Recipes from real consumers — hosted-vs-standalone launch, per-domain slots, presets, cross-UI sync |
| [Tutorial](docs/EXAMPLES.md) | Step-by-step walkthrough from empty folder to working app |
| [API Reference](docs/API_REFERENCE.md) | Public signatures — `Switchboard`, `MainWindow`, `Signals`, `UiHandler`, `MarkingMenu` |

## Used by

- **[tentacle](https://github.com/m3trik/tentacle)** — Maya / Max / Blender artist toolkit. Uses UITK's `MarkingMenu` as a radial gesture shell around per-domain slot classes (`cameras.py`, `selection.py`, `scene.py`, …).
- **[mayatk](https://github.com/m3trik/mayatk)** — Maya utility library. Embeds UITK Switchboards for standalone tools (Channels, Shot Sequencer, Texture Path Editor) with a dual-mode `launch(sb=None)` pattern that works both hosted in tentacle and standalone.

## Contributing

```bash
python -m pytest test/ -v
```

Bug fixes require a failing test in `test/test_*.py` before the fix (issue-driven TDD — see [CLAUDE.md](../CLAUDE.md) at the monorepo root).

## License

LGPL-3.0-or-later — see [COPYING.LESSER](COPYING.LESSER).
