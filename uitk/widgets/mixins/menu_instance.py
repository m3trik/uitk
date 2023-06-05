# !/usr/bin/python
# coding=utf-8
from PySide2 import QtWidgets


class MenuInstance:
    """Get a Menu and ctx_menu instance."""

    @property
    def option_menu(self) -> QtWidgets.QMenu:
        """Get the standard menu."""
        try:
            return self._option_menu
        except AttributeError:
            from uitk.widgets.menu import Menu

            self._option_menu = Menu(self, position="bottomLeft")
            return self._option_menu

    @option_menu.setter
    def option_menu(self, menu: QtWidgets.QMenu):
        """Set the standard menu."""
        self._option_menu = menu

    @property
    def ctx_menu(self) -> QtWidgets.QMenu:
        """Get the context menu."""
        try:
            return self._ctx_menu
        except AttributeError:
            from uitk.widgets.menu import Menu

            self._ctx_menu = Menu(self, position="cursorPos")
            return self._ctx_menu

    @ctx_menu.setter
    def ctx_menu(self, menu: QtWidgets.QMenu):
        """Set the context menu."""
        self._ctx_menu = menu


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # return the existing QApplication object, or create a new one if none exists.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # # grid layout example
    menu = MenuInstance().option_menu
    print(menu)
    # a = menu.add(["Label A", "Label B"])
    a = menu.add("Label A")
    b = menu.add("Label B")
    c = menu.add("QDoubleSpinBox", set_spinbox_by_value=1.0, row=0, col=1)
    d = menu.add("QDoubleSpinBox", set_spinbox_by_value=2.0, row=1, col=1)

    menu.on_item_interacted.connect(lambda x: print(x))

    from uitk.widgets.mixins.style_sheet import StyleSheet

    StyleSheet().set_style(widget=menu.get_items(), theme="dark")

    menu.show()
    print(menu.get_items())
    sys.exit(app.exec_())

# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------

"""
Promoting a widget in designer to use a custom class:
>   In Qt Designer, select all the widgets you want to replace, 
        then right-click them and select 'Promote to...'. 

>   In the dialog:
        Base Class:     Class from which you inherit. ie. QWidget
        Promoted Class: Name of the class. ie. "MyWidget"
        Header File:    Path of the file (changing the extension .py to .h)  ie. myfolder.mymodule.mywidget.h

>   Then click "Add", "Promote", 
        and you will see the class change from "QWidget" to "MyWidget" in the Object Inspector pane.
"""

# depricated:

# def hide(self, force=False):
#   '''Sets the widget as invisible.
#   Prevents hide event under certain circumstances.

#   Parameters:
#       force (bool): override prevent_hide.
#   '''
#   if force or not self.prevent_hide:

#       for w in self.get_items():
#           try:
#               if w.view().isVisible(): #comboBox menu open.
#                   return
#           except AttributeError as error:
#               pass

#       super().hide()


# def show(self):
#   '''Show the menu.
#   '''
#   if not self.contains_items: #prevent show if the menu is empty.
#       return

#   if not self.title():
#           self.setTitle()

#   if hasattr(self.parent(), 'released') and not self.parent().objectName()=='draggable_header':
#       # print (f'show menu | title: {self.title()} | {self.parent().objectName()} has attr released.') #debug
#       self.applyButton.show()

#   checkboxes = self.get_items(inc=['QCheckBox'])
#   if checkboxes: #returns None if the menu doesn't contain checkboxes.
#       self.toggleAllButton.show()

#   super().show()


# def showEvent(self, event):
#   '''
#   Parameters:
#       event = <QEvent>
#   '''
#   self.resize(self.sizeHint().width(), self.sizeHint().height()+10) #self.setMinimumSize(width, self.sizeHint().height()+5)
#   get_center = lambda w, p: QtCore.QPoint(p.x()-(w.width()/2), p.y()-(w.height()/4)) #get widget center position.

#   #set menu position
#   if self.position=='cursorPos':
#       pos = QtGui.QCursor.pos() #global position
#       self.move(get_center(self, pos)) #move to cursor position.

#   elif not isinstance(self.position, (type(None), str)): #if a widget is passed to 'position' (move to the widget's position).
#       pos = getattr(self.positionRelativeTo.rect(), self.position)
#       self.move(self.positionRelativeTo.mapToGlobal(pos()))

#   elif self.parent(): #if parent: map relative to parent.
#       pos = getattr(self.parent().rect(), self.position if not self.position=='cursorPos' else 'bottomLeft')
#       pos = self.parent().mapToGlobal(pos())
#       self.move(pos) # self.move(get_center(self, pos))

#   QtWidgets.QMenu.showEvent(self, event)
