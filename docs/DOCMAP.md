# DOCMAP — the docs ledger

Machine-checked single source of truth for uitk's hand-written documentation: what each doc covers, what code it must stay true to, and what work remains. Format and workflow: [MAINTAINING.md](MAINTAINING.md). Swept by `m3trik/scripts/check_docs.py` (`python ../m3trik/scripts/check_docs.py --root .` from the uitk root — must exit 0).

**Nav**: [← README](README.md) · [Maintaining](MAINTAINING.md)

Legend — **Status**: `current` (verified against code on the Verified date, zero DOC-TODOs) · `needs-verify` (content complete, not yet verified claim-by-claim) · `stub` (skeleton with DOC-TODO markers). **Role**: `landing` (front door, no Nav line required) · `guide` (task-oriented) · `reference` (looks-things-up) · `meta` (about the docs themselves).

## Ledger

| Doc | Role | Status | Verified | Sources of truth |
|:--|:--|:--|:--|:--|
| [../README.md](../README.md) | landing | needs-verify | — | `uitk/__init__.py` · `uitk/examples/example.py` · quickstart must run verbatim (DOC-01) |
| [README.md](README.md) | landing | needs-verify | — | the PyPI long-description (`pyproject.toml` readme) · shares sync blocks with ../README.md (DOC-01) |
| [USER_GUIDE.md](USER_GUIDE.md) | guide | needs-verify | — | `uitk/switchboard/` · `uitk/widgets/mainWindow.py` · `uitk/widgets/mixins/settings_manager.py` · `state_manager.py` (DOC-03) |
| [SLOTS.md](SLOTS.md) | reference | needs-verify | — | `uitk/switchboard/slots.py` · `uitk/switchboard/_core.py` (DOC-02) |
| [WIDGETS.md](WIDGETS.md) | reference | needs-verify | — | `uitk/widgets/` · `optionBox/` · `sequencer/` · `editors/` · `delegates/` (DOC-04) |
| [MARKING_MENU.md](MARKING_MENU.md) | reference | needs-verify | — | `uitk/widgets/marking_menu/` (DOC-05) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | reference | needs-verify | — | `uitk/switchboard/_core.py` · `handlers/` · `loaders/` · `compile.py` · `widgets/mainWindow.py` (DOC-06) |
| [COOKBOOK.md](COOKBOOK.md) | guide | needs-verify | — | consumer repos (mayatk, tentacle) · each recipe must run offscreen where possible (DOC-07) |
| [EXAMPLES.md](EXAMPLES.md) | guide | needs-verify | — | the tutorial project it walks through · `uitk/examples/example.py` (DOC-08) |
| [API_REFERENCE.md](API_REFERENCE.md) | reference | needs-verify | — | `API_INDEX.md` (grep `API_REGISTRY.md` for full signatures) (DOC-09) |
| [BRIDGE.md](BRIDGE.md) | reference | stub | — | `uitk/bridge/slots.py` · `spec.py` · `formatters.py` · `parameters.py` · `tooltip.py` (DOC-10) |
| [DOCMAP.md](DOCMAP.md) | meta | current | 2026-07-04 | this file — ledger, coverage map, backlog |
| [MAINTAINING.md](MAINTAINING.md) | meta | current | 2026-07-04 | the maintenance contract and conventions |

## Coverage — module → primary doc home

Every module in `API_INDEX.md` must match exactly one home via longest-prefix match (a prefix ending in `/` matches everything under it). `—` means "deliberately undocumented" and requires a reason. A new module that matches no rule fails the sweep — triage it: assign a home, or opt it out with a reason.

