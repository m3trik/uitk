# !/usr/bin/python
# coding=utf-8
"""Unit tests for ``uitk.widgets.formPanel.FormPanel`` and the two switchboard
entry points over it — ``form_panel`` (modeless, runs in place) and
``form_dialog`` (modal, returns the answers).

The widget exists because a sequence of single-purpose dialogs handles "two
answers the user must tell apart" badly: two native folder pickers shown back
to back are the SAME widget with different captions, so which one means
"search here" and which means "write here" lives entirely in a title bar — and
the answer moves when one of them is skipped. That is the mayatk Texture Path
Editor's reported Find & Copy confusion (2026-08-25), where users picked their
texture folder as the DESTINATION.

What this file pins beyond that: the panel is a real uitk tool window (themed
Header / Footer chrome, not a host-default QDialog), a row's ``hint`` is a
formatted TOOLTIP rather than a wall of prose under the controls, the panel's
ONE text area is the output pane a run-in-place handler logs into, and the
validation reason lives in the footer.

Run standalone: python -m test.test_form_panel
"""

import unittest
from unittest.mock import patch

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets

from uitk.switchboard.utils import SwitchboardUtilsMixin
from uitk.widgets.formPanel import FormPanel


class FormPanelTestCase(QtBaseTestCase):
    """Shared construction helpers."""

    FIELDS = [
        {"name": "src", "kind": "dir", "label": "Search in", "value": "C:/from"},
        {"name": "dest", "kind": "dir", "label": "Copy into", "value": "C:/to"},
    ]

    def _panel(self, fields=None, **kwargs):
        kwargs.setdefault("output", False)
        panel = SwitchboardUtilsMixin.form_panel(
            self.FIELDS if fields is None else fields, **kwargs
        )
        self.addCleanup(panel.deleteLater)
        self.addCleanup(panel.close)
        return panel

    @staticmethod
    def _edits(panel):
        return panel.findChildren(QtWidgets.QLineEdit)

    @staticmethod
    def _ok(panel):
        return panel.button_box.button(QtWidgets.QDialogButtonBox.Ok)

    @staticmethod
    def _browse_buttons(panel):
        """The pickers — one option button inside each path editor, row order."""
        from uitk.widgets.optionBox._optionBox import OptionBoxContainer

        return [
            b
            for b in panel.findChildren(QtWidgets.QAbstractButton)
            if isinstance(b.parent(), OptionBoxContainer)
        ]


class TestFormPanelFields(FormPanelTestCase):
    """The rows: what is on screen, and what each one reports."""

    def test_every_field_is_reported_keyed_by_name(self):
        self.assertEqual(self._panel().values(), {"src": "C:/from", "dest": "C:/to"})

    def test_edited_values_are_reported(self):
        panel = self._panel()
        self._edits(panel)[1].setText("C:/elsewhere")
        self.assertEqual(panel.values()["dest"], "C:/elsewhere")

    def test_values_are_stripped(self):
        panel = self._panel()
        self._edits(panel)[0].setText("  C:/x  ")
        self.assertEqual(panel.values()["src"], "C:/x")

    def test_set_values_writes_back(self):
        panel = self._panel()
        panel.set_values({"dest": "C:/written", "nosuchrow": "ignored"})
        self.assertEqual(panel.values()["dest"], "C:/written")

    def test_a_field_needs_a_name(self):
        with self.assertRaises(ValueError):
            self._panel([{"label": "nameless"}])

    def test_no_fields_is_refused(self):
        with self.assertRaises(ValueError):
            self._panel([])

    def test_set_fields_replaces_the_rows(self):
        """A reopened panel re-reads live state; the old rows must not survive."""
        panel = self._panel()
        panel.set_fields([{"name": "only", "label": "Only", "value": "x"}])
        self.assertEqual(panel.values(), {"only": "x"})
        self.assertEqual(len(self._edits(panel)), 1)

    # -- the reason it exists: two rows, both visible ---------------------

    def test_both_paths_are_on_screen_at_once(self):
        """The whole point — nothing to confuse, and no order to remember."""
        panel = self._panel()
        self.assertEqual(len(self._edits(panel)), 2)
        labels = [w.text() for w in panel.findChildren(QtWidgets.QLabel)]
        self.assertIn("Search in", labels)
        self.assertIn("Copy into", labels)


class TestFormPanelAdd(FormPanelTestCase):
    """``add`` is the base's, plus field registration — and reads the same."""

    def test_a_positional_label_means_label_here_too(self):
        """The base takes the caption as its second positional; an override
        that put ``enabled_by`` there would silently rebind it."""
        panel = self._panel()
        widget = panel.add("LineEdit", "Extra", setObjectName="extra")
        caption = panel._companions["extra"][0]
        self.assertEqual(caption.text(), "Extra")
        self.assertIs(widget, panel.extra)

    def test_a_named_value_widget_joins_values(self):
        panel = self._panel()
        panel.add("CheckBox", setObjectName="opt", setChecked=True)
        self.assertTrue(panel.values()["opt"])

    def test_an_unnamed_or_non_value_widget_is_plain_content(self):
        panel = self._panel()
        panel.add("CheckBox")
        panel.add("PushButton", setObjectName="b_go")
        self.assertEqual(set(panel.values()), {"src", "dest"})
        self.assertIs(panel.b_go, panel.b_go)  # exposed all the same

    def test_clear_rows_drops_the_fields_with_the_rows(self):
        """A registry left behind would hand values() a deleted widget."""
        panel = self._panel()
        panel.clear_rows()
        self.assertEqual(panel.values(), {})
        self.assertEqual(panel._companions, {})


