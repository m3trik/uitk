# !/usr/bin/python
# coding=utf-8
"""Tests for PanelRenames: a renamed panel's saved values carried to the panel
that took its name.

The stores are a real ``SettingsManager`` over a throwaway ini file; the
switchboard is a stand-in carrying exactly what ``carry`` reads (its settings
root, ``configurable``, ``context_tags``, the Slots-class pairing and a UI
handler's persistence overrides), and one case runs over a real ``Switchboard``.

Run standalone: python test/test_panel_renames.py
"""

import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

import conftest  # noqa: F401 -- inserts the package root on sys.path

from qtpy import QtCore
from uitk.managers.panel_renames import PanelRenames
from uitk.managers.settings_manager import SettingsManager

#: The renames under test: two panels merged into one (the second's ``txt000``
#: renamed, its first claimed by the other), and two into another.
RENAMED_FROM = {
    "dcc_bridge": {"blender_bridge": {}, "maya_bridge": {}},
    "workspaces": {"workspace_map": {}, "workspace_editor": {"txt000": "txt002"}},
}


class _Persistence:
    """A UI handler's per-window persistence overrides, over a dict."""

    def __init__(self):
        self.modes = {}

    def persistence_override(self, name):
        return self.modes.get(name)

    def set_persistence_override(self, name, mode):
        self.modes[name] = mode


def _slot_class_names(panel):
    """The Switchboard's pairing: the Slots class, then the pre-suffix name."""
    base = "".join(part.title() for part in panel.split("_"))
    return [f"{base}Slots", base]


