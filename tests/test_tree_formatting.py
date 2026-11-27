# !/usr/bin/python
# coding=utf-8
"""Regression tests for TreeFormatMixin.apply_formatting.

Run standalone: python -m tests.test_tree_formatting
"""

import re
import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtCore, QtGui, QtWidgets


class TestAnItemsOwnTextColour(QtBaseTestCase):
    """A cell's foreground brush reaches the screen.

    Bug: the tree's own sheet coloured ``QTreeWidget::item``, and a
    stylesheet's item colour beats an item's foreground brush, so no cell's
    own text colour was ever drawn (a formatter's, a panel's dim "filled in"
    frames): the delegate's palette injection only wins over a colour set on
    the widget. Fixed: 2026-11-22
    """

    def _reds(self, tree) -> int:
        image = tree.grab().toImage()
        count = 0
        for y in range(image.height()):
            for x in range(image.width()):
                c = image.pixelColor(x, y)
                if c.red() > 200 and c.green() < 90 and c.blue() < 90:
                    count += 1
        return count

    @staticmethod
    def _peak(tree, item, column) -> QtGui.QColor:
        """The brightest pixel of *item*'s cell in *column*: its text's colour."""
        image = tree.viewport().grab().toImage()
        rect = tree.visualItemRect(item)
        x0 = tree.header().sectionViewportPosition(column)
        pixels = (
            image.pixelColor(x, y)
            for y in range(rect.top(), rect.bottom())
            for x in range(x0, x0 + tree.header().sectionSize(column))
        )
        return max(pixels, key=lambda c: c.lightness())

    def test_a_cells_foreground_is_drawn_and_a_plain_cell_keeps_the_sheets(self):
        from uitk.widgets.treeWidget import TreeWidget

        tree = self.track_widget(TreeWidget())
        tree.setColumnCount(2)
        item = tree.create_item(["WWWWWWWW", "plain"])
        tree.resize(400, 80)
        tree.show()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self._reds(tree), 0, "nothing red before")
        item.setForeground(0, QtGui.QBrush(QtGui.QColor("#FF2020")))
        QtWidgets.QApplication.processEvents()
        self.assertGreater(self._reds(tree), 0, "its own colour, drawn")
        # The plain cell beside it is drawn in the view's sheet colour.
        [sheet] = re.findall(
            r"QTreeWidget\s*\{[^}]*?(?<![\w-])color:\s*(#[0-9a-fA-F]{6})",
            tree.styleSheet(),
        )
        plain = self._peak(tree, item, 1)
        self.assertLessEqual(
            abs(plain.lightness() - QtGui.QColor(sheet).lightness()), 24, plain.name()
        )
        self.assertLessEqual(
            abs(plain.red() - plain.blue()),
            12,
            f"grey text, not the red: {plain.name()}",
        )


class TestTheThemeLeavesACellsColourToTheCell(unittest.TestCase):
    """The theme's sheet colours a tree's text on the view, never on
    ``::item``: that rule would beat each cell's own foreground brush, as the
    tree's own sheet did. Fixed: 2026-11-22"""

    def test_no_base_item_rule_of_a_tree_sets_a_colour(self):
        from pathlib import Path

        import uitk

        sheet = (Path(uitk.__file__).parent / "themes" / "style.qss").read_text(
            encoding="utf-8"
        )
        # A ``{PLACEHOLDER}`` value's brace would end a rule's body early.
        sheet = re.sub(r"\{[A-Z_]+\}", "X", sheet)
        rules = re.findall(
            r"^Q(?:Tree|Abstract)\w*::item\s*\{([^}]*)\}", sheet, flags=re.M
        )
        self.assertTrue(rules, "the theme styles tree items")
        for body in rules:
            self.assertIsNone(re.search(r"(?m)^\s*color\s*:", body), body)


