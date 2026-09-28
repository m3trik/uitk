# !/usr/bin/python
# coding=utf-8
"""The preset selector: a combo wired as a fully functional preset picker.

One part of :class:`~uitk.managers.preset_manager.PresetManager`, reached
through its public :meth:`~uitk.managers.preset_manager.PresetManager.wire_combo`
(the documented contract lives there). The wiring is a set of closures over
the manager and the combo: the combo's own signal connections hold them, and
through them the manager, so a panel that wires a combo and keeps nothing else
still has a working selector.
"""

from typing import Optional

from qtpy import QtCore, QtGui
import pythontk as ptk


class _PresetComboWiring:
    """Builds the Refresh / Save / menu toolbar and the list behavior of a preset combo."""

    @classmethod
    def wire(cls, mgr, combo, on_loaded=None, placeholder=None):
        """Wire *combo* as *mgr*'s preset selector; see ``PresetManager.wire_combo``.

        Returns:
            The combo's ``option_box`` container (combo + toolbar).
        """
        placeholder = placeholder or "Presets…"

        def listing():
            """``(names, marks)`` from ONE store build.

            *names* are what the dropdown offers; *marks* is ``{name:
            (read_only, tooltip)}`` for the ones that need either. A name is
            read-only when it ships as a built-in not shadowed by a user preset,
            or is a user preset locked in the Preset Editor; the tooltip carries
            that, and the preset's description. A preset hidden in the Preset
            Editor is left out -- unless it is the active one: a hide never
            blanks the selection a panel is on. Resolved in one pass (two globs
            + one sidecar read per user preset) rather than probing
            ``source(nm)`` per name -- each call rebuilt the store and stat'd
            both tiers, so a preset-heavy panel paid O(N) store builds. A
            built-in not shadowed by a user preset still costs its own lookups
            (``is_hidden`` reads the store's ``.hidden`` list, ``description``
            its payload): built-ins are few, and ``PresetStore`` has no batch
            read of either.
            """
            store = mgr._store
            builtin_names = set(store.list(tier="builtin"))
            user_names = set(store.list(tier="user"))
            active = store.active
            names, marks = [], {}
            for nm in sorted(builtin_names | user_names):
                if nm in user_names:
                    info = store.info(nm)
                    hidden = bool(info.get("hidden"))
                    read_only = bool(info.get("read_only"))
                    note = "locked; unlock it in the Preset Editor" if read_only else ""
                    description = str(info.get("description") or "")
                else:
                    hidden = store.is_hidden(nm)
                    read_only = True
                    note = "built-in, read-only"
                    description = store.description(nm)
                if hidden and nm != active:
                    continue
                names.append(nm)
                lines = [f"{nm} ({note})" if note else "", description]
                tip = "\n".join(line for line in lines if line)
                if read_only or tip:
                    marks[nm] = (read_only, tip)
            return names, marks

        def mark_items(names, marks):
            """Italicise read-only presets (built-in or locked); set tooltips.

            Sets the model item's font/tooltip rather than its text, so
            ``itemText`` stays the raw preset name for load/rename/delete. The
            italic is via ``Qt.FontRole`` (dropdown list only) -- the collapsed
            display keeps the widget font, so the dropdown arrow is unaffected.
            """
            model = combo.model()
            if not hasattr(model, "item"):
                return
            italic = QtGui.QFont(combo.font())
            italic.setItalic(True)
            for i, nm in enumerate(names):
                mark = marks.get(nm)
                item = model.item(i) if mark is not None else None
                if item is None:
                    continue
                read_only, tip = mark
                if read_only:
                    item.setFont(italic)
                if tip:
                    item.setToolTip(tip)

        # (names, marks) the combo last showed; the popup hook compares against
        # it so an unchanged folder costs no repopulate.
        shown = {"listing": None}

        def refresh(select_name: Optional[str] = None):
            """Repopulate the combo with current preset names.

            Parameters:
                select_name: If given, select this preset after repopulating.
                    If ``None``, the persisted **active preset** is re-selected
                    (idea: restore only the *selection* -- widget values restore
                    themselves from session state). Selection is set with
                    signals blocked, so **no values are applied** (selection-load
                    is keyed off the user-only ``activated`` signal). The name
                    as typed finds its item too: items are file stems, which
                    lose punctuation (``"a (b)"`` is listed as ``"a _b_"``).
            """
            if select_name is None:
                select_name = mgr.active_preset
            names, marks = listing()
            shown["listing"] = (names, marks)
            combo.blockSignals(True)
            try:
                combo.clear()
                if names:
                    combo.addItems(names)
                    mark_items(names, marks)
                    # findText -> -1 when the (stale) name is gone, which falls
                    # through to the placeholder rather than a silent item-0.
                    index = combo.findText(select_name) if select_name else -1
                    if index < 0 and select_name:
                        index = combo.findText(
                            ptk.PresetStore.sanitize_preset_name(select_name)
                        )
                    combo.setCurrentIndex(index)
                    combo.setPlaceholderText(placeholder)
                else:
                    combo.setCurrentIndex(-1)
                    combo.setPlaceholderText("No saved presets")
            finally:
                combo.blockSignals(False)
            # Selection was set with signals blocked (no value apply); sync the
            # dirty baseline from the active preset and refresh the marker.
            mgr._resync_active()

        def selected_name() -> str:
            """The currently-selected preset name (``""`` when none)."""
            idx = combo.currentIndex()
            return combo.itemText(idx) if idx >= 0 else ""

        def apply_preset(name):
            """(Re)apply preset *name*'s values to the widgets (no-op if falsy).

            When ``on_loaded`` is provided, block signals during load and fire
            the single consolidated callback afterwards. Otherwise, let signals
            propagate so normal slot handlers (e.g. checkbox -> refresh) fire.
            """
            if not name:
                return
            mgr.load(name, block_signals=on_loaded is not None)
            if on_loaded:
                on_loaded()

        def on_selected(idx):
            """User picked a preset from the dropdown -> load it.

            Wired to ``activated`` (user-only), never ``currentIndexChanged``,
            so programmatic selection during ``refresh`` / inline-edit commit
            never triggers a (potentially clobbering) reload.
            """
            if idx >= 0:
                apply_preset(combo.itemText(idx))

        def on_refresh():
            """Re-scan the preset dir, then reload the **active** preset's values.

            Repopulates the combo from disk first (via :func:`refresh`) so
            presets added to or removed from the preset directory *outside* the
            UI -- a user dropping in or deleting ``*.json`` files by hand -- are
            picked up. Then re-applies the active preset's values, discarding
            any edits.

            The value re-apply is keyed off ``mgr.active_preset`` rather than the
            combo's ``currentIndex`` so Refresh still works after a session
            restore (or any state that left the index at -1) -- the index-based
            version silently no-oped, which read as "Refresh is broken". It is
            skipped when the active preset no longer exists on disk (e.g. its
            file was just deleted by hand), so there's no spurious warning.
            """
            refresh()
            active = mgr.active_preset
            if active and mgr.exists(active):
                apply_preset(active)

        def begin_inline_edit(mode: str, seed: str, subject: str = ""):
            """Enter in-place edit mode pre-filled with *seed* for *mode*.

            *mode* (``"save"`` / ``"rename"``) and *subject* (the preset being
            renamed) are consumed by :func:`on_edit_committed` on the next
            Enter. The subject must be captured now: the combo item text is
            already the NEW name when the commit fires. Clicking away fires no
            commit (``ComboBox.focusOutEvent`` exits edit mode silently).
            """
            mgr._pending_preset_action = (mode, subject)
            combo.setEditable(True)
            line_edit = combo.lineEdit()
            if line_edit is not None:
                line_edit.setText(seed or "")
                line_edit.selectAll()
                line_edit.setFocus()

        def copy_name(name: str) -> str:
            """``"<name> copy"``, numbered until free: where a locked save lands."""
            return mgr._store.unique_name(f"{name} copy")

        def on_save():
            """Start an inline Save: type a name + Enter (same name overwrites)."""
            current = selected_name()
            # A built-in blanks the seed so Save acts as duplicate-to-edit
            # rather than re-typing the read-only default's name; a locked user
            # preset seeds a free "<name> copy" (it can't be overwritten).
            if current and mgr.source(current) == "builtin":
                seed = ""
            elif current and mgr.is_locked(current):
                seed = copy_name(current)
            else:
                seed = current
            begin_inline_edit("save", seed)

        def on_rename():
            """Start an inline Rename of the selected (unlocked) user preset."""
            current = selected_name()
            if not current or mgr.source(current) != "user" or mgr.is_locked(current):
                return
            begin_inline_edit("rename", current, subject=current)

        def on_edit_committed(text: str):
            """Dispatch the committed inline-edit text per the pending action."""
            pending = getattr(mgr, "_pending_preset_action", None)
            mgr._pending_preset_action = None
            if pending is None:
                return
            mode, subject = pending
            name = (text or "").strip()
            if mode == "save":
                if not name:
                    return
                if mgr.is_locked(name):
                    # Typed over a locked preset: offer the free copy name
                    # instead of failing silently (Enter again saves it).
                    mgr.logger.warning(
                        f"Preset '{name}' is locked; saving as a copy instead."
                    )
                    begin_inline_edit("save", copy_name(name))
                    return
                mgr.save(name)
                # The saved preset becomes active; its values == what we just
                # wrote, so the marker is clean.
                mgr.active_preset = name
                refresh(select_name=name)
            elif mode == "rename":
                old = subject or mgr.active_preset
                if (
                    name
                    and old
                    and name != old
                    and mgr.source(old) == "user"
                    and not mgr.is_locked(old)
                ):
                    if mgr.rename(old, name):
                        refresh(select_name=name)
                        return
                # Invalid / unchanged / cancelled -- restore the display.
                refresh()

        def on_delete():
            current = selected_name()
            if not current:
                return
            mgr.delete(current)
            refresh()

        def on_open_folder():
            """Open the preset directory in the system file explorer."""
            preset_dir = mgr.preset_dir
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(preset_dir)))

        def build_menu_items(_widget):
            """Menu items, rebuilt per open so read-only presets hide Rename/Delete.

            A read-only built-in, a locked user preset (or no selection) can't be
            renamed or deleted, so those entries are omitted rather than shown
            disabled -- cleaner for a short pop-up menu.
            """
            current = selected_name()
            editable = (
                bool(current)
                and mgr.source(current) == "user"
                and not mgr.is_locked(current)
            )
            items = []
            if editable:
                items.append(("Rename", on_rename))
            items.append(("Open Folder", on_open_folder))
            if editable:
                items.append(("Delete", on_delete))
            return items

        def refresh_if_changed():
            """Re-list on dropdown open; repopulate only if the list or marks changed.

            Picks up presets added, locked, hidden or imported outside this panel (another
            DCC, the Preset Editor) without a manual Refresh, at the cost of the
            same globs a refresh does -- and without disturbing the list when
            nothing changed.
            """
            try:
                if listing() != shown["listing"]:
                    refresh()
            except (OSError, RuntimeError) as e:
                mgr.logger.debug(f"Preset popup refresh skipped: {e}")

        def update_marker(modified: bool):
            """Reflect the modified ('dirty') state as an asterisk on the combo's
            displayed current text (item data is left untouched)."""
            combo.current_text_suffix = " *" if modified else ""

        mgr._excluded_widgets.add(combo)
        mgr._refresh_combo = refresh
        mgr._live.add(mgr)  # the class-level WeakSet ``notify`` walks

        # Bound the combo's height so the option-box icon buttons (sized to the
        # combo's height) stay compact. A combo dropped into a *stretchy*
        # container — e.g. a menu's "Menu Actions" group (``add_presets``) — has
        # no vertical limit and expands to fill it, which would balloon the
        # square icon buttons and squeeze the dropdown to nothing. Pin it to the
        # natural row height (its size hint) unless the caller already set an
        # explicit maximum (the in-panel rows that pass a fixed height).
        hint_h = combo.sizeHint().height()
        if hint_h > 0 and combo.maximumHeight() >= 16777215:  # QWIDGETSIZE_MAX
            combo.setFixedHeight(hint_h)

        # The compact option-box toolbar: Refresh, Save, then a menu holding
        # Rename / Open / Delete. ActionOptions sort before the menu option, and
        # insertion order is preserved within the action group, so the rendered
        # left-to-right order is exactly [refresh][save][menu]. The menu is a
        # cursor-centred pop-up with no header / footer / apply chrome (a plain
        # action list), matching a right-click context menu.
        from uitk.widgets.optionBox.options.option_menu import ContextMenuOption

        combo.option_box.add_action(
            callback=on_refresh,
            icon="refresh",
            tooltip="Rescan presets folder and reload the active preset (discard edits).",
        )
        combo.option_box.add_action(
            callback=on_save,
            icon="save",
            tooltip="Save the current settings as a preset (type a name, Enter).",
        )
        combo.option_box.add_option(
            ContextMenuOption(
                wrapped_widget=combo,
                menu_provider=build_menu_items,
                icon="menu",
                tooltip="Preset actions: rename, open folder, delete.",
                position="cursorPos",
                add_header=False,
                add_footer=False,
                add_apply_button=False,
                add_defaults_button=False,
                match_parent_width=False,
            )
        )

        mgr.on_modified_changed(update_marker)
        # Live marker updates for the menu / standalone (widget-state) paths;
        # no-op in semantic mode (the caller wires its own param widgets).
        mgr.connect_value_widgets()

        # Inline Save / Rename commit on Enter (see ComboBox.on_editing_finished).
        combo.on_editing_finished.connect(on_edit_committed)
        # A plain QComboBox has no such signal; only uitk's ComboBox re-lists.
        before_popup = getattr(combo, "before_popup_shown", None)
        if before_popup is not None:
            before_popup.connect(refresh_if_changed)

        refresh()
        # ``activated`` is user-only -- programmatic selection (refresh, inline
        # commit) never reloads, so an overwrite-Save can't clobber the live
        # values with the pre-save snapshot.
        try:
            combo.activated[int].connect(on_selected)
        except (TypeError, KeyError):
            combo.activated.connect(on_selected)

        return combo.option_box.container
