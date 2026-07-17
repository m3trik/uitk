# uitk

**Role**: Qt UI library — reusable widgets, themes, DCC-agnostic.

**Nav**: [← root](../CLAUDE.md) · **Deps**: [pythontk](../pythontk/CLAUDE.md) · **Used by**: [mayatk](../mayatk/CLAUDE.md) · [tentacle](../tentacle/CLAUDE.md)

## Hard rules

- **PySide2 + PySide6 compat.** Use `Qt.py` or the internal abstraction; never import `PySide2` / `PySide6` directly in widget code.
- **snake_case** for Python wrappers. Only use camelCase when overriding Qt methods (e.g. `showEvent`).
- **No side-effects on import.** Widget classes registered via root `DEFAULT_INCLUDE`.

## API surface

**Before adding a helper, check the registry** (navigation rules: [root](../CLAUDE.md)):

- [`API_INDEX.md`](API_INDEX.md) (compact — read first) · [`API_REGISTRY.md`](API_REGISTRY.md) (grep, don't Read whole) · [`API_CHANGES.md`](API_CHANGES.md)
- Upstream: [pythontk](../pythontk/API_INDEX.md)
- Cross-package shadows: [`m3trik/docs/API_SHADOWS.md`](../m3trik/docs/API_SHADOWS.md)

## Docs

Hand-written docs are ledgered in [`docs/DOCMAP.md`](docs/DOCMAP.md) (status, module→doc coverage, backlog); workflow contract: [`docs/MAINTAINING.md`](docs/MAINTAINING.md). After any docs or public-API change: `python ../m3trik/scripts/check_docs.py --root .` must exit 0 (fix-or-ledger, like the parity sweep).

## Architecture

- `uitk/widgets/` — reusable widgets. **Module filenames are frozen public API**: `.ui` files across the ecosystem reference them as custom-widget headers (`uitk.widgets.pushButton`) — never rename or move a widget module.
- `uitk/widgets/mixins/` — inheritance mixins only. Standalone services live in `uitk/managers/`.
- `uitk/managers/` — service objects (settings, state, values, presets, icons, shortcuts) consumed compositionally by widgets, handlers, bridge, and Switchboard.
- `uitk/themes/` — QSS theming: `StyleSheet` engine + `style.qss`.
- `uitk/switchboard/` — dynamic UI loader; `slots.py`: `Signals` decorator, `SlotWrapper` dispatch.
- `uitk/handlers/` — Switchboard launchable-entry handlers (UI, external apps).
- `uitk/bridge/` — kind-driven parameter-panel contract shared with the DCC bridges.
- `uitk/loaders/` + `uitk/compile.py` — runtime/compiled `.ui` loading.

See [CHANGELOG.md](CHANGELOG.md) for history.
