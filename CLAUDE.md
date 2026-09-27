# uitk

**Role**: generic Qt UI library — reusable widgets, themes; DCC- *and* app-agnostic.

**Nav**: [← root](../CLAUDE.md) · [docs](docs/README.md) · **Deps**: [pythontk](../pythontk/CLAUDE.md) · **Used by**: [mayatk](../mayatk/CLAUDE.md) · [blendertk](../blendertk/CLAUDE.md) · [tentacle](../tentacle/CLAUDE.md) · [extapps](../extapps/CLAUDE.md)

## Hard rules

- **PySide6 through `qtpy` only.** `from qtpy import QtWidgets, QtCore, QtGui` — never import `PySide6` (or `PySide2`) directly in widget code; binding names appear only in the `.ui` compile / Designer helpers that must spell them.
- **snake_case** for Python wrappers. Only use camelCase when overriding Qt methods (e.g. `showEvent`).
- **No application logic.** uitk names no DCC, product or domain: no Maya attribute names, no shot-system models (stores, manifests) or exporters. (The sequencer's shot lane is generic NLE vocabulary; `bridge/` is the generic UI half of pythontk's handoff kit and speaks only its scope/carrier vocabulary, never a product's.) A widget takes the host's vocabulary as data (the sequencer's channel colours arrive from `ptk.Palette.channels()`); DCC-free Qt that carries domain logic splits — model to a pythontk engine, generic widgetry here, thin glue mirrored in the DCC packages ([CODE_STANDARD §14](../m3trik/docs/CODE_STANDARD.md)).
- **No side-effects on import; lazy by default.** Widget classes registered via root `DEFAULT_INCLUDE`; a subpackage `__init__` publishes through `lazy_exports`, never an eager import.

## API surface

[`API_INDEX.md`](API_INDEX.md) · [`API_REGISTRY.md`](API_REGISTRY.md) · [`API_CHANGES.md`](API_CHANGES.md) · shadows [`API_SHADOWS.md`](../m3trik/docs/API_SHADOWS.md) — registry rules in [root](../CLAUDE.md). Upstream: [pythontk](../pythontk/API_INDEX.md).

## Docs

Hand-written docs are ledgered in [`docs/DOCMAP.md`](docs/DOCMAP.md) (status, module→doc coverage, backlog); workflow contract: [`docs/MAINTAINING.md`](docs/MAINTAINING.md). After any docs or public-API change: `python ../m3trik/scripts/check_docs.py --root .` must exit 0 (fix-or-ledger, like the parity sweep).

## Test

```powershell
$env:QT_QPA_PLATFORM = "offscreen"; & python o:\Cloud\Code\_scripts\uitk\test\run_tests.py
```

**`offscreen` is not optional.** Without it the suite runs under the platform's NATIVE style and system palette (`windows11`, dark) and the pixel-rendering tests fail against a widget stack they were never written for -- `TestShortcutOverlay.test_the_card_stays_translucent_under_the_theme` draws a 344x202 card of pale cyan where offscreen/Fusion gives 380x336 of translucent dark. Same tree: 0 failures offscreen, 2 native. The runner warns when the variable is unset.

**Never patch a QObject subclass's attribute with a bare `MagicMock`** (`mock.patch.object(BrowseOption, "browse")`): the next bound-method `connect` on an instance makes PySide build that class's dynamic meta-object from its class dict, and it faults natively on the mock -- no Python frame, no traceback (PySide 6.10.1, backtraced). Use `autospec=True` or `new=<function>`.

## Architecture

- `uitk/widgets/` — reusable widgets. **Placeable widgets' module filenames are frozen public API**: `.ui` files across the ecosystem reference them as custom-widget headers (`uitk.widgets.pushButton`) — never rename or move one (the grandfathered exception to root's `my_class.py` naming rule; windows/popups Designer never places (`designer_spec`) and new modules elsewhere follow it).
- `uitk/widgets/mixins/` — inheritance mixins only. Standalone services live in `uitk/managers/`.
- `uitk/managers/` — service objects (settings, state, values, presets, icons, shortcuts, cursors) consumed compositionally by widgets, handlers, bridge, and Switchboard.
- `uitk/themes/` — QSS theming: `StyleSheet` engine + `style.qss`.
- `uitk/switchboard/` — dynamic UI loader; `slots.py`: `Signals` decorator, `SlotWrapper` dispatch.
- `uitk/handlers/` — Switchboard launchable-entry handlers (UI, external apps).
- `uitk/bridge/` — kind-driven parameter-panel contract shared with the DCC bridges.
- `uitk/loaders/` + `uitk/compile.py` — runtime/compiled `.ui` loading.

See [CHANGELOG.md](CHANGELOG.md) for history.
