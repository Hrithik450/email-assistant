import logging
import os

from rich.console import Console

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)-5s [%(name)s] %(message)s",
)

_console = Console()


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(name or __name__)


logger = get_logger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}


def _dev_mode_enabled() -> bool:
    """Read DEV_MODE at call time so it works regardless of when .env loads."""
    return os.environ.get("DEV_MODE", "").strip().lower() in _TRUTHY


def log_tool_call(tool_name: str, query: str) -> None:
    """In dev mode, show which retrieval tool handled a query.

    Enabled by setting DEV_MODE=1 (or true/yes/on). No-op otherwise.
    """
    if not _dev_mode_enabled():
        return
    snippet = " ".join(query.split())
    if len(snippet) > 120:
        snippet = snippet[:117] + "..."
    _console.log(f"[magenta]Tool → {tool_name}[/magenta] [dim]{snippet}[/dim]")
