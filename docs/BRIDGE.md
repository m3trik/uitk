# DCC Bridge

The shared engine behind uitk's "parameterised script panel" tools — panels that render a script template's parameters as widgets, collect the values, format them as target-language literals, and hand the result to an external DCC process (Marmoset, Substance, RizomUV, and any future bridge).

**Nav**: [← README](README.md) · [Widgets](WIDGETS.md) · [Architecture](ARCHITECTURE.md) · [Cookbook](COOKBOOK.md) · [API](API_REFERENCE.md)

> **Status: stub.** Structure is in place; sections marked with DOC-TODO comments await content verified against `uitk/bridge/`. Task **DOC-10** in [DOCMAP.md](DOCMAP.md#backlog).

## Why it exists

Every "drive an external app from a panel" tool is the same tool wearing a different logo: pick a template, tweak its parameters, press send. Before `uitk.bridge`, each one (marmoset, substance, rizom) re-implemented parameter-widget construction, presets, logging, and template plumbing — and each copy drifted. The bridge subsystem centralizes that machinery once: a per-bridge subclass contributes only the DCC-specific bits (its parameter module, its bridge transport class, its template directory, and the send action), and inherits everything else — including every widget *kind* the shared registry knows about.

## Anatomy of a bridge

`BridgeSlotsBase` (`uitk/bridge/slots.py`) is the slot base class all bridges extend. A subclass supplies:

- `params_module` — exposes `PARAMS`, `referenced_keys`, `defaults`
- a bridge class exposing `.logger`, `.send(...)`, and optionally `.STARTUP_INFO`
- its template directory + `list_template_modes`
- the `b000` action that wires DCC selection and the bridge handoff

<!-- DOC-TODO(DOC-10): Walk one concrete subclass end-to-end (template combo → parameter form → send). Read uitk/bridge/slots.py (BridgeSlotsBase docstring + methods) and one consumer bridge for the wiring. -->

## Parameter specs and kind handlers

<!-- DOC-TODO(DOC-10): Document AttributeSpec and the KindHandler registry — infer_kind, register_kind, make_widget/read_value/set_value/connect_changed — and note the registry is shared with AttributeWindow. Read uitk/bridge/spec.py. -->

## Value formatters

<!-- DOC-TODO(DOC-10): Document the per-target-language formatters (python_literal, lua_literal, js_literal, cli_raw) and render_context. Read uitk/bridge/formatters.py + uitk/bridge/parameters.py. -->

## Panel services (presets, logging, templates)

<!-- DOC-TODO(DOC-10): Document what BridgeSlotsBase provides for free: PresetManager combo + reset, log-panel redirect with action:// URIs, the optional required Output Dir row, STARTUP_INFO, per-template descriptions, HEADER_MENU_ITEMS / HELP_SPEC hooks. Read uitk/bridge/slots.py + uitk/bridge/tooltip.py. -->

## Writing a new bridge

<!-- DOC-TODO(DOC-10): Minimal checklist for adding a bridge (subclass, params module, templates dir, transport class, custom kinds via register_kind). Verify against an existing bridge implementation. -->

## See also

- [WIDGETS.md](WIDGETS.md) — the widgets the parameter forms are built from
- [ARCHITECTURE.md](ARCHITECTURE.md) — where slot classes and handlers fit overall
- [DOCMAP.md](DOCMAP.md) — ledger entry and the DOC-10 task this stub tracks
