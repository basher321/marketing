"""Global exception handler registration."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError, app_error_handler

logger = logging.getLogger(__name__)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception while processing request")
    return JSONResponse(status_code=500, content={"error": "Internal server error."})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
