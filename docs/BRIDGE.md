# DCC Bridge

The shared engine behind uitk's "parameterised script panel" tools — panels that render a script template's parameters as widgets, collect the values, format them as target-language literals, and hand the result to an external DCC process (Marmoset, Substance, RizomUV, and any future bridge).

**Nav**: [← README](README.md) · [Widgets](WIDGETS.md) · [Architecture](ARCHITECTURE.md) · [Cookbook](COOKBOOK.md) · [API](API_REFERENCE.md)

## Why it exists

Every "drive an external app from a panel" tool is the same tool wearing a different logo: pick a template, tweak its parameters, press send. Before `uitk.bridge`, each one (marmoset, substance, rizom) re-implemented parameter-widget construction, presets, logging, and template plumbing — and each copy drifted. The bridge subsystem centralizes that machinery once: a per-bridge subclass contributes only the DCC-specific bits (its parameter module, its bridge transport class, its template directory, and the send action), and inherits everything else — including every widget *kind* the shared registry knows about.

## Anatomy of a bridge

The subsystem is five modules under [`uitk/bridge/`](../uitk/bridge/), all re-exported from [`__init__.py`](../uitk/bridge/__init__.py) so consumers write `from uitk.bridge import AttributeSpec, BridgeSlotsBase, ...`:

| Module | Owns |
|:---|:---|
| [`spec.py`](../uitk/bridge/spec.py) | `AttributeSpec` + the `KindHandler` registry (widget build/read/write/change-signal per kind) |
| [`formatters.py`](../uitk/bridge/formatters.py) | Per-target-language value renderers (`python_literal`, `lua_literal`, `js_literal`, `cli_raw`) |
| [`parameters.py`](../uitk/bridge/parameters.py) | Helpers over a per-bridge `PARAMS` dict (`referenced_keys`, `defaults`, `render_context`) |
| [`tooltip.py`](../uitk/bridge/tooltip.py) | Rich-text parameter tooltips + per-template description extraction |
| [`slots.py`](../uitk/bridge/slots.py) | `BridgeSlotsBase` — the slot base class that assembles it all into a panel |

`BridgeParam` is an alias for `AttributeSpec` (kept in `__init__.py` for existing call sites).

### The panel `.ui` contract

`BridgeSlotsBase.__init__` resolves its panel via `self.sb.loaded_ui.<UI_NAME>` and injects rows into a fixed set of widgets the `.ui` file must provide (verified against `blender_bridge.ui` in mayatk):

- `grp_process` — the group box whose layout receives the injected Output Dir row, "Parameters" group, and preset controls.
- `cmb000` — the template combo (populated by the `cmb000_init` Switchboard hook).
- `b000` — the send button; injected widgets are inserted above it, and the subclass implements the `b000` slot.
- `txt000` — the log text browser (`anchorClicked` powers the `action://` links).
- `header` — a uitk `Header`; the default `header_init` builds its Utilities menu.

### Subclass contract

A subclass **must** set / implement (from the `BridgeSlotsBase` docstring and body):

