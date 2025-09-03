# !/usr/bin/python
# coding=utf-8
from uitk import Signals


class ExampleSlots:
    """Example slot class demonstrating UITK features and patterns.

    This example showcases:
    - Basic widget signal connections
    - Menu integration with complex options
    - Rich text and styling
    - Signal decorators for custom behavior
    - State management and cross-widget communication
    """

    def __init__(self, *args, **kwargs):
        self.sb = kwargs.get("switchboard")
        self.ui = self.sb.loaded_ui.example

        # Example of accessing multiple UIs (if they exist)
        # self.settings = getattr(self.sb.loaded_ui, 'example_settings', None)

    # =============================================================================
    # Header Widget with Menu Integration
    # =============================================================================

    def header_init(self, widget):
        """Initialize the header with draggable menu functionality."""
        widget.config_buttons(menu_button=True, minimize_button=True, hide_button=True)
        widget.menu.setTitle("EXAMPLE MENU")

        # Add interactive label to header menu
        widget.menu.add(
            self.sb.registered_widgets.Label,
            setObjectName="info_label",
            setText="📋 Click for Info",
        )

    def info_label(self):
        """Handle click on info label in header menu."""
        widget = self.ui.header.menu.info_label
        self.sb.message_box("This demonstrates UITK's menu integration capabilities!")

    # =============================================================================
    # Document Management Section
    # =============================================================================

    def save_button_init(self, widget):
        """Initialize save button with comprehensive menu options."""
        widget.setText("Save Document")
        widget.setToolTip("Save the current document with options")

        # Set icon using the new icon system
        widget.setIcon(self.sb.get_icon("save"))

        # Create comprehensive save options menu
        widget.menu.setTitle("Save Options")

        # File format selection
        widget.menu.add(
            "QComboBox",
            addItems=[
                "Text (.txt)",
                "Rich Text (.rtf)",
                "HTML (.html)",
                "Markdown (.md)",
            ],
            setObjectName="format_combo",
            setCurrentText="Text (.txt)",
        )

        # Save options
        widget.menu.add(
            "QCheckBox",
            setText="Create Backup",
            setObjectName="backup_check",
            setChecked=True,
        )

        widget.menu.add(
            "QCheckBox", setText="Auto-save Enabled", setObjectName="autosave_check"
        )

        # Quality/compression setting
        widget.menu.add(
            "QSpinBox",
            setPrefix="Compression: ",
            setSuffix="%",
            setMinimum=0,
            setMaximum=100,
            setValue=85,
            setObjectName="compression_spin",
        )

    def save_button(self, widget):
        """Handle save button click with menu option processing."""
        # Get values from menu widgets
        file_format = widget.menu.format_combo.currentText()
        create_backup = widget.menu.backup_check.isChecked()
        autosave = widget.menu.autosave_check.isChecked()
        compression = widget.menu.compression_spin.value()

        # Get document content
        content = self.ui.document_edit.toPlainText()

        # Update status with save information
        status_msg = f"Saving as {file_format}"
        if create_backup:
            status_msg += " (with backup)"

        self.ui.status_label.setText(f"<b style='color: green;'>✓</b> {status_msg}")

        # Show confirmation with details
        details = f"""Document saved successfully!
        
Format: {file_format}
Backup: {'Yes' if create_backup else 'No'}
Auto-save: {'Enabled' if autosave else 'Disabled'}
Compression: {compression}%
Characters: {len(content)}"""

        self.sb.message_box(details)

        # Update auto-save checkbox in other widgets
        if hasattr(self.ui, "autosave_enabled"):
            self.ui.autosave_enabled.setChecked(autosave)

    def filename_edit_init(self, widget):
        """Initialize filename input field."""
        widget.setPlaceholderText("Enter filename (e.g., 'my_document')")
        widget.setText("example_document")

    def filename_edit(self, text, widget):
        """Handle filename changes - enable/disable save button."""
        # Enable save button only if filename is provided
        has_filename = bool(text.strip())
        self.ui.save_button.setEnabled(has_filename)

        # Update status
        if has_filename:
            self.ui.status_label.setText(f"Ready to save: <i>{text}</i>")
        else:
            self.ui.status_label.setText(
                "<span style='color: orange;'>⚠</span> Enter filename to enable saving"
            )

    # =============================================================================
    # Settings and Configuration
    # =============================================================================

    def open_settings_button_init(self, widget):
        """Initialize settings button."""
        widget.setText("Preferences")
        widget.setToolTip("Open application preferences")

        # Set icon using the new icon system
        widget.setIcon(self.sb.get_icon("settings"))

    def open_settings_button(self, widget):
        """Open settings dialog (simulated)."""
        # In a real application, this would open a settings UI
        # settings_ui = self.sb.loaded_ui.example_settings
        # settings_ui.show()

        self.sb.message_box(
            "Settings dialog would open here.\nIn a real app, this would load example_settings.ui"
        )

    def theme_combo_init(self, widget):
        """Initialize theme selection combo box."""
        widget.addItems(["Light Theme", "Dark Theme", "Auto"])
        widget.setCurrentText("Auto")

    def theme_combo(self, text, widget):
        """Handle theme selection changes."""
        self.ui.status_label.setText(f"Theme changed to: <b>{text}</b>")

        # Simulate theme application
        if text == "Dark Theme":
            self.ui.document_edit.setStyleSheet(
                "background-color: #2b2b2b; color: #ffffff;"
            )
        elif text == "Light Theme":
            self.ui.document_edit.setStyleSheet(
                "background-color: #ffffff; color: #000000;"
            )
        else:  # Auto
            self.ui.document_edit.setStyleSheet("")

    # =============================================================================
    # Document Editing
    # =============================================================================

    def document_edit_init(self, widget):
        """Initialize the main document editor."""
        widget.setPlaceholderText("Start typing your document here...")

        # Set initial content with rich text demonstration
        initial_content = """Welcome to the UITK Example!

This text editor demonstrates several features:

• Widget states are automatically restored
• Signal connections work seamlessly
• Rich text rendering is supported
• Menu integration provides advanced options

Try the buttons and menus to see UITK in action!"""

        widget.setText(initial_content)

    @Signals("textChanged", "returnPressed")
    def document_edit(self, widget):
        """Handle document text changes with multiple signals."""
        text = widget.toPlainText()
        word_count = len(text.split()) if text.strip() else 0
        char_count = len(text)

        # Update word count display
        if hasattr(self.ui, "word_count_label"):
            self.ui.word_count_label.setText(
                f"Words: {word_count} | Characters: {char_count}"
            )

        # Update status if document has content
        if text.strip():
            self.ui.status_label.setText("Document modified - remember to save!")

    # =============================================================================
    # Analysis and Processing
    # =============================================================================

    def analyze_button_init(self, widget):
        """Initialize text analysis button."""
        widget.setText("Analyze Text")
        widget.setToolTip("Perform text analysis on the document")

        # Set icon using the new icon system
        widget.setIcon(self.sb.get_icon("analyze"))

    def analyze_button(self, widget):
        """Perform text analysis on document content."""
        content = self.ui.document_edit.toPlainText()

        if not content.strip():
            self.sb.message_box("No content to analyze. Please enter some text first.")
            return

        # Perform analysis
        words = content.split()
        word_count = len(words)
        char_count = len(content)
        char_count_no_spaces = len(content.replace(" ", ""))
        line_count = len(content.splitlines())

        # Find most common words (simple implementation)
        word_freq = {}
        for word in words:
            clean_word = word.lower().strip('.,!?";')
            word_freq[clean_word] = word_freq.get(clean_word, 0) + 1

        common_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]

        # Create analysis report
        analysis = f"""Text Analysis Results:

Lines: {line_count}
Words: {word_count}
Characters: {char_count}
Characters (no spaces): {char_count_no_spaces}

Most Common Words:"""

        for word, count in common_words:
            analysis += f"\n• {word}: {count}"

        # Update status and show results
        self.ui.status_label.setText("<b style='color: blue;'>📊</b> Analysis complete")
        self.sb.message_box(analysis)

    # =============================================================================
    # State Management Examples
    # =============================================================================

    def autosave_enabled_init(self, widget):
        """Initialize auto-save checkbox."""
        widget.setText("Enable Auto-save")
        widget.setChecked(False)  # This will be restored from settings

        # Set icon using the new icon system
        widget.setIcon(self.sb.get_icon("autosave"))

    def autosave_enabled(self, checked, widget):
        """Handle auto-save setting changes."""
        status = "enabled" if checked else "disabled"
        self.ui.status_label.setText(f"Auto-save {status}")

        # Sync with save button menu if it exists
        save_menu = getattr(self.ui.save_button, "menu", None)
        if save_menu and hasattr(save_menu, "autosave_check"):
            save_menu.autosave_check.setChecked(checked)

    def font_size_spin_init(self, widget):
        """Initialize font size spinner."""
        widget.setRange(8, 72)
        widget.setValue(12)
        widget.setSuffix(" pt")

    def font_size_spin(self, value, widget):
        """Handle font size changes."""
        # Apply font size to document editor
        font = self.ui.document_edit.font()
        font.setPointSize(value)
        self.ui.document_edit.setFont(font)

        self.ui.status_label.setText(f"Font size: {value}pt")

    # =============================================================================
    # Status and Information
    # =============================================================================

    def status_label_init(self, widget):
        """Initialize status label with rich text."""
        widget.setText('<b style="color: green;">✓</b> Ready')
        widget.setToolTip("Application status")

    def word_count_label_init(self, widget):
        """Initialize word count display."""
        widget.setText("Words: 0 | Characters: 0")
        widget.setStyleSheet("color: #666; font-size: 10px;")

    # =============================================================================
    # Legacy Examples (for compatibility)
    # =============================================================================

    def button_b_init(self, widget):
        """Initialize button with menu and signal decorator example."""
        widget.setText("Menu Button")
        widget.menu.setTitle("SIMPLE MENU")
        widget.menu.add(
            "QRadioButton",
            setObjectName="option_1",
            setText="Option 1",
            setChecked=True,
        )
        widget.menu.add("QRadioButton", setObjectName="option_2", setText="Option 2")

    @Signals("released")
    def button_b(self, widget):
        """Handle button with signal decorator."""
        option = "1" if widget.menu.option_1.isChecked() else "2"
        self.sb.message_box(f"Selected Option {option}")

    def checkbox_init(self, widget):
        """Initialize checkbox example."""
        widget.setText("Example Checkbox")

    def checkbox(self, state):
        """Handle checkbox state changes."""
        self.sb.message_box(
            f'Checkbox State: <hl style="color:yellow;">{bool(state)}</hl>'
        )


