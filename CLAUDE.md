# uitk

**Role**: Qt UI library — reusable widgets, themes, DCC-agnostic.

**Nav**: [← root](../CLAUDE.md) · [docs](docs/README.md) · **Deps**: [pythontk](../pythontk/CLAUDE.md) · **Used by**: [mayatk](../mayatk/CLAUDE.md) · [blendertk](../blendertk/CLAUDE.md) · [tentacle](../tentacle/CLAUDE.md) · [extapps](../extapps/CLAUDE.md)

## Hard rules

- **PySide6 through `qtpy` only.** `from qtpy import QtWidgets, QtCore, QtGui` — never import `PySide6` (or `PySide2`) directly in widget code; binding names appear only in the `.ui` compile / Designer helpers that must spell them.
- **snake_case** for Python wrappers. Only use camelCase when overriding Qt methods (e.g. `showEvent`).
- **No side-effects on import.** Widget classes registered via root `DEFAULT_INCLUDE`.

## API surface

[`API_INDEX.md`](API_INDEX.md) · [`API_REGISTRY.md`](API_REGISTRY.md) · [`API_CHANGES.md`](API_CHANGES.md) · shadows [`API_SHADOWS.md`](../m3trik/docs/API_SHADOWS.md) — registry rules in [root](../CLAUDE.md). Upstream: [pythontk](../pythontk/API_INDEX.md).

## Docs

Hand-written docs are ledgered in [`docs/DOCMAP.md`](docs/DOCMAP.md) (status, module→doc coverage, backlog); workflow contract: [`docs/MAINTAINING.md`](docs/MAINTAINING.md). After any docs or public-API change: `python ../m3trik/scripts/check_docs.py --root .` must exit 0 (fix-or-ledger, like the parity sweep).

## Architecture

- `uitk/widgets/` — reusable widgets. **Module filenames are frozen public API**: `.ui` files across the ecosystem reference them as custom-widget headers (`uitk.widgets.pushButton`) — never rename or move a widget module (the grandfathered exception to root's `my_class.py` naming rule; new modules elsewhere follow it).
- `uitk/widgets/mixins/` — inheritance mixins only. Standalone services live in `uitk/managers/`.
- `uitk/managers/` — service objects (settings, state, values, presets, icons, shortcuts) consumed compositionally by widgets, handlers, bridge, and Switchboard.
- `uitk/themes/` — QSS theming: `StyleSheet` engine + `style.qss`.
- `uitk/switchboard/` — dynamic UI loader; `slots.py`: `Signals` decorator, `SlotWrapper` dispatch.
- `uitk/handlers/` — Switchboard launchable-entry handlers (UI, external apps).
- `uitk/bridge/` — kind-driven parameter-panel contract shared with the DCC bridges.
- `uitk/loaders/` + `uitk/compile.py` — runtime/compiled `.ui` loading.

See [CHANGELOG.md](CHANGELOG.md) for history.
