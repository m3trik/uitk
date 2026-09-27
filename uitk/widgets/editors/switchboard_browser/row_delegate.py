# !/usr/bin/python
# coding=utf-8
"""How a browser row paints: the name, the tag chips, and the inline tag editor."""

from __future__ import annotations

from typing import Optional

import pythontk as ptk
from qtpy import QtCore, QtGui, QtWidgets

from .model import SwitchboardBrowserModel


# ── Row delegate ──────────────────────────────────────────────────────────────


# Color palette for the row paint, sourced from pythontk so we get the same
# desaturated pastel set used elsewhere in the ecosystem (status badges,
# diff trees, etc.) and stay consistent if those palettes are tweaked later.
_STATUS_PALETTE = ptk.Palette.status()
_UI_PALETTE = ptk.Palette.ui()
_NAME_COLOR = _UI_PALETTE["text"].hex  # neutral text
_NAME_VISIBLE_COLOR = _STATUS_PALETTE["warn"].fg.hex  # warm gold (visible)
_INHERITED_TAG_COLOR = _STATUS_PALETTE["locked"].fg.hex  # dimmed grey
_FILE_TAG_COLOR = _STATUS_PALETTE["info"].fg.hex  # soft steel-blue
_KIND_CHIP_COLOR = _STATUS_PALETTE["info"].fg.hex  # same family as file tags

# Kind chips suppress the default "ui_file" chip — it's the dominant
# population and rendering one for every row would be visual noise.
# External / future kinds get an explicit chip so users can tell rows
# apart at a glance and filter on the kind via the tag search.
_KIND_CHIP_LABELS = {
    "external_subprocess": "external",
    "external_in_process": "external:in-proc",
    "editor": "editor",
}


