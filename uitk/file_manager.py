# !/usr/bin/python
# coding=utf-8
import os
import inspect
from collections import namedtuple
import pythontk as ptk


class NamedTupleContainer(ptk.HelpMixin, ptk.LoggingMixin):
    """The NamedTupleContainer class is responsible for managing collections of named tuples.
    The class provides methods to query, modify, extend, and remove elements within the container.
    It is typically initialized and used by the FileManager class, which serves as the main container manager.
    NamedTupleContainer allows for advanced manipulation of the named tuples, such as accessing specific fields across all tuples.

    Attributes:
        - `file_manager`: A reference to the FileManager object that owns this container.
        - `named_tuples`: The list of named tuples stored in this container.
        - `metadata`: A dictionary containing additional information like "fields" which are the named tuple fields, and an "allow_duplicates" flag.
        - `fields`: List of named tuple fields derived from metadata.
        - `_tuple_class`: The dynamically generated named tuple class based on `fields`.

    Methods:
        - `extend`: Add new named tuples to the container while handling duplicates.
        - `get`: Query the named tuples based on certain conditions and optionally retrieve a specific field's value.
        - `modify`: Modify a named tuple at a specific index.
        - `remove`: Remove a named tuple at a specific index.

    Examples:
        - Create a new container with the FileManager class:
        ```python
        file_manager = FileManager()
        container = file_manager.create("example_descriptor", objects, fields=["name", "age"])
        ```

        - Extend the container with new objects:
        ```python
        container.extend(new_objects, allow_duplicates=False)
        ```

        - Query the container:
        ```python
        adults = container.get(age=18)
        ```

        - Modify an item:
        ```python
        container.modify(0, name="NewName")
        ```

        - Remove an item:
        ```python
        container.remove(0)
        ```

    Notes:
        - This class utilizes internal logging. The logging level can be set during instantiation.
        - The class defines custom `__iter__` and `__repr__` methods to iterate over the named tuples and represent the object.
        - Uses the `namedtuple` class from Python's standard library to dynamically create tuple classes.
    """

    def __init__(
        self,
        file_manager,
        named_tuples,
        metadata=None,
        log_level: str = "WARNING",
    ):
        """Creates a container for named tuples, providing dynamic attribute access and query capabilities.

        Parameters:
            file_manager (FileManager): Reference to the FileManager object that created this container.
            named_tuples (list): A list of named tuples.
            metadata (dict, optional): Metadata related to the container, including field names (as 'fields').
            log_level (int, optional): Logging level. Defaults to logging.WARNING.
        """
        self.logger.setLevel(log_level)

        self.file_manager = file_manager
        self.named_tuples = named_tuples
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
            method: The method corresponding to the name if found in ["modify", "extend", "remove"].

        Raises:
            AttributeError: If the attribute is not found in fields or the specific methods.
        """
        if name in self.fields:
            return [getattr(nt, name) for nt in self.named_tuples]
        elif name in ["modify", "extend", "remove"]:
            return getattr(self, name)
        else:
            raise AttributeError(
                f"'NamedTupleContainer' object has no attribute '{name}'"
            )

    @staticmethod
    def _handle_duplicates(existing, new, allow_duplicates):
        """Handles duplicates based on the allow_duplicates flag.

        Parameters:
            existing (list): List of existing named tuples.
            new (list): List of new named tuples to add.
            allow_duplicates (bool): Flag to allow or disallow duplicates.

        Returns:
            list: Combined list of named tuples with or without duplicates based on the flag.
        """
        if allow_duplicates:
            return existing + new
        else:
            return existing + [nt for nt in new if nt not in existing]

    def extend(self, objects, **new_metadata):
        try:
            # Retrieve the metadata from the container
            metadata = {**self.metadata, **new_metadata}

            # Retrieve the allow_duplicates flag from metadata, defaulting to False
            allow_duplicates = metadata.get("allow_duplicates", False)

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

            # Extend the backed-up named tuples with the new ones, handling duplicates
            combined_named_tuples = self._handle_duplicates(
                existing_named_tuples, new_named_tuples, allow_duplicates
            )

            # Update the named tuples in the new container with the combined list
            new_container.named_tuples = combined_named_tuples

        except FileNotFoundError as e:
            self.logger.error(f"File not found: {e.filename}")
        except Exception as e:
            self.logger.error(
                f"An error occurred while extending the container: {str(e)}"
            )

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


class FileManager(ptk.HelpMixin, ptk.LoggingMixin):
    def __init__(self, log_level="WARNING"):
        """Manages files and directories, supporting file queries and path manipulations."""
        self.logger.setLevel(log_level)

        self.containers = []
        self.processing_stack = []

    @staticmethod
    def _get_caller_dir():
        """Identifies the correct caller directory by ignoring known library paths."""
        stack = inspect.stack()
        caller_frame = next(
            (frame for frame in stack if "lib\\" not in frame.filename), None
        )
        if caller_frame:
            caller_filename = caller_frame.filename
            caller_dir = os.path.abspath(os.path.dirname(caller_filename))
            return caller_dir
        return None

    def _get_base_dir(self, caller_info=0):
        """Identifies the base directory based on the caller's frame index or an object.

        Parameters:
            caller_info (str/int/object): Either a full path, an index to identify the caller's
                    frame, or a Python object (e.g., module, class) to derive the path from.
        Returns:
            str: Absolute path of the caller's directory or the object's directory.
        """
        # Handle the case where an integer frame index is provided
        if isinstance(caller_info, int):
            # Create a dictionary to filter out duplicates by filename
            unique_frames = {frame.filename: frame for frame in inspect.stack()}

            # Convert the unique frames back to a list and exclude the first frame
            filtered_stack = list(unique_frames.values())[1:]

            # Check if the frame index is within the filtered stack
            frame_index = caller_info
            if frame_index < len(filtered_stack):
                frame = filtered_stack[frame_index]
                return os.path.abspath(os.path.dirname(frame.filename))

        else:  # Handle the case where an object is provided
            # Use get_object_path to derive the path from the object
            return ptk.get_object_path(caller_info)

        return None

    def _resolve_path(self, target_obj, **metadata):
        """Resolves a path based on different types of target objects.

        Parameters:
            target_obj (int/str/module/class): The target object to resolve.
            **metadata: Additional keyword arguments used to construct the container.

        Returns:
            str: Absolute path of the target.
        """
        base_dir_option = metadata.get("base_dir", 0)
        base_dir = self._get_base_dir(base_dir_option)

        if isinstance(target_obj, str):
            return os.path.abspath(
                target_obj
                if os.path.isabs(target_obj)
                else os.path.join(base_dir, target_obj)
            )
        return ptk.get_object_path(target_obj)

    def create(self, descriptor, objects=None, **metadata):
        """Creates a named tuple container for the specified files.

        Parameters:
            descriptor (str): Descriptor for the named tuples.
            objects (str/module/class/list, optional): Objects representing files or directories.
            **metadata: Additional keyword arguments used to construct the container.
             - fields (str/list, optional): A list of field names or a single string representing a field name for the named tuples. Defaults to ["filename", "filepath"]
             - inc_files (list, optional): List of included files.
             - exc_files (list, optional): List of excluded files.
             - inc_dirs (list, optional): List of included directories.
             - exc_dirs (list, optional): List of excluded directories.
             - base_dir (str/int/object, optional): Either a full path, an index to identify the caller's
                        frame, or a Python object (e.g., module, class) to derive the path from.
        Returns:
            NamedTupleContainer: Container holding the named tuples for the file information.
        """
        fields = ptk.make_iterable(metadata.get("fields", ["filename", "filepath"]))
        named_tuples = []

        allow_duplicates = metadata.get("allow_duplicates", False)

        if objects is not None:
            all_files = []
            for obj in ptk.make_iterable(objects):
                file_info = self._handle_single_obj(obj, **metadata)
                all_files.extend(file_info)

            TupleClass = namedtuple(descriptor.capitalize(), fields)
            named_tuples = [TupleClass(*info) for info in all_files]

            # Assume you have existing named tuples if needed
            existing_named_tuples = []
            combined_named_tuples = NamedTupleContainer._handle_duplicates(
                existing_named_tuples, named_tuples, allow_duplicates
            )

            named_tuples = combined_named_tuples

        container = NamedTupleContainer(self, named_tuples, metadata=metadata)

        self.containers.append(container)
        setattr(self, descriptor, container)
        return container

    def _handle_single_obj(self, obj, **metadata):
        """Handles a single object and returns its corresponding file information.

        This internal method is used by the create method to handle individual objects
        and gather file information based on the provided fields and filters.

        Parameters:
            obj (str/module/class): The object representing a file or directory.
            **metadata: Additional keyword arguments used to construct the container.
                        See the `create` method documentation.
        Returns:
            list: List of tuples containing the file information based on the fields.
        """
        fields = metadata.get("fields", ["filename", "filepath"])
        dir_path = self._resolve_path(obj, **metadata)

        if dir_path in self.processing_stack:
            raise RecursionError(
                f"Recursion detected while processing '{dir_path}'. Current stack: {self.processing_stack}"
            )
        self.processing_stack.append(dir_path)

        class_name = obj.__name__ if inspect.isclass(obj) else None

        # Determine the way to gather file information based on the fields
        needs_classes = any(
            item in fields for item in ["classname", "classobj", "module"]
        )

        if os.path.isdir(dir_path) and not needs_classes:
            files = ptk.get_dir_contents(
                dir_path,
                "filepath",
                inc_files=metadata.get("inc_files"),
                exc_files=metadata.get("exc_files"),
                inc_dirs=metadata.get("inc_dirs"),
                exc_dirs=metadata.get("exc_dirs"),
            )
            file_info = ptk.get_file_info(files, fields, force_tuples=True)
        elif needs_classes:
            file_info = ptk.get_classes_from_path(
                dir_path,
                fields,
                inc=class_name,
                top_level_only=False,
                force_tuples=True,
            )
            if class_name and "classobj" in fields:
                for i, info in enumerate(file_info):
                    if info[0] == class_name and info[1] is None:
                        file_info[i] = (class_name, obj) + info[2:]
        else:
            lst = ptk.get_file_info(dir_path, fields, force_tuples=True)
            file_info = ptk.filter_list(
                lst,
                metadata.get("inc_files"),
                metadata.get("exc_files"),
                nested_as_unit=True,
            )

        # Remove the directory from the processing stack after handling
        self.processing_stack.remove(dir_path)

        return file_info

    def contains_location(self, location, container_descriptor):
        """Checks if the container with the given descriptor contains a specific location.

        Parameters:
            location (str/module/class): The location to query.
            container_descriptor (str): Descriptor for the named tuples.

        Returns:
            bool: True if the location is found in the container, False otherwise.

        Example:
            <file manager>.contains_location(<int/str/module/class>, "container name")
        """
        container = getattr(self, container_descriptor, None)
        if container:
            resolved_path = self._resolve_path(location)
            return any(resolved_path in nt for nt in container.named_tuples)
        return False


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    ...

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------
