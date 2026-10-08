"""Structured logging setup."""
import logging
import sys

from app.config import get_settings

settings = get_settings()


def configure_logging() -> None:
    level = logging.DEBUG if settings.APP_DEBUG else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
        defaults={"request_id": "-"},
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]


class RequestIdAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        kwargs.setdefault("extra", {})["request_id"] = self.extra.get("request_id", "-")
        return msg, kwargs


def get_logger(name: str, request_id: str = "-") -> logging.LoggerAdapter:
    return RequestIdAdapter(logging.getLogger(name), {"request_id": request_id})
