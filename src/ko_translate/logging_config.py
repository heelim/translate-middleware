"""Logging system for ko-translate-middleware."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Optional


class TranslationLogger:
    def __init__(
        self,
        name: str = "ko-translate",
        log_file: Optional[str] = None,
        level: str = "INFO",
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))

        if self.logger.handlers:
            self.logger.handlers.clear()

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        if log_file:
            log_path = Path(log_file).expanduser()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def debug(self, msg: str, **kwargs):
        self.logger.debug(msg, **kwargs)

    def info(self, msg: str, **kwargs):
        self.logger.info(msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        self.logger.warning(msg, **kwargs)

    def error(self, msg: str, **kwargs):
        self.logger.error(msg, **kwargs)

    def critical(self, msg: str, **kwargs):
        self.logger.critical(msg, **kwargs)

    def log_failure(self, original: str, translated: str, direction: str, error: Exception):
        self.logger.error(
            f"Translation failure [{direction}]: {error.__class__.__name__}: {error}\n"
            f"Original: {original[:500]!r}\n"
            f"Attempted: {(translated[:500] if translated else 'N/A')!r}",
            exc_info=True,
        )


def get_logger(
    log_file: Optional[str] = None,
    level: str = "INFO",
) -> TranslationLogger:
    return TranslationLogger(log_file=log_file, level=level)
