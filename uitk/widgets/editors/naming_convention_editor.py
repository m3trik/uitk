# !/usr/bin/python
# coding=utf-8
"""An editor for a naming convention, built into a uitk ``Menu``.

:class:`NamingConventionEditor` lays out one row per convention entry -- an
affix field with a placement picker (``AffixOption``: Auto / Suffix / Prefix)
and the entry's label beside it -- writes every edit straight back to the
convention, and offers named snapshots of the whole convention in the menu's
preset combo.

It is generic over the convention: any object with the class-level surface of
:class:`pythontk.NamingConvention` (``keys`` / ``get`` / ``label`` / ``set`` /
``update`` / ``as_dict`` / ``preset_store``) can be edited, and every label,
spelling and placement comes from it.  What a host adds is data: how the rows
are grouped and which objectName each field carries (``groups``), what a row's
tooltip says (``tooltip``), and which rows it shows but cannot apply
(``disabled``).

Example
-------
>>> editor = NamingConventionEditor(
...     widget.option_box.menu,
...     groups=[("Shapes", [("mesh", "txt_mesh"), ("camera", "txt_camera")])],
...     disabled={"camera": "Cameras are not renamed here."},
... ).build()
>>> dict(editor.fields())["mesh"].text()
'_GEO'
"""

from typing import Callable, Iterator, List, Mapping, Optional, Sequence, Tuple

import pythontk as ptk

#: ``(title, ((convention key, field objectName), ...))`` -- one display group.
Group = Tuple[str, Sequence[Tuple[str, str]]]


