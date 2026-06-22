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

## Architecture

- `uitk/widgets/` — reusable widgets.
- `uitk/themes/` — QSS-based style management.
- `uitk/switchboard/slots.py` — slot wiring: `Signals` decorator, `SlotWrapper` dispatch.

See [CHANGELOG.md](CHANGELOG.md) for history.
