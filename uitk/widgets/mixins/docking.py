import sys
from qtpy.QtCore import QObject, Qt, QEvent, Signal
from qtpy.QtGui import QPainter, QColor, QBrush
from qtpy.QtWidgets import (
    QApplication,
    QMainWindow,
    QDockWidget,
    QVBoxLayout,
    QWidget,
    QLabel,
)


class DockingOverlay(QWidget):
    def __init__(self, docking):
        super().__init__()
        self.docking = docking
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        self.docking.dock_position_changed.connect(self.update)
        self.raise_()

    def update(self):
        dock_position = self.docking.dock_position
        dock_window = (
            self.docking.dock_window
        )  # Get the reference to the window being dragged over
        if not dock_position or not dock_window:
            self.hide()
            return

        self.setGeometry(
            dock_window.geometry()
        )  # Use the geometry of the window being dragged over
        self.show()

    def paintEvent(self, event):
        position = self.docking.dock_position
        if not position:
            return

        painter = QPainter(self)
        color = QColor(0, 255, 0, 100)  # Green color with transparency
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)

        rect_width = 10
        rect_height = self.height()

        if position == "right":
            rect_x = 0
            rect_y = 0
        elif position == "left":
            rect_x = self.width() - rect_width
            rect_y = 0
        elif position == "top":
            rect_x = 0
            rect_y = self.height() - 10
            rect_width = self.width()
            rect_height = 10
        elif position == "bottom":
            rect_x = 0
            rect_y = 0
            rect_width = self.width()
            rect_height = 10
        else:
            return

        painter.drawRect(rect_x, rect_y, rect_width, rect_height)


class DockingWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DockingMixin Window")
        self.setGeometry(300, 100, 400, 300)
        self.setWindowFlags(Qt.Tool)
        self.docked_widgets = []

    def add_tool_window(self, tool_window, position):
        dock_widget = CustomDockWidget(tool_window.windowTitle(), self)
        dock_widget.setAllowedAreas(Qt.AllDockWidgetAreas)
        dock_widget.setWidget(tool_window)
        self.addDockWidget(position, dock_widget)
        self.docked_widgets.append(dock_widget)
        dock_widget.undocked.connect(self.remove_tool_window)

    def remove_tool_window(self, tool_window):
        if tool_window in self.docked_widgets:
            self.docked_widgets.remove(tool_window)

    def get_docked_widgets(self):
        return self.docked_widgets


class CustomDockWidget(QDockWidget):
    docked = Signal(QDockWidget)
    undocked = Signal(QDockWidget)

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
        )
        self.setFloating(False)
        self.topLevelChanged.connect(self.handle_top_level_change)
        self.installEventFilter(self)

    def handle_top_level_change(self, floating):
        if floating:
            self.undocked.emit(self)
        else:
            self.docked.emit(self)

    def eventFilter(self, widget, event):
        if event.type() == QEvent.MouseMove:
            if self.isFloating():
                # Check if any part of the dock widget is inside the docking window
                if self.parent().geometry().intersects(self.geometry()):
                    print("Dragging inside the docking window")
                else:
                    print("Dragging outside the docking window")

                    # Hide the DockingWindow if there are no docked widgets left
                    docked_widgets = self.parent().get_docked_widgets()
                    print(docked_widgets)
                    if not docked_widgets:
                        self.parent().hide()
            else:
                print("Mouse moved while docked")
        return super().eventFilter(widget, event)


class DockingMixin(QObject):
    """Enables window docking with visual overlay for dock position preview."""

    dock_position_changed = Signal()
    tool_windows = []
    docked_window_groups = []

    def __init__(self, window):
        super().__init__()
        self.window = window
        self._dock_enabled = False
        self._last_dock_position = None
        self.overlay = DockingOverlay(self)
        self.dock_window = None  # Add a reference to the window being docked to

    @property
    def docking_enabled(self):
        return self._dock_enabled

    @docking_enabled.setter
    def docking_enabled(self, value):
        if value == self._dock_enabled:
            return

        self._dock_enabled = value
        if value:
            self.window.installEventFilter(self)
            self.__class__.tool_windows.append(self.window)
        else:
            self.window.removeEventFilter(self)
            self.__class__.tool_windows.remove(self.window)

    @property
    def dock_position(self):
        return self._last_dock_position

    @dock_position.setter
    def dock_position(self, value):
        self._last_dock_position = value
        self.dock_position_changed.emit()

    def dock(self, target_window, position):
        docking_window = DockingWindow()
        self.__class__.docked_window_groups.append(docking_window)
        self.window.setParent(None)
        target_window.setParent(None)
        self.window.setWindowFlags(Qt.Widget)
        target_window.setWindowFlags(Qt.Widget)

        docking_window.add_tool_window(self.window, self.dock_positions[position][0])
        docking_window.add_tool_window(target_window, self.dock_positions[position][1])
        docking_window.show()
        docking_window.activateWindow()

        self.window.removeEventFilter(self)

    @property
    def dock_positions(self):
        return {
            "left": (Qt.RightDockWidgetArea, Qt.LeftDockWidgetArea),
            "right": (Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea),
            "top": (Qt.BottomDockWidgetArea, Qt.TopDockWidgetArea),
            "bottom": (Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea),
        }

    def _get_dock_position(self, window1, window2):
        intersection = window1.geometry().intersected(window2.geometry())

        position_diff = {
            "left": abs(intersection.right() - window1.geometry().left()),
            "right": abs(intersection.left() - window1.geometry().right()),
            "top": abs(intersection.bottom() - window1.geometry().top()),
            "bottom": abs(intersection.top() - window1.geometry().bottom()),
        }
        return min(position_diff, key=position_diff.get)

    def update_docking_position(self):
        dock_distance = 50
        for window in self.__class__.tool_windows:
            if window is not self.window and self.window.geometry().adjusted(
                -dock_distance, -dock_distance, dock_distance, dock_distance
            ).contains(window.geometry().center()):
                dock_position = self._get_dock_position(self.window, window)
                if dock_position:
                    self.dock_position = (
                        dock_position  # Update dock_position with the position only
                    )
                    self.dock_window = window  # Update dock_window reference
                    return
        self.dock_position = None
        self.dock_window = None

    def eventFilter(self, widget, event):
        if not self.docking_enabled:
            return False

        elif event.type() == QEvent.Move:
            self.update_docking_position()

        elif event.type() == QEvent.NonClientAreaMouseButtonRelease:
            if self.dock_position:
                for window in self.__class__.tool_windows:
                    if window is not self.window and self.window.geometry().adjusted(
                        -50, -50, 50, 50
                    ).contains(window.geometry().center()):
                        self.dock(window, self.dock_position)
                        self.dock_position = None
                        break
        return False


if __name__ == "__main__":

    class CustomToolWindow(QMainWindow):
        def __init__(self, title):
            super().__init__()
            self.setWindowFlags(Qt.Tool)
            self.setWindowTitle(title)
            central_widget = QWidget()
            layout = QVBoxLayout(central_widget)
            layout.addWidget(QLabel(title))
            self.setCentralWidget(central_widget)

            self.docking = DockingMixin(self)
            self.docking.docking_enabled = True

    app = QApplication.instance() or QApplication(sys.argv)

    window1 = CustomToolWindow("Window 1")
    window1.setGeometry(100, 100, 200, 200)
    window1.show()

    window2 = CustomToolWindow("Window 2")
    window2.setGeometry(350, 100, 200, 200)
    window2.show()

    sys.exit(app.exec_())