class NamingConventionEditor:
    """Rows of affix fields in a ``Menu`` that edit a naming convention in place.

    The convention is the fields' store: a field shows the convention's current
    spelling, an edit (text or placement) writes it back through
    ``convention.set``, and loading a preset writes the whole snapshot through
    ``convention.update`` and then re-shows it.  Per-widget state persistence is
    switched off on every field, because a value it restored would sit over the
    convention and be written back into it on the next edit.

    Parameters:
        menu: The ``uitk.Menu`` to build into -- typically an option box's menu.
        groups: Display groups, ``((title, ((key, object_name), ...)), ...)``.
            The objectName makes each field reachable as ``menu.<object_name>``.
            ``None`` (default): one untitled group holding every
            ``convention.keys()`` entry, each field named after its key.
        convention: The convention to edit; default ``pythontk.NamingConvention``.
        tooltip: ``(key, label) -> str`` for an editable row. Default: a generic
            description of the field and its placement picker.
        disabled: ``{key: reason}`` -- rows shown greyed out, with *reason* as
            their tooltip. Such a row is still wired: the convention may be
            shared with another host that CAN apply the entry.
        presets: Offer named snapshots of the convention in the menu's preset
            combo (semantic mode), kept in ``convention.preset_store()``.
        logger: Optional logger; each write is logged at debug level.
    """

    def __init__(
        self,
        menu,
        groups: Optional[Sequence[Group]] = None,
        *,
        convention=None,
        tooltip: Optional[Callable[[str, str], str]] = None,
        disabled: Optional[Mapping[str, str]] = None,
        presets: bool = True,
        logger=None,
    ):
        self.menu = menu
        self.convention = convention if convention is not None else ptk.NamingConvention
        self.groups = tuple(groups) if groups is not None else self.default_groups()
        self.tooltip = tooltip or self.default_tooltip
        self.disabled = dict(disabled or {})
        self.presets = presets
        self.logger = logger
        #: ``(key, field)`` per row built, in build order (see :meth:`fields`).
        self._rows: List[Tuple[str, object]] = []

    # ------------------------------------------------------------ vocabulary
    def default_groups(self) -> Tuple[Group, ...]:
        """One untitled group over every entry the convention holds."""
        return (("", tuple((key, key) for key in self.convention.keys())),)

    @staticmethod
    def default_tooltip(key: str, label: str) -> str:
        """A generic row tooltip: what the field is and what its picker does."""
        return (
            f"Affix for {label.lower()}s. Leave empty to skip this type.<br><br>"
            "The button beside the field sets placement: Auto (a leading '_' "
            "trails, a trailing '_' leads) / Suffix / Prefix."
        )

    # ----------------------------------------------------------------- build
    def build(self) -> "NamingConventionEditor":
        """Add every group's rows (and the preset combo) to the menu.

        Returns:
            This editor, so construction and build chain.
        """
        from uitk import OptionBoxManager

        # Every field needs the ``option_box`` manager for its placement picker.
        # A Switchboard patches the common widget classes at startup; outside
        # one they are plain Qt. Idempotent.
        OptionBoxManager.patch_common_widgets()
        for title, rows in self.groups:
            if title:
                self.menu.add("Separator", setTitle=title, colSpan=2)
            for key, object_name in rows:
                self.add_row(key, object_name)
        if self.presets:
            self._wire_presets()
        return self

    def add_row(self, key: str, object_name: str):
        """One row: the affix field, the entry's label beside it, wired.

        The placeholder names a field only while it is empty, and every row
        ships filled, so the label in the second grid column is what tells
        near-identical ``_XYZ`` fields apart. Both cells take one column
        explicitly: ``Menu.add`` otherwise spans the grid's full width.

        Returns:
            The field.
        """
        label = self.convention.label(key)
        reason = self.disabled.get(key)
        tip = reason if reason is not None else self.tooltip(key, label)
        attrs = {} if reason is None else {"setEnabled": False}
        field = self.menu.add(
            "QLineEdit",
            setPlaceholderText=f"{label} Affix",
            setText=self.convention.get(key).text,
            setObjectName=object_name,
            setToolTip=tip,
            colSpan=1,
            **attrs,
        )
        grid = self.menu.gridLayout
        row = grid.getItemPosition(grid.indexOf(field))[0]
        self.menu.add(
            "QLabel",
            setText=label,
            setToolTip=tip,
            setIndent=4,
            row=row,
            col=1,
            colSpan=1,
            **attrs,
        )
        self._wire_field(field, key)
        self._rows.append((key, field))
        return field

    def _wire_field(self, field, key: str) -> None:
        """Give *field* a placement picker and write its edits to the convention."""
        rule = self.convention.get(key)
        # The convention is this field's store, so per-widget state persistence
        # has to stand down: it would restore a value saved before the
        # convention existed over the top of it, and the next edit would write
        # that stale value back.
        field.restore_state = False
        field.setText(rule.text)
        field.option_box.set_affix(
            default=rule.mode,
            # This editor EDITS the convention, so it must not also offer the
            # "follow the convention" state -- that would be a field bound to
            # itself. The three manual modes are exactly the placement choice.
            settings_key=False,  # the convention is the store, not QSettings
            on_change=lambda mode, k=key, f=field: self.save(k, f.text(), mode, f),
        )
        field.editingFinished.connect(
            lambda k=key, f=field: self.save(k, f.text(), f.option_box.affix_mode, f)
        )

    # ----------------------------------------------------------------- write
    def save(self, key: str, text: str, mode: str, field=None) -> bool:
        """Persist one row to the convention (a no-op when unchanged).

        A bare token typed into the field is delimited first
        (``StrUtils.delimit_affix``) -- the convention's consumers concatenate
        verbatim and must not guess, so the field that accepts free text is
        where to be forgiving -- and the delimited spelling is reflected back,
        so the row shows what was actually stored.

        Returns:
            True when the convention changed.
        """
        text = ptk.StrUtils.delimit_affix(text, mode)
        if field is not None and field.text() != text:
            field.setText(text)
        rule = self.convention.get(key)
        if (rule.text, rule.mode) == (text, mode):
            return False
        self.convention.set(key, text, mode)
        if self.logger is not None:
            self.logger.debug(f"[naming] convention {key!r} -> {text!r} ({mode})")
        # Semantic presets watch no widgets; an edit has to report itself so
        # the preset combo marks the active preset modified.
        if self.presets:
            try:
                self.menu.presets.refresh_modified_state()
            except AttributeError:
                pass
        return True

    # ---------------------------------------------------------------- presets
    def fields(self) -> Iterator[Tuple[str, object]]:
        """``(key, field)`` for every row built -- by :meth:`build` or
        :meth:`add_row` -- in the order they were added.

        The editor keeps its own rows rather than looking them up on the menu
        by objectName: a name shared with a ``Menu`` member (``render``,
        ``layout``) would resolve to that member instead.
        """
        return iter(list(self._rows))

    def apply_preset(self, data: Mapping[str, object]) -> int:
        """Preset applier: store a saved convention snapshot, then show it.

        The convention is the store its consumers read, so loading a preset
        writes it there (``convention.update``) and the fields follow -- each
        picker's ``on_change`` then finds the convention already equal and
        writes nothing.

        Returns:
            The number of entries applied.
        """
        from uitk import AffixOption

        # ``_``-keys are a preset's own blocks (a shipped one's ``_meta``), not
        # entries -- ``convention.update`` skips them too, so counting them
        # would overstate what was applied.
        rules = {
            k: v
            for k, v in data.items()
            if not k.startswith("_") and isinstance(v, (dict, str))
        }
        self.convention.update(rules)
        for key, field in self.fields():
            rule = self.convention.get(key)
            field.setText(rule.text)
            picker = field.option_box.find_option(AffixOption)
            if picker is not None:
                picker.set_mode(rule.mode)
        return len(rules)

    def _wire_presets(self) -> None:
        """Named snapshots of the whole convention in the menu's action row.

        Semantic mode: a preset is ``convention.as_dict()``, not a widget
        snapshot, kept in the convention's own store
        (``convention.preset_store()``) so every host editing the same
        convention shares them. The store's built-in tier (the shipped
        ``default``, read-only) is listed beside the user's own.
        """
        store = self.convention.preset_store()
        presets = self.menu.presets
        presets.preset_dir = str(store.user_dir)
        presets.builtin_dir = store.builtin_dir
        presets.value_provider = self.convention.as_dict
        presets.value_applier = self.apply_preset
        self.menu.add_presets = True
