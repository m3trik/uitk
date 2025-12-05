# !/usr/bin/python
# coding=utf-8
"""UITK Package Explorer

An interactive browser for exploring UITK's package structure, classes,
and documentation with introspection that excludes inherited members.

NAVIGATION:
===========
- ComboBox: Select package/subpackage to browse
- Tree: Hierarchical view (modules > classes > methods)
- Click: Show help in output panel

KEY PATTERNS DEMONSTRATED:
==========================
1. Name slots to match widget objectNames (e.g., 'tree_demo' -> 'def tree_demo()')
2. Use '_init' suffix for one-time setup (e.g., 'def tree_demo_init(widget)')
3. Default signals connect automatically (e.g., QTreeWidget uses itemClicked)
4. Use @Signals decorator only for non-default signals
5. Access .menu on any widget to add a popup menu
6. Access .option_box on input widgets for pin/clear/menu features
"""
import os
import logging
import importlib
from pathlib import Path
from qtpy import QtWidgets, QtCore, QtGui
from uitk import Switchboard
from uitk.widgets.mixins.icon_manager import IconManager
from uitk.widgets.textEditLogHandler import TextEditLogHandler


class ResizeHandle(QtWidgets.QFrame):
    """Horizontal drag handle for resizing widget heights.

    A thin bar that can be dragged vertically to resize the widget above it.
    Shows visual feedback on hover.
    """

    def __init__(self, target_widget, min_height=250, max_height=600, parent=None):
        super().__init__(parent)
        self.target_widget = target_widget
        self.min_height = min_height
        self.max_height = max_height
        self._dragging = False
        self._start_y = 0
        self._start_height = 0

        # Visual setup
        self.setFixedHeight(6)
        self.setCursor(QtCore.Qt.SizeVerCursor)
        self.setStyleSheet(
            """
            ResizeHandle {
                background-color: transparent;
                border: none;
            }
            ResizeHandle:hover {
                background-color: rgba(100, 150, 255, 80);
            }
            """
        )

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._dragging = True
            self._start_y = event.globalPos().y()
            self._start_height = self.target_widget.height()
            self.setStyleSheet(
                """
                ResizeHandle {
                    background-color: rgba(100, 150, 255, 150);
                }
                """
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.globalPos().y() - self._start_y
            new_height = max(
                self.min_height, min(self.max_height, self._start_height + delta)
            )
            self.target_widget.setMinimumHeight(new_height)
            self.target_widget.setMaximumHeight(new_height)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._dragging = False
            self.setStyleSheet(
                """
                ResizeHandle {
                    background-color: transparent;
                    border: none;
                }
                ResizeHandle:hover {
                    background-color: rgba(100, 150, 255, 80);
                }
                """
            )
            event.accept()


class ExampleSlots:
    """Slots for the UITK Package Explorer - method names match widget objectNames."""

    def __init__(self, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.example
        self._selected_obj = None  # Currently selected module/class/method
        self._selected_name = None
        self._setup_logger()

    def _setup_logger(self):
        """Route logging to the output widget."""
        self.logger = logging.getLogger("uitk.example")
        self.logger.handlers.clear()
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(TextEditLogHandler(self.ui.txt_output))
        # Use Footer's setDefaultStatusText for persistent status
        self.ui.footer.setDefaultStatusText("Select an item to view details")
        self.logger.info("UITK Package Explorer ready")

    def _get_help_text(self, obj, include_inherited=False):
        """Get help text for an object, optionally filtering inherited members.

        Parameters:
            obj: The object to get help for.
            include_inherited (bool): If False, filter out inherited attributes.

        Returns:
            str: Formatted help text.
        """
        import inspect

        lines = []

        # Get basic info
        name = getattr(obj, "__name__", type(obj).__name__)
        doc = inspect.getdoc(obj) or "No documentation available."

        # Signature for callables
        sig = ""
        if callable(obj):
            try:
                sig = str(inspect.signature(obj))
            except (ValueError, TypeError):
                sig = "(...)"

        lines.append(f"{name}{sig}")
        lines.append("=" * len(f"{name}{sig}"))
        lines.append("")
        lines.append(doc)

        # For classes, show defined (non-inherited) members
        if isinstance(obj, type):
            # Get members defined in this class only
            own_members = []
            inherited_from = set()

            for base in obj.__mro__[1:]:
                inherited_from.update(dir(base))

            for attr_name in sorted(dir(obj)):
                if attr_name.startswith("_"):
                    continue
                if not include_inherited and attr_name in inherited_from:
                    continue
                try:
                    attr = getattr(obj, attr_name)
                    if callable(attr) and not isinstance(attr, type):
                        own_members.append((attr_name, "method", attr))
                    elif isinstance(attr, property):
                        own_members.append((attr_name, "property", attr))
                except Exception:
                    continue

            if own_members:
                lines.append("")
                lines.append("Defined Members:")
                lines.append("-" * 16)
                for member_name, member_type, member_obj in own_members:
                    member_doc = inspect.getdoc(member_obj)
                    desc = ""
                    if member_doc:
                        desc = member_doc.split("\n")[0][:60]
                    lines.append(f"    {member_name} ({member_type}): {desc}")

        # For modules, show contents
        elif inspect.ismodule(obj):
            classes = []
            functions = []

            for attr_name in sorted(dir(obj)):
                if attr_name.startswith("_"):
                    continue
                try:
                    attr = getattr(obj, attr_name)
                    if isinstance(attr, type) and attr.__module__ == obj.__name__:
                        classes.append(attr_name)
                    elif (
                        callable(attr)
                        and getattr(attr, "__module__", None) == obj.__name__
                    ):
                        functions.append(attr_name)
                except Exception:
                    continue

            if classes:
                lines.append("")
                lines.append("Classes:")
                lines.append("-" * 8)
                for c in classes:
                    lines.append(f"    {c}")

            if functions:
                lines.append("")
                lines.append("Functions:")
                lines.append("-" * 10)
                for f in functions:
                    lines.append(f"    {f}")

        return "\n".join(lines)

    # =========================================================================
    # HEADER - window controls and settings menu
    # =========================================================================

    def header_init(self, widget):
        """Setup header buttons and menu."""
        widget.config_buttons("menu", "minimize", "maximize", "hide")
        # Build settings menu - items are accessible as widget.menu.objectName
        widget.menu.setTitle("SETTINGS")
        widget.menu.add(
            "QComboBox", setObjectName="cmb_theme", addItems=["Dark", "Light"]
        )
        widget.menu.add("QSeparator")
        widget.menu.add("QPushButton", setText="Clear Log", setObjectName="btn_clear")
        # Connect menu widget signals
        widget.menu.cmb_theme.currentTextChanged.connect(
            lambda t: self.ui.style.set(
                theme=t.lower(), style_class="translucentBgWithBorder"
            )
        )
        widget.menu.btn_clear.clicked.connect(self.ui.txt_output.clear)

    # =========================================================================
    # INPUT WIDGETS - package and view options
    # =========================================================================

    def txt_input_init(self, widget):
        """Show file path to uitk package root."""
        uitk_path = Path(__file__).parent.parent
        widget.setText(str(uitk_path))

    def cmb_options_init(self, widget):
        """Setup package combobox with UITK subdirectories using flexible add method."""
        import pythontk as ptk

        uitk_path = Path(__file__).parent.parent

        # Get all subdirectories recursively
        packages = ["uitk"]
        all_dirs = ptk.file_utils.FileUtils.get_dir_contents(
            str(uitk_path),
            content="dirpath",
            recursive=True,
            exc_dirs=["__pycache__", ".*", "_*", "icons"],
        )

        for dir_path in sorted(all_dirs):
            rel_path = Path(dir_path).relative_to(uitk_path)
            if (Path(dir_path) / "__init__.py").exists():
                dot_path = "uitk." + str(rel_path).replace("\\", ".").replace("/", ".")
                packages.append(dot_path)

        # Use flexible add() method - no header, displays current selection
        widget.add(packages)
        widget.setCurrentIndex(0)  # Start with 'uitk' selected

    def cmb_options(self, index):
        """Update tree when package selection changes."""
        package = self.ui.cmb_options.currentText()
        self._populate_tree(package)
        # Update path display
        uitk_path = Path(__file__).parent.parent
        if package == "uitk":
            self.ui.txt_input.setText(str(uitk_path))
        else:
            rel_path = package.replace("uitk.", "").replace(".", os.sep)
            self.ui.txt_input.setText(str(uitk_path / rel_path))

    def cmb_view_init(self, widget):
        """Setup view options dropdown with checkboxes."""
        from qtpy.QtWidgets import QCheckBox

        # Create checkboxes for view options
        widget.chk_types = QCheckBox("Show Types")
        widget.chk_types.setChecked(True)
        widget.chk_types.toggled.connect(
            lambda show: self.ui.tree_demo.setColumnHidden(1, not show)
        )

        widget.chk_classes = QCheckBox("Show Classes")
        widget.chk_classes.setChecked(True)
        widget.chk_classes.toggled.connect(
            lambda: self._populate_tree(self.ui.cmb_options.currentText())
        )

        widget.chk_members = QCheckBox("Show Members")
        widget.chk_members.setChecked(False)
        widget.chk_members.toggled.connect(
            lambda: self._populate_tree(self.ui.cmb_options.currentText())
        )

        widget.chk_expand = QCheckBox("Auto-expand")
        widget.chk_expand.setChecked(True)

        widget.chk_recursive = QCheckBox("Include Subpackages")
        widget.chk_recursive.setChecked(False)
        widget.chk_recursive.toggled.connect(
            lambda: self._populate_tree(self.ui.cmb_options.currentText())
        )

        # Add all checkboxes using flexible add method with (widget, label) tuples
        widget.add(
            [
                (widget.chk_types, "Types"),
                (widget.chk_classes, "Classes"),
                (widget.chk_members, "Members"),
                (widget.chk_expand, "Expand"),
                (widget.chk_recursive, "Recursive"),
            ],
            header="VIEW OPTIONS",
        )

    # =========================================================================
    # TREE - shows UITK package structure with context menu
    # =========================================================================

    def tree_demo_init(self, widget):
        """Populate tree with UITK package structure and add context menu."""
        # Use TreeWidget's set_selection_mode method
        widget.set_selection_mode("single")
        widget.setHeaderLabels(["Name", "Type", "Description"])
        widget.setColumnWidth(0, 180)
        widget.setColumnWidth(1, 70)
        # Disable double-click expand/collapse behavior
        widget.setExpandsOnDoubleClick(False)
        # Override mouseDoubleClickEvent to completely block double-click
        widget.mouseDoubleClickEvent = lambda event: None
        self._populate_tree("uitk")

        # Add resize handle below tree for height adjustment
        self._add_tree_resize_handle()

        # Add right-click context menu using MenuMixin
        widget.menu.trigger_button = "right"
        widget.menu.setTitle("TREE ACTIONS")
        widget.menu.add("QPushButton", setText="Expand All", setObjectName="btn_expand")
        widget.menu.add(
            "QPushButton", setText="Collapse All", setObjectName="btn_collapse"
        )
        widget.menu.add("QSeparator")
        widget.menu.add("QPushButton", setText="Refresh", setObjectName="btn_refresh")
        # Use TreeWidget's expand_all_items/collapse_all_items methods
        widget.menu.btn_expand.clicked.connect(widget.expand_all_items)
        widget.menu.btn_collapse.clicked.connect(widget.collapse_all_items)
        widget.menu.btn_refresh.clicked.connect(
            lambda: self._populate_tree(self.ui.cmb_options.currentText())
        )

    def _add_tree_resize_handle(self):
        """Add a draggable resize handle below the tree widget."""
        # Find the parent layout that contains tree_group and output_group
        tree_group = self.ui.tree_group
        output_group = self.ui.output_group
        parent_widget = tree_group.parentWidget()

        if parent_widget and parent_widget.layout():
            layout = parent_widget.layout()
            # Find index of output_group (we'll insert handle before it)
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget() == output_group:
                    # Create resize handle targeting the tree widget
                    handle = ResizeHandle(
                        self.ui.tree_demo, min_height=300, max_height=600
                    )
                    layout.insertWidget(i, handle)
                    break

    def tree_demo(self, item, column, widget=None):
        """Handle tree item click - show help for selected item.

        Connected automatically to itemClicked (default signal for QTreeWidget).
        """
        from qtpy.QtCore import Qt

        item_data = item.data(0, Qt.UserRole)
        if not item_data:
            return

        obj = item_data.get("obj")
        name = item_data.get("full_name", item.text(0))

        self._selected_obj = obj
        self._selected_name = name
        self.ui.footer.setText(f"{item.text(0)}: {item.text(2)}")

        # Update path to show file location
        if hasattr(obj, "__file__"):
            self.ui.txt_input.setText(obj.__file__)
        elif hasattr(obj, "__module__"):
            try:
                mod = importlib.import_module(obj.__module__)
                if hasattr(mod, "__file__"):
                    self.ui.txt_input.setText(mod.__file__)
            except Exception:
                pass

        # Auto-populate help in output (exclude inherited members by default)
        self.ui.txt_output.clear()
        if obj is None:
            self.ui.txt_output.setPlainText(f"{name}: No object data available")
            return
        try:
            help_text = self._get_help_text(obj, include_inherited=False)
            formatted = self._format_help_text(name, help_text)
            self.ui.txt_output.setHtml(formatted)
        except Exception as e:
            self.ui.txt_output.setPlainText(f"Error getting help for {name}: {e}")

    def _format_help_text(self, name, help_text):
        """Format help text as styled HTML for the output widget."""
        import html

        lines = help_text.split("\n")
        html_parts = [
            "<style>",
            "body { font-family: Consolas, monospace; font-size: 11px; }",
            ".header { color: #4EC9B0; font-weight: bold; font-size: 13px; }",
            ".section { color: #569CD6; font-weight: bold; margin-top: 10px; }",
            ".param { color: #9CDCFE; }",
            ".type { color: #4EC9B0; }",
            ".desc { color: #D4D4D4; }",
            ".code { color: #CE9178; }",
            "</style>",
            f'<div class="header">=== {html.escape(name)} ===</div>',
            "<pre>",
        ]

        in_params = False
        in_example = False

        for line in lines:
            escaped = html.escape(line)

            # Detect section headers (lines of === or ---)
            if line.strip() and all(c in "=-" for c in line.strip()):
                continue  # Skip separator lines

            # Detect section titles
            if line.strip().endswith(":") and not line.startswith(" "):
                section = line.strip()
                html_parts.append(
                    f'<span class="section">{html.escape(section)}</span>'
                )
                in_params = "Parameters" in section or "Attributes" in section
                in_example = "Example" in section
                continue

            # Format parameter lines
            if in_params and line.strip().startswith("-"):
                # Parameter description continuation
                html_parts.append(f'<span class="desc">  {escaped.strip()}</span>')
            elif in_params and ":" in line and line.startswith("    "):
                # Parameter name : type
                parts = line.split(":", 1)
                if len(parts) == 2:
                    param_name = parts[0].strip()
                    param_type = parts[1].strip()
                    html_parts.append(
                        f'  <span class="param">{html.escape(param_name)}</span>: '
                        f'<span class="type">{html.escape(param_type)}</span>'
                    )
                else:
                    html_parts.append(escaped)
            elif in_example:
                html_parts.append(f'<span class="code">{escaped}</span>')
            else:
                html_parts.append(escaped)

        html_parts.append("</pre>")
        return "\n".join(html_parts)

    # Double-click is disabled - we show info on single click instead

    def _get_docstring_summary(self, obj):
        """Extract the first line of a docstring."""
        doc = getattr(obj, "__doc__", None)
        if not doc:
            return ""
        first_line = doc.strip().split("\n")[0].strip()
        return first_line.rstrip(".")

    def _add_class_members(self, parent_item, cls):
        """Add methods and properties of a class as tree children."""
        tree = self.ui.tree_demo

        members = []
        for name in dir(cls):
            if name.startswith("_"):
                continue
            try:
                attr = getattr(cls, name)
                # Skip inherited from object
                if hasattr(object, name):
                    continue
                if callable(attr):
                    desc = self._get_docstring_summary(attr)
                    members.append((name, "method", desc or "Method", attr, "code"))
                elif isinstance(attr, property):
                    desc = self._get_docstring_summary(attr.fget) if attr.fget else ""
                    members.append((name, "property", desc or "Property", attr, "tag"))
            except Exception:
                continue

        for name, typ, desc, obj, icon_name in sorted(members):
            child = tree.create_item([name, typ, desc], parent=parent_item)
            tree.set_item_type_icon(child, icon_name)
            tree.set_item_data(
                child, {"obj": obj, "full_name": f"{cls.__name__}.{name}"}
            )

    def _introspect_subdir(self, package):
        """Dynamically introspect a UITK package and return modules with their classes."""
        modules = []
        uitk_path = Path(__file__).parent.parent

        if package == "uitk":
            target_path = uitk_path
            import_prefix = "uitk"
        else:
            rel_path = package.replace("uitk.", "").replace(".", os.sep)
            target_path = uitk_path / rel_path
            import_prefix = package

        if not target_path.exists():
            return modules

        for py_file in sorted(target_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            mod_name = py_file.stem
            try:
                # Use importlib.util to check if module can be imported safely
                spec = importlib.util.find_spec(f"{import_prefix}.{mod_name}")
                if spec is None:
                    modules.append((mod_name, "module", f"{mod_name}", None, []))
                    continue

                mod = importlib.import_module(f"{import_prefix}.{mod_name}")
                desc = self._get_docstring_summary(mod)
                # Find all classes defined in this module
                classes = []
                for attr_name in dir(mod):
                    if attr_name.startswith("_"):
                        continue
                    try:
                        attr = getattr(mod, attr_name)
                        if isinstance(attr, type) and attr.__module__ == mod.__name__:
                            classes.append(attr)
                    except Exception:
                        continue
                modules.append(
                    (mod_name, "module", desc or f"{mod_name}", mod, classes)
                )
            except Exception:
                # Module exists but can't be imported (missing dependencies, etc.)
                # Just show it as a module without drilling into it
                modules.append((mod_name, "module", f"{mod_name}", None, []))

        # Also check for subpackages
        for item in sorted(target_path.iterdir()):
            if (
                item.is_dir()
                and not item.name.startswith(("_", "."))
                and (item / "__init__.py").exists()
            ):
                try:
                    mod = importlib.import_module(f"{import_prefix}.{item.name}")
                    desc = self._get_docstring_summary(mod)
                    modules.append(
                        (item.name, "package", desc or f"{item.name}", mod, [])
                    )
                except Exception:
                    modules.append((item.name, "package", f"{item.name}", None, []))

        return modules

    def _populate_tree(self, package="uitk"):
        """Build tree showing modules → classes → members hierarchy."""
        tree = self.ui.tree_demo
        tree.clear()
        self._selected_obj = None
        self._selected_name = None

        # Get view settings from cmb_view dropdown
        show_classes = self.ui.cmb_view.chk_classes.isChecked()
        show_members = self.ui.cmb_view.chk_members.isChecked()
        auto_expand = self.ui.cmb_view.chk_expand.isChecked()
        include_subpackages = self.ui.cmb_view.chk_recursive.isChecked()

        modules = self._introspect_subdir(package)

        # If include subpackages, recursively add contents from child packages
        if include_subpackages:
            subpkg_modules = []
            for name, typ, desc, obj, classes in modules:
                if typ == "package":
                    subpkg_name = f"{package}.{name}"
                    sub_modules = self._introspect_subdir(subpkg_name)
                    # Prefix names with subpackage for clarity
                    for sn, st, sd, so, sc in sub_modules:
                        if st != "package":  # Don't recurse further
                            subpkg_modules.append((f"{name}.{sn}", st, sd, so, sc))
            modules.extend(subpkg_modules)

        # Separate packages from modules
        packages = [(n, t, d, o, c) for n, t, d, o, c in modules if t == "package"]
        mods = [(n, t, d, o, c) for n, t, d, o, c in modules if t == "module"]

        # Add packages group using TreeWidget's create_item method
        if packages:
            pkg_parent = tree.create_item(["Packages", "", ""])
            tree.set_item_type_icon(pkg_parent, "folder")
            for name, typ, desc, obj, classes in packages:
                child = tree.create_item([name, "package", desc], parent=pkg_parent)
                tree.set_item_type_icon(child, "folder")
                if obj:
                    tree.set_item_data(
                        child, {"obj": obj, "full_name": f"{package}.{name}"}
                    )
            pkg_parent.setExpanded(auto_expand)

        # Add modules group using TreeWidget's create_item method
        if mods:
            mod_parent = tree.create_item(["Modules", "", ""])
            tree.set_item_type_icon(mod_parent, "folder")
            for name, typ, desc, obj, classes in mods:
                mod_item = tree.create_item([name, typ, desc], parent=mod_parent)
                tree.set_item_type_icon(mod_item, "file")
                if obj:
                    tree.set_item_data(
                        mod_item, {"obj": obj, "full_name": f"{package}.{name}"}
                    )

                # Add classes under this module
                if show_classes and classes:
                    for cls in classes:
                        cls_desc = self._get_docstring_summary(cls)
                        cls_item = tree.create_item(
                            [cls.__name__, "class", cls_desc], parent=mod_item
                        )
                        tree.set_item_type_icon(cls_item, "widgets")
                        tree.set_item_data(
                            cls_item,
                            {
                                "obj": cls,
                                "full_name": f"{package}.{name}.{cls.__name__}",
                            },
                        )

                        # Add members under this class
                        if show_members:
                            self._add_class_members_inline(tree, cls_item, cls)

                        if auto_expand:
                            cls_item.setExpanded(True)

                if auto_expand and (show_classes and classes):
                    mod_item.setExpanded(True)

            mod_parent.setExpanded(auto_expand)

    def _add_class_members_inline(self, tree, parent_item, cls):
        """Add methods and properties of a class as tree children (inline mode)."""
        members = []
        for name in dir(cls):
            if name.startswith("_"):
                continue
            try:
                attr = getattr(cls, name)
                if hasattr(object, name):
                    continue
                if callable(attr):
                    desc = self._get_docstring_summary(attr)
                    members.append((name, "method", desc or "Method", attr, "code"))
                elif isinstance(attr, property):
                    desc = self._get_docstring_summary(attr.fget) if attr.fget else ""
                    members.append((name, "property", desc or "Property", attr, "tag"))
            except Exception:
                continue

        for name, typ, desc, obj, icon_name in sorted(members):
            child = tree.create_item([name, typ, desc], parent=parent_item)
            tree.set_item_type_icon(child, icon_name)
            tree.set_item_data(
                child, {"obj": obj, "full_name": f"{cls.__name__}.{name}"}
            )

    # =========================================================================
    # OUTPUT - collapsible log section
    # =========================================================================

    def output_group_init(self, widget):
        """Start with output section expanded."""
        widget.setChecked(True)

    # =========================================================================
    # TEST WIDGETS - hidden, for unit tests only
    # =========================================================================

    def button_a_init(self, widget):
        widget.menu.setTitle("OPTIONS")

    def button_a(self):
        pass

    def button_b_init(self, widget):
        widget.menu.setTitle("OPTIONS")
        widget.menu.add(
            "QRadioButton", setText="Option 1", setObjectName="opt1", setChecked=True
        )
        widget.menu.add("QRadioButton", setText="Option 2", setObjectName="opt2")

    def button_b(self):
        pass

    def checkbox(self, state):
        pass

    def spinbox(self, value):
        pass


# =============================================================================
# MAIN - Minimal setup code
# =============================================================================

if __name__ == "__main__":
    from uitk.examples import example

    # Two lines to load UI and connect all slots automatically
    sb = Switchboard(ui_source=example, slot_source=example.ExampleSlots)
    ui = sb.loaded_ui.example

    # Configure window appearance
    ui.set_attributes(WA_TranslucentBackground=True)
    ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
    ui.style.set(theme="dark", style_class="translucentBgWithBorder")

    # Show and run
    ui.show(pos="screen", app_exec=True)
