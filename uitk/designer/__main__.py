# !/usr/bin/python
# coding=utf-8
"""``python -m uitk.designer`` — open Qt Designer with uitk's widgets loaded.

python -m uitk.designer                  # empty Designer
python -m uitk.designer my_form.ui       # open a form
python -m uitk.designer --list           # print the catalog and exit
"""

import argparse
import logging
import sys

from uitk.designer._designer import DesignerPlugin


def main(argv=None) -> int:
    """Parse arguments and either list the catalog or launch Qt Designer."""
    parser = argparse.ArgumentParser(
        prog="python -m uitk.designer",
        description="Open Qt Designer with uitk's custom widgets in the widget box.",
    )
    parser.add_argument("ui_files", nargs="*", help=".ui file(s) to open on start")
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the widgets that would be registered, then exit",
    )
    parser.add_argument(
        "--plugin-dir",
        action="append",
        default=[],
        metavar="DIR",
        help="extra directory holding a register*.py entry file (repeatable)",
    )
    parser.add_argument(
        "--python-path",
        action="append",
        default=[],
        metavar="DIR",
        help="extra import root Designer should see (repeatable)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.list:
        for widget in DesignerPlugin.collect():
            marker = " [container]" if widget.container else ""
            print(f"{widget.name:20s} {widget.base:18s} {widget.module}{marker}")
        return 0

    try:
        return DesignerPlugin.launch(
            *args.ui_files,
            plugin_dirs=args.plugin_dir or None,
            python_paths=args.python_path or None,
        )
    except FileNotFoundError as error:
        # The one expected failure — Designer isn't installed. A CLI should say
        # so in a sentence, not in a traceback.
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