- `UI_NAME` — the loaded-ui attribute name (e.g. `"marmoset_bridge"`). Empty raises `ValueError` at init.
- `PRESETS_ROOT` — per-bridge preset storage root (required unless `make_preset_store` returns a store; then presets are semantic and `PRESETS_ROOT` is unused).
- `params_module` (class attr or property) — a module exposing `PARAMS`, `referenced_keys`, `defaults` (see [Value formatters](#value-formatters-and-the-params-module)).
- `template_dir` (class attr or property) — the per-bridge template directory.
- `make_bridge()` — factory returning the transport instance; called once, lazily, via the `bridge` property. The instance must expose `.logger` and `.send(...)`, optionally `.STARTUP_INFO`. In practice this is a `pythontk.ScriptLaunchBridge` subclass (from `pythontk.core_utils.app_handoff`), whose `send()` runs the shared resolve → preflight → produce → deliver skeleton and inherits `.logger` from `LoggingMixin`.
- `list_template_modes()` — `[(stem, mode), ...]` pairs for the combo.
- `b000()` — the DCC-specific send action.

Optional overrides:

- `select_initial_template_index(pairs)` — bias the starting combo entry (default: index 0).
- `default_output_dir()` — DCC-side fallback for a blank Output Dir (default `""`; mayatk's `MayaBridgeSlotsBase` overrides it to return `EnvUtils.default_artifact_dir()`).
- `REQUIRE_OUTPUT_DIR` — set `False` for bridges with no user-visible output; the row is never built and `require_output_dir()` returns `""`.
- `TEMPLATE_EXTENSION` — `.py` (default) or `.lua` etc.; locates the placeholder source for row visibility and dispatches the description extractor.
- `make_preset_store()` — return a `pythontk.PresetStore` to switch presets to semantic mode (see [Panel services](#panel-services)).
- `_relevant_param_keys()` — which parameter rows are visible for the current selection (default: the `__KEY__` tokens referenced by the active template file). Run-mode panels override this to gate on a mode instead of a template file.
- `_configure_output_dir_options(edit)` — the option-box buttons on the Output Dir field (default: persisted recent-values history + directory browse).
- `template_description(path)` / `format_param_tooltip(spec)` — per-bridge rendering hooks; defaults delegate to [`tooltip.py`](../uitk/bridge/tooltip.py).
- `HEADER_MENU_TITLE` / `HEADER_MENU_ITEMS` / `HELP_SPEC` (or the `header_menu_items()` / `help_spec()` hooks) — header-menu data (see [Panel services](#panel-services)).

### End to end

Init order in `__init__(switchboard)`: Output Dir row (if `REQUIRE_OUTPUT_DIR`) → parameter widgets → preset controls → log redirect + `anchorClicked` wiring → `STARTUP_INFO`. `cmb000_init` then populates the template combo and fires the first `_on_template_changed`, which shows only the rows the template references, re-points the preset dir (widget-state mode only), and logs the template's description.

A concrete walk-through, from `mayatk.env_utils.blender_bridge` (Maya → Blender hand-off): `BlenderBridgeSlots` subclasses `MayaBridgeSlotsBase` (itself a thin `BridgeSlotsBase` subclass adding the Maya output-dir fallback), sets `UI_NAME` / `PRESETS_ROOT` / `LOG_TAG` / `REQUIRE_OUTPUT_DIR = False` / `HELP_SPEC`, points `params_module` at its `parameters.py` and `template_dir` at its `templates/` folder, and implements `b000` — which validates the Maya selection, reads the active `(template, mode)` pair via `_selected_template_mode()`, and calls:

```python
# mayatk.env_utils.blender_bridge.blender_bridge_slots — b000 (abridged)
template, mode = self._selected_template_mode()
with self.sb.progress(text=f"Working: Send to Blender ({template})"):
    self.bridge.send(
        objects=selection,
        template=template,
        mode=mode,
        params=self.collect_param_values(),
    )
```

`collect_param_values()` snapshots every parameter widget (visible or not) through the kind registry; the transport renders the chosen template with those values substituted and launches a fresh Blender on the result.

## Parameter specs and kind handlers

[`spec.py`](../uitk/bridge/spec.py) is the single registry powering both the DCC bridges and `AttributeWindow` — it originally lived at `uitk.widgets.attributeWindow._factory`, and that import path remains as a back-compat shim.

### `AttributeSpec`

A frozen dataclass describing one editable parameter: `key` (required, non-empty — becomes the widget's `objectName`), `label` (display falls back to `key` via `display_label`), `kind`, `default`, `minimum` / `maximum` / `step`, `decimals` (float precision), `choices` (values or `(label, value)` pairs), `tooltip`, and `section` — an optional category label; `BridgeSlotsBase` inserts a titled `Separator` before the first spec of each new section (sections are expected contiguous in iteration order).

`kind` is one of the registered kinds, or `"auto"` (the default) to derive it from `type(default)` via `infer_kind`: `bool` → `"bool"` (checked before `int`, since `bool` subclasses it), `int`, `float`, `str` — and anything else, including lists, deliberately falls through to `"str"`; set `kind="file_list"` explicitly when you want a file picker. The bridges always set `kind` explicitly; `AttributeWindow` builds specs with `AttributeSpec.from_value(key, value)` and lets inference decide.

### `KindHandler` and the registry

A `KindHandler` bundles four callables per kind: `build(spec, parent)`, `read(widget)`, `write(widget, value)`, and either `signal` (the name of a Qt signal on the built widget) or `connect` (a custom `(widget, callback)` wirer for composite widgets whose change signal lives on an inner child). One of the two is required — the constructor raises `ValueError` otherwise — and `connect` wins when both are set.

The module-level functions are the whole consumer API:

- `register_kind(name, handler)` — register a new kind or override an existing one.
- `get_handler(kind)` — look up a handler (`KeyError` listing known kinds if unregistered).
- `make_widget(spec, parent)` — resolve `"auto"`, build the widget, set its `objectName` to `spec.key`, apply the plain tooltip, and stamp the resolved kind on the widget (`_attr_kind` property).
- `read_value(widget)` / `set_value(widget, value)` / `connect_changed(widget, callback)` — operate on any widget produced by `make_widget`, using the stamped kind to find the handler (`ValueError` on an unstamped widget).

Registering a custom kind is one call — exactly how the built-ins register themselves at the bottom of `spec.py`, e.g. `register_kind("path", KindHandler(_build_path, _read_path, _write_path, connect=_connect_path))`. New bridges inherit every registered kind automatically; `_build_param_widgets` builds each row through `make_widget`, so a custom kind needs no slot-side changes.

### Built-in kinds

| Kind | Widget | Value | Change wiring |
|:---|:---|:---|:---|
| `bool` | uitk `CheckBox` with a flipping "On"/"Off" text label | `bool` | `stateChanged` |
| `int` | uitk `SpinBox` (`decimals=0` → `value()` returns `int`), no step buttons | `int` | `valueChanged` |
| `float` | uitk `DoubleSpinBox`, `spec.decimals` or 4 decimals | `float` | `valueChanged` |
| `str` | `QLineEdit` | `str` | `textChanged` |
| `choice` | `QComboBox` from `spec.choices` | the entry's *value* (`currentData` when present, else text) | `currentIndexChanged` |
| `path` | composite: `QLineEdit` + `...` directory-browse button | `str` | custom `connect` on the inner edit's `textChanged` |
| `file_list` | composite: `QListWidget` + Add… / Remove buttons | `list[str]` | custom `connect` on the model's `rowsInserted` / `rowsRemoved` |

Unset `minimum` / `maximum` default to the full 32-bit int range (`int`) or ±1e100 (`float`). `choice` writing matches by `itemData` first, then by text. The `path` and `file_list` containers expose their inner widget as `_line_edit` / `_list_widget`; `BridgeSlotsBase.PATH_LIKE_KINDS` lists these composite kinds so they escape the 19 px height clamp applied to single-line input widgets.

## Value formatters and the PARAMS module

### Formatters

Each formatter in [`formatters.py`](../uitk/bridge/formatters.py) has the signature `formatter(spec, value) -> str` and renders a value as a literal in one target language. Decoupling formatters from the spec lets one `AttributeSpec` serve any number of target languages — the bridge author picks a formatter at render time. All four share one float renderer that honours `spec.decimals` then strips trailing zeros.

| Formatter | Booleans | Strings | Used by |
|:---|:---|:---|:---|
| `python_literal` | `True` / `False` | `repr()` | Marmoset Toolbag `.py` templates, and any `.py` substitution target |
| `lua_literal` | `true` / `false` | passed through bare (Rizom templates quote in the body) | RizomUV `.lua` preset scripts |
| `js_literal` | `true` / `false` | double-quoted, `\` and `"` escaped | Substance Painter RPC payloads |
| `cli_raw` | `true` / `false` | raw token, no quoting; lists join with `os.pathsep` | Substance Painter `--mesh ...` argv flags |

### The per-bridge `parameters` module

[`parameters.py`](../uitk/bridge/parameters.py) defines the helpers that operate over a per-bridge `PARAMS` dict (`{key: AttributeSpec}`, display order = iteration order):

- `referenced_keys(script_text, params)` — the registry keys whose `__KEY__` token appears in the text (placeholder pattern: `__` + upper-case letter + upper-case letters/digits/underscores + `__`). Unregistered tokens are silently ignored — substitution leaves them intact for the target app to complain about. This drives per-template row visibility.
- `defaults(params)` — `{key: default}` for every spec.
- `render_context(values, params, formatter=python_literal)` — formats registered keys through the formatter; unknown keys (bridge-injected tokens like `FBX_PATH`) fall through to `str(value)`. The result feeds `pythontk.StrUtils.replace_delimited` (via `pythontk.core_utils.script_template.render_template` in the `ScriptLaunchBridge` transports).

Each bridge wraps these once with its own `PARAMS` and formatter, so the slot machinery calls `params_module.referenced_keys(text)` without passing the dict. Condensed from `mayatk.env_utils.blender_bridge.parameters`:

```python
from uitk.bridge import (
    AttributeSpec, python_literal,
    referenced_keys as _refkeys, defaults as _defaults, render_context as _render_context,
)

PARAMS = {
    "CLEAR_SCENE": AttributeSpec(
        key="CLEAR_SCENE", label="Clear Scene First", kind="bool", default=False,
        tooltip="Delete the existing scene objects before importing.",
    ),
    # ... one entry per __KEY__ token the templates may reference
}

def referenced_keys(script_text):
    return _refkeys(script_text, PARAMS)

def defaults():
    return _defaults(PARAMS)

def render_context(values):
    return _render_context(values, PARAMS, formatter=python_literal)
```

## Templates: discovery, modes, description

`list_template_modes()` is a subclass hook returning `[(stem, mode), ...]`; the combo shows each pair as `"<template> (<mode>)"`, with the parens elided when `mode` is `""` (single-mode bridges like rizom). `select_initial_template_index` picks the starting entry; the header menu's **Refresh Templates** re-scans via `refresh_templates()`.

The typical implementation delegates to the transport: `pythontk.ScriptLaunchBridge.list_template_modes()` lists `*.ext` files in the template dir (skipping `_`-prefixed stems) and parses each template's top-level `BRIDGE_MODES = (...)` tuple textually — without importing, since pre-substitution templates carry raw `__KEY__` tokens — falling back to `("send_to",)` when absent.

On every combo change, `BridgeSlotsBase`:

1. **Refreshes row visibility** — the default `_relevant_param_keys()` reads `<template><TEMPLATE_EXTENSION>` from `template_dir` and shows only rows whose keys `params_module.referenced_keys` finds in it. Section separators hide when their whole section is hidden; the Parameters group hides when nothing is relevant.
2. **Re-points the preset dir** (widget-state preset mode only) to `PRESETS_ROOT / <template stem>`.
3. **Logs the template's description** — `template_description(path)` (from [`tooltip.py`](../uitk/bridge/tooltip.py)) dispatches on extension: `.py` returns the module docstring via `ast.get_docstring` (parsing works pre-substitution because `__KEY__` tokens are valid Python names); `.lua` returns the contiguous leading `--` comment block; anything else returns `None` (nothing logged).

## Panel services

What every subclass gets for free from [`slots.py`](../uitk/bridge/slots.py):

**Output Dir row** (`REQUIRE_OUTPUT_DIR`, default `True`) — a line edit inserted above the parameters, carrying uitk option-box buttons: a persisted recent-values history plus a directory-browse button by default (`_configure_output_dir_options` hook to swap them). `require_output_dir()` resolves in order: the typed value → `default_output_dir()` (on hit, written back into the field and announced in the log with a clickable link) → log an error, focus the field, return `None` so the caller aborts. With `REQUIRE_OUTPUT_DIR = False` the row is never built and both `resolved_output_dir()` and `require_output_dir()` return `""`, so callers need no guard.

**Presets** — a preset combo plus a "Reset to Defaults" button, driven by `PresetManager` ([`preset_manager.py`](../uitk/widgets/mixins/preset_manager.py)), in one of two modes chosen by `make_preset_store()`:

- *Widget-state mode* (default, `make_preset_store()` → `None`): raw widget snapshots keyed by `objectName`, stored per-template under `PRESETS_ROOT`. Used by the DCC bridges.
- *Semantic mode* (return a `pythontk.PresetStore`): presets are `{param_key: value}` run-templates keyed by spec name, shared with a headless CLI through the same store (built-in + user tiers), template-agnostic. Captured via `collect_param_values`; applied with overlay semantics — unknown keys ignored, absent keys keep current widget values.

Every parameter widget's change signal (via `connect_changed`) re-evaluates the combo's "modified" marker. `_reset_to_defaults` restores each widget to its spec's `default` and abandons the active preset.

**Log panel** — the bridge's logger is piped into `txt000` through the registered `TextEditLogHandler` widget (no-op when unavailable). `action://open?path=...` links in log output open the path in the OS file manager cross-platform — handled inside uitk so panels work as standalone apps; node-based actions (select / reveal in the Maya Outliner) are delegated to mayatk's `UiUtils.dispatch_log_link`, imported lazily so uitk keeps no hard DCC dependency. `STARTUP_INFO` on the bridge class, if declared, is logged once at panel load.

**Header menu** — the default `header_init` builds a titled separator (`HEADER_MENU_TITLE`, default "Utilities"), one button per `HEADER_MENU_ITEMS` entry — `(label, objectName, tooltip, handler_method_name)` tuples, each handler resolved on the slot via `getattr` — and the rich-text help from `HELP_SPEC` (a keyword dict for the tooltip-mixin `fmt()`: `title` / `body` / `steps` / `sections` / `notes`). The stock items are Open Templates Folder / Refresh Templates / Clear Log, backed by the provided `open_templates_folder` / `refresh_templates` / `clear_log` methods (plus the shared `reveal_folder` helper). Subclasses customise by setting data, not code; overriding `header_init` wholesale remains possible.

**Parameter tooltips** — each row's label and widget get `format_param_tooltip(spec)`: rich-text HTML with the spec's title and body plus Type / Range / Step / Default rows and, for `choice` specs, a bullet list of options (`\n` in registry tooltips becomes `<br>` so hand-wrapped text keeps its line breaks).

## Writing a new bridge

1. **Transport** — subclass `pythontk.ScriptLaunchBridge` (declare a `ScriptLaunchSpec`: app discovery, template dir, launch argv), or any class exposing `.logger` and `.send(...)`.
2. **Parameters module** — a `PARAMS` dict of `AttributeSpec`s plus the three thin wrappers over `uitk.bridge.parameters` (snippet above), picking the formatter that matches the template language.
3. **Templates directory** — one script per template, `__KEY__` tokens for every exposed knob, an optional `BRIDGE_MODES` tuple, and a leading docstring / `--` comment block as its description.
4. **`.ui` file** — provide `header`, `grp_process`, `cmb000`, `b000`, `txt000` (copy an existing bridge panel's layout).
5. **Slots class** — subclass `BridgeSlotsBase` (or a DCC-flavored base like mayatk's `MayaBridgeSlotsBase`) and fill in the contract:

```python
# Modeled on mayatk.env_utils.blender_bridge.blender_bridge_slots
class MyBridgeSlots(BridgeSlotsBase):
    UI_NAME = "my_bridge"
    PRESETS_ROOT = Path("mytool/my_bridge")
    LOG_TAG = "my_bridge"

    @property
    def params_module(self):
        return parameters          # the module from step 2

    @property
    def template_dir(self) -> Path:
        return TEMPLATE_DIR        # the directory from step 3

    def make_bridge(self):
        return MyBridge()          # the transport from step 1

    def list_template_modes(self):
        return list_template_modes()

    def b000(self):
        template, mode = self._selected_template_mode()
        self.bridge.send(template=template, mode=mode,
                         params=self.collect_param_values())
```

6. **Custom widget kinds** (only if needed) — `register_kind("my_kind", KindHandler(...))` once at import time; every spec with `kind="my_kind"` then renders through it, in this bridge and every other registry consumer.

## See also

- [WIDGETS.md](WIDGETS.md) — the uitk widgets (`CheckBox`, `SpinBox`, `ComboBox`, option box) the parameter forms are built from
- [SLOTS.md](SLOTS.md) — the Switchboard slot/naming conventions (`cmb000_init`, `b000`) the panel hooks rely on
- [ARCHITECTURE.md](ARCHITECTURE.md) — where slot classes and handlers fit overall
- [DOCMAP.md](DOCMAP.md) — this doc's ledger row and coverage rules
