# !/usr/bin/python
# coding=utf-8
"""A live preview bound to its panel's widgets, over the host's scene session.

A preview panel has an enable checkbox, a commit button and option widgets
wired to :meth:`PreviewController.refresh`. Checking the box runs the
operation on the selection as a throwaway pass; each option change rolls the
pass back and runs it again; unchecking rolls it back for good; the commit
button keeps the result as one undo step, and with no preview running runs the
operation once on the selection, as one undo step too.

:class:`PreviewController` owns that lifecycle and the widgets: their signals,
the commit button's enabled state, the window's show / hide hooks, the Select
Result toggle, the error popup, the operation's hooks. The scene is reached
only through a :class:`PreviewSession`, a small protocol each host library
implements over its own scene (a snapshot or a node diff to roll back, an undo
chunk or an undo push to commit); the library's ``Preview`` is this class bound
to its session (:attr:`PreviewController.SESSION_CLASS`), so a panel builds
one the same way in every host: ``tk.Preview(self, ui.chk000, ui.b000, ...)``.

The operation (a panel's Slots, typically) implements
``perform_operation(objects, ...)`` -- its host session calls it -- and may
implement ``prepare_operation(objects)``: a one-shot precondition run once
before a preview captures the scene (and inside a commit's undo step when no
preview runs), for state the rollback must not undo.

The widgets are duck-typed: the checkbox needs ``toggled.connect`` /
``setChecked`` / ``isChecked``, the button ``clicked.connect`` /
``setEnabled``, and either one's ``window()`` may offer ``on_show`` /
``on_hide`` signals (uitk's ``MainWindow`` does). Nothing here imports Qt, so a
headless host drives a preview with stand-ins.
"""

import logging
import weakref
from functools import wraps
from html import escape
from typing import (
    Any,
    Callable,
    ContextManager,
    List,
    Optional,
    Protocol,
    Sequence,
    Set,
)

import pythontk as ptk


class PreviewSession(Protocol):
    """What a :class:`PreviewController` asks of the scene it previews in.

    Each host library implements it (its ``Preview`` binds the controller to
    it); a fake stands in for one in a plain-Python test. One session serves
    one preview and holds what it captured. The controller calls it in this
    order: ``selection``, ``begin``, then ``run`` and ``rollback`` (a refresh
    is a rollback and a run), and to end the preview either ``rollback`` +
    ``discard``, or ``commit`` inside ``undo_step``. A commit with no preview
    running is ``selection`` and ``apply`` inside ``undo_step``.
    """

    def selection(self) -> List[Any]:
        """The objects a preview or a commit would act on now ([] for none)."""

    def begin(self, objects: Sequence[Any]) -> None:
        """Capture *objects* and the scene state a rollback returns to."""

    def run(self) -> None:
        """Run the operation over the captured objects as a pass
        :meth:`rollback` reverses, recorded on no undo queue. Raises what the
        operation raised; a rollback still reverses what the pass did."""

    def rollback(self) -> None:
        """Reverse the last pass (none: a no-op); the capture is kept."""

    def discard(self, reselect: bool) -> None:
        """End the preview without keeping it, after its rollback: drop the
        capture, and with *reselect* select the captured objects again."""

    def commit(self) -> None:
        """Keep the previewed result as the scene's own, undoably, and end the
        preview. Called inside :meth:`undo_step`."""

    def apply(self, objects: Sequence[Any]) -> None:
        """Run the operation once over *objects* with no preview, undoably.
        Called inside :meth:`undo_step`."""

    def undo_step(self, name: str) -> ContextManager:
        """Everything done inside is ONE undo step, named *name*. It may yield
        a handle whose ``cancel()`` drops the step, which the controller calls
        when a commit is refused having changed nothing (a host that keeps no
        empty step on its own yields None)."""

    def unrecorded(self) -> ContextManager:
        """Scene edits made inside reach no undo queue."""

    def select_result(self, checkbox: Any, results: Any, committed: bool) -> None:
        """Select the operation's *results* while *checkbox* reads checked
        (a dead widget reads checked), else deselect them; *committed*: right
        after a commit, where a host that settles its selection late
        re-asserts it."""