class TestRowGrounds(QtBaseTestCase):
    """The grounds the tree's delegate composites (``_RowTintDelegate``):
    alternating rows, a row colour of its own, and the indentation under it.

    Bugs: ``alternatingRowColors`` never reached a cell (the delegate painted
    every cell over Qt's alternate ground); a row's ground stopped at its
    indentation, so a darker child row showed a strip of the view's base down
    its left; and the theme's ``qproperty-childRowColor`` reset the colour a
    panel set at every polish. Fixed: 2026-11-25
    """

    def _tree(self, alternate=True):
        from uitk.themes.style_sheet import StyleSheet
        from uitk.widgets.treeWidget import TreeWidget

        holder = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(holder)
        tree = TreeWidget(holder)
        layout.addWidget(tree)
        StyleSheet().set(holder, theme="dark")  # as a panel wears it
        tree.setColumnCount(2)
        tree.setAlternatingRowColors(alternate)
        holder.resize(400, 300)
        return holder, tree

    @staticmethod
    def _show(holder):
        holder.show()
        QtWidgets.QApplication.processEvents()

    @staticmethod
    def _ground(tree, item, x=None) -> QtGui.QColor:
        """The colour at *x* (default: the end of the last column, past any
        text) on *item*'s row."""
        image = tree.viewport().grab().toImage()
        rect = tree.visualItemRect(item)
        if x is None:
            header = tree.header()
            last = tree.columnCount() - 1
            x = header.sectionViewportPosition(last) + header.sectionSize(last) - 3
        return image.pixelColor(x, rect.center().y())

    def test_alternating_rows_reach_the_cells(self):
        holder, tree = self._tree()
        rows = [tree.create_item([f"row {i}", ""]) for i in range(4)]
        self._show(holder)
        grounds = [self._ground(tree, r).lightness() for r in rows]
        self.assertGreater(grounds[1], grounds[0], grounds)
        self.assertEqual(grounds[0], grounds[2], grounds)
        self.assertEqual(grounds[1], grounds[3], grounds)

    def test_a_row_colour_of_its_own_does_not_alternate(self):
        """The Unity manifest's look: a step's object rows are one darker band
        while the steps alternate."""
        holder, tree = self._tree()
        tops = [tree.create_item([f"step {i}", ""]) for i in range(3)]
        kids = [tree.create_item([f"object {i}", ""], parent=tops[0]) for i in range(3)]
        tops[0].setExpanded(True)
        tree.setChildRowColor(QtGui.QColor(0, 0, 0, 56))
        self._show(holder)
        self.assertEqual(len({self._ground(tree, k).name() for k in kids}), 1)
        # Qt painted its own alternate ground into an odd row's indentation.
        self.assertEqual(len({self._ground(tree, k, x=2).name() for k in kids}), 1)
        # Below three object rows the next step is the 5th row shown: odd.
        self.assertLess(
            self._ground(tree, tops[1]).lightness(),
            self._ground(tree, tops[2]).lightness(),
        )
        self.assertLess(
            self._ground(tree, kids[0]).lightness(),
            self._ground(tree, tops[1]).lightness(),
        )

    def test_a_rows_ground_runs_under_its_indentation(self):
        holder, tree = self._tree(alternate=False)
        top = tree.create_item(["step", ""])
        kid = tree.create_item(["object", ""], parent=top)
        top.setExpanded(True)
        self._show(holder)
        tree.setChildRowColor(QtGui.QColor(0, 0, 0, 56))
        tree.set_column_tint(0, QtGui.QColor(0, 0, 0, 36))
        QtWidgets.QApplication.processEvents()
        header = tree.header()
        indent = self._ground(tree, kid, x=2)  # left of every branch line
        cell = self._ground(
            tree, kid, x=header.sectionViewportPosition(0) + header.sectionSize(0) - 3
        )
        self.assertLess(cell.lightness(), 50, "the child colour and the tint")
        self.assertEqual(indent.name(), cell.name())

    def test_a_row_colour_a_panel_set_survives_a_repolish(self):
        holder, tree = self._tree(alternate=False)
        tree.setChildRowColor(QtGui.QColor(0, 0, 0, 56))
        self._show(holder)
        tree.style().unpolish(tree)
        tree.style().polish(tree)
        self.assertEqual(tree.childRowColor.getRgb(), (0, 0, 0, 56))

    def test_an_alternate_ground_a_panel_set_survives_a_repolish(self):
        """The theme's ``ALTERNATE_BACKGROUND`` until a panel sets its own.

        Bug: the theme's ``qproperty-alternateRowColor`` set the theme's
        colour again at every polish, over the colour a panel had set (fixed
        for ``childRowColor`` already). Fixed: 2026-11-26
        """
        from uitk.themes.style_sheet import StyleSheet

        holder, tree = self._tree()
        rows = [tree.create_item([f"row {i}", ""]) for i in range(2)]
        self._show(holder)
        r, g, b, *_ = parsed = StyleSheet._parse_color(
            StyleSheet.themes["dark"]["ALTERNATE_BACKGROUND"]
        )
        self.assertEqual(
            tree.alternateRowColor.getRgb(),
            (r, g, b, round(StyleSheet._alpha(parsed))),
            "the theme's",
        )
        tree.setAlternateRowColor(QtGui.QColor(0, 0, 0, 56))
        tree.style().unpolish(tree)
        tree.style().polish(tree)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(tree.alternateRowColor.getRgb(), (0, 0, 0, 56))
        self.assertLess(
            self._ground(tree, rows[1]).lightness(),
            self._ground(tree, rows[0]).lightness(),
        )
        tree.setAlternateRowColor(QtGui.QColor())  # none of its own: the theme's again
        self.assertEqual(
            tree.alternateRowColor.getRgb(), (r, g, b, round(StyleSheet._alpha(parsed)))
        )


