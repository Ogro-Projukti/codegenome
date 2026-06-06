"""Textual CSS for the CodeGenome TUI, extracted from the app class."""

from __future__ import annotations

APP_CSS = """
    Screen {
        layout: vertical;
    }

    ContentSwitcher {
        height: 1fr;
    }

    .page {
        height: 1fr;
        layout: vertical;
    }

    #page-set-workspace {
        align: center middle;
        padding: 2 4;
    }

    .set-workspace-panel {
        width: 60;
        max-width: 100%;
        height: auto;
        padding: 2 3;
        border: solid green;
    }

    .set-workspace-panel Label {
        margin-bottom: 1;
    }

    .set-workspace-panel Input {
        margin-bottom: 1;
    }

    .page-actions {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin-top: 1;
    }

    #page-workspace-info {
        padding: 1 2;
    }

    #workspace-scan-status {
        height: auto;
        margin-bottom: 1;
    }

    #workspace-info-panels {
        height: 1fr;
        layout: horizontal;
    }

    .info-panel {
        width: 1fr;
        height: 1fr;
        layout: vertical;
        border: solid $surface-lighten-1;
        margin: 0 1;
        padding: 1;
    }

    .info-panel Label {
        height: auto;
        margin-bottom: 1;
    }

    .info-panel ReadOnlyRichLog {
        height: 1fr;
        min-height: 6;
    }

    #workspace-summary-bar {
        height: auto;
        padding: 0 2;
        margin: 1 1 0 1;
        border: solid green;
        align: center middle;
    }

    #workspace-summary {
        width: 1fr;
        height: auto;
    }

    #commands-container {
        height: auto;
        padding: 1 2;
        border: solid blue;
        margin: 1 1 0 1;
        layout: vertical;
    }

    #page-memory-setup {
        padding: 1 2;
        layout: vertical;
    }

    #memory-setup-topbar {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin-bottom: 1;
    }

    .memory-topbar-presets {
        width: 1fr;
        height: auto;
        layout: horizontal;
        align: left middle;
    }

    .memory-topbar-presets Button {
        margin: 0 1 0 0;
    }

    #btn-back-to-main {
        margin-left: 1;
    }

    #memory-setup-columns {
        height: 1fr;
        layout: horizontal;
    }

    .memory-column {
        width: 1fr;
        height: 1fr;
        layout: vertical;
        min-width: 0;
    }

    #memory-setup-left {
        border: solid $warning-darken-2;
        padding: 1;
        margin-right: 1;
    }

    #memory-setup-right {
        border: solid $warning;
        padding: 1;
    }

    #memory-setup-controls {
        height: 1fr;
        layout: vertical;
        align: left top;
    }

    #memory-setup-controls Label {
        height: auto;
        margin: 0 1 0 0;
        text-align: left;
    }

    #memory-setup-controls Input {
        width: 8;
        min-width: 8;
        max-width: 8;
        margin: 0;
    }

    #memory-setup-controls Switch {
        margin: 0 1 0 0;
        width: auto;
        min-width: 5;
    }

    .memory-setup-option {
        height: auto;
        width: 100%;
        layout: horizontal;
        align: left middle;
        content-align: left middle;
        margin: 0 0 1 0;
    }

    .memory-mode-hint {
        height: auto;
        margin: 0 0 1 0;
        color: $text-muted;
    }

    #memory-setup-summary {
        height: auto;
        min-height: 6;
        border: solid $surface-lighten-1;
        padding: 1;
        margin: 1 0;
        background: $surface-darken-1;
    }

    #memory-setup-console {
        height: 1fr;
        min-height: 10;
    }

    .memory-console-header {
        height: auto;
        layout: horizontal;
        align: left middle;
        margin-bottom: 1;
    }

    .memory-column-title {
        height: auto;
        margin-bottom: 1;
    }

    .command-row {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin: 0 0 1 0;
    }

    .command-row:last-child {
        margin-bottom: 0;
    }

    Button {
        margin: 0 1;
    }

    #log-container {
        height: 1fr;
        padding: 0 1 1 1;
        margin: 0 1 1 1;
    }

    TabbedContent {
        height: 1fr;
    }

    TabPane {
        padding: 0 1;
    }

    .log-pane {
        height: 1fr;
        layout: vertical;
    }

    .log-pane ReadOnlyRichLog {
        height: 1fr;
        width: 1fr;
        border: solid $surface-lighten-1;
    }

    #tab-analyze ReadOnlyRichLog {
        border: solid cyan;
    }

    .mcp-activity-stats {
        height: 1;
        width: 1fr;
        margin-bottom: 1;
        padding: 0 1;
        color: $text-muted;
    }

    #tab-mcp ReadOnlyRichLog {
        border: solid green;
    }

    #tab-evolve ReadOnlyRichLog {
        border: solid magenta;
    }

    #tab-general ReadOnlyRichLog {
        border: solid white;
    }

    .panel-header {
        height: 1;
        layout: horizontal;
        align: left middle;
        margin-bottom: 1;
    }

    .panel-header Label {
        width: 1fr;
        margin: 0;
        padding: 0;
        height: auto;
    }

    .copy-btn {
        height: 1;
        min-width: 8;
        border: none;
        padding: 0 1;
        margin: 0;
        background: $surface-lighten-1;
        color: $text;
        text-style: bold;
    }

    .copy-btn:hover {
        background: $primary;
        color: $text;
    }
    """