class _PreviewControllerInternal:
    """Internal helpers for :class:`PreviewController`."""

    @staticmethod
    def _format_op_error(err: Exception) -> str:
        """The message-box text for an operation failure.

        The traceback goes to the log; this is only the popup. An exception
        that carries a curated ``user_message`` (a host library's ``OperationError``:
        plus optional ``causes`` and ``title``, inline HTML allowed) shows it;
        any other is reduced to its first non-empty line, escaped, so a
        multi-line driver error never floods the popup.
        """
        user_message = getattr(err, "user_message", None)
        if user_message:
            title = getattr(err, "title", None) or "Operation failed"
            body = user_message
            bullets = list(getattr(err, "causes", None) or []) or None
        else:
            title = "Operation failed"
            lines = [ln.strip() for ln in str(err).splitlines() if ln.strip()]
            # Untrusted text: escaped, so a stray '<' renders instead of
            # opening a tag.
            body = escape(lines[0]) if lines else type(err).__name__
            bullets = None
        try:
            return ptk.TooltipFormat.fmt(title=title, body=body, bullets=bullets)
        except Exception:  # degrade to plain text, never lose the message
            tail = (" " + " ".join(bullets)) if bullets else ""
            return f"{title}: {body}{tail}"

    @staticmethod
    def _safe(func):
        """Report an unexpected failure of *func*, switch the preview off, and
        re-raise. Operation failures never reach here: the lifecycle reports
        them itself and stays quiet."""

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                self.logger.exception(f"Error in {func.__name__}: {e}")
                if self.message_func:
                    self.message_func(_PreviewControllerInternal._format_op_error(e))
                # Re-entry guard: a raising disable() would recurse forever.
                if not getattr(self, "_in_recovery", False):
                    self._in_recovery = True
                    try:
                        self.disable()
                    except Exception as inner:
                        self.logger.exception(
                            f"disable() during recovery raised: {inner}"
                        )
                    finally:
                        self._in_recovery = False
                raise

        return wrapper


