#!/usr/bin/env python

# Simulate the exact call pattern from switchboard.py
import os
import sys

# This would normally be in the uitk package directory
current_dir = os.path.dirname(__file__)
uitk_dir = os.path.join(current_dir, "uitk")
sys.path.insert(0, current_dir)

from uitk.file_manager import FileManager


class MockRegistry:
    def __init__(self):
        self.fm = FileManager()
        self.widget_registry = self.fm.create(
            "widget_registry",
            [],
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )


def simulate_switchboard_init():
    """Simulate the exact initialization pattern from switchboard.py"""
    print(f"Current file: {__file__}")
    print(f"Current directory: {os.path.dirname(__file__)}")

    registry = MockRegistry()

    print(f"Initial widget registry: {registry.widget_registry}")
    print(f"Initial length: {len(registry.widget_registry)}")

    # This is the exact line that fails in switchboard.py:
    # self.registry.widget_registry.extend("widgets", base_dir=0)
    print("\nTesting the problematic extend call:")
    try:
        registry.widget_registry.extend("widgets", base_dir=0)
        print(f"SUCCESS: Extended registry length: {len(registry.widget_registry)}")
        if len(registry.widget_registry) > 0:
            print(f"First widget: {registry.widget_registry.named_tuples[0]}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    simulate_switchboard_init()
