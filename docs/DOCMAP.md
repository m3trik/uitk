# DOCMAP — the docs ledger

Machine-checked single source of truth for uitk's hand-written documentation: what each doc covers, what code it must stay true to, and what work remains. Format and workflow: [MAINTAINING.md](MAINTAINING.md). Swept by `m3trik/scripts/check_docs.py` (`python ../m3trik/scripts/check_docs.py --root .` from the uitk root — must exit 0).

**Nav**: [← README](README.md) · [Maintaining](MAINTAINING.md)

Legend — **Status**: `current` (verified against code on the Verified date, zero DOC-TODOs) · `needs-verify` (content complete, not yet verified claim-by-claim) · `stub` (skeleton with DOC-TODO markers). **Role**: `landing` (front door, no Nav line required) · `guide` (task-oriented) · `reference` (looks-things-up) · `meta` (about the docs themselves).

## Ledger

| Doc | Role | Status | Verified | Sources of truth |
|:--|:--|:--|:--|:--|
| [../README.md](../README.md) | landing | current | 2026-07-08 | `uitk/__init__.py` · `uitk/examples/example.py` · quickstart must run verbatim |
| [README.md](README.md) | landing | current | 2026-07-08 | the PyPI long-description (`pyproject.toml` readme) · shares sync blocks with ../README.md |
| [USER_GUIDE.md](USER_GUIDE.md) | guide | needs-verify | — | `uitk/switchboard/` · `uitk/widgets/mainWindow.py` · `uitk/managers/settings_manager.py` · `state_manager.py` (DOC-03) |
| [SLOTS.md](SLOTS.md) | reference | needs-verify | — | `uitk/switchboard/slots.py` · `uitk/switchboard/_core.py` (DOC-02) |
| [WIDGETS.md](WIDGETS.md) | reference | current | 2026-07-08 | `uitk/widgets/` · `optionBox/` · `sequencer/` · `editors/` · `delegates/` |
| [MARKING_MENU.md](MARKING_MENU.md) | reference | current | 2026-07-08 | `uitk/widgets/marking_menu/` |
| [ARCHITECTURE.md](ARCHITECTURE.md) | reference | needs-verify | — | `uitk/switchboard/_core.py` · `handlers/` · `loaders/` · `compile.py` · `widgets/mainWindow.py` (DOC-06) |
| [COOKBOOK.md](COOKBOOK.md) | guide | needs-verify | — | consumer repos (mayatk, tentacle) · each recipe must run offscreen where possible (DOC-07) |
| [EXAMPLES.md](EXAMPLES.md) | guide | needs-verify | — | the tutorial project it walks through · `uitk/examples/example.py` (DOC-08) |
| [API_REFERENCE.md](API_REFERENCE.md) | reference | needs-verify | — | `API_INDEX.md` (grep `API_REGISTRY.md` for full signatures) (DOC-09) |
| [BRIDGE.md](BRIDGE.md) | reference | needs-verify | — | `uitk/bridge/slots.py` · `spec.py` · `formatters.py` · `parameters.py` · `tooltip.py` |
| [DOCMAP.md](DOCMAP.md) | meta | current | 2026-07-04 | this file — ledger, coverage map, backlog |
| [MAINTAINING.md](MAINTAINING.md) | meta | current | 2026-07-04 | the maintenance contract and conventions |

## Coverage — module → primary doc home

Every module in `API_INDEX.md` must match exactly one home via longest-prefix match (a prefix ending in `/` matches everything under it). `—` means "deliberately undocumented" and requires a reason. A new module that matches no rule fails the sweep — triage it: assign a home, or opt it out with a reason.

