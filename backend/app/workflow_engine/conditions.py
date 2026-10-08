"""Condition evaluator for workflows.condition_dsl (SPEC-BE-060).

The grammar is the one workflow_service.parse_condition() validates
(SPEC-BE-049): clauses joined by AND, each `<field> <op> <value>` with ops
== != > >= < <= contains. Values: numbers, true/false, or text. A clause whose
field is missing from the context, or whose types can't be compared, is false.
"""
from typing import Any

from app.workflow_engine.actions import lookup

_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "contains": lambda a, b: b in a,
}


def coerce(raw: str) -> Any:
    text = raw.strip()
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def evaluate_clause(field: str, op: str, raw_value: str, context: dict[str, Any]) -> bool:
    actual = lookup(context, field)
    if actual is None or op not in _OPS:
        return False
    expected = coerce(raw_value)
    if isinstance(actual, (int, float)) and not isinstance(actual, bool) and isinstance(expected, str):
        return False
    try:
        return bool(_OPS[op](actual, expected))
    except TypeError:
        return False


def evaluate_all(clauses: list[tuple[str, str, str]], context: dict[str, Any]) -> bool:
    return all(evaluate_clause(f, op, v, context) for f, op, v in clauses)
