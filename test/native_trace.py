"""Capture a NATIVE backtrace for a Windows access violation.

``faulthandler`` prints Python frames only, so a fault inside Qt/shiboken with
no Python frame on the stack yields an empty report. That is the signature of
the uitk suite segfault, and reading it is what identified the cause: an
application-level Python event filter being dispatched for an event Qt sends
from inside ``QWidgetPrivate::init``, which drives shiboken's
``storePythonOverrideErrorOrPrint`` into an access violation.

Needs no debugger and no symbol-built Qt -- ``dbghelp.dll`` ships with Windows.
A vectored exception handler runs ON the faulting thread while its stack is
intact, captures the native return-address chain, and symbolizes each frame to
``module!symbol+0xNN`` (or ``module+0xNN`` where no PDB exists).

Arming it, without editing the runner or the suite -- put this directory on
``PYTHONPATH`` (APPEND to the ambient value; replacing it hides ``pythontk`` and
every module then errors at collection) next to a ``sitecustomize.py`` of::

    import native_trace
    native_trace.install()

Then run the suite as usual. The report is appended to the path in
``UITK_NATIVE_TRACE`` (default ``native_trace.txt``).

Reading the result: frames below ``ntdll!KiUserExceptionDispatcher`` are the
real fault site; everything above it is this handler's own stack. Module names
are resolved at FAULT time, not at import -- Qt and the PySide bindings load
long after this module does, so an install-time snapshot names none of them.
"""

import ctypes
import os
from ctypes import wintypes

MAX_FRAMES = 62
EXCEPTION_CONTINUE_SEARCH = 0
_INTERESTING = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000374: "HEAP_CORRUPTION",
    0xC000041D: "FATAL_USER_CALLBACK",
    0xC0000409: "FAST_FAIL",
    0x80000003: "BREAKPOINT",
}

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dbghelp = ctypes.WinDLL("dbghelp", use_last_error=True)


class EXCEPTION_RECORD(ctypes.Structure):
    pass


EXCEPTION_RECORD._fields_ = [
    ("ExceptionCode", wintypes.DWORD),
    ("ExceptionFlags", wintypes.DWORD),
    ("ExceptionRecord", ctypes.POINTER(EXCEPTION_RECORD)),
    ("ExceptionAddress", ctypes.c_void_p),
    ("NumberParameters", wintypes.DWORD),
    ("__unusedAlignment", wintypes.DWORD),
    ("ExceptionInformation", ctypes.c_ulonglong * 15),
]


class EXCEPTION_POINTERS(ctypes.Structure):
    _fields_ = [
        ("ExceptionRecord", ctypes.POINTER(EXCEPTION_RECORD)),
        ("ContextRecord", ctypes.c_void_p),
    ]


class SYMBOL_INFO(ctypes.Structure):
    _fields_ = [
        ("SizeOfStruct", ctypes.c_ulong),
        ("TypeIndex", ctypes.c_ulong),
        ("Reserved", ctypes.c_ulonglong * 2),
        ("Index", ctypes.c_ulong),
        ("Size", ctypes.c_ulong),
        ("ModBase", ctypes.c_ulonglong),
        ("Flags", ctypes.c_ulong),
        ("Value", ctypes.c_ulonglong),
        ("Address", ctypes.c_ulonglong),
        ("Register", ctypes.c_ulong),
        ("Scope", ctypes.c_ulong),
        ("Tag", ctypes.c_ulong),
        ("NameLen", ctypes.c_ulong),
        ("MaxNameLen", ctypes.c_ulong),
        ("Name", ctypes.c_char * 512),
    ]


class MODULEINFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", ctypes.c_void_p),
        ("SizeOfImage", wintypes.DWORD),
        ("EntryPoint", ctypes.c_void_p),
    ]


_frames = (ctypes.c_void_p * MAX_FRAMES)()
_sym_buf = SYMBOL_INFO()
_out_path = os.environ.get("UITK_NATIVE_TRACE", "native_trace.txt")
_handler_ref = None
_modules = []  # (base, size, name), sorted -- the no-PDB fallback