class TestPanelRenames(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="panel_renames_")
        self.addCleanup(shutil.rmtree, tmp, True)
        qsettings = QtCore.QSettings(
            os.path.join(tmp, "store.ini"), QtCore.QSettings.IniFormat
        )
        #: One store for both hosts, as QSettings is (each host's keys suffixed).
        self.settings = SettingsManager(qsettings=qsettings, namespace="switchboard")
        self.persistence = _Persistence()

    def _switchboard(self, host):
        return types.SimpleNamespace(
            settings=self.settings,
            configurable=self.settings.branch("configurable"),
            context_tags={host},
            get_slot_class_names=_slot_class_names,
            handlers=types.SimpleNamespace(ui=self.persistence),
            logger=mock.Mock(),
        )

    def _seed(self, branch, values):
        store = self.settings.branch(branch)
        for key, value in values.items():
            store.setValue(key, value)

    def _values(self, branch):
        store = self.settings.branch(branch)
        return {key: store.value(key) for key in store.keys()}

    def test_each_host_carries_its_former_panels_values(self):
        self._seed(
            "blender_bridge_maya",
            {
                "cmb000/currentIndexChanged": 2,
                "shortcuts_maya.BlenderBridgeSlots.b000": "Ctrl+B",
                "shortcuts_maya.BlenderBridgeSlots.b000.scope": "window",
                "shortcuts_maya.BlenderBridge.b000.hidden": True,
            },
        )
        self._seed("workspace_map_maya", {"txt000/textChanged": "C:/projects"})
        self._seed(
            "workspace_editor_blender",
            {
                "txt000/textChanged": "C:/projects/shot",
                "workspace_root": "C:/projects/shot",
            },
        )
        self.persistence.modes["blender_bridge"] = "transient"
        carried = PanelRenames.carry(self._switchboard("maya"), RENAMED_FROM)
        PanelRenames.carry(self._switchboard("blender"), RENAMED_FROM)

        self.assertEqual(
            sorted(carried),
            ["blender_bridge", "maya_bridge", "workspace_editor", "workspace_map"],
        )
        self.assertEqual(
            self._values("dcc_bridge_maya"),
            {
                "cmb000/currentIndexChanged": 2,
                "shortcuts_maya.DccBridgeSlots.b000": "Ctrl+B",
                "shortcuts_maya.DccBridgeSlots.b000.scope": "window",
                "shortcuts_maya.DccBridgeSlots.b000.hidden": True,
            },
        )
        self.assertEqual(self.persistence.modes["dcc_bridge"], "transient")
        # One kept its field's name; the other's moved to txt002.
        self.assertEqual(
            self._values("workspaces_maya"), {"txt000/textChanged": "C:/projects"}
        )
        self.assertEqual(
            self._values("workspaces_blender"),
            {
                "txt002/textChanged": "C:/projects/shot",
                "workspace_root": "C:/projects/shot",
            },
        )
        self.assertEqual(self._values("dcc_bridge_blender"), {})
        # The former branches stay (as the shortcut migration leaves its sources).
        self.assertEqual(
            self._values("workspace_map_maya"), {"txt000/textChanged": "C:/projects"}
        )

    def test_the_new_panels_own_value_wins_and_each_host_carries_once(self):
        self._seed(
            "blender_bridge_maya",
            {"cmb000/currentIndexChanged": 2, "chk000/toggled": True},
        )
        self._seed("dcc_bridge_maya", {"cmb000/currentIndexChanged": 5})
        sb = self._switchboard("maya")
        PanelRenames.carry(sb, RENAMED_FROM)
        self.assertEqual(
            self._values("dcc_bridge_maya"),
            {"cmb000/currentIndexChanged": 5, "chk000/toggled": True},
        )
        self.assertEqual(
            sorted(sb.configurable.value(PanelRenames.CARRIED_KEY + "_maya")),
            ["blender_bridge", "maya_bridge", "workspace_editor", "workspace_map"],
        )
        # A value the user clears afterwards stays cleared.
        self.settings.branch("dcc_bridge_maya").remove("chk000/toggled")
        self.assertEqual(PanelRenames.carry(sb, RENAMED_FROM), [])
        self.assertNotIn("chk000/toggled", self._values("dcc_bridge_maya"))
        # Each host keeps its own record.
        self.assertIsNone(sb.configurable.value(PanelRenames.CARRIED_KEY + "_blender"))

    def test_a_rename_added_later_still_carries(self):
        sb = self._switchboard("maya")
        PanelRenames.carry(sb, {"dcc_bridge": {"blender_bridge": {}}})
        self._seed("old_tool_maya", {"s000/valueChanged": 3})
        self.assertEqual(
            PanelRenames.carry(sb, {**RENAMED_FROM, "new_tool": {"old_tool": {}}})[-1],
            "old_tool",
        )
        self.assertEqual(self._values("new_tool_maya"), {"s000/valueChanged": 3})

    def test_slot_class_names_can_be_given(self):
        self._seed("blender_bridge_maya", {"shortcuts_maya.SendToBlender.b000": "B"})
        PanelRenames.carry(
            self._switchboard("maya"),
            {"dcc_bridge": {"blender_bridge": {}}},
            slot_class_names=lambda panel: {
                "dcc_bridge": ["DccBridgeSlots"],
                "blender_bridge": ["SendToBlender"],
            }[panel],
        )
        self.assertEqual(
            self._values("dcc_bridge_maya"), {"shortcuts_maya.DccBridgeSlots.b000": "B"}
        )

    def test_an_unreadable_store_never_raises(self):
        sb = self._switchboard("maya")
        sb.configurable = mock.Mock(value=mock.Mock(side_effect=RuntimeError("locked")))
        self.assertEqual(PanelRenames.carry(sb, RENAMED_FROM), [])
        sb.logger.debug.assert_called_once()

    def test_a_saved_default_moves_with_its_widget_and_a_custom_key_stays(self):
        """``StateManager`` keeps a widget's saved default beside its session value
        (``defaults/<objectName>/<signal>``): a renamed widget's default follows
        it, or Reset would land it on another widget. A custom key names no
        widget and carries as it is."""
        self._seed(
            "workspace_editor_blender",
            {
                "txt000/textChanged": "C:/projects/shot",
                "defaults/txt000/textChanged": "C:/projects",
                "custom/txt000": "kept",
            },
        )
        PanelRenames.carry(self._switchboard("blender"), RENAMED_FROM)
        self.assertEqual(
            self._values("workspaces_blender"),
            {
                "txt002/textChanged": "C:/projects/shot",
                "defaults/txt002/textChanged": "C:/projects",
                "custom/txt000": "kept",
            },
        )

    def test_the_current_class_spelling_wins_over_a_legacy_one(self):
        """An override under the pre-``Slots`` class name is older than one under
        the current name: the current one is carried, the stale one never
        shadows it."""
        self._seed(
            "blender_bridge_maya",
            {
                "shortcuts_maya.BlenderBridge.b000": "Ctrl+Old",
                "shortcuts_maya.BlenderBridgeSlots.b000": "Ctrl+New",
                "shortcuts_maya.BlenderBridge.b001": "Ctrl+Only",
            },
        )
        PanelRenames.carry(self._switchboard("maya"), RENAMED_FROM)
        target = self.settings.branch("dcc_bridge_maya")
        self.assertEqual(target.value("shortcuts_maya.DccBridgeSlots.b000"), "Ctrl+New")
        self.assertEqual(target.value("shortcuts_maya.DccBridgeSlots.b001"), "Ctrl+Only")

    def test_one_failing_former_panel_never_repeats_the_others(self):
        """Each former panel is marked carried as soon as it is: one that fails is
        retried on the next launch, alone."""
        self._seed("blender_bridge_maya", {"cmb000/currentIndexChanged": 2})
        sb = self._switchboard("maya")
        real = PanelRenames._carry_panel.__func__

        def flaky(cls, switchboard, suffix, panel, former, *args):
            if former == "workspace_map":
                raise RuntimeError("locked")
            return real(cls, switchboard, suffix, panel, former, *args)

        with mock.patch.object(PanelRenames, "_carry_panel", classmethod(flaky)):
            carried = PanelRenames.carry(sb, RENAMED_FROM)
        self.assertEqual(
            sorted(carried), ["blender_bridge", "maya_bridge", "workspace_editor"]
        )
        self.assertEqual(
            self._values("dcc_bridge_maya"), {"cmb000/currentIndexChanged": 2}
        )
        self.assertEqual(PanelRenames.carry(sb, RENAMED_FROM), ["workspace_map"])

    def test_renamed_key(self):
        classes = {"OldSlots": "NewSlots", "Old": "NewSlots"}
        key = PanelRenames.renamed_key
        self.assertEqual(
            key("txt000/textChanged", {"txt000": "txt002"}, classes),
            "txt002/textChanged",
        )
        self.assertEqual(key("workspace_root", {}, classes), "workspace_root")
        self.assertEqual(
            key("defaults/txt000/textChanged", {"txt000": "txt002"}, classes),
            "defaults/txt002/textChanged",
        )
        self.assertEqual(
            key("custom/txt000", {"txt000": "txt002"}, classes), "custom/txt000"
        )
        self.assertEqual(
            key("shortcuts_blender.Old.txt000.scope", {"txt000": "txt002"}, classes),
            "shortcuts_blender.NewSlots.txt002.scope",
        )
        self.assertEqual(
            key("shortcuts_maya.Other.b000", {}, classes), "shortcuts_maya.Other.b000"
        )