class TestFormPanelHints(FormPanelTestCase):
    """A hint is a TOOLTIP, not a paragraph parked under the row.

    A hint per row is a wall of prose the user reads past to reach the
    controls, and it is longest exactly when the form is busiest. On hover it
    is there at the one moment it is wanted, and the panel stays a form.
    """

    HINT = "3 unresolved texture(s), searched recursively"

    def _hinted(self):
        return self._panel([dict(self.FIELDS[0], hint=self.HINT)])

    def test_a_hint_is_not_a_label(self):
        panel = self._hinted()
        labels = [w.text() for w in panel.findChildren(QtWidgets.QLabel)]
        self.assertFalse(
            any(self.HINT in t for t in labels),
            f"the hint leaked back onto the form as a label: {labels}",
        )

    def test_a_hint_reaches_the_editor_as_formatted_rich_text(self):
        panel = self._hinted()
        tip = panel.editor("src").toolTip()
        self.assertIn(self.HINT, tip)
        self.assertIn("<b>Search in</b>", tip, "the label must title the tooltip")

    def test_the_whole_row_carries_the_same_tooltip(self):
        """Reachable from wherever the pointer already is — label and field."""
        panel = self._hinted()
        tip = panel.editor("src").toolTip()
        for widget in panel._companions["src"]:
            self.assertEqual(widget.toolTip(), tip)

    def test_the_picker_says_what_IT_does(self):
        """It is a button inside the field, not the field: the row's hint
        under it would name the wrong thing to click."""
        panel = self._hinted()
        self.assertIn("Browse", self._browse_buttons(panel)[0].toolTip())

    def test_an_explicit_tooltip_is_used_verbatim(self):
        panel = self._panel(
            [dict(self.FIELDS[0], hint="ignored", tooltip="<i>mine</i>")]
        )
        self.assertEqual(panel.editor("src").toolTip(), "<i>mine</i>")


class TestFormPanelMessage(FormPanelTestCase):
    """The optional line above the rows — prose, not a field caption."""

    def test_no_message_shows_nothing(self):
        """An empty line above the rows is a gap that reads as a bug."""
        self.assertTrue(self._panel()._message_label.isHidden())

    def test_a_message_is_shown_above_the_rows(self):
        panel = self._panel(message="Relocating 3 texture(s).")
        label = panel._message_label
        self.assertFalse(label.isHidden())
        self.assertEqual(label.text(), "Relocating 3 texture(s).")
        self.assertIs(panel.body_layout.itemAt(0).widget(), label)
        self.assertIs(panel.body_layout.itemAt(1).widget(), panel._rows_host)

    def test_a_message_is_not_a_field_caption(self):
        """It takes the caption's PLATE through its own selector, not the
        caption hook: that one is height-matched to the control beside it,
        and this one wraps."""
        label = self._panel(message="Wraps over several lines.")._message_label
        self.assertEqual(label.objectName(), "formPanelMessage")
        self.assertFalse(label.property("caption"))
        self.assertTrue(label.wordWrap())


class TestFormPanelPlaceholder(FormPanelTestCase):
    """What leaving a field EMPTY does, said where the empty field is.

    An optional field is a question the form will accept no answer to, and
    the tooltip is the wrong place to say what that answer MEANS: the user
    who leaves it empty is the one who never hovered it.
    """

    def test_a_placeholder_reaches_the_editor(self):
        panel = self._panel(
            [dict(self.FIELDS[0], placeholder="Leave empty to skip the 2 missing")]
        )
        self.assertEqual(
            panel.editor("src").placeholderText(),
            "Leave empty to skip the 2 missing",
        )

    def test_a_placeholder_is_not_a_value(self):
        """It must never be mistaken for an answer the form was given."""
        spec = dict(self.FIELDS[0], placeholder="Optional")
        spec.pop("value", None)
        panel = self._panel([spec])
        self.assertEqual(panel.values()["src"], "")

    def test_no_placeholder_leaves_the_field_blank(self):
        self.assertEqual(self._panel().editor("src").placeholderText(), "")


