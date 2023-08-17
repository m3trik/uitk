# !/usr/bin/python
# coding=utf-8
import os
import inspect
import logging
from collections import namedtuple
import pythontk as ptk


class NamedTupleContainer:
    def __init__(
        self,
        file_manager,
        named_tuples,
        location,
        metadata=None,
        log_level=logging.WARNING,
    ):
        """Creates a container for named tuples, providing dynamic attribute access and query capabilities.

        Parameters:
            file_manager (FileManager): Reference to the FileManager object that created this container.
            named_tuples (list): A list of named tuples.
            location: The location information.
            metadata (dict, optional): Metadata related to the container, including field names (as 'fields').
            log_level (int, optional): Logging level. Defaults to logging.WARNING.
        """
        self._init_logger(log_level)

        self.file_manager = file_manager
        self.named_tuples = named_tuples
        self.location = location
        self.metadata = metadata or {}
        self.fields = ptk.make_iterable(self.metadata.get("fields", []))

        self._tuple_class = namedtuple("TupleClass", self.fields)

    def __iter__(self):
        """Allows iteration over the named tuples in the container.

        Returns:
            iterator: An iterator over the named tuples.
        """
        return iter(self.named_tuples)

    def __repr__(self):
        """Returns the string representation of the named tuples.

        Returns:
            str: The string representation of the named tuples.
        """
        return repr(self.named_tuples)

    def __getattr__(self, name):
        """Dynamic attribute access for field names or specific methods.

        Parameters:
            name (str): The attribute name.

        Returns:
            list: A list of values for the specified field name if found in fields.
            method: The method corresponding to the name if found in ["modify", "add", "remove"].

        Raises:
            AttributeError: If the attribute is not found in fields or the specific methods.
        """
        if name in self.fields:
            return [getattr(nt, name) for nt in self.named_tuples]
        elif name in ["modify", "add", "remove"]:
            return getattr(self, name)
        else:
            raise AttributeError(
                f"'NamedTupleContainer' object has no attribute '{name}'"
            )

    def _init_logger(self, log_level):
        """Initializes logger with the specified log level.

        Parameters:
            log_level (int): Logging level.
        """
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        self.logger.addHandler(handler)

    def extend(self, objects, **new_metadata):
        """Extends the container with additional objects.

        This method takes new objects and combines them with the existing named tuples in the container.
        It then recreates the container using the combined objects and merged metadata.

        Parameters:
            objects (str/module/class/list): Objects representing new files or directories to add to the container.
            **new_metadata: Additional metadata for the new container.
        """
        try:
            # Retrieve the metadata from the container
            metadata = {**self.metadata, **new_metadata}

            # Back up the existing named tuples
            existing_named_tuples = self.named_tuples.copy()

            # Retrieve the descriptor (name) of the container
            descriptor = [
                name
                for name, value in self.file_manager.__dict__.items()
                if value == self
            ][0]

            # Re-create the container with the new objects using the merged metadata
            new_container = self.file_manager.create(descriptor, objects, **metadata)

            # Extract the named tuples from the new container
            new_named_tuples = new_container.named_tuples

            # Extend the backed-up named tuples with the new ones
            existing_named_tuples.extend(new_named_tuples)

            # Update the named tuples in the new container with the combined list
            new_container.named_tuples = existing_named_tuples

        except FileNotFoundError as e:
            self.logger.error(f"File not found: {e.filename}")
        except Exception as e:
            self.logger.error(
                f"An error occurred while extending the container: {str(e)}"
            )

    def add(self, **kwargs):
        """Add a new named tuple to the container.

        Parameters:
            kwargs: Key-value pairs representing the fields and their values for the new named tuple.

        Returns:
            NamedTuple: The newly added named tuple.

        Example:
            container = NamedTupleContainer(named_tuples=[], fields=["filename", "extension"])
            container.add(filename="document.txt", extension="txt")
            print(container.named_tuples)  # Output: [TupleClass(filename='document.txt', extension='txt')]
        """
        new_tuple = self._tuple_class(**kwargs)
        self.named_tuples.append(new_tuple)
        return new_tuple

    def get(self, return_field=None, **conditions):
        """Query the named tuples based on specified conditions.

        This method allows querying the named tuples in the container based on specific conditions,
        and optionally returning a specific field's value from the matching named tuples.

        Parameters:
            return_field (str, optional): The name of the field to return. If None, returns the entire named tuple.
            **conditions: Key-value pairs representing the query conditions, where keys are field names and values are the values to match.

        Returns:
            A list of matching named tuples or specified field values.
            If conditions and return_field are specified, returns the first matching value or None if not found.

        Examples:
            Assuming named tuples contain information about files, such as filename, extension, and size.

            # Query and return all filenames in the container
            all_filenames = container.get("filename")

            # Query all named tuples with the extension ".txt"
            files_txt = container.get(extension=".txt")

            # Query and return filenames of all named tuples with the extension ".jpg"
            jpg_filenames = container.get(return_field="filename", extension=".jpg")
        """
        results = []
        for named_tuple in self.named_tuples:
            if all(
                getattr(named_tuple, field) == value
                for field, value in conditions.items()
            ):
                result = (
                    getattr(named_tuple, return_field) if return_field else named_tuple
                )
                # If conditions and return_field are specified, return the first match
                if conditions and return_field:
                    return result
                results.append(result)
        return results

    def modify(self, index, **kwargs):
        """Modify a named tuple at a specific index within the container.

        Parameters:
            index (int): The index of the named tuple within the container to modify.
            kwargs: Key-value pairs representing the fields to update and their new values.

        Returns:
            NamedTuple: The updated named tuple.

        Example:
            container.modify(0, filename="new_document.txt")
            print(container.named_tuples)  # Output: [TupleClass(filename='new_document.txt', extension='txt')]
        """
        named_tuple = self.named_tuples[index]
        new_tuple = named_tuple._replace(**kwargs)
        self.named_tuples[index] = new_tuple
        return new_tuple

    def remove(self, index):
        """Remove a named tuple at a specific index within the container.

        Parameters:
            index (int): The index of the named tuple within the container to remove.

        Example:
            container.remove(0)
            print(container.named_tuples)  # Output: []
        """
        self.named_tuples.pop(index)


