[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![PyPI](https://img.shields.io/pypi/v/uitk.svg)](https://pypi.org/project/uitk/)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide2%20|%20PySide6-green.svg)](https://doc.qt.io/)

# uitk

> **Name it, and it connects.**
> A convention-driven Qt framework that turns Qt Designer files + Python slot classes into working applications with zero glue code.

Design the UI in Qt Designer, name your widgets, write matching Python methods. UITK discovers the files, wires signals to slots, persists state, applies themes, and manages the window lifecycle. When you need control, every convention is overridable.

## Why uitk exists

UITK comes from years of building artist tooling for DCC pipelines (Maya, Blender, 3ds Max). That environment produces a particular problem: you don't need one big application — you need *dozens of small ones*, and each traditionally pays the same Qt tax before it does anything useful: load the `.ui` file, `findChild()` every widget, `.connect()` every signal, restore last-used values, save them on close, style it to match the pipeline, and behave correctly whether it floats standalone or lives inside a host app.

None of that code is the tool. It's the same two hundred lines, slightly different every time — and *slightly different* is the killer: tools drift, state persistence gets skipped because it's tedious, and a toolkit of thirty tools feels like thirty apps by thirty authors.

UITK's intent is to drive the marginal cost of a **well-behaved** tool toward zero:

- **The convention is the wiring.** `btn_save` in Designer connects to `def btn_save(self)` because the names match; UI files map to slot classes, tags (`#submenu`) map to UI hierarchy. What remains in your slot class is only the code that does something.
- **Good behavior is the default, not a feature.** Every widget persists its state, every window remembers geometry, theming and positioning just work — no opt-in. A tool built in ten minutes behaves like one built in a week.
- **One convention, many tools.** Because every tool is wired the same way, fifty tools feel like one application — and any maintainer can open any slot class and already know where everything is.
- **Composable primitives.** Public APIs take plain values (`str`, `dict`, callable); widgets gain capabilities through mixins (`.menu`, `.option_box`, `.state`, `.style`) rather than deep inheritance.
- **DCC-agnostic core.** Built on `qtpy` (PySide2 / PySide6); runs standalone or hosted inside Maya / Blender / 3ds Max via a pluggable handler ecosystem. Extending UITK — handlers, widgets, mixins via `DEFAULT_INCLUDE` and `Switchboard.register()` — never requires editing it.
- **Escape hatches everywhere.** Conventions are defaults, not walls: `@Signals(...)` overrides wiring, handlers override host behavior, every enhancement is opt-out per widget or per UI.

**When it fits:** fleets of small-to-medium Designer-based tools — especially hosted in DCCs — where consistency and iteration speed matter more than bespoke UI architecture. **When it doesn't:** a single large app with its own hand-rolled UI layer, non-Qt targets, or a workflow without Qt Designer; the conventions pay for themselves across a fleet, not a one-off.

### What each subsystem is for

| Subsystem | Intent |
|:---|:---|
| `Switchboard` | The discovery hub — finds UI files and slot classes, wires them, owns registries and settings. One object bootstraps a whole tool fleet. |
| `MainWindow` wrapper | Makes *every* loaded UI well-behaved: lifecycle signals, geometry/state persistence, styling, positioning. |
| Widget enhancements (`.menu`, `.option_box`, …) | Progressive disclosure — advanced options live on the widget that owns them, not in dialog sprawl. |
| Marking menu | Muscle-memory access inside a DCC viewport: an entire toolkit reachable from one held key. |
| Handlers | Host-specific behavior (Maya vs. Blender vs. standalone) without forking the library or the tools. |
| Bridge | Parameterised script panels that drive external DCC processes from one shared form/preset/logging engine. |

## Install

```bash
pip install uitk
```

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
