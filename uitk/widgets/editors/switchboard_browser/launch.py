# !/usr/bin/python
# coding=utf-8
"""How the browser launches an entry: the options, the window persistence, the handler calls."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

from qtpy import QtWidgets


# ── Launch options (per-launch, not persisted per-UI) ─────────────────────────
#
# Defaults: frameless + dark theme so a browser-launched window matches
# the rest of the toolset out of the box.

# Window persistence modes — how a window behaves once open. "sticky" and
# "transient" map to the UiHandler header button sets: "sticky" -> hide button
# (stays open), "transient" -> pin button (auto-hides when you leave the marking
# menu, user-pinnable). "context" is the default: no user choice, so each window
# keeps its own default (``UiHandler.default_persistence``). The vocabulary is
# the handler's — it owns resolution and persistence; the browser is its front
# end. The resolved value handed to launch() is "sticky"/"transient", or None
# for "context" (let the handler resolve).
PERSISTENCE_STICKY = "sticky"
PERSISTENCE_TRANSIENT = "transient"
PERSISTENCE_CONTEXT = "context"
PERSISTENCE_DEFAULT = PERSISTENCE_CONTEXT
# Ordered (value, label) for the global combo and the per-entry submenu.
PERSISTENCE_CHOICES = (
    (PERSISTENCE_CONTEXT, "Default (context)"),
    (PERSISTENCE_STICKY, "Stay open (sticky)"),
    (PERSISTENCE_TRANSIENT, "Auto-hide (transient)"),
)


@dataclass
class LaunchOptions:
    frameless: bool = True
    translucent: bool = True
    restore_geometry: bool = True
    on_top: bool = True
    theme: str = "dark"
    # Resolved value passed to the handler: "sticky"/"transient", or None to
    # keep the launch context's default chrome.
    persistence: Optional[str] = None


class _LaunchMixin:
    """Launching an entry through its handler, with the browser's options."""

    def launch_options(self) -> LaunchOptions:
        return LaunchOptions(
            frameless=self._cb_frameless.isChecked(),
            translucent=self._cb_translucent.isChecked(),
            restore_geometry=self._cb_restore.isChecked(),
            on_top=self._cb_on_top.isChecked(),
            theme=self._cmb_theme.currentText(),
            persistence=self._resolve_persistence(None),
        )

    # ── Pin-button click mode (handler-owned preference) ─────────────────────

    def _ui_handler(self):
        """The Switchboard's UI handler (the ``"ui"`` slot), or None.

        Every app registers its UiHandler subclass under that name (tentacle
        passes ``handlers={"ui": MayaUiHandler}``; a bare Switchboard
        auto-registers the base class), so it's the stable way to reach the
        owner of window chrome without a handler-typed import.
        """
        return getattr(getattr(self.sb, "handlers", None), "ui", None)

    def _pin_click_hides(self) -> bool:
        """Whether a pin-button click currently dismisses the window."""
        return bool(getattr(self._ui_handler(), "pin_click_hides", True))

    def _on_pin_click_hides_toggled(self, checked: bool) -> None:
        """Persist + live-apply the pin-click mode via the UI handler."""
        handler = self._ui_handler()
        if handler is None:
            return
        try:
            handler.pin_click_hides = bool(checked)
        except AttributeError:  # handler predates the preference
            pass

    def _pin_on_tap(self) -> bool:
        """Whether tapping the activation key currently pins a window open."""
        return bool(getattr(self._ui_handler(), "pin_on_tap", False))

    def _on_pin_on_tap_toggled(self, checked: bool) -> None:
        """Persist + live-apply the tap-to-pin behavior via the UI handler."""
        handler = self._ui_handler()
        if handler is None:
            return
        try:
            handler.pin_on_tap = bool(checked)
        except AttributeError:  # handler predates the preference
            pass

    # ── Window persistence (context/sticky/transient) resolution ─────────────

    @staticmethod
    def _persistence_label(value: str) -> str:
        """Combo label for a stored persistence value (falls back to Default)."""
        return dict(PERSISTENCE_CHOICES).get(value, PERSISTENCE_CHOICES[0][1])

    @staticmethod
    def _persistence_value(label: str) -> str:
        """Stored persistence value for a combo label (falls back to context)."""
        for value, lbl in PERSISTENCE_CHOICES:
            if lbl == label:
                return value
        return PERSISTENCE_CONTEXT

    def _global_persistence(self) -> str:
        """The global default persistence mode ("context"/"sticky"/"transient").

        Handler-owned, like ``pin_click_hides`` — the handler styles every
        window whatever opened it, so a browser-local copy would (and did)
        reach browser-launched windows only.
        """
        value = getattr(self._ui_handler(), "window_persistence", PERSISTENCE_DEFAULT)
        return (
            value
            if value in (PERSISTENCE_CONTEXT, PERSISTENCE_STICKY, PERSISTENCE_TRANSIENT)
            else PERSISTENCE_DEFAULT
        )

    def _set_global_persistence(self, mode: str) -> None:
        """Persist + live-apply the global default via the UI handler."""
        handler = self._ui_handler()
        if handler is None:
            return
        try:
            handler.window_persistence = mode
        except AttributeError:  # handler predates the preference
            pass

    def _entry_persistence_override(self, name: str) -> Optional[str]:
        """The stored per-entry override, or None if the entry follows the default."""
        handler = self._ui_handler()
        getter = getattr(handler, "persistence_override", None)
        return getter(name) if callable(getter) else None

    def _effective_default(self, name: str) -> str:
        """What "Default" currently resolves to for *name* — so the row menu can
        say ``Default (sticky)`` instead of the opaque ``Default (context)``.

        The global default when one is set; otherwise the window's OWN default
        (``UiHandler.default_persistence``), which needs the loaded widget to
        read its tags — an unlisted/unloaded entry honestly reports "context".
        """
        global_mode = self._global_persistence()
        if global_mode != PERSISTENCE_CONTEXT:
            return global_mode
        hook = getattr(self._ui_handler(), "default_persistence", None)
        loaded = getattr(self.sb, "loaded_ui", None)
        ui = loaded.peek(name) if loaded is not None else None
        if ui is not None and callable(hook):
            try:
                return hook(ui)
            except Exception:
                pass
        return global_mode

    def _resolve_persistence(self, name: Optional[str]) -> Optional[str]:
        """Effective persistence handed to the handler: per-entry override, else
        the global default. Returns ``None`` for "Default (context)" so the launch
        keeps its context chrome. ``name=None`` resolves the global only."""
        if name is not None:
            override = self._entry_persistence_override(name)
            if override is not None:
                return override
        global_mode = self._global_persistence()
        return global_mode if global_mode != PERSISTENCE_CONTEXT else None

    def _set_entry_persistence(self, name: str, mode: Optional[str]) -> None:
        """Set (``"sticky"``/``"transient"``) or clear (``None`` -> follow default)
        a per-entry override. The handler re-chromes the window if it's open."""
        handler = self._ui_handler()
        setter = getattr(handler, "set_persistence_override", None)
        if callable(setter):
            setter(name, mode)

    def _migrate_browser_persistence(self) -> None:
        """One-shot: hand pre-existing browser-local persistence keys to the handler.

        These keys used to live in the ``ui_browser`` settings branch, where
        they only ever reached browser-launched windows. Copy them once (never
        clobbering a value the handler already has) and drop the originals, so
        a user's stored choices survive the move to handler ownership.
        """
        handler = self._ui_handler()
        if handler is None or not hasattr(handler, "set_persistence_override"):
            return
        legacy_global = self._settings.value("opt_persistence", None)
        if legacy_global in (PERSISTENCE_STICKY, PERSISTENCE_TRANSIENT):
            if handler.window_persistence == PERSISTENCE_CONTEXT:
                handler.window_persistence = legacy_global
        self._settings.remove("opt_persistence")

        prefix = "persistence_override/"
        for key in [k for k in self._settings.keys() if k.startswith(prefix)]:
            mode = self._settings.value(key, None)
            # The legacy keys were host-namespaced with the same SSoT the
            # handler uses, so the stored leaf IS the handler's leaf: write the
            # raw key through rather than re-namespacing an already-namespaced
            # name (``mirror_maya`` -> ``mirror_maya_maya``).
            if mode in (PERSISTENCE_STICKY, PERSISTENCE_TRANSIENT):
                if handler.config.value(key, None) is None:
                    handler.config.setValue(key, mode)
            self._settings.remove(key)

    def _close_ui(self, name: str) -> None:
        """Dismiss the entry via its owning handler.

        The handler decides what "close" means — hide a window, terminate
        a subprocess, etc. Browser stays kind-agnostic.
        """
        entry = self._model.entry_for_name(name)
        if entry is None:
            return
        try:
            entry.handler.close(name)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Close failed", f"{name}: {e}")
            return
        self._model.refresh_after_launch(name)

    def _launch_kwargs(self, name: str) -> dict:
        """The launch options this browser hands *name*'s handler.

        Shared by :meth:`_launch` and :meth:`_launch_code`, so a copied
        snippet opens the window exactly as the Launch button would.
        """
        # Per-entry persistence override wins over the global default in opts.
        return {
            **asdict(self.launch_options()),
            "persistence": self._resolve_persistence(name),
        }

    def _launch(self, name: str) -> None:
        """Launch the entry through its owning handler.

        Browser passes the current launch options (frameless/translucent/
        restore_geometry/on_top/theme) as **kwargs; handlers that don't
        care about UI styling discard the unknown keys.
        """
        entry = self._model.entry_for_name(name)
        if entry is None:
            return
        try:
            entry.handler.launch(name, **self._launch_kwargs(name))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Launch failed", f"{name}: {e}")
            return
        self._model.refresh_after_launch(name)

    def _launch_code(self, name: str) -> Optional[str]:
        """*name*'s standalone launch snippet, or None.

        Rendered by the handler's optional ``launch_code`` from this
        browser's launch options. None when the handler offers none, can't
        spell one, or fails -- a broken handler must not break the menu.
        """
        entry = self._model.entry_for_name(name)
        render = getattr(entry.handler, "launch_code", None) if entry else None
        if not callable(render):
            return None
        try:
            return render(name, **self._launch_kwargs(name)) or None
        except Exception:
            self.sb.logger.warning(
                f"[SwitchboardBrowser] launch_code failed for {name!r}",
                exc_info=True,
            )
            return None

    def _copy_launch_code(self, name: str, code: str) -> None:
        """Put *code* on the clipboard and confirm in the footer."""
        QtWidgets.QApplication.clipboard().setText(code)
        self.footer.setStatusText(f"Copied launch code for {name}", "success")

    def _focus(self, name: str) -> None:
        """Raise a currently-visible entry through its handler's optional
        ``focus``. A handler without one (a subprocess app has no window in
        this process to raise) leaves Focus a no-op.
        """
        entry = self._model.entry_for_name(name)
        focus = getattr(entry.handler, "focus", None) if entry is not None else None
        if callable(focus):
            focus(name)
