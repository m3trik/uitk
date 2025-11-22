# !/usr/bin/python
# coding=utf-8
import re
from typing import Union, List, Set
from qtpy import QtWidgets
import pythontk as ptk


class SwitchboardNameMixin:
    """Mixin for Switchboard name and tag management."""

    TAG_DELIMITER = "#"
    UI_NAME_DELIMITER = "."
    SLOT_SUFFIX = "Slots"
    INIT_SUFFIX = "_init"
    STATE_PREFIX = "on_"

    @staticmethod
    def convert_to_legal_name(name: str) -> str:
        """Convert a name to a legal format by replacing non-alphanumeric characters with underscores.

        Parameters:
            name (str): The name to convert.

        Returns:
            str: The converted name with only alphanumeric characters and underscores.
        """
        if not isinstance(name, str):
            raise ValueError(f"Expected a string, got {type(name)}")

        return re.sub(r"[^0-9a-zA-Z]", "_", name)

    def get_slot_class_names(self, base_name: str) -> List[str]:
        """Generate potential slot class names from a base name.

        Parameters:
            base_name (str): The base name to generate slot class names from.

        Returns:
            List[str]: A list of potential slot class names.
        """
        legal_name = self.convert_to_legal_name(base_name)
        capitalized = "".join(part.title() for part in legal_name.split("_"))
        return [f"{capitalized}{self.SLOT_SUFFIX}", capitalized]

    def get_base_name(self, name: str) -> str:
        if not isinstance(name, str):
            raise ValueError(f"Expected a string, got {type(name)}")
        if not name:
            return ""
        name = name.split(self.TAG_DELIMITER)[0]
        name = re.sub(r"[_\d]+$", "", name)
        match = re.search(r"\b[a-zA-Z]\w*", name)
        return match.group() if match else name

    def get_tags_from_name(self, name: str) -> set[str]:
        """Extract tags from a UI name string.

        Parameters:
            name (str): The name to parse (e.g. "menu#submenu").

        Returns:
            set[str]: A set of tags extracted from the name.
        """
        parts = name.split(self.TAG_DELIMITER)
        return set(parts[1:]) if len(parts) > 1 else set()

    def has_tags(self, ui, tags=None) -> bool:
        """Check if any of the given tag(s) are present in the UI's tags set.
        If no tags are provided, it checks if the UI has any tags at all.

        Parameters:
            ui (QWidget): The UI object to check.
            tags (str/list): The tag(s) to check.

        Returns:
            bool: True if any of the given tags are present in the tags set, False otherwise.
        """
        if not isinstance(ui, QtWidgets.QWidget):
            self.logger.debug(f"Invalid UI type: {type(ui)}. Expected QWidget.")
            return False

        if not hasattr(ui, "tags"):
            self.logger.debug(f"UI '{ui.objectName()}' has no 'tags' attribute.")
            return False

        if tags is None:
            return bool(ui.tags)

        tags_to_check = ptk.make_iterable(tags)
        return any(tag in ui.tags for tag in tags_to_check)

    def edit_tags(
        self,
        target: Union[str, QtWidgets.QWidget],
        add: Union[str, List[str]] = None,
        remove: Union[str, List[str]] = None,
        clear: bool = False,
        reset: bool = False,
    ) -> Union[str, None]:
        """Edit tags on a widget or a tag string.

        Parameters:
            target (str or QWidget): The widget to edit tags on, or a tag string.
            add (str or list[str]): Tags to add.
            remove (str or list[str]): Tags to remove.
            clear (bool): If True, clears all tags.
            reset (bool): If True, resets tags to default (only for widgets).

        Returns:
            str or None: The modified tag string if target is a string, otherwise None.
        """
        if isinstance(target, str):
            current_tags = self.get_tags_from_name(target)
            base_name = target.split(self.TAG_DELIMITER)[0]

            if clear:
                current_tags.clear()

            if add:
                current_tags.update(ptk.make_iterable(add))
            if remove:
                current_tags.difference_update(ptk.make_iterable(remove))

            if not current_tags:
                return base_name

            return (
                base_name
                + self.TAG_DELIMITER
                + self.TAG_DELIMITER.join(sorted(current_tags))
            )

        elif isinstance(target, QtWidgets.QWidget):
            if not hasattr(target, "tags"):
                target.tags = set()

            if reset:
                target.tags = self.get_tags_from_name(target.objectName())
            elif clear:
                target.tags.clear()

            if add:
                target.tags.update(ptk.make_iterable(add))
            if remove:
                target.tags.difference_update(ptk.make_iterable(remove))

            return None

    def filter_tags(
        self,
        tag_string: str,
        keep_tags: list[str] = None,
        remove_tags: list[str] = None,
    ) -> str:
        """Filter tags from a tag string - either keep only specified tags or remove specified tags.

        Parameters:
            tag_string (str): The string containing tags
            keep_tags (list[str], optional): If provided, keep only these tags
            remove_tags (list[str], optional): If provided, remove these tags

        Returns:
            str: The filtered tag string
        """
        if keep_tags is not None:
            # Keep only specified tags
            base_name = tag_string.split(self.TAG_DELIMITER)[0]
            current_tags = self.get_tags_from_name(tag_string)
            keep_tags_set = set(ptk.make_iterable(keep_tags))
            filtered_tags = current_tags.intersection(keep_tags_set)

            if filtered_tags:
                return (
                    base_name
                    + self.TAG_DELIMITER
                    + self.TAG_DELIMITER.join(sorted(filtered_tags))
                )
            else:
                return base_name

        elif remove_tags is not None:
            return self.edit_tags(tag_string, remove=remove_tags)

        return tag_string

    def get_unknown_tags(self, tag_string: str, known_tags: list[str]) -> list[str]:
        """Get tags that are not in the known_tags list.

        Parameters:
            tag_string (str): The string containing tags
            known_tags (list[str]): List of known/expected tags

        Returns:
            list[str]: List of unknown tag names (without delimiter prefix)
        """
        known_tags_list = ptk.make_iterable(known_tags)
        pattern = "|".join(re.escape(tag) for tag in known_tags_list)
        tag_re = re.escape(self.TAG_DELIMITER) + f"(?!{pattern})[a-zA-Z0-9]*"
        unknown_tags = re.findall(tag_re, tag_string)
        return [
            tag[len(self.TAG_DELIMITER) :]
            for tag in unknown_tags
            if tag != self.TAG_DELIMITER
        ]
