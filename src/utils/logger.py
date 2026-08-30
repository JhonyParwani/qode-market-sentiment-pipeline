"""
Centralized logging setup.

Everything in this project logs through get_logger() instead of print(),
so the scraper (which runs unattended for hours) leaves a proper audit
trail: what was scraped, what got rate-limited, what failed and why.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)


def get_logger(name: str, log_file: str = "pipeline.log", level=logging.INFO) -> logging.Logger:
    """
    Return a module-level logger that writes to both stdout and a rotating
    file handler (5MB x 3 backups — enough for a multi-hour scrape run
    without eating disk).
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        # Avoid duplicate handlers if get_logger() is called more than once
        # for the same module (happens on reimport in notebooks/tests).
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_DIR / log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger
