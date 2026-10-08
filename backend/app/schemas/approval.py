"""Approval schemas."""
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints


class PendingApprovalCounts(BaseModel):
    """Dashboard engine cards' "Pending approvals" rows (SPEC-BE-020)."""

    ecommerce: int
    marketing: int


class RejectRequest(BaseModel):
    """Optional reason on reject (SPEC-BE-024) -> approval_queue.reason."""

    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None


class ApprovalDecisionResult(BaseModel):
    """One decided approval-queue item (SPEC-BE-024)."""

    id: str
    subject_type: str
    subject_id: str
    title: str
    decision: str
    decided_by: str | None
    decided_at: datetime | None
    reason: str | None


class GroupDecisionResult(BaseModel):
    """Approve-all / reject-all result for one subject_id group (SPEC-BE-024)."""

    subject_id: str
    decision: str
    decided_count: int
    decided_ids: list[str]


class PendingApprovalItem(BaseModel):
    """One row of the Command Chat "Pending Approvals" panel (SPEC-BE-025).
    engine is null for subject types SPEC-BE-020 maps to no engine."""

    id: str
    subject_type: str
    title: str
    engine: str | None
    requested_at: datetime
    elapsed_seconds: int


class PendingApprovalList(BaseModel):
    """Pending Approvals panel: heading count + rows (SPEC-BE-025)."""

    count: int
    items: list[PendingApprovalItem]
