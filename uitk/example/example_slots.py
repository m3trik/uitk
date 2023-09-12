# !/usr/bin/python
# coding=utf-8
from uitk import signals


class ExampleSlots:
    def __init__(self, *args, **kwargs):
        self.sb = self.switchboard()

    def button_a(self):
        widget = self.sb.example.button_a
        self.sb.message_box(f"{widget.text()} Pressed")

    @signals("released")
    def button_b(self, widget):
        self.sb.message_box(f"{widget.text()} Released")

    def checkbox(self, state):
        self.sb.message_box(f"CheckBox State: {bool(state)}")

    def spinbox(self, value, widget):
        self.sb.message_box(f"SpinBox Value: {value}")


# --------------------------------------------------------------------------------------------

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
