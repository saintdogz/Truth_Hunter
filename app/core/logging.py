"""Conservative application logging configuration."""

import logging


def configure_logging(level: str) -> None:
    """Configure predictable logs without including configuration or secrets."""

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
