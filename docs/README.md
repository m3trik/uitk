[![License: LGPL v3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![Version](https://img.shields.io/badge/Version-1.0.31-blue.svg)](https://pypi.org/project/uitk/)

# UITK: UI Toolkit for Dynamic Qt Applications

UITK is dynamic UI loader designed to manage multiple UI from one central switchboard.  Leverages naming convention to dynamically load UI files, register custom widgets, auto connect slots, set styles, restore and sync states, etc.

## What UITK Does

UITK's primary goal is to eliminate the manual wiring typically required in Qt applications. Instead of manually connecting signals to slots and managing UI loading, UITK uses file and method naming conventions to automatically establish these connections.

### Core Features

**Dynamic UI Loading**
- Automatically loads .ui files created in Qt Designer
- Connects UI widgets to Python methods based on naming conventions
- Supports multiple UI file locations and sources

**Convention-Based Signal Connection**
- Widget named `save_button` automatically connects to method `save_button()`
- Initialization methods like `save_button_init()` are called during setup
- Override default signals using the `@Signals()` decorator

**Enhanced Widgets**
- Extended Qt widgets with additional functionality
- Rich text support in buttons, labels, and other text widgets
- Integrated menu system for buttons and other controls
- Bulk attribute setting with `set_attributes()`

**State Management**
- Basic widget state persistence across application sessions
- Window geometry and position restoration
- Configurable state saving per widget

**File Organization**
- Registry system for tracking UI files, slot classes, and custom widgets
- Support for multiple source directories
- Lazy loading of components

## Package Structure

```
uitk/