class _BrowserRowDelegate(QtWidgets.QStyledItemDelegate):
    """Per-column renderer for the browser table.

    Column 0 (Name): bold; gold + italic when the UI is currently visible.
    Column 1 (Tags): mixed-source chips. Inherited tags (filename +
        source-directory) are gray + italic to signal they're read-only.
        File tags (XML ``uitk_tags``) are teal + regular weight; these are
        what inline-editing modifies.

    Inline editing on the Tags column edits only the file-tags portion as
    a comma-separated string. Inherited tags are not shown in the editor —
    they live elsewhere and editing them here would be misleading.

    Selection / hover styling comes from the global QSS
    (``QAbstractItemView::item:selected`` / ``:hover``) — the delegate
    deliberately does *not* mute ``State_Selected`` so the standard blue
    fill paints through behind the HTML chips, the same as a default
    item view would render.
    """

    _MARGIN = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = QtGui.QTextDocument()
        self._doc.setDocumentMargin(0)
        # No line wrapping in cells — long tag strings should clip
        # horizontally (and scroll on column resize), not wrap into a
        # second line that gets cropped by the 22px row height. Default
        # QTextDocument wraps at the set textWidth; turn that off here
        # once. The textWidth set in paint() still controls the painted
        # extent for clipping, just without forcing a line break.
        _opt = QtGui.QTextOption()
        _opt.setWrapMode(QtGui.QTextOption.NoWrap)
        self._doc.setDefaultTextOption(_opt)

    def _name_html(self, index) -> str:
        from html import escape

        name = index.data(SwitchboardBrowserModel.NameRole) or ""
        visible = bool(index.data(SwitchboardBrowserModel.VisibleRole))
        if visible:
            return (
                f'<span style="color:{_NAME_VISIBLE_COLOR};font-weight:bold;'
                f'font-style:italic">{escape(name)}</span>'
            )
        return (
            f'<span style="color:{_NAME_COLOR};font-weight:bold">{escape(name)}</span>'
        )

    def _tags_html(self, index) -> str:
        from html import escape

        inherited = index.data(SwitchboardBrowserModel.InheritedTagsRole) or []
        file_tags = index.data(SwitchboardBrowserModel.FileTagsRole) or []
        kind = index.data(SwitchboardBrowserModel.KindRole) or ""
        # "Hide inherited tags" lives on the owning browser. The delegate
        # is parented to it, so a quick parent walk reaches the toggle
        # without coupling the delegate to a Switchboard import.
        browser = self.parent()
        hide_inherited = bool(getattr(browser, "hide_inherited_tags", False))
        if hide_inherited:
            inherited = []
        chips = []
        # Kind chip first when the kind has an explicit label — lets the
        # eye anchor "what kind of thing am I looking at" before scanning
        # tags. .ui-backed entries get no chip (they're the default and
        # rendering one for every row is noise).
        kind_label = _KIND_CHIP_LABELS.get(kind)
        if kind_label:
            chips.append(
                f'<span style="color:{_KIND_CHIP_COLOR};font-weight:bold">'
                f"⟨{escape(kind_label)}⟩</span>"
            )
        # Inherited tags — italic to signal "not editable here"
        for t in sorted(inherited):
            chips.append(
                f'<span style="color:{_INHERITED_TAG_COLOR};font-style:italic">'
                f"#{escape(t)}</span>"
            )
        for t in sorted(file_tags):
            chips.append(f'<span style="color:{_FILE_TAG_COLOR}">#{escape(t)}</span>')
        return " ".join(chips)

    def _build_html(self, index) -> Optional[str]:
        col = index.column()
        if col == SwitchboardBrowserModel.COL_NAME:
            return self._name_html(index)
        if col == SwitchboardBrowserModel.COL_TAGS:
            return self._tags_html(index)
        return None

    def paint(self, painter, option, index):
        html = self._build_html(index)
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if html is not None:
            # Suppress the default text — we draw our own HTML on top of
            # the cell background.  Leaving ``opt.text`` populated would
            # render the plain string under the HTML chips.
            opt.text = ""

        style = opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        if html is not None:
            self._doc.setHtml(html)
            self._doc.setTextWidth(option.rect.width() - 2 * self._MARGIN)
            painter.save()
            painter.translate(
                option.rect.left() + self._MARGIN, option.rect.top() + self._MARGIN
            )
            clip = QtCore.QRectF(
                0, 0, option.rect.width() - 2 * self._MARGIN, option.rect.height()
            )
            self._doc.drawContents(painter, clip)
            painter.restore()

    def sizeHint(self, option, index):
        html = self._build_html(index)
        if html is None:
            return super().sizeHint(option, index)
        self._doc.setHtml(html)
        self._doc.setTextWidth(option.rect.width() - 2 * self._MARGIN)
        return QtCore.QSize(
            int(self._doc.idealWidth()) + 2 * self._MARGIN,
            int(self._doc.size().height()) + 2 * self._MARGIN,
        )

    # ── Inline editing on the Tags column ──────────────────────────

    def createEditor(self, parent, option, index):
        if index.column() != SwitchboardBrowserModel.COL_TAGS:
            return super().createEditor(parent, option, index)
        editor = QtWidgets.QLineEdit(parent)
        editor.setPlaceholderText("comma-separated file tags")
        return editor

    def setEditorData(self, editor, index):
        if index.column() != SwitchboardBrowserModel.COL_TAGS:
            return super().setEditorData(editor, index)
        # Edit only the file-tags portion. Inherited tags aren't shown here
        # because editing them would be a lie — they come from filename or
        # registration, not from this file's XML. Tooltip surfaces the
        # inherited set so the user knows nothing was dropped.
        file_tags = index.data(SwitchboardBrowserModel.FileTagsRole) or []
        inherited = index.data(SwitchboardBrowserModel.InheritedTagsRole) or []
        editor.setText(", ".join(file_tags))
        if inherited:
            inh_str = ", ".join(f"#{t}" for t in inherited)
            editor.setToolTip(
                f"Editing file tags only.\nInherited (not editable here): {inh_str}"
            )
        else:
            editor.setToolTip("Comma-separated tags stored in this .ui file.")

    def setModelData(self, editor, model, index):
        if index.column() != SwitchboardBrowserModel.COL_TAGS:
            return super().setModelData(editor, model, index)
        model.setData(index, editor.text(), QtCore.Qt.EditRole)

    def eventFilter(self, editor, event):
        """Make Esc always dismiss the editor (cancel without commit).

        QLineEdit in modern Qt swallows Esc to revert an undoable
        change — so a user who types and then changes their mind
        sees the text clear but the editor stays open, forcing them
        to commit-or-keep-typing. That reads as "I can't exit edit
        mode without making an entry."

        Intercept Esc here and emit ``closeEditor`` with NoHint so
        the view tears the editor down regardless of QLineEdit's
        internal undo state. Other keys (Tab, Enter, Return,
        Backtab) keep their default handling from
        QStyledItemDelegate.
        """
        if (
            isinstance(editor, QtWidgets.QLineEdit)
            and event.type() == QtCore.QEvent.KeyPress
            and event.key() == QtCore.Qt.Key_Escape
        ):
            # NoHint = cancel; commit path is via Enter/Return only.
            self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)
            return True
        return super().eventFilter(editor, event)
