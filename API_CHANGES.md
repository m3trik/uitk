# uitk — API Changes

_Diff vs the last release (origin/main @ 8797389)._

## Added (59)

- `managers/background_task.py::BackgroundTask(class)`
- `managers/background_task.py::BackgroundTask.done(self) -> bool`
- `managers/background_task.py::BackgroundTask.result(self) -> Any`
- `managers/background_task.py::BackgroundTask.wait(self, seconds: float) -> None`
- `managers/background_task.py::BackgroundTask.when_done(self, parent: QtCore.QObject, callback: Callable[[], None], poll_ms: Optional[int] = None) -> None`
- `widgets/compare_view.py::CompareView(class)`
- `widgets/compare_view.py::CompareView.blink(self, showing_b: bool) -> None`
- `widgets/compare_view.py::CompareView.fit(self) -> None`
- `widgets/compare_view.py::CompareView.focusOutEvent(self, event) -> None`
- `widgets/compare_view.py::CompareView.keyPressEvent(self, event) -> None`
- `widgets/compare_view.py::CompareView.keyReleaseEvent(self, event) -> None`
- `widgets/compare_view.py::CompareView.mode(self) -> str`
- `widgets/compare_view.py::CompareView.set_images(self, a: Any, b: Any) -> None`
- `widgets/compare_view.py::CompareView.set_labels(self, a: str, b: str) -> None`
- `widgets/compare_view.py::CompareView.set_mode(self, mode: str) -> None`
- `widgets/compare_view.py::CompareView.set_overlays(self, overlays: Sequence[Mapping[str, Any]]) -> None`
- `widgets/compare_view.py::CompareView.set_split_position(self, position: float) -> None`
- `widgets/compare_view.py::CompareView.split_position(self) -> float`
- `widgets/delegates/value_bar.py::ValueBarDelegate(class)`
- `widgets/delegates/value_bar.py::ValueBarDelegate.fraction(self, value: float) -> float`
- `widgets/delegates/value_bar.py::ValueBarDelegate.paint(self, painter, option, index) -> None`
- `widgets/delegates/value_bar.py::ValueBarDelegate.text_of(self, value: float) -> str`
- `widgets/delegates/value_bar.py::ValueBarDelegate.value_of(self, index: QtCore.QModelIndex, role: Optional[int] = None) -> Optional[float]`
- `widgets/image_view.py::ImageTool(class)`
- `widgets/image_view.py::ImageTool.finish(self) -> bool`
- `widgets/image_view.py::ImageTool.move(self, point: Tuple[float, float]) -> None`
- `widgets/image_view.py::ImageTool.press(self, point: Tuple[float, float]) -> bool`
- `widgets/image_view.py::ImageTool.preview(self) -> List[Tuple[float, float]]`
- `widgets/image_view.py::ImageTool.release(self, point: Tuple[float, float]) -> bool`
- `widgets/image_view.py::ImageTool.result(self) -> List[Tuple[float, float]]`
- `widgets/image_view.py::ImageView(class)`
- `widgets/image_view.py::ImageView.actual_size(self) -> None`
- `widgets/image_view.py::ImageView.fit(self) -> None`
- `widgets/image_view.py::ImageView.fitting(self) -> bool`
- `widgets/image_view.py::ImageView.image_size(self) -> Tuple[int, int]`
- `widgets/image_view.py::ImageView.keyPressEvent(self, event) -> None`
- `widgets/image_view.py::ImageView.keyReleaseEvent(self, event) -> None`
- `widgets/image_view.py::ImageView.leaveEvent(self, event) -> None`
- `widgets/image_view.py::ImageView.mouseDoubleClickEvent(self, event) -> None`
- `widgets/image_view.py::ImageView.mouseMoveEvent(self, event) -> None`
- `widgets/image_view.py::ImageView.mousePressEvent(self, event) -> None`
- `widgets/image_view.py::ImageView.mouseReleaseEvent(self, event) -> None`
- `widgets/image_view.py::ImageView.overlay_at(self, view_pos: QtCore.QPointF) -> Any`
- `widgets/image_view.py::ImageView.overlays(self) -> List[Dict[str, Any]]`
- `widgets/image_view.py::ImageView.path_of(points: Sequence[Sequence[float]], closed: bool) -> QtGui.QPainterPath`
- `widgets/image_view.py::ImageView.register_tool(cls, name: str, tool: Type[ImageTool]) -> None`
- `widgets/image_view.py::ImageView.resizeEvent(self, event) -> None`
- `widgets/image_view.py::ImageView.set_image(self, image: Any) -> None`
- `widgets/image_view.py::ImageView.set_overlays(self, overlays: Sequence[Mapping[str, Any]]) -> None`
- `widgets/image_view.py::ImageView.set_tool(self, name: Optional[str]) -> None`
- `widgets/image_view.py::ImageView.set_view_state(self, state: Mapping[str, Any]) -> None`
- `widgets/image_view.py::ImageView.set_wipe(self, image: Any, position: float = 0.5) -> None`
- `widgets/image_view.py::ImageView.set_wipe_position(self, position: float) -> None`
- `widgets/image_view.py::ImageView.to_pixmap(image: Any) -> Optional[QtGui.QPixmap]`
- `widgets/image_view.py::ImageView.tool(self) -> Optional[str]`
- `widgets/image_view.py::ImageView.view_state(self) -> Dict[str, Any]`
- `widgets/image_view.py::ImageView.wheelEvent(self, event) -> None`
- `widgets/image_view.py::ImageView.wipe_position(self) -> Optional[float]`
- `widgets/image_view.py::ImageView.zoom(self) -> float`

## Deprecations (1)

_Live retirement debt, earliest deadline first. An **EXPIRED** row has outlived its window: delete the alias and its tests rather than moving the date. A **HELD** row is due by version, but its notice has not yet had its calendar window._

- **HELD** `bridge/parameters.py::Parameters.shader_type_spec` — remove in 1.7.0, not before 2026-10-26