# --------------------------------------------------------------------------------------------

if __name__ == "__main__":
    """Example of running the UITK example directly."""
    from uitk import Switchboard
    from uitk import examples

    # Create switchboard and load the example
    sb = Switchboard(
        ui_source=examples,
        slot_source=examples.ExampleSlots,
        icon_source="uitk/examples/icons",  # Use the icon path directly
    )
    ui = sb.loaded_ui.example

    # Optional styling
    ui.set_attributes(WA_TranslucentBackground=True)
    ui.set_flags(FramelessWindowHint=True, WindowStaysOnTopHint=True)
    ui.style.set(theme="dark", style_class="translucentBgWithBorder")

    # Show the UI
    ui.show(pos="screen", app_exec=True)

# --------------------------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------------------------

"""
This example demonstrates comprehensive UITK usage patterns:

1. Widget Initialization (_init methods):
   - Setting up widget properties and initial states
   - Creating complex menu systems with multiple widget types
   - Configuring tooltips, placeholders, and styling

2. Signal Handling:
   - Default signal connections (method name matches widget name)
   - Custom signal decorators (@Signals) for multiple signals
   - Parameter handling for different signal types

3. Menu Integration:
   - Adding various widget types to button menus
   - Accessing menu widget values in slot methods
   - Dynamic menu behavior and widget interactions

4. Cross-Widget Communication:
   - Updating multiple widgets based on single actions
   - Maintaining state consistency across the UI
   - Status updates and user feedback

5. Rich Text and Styling:
   - HTML formatting in labels and messages
   - Dynamic style application based on user choices
   - Font and appearance management

6. State Management:
   - Widget state persistence (automatic via UITK)
   - Settings synchronization across widgets
   - User preference handling

This example serves as a comprehensive reference for UITK capabilities
and can be used as the primary example in documentation.
"""
