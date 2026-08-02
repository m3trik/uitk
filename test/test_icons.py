# !/usr/bin/python
# coding=utf-8
"""Invariants for the shipped SVG icon set (uitk/icons).

Pins the 2026 icon-set regularization: every icon is a 16x16 SVG drawn in a
single visual grammar (stroke #888888 / width 1.5 for themeable glyphs) so
IconManager's colorize pipeline can retint the whole set. The QSS-only tree
family (consumed by file path in treeWidget.py, never colorized) keeps its
hardcoded dark-theme palette and full-bleed guides.

Run standalone: python -m test.test_icons
"""

import re
import unittest
from pathlib import Path

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtGui, QtSvg  # noqa: E402

from uitk.managers.icon_manager import IconManager  # noqa: E402

ICON_DIR = Path(__file__).resolve().parent.parent / "uitk" / "icons"

# Consumed via file paths in treeWidget.py QSS (never colorized); drawn
# edge-to-edge by design and allowed a hardcoded dark-theme palette.
TREE_FAMILY = {
    "tree_vertical",
    "tree_horizontal",
    "tree_branch",
    "tree_end",
    "expand_end",
    "expand_branch",
    "collapse_end",
    "collapse_branch",
}

PLACEHOLDER = "#888888"


def _render(svg_text: str, scale: int = 4):
    """Rasterize SVG text at 16*scale px; return (QImage, ink_bbox|None)."""
    size = 16 * scale
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg_text.encode("utf-8")))
    if not renderer.isValid():
        return None, None
    img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
    img.fill(0)
    painter = QtGui.QPainter(img)
    renderer.render(painter, QtCore.QRectF(0, 0, size, size))
    painter.end()
    xs, ys = [], []
    for y in range(size):
        for x in range(size):
            if (img.pixel(x, y) >> 24) & 0xFF > 8:
                xs.append(x)
                ys.append(y)
    if not xs:
        return img, None
    return img, (min(xs), min(ys), max(xs), max(ys))


class TestIconAssets(QtBaseTestCase):
    """Whole-set invariants; failures name the offending icon."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.svgs = {
            p.stem: p.read_text(encoding="utf-8")
            for p in sorted(ICON_DIR.glob("*.svg"))
        }

    def test_set_is_nonempty(self):
        self.assertGreater(len(self.svgs), 100)

    def test_all_icons_declare_16x16_viewbox(self):
        bad = [
            name
            for name, text in self.svgs.items()
            if 'viewBox="0 0 16 16"' not in text
        ]
        self.assertEqual(bad, [], f"icons without a 16x16 viewBox: {bad}")

    def test_all_icons_render_non_blank(self):
        blank = []
        for name, text in self.svgs.items():
            _, bbox = _render(text)
            if bbox is None:
                blank.append(name)
        self.assertEqual(blank, [], f"icons that render blank/invalid: {blank}")

    def test_themeable_icons_use_only_the_placeholder_color(self):
        """Colorize replaces fill/stroke wholesale; a stray literal color would
        survive some paths and break dark/light retinting."""
        bad = []
        for name, text in self.svgs.items():
            if name in TREE_FAMILY:
                continue
            colors = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{3,8}", text)}
            if colors - {PLACEHOLDER}:
                bad.append((name, sorted(colors - {PLACEHOLDER})))
        self.assertEqual(bad, [], f"non-placeholder colors found: {bad}")

    def test_colorize_pipeline_retints_every_themeable_icon(self):
        target = "#12ab34"
        stubborn = []
        for name, text in self.svgs.items():
            if name in TREE_FAMILY:
                continue
            recolored = IconManager._colorize_svg(text, target)
            if PLACEHOLDER in recolored or target not in recolored:
                stubborn.append(name)
        self.assertEqual(stubborn, [], f"icons the theme pipeline can't retint: {stubborn}")

    def test_themeable_ink_stays_inside_safe_margins(self):
        """Out-of-viewBox geometry clips silently (the old redo.svg bug)."""
        scale = 4
        bad = []
        for name, text in self.svgs.items():
            if name in TREE_FAMILY:
                continue
            _, bbox = _render(text, scale)
            if bbox is None:
                continue  # covered by the non-blank test
            lo = min(bbox[0], bbox[1]) / scale
            hi = (max(bbox[2], bbox[3]) + 1) / scale
            if lo < 0.2 or hi > 15.8:
                bad.append(f"{name} [{lo:.2f}..{hi:.2f}]")
        self.assertEqual(bad, [], f"ink outside safe margins: {bad}")


if __name__ == "__main__":
    unittest.main()
