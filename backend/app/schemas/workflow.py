"""Workflow schemas."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class WorkflowListItem(BaseModel):
    """One row of the Workflows page "Saved Workflows" table (SPEC-BE-014)."""

    id: str
    name: str
    trigger_type: str
    actions_count: int
    runs_7d: int
    status: Literal["Enabled", "Paused"]


class WorkflowDetail(BaseModel):
    """GET /workflows/{id}: one workflow's raw structure for the Workflow Builder canvas
    (SPEC-FE-018). Values are returned as stored - no human-readable rewording exists."""

    id: str
    name: str
    trigger_type: str
    trigger_config: dict[str, Any]
    # Raw condition text, never parsed (no grammar is defined); null when none.
    condition_dsl: str | None
    # The stored actions array as-is (each normally {"type": ..., ...config}).
    actions: list[Any]
    status: Literal["Enabled", "Paused"]
    # SPEC-BE-049.
    description: str | None = None
    version: int = 1
    is_current: bool = True


class WorkflowActionIn(BaseModel):
    type: str = Field(min_length=1, max_length=50)
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowSave(BaseModel):
    """POST /workflows and PUT /workflows/{id} (SPEC-BE-049)."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    trigger_type: str
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    condition_dsl: str | None = Field(default=None, max_length=2000)
    actions: list[WorkflowActionIn] = Field(min_length=1, max_length=10)
    enabled: bool = False

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name is required.")
        return value.strip()


class WorkflowEnabled(BaseModel):
    enabled: bool


class WorkflowVersion(BaseModel):
    id: str
    version: int
    created_at: datetime
    created_by_name: str | None
    name: str
    trigger_type: str
    action_count: int
    enabled: bool
    is_current: bool


class CatalogFieldOut(BaseModel):
    key: str
    label: str
    kind: Literal["text", "number", "select", "url"]
    required: bool
    options: list[str] = []
    help: str = ""


class CatalogEntry(BaseModel):
    type: str
    label: str
    fields: list[CatalogFieldOut]


class WorkflowCatalog(BaseModel):
    triggers: list[CatalogEntry]
    actions: list[CatalogEntry]
    condition_help: str
    condition_examples: list[str]


class WorkflowTestRequest(BaseModel):
    """POST /workflows/{id}/test body (optional). None/omitted -> {}."""

    input: dict[str, Any] | None = None


class WorkflowRunSummary(BaseModel):
    id: str
    # Live run_status value: 'succeeded' or 'failed' for a finished dry run.
    status: str
    started_at: datetime
    finished_at: datetime | None
    error: str | None


class ActionExecutionSummary(BaseModel):
    action_index: int
    type: str
    # Live run_status value ('succeeded'); the dry-run nature is in `output`.
    status: str
    output: dict[str, Any]


class WorkflowTestResult(BaseModel):
    workflow_run: WorkflowRunSummary
    action_executions: list[ActionExecutionSummary]


class WorkflowLiveRun(BaseModel):
    """POST /workflows/{id}/run (SPEC-BE-060)."""

    id: str
    status: str
    output: dict[str, Any]