| Prefix | Primary doc | Note |
|:--|:--|:--|
| `_bootstrap.py` | [ARCHITECTURE.md](ARCHITECTURE.md) | package-bootstrap section |
| `bridge/` | [BRIDGE.md](BRIDGE.md) | dedicated subsystem doc |
| `compile.py` | [ARCHITECTURE.md](ARCHITECTURE.md) | §12 UI loading & compilation |
| `events.py` | [API_REFERENCE.md](API_REFERENCE.md) | `uitk.events` section |
| `examples/` | — | demo code; run `python -m uitk.examples.example`, don't document it |
| `managers/registry_manager.py` | [API_REFERENCE.md](API_REFERENCE.md) | FileRegistry / RegistryManager section; `file_manager.py` is its deprecated alias shim |
| `handlers/` | [ARCHITECTURE.md](ARCHITECTURE.md) | handler-ecosystem section |
| `loaders/` | [ARCHITECTURE.md](ARCHITECTURE.md) | §12 UI loading & compilation |
| `managers/` | [WIDGETS.md](WIDGETS.md) | standalone services (settings/state/values/presets/icons/shortcuts), split out of `widgets/mixins/` 2026-07; settings/state user-level detail in USER_GUIDE.md |
| `themes/` | [ARCHITECTURE.md](ARCHITECTURE.md) | theming section (`StyleSheet` + `style.qss`) |
| `switchboard/` | [ARCHITECTURE.md](ARCHITECTURE.md) | slot-contract detail lives in SLOTS.md |
| `widgets/mainWindow.py` | [ARCHITECTURE.md](ARCHITECTURE.md) | MainWindow section; per-property detail in API_REFERENCE.md |
| `widgets/marking_menu/` | [MARKING_MENU.md](MARKING_MENU.md) | dedicated subsystem doc |
| `widgets/` | [WIDGETS.md](WIDGETS.md) | catch-all: catalog, mixins, optionBox, editors, sequencer, delegates |

## Backlog

One task = one unit of maintenance work. Do them in any order; each states its done-condition. Check the box **and** update the doc's ledger row (status + Verified date) in the same edit. Conventions and the verification protocol: [MAINTAINING.md](MAINTAINING.md).

- [x] **DOC-01** (README.md ×2) — Done 2026-07-08: both run verbatim against the published wheel in a clean venv (offscreen). Drift found & fixed: `pip install uitk` alone can't run the quickstart — `qtpy` + a Qt binding are deliberately not dependencies; both Install sections now say so (sync block `qt-install-note`).
- [ ] **DOC-02** (SLOTS.md) — Verify every numbered section against `uitk/switchboard/slots.py` + `_core.py`: class/method resolution order, the default-signals table, parameter injection, `@Signals`, debounce/`@Cancelable`/refresh flags, slot history. Done when: each claim traced to code; row flips to `current`.
- [ ] **DOC-03** (USER_GUIDE.md) — Same claim-by-claim pass for sections 1–13. Done when: row flips to `current`.
- [x] **DOC-04** (WIDGETS.md) — Done 2026-07-08: full claim-by-claim catalog pass (18 drift fixes) + sections added for sequencer, editors, delegates, `WindowPanel`, `TextViewBox`, `Slider`, `ScriptOutput`; `MenuButton` pointered to MARKING_MENU.md.
- [x] **DOC-05** (MARKING_MENU.md) — Done 2026-07-08: full claim-by-claim pass; chord-release, binding persistence, MenuButton nav, and the shortcut-register work (activation key, route targets, `global_shortcuts` editor) now reflected.
- [ ] **DOC-06** (ARCHITECTURE.md) — §12 **UI loading & compilation** added and §§11–14 + §3 verified (2026-07-08). Remaining: claim-by-claim pass of §§1–10 (MainWindow lifecycle, SlotWrapper, state layers, theming, tag depth). Done when: row flips to `current`.
- [ ] **DOC-07** (COOKBOOK.md) — Run each recipe offscreen (`QT_QPA_PLATFORM=offscreen`); mark DCC-only recipes as such. Done when: every recipe is run-verified or explicitly DCC-gated; row flips to `current`.
- [ ] **DOC-08** (EXAMPLES.md) — Follow the tutorial end-to-end from an empty folder. Done when: a fresh run matches every step's stated outcome; row flips to `current`.
- [ ] **DOC-09** (API_REFERENCE.md) — Diff the documented surface against `API_INDEX.md`; add missing public symbols (e.g. `RichTextFormatter`, the delegates, `WindowPanel`, `ShortcutEditor`, `ExternalAppHandler`) or note where they're covered. (2026-07-08: ghost `get_property_from_ui_file` removed; `load_ui` row corrected to the loader-delegate reality.) Done when: no public top-level symbol lacks a home; row flips to `current`.
- [x] **DOC-10** (BRIDGE.md) — Done 2026-07-08: stub fully written from the cited sources; zero DOC-TODOs; row flipped to `needs-verify` (a later claim pass flips it to `current`).
- [x] **DOC-11** — Done 2026-07-08. Decision: the shortcut/command registry lives in **WIDGETS.md § Shortcut & command registry** (inside the editors section), covering `GlobalShortcut`, `ShortcutManager`, `register_command`, host-namespaced persistence, and the `ShortcutEditor`/`global_shortcuts` views. A COOKBOOK recipe remains optional under DOC-07.
