"""uitk benchmarks.

Reusable, host-agnostic performance benches for uitk subsystems.  Each
bench is a class that runs inside any live ``QApplication`` (DCC host,
plain Python, etc.) and emits JSON describing per-phase wall-time.

Subclass :class:`OptionBoxInitBench` (and friends) to point at your
project's UI / slot sources.  How the bench is *driven* — including
spawning a fresh DCC instance — is the consumer's responsibility; uitk
deliberately does not import ``maya``, ``max``, or any other host SDK.
"""