| Prefix | Primary doc | Note |
|:--|:--|:--|
| `_bootstrap.py` | [ARCHITECTURE.md](ARCHITECTURE.md) | package-bootstrap section |
| `bridge/` | [BRIDGE.md](BRIDGE.md) | stub — DOC-10 |
| `compile.py` | [ARCHITECTURE.md](ARCHITECTURE.md) | UI loading & compilation — DOC-06 |
| `events.py` | [API_REFERENCE.md](API_REFERENCE.md) | `uitk.events` section |
| `examples/` | — | demo code; run `python -m uitk.examples.example`, don't document it |
| `file_manager.py` | [API_REFERENCE.md](API_REFERENCE.md) | FileContainer / FileManager section |
| `handlers/` | [ARCHITECTURE.md](ARCHITECTURE.md) | handler-ecosystem section |
| `loaders/` | [ARCHITECTURE.md](ARCHITECTURE.md) | UI loading & compilation — DOC-06 |
| `switchboard/` | [ARCHITECTURE.md](ARCHITECTURE.md) | slot-contract detail lives in SLOTS.md |
| `widgets/mainWindow.py` | [ARCHITECTURE.md](ARCHITECTURE.md) | MainWindow section; per-property detail in API_REFERENCE.md |
| `widgets/marking_menu/` | [MARKING_MENU.md](MARKING_MENU.md) | dedicated subsystem doc |
| `widgets/` | [WIDGETS.md](WIDGETS.md) | catch-all: catalog, mixins, optionBox, editors, sequencer, delegates |

## Backlog

One task = one unit of maintenance work. Do them in any order; each states its done-condition. Check the box **and** update the doc's ledger row (status + Verified date) in the same edit. Conventions and the verification protocol: [MAINTAINING.md](MAINTAINING.md).

- [ ] **DOC-01** (README.md ×2) — On a clean venv, run the Quickstart verbatim and `python -m uitk.examples.example`; fix any drift. Done when: both run as written; both ledger rows flip to `current`.
- [ ] **DOC-02** (SLOTS.md) — Verify every numbered section against `uitk/switchboard/slots.py` + `_core.py`: class/method resolution order, the default-signals table, parameter injection, `@Signals`, debounce/`@Cancelable`/refresh flags, slot history. Done when: each claim traced to code; row flips to `current`.
- [ ] **DOC-03** (USER_GUIDE.md) — Same claim-by-claim pass for sections 1–13. Done when: row flips to `current`.
- [ ] **DOC-04** (WIDGETS.md) — Verify the catalog against `uitk/widgets/`, then close the known gaps: no sections exist for the **sequencer** subpackage (~13 modules), the **editors** subpackage (style, color-mapping, shortcut, switchboard-browser), **delegates**, `WindowPanel`, `TextViewBox`, or `AttributeWindow`. Done when: every `widgets/` module has a section or an explicit pointer; row flips to `current`.
- [ ] **DOC-05** (MARKING_MENU.md) — Verify against `uitk/widgets/marking_menu/`; recent shortcut-register work (activation key, `get_route_target`/`set_route_target`, `sb.editors.show("global_shortcuts")` — see CHANGELOG 2026-06-30) may not be reflected. Done when: row flips to `current`.
- [ ] **DOC-06** (ARCHITECTURE.md) — Verify; then add a **UI loading & compilation** section covering `compile.py` (`ensure_compiled`, `precompile_async`, embedded hash/tags) and `loaders/` (compiled vs runtime QUiLoader delegates). Done when: section exists; the two coverage notes stop pointing at this task; row flips to `current`.
- [ ] **DOC-07** (COOKBOOK.md) — Run each recipe offscreen (`QT_QPA_PLATFORM=offscreen`); mark DCC-only recipes as such. Done when: every recipe is run-verified or explicitly DCC-gated; row flips to `current`.
- [ ] **DOC-08** (EXAMPLES.md) — Follow the tutorial end-to-end from an empty folder. Done when: a fresh run matches every step's stated outcome; row flips to `current`.
- [ ] **DOC-09** (API_REFERENCE.md) — Diff the documented surface against `API_INDEX.md`; add missing public symbols (e.g. `RichTextFormatter`, the delegates, `WindowPanel`, `ShortcutEditor`, `ExternalAppHandler`) or note where they're covered. Done when: no public top-level symbol lacks a home; row flips to `current`.
- [ ] **DOC-10** (BRIDGE.md) — Finish the stub: resolve each DOC-TODO from the cited sources. Done when: zero DOC-TODOs; row flips to `needs-verify` (then `current` after a claim pass).
- [ ] **DOC-11** (home: decide) — The shortcut/command registry (`Switchboard.register_command`, `ShortcutEditor`, host-namespaced persistence, `GlobalShortcut`) has no narrative home. Decide where it lives (likely a WIDGETS.md editors section + a COOKBOOK recipe), write it, and record the decision here. Done when: written and linked from the Nav-adjacent "See also" of the chosen doc.
