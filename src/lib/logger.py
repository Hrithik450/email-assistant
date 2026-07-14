import logging

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)-5s [%(name)s] %(message)s",
)


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(name or __name__)


logger = get_logger(__name__)
