# !/usr/bin/python
# coding=utf-8
"""The shared core of uitk's item-view format mixins.

``CellFormatMixin`` (``tableWidget.py``) and ``TreeFormatMixin``
(``treeWidget.py``) register per-item / per-column formatters and colour items
by a semantic key. What they share -- the semantic colour map, the formatter
store, the colour resolution with its cached-default fallback, and the
signal-blocked formatting pass -- lives here once, so the two cannot drift
again (the tree copy once lacked the table's ``"current"`` key, and a consumer
reading it off a tree hit a ``KeyError``). Each subclass keeps only what its
item model makes different: how an item is addressed (row/col vs item/col) and
how its roles are set.
"""

import logging
from contextlib import contextmanager
from typing import Callable, Tuple

from uitk.widgets.mixins.convert import ConvertMixin

logger = logging.getLogger(__name__)


class ItemFormatMixin(ConvertMixin):
    """Formatter store + semantic colours shared by the table and tree mixins."""

    #: Semantic key -> (foreground, background). ``None`` leaves that role alone.
    ACTION_COLOR_MAP = {
        "valid": ("#3C8D3C", "#E6F4EA"),
        "invalid": ("#B97A7A", "#FBEAEA"),
        "warning": ("#B49B5C", "#FFF6DC"),
        "info": ("#6D9BAA", "#E2F3F9"),
        "inactive": ("#AAAAAA", None),
        "current": ("#C4A44A", None),
        "reset": (None, None),
    }

    @staticmethod
    def _set_formatter(store: dict, key, formatter, append: bool) -> None:
        """Replace (or, with *append*, extend) the formatters under *key*."""
        if append:
            store.setdefault(key, []).append(formatter)
        else:
            store[key] = [formatter]

    def _valid_color(
        self, color, color_type: str, defaults: Callable[[], Tuple[str, str]]
    ):
        """*color* as a ``QColor``; else the item's cached default for
        *color_type* (``"fg"`` / ``"bg"``); else ``None``, with a warning.

        *defaults* is called only when *color* does not convert: reading the
        defaults caches them, and an item that is recoloured must not have its
        current (already formatted) colours cached as its defaults.
        """
        try:
            return self.to_qobject(color, "QColor")
        except Exception:
            pass

        cached = defaults()[0 if color_type == "fg" else 1]
        try:
            return self.to_qobject(cached, "QColor")
        except Exception:
            logger.warning(
                "Invalid %s color: %r, and fallback %r failed. Using None.",
                color_type,
                color,
                cached,
            )
            return None

    @contextmanager
    def _formatting_signals_blocked(self):
        """Block the view's signals for a formatting pass.

        A formatter changes item roles (foreground/background), which fires the
        view's item-changed signal -> the edit handler -> the formatters again:
        unbounded recursion on a view with many formatted items.
        """
        was_blocked = self.signalsBlocked()
        self.blockSignals(True)
        try:
            yield
        finally:
            self.blockSignals(was_blocked)
