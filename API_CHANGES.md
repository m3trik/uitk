# uitk — API Changes

_Diff vs prior baseline. Generated 2026-05-19._

## Signature changed (1)

- `handlers/external_tool_handler.py::ExternalToolHandler.launch`
  - was: `(self, name: Optional[str] = None, *, module: Optional[str] = None, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: Optional[str] = None, **_options)`
  - now: `(self, name: Optional[str] = None, *, module: Optional[str] = None, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: Optional[str] = None, show: bool = True, **_options)`