class TestFormPanelLayout(FormPanelTestCase):
    """The label sits to the LEFT of the control it names."""

    def _form(self, panel):
        return panel._rows_layout

    @staticmethod
    def _field_widgets(form, row):
        """The controls in *row*'s field cell.

        A path editor stands in its cell as its option-box container (the
        picker rides inside it), so a container is opened rather than
        counted: what the row OFFERS is the editor and its buttons.
        """
        from uitk.widgets.optionBox._optionBox import OptionBoxContainer

        item = form.itemAt(row, QtWidgets.QFormLayout.FieldRole)
        if item.widget() is not None:
            cells = [item.widget()]
        else:
            cell = item.layout()
            cells = [cell.itemAt(i).widget() for i in range(cell.count())]
        out = []
        for widget in cells:
            if isinstance(widget, OptionBoxContainer):
                out.extend(widget.findChildren(QtWidgets.QWidget))
            else:
                out.append(widget)
        return out

    def test_rows_are_a_form_not_a_stack(self):
        panel = self._panel()
        self.assertIsInstance(self._form(panel), QtWidgets.QFormLayout)

    def test_each_label_is_in_the_label_column_beside_its_editor(self):
        """Stacked headings read as twice as many controls as the form has,
        and push the output pane off the bottom."""
        panel = self._panel()
        form = self._form(panel)
        for row, name in enumerate(("src", "dest")):
            self.assertIs(
                form.itemAt(row, QtWidgets.QFormLayout.LabelRole).widget(),
                panel._companions[name][0],
            )
            self.assertIn(panel.editor(name), self._field_widgets(form, row))

    def test_a_checkbox_row_spans_both_columns(self):
        """Its label IS its text, so a label column entry would be an empty
        cell beside a control that already names itself."""
        panel = self._panel(
            [{"name": "widen", "kind": "check", "label": "Search everything"}]
        )
        form = self._form(panel)
        self.assertIsNone(form.itemAt(0, QtWidgets.QFormLayout.LabelRole))
        self.assertIs(
            form.itemAt(0, QtWidgets.QFormLayout.FieldRole).widget(),
            panel.editor("widen"),
        )

    def test_the_field_order_is_the_spec_order(self):
        """A caller placing an opt-in ABOVE the row it widens must get that."""
        panel = self._panel(
            [
                {"name": "widen", "kind": "check", "label": "Widen"},
                {"name": "src", "kind": "dir", "label": "Search in"},
            ]
        )
        form = self._form(panel)
        self.assertIs(
            form.itemAt(0, QtWidgets.QFormLayout.FieldRole).widget(),
            panel.editor("widen"),
        )
        self.assertIs(
            form.itemAt(1, QtWidgets.QFormLayout.LabelRole).widget(),
            panel._companions["src"][0],
        )


class TestFormPanelInlineFields(FormPanelTestCase):
    """A second answer that belongs WITH the first, in the same cell."""

    INLINE = [
        {
            "name": "mode",
            "kind": "choice",
            "label": "Operation",
            "items": ["Copy", "Move"],
            "value": "Copy",
            "inline": [
                {
                    "name": "dry_run",
                    "kind": "check",
                    "label": "Dry run",
                    "hint": "Report it, write nothing.",
                }
            ],
        },
        {"name": "dest", "kind": "dir", "label": "Copy into", "value": "C:/to"},
    ]

    def test_an_inline_field_is_read_like_any_other(self):
        panel = self._panel(self.INLINE)
        self.assertEqual(
            panel.values(), {"mode": "Copy", "dry_run": False, "dest": "C:/to"}
        )

    def test_an_inline_field_shares_its_host_s_row(self):
        """The point of it: no caption of its own, no row of its own."""
        panel = self._panel(self.INLINE)
        form = panel._rows_layout
        self.assertEqual(form.rowCount(), 2, "the inline field took a row of its own")
        cell = form.itemAt(0, QtWidgets.QFormLayout.FieldRole).layout()
        self.assertEqual(
            [cell.itemAt(i).widget() for i in range(cell.count())],
            [panel.editor("mode"), panel.editor("dry_run")],
        )

    def test_an_inline_field_revalidates_the_form(self):
        seen = []
        panel = self._panel(self.INLINE, validate=lambda v: seen.append(v) or "")
        panel.editor("dry_run").setChecked(True)
        self.assertTrue(seen[-1]["dry_run"])

    def test_an_inline_field_carries_its_own_hint(self):
        """It names something the row it rides does not."""
        panel = self._panel(self.INLINE)
        self.assertIn("Report it", panel.editor("dry_run").toolTip())
        self.assertNotIn("Report it", panel.editor("mode").toolTip())

    def test_an_inline_field_gets_the_same_width_as_its_host(self):
        """Two answers, one row: a full-width control beside a tick jammed
        into the margin reads as one control with a label stuck to it."""
        panel = self._panel(self.INLINE)
        panel.show()
        app.processEvents()
        self.assertEqual(panel.editor("mode").width(), panel.editor("dry_run").width())

    def test_a_companion_button_still_rides_at_its_own_width(self):
        """Only inline FIELDS split the row — a picker is a control ON the
        field, so the width stays with the path."""
        panel = self._panel(self.INLINE)
        panel.show()
        app.processEvents()
        editor = panel.editor("dest")
        self.assertGreater(editor.width(), self._browse_buttons(panel)[0].width() * 4)

    def test_an_inline_field_is_exposed_by_name(self):
        panel = self._panel(self.INLINE)
        self.assertIs(panel.dry_run, panel.editor("dry_run"))

    def test_an_unnamed_inline_field_is_refused(self):
        with self.assertRaises(ValueError):
            self._panel(
                [{"name": "mode", "kind": "check", "inline": [{"kind": "check"}]}]
            )


