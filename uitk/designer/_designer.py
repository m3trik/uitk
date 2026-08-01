# !/usr/bin/python
# coding=utf-8
"""Publish uitk widgets to Qt Designer's widget box.

Without a plugin, a custom widget can only reach Designer by *promotion*: you
drop a stock ``QPushButton``, right-click it, and name a class Designer never
loads. The form shows a plain Qt widget, and the property editor shows only the
base class's properties — everything the custom class adds is invisible until
runtime.

:class:`DesignerPlugin` removes that step. It discovers widget classes, resolves
each one's Designer metadata, and hands them to PySide6's
``QPyDesignerCustomWidgetCollection`` so Designer instantiates the *real* class:
the form renders the actual widget, and every ``QtCore.Property`` it declares
shows up in the property editor beside the inherited Qt ones.

Discovery reuses :class:`~uitk.managers.registry_manager.RegistryManager` — the
same scan the Switchboard runs — so a new widget module is picked up with no
registration step. Metadata is derived per class (Qt base, tooltip from the
docstring, container-ness from the base) and any widget can override or opt out
with a ``designer_spec`` class attribute::

    class Region(QtWidgets.QWidget, ...):
        designer_spec = {"container": True, "object_name": "region"}

    class AlignedComboBox(QtWidgets.QComboBox):
        designer_spec = {"visible": False}

Nothing here runs on import. ``register_uitk_widgets.py`` is the file Designer
loads; this module is the implementation it calls.
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple
from xml.sax.saxutils import escape, quoteattr

from qtpy import QtWidgets

# From this package:
from uitk.widgets.mixins.attributes import AttributesMixin

logger = logging.getLogger(__name__)


#: Environment variable Qt Designer's plugin path is read from (PySide6).
PLUGIN_PATH_ENV = "PYSIDE_DESIGNER_PLUGINS"


class DesignerWidget(NamedTuple):
    """Resolved Qt Designer metadata for one widget class.

    Produced by :meth:`DesignerPlugin.collect` and consumed by
    :meth:`DesignerPlugin.register`. Split out so the whole catalog can be
    inspected and tested without a running Designer.

    Attributes:
        cls: The widget class itself.
        name: Class name as it appears in the ``.ui`` file.
        module: Dotted module path emitted as the ``<header>`` — e.g.
            ``uitk.widgets.pushButton``.
        base: Name of the nearest Qt base class (``QPushButton``, ...).
        group: Widget-box group heading.
        tooltip: Widget-box tooltip.
        icon: Widget-box icon *name*, resolved through
            :class:`~uitk.managers.IconManager` at registration time (or an
            absolute path to an image file). ``""`` for no icon.
        container: Whether Designer may drop child widgets onto it.
        object_name: Default ``objectName`` Designer assigns on drop.
        size: Default ``(width, height)`` on drop, or ``None`` to use
            the widget's own ``sizeHint``.
        string_properties: ``{property_name: editor_kind}`` — promotes a
            plain string field to a richer Designer editor. Valid kinds are
            Qt's ``stringpropertyspecification`` types: ``singleline``,
            ``multiline``, ``richtext``, ``stylesheet``, ``url``.
    """

    cls: type
    name: str
    module: str
    base: str
    group: str
    tooltip: str
    icon: str
    container: bool
    object_name: str
    size: Optional[Tuple[int, int]]
    string_properties: Dict[str, str]

    @property
    def xml(self) -> str:
        """The ``domXml`` snippet Designer inserts when this widget is dropped.

        Carries the default ``objectName``, the drop geometry, the tooltip, and
        any ``<propertyspecifications>`` that upgrade a string property's editor
        (a rich-text field gets Designer's HTML editor rather than a one-line
        text box).
        """
        geometry = ""
        if self.size:
            w, h = self.size
            geometry = (
                '<property name="geometry"><rect>'
                f"<x>0</x><y>0</y><width>{w}</width><height>{h}</height>"
                "</rect></property>"
            )

        specs = "".join(
            f"<stringpropertyspecification name={quoteattr(prop)} "
            f"type={quoteattr(kind)}/>"
            for prop, kind in sorted(self.string_properties.items())
        )
        # Always emitted, even with no tooltip and no specs: ``<header>`` is
        # what tells the saved .ui which module to import the class from, so a
        # form written without it can't be loaded back.
        custom = (
            "<customwidgets><customwidget>"
            f"<class>{escape(self.name)}</class>"
            f"<extends>{escape(self.base)}</extends>"
            f"<header>{escape(self.module)}</header>"
            + (f"<tooltip>{escape(self.tooltip)}</tooltip>" if self.tooltip else "")
            + (
                f"<propertyspecifications>{specs}</propertyspecifications>"
                if specs
                else ""
            )
            + "</customwidget></customwidgets>"
        )

        return (
            '<ui language="c++">'
            f"<widget class={quoteattr(self.name)} name={quoteattr(self.object_name)}>"
            f"{geometry}</widget>{custom}</ui>"
        )


class _DesignerPluginInternal:
    """Derivation helpers behind :class:`DesignerPlugin`.

    Everything here answers one question: given a bare widget class, what should
    Qt Designer be told about it? Kept separate so the public surface stays the
    four verbs a caller actually uses — collect, register, launch, is_design_time.
    """

    #: Qt binding packages a base class may come from.
    _BINDING_PREFIXES = ("PySide2", "PySide6", "PyQt5", "PyQt6")

    #: Widgets that are windows, popups, or window furniture — never dropped
    #: onto a form, so they are excluded from the widget box by default.
    _NON_PLACEABLE = (
        "QDialog",
        "QMainWindow",
        "QMenu",
        "QMenuBar",
        "QDockWidget",
        "QSizeGrip",
        "QWizard",
        "QWizardPage",
    )

    #: Qt bases whose subclasses accept child widgets in Designer.
    _CONTAINER_BASES = (
        "QGroupBox",
        "QToolBox",
        "QTabWidget",
        "QStackedWidget",
        "QSplitter",
        "QScrollArea",
        "QMdiArea",
    )

    #: Longest tooltip taken from a class docstring before ellipsis.
    _TOOLTIP_LIMIT = 160

    @classmethod
    def _qt_base(cls, widget_cls: type) -> Optional[str]:
        """Return the nearest Qt base class name, or None if there isn't one."""
        for ancestor in widget_cls.__mro__[1:]:
            module = getattr(ancestor, "__module__", "") or ""
            if module.startswith(cls._BINDING_PREFIXES) and issubclass(
                ancestor, QtWidgets.QWidget
            ):
                return ancestor.__name__
        return None

    @classmethod
    def _qt_bases(cls, widget_cls: type) -> Tuple[str, ...]:
        """Return every Qt base class name in the MRO (nearest first)."""
        return tuple(
            ancestor.__name__
            for ancestor in widget_cls.__mro__[1:]
            if (getattr(ancestor, "__module__", "") or "").startswith(
                cls._BINDING_PREFIXES
            )
        )

    @classmethod
    def _spec(cls, widget_cls: type) -> dict:
        """Return the class's own ``designer_spec``, ignoring inherited ones.

        Read off ``__dict__`` rather than by attribute lookup: a subclass must
        not silently inherit its parent's Designer entry (``ColorSwatch``
        extends ``PushButton``; opting the parent out would otherwise take the
        child with it).
        """
        spec = widget_cls.__dict__.get("designer_spec")
        return dict(spec) if isinstance(spec, dict) else {}

    @classmethod
    def _is_placeable(cls, widget_cls: type, root: str) -> bool:
        """Whether this class belongs in the widget box, absent an explicit say.

        Three rules, all derived from how the package is already laid out:
        private classes (leading underscore) are implementation detail; classes
        defined below the scanned root — ``uitk/widgets/optionBox/``,
        ``editors/``, ``sequencer/`` — are internals of a larger widget rather
        than catalog entries; and window/popup classes cannot be dropped onto a
        form at all.
        """
        if widget_cls.__name__.startswith("_"):
            return False
        if not cls._is_root_module(widget_cls, root):
            return False
        if set(cls._qt_bases(widget_cls)) & set(cls._NON_PLACEABLE):
            return False
        return True

    @classmethod
    def _is_container(cls, widget_cls: type) -> bool:
        """Whether Designer should let child widgets be dropped onto this class.

        Derived from the Qt base — a ``QGroupBox`` subclass holds children, a
        ``QPushButton`` subclass does not. A plain-``QWidget`` container (uitk's
        ``Region``) has no such hint and says so with ``designer_spec``.
        """
        return bool(set(cls._qt_bases(widget_cls)) & set(cls._CONTAINER_BASES))

    @classmethod
    def _is_root_module(cls, widget_cls: type, root: str) -> bool:
        """Whether the class is defined in a module directly inside ``root``."""
        module = sys.modules.get(widget_cls.__module__)
        path = getattr(module, "__file__", None)
        if not path or not root:
            return False
        return os.path.normcase(
            os.path.dirname(os.path.abspath(path))
        ) == os.path.normcase(root)

    @classmethod
    def _tooltip(cls, widget_cls: type) -> str:
        """First sentence of the class docstring, for the widget-box tooltip."""
        doc = (widget_cls.__doc__ or "").strip()
        if not doc:
            return widget_cls.__name__
        summary = " ".join(doc.split("\n\n")[0].split())
        if len(summary) > cls._TOOLTIP_LIMIT:
            summary = summary[: cls._TOOLTIP_LIMIT - 1].rstrip() + "…"
        return summary

    #: Edge length of a rasterised widget-box icon, in pixels.
    _ICON_PX = 22

    @classmethod
    def _icon_cache_dir(cls, group: str) -> str:
        """Directory holding one group's rasterised widget-box icons.

        Keyed by group so two packages publishing a same-named icon (uitk's
        ``list`` and a downstream package's) can't overwrite each other's.
        """
        return os.path.join(tempfile.gettempdir(), "uitk-designer-icons", group)

    @classmethod
    def _icon_file(cls, name: str, group: str) -> str:
        """Resolve an icon name to a bitmap file Designer's widget box can load.

        Two problems solved at once. Resolution goes through
        :class:`~uitk.managers.icon_manager.IconManager` — the one icon
        resolver in the package — so registered icon directories, the installed
        wheel's package resources, and a source checkout all work, and a
        downstream package that called ``IconManager.register_icon_dir`` gets
        its own icons for free. An absolute path is taken as-is.

        Then the rasterisation: uitk ships SVG, but ``registerCustomWidget``'s
        ``icon`` argument does not go through Qt's SVG icon engine — hand it an
        ``.svg`` and the entry renders with no icon at all, silently. Bitmaps
        load, so the resolved icon is written out as a PNG.

        Needs a running ``QGuiApplication``, which is why this happens in
        :meth:`DesignerPlugin.register` rather than ``collect``. Returns ``""``
        on any failure — an iconless entry, never a lost registration.
        """
        if not name:
            return ""
        try:
            from qtpy import QtGui

            if os.path.isabs(name) and os.path.isfile(name):
                icon = QtGui.QIcon(name)
            else:
                from uitk.managers.icon_manager import IconManager

                icon = IconManager.get(name, size=(cls._ICON_PX, cls._ICON_PX))

            pixmap = icon.pixmap(cls._ICON_PX, cls._ICON_PX) if icon else None
            if pixmap is None or pixmap.isNull():
                logger.debug("No Designer icon found for %r", name)
                return ""

            cache_dir = cls._icon_cache_dir(group)
            os.makedirs(cache_dir, exist_ok=True)
            # Rewritten every registration rather than cached against a source
            # mtime: rendering 20-odd 22px pixmaps costs microseconds, and a
            # staleness check is one more thing to get wrong for no gain.
            png_path = os.path.join(
                cache_dir, f"{os.path.basename(name)}-{cls._ICON_PX}.png"
            )
            if pixmap.save(png_path, "PNG"):
                return png_path
        except Exception as error:  # noqa: BLE001 - cosmetic, never fatal
            logger.debug("Could not prepare Designer icon %r: %s", name, error)
        return ""

    @staticmethod
    def _default_object_name(widget_cls: type) -> str:
        """Fall back to Qt's own convention — the class name, lower camel case."""
        name = widget_cls.__name__
        return name[0].lower() + name[1:]

    @classmethod
    def _resolve_root(cls, source, base_dir) -> str:
        """Return the absolute directory a scan ``source`` resolves to."""
        if hasattr(source, "__file__"):  # a module or package
            path = os.path.abspath(source.__file__)
            return path if os.path.isdir(path) else os.path.dirname(path)
        if isinstance(source, str):
            path = (
                source
                if os.path.isabs(source)
                else os.path.join(base_dir or "", source)
            )
            return os.path.abspath(path)
        return ""

    @classmethod
    def _discover(cls, source, base_dir, recursive: bool) -> List[type]:
        """Return every widget class under ``source``, de-duplicated by identity.

        Delegates to the Switchboard's own registry so Designer sees exactly the
        classes the runtime loader would resolve — one scanner, not two.
        """
        from uitk.managers.registry_manager import RegistryManager

        manager = RegistryManager()
        manager.create(
            "widget_registry",
            source,
            base_dir=base_dir,
            recursive=recursive,
            fields=["classname", "classobj", "filename", "filepath"],
            inc_files="*.py",
            exc_files="*_ui.py",
        )

        found, seen = [], set()
        for row in manager.widget_registry.named_tuples or []:
            obj = row.classobj
            if not (isinstance(obj, type) and issubclass(obj, QtWidgets.QWidget)):
                continue
            if id(obj) in seen:  # re-exported from more than one module
                continue
            seen.add(id(obj))
            found.append(obj)
        return found


