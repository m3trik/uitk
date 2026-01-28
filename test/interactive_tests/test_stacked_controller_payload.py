import sys
import unittest
from qtpy import QtWidgets, QtCore, QtGui

# Ensure script root is in path
if r"O:\Cloud\Code\_scripts" not in sys.path:
    sys.path.append(r"O:\Cloud\Code\_scripts")

from uitk.menus.marking_menu import MarkingMenu as StackedController
from uitk.switchboard import Switchboard


# Mock Infrastructure to avoid full UI dependency
class MockWidget(QtWidgets.QPushButton):
    def __init__(self, name="TestButton"):
        super(MockWidget, self).__init__(name)
        self.setObjectName(name)
        self.clicked_signal_received = False
        self.clicked.connect(self._on_click)

        # Mocking UI tags/properties expected by StackedController
        self.ui = type("MockUI", (), {})()
        self.ui.has_tags = lambda tags: True
        self.ui.objectName = lambda: name
        self.ui.style = type("MockStyle", (), {"set": lambda **k: None})()

        # Mock derived properties
        # In the real code, these might come from mixins or property inspection
        self.derived_type = QtWidgets.QPushButton
        self.type = "Button"

        # Mock base_name (e.g. 'btn' or 'i')
        self.base_name = lambda: "btn"

    def _on_click(self):
        self.clicked_signal_received = True
        print(f"DEBUG: Click received on {self.objectName()}")


class TestStackedControllerInteractions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QtWidgets.QApplication.instance():
            cls.app = QtWidgets.QApplication(sys.argv)

    def setUp(self):
        # Reset singleton to ensure fresh state
        if hasattr(StackedController, "_instance"):
            # We can't easily delete it if it's referenced elsewhere, but we can set the class var to None
            # The SingletonMixin implementation usually stores it in _instance
            StackedController._instance = None

        self.sb = Switchboard()
        self.controller = StackedController.instance(switchboard=self.sb)

        # Setup a dummy view/widget for the controller to manage
        self.btn = MockWidget("TargetButton")
        # Mock underMouse to always be true for these tests
        self.btn.underMouse = lambda: True

    def test_loose_chord_release(self):
        """
        Verify that releasing one button while holding another triggers the click
        if the chord logic is active. (The 'Loose Chord' requirement).
        """
        print("\nTEST: Loose Chord Release (Left Released, Right Held)")

        # Scenario: User holds Left+Right. Releases Left.
        # Event: Release Left.
        # Buttons Held: Right.

        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(10, 10),
            QtCore.Qt.LeftButton,  # Button causing event
            QtCore.Qt.RightButton,  # Buttons state (buttons currently held)
            QtCore.Qt.NoModifier,
        )

        # Execute
        result = self.controller.child_mouseButtonReleaseEvent(self.btn, event)

        # Assert
        self.assertTrue(result, "Controller should accept the event")
        self.assertTrue(
            self.btn.clicked_signal_received, "Loose chord release should trigger click"
        )

    def test_standard_release(self):
        """Verify standard single click works."""
        print("\nTEST: Standard Release")

        # Scenario: User presses Left. Releases Left. No other buttons held.
        self.btn.clicked_signal_received = False

        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(10, 10),
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoButton,  # No buttons held
            QtCore.Qt.NoModifier,
        )

        result = self.controller.child_mouseButtonReleaseEvent(self.btn, event)

        self.assertTrue(result)
        self.assertTrue(self.btn.clicked_signal_received)

    def test_transition_behavior(self):
        """Verify that holding buttons over a NON-clickable area (or mocked) does NOT click."""
        print("\nTEST: Transition Behavior (Non-Clickable)")

        # Using a minimal widget implies non-clickable
        generic_widget = QtWidgets.QWidget()
        generic_widget.underMouse = lambda: True
        generic_widget.derived_type = QtWidgets.QWidget
        generic_widget.ui = type("MockUI", (), {"has_tags": lambda t: True})()

        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(10, 10),
            QtCore.Qt.LeftButton,
            QtCore.Qt.RightButton,  # Holding Right
            QtCore.Qt.NoModifier,
        )

        # Should initiate transition / binding lookup
        # We haven't mocked bindings, so it might fail or do nothing, but it definitely should NOT error.
        # IMPORTANT: logic says `is_clickable = isinstance(...) and hasattr(..., "clicked")`
        # QWidget does not have "clicked".

        try:
            result = self.controller.child_mouseButtonReleaseEvent(
                generic_widget, event
            )
            print("Transition event handled without error.")
        except Exception as e:
            self.fail(f"Transition logic crashed: {e}")


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(
        TestStackedControllerInteractions
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    # Signal success/failure for the calling script
    if not result.wasSuccessful():
        sys.exit(1)
