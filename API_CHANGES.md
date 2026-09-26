# uitk — API Changes

_Diff vs the last release (origin/main @ 64dffd3)._

## Added (7)

- `widgets/mixins/text.py::RichTextFormatter.linkify(cls, string: str) -> str`
- `widgets/mixins/tooltip_mixin.py::TooltipFormat.display_ms(cls, text: str, rich: bool = None) -> int`
- `widgets/mixins/tooltip_mixin.py::TooltipFormat.wrap(cls, text: str, width: int = None, slack: int = None, rich: bool = None) -> str`
- `widgets/mixins/tooltip_mixin.py::TooltipNamespace.manage(self, widgets, ui=None) -> list`
- `widgets/mixins/tooltip_mixin.py::TooltipPresenter(class)`
- `widgets/mixins/tooltip_mixin.py::TooltipPresenter.manage(cls, widget) -> '_TooltipFilter'`
- `widgets/mixins/tooltip_mixin.py::TooltipPresenter.show_text(cls, pos, text: str, widget=None, rect=None, duration=None) -> None`

## Signature changed (1)

- `switchboard/utils.py::SwitchboardUtilsMixin.text_view_dialog`
  - was: `(self, text: str = '', *buttons, title: str = '', size=(640, 400), monospace: bool = False, word_wrap: bool = True, background=False, parent=None)`
  - now: `(self, text: str = '', *buttons, title: str = '', size=(640, 400), monospace: bool = False, word_wrap: bool = True, background=False, parent=None, link_handler=None)`
