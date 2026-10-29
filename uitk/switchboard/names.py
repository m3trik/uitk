# !/usr/bin/python
# coding=utf-8
import re
from typing import Union, List
from qtpy import QtWidgets
import pythontk as ptk


class _Names:
    """Names and tags behind the Switchboard: legal names, slot-class names, tag
    strings and the shorthand name patterns (``'b000-3'``). Stateless; reads the
    Switchboard's vocabulary (``TAG_DELIMITER``, ``SLOT_SUFFIX``) live, so a
    subclass that overrides one is honored everywhere.
    """

    def __init__(self, sb):
        self._sb = sb

    @staticmethod
    def convert_to_legal_name(name: str) -> str:
        if not isinstance(name, str):
            raise ValueError(f"Expected a string, got {type(name)}")

        # One rule, owned by pythontk: a headless reader deriving the same
        # objectName from a definition (ExportProfile.widget_key) must agree
        # with the widget the switchboard built. It lives on StrUtils, not on
        # the export-profile class that also reads it -- this class is core
        # switchboard naming and has no business reaching into a Scene
        # Exporter's contract for it.
        return ptk.StrUtils.to_legal_name(name)

    def get_slot_class_names(self, base_name: str) -> List[str]:
        legal_name = self._sb.convert_to_legal_name(base_name)
        capitalized = "".join(part.title() for part in legal_name.split("_"))
        return [f"{capitalized}{self._sb.SLOT_SUFFIX}", capitalized]

    def get_slot_file_names(self, base_name: str) -> List[str]:
        legal_name = self._sb.convert_to_legal_name(base_name)
        # Strip leading underscores for variations
        stripped_name = legal_name.lstrip("_")

        candidates = [
            f"{legal_name}{self._sb.SLOT_SUFFIX}",  # e.g. nameSlots
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
        name = name.split(self._sb.TAG_DELIMITER)[0]
        name = re.sub(r"[_\d]+$", "", name)
        match = re.search(r"\b[a-zA-Z]\w*", name)
        return match.group() if match else name

    def get_tags_from_name(self, name: str) -> set[str]:
        parts = name.split(self._sb.TAG_DELIMITER)
        return set(parts[1:]) if len(parts) > 1 else set()

    def has_tags(self, ui, tags=None) -> bool:
        if not isinstance(ui, QtWidgets.QWidget):
            self._sb.logger.debug(f"Invalid UI type: {type(ui)}. Expected QWidget.")
            return False

        if not hasattr(ui, "tags"):
            self._sb.logger.debug(f"UI '{ui.objectName()}' has no 'tags' attribute.")
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
        if isinstance(target, str):
            current_tags = self._sb.get_tags_from_name(target)
            base_name = target.split(self._sb.TAG_DELIMITER)[0]

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
                + self._sb.TAG_DELIMITER
                + self._sb.TAG_DELIMITER.join(sorted(current_tags))
            )

        elif isinstance(target, QtWidgets.QWidget):
            if not hasattr(target, "tags"):
                target.tags = set()

            if reset:
                target.tags = self._sb.get_tags_from_name(target.objectName())
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
        if keep_tags is not None:
            # Keep only specified tags
            base_name = tag_string.split(self._sb.TAG_DELIMITER)[0]
            current_tags = self._sb.get_tags_from_name(tag_string)
            keep_tags_set = set(ptk.make_iterable(keep_tags))
            filtered_tags = current_tags.intersection(keep_tags_set)

            if filtered_tags:
                return (
                    base_name
                    + self._sb.TAG_DELIMITER
                    + self._sb.TAG_DELIMITER.join(sorted(filtered_tags))
                )
            else:
                return base_name

        elif remove_tags is not None:
            return self._sb.edit_tags(tag_string, remove=remove_tags)

        return tag_string

    def get_unknown_tags(self, tag_string: str, known_tags: list[str]) -> list[str]:
        # Exact-token matching: split the delimited string and compare whole
        # tags. Substring regex mis-fired on prefixes ('sub' vs 'submenu'),
        # truncated underscore tags, and never matched with an empty known list.
        known = set(ptk.make_iterable(known_tags))
        tags = tag_string.split(self._sb.TAG_DELIMITER)[1:]
        return [tag for tag in tags if tag and tag not in known]

    @classmethod
    def unpack_names(cls, name_string):
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
        if not isinstance(ui, QtWidgets.QWidget):
            raise ValueError(f"Invalid datatype: Expected QWidget, got {type(ui)}")

        widgets = []
        for n in self._sb.unpack_names(name_string):
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
                self._sb.logger.info(f"[get_widgets_by_string_pattern] no widget {n!r}")
                continue
            widgets.append(w)

        return widgets

    def get_methods_by_string_pattern(self, clss, name_string):
        if not isinstance(clss, object):
            raise ValueError(f"Invalid datatype: Expected class, got {type(clss)}")

        result = []
        for method_name in self._sb.unpack_names(name_string):
            method = getattr(clss, method_name, None)
            if method is not None:
                result.append(method)

        return result
