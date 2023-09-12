# !/usr/bin/python
# coding=utf-8
from uitk import signals


class ExampleSlots:
    def __init__(self, *args, **kwargs):
        self.sb = self.switchboard()

    def header_init(self, widget):
        widget.configureButtons(
            menu_button=True, minimize_button=True, hide_button=True
        )
        widget.menu.setTitle("DRAG ME!")
        widget.menu.add(self.sb.Label, setObjectName="label", setText="Clickable Label")

    def label(self):
        widget = self.sb.example.header.menu.label
        self.sb.message_box(f"{widget.text()}: Clicked")

    @signals("released")
    def button(self, widget):
        self.sb.message_box(f"{widget.text()}: Released")

    def checkbox(self, state):
        self.sb.message_box(
            f'CheckBox State: <hl style="color:yellow;">{bool(state)}</hl>'
        )

    def spinbox(self, value, widget):
        self.sb.message_box(f'SpinBox Value: <b style="font-weight: bold;">{value}</b>')

    @staticmethod
    def textedit_init(widget):
        widget.setText("Initialized with this text.")


# --------------------------------------------------------------------------------------------

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
