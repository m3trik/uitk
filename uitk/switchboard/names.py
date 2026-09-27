# !/usr/bin/python
# coding=utf-8
import re
from typing import Union, List
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

        # One rule, owned by pythontk: a headless reader deriving the same
        # objectName from a definition (ExportProfile.widget_key) must agree
        # with the widget the switchboard built. It lives on StrUtils, not on
        # the export-profile class that also reads it -- this mixin is core
        # switchboard naming and has no business reaching into a Scene
        # Exporter's contract for it.
        return ptk.StrUtils.to_legal_name(name)

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

    def get_slot_file_names(self, base_name: str) -> List[str]:
        """Generate potential slot file names from a base name.

        Parameters:
            base_name (str): The base name to generate slot file names from.

        Returns:
            List[str]: A list of potential slot file names WITHOUT extension.
        """
        legal_name = self.convert_to_legal_name(base_name)
        # Strip leading underscores for variations
        stripped_name = legal_name.lstrip("_")

        candidates = [
            f"{legal_name}{self.SLOT_SUFFIX}",  # e.g. nameSlots
            f"{legal_name}_slots",  # e.g. name_slots
            legal_name,  # e.g. name (same as UI)
            f"_{stripped_name}",  # e.g. _name (underscore prefix)
        ]
        # Remove duplicates while preserving order
        seen = set()
        return [x for x in candidates if not (x in seen or seen.add(x))]

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
        # Exact-token matching: split the delimited string and compare whole
        # tags. Substring regex mis-fired on prefixes ('sub' vs 'submenu'),
        # truncated underscore tags, and never matched with an empty known list.
        known = set(ptk.make_iterable(known_tags))
        tags = tag_string.split(self.TAG_DELIMITER)[1:]
        return [tag for tag in tags if tag and tag not in known]

    @classmethod
    def unpack_names(cls, name_string):
        """Unpacks a comma-separated string of names and returns a list of individual names.

        Parameters:
            name_string (str): A string consisting of widget names separated by commas.
                    Names may include ranges with hyphens, e.g., 'chk021-23, 25, tb001'.
        Returns:
            list: A list of unpacked names, e.g., ['chk021', 'chk022', 'chk023', 'chk025', 'tb001'].
        """

        def extract_parts(name):
            """Extract alphabetic and numeric parts from a given name using regular expressions."""
            return re.findall(r"([a-zA-Z]+)|(\d+)", name)

        names = re.split(r",\s*", name_string)
        unpacked_names = []
        last_prefix = None
        last_width = 3  # zero-pad width for bare-number continuations

        for name in names:
            parts = extract_parts(name)
            # Keep the raw numeric tokens so the zero-pad width can be derived
            # from the source string rather than hard-coded.
            digit_tokens = [p[1] for p in parts if p[1]]

            if not digit_tokens:
                # A name with no numeric token passes through verbatim (e.g.
                # 'grp_basic'); a purely non-alphanumeric token is skipped.
                if parts:
                    unpacked_names.append(name)
                    if parts[0][0]:
                        last_prefix = parts[0][0]
                continue

            prefix = parts[0][0]
            width = len(digit_tokens[0])

            if len(digit_tokens) >= 2:
                # Range notation, e.g. 'chk000-2' (reverse ranges yield nothing).
                start, stop = int(digit_tokens[0]), int(digit_tokens[1])
                unpacked_names.extend(
                    prefix + str(num).zfill(width) for num in range(start, stop + 1)
                )
                last_prefix, last_width = prefix, width
            elif not prefix:
                # Bare number — continuation of the previous prefix, e.g. the
                # '1' in 'chk000, 1'.
                unpacked_names.append(
                    (last_prefix or "") + digit_tokens[0].zfill(last_width)
                )
            else:
                # Single prefixed name, e.g. 'chk000'.
                unpacked_names.append(name)
                last_prefix, last_width = prefix, width

        return unpacked_names

    def get_widgets_by_string_pattern(self, ui, name_string):
        """Get a list of corresponding widgets from a single shorthand formatted string.
        ie. 's000,b002,cmb011-15' would return object list: [<s000>, <b002>, <cmb011>, <cmb012>, <cmb013>, <cmb014>, <cmb015>]

        Parameters:
            ui (QWidget): A previously loaded dynamic UI object.
            name_string (str): Widget object names separated by ','. ie. 's000,b004-7'. b004-7 specifies buttons b004 though b007.

        Returns:
            (list) QWidget(s)

        Example:
            get_widgets_by_string_pattern(<ui>, 's000,b002,cmb011-15')
        """
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        widgets = []
        for n in self.unpack_names(name_string):
            w = getattr(ui, n, None)
            if not isinstance(w, QtWidgets.QWidget):
                # A registered widget whose objectName shadows a QWidget method
                # ('size', 'font') is deliberately NOT bound as an attribute
                # (see MainWindow.register_widget), so the attribute is the
                # method: read the registry instead of handing a rule a bound
                # method to setEnabled(). A container with no registry (an
                # option-box Menu) has only its attributes to offer.
                registered = getattr(ui, "widgets", None) or ()
                w = next((x for x in registered if x.objectName() == n), None)
            if w is None:
                self.logger.info(f"[get_widgets_by_string_pattern] no widget {n!r}")
                continue
            widgets.append(w)

        return widgets

    def get_methods_by_string_pattern(self, clss, name_string):
        """Get a list of corresponding methods from a single shorthand formatted string.
        ie. 's000,b002,cmb011-15' would return methods: [<s000>, <b002>, <cmb011>, <cmb012>, <cmb013>, <cmb014>, <cmb015>]

        Parameters:
            clss (class): The class containing the methods.
            name_string (str): Slot names separated by ','. ie. 's000,b004-7'. b004-7 specifies methods b004 through b007.

        Returns:
            (list) class methods.

        Example:
            get_methods_by_string_pattern(<ui>, 'slot1,slot2,slot3')
        """
        if not isinstance(clss, object):
            raise ValueError(f"Invalid datatype: Expected class, got {type(clss)}")

        result = []
        for method_name in self.unpack_names(name_string):
            method = getattr(clss, method_name, None)
            if method is not None:
                result.append(method)

        return result
