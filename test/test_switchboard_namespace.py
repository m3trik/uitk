# !/usr/bin/python
# coding=utf-8
"""``SwitchboardNamespaceMixin`` — the Switchboard as the single uitk entry point.

Consumers that already hold a Switchboard (every slot class gets ``self.sb`` for
free) reach uitk through it rather than importing uitk and hard-coding which
submodule a class currently lives in.

The fallback is only safe because of two invariants, both pinned here rather than
asserted in a comment:

1. it never runs for a name normal lookup resolves (so no Switchboard attribute,
   property or method can be shadowed), and
2. uitk's public names cannot collide with the Switchboard's own API, nor with the
   ``getattr(sb, "...", None)`` probes scattered across uitk and the DCC packages —
   uitk's surface is entirely CamelCase classes, those are all snake_case.
"""
import unittest

from qtpy import QtWidgets

import uitk
from uitk import Switchboard


class _SwitchboardTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.sb = Switchboard()


class TestNamespaceFallback(_SwitchboardTestCase):
    """Public uitk symbols resolve off the Switchboard."""

    def test_resolves_manager_classes(self):
        self.assertIs(self.sb.IconManager, uitk.IconManager)
        self.assertIs(self.sb.RecentValuesStore, uitk.RecentValuesStore)

    def test_resolves_widget_classes(self):
        self.assertIs(self.sb.PushButton, uitk.PushButton)
        self.assertIs(self.sb.Footer, uitk.Footer)

    def test_resolves_every_public_uitk_name(self):
        """No enumeration in the mixin — the whole surface comes for free, so a
        newly registered uitk class needs no Switchboard edit."""
        missing = [
            n for n in (uitk.__all__ or []) if getattr(self.sb, n, None) is not getattr(uitk, n)
        ]
        self.assertEqual(missing, [], f"unreachable via the Switchboard: {missing}")


class TestFallbackNeverShadows(_SwitchboardTestCase):
    """Invariant 1 — ``__getattr__`` runs only after normal lookup fails."""

    def test_switchboard_attributes_win(self):
        """``sb.style`` is the Switchboard's own shortcut property, not a uitk lookup."""
        self.assertIs(self.sb.style, uitk.StyleSheet)  # same object...
        self.assertIn("style", dir(type(self.sb)))  # ...but resolved as a real property

    def test_instance_namespaces_are_untouched(self):
        self.assertEqual(
            type(self.sb.registered_widgets).__name__, "NamespaceHandler"
        )

    def test_mixin_is_last_in_the_mro(self):
        """Placed last so it can never pre-empt a real attribute from another base."""
        from uitk.switchboard.namespace import SwitchboardNamespaceMixin

        mro = [c for c in Switchboard.__mro__ if c is not object]
        self.assertIs(mro[-1], SwitchboardNamespaceMixin)


