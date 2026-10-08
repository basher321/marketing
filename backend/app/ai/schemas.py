"""Strict output JSON schemas for LLM responses."""
from pydantic import BaseModel


class IntentResult(BaseModel):
    intent: str
    confidence: float = 0.0
    entities: dict = {}


class PlanStep(BaseModel):
    action_type: str
    description: str
    parameters: dict = {}
    requires_approval: bool = True


class PlanResult(BaseModel):
    summary: str
    steps: list[PlanStep] = []
