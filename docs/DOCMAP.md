# DOCMAP — the docs ledger

Machine-checked single source of truth for uitk's hand-written documentation: what each doc covers, what code it must stay true to, and what work remains. Format and workflow: [MAINTAINING.md](MAINTAINING.md). Swept by `m3trik/scripts/check_docs.py` (`python ../m3trik/scripts/check_docs.py --root .` from the uitk root — must exit 0).

**Nav**: [← README](README.md) · [Maintaining](MAINTAINING.md)

Legend — **Status**: `current` (verified against code on the Verified date, zero DOC-TODOs) · `needs-verify` (content complete, not yet verified claim-by-claim) · `stub` (skeleton with DOC-TODO markers). **Role**: `landing` (front door, no Nav line required) · `guide` (task-oriented) · `reference` (looks-things-up) · `meta` (about the docs themselves).

## Ledger

| Doc | Role | Status | Verified | Sources of truth |
|:--|:--|:--|:--|:--|
| [../README.md](../README.md) | landing | current | 2026-07-08 | `uitk/__init__.py` · `uitk/examples/example.py` · quickstart must run verbatim |
| [README.md](README.md) | landing | current | 2026-07-08 | the PyPI long-description (`pyproject.toml` readme) · shares sync blocks with ../README.md |
| [USER_GUIDE.md](USER_GUIDE.md) | guide | current | 2026-08-14 | `uitk/switchboard/` · `uitk/widgets/mainWindow.py` · `uitk/managers/settings_manager.py` · `state_manager.py` |
| [SLOTS.md](SLOTS.md) | reference | current | 2026-08-14 | `uitk/switchboard/slots.py` · `uitk/switchboard/_core.py` |
| [WIDGETS.md](WIDGETS.md) | reference | current | 2026-07-08 | `uitk/widgets/` · `optionBox/` · `sequencer/` · `editors/` · `delegates/` |
| [MARKING_MENU.md](MARKING_MENU.md) | reference | current | 2026-07-08 | `uitk/widgets/marking_menu/` |
| [ARCHITECTURE.md](ARCHITECTURE.md) | reference | current | 2026-08-14 | `uitk/switchboard/_core.py` · `handlers/` · `loaders/` · `compile.py` · `widgets/mainWindow.py` |
| [COOKBOOK.md](COOKBOOK.md) | guide | current | 2026-08-14 | consumer repos (mayatk, tentacle) · each recipe must run offscreen where possible |
| [EXAMPLES.md](EXAMPLES.md) | guide | current | 2026-08-14 | the tutorial project it walks through · `uitk/examples/example.py` |
| [API_REFERENCE.md](API_REFERENCE.md) | reference | current | 2026-08-14 | `API_INDEX.md` (grep `API_REGISTRY.md` for full signatures) |
| [BRIDGE.md](BRIDGE.md) | reference | current | 2026-08-16 | `uitk/bridge/slots.py` · `spec.py` · `formatters.py` · `parameters.py` · `tooltip.py` |
| [DOCMAP.md](DOCMAP.md) | meta | current | 2026-07-04 | this file — ledger, coverage map, backlog |
| [MAINTAINING.md](MAINTAINING.md) | meta | current | 2026-07-04 | the maintenance contract and conventions |

## Coverage — module → primary doc home

Every module in `API_INDEX.md` must match exactly one home via longest-prefix match (a prefix ending in `/` matches everything under it). `—` means "deliberately undocumented" and requires a reason. A new module that matches no rule fails the sweep — triage it: assign a home, or opt it out with a reason.

| Prefix | Primary doc | Note |
|:--|:--|:--|
| `__init__.py` | [ARCHITECTURE.md](ARCHITECTURE.md) | `DEFAULT_INCLUDE` — the lazy-exposure map, documented in the `bootstrap_package` section; API_REFERENCE.md points at it too |
| `_bootstrap.py` | [API_REFERENCE.md](API_REFERENCE.md) | `Bootstrap` (high-DPI) row — ARCHITECTURE §4 covers lazy symbol exposure, not this class |
| `bridge/` | [BRIDGE.md](BRIDGE.md) | dedicated subsystem doc |
| `compile.py` | [ARCHITECTURE.md](ARCHITECTURE.md) | §12 UI loading & compilation |
| `designer/` | [WIDGETS.md](WIDGETS.md) | § Using the widgets in Qt Designer — the widget-box plugin, `designer_spec`, design-time flag |
| `events.py` | [API_REFERENCE.md](API_REFERENCE.md) | `uitk.events` section |
| `examples/` | — | demo code; run `python -m uitk.examples.example`, don't document it |
| `managers/registry_manager.py` | [API_REFERENCE.md](API_REFERENCE.md) | FileRegistry / RegistryManager section; `file_manager.py` is its deprecated alias shim |
| `handlers/` | [ARCHITECTURE.md](ARCHITECTURE.md) | handler-ecosystem section |
| `loaders/` | [ARCHITECTURE.md](ARCHITECTURE.md) | §12 UI loading & compilation |
| `managers/` | [WIDGETS.md](WIDGETS.md) | standalone services (settings/state/values/presets/icons/shortcuts/cursors — § Cursors), split out of `widgets/mixins/` 2026-07; settings/state user-level detail in USER_GUIDE.md |
| `testing.py` | — | test-only affordance, not part of the runtime API. `TestSandbox.activate()` is the whole surface and its own docstring is the contract; it extends `pythontk.TestSandbox` (browser refusal, throwaway temp root) with the two Qt-side stores. Downstream suites are pointed at it from their conftest/runner, which is where a maintainer looks. |
| `themes/` | [ARCHITECTURE.md](ARCHITECTURE.md) | theming section (`StyleSheet` + `style.qss`) |
| `switchboard/` | [ARCHITECTURE.md](ARCHITECTURE.md) | slot-contract detail lives in SLOTS.md |
| `widgets/mainWindow.py` | [ARCHITECTURE.md](ARCHITECTURE.md) | MainWindow section; per-property detail in API_REFERENCE.md |
| `widgets/marking_menu/` | [MARKING_MENU.md](MARKING_MENU.md) | dedicated subsystem doc |
| `widgets/` | [WIDGETS.md](WIDGETS.md) | catch-all: catalog, mixins, optionBox, editors, sequencer, delegates |

