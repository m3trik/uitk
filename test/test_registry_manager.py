# !/usr/bin/python
# coding=utf-8
"""Unit tests for uitk.managers.registry_manager (RegistryManager / FileRegistry).

This module tests the registry system backing Switchboard discovery:
- Registry creation, file discovery, and filtering
- Extension from raw paths / prebuilt tuples, duplicate handling
- Path resolution (caller frame, explicit dir, object) and the validate contract
- Location checks (case-normalized, extensionless)
- Descriptor guards and container bookkeeping
- Deprecated ``uitk.file_manager`` aliases

Run standalone: python -m test.test_registry_manager
"""

import importlib
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
import warnings
from collections import namedtuple
from pathlib import Path

from conftest import BaseTestCase, EXAMPLES_DIR, WIDGETS_DIR

from uitk.managers.registry_manager import FileRegistry, RegistryManager
from pythontk.core_utils.namedtuple_container import NamedTupleContainer

TEMP_ROOT = Path(__file__).parent / "temp_tests"

SAMPLE_MODULE = '''class SampleWidget:
    """Sample class for registry tests."""


class OtherWidget:
    """Second class so scans return multiple rows."""
'''


class TempTreeTestCase(BaseTestCase):
    """Base for tests that need a scratch file tree under temp_tests/."""

    def setUp(self):
        super().setUp()
        TEMP_ROOT.mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="registry_", dir=TEMP_ROOT))
        (self.tmp / "a.ui").write_text("<ui/>", encoding="utf-8")
        (self.tmp / "b.ui").write_text("<ui/>", encoding="utf-8")
        (self.tmp / "notes.txt").write_text("not a ui", encoding="utf-8")
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "c.ui").write_text("<ui/>", encoding="utf-8")
        (self.tmp / "sample_registry_mod.py").write_text(
            SAMPLE_MODULE, encoding="utf-8"
        )
        self.manager = RegistryManager()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def load_sample_module(self):
        """Import the scratch module from the temp tree and return it.

        Registered in ``sys.modules`` (and unregistered on teardown) so the
        class behaves like a normally-imported one — ``inspect.getfile``
        resolves through ``sys.modules[cls.__module__]``.
        """
        spec = importlib.util.spec_from_file_location(
            "sample_registry_mod", self.tmp / "sample_registry_mod.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(module)
        return module


class TestRegistryCreation(TempTreeTestCase):
    """Registry creation and record collection."""

    def test_create_collects_matching_files(self):
        registry = self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")
        self.assertIsInstance(registry, FileRegistry)
        self.assertEqual(sorted(registry.get("filename")), ["a", "b"])

    def test_create_recursive(self):
        registry = self.manager.create(
            "ui_registry", str(self.tmp), inc_files="*.ui", recursive=True
        )
        self.assertEqual(sorted(registry.get("filename")), ["a", "b", "c"])

    def test_field_query_roundtrip(self):
        registry = self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")
        path = registry.get(filename="a", return_field="filepath")
        self.assertTrue(os.path.samefile(path, self.tmp / "a.ui"))

    def test_create_makes_attribute_and_tracks_container(self):
        registry = self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")
        self.assertIs(self.manager.ui_registry, registry)
        self.assertIn(registry, self.manager.containers)

    def test_create_multiple_containers(self):
        self.manager.create("registry1", str(self.tmp), inc_files="*.ui")
        self.manager.create("registry2", str(self.tmp), inc_files="*.py")
        self.assertEqual(
            sorted(self.manager.list_containers()), ["registry1", "registry2"]
        )

    def test_create_with_tuple_of_paths(self):
        """A plain tuple of paths is a sequence of sources, not row data."""
        registry = self.manager.create(
            "ui_registry", (str(self.tmp),), inc_files="*.ui"
        )
        self.assertEqual(sorted(registry.get("filename")), ["a", "b"])
        registry.extend((str(self.tmp / "sub"),))
        self.assertEqual(sorted(registry.get("filename")), ["a", "b", "c"])

    def test_create_empty_then_extend(self):
        """The Switchboard lazily creates empty registries and extends later."""
        registry = self.manager.create("ui_registry", None, inc_files="*.ui")
        self.assertEqual(len(registry), 0)
        registry.extend(str(self.tmp))
        self.assertEqual(sorted(registry.get("filename")), ["a", "b"])

    def test_create_with_class_fields(self):
        registry = self.manager.create(
            "widget_registry",
            str(self.tmp),
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        self.assertIn("SampleWidget", registry.get("classname"))
        self.assertIn("OtherWidget", registry.get("classname"))

    def test_create_with_class_object(self):
        """Registering a class object scans its module dir and binds the object."""
        module = self.load_sample_module()
        registry = self.manager.create(
            "widget_registry",
            module.SampleWidget,
            fields=["classname", "classobj", "filename", "filepath"],
        )
        row = registry.get(classname="SampleWidget")
        self.assertTrue(row)
        self.assertIsNotNone(row[0].classobj)


class TestRegistryExtension(TempTreeTestCase):
    """FileRegistry.extend growth and duplicate handling."""

    def test_extend_deduplicates_by_default(self):
        registry = self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")
        registry.extend(str(self.tmp))
        self.assertEqual(len(registry), 2)

    def test_extend_disallows_duplicate_class_records(self):
        """Re-scanning the same module must not duplicate class rows.

        Regression (previously skipped as 'failing on Windows CI'): the
        default duplicate signature included the live ``classobj`` and
        case-sensitive filepaths, so identical rescans could re-add rows.
        FileRegistry now signs records by name + normalized location.
        """
        registry = self.manager.create(
            "widget_registry",
            str(self.tmp),
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        initial = len(registry)
        self.assertGreater(initial, 0)
        registry.extend(str(self.tmp), allow_duplicates=False)
        self.assertEqual(len(registry), initial)

    def test_extend_dedup_ignores_filepath_case(self):
        registry = self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")
        swapped = [
            nt._replace(filepath=nt.filepath.swapcase())
            for nt in registry.named_tuples
        ]
        registry.extend(swapped)
        self.assertEqual(
            len(registry), 2, "case-variant duplicates must not be re-added"
        )

    def test_extend_allows_duplicates_when_enabled(self):
        registry = self.manager.create(
            "ui_registry", str(self.tmp), inc_files="*.ui", allow_duplicates=True
        )
        registry.extend(str(self.tmp))
        self.assertEqual(len(registry), 4)

    def test_extend_with_prebuilt_tuples(self):
        registry = self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")
        registry.extend([("z", str(self.tmp / "z.ui"))])
        self.assertIn("z", registry.get("filename"))

    def test_extend_with_single_named_tuple(self):
        registry = self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")
        clone = registry.named_tuples[0]._replace(
            filename="w", filepath=str(self.tmp / "w.ui")
        )
        registry.extend(clone)
        self.assertIn("w", registry.get("filename"))

    def test_extend_with_base_dir_index(self):
        """A relative path extends against the caller's directory (this file's)."""
        registry = self.manager.create("ui_registry", None, inc_files="*.ui")
        rel = os.path.relpath(self.tmp, Path(__file__).parent)
        registry.extend(rel, base_dir=0)
        self.assertEqual(sorted(registry.get("filename")), ["a", "b"])


class TestPathResolution(TempTreeTestCase):
    """get_base_dir / resolve_path semantics."""

    def test_relative_path_resolves_against_caller_dir(self):
        rel = os.path.relpath(self.tmp, Path(__file__).parent)
        registry = self.manager.create("ui_registry", rel, inc_files="*.ui")
        self.assertEqual(sorted(registry.get("filename")), ["a", "b"])

    def test_base_dir_as_explicit_directory(self):
        registry = self.manager.create(
            "ui_registry", "sub", base_dir=str(self.tmp), inc_files="*.ui"
        )
        self.assertEqual(registry.get("filename"), ["c"])

    def test_base_dir_as_object(self):
        module = self.load_sample_module()
        registry = self.manager.create(
            "ui_registry", "sub", base_dir=module, inc_files="*.ui"
        )
        self.assertEqual(registry.get("filename"), ["c"])

    def test_base_dir_none_falls_back_to_cwd(self):
        self.assertIsNone(self.manager.get_base_dir(None))

    def test_resolve_path_normalizes(self):
        messy = str(self.tmp / "sub" / ".." / "a.ui")
        resolved = self.manager.resolve_path(messy)
        self.assertEqual(resolved, os.path.normpath(str(self.tmp / "a.ui")))

    def test_resolve_path_unresolvable_object_returns_none(self):
        """Objects without a file location resolve to None instead of raising."""
        self.assertIsNone(self.manager.resolve_path(object()))

    def test_resolve_path_validate_warn_returns_none(self):
        with self.assertLogs(self.manager.logger, level="WARNING"):
            result = self.manager.resolve_path(
                str(self.tmp / "missing_dir"), validate=1
            )
        self.assertIsNone(result)

    def test_resolve_path_validate_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.manager.resolve_path(str(self.tmp / "missing_dir"), validate=2)

    def test_recursion_guard(self):
        resolved = self.manager.resolve_path(str(self.tmp))
        self.manager.processing_stack.append(resolved)
        try:
            with self.assertRaises(RecursionError):
                self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")
        finally:
            self.manager.processing_stack.remove(resolved)


class TestValidateWarn(TempTreeTestCase):
    """validate=1 ('warn') must warn and skip, not hard-crash.

    Regression: when ``resolve_path`` returns ``None`` (an invalid path under
    the documented validate=1 'warn' level), collection fell through to
    ``os.path.isdir(None)`` and raised ``TypeError`` — turning 'warn' into a
    hard crash.
    """

    def test_collect_skips_none_path(self):
        from unittest.mock import patch

        with patch.object(self.manager, "resolve_path", return_value=None):
            with self.assertLogs(self.manager.logger, level="WARNING"):
                result = self.manager._collect_file_info(
                    "whatever", fields=["filename", "filepath"]
                )
        self.assertEqual(result, [])

    def test_create_with_invalid_path_validate_warn_does_not_crash(self):
        registry = self.manager.create(
            "warn_registry",
            "definitely_not_a_real_dir_123",
            validate=1,
            inc_files="*.ui",
        )
        self.assertIsNotNone(registry)
        self.assertEqual(len(registry), 0)


class TestLocationCheck(TempTreeTestCase):
    """contains_location semantics."""

    def setUp(self):
        super().setUp()
        self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")

    def test_contains_existing_location(self):
        self.assertTrue(
            self.manager.contains_location(str(self.tmp / "a.ui"), "ui_registry")
        )

    def test_does_not_contain_nonexistent_location(self):
        self.assertFalse(
            self.manager.contains_location(str(self.tmp / "zzz.ui"), "ui_registry")
        )

    @unittest.skipUnless(os.name == "nt", "case-insensitive filesystem semantics")
    def test_contains_location_is_case_insensitive(self):
        swapped = str(self.tmp / "a.ui").swapcase()
        self.assertTrue(self.manager.contains_location(swapped, "ui_registry"))

    def test_contains_location_extensionless(self):
        """A query without extension matches a registered stem in the same dir."""
        self.assertTrue(
            self.manager.contains_location(str(self.tmp / "a"), "ui_registry")
        )

    def test_missing_container_returns_false(self):
        self.assertFalse(self.manager.contains_location("x", "nope_registry"))


class TestDescriptorGuardsAndBookkeeping(TempTreeTestCase):
    """create/get/list/remove container management."""

    def test_invalid_descriptors_raise(self):
        for bad in ("", None, "not an identifier", "_private", "create", "containers"):
            with self.assertRaises(ValueError, msg=f"descriptor {bad!r}"):
                self.manager.create(bad, str(self.tmp), inc_files="*.ui")

    def test_recreate_replaces_container_without_leak(self):
        first = self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")
        second = self.manager.create(
            "ui_registry", str(self.tmp / "sub"), inc_files="*.ui"
        )
        self.assertIs(self.manager.ui_registry, second)
        self.assertNotIn(first, self.manager.containers)
        self.assertEqual(len(self.manager.containers), 1)

    def test_get_container(self):
        registry = self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")
        self.assertIs(self.manager.get_container("ui_registry"), registry)
        self.assertIsNone(self.manager.get_container("missing"))
        # Non-registry attributes are not exposed as containers.
        self.assertIsNone(self.manager.get_container("containers"))

    def test_remove_container(self):
        self.manager.create("ui_registry", str(self.tmp), inc_files="*.ui")
        self.assertTrue(self.manager.remove_container("ui_registry"))
        self.assertFalse(hasattr(self.manager, "ui_registry"))
        self.assertEqual(self.manager.containers, [])
        self.assertFalse(self.manager.remove_container("ui_registry"))


class TestPackageSurface(BaseTestCase):
    """Real-tree smoke tests + deprecated alias wiring."""

    def test_scan_examples_dir(self):
        manager = RegistryManager()
        registry = manager.create("ui_registry", str(EXAMPLES_DIR), inc_files="*.ui")
        self.assertGreater(len(registry), 0)
        self.assertTrue(
            manager.contains_location(str(EXAMPLES_DIR / "example.ui"), "ui_registry")
        )

    def test_scan_widgets_class_fields(self):
        manager = RegistryManager()
        registry = manager.create(
            "widget_registry",
            str(WIDGETS_DIR),
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
        )
        self.assertIn("PushButton", registry.get("classname"))

    def test_deprecated_file_manager_shim(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            sys.modules.pop("uitk.file_manager", None)
            shim = importlib.import_module("uitk.file_manager")
        self.assertTrue(
            any(issubclass(w.category, DeprecationWarning) for w in caught),
            "importing uitk.file_manager must emit a DeprecationWarning",
        )
        self.assertIs(shim.FileManager, RegistryManager)
        self.assertIs(shim.FileContainer, FileRegistry)

    def test_lazy_root_exports(self):
        import uitk

        self.assertIs(uitk.RegistryManager, RegistryManager)
        self.assertIs(uitk.FileRegistry, FileRegistry)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self.assertIs(uitk.FileManager, RegistryManager)
            self.assertIs(uitk.FileContainer, FileRegistry)


class TestNamedTupleContainerContract(BaseTestCase):
    """Pin the upstream NamedTupleContainer behaviors the registries rely on."""

    def setUp(self):
        super().setUp()
        File = namedtuple("File", ["filename", "filepath"])
        self.File = File
        self.container = NamedTupleContainer(
            named_tuples=[
                File("file1.txt", "/path1"),
                File("file2.txt", "/path2"),
                File("file3.txt", "/path3"),
            ],
            fields=["filename", "filepath"],
        )

    def test_get_returns_matching_field(self):
        result = self.container.get(return_field="filename", filepath="/path1")
        self.assertEqual(result, "file1.txt")

    def test_get_returns_none_for_no_match(self):
        result = self.container.get(return_field="filename", filepath="/nonexistent")
        self.assertIsNone(result)

    def test_get_returns_all_when_no_filter(self):
        self.assertEqual(len(self.container.get(return_field="filename")), 3)

    def test_get_all_matches_without_return_field(self):
        result = self.container.get(filepath="/path2")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].filename, "file2.txt")

    def test_dynamic_field_attribute(self):
        self.assertEqual(
            self.container.filename, ["file1.txt", "file2.txt", "file3.txt"]
        )

    def test_modify_updates_container(self):
        modified = self.container.modify(0, filename="updated.txt")
        self.assertEqual(modified.filepath, "/path1")
        self.assertEqual(self.container.named_tuples[0].filename, "updated.txt")

    def test_iteration_and_length(self):
        self.assertEqual(len(list(self.container)), 3)
        self.assertEqual(len(self.container), 3)

    def test_empty_container(self):
        empty = NamedTupleContainer(named_tuples=[], fields=["name"])
        self.assertEqual(len(empty), 0)
        self.assertEqual(empty.get(return_field="name"), [])

    def test_handle_duplicates_default(self):
        existing = [self.File("file1.txt", "/p1")]
        new = [self.File("file1.txt", "/p1"), self.File("file2.txt", "/p2")]
        self.assertEqual(
            len(self.container._handle_duplicates(existing, new, True)), 3
        )
        self.assertEqual(
            len(self.container._handle_duplicates(existing, new, False)), 2
        )


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
