# !/usr/bin/python
# coding=utf-8
"""Typed file registries backing Switchboard discovery.

A ``RegistryManager`` owns any number of named ``FileRegistry`` containers
(the Switchboard's ``ui_registry``, ``slot_registry``, ``widget_registry``
and ``icon_registry``).  Each registry holds one named tuple per discovered
file (or class) with queryable fields, and knows how to grow itself from raw
paths, modules, or classes while honouring its stored filters.

Classes:
    FileRegistry: A :class:`pythontk.NamedTupleContainer` of file records
        that routes raw (non-tuple) objects through its owning manager's
        collection logic on ``extend``.
    RegistryManager: Creates and owns named ``FileRegistry`` containers and
        resolves caller-relative paths.

Example:
    Creating and querying a registry::

        manager = RegistryManager()
        manager.create("ui_registry", "./ui", inc_files="*.ui")

        path = manager.ui_registry.get(
            filename="main_window", return_field="filepath"
        )

Note:
    This module supersedes ``uitk.file_manager`` (``FileManager`` /
    ``FileContainer``).  The old import path and class names remain
    available as deprecated aliases via that module.
"""
import os
import sys
import inspect
from collections import namedtuple
from typing import Any, List, Optional, Tuple, Union

import pythontk as ptk


class FileRegistry(ptk.NamedTupleContainer):
    """A named tuple container of file records.

    Extends the base container with file-specific growth: anything passed to
    :meth:`extend` that is not already tuple data (raw paths, directories,
    modules, classes) is routed through the owning :class:`RegistryManager`'s
    collection logic, using the registry's stored filters and honouring its
    ``allow_duplicates`` metadata.
    """

    def __init__(self, manager: "RegistryManager", **kwargs):
        """Initialize the registry with a reference to its owning manager.

        Args:
            manager: The RegistryManager instance that owns this registry.
            **kwargs: Additional arguments passed to NamedTupleContainer.
        """
        super().__init__(**kwargs)
        self.manager = manager

    @property
    def file_manager(self) -> "RegistryManager":
        """Deprecated alias for :attr:`manager`."""
        return self.manager

    @staticmethod
    def _is_tuple_data(objects: Any) -> bool:
        """Return True if *objects* is already row data.

        Row data is a single named tuple or a list of (named) tuples.  A
        *plain* tuple is a sequence of raw objects (e.g. ``(dir_a, dir_b)``
        as a Switchboard source), not a row.
        """
        if hasattr(objects, "_fields"):  # single named tuple row
            return True
        return bool(
            isinstance(objects, list)
            and objects
            and (isinstance(objects[0], tuple) or hasattr(objects[0], "_fields"))
        )

    @staticmethod
    def _record_signature(nt: namedtuple) -> tuple:
        """Duplicate-detection identity for a file record.

        Path-like fields are case/sep-normalized (Windows-safe) and the live
        ``classobj`` is excluded — a class's identity here is its name plus
        where it lives, not whether the scanner could import it at the time.
        """
        sig = []
        for field in nt._fields:
            value = getattr(nt, field)
            if field == "classobj" and len(nt._fields) > 1:
                continue
            if field in ("filepath", "dirpath") and isinstance(value, str):
                value = os.path.normcase(os.path.normpath(value))
            elif hasattr(value, "__name__") and hasattr(value, "__module__"):
                value = (value.__name__, value.__module__)
            sig.append((field, value))
        return tuple(sig)

    def extend(
        self, objects: Union[List[namedtuple], List[tuple], Any], **metadata
    ) -> None:
        """Extend the registry, collecting file records from raw objects.

        Args:
            objects: Tuples/named tuples are added directly; anything else
                (path strings, directories, modules, classes) is processed
                into file records first.
            **metadata: Per-call overrides merged over the registry's stored
                metadata (e.g. ``recursive``, ``base_dir``, ``inc_files``,
                ``allow_duplicates``, ``signature_func``).
        """
        if "signature_func" not in self.metadata:
            metadata.setdefault("signature_func", self._record_signature)
        if self._is_tuple_data(objects):
            super().extend(objects, **metadata)
            return

        processing_metadata = {**self.metadata, **metadata}
        processing_metadata.setdefault("fields", self.fields)

        rows: List[Tuple] = []
        for obj in ptk.make_iterable(objects):
            rows.extend(self.manager._collect_file_info(obj, **processing_metadata))

        if not rows:
            return
        if not self._tuple_class:
            raise ValueError(
                f"{type(self).__name__} has no fields; cannot convert file records"
            )
        super().extend([self._tuple_class(*row) for row in rows], **metadata)


