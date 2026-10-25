# uitk — API Changes

_Diff vs the last release (origin/main @ 2f60c23)._

No public API changes since the last release (origin/main @ 2f60c23).

## Deprecations (1)

_Live retirement debt, earliest deadline first. An **EXPIRED** row has outlived its window: delete the alias and its tests rather than moving the date. A **HELD** row is due by version, but its notice has not yet had its calendar window._

- **HELD** `bridge/parameters.py::Parameters.shader_type_spec` — remove in 1.7.0, not before 2026-10-26

