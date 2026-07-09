[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![PyPI](https://img.shields.io/pypi/v/uitk.svg)](https://pypi.org/project/uitk/)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide2%20|%20PySide6-green.svg)](https://doc.qt.io/)

# uitk

> **Name it, and it connects.**
> A convention-driven Qt framework that turns Qt Designer files + Python slot classes into working applications with zero glue code.

Design the UI in Qt Designer, name your widgets, write matching Python methods. UITK discovers the files, wires signals to slots, persists state, applies themes, and manages the window lifecycle. When you need control, every convention is overridable.

## Why uitk exists

UITK comes from years of building artist tooling for DCC pipelines (Maya, Blender, 3ds Max), where you don't need one big application — you need *dozens of small ones*. Each traditionally pays the same Qt tax before doing anything useful: load the `.ui`, `findChild()` every widget, `.connect()` every signal, restore and save state, style it, and behave correctly standalone or inside a host app. None of that code is the tool — and hand-rolling it slightly differently each time is how a toolkit of thirty tools becomes thirty apps by thirty authors.

UITK drives the marginal cost of a **well-behaved** tool toward zero:

- **The convention is the wiring.** `btn_save` in Designer connects to `def btn_save(self)` because the names match; UI files map to slot classes, filename tags map to UI hierarchy. What remains in a slot class is only the code that does something.
- **Good behavior is the default.** Every widget persists state, every window remembers geometry, theming and positioning just work — no opt-in. Fifty tools wired one way feel like a single application.
- **DCC-agnostic core, host-aware edges.** Built on `qtpy` (PySide2 / PySide6); runs standalone or hosted in Maya / Blender / 3ds Max via pluggable handlers. Extending UITK — handlers, widgets, mixins — never requires editing it.
- **Escape hatches everywhere.** `@Signals(...)` overrides wiring, handlers override host behavior, every enhancement is opt-out per widget or per UI.

**Fits:** fleets of small-to-medium Designer-based tools — especially DCC-hosted — where consistency and iteration speed beat bespoke UI architecture. **Doesn't:** a single large app with its own hand-rolled UI layer, non-Qt targets, or a workflow without Qt Designer.

### What each subsystem is for

| Subsystem | Intent |
|:---|:---|
| `Switchboard` | The discovery hub — finds UI files and slot classes, wires them, owns registries and settings. One object bootstraps a whole tool fleet. |
| `MainWindow` wrapper | Makes *every* loaded UI well-behaved: lifecycle signals, geometry/state persistence, styling, positioning. |
| Widget enhancements (`.menu`, `.option_box`, …) | Progressive disclosure — advanced options live on the widget that owns them, not in dialog sprawl. |
| Marking menu | Muscle-memory access inside a DCC viewport: an entire toolkit reachable from one held key. |
| Sequencer & editors | An NLE-style timeline widget (clips, keyframes, markers, audio scrub), plus bundled Style / Shortcut / Browser panels on `sb.editors`. |
| Handlers | Host-specific behavior (Maya vs. Blender vs. standalone) without forking the library or the tools. |
| Bridge | Parameterised script panels that drive external DCC processes from one shared form/preset/logging engine. |

## Install

```bash
pip install uitk qtpy PySide6     # standalone — PySide2 works too
python -m uitk.examples.example   # optional: interactive demo of the full feature set
```

<!-- sync:qt-install-note -->
Inside a DCC, install only `uitk qtpy` — the host provides its own Qt binding (uitk deliberately doesn't pull one in).
<!-- /sync:qt-install-note -->

## Quickstart

<!-- sync:quickstart -->
```python
from uitk import Switchboard

class EditorSlots:
    def __init__(self, **kwargs):
        self.sb = kwargs["switchboard"]
        self.ui = self.sb.loaded_ui.editor

    def btn_save_init(self, widget):   # runs once when btn_save registers
        widget.setText("Save")

    def btn_save(self):                # runs on clicked (QPushButton default signal)
        self.sb.message_box("Saved")

sb = Switchboard(ui_source="editor.ui", slot_source=EditorSlots)
sb.loaded_ui.editor.show(pos="screen", app_exec=True)
```

Widget `btn_save` in `editor.ui` is connected to `EditorSlots.btn_save` because the names match.
<!-- /sync:quickstart -->

No `.connect()` calls. No `findChild()`. No manual state restore.

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
| [Docs ledger](docs/DOCMAP.md) | Maintainers — per-doc status, module→doc coverage map, backlog; contract in [MAINTAINING.md](docs/MAINTAINING.md) |

## Used by

- **[tentacle](https://github.com/m3trik/tentacle)** — Maya / Max / Blender artist toolkit. Uses UITK's `MarkingMenu` as a radial gesture shell around per-domain slot classes (`cameras.py`, `selection.py`, `scene.py`, …).
- **[mayatk](https://github.com/m3trik/mayatk)** — Maya utility library. Embeds UITK Switchboards for standalone tools (Channels, Shot Sequencer, Texture Path Editor) with a dual-mode `launch(sb=None)` pattern that works both hosted in tentacle and standalone.

## Contributing

```bash
python -m pytest test/ -v
```

Bug fixes require a failing test in `test/test_*.py` before the fix (issue-driven TDD — see [CLAUDE.md](../CLAUDE.md) at the monorepo root).

Doc changes follow the ledgered workflow in [docs/MAINTAINING.md](docs/MAINTAINING.md); the sweep (`python ../m3trik/scripts/check_docs.py --root .`) must exit 0.

## License

LGPL-3.0-or-later — see [COPYING.LESSER](COPYING.LESSER).
