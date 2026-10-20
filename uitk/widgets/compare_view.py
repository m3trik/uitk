# !/usr/bin/python
# coding=utf-8
"""Two images compared: wiped, side by side, blinked, or one at a time."""

from typing import Any, Mapping, Sequence

from qtpy import QtCore, QtWidgets

from uitk.widgets.image_view import ImageView
from uitk.widgets.mixins.attributes import AttributesMixin


class CompareView(QtWidgets.QWidget, AttributesMixin):
    """Image A against image B, the ways a compositor's viewer compares them.

    Modes (:attr:`MODES`): ``split`` -- B wiped over A, the line dragged
    sideways; ``side`` -- A and B side by side, zoomed and panned together;
    ``blink`` -- A, with B while Space is held (:meth:`blink`); ``a`` / ``b``
    -- one alone. Each image is anything :class:`ImageView` shows; a third
    picture (a difference) is the caller's to make and show as A in mode ``a``.
    The overlays and the hover pixel are the inner views'.

    Signals:
        mode_changed(str): The mode changed.
        overlay_clicked(object): An overlay's key, or ``None`` (the image).
        hovered(int, int): The image pixel under the cursor, ``(-1, -1)`` off it.
    """

    designer_spec = {"icon": "compare", "object_name": "compare_view", "size": (480, 280)}

    MODES = ("split", "side", "blink", "a", "b")

    mode_changed = QtCore.Signal(str)
    overlay_clicked = QtCore.Signal(object)
    hovered = QtCore.Signal(int, int)

    def __init__(self, parent=None, mode: str = "split", **kwargs):
        super().__init__(parent)
        self.view_a = ImageView(self)
        self.view_b = ImageView(self)
        self._caption_a = QtWidgets.QLabel(self)
        self._caption_b = QtWidgets.QLabel(self)
        self._caption_b.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        captions = QtWidgets.QHBoxLayout()
        captions.setContentsMargins(4, 0, 4, 0)
        captions.addWidget(self._caption_a)
        captions.addStretch(1)
        captions.addWidget(self._caption_b)
        views = QtWidgets.QHBoxLayout()
        views.setContentsMargins(0, 0, 0, 0)
        views.setSpacing(2)
        views.addWidget(self.view_a)
        views.addWidget(self.view_b)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(captions)
        layout.addLayout(views, 1)

        self._images: list = [None, None]
        self._labels = ["A", "B"]
        self._mode = mode if mode in self.MODES else "split"
        self._split = 0.5
        self._blinking = False
        self._syncing = False
        for view in (self.view_a, self.view_b):
            view.overlay_clicked.connect(self.overlay_clicked)
            view.hovered.connect(self.hovered)
            view.view_changed.connect(lambda v=view: self._lock(v))
        self.view_a.wipe_moved.connect(self._wiped)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._refresh()
        self.set_attributes(**kwargs)

    # ------------------------------------------------------------------ what it shows
    def set_images(self, a: Any, b: Any) -> None:
        """Image A and image B (either may be ``None``)."""
        # Converted once: a blink or mode switch re-shows them, and an
        # array's conversion is the slow part.
        self._images = [ImageView.to_pixmap(a), ImageView.to_pixmap(b)]
        self._refresh()

    def set_labels(self, a: str, b: str) -> None:
        """What each image is called, in the captions."""
        self._labels = [str(a), str(b)]
        self._refresh()

    def set_mode(self, mode: str) -> None:
        """One of :attr:`MODES`.

        Raises:
            ValueError: an unknown mode.
        """
        if mode not in self.MODES:
            raise ValueError(f"Unknown mode {mode!r}; one of {', '.join(self.MODES)}.")
        if mode == self._mode:
            return
        self._mode = mode
        self._blinking = False
        self._refresh()
        self.mode_changed.emit(mode)

    def mode(self) -> str:
        return self._mode

    def blink(self, showing_b: bool) -> None:
        """In ``blink`` mode, show B (True) or A (False)."""
        self._blinking = bool(showing_b)
        if self._mode == "blink":
            self._refresh()

    def split_position(self) -> float:
        """Where the ``split`` mode's line is (0..1 of the width)."""
        return self._split

    def set_split_position(self, position: float) -> None:
        self._split = min(1.0, max(0.0, float(position)))
        if self._mode == "split":
            self.view_a.set_wipe_position(self._split)

    def set_overlays(self, overlays: Sequence[Mapping[str, Any]]) -> None:
        """Draw *overlays* over both images (see :meth:`ImageView.set_overlays`)."""
        self.view_a.set_overlays(overlays)
        self.view_b.set_overlays(overlays)

    def fit(self) -> None:
        self.view_a.fit()
        self.view_b.fit()

    # ------------------------------------------------------------------ internals
    def _refresh(self) -> None:
        a, b = self._images
        label_a, label_b = self._labels
        mode = self._mode
        self.view_b.setVisible(mode == "side")
        if mode == "split":
            self.view_a.set_image(a)
            self.view_a.set_wipe(b, self._split)
            captions = (label_a, label_b)
        elif mode == "side":
            self.view_a.set_image(a)
            self.view_a.set_wipe(None)
            self.view_b.set_image(b)
            if self.view_a.fitting():
                self.view_b.fit()
            else:
                self.view_b.set_view_state(self.view_a.view_state())
            captions = (label_a, label_b)
        elif mode == "blink":
            shown = b if self._blinking else a
            self.view_a.set_image(shown)
            self.view_a.set_wipe(None)
            captions = (
                label_b if self._blinking else label_a,
                f"hold Space: {label_a if self._blinking else label_b}",
            )
        else:
            self.view_a.set_image(a if mode == "a" else b)
            self.view_a.set_wipe(None)
            captions = (label_a if mode == "a" else label_b, "")
        self._caption_a.setText(captions[0])
        self._caption_b.setText(captions[1])

    def _lock(self, moved: ImageView) -> None:
        """Side by side, the other view follows the one the user framed."""
        if self._mode != "side" or self._syncing:
            return
        other = self.view_b if moved is self.view_a else self.view_a
        self._syncing = True
        try:
            other.set_view_state(moved.view_state())
        finally:
            self._syncing = False

    def _wiped(self, position: float) -> None:
        self._split = position

    def keyPressEvent(self, event) -> None:
        if (
            event.key() == QtCore.Qt.Key_Space
            and not event.isAutoRepeat()
            and self._mode == "blink"
        ):
            self.blink(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if (
            event.key() == QtCore.Qt.Key_Space
            and not event.isAutoRepeat()
            and self._mode == "blink"
        ):
            self.blink(False)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        if self._blinking:  # a release the widget never sees must not leave B up
            self.blink(False)
        super().focusOutEvent(event)
