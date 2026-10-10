"""Media library schemas (SPEC-BE-074)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class MediaOut(BaseModel):
    id: str
    kind: Literal["image", "video", "audio"]
    mime: str
    bytes: int
    width: int | None
    height: int | None
    duration_ms: int | None
    source: str
    name: str | None
    url: str
    parent_id: str | None
    approved: bool
    created_at: datetime


class MediaList(BaseModel):
    count: int
    items: list[MediaOut]


class DeriveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ratio: Literal["1:1", "4:5", "9:16", "16:9", "1.91:1", "2:3"]
    mode: Literal["crop", "pad"] = "crop"