class TestFormPanelCaptionAlignment(FormPanelTestCase):
    """Where the caption's text sits in the plate that fills the column."""

    def _caption(self, panel, name):
        return panel._companions[name][0]

    def test_a_caption_reads_from_the_left_by_default(self):
        panel = self._panel()
        self.assertTrue(
            self._caption(panel, "src").alignment() & QtCore.Qt.AlignLeft,
            "a leading marker must line up down the column",
        )

    def test_a_caption_can_lead_into_the_control_beside_it(self):
        panel = self._panel([dict(self.FIELDS[0], label_align="right")])
        alignment = self._caption(panel, "src").alignment()
        self.assertTrue(alignment & QtCore.Qt.AlignRight)
        self.assertTrue(
            alignment & QtCore.Qt.AlignVCenter, "captions centre on the row"
        )

    def test_an_unknown_alignment_is_refused(self):
        """Silently left-aligning a typo is a layout bug found by eye."""
        with self.assertRaises(ValueError):
            self._panel([dict(self.FIELDS[0], label_align="middle")])


class TestFormPanelCaptionColumn(FormPanelTestCase):
    """The captions are a COLUMN — each carries an opaque plate, so a short
    one left at its text width ends the plate in mid-air."""

    WIDE = [
        {"name": "src", "kind": "dir", "label": "Search in a much longer caption"},
        {"name": "dest", "kind": "dir", "label": "Copy into"},
    ]

    def test_every_caption_fills_the_label_column(self):
        panel = self._panel(self.WIDE)
        panel.show()
        app.processEvents()
        widths = {panel._companions[n][0].width() for n in ("src", "dest")}
        self.assertEqual(len(widths), 1, f"ragged caption plates: {widths}")

    def test_the_column_is_the_widest_caption_not_more(self):
        """Filling the column must not WIDEN it — the field column pays for
        every pixel the captions take."""
        panel = self._panel(self.WIDE)
        panel.show()
        app.processEvents()
        widest = panel._companions["src"][0]
        self.assertEqual(widest.minimumWidth(), widest.sizeHint().width())


class TestFormPanelChrome(FormPanelTestCase):
    """It is a uitk tool window, not a host-default dialog."""

    def test_it_has_the_header_and_footer_chrome(self):
        panel = self._panel(title="Find & Copy Textures")
        self.assertIsNotNone(panel.header)
        self.assertIsNotNone(panel.footer)
        # ``title()``, not ``text()``: the label elides its display text to
        # whatever width the unshown window happens to have.
        self.assertEqual(panel.header.title(), "FIND & COPY TEXTURES")

    def test_it_is_a_frameless_top_level_window(self):
        """The chrome is drawn by the panel, so the window manager's must go."""
        panel = self._panel()
        flags = panel.windowFlags()
        self.assertTrue(flags & QtCore.Qt.FramelessWindowHint)
        # Mask the type out and compare it: Qt.Tool is a COMPOSITE, so a bare
        # ``flags & Qt.Window`` proves nothing.
        self.assertEqual(flags & QtCore.Qt.WindowType_Mask, QtCore.Qt.Window)

    def test_help_text_reaches_the_header(self):
        panel = self._panel(help_text="<b>what this does</b>")
        self.assertEqual(panel.header.help_text(), "<b>what this does</b>")
        self.assertIn("help", panel.header.buttons, "the ? button must appear")

    def test_the_ok_button_carries_the_verb(self):
        """The last thing read before committing must say what happens."""
        panel = self._panel(ok_text="Copy 12 files")
        self.assertEqual(self._ok(panel).text(), "Copy 12 files")

    def test_a_callable_ok_text_tracks_the_form(self):
        """A verb chosen ON the form must reach the button that names it."""
        panel = self._panel(
            [
                {"name": "mode", "kind": "choice", "items": ["Copy", "Move"]},
                *self.FIELDS,
            ],
            ok_text=lambda v: f"{v['mode']} 2 files",
        )
        self.assertEqual(self._ok(panel).text(), "Copy 2 files")
        panel.editor("mode").setCurrentIndex(1)
        self.assertEqual(self._ok(panel).text(), "Move 2 files")

    def test_a_modal_keeps_cancel(self):
        """Discarding really is one of the two answers there."""
        self.assertEqual(
            self._panel().button_box.button(QtWidgets.QDialogButtonBox.Cancel).text(),
            "Cancel",
        )

    def test_a_run_in_place_panel_has_no_reject_button(self):
        """The header already draws this window's close; a second one in the
        footer says nothing the first does not, and sits where the eye looks
        for the action."""
        panel = self._panel(on_run=lambda values: None)
        self.assertIsNone(panel.button_box.button(QtWidgets.QDialogButtonBox.Cancel))

    def test_an_explicit_cancel_text_forces_one_back(self):
        panel = self._panel(on_run=lambda values: None, cancel_text="Discard")
        button = panel.button_box.button(QtWidgets.QDialogButtonBox.Cancel)
        self.assertIsNotNone(button)
        self.assertEqual(button.text(), "Discard")