class TestTheTreeDrawsItsHierarchy(QtBaseTestCase):
    """The expander is a thin-walled box filling its indentation cell, and a
    row hangs from its parent's expander by a guide line.

    Bug: the expander was a 7 px SVG box (now 11 px) and the guides `#555` on `#393939`,
    hard to make out; a child's line ran in its own cell, apart from its
    parent's box. Fixed: 2026-11-25 -- the tree paints them
    (``HierarchyIconMixin._paint_branches``) in its text colour.
    """

    def _tree(self):
        from uitk.themes.style_sheet import StyleSheet
        from uitk.widgets.treeWidget import TreeWidget

        holder = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(holder)
        tree = TreeWidget(holder)
        layout.addWidget(tree)
        StyleSheet().set(holder, theme="dark")
        tree.setColumnCount(1)
        tree.set_row_height(20)
        top = tree.create_item(["step"])
        kids = [tree.create_item([f"object {i}"], parent=top) for i in range(2)]
        top.setExpanded(True)
        holder.resize(300, 200)
        holder.show()
        QtWidgets.QApplication.processEvents()
        return tree, top, kids

    @staticmethod
    def _lit(image, x, y, ground) -> bool:
        return image.pixelColor(x, y).lightness() > ground.lightness() + 25

    def test_every_row_is_as_high_as_asked(self):
        tree, top, kids = self._tree()
        self.assertEqual({tree.visualItemRect(i).height() for i in (top, *kids)}, {20})

    def test_the_expander_is_a_box_filling_its_cell(self):
        tree, top, _kids = self._tree()
        image = tree.viewport().grab().toImage()
        rect = tree.visualItemRect(top)
        ground = image.pixelColor(rect.right() - 2, rect.center().y())
        # Its walls: 11 px apart (a 16 px cell, 20 px row), lit top to bottom.
        cy = rect.top() + 9
        walls = [x for x in range(0, 16) if self._lit(image, x, rect.top() + 4, ground)]
        self.assertEqual(len(walls), 11, f"the top wall spans the box: {walls}")
        self.assertTrue(self._lit(image, 2, cy, ground), "the left wall")
        self.assertTrue(self._lit(image, 12, cy, ground), "the right wall")
        # Open: a minus, no plus stroke above it.
        self.assertTrue(self._lit(image, 7, cy, ground), "the minus")
        self.assertFalse(self._lit(image, 7, cy - 2, ground), "no plus while open")
        top.setExpanded(False)
        QtWidgets.QApplication.processEvents()
        image = tree.viewport().grab().toImage()
        self.assertTrue(self._lit(image, 7, cy - 2, ground), "a plus while closed")

    def test_only_the_expander_under_the_pointer_is_lit(self):
        """Bug: an expander judged the pointer while it was painted, and Qt
        repaints a hovered row's cells, never its indentation: moving down or
        up across boxes left them lit, or unlit under the pointer. Fixed:
        2026-11-25 -- the tree tracks the hot expander and repaints the rows
        it leaves and reaches (``_set_hot_branch``)."""
        from uitk.themes.style_sheet import StyleSheet
        from uitk.widgets.treeWidget import TreeWidget

        holder = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(holder)
        tree = TreeWidget(holder)
        layout.addWidget(tree)
        StyleSheet().set(holder, theme="dark")
        tree.setColumnCount(1)
        tree.set_row_height(20)
        tops = [tree.create_item([f"step {i}"]) for i in range(3)]
        for top in tops:
            tree.create_item(["object"], parent=top)
        holder.resize(300, 200)
        holder.show()
        QtWidgets.QApplication.processEvents()

        def move(top):
            pos = (
                QtCore.QPointF(7, tree.visualItemRect(top).center().y())
                if top
                else QtCore.QPointF(200, 150)
            )
            event = QtGui.QMouseEvent(
                QtCore.QEvent.MouseMove,
                pos,
                tree.viewport().mapToGlobal(pos),
                QtCore.Qt.NoButton,
                QtCore.Qt.NoButton,
                QtCore.Qt.NoModifier,
            )
            QtWidgets.QApplication.sendEvent(tree.viewport(), event)
            QtWidgets.QApplication.processEvents()

        def lit():
            image = tree.viewport().grab().toImage()
            return [
                image.pixelColor(2, tree.visualItemRect(t).top() + 9).lightness()
                for t in tops
            ]

        resting = lit()[0]
        for top in (tops[0], tops[1], tops[2], tops[1], tops[0]):  # down, then back up
            move(top)
            walls = lit()
            hot = tops.index(top)
            self.assertGreater(
                walls[hot], resting + 20, f"the box under the pointer: {walls}"
            )
            self.assertEqual(
                [w for i, w in enumerate(walls) if i != hot],
                [resting] * 2,
                f"the others: {walls}",
            )
        move(None)
        self.assertEqual(lit(), [resting] * 3, "none once the pointer is off them")

    def test_a_child_hangs_from_its_parents_expander(self):
        tree, top, kids = self._tree()
        image = tree.viewport().grab().toImage()
        ground = image.pixelColor(
            tree.visualItemRect(kids[0]).right() - 2,
            tree.visualItemRect(kids[0]).center().y(),
        )
        first, last = (tree.visualItemRect(k) for k in kids)
        x = 7  # the parent's cell, under its box
        self.assertTrue(
            self._lit(image, x, tree.visualItemRect(top).bottom() - 1, ground),
            "down from the box",
        )
        self.assertTrue(
            self._lit(image, x, first.top() + 1, ground), "into the first child"
        )
        self.assertTrue(
            self._lit(image, x, first.bottom() - 1, ground),
            "on past it: a sibling follows",
        )
        self.assertTrue(
            self._lit(image, 20, first.top() + 9, ground), "across to the child"
        )
        self.assertFalse(
            self._lit(image, x, last.bottom() - 1, ground), "the last child ends it"
        )

    def test_hiding_the_last_child_ends_the_line_at_the_one_before(self):
        """Each parent's last row shown is kept from paint to paint; a hide
        (a layout) counts it again (``_forget_rows_shown``)."""
        tree, _top, kids = self._tree()
        first = tree.visualItemRect(kids[0])

        def lit_below_first():
            image = tree.viewport().grab().toImage()
            ground = image.pixelColor(first.right() - 2, first.center().y())
            return self._lit(image, 7, first.bottom() - 1, ground)

        self.assertTrue(lit_below_first(), "a sibling follows")
        kids[1].setHidden(True)
        self.assertFalse(lit_below_first(), "none follows once it is hidden")
        kids[1].setHidden(False)
        self.assertTrue(lit_below_first(), "shown again")