class RegistryManager(ptk.HelpMixin, ptk.LoggingMixin):
    """Creates and owns named file registries.

    Organizes files and directories into :class:`FileRegistry` containers
    (named tuples with query capabilities), resolving relative paths against
    an explicit directory, a Python object's location, or the caller's frame.

    Attributes:
        containers (List[FileRegistry]): All containers created by this manager.
        processing_stack (List[str]): Directories currently being processed
            (guards against recursive re-entry).
    """

    def __init__(self, log_level: str = "WARNING") -> None:
        """Initialize the manager.

        Args:
            log_level: Logging level for the manager.
        """
        self.set_log_level(log_level)
        self.containers: List[FileRegistry] = []
        self.processing_stack: List[str] = []

    def get_base_dir(self, caller_info: Union[str, int, Any] = 0) -> Optional[str]:
        """Identify a base directory from a path, a caller frame index, or an object.

        Args:
            caller_info: One of:
                - str: an existing directory (returned as-is) or a file path
                  (its parent directory is returned).
                - int: an index into the chain of distinct source files that
                  called into this module — ``0`` is the file that invoked
                  uitk directly, ``1`` is that file's caller, and so on.
                - object: a module/class/callable whose location is used.
                - None: no base (returns None).

        Returns:
            Absolute directory path, or None if it cannot be determined.
        """
        if caller_info is None:
            return None

        if isinstance(caller_info, int):
            # Walk the raw frame chain (cheap — no source-context loading
            # like inspect.stack) collecting each distinct source file,
            # innermost first.  files[0] is always this module.
            files: List[str] = []
            seen = set()
            frame = sys._getframe()
            while frame is not None:
                filename = frame.f_code.co_filename
                if filename not in seen:
                    seen.add(filename)
                    files.append(filename)
                frame = frame.f_back
            try:
                return os.path.abspath(os.path.dirname(files[1:][caller_info]))
            except IndexError:
                return None

        if isinstance(caller_info, str) and os.path.isdir(caller_info):
            return caller_info

        # Module, class, callable — or a string file path (its directory).
        return ptk.get_object_path(caller_info)

    def resolve_path(
        self,
        target_obj: Union[str, Any],
        validate: int = 0,
        path_type: str = "Path",
        **metadata,
    ) -> Optional[str]:
        """Resolve a target object to an absolute path.

        Args:
            target_obj: Object to resolve (path string or Python object).
            validate: Validation level (0=none, 1=warn and return None,
                2=raise) applied when the path is missing or invalid.
            path_type: Type description for messages (e.g. "UI", "Slot").
            **metadata: May include ``base_dir`` (str path, caller frame
                index, or object) used to anchor relative string paths.

        Returns:
            Resolved absolute path, or None if it cannot be resolved
            (with ``validate=1``) or the object has no file location.

        Raises:
            FileNotFoundError: If ``validate=2`` and the path is invalid.
        """
        if isinstance(target_obj, str):
            base_dir = self.get_base_dir(metadata.get("base_dir", 0))
            if os.path.isabs(target_obj):
                path = target_obj
            else:
                path = os.path.join(base_dir or os.getcwd(), target_obj)
            path = os.path.normpath(os.path.abspath(path))
        else:
            try:
                path = os.path.normpath(ptk.get_object_path(target_obj))
            except ValueError:
                # Object with no importable file location — handled below
                # via the validate contract instead of always raising.
                path = None

        if validate > 0 and not (path and ptk.FileUtils.is_valid(path)):
            msg = (
                f"[{type(self).__name__}] Invalid {path_type}: "
                f"{path if path is not None else target_obj!r}"
            )
            if validate == 2:
                raise FileNotFoundError(msg)
            self.logger.warning(msg)
            return None

        return path

    def create(
        self,
        descriptor: str,
        objects: Optional[Union[str, List[str], Any]] = None,
        **metadata,
    ) -> FileRegistry:
        """Create a named registry and bind it as an attribute on this manager.

        Args:
            descriptor: Attribute name for the registry (a valid Python
                identifier that does not shadow a manager attribute), e.g.
                ``"ui_registry"``.
            objects: Initial objects (paths, directories, modules, classes)
                to collect records from, processed exactly like
                :meth:`FileRegistry.extend`; None creates an empty registry.
            **metadata: Stored on the registry and used for collection:
                - fields: Field name(s) for the named tuples.
                  Defaults to ["filename", "filepath"].
                - inc_files / exc_files: Filename include/exclude patterns.
                - inc_dirs / exc_dirs: Directory include/exclude patterns.
                - recursive: Recurse into subdirectories. Defaults to False.
                - base_dir: Anchor for relative paths — a directory path, a
                  caller frame index, or a Python object.
                - allow_duplicates: Keep duplicate entries on extend.

        Returns:
            The created FileRegistry (also available as
            ``manager.<descriptor>``).

        Raises:
            ValueError: If descriptor is not a valid, non-shadowing identifier.
        """
        if (
            not descriptor
            or not isinstance(descriptor, str)
            or not descriptor.isidentifier()
        ):
            raise ValueError(
                f"Descriptor must be a non-empty identifier string, got {descriptor!r}"
            )
        existing = getattr(self, descriptor, None)
        if (
            descriptor.startswith("_")
            or hasattr(type(self), descriptor)
            or (existing is not None and not isinstance(existing, ptk.NamedTupleContainer))
        ):
            raise ValueError(
                f"Descriptor {descriptor!r} would shadow a "
                f"{type(self).__name__} attribute"
            )

        # Normalize once so every downstream consumer sees a field list.
        fields = ptk.make_iterable(metadata.get("fields", ["filename", "filepath"]))
        metadata = {**metadata, "fields": fields}

        container = FileRegistry(
            manager=self,
            fields=fields,
            metadata=metadata,
            tuple_class_name=descriptor.capitalize(),
        )
        if objects is not None:
            container.extend(objects)

        # Re-creating a descriptor replaces its container; drop the old one
        # from the tracking list so it can't leak.
        if isinstance(existing, ptk.NamedTupleContainer) and existing in self.containers:
            self.containers.remove(existing)

        self.containers.append(container)
        setattr(self, descriptor, container)
        return container

    def _collect_file_info(self, obj: Any, **metadata) -> List[Tuple]:
        """Collect file-record rows for a single path/module/class object.

        Args:
            obj: The object representing a file or directory.
            **metadata: Collection options (see :meth:`create`).

        Returns:
            List of value tuples ordered per ``metadata["fields"]``.

        Raises:
            RecursionError: If circular directory processing is detected.
        """
        fields = ptk.make_iterable(metadata.get("fields", ["filename", "filepath"]))
        dir_path = self.resolve_path(obj, **metadata)

        if dir_path is None:
            # resolve_path returns None for an invalid path under validate=1
            # ('warn'), or for an object with no resolvable path.  Skip rather
            # than fall through to os.path.isdir(None), which raises TypeError
            # — turning the documented 'warn' level into a hard crash.
            self.logger.warning(
                f"[{type(self).__name__}] Skipping unresolved "
                f"{metadata.get('path_type', 'Path')}: {obj!r}"
            )
            return []

        if dir_path in self.processing_stack:
            raise RecursionError(
                f"Recursion detected while processing '{dir_path}'. "
                f"Current stack: {self.processing_stack}"
            )
        self.processing_stack.append(dir_path)

        try:
            needs_classes = any(
                f in ("classname", "classobj", "module") for f in fields
            )
            recursive = bool(metadata.get("recursive", False))

            if needs_classes:
                class_name = obj.__name__ if inspect.isclass(obj) else None
                if os.path.isdir(dir_path):
                    py_files = ptk.get_dir_contents(
                        dir_path,
                        "filepath",
                        inc_files=metadata.get("inc_files") or "*.py",
                        exc_files=metadata.get("exc_files"),
                        inc_dirs=metadata.get("inc_dirs"),
                        exc_dirs=metadata.get("exc_dirs"),
                        recursive=recursive,
                    )
                else:
                    py_files = [dir_path]

                file_info: List[Tuple] = []
                for f_path in py_files:
                    file_info.extend(
                        ptk.get_classes_from_path(
                            f_path,
                            fields,
                            inc=class_name,
                            top_level_only=False,
                            force_tuples=True,
                        )
                    )

                # When registering a class object directly, patch in the live
                # object where the scanner could not import one.
                if class_name and "classname" in fields and "classobj" in fields:
                    name_i = fields.index("classname")
                    obj_i = fields.index("classobj")
                    for i, row in enumerate(file_info):
                        if row[name_i] == class_name and row[obj_i] is None:
                            patched = list(row)
                            patched[obj_i] = obj
                            file_info[i] = tuple(patched)

            elif os.path.isdir(dir_path):
                files = ptk.get_dir_contents(
                    dir_path,
                    "filepath",
                    inc_files=metadata.get("inc_files"),
                    exc_files=metadata.get("exc_files"),
                    inc_dirs=metadata.get("inc_dirs"),
                    exc_dirs=metadata.get("exc_dirs"),
                    recursive=recursive,
                )
                file_info = ptk.get_file_info(files, fields, force_tuples=True)

            else:
                lst = ptk.get_file_info(dir_path, fields, force_tuples=True)
                file_info = ptk.filter_list(
                    lst,
                    metadata.get("inc_files"),
                    metadata.get("exc_files"),
                    nested_as_unit=True,
                )

            return file_info

        finally:
            if dir_path in self.processing_stack:
                self.processing_stack.remove(dir_path)

    def contains_location(
        self, location: Union[str, Any], container_descriptor: str
    ) -> bool:
        """Check whether a registry already holds a given file location.

        Comparison is case-normalized (Windows-safe).  A query path without
        an extension matches an entry whose directory and stem agree (e.g.
        ``"<dir>/main_window"`` matches ``"<dir>/main_window.ui"``).

        Args:
            location: The location to query (path string or object).
            container_descriptor: Name of the registry to search.

        Returns:
            True if the location is found in the registry.

        Example:
            manager.contains_location("path/to/file.ui", "ui_registry")
        """
        container = self.get_container(container_descriptor)
        if not container:
            return False

        try:
            resolved = self.resolve_path(location)
        except Exception as e:
            self.logger.warning(f"Error checking location {location}: {e}")
            return False
        if not resolved:
            return False

        resolved = os.path.normcase(os.path.normpath(resolved))
        resolved_dir, resolved_name = os.path.split(resolved)

        for nt in container.named_tuples:
            filepath = getattr(nt, "filepath", None)
            if not filepath:
                continue
            nt_path = os.path.normcase(os.path.normpath(filepath))
            if nt_path == resolved:
                return True
            stem = getattr(nt, "filename", None)
            if (
                stem
                and os.path.normcase(stem) == resolved_name
                and os.path.dirname(nt_path) == resolved_dir
            ):
                return True
        return False

    def get_container(self, descriptor: str) -> Optional[FileRegistry]:
        """Get a registry by name.

        Args:
            descriptor: The name of the registry to retrieve.

        Returns:
            The registry if found (non-registry attributes are ignored),
            None otherwise.
        """
        value = getattr(self, descriptor, None)
        return value if isinstance(value, ptk.NamedTupleContainer) else None

    def list_containers(self) -> List[str]:
        """List all registry descriptor names.

        Returns:
            List of registry descriptor names.
        """
        return [
            name
            for name, value in self.__dict__.items()
            if isinstance(value, ptk.NamedTupleContainer)
        ]

    def remove_container(self, descriptor: str) -> bool:
        """Remove a registry by name.

        Args:
            descriptor: The name of the registry to remove.

        Returns:
            True if the registry was removed, False if it didn't exist.
        """
        container = self.get_container(descriptor)
        if container is None:
            return False
        if container in self.containers:
            self.containers.remove(container)
        delattr(self, descriptor)
        return True


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    manager = RegistryManager(log_level="INFO")
    registry = manager.create("module_registry", os.path.dirname(__file__), inc_files="*.py")
    print(registry)
    print(registry.get("filename"))
