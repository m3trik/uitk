#!/usr/bin/env python

import os
import sys

# Add the uitk package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from uitk.file_manager import FileManager


def simulate_switchboard_call():
    """Simulate the call pattern from switchboard.py"""
    fm = FileManager()

    # This simulates creating a container from switchboard.py
    widget_registry = fm.create(
        "widget_registry",
        [],  # Start with empty list
        fields=["classname", "classobj", "filename", "filepath"],
        inc_files="*.py",
    )

    print(f"Created widget registry: {widget_registry}")
    print(f"Registry length: {len(widget_registry)}")

    # This simulates the extend call that's failing
    print('\nTesting extend with "widgets" and base_dir=0:')
    try:
        widget_registry.extend("widgets", base_dir=0)
        print(f"Extended registry length: {len(widget_registry)}")
        print("SUCCESS: Extend worked")
    except Exception as e:
        print(f"ERROR: {e}")

        # Let's test what the correct path should be
        current_file = __file__
        current_dir = os.path.dirname(current_file)
        expected_widgets_path = os.path.join(current_dir, "uitk", "widgets")
        print(f"Current file: {current_file}")
        print(f"Current dir: {current_dir}")
        print(f"Expected widgets path: {expected_widgets_path}")
        print(f"Expected path exists: {os.path.exists(expected_widgets_path)}")

        # Test with absolute path
        try:
            print("\nTesting with absolute path:")
            widget_registry.extend(expected_widgets_path)
            print(
                f"SUCCESS: Absolute path worked, registry length: {len(widget_registry)}"
            )
        except Exception as e2:
            print(f"ERROR with absolute path: {e2}")


if __name__ == "__main__":
    simulate_switchboard_call()
