# !/usr/bin/python
# coding=utf-8
from uitk import Signals


class ExampleSlots:
    def __init__(self, *args, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.example

    def header_init(self, widget):
        widget.config_buttons(
            menu_button=True, minimize_button=True, hide_button=True
        )
        widget.menu.setTitle("DRAGGABLE MENU")
        widget.menu.add(self.sb.registered_widgets.Label, setObjectName="label", setText="Clickable Label")

    def label(self):
        widget = self.ui.header.menu.label
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

    @Signals("released")
    def button_b(self, widget):
        option = (
            "A"
            if widget.menu.radio_a.isChecked()
            else "B" if widget.menu.radio_b.isChecked() else "C"
        )
        self.sb.message_box(f"{widget.text()}: Option {option}")

    def checkbox(self, state):
        self.sb.message_box(
            f'CheckBox State: <hl style="color:yellow;">{bool(state)}</hl>'
        )

    def spinbox(self, value, widget):
        self.sb.message_box(
            f'{widget.type} Value: <b style="font-weight: bold;">{value}</b>'
        )

    @staticmethod
    def textedit_init(widget):
        widget.setText("• Widget states are restored the next time this UI is opened.")

    @Signals("textChanged", "returnPressed")
    def textedit(self, widget):
        """Slot for handling actions in a QTextEdit widget.

        Parameters:
            widget (QTextEdit): The QTextEdit widget.
        """
        text = widget.toPlainText()
        print(text)


# --------------------------------------------------------------------------------------------

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
