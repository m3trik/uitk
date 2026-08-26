# !/usr/bin/python
# coding=utf-8
"""Unit tests for ``Tooltip.template_description``.

What a bridge panel logs when the user switches template. The Lua branch
serves two audiences out of ONE comment block -- the artist picking a preset
and whoever maintains the script -- so the split between them has to be
mechanical: the first paragraph is the artist's, everything after the first
empty ``--`` line is the maintainer's, and lines carrying a ``__TOKEN__``
placeholder are machine directives that belong to neither.

Pins the live report behind that: a rizom preset switch used to dump its
whole header -- measured-behaviour notes, host-version constraints, the
``scope=__SCOPE__`` marker -- into the log panel.

The SHIPPED presets are guarded downstream, in mayatk's
``test_uv_rizom_bridge`` -- uitk is upstream of the DCC packages and must
not reach into them (it is also where the mayatk/blendertk twin check
already lives).
"""

import tempfile
import unittest
from pathlib import Path

from uitk.bridge.tooltip import Tooltip


class LuaTemplateDescriptionTest(unittest.TestCase):
    """The ``.lua`` branch: leading summary paragraph only."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)

    def _write(self, text: str) -> Path:
        path = self.root / "preset.lua"
        path.write_text(text, encoding="utf-8")
        return path

    def test_stops_at_the_first_paragraph_break(self):
        """Maintainer rationale below an empty ``--`` line is not user-facing."""
        path = self._write(
            "-- Repack existing UV islands into the target tile.\n"
            "-- Use when seams are already cut and unfolded.\n"
            "--\n"
            "-- Measured 2026-08-17 on 2020.1: the old inline pack was a NO-OP,\n"
            "-- so LayoutScalingMode 0/1/2 all saved byte-identical output.\n"
            "\n"
            "ZomPack({})\n"
        )
        self.assertEqual(
            Tooltip.template_description(path),
            "Repack existing UV islands into the target tile.\n"
            "Use when seams are already cut and unfolded.",
        )

    def test_skips_a_leading_separator(self):
        """A header that opens with ``--`` still yields its summary."""
        path = self._write("--\n-- The summary.\n--\n-- The rationale.\n")
        self.assertEqual(Tooltip.template_description(path), "The summary.")

    def test_drops_placeholder_directives(self):
        """``scope=__SCOPE__`` is aimed at referenced_keys, not at the artist."""
        path = self._write(
            "-- Send to RizomUV (one-way).\n"
            "-- Host-side export scope (echoed so the panel exposes the\n"
            "-- Scope combo): scope=__SCOPE__\n"
        )
        self.assertEqual(
            Tooltip.template_description(path),
            "Send to RizomUV (one-way).\n"
            "Host-side export scope (echoed so the panel exposes the",
        )

    def test_blank_line_and_code_still_end_the_block(self):
        path = self._write("-- Summary.\n\n-- Not part of it.\n")
        self.assertEqual(Tooltip.template_description(path), "Summary.")

        path = self._write("-- Summary.\nZomPack({})\n-- Not part of it.\n")
        self.assertEqual(Tooltip.template_description(path), "Summary.")

    def test_no_comment_block_is_none(self):
        self.assertIsNone(Tooltip.template_description(self._write("ZomPack({})\n")))
        self.assertIsNone(Tooltip.template_description(self.root / "missing.lua"))

    def test_unknown_extension_is_none(self):
        path = self.root / "preset.txt"
        path.write_text("-- Summary.\n", encoding="utf-8")
        self.assertIsNone(Tooltip.template_description(path))


if __name__ == "__main__":
    unittest.main()