def _snapshot_modules():
    """Record loaded module ranges so an address resolves even without symbols."""
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    proc = kernel32.GetCurrentProcess()
    needed = wintypes.DWORD()
    arr = (ctypes.c_void_p * 2048)()
    if not psapi.EnumProcessModules(
        ctypes.c_void_p(proc), arr, ctypes.sizeof(arr), ctypes.byref(needed)
    ):
        return
    name = ctypes.create_unicode_buffer(512)
    info = MODULEINFO()
    for i in range(min(needed.value // ctypes.sizeof(ctypes.c_void_p), 2048)):
        h = arr[i]
        if not h:
            continue
        psapi.GetModuleFileNameExW(ctypes.c_void_p(proc), ctypes.c_void_p(h), name, 512)
        if psapi.GetModuleInformation(
            ctypes.c_void_p(proc),
            ctypes.c_void_p(h),
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            _modules.append(
                (
                    int(info.lpBaseOfDll),
                    int(info.SizeOfImage),
                    os.path.basename(name.value),
                )
            )
    _modules.sort()


def _module_of(addr):
    for base, size, name in _modules:
        if base <= addr < base + size:
            return f"{name}+0x{addr - base:x}"
    return f"0x{addr:016x}"


def _describe(addr):
    """module!symbol+0xNN when a PDB is present, else module+0xNN."""
    _sym_buf.SizeOfStruct = ctypes.sizeof(SYMBOL_INFO) - 512
    _sym_buf.MaxNameLen = 511
    disp = ctypes.c_ulonglong(0)
    try:
        ok = dbghelp.SymFromAddr(
            ctypes.c_void_p(kernel32.GetCurrentProcess()),
            ctypes.c_ulonglong(addr),
            ctypes.byref(disp),
            ctypes.byref(_sym_buf),
        )
    except OSError:
        ok = False
    where = _module_of(addr)
    if ok:
        sym = _sym_buf.Name.decode("mbcs", "replace")
        if sym:
            return f"{where}  {sym}+0x{disp.value:x}"
    return where


HANDLER = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(EXCEPTION_POINTERS))


def _on_exception(info):
    try:
        rec = info.contents.ExceptionRecord.contents
        code = rec.ExceptionCode & 0xFFFFFFFF
        if code not in _INTERESTING:
            return EXCEPTION_CONTINUE_SEARCH
        n = kernel32.RtlCaptureStackBackTrace(
            ctypes.c_ulong(0), ctypes.c_ulong(MAX_FRAMES), _frames, None
        )
        # Re-snapshot HERE, not at install time: Qt6Core/Qt6Widgets/the PySide
        # .pyd bindings all load long after this module is imported, so the
        # install-time table names none of them and every interesting frame
        # comes back as a bare address. Refresh dbghelp too, so its nearest-
        # export lookup can name Qt's exported symbols.
        del _modules[:]
        _snapshot_modules()
        try:
            dbghelp.SymRefreshModuleList(ctypes.c_void_p(kernel32.GetCurrentProcess()))
        except OSError:
            pass
        lines = [
            "",
            "=" * 72,
            f"NATIVE FAULT {_INTERESTING[code]} (0x{code:08X}) "
            f"at {_describe(int(rec.ExceptionAddress or 0))}",
            f"pid={os.getpid()} tid={kernel32.GetCurrentThreadId()}",
        ]
        if code == 0xC0000005 and rec.NumberParameters >= 2:
            op = {0: "read", 1: "write", 8: "execute"}.get(
                rec.ExceptionInformation[0], rec.ExceptionInformation[0]
            )
            lines.append(
                f"  tried to {op} address 0x{rec.ExceptionInformation[1]:016x}"
            )
        lines.append("native stack (innermost first):")
        for i in range(n):
            lines.append(f"  #{i:02d} {_describe(int(_frames[i] or 0))}")
        lines.append("=" * 72)
        with open(_out_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        pass
    return EXCEPTION_CONTINUE_SEARCH


def install():
    global _handler_ref
    if _handler_ref is not None:
        return
    _snapshot_modules()
    try:
        dbghelp.SymSetOptions(0x00000004 | 0x00000200)  # UNDNAME | DEFERRED_LOADS
        dbghelp.SymInitialize(ctypes.c_void_p(kernel32.GetCurrentProcess()), None, True)
    except OSError:
        pass
    _handler_ref = HANDLER(_on_exception)
    kernel32.AddVectoredExceptionHandler.argtypes = (ctypes.c_ulong, HANDLER)
    kernel32.AddVectoredExceptionHandler.restype = ctypes.c_void_p
    kernel32.AddVectoredExceptionHandler(ctypes.c_ulong(1), _handler_ref)