class TestTheStylesBranchesWithTheTreesOwnOff(QtBaseTestCase):
    """``enable_hierarchy_icons(False)`` hands the branches to Qt's style.

    Bug: the theme's ``QTreeView::branch`` / ``QTreeWidget::branch`` rules gave
    every branch cell a transparent ground and no image (its comment said
    TreeWidget set one; nothing did any more), and a sheet's branch rule
    replaces the style's indicator: a themed tree drawing none of its own
    showed no expander at all, nor did a plain ``QTreeWidget`` under the theme
    (the graph editor's curves, the preset editor's tools). Fixed: 2026-11-26
    -- the theme leaves a tree's branches to the style.
    """

    def _expanders(self, make):
        """The pixels unlike the row's ground in a closed and an open parent's
        indentation, each a set of ``(x, y)`` in its row."""
        from uitk.themes.style_sheet import StyleSheet

        holder = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(holder)
        tree = make(holder)
        layout.addWidget(tree)
        StyleSheet().set(holder, theme="dark")
        tree.setColumnCount(1)
        parents = [
            QtWidgets.QTreeWidgetItem(tree, [name]) for name in ("closed", "open")
        ]
        for parent in parents:
            QtWidgets.QTreeWidgetItem(parent, ["child"])
        parents[1].setExpanded(True)
        holder.resize(300, 200)
        holder.show()
        QtWidgets.QApplication.processEvents()
        image = tree.viewport().grab().toImage()
        marks = []
        for parent in parents:
            rect = tree.visualItemRect(parent)
            ground = image.pixelColor(rect.right() - 2, rect.center().y())
            marks.append(
                {
                    (x, y - rect.top())
                    for y in range(rect.top(), rect.bottom() + 1)
                    for x in range(rect.left())
                    if image.pixelColor(x, y) != ground
                }
            )
        return marks

    def test_a_tree_drawing_no_branches_of_its_own_shows_the_styles_expander(self):
        from uitk.widgets.treeWidget import TreeWidget

        def own_off(parent):
            tree = TreeWidget(parent)
            tree.enable_hierarchy_icons(False)
            return tree

        for name, make in (
            ("TreeWidget, its own off", own_off),
            ("QTreeWidget", QtWidgets.QTreeWidget),
        ):
            with self.subTest(name):
                closed, opened = self._expanders(make)
                self.assertTrue(closed, "an expander on the closed parent")
                self.assertTrue(opened, "an expander on the open parent")
                self.assertNotEqual(closed, opened, "open and closed read apart")