class FileManager:
    def __init__(self, caller_dir=None):
        """Manages files and directories, supporting file queries and path manipulations.

        The FileManager class provides methods to retrieve file information, including file paths,
        class names, class objects, etc. It allows the creation of custom named tuple containers
        for structured access to file data.

        Parameters:
            caller_dir (str, optional): The directory of the caller. If not provided, retrieved from the stack.
        """
        self.containers = []
        self.processing_stack = []

        self.stack = inspect.stack()
        self.caller_dir = caller_dir or self._get_dir_from_stack(2)
        self.module_dir = self._get_dir_from_stack(0)

    def _get_dir_from_stack(self, index) -> str:
        """Retrieves the directory path from the stack frame at the given index.

        Parameters:
            index (int): Index in the stack frame.

        Returns:
            str: Absolute path of the directory.
        """
        # If desired index is out of range, use the highest available one
        if index >= len(self.stack):
            index = len(self.stack) - 1

        frame = self.stack[index][0]
        filename = frame.f_code.co_filename
        return os.path.abspath(os.path.dirname(filename))

    def create(self, descriptor, objects=None, **metadata):
        """Creates a named tuple container for the specified files.

        Parameters:
            descriptor (str): Descriptor for the named tuples.
            objects (str/module/class/list, optional): Objects representing files or directories.
            **metadata: Additional keyword arguments used to construct the container.
             - structure (str/list, optional): Structure of the named tuple. Defaults to ["filename", "filepath"]
             - fields (str/list, optional): A list of field names or a single string representing a field name for the named tuples.
             - inc_files (list, optional): List of included files.
             - exc_files (list, optional): List of excluded files.
             - inc_dirs (list, optional): List of included directories.
             - exc_dirs (list, optional): List of excluded directories.
             - base_dir (str, optional): Base directory for relative paths.

        Returns:
            NamedTupleContainer: Container holding the named tuples for the file information.
        """
        structure = ptk.make_iterable(
            metadata.get("structure", ["filename", "filepath"])
        )
        metadata["fields"] = structure  # Include the structure as fields in metadata
        named_tuples = []

        if objects is not None:
            all_files = []
            for obj in ptk.make_iterable(objects):
                file_info = self._handle_single_obj(obj, **metadata)
                all_files.extend(file_info)

            TupleClass = namedtuple(descriptor.capitalize(), structure)
            named_tuples = [TupleClass(*info) for info in all_files]

        container = NamedTupleContainer(
            self,
            named_tuples,
            self.caller_dir,
            metadata=metadata,
        )

        self.containers.append(container)
        setattr(self, descriptor, container)
        return container

    def _handle_single_obj(self, obj, **metadata):
        """Handles a single object and returns its corresponding file information.

        This internal method is used by the create method to handle individual objects
        and gather file information based on the provided structure and filters.

        Parameters:
            obj (str/module/class): The object representing a file or directory.
            **metadata: Additional keyword arguments used to construct the container.
                        See the `create` method documentation.
        Returns:
            list: List of tuples containing the file information based on the structure.
        """
        # Retrieve the structure from metadata or use the default value
        structure = metadata.get("structure", ["filename", "filepath"])

        def resolve_path(target_obj):
            if isinstance(target_obj, int):
                return self._get_dir_from_stack(target_obj)
            elif isinstance(target_obj, str):
                return os.path.abspath(
                    os.path.join(base_dir, target_obj)
                    if not os.path.isabs(target_obj)
                    else target_obj
                )
            elif hasattr(target_obj, "__path__"):
                return ptk.get_object_path(target_obj, inc_filename=False)
            return ptk.get_object_path(target_obj, inc_filename=True)

        base_dir = resolve_path(metadata.get("base_dir", self.caller_dir))
        dir_path = resolve_path(obj)

        if dir_path in self.processing_stack:
            raise RecursionError(
                f"Recursion detected while processing '{dir_path}'. Current stack: {self.processing_stack}"
            )
        self.processing_stack.append(dir_path)

        class_name = obj.__name__ if inspect.isclass(obj) else None

        # Determine the way to gather file information based on the structure
        needs_classes = any(
            item in structure for item in ["classname", "classobj", "module"]
        )

        if os.path.isdir(dir_path) and not needs_classes:
            files = ptk.get_dir_contents(
                dir_path,
                returned_type="filepath",
                inc_files=metadata.get("inc_files"),
                exc_files=metadata.get("exc_files"),
                inc_dirs=metadata.get("inc_dirs"),
                exc_dirs=metadata.get("exc_dirs"),
            )
            file_info = ptk.get_file_info(files, structure, force_tuples=True)
        elif needs_classes:
            file_info = ptk.get_classes_from_path(
                dir_path,
                structure,
                inc=class_name,
                top_level_only=False,
                force_tuples=True,
            )
            if class_name and "classobj" in structure:
                for i, info in enumerate(file_info):
                    if info[0] == class_name and info[1] is None:
                        file_info[i] = (class_name, obj) + info[2:]
        else:
            lst = ptk.get_file_info(dir_path, structure, force_tuples=True)
            file_info = ptk.filter_list(
                lst,
                metadata.get("inc_files"),
                metadata.get("exc_files"),
                nested_as_unit=True,
            )

        # Remove the directory from the processing stack after handling
        self.processing_stack.remove(dir_path)

        return file_info


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    ...

logging.info(__name__)  # module name
# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
