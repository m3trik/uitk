# uitk — API Changes

_Diff vs prior baseline. Generated 2026-07-01._

## Signature changed (1)

- `switchboard/shortcuts.py::SwitchboardShortcutMixin.register_command`
  - was: `(self, name: str, callback: Optional[Callable] = None, *, label: Optional[str] = None, sequence: str = '', scope: str = 'application', doc: str = '', hidden: bool = False, editable: bool = True, bind: bool = True, on_rebind: Optional[Callable[[str, str], None]] = None, value_getter: Optional[Callable[[], str]] = None) -> str`
  - now: `(self, name: str, callback: Optional[Callable] = None, *, label: Optional[str] = None, sequence: str = '', scope: str = 'application', doc: str = '', hidden: bool = False, editable: bool = True, bind: bool = True, clearable: bool = True, on_rebind: Optional[Callable[[str, str], None]] = None, value_getter: Optional[Callable[[], str]] = None) -> str`