class DesignerPlugin(_DesignerPluginInternal):
    """Registrar that puts uitk widgets in Qt Designer's widget box.

    Three entry points, in the order you meet them:

    ``launch()``
        Start Qt Designer with this package wired in — ``python -m uitk.designer``.
    ``register()``
        Called from inside Designer by ``register_uitk_widgets.py``.
    ``collect()``
        The catalog as data, for tests and for inspecting what will be published.

    ``register`` takes a scan location, so a downstream package publishes its own
    widgets the same way uitk does::

        DesignerPlugin.register("widgets", base_dir=MAYATK_DIR, group="mayatk")

    Example:
        >>> catalog = DesignerPlugin.collect()
        >>> next(w.module for w in catalog if w.name == "PushButton")
        'uitk.widgets.pushButton'
    """

    #: Default widget-box group heading for uitk's own widgets.
    DEFAULT_GROUP = "uitk"

    @staticmethod
    def is_design_time() -> bool:
        """Whether this process is Qt Designer loading widgets for a form.

        Widgets that would otherwise act on their runtime environment — a
        ``Header`` that hides itself next to a native title bar, a
        ``CollapsableGroup`` that restores a saved collapsed state — consult
        this so a form in Designer shows the widget as authored.

        Delegates to :meth:`AttributesMixin.is_design_time`, which is where
        widgets read it from; the flag has one home, not two.
        """
        return AttributesMixin.is_design_time()

    @staticmethod
    def set_design_time(value: bool) -> None:
        """Mark (or unmark) this process as a Qt Designer session.

        :meth:`register` calls this for you. Exposed so a test — or a host that
        embeds Designer itself — can drive the flag directly.
        """
        AttributesMixin.set_design_time(value)

    @classmethod
    def collect(
        cls,
        source="widgets",
        base_dir: Optional[str] = None,
        group: Optional[str] = None,
        recursive: bool = True,
    ) -> List[DesignerWidget]:
        """Resolve Designer metadata for every widget class under ``source``.

        Parameters:
            source: Directory (relative to ``base_dir``), module, or package to
                scan. Defaults to uitk's own ``widgets`` directory.
            base_dir: Directory ``source`` is relative to. Defaults to the uitk
                package root.
            group: Widget-box group heading. Defaults to :attr:`DEFAULT_GROUP`.
            recursive: Whether to scan subdirectories. Subpackage widgets are
                still excluded from the box by default — see
                :meth:`_is_placeable` — but scanning them lets one opt in with
                ``designer_spec = {"visible": True}``.

        Returns:
            list[DesignerWidget]: Placeable widgets, sorted by name.
        """
        base_dir = base_dir or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        group = group or cls.DEFAULT_GROUP
        root = cls._resolve_root(source, base_dir)

        catalog = []
        for widget_cls in cls._discover(source, base_dir, recursive):
            spec = cls._spec(widget_cls)
            if not spec.get("visible", cls._is_placeable(widget_cls, root)):
                continue

            qt_base = cls._qt_base(widget_cls)
            if qt_base is None:
                logger.debug(
                    "Skipping %s: no Qt base class in its MRO", widget_cls.__name__
                )
                continue

            catalog.append(
                DesignerWidget(
                    cls=widget_cls,
                    name=widget_cls.__name__,
                    module=widget_cls.__module__,
                    base=qt_base,
                    group=spec.get("group", group),
                    tooltip=spec.get("tooltip") or cls._tooltip(widget_cls),
                    icon=spec.get("icon", ""),
                    container=bool(
                        spec.get("container", cls._is_container(widget_cls))
                    ),
                    object_name=spec.get("object_name")
                    or cls._default_object_name(widget_cls),
                    size=spec.get("size"),
                    string_properties=dict(spec.get("string_properties") or {}),
                )
            )
        return sorted(catalog, key=lambda w: w.name)

    @classmethod
    def register(
        cls,
        source="widgets",
        base_dir: Optional[str] = None,
        group: Optional[str] = None,
        recursive: bool = True,
    ) -> List[DesignerWidget]:
        """Publish the collected widgets to Qt Designer's widget box.

        Only meaningful inside Designer, which is the one process that provides
        ``QPyDesignerCustomWidgetCollection``. Elsewhere it logs and returns the
        catalog it would have registered, so a caller can check the result
        without a Designer running.

        Marks the process as design time (see :meth:`is_design_time`) — but only
        once those bindings are confirmed present, since that is the only proof
        this really is Designer. Flipping the flag in an ordinary application
        would leave every ``Header`` and ``CollapsableGroup`` in the process
        behaving as though its form were being authored.

        Returns:
            list[DesignerWidget]: The registered widgets.
        """
        catalog = cls.collect(
            source, base_dir=base_dir, group=group, recursive=recursive
        )

        try:
            from qtpy.QtDesigner import QPyDesignerCustomWidgetCollection
        except ImportError as error:
            logger.warning(
                "Qt Designer bindings unavailable (%s) — %d uitk widget(s) not "
                "registered. Designer integration needs PySide6.",
                error,
                len(catalog),
            )
            return catalog

        AttributesMixin.set_design_time(True)

        for widget in catalog:
            QPyDesignerCustomWidgetCollection.registerCustomWidget(
                widget.cls,
                xml=widget.xml,
                tool_tip=widget.tooltip,
                group=widget.group,
                module=widget.module,
                container=widget.container,
                icon=cls._icon_file(widget.icon, widget.group),
            )
        logger.info(
            "Registered %d widget(s) with Qt Designer under %r",
            len(catalog),
            group or cls.DEFAULT_GROUP,
        )
        return catalog

    @classmethod
    def plugin_dirs(cls) -> List[str]:
        """Directories holding a Designer entry file, for ``PYSIDE_DESIGNER_PLUGINS``.

        This package's own directory — the one containing
        ``register_uitk_widgets.py``, which is what Designer's scan for
        ``register*.py`` looks for.
        """
        return [os.path.dirname(os.path.abspath(__file__))]

    @classmethod
    def environment(
        cls,
        plugin_dirs: Optional[Sequence[str]] = None,
        python_paths: Optional[Sequence[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Return an environment mapping that lets Designer import and find uitk.

        Designer runs its own process: it needs ``PYSIDE_DESIGNER_PLUGINS`` to
        find the entry file and ``PYTHONPATH`` to import ``uitk`` at all — the
        latter matters whenever uitk is used from a source checkout rather than
        an installed wheel.

        Existing values in both variables are preserved, so several packages can
        publish widgets to the same Designer session.
        """
        env = dict(os.environ if env is None else env)
        plugin_dirs = list(plugin_dirs or cls.plugin_dirs())

        # uitk's own import root — the directory containing the `uitk` package.
        uitk_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        python_paths = [uitk_root, *(python_paths or [])]

        def _prepend(var: str, paths: Sequence[str]) -> None:
            existing = [p for p in env.get(var, "").split(os.pathsep) if p]
            merged = list(dict.fromkeys([*paths, *existing]))
            env[var] = os.pathsep.join(merged)

        _prepend(PLUGIN_PATH_ENV, plugin_dirs)
        _prepend("PYTHONPATH", python_paths)
        env[AttributesMixin.DESIGN_TIME_ENV] = "1"
        return env

    @classmethod
    def launch(
        cls,
        *ui_files: str,
        plugin_dirs: Optional[Sequence[str]] = None,
        python_paths: Optional[Sequence[str]] = None,
        wait: bool = True,
    ) -> int:
        """Start Qt Designer with uitk's widgets available in the widget box.

        Parameters:
            *ui_files: ``.ui`` files to open on start.
            plugin_dirs: Extra directories holding ``register*.py`` entry files —
                pass a downstream package's to publish its widgets alongside
                uitk's.
            python_paths: Extra import roots Designer needs to resolve those.
            wait: Block until Designer exits. False returns immediately with 0.

        Returns:
            int: Designer's exit code (0 when ``wait`` is False).

        Raises:
            FileNotFoundError: If the ``pyside6-designer`` launcher is missing.
        """
        executable = cls._designer_executable()
        if not executable:
            raise FileNotFoundError(
                "pyside6-designer was not found. Qt Designer integration requires "
                "PySide6 (`pip install PySide6`); PySide2 ships no Designer "
                "Python bindings."
            )

        env = cls.environment(plugin_dirs=plugin_dirs, python_paths=python_paths)
        command = [executable, *ui_files]
        logger.info("Launching %s", " ".join(command))

        process = subprocess.Popen(command, env=env)
        return process.wait() if wait else 0

    @staticmethod
    def _designer_executable() -> Optional[str]:
        """Locate ``pyside6-designer``, preferring the running interpreter's env."""
        names = ("pyside6-designer.exe", "pyside6-designer")
        for directory in (
            os.path.dirname(sys.executable),
            os.path.join(sys.prefix, "Scripts"),
            os.path.join(sys.prefix, "bin"),
        ):
            for name in names:
                candidate = os.path.join(directory, name)
                if os.path.exists(candidate):
                    return candidate
        for name in names:
            found = shutil.which(name)
            if found:
                return found
        return None


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for entry in DesignerPlugin.collect():
        flags = " [container]" if entry.container else ""
        print(f"{entry.name:20s} {entry.base:18s} {entry.module}{flags}")
