# !/usr/bin/python
# coding=utf-8
"""Pure menu-resolution logic for the MarkingMenu.

Stateless functions that map an input state
``(activation_held, modifiers, buttons, extra_key)`` to a target UI name.

Kept Qt-free except for the integer flag values, so it is fast to unit test
and impossible to accidentally couple to event-loop state.
"""
from typing import Optional, Mapping


# Qt button / modifier flag values, hard-coded to avoid importing Qt at module load.
# These match Qt::MouseButton and Qt::KeyboardModifier across PySide2/PySide6.
LEFT_BUTTON = 0x00000001
RIGHT_BUTTON = 0x00000002
MIDDLE_BUTTON = 0x00000004

SHIFT_MOD = 0x02000000
CTRL_MOD = 0x04000000
ALT_MOD = 0x08000000
META_MOD = 0x10000000


def normalize_key(parts) -> str:
    """Sort and join binding parts into a canonical lookup string."""
    return "|".join(sorted(p.strip() for p in parts if p and p.strip()))


def build_state_key(
    activation_key_str: Optional[str],
    buttons: int,
    modifiers: int,
    extra_key: Optional[str] = None,
) -> str:
    """Build a normalized lookup key from a complete input state."""
    parts = []
    if activation_key_str:
        parts.append(activation_key_str)
    if extra_key:
        parts.append(extra_key)

    if modifiers & SHIFT_MOD:
        parts.append("ShiftModifier")
    if modifiers & CTRL_MOD:
        parts.append("ControlModifier")
    if modifiers & ALT_MOD:
        parts.append("AltModifier")
    if modifiers & META_MOD:
        parts.append("MetaModifier")

    if buttons & LEFT_BUTTON:
        parts.append("LeftButton")
    if buttons & RIGHT_BUTTON:
        parts.append("RightButton")
    if buttons & MIDDLE_BUTTON:
        parts.append("MiddleButton")

    return normalize_key(parts)


def priority_button(buttons: int) -> int:
    """Pick the highest-priority single button from a button mask."""
    if buttons & RIGHT_BUTTON:
        return RIGHT_BUTTON
    if buttons & MIDDLE_BUTTON:
        return MIDDLE_BUTTON
    if buttons & LEFT_BUTTON:
        return LEFT_BUTTON
    return 0


def count_buttons(buttons: int) -> int:
    """Count distinct buttons set in the mask."""
    n = 0
    if buttons & LEFT_BUTTON:
        n += 1
    if buttons & RIGHT_BUTTON:
        n += 1
    if buttons & MIDDLE_BUTTON:
        n += 1
    return n


def resolve_target_menu(
    *,
    activation_held: bool,
    activation_key_str: Optional[str],
    buttons: int,
    modifiers: int,
    bindings: Mapping[str, str],
    extra_key: Optional[str] = None,
) -> Optional[str]:
    """Return the UI name that should be visible for the given input state.

    Returns None when the menu should be hidden (activation key not held,
    or no binding can be resolved).

    Resolution order:
        1. Exact match on the full state.
        2. Same state with multi-button mask collapsed to its priority button.
        3. Same state with modifiers stripped.
        4. Priority button without modifiers.
        5. Default binding (activation key alone).
    """
    if not activation_held or not activation_key_str:
        return None

    # 1. Exact full-state match.
    key = build_state_key(activation_key_str, buttons, modifiers, extra_key)
    if key in bindings:
        return bindings[key]

    # 2. Collapse multi-button mask to its priority button.
    if count_buttons(buttons) > 1:
        pb = priority_button(buttons)
        single_key = build_state_key(activation_key_str, pb, modifiers, extra_key)
        if single_key in bindings:
            return bindings[single_key]

    # 3. Strip modifiers.
    if modifiers:
        no_mod_key = build_state_key(activation_key_str, buttons, 0, extra_key)
        if no_mod_key in bindings:
            return bindings[no_mod_key]
        if count_buttons(buttons) > 1:
            pb = priority_button(buttons)
            no_mod_pb_key = build_state_key(activation_key_str, pb, 0, extra_key)
            if no_mod_pb_key in bindings:
                return bindings[no_mod_pb_key]

    # 4. Default (activation key alone).
    return bindings.get(activation_key_str)


def parse_binding_keys(raw_bindings: Mapping[str, str]) -> tuple:
    """Parse user-supplied bindings into (normalized_dict, activation_key_str).

    Tolerates parts like ``"F12"`` (auto-prefixed to ``"Key_F12"``) and
    arbitrary ordering on either side of ``|``.

    Returns:
        (normalized_bindings, activation_key_str | None)
    """
    normalized: dict = {}
    activation_key_str: Optional[str] = None

    for raw_key, ui_name in raw_bindings.items():
        if not isinstance(raw_key, str):
            continue
        parts = [p.strip() for p in raw_key.split("|") if p.strip()]

        # Find the activation key in this binding (first Key_* wins,
        # bare keys like "F12" are auto-prefixed).
        for part in parts:
            if part.startswith("Key_"):
                if activation_key_str is None:
                    activation_key_str = part
                break
            if not part.endswith(("Button", "Modifier")):
                prefixed = f"Key_{part}"
                if activation_key_str is None:
                    activation_key_str = prefixed
                # Rewrite the part in-place so the key uses the canonical form.
                idx = parts.index(part)
                parts[idx] = prefixed
                break

        normalized[normalize_key(parts)] = ui_name

    return normalized, activation_key_str
