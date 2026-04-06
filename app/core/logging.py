import structlog
import logging
from app.core.config import settings


def setup_logging():
    """Configure structlog — call once at app startup."""

    # Shared processors — run on every log message
    shared_processor = [
        structlog.contextvars.merge_contextvars,    # picks up request_id from middleware
        structlog.stdlib.add_log_level,             # adds "level": "info"
        structlog.processors.TimeStamper(fmt="iso"), # adds "timestamp": "2026-..."
        structlog.processors.StackInfoRenderer(),   # adds stack trace on exceptions
    ]

    if settings.ENVIRONMENT == "development":
        # Dev: colored, human-readable
        structlog.configure(
            processors=shared_processor + [
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        )
    else:
        # Production: json
        structlog.configure(
            processors=shared_processor + [
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        )
    