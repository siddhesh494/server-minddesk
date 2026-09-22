"""Structured logging without secret leakage."""

from __future__ import annotations

import logging
import sys

import structlog


SENSITIVE_KEYS = {
    "password",
    "access_token",
    "token",
    "authorization",
    "api_key",
    "jwt",
    "secret",
    "pinecone_api_key",
    "google_api_key",
    "groq_api_key",
    "mongodb_uri",
    "mongo_uri",
}


def _drop_secrets(
    _logger: logging.Logger, _method: str, event_dict: dict
) -> dict:
    for key in list(event_dict.keys()):
        lowered = str(key).lower()
        if lowered in SENSITIVE_KEYS or "secret" in lowered or "api_key" in lowered:
            event_dict[key] = "***"
    return event_dict


def configure_logging(app_env: str = "development") -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        _drop_secrets,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if app_env == "development":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    for noisy in ("httpx", "httpcore", "pymongo", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
