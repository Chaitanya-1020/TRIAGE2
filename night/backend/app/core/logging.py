"""
Production-grade structured logging using structlog.
JSON output for production, pretty-printed for development.
"""

import logging
import sys
import structlog
from app.core.config import settings


def setup_logging():
    """Configure structured logging for the application."""

    # Set root log level
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    # Configure stdlib logging
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stdout,
    )

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )

    # Structlog processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.DEBUG:
        # Pretty-print for dev
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # JSON for production (ELK, CloudWatch, etc.)
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )