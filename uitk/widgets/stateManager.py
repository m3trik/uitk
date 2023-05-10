import os
import json
from PySide2 import QtWidgets
from pythontk import File


#     # sync all widgets within relative uis.
#     relatives = self.get_ui_relatives(ui)
#     self.sync_all_widgets(relatives)


class StateManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.ui_filepath = main_window.path

    #     self.state_file = os.path.join(self.ui_filepath, "widget_states.json")

    # def save_widget_states(self):
    #     widget_states = {}
    #     for widget in self.main_window._widgets:
    #         if isinstance(widget, QtWidgets.QWidget):
    #             widget_states[widget.objectName()] = self.get_widget_state(widget)

    #     with open(self.state_file, "w") as file:
    #         json.dump(widget_states, file)

    def load_widget_states(self):
        """ """
        # if not os.path.exists(self.state_file):
        #     return

        # with open(self.state_file, "r") as file:
        #     widget_states = json.load(file)

        # for widget in self.main_window._widgets:
        #     if isinstance(widget, QtWidgets.QWidget):
        #         object_name = widget.objectName()
        #         if object_name in widget_states:
        #             self.set_widget_state(widget, widget_states[object_name])

    # @staticmethod
    # def get_widget_state(widget):
    #     if isinstance(widget, QtWidgets.QAbstractButton):
    #         return widget.isChecked()
    #     elif isinstance(widget, QtWidgets.QComboBox):
    #         return widget.currentIndex()
    #     # Add more widget types as needed

    # @staticmethod
    # def set_widget_state(widget, state):
    #     if isinstance(widget, QtWidgets.QAbstractButton):
    #         widget.setChecked(state)
    #     elif isinstance(widget, QtWidgets.QComboBox):
    #         widget.setCurrentIndex(state)
    #     # Add more widget types as needed
