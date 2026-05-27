# uitk — API Changes

_Diff vs prior baseline. Generated 2026-05-27._

## Removed (10)

- `widgets/doubleSpinBox.py::DoubleSpinBox.adjustStepSize` — was `(self, event: QtGui.QWheelEvent) -> None`
- `widgets/doubleSpinBox.py::DoubleSpinBox.decreaseValueWithSmallStep` — was `(self, event: QtGui.QWheelEvent) -> None`
- `widgets/doubleSpinBox.py::DoubleSpinBox.increaseValueWithLargeStep` — was `(self, event: QtGui.QWheelEvent) -> None`
- `widgets/doubleSpinBox.py::DoubleSpinBox.message` — was `(self, text: str) -> None`
- `widgets/doubleSpinBox.py::DoubleSpinBox.wheelEvent` — was `(self, event: QtGui.QWheelEvent) -> None`
- `widgets/spinBox.py::SpinBox.adjustStepSize` — was `(self, event: QtGui.QWheelEvent) -> None`
- `widgets/spinBox.py::SpinBox.decreaseValueWithSmallStep` — was `(self, event: QtGui.QWheelEvent) -> None`
- `widgets/spinBox.py::SpinBox.increaseValueWithLargeStep` — was `(self, event: QtGui.QWheelEvent) -> None`
- `widgets/spinBox.py::SpinBox.message` — was `(self, text: str) -> None`
- `widgets/spinBox.py::SpinBox.wheelEvent` — was `(self, event: QtGui.QWheelEvent) -> None`

## Added (4)

- `widgets/mixins/feedback.py::FeedbackMixin(class)`
- `widgets/mixins/feedback.py::FeedbackMixin.show_feedback(self, html_text: str) -> None`
- `widgets/mixins/wheel_step.py::WheelStepMixin(class)`
- `widgets/mixins/wheel_step.py::WheelStepMixin.wheelEvent(self, event: QtGui.QWheelEvent) -> None`

## Signature changed (2)

- `widgets/marking_menu/_marking_menu.py::MarkingMenu.setCurrentWidget`
  - was: `(self, widget: QtWidgets.QWidget) -> None`
  - now: `(self, widget: QtWidgets.QWidget, *, anchor: Optional[QtCore.QPoint] = None) -> None`
- `widgets/messageBox.py::MessageBox.setText`
  - was: `(self, string, fontColor='white', background=0.75, fontSize=5) -> None`
  - now: `(self, string, fontColor='white', background=None, fontSize=5) -> None`