class TestFormPanelDisabledRows(FormPanelTestCase):
    def test_a_disabled_row_still_reports_its_value(self):
        """A settled step stays visible WITH its reason rather than vanishing
        and leaving a gap the user has to explain to themselves."""
        panel = self._panel(
            [
                dict(self.FIELDS[0], enabled=False, hint="all paths resolve"),
                self.FIELDS[1],
            ]
        )
        self.assertEqual(panel.values()["src"], "C:/from")
        self.assertFalse(self._edits(panel)[0].isEnabled())
        self.assertTrue(self._edits(panel)[1].isEnabled())


class TestFormPanelEnabledBy(FormPanelTestCase):
    """A checkbox switching a settled row back on."""

    ENABLED_BY_FIELDS = [
        {
            "name": "src",
            "kind": "dir",
            "label": "Search in",
            "value": "C:/from",
            "hint": "nothing needs finding",
            "enabled": False,
            "enabled_by": "widen",
        },
        {"name": "widen", "kind": "check", "label": "Search everything"},
    ]

    def _dependent(self, **kwargs):
        return self._panel(self.ENABLED_BY_FIELDS, **kwargs)

    def test_a_dependent_row_starts_disabled(self):
        self.assertFalse(self._dependent().editor("src").isEnabled())

    def test_ticking_the_driver_re_enables_the_row(self):
        """Without this the opt-in is unreachable: ticking a box beside a row
        that stays grey does nothing at all."""
        panel = self._dependent()
        self.assertFalse(panel.editor("src").isEnabled())
        panel.editor("widen").setChecked(True)
        self.assertTrue(panel.editor("src").isEnabled())

    def test_unticking_the_driver_disables_it_again(self):
        panel = self._dependent()
        panel.editor("widen").setChecked(True)
        panel.editor("widen").setChecked(False)
        self.assertFalse(panel.editor("src").isEnabled())

    def test_the_whole_row_greys_out_together(self):
        """Label and picker follow the editor, or the row reads as live."""
        panel = self._dependent()
        row = [*panel._companions["src"], self._browse_buttons(panel)[0]]
        for widget in row:
            self.assertFalse(widget.isEnabled())
        panel.editor("widen").setChecked(True)
        for widget in row:
            self.assertTrue(widget.isEnabled())

    def test_a_statically_enabled_row_ignores_the_driver(self):
        """``enabled: True`` wins — the dependency only ever ADDS a way on."""
        panel = self._panel(
            [dict(self.ENABLED_BY_FIELDS[0], enabled=True), self.ENABLED_BY_FIELDS[1]]
        )
        self.assertTrue(panel.editor("src").isEnabled())

    def test_an_unknown_enabled_by_is_ignored(self):
        """A typo must not crash the panel or freeze the row."""
        panel = self._panel(
            [dict(self.ENABLED_BY_FIELDS[0], enabled=True, enabled_by="nope")]
        )
        self.assertTrue(panel.editor("src").isEnabled())


class TestFormPanelValidation(FormPanelTestCase):
    """The reason lives in the FOOTER — the panel's one status line."""

    def _same_dir_validator(self, values):
        if values["src"] and values["src"] == values["dest"]:
            return "Destination is the search folder — nothing would move."
        return ""

    def _same(self, **kwargs):
        return self._panel(
            [
                dict(self.FIELDS[0], value="C:/same"),
                dict(self.FIELDS[1], value="C:/same"),
            ],
            validate=self._same_dir_validator,
            **kwargs,
        )

    def test_a_valid_form_enables_ok_and_says_nothing(self):
        panel = self._panel(validate=self._same_dir_validator)
        self.assertTrue(self._ok(panel).isEnabled())
        self.assertEqual(panel.footer.statusText(), "")

    def test_an_invalid_form_disables_ok_and_says_why(self):
        """The reported mistake, caught BEFORE any file is touched."""
        panel = self._same()
        self.assertFalse(self._ok(panel).isEnabled())
        self.assertIn("nothing would move", panel.footer.statusText())

    def test_the_reason_is_flagged_as_an_error(self):
        self.assertEqual(self._same().footer._status_level, "error")

    def test_validation_re_runs_as_the_user_types(self):
        """Typing out of the bad state must re-enable OK without a reopen."""
        panel = self._same()
        self.assertFalse(self._ok(panel).isEnabled())
        panel.editor("dest").setText("C:/different")
        self.assertTrue(self._ok(panel).isEnabled())
        self.assertEqual(panel.footer.statusText(), "")

    def test_a_rebuild_that_fails_the_same_way_still_says_why(self):
        """set_fields clears the footer; revalidate's no-op guard must not
        then skip re-writing an error just because the STRING is unchanged —
        that leaves OK disabled with the reason nowhere on screen."""
        panel = self._same()
        self.assertIn("nothing would move", panel.footer.statusText())
        panel.set_fields(
            [
                dict(self.FIELDS[0], value="C:/same"),
                dict(self.FIELDS[1], value="C:/same"),
            ]
        )
        self.assertFalse(self._ok(panel).isEnabled())
        self.assertIn("nothing would move", panel.footer.statusText())

    def test_an_invalid_form_cannot_be_accepted(self):
        ran = []
        panel = self._same(on_run=ran.append)
        panel._on_accept()
        self.assertEqual(ran, [], "an invalid form must not reach the handler")