class TestFallbackRefusals(_SwitchboardTestCase):
    """A miss must still read as a miss — the fallback is not a catch-all."""

    def test_unknown_name_raises(self):
        with self.assertRaises(AttributeError):
            self.sb.definitely_not_a_uitk_symbol

    def test_typo_on_a_real_attribute_still_raises(self):
        with self.assertRaises(AttributeError):
            self.sb.registerd_widgets  # noqa: B018 — deliberate typo

    def test_error_names_the_switchboard_not_uitk(self):
        with self.assertRaises(AttributeError) as ctx:
            self.sb.no_such_thing
        self.assertIn("Switchboard", str(ctx.exception))

    def test_uitk_private_module_state_is_not_published(self):
        """The gate is ``uitk.__all__``, not a bare ``getattr(uitk, name)``.

        ``resolve`` consults the package ``__dict__`` first, so a plain getattr also
        reaches uitk's own module globals. Two of them — ``configure`` and
        ``export_all`` — are snake_case, and would land in the space
        :class:`TestCollisionInvariant` reserves for the Switchboard: a
        ``getattr(sb, "configure", None)`` probe would start returning uitk's
        resolver method instead of ``None``.
        """
        for name in (
            "DEFAULT_INCLUDE",
            "bootstrap_package",
            "importlib",
            "CLASS_TO_MODULE",
            "METHOD_TO_MODULE",
            "PACKAGE_RESOLVER",
            "configure",
            "export_all",
            "build_dictionaries",
            "import_module",
        ):
            with self.subTest(name=name):
                self.assertFalse(
                    hasattr(self.sb, name),
                    f"uitk private module state leaked onto the Switchboard: {name}",
                )

    def test_registered_symbol_keeps_its_own_resolution_error(self):
        """A symbol uitk *knows* but cannot resolve — a broken import behind it —
        must keep uitk's own diagnostic. Reporting "not a public uitk symbol" would
        send a reader hunting for a missing export instead of the real ImportError.

        Stands in a stub uitk whose symbol is registered but raises on access; the
        mixin must let that error through untouched.
        """
        import sys

        from uitk.switchboard.namespace import SwitchboardNamespaceMixin

        class _StubUitk:
            __all__ = ["Boom"]

            def __getattr__(self, name):
                raise AttributeError(
                    f"Failed to resolve '{name}' in 'uitk'. Original Error: boom"
                )

        saved = sys.modules["uitk"]
        sys.modules["uitk"] = _StubUitk()
        try:
            with self.assertRaises(AttributeError) as ctx:
                SwitchboardNamespaceMixin.__getattr__(self.sb, "Boom")
            self.assertIn("Original Error: boom", str(ctx.exception))
            self.assertNotIn("not a public uitk symbol", str(ctx.exception))
        finally:
            sys.modules["uitk"] = saved

    def test_underscore_names_are_refused_by_the_guard(self):
        """Qt / copy / pickle probe dunders on every QObject; the fallback must
        refuse them outright rather than round-tripping through the package
        resolver. Asserted against ``__getattr__`` directly: some dunders
        (``object.__getstate__``, new in 3.11) resolve normally and so never reach
        it, which would make a plain ``hasattr`` check prove nothing."""
        from uitk.switchboard.namespace import SwitchboardNamespaceMixin

        for name in ("_private", "__deepcopy__", "__getstate__", "__setstate__"):
            with self.subTest(name=name):
                with self.assertRaises(AttributeError):
                    SwitchboardNamespaceMixin.__getattr__(self.sb, name)

    def test_absent_dunder_probe_stays_absent(self):
        """End-to-end: a dunder neither Qt nor object defines must still miss."""
        self.assertFalse(hasattr(self.sb, "__deepcopy__"))


class TestCollisionInvariant(_SwitchboardTestCase):
    """Invariant 2 — the two namespaces cannot overlap.

    Asserted against what is *actually reachable* through the fallback rather than
    against ``uitk.__all__``, so it stays honest however the gate is implemented —
    reading ``__all__`` is what let the private-module-state leak
    (``sb.configure`` / ``sb.export_all``) slip past an earlier version of this file.

    A snake_case name reachable off ``sb`` is the failure mode: it could be picked up
    by one of the ``getattr(sb, "...", None)`` probes across uitk and the DCC
    packages, which all probe snake_case Switchboard attributes.
    """

    #: Every distinct name probed as ``getattr/hasattr(sb|switchboard, "<name>", ...)``
    #: across uitk, tentacle, mayatk, blendertk and extapps. Not exhaustive forever —
    #: it is a sample of the real usage the invariant protects.
    PROBED_NAMES = (
        "active_ui", "handlers", "loaded_ui", "context_tags", "editors", "parent",
        "register_command", "get_command_registry", "preset_config", "editor_title",
        "on_ui_loaded", "on_handler_entries_changed", "apply_visibility_policy",
    )

    def _reachable_via_fallback(self):
        """Names the mixin publishes — probed through it, not read off ``__all__``."""
        from uitk.switchboard.namespace import SwitchboardNamespaceMixin

        found = set()
        for name in set(uitk.__all__ or []) | set(vars(uitk)) | set(self.PROBED_NAMES):
            try:
                SwitchboardNamespaceMixin.__getattr__(self.sb, name)
            except AttributeError:
                continue
            found.add(name)
        return found

    def test_nothing_snakecase_is_reachable(self):
        offenders = sorted(n for n in self._reachable_via_fallback() if not n[:1].isupper())
        self.assertEqual(
            offenders,
            [],
            "non-CamelCase names reachable off the Switchboard can collide with "
            f"snake_case getattr(sb, ...) probes: {offenders}",
        )

    def test_no_probed_name_is_reachable(self):
        """The real usage: none of these may start resolving to a uitk symbol."""
        hijacked = sorted(set(self.PROBED_NAMES) & self._reachable_via_fallback())
        self.assertEqual(hijacked, [], f"probe names hijacked by the fallback: {hijacked}")

    def test_no_overlap_with_switchboard_api(self):
        sb_api = {n for n in dir(Switchboard) if not n.startswith("__")}
        overlap = sorted(self._reachable_via_fallback() & sb_api)
        self.assertEqual(overlap, [], f"uitk names shadowed by Switchboard API: {overlap}")


if __name__ == "__main__":
    unittest.main()