class TestTheRowsAreNumberedOnce(QtBaseTestCase):
    """Rows alternate by their number among the rows shown, the number Qt
    alternates them by (``TreeWidget._shown_row``).

    Bug: the numbering was dropped at every paint and counted again up from
    the first row painted to the top, so each repaint of a long tree scrolled
    to its end walked every row above it (51 ms a repaint at 20,000 rows).
    Fixed: 2026-11-26 -- kept until Qt lays its rows out again.
    """

    def _tree(self, rows):
        from uitk.themes.style_sheet import StyleSheet
        from uitk.widgets.treeWidget import TreeWidget

        holder = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(holder)
        tree = TreeWidget(holder)
        layout.addWidget(tree)
        StyleSheet().set(holder, theme="dark")
        tree.setColumnCount(1)
        tree.setAlternatingRowColors(True)
        tops = [tree.create_item([f"row {i:04}"]) for i in range(rows)]
        for top in tops[::10]:
            for k in range(3):
                tree.create_item([f"child {k}"], parent=top)
        holder.resize(300, 300)
        holder.show()
        tree.scrollToBottom()
        QtWidgets.QApplication.processEvents()
        return tree, tops

    def _assert_alternation(self, tree, step):
        """Every top row in view is lighter when its number among the rows
        shown is odd, its indentation too: the tree lays that ground by its
        own numbering (``drawRow``), the cells by Qt's (child rows carry the
        child colour and never alternate)."""
        tree.scrollToBottom()
        QtWidgets.QApplication.processEvents()
        image = tree.viewport().grab().toImage()
        x = tree.header().sectionSize(0) - 3  # the cell, past its text
        numbers, index = {}, tree.model().index(0, 0)
        while index.isValid():
            numbers[tree.itemFromIndex(index)] = len(numbers)
            index = tree.indexBelow(index)
        grounds = {0: set(), 1: set()}
        for item, number in numbers.items():
            rect = tree.visualItemRect(item)
            if (
                item.parent() is None
                and rect.top() >= 0
                and rect.bottom() < image.height()
            ):
                y = rect.center().y()
                cell, indent = image.pixelColor(x, y), image.pixelColor(1, y)
                self.assertEqual(indent.name(), cell.name(), f"{step}: {item.text(0)}")
                grounds[number % 2].add(cell.lightness())
        self.assertEqual(len(grounds[0]), 1, f"{step}: the even rows {grounds}")
        self.assertEqual(len(grounds[1]), 1, f"{step}: the odd rows {grounds}")
        self.assertGreater(min(grounds[1]), min(grounds[0]), f"{step}: {grounds}")

    def test_a_repaint_counts_no_row_again(self):
        tree, _tops = self._tree(rows=3000)
        tree.viewport().grab()  # numbers the rows
        walked = []
        above = tree.indexAbove
        tree.indexAbove = lambda index: walked.append(index) or above(index)
        tree.viewport().grab()
        self.assertLess(len(walked), 100, "a repaint walked rows it had numbered")

    def test_the_numbering_follows_every_change_to_the_rows_shown(self):
        tree, tops = self._tree(rows=120)
        self._assert_alternation(tree, "at first")
        changes = (
            ("an item hidden", lambda: tops[1].setHidden(True)),
            ("a row hidden", lambda: tree.setRowHidden(2, QtCore.QModelIndex(), True)),
            ("expanded", lambda: tops[10].setExpanded(True)),
            ("collapsed", lambda: tops[10].setExpanded(False)),
            ("all expanded", tree.expandAll),
            ("all collapsed", tree.collapseAll),
            (
                "inserted",
                lambda: tree.insertTopLevelItem(3, QtWidgets.QTreeWidgetItem(["new"])),
            ),
            ("taken", lambda: tree.takeTopLevelItem(3)),
            ("sorted", lambda: tree.sortItems(0, QtCore.Qt.DescendingOrder)),
        )
        for step, change in changes:
            change()
            self._assert_alternation(tree, step)


class TestIconStyles(QtBaseTestCase):
    """``set_icon_style``: the expander's styles (``ICON_STYLES``)."""

    def _tree(self):
        from uitk.widgets.treeWidget import TreeWidget

        return self.track_widget(TreeWidget())

    def test_every_style_listed_is_taken(self):
        tree = self._tree()
        self.assertEqual(tree.get_available_icon_styles(), ["plus_minus", "arrows"])
        self.assertEqual(tree.get_current_icon_style(), "plus_minus", "the default")
        for style in tree.get_available_icon_styles():
            tree.set_icon_style(style)
            self.assertEqual(tree.get_current_icon_style(), style)

    def test_modern_reads_as_arrows_and_is_not_listed(self):
        tree = self._tree()
        tree.set_icon_style("modern")
        self.assertEqual(tree.get_current_icon_style(), "arrows")
        self.assertNotIn("modern", tree.get_available_icon_styles())

    def test_an_unknown_style_is_refused_and_the_current_one_kept(self):
        tree = self._tree()
        tree.set_icon_style("arrows")
        with self.assertRaises(ValueError):
            tree.set_icon_style("triangles")
        self.assertEqual(tree.get_current_icon_style(), "arrows")


