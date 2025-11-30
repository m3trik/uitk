# !/usr/bin/python
# coding=utf-8
import sys
import time
from qtpy import QtCore, QtWidgets, QtGui


class WorkIndicator(QtWidgets.QDialog):
    def __init__(
        self,
        parent=None,
        gif_path="O:/Cloud/Code/_scripts/uitk/uitk/widgets/mixins/task_indicator.gif",
    ):
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.movie = QtGui.QMovie(gif_path)
        self.initUI()

    def initUI(self):
        label = QtWidgets.QLabel(self)
        label.setMovie(self.movie)
        if not self.movie.isValid():
            print("Failed to load GIF")

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(label)
        self.setLayout(layout)
        self.movie.start()

    def closeEvent(self, event):
        self.movie.stop()
        super().closeEvent(event)


class TasksMixin(QtCore.QThread):
    """Background task runner with optional visual work indicator."""

    taskCompleted = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.workIndicator = None
        self.taskFunction = None

    def run(self):
        if self.taskFunction:
            self.taskFunction()
        self.taskCompleted.emit()

    def startTask(self, taskFunction):
        self.taskFunction = taskFunction
        self.workIndicator = WorkIndicator(self.parent())
        self.workIndicator.show()
        self.start()

    def stopTask(self):
        if self.workIndicator:
            self.workIndicator.close()
            self.workIndicator = None
        self.wait()  # Ensure the thread has finished


# --------------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------
if __name__ == "__main__":

    class Window(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.initUI()

        def initUI(self):
            layout = QtWidgets.QVBoxLayout(self)

            button = QtWidgets.QPushButton("Perform Long Running Task", self)
            button.clicked.connect(self.performLongRunningTask)

            layout.addWidget(button)

            self.task = TasksMixin(self)

        def performLongRunningTask(self):
            self.task.taskCompleted.connect(self.onTaskCompleted)
            self.task.startTask(self.longRunningTask)

        def longRunningTask(self):
            # Simulate a long-running task
            time.sleep(2)

        def onTaskCompleted(self):
            # Handle task completion
            print("Task completed")

    app = QtWidgets.QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec_())

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------
# deprecated:
# --------------------------------------------------------------------------------------------