class TestFormPanelBrowse(FormPanelTestCase):
    def test_the_picker_rides_inside_the_field_it_fills(self):
        """A *Browse…* beside the field spends the row's width on a caption;
        an option button spends an icon's worth, and the path keeps the
        rest — which is the one thing on the row never wide enough."""
        panel = self._panel()
        editor = panel.editor("src")
        self.assertIs(self._browse_buttons(panel)[0].parent(), editor.parent())
        titled = [
            b
            for b in panel._rows_host.findChildren(QtWidgets.QAbstractButton)
            if b.text()
        ]
        self.assertEqual(titled, [], "a titled button in the form is a Browse… again")

    def test_browse_writes_the_picked_folder_into_its_own_row(self):
        """The native picker survives as an option button — it is subordinate
        to a labelled field now, so its caption is no longer the only signal.
        """
        panel = self._panel()
        with patch.object(
            QtWidgets.QFileDialog,
            "getExistingDirectory",
            staticmethod(lambda *a, **k: "D:\\picked"),
        ):
            self._browse_buttons(panel)[1].click()
        self.assertEqual(panel.values()["dest"], "D:/picked")
        self.assertEqual(
            panel.values()["src"], "C:/from", "browse leaked into the other row"
        )

    def test_browse_is_not_the_default_button(self):
        """Return in a line edit must commit the form, not open a picker."""
        for button in self._browse_buttons(self._panel()):
            self.assertFalse(button.autoDefault())

    def test_the_busy_cursor_is_suspended_for_the_picker(self):
        panel = self._panel()
        with (
            patch.object(SwitchboardUtilsMixin, "_suspend_override_cursor") as suspend,
            patch.object(
                QtWidgets.QFileDialog,
                "getExistingDirectory",
                staticmethod(lambda *a, **k: ""),
            ),
        ):
            self._browse_buttons(panel)[0].click()
        suspend.assert_called()


class TestFormPanelRunInPlace(FormPanelTestCase):
    """The Scene Exporter shape: press the verb, watch it happen, run again."""

    def _running(self, handler, **kwargs):
        kwargs.setdefault("output", True)
        return self._panel(on_run=handler, **kwargs)

    def test_accept_runs_the_handler_with_the_values(self):
        seen = []
        panel = self._running(seen.append)
        panel._on_accept()
        self.assertEqual(seen, [{"src": "C:/from", "dest": "C:/to"}])

    def test_the_panel_stays_open_after_a_run(self):
        """A modal that has closed can neither show what it did nor be re-run."""
        panel = self._running(lambda values: None)
        panel.show()
        panel._on_accept()
        self.assertTrue(panel.isVisible())

    def test_the_handler_logs_into_the_one_output_pane(self):
        panel = self._running(lambda values: panel.logger.info("did the thing"))
        panel._on_accept()
        app.processEvents()
        self.assertIn("did the thing", panel.output.toPlainText())

    def test_each_run_starts_from_a_clean_pane(self):
        """Two runs' output read as one report otherwise."""
        panel = self._running(lambda values: panel.logger.info("run"))
        panel._on_accept()
        app.processEvents()
        panel._on_accept()
        app.processEvents()
        self.assertEqual(panel.output.toPlainText().count("run"), 1)

    def test_a_raising_handler_is_reported_not_raised(self):
        """A traceback in the DCC's script editor is exactly the 'look
        somewhere else' this panel exists to remove."""

        def boom(_values):
            raise RuntimeError("nope")

        panel = self._running(boom)
        panel._on_accept()  # must not raise
        app.processEvents()
        self.assertEqual(panel.footer.statusText(), "nope")
        self.assertIn("nope", panel.output.toPlainText())

    def test_the_button_comes_back_after_a_failure(self):
        def boom(_values):
            raise RuntimeError("nope")

        panel = self._running(boom)
        panel._on_accept()
        self.assertTrue(self._ok(panel).isEnabled())

    def test_a_failure_report_survives_the_revalidate(self):
        """The pass that re-enables the button must not wipe the reason."""

        def boom(_values):
            raise RuntimeError("nope")

        panel = self._running(boom, validate=lambda v: "")
        panel._on_accept()
        self.assertEqual(panel.footer.statusText(), "nope")

    def test_a_handler_that_set_its_own_status_keeps_it(self):
        panel = self._running(lambda values: panel.set_status("12 copied"))
        panel._on_accept()
        self.assertEqual(panel.footer.statusText(), "12 copied")

    def test_a_silent_handler_does_not_leave_the_placeholder_up(self):
        panel = self._running(lambda values: None)
        panel._on_accept()
        self.assertEqual(panel.footer.statusText(), "")

    def test_a_cooperative_cancel_is_reported_as_a_cancel(self):
        """``OperationCancelled`` is a BaseException so ordinary handlers can't
        swallow it — which means only this panel's own catch stops it escaping
        a Qt signal."""
        from pythontk.core_utils.cancel_scope import OperationCancelled

        def cancel(_values):
            raise OperationCancelled("user pressed Esc")

        panel = self._running(cancel)
        panel._on_accept()  # must not raise
        app.processEvents()
        self.assertEqual(panel.footer.statusText(), "Cancelled.")
        self.assertEqual(panel.footer._status_level, "warning")
        self.assertIn("Cancelled.", panel.output.toPlainText())

    def test_a_cancel_does_not_report_a_run(self):
        from pythontk.core_utils.cancel_scope import OperationCancelled

        seen = []

        def cancel(_values):
            raise OperationCancelled()

        panel = self._running(cancel)
        panel.ran.connect(seen.append)
        panel._on_accept()
        self.assertEqual(seen, [])
        self.assertTrue(self._ok(panel).isEnabled())

    def test_ran_is_emitted_with_the_values(self):
        seen = []
        panel = self._running(lambda values: None)
        panel.ran.connect(seen.append)
        panel._on_accept()
        self.assertEqual(seen, [{"src": "C:/from", "dest": "C:/to"}])

    def test_ran_is_not_emitted_when_the_handler_fails(self):
        seen = []

        def boom(_values):
            raise RuntimeError("nope")

        panel = self._running(boom)
        panel.ran.connect(seen.append)
        panel._on_accept()
        self.assertEqual(seen, [])


