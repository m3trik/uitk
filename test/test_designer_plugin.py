# !/usr/bin/python
# coding=utf-8
"""Unit tests for the Qt Designer widget-box plugin.

Covers the three things that decide whether uitk widgets are usable in
Designer at all:

1. The catalog holds the right classes — every public widget, no windows,
   popups, or internals.
2. Each entry's ``domXml`` is well-formed and names the class, the header
   module, and the default objectName Designer needs.
3. Every catalogued class survives ``cls(parent)`` — the single-argument
   call Designer makes when a widget is dropped — and exposes its declared
   Qt properties on the resulting instance.

The registration call itself is exercised through its no-Designer path,
which is what any process other than Designer takes.

Run standalone: python -m test.test_designer_plugin
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets  # noqa: E402

from uitk.designer._designer import DesignerPlugin, DesignerWidget  # noqa: E402
from uitk.widgets.mixins.attributes import AttributesMixin  # noqa: E402


class TestDesignerCatalog(unittest.TestCase):
    """What the widget box is offered, and what it must never offer."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = DesignerPlugin.collect()
        cls.by_name = {w.name: w for w in cls.catalog}

    def test_catalog_is_not_empty(self):
        """A silently empty catalog is the failure mode this whole file guards."""
        self.assertGreater(len(self.catalog), 10)

    def test_includes_the_common_widgets(self):
        """The widgets a form is actually built from must all be present."""
        for name in (
            "PushButton",
            "CheckBox",
            "ComboBox",
            "LineEdit",
            "Label",
            "Header",
            "Footer",
            "CollapsableGroup",
            "TreeWidget",
            "TableWidget",
            "MenuButton",
        ):
            with self.subTest(widget=name):
                self.assertIn(name, self.by_name)

    def test_excludes_windows_and_popups(self):
        """Windows, dialogs, and popups can't be dropped onto a form."""
        for name in (
            "MainWindow",
            "MessageBox",
            "Menu",
            "PersistentMenu",
            "TextViewBox",
        ):
            with self.subTest(widget=name):
                self.assertNotIn(name, self.by_name)

    def test_excludes_private_and_subpackage_internals(self):
        """Implementation detail must not leak into the widget box."""
        for name in (
            "_HeaderActionBar",
            "OptionBoxContainer",
            "Overlay",
            "CornerSizeGrip",
            "AlignedComboBox",
            "StyleEditor",
        ):
            with self.subTest(widget=name):
                self.assertNotIn(name, self.by_name)

    def test_header_module_is_the_import_path(self):
        """``module`` becomes the ``<header>`` in the .ui — it must be importable."""
        self.assertEqual(self.by_name["PushButton"].module, "uitk.widgets.pushButton")
        self.assertEqual(self.by_name["Header"].module, "uitk.widgets.header")

    def test_qt_base_is_resolved_through_the_mro(self):
        """The ``<extends>` class has to be the nearest real Qt base."""
        self.assertEqual(self.by_name["PushButton"].base, "QPushButton")
        self.assertEqual(self.by_name["CollapsableGroup"].base, "QGroupBox")
        self.assertEqual(self.by_name["Header"].base, "QLabel")

    def test_containers_accept_child_widgets(self):
        """Widgets that exist to hold children must be droppable containers."""
        for name in ("CollapsableGroup", "ToolBox", "Region"):
            with self.subTest(widget=name):
                self.assertTrue(self.by_name[name].container)

    def test_leaf_widgets_are_not_containers(self):
        """A button that accepted child widgets would be a Designer trap."""
        for name in ("PushButton", "CheckBox", "LineEdit"):
            with self.subTest(widget=name):
                self.assertFalse(self.by_name[name].container)

    def test_every_entry_has_a_tooltip(self):
        """The widget box shows the tooltip; an empty one reads as a bug."""
        for widget in self.catalog:
            with self.subTest(widget=widget.name):
                self.assertTrue(widget.tooltip.strip())

    def test_every_icon_name_resolves(self):
        """A typo'd icon name silently blanks the widget-box entry.

        Resolution goes through ``IconManager``, so this also pins that every
        name a ``designer_spec`` asks for is actually shipped in ``uitk/icons``.
        """
        from uitk.managers.icon_manager import IconManager

        for widget in self.catalog:
            if not widget.icon:
                continue
            with self.subTest(widget=widget.name, icon=widget.icon):
                self.assertFalse(
                    IconManager.get(widget.icon).isNull(),
                    f"{widget.name}: no icon named {widget.icon!r}",
                )

    def test_object_names_follow_the_ecosystem_convention(self):
        """Dropped widgets should already carry the prefix the .ui files use."""
        self.assertEqual(self.by_name["PushButton"].object_name, "tb")
        self.assertEqual(self.by_name["ComboBox"].object_name, "cmb")
        self.assertEqual(self.by_name["CheckBox"].object_name, "chk")

    def test_collect_is_a_pure_query(self):
        """``collect`` must not need Qt, touch disk, or flip the design-time flag.

        It is the introspection entry point — used by ``--list``, by tests, and
        by anything asking "what would be published". Resolving icons here would
        drag in a ``QGuiApplication`` and write PNGs as a side effect of asking
        a question; that work belongs in ``register``.
        """
        previous = os.environ.get(AttributesMixin.DESIGN_TIME_ENV)
        os.environ.pop(AttributesMixin.DESIGN_TIME_ENV, None)
        try:
            catalog = DesignerPlugin.collect()
            self.assertFalse(AttributesMixin.is_design_time())
            for widget in catalog:
                with self.subTest(widget=widget.name):
                    # An icon *name*, not a resolved path.
                    self.assertFalse(os.path.isabs(widget.icon))
        finally:
            if previous is not None:
                os.environ[AttributesMixin.DESIGN_TIME_ENV] = previous

    def test_designer_spec_is_not_inherited(self):
        """A subclass must not silently adopt its parent's Designer entry.

        ``ColorSwatch`` extends ``PushButton``; reading ``designer_spec``
        through the MRO would give it the button's object-name prefix.
        """
        self.assertEqual(self.by_name["ColorSwatch"].object_name, "swatch")


