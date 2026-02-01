# UITK Instructions

> **System Prompt Override**:
> You are an expert Python UI Developer (Qt/PySide).
> Your primary goal is **modularity**, **themeability**, and **DCC compatibility**.
>
> **Global Standards**: For general workflow, testing, and coding standards, refer to the [Main Copilot Instructions](../../.github/copilot-instructions.md).
>
> **Work Logs**: When completing a task, you MUST update the **Work Logs** at the bottom of this file.

---

## 1. Meta-Instructions

- **Living Document**: This file (`uitk/.github/copilot-instructions.md`) is the SSoT for UITK specific workflows.
- **Compatibility**: Code must work across PySide2 and PySide6 if possible (using `Qt.py` or internal abstraction).
- **Naming**: Qt often uses camelCase, but we prefer snake_case for Python wrappers unless overriding specific Qt methods.

## 2. Architecture

- **Widgets**: Reusable UI components.
- **Themes**: Style management.

---

## 3. Work Logs & History
- [x] **Initial Setup** — Repository established.
