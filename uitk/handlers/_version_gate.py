# !/usr/bin/python
# coding=utf-8
"""The optional version ranges of :class:`~uitk.handlers.external_app_handler.ExternalAppHandler`.

An app or a provider may state a version range in its install spec
(``"extapps>=0.9,<0.10"``). :class:`_VersionGate` answers which range applies,
reads the version an interpreter would import, and holds a launch until that
version is inside the range -- asking, then updating through pip, when it is
not. It holds the handler and reads its providers, prompt and interpreter
helpers through it at call time, so a subclass's or a test's override of
those is the one in effect.
"""

import importlib
import subprocess
import sys
from typing import Dict, Optional, Tuple

import pythontk as ptk


class _VersionGate:
    """Version ranges for one :class:`ExternalAppHandler` (module docstring).

    Another interpreter's version is read with a ``python -c`` query, a fork
    with a 15 s timeout; each answer is kept per (interpreter, distribution,
    package) for the session, until the handler installs or updates something
    (:meth:`forget`).
    """

    QUERY_TIMEOUT = 15  # seconds a version query in another interpreter may take

    def __init__(self, handler) -> None:
        self._handler = handler
        # (python, dist, top) -> what that interpreter answered.
        self._queried: Dict[Tuple[str, str, str], Optional[str]] = {}

    # ------------------------------------------------------------- ranges
    @staticmethod
    def ranged(spec: Optional[str]) -> Optional["ptk.PackageRequirement"]:
        """*spec* as a requirement when it states a version range, else None.

        None for a bare name and for anything the reader does not parse (a VCS
        or file URL): those keep the unversioned behaviour.
        """
        if not spec:
            return None
        try:
            requirement = ptk.PackageRequirement(spec)
        except ValueError:
            return None
        return requirement if requirement.specifiers else None

    def range_for(
        self, dist: Optional[str], top: Optional[str]
    ) -> Optional["ptk.PackageRequirement"]:
        """The range a registered provider states for distribution *dist*, or
        for the provider whose probe module is the package *top*; else None."""
        handler = self._handler
        wanted = handler._normalize_dist_name(dist) if dist else None
        for spec, prov in handler._providers.items():
            requirement = self.ranged(spec)
            if requirement is None:
                continue
            if (
                wanted and handler._normalize_dist_name(requirement.name) == wanted
            ) or (top and prov.get("probe_module") == top):
                return requirement
        return None

    def requirement(
        self, spec: Optional[str], top: str
    ) -> Optional["ptk.PackageRequirement"]:
        """The range an install *spec* for package *top* must satisfy; None
        means no check at all.

        The spec's own range when it states one, else a provider's: discovery
        registers an app under its bare distribution name, so the range a host
        gave ``add_provider`` is found by that name (or by the package *top*,
        the provider's probe module).
        """
        dist = self._handler._base_pkg_name(spec) if spec else None
        return self.ranged(spec) or self.range_for(dist, top)

    # ----------------------------------------------------------- versions
    def installed_version(
        self, dist: str, module: str, python: str, in_process: bool = False
    ) -> Optional[str]:
        """The version of *dist* that *module* would import under *python*.

        In this interpreter, nothing is imported to answer: for an *in_process*
        launch, a loaded package's ``__version__`` (what is running -- a
        subprocess launch starts a fresh interpreter, where it is not); a
        source checkout's own ``__version__`` (an editable install's metadata is
        as old as the install); the installed metadata; failing that, the
        package's ``__version__`` read from its source. Another interpreter is
        asked with a short ``-c`` query (:meth:`query_version`).

        Returns:
            The version; ``""`` when the package is present but declares none
            readable; None when it is not there at all.
        """
        top = module.split(".")[0]
        if python != sys.executable:
            return self.query_version(dist, top, python)
        loaded = sys.modules.get(top) if in_process else None
        version = getattr(loaded, "__version__", None) if loaded is not None else None
        if version:
            return str(version)
        if self.checkout_of(dist, module) is None:
            version = ptk.PackageManager.metadata_version(dist)
            if version:
                return version
        return self.source_version(top)

    def query_version(self, dist: str, top: str, python: str) -> Optional[str]:
        """Ask *python* for *dist*'s version, once a session (until :meth:`forget`).

        The ``-c`` probe style of ``ExternalAppHandler._is_importable``, through
        a DCC host's companion python (a host binary's ``-c`` is not Python):
        the package's ``__version__``, else its metadata. None when it is
        absent or the query fails.
        """
        key = (python, dist, top)
        if key not in self._queried:
            self._queried[key] = self._ask(dist, top, python)
        return self._queried[key]

    def forget(self) -> None:
        """Drop every kept answer: an install or update may have changed one."""
        self._queried.clear()
        importlib.invalidate_caches()

    def _ask(self, dist: str, top: str, python: str) -> Optional[str]:
        python = self._handler._pip_capable_python(python)
        if not python or not top.isidentifier():
            return None
        script = (
            "import sys\n"
            "version = mod = None\n"
            "try:\n"
            f"    import {top} as mod\n"
            "    version = getattr(mod, '__version__', None)\n"
            "except Exception:\n"
            "    pass\n"
            "if not version:\n"
            "    try:\n"
            "        from importlib.metadata import version as read\n"
            f"        version = read({dist!r})\n"
            "    except Exception:\n"
            "        if mod is None:\n"
            "            sys.exit(3)\n"
            "print(version or '')\n"
        )
        try:
            result = subprocess.run(
                [python, "-c", script],
                capture_output=True,
                text=True,
                timeout=self.QUERY_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        lines = (result.stdout or "").strip().splitlines()
        return lines[-1].strip() if lines else ""

    def source_version(self, top: str) -> Optional[str]:
        """Package *top*'s literal ``__version__``, read from its source unimported.

        None when the package cannot be found -- or is only a namespace (a
        bare repo folder on the path, which imports and holds nothing);
        ``""`` when it is found but its ``__version__`` is not a plain string
        literal.
        """
        import ast

        try:
            spec = self._handler._find_spec_unimported(top)
        except Exception:  # noqa: BLE001 -- unfindable reads as absent
            return None
        if spec is None or getattr(spec, "origin", None) in (None, "namespace"):
            return None
        try:
            source = spec.loader.get_source(top)
            tree = ast.parse(source or "")
        except Exception:  # noqa: BLE001 -- unreadable source declares nothing
            return ""
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets
            ):
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value
                return ""
        return ""

    def checkout_of(self, dist: str, module: str) -> Optional[str]:
        """The ``pyproject.toml`` of the source checkout *module* resolves to, or None.

        The file the handler's source discovery reads apps from: a checkout's
        version is pip's to replace only by replacing the checkout.
        """
        handler = self._handler
        loads = handler._toml_loader()
        if loads is None:
            return None
        path, _data = handler._source_project(module.split(".")[0], dist, loads)
        return path

    # --------------------------------------------------------------- gate
    def gate(
        self,
        requirement: "ptk.PackageRequirement",
        module: str,
        python: str,
        *,
        label: str,
        in_process: bool,
    ) -> None:
        """Return only when what *module* imports satisfies *requirement*.

        Absent (None from :meth:`installed_version`) passes: the install
        path then installs inside the range. Present outside it, the user is
        asked (the handler's ``prompt``); "Yes" updates through pip with the
        range, and the launch goes on once the new version reads inside it.

        Raises:
            RuntimeError: Declined (naming the installed version and the
                range), no prompt to ask with, a source checkout outside the
                range (pip cannot replace it), a DCC host with no pip-capable
                python, a failed update, an update an imported package of an
                in-process app picks up only after a restart (said in a
                notice first), or a version still outside after the update.
        """
        from uitk.handlers.external_app_handler import _InstallOffer

        handler = self._handler
        installed = self.installed_version(requirement.name, module, python, in_process)
        if installed is None or requirement.contains(installed):
            return
        shown = installed or "a version that declares none"
        found = f"{requirement.name} {shown}"
        checkout = (
            self.checkout_of(requirement.name, module)
            if (python == sys.executable)
            else None
        )
        if checkout:
            raise RuntimeError(
                f"'{label}' was not launched: {found} is a source checkout "
                f"({checkout}) outside the {requirement} this host requires. "
                f"Update that checkout; pip cannot replace it."
            )
        pip_py = handler._pip_capable_python(python)
        if not pip_py:
            raise RuntimeError(
                f"'{label}' was not launched: {found} is installed, outside the "
                f"{requirement} this host requires, and {python!r} is a DCC host "
                f"with no sibling python to update it through."
            )
        prompt = handler.prompt or getattr(handler.sb, "message_box", None)
        if prompt is None or not _InstallOffer.ask(
            prompt, str(requirement), label=label, installed=installed
        ):
            raise RuntimeError(
                f"'{label}' was not launched: {found} is installed, and this "
                f"host requires {requirement}. Update it to launch."
            )
        handler.logger.info(f"Updating {requirement} into {pip_py} (was {shown})")
        try:
            ptk.PackageManager(python_path=pip_py).update(str(requirement))
        except Exception as e:
            raise RuntimeError(
                f"Failed to update {requirement} into {pip_py}: {e}"
            ) from e
        finally:
            self.forget()
        top = module.split(".")[0]
        if in_process and top in sys.modules:
            _InstallOffer.restart(prompt, requirement.name)
            raise RuntimeError(
                f"Updated {requirement} on disk; restart this session to launch "
                f"'{label}' -- the {top} it imports is already loaded."
            )
        after = self.installed_version(requirement.name, module, python, in_process)
        if not requirement.contains(after):
            raise RuntimeError(
                f"Updated {requirement} into {pip_py}, but {python} still reads "
                f"{requirement.name} {after or 'without a version'}."
            )