class TestDesignerXml(unittest.TestCase):
    """The domXml snippet Designer inserts when a widget is dropped."""

    @classmethod
    def setUpClass(cls):
        cls.by_name = {w.name: w for w in DesignerPlugin.collect()}

    def test_xml_is_well_formed(self):
        """Malformed XML is rejected by Designer with no visible diagnostic."""
        for name, widget in self.by_name.items():
            with self.subTest(widget=name):
                ET.fromstring(widget.xml)

    def test_xml_names_the_class_and_object_name(self):
        """Designer reads both off the root ``<widget>`` element."""
        root = ET.fromstring(self.by_name["PushButton"].xml)
        element = root.find("widget")
        self.assertEqual(element.get("class"), "PushButton")
        self.assertEqual(element.get("name"), "tb")

    def test_xml_carries_the_header_module(self):
        """Without ``<header>`` the generated .ui can't import the class."""
        root = ET.fromstring(self.by_name["PushButton"].xml)
        header = root.find("customwidgets/customwidget/header")
        self.assertEqual(header.text, "uitk.widgets.pushButton")

    def test_every_entry_carries_its_header_module(self):
        """No entry may save a form that can't be loaded back."""
        for name, widget in self.by_name.items():
            with self.subTest(widget=name):
                root = ET.fromstring(widget.xml)
                header = root.find("customwidgets/customwidget/header")
                self.assertIsNotNone(header, f"{name} has no <header>")
                self.assertEqual(header.text, widget.module)

    def test_rich_text_properties_declare_an_editor(self):
        """PushButton renders HTML, so Designer must offer its HTML editor."""
        root = ET.fromstring(self.by_name["PushButton"].xml)
        specs = root.findall(
            "customwidgets/customwidget/propertyspecifications/"
            "stringpropertyspecification"
        )
        self.assertIn(
            ("text", "richtext"), [(s.get("name"), s.get("type")) for s in specs]
        )

    def test_declared_size_becomes_drop_geometry(self):
        """A widget with no useful sizeHint needs an explicit drop size."""
        root = ET.fromstring(self.by_name["CollapsableGroup"].xml)
        rect = root.find("widget/property/rect")
        self.assertEqual(rect.find("width").text, "200")
        self.assertEqual(rect.find("height").text, "120")

    def test_tooltip_with_markup_is_escaped(self):
        """A docstring containing < or & must not break the XML."""
        widget = DesignerWidget(
            cls=QtWidgets.QWidget,
            name="Probe",
            module="probe.module",
            base="QWidget",
            group="uitk",
            tooltip='Uses <b>markup</b> & "quotes"',
            icon="",
            container=False,
            object_name="probe",
            size=None,
            string_properties={},
        )
        root = ET.fromstring(widget.xml)  # would raise if unescaped
        self.assertEqual(
            root.find("customwidgets/customwidget/tooltip").text,
            'Uses <b>markup</b> & "quotes"',
        )


