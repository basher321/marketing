"""Shared response schemas, pagination, error schemas."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    error: str


class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
