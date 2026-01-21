# !/usr/bin/python
# coding=utf-8
"""Quick visual inspection for scrollbars and ComboBox popup clipping."""
import sys
from pathlib import Path

# Ensure package root is in sys.path
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

from qtpy import QtWidgets, QtCore
from uitk.widgets.mixins.style_sheet import StyleSheet


def build_ui():
    window = QtWidgets.QMainWindow()
    window.setWindowTitle("UITK Scrollbar + ComboBox Inspect")
    window.resize(800, 520)

    central = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(central)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    info = QtWidgets.QLabel(
        "Inspect: ComboBox popup right border + Table scrollbars.\n"
        "Close window to exit."
    )
    layout.addWidget(info)

    combo = QtWidgets.QComboBox()
    combo.setMinimumWidth(260)
    for i in range(50):
        combo.addItem(f"Item {i:02d} - long text for clipping test")
    layout.addWidget(combo)

    table = QtWidgets.QTableWidget(30, 5)
    table.setHorizontalHeaderLabels([f"Col {i}" for i in range(1, 6)])
    for r in range(30):
        for c in range(5):
            table.setItem(r, c, QtWidgets.QTableWidgetItem(f"R{r:02d} C{c}"))
    table.horizontalHeader().setStretchLastSection(True)
    table.setMinimumHeight(240)
    layout.addWidget(table)

    # Extra scroll area for vertical scroll visibility
    scroll_area = QtWidgets.QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_content = QtWidgets.QWidget()
    scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
    for i in range(40):
        scroll_layout.addWidget(QtWidgets.QLabel(f"Scroll item {i:02d}"))
    scroll_area.setWidget(scroll_content)
    scroll_area.setMinimumHeight(140)
    layout.addWidget(scroll_area)

    window.setCentralWidget(central)
    return window


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    window = build_ui()
    StyleSheet().set(window, theme="light", recursive=True)
    window.show()

    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
