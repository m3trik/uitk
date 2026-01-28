"""Temporary test file for duplicate_linear restore behavior.

This test mimics the EXACT duplicate_linear scenario:
- Spinboxes have UI file defaults (e.g., 0)
- Slots.__init__ does NOT change spinbox values
- Session state restores spinboxes to previous values (e.g., 50)
- Reset should restore to UI file defaults (0), not session values (50)
"""

from qtpy import QtWidgets


class TempTestSlots:
    """Mimics DuplicateLinearSlots - does NOT set spinbox values."""

    def __init__(self, switchboard):
        self.sb = switchboard
        self.ui = self.sb.loaded_ui.temp_test

        # Like duplicate_linear: access widgets but DON'T set spinbox values
        # The spinbox keeps its UI file default (0)
        print(f"[Slots.__init__] s000 value (UI file default): {self.ui.s000.value()}")
        print(
            f"[Slots.__init__] s000 in _defaults: {self.ui.s000 in self.ui.state._defaults}"
        )
