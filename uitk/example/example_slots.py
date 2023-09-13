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

    def button_a(self, widget):
        self.sb.message_box(f"{widget.text()}: Clicked")

    def button_b_init(self, widget):
        widget.menu.setTitle("OPTION MENU")
        widget.menu.add(
            "QRadioButton", setObjectName="radio_a", setText="Option A", setChecked=True
        )
        widget.menu.add("QRadioButton", setObjectName="radio_b", setText="Option B")
        widget.menu.add("QRadioButton", setObjectName="radio_c", setText="Option C")

    @signals("released")
    def button_b(self, widget):
        option = (
            "A"
            if widget.menu.radio_a.isChecked()
            else "B"
            if widget.menu.radio_b.isChecked()
            else "C"
        )
        self.sb.message_box(f"{widget.text()}: Option {option}")

    def checkbox(self, state):
        self.sb.message_box(
            f'CheckBox State: <hl style="color:yellow;">{bool(state)}</hl>'
        )

    def spinbox(self, value, widget):
        self.sb.message_box(f'SpinBox Value: <b style="font-weight: bold;">{value}</b>')

    @staticmethod
    def textedit_init(widget):
        widget.setText(
            "• Collapse this text edit by clicking on the three dots above it.\n\n• Widget states are restored the next time this UI is opened."
        )


# --------------------------------------------------------------------------------------------

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
