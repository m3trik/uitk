# !/usr/bin/python
# coding=utf-8
"""UITK Example — a polished tour of the framework.

This single-window demo exercises the major UITK features:

  • Convention-based slot discovery (``def widget_name`` runs on the
    widget's default signal; ``_init`` suffix runs once on registration).
  • Default signal auto-wiring (combobox, tree, menus).
  • Header popup menu — theme picker, log-level selector, timestamp
    toggle, logger-name toggle, clear, about.
  • LineEdit option_box plugin stack — stateful action, browse,
    recent, pin, clear — wired with a single fluent chain.
  • Tree right-click context menu via ``widget.menu`` with
    ``trigger_button = "right"``.
  • CollapsableGroup + QSplitter for the resizable tree/console split.
  • pythontk LoggingMixin console with HTML rendering, custom log
    levels (PROGRESS / SUCCESS / RESULT / NOTICE), ``log_box``,
    ``log_divider``, and clickable ``action://`` links routed through
    ``QTextBrowser.anchorClicked``.
  • Footer default status, live status, and progress context manager.
  • Slot-level controls — ``widget.debounce`` and
    ``ui.default_slot_timeout``.

Every visible message comes from the shared class logger.
"""
import os
import html
import inspect
import logging
import importlib
import importlib.util
from pathlib import Path
from urllib.parse import parse_qs

from qtpy import QtWidgets, QtCore, QtGui
from qtpy.QtCore import Qt

import pythontk as ptk
from pythontk.core_utils.logging_mixin import LevelAwareFormatter, LoggerExt

from uitk import Switchboard
from uitk.widgets.textEditLogHandler import TextEditLogHandler


# Wire pythontk's LoggingMixin to use UITK's Qt-aware handler so that
# ``logger.add_text_widget_handler(...)`` (and any downstream helpers)
# emit through TextEditLogHandler by default.
LoggerExt._set_text_handler(TextEditLogHandler)