class TestFormPanelDryRun(FormPanelTestCase):
    """A handler that returns a callable previewed; the panel arms Apply."""

    def _previewing(self, commit=None, **kwargs):
        self.committed = []
        commit = commit or (lambda: self.committed.append(True))
        kwargs.setdefault("output", True)
        return self._panel(on_run=lambda values: commit, **kwargs)

    def _apply_btn(self, panel):
        return panel._apply_btn

    @staticmethod
    def _shown(button):
        """``isHidden``, not ``isVisible``: a child of an unshown window reads
        as invisible however it was set, so ``isVisible`` cannot tell an armed
        button from a hidden one here."""
        return not button.isHidden()

    def test_a_returned_callable_arms_apply(self):
        panel = self._previewing()
        self.assertIsNone(self._apply_btn(panel))
        panel._on_accept()
        self.assertIsNotNone(panel.pending_commit)
        self.assertTrue(self._shown(self._apply_btn(panel)))

    def test_the_footer_says_the_run_was_only_a_preview(self):
        panel = self._previewing()
        panel._on_accept()
        self.assertIn("Preview only", panel.footer.statusText())
        self.assertEqual(panel.footer._status_level, "warning")

    def test_apply_runs_the_held_call(self):
        panel = self._previewing()
        panel._on_accept()
        panel.apply_pending()
        self.assertEqual(self.committed, [True])

    def test_apply_disarms_itself(self):
        """The plan is spent; a button still offering it would commit twice."""
        panel = self._previewing()
        panel._on_accept()
        panel.apply_pending()
        self.assertIsNone(panel.pending_commit)
        self.assertFalse(self._shown(self._apply_btn(panel)))

    def test_apply_reports_like_any_other_run(self):
        panel = self._panel(
            output=True,
            on_run=lambda values: lambda: panel.logger.info("committed"),
        )
        panel._on_accept()
        app.processEvents()
        panel.apply_pending()
        app.processEvents()
        self.assertIn("committed", panel.output.toPlainText())

    def test_a_second_preview_supersedes_the_first(self):
        """A button still offering to commit a preview a later run has
        invalidated is worse than no button."""
        held = []

        def preview(_values):
            commit = lambda: held.append(len(held))  # noqa: E731
            return commit

        panel = self._panel(on_run=preview)
        panel._on_accept()
        first = panel.pending_commit
        panel._on_accept()
        self.assertIsNotNone(panel.pending_commit)
        self.assertIsNot(panel.pending_commit, first)

    def test_a_live_run_drops_an_armed_plan(self):
        modes = {"preview": True}

        def handler(_values):
            return (lambda: None) if modes["preview"] else None

        panel = self._panel(on_run=handler)
        panel._on_accept()
        self.assertIsNotNone(panel.pending_commit)
        modes["preview"] = False
        panel._on_accept()
        self.assertIsNone(panel.pending_commit)
        self.assertFalse(self._shown(self._apply_btn(panel)))

    def test_re_seeding_the_rows_drops_an_armed_plan(self):
        """Reopened over a new scope, the held call is for the old one."""
        panel = self._previewing()
        panel._on_accept()
        panel.set_fields(self.FIELDS)
        self.assertIsNone(panel.pending_commit)
        self.assertEqual(panel.footer.statusText(), "")

    def test_a_failed_preview_arms_nothing(self):
        def boom(_values):
            raise RuntimeError("nope")

        panel = self._panel(on_run=boom, output=True)
        panel._on_accept()
        self.assertIsNone(panel.pending_commit)

    def test_apply_does_nothing_when_nothing_is_armed(self):
        panel = self._previewing()
        panel.apply_pending()
        self.assertEqual(self.committed, [])