class TestDesignerInstantiation(QtBaseTestCase):
    """Every catalogued class must survive the call Designer actually makes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.catalog = DesignerPlugin.collect()

    def test_every_widget_constructs_from_a_bare_parent(self):
        """Designer calls ``cls(parent)`` — nothing else, no keywords."""
        for widget in self.catalog:
            with self.subTest(widget=widget.name):
                form = QtWidgets.QWidget()
                try:
                    instance = widget.cls(form)
                finally:
                    form.deleteLater()
                self.assertIsInstance(instance, QtWidgets.QWidget)

    def test_declared_properties_reach_the_meta_object(self):
        """A Qt property Designer can't see in the QMetaObject isn't editable."""
        expected = {
            "Header": ("helpText", "configButtons", "pinOnDragOnly"),
            "Footer": ("status", "defaultStatusText", "sizeGripEnabled"),
            "MenuButton": ("target", "filterTags"),
            "Region": ("visibleOnMouseOver",),
            "Separator": ("title",),
            "ProgressBar": ("autoHide", "cancelHoldMs"),
            "ColorSwatch": ("swatchColor", "keepSquare"),
            "TreeWidget": ("selectionStyle", "ctrlToggle"),
            "TableWidget": ("leftClickSelectOnly",),
            "CollapsableGroup": ("restoreState",),
            "ComboBox": ("currentTextPrefix", "currentTextSuffix"),
            "ExpandableList": ("expandPosition", "fixedItemHeight"),
        }
        by_name = {w.name: w for w in self.catalog}
        for name, properties in expected.items():
            form = QtWidgets.QWidget()
            instance = by_name[name].cls(form)
            meta = instance.metaObject()
            declared = {meta.property(i).name() for i in range(meta.propertyCount())}
            for prop in properties:
                with self.subTest(widget=name, property=prop):
                    self.assertIn(prop, declared)
            form.deleteLater()

    def test_every_declared_property_has_a_matching_setter(self):
        """``pyside6-uic`` compiles a .ui property into a ``set<Name>()`` call.

        Declaring ``foo = QtCore.Property(..., fset=<lambda>)`` and nothing else
        loads fine through ``QUiLoader`` and raises ``AttributeError`` in a
        compiled form — so a widget works in Designer, saves, and then breaks
        only for consumers on the compiled path. Every property a form can
        carry must have the camelCase setter uic will reach for.
        """
        for widget in self.catalog:
            form = QtWidgets.QWidget()
            instance = widget.cls(form)
            meta = instance.metaObject()
            base_meta = getattr(
                next(
                    (a for a in widget.cls.__mro__[1:] if a.__name__ == widget.base),
                    None,
                ),
                "staticMetaObject",
                None,
            )
            inherited = (
                {base_meta.property(i).name() for i in range(base_meta.propertyCount())}
                if base_meta
                else set()
            )
            for index in range(meta.propertyCount()):
                name = meta.property(index).name()
                if name in inherited:
                    continue  # Qt's own properties already have their setters
                setter = f"set{name[0].upper()}{name[1:]}"
                with self.subTest(widget=widget.name, property=name):
                    self.assertTrue(
                        callable(getattr(instance, setter, None)),
                        f"{widget.name}.{name} has no {setter}()",
                    )
            form.deleteLater()

    def test_properties_round_trip_through_the_qt_api(self):
        """Designer writes through ``setProperty``; the value must stick."""
        cases = [
            ("Header", "helpText", "Press to export"),
            ("Footer", "status", "Ready"),
            ("Separator", "title", "Options"),
            ("MenuButton", "target", "polygons#submenu"),
            ("Region", "visibleOnMouseOver", True),
            ("ProgressBar", "cancelHoldMs", 250),
            ("TreeWidget", "selectionStyle", "tint"),
            ("TableWidget", "leftClickSelectOnly", True),
            ("CollapsableGroup", "restoreState", False),
            ("ComboBox", "currentTextPrefix", "Target: "),
            ("ExpandableList", "expandPosition", "left"),
        ]
        by_name = {w.name: w for w in self.catalog}
        for name, prop, value in cases:
            with self.subTest(widget=name, property=prop):
                form = QtWidgets.QWidget()
                instance = by_name[name].cls(form)
                self.assertTrue(instance.setProperty(prop, value))
                self.assertEqual(instance.property(prop), value)
                form.deleteLater()


class TestUiRoundTrip(QtBaseTestCase):
    """A form authored in Designer must load back with its values intact.

    The two loaders take different routes to the same ``.ui``:
    ``pyside6-uic`` compiles each property into a ``set<Name>()`` call, while
    ``QUiLoader`` goes through ``setProperty``. A property can satisfy one and
    fail the other, so both are exercised.
    """

    # A property per widget, in the form Designer writes it.
    FORM_PROPERTIES = {
        "Header": {"helpText": ("string", "Help from Designer")},
        "MenuButton": {"target": ("string", "polygons#submenu")},
        "Separator": {"title": ("string", "Options")},
        "CollapsableGroup": {"restoreState": ("bool", "false")},
        "ProgressBar": {"cancelHoldMs": ("number", "750")},
        "TreeWidget": {"selectionStyle": ("string", "tint")},
        "TableWidget": {"leftClickSelectOnly": ("bool", "true")},
        "Footer": {"status": ("string", "Ready")},
        "ComboBox": {"currentTextPrefix": ("string", "Target: ")},
        "Region": {"visibleOnMouseOver": ("bool", "true")},
        "ExpandableList": {"expandPosition": ("string", "left")},
        "ColorSwatch": {"keepSquare": ("bool", "true")},
    }

    EXPECTED = {
        "Header": {"helpText": "Help from Designer"},
        "MenuButton": {"target": "polygons#submenu"},
        "Separator": {"title": "Options"},
        "CollapsableGroup": {"restoreState": False},
        "ProgressBar": {"cancelHoldMs": 750},
        "TreeWidget": {"selectionStyle": "tint"},
        "TableWidget": {"leftClickSelectOnly": True},
        "Footer": {"status": "Ready"},
        "ComboBox": {"currentTextPrefix": "Target: "},
        "Region": {"visibleOnMouseOver": True},
        "ExpandableList": {"expandPosition": "left"},
        "ColorSwatch": {"keepSquare": True},
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.by_name = {w.name: w for w in DesignerPlugin.collect()}
        cls.tmp_dir = tempfile.mkdtemp(prefix="uitk_designer_test_")
        cls.ui_path = os.path.join(cls.tmp_dir, "roundtrip.ui")
        with open(cls.ui_path, "w", encoding="utf-8") as handle:
            handle.write(cls._build_ui())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def _build_ui(cls) -> str:
        """Compose a .ui the way Designer would, from the plugin's own metadata."""
        widgets, customs, top = [], [], 0
        for name, properties in cls.FORM_PROPERTIES.items():
            entry = cls.by_name[name]
            body = "".join(
                f'<property name="{prop}"><{kind}>{value}</{kind}></property>'
                for prop, (kind, value) in properties.items()
            )
            widgets.append(
                f'<widget class="{name}" name="{entry.object_name}_probe">'
                f'<property name="geometry"><rect><x>0</x><y>{top}</y>'
                f"<width>200</width><height>24</height></rect></property>"
                f"{body}</widget>"
            )
            customs.append(
                f"<customwidget><class>{name}</class>"
                f"<extends>{entry.base}</extends>"
                f"<header>{entry.module}</header>"
                + ("<container>1</container>" if entry.container else "")
                + "</customwidget>"
            )
            top += 30
        return (
            '<?xml version="1.0" encoding="UTF-8"?><ui version="4.0">'
            "<class>roundtrip</class>"
            '<widget class="QMainWindow" name="roundtrip">'
            '<property name="geometry"><rect><x>0</x><y>0</y>'
            f"<width>420</width><height>{top + 40}</height></rect></property>"
            '<widget class="QWidget" name="central_widget">'
            + "".join(widgets)
            + "</widget></widget><customwidgets>"
            + "".join(customs)
            + "</customwidgets><resources/><connections/></ui>"
        )

    def _verify(self, window):
        for name, properties in self.EXPECTED.items():
            object_name = f"{self.by_name[name].object_name}_probe"
            widget = window.findChild(QtWidgets.QWidget, object_name)
            self.assertIsNotNone(widget, f"{name} missing from the loaded form")
            for prop, expected in properties.items():
                with self.subTest(widget=name, property=prop):
                    self.assertEqual(widget.property(prop), expected)

    def test_compiled_by_pyside6_uic(self):
        """uic emits ``set<Name>()`` — a property with no such method breaks here."""
        uic = shutil.which("pyside6-uic") or os.path.join(
            os.path.dirname(sys.executable), "pyside6-uic.exe"
        )
        if not os.path.exists(uic):
            self.skipTest("pyside6-uic not available")

        module_path = os.path.join(self.tmp_dir, "roundtrip_ui.py")
        result = subprocess.run(
            [uic, self.ui_path, "-o", module_path], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        spec = importlib.util.spec_from_file_location("roundtrip_ui", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        window = QtWidgets.QMainWindow()
        module.Ui_roundtrip().setupUi(window)
        self._verify(window)
        window.deleteLater()

    def test_loaded_by_quiloader(self):
        """The runtime path goes through ``setProperty`` instead."""
        from qtpy.QtUiTools import QUiLoader

        loader = QUiLoader()
        for entry in self.by_name.values():
            loader.registerCustomWidget(entry.cls)
        window = loader.load(self.ui_path)
        self.assertIsNotNone(window, "QUiLoader could not load the form")
        self._verify(window)
        window.deleteLater()


class TestDesignTimeFlag(unittest.TestCase):
    """The switch widgets consult to stay inert while a form is authored."""

    def setUp(self):
        self._previous = os.environ.get(AttributesMixin.DESIGN_TIME_ENV)

    def tearDown(self):
        if self._previous is None:
            os.environ.pop(AttributesMixin.DESIGN_TIME_ENV, None)
        else:
            os.environ[AttributesMixin.DESIGN_TIME_ENV] = self._previous

    def test_defaults_to_off(self):
        """A normal application run must never look like design time."""
        os.environ.pop(AttributesMixin.DESIGN_TIME_ENV, None)
        self.assertFalse(AttributesMixin.is_design_time())
        self.assertFalse(DesignerPlugin.is_design_time())

    def test_set_and_clear(self):
        """The plugin and the widgets must read the same flag."""
        DesignerPlugin.set_design_time(True)
        self.assertTrue(AttributesMixin.is_design_time())
        DesignerPlugin.set_design_time(False)
        self.assertFalse(AttributesMixin.is_design_time())

    def test_falsey_strings_read_as_off(self):
        """``UITK_DESIGNER=0`` in a shell profile must not enable design time."""
        for value in ("0", "false", "False", "no", ""):
            with self.subTest(value=value):
                os.environ[AttributesMixin.DESIGN_TIME_ENV] = value
                self.assertFalse(AttributesMixin.is_design_time())


class TestDesignTimeBehaviour(QtBaseTestCase):
    """Widgets that adapt to their runtime must not do so inside Designer."""

    def setUp(self):
        super().setUp()
        self._previous = os.environ.get(AttributesMixin.DESIGN_TIME_ENV)
        DesignerPlugin.set_design_time(True)

    def tearDown(self):
        if self._previous is None:
            DesignerPlugin.set_design_time(False)
        else:
            os.environ[AttributesMixin.DESIGN_TIME_ENV] = self._previous
        super().tearDown()

    def test_header_does_not_hide_itself_on_a_framed_window(self):
        """A Designer form is framed; auto-hide would erase the header on drop."""
        from uitk.widgets.header import Header

        window = QtWidgets.QWidget()  # ordinary framed window
        header = Header(window, auto_hide_with_os_frame=True)
        header._apply_auto_hide_with_os_frame()
        self.assertFalse(header.isHidden())

    def test_collapsable_group_stays_expanded(self):
        """Restoring a saved collapsed state hides the children being laid out."""
        from uitk.widgets.collapsableGroup import CollapsableGroup

        group = CollapsableGroup("Options")
        group.setObjectName("designtime_probe")
        group.settings.setValue(f"CollapsableGroup/{group.objectName()}/checked", False)
        group._enforce_state()
        self.assertTrue(group.isChecked())

    def test_region_keeps_its_children_visible(self):
        """A Region that hides children on drop can't be laid out."""
        from uitk.widgets.region import Region

        region = Region(None, visible_on_mouse_over=True)
        child = QtWidgets.QLabel("child", region)
        child.show()
        region.hide_top_level_children()
        self.assertFalse(child.isHidden())


class TestRegisterAndEnvironment(QtBaseTestCase):
    """Registration, and the environment handed to a Designer subprocess."""

    def setUp(self):
        super().setUp()
        self._previous = os.environ.get(AttributesMixin.DESIGN_TIME_ENV)

    def tearDown(self):
        if self._previous is None:
            DesignerPlugin.set_design_time(False)
        else:
            os.environ[AttributesMixin.DESIGN_TIME_ENV] = self._previous
        super().tearDown()

    def test_returns_the_catalog_it_would_register(self):
        """The caller can verify the result without inspecting Designer."""
        registered = DesignerPlugin.register()
        self.assertEqual(
            [w.name for w in registered], [w.name for w in DesignerPlugin.collect()]
        )

    def test_icons_become_bitmaps_designer_can_actually_load(self):
        """``registerCustomWidget``'s icon argument silently ignores SVG.

        uitk ships only SVG, so an un-rasterised icon means every widget-box
        entry renders blank — a failure with no error anywhere. Assert the
        resolved file is a bitmap that loads.
        """
        from qtpy import QtGui

        named = [w for w in DesignerPlugin.collect() if w.icon]
        self.assertTrue(named, "no widget declares an icon")
        for widget in named:
            with self.subTest(widget=widget.name):
                path = DesignerPlugin._icon_file(widget.icon, widget.group)
                self.assertTrue(os.path.isfile(path), f"{widget.icon!r} -> {path!r}")
                self.assertFalse(path.lower().endswith(".svg"))
                self.assertFalse(QtGui.QPixmap(path).isNull())

    def test_unknown_icon_name_degrades_to_no_icon(self):
        """A bad name must cost the entry its icon, never its registration."""
        self.assertEqual(DesignerPlugin._icon_file("not_a_real_icon", "uitk"), "")
        self.assertEqual(DesignerPlugin._icon_file("", "uitk"), "")

    def test_icon_cache_is_scoped_by_group(self):
        """Two packages publishing a same-named icon must not collide."""
        self.assertNotEqual(
            DesignerPlugin._icon_cache_dir("uitk"),
            DesignerPlugin._icon_cache_dir("mayatk"),
        )

    def test_environment_carries_the_plugin_path_and_import_root(self):
        """Designer is a separate process: both must be handed to it."""
        env = DesignerPlugin.environment(env={})
        plugin_dirs = env["PYSIDE_DESIGNER_PLUGINS"].split(os.pathsep)
        self.assertIn(DesignerPlugin.plugin_dirs()[0], plugin_dirs)
        self.assertTrue(env["PYTHONPATH"])
        self.assertEqual(env[AttributesMixin.DESIGN_TIME_ENV], "1")

    def test_environment_preserves_existing_entries(self):
        """Another package's widgets must survive being joined by uitk's."""
        env = DesignerPlugin.environment(
            env={"PYSIDE_DESIGNER_PLUGINS": "/other/plugins"}
        )
        self.assertIn(
            "/other/plugins", env["PYSIDE_DESIGNER_PLUGINS"].split(os.pathsep)
        )

    def test_plugin_dir_holds_the_entry_file_designer_scans_for(self):
        """PySide6's Designer plugin only imports files matching register*.py."""
        directory = DesignerPlugin.plugin_dirs()[0]
        entries = [
            name
            for name in os.listdir(directory)
            if name.startswith("register") and name.endswith(".py")
        ]
        self.assertTrue(entries, f"no register*.py in {directory}")


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
