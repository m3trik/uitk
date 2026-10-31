# !/usr/bin/python
# coding=utf-8
"""Provisioning for optional packages a panel needs importable in THIS session.

The in-process counterpart of :class:`uitk.handlers.ExternalAppHandler`'s
install-on-demand, which provisions *subprocess* apps. Same idea, harder
requirement: the result has to be importable **here**, in the interpreter that is
already running, so a panel whose engine lives in an optional distribution can
open and work without a restart.

A service object rather than methods on a slot class. The two halves of this one
policy used to live apart -- the subprocess half in ``ExternalAppHandler``, the
in-process half inlined into ``BridgeSlotsBase`` -- to the point that the latter
reached into the former for ``_pip_capable_python`` to stop them drifting. That
cross-import was the design asking for this module.

Everything host-facing is injected (:attr:`prompt`, :attr:`logger`,
:attr:`installer`), so nothing here knows about Qt, Switchboard, or a DCC.
"""

from __future__ import annotations

import importlib
import re
import sys
from typing import Callable, Optional, Tuple

import pythontk as ptk

__all__ = ["OptionalPackageManager"]


class _OptionalPackageManagerInternal(object):
    """Requirement-string reading for :class:`OptionalPackageManager`, over
    ``ptk.PackageRequirement`` -- the one reader of a requirement's range, which
    ``ExternalAppHandler`` checks a provider's range with too."""

    #: Where a PEP 508 requirement stops being the distribution name: the
    #: fallback for a spec the reader does not parse (a URL).
    _REQ_BOUNDARY = re.compile(r"[<>=!~;\[\s]")

    #: Specifiers that state an inclusive lower bound.
    _FLOOR_OPS = (">=", "~=", "==")

    @staticmethod
    def _requirement(spec: str) -> Optional["ptk.PackageRequirement"]:
        """*spec* parsed, or None when the reader does not read it (a URL)."""
        try:
            return ptk.PackageRequirement(spec)
        except ValueError:
            return None

    @staticmethod
    def version_tuple(text: str) -> Tuple[int, ...]:
        """``"0.0.8"`` -> ``(0, 0, 8)``; stops at the first non-numeric segment.

        A coarse key that never raises (``ptk.PackageRequirement.release``):
        ``"1.2.0rc1"`` -> ``(1, 2, 0)``. Range checks do not use it --
        :meth:`available` compares with ``PackageRequirement.contains``, which
        orders a pre-release below its release.
        """
        return ptk.PackageRequirement.release(text)

    @staticmethod
    def split_requirement(spec: str) -> Tuple[str, Optional[Tuple[int, ...]]]:
        """``"unitytk>=0.0.8"`` -> ``("unitytk", (0, 0, 8))``; a bare name -> floor None.

        One string carries both the pip requirement and the runtime range, so a
        caller can never let the two drift apart. Every specifier
        ``ptk.PackageRequirement`` reads is accepted; the floor is the highest
        inclusive lower bound among them (``>=``, ``~=``, ``==``), so
        ``"extapps>=0.8.0,<0.9"`` -> ``("extapps", (0, 8, 0))`` and a cap alone
        states none. A spec the reader does not parse (a URL) yields its name
        and no floor.
        """
        cls = _OptionalPackageManagerInternal
        requirement = cls._requirement(spec)
        if requirement is None:
            return cls._REQ_BOUNDARY.split(str(spec), 1)[0].strip(), None
        floors = [v for op, v in requirement.specifiers if op in cls._FLOOR_OPS]
        if not floors:
            return requirement.name, None
        floor = max(floors, key=ptk.PackageRequirement.version_key)
        return requirement.name, cls.version_tuple(floor)


