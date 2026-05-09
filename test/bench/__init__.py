"""uitk benchmarks.

Reusable, host-agnostic performance benches for uitk subsystems.  Each
bench is a class that runs inside any live ``QApplication`` (DCC host,
plain Python, etc.) and emits JSON describing per-phase wall-time.

Subclass the relevant base (:class:`MarkingMenuInitBench`,
:class:`OptionBoxInitBench`, :class:`StandaloneUiInitBench`) to point
at your project's UI / slot sources.  How the bench is *driven* —
including spawning a fresh DCC instance — is the consumer's
responsibility; uitk deliberately does not import ``maya``, ``max``,
or any other host SDK.

This package lives under ``test/`` because it is test infrastructure,
not part of the runtime API.  Pytest sees it via the ``test/`` entry
in :mod:`conftest`'s sys.path setup; external consumers (e.g.
tentacle's bench scripts) add ``uitk/test/`` to sys.path explicitly
and import as ``from bench.<name> import <Class>``.
"""
