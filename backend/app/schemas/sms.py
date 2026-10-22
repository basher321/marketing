"""SMS settings and confirmation schemas (SPEC-BE-108)."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

SmsStatus = Literal["not_configured", "no_number", "blocked", "ready"]


class SmsSettingsRead(BaseModel):
    status: SmsStatus
    reason: str | None
    number: str | None
    auto_confirm: bool
    language: Literal["en", "bn", "auto"]
    template: str | None
    default_template: str
    preview: str
    segments: int


class SmsSettingsSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_confirm: bool | None = None
    language: Literal["en", "bn", "auto"] | None = None
    # Blank = back to the default text.
    template: Annotated[str, StringConstraints(strip_whitespace=True, max_length=480)] | None = None


class SmsSendResult(BaseModel):
    sms_id: str
    status: str
    order_status: str


class SmsNumber(BaseModel):
    number: str | None
    name: str | None
    sms: bool
    company_id: str | None = None
    company_name: str | None = None


class SmsNumberList(BaseModel):
    items: list[SmsNumber]


class SmsNumberAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Empty = remove the company's number.
    number: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] = ""


class SmsNumberAssigned(BaseModel):
    company_id: str
    number: str | None
