# uitk — API Changes

_Diff vs prior baseline. Generated 2026-05-19._

## Removed (10)

- `handlers/external_tool_handler.py::ExternalToolHandler` — was `(class)`
- `handlers/external_tool_handler.py::ExternalToolHandler.close` — was `(self, name: str) -> None`
- `handlers/external_tool_handler.py::ExternalToolHandler.discover` — was `(self, groups: Optional[Iterable[str]] = None) -> int`
- `handlers/external_tool_handler.py::ExternalToolHandler.entries` — was `(self) -> Iterable[HandlerEntry]`
- `handlers/external_tool_handler.py::ExternalToolHandler.is_registered` — was `(self, name: str) -> bool`
- `handlers/external_tool_handler.py::ExternalToolHandler.is_visible` — was `(self, name: str) -> bool`
- `handlers/external_tool_handler.py::ExternalToolHandler.launch` — was `(self, name: Optional[str] = None, *, module: Optional[str] = None, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: Optional[str] = None, show: bool = True, **_options)`
- `handlers/external_tool_handler.py::ExternalToolHandler.register` — was `(self, name: str, *, module: str, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: str = 'subprocess', tags: Optional[Iterable[str]] = None) -> None`
- `handlers/external_tool_handler.py::ExternalToolHandler.save_tags` — was `(self, name: str, tags: Iterable[str]) -> None`
- `handlers/external_tool_handler.py::ExternalToolHandler.unregister` — was `(self, name: str) -> None`

## Added (10)

- `handlers/external_app_handler.py::ExternalAppHandler(class)`
- `handlers/external_app_handler.py::ExternalAppHandler.close(self, name: str) -> None`
- `handlers/external_app_handler.py::ExternalAppHandler.discover(self, groups: Optional[Iterable[str]] = None) -> int`
- `handlers/external_app_handler.py::ExternalAppHandler.entries(self) -> Iterable[HandlerEntry]`
- `handlers/external_app_handler.py::ExternalAppHandler.is_registered(self, name: str) -> bool`
- `handlers/external_app_handler.py::ExternalAppHandler.is_visible(self, name: str) -> bool`
- `handlers/external_app_handler.py::ExternalAppHandler.launch(self, name: Optional[str] = None, *, module: Optional[str] = None, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: Optional[str] = None, show: bool = True, **_options)`
- `handlers/external_app_handler.py::ExternalAppHandler.register(self, name: str, *, module: str, entry: Optional[str] = None, install_spec: Optional[str] = None, python: Optional[str] = None, show_kwargs: Optional[dict] = None, mode: str = 'subprocess', tags: Optional[Iterable[str]] = None) -> None`
- `handlers/external_app_handler.py::ExternalAppHandler.save_tags(self, name: str, tags: Iterable[str]) -> None`
- `handlers/external_app_handler.py::ExternalAppHandler.unregister(self, name: str) -> None`
