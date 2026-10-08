"""Scheduled post schemas."""
from datetime import date, datetime

from pydantic import BaseModel


class ScheduledPostCount(BaseModel):
    pending: int


class CalendarPost(BaseModel):
    """One post in the Marketing Content Calendar (SPEC-BE-038)."""

    id: str
    channel: str
    # content_assets.format, e.g. "post", "story", "reel", "newsletter".
    format: str
    status: str
    scheduled_at: datetime


class CalendarDay(BaseModel):
    # Tenant-local calendar date.
    date: date
    posts: list[CalendarPost]


class ContentCalendar(BaseModel):
    """Monday-Sunday week containing now, in the tenant's timezone: always 7 days."""

    week_start: date
    timezone: str
    days: list[CalendarDay]
