"""Log panel — scrollable narrative/message log."""

from textual.widgets import RichLog


class LogPanel(RichLog):
    """Scrollable log for game messages, AI narration, and combat text."""

    DEFAULT_CSS = """
    LogPanel {
        height: 8;
        border-top: solid #808080;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """
