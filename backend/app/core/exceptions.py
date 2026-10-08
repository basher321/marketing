"""Custom exception classes and handlers."""
from fastapi import Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "An unexpected error occurred."

    def __init__(self, detail: str | None = None, status_code: int | None = None):
        self.detail = detail or self.detail
        self.status_code = status_code or self.status_code
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    detail = "Resource conflict."


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Authentication required."


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "You do not have permission to perform this action."


class TenantMismatchError(ForbiddenError):
    detail = "Resource does not belong to the current tenant."


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