class TestACellsTail(QtBaseTestCase):
    """``TreeWidget.set_cell_tail``: a long name reads by its end -- the lead
    faded and cut from its left when narrow, the tail whole and semi-bold."""

    def test_a_narrow_cell_cuts_the_lead_never_the_tail(self):
        from uitk.widgets.treeWidget import _RowTintDelegate

        font = QtGui.QFont()
        bold = QtGui.QFont(font)
        bold.setWeight(QtGui.QFont.DemiBold)
        metrics, bold_metrics = QtGui.QFontMetrics(font), QtGui.QFontMetrics(bold)
        text = "PUMP_ASSY|HOUSING|FASTENERS|SCREW_UPPER"
        start = text.rindex("|") + 1
        layout = _RowTintDelegate._tail_layout
        wide = layout(text, start, 2000, metrics, bold_metrics)
        self.assertEqual(wide, (text[:start], "SCREW_UPPER"))
        room = bold_metrics.horizontalAdvance(
            "SCREW_UPPER"
        ) + metrics.horizontalAdvance("…|HOUSING|")
        lead, tail = layout(text, start, room, metrics, bold_metrics)
        self.assertEqual(tail, "SCREW_UPPER", "the tail whole")
        self.assertTrue(lead.startswith("…") and lead.endswith("|"), lead)
        lead, tail = layout(text, start, 30, metrics, bold_metrics)
        self.assertEqual(lead, "", "no room: the lead goes first")
        self.assertTrue(tail.endswith("…"), tail)

    def test_the_lead_is_drawn_fainter_than_the_tail(self):
        from uitk.themes.style_sheet import StyleSheet
        from uitk.widgets.treeWidget import TreeWidget

        holder = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(holder)
        tree = TreeWidget(holder)
        layout.addWidget(tree)
        StyleSheet().set(holder, theme="dark")
        tree.setColumnCount(1)
        tree.setRootIsDecorated(False)
        lead = "WWWWWWWW|"
        item = tree.create_item([lead + "MMMMMMMM"])
        tree.set_cell_tail(item, 0, len(lead))
        holder.resize(500, 120)
        holder.show()
        QtWidgets.QApplication.processEvents()
        image = tree.viewport().grab().toImage()
        rect = tree.visualItemRect(item)
        split = (
            rect.left() + 4 + QtGui.QFontMetrics(tree.font()).horizontalAdvance(lead)
        )

        def brightest(x0, x1):
            return max(
                image.pixelColor(x, y).lightness()
                for y in range(rect.top(), rect.bottom())
                for x in range(x0, x1)
            )

        self.assertLess(
            brightest(rect.left(), split - 4) + 30, brightest(split + 4, split + 60)
        )
        tree.set_cell_tail(item, 0, None)
        QtWidgets.QApplication.processEvents()
        image = tree.viewport().grab().toImage()
        self.assertLess(
            abs(brightest(rect.left(), split - 4) - brightest(split + 4, split + 60)),
            20,
            "plain again",
        )

    def test_a_selected_or_hovered_tail_takes_the_sheets_colour_as_a_plain_cell_does(
        self,
    ):
        """Bug: a tail cell's text took the palette's ``Text`` /
        ``HighlightedText``, never the colour the sheet gives the cell's state
        (``::item:selected``, ``::item:hover``) that a plain cell beside it
        shows. Fixed: 2026-11-26 -- the style writes a tail cell's text too."""
        from uitk.themes.style_sheet import StyleSheet
        from uitk.widgets.treeWidget import TreeWidget

        holder = self.track_widget(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(holder)
        tree = TreeWidget(holder)
        layout.addWidget(tree)
        StyleSheet().set(holder, theme="dark")
        tree.setColumnCount(1)
        tree.setRootIsDecorated(False)
        tree.setStyleSheet(
            tree.styleSheet()
            + "QTreeWidget::item:selected { color: #20E020; }"
            + "QTreeWidget::item:hover:!selected { color: #E02020; }"
        )
        plain = tree.create_item(["MMMMMMMM"])
        tailed = tree.create_item(["WWWW|MMMMMMMM"])
        tree.set_cell_tail(tailed, 0, 5)
        holder.resize(400, 120)
        holder.show()
        QtWidgets.QApplication.processEvents()

        def count(item, hue):
            image = tree.viewport().grab().toImage()
            rect = tree.visualItemRect(item)
            return sum(
                1
                for y in range(rect.top(), rect.bottom())
                for x in range(rect.left(), rect.right())
                if hue(image.pixelColor(x, y))
            )

        def green(c):
            return c.green() > 150 and c.red() < 110 and c.blue() < 110

        def red(c):
            return c.red() > 150 and c.green() < 110 and c.blue() < 110

        plain.setSelected(True)
        tailed.setSelected(True)
        QtWidgets.QApplication.processEvents()
        self.assertGreater(count(plain, green), 0, "a plain selected cell: the sheet's")
        self.assertGreater(
            count(tailed, green), 0, "a selected tail cell: the sheet's too"
        )
        tree.clearSelection()
        for item in (plain, tailed):
            pos = QtCore.QPointF(tree.visualItemRect(item).center())
            viewport = tree.viewport()
            QtWidgets.QApplication.sendEvent(
                viewport,
                QtGui.QHoverEvent(
                    QtCore.QEvent.HoverMove,
                    pos,
                    viewport.mapToGlobal(pos),
                    QtCore.QPointF(-1, -1),
                ),
            )
            QtWidgets.QApplication.processEvents()
            self.assertGreater(
                count(item, red), 0, f"hovered: the sheet's ({item.text(0)})"
            )


class TestTreeApplyFormattingRecursion(QtBaseTestCase):
    """apply_formatting must not recurse when formatters write item roles.

    Formatters call item.setForeground/setBackground, which fires itemChanged
    -> _on_item_edited -> formatters -> ... Without a signal-block guard (which
    CellFormatMixin already had but TreeFormatMixin lacked), two formatters
    setting differing colors flip-flop forever -> RecursionError.
    """

    def test_conflicting_formatters_do_not_recurse(self):
        from uitk.widgets.treeWidget import TreeWidget

        tree = self.track_widget(TreeWidget())
        tree.setColumnCount(1)
        item = QtWidgets.QTreeWidgetItem(["node"])
        tree.addTopLevelItem(item)

        def paint_red(it, value, col, *_):
            it.setForeground(col, QtGui.QColor("red"))

        def paint_blue(it, value, col, *_):
            it.setForeground(col, QtGui.QColor("blue"))

        tree.set_column_formatter(0, paint_red, append=True)
        tree.set_column_formatter(0, paint_blue, append=True)

        # Must complete without RecursionError.
        tree.apply_formatting()

        # Last formatter wins; the point is that it terminated at all.
        self.assertEqual(item.foreground(0).color().name(), QtGui.QColor("blue").name())


class TestTreeAddSignalBlocking(QtBaseTestCase):
    """add() must keep signals blocked through its whole body.

    Regression: an inner blockSignals(True)/blockSignals(False) pair ran before
    the tail (set_attributes/apply_formatting), unblocking signals mid-method
    and defeating the @Signals.blockSignals decorator — letting itemChanged
    escape during the tail of add().
    """

    def test_item_changed_does_not_escape_during_add(self):
        from uitk.widgets.treeWidget import TreeWidget

        tree = self.track_widget(TreeWidget())
        received = []
        tree.itemChanged.connect(lambda *a: received.append(a))

        # A formatter makes apply_formatting() (part of add's tail) write item
        # roles; those must not surface as external itemChanged emissions.
        tree.set_column_formatter(
            0, lambda it, v, col, *_: it.setForeground(col, QtGui.QColor("red"))
        )
        tree.add(["a", "b", "c"], headers=["Name"])

        self.assertEqual(received, [], "itemChanged must not escape during add()")


if __name__ == "__main__":
    unittest.main()


def _hover(tree, item, col) -> str:
    """The tooltip a hover over *item*'s cell *col* shows (``""``: none)."""
    import time
    from qtpy import QtCore

    QtWidgets.QToolTip.hideText()  # hides on a timer: wait it out
    deadline = time.monotonic() + 2.0
    while QtWidgets.QToolTip.isVisible() and time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    index = tree.indexFromItem(item, col)
    pos = tree.visualRect(index).center()
    event = QtGui.QHelpEvent(
        QtCore.QEvent.ToolTip, pos, tree.viewport().mapToGlobal(pos)
    )
    QtWidgets.QApplication.sendEvent(tree.viewport(), event)
    return QtWidgets.QToolTip.text() if QtWidgets.QToolTip.isVisible() else ""


class TestTreeRowTooltips(QtBaseTestCase):
    """``TreeWidget.set_row_tooltip``: one tooltip for a whole row -- its
    status -- shown on every cell ahead of the cell's own.  Composed at hover
    time, so neither a cell tooltip set later nor the row's is lost."""

    def _tree(self):
        from uitk.widgets.treeWidget import TreeWidget

        tree = self.track_widget(TreeWidget())
        tree.setColumnCount(3)
        tree.setHeaderLabels(["Step", "Description", "End"])
        tree.resize(400, 120)
        self.row = QtWidgets.QTreeWidgetItem(["A01", "Open", "40"])
        self.child = QtWidgets.QTreeWidgetItem(["", "lid", ""])
        self.row.addChild(self.child)
        tree.addTopLevelItem(self.row)
        self.row.setExpanded(True)
        tree.show()
        QtWidgets.QApplication.processEvents()
        return tree

    def test_every_cell_shows_it_ahead_of_its_own(self):
        tree = self._tree()  # unmanaged: setting one hands it to the presenter
        tree.set_row_tooltip(self.row, "Missing: lid")
        self.row.setToolTip(1, "Sheet: Close")
        self.assertEqual(_hover(tree, self.row, 0), "Missing: lid")
        self.assertEqual(_hover(tree, self.row, 2), "Missing: lid")
        self.assertEqual(_hover(tree, self.row, 1), "Missing: lid\n\nSheet: Close")
        self.assertEqual(_hover(tree, self.child, 1), "", "a row of its own")

    def test_a_rich_row_tooltip_escapes_a_plain_cell_tooltip(self):
        tree = self._tree()
        tree.set_row_tooltip(self.row, "<b>Missing</b>")
        index = tree.indexFromItem(self.row, 1)
        self.assertEqual(
            tree.item_tooltip(index, "a < b\nc"), "<b>Missing</b><br><br>a &lt; b<br>c"
        )

    def test_none_clears_it(self):
        tree = self._tree()
        tree.set_row_tooltip(self.row, "Missing: lid")
        tree.set_row_tooltip(self.row, None)
        self.assertIsNone(tree.row_tooltip(self.row))
        self.assertEqual(_hover(tree, self.row, 0), "")

    def test_it_leads_an_elided_cells_full_text_and_its_own(self):
        """A cell cut short shows its full text, then its own tooltip: the
        row's status leads them both."""
        tree = self._tree()
        tree.elided_tooltips = True
        long = "Selecting the top lock triggers the Top Lock Open animation " * 3
        self.row.setText(1, long)
        tree.header().resizeSection(1, 80)
        QtWidgets.QApplication.processEvents()
        self.assertTrue(tree.is_elided(tree.indexFromItem(self.row, 1)))
        self.row.setToolTip(1, "Sheet: Close")
        tree.set_row_tooltip(self.row, "Missing: lid")
        shown = _hover(tree, self.row, 1)  # the presenter wraps a long line
        self.assertTrue(shown.startswith("Missing: lid\n\n"), shown)
        self.assertTrue(shown.endswith("\n\nSheet: Close"), shown)
        self.assertEqual(
            " ".join(shown.split()),
            " ".join(f"Missing: lid {long} Sheet: Close".split()),
        )


class TestTreeElidedTooltips(QtBaseTestCase):
    """``TreeWidget.elided_tooltips``: a cell cut short shows its full text in
    its tooltip -- through ``TooltipPresenter``, whether the tree was managed
    already (a registered widget) or turning it on manages it -- and its own
    tooltip follows the text."""

    LONG = "Selecting the top lock triggers the Top Lock Open animation " * 3

    def _tree(self, managed: bool):
        from uitk.widgets.treeWidget import TreeWidget
        from uitk.widgets.mixins.tooltip_mixin import TooltipPresenter

        tree = self.track_widget(TreeWidget())
        tree.setColumnCount(2)
        tree.setHeaderLabels(["Step", "Description"])
        tree.resize(300, 120)
        tree.header().resizeSection(0, 60)
        tree.header().resizeSection(1, 120)
        self.short = QtWidgets.QTreeWidgetItem(["A01", "Open"])
        self.long = QtWidgets.QTreeWidgetItem(["A02", self.LONG])
        tree.addTopLevelItems([self.short, self.long])
        if managed:
            TooltipPresenter.manage(tree)
        tree.show()
        QtWidgets.QApplication.processEvents()
        return tree

    def _hover(self, tree, item, col) -> str:
        return _hover(tree, item, col)

    def test_off_by_default(self):
        tree = self._tree(managed=True)
        self.assertFalse(tree.elided_tooltips)
        self.assertEqual(self._hover(tree, self.long, 1), "")

    def test_an_elided_cell_shows_its_full_text_managed_or_not(self):
        for managed in (True, False):
            with self.subTest(managed=managed):
                tree = self._tree(managed)
                tree.elided_tooltips = True
                self.assertTrue(tree.is_elided(tree.indexFromItem(self.long, 1)))
                self.assertFalse(tree.is_elided(tree.indexFromItem(self.short, 1)))
                shown = self._hover(tree, self.long, 1)
                self.assertIn("Top Lock Open", shown)
                self.assertEqual(self._hover(tree, self.short, 1), "")

    def test_the_cells_own_tooltip_follows_unless_it_holds_the_text(self):
        tree = self._tree(managed=True)
        tree.elided_tooltips = True
        index = tree.indexFromItem(self.long, 1)
        self.assertEqual(
            tree.item_tooltip(index, "Missing object"),
            f"{self.LONG.strip()}\n\nMissing object",
        )
        self.assertEqual(
            tree.item_tooltip(index, f"x {self.LONG} y"), f"x {self.LONG} y"
        )
        self.assertTrue(
            tree.item_tooltip(index, "<b>Status</b>").endswith("<br><br><b>Status</b>")
        )
        self.long.setText(1, "line one\nline two")
        self.assertTrue(tree.is_elided(index))
