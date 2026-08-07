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
from typing import Callable, List, Optional, Tuple

__all__ = ["OptionalPackageManager"]


class _OptionalPackageManagerInternal(object):
    """Requirement-string parsing for :class:`OptionalPackageManager`."""

    #: Where a PEP 508 requirement stops being the distribution name.
    _REQ_BOUNDARY = re.compile(r"[<>=!~;\[\s]")

    @staticmethod
    def version_tuple(text: str) -> Tuple[int, ...]:
        """``"0.0.8"`` -> ``(0, 0, 8)``; stops at the first non-numeric segment.

        Deliberately not a full PEP 440 parser: the ecosystem versions are plain
        ``X.Y.Z``, and truncating at a suffix (``1.2.0rc1`` -> ``(1, 2)``) errs
        toward "older", which is the safe direction for a floor check.
        """
        parts: List[int] = []
        for chunk in str(text).split("."):
            digits = ""
            for ch in chunk:
                if not ch.isdigit():
                    break
                digits += ch
            if not digits:
                break
            parts.append(int(digits))
        return tuple(parts)

    @staticmethod
    def split_requirement(spec: str) -> Tuple[str, Optional[Tuple[int, ...]]]:
        """``"unitytk>=0.0.8"`` -> ``("unitytk", (0, 0, 8))``; a bare name -> floor None.

        One string carries both the pip requirement and the runtime floor, so a
        caller can never let the two drift apart. Only ``>=`` is read -- that is
        the constraint an optional-package floor is ever expressed with here.
        """
        cls = _OptionalPackageManagerInternal
        name = cls._REQ_BOUNDARY.split(spec, 1)[0].strip()
        match = re.search(r">=\s*([0-9][0-9A-Za-z.]*)", spec)
        return name, (cls.version_tuple(match.group(1)) if match else None)


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
        """Is *spec* importable in THIS interpreter, at or above any floor? Silent.

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

        A version floor (``"unitytk>=0.0.8"``) makes an installed-but-TOO-OLD
        package read as unavailable too. That case is not hypothetical: a
        pyproject extra only constrains a fresh install, so a session already
        carrying the older release imports fine and then raises ``AttributeError``
        on the API the caller came for. A package that declares no ``__version__``
        cannot clear a floor, and refusing is the safe direction -- the same rule
        as "present but broken reads as unavailable".
        """
        name, floor = OptionalPackageManager.split_requirement(spec)
        module = import_name or name.replace("-", "_")
        try:
            mod = importlib.import_module(module)
        except Exception:  # noqa: BLE001 - any failure means "not usable here"
            return False
        if getattr(mod, "__file__", None) is None:
            return False
        if floor is None:
            return True
        return (
            OptionalPackageManager.version_tuple(getattr(mod, "__version__", ""))
            >= floor
        )

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
        ptk.PackageManager(python_path=python).pip(f"install --user {spec}")

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

        A *spec* carrying a version floor also catches an installed-but-too-old
        package, which mere importability let through. That case offers an
        *update* and then returns **False with a restart notice**: a package
        already in ``sys.modules`` cannot be swapped in place, so the freshly
        written files are not what this session would call.

        Returns:
            bool: True only when the package is usable **in this session** at or
            above any floor -- an upgrade written to disk returns False.
        """
        if self.available(spec, import_name):
            return True
        if self.prompt is None:
            self._log("info", f"{spec} is unavailable and no prompt is configured.")
            return False

        name, floor = self.split_requirement(spec)
        # Present-but-too-old is a different sentence from absent -- and the only
        # one of the two the user can't act on by reading "install it".
        stale = floor is not None and self.available(name, import_name)
        label = feature or "This panel"
        verb = "update" if stale else "install"

        answer = self.prompt(
            f"<b>{label} needs the optional <i>{spec}</i> package"
            f"{' (the installed one is older)' if stale else ''}.</b><br><br>"
            f"{verb.capitalize()} it now?",
            "Yes",
            "No",
        )
        if answer != "Yes":
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
            self.prompt(
                f"<b>Updated {name} on disk.</b><br><br>"
                f"Restart this session to pick it up — a package already "
                f"imported cannot be swapped in place.",
                "Ok",
            )
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