## Backlog

One task = one unit of maintenance work. Do them in any order; each states its done-condition. Check the box **and** update the doc's ledger row (status + Verified date) in the same edit. Conventions and the verification protocol: [MAINTAINING.md](MAINTAINING.md).

- [x] **DOC-01** (README.md ×2) — Done 2026-07-08: both run verbatim against the published wheel in a clean venv (offscreen). Drift found & fixed: `pip install uitk` alone can't run the quickstart — `qtpy` + a Qt binding were deliberately not dependencies; both Install sections said so (sync block `qt-install-note`). Re-verified 2026-08-06: `qtpy>=2.0` promoted to a declared dep (it's a pure-Python shim, not a binding — clean-DCC installs failed without it; see CHANGELOG); only the Qt *binding* remains excluded, and both Install sections now say that instead. Verified against the published wheels in an isolated stock-Maya-2025 env incl. a GUI first-launch.
- [x] **DOC-02** (SLOTS.md) — Done 2026-08-14: ~90 claims traced (all 26 default-signals rows exact); 8 drift fixes (slot-file resolution order, sole-class fallback added, `base_name()` semantics, no try/except around slot bodies). Found `sync_widget_values` ignoring `restore_state` for sibling-surface writes — fixed same day (gate + key now via `StateManager._get_state_key`; regression test in `test_persistence_hardening.py`).
- [x] **DOC-03** (USER_GUIDE.md) — Done 2026-08-14: ~85 claims traced across §§1–13, 5 verified by offscreen runs; 20 drift fixes (the follower-breaking ones: `file_dialog` filter/return shape, chained `configurable` access that raises, `@Signals.blockSignals` on a non-widget). `file_dialog` str-coercion inconsistency fixed in code (test-first, `test_switchboard.py`).
- [x] **DOC-04** (WIDGETS.md) — Done 2026-07-08: full claim-by-claim catalog pass (18 drift fixes) + sections added for sequencer, editors, delegates, `WindowPanel`, `TextViewBox`, `Slider`, `ScriptOutput`; `MenuButton` pointered to MARKING_MENU.md.
- [x] **DOC-05** (MARKING_MENU.md) — Done 2026-07-08: full claim-by-claim pass; chord-release, binding persistence, MenuButton nav, and the shortcut-register work (activation key, route targets, `global_shortcuts` editor) now reflected.
- [x] **DOC-06** (ARCHITECTURE.md) — §12 added and §§11–14 + §3 verified 2026-07-08. Done 2026-08-14: §§1–10 claim-by-claim (~140 claims); heaviest drift in §5 lifecycle (fit-vs-restored geometry, footer adoption vs construction, host-namespaced settings branch) and §6 dispatch (deferred placeholders, per-signal `SlotWrapper`, prior-block-state restore). Found Table/Tree `ACTION_COLOR_MAP` hardcoding the light palette — logged to the workspace backlog.
- [x] **DOC-07** (COOKBOOK.md) — Done 2026-08-14: every recipe extracted and run offscreen (TestSandbox-isolated) or explicitly DCC-labeled with its claims traced to source; 13 fixes (presets API forms, retired `i`-prefix launcher convention → `MenuButton` `target`/`filterTags`, `configurable` proxy access, `on_item_added` mis-wiring). No uitk code bugs blocked any recipe.
- [x] **DOC-08** (EXAMPLES.md) — Done 2026-08-14: tutorial followed end-to-end from an empty folder, offscreen. Step 2 failed as written (plain Qt widgets lack the uitk APIs step 3 uses) — Designer promotion table now documented; presets/configurable steps rewritten to verified APIs; persistence outcome verified across two Switchboard rounds incl. geometry.
- [x] **DOC-09** (API_REFERENCE.md) — Done 2026-08-14: full two-way diff vs `API_INDEX.md`. Added handlers/text-mixins sections + an "everything else on the namespace" coverage table (every `DEFAULT_INCLUDE` symbol has a home); ghosts removed (`MouseTracking` signals, legacy `settings.__setattr__` path, stale ctor forms). Found `SpinBox` missing from `DEFAULT_INCLUDE` — fixed same day (registered; `uitk.SpinBox` resolves).
- [x] **DOC-10** (BRIDGE.md) — Done 2026-07-08: stub fully written from the cited sources; zero DOC-TODOs; row flipped to `needs-verify`. Claim pass done 2026-08-14 (~140 claims incl. cross-repo confirmation in mayatk/blendertk consumers; 13 drift fixes — `action` kind row, log-link dependency inversion, three-step output-dir resolution); row flipped to `current`. Three stale bridge docstrings fixed in code same day.
- [x] **DOC-11** — Done 2026-07-08. Decision: the shortcut/command registry lives in **WIDGETS.md § Shortcut & command registry** (inside the editors section), covering `GlobalShortcut`, `ShortcutManager`, `register_command`, host-namespaced persistence, and the `ShortcutEditor`/`global_shortcuts` views. A COOKBOOK recipe remains optional under DOC-07.