class TestPanelRenamesOverASwitchboard(unittest.TestCase):
    """The same carry over a real ``Switchboard`` (the suite's sandboxed
    stores): its settings branches, host suffix and Slots-class pairing are the
    ones a loaded panel reads."""

    @classmethod
    def setUpClass(cls):
        from conftest import setup_qt_application

        cls.app = setup_qt_application()

    def test_a_switchboard_carries_through_its_own_api(self):
        from uitk import Switchboard

        sb = Switchboard(context_tags={"blender"})
        source = sb.settings.branch("maya_bridge_blender")
        source.setValue("cmb000/currentIndexChanged", 1)
        source.setValue("shortcuts_blender.MayaBridgeSlots.b000", "Ctrl+M")
        self.addCleanup(sb.settings.branch("maya_bridge_blender").clear)
        self.addCleanup(sb.settings.branch("dcc_bridge_blender").clear)
        self.addCleanup(sb.configurable.clear, PanelRenames.CARRIED_KEY + "_blender")
        PanelRenames.carry(sb, {"dcc_bridge": {"maya_bridge": {}}})
        target = sb.settings.branch("dcc_bridge_blender")
        self.assertEqual(target.value("cmb000/currentIndexChanged"), 1)
        self.assertEqual(
            target.value("shortcuts_blender.DccBridgeSlots.b000"), "Ctrl+M"
        )


if __name__ == "__main__":
    unittest.main()
