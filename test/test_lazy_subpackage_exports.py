# !/usr/bin/python
# coding=utf-8
"""Lazy subpackage re-export contract.

Three uitk subpackages publish a class surface from their ``__init__``:
``uitk.bridge``, ``uitk.widgets.sequencer`` and
``uitk.widgets.editors.shortcut_editor``. Downstream packages import from
those package paths (``from uitk.bridge import AttributeSpec``), so the
names are public API and must stay resolvable.

They are resolved lazily (PEP 562 module ``__getattr__``) rather than by
eager ``from .submodule import ...`` at package-import time. That matters
beyond taste: ``uitk/__init__.py`` bootstraps through
``pythontk.core_utils.module_resolver.bootstrap_package``, whose
``pkgutil.walk_packages`` scan **imports every subpackage ``__init__``**.
An eager re-export there is therefore paid by every plain ``import uitk``
in the ecosystem, not only by the callers that want the widget.

This module pins both halves: the names stay importable, and importing
does not drag the implementation modules in.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

from conftest import BaseTestCase, PACKAGE_ROOT


# Public surface per subpackage, as published before the lazy conversion.
# Underscore-prefixed sequencer entries are shared layout constants and
# internal item classes that the widget's consumers (and this repo's own
# tests) import by name; they are part of the re-export surface even though
# ``import *`` never exported them.
SEQUENCER_EXPORTS = (
    "AttributeColorDialog",
    "ClipData",
    "ClipItem",
    "CurveUtils",
    "FrameTooltip",
    "HATCH_DENSE",
    "HATCH_MEDIUM",
    "HATCH_SPARSE",
    "KeyframeItem",
    "MarkerData",
    "MarkerItem",
    "MenuUtils",
    "PatternPainter",
    "PatternRegistry",
    "PatternSpec",
    "PlayController",
    "PlayheadItem",
    "RangeHighlightItem",
    "RulerItem",
    "ScrubPlayer",
    "ScrubPlayerPlayController",
    "SequencerWidget",
    "TimelineScene",
    "TimelineView",
    "TrackData",
    "TrackHeaderWidget",
    "TransportControls",
    "_COMMON_ATTRIBUTES",
    "_DEFAULT_ATTRIBUTE_COLORS",
    "_DISPLAY_COLORS",
    "_ElidingLabel",
    "_GapOverlayItem",
    "_HANDLE_WIDTH",
    "_MENU_STYLESHEET",
    "_MIN_CLIP_DURATION",
    "_MIN_POINT_CLIP_WIDTH",
    "_RULER_HEIGHT",
    "_SHOT_LANE_HEIGHT",
    "_SUB_ROW_HEIGHT",
    "_StaticRangeOverlay",
    "_TRACK_HEIGHT",
    "_TRACK_PADDING",
)

BRIDGE_EXPORTS = (
    "AttributeSpec",
    "BridgeParam",
    "BridgeSlotsBase",
    "Formatters",
    "KindFactory",
    "KindHandler",
    "Parameters",
    "Tooltip",
)

SHORTCUT_EDITOR_EXPORTS = (
    "CollisionConflict",
    "ManagerSwitchboardFacade",
    "RegistrySwitchboardFacade",
    "ShortcutEditor",
)

SURFACE = {
    "uitk.widgets.sequencer": SEQUENCER_EXPORTS,
    "uitk.bridge": BRIDGE_EXPORTS,
    "uitk.widgets.editors.shortcut_editor": SHORTCUT_EDITOR_EXPORTS,
}

# Submodules that must NOT be in ``sys.modules`` until something actually
# reaches for a name they define. These are the heavy trees the eager
# re-exports used to pull in.
LAZY_SUBMODULES = {
    "uitk.widgets.sequencer": (
        "uitk.widgets.sequencer._sequencer",
        "uitk.widgets.sequencer._timeline",
        "uitk.widgets.sequencer._clip",
        "uitk.widgets.sequencer._data",
    ),
    "uitk.bridge": (
        "uitk.bridge.slots",
        "uitk.bridge.spec",
        "uitk.bridge.parameters",
    ),
    "uitk.widgets.editors.shortcut_editor": (
        "uitk.widgets.editors.shortcut_editor.registry_editor",
        "uitk.widgets.editors.shortcut_editor.registry_facade",
        "uitk.widgets.editors.shortcut_editor.manager_facade",
    ),
}


def _run_probe(source: str) -> str:
    """Execute *source* in a fresh interpreter that can see this checkout.

    Parameters:
        source (str): Python source to run.

    Returns:
        str: The child's stdout, stripped.

    Raises:
        AssertionError: If the child exits non-zero.
    """
    import os

    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PACKAGE_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(PACKAGE_ROOT)),
    )
    assert proc.returncode == 0, (
        f"probe failed (rc={proc.returncode}):\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    return proc.stdout.strip()


class TestLazySubpackageSurface(BaseTestCase):
    """Every previously-importable name is still importable."""

    def test_every_public_name_resolves(self):
        """Each documented name resolves off its subpackage."""
        import importlib

        for pkg, names in SURFACE.items():
            module = importlib.import_module(pkg)
            for name in names:
                with self.subTest(package=pkg, name=name):
                    self.assertTrue(
                        hasattr(module, name),
                        f"{pkg}.{name} is no longer importable",
                    )

    def test_from_import_form_works(self):
        """``from <pkg> import <name>`` still binds every name."""
        for pkg, names in SURFACE.items():
            src = f"from {pkg} import (\n" + "".join(f"    {n},\n" for n in names) + ")"
            with self.subTest(package=pkg):
                ns = {}
                exec(compile(src, f"<{pkg}-from-import>", "exec"), ns)
                for name in names:
                    self.assertIn(name, ns)

    def test_star_import_surface_unchanged(self):
        """``import *`` exports exactly the non-underscore public names."""
        expected = {
            "uitk.widgets.sequencer": {
                n for n in SEQUENCER_EXPORTS if not n.startswith("_")
            },
            "uitk.bridge": set(BRIDGE_EXPORTS),
            "uitk.widgets.editors.shortcut_editor": set(SHORTCUT_EDITOR_EXPORTS),
        }
        for pkg, names in expected.items():
            with self.subTest(package=pkg):
                ns = {}
                exec(compile(f"from {pkg} import *", "<star>", "exec"), ns)
                exported = {k for k in ns if not k.startswith("__")}
                self.assertEqual(exported, names)

    def test_all_is_published(self):
        """``__all__`` exists and covers the non-underscore names."""
        import importlib

        for pkg, names in SURFACE.items():
            with self.subTest(package=pkg):
                module = importlib.import_module(pkg)
                self.assertTrue(hasattr(module, "__all__"), f"{pkg} has no __all__")
                self.assertEqual(
                    set(module.__all__),
                    {n for n in names if not n.startswith("_")},
                )

    def test_dir_lists_the_surface(self):
        """``dir()`` advertises the lazy names for IDE / tab completion."""
        import importlib

        for pkg, names in SURFACE.items():
            with self.subTest(package=pkg):
                listed = set(dir(importlib.import_module(pkg)))
                self.assertTrue(set(names).issubset(listed))

    def test_unknown_name_raises_attribute_error(self):
        """A bogus name still raises ``AttributeError``, not ``ImportError``."""
        import importlib

        for pkg in SURFACE:
            with self.subTest(package=pkg):
                module = importlib.import_module(pkg)
                with self.assertRaises(AttributeError):
                    getattr(module, "NoSuchSymbol_xyz")


class TestSubpackageImportIsLazy(BaseTestCase):
    """Importing the subpackage must not import its implementation modules."""

    def test_subpackage_import_does_not_load_submodules(self):
        """``import <pkg>`` leaves the heavy submodules unimported."""
        for pkg, submodules in LAZY_SUBMODULES.items():
            with self.subTest(package=pkg):
                out = _run_probe(
                    f"""
                    import sys
                    import {pkg}
                    loaded = [m for m in {submodules!r} if m in sys.modules]
                    print(",".join(loaded))
                    """
                )
                self.assertEqual(
                    out,
                    "",
                    f"import {pkg} eagerly loaded: {out}",
                )

    def test_first_attribute_access_resolves(self):
        """Touching a name imports its module and returns the real object."""
        probes = {
            "uitk.bridge": ("BridgeSlotsBase", "uitk.bridge.slots"),
            "uitk.widgets.sequencer": (
                "SequencerWidget",
                "uitk.widgets.sequencer._sequencer",
            ),
            "uitk.widgets.editors.shortcut_editor": (
                "ShortcutEditor",
                "uitk.widgets.editors.shortcut_editor.registry_editor",
            ),
        }
        for pkg, (name, submodule) in probes.items():
            with self.subTest(package=pkg):
                out = _run_probe(
                    f"""
                    import sys, importlib
                    pkg = importlib.import_module({pkg!r})
                    obj = getattr(pkg, {name!r})
                    canonical = getattr(
                        importlib.import_module({submodule!r}), {name!r}
                    )
                    print(obj is canonical, {submodule!r} in sys.modules)
                    """
                )
                self.assertEqual(out, "True True")


class TestRootImportStaysLight(BaseTestCase):
    """``import uitk`` must not drag the three heavy trees in.

    ``bootstrap_package`` walks the package with ``pkgutil.walk_packages``,
    which imports every subpackage ``__init__``. Eager re-exports there are
    charged to every consumer of the root package.
    """

    HEAVY = (
        "uitk.widgets.sequencer._sequencer",
        "uitk.widgets.sequencer._timeline",
        "uitk.bridge.slots",
        "uitk.widgets.editors.shortcut_editor.registry_editor",
    )

    def test_plain_import_uitk_skips_heavy_trees(self):
        """A bare ``import uitk`` loads none of the heavy implementation modules."""
        out = _run_probe(
            f"""
            import sys
            import uitk
            print(",".join(m for m in {self.HEAVY!r} if m in sys.modules))
            """
        )
        self.assertEqual(out, "", f"import uitk eagerly loaded: {out}")


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
