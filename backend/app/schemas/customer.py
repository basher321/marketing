"""Customer schemas (SPEC-BE-007)."""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class CustomerCreate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def contact_required(self) -> "CustomerCreate":
        # Mirrors the live CHECK customer_contact_required (email IS NOT NULL OR phone IS NOT
        # NULL), so a request without either is a 422 here rather than a database error.
        if not self.email and not (self.phone and self.phone.strip()):
            raise ValueError("A customer needs an email or a phone number.")
        return self


class CustomerRead(BaseModel):
    id: str
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    created_at: datetime
