# uitk — API Changes

_Diff vs prior baseline. Generated 2026-05-22._

## Removed (7)

- `widgets/editors/editor_panel.py::EditorPanel.body_layout` — was `(self)`
- `widgets/editors/editor_panel.py::EditorPanel.footer` — was `(self)`
- `widgets/editors/editor_panel.py::EditorPanel.header` — was `(self)`
- `widgets/editors/editor_panel.py::EditorPanel.icon_button` — was `(icon_name: str = '', size: int = 24, tooltip: str = '', icon_size=None) -> QtWidgets.QPushButton`
- `widgets/editors/editor_panel.py::EditorPanel.showEvent` — was `(self, event)`
- `widgets/editors/editor_panel.py::EditorPanel.style` — was `(self) -> 'StyleSheet'`
- `widgets/editors/editor_panel.py::EditorPanel.tighten_sublayouts` — was `(self, spacing: int = 1) -> None`

## Added (27)

- `_bootstrap.py::configure_high_dpi() -> bool`
- `switchboard/slots.py::Cancelable(class)`
- `switchboard/utils.py::SwitchboardUtilsMixin.progress_adapter(update: Callable[..., bool]) -> Callable[..., bool]`
- `switchboard/utils.py::SwitchboardUtilsMixin.text_view_dialog(self, text: str = '', *buttons, title: str = '', size=(640, 400), monospace: bool = False, word_wrap: bool = True, background=False, parent=None)`
- `widgets/_html_style.py::apply_inline_styles(string: str) -> str`
- `widgets/_html_style.py::apply_prefix_styles(string: str) -> str`
- `widgets/_html_style.py::format_rich_text(string: str, *, align: str = 'left', font_color: str = 'white', font_size: Union[int, str, None] = None) -> str`
- `widgets/_html_style.py::resolve_background(background) -> Optional[str]`
- `widgets/_html_style.py::wrap_font_color(string: str, color: str) -> str`
- `widgets/_html_style.py::wrap_font_size(string: str, size) -> str`
- `widgets/footer.py::Footer.set_progress_total(self, total: int) -> None`
- `widgets/mixins/preset_manager.py::QStandardPaths_genericConfigLocation() -> str`
- `widgets/progressBar.py::ProgressBar.set_total(self, total: int) -> None`
- `widgets/textViewBox.py::TextViewBox(class)`
- `widgets/textViewBox.py::TextViewBox.append_text(self, string: str, fontColor: str = 'white', fontSize=None) -> None`
- `widgets/textViewBox.py::TextViewBox.clear_text(self) -> None`
- `widgets/textViewBox.py::TextViewBox.clicked_button(self)`
- `widgets/textViewBox.py::TextViewBox.setStandardButtons(self, *buttons) -> None`
- `widgets/textViewBox.py::TextViewBox.setText(self, string: str, fontColor: str = 'white', background=False, fontSize=None) -> None`
- `widgets/windowPanel.py::WindowPanel(class)`
- `widgets/windowPanel.py::WindowPanel.body_layout(self)`
- `widgets/windowPanel.py::WindowPanel.footer(self)`
- `widgets/windowPanel.py::WindowPanel.header(self)`
- `widgets/windowPanel.py::WindowPanel.icon_button(icon_name: str = '', size: int = 24, tooltip: str = '', icon_size=None) -> QtWidgets.QPushButton`
- `widgets/windowPanel.py::WindowPanel.showEvent(self, event)`
- `widgets/windowPanel.py::WindowPanel.style(self) -> 'StyleSheet'`
- `widgets/windowPanel.py::WindowPanel.tighten_sublayouts(self, spacing: int = 1) -> None`

## Signature changed (4)

- `switchboard/utils.py::SwitchboardUtilsMixin.progress`
  - was: `(self, ui=None, total: Optional[int] = 100, text: str = '')`
  - now: `(self, ui=None, total: Optional[int] = None, text: str = '')`
- `widgets/footer.py::Footer.progress`
  - was: `(self, total: Optional[int] = 100, text: str = '') -> 'FooterProgressContext'`
  - now: `(self, total: Optional[int] = None, text: str = '') -> 'FooterProgressContext'`
- `widgets/footer.py::Footer.start_progress`
  - was: `(self, total: Optional[int] = 100, text: str = '') -> Callable[[int, Optional[str]], bool]`
  - now: `(self, total: Optional[int] = None, text: str = '') -> Callable[[Optional[int], Optional[str]], bool]`
- `widgets/footer.py::Footer.update_progress`
  - was: `(self, value: int, text: Optional[str] = None) -> bool`
  - now: `(self, value: Optional[int] = None, text: Optional[str] = None) -> bool`
