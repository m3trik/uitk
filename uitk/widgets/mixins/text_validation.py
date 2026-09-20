# !/usr/bin/python
# coding=utf-8
"""Validation feedback for a text field -- the red "refused" state.

One mixin for every uitk text field (:class:`~uitk.widgets.lineEdit.LineEdit`,
:class:`~uitk.widgets.textEdit.TextEdit`): a debounced check of the field's
value, the ``actionState`` color and tooltip that say what is wrong, and a
``validated(bool, str)`` signal.  A check never rewrites what the user typed:
a refused value stays in the field, marked, with the reason in its tooltip --
which is how a field enforces a rule (a path that must exist, a legal name)
without the silent cleanup that makes a value arrive differently from how it
was typed.  The one edit a check may make is the opt-in revert on commit
(``revert_on_commit``), and it happens in the field, where the user sees it.
"""

import threading

from qtpy import QtCore


class TextValidationMixin:
    """Reversible visual state feedback plus an optional validator.

    Provides ``set_action_color(key)`` / ``reset_action_color()`` for
    signaling validation state.  Styling is driven by an ``actionState``
    dynamic property and defined in style.qss.

    Also provides an optional ``set_validator()`` API that wires up
    debounced ``textChanged`` -> user-supplied check -> visual feedback
    (``actionState`` color + tooltip) -> ``validated(bool, str)`` signal.

    Built-in string shortcuts for ``set_validator()``:
        - ``"file"``  -- ``ptk.is_valid(text, "file")``
        - ``"dir"``   -- ``ptk.is_valid(text, "dir")``
        - ``"path"``  -- ``ptk.is_valid(text)`` (file or dir)
        - ``"url"`` / ``"file_or_url"`` -- an address (probed off-thread)
        - ``"name"``  -- ``ptk.StrUtils.name_error``: a legal name, the reason
          a name is refused in the tooltip

    Or pass any ``callable(text) -> bool``, or with ``reasons=True`` any
    ``callable(text) -> reason or None``.

    Host contract: the value is :meth:`_validation_value` (the text by
    default) and a change arrives through ``textChanged``.  A host that
    declares ``validated = QtCore.Signal(bool, str)`` gets the signal;
    ``set_validator()`` still works (color + tooltip) without it.  A host
    whose edits COMMIT (Enter, focus-out) names that signal in
    :meth:`_commit_signal`, which ``revert_on_commit`` needs.
    """

    def set_action_color(self, key: str) -> None:
        self.setProperty("actionState", key)
        self.style().unpolish(self)
        self.style().polish(self)

    def reset_action_color(self) -> None:
        self.setProperty("actionState", None)
        self.style().unpolish(self)
        self.style().polish(self)

    # ------------------------------------------------------------------
    # Validator API
    # ------------------------------------------------------------------

    _VALIDATOR_PRESETS = ("file", "dir", "path", "url", "file_or_url", "name")
    # Presets whose value may be a URL: the synchronous check passes a URL on
    # shape alone and a deferred probe (``_url_probe``) settles reachability.
    _URL_PRESETS = ("url", "file_or_url")
    # Presets that answer with a REASON (a sentence, or None when accepted)
    # rather than a bool -- see ``set_validator(reasons=...)``.
    _REASON_PRESETS = ("name",)

    @staticmethod
    def _resolve_validator(validator):
        """Convert a preset string into a callable, or return *validator* as-is."""
        if callable(validator):
            return validator
        if validator in TextValidationMixin._VALIDATOR_PRESETS:
            import pythontk as ptk

            if validator == "name":
                return ptk.StrUtils.name_error
            if validator == "url":
                return lambda text: ptk.RemoteFile.is_url(text)
            if validator == "file_or_url":
                return lambda text: (
                    ptk.RemoteFile.is_url(text) or ptk.is_valid(text, "file")
                )
            kind = None if validator == "path" else validator
            return lambda text, _k=kind: bool(text) and ptk.is_valid(text, _k)
        raise ValueError(
            f"validator must be callable or one of "
            f"{TextValidationMixin._VALIDATOR_PRESETS!r}, got {validator!r}"
        )

    @staticmethod
    def _url_probe(text):
        """Deferred check behind the URL presets: can *text* be fetched?

        A URL can't be verified without a round trip, so the synchronous
        preset accepts it on shape and this settles it off the Qt thread via
        ``ptk.RemoteFile.probe`` (which also rewrites share links and refuses
        a sign-in page).  A non-URL value already passed synchronously.
        """
        import pythontk as ptk

        if not ptk.RemoteFile.is_url(text):
            return True, None
        problem = ptk.RemoteFile.probe(text)
        return problem is None, problem

    def _commit_signal(self):
        """The signal a finished edit emits (Enter, focus-out), or ``None``
        when the host has no such moment -- which ``revert_on_commit`` needs.
        """
        return None

    def set_validator(
        self,
        validator,
        *,
        debounce_ms: int = 300,
        invalid_tooltip: str = "Invalid",
        valid_tooltip=None,
        empty_tooltip=None,
        empty_is_valid: bool = True,
        deferred=None,
        pending_tooltip: str = "Checking…",
        reasons=None,
        revert_on_commit=False,
    ):
        """Install a debounced text validator with visual feedback.

        Parameters:
            validator: A callable ``(text) -> bool`` or a preset string:
                ``"file"`` / ``"dir"`` / ``"path"`` (must exist on disk),
                ``"url"`` (an ``http(s)`` address), ``"file_or_url"`` (either),
                ``"name"`` (a legal name: letters, digits and ``_`` --
                ``ptk.StrUtils.name_error``).
                The URL presets also install a deferred reachability probe
                (see *deferred*) unless one is passed explicitly.
            debounce_ms: Delay before validating after the last keystroke.
                Set to 0 to validate immediately (typically only useful
                in tests).
            invalid_tooltip: Tooltip shown when validation fails and no reason
                was given.  A string, or a callable ``(message) -> str``
                handed the reason (``None`` when a bool check failed) so a
                host can wrap it in its own rich tooltip.
            valid_tooltip: Tooltip shown when validation passes.  Can be
                a string, a callable ``(text) -> str``, or ``None`` to
                show the text itself.
            empty_tooltip: Tooltip shown when text is empty.  ``None``
                (default) preserves whatever tooltip was set on the
                widget before ``set_validator`` was called.
            empty_is_valid: When True (default), empty text resets the
                color and emits ``validated(True, "")``.  When False,
                empty text is checked like any other (and a bool check
                is expected to refuse it).
            deferred: Optional slow check run on a worker thread AFTER
                *validator* passes -- a network probe, a disk scan.  Called
                with the value; returns ``bool`` or ``(bool, message)``.
                While it runs the field shows the ``info`` state and
                *pending_tooltip*; its answer then sets the final color
                (``message`` becomes the tooltip on failure) and emits
                ``validated`` a second time.  An answer for a value the
                user has since replaced is dropped.  The host must declare
                ``deferred_validated = QtCore.Signal(int, bool, object)``
                (:class:`LineEdit` does): a worker thread cannot touch
                widgets, so the result crosses back through that signal.
            pending_tooltip: Tooltip while *deferred* is in flight.
            reasons: True when *validator* answers with the REASON a value is
                refused -- a sentence, or ``None`` when it is accepted -- the
                shape ``ptk.StrUtils.name_error`` and ``ShotStore.name_error``
                return.  The reason becomes the tooltip.  ``None`` (default)
                infers it: True for the ``"name"`` preset, else False.
            revert_on_commit: What a COMMIT of a refused value does (Enter or
                focus-out; needs a host with a :meth:`_commit_signal`).
                False (default) leaves it in the field, marked.  True puts
                back the last value this validator accepted; a callable is
                asked for the value to put back (the model's own -- a store
                whose current name predates the rule and was never accepted
                here).  Before it reverts, a host declaring
                ``commit_refused = QtCore.Signal(str, str)`` emits
                ``(refused text, reason)`` so the caller can say what was
                not applied.

        Raises:
            TypeError: *revert_on_commit* on a host without a commit signal,
                or *deferred* on a host without ``deferred_validated``.
        """
        callable_validator = self._resolve_validator(validator)
        if deferred is None and validator in self._URL_PRESETS:
            deferred = self._url_probe
        if reasons is None:
            reasons = validator in self._REASON_PRESETS

        # Capture pre-install tooltip so empty-text state can restore it
        prior_tooltip = self.toolTip()

        # Idempotent install — disconnect any prior wiring first
        self.clear_validator()

        commit = None
        if revert_on_commit:
            commit = self._commit_signal()
            if commit is None:
                raise TypeError(
                    f"{type(self).__name__} has no commit signal; "
                    "revert_on_commit needs one (see _commit_signal)."
                )

        # QTimer-based debouncer (replaces any pending validation)
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._run_validation)

        self._validator_callable = callable_validator
        self._validator_reasons = bool(reasons)
        self._validator_timer = timer
        self._validator_debounce_ms = max(0, int(debounce_ms))
        self._validator_invalid_tooltip = invalid_tooltip
        self._validator_valid_tooltip = valid_tooltip
        self._validator_empty_tooltip = (
            empty_tooltip if empty_tooltip is not None else prior_tooltip
        )
        self._validator_empty_is_valid = empty_is_valid
        self._validator_deferred = deferred
        self._validator_pending_tooltip = pending_tooltip
        self._validator_revert = revert_on_commit
        self._validator_commit = commit
        self._deferred_generation = 0
        if deferred is not None:
            emitter = getattr(self, "deferred_validated", None)
            if emitter is None or not hasattr(emitter, "connect"):
                raise TypeError(
                    "a deferred validator needs a host that declares "
                    "`deferred_validated = QtCore.Signal(int, bool, object)`"
                )
            emitter.connect(self._on_deferred_validated)
        if commit is not None:
            commit.connect(self._on_commit_validate)
        self._last_validation_text = None
        self._last_validation_result = None
        self._last_validation_message = None
        self._last_accepted_value = None

        self.textChanged.connect(self._on_text_changed_validate)

        # Run once now so the initial color/tooltip reflect current state
        self._run_validation()

    def clear_validator(self):
        """Remove any installed validator and reset visual state."""
        timer = getattr(self, "_validator_timer", None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        if getattr(self, "_validator_callable", None) is not None:
            try:
                self.textChanged.disconnect(self._on_text_changed_validate)
            except (TypeError, RuntimeError):
                pass
        # Retire any in-flight deferred check; its answer must not land on
        # a field that no longer validates.
        self._deferred_generation = getattr(self, "_deferred_generation", 0) + 1
        if getattr(self, "_validator_deferred", None) is not None:
            try:
                self.deferred_validated.disconnect(self._on_deferred_validated)
            except (TypeError, RuntimeError):
                pass
        commit = getattr(self, "_validator_commit", None)
        if commit is not None:
            try:
                commit.disconnect(self._on_commit_validate)
            except (TypeError, RuntimeError):
                pass
        self._validator_commit = None
        self._validator_revert = False
        self._validator_deferred = None
        self._validator_callable = None
        self._validator_timer = None
        self._last_validation_text = None
        self._last_validation_result = None
        self._last_validation_message = None
        self._last_accepted_value = None
        self.reset_action_color()

    @property
    def is_valid(self):
        """Last validation result, or ``None`` if no validator is set."""
        return getattr(self, "_last_validation_result", None)

    @property
    def validation_message(self):
        """Why the last validation refused the value (a reason validator's
        sentence, a deferred check's message), or ``None`` -- accepted, not
        yet checked, or refused by a bool check that gives no reason."""
        return getattr(self, "_last_validation_message", None)

    def validate_now(self, run_deferred: bool = True):
        """Cancel any pending debounce and validate the current text now.

        Useful from commit handlers (``editingFinished``) where stale
        ``is_valid`` would be wrong if the user pressed Enter before the
        debounce timer fired.

        Parameters:
            run_deferred: Also start the ``deferred`` check when one is
                installed.  A commit handler about to do the real work
                itself -- fetch the URL, open the file -- passes False: the
                synchronous check settles, any in-flight deferred answer is
                retired, and the handler's own result is the last word.
        """
        timer = getattr(self, "_validator_timer", None)
        if timer is not None:
            timer.stop()
        if getattr(self, "_validator_callable", None) is not None:
            self._run_validation(run_deferred=run_deferred)

    def _on_text_changed_validate(self, *_args):
        # ``*_args``: QLineEdit.textChanged carries the text, QTextEdit's none.
        timer = getattr(self, "_validator_timer", None)
        if timer is None:
            return
        if self._validator_debounce_ms <= 0:
            self._run_validation()
            return
        timer.start(self._validator_debounce_ms)

    def _validation_value(self):
        """The value validation runs against.

        Defaults to the field text. Data-carrying hosts (e.g. :class:`LineEdit`
        whose :meth:`set_value` shows a friendly display while storing a
        distinct payload) override this to return that payload, so the
        validator and the ``valid_tooltip`` callback see the real value rather
        than the display string.
        """
        return self.text()

    def _check(self, validator, value):
        """``(ok, reason)`` for *value*: a reason validator's sentence, or a
        bool check's answer with no reason.  A check that raises refuses."""
        try:
            result = validator(value)
        except Exception:
            return False, None
        if getattr(self, "_validator_reasons", False):
            reason = result or None
            return reason is None, reason
        return bool(result), None

    def _run_validation(self, run_deferred: bool = True):
        validator = getattr(self, "_validator_callable", None)
        if validator is None:
            return
        value = self._validation_value()
        empty = not value
        message = None
        # Every run supersedes a deferred check still in flight: its answer
        # describes a value that may no longer be in the field.
        self._deferred_generation = getattr(self, "_deferred_generation", 0) + 1

        if empty and self._validator_empty_is_valid:
            ok = True
            self.reset_action_color()
            self.setToolTip(self._validator_empty_tooltip or "")
            self._last_accepted_value = value
        else:
            ok, message = self._check(validator, value)

            deferred = getattr(self, "_validator_deferred", None)
            if ok and deferred is not None and run_deferred:
                # Not accepted yet: the deferred answer settles it.
                self.set_action_color("info")
                self.setToolTip(self._validator_pending_tooltip or "")
                self._start_deferred(deferred, value)
            elif ok:
                self._show_valid(value)
                self._last_accepted_value = value
            else:
                self._show_invalid(message)

        self._last_validation_text = value
        self._last_validation_result = ok
        self._last_validation_message = message
        self._emit_validated(ok, value)

    def _on_commit_validate(self):
        """A finished edit: settle the check, and revert a refused value when
        ``revert_on_commit`` asks for it (see :meth:`set_validator`)."""
        if getattr(self, "_validator_callable", None) is None:
            return
        self.validate_now(run_deferred=False)
        if self.is_valid is not False or not self._validator_revert:
            return
        revert = self._validator_revert
        restore = revert() if callable(revert) else self._last_accepted_value
        refused = self._validation_value()
        if restore is None or restore == refused:
            return  # nothing known to go back to; the value stays, marked
        emitter = getattr(self, "commit_refused", None)
        if emitter is not None and hasattr(emitter, "emit"):
            emitter.emit(str(refused), self.validation_message or "")
        self._set_validation_value(restore)
        # Settle now: the restore's textChanged only re-arms the debounce, and a
        # caller reading ``is_valid`` right after the commit must get the
        # restored value's verdict, not the refused one's.
        self.validate_now(run_deferred=False)

    def _set_validation_value(self, value):
        """Put *value* back in the field (the revert on commit)."""
        self.setText(str(value))

    def _show_valid(self, value):
        self.set_action_color("reset")
        tip = self._validator_valid_tooltip
        if callable(tip):
            tip = tip(value)
        self.setToolTip(tip if tip is not None else str(value))

    def _show_invalid(self, message):
        self.set_action_color("invalid")
        tip = self._validator_invalid_tooltip
        if callable(tip):
            tip = tip(message)
        else:
            tip = message or tip
        self.setToolTip(tip if tip is not None else "")

    def _emit_validated(self, ok, value):
        emitter = getattr(self, "validated", None)
        if emitter is not None and hasattr(emitter, "emit"):
            emitter.emit(ok, value if isinstance(value, str) else str(value))

    def _start_deferred(self, deferred, value):
        """Run ``deferred(value)`` on a daemon thread.

        The answer comes back on the Qt thread through ``deferred_validated``
        tagged with the generation it was started for, so a late answer
        for a value the user has since replaced is ignored.
        """
        generation = self._deferred_generation
        emitter = self.deferred_validated

        def _work():
            try:
                result = deferred(value)
            except Exception:
                result = False
            if isinstance(result, tuple):
                ok = result[0]
                message = result[1] if len(result) > 1 else None
            else:
                ok, message = result, None
            try:
                emitter.emit(generation, bool(ok), message)
            except RuntimeError:
                pass  # the widget was deleted while the check ran

        threading.Thread(
            target=_work, name="TextValidation-deferred-validate", daemon=True
        ).start()

    def _on_deferred_validated(self, generation, ok, message):
        if generation != getattr(self, "_deferred_generation", 0):
            return  # answer for a value the user has since replaced
        if ok:
            self._show_valid(self._last_validation_text)
            self._last_accepted_value = self._last_validation_text
        else:
            self._show_invalid(message)
        self._last_validation_result = ok
        self._last_validation_message = None if ok else message
        self._emit_validated(ok, self._last_validation_text)
