# !/usr/bin/python
# coding=utf-8
"""A panel row declared as setter kwargs, read without Qt.

Panels declare rows as dicts of widget setters (``{"widget_type": "QCheckBox",
"setChecked": True, ...}``: the Scene Exporter's task definitions are such a
table). What a widget built from one reads at rest is fixed by the spec, so a
headless caller can run with a fresh panel's values without building a widget
or importing a Qt binding (a headless Blender ships none): Unity Scripts' Send to
Unity runs the Scene Exporter that way. Qt-free by design.
"""

from typing import Any, Callable, Dict, Mapping, Tuple


class WidgetSpec:
    """Read the value a setter-kwargs row spec holds at rest (module docstring)."""

    @staticmethod
    def default(spec: Mapping[str, Any]) -> Tuple[bool, Any]:
        """``(found, value)``: what a widget built from *spec* reads at rest.

        A checkbox its ``setChecked`` (else off); a combo the data of its
        ``setCurrentIndex`` entry, else its first, in the items ``add`` gives (a
        ``{label: data}`` dict, a list of labels or ``(label, data)`` pairs, or a
        callable returning one); a spin box its ``setValue``; a field its
        ``setText``, else empty. ``found`` is False for a combo with no items,
        which reads no value either.
        """
        kind = str(spec.get("widget_type", "QCheckBox"))
        if "CheckBox" in kind:
            return True, bool(spec.get("setChecked", False))
        if "ComboBox" in kind:
            items = spec.get("add")
            items = items() if callable(items) else items
            if isinstance(items, Mapping):
                pairs = list(items.items())
            else:
                pairs = [item if isinstance(item, (tuple, list)) else (item, item) for item in (items or ())]
            if not pairs:
                return False, None
            index = int(spec.get("setCurrentIndex", 0) or 0)
            return True, pairs[min(max(index, 0), len(pairs) - 1)][1]
        if "setValue" in spec:
            return True, spec["setValue"]
        return True, spec.get("setText", "")

    @staticmethod
    def defaults(specs: Mapping[str, Mapping[str, Any]], key: Callable[[str, Mapping[str, Any]], str]) -> Dict[str, Any]:
        """``{key(name, spec): value}`` for each row of *specs* (``{name: spec}``)
        that reads a value at rest (:meth:`default`): a fresh panel's values."""
        values: Dict[str, Any] = {}
        for name, spec in specs.items():
            found, value = WidgetSpec.default(spec)
            if found:
                values[key(name, spec)] = value
        return values
