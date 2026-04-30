# uitk

**Role**: Qt UI library — reusable widgets, themes, DCC-agnostic.

**Nav**: [← root](../CLAUDE.md) · **Deps**: [pythontk](../pythontk/CLAUDE.md) · **Used by**: [mayatk](../mayatk/CLAUDE.md) · [tentacle](../tentacle/CLAUDE.md)

## Hard rules

- **PySide2 + PySide6 compat.** Use `Qt.py` or the internal abstraction; never import `PySide2` / `PySide6` directly in widget code.
- **snake_case** for Python wrappers. Only use camelCase when overriding Qt methods (e.g. `showEvent`).
- **No side-effects on import.** Widget classes registered via root `DEFAULT_INCLUDE`.

## API surface

Before writing a new helper, **check the registry first** — duplicates undermine the SSoT goal.

- This package: [`API_REGISTRY.md`](API_REGISTRY.md) · [`API_CHANGES.md`](API_CHANGES.md) (diff vs last refresh)
- Upstream: [`pythontk` API](../pythontk/API_REGISTRY.md)
- Cross-package shadows: [`m3trik/docs/API_SHADOWS.md`](../m3trik/docs/API_SHADOWS.md)

Refresh manually: `python m3trik/scripts/generate_api_registry.py uitk` — otherwise auto-refreshed bi-weekly.

## Architecture

- `uitk/widgets/` — reusable widgets.
- `uitk/themes/` — QSS-based style management.
- `uitk/signals.py` — central signal registry.

See [CHANGELOG.md](CHANGELOG.md) for history.
