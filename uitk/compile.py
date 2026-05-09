# !/usr/bin/python
# coding=utf-8
"""Compile Qt Designer .ui files to switchboard-augmented _ui.py modules.

The generated _ui.py file embeds metadata constants the switchboard reads
at load time (uitk_tags, custom widgets, base class, source hash). Hash-
based staleness detection keeps the .ui and _ui.py in sync without
relying on file mtimes.

CLI: ``python -m uitk.compile [paths...] [--check] [--force]``
"""
import ast
import hashlib
import logging
import os
import re
import shutil
import subprocess
import threading
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union


logger = logging.getLogger(__name__)


UIC_TIMEOUT_SECONDS = 60


UIC_BINDINGS = {
    "PySide6": "pyside6-uic",
    "PySide2": "pyside2-uic",
    "PyQt6": "pyuic6",
    "PyQt5": "pyuic5",
}

_BINDING_IMPORT_RE = re.compile(
    r"^(\s*)(from|import)\s+(PySide6|PySide2|PyQt6|PyQt5)\b",
    flags=re.MULTILINE,
)


def _find_bundled_uic(binding: str) -> Optional[Path]:
    """Locate Qt's raw uic binary next to the active binding's Python module.

    Critical when multiple PySide installs coexist (e.g. Maya 2025 ships
    PySide6 6.5.3 while a venv may have 6.10+). uic from a newer version
    emits enum-class syntax (``QSizePolicy.Policy.Ignored``) that older
    runtimes reject — so the compiled output must come from the runtime's
    own bundled uic to be loadable. PyQt distributions don't ship uic in
    this layout; this returns None for them and falls back to pyuic5/6.
    """
    if binding not in ("PySide6", "PySide2"):
        return None
    try:
        mod = __import__(binding)
    except ImportError:
        return None
    base = Path(mod.__file__).parent
    candidates = [
        base / "uic.exe",                  # Windows
        base / "Qt" / "libexec" / "uic",   # Linux/macOS bundled
        base / "uic",                      # bare Unix
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _detect_uic_command() -> Tuple[str, list]:
    """Return (binding_name, argv_prefix) for invoking uic.

    argv_prefix is the full list of args to pass before the .ui path.
    Bundled Qt uic emits C++ by default, so it gets ``-g python``.
    The pyside6-uic / pyuic5 / pyuic6 wrappers are language-specific and
    do not accept the flag.

    Prefers uic bundled with the currently-imported binding so output
    syntax matches the runtime in use. Falls back to PATH search.
    Raises FileNotFoundError if no uic is available.
    """
    binding = "PySide6"
    try:
        from qtpy import API_NAME

        binding = API_NAME
    except Exception:
        pass

    bundled = _find_bundled_uic(binding)
    if bundled is not None:
        return binding, [str(bundled), "-g", "python"]

    cmd = UIC_BINDINGS.get(binding)
    if cmd and shutil.which(cmd):
        return binding, [shutil.which(cmd)]

    for b, c in UIC_BINDINGS.items():
        path = shutil.which(c)
        if path:
            return b, [path]

    raise FileNotFoundError(
        "No Qt uic compiler found. Install one of: "
        + ", ".join(UIC_BINDINGS.values())
    )


def _detect_binding() -> Tuple[str, str]:
    """Compatibility shim: return (binding, single uic path).

    Discards any required language flag. New code should call
    :func:`_detect_uic_command` to get the full argv prefix.
    """
    binding, argv = _detect_uic_command()
    return binding, argv[0]


def hash_ui_source(ui_path) -> str:
    """SHA-256 hex digest of the .ui file bytes."""
    return hashlib.sha256(Path(ui_path).read_bytes()).hexdigest()


def compiled_path_for(ui_path) -> Path:
    """Return the _ui.py path paired with a given .ui path."""
    p = Path(ui_path)
    return p.with_name(p.stem + "_ui.py")


_HASH_RE = re.compile(r'^__source_hash__\s*=\s*[\'"]([a-f0-9]+)[\'"]')
_TAGS_RE = re.compile(r"^__uitk_tags__\s*=\s*(\[.*?\])\s*$")
_BASE_RE = re.compile(r'^__base_class__\s*=\s*[\'"](\w+)[\'"]')
_FORM_RE = re.compile(r'^__form_class__\s*=\s*[\'"](\w+)[\'"]')


def _read_header(py_path, pattern, transform=lambda s: s):
    try:
        with Path(py_path).open("r", encoding="utf-8") as f:
            for _ in range(40):
                line = f.readline()
                if not line:
                    break
                m = pattern.match(line)
                if m:
                    return transform(m.group(1))
    except OSError:
        return None
    return None


def read_embedded_hash(py_path) -> Optional[str]:
    """Return __source_hash__ from a generated _ui.py header, or None."""
    return _read_header(py_path, _HASH_RE)


def read_embedded_tags(py_path) -> set:
    """Return __uitk_tags__ from a generated _ui.py header. Empty set if absent."""
    raw = _read_header(py_path, _TAGS_RE)
    if not raw:
        return set()
    try:
        return set(ast.literal_eval(raw))
    except (ValueError, SyntaxError):
        return set()


def read_embedded_base_class(py_path) -> Optional[str]:
    """Return __base_class__ from a generated _ui.py header, or None."""
    return _read_header(py_path, _BASE_RE)


def read_embedded_form_class(py_path) -> Optional[str]:
    """Return __form_class__ from a generated _ui.py header, or None."""
    return _read_header(py_path, _FORM_RE)


def is_compiled_fresh(ui_path, py_path=None) -> bool:
    """True only if py_path carries a uitk hash matching ui_path's content.

    A _ui.py without an embedded uitk hash (e.g. produced by raw
    pyside6-uic by an editor extension or hand-written) is treated as
    stale and regenerated through compile_ui. uitk owns the _ui.py
    format end-to-end: the embedded hash is the single source of truth
    for whether the artifact matches its .ui source.

    **mtime fast path.** When ``py_path.mtime > ui_path.mtime`` the artifact
    is post-source and (combined with the header presence check) safe to
    accept without rehashing the .ui. This avoids reading the full .ui
    bytes on every freshness check — the dominant cost when scanning
    dozens of UIs at startup (precompile_async) or on warm-cache repeats.
    Falls back to the canonical hash compare when mtime is inconclusive
    (equal or older), preserving correctness for filesystems with coarse
    mtime resolution and edge cases like ``touch -t``.
    """
    py_path = Path(py_path) if py_path else compiled_path_for(ui_path)
    if not py_path.exists():
        return False
    embedded = read_embedded_hash(py_path)
    if embedded is None:
        return False  # raw uic or hand-written: not our format
    try:
        if os.path.getmtime(py_path) > os.path.getmtime(ui_path):
            return True
    except OSError:
        pass  # one of them vanished mid-check; fall through to canonical
    return embedded == hash_ui_source(ui_path)


def extract_metadata(ui_path) -> dict:
    """Extract switchboard-relevant metadata from a .ui file.

    Returns:
        {
            "base_class":     "QMainWindow",            # form's Qt base class
            "form_class":     "MyForm",                  # <class> root element
            "customwidgets":  [(class_name, header), ...],
            "uitk_tags":      ["alpha", "beta"],         # sorted list
        }
    """
    tree = ET.parse(str(ui_path))
    root = tree.getroot()

    form_class_el = root.find("class")
    form_class = (form_class_el.text if form_class_el is not None else None) or "Form"

    widget_el = root.find("widget")
    base_class = (widget_el.get("class") if widget_el is not None else None) or "QWidget"

    customwidgets = []
    for cw in root.findall(".//customwidget"):
        cls_el = cw.find("class")
        hdr_el = cw.find("header")
        if cls_el is not None and cls_el.text:
            customwidgets.append(
                (cls_el.text, hdr_el.text if hdr_el is not None else "")
            )

    tags = set()
    if widget_el is not None:
        for prop in widget_el.findall("property"):
            if prop.get("name") == "uitk_tags":
                s = prop.find("string")
                if s is not None and s.text:
                    tags.update(t.strip() for t in s.text.split(",") if t.strip())
                break

    return {
        "base_class": base_class,
        "form_class": form_class,
        "customwidgets": customwidgets,
        "uitk_tags": sorted(tags),
    }


def _rewrite_imports_to_qtpy(source: str) -> str:
    """Rewrite binding-specific imports to qtpy so the artifact is binding-agnostic."""
    return _BINDING_IMPORT_RE.sub(r"\1\2 qtpy", source)


def _rewrite_customwidget_imports(source: str, customwidgets, resolver) -> str:
    """Rewrite ``from X import ClassName`` lines using a class-name resolver.

    Repairs malformed ``<header>`` paths in legacy .ui files (e.g. C++-style
    ``widgets.foo.h``) without touching the .ui itself. For each customwidget,
    if ``resolver(class_name, original_header)`` returns a non-None module
    path, the corresponding from-import line in ``source`` is rewritten to
    use that path. Lines whose class the resolver does not know about are
    left alone, so a missing-from-registry case still fails loudly at
    exec_module time with the original (broken) module name.
    """
    for class_name, original_header in customwidgets:
        resolved = resolver(class_name, original_header)
        if not resolved or resolved == original_header:
            continue
        pattern = re.compile(
            rf"^(\s*)from\s+\S+\s+import\s+{re.escape(class_name)}\b",
            flags=re.MULTILINE,
        )
        source = pattern.sub(rf"\1from {resolved} import {class_name}", source, count=1)
    return source


def _build_header(ui_path: Path, binding: str, metadata: dict, source_hash: str) -> str:
    return (
        f"# AUTO-GENERATED by uitk.compile from {ui_path.name} — do not edit.\n"
        f"# Edit the .ui file in Qt Designer; this file is regenerated.\n"
        f"\n"
        f"__source__         = {ui_path.name!r}\n"
        f"__source_hash__    = {source_hash!r}\n"
        f"__binding__        = {binding!r}\n"
        f"__base_class__     = {metadata['base_class']!r}\n"
        f"__form_class__     = {metadata['form_class']!r}\n"
        f"__customwidgets__  = {metadata['customwidgets']!r}\n"
        f"__uitk_tags__      = {metadata['uitk_tags']!r}\n"
        f"\n"
    )


def compile_ui(ui_path, out_path=None, header_resolver=None) -> Path:
    """Compile a .ui file to a switchboard-augmented _ui.py.

    Args:
        ui_path: Source .ui path.
        out_path: Output .py path. Defaults to {stem}_ui.py next to source.
        header_resolver: Optional callable
            ``(class_name, original_header) -> module_path | None``. If
            provided and returns a non-None path, the corresponding
            ``from X import ClassName`` line in the generated source is
            rewritten to use that path. Used to repair malformed
            ``<header>`` declarations in legacy .ui files (typically wired
            up by the switchboard via its widget_registry).

    Returns:
        Path to the written _ui.py file.

    Raises:
        FileNotFoundError: No Qt uic compiler is on PATH.
        subprocess.CalledProcessError: uic failed on the .ui file.
        subprocess.TimeoutExpired: uic exceeded UIC_TIMEOUT_SECONDS.
    """
    ui_path = Path(ui_path)
    out_path = Path(out_path) if out_path else compiled_path_for(ui_path)

    binding, argv_prefix = _detect_uic_command()
    proc = subprocess.run(
        argv_prefix + [str(ui_path)],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        timeout=UIC_TIMEOUT_SECONDS,
    )
    body = _rewrite_imports_to_qtpy(proc.stdout)

    metadata = extract_metadata(ui_path)

    if header_resolver is not None and metadata["customwidgets"]:
        body = _rewrite_customwidget_imports(
            body, metadata["customwidgets"], header_resolver
        )

    header = _build_header(ui_path, binding, metadata, hash_ui_source(ui_path))

    # Unique per-call tmp suffix so concurrent writes (e.g. background
    # precompile racing the lazy load path) don't collide on the same
    # filename. Both calls produce identical content for the same .ui;
    # whichever os.replace lands second wins, and the result is convergent.
    # Use ``with_name`` (not ``with_suffix``) so the .py suffix is preserved:
    # ``foo_ui.py`` -> ``foo_ui.py.{uuid}.tmp`` rather than ``foo_ui.{uuid}.tmp``.
    tmp_path = out_path.with_name(f"{out_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(header + body, encoding="utf-8")
        os.replace(str(tmp_path), str(out_path))
    except Exception:
        # Best-effort cleanup of orphan tmp on failure.
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise

    return out_path


def ensure_compiled(ui_path, header_resolver=None) -> Path:
    """Return the _ui.py path for ui_path, regenerating if missing or stale.

    See :func:`compile_ui` for the semantics of ``header_resolver``.
    """
    ui_path = Path(ui_path)
    py_path = compiled_path_for(ui_path)
    if not is_compiled_fresh(ui_path, py_path):
        compile_ui(ui_path, py_path, header_resolver=header_resolver)
    return py_path


def _compile_one(target: Path) -> Tuple[Path, Optional[str]]:
    """Worker for parallel bulk compile. Returns (target, error_message_or_None)."""
    try:
        compile_ui(target, compiled_path_for(target))
        return target, None
    except subprocess.CalledProcessError as e:
        return target, (e.stderr or str(e)).rstrip()
    except subprocess.TimeoutExpired:
        return target, f"uic timed out after {UIC_TIMEOUT_SECONDS}s"
    except Exception as e:
        return target, f"{type(e).__name__}: {e}"


_precompile_lock = threading.Lock()
_precompile_active: Optional[threading.Thread] = None


def _gather_ui_files(paths: Iterable[Union[str, Path]]) -> List[Path]:
    """Walk *paths* and return all .ui files (file or under a dir).

    Silently skips entries that don't exist or aren't .ui files — callers
    routinely hand in registry filepaths that may be stale.
    """
    targets: List[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            targets.extend(sorted(path.rglob("*.ui")))
        elif path.is_file() and path.suffix == ".ui":
            targets.append(path)
    return targets


def _gather_stale(paths: Iterable[Union[str, Path]]) -> List[Path]:
    """Return only the .ui files whose paired _ui.py is missing or stale."""
    return [
        t for t in _gather_ui_files(paths)
        if not is_compiled_fresh(t, compiled_path_for(t))
    ]


def _precompile_run(targets: List[Path], jobs: int) -> None:
    if not targets:
        return
    from concurrent.futures import ThreadPoolExecutor

    # Threads, not processes:
    #   - compile_ui's only heavy work is `subprocess.run(uic, ...)` which
    #     releases the GIL, so threads achieve real parallelism here.
    #   - ProcessPoolExecutor on Windows uses spawn, which re-imports the
    #     caller's main module. When precompile_async is triggered by
    #     library code (e.g. MarkingMenu.__init__), workers recursively
    #     re-execute the import path → RuntimeError ("not in __main__").
    #     Threads sidestep that entirely.
    logger.info("uitk precompile: %d file(s) with %d worker(s)", len(targets), jobs)
    if jobs <= 1 or len(targets) == 1:
        for t in targets:
            _, err = _compile_one(t)
            if err:
                logger.warning("uitk precompile: %s failed: %s", t.name, err)
        return
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for t, err in pool.map(_compile_one, targets):
            if err:
                logger.warning("uitk precompile: %s failed: %s", t.name, err)


class PrecompileJob:
    """Handle for an in-flight (or no-op) :func:`precompile_async` call.

    Attributes:
        thread:    Daemon thread running the parallel uic invocations, or
                   ``None`` if no work was started.
        stale:     Number of .ui files that needed compilation.
        reason:    Why ``thread`` is ``None`` — one of ``"running"``,
                   ``"none-stale"``, or ``""`` if a job actually started.

    The handle is truthy iff a thread is running (``bool(job)`` works as
    a "did we kick off work?" check). ``job.is_alive()`` is forwarded to
    the thread for convenience.
    """

    __slots__ = ("thread", "stale", "reason")

    def __init__(
        self,
        thread: Optional[threading.Thread],
        stale: int,
        reason: str,
    ):
        self.thread = thread
        self.stale = stale
        self.reason = reason

    def __bool__(self) -> bool:
        return self.thread is not None

    def is_alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


def precompile_async(
    *paths: Union[str, Path],
    jobs: Optional[int] = None,
    force: bool = False,
) -> PrecompileJob:
    """Pre-compile _ui.py files in a daemon background thread.

    Walks each path (file or directory) and runs ``compile_ui`` in a thread
    pool. By default only files whose hash doesn't match are recompiled
    (``force=False``). Pass ``force=True`` to recompile every .ui under
    *paths* regardless of staleness — useful when the user explicitly
    wants to refresh everything (e.g. after a uic version change). The
    lazy load path (``ensure_compiled``) still works as a fallback if a
    UI is needed before the background job finishes — atomic writes
    converge.

    Returns a :class:`PrecompileJob`. The handle is truthy iff a thread was
    actually started; ``job.stale`` is the count of files queued for compile;
    ``job.reason`` distinguishes ``"none-stale"`` (everything fresh) from
    ``"running"`` (another precompile is in flight). The thread is daemon
    and will not block process exit.

    Use this on application startup to amortize cold-clone first-launch
    latency: ~150-200ms per uic subprocess × dozens of UIs becomes a few
    hundred ms of background work the user never feels.
    """
    global _precompile_active
    workers = jobs if jobs is not None else min(8, os.cpu_count() or 4)
    targets = _gather_ui_files(paths) if force else _gather_stale(paths)
    if not targets:
        return PrecompileJob(thread=None, stale=0, reason="none-stale")
    with _precompile_lock:
        if _precompile_active is not None and _precompile_active.is_alive():
            return PrecompileJob(thread=None, stale=len(targets), reason="running")
        thread = threading.Thread(
            target=_precompile_run,
            args=(targets, workers),
            daemon=True,
            name="uitk-precompile",
        )
        _precompile_active = thread
        thread.start()
        return PrecompileJob(thread=thread, stale=len(targets), reason="")


def main():
    """CLI entry point: python -m uitk.compile [paths...] [--check] [--force] [-j N]."""
    import argparse
    from concurrent.futures import ProcessPoolExecutor, as_completed

    parser = argparse.ArgumentParser(
        description="Compile Qt Designer .ui files to switchboard _ui.py modules.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help=".ui files or directories to scan recursively.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any _ui.py is missing or stale; do not regenerate.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompile even when the existing _ui.py is fresh.",
    )
    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=min(8, (os.cpu_count() or 4)),
        help="Parallel uic processes (default: min(8, CPU count)). Use 1 for serial.",
    )
    args = parser.parse_args()

    targets = []
    for p in args.paths:
        path = Path(p)
        if path.is_dir():
            targets.extend(sorted(path.rglob("*.ui")))
        elif path.suffix == ".ui":
            targets.append(path)

    if not targets:
        print("No .ui files found.")
        return

    if args.check:
        stale = [t for t in targets if not is_compiled_fresh(t, compiled_path_for(t))]
        if stale:
            for s in stale:
                print(f"STALE: {s}")
            raise SystemExit(1)
        print(f"OK: {len(targets)} _ui.py file(s) up to date.")
        return

    todo = [t for t in targets if args.force or not is_compiled_fresh(t, compiled_path_for(t))]
    fresh_count = len(targets) - len(todo)
    if fresh_count:
        print(f"Fresh: {fresh_count} file(s) skipped (use --force to recompile).")
    if not todo:
        return

    failed = []
    if args.jobs <= 1 or len(todo) == 1:
        for target in todo:
            t, err = _compile_one(target)
            if err:
                print(f"FAILED: {t}\n  {err}")
                failed.append(t)
            else:
                print(f"Compiled: {t}")
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(_compile_one, t): t for t in todo}
            for fut in as_completed(futures):
                t, err = fut.result()
                if err:
                    print(f"FAILED: {t}\n  {err}")
                    failed.append(t)
                else:
                    print(f"Compiled: {t}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
