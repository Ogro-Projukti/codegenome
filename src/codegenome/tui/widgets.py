"""Custom Textual widgets for the CodeGenome TUI."""

from __future__ import annotations

from textual import events
from textual.selection import Selection
from textual.widgets import RichLog


class ReadOnlyRichLog(RichLog):
    """Console log output: selectable/copyable, not keyboard-editable."""

    ALLOW_SELECT = True

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """Return plain text for the selected region."""
        if not self.lines:
            return None
        text = "\n".join(line.text for line in self.lines)
        extracted = selection.extract(text)
        if not extracted:
            return None
        return extracted, "\n"

    def selection_updated(self, selection: Selection | None) -> None:
        self._line_cache.clear()
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        """Ignore printable keys so log panes cannot be edited."""
        if event.character and event.character.isprintable():
            event.prevent_default()
            event.stop()
