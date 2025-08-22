#!/usr/bin/env python

from uitk.file_manager import FileManager
import inspect
import os


def test_from_file():
    fm = FileManager()

    print("Current working directory:", os.getcwd())
    print("This file location:", __file__)
    print("This file directory:", os.path.dirname(__file__))

    stack = inspect.stack()
    print("\nStack frames:")
    for i, frame in enumerate(stack):
        print(f"  {i}: {frame.filename}")

    # Test the unique filtering (as done in get_base_dir)
    unique_frames = {frame.filename: frame for frame in stack}
    filtered_stack = list(unique_frames.values())[1:]
    print(f"\nFiltered stack (excluding frame 0):")
    for i, frame in enumerate(filtered_stack):
        print(f"  {i}: {frame.filename}")

    print("\nTesting base_dir resolution:")
    for i in range(3):
        try:
            base_dir = fm.get_base_dir(i)
            print(f"  base_dir({i}): {base_dir}")
        except IndexError:
            print(f"  base_dir({i}): IndexError")

    print("\nTesting path resolution:")
    resolved = fm.resolve_path("widgets", base_dir=0)
    print(f'  Resolved "widgets" with base_dir=0: {resolved}')
    print(f'  Path exists: {os.path.exists(resolved) if resolved else "None"}')

    # Test the correct path
    correct_path = os.path.join(os.path.dirname(__file__), "uitk", "widgets")
    print(f"  Expected path: {correct_path}")
    print(f"  Expected path exists: {os.path.exists(correct_path)}")


if __name__ == "__main__":
    test_from_file()
