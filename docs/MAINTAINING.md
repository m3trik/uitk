# Maintaining these docs

The contract for anyone — human or agent — finishing or maintaining uitk's documentation. The docs are a **linked, ledgered set**: [DOCMAP.md](DOCMAP.md) records what each doc covers, which code it must stay true to, and what work remains; two sweep scripts verify the set mechanically. If the sweeps exit 0 and the ledger is honest, the docs are healthy.

**Nav**: [← README](README.md) · [Docmap](DOCMAP.md)

## Ground rules

1. **Docs describe verified behavior.** Every claim must be traceable to a source module (the ledger row's *Sources of truth* column tells you where to look) or to a snippet you actually ran. Never document what the code *should* do, and never invent features.
2. **If you can't verify it, mark it.** Leave a `DOC-TODO` marker (format below) rather than a confident guess. An honest gap is maintainable; a plausible fiction is poison.
3. **Generated files are off-limits.** `API_INDEX.md`, `API_REGISTRY.md`, `API_CHANGES.md` are emitted by `m3trik/scripts/generate_api_registry.py`. Never hand-edit them; the sweep ignores them.
4. **Docs state the present.** No changelog prose, no "as of version X", no history of how a feature evolved — that lives in [CHANGELOG.md](../CHANGELOG.md).
5. **Front doors stay small.** `../README.md` (GitHub) and `README.md` (PyPI) are pitches with pointers. Depth goes in the topic docs; don't grow the landings.
6. **Verify snippets offscreen.** `QT_QPA_PLATFORM=offscreen` lets most uitk code run headless. Recipes that genuinely need a DCC are labeled as such, never silently assumed to work.
7. **Prefer symbol names over line numbers.** A link like `[slots.py](../uitk/switchboard/slots.py)` plus a symbol name in prose survives refactors; `#L42` links rot (they're swept by `check_doc_line_refs.py`, but not rotting beats being caught).

## The maintenance loop

The unit of work is **one Backlog task** from [DOCMAP.md](DOCMAP.md#backlog).

1. **Pick a task.** Read its target doc and its ledger row's *Sources of truth*.
2. **Read the sources.** The actual modules — not your memory of them, not other docs.
3. **Write or verify.** Fix drift, fill gaps, resolve `DOC-TODO` markers. Every removed marker means you verified or wrote that content against the sources.
4. **Update the ledger in the same edit.** Flip the row's Status, stamp Verified (`YYYY-MM-DD`), check the Backlog box. A doc edit without a ledger update is an incomplete change.
5. **Sweep.** From the uitk repo root:
   ```bash
   python ../m3trik/scripts/check_docs.py --root .
   python ../m3trik/scripts/check_doc_line_refs.py --root .
   ```
   Both must exit 0. Fix what they flag; don't suppress.
6. **Log it.** One dated entry in [CHANGELOG.md](../CHANGELOG.md) per session of doc work (not per file).

### Status definitions (what you're attesting)

| Status | Meaning | Requirements |
|:--|:--|:--|
| `stub` | Skeleton; structure exists, content doesn't | ≥1 `DOC-TODO` marker |
| `needs-verify` | Content complete; not yet traced claim-by-claim to code | — |
| `current` | Every claim verified against the sources on the Verified date | zero `DOC-TODO`s, dated |

Verification is **claim-by-claim**: for each factual statement (a method name, a default value, a resolution order, a signal name), find it in the source. If the doc and code disagree, the code wins — fix the doc, or if the code looks wrong, flag it as a code issue instead of documenting the bug as intended behavior.

## Conventions

### Nav line

Every doc except the two landings carries, within its first 12 lines:

```markdown
**Nav**: [← README](README.md) · [User Guide](USER_GUIDE.md) · … · [API](API_REFERENCE.md)
```

Link the docs a reader of *this* doc most plausibly wants next — not necessarily all of them.

### See also footer

Every guide/reference doc ends with a `## See also` section linking related docs *with a reason*: `[SLOTS.md](SLOTS.md) — the naming contract this builds on`.

### DOC-TODO markers

An HTML comment naming its Backlog task and citing where the answer lives:

```markdown
<!-- DOC-TODO(DOC-10): Document the KindHandler registry — read uitk/bridge/spec.py (register_kind, infer_kind). -->
```

Invisible when rendered; counted by the sweep. A `current` doc may contain none. Markers inside fenced code blocks are treated as examples and not counted.

### Sync blocks

Content that must stay identical across files (e.g. the Quickstart in both READMEs) is fenced with paired markers; the sweep fails if the copies diverge:

```markdown
<!-- sync:quickstart -->
…identical content in every file that carries the block…
<!-- /sync:quickstart -->
```

Edit every copy in the same change, or the sweep will remind you.

### Ledger and coverage hygiene

- **New doc file** → add a Ledger row (the sweep fails on unledgered files).
- **New module** in `API_INDEX.md` with no coverage match → the sweep fails; triage it: map it to a doc (and write/mark the content), or opt out with `—` and a reason.
- **Deleted/renamed module** → the sweep warns about stale rules; prune them.

## When code changes (ongoing maintenance)

After any public-API change (a symbol added, renamed, removed, or behavior changed):

1. Regenerate the registry if not already done: `python m3trik/scripts/generate_api_registry.py uitk`.
2. Run the docs sweep — coverage failures point at brand-new modules.
3. `grep` the changed symbol's name across `docs/*.md`: every mention must still be true.
4. If a `current` doc is now stale and you can't fix it immediately, demote its row to `needs-verify` and add a `DOC-TODO` at the stale spot. **A wrong ledger is worse than a wrong doc.**

## What NOT to do

- Don't restructure the doc set (add/merge/split files) without also updating Ledger + Coverage rows — the sweep only protects what the ledger describes.
- Don't pad. If a section's honest content is three sentences, three sentences is complete.
- Don't duplicate content between docs — link to the owning doc instead. The only sanctioned duplication is a sync block.
- Don't touch `docs/README.md`'s role: it is the PyPI long-description (`pyproject.toml` → `readme`). It must render standalone on PyPI, so its deep links stay absolute GitHub URLs, not relative paths.

## See also

- [DOCMAP.md](DOCMAP.md) — the ledger this contract governs
- [../CLAUDE.md](../CLAUDE.md) — repo-wide agent instructions (uitk)