class OptionalPackageManager(_OptionalPackageManagerInternal):
    """Probe for, and offer to install, an optional package.

    :meth:`available` is the silent probe every implicit code path uses;
    :meth:`ensure` is the interactive one and may ONLY be reached from an explicit
    user action (it shows a modal).
    """

    def __init__(
        self,
        prompt: Optional[Callable[..., str]] = None,
        logger=None,
        installer: Optional[Callable[[str], None]] = None,
    ):
        """
        Parameters:
            prompt: ``(message, *buttons) -> chosen_button``. Required by
                :meth:`ensure`; a manager built without one is probe-only.
            logger: Anything with ``info`` / ``error``. Note for slot callers:
                pass the *Switchboard's* logger, not the panel's -- a bridge slot
                gets its logger from ``self.bridge``, and the whole point of this
                service is that the bridge does not exist yet.
            installer: ``(spec) -> None``, overriding :meth:`default_install`.
                The seam a host with an unusual import path uses -- Blender's
                bundled interpreter keeps user-site OFF ``sys.path``, so a
                ``--user`` install there succeeds and stays unimportable.
        """
        self.prompt = prompt
        self.logger = logger
        self._installer = installer

    # ------------------------------------------------------------- probing
    @staticmethod
    def available(spec: str, import_name: str = None) -> bool:
        """Is *spec* importable in THIS interpreter, inside any version range? Silent.

        Never prompts, never installs, never raises -- the probe implicit code
        paths use. A panel whose engine lives in an optional distribution must be
        able to *open* (and say so in its log) without a dialog.

        Prefers a real import over :func:`importlib.util.find_spec`: find_spec
        answers "is there a module file", not "does it import", and it raises
        ValueError for an already-imported module whose ``__spec__`` is None.
        Importing is what the caller is about to do anyway, and a package that is
        present but broken must read as unavailable, not as available-then-
        exploding inside the caller.

        A bare repo/workspace folder on ``sys.path`` masquerades as an empty
        *namespace* package -- ``import unitytk`` "succeeds" against
        ``_scripts/unitytk/`` (the repo dir, which holds the real package one
        level down) and then every attribute access fails. A module with no
        ``__file__`` is exactly that case and reads as unavailable.

        A version range (``"unitytk>=0.0.8"``, ``"extapps>=0.8.0,<0.9"``) makes a
        package installed outside it read as unavailable too. That case is not
        hypothetical: a pyproject extra only constrains a fresh install, so a
        session already carrying the older release imports fine and then raises
        ``AttributeError`` on the API the caller came for. A package that
        declares no ``__version__`` cannot satisfy a range, and refusing is the
        safe direction -- the same rule as "present but broken reads as
        unavailable".
        """
        name, _floor = OptionalPackageManager.split_requirement(spec)
        module = import_name or name.replace("-", "_")
        try:
            mod = importlib.import_module(module)
        except Exception:  # noqa: BLE001 - any failure means "not usable here"
            return False
        if getattr(mod, "__file__", None) is None:
            return False
        requirement = OptionalPackageManager._requirement(spec)
        if requirement is None or not requirement.specifiers:
            return True
        return requirement.contains(getattr(mod, "__version__", None))

    # ---------------------------------------------------------- installing
    @staticmethod
    def pip_python() -> Optional[str]:
        """Interpreter to drive pip with, for an install this session must import.

        Single-sources the DCC-host substitution from
        :meth:`uitk.handlers.ExternalAppHandler._pip_capable_python` so the
        in-process and subprocess install paths can't drift -- and, critically,
        inherits its ``None`` for a host with no sibling rather than handing back
        the host binary, which would hang on the first pip call.
        """
        from uitk.handlers.external_app_handler import ExternalAppHandler

        return ExternalAppHandler._pip_capable_python(sys.executable)

    @staticmethod
    def default_install(spec: str) -> None:
        """``pip install --user`` *spec* against the running interpreter.

        Substitutes the sibling python when the host executable is a DCC that does
        not take ``-c`` (``maya.exe`` -> ``mayapy.exe``).

        Raises:
            RuntimeError: when the running interpreter is a DCC host with no
                sibling python. Driving pip through the host binary itself routes
                the install into its ``-c`` handler (MEL / a blocked Qt loop) and
                HANGS it, so refusing is the only safe answer.
        """
        import pythontk as ptk

        python = OptionalPackageManager.pip_python()
        if not python:
            raise RuntimeError(
                f"Cannot install {spec!r}: this session's interpreter "
                f"({sys.executable!r}) is a DCC host with no sibling python to "
                f"install through. Provision it into the host environment."
            )
        # ``--user`` is refused inside a venv ("user site-packages are not
        # visible"): a venv interpreter installs into the venv itself.
        in_venv = python == sys.executable and sys.prefix != sys.base_prefix
        user = "" if in_venv else "--user "
        ptk.PackageManager(python_path=python).pip(f"install {user}{spec}")

    def install(self, spec: str) -> None:
        """Install *spec* via the injected installer, else :meth:`default_install`."""
        (self._installer or OptionalPackageManager.default_install)(spec)

    # ------------------------------------------------------------ ensuring
    def ensure(
        self, spec: str, import_name: str = None, *, feature: str = None
    ) -> bool:
        """Make *spec* importable, offering to install it on demand.

        **Explicit user actions only.** This shows a modal, so it must never run
        from a panel's ``__init__`` or anything reached while it is constructing:
        a modal raised from a constructor is parented to a window that does not
        exist yet, and if construction then fails the box is orphaned with no way
        to dismiss it. Implicit paths use :meth:`available` and report through the
        log instead.

        A *spec* carrying a version range also catches a package installed
        outside it, which mere importability let through. That case offers an
        *update* and then returns **False with a restart notice**: a package
        already in ``sys.modules`` cannot be swapped in place, so the freshly
        written files are not what this session would call. The question and
        the notice are the handler's (``ExternalAppHandler`` asks the same
        before updating an app outside its range), so the two cannot drift.

        Returns:
            bool: True only when the package is usable **in this session** inside
            any range -- an upgrade written to disk returns False.
        """
        from uitk.handlers.external_app_handler import _InstallOffer

        if self.available(spec, import_name):
            return True
        if self.prompt is None:
            self._log("info", f"{spec} is unavailable and no prompt is configured.")
            return False

        name, _floor = self.split_requirement(spec)
        requirement = self._requirement(spec)
        # Present-but-outside is a different sentence from absent -- and the only
        # one of the two the user can't act on by reading "install it".
        stale = bool(requirement is not None and requirement.specifiers) and (
            self.available(name, import_name)
        )
        installed = None
        if stale:
            module = sys.modules.get(import_name or name.replace("-", "_"))
            installed = str(getattr(module, "__version__", "") or "")
        label = feature or "This panel"
        verb = "update" if stale else "install"

        if not _InstallOffer.ask(self.prompt, spec, label=label, installed=installed):
            self._log("info", f"{spec} {verb} declined; {label} is unavailable.")
            return False

        try:
            self.install(spec)
        except Exception as error:  # noqa: BLE001 - reported, never raised at the UI
            self._log("error", f"Failed to {verb} {spec}: {error}")

        # Trust the import, not pip's exit code: a --target/--user install can
        # report a non-zero dependency-resolver error for an UNRELATED conflict in
        # the base environment while the requested wheel installed fine.
        importlib.invalidate_caches()

        if stale:
            # An UPGRADE cannot take effect in this process: the old package is
            # already in ``sys.modules``, and reloading it does NOT refresh the
            # submodules its ``__init__`` re-imports from cache -- the caller would
            # still get the old class. Report the on-disk result and stop; the
            # probe below would read the cached ``__version__`` anyway and
            # mis-report the upgrade as a failed install.
            _InstallOffer.restart(self.prompt, name)
            self._log("info", f"Updated {spec}; restart required.")
            return False

        if self.available(spec, import_name):
            self._log("info", f"Installed {spec}.")
            return True

        self.prompt(
            f"<b>Could not install {spec}.</b><br><br>"
            f"Install it manually, then reopen {label}.",
            "Ok",
        )
        return False

    def _log(self, level: str, message: str) -> None:
        """Log *message* when a logger was injected; stay silent otherwise."""
        if self.logger is not None:
            getattr(self.logger, level)(message)