class PreviewController(_PreviewControllerInternal):
    """A panel's live preview: its widgets bound to a host scene session.

    The preview is optional: the commit button is live from the start and,
    with no preview running, commits the operation straight onto the
    selection, gated the same way and as the same one undo step.
    ``require_preview=True`` keeps it dead until a preview runs.

    Parameters:
        operation_instance: The operation: ``perform_operation`` (its session
            calls it), optionally ``prepare_operation(objects)``.
        preview_checkbox: The enable checkbox. Tagged to stay out of state
            restore and resets: a preview starts off, and a reset never runs
            the operation.
        create_button: The commit button.
        finalize_func: Called after a commit, inside its undo step.
        message_func: Shows a message (a selection refused, an operation
            failed); ``None`` logs it.
        enable_on_show: Start the preview each time the panel's window shows.
        disable_on_hide: Discard the preview when the panel's window hides.
        validation_func: ``(objects) -> bool``; False refuses a preview or a
            commit on that selection.
        select_result_checkbox: The panel's Select Result checkbox: with
            *result_provider*, the result is selected (checked) or deselected
            after every pass and on commit, and a toggle applies at once,
            without a re-run.
        result_provider: ``() -> result(s)`` -- what the operation built last.
        reselect_on_disable: A discarded preview selects the captured objects
            again (an operation often changes the selection).
        require_preview: Commit only a running preview.
        undo_message: The commit's undo step name; the operation's class name
            when omitted.
        restore_func: Called once after the rollback that DISCARDS a preview
            (unchecked, failed, hidden; never a commit), recorded on no undo
            queue, for state the rollback cannot reach.
        session: The scene session (:class:`PreviewSession`); ``None`` builds
            one from :attr:`SESSION_CLASS`.
    """

    #: The host's session factory, ``SESSION_CLASS(operation) ->
    #: PreviewSession``, built once per preview when no *session* is passed
    #: (a session holds what it captured). Each host library's ``Preview``
    #: sets it; ``None``: a session must be passed.
    SESSION_CLASS: Optional[Callable[[Any], PreviewSession]] = None

    #: Every live preview, so a host can discard them all at once
    #: (:meth:`cleanup_all_instances`).
    _instances: Set["PreviewController"] = set()

    @classmethod
    def cleanup_all_instances(cls) -> None:
        """Discard every live preview and forget them all."""
        for inst in list(cls._instances):
            try:
                inst.cleanup()
            except Exception:
                pass
        cls._instances.clear()

    def __init__(
        self,
        operation_instance,
        preview_checkbox,
        create_button,
        finalize_func: Optional[Callable] = None,
        message_func: Optional[Callable] = print,
        enable_on_show: bool = False,
        disable_on_hide: bool = True,
        validation_func: Optional[Callable] = None,
        select_result_checkbox=None,
        result_provider: Optional[Callable] = None,
        reselect_on_disable: bool = True,
        require_preview: bool = False,
        undo_message: Optional[str] = None,
        restore_func: Optional[Callable] = None,
        *,
        session: Optional[PreviewSession] = None,
    ):
        if not hasattr(operation_instance, "perform_operation"):
            raise ValueError("operation_instance must implement perform_operation")
        if preview_checkbox is None or create_button is None:
            raise ValueError("preview_checkbox and create_button cannot be None")
        if session is None:
            if self.SESSION_CLASS is None:
                raise TypeError(
                    "PreviewController needs a scene session (session=, or SESSION_CLASS)"
                )
            session = self.SESSION_CLASS(operation_instance)

        self.logger = logging.getLogger(f"{__name__}.{type(self).__name__}")
        #: The scene session every scene read and edit goes through.
        self.session: PreviewSession = session
        self.operation_instance = operation_instance
        self.preview_checkbox = preview_checkbox
        # A preview starts off on load, and Reset / Save as Defaults never
        # switch one on (that runs the operation): uitk's state restore and
        # its defaults operations skip a widget tagged this way.
        preview_checkbox.exclude_from_reset = True
        preview_checkbox.restore_state = False
        self.create_button = create_button
        self.finalize_func = finalize_func
        self.message_func = message_func or self.logger.info
        self.validation_func = validation_func
        self.select_result_checkbox = select_result_checkbox
        self.result_provider = result_provider
        self.reselect_on_disable = reselect_on_disable
        self.require_preview = require_preview
        self.undo_message = undo_message
        self.restore_func = restore_func

        self._enabled = False
        # Set while the checkbox is checked FOR the user, so its toggled
        # signal does not re-enter the preview (its other listeners still hear
        # the change).
        self._setting_checkbox = False
        # Re-entry guard: an operation or a rollback that emits a signal wired
        # to refresh (a selection change, a widget the rollback touches) must
        # not start a second pass over the one being built or undone.
        self._refresh_in_progress = False
        self._in_recovery = False

        # The tools' .ui files ship the commit button disabled (the old gated
        # contract); previewing is optional, so the state is asserted here.
        self._sync_commit_enabled(False)
        self.window = self._find_window()
        self._setup_ui_connections()
        self.init_show_hide_behavior(enable_on_show, disable_on_hide)

        PreviewController._instances.add(self)

    # ------------------------------------------------------------------ setup
    def _find_window(self):
        """A weak reference to the widgets' window, or None."""
        for widget in (self.create_button, self.preview_checkbox):
            try:
                window = widget.window() if hasattr(widget, "window") else None
            except Exception as e:
                self.logger.warning(f"Could not read the preview's window: {e}")
                continue
            if window is not None:
                try:
                    return weakref.ref(window)
                except TypeError:
                    return lambda window=window: window
        return None

    def _setup_ui_connections(self) -> None:
        self.preview_checkbox.toggled.connect(self._on_toggled)
        self.create_button.clicked.connect(self.finalize_changes)
        if self.select_result_checkbox is not None and self.result_provider is not None:
            # A toggle (de)selects the current result at once, never a re-run.
            self.select_result_checkbox.toggled.connect(self._on_select_result_toggled)

    def init_show_hide_behavior(self, enable_on_show: bool, disable_on_hide: bool) -> None:
        """Hook the window's show / hide to the preview.

        Parameters:
            enable_on_show: Start the preview each time the window shows.
            disable_on_hide: Discard the preview when the window hides.
        """
        self.enable_on_show = enable_on_show
        self.disable_on_hide = disable_on_hide
        window = self.window() if self.window else None
        if window is None:
            return
        try:
            if hasattr(window, "on_show"):
                window.on_show.connect(self.conditionally_enable)
            if hasattr(window, "on_hide"):
                window.on_hide.connect(self.conditionally_disable)
        except Exception as e:
            self.logger.warning(f"Show/hide signal setup failed: {e}")

    def conditionally_enable(self) -> None:
        """Start the preview if :attr:`enable_on_show` (the window showed)."""
        if self.enable_on_show:
            self.enable()

    def conditionally_disable(self) -> None:
        """Discard the preview if :attr:`disable_on_hide` (the window hid)."""
        if self.disable_on_hide:
            self.disable()

    # --------------------------------------------------------------- lifecycle
    @property
    def is_enabled(self) -> bool:
        """Whether a preview is running."""
        return self._enabled

    def toggle(self, state: bool) -> None:
        """Start (*state*) or discard the preview."""
        if state:
            self.enable()
        else:
            self.disable()

    def validate_operation(self, objects: List[Any]) -> bool:
        """Whether *validation_func* accepts *objects* (none given: True)."""
        if self.validation_func:
            try:
                return bool(self.validation_func(objects))
            except Exception as e:
                self.logger.warning(f"Validation function failed: {e}")
                return False
        return True

    @_PreviewControllerInternal._safe
    def enable(self) -> None:
        """Start the preview on the selection (running: a no-op)."""
        if self._enabled:
            return
        objects = self._gated_selection()
        # The precondition runs before the capture, so the capture holds the
        # state the preview starts from; a failed one aborts the enable.
        if objects is None or not self._prepare(objects):
            self._set_checkbox(False)
            return
        self.session.begin(objects)
        self._enabled = True
        if self._refresh_in_progress:
            # Re-entered from inside another step, which owns the critical
            # section: the state is set, its pass is that step's.
            self._set_checkbox(True)
            self._sync_commit_enabled(True)
            return
        # Taken BEFORE the box is checked: the check reaches the box's other
        # listeners, and one that refreshes must not run a pass ahead of this.
        self._refresh_in_progress = True
        try:
            self._set_checkbox(True)
            self._sync_commit_enabled(True)
            self._run_pass()
        finally:
            self._refresh_in_progress = False

    @_PreviewControllerInternal._safe
    def refresh(self, *args) -> None:
        """Roll the running preview back and run it again (an option changed;
        no preview running: a no-op)."""
        if not self._enabled or self._refresh_in_progress:
            return
        self._refresh_in_progress = True
        try:
            self.session.rollback()
            self._run_pass()
        finally:
            self._refresh_in_progress = False

    @_PreviewControllerInternal._safe
    def disable(self) -> None:
        """Discard the preview: roll it back without committing."""
        if self._refresh_in_progress:
            return
        self._refresh_in_progress = True
        try:
            if self._enabled:
                self.session.rollback()
                self._discard()
            else:
                self._set_off()
        finally:
            self._refresh_in_progress = False

    @_PreviewControllerInternal._safe
    def finalize_changes(self) -> None:
        """Commit: keep the running preview, or run the operation once on the
        selection with none running (``require_preview``: a no-op), as one undo
        step the ``finalize_func`` step and Select Result are part of."""
        if self._refresh_in_progress:
            return
        previewing = self._enabled
        if not previewing and self.require_preview:
            return
        objects = None if previewing else self._gated_selection()
        if not previewing and objects is None:
            return

        self._refresh_in_progress = True
        try:
            with self.session.undo_step(self._undo_name()) as step:
                if previewing:
                    self.session.commit()
                elif not self._prepare(objects):
                    # Refused (reason reported): nothing committed, no step.
                    getattr(step, "cancel", lambda: None)()
                    return
                else:
                    self.session.apply(objects)
                self._set_off()
                # The step's own work is done: a signal its finalize step
                # emits may start what it likes.
                self._refresh_in_progress = False
                self._call_hook(self.finalize_func, "finalize_func")
                # After finalize_func, which can change the selection.
                self._apply_select_result(committed=True)
        except Exception as e:
            # The operation failed mid-commit: what it did is one undo step.
            self.logger.exception(f"The commit raised: {e}")
            self.message_func(self._format_op_error(e))
            if previewing:
                # The commit rolled the preview back before it failed: end it
                # as a discard does (a host reasserts what its rollback drops).
                try:
                    self.session.discard(self.reselect_on_disable)
                except Exception:
                    self.logger.exception("discard after a failed commit raised")
            self._set_off()
        finally:
            self._refresh_in_progress = False

    def cleanup(self) -> None:
        """Discard a running preview and forget this one."""
        try:
            PreviewController._instances.discard(self)
            # getattr: a constructor that raised leaves a half-built instance.
            if getattr(self, "_enabled", False):
                self.disable()
        except Exception as e:
            logging.getLogger(__name__).error(f"Cleanup error: {e}")

    def __del__(self):
        self.cleanup()

    # ---------------------------------------------------------------- internals
    def _undo_name(self) -> str:
        return (
            self.undo_message
            or type(self.operation_instance).__name__
            or "PreviewCommit"
        )

    def _gated_selection(self) -> Optional[List[Any]]:
        """The selection, or None (the reason reported) when the operation
        must not run on it. Gates a preview and a commit alike."""
        objects = list(self.session.selection() or [])
        if not objects:
            self.message_func("No objects selected.")
            return None
        if not self.validate_operation(objects):
            self.message_func("Operation validation failed.")
            return None
        return objects

    def _prepare(self, objects: Sequence[Any]) -> bool:
        """Run the operation's ``prepare_operation``; False (reported) when it
        raised."""
        prepare = getattr(self.operation_instance, "prepare_operation", None)
        if not callable(prepare):
            return True
        try:
            prepare(list(objects))
        except Exception as e:
            self.logger.exception(f"prepare_operation raised: {e}")
            self.message_func(self._format_op_error(e))
            return False
        return True

    def _run_pass(self) -> None:
        """One preview pass; a failed one is reported and turns the preview off.

        Called inside the refresh critical section only.
        """
        try:
            self.session.run()
        except Exception as e:
            self.logger.exception(f"perform_operation raised: {e}")
            self.message_func(self._format_op_error(e))
            # A failed pass is no preview: left on, the checked box claimed a
            # preview that is not there, over what the pass left behind.
            try:
                self.session.rollback()
            except Exception:
                self.logger.exception("rollback after a failed preview raised")
            self._discard()
            return
        self._apply_select_result()

    def _discard(self) -> None:
        """End a rolled-back preview: its restore hook, the session's discard,
        the off state."""
        with self.session.unrecorded():
            self._call_hook(self.restore_func, "restore_func")
        self.session.discard(self.reselect_on_disable)
        self._set_off()

    def _set_off(self) -> None:
        self._enabled = False
        self._set_checkbox(False)
        self._sync_commit_enabled(False)

    def _call_hook(self, hook: Optional[Callable], name: str) -> None:
        """Call a panel hook; a failure is logged, never raised: the lifecycle
        step it belongs to has happened either way."""
        if not hook:
            return
        try:
            hook()
        except Exception as e:
            self.logger.exception(f"{name} raised: {e}")

    def _on_toggled(self, state) -> None:
        if self._setting_checkbox:
            return
        self.toggle(bool(state))

    def _set_checkbox(self, checked: bool) -> None:
        """Check or uncheck the box for the user without re-entering the
        preview."""
        self._setting_checkbox = True
        try:
            self.preview_checkbox.setChecked(checked)
        finally:
            self._setting_checkbox = False

    def _sync_commit_enabled(self, previewing: bool) -> None:
        """The commit button waits for a preview only under ``require_preview``."""
        try:
            self.create_button.setEnabled(previewing or not self.require_preview)
        except Exception as e:  # a duck-typed or dead widget never aborts
            self.logger.debug(f"create_button.setEnabled failed: {e}")

    def _on_select_result_toggled(self, *args) -> None:
        self._apply_select_result()

    def _apply_select_result(self, committed: bool = False) -> None:
        """Apply the Select Result toggle to the operation's current result
        (unconfigured: a no-op). Cosmetic, so a failure is logged only."""
        if self.select_result_checkbox is None or self.result_provider is None:
            return
        try:
            self.session.select_result(
                self.select_result_checkbox, self.result_provider(), committed
            )
        except Exception:
            self.logger.exception("Select Result apply failed")