class TestFormPanelKeys(FormPanelTestCase):
    """Escape and Return, which a frameless non-dialog window has to wire itself."""

    def _press(self, panel, key):
        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, QtCore.Qt.NoModifier)
        panel.keyPressEvent(event)

    def test_escape_closes_the_panel(self):
        panel = self._panel()
        panel.show()
        self._press(panel, QtCore.Qt.Key_Escape)
        self.assertFalse(panel.isVisible())

    def test_return_accepts_when_no_button_has_focus(self):
        ran = []
        panel = self._panel(on_run=ran.append)
        self._press(panel, QtCore.Qt.Key_Return)
        self.assertEqual(len(ran), 1)

    def test_return_over_a_focused_button_is_left_alone(self):
        """Return on Cancel must cancel and on Apply must apply — accepting
        here can move files, so it never fires on a guess about what has
        focus."""
        ran = []
        panel = self._panel(on_run=ran.append, cancel_text="Cancel")
        panel.show()
        panel._cancel_btn.setFocus()
        app.processEvents()
        self._press(panel, QtCore.Qt.Key_Return)
        self.assertEqual(ran, [])

    def test_the_picker_never_takes_the_focus_return_would_reach(self):
        """It sits INSIDE the editor: tabbing into it would leave the caret
        nowhere, and Return would open a dialog over a form ready to run."""
        panel = self._panel(on_run=lambda values: None)
        panel.show()
        for button in self._browse_buttons(panel):
            self.assertEqual(button.focusPolicy(), QtCore.Qt.NoFocus)

    def test_return_does_nothing_while_the_form_is_invalid(self):
        ran = []
        panel = self._panel(on_run=ran.append, validate=lambda v: "nope")
        self._press(panel, QtCore.Qt.Key_Return)
        self.assertEqual(ran, [])


class TestFormDialog(FormPanelTestCase):
    """The modal wrapper: block, then hand back the answers."""

    def _run_modal(self, drive, fields=None, **kwargs):
        """Show the modal and act on it from a one-shot timer.

        The panel is a WindowPanel, not a QDialog, so there is no ``exec_`` to
        stub — the modal is a real local event loop and the only way in is
        from inside it.
        """

        def act():
            for widget in QtWidgets.QApplication.topLevelWidgets():
                if isinstance(widget, FormPanel) and widget.isVisible():
                    drive(widget)
                    return
            raise AssertionError("the modal panel never appeared")

        QtCore.QTimer.singleShot(0, act)
        return SwitchboardUtilsMixin.form_dialog(
            self.FIELDS if fields is None else fields, **kwargs
        )

    def test_accept_returns_every_field_keyed_by_name(self):
        result = self._run_modal(lambda panel: panel._on_accept())
        self.assertEqual(result, {"src": "C:/from", "dest": "C:/to"})

    def test_cancel_returns_none(self):
        """None, not an empty dict — cancelling must be distinguishable from
        a form whose fields are all blank."""
        self.assertIsNone(self._run_modal(lambda panel: panel._on_reject()))

    def test_closing_the_window_returns_none(self):
        """Every dismissal path must end the loop, or the host locks up."""
        self.assertIsNone(self._run_modal(lambda panel: panel.close()))

    def test_hiding_the_window_returns_none(self):
        """The header's hide button is a dismissal too."""
        self.assertIsNone(self._run_modal(lambda panel: panel.hide()))

    def test_edited_values_are_returned(self):
        def edit_and_accept(panel):
            panel.editor("dest").setText("C:/elsewhere")
            panel._on_accept()

        self.assertEqual(self._run_modal(edit_and_accept)["dest"], "C:/elsewhere")

    def test_the_modal_carries_no_output_pane(self):
        """A modal that closes before the work starts has nothing to stream."""
        seen = {}

        def check(panel):
            seen["output"] = panel.output
            panel._on_reject()

        self._run_modal(check)
        self.assertIsNone(seen["output"])

    def test_the_busy_cursor_is_suspended_for_the_modal(self):
        """A modal under a slot's busy cursor must show an I-beam in its fields
        and an arrow on its buttons, not the host's hourglass."""
        with patch.object(
            SwitchboardUtilsMixin,
            "_suspend_override_cursor",
            wraps=SwitchboardUtilsMixin._suspend_override_cursor,
        ) as suspend:
            self._run_modal(lambda panel: panel._on_reject())
        suspend.assert_called()


if __name__ == "__main__":
    unittest.main()
