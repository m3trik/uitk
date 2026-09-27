# !/usr/bin/python
# coding=utf-8
"""Which chord opens which menu: the binding table, the activation key, routes.

The persisted, host-namespaced chord -> menu table (forward-merged with
the shipped defaults on every construction), the activation key elected
from it and the ``GlobalShortcut`` that listens for it, the mouse-gesture
routes the host's binding combos edit, and their read-only entries in the
unified shortcut editor.

One part of :class:`~uitk.widgets.marking_menu._marking_menu.MarkingMenu`,
which inherits it; it holds no state of its own beyond the class-level
defaults it declares, and is never instantiated alone.
"""

from typing import Optional

from qtpy import QtCore

from uitk.managers.settings_manager import SettingsManager
from uitk.managers.shortcut_manager import GlobalShortcut, ShortcutManager
from ._resolver import MenuResolver


class _BindingsMixin:
    """Which chord opens which menu: the binding table, the activation key, routes."""

    _shortcut_instance: Optional["GlobalShortcut"] = None

    # The mouse-button gestures whose target menu the host's "Menu Bindings"
    # combos edit. Surfaced in the unified shortcut editor as hidden, read-only
    # entries (the routing table is not a key trigger — the combos stay its
    # editor), so "everything is in the register" without cluttering the default
    # view. The key-only default menu is intentionally absent (it isn't a mouse
    # chord; its trigger is the activation key, which has its own visible entry).
    _ROUTE_GESTURES = (
        ("left", ("LeftButton",)),
        ("middle", ("MiddleButton",)),
        ("right", ("RightButton",)),
        ("left_right", ("LeftButton", "RightButton")),
    )
    _BUTTON_LABELS = {
        "LeftButton": "Left",
        "MiddleButton": "Middle",
        "RightButton": "Right",
    }

    @classmethod
    def _reconcile_bindings(
        cls, defaults: dict, stored: Optional[dict]
    ) -> Optional[dict]:
        """Decide what binding dict (if any) to persist at construction.

        Returns the dict to write to persistent storage, or ``None`` when no
        write is needed:

        * ``stored is None`` (first run) → seed with ``defaults``.
        * ``stored`` present → ``{**defaults, **stored}`` so newly-shipped default
          keys are added while the user's customizations of existing keys win on
          overlap. Returns ``None`` when that merge equals the stored dict
          (already current — avoid a redundant write + ``changed`` signal).

        Without the forward-merge a user who ran an older version keeps a frozen
        binding set and never receives new defaults — the symptom that a newly
        added chord (e.g. ``F12+L+R``) silently falls through to a sibling menu
        because its binding was never present in the resolver's lookup.

        **Bindings for a different activation key are evicted first**, because a menu has exactly
        one activation key and the resolver elects it by taking the first ``Key_*`` it meets while
        walking this dict. Merging without eviction let several accumulate (measured in the wild:
        one store held ``F11``, ``Z``, ``F12`` *and* ``F10``), and then whichever landed first —
        pure insertion-order accident from some earlier session — silently became the live key.
        That also made ``key_show`` powerless to correct it: once the requested key already
        existed in the store with matching values, the merge equalled the stored dict, so nothing
        was rewritten and the stale leader kept winning every launch. The caller's ``key_show`` /
        ``bindings`` is therefore authoritative for *which key activates*; the store keeps the
        user's chord→menu customizations on that key.

        A ``None`` or non-dict ``stored`` (unset, or corrupt/legacy QSettings) is
        treated as first run and re-seeded with ``defaults`` — never spread into
        a dict literal, which would raise at construction.
        """
        if not defaults:
            return None
        if not isinstance(stored, dict):
            return dict(defaults)

        def elect(bindings):
            """The activation key the resolver would pick from ``bindings``.

            Deferring to the resolver rather than re-implementing "first ``Key_*`` wins" keeps
            this in step with ``_build_bindings``, which elects the live key the same way — and
            it auto-prefixes bare forms (``"F12|LeftButton"`` → ``Key_F12``), which a local
            prefix scan reports as None and therefore fails to evict.
            """
            return MenuResolver.parse_binding_keys(bindings)[1]

        wanted = elect(defaults)
        kept = stored
        if wanted:
            kept = {
                chord: target
                for chord, target in stored.items()
                if elect({chord: target}) in (wanted, None)
            }
        merged = {**defaults, **kept}
        # Compare against what is actually on disk, not the filtered copy — an eviction is
        # itself a reason to write, even when the surviving entries match the defaults.
        return merged if merged != stored else None

    @staticmethod
    def _binding_store_key(context_tags) -> str:
        """QSettings key for persisted bindings, namespaced by host context.

        The QSettings backend is shared across processes by ``(org, app)``, so a
        Maya and a Blender session would otherwise read/write the SAME
        ``marking_menu_bindings`` key — and their chords collide: ``F12+L+R`` maps
        to ``maya#startmenu`` in one host and ``blender#startmenu`` in the other,
        so whichever persisted last hijacks the key and the other host's chord
        resolves to a UI it doesn't even have. Namespacing by ``context_tags``
        (``..._maya`` / ``..._blender``) keeps each DCC's binding set independent;
        an empty/absent context (standalone) keeps the legacy un-suffixed key.

        The host suffix is computed by the shared
        :meth:`ShortcutManager.host_namespace_suffix`, the same one the
        shortcut/command store uses — so the two binding systems can never
        disagree on a host's identity.
        """
        return "marking_menu_bindings" + ShortcutManager.host_namespace_suffix(
            context_tags
        )

    @staticmethod
    def _user_key_store_key(context_tags) -> str:
        """QSettings key for the activation key the USER chose, host-namespaced
        like :meth:`_binding_store_key` (and by the same shared suffix helper,
        so the two stores can't disagree on a host's identity)."""
        return (
            "marking_menu_user_activation_key"
            + ShortcutManager.host_namespace_suffix(context_tags)
        )

    @property
    def _user_key_store(self):
        """The persisted user-chosen-activation-key ``SettingItem`` for this
        menu's host context. Written only by :meth:`set_activation_key` — see
        :meth:`stored_activation_key` for why that exclusivity is load-bearing."""
        key = self._user_key_store_key(getattr(self.sb, "context_tags", None))
        return getattr(self.sb.configurable, key)

    @classmethod
    def stored_activation_key(cls, context_tags=None) -> Optional[str]:
        """The activation key the USER chose for a host context (``"Key_F11"``), or ``None``.

        Written **only** by :meth:`set_activation_key` — i.e. by an actual rebind route
        (the shortcut editor, a host Preferences panel, or an adopted DCC-side keymap
        edit) — never by construction seeding the chord store. Presence is therefore
        provenance: ``None`` means the user never expressed a choice, so the caller's
        shipped default should apply — including a NEWLY shipped default, which must
        reach exactly the installs whose user never rebound. A host resolves its launch
        key as: this value > its own ``key_show`` default > the shipped fallback (see
        tentacle's ``Tcl.resolve_key``); the user's choice outranks a startup script
        re-asserting its default at every launch.

        Readable **before** a menu exists — which is the point: hosts ask at launch,
        before construction. Reads the same host-namespaced store the live menu writes
        (:meth:`_user_key_store`) on the shared ``(org, app)`` backend. ``None`` when
        nothing is stored, the store is unreadable, or the value is not a plausible
        ``Key_*`` name (the write path only ever stores normalized, validated names).
        """
        try:
            configurable = SettingsManager(namespace="switchboard").branch(
                "configurable"
            )
            stored = getattr(configurable, cls._user_key_store_key(context_tags)).get(
                None
            )
        except (
            Exception
        ):  # unreadable/corrupt store — the caller falls back to its default
            return None
        # The write path stores only validated Qt key names, so anything else is
        # tampering/corruption. Declining it here matters: a host launches on this
        # value, and _build_bindings leaves the menu un-triggerable on a name
        # QtCore.Qt doesn't have — better the shipped default than a dead menu.
        if (
            not isinstance(stored, str)
            or not stored.startswith("Key_")
            or not hasattr(QtCore.Qt, stored)
        ):
            return None
        return stored

    @property
    def _bindings_store(self):
        """The persisted-bindings ``SettingItem`` for this menu's host context.

        See :meth:`_binding_store_key` for why the key is host-namespaced. The
        pre-namespace key is intentionally left orphaned — re-seeding each host
        from its own current defaults is the correct recovery from the prior
        shared-key collision (so a Blender session no longer inherits Maya's
        ``F12+L+R`` target, or vice versa).
        """
        key = self._binding_store_key(getattr(self.sb, "context_tags", None))
        return getattr(self.sb.configurable, key)

    @property
    def default_bindings(self) -> dict:
        """The original bindings passed at construction time."""
        return dict(self._default_bindings or {})

    @property
    def bindings(self) -> dict:
        """Get bindings from persistent storage."""
        return self._bindings_store.get({})

    @bindings.setter
    def bindings(self, value: dict):
        """Set bindings (auto-persists and triggers rebuild via callback)."""
        self._bindings_store.set(value)

    def on_bindings_changed(self, callback) -> None:
        """Subscribe to binding changes on this menu's persistent store.

        Public hook for the binding editor (tentacle's settings panel): it must
        listen on — and write to — the SAME host-namespaced store the menu reads
        (see :meth:`_binding_store_key`), or its combos desync from the live menu.
        Routing through ``bindings`` / this hook keeps that storage key an
        internal detail rather than something every editor reimplements.
        """
        self._bindings_store.changed.connect(callback)

    def _build_bindings(self, _value=None):
        """Parse and organize the input bindings into a unified lookup dict.

        Args:
            _value: Ignored. Accepts callback arg from on_change.
        """
        if not isinstance(self.bindings, dict):
            self.logger.warning("Bindings not configured correctly or invalid.")
            self._bindings = {}
            self._activation_key = None
            self._activation_key_str = None
            return

        normalized, activation_key_str = MenuResolver.parse_binding_keys(self.bindings)
        self._bindings = normalized
        self._activation_key_str = activation_key_str

        if activation_key_str and hasattr(QtCore.Qt, activation_key_str):
            self._activation_key = self._to_int(getattr(QtCore.Qt, activation_key_str))
        else:
            self._activation_key = None

        self.logger.debug(
            f"Activation key: {self._activation_key_str} ({self._activation_key})"
        )
        self.logger.debug(f"All bindings: {self._bindings}")

        if self._activation_key is None:
            if not self._bindings and self._initial_bindings:
                self.logger.warning("No bindings found. reverting to default bindings.")
                self.bindings = self._initial_bindings
                return

            self.logger.warning(
                "No activation key found in bindings. Include Key_* in at least one binding."
            )

        # Keep the unified shortcut-editor register in step with the live bindings
        # (activation key + chord→menu targets). Cheap and bind=False, so no
        # QShortcut churn; guarded for a switchboard predating the API.
        self._register_shortcut_editor_bindings()

    def _dispose_activation_shortcut(self) -> None:
        """Dispose the live activation ``GlobalShortcut`` (if any) and clear it.
        Shared by re-install (:meth:`_install_activation_shortcut`) and
        :meth:`retire`."""
        if self._shortcut_instance is None:
            return
        try:
            self._shortcut_instance.dispose()
        except Exception:
            self.logger.debug(
                "disposing prior activation shortcut failed", exc_info=True
            )
        self._shortcut_instance = None

    def _install_activation_shortcut(self) -> None:
        """(Re)create the application-scoped GlobalShortcut that shows the menu on
        the current activation key.

        Disposes any prior instance first, so changing the activation key never
        leaves the old key live. Shared by construction and
        :meth:`set_activation_key`; a no-op without a host parent — or on a
        retired instance (a stale editor callback must not re-arm activation
        on an instance a newer MarkingMenu has replaced).
        """
        if self._retired:
            return
        parent = getattr(self, "_activation_parent", None)
        if parent is None:
            return
        # Re-derive the live key from the freshly-parsed activation key so a
        # set_activation_key change actually MOVES the shortcut — reading a
        # cached self.key_show would re-bind the old key (the shortcut would stay
        # on F12 after the user picked F11). Fall back to F12 when the bindings
        # carry no valid activation key.
        if not self._activation_key:
            self.logger.warning("No valid activation key found; defaulting to F12.")
        self.key_show = self._activation_key or QtCore.Qt.Key_F12
        self._dispose_activation_shortcut()
        self._shortcut_instance = GlobalShortcut(
            self.key_show, parent, context=QtCore.Qt.ApplicationShortcut
        )
        self._shortcut_instance.pressed.connect(self._on_activation_press)
        self._shortcut_instance.released.connect(self._on_activation_release)

    def set_activation_key(self, new_key: str) -> None:
        """Rebind the marking menu's activation key across every chord.

        The activation key (``key_show``) is the shared prefix of *every* binding
        key (``Key_F12|LeftButton`` …), so changing it is a cross-cutting rewrite,
        not a single edit: each chord's ``Key_*`` part is swapped, the set is
        re-persisted (rebuilding the resolver + re-registering the editor entries),
        and the live activation ``GlobalShortcut`` is re-installed on the new key.
        Centralized here so the Settings panel and the shortcut editor share one
        implementation — the single source of truth for "what shows the menu".

        Accepts a Qt key name (``"Key_F11"``) or a bare / NativeText key
        (``"F11"``, auto-prefixed). A no-op when empty, unchanged, or not a valid
        ``QtCore.Qt.Key_*`` — the menu must always keep a working activation key
        (an invalid one leaves ``_activation_key`` None and the menu un-triggerable).

        Also records the key as the USER's chosen one (:meth:`stored_activation_key`),
        so it outranks a host's shipped default at the next launch.
        """
        if not new_key:
            return
        new_part = new_key if str(new_key).startswith("Key_") else f"Key_{new_key}"
        if not hasattr(QtCore.Qt, new_part):
            self.logger.warning(
                f"Ignoring invalid activation key {new_key!r} (no QtCore.Qt.{new_part})."
            )
            return
        old_part = self._activation_key_str
        if new_part == old_part:
            return

        rebound = {}
        for chord_key, menu in self.bindings.items():
            parts = [new_part if p == old_part else p for p in chord_key.split("|")]
            rebound["|".join(parts)] = menu
        # Persist -> _bindings_store.changed -> _build_bindings (reparse + refresh
        # the register). Then move the live activation shortcut onto the new key.
        self.bindings = rebound
        # Record the choice as the USER's — the provenance :meth:`stored_activation_key`
        # reads at the next launch. Only rebind routes reach this method (construction
        # seeds the chord store directly), so a host's shipped default keeps applying
        # until the user actually chooses.
        self._user_key_store.set(new_part)
        self._install_activation_shortcut()

    def start_menu_names(self, short: bool = True) -> list:
        """Available ``#startmenu`` UI names, sorted.

        The set the host's "Menu Bindings" combos pick a target menu from.
        ``short=True`` strips the ``#startmenu`` tag ("cameras"); ``False`` keeps
        the registered filename ("cameras#startmenu"). Centralizes what the host's
        settings slot used to compute inline (``_get_startmenus``).
        """
        filenames = self.sb.registry.ui_registry.get("filename") or []
        names = sorted(f for f in filenames if "#startmenu" in f)
        return [n.replace("#startmenu", "") for n in names] if short else names

    # -- unified shortcut-editor register ("hotkey register" integration) ---

    def _activation_key_display(self) -> str:
        """Current activation key as an editor / NativeText string ("F12")."""
        return (self._activation_key_str or "Key_F12").replace("Key_", "")

    def _default_activation_key_str(self) -> str:
        """The *default* activation key ("F12") from the construction bindings —
        the editor's reset/default target for the activation-key entry."""
        for chord_key in self.default_bindings:
            for part in str(chord_key).split("|"):
                if part.startswith("Key_"):
                    return part.replace("Key_", "")
        return "F12"

    def _chord_key_for(self, buttons) -> str:
        """The normalized binding key for the current activation key + *buttons*."""
        return "|".join(sorted([self._activation_key_str or "Key_F12", *buttons]))

    def _route_display(self, buttons) -> str:
        """Human chord for a route, e.g. ``"F12 + Left"`` — the read-only trigger
        shown in the editor's Shortcut column (a gesture is still a trigger)."""
        key_disp = self._activation_key_display()
        if not buttons:
            return key_disp
        btns = " + ".join(self._BUTTON_LABELS.get(b, b) for b in buttons)
        return f"{key_disp} + {btns}"

    def get_route_target(self, buttons=()) -> str:
        """Full target menu (…#startmenu) bound to the activation key + *buttons*
        gesture, or "" when unbound.

        ``buttons`` is a sequence of Qt button-flag names (``("LeftButton",)``,
        ``("LeftButton", "RightButton")``); ``()`` = the key-only default.
        Key-agnostic — resolved against the *current* activation key, so it stays
        correct after :meth:`set_activation_key`. This is why the host's Menu
        Bindings combos bind by gesture rather than a captured key string.
        """
        return self.bindings.get(self._chord_key_for(buttons), "") or ""

    def set_route_target(self, buttons, menu: str) -> None:
        """Bind the activation key + *buttons* gesture to *menu* (a …#startmenu UI
        name). Persists via the host-namespaced store (auto rebuild + notify)."""
        bindings = dict(self.bindings)
        bindings[self._chord_key_for(buttons)] = menu
        self.bindings = bindings

    def _route_target(self, buttons) -> str:
        """Short (tag-stripped) target menu for a route, or "" when unset."""
        return self.get_route_target(buttons).replace("#startmenu", "")

    def _register_shortcut_editor_bindings(self) -> None:
        """Surface the marking-menu bindings in the unified shortcut editor.

        Registers the activation key as a **visible, editable** external binding
        (its edit routes back through :meth:`set_activation_key`), and each
        chord→menu route as a **hidden, read-only** entry (edited via the host's
        "Menu Bindings" combos — a routing table isn't a key trigger). All are
        ``bind=False``: the register creates no ``QShortcut``; the marking menu's
        own activation ``GlobalShortcut`` owns the real key (a second one would
        collide — the ambiguous-overload failure). Re-run on every binding change
        so shown values/targets stay live. No-op without an activation key, or on a
        switchboard predating the external-binding API (older uitk / a test double).
        """
        sb = getattr(self, "sb", None)
        if (
            sb is None
            or not hasattr(sb, "register_command")
            or not self._activation_key_str
        ):
            return
        try:
            sb.register_command(
                "marking_menu_show",
                label="Show Marking Menu",
                doc="Hold to open the marking menu.",
                sequence=self._default_activation_key_str(),
                scope="application",
                bind=False,
                clearable=False,  # set_activation_key("") no-ops — the menu must
                # always keep a working activation key, so don't offer a clear.
                value_getter=self._activation_key_display,
                on_rebind=lambda seq, _scope: self.set_activation_key(seq),
            )
            for gesture, buttons in self._ROUTE_GESTURES:
                target = self._route_target(buttons)
                gesture_label = " + ".join(
                    self._BUTTON_LABELS.get(b, b) for b in buttons
                )
                chord = self._route_display(buttons)
                sb.register_command(
                    f"marking_menu_route_{gesture}",
                    # The action names WHAT the gesture opens (the target menu) —
                    # not the mouse button; the chord itself is in the Shortcut
                    # column. A fuller description rides the hover tooltip.
                    label=(
                        f"Marking Menu: {target.title()}"
                        if target
                        else f"Marking Menu ({gesture_label}) — unbound"
                    ),
                    doc=(
                        f"Opens the {target} menu on {chord} — set targets in "
                        "Settings ▸ Menu Bindings."
                        if target
                        else f"The {gesture_label} gesture is unbound."
                    ),
                    sequence=chord,  # default == current, so it isn't flagged "modified"
                    scope="application",
                    bind=False,
                    hidden=True,
                    editable=False,
                    value_getter=(lambda b=buttons: self._route_display(b)),
                )
        except TypeError:
            # register_command predates the external-binding kwargs — the Settings
            # combos remain the sole binding editor.
            self.logger.debug(
                "register_command lacks external-binding support; marking-menu "
                "bindings not surfaced in the editor.",
                exc_info=True,
            )
