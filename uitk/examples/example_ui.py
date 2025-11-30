# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'example.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QGroupBox, QHBoxLayout,
    QHeaderView, QMainWindow, QSizePolicy, QSpinBox,
    QTextEdit, QTreeWidgetItem, QVBoxLayout, QWidget)

from uitk.widgets.collapsableGroup import CollapsableGroup
from uitk.widgets.comboBox import ComboBox
from uitk.widgets.footer import Footer
from uitk.widgets.header import Header
from uitk.widgets.lineEdit import LineEdit
from uitk.widgets.pushButton import PushButton
from uitk.widgets.treeWidget import TreeWidget
from uitk.widgets.widgetComboBox import WidgetComboBox

class Ui_QtUi(object):
    def setupUi(self, QtUi):
        if not QtUi.objectName():
            QtUi.setObjectName(u"QtUi")
        QtUi.resize(600, 480)
        self.central_widget = QWidget(QtUi)
        self.central_widget.setObjectName(u"central_widget")
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setSpacing(1)
        self.main_layout.setObjectName(u"main_layout")
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        self.header = Header(self.central_widget)
        self.header.setObjectName(u"header")
        self.header.setMinimumSize(QSize(0, 22))
        self.header.setMaximumSize(QSize(16777215, 22))
        font = QFont()
        font.setBold(True)
        self.header.setFont(font)

        self.main_layout.addWidget(self.header)

        self.input_group = QGroupBox(self.central_widget)
        self.input_group.setObjectName(u"input_group")
        self.input_layout = QVBoxLayout(self.input_group)
        self.input_layout.setSpacing(4)
        self.input_layout.setObjectName(u"input_layout")
        self.input_layout.setContentsMargins(6, 6, 6, 6)
        self.txt_input = LineEdit(self.input_group)
        self.txt_input.setObjectName(u"txt_input")
        self.txt_input.setMinimumSize(QSize(0, 22))
        self.txt_input.setReadOnly(True)

        self.input_layout.addWidget(self.txt_input)

        self.combobox_layout = QHBoxLayout()
        self.combobox_layout.setSpacing(4)
        self.combobox_layout.setObjectName(u"combobox_layout")
        self.cmb_options = ComboBox(self.input_group)
        self.cmb_options.setObjectName(u"cmb_options")
        self.cmb_options.setMinimumSize(QSize(0, 22))

        self.combobox_layout.addWidget(self.cmb_options)

        self.cmb_view = WidgetComboBox(self.input_group)
        self.cmb_view.setObjectName(u"cmb_view")
        self.cmb_view.setMinimumSize(QSize(120, 22))
        self.cmb_view.setMaximumSize(QSize(150, 22))

        self.combobox_layout.addWidget(self.cmb_view)


        self.input_layout.addLayout(self.combobox_layout)


        self.main_layout.addWidget(self.input_group)

        self.tree_group = QGroupBox(self.central_widget)
        self.tree_group.setObjectName(u"tree_group")
        self.tree_layout = QVBoxLayout(self.tree_group)
        self.tree_layout.setSpacing(1)
        self.tree_layout.setObjectName(u"tree_layout")
        self.tree_layout.setContentsMargins(0, 0, 0, 0)
        self.tree_demo = TreeWidget(self.tree_group)
        self.tree_demo.setObjectName(u"tree_demo")
        self.tree_demo.setMinimumSize(QSize(0, 120))
        self.tree_demo.setAlternatingRowColors(False)

        self.tree_layout.addWidget(self.tree_demo)


        self.main_layout.addWidget(self.tree_group)

        self.output_group = CollapsableGroup(self.central_widget)
        self.output_group.setObjectName(u"output_group")
        self.output_group.setAlignment(Qt.AlignCenter)
        self.output_layout = QVBoxLayout(self.output_group)
        self.output_layout.setSpacing(1)
        self.output_layout.setObjectName(u"output_layout")
        self.output_layout.setContentsMargins(0, 0, 0, 0)
        self.txt_output = QTextEdit(self.output_group)
        self.txt_output.setObjectName(u"txt_output")
        self.txt_output.setMinimumSize(QSize(0, 80))
        self.txt_output.setReadOnly(True)
        self.txt_output.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.output_layout.addWidget(self.txt_output)


        self.main_layout.addWidget(self.output_group)

        self.test_layout = QHBoxLayout()
        self.test_layout.setSpacing(0)
        self.test_layout.setObjectName(u"test_layout")
        self.test_layout.setContentsMargins(0, 0, 0, 0)
        self.spinbox = QSpinBox(self.central_widget)
        self.spinbox.setObjectName(u"spinbox")
        self.spinbox.setMaximumSize(QSize(0, 0))
        self.spinbox.setMaximum(100)
        self.spinbox.setValue(50)

        self.test_layout.addWidget(self.spinbox)

        self.checkbox = QCheckBox(self.central_widget)
        self.checkbox.setObjectName(u"checkbox")
        self.checkbox.setMaximumSize(QSize(0, 0))

        self.test_layout.addWidget(self.checkbox)

        self.button_a = PushButton(self.central_widget)
        self.button_a.setObjectName(u"button_a")
        self.button_a.setMaximumSize(QSize(0, 0))

        self.test_layout.addWidget(self.button_a)

        self.button_b = PushButton(self.central_widget)
        self.button_b.setObjectName(u"button_b")
        self.button_b.setMaximumSize(QSize(0, 0))

        self.test_layout.addWidget(self.button_b)


        self.main_layout.addLayout(self.test_layout)

        self.footer = Footer(self.central_widget)
        self.footer.setObjectName(u"footer")
        self.footer.setMinimumSize(QSize(0, 18))
        self.footer.setMaximumSize(QSize(16777215, 18))

        self.main_layout.addWidget(self.footer)

        QtUi.setCentralWidget(self.central_widget)

        self.retranslateUi(QtUi)

        QMetaObject.connectSlotsByName(QtUi)
    # setupUi

    def retranslateUi(self, QtUi):
        QtUi.setWindowTitle(QCoreApplication.translate("QtUi", u"UITK Example", None))
        self.header.setText(QCoreApplication.translate("QtUi", u"EXAMPLE", None))
        self.input_group.setTitle(QCoreApplication.translate("QtUi", u"Navigation", None))
        self.txt_input.setPlaceholderText(QCoreApplication.translate("QtUi", u"Path to uitk package", None))
#if QT_CONFIG(tooltip)
        self.txt_input.setToolTip(QCoreApplication.translate("QtUi", u"File path to the uitk package root", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.cmb_options.setToolTip(QCoreApplication.translate("QtUi", u"Select package to browse", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.cmb_view.setToolTip(QCoreApplication.translate("QtUi", u"View options", None))
#endif // QT_CONFIG(tooltip)
        self.tree_group.setTitle(QCoreApplication.translate("QtUi", u"Package Explorer", None))
        ___qtreewidgetitem = self.tree_demo.headerItem()
        ___qtreewidgetitem.setText(2, QCoreApplication.translate("QtUi", u"Type", None));
        ___qtreewidgetitem.setText(1, QCoreApplication.translate("QtUi", u"Value", None));
        ___qtreewidgetitem.setText(0, QCoreApplication.translate("QtUi", u"Item", None));
        self.output_group.setTitle(QCoreApplication.translate("QtUi", u"\u2022 \u2022 \u2022", None))
        self.checkbox.setText(QCoreApplication.translate("QtUi", u"Test", None))
        self.button_a.setText(QCoreApplication.translate("QtUi", u"A", None))
        self.button_b.setText(QCoreApplication.translate("QtUi", u"B", None))
    # retranslateUi