class ExampleSlots(ptk.LoggingMixin):
    """Slots for the UITK Example — method names match widget objectNames."""

    # =========================================================================
    # Lifecycle
    # =========================================================================
    def __init__(self, **kwargs):
        self.sb = kwargs["switchboard"]
        self.ui = self.sb.loaded_ui.example

        self._selected_obj = None
        self._selected_name = None
        self._include_inherited = False

        self._setup_console()
        self._welcome()

    # =========================================================================
    # Console — driven entirely by pythontk's LoggingMixin
    # =========================================================================
    def _setup_console(self):
        """Attach a Qt text-widget handler to the class logger."""
        logger = self.logger
        logger.setLevel(logging.DEBUG)

        # Hot-reload safety — drop any stale handlers from prior sessions.
        for h in list(logger.handlers):
            logger.removeHandler(h)

        handler = TextEditLogHandler(self.ui.txt_output, monospace=True)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(LevelAwareFormatter(logger=logger, strip_html=False))
        logger.addHandler(handler)

        logger.hide_logger_name(True)
        logger.log_timestamp = "%H:%M:%S"

        # Footer default status replaces the current example's "sticky" setText.
        self.ui.footer.setDefaultStatusText("Ready  •  Select an item to inspect")

        # action:// link routing from QTextBrowser (log_link clicks).
        out = self.ui.txt_output
        if hasattr(out, "anchorClicked"):
            out.anchorClicked.connect(self._on_anchor_clicked)

    def _welcome(self):
        """Splash banner printed once at startup."""
        self.logger.log_box(
            "UITK EXAMPLE  —  a polished feature tour",
            items=[
                "• pick a subpackage from the Navigate row",
                "• click any tree item — its docs render here",
                "• try the buttons attached to the path field  (option_box plugins)",
                "• right-click the tree for a context menu",
                "• open the gear menu in the header for themes / log level / more",
            ],
            level="NOTICE",
            align="left",
        )
        self.logger.info("Console ready.")

    def _on_anchor_clicked(self, url: QtCore.QUrl):
        """Route pythontk ``log_link`` clicks (``action://VERB?k=v``)."""
        if url.scheme() != "action":
            return
        action = url.host() or url.path().strip("/")
        params = {k: v[0] for k, v in parse_qs(url.query()).items()}

        if action == "reveal":
            path = params.get("path", "")
            if path and os.path.exists(path):
                folder = path if os.path.isdir(path) else os.path.dirname(path)
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))
                self.logger.success(f"Revealed in file explorer: <code>{html.escape(path)}</code>")
            else:
                self.logger.warning(f"Path not found: {html.escape(path)}")
        elif action == "copy":
            text = params.get("text", "")
            QtWidgets.QApplication.clipboard().setText(text)
            preview = text if len(text) <= 60 else text[:57] + "..."
            self.logger.success(f"Copied: <code>{html.escape(preview)}</code>")
        else:
            self.logger.notice(f"Unhandled link action: <code>{html.escape(action)}</code>")

        # Prevent QTextBrowser from navigating away and clearing the document.
        self.ui.txt_output.setSource(QtCore.QUrl())

    # =========================================================================
    # Header — popup menu
    # =========================================================================
    def header_init(self, widget):
        widget.config_buttons("menu", "minimize", "maximize", "hide")

        m = widget.menu
        m.add("QLabel", setText="<b>Preferences</b>")
        m.add("QSeparator")
        m.add(
            "QComboBox",
            setObjectName="cmb_theme",
            addItems=["Dark", "Light"],
        )
        m.add(
            "QComboBox",
            setObjectName="cmb_level",
            addItems=["Debug", "Info", "Progress", "Success", "Result", "Notice", "Warning"],
        )
        m.add(
            "QCheckBox",
            setObjectName="chk_timestamps",
            setText="Show timestamps",
            setChecked=True,
        )
        m.add(
            "QCheckBox",
            setObjectName="chk_hide_name",
            setText="Hide logger name",
            setChecked=True,
        )
        m.add("QSeparator")
        m.add("QPushButton", setText="Clear console", setObjectName="btn_clear")
        m.add("QPushButton", setText="About UITK",    setObjectName="btn_about")

        m.cmb_level.setCurrentText("Debug")

        m.cmb_theme.currentTextChanged.connect(self._on_theme_change)
        m.cmb_level.currentTextChanged.connect(self._on_level_change)
        m.chk_timestamps.toggled.connect(self._on_timestamps_toggled)
        m.chk_hide_name.toggled.connect(self._on_hide_name_toggled)
        m.btn_clear.clicked.connect(self._clear_console)
        m.btn_about.clicked.connect(self._log_about)

    def _on_theme_change(self, theme: str):
        self.ui.style.set(theme=theme.lower(), style_class="translucentBgWithBorder")
        self.logger.success(f"Theme: <b>{theme}</b>")

    def _on_level_change(self, level_name: str):
        level_map = {
            "Debug":    logging.DEBUG,
            "Info":     logging.INFO,
            "Progress": LoggerExt.PROGRESS,
            "Success":  LoggerExt.SUCCESS,
            "Result":   LoggerExt.RESULT,
            "Notice":   LoggerExt.NOTICE,
            "Warning":  logging.WARNING,
        }
        level = level_map.get(level_name, logging.INFO)
        self.logger.setLevel(level)
        for h in self.logger.handlers:
            h.setLevel(level)
        self.logger.result(
            f"Log level: <b>{level_name}</b> "
            f"<i>(messages below this threshold are hidden)</i>"
        )

    def _on_timestamps_toggled(self, checked: bool):
        self.logger.log_timestamp = "%H:%M:%S" if checked else None
        self.logger.notice(f"Timestamps: {'on' if checked else 'off'}")

    def _on_hide_name_toggled(self, checked: bool):
        self.logger.hide_logger_name(checked)
        LoggerExt._update_handler_formatters(self.logger)
        self.logger.notice(f"Hide logger name: {'on' if checked else 'off'}")

    def _clear_console(self):
        self.ui.txt_output.clear()
        self.logger.notice("Console cleared.")

    def _log_about(self):
        self.logger.log_box(
            "ABOUT  —  UITK",
            items=[
                "A convention-driven Qt framework built on qtpy (PySide2 / PySide6).",
                "Every message in this console is rendered by pythontk's LoggingMixin.",
                "",
                "• Docs:  https://github.com/m3trik/uitk",
                "• PyPI:  pip install uitk",
            ],
            level="NOTICE",
            align="left",
        )

    # =========================================================================
    # Navigation row
    # =========================================================================
    def txt_input_init(self, widget):
        """Wire the full option_box plugin stack onto the path field."""
        uitk_root = str(Path(__file__).parent.parent)
        widget.setText(uitk_root)
        # Demonstrate slot-level debounce (rapid edits coalesce into one call).
        widget.debounce = 300

        # Stateful action button — toggles 'include inherited' for help output.
        widget.option_box.add_action(
            callback=self._toggle_inherited,
            icon="eye_off",
            tooltip="Inherited members: hidden",
            states=[
                {"icon": "eye_off", "tooltip": "Inherited members: hidden  (click to show)"},
                {"icon": "eye",     "tooltip": "Inherited members: visible  (click to hide)"},
            ],
        )
        widget.option_box.browse(
            mode="directory",
            title="Select a package directory",
            tooltip="Browse for a package folder",
        )
        widget.option_box.recent(max_recent=8)
        widget.option_box.pin()
        widget.option_box.enable_clear()

    def _toggle_inherited(self):
        self._include_inherited = not self._include_inherited
        state = "visible" if self._include_inherited else "hidden"
        self.logger.success(f"Inherited members: <b>{state}</b>")
        if self._selected_obj is not None:
            self._log_help(self._selected_obj, self._selected_name)

    def txt_input(self, text):
        """Default signal = textChanged (debounced 300 ms via ``widget.debounce``)."""
        text = (text or "").strip()
        if not text:
            return
        uitk_root = Path(__file__).parent.parent.resolve()
        try:
            p = Path(text).resolve()
        except (OSError, ValueError):
            return
        if not p.is_dir():
            return
        if p != uitk_root and uitk_root not in p.parents:
            return
        rel = p.relative_to(uitk_root.parent) if p != uitk_root else Path("uitk")
        dot = str(rel).replace(os.sep, ".").replace("/", ".")
        idx = self.ui.cmb_options.findText(dot)
        if idx >= 0 and self.ui.cmb_options.currentIndex() != idx:
            self.ui.cmb_options.setCurrentIndex(idx)
            self.logger.progress(f"Jumped to package: <b>{html.escape(dot)}</b>")

    def cmb_options_init(self, widget):
        """Populate the package combo with every importable UITK subpackage."""
        uitk_path = Path(__file__).parent.parent
        packages = ["uitk"]
        subdirs = ptk.FileUtils.get_dir_contents(
            str(uitk_path),
            content="dirpath",
            recursive=True,
            exc_dirs=["__pycache__", ".*", "_*", "icons"],
        )
        for d in sorted(subdirs):
            rel = Path(d).relative_to(uitk_path)
            if (Path(d) / "__init__.py").exists():
                packages.append("uitk." + str(rel).replace(os.sep, ".").replace("/", "."))
        widget.add(packages)
        widget.setCurrentIndex(0)

    def cmb_options(self, index):
        """Default signal = currentIndexChanged."""
        package = self.ui.cmb_options.currentText()
        self._populate_tree(package)

        uitk_path = Path(__file__).parent.parent
        target = uitk_path if package == "uitk" else uitk_path / package.replace("uitk.", "").replace(".", os.sep)
        # Update the path field *without* retriggering our debounced handler.
        blocker = QtCore.QSignalBlocker(self.ui.txt_input)
        self.ui.txt_input.setText(str(target))
        del blocker

    def cmb_view_init(self, widget):
        """Inline checkbox panel for tree view options."""
        chk_types = QtWidgets.QCheckBox("Show Types")
        chk_types.setChecked(True)
        chk_types.toggled.connect(
            lambda show: self.ui.tree_demo.setColumnHidden(1, not show)
        )

        chk_classes = QtWidgets.QCheckBox("Show Classes")
        chk_classes.setChecked(True)
        chk_classes.toggled.connect(self._refresh_current)

        chk_members = QtWidgets.QCheckBox("Show Members")
        chk_members.setChecked(False)
        chk_members.toggled.connect(self._refresh_current)

        chk_expand = QtWidgets.QCheckBox("Auto-expand")
        chk_expand.setChecked(True)

        chk_recursive = QtWidgets.QCheckBox("Include Subpackages")
        chk_recursive.setChecked(False)
        chk_recursive.toggled.connect(self._refresh_current)

        # Store on the widget so tree code can read them by name.
        widget.chk_types = chk_types
        widget.chk_classes = chk_classes
        widget.chk_members = chk_members
        widget.chk_expand = chk_expand
        widget.chk_recursive = chk_recursive

        widget.add(
            [
                (chk_types,     "Types"),
                (chk_classes,   "Classes"),
                (chk_members,   "Members"),
                (chk_expand,    "Expand"),
                (chk_recursive, "Recursive"),
            ],
            header="VIEW OPTIONS",
        )

    def _refresh_current(self):
        self._populate_tree(self.ui.cmb_options.currentText())

    # =========================================================================
    # Tree — default signal is itemClicked, plus a right-click context menu
    # =========================================================================
    def tree_demo_init(self, widget):
        widget.set_selection_mode("single")
        widget.setHeaderLabels(["Name", "Type", "Description"])
        widget.setColumnWidth(0, 200)
        widget.setColumnWidth(1, 80)
        widget.setExpandsOnDoubleClick(False)
        widget.mouseDoubleClickEvent = lambda event: None
        # Coalesce rapid clicks so the console isn't flooded.
        widget.debounce = 120

        self._populate_tree("uitk")

        # Right-click context menu — uses the MenuMixin on the tree widget.
        m = widget.menu
        m.trigger_button = "right"
        m.add("QPushButton", setText="Expand All",       setObjectName="btn_expand")
        m.add("QPushButton", setText="Collapse All",     setObjectName="btn_collapse")
        m.add("QSeparator")
        m.add("QPushButton", setText="Log Signature",    setObjectName="btn_sig")
        m.add("QPushButton", setText="Log Source Path",  setObjectName="btn_src")
        m.add("QPushButton", setText="Reveal in Finder", setObjectName="btn_reveal")
        m.add("QSeparator")
        m.add("QPushButton", setText="Refresh",          setObjectName="btn_refresh")

        m.btn_expand.clicked.connect(widget.expand_all_items)
        m.btn_collapse.clicked.connect(widget.collapse_all_items)
        m.btn_sig.clicked.connect(self._log_selected_signature)
        m.btn_src.clicked.connect(self._log_selected_source)
        m.btn_reveal.clicked.connect(self._reveal_selected_source)
        m.btn_refresh.clicked.connect(self._refresh_current)

    def tree_demo(self, item, column, widget=None):
        """Default signal = itemClicked. Shows rich help in the console."""
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        obj = data.get("obj")
        name = data.get("full_name", item.text(0))

        self._selected_obj = obj
        self._selected_name = name
        self.ui.footer.setStatusText(f"{item.text(0)}  —  {item.text(2) or item.text(1)}")

        if obj is None:
            self.logger.warning(f"No live object for <b>{html.escape(name)}</b>")
            return

        # Reflect file path in the text field (blocked to avoid triggering nav).
        src = getattr(obj, "__file__", None) or self._module_file(obj)
        if src:
            blocker = QtCore.QSignalBlocker(self.ui.txt_input)
            self.ui.txt_input.setText(src)
            del blocker

        self._log_help(obj, name)

    # ---- context menu actions -------------------------------------------------
    def _log_selected_signature(self):
        if self._selected_obj is None:
            self.logger.warning("Nothing selected.")
            return
        sig = self._signature_of(self._selected_obj)
        name = self._selected_name or "<obj>"
        copy_link = self.logger.log_link(
            "copy", "copy", text=f"{name}{sig}"
        )
        self.logger.result(
            f"<b>{html.escape(name)}</b>{html.escape(sig)}  &nbsp;·&nbsp;  [{copy_link}]"
        )

    def _log_selected_source(self):
        path = self._selected_source_path()
        if not path:
            self.logger.warning("No source file for selection.")
            return
        reveal = self.logger.log_link("reveal in explorer", "reveal", path=path)
        self.logger.result(f"Source: <code>{html.escape(path)}</code>  &nbsp;·&nbsp;  [{reveal}]")

    def _reveal_selected_source(self):
        path = self._selected_source_path()
        if not path:
            self.logger.warning("No source file for selection.")
            return
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))
        self.logger.success(f"Opened: <code>{html.escape(folder)}</code>")

    def _selected_source_path(self) -> str | None:
        obj = self._selected_obj
        if obj is None:
            return None
        path = getattr(obj, "__file__", None)
        if path:
            return path
        return self._module_file(obj)

    @staticmethod
    def _module_file(obj) -> str | None:
        mod_name = getattr(obj, "__module__", None)
        if not mod_name:
            return None
        try:
            return getattr(importlib.import_module(mod_name), "__file__", None)
        except Exception:
            return None

    # =========================================================================
    # Rich help rendering — all output goes through the logger
    # =========================================================================
    def _log_help(self, obj, name: str):
        """Print a pretty, multi-section help entry for *obj*."""
        logger = self.logger

        # Signature box ---------------------------------------------------------
        sig = self._signature_of(obj)
        title = f"{name}{sig}"
        kind = self._kind_of(obj)
        logger.log_box(title, items=[f"kind: {kind}"], level="NOTICE", align="left")

        # Docstring -------------------------------------------------------------
        doc = inspect.getdoc(obj) or "No documentation available."
        logger.info(html.escape(doc).replace("\n", "<br>"))

        # Members for classes ---------------------------------------------------
        if isinstance(obj, type):
            self._log_class_members(obj)

        # Actions footer --------------------------------------------------------
        path = getattr(obj, "__file__", None) or self._module_file(obj)
        parts = []
        if path:
            parts.append(self.logger.log_link("reveal source", "reveal", path=path))
        parts.append(self.logger.log_link("copy signature", "copy", text=f"{name}{sig}"))
        logger.notice(" &nbsp;·&nbsp; ".join(f"[{p}]" for p in parts))

    def _log_class_members(self, cls: type):
        """Render defined and (optionally) inherited members as grouped lists."""
        inherited_names = set()
        for base in cls.__mro__[1:]:
            inherited_names.update(dir(base))

        defined, inherited = [], []
        for attr_name in sorted(dir(cls)):
            if attr_name.startswith("_"):
                continue
            try:
                attr = getattr(cls, attr_name)
            except Exception:
                continue
            kind = self._member_kind(attr)
            if kind is None:
                continue
            entry = (attr_name, kind, self._first_line(inspect.getdoc(attr)))
            if attr_name in inherited_names:
                inherited.append(entry)
            else:
                defined.append(entry)

        if defined:
            self.logger.log_divider(width=72, char="─")
            self.logger.progress(f"Defined members ({len(defined)})")
            for entry in defined:
                self._log_member_row(*entry)

        if self._include_inherited and inherited:
            self.logger.log_divider(width=72, char="─")
            self.logger.progress(f"Inherited members ({len(inherited)})")
            for entry in inherited:
                self._log_member_row(*entry)
        elif inherited:
            self.logger.log_divider(width=72, char="─")
            self.logger.debug(
                f"{len(inherited)} inherited members hidden "
                f"— toggle the eye icon on the path field to show."
            )

    def _log_member_row(self, name: str, kind: str, desc: str):
        colors = LoggerExt.LOG_COLORS
        name_c = colors.get("RESULT", "#CCFFFF")   # pastel teal
        kind_c = colors.get("SUCCESS", "#CCFFCC")  # pastel green
        desc_c = colors.get("INFO", "#FFFFFF")
        # Single raw HTML row — bypass level-color wrapping for cleaner layout.
        name_html = f'<span style="color:{name_c}">{html.escape(name):<22}</span>'
        kind_html = f'<span style="color:{kind_c}">{html.escape(kind):<10}</span>'
        desc_html = f'<span style="color:{desc_c}">{html.escape(desc)}</span>'
        self.logger.log_raw(f"  {name_html} {kind_html} {desc_html}")

    # ---- introspection helpers ------------------------------------------------
    @staticmethod
    def _signature_of(obj) -> str:
        if not callable(obj):
            return ""
        try:
            return str(inspect.signature(obj))
        except (ValueError, TypeError):
            return "(...)"

    @staticmethod
    def _kind_of(obj) -> str:
        if inspect.ismodule(obj):
            return "module"
        if isinstance(obj, type):
            return "class"
        if isinstance(obj, property):
            return "property"
        if inspect.isfunction(obj) or inspect.ismethod(obj):
            return "function"
        if callable(obj):
            return "callable"
        return type(obj).__name__

    @staticmethod
    def _member_kind(attr) -> str | None:
        if isinstance(attr, property):
            return "property"
        if isinstance(attr, type):
            return "class"
        if callable(attr):
            return "method"
        return None

    @staticmethod
    def _first_line(doc: str | None) -> str:
        if not doc:
            return ""
        return doc.strip().splitlines()[0].strip().rstrip(".")[:72]

    # =========================================================================
    # Tree population
    # =========================================================================
    def _introspect_subdir(self, package: str):
        modules = []
        uitk_path = Path(__file__).parent.parent

        if package == "uitk":
            target = uitk_path
            prefix = "uitk"
        else:
            rel = package.replace("uitk.", "").replace(".", os.sep)
            target = uitk_path / rel
            prefix = package

        if not target.exists():
            return modules

        for py in sorted(target.glob("*.py")):
            if py.name.startswith("_"):
                continue
            mod_name = py.stem
            try:
                spec = importlib.util.find_spec(f"{prefix}.{mod_name}")
                if spec is None:
                    modules.append((mod_name, "module", mod_name, None, []))
                    continue
                mod = importlib.import_module(f"{prefix}.{mod_name}")
                desc = self._first_line(inspect.getdoc(mod))
                classes = []
                for a in dir(mod):
                    if a.startswith("_"):
                        continue
                    try:
                        v = getattr(mod, a)
                        if isinstance(v, type) and v.__module__ == mod.__name__:
                            classes.append(v)
                    except Exception:
                        continue
                modules.append((mod_name, "module", desc or mod_name, mod, classes))
            except Exception:
                modules.append((mod_name, "module", mod_name, None, []))

        for item in sorted(target.iterdir()):
            if (
                item.is_dir()
                and not item.name.startswith(("_", "."))
                and (item / "__init__.py").exists()
            ):
                try:
                    mod = importlib.import_module(f"{prefix}.{item.name}")
                    desc = self._first_line(inspect.getdoc(mod))
                    modules.append((item.name, "package", desc or item.name, mod, []))
                except Exception:
                    modules.append((item.name, "package", item.name, None, []))

        return modules

    def _populate_tree(self, package: str = "uitk"):
        tree = self.ui.tree_demo
        tree.clear()
        self._selected_obj = None
        self._selected_name = None

        show_classes = self.ui.cmb_view.chk_classes.isChecked()
        show_members = self.ui.cmb_view.chk_members.isChecked()
        auto_expand = self.ui.cmb_view.chk_expand.isChecked()
        recurse = self.ui.cmb_view.chk_recursive.isChecked()

        with self.ui.footer.progress(100, f"Scanning {package}…") as tick:
            tick(10)
            modules = self._introspect_subdir(package)
            tick(40)

            if recurse:
                extra = []
                for name, typ, desc, obj, classes in modules:
                    if typ == "package":
                        sub = self._introspect_subdir(f"{package}.{name}")
                        for sn, st, sd, so, sc in sub:
                            if st != "package":
                                extra.append((f"{name}.{sn}", st, sd, so, sc))
                modules.extend(extra)
            tick(60)

            packages = [m for m in modules if m[1] == "package"]
            mods     = [m for m in modules if m[1] == "module"]

            if packages:
                root = tree.create_item(["Packages", "", ""])
                tree.set_item_type_icon(root, "folder")
                for name, _, desc, obj, _ in packages:
                    child = tree.create_item([name, "package", desc], parent=root)
                    tree.set_item_type_icon(child, "folder")
                    if obj:
                        tree.set_item_data(child, {"obj": obj, "full_name": f"{package}.{name}"})
                root.setExpanded(auto_expand)

            if mods:
                root = tree.create_item(["Modules", "", ""])
                tree.set_item_type_icon(root, "folder")
                for name, _, desc, obj, classes in mods:
                    mod_item = tree.create_item([name, "module", desc], parent=root)
                    tree.set_item_type_icon(mod_item, "file")
                    if obj:
                        tree.set_item_data(mod_item, {"obj": obj, "full_name": f"{package}.{name}"})
                    if show_classes and classes:
                        for cls in classes:
                            cls_item = tree.create_item(
                                [cls.__name__, "class", self._first_line(inspect.getdoc(cls))],
                                parent=mod_item,
                            )
                            tree.set_item_type_icon(cls_item, "widgets")
                            tree.set_item_data(
                                cls_item,
                                {"obj": cls, "full_name": f"{package}.{name}.{cls.__name__}"},
                            )
                            if show_members:
                                self._add_class_members(tree, cls_item, cls)
                            if auto_expand:
                                cls_item.setExpanded(True)
                    if auto_expand and show_classes and classes:
                        mod_item.setExpanded(True)
                root.setExpanded(auto_expand)

            tick(100)

        self.logger.progress(
            f"Loaded <b>{len(packages)}</b> subpackages, <b>{len(mods)}</b> modules"
            f" from <b>{html.escape(package)}</b>"
        )

    def _add_class_members(self, tree, parent_item, cls):
        inherited = set()
        for base in cls.__mro__[1:]:
            inherited.update(dir(base))

        rows = []
        for name in sorted(dir(cls)):
            if name.startswith("_") or name in inherited:
                continue
            try:
                attr = getattr(cls, name)
            except Exception:
                continue
            if isinstance(attr, property):
                rows.append((name, "property", self._first_line(inspect.getdoc(attr.fget)), attr, "tag"))
            elif callable(attr):
                rows.append((name, "method",   self._first_line(inspect.getdoc(attr)),       attr, "code"))

        for name, kind, desc, attr, icon in rows:
            row = tree.create_item([name, kind, desc], parent=parent_item)
            tree.set_item_type_icon(row, icon)
            tree.set_item_data(row, {"obj": attr, "full_name": f"{cls.__name__}.{name}"})


# =============================================================================
# Main
# =============================================================================
if __name__ == "__main__":
    from uitk.examples import example

    sb = Switchboard(ui_source=example, slot_source=example.ExampleSlots)
    ui = sb.loaded_ui.example

    # Demonstrate the per-UI timeout fallback.
    ui.default_slot_timeout = 30

    ui.set_attributes(WA_TranslucentBackground=True)
    ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
    ui.style.set(theme="dark", style_class="translucentBgWithBorder")

    ui.show(pos="screen", app_exec=True)
