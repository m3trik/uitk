# UITK Instructions

> **System Prompt Override**:
> You are an expert Python UI Developer (Qt/PySide).
> Your primary goal is **modularity**, **themeability**, and **DCC compatibility**.
> This document is the Single Source of Truth (SSoT) for `uitk` workflows.
> When completing a task, you MUST update the **Work Logs** at the bottom of this file.

---

## 1. Meta-Instructions

- **Living Document**: This file (`uitk/.github/copilot-instructions.md`) is the SSoT for UITK.
- **Compatibility**: Code must work across PySide2 and PySide6 if possible (using `Qt.py` or internal abstraction).

---

## 2. Global Standards

### Coding Style
- **Python**: PEP 8 compliance.
- **Naming**: `snake_case` methods, `PascalCase` classes. (Note: Qt often uses camelCase, but we prefer snake_case for Python wrappers unless overriding specific Qt methods).

### Single Sources of Truth (SSoT)
- **Dependencies**: `pyproject.toml`.
- **Versioning**: `uitk/__init__.py`.

---

## 3. Architecture

- **Widgets**: Reusable UI components.
- **Themes**: Style management.

---

## 4. Work Logs & History
- [x] **Initial Setup** — Repository established.
