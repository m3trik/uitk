# !/usr/bin/python
# coding=utf-8
"""Mixin that falls back to the uitk package namespace for unknown attributes.

Makes the Switchboard the single uitk entry point for anything that already holds
one — notably slot classes, which are handed ``self.sb`` for free::

    self.sb.IconManager.set_label_icon(widget, "folder_filled")
    store = self.sb.RecentValuesStore(settings_key="workspace_recent_projects")

instead of each consumer importing uitk itself and hard-coding which submodule a
class currently lives in. Nothing is enumerated here, so every public uitk symbol
is reachable the moment it is registered in uitk's ``DEFAULT_INCLUDE`` — no
per-symbol upkeep, and no reason to keep adding one-off accessor properties.

The rest of uitk reaches consumers through the Switchboard's *children* rather
than this fallback: ``self.ui`` is the MainWindow, ``self.ui.<widget>`` its
registered widgets, and a widget's own API is preferred over a class import when
it has one (``self.ui.footer.status_controller(...)`` over ``FooterStatusController``).

Scope and safety
----------------
``__getattr__`` runs only after normal lookup has already failed, so this can
never shadow a Switchboard attribute, property or method — including the
high-traffic shortcuts ``sb.style`` (see :mod:`~uitk.switchboard.style`),
``sb.registered_widgets`` and ``sb.registered_icons``, which resolve normally and
never reach here.

Two kinds of name are refused outright:

* anything starting with ``_`` — Qt, ``copy`` and ``pickle`` probe dunders
  (``__deepcopy__``, ``__getstate__``, ``__setstate__``, ...) on every QObject,
  and those must keep raising ``AttributeError`` cheaply instead of round-tripping
  through a package resolver; and
* anything outside ``uitk.__all__`` — reported against the Switchboard, not uitk,
  so a typo on ``sb.`` still reads as a typo on ``sb.``.

``__all__`` is the gate rather than a bare ``getattr(uitk, name)``, for three
reasons — a plain getattr is wrong on all of them, and measurably so: it publishes
**18 snake_case names**, straight into the space the collision invariant below
reserves for the Switchboard.

1. **It would publish uitk's private module state and every submodule.**
   ``ModuleAttributeResolver.resolve`` consults the package ``__dict__`` first and
   its submodule list last, so ``getattr`` also reaches ``DEFAULT_INCLUDE``,
   ``bootstrap_package``, ``CLASS_TO_MODULE``, the resolver's own ``configure`` /
   ``export_all`` helpers — and the ``uitk.widgets`` / ``uitk.themes`` /
   ``uitk.handlers`` **modules**. That last one is the sharp edge: ``handlers`` is
   the most-probed Switchboard attribute in the ecosystem
   (``getattr(self.sb, "handlers", None)`` in ``base_handler``, ``ui_handler``,
   ``switchboard_browser``, tentacle's ``_slots``), and the fallback would answer it
   with the *module* instead of ``None`` for any Switchboard whose own ``handlers``
   is not yet set — a duck-typed stand-in, or one still inside ``__init__``.
2. **It would mask real resolution failures.** uitk reports a symbol whose module
   fails to import as ``AttributeError("Failed to resolve ... Original Error: ...")``
   with the ``ImportError`` as ``__cause__``. Swallowing that to report "not a public
   uitk symbol" would send a reader hunting for a missing export instead of the
   broken import. A registered name's error now propagates untouched.
3. **A miss stays cheap** — one membership test, with no resolver round-trip and no
   discarded exception, on the path every failed ``getattr(sb, ...)`` probe takes.

Collision-free by construction once gated: every name in ``uitk.__all__`` is a
CamelCase class, while the Switchboard's own API — and all ~26
``getattr(sb, "...", None)`` probes across uitk and the DCC packages — are
snake_case. ``test_switchboard_namespace.py`` pins this by probing what is *actually
reachable* rather than by reading ``__all__``; reading ``__all__`` is exactly what let
the leak above past an earlier version of that file.
"""


class SwitchboardNamespaceMixin:
    """Resolve otherwise-unknown Switchboard attributes against the ``uitk`` namespace."""

    def __getattr__(self, name):
        # Private/dunder probes never reach uitk — see the module docstring.
        if name.startswith("_"):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )
        import uitk

        if name not in (uitk.__all__ or ()):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}' "
                f"(and '{name}' is not a public uitk symbol)"
            )
        # Registered: any failure here is a real resolution error (a broken import
        # behind the symbol), and must keep its own message and __cause__.
        return getattr(uitk, name)
