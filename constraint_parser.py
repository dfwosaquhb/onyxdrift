"""Constraint parsing from IWA task prompts (TASK-05, TASK-06).

Extracts structured constraints from natural language task descriptions using
regex patterns. Covers all IWA constraint operators: equals, not_equals,
contains, not_contains, greater_than, less_than, greater_equal, less_equal,
in, not_in.

Format: parse_constraints() extracts Constraint objects, format_constraints_block()
renders them as a structured text block for the LLM prompt.
"""

from __future__ import annotations

import re

from models import Constraint

# Regex fragment for field names: a single word or snake_case compound
_FIELD = r"([\w]+(?:_[\w]+)*)"

# Ordered pattern list -- more specific patterns first to avoid false matches.
# Each tuple: (regex_pattern, operator_string)
_PATTERNS: list[tuple[str, str]] = [
    # "field that does NOT CONTAIN 'value'"
    (_FIELD + r"(?:\s+that)?\s+does\s+NOT\s+CONTAIN\s+['\"]([^'\"]+)['\"]", "not_contains"),
    (_FIELD + r"(?:\s+that)?\s+does\s+NOT\s+CONTAIN\s+([^\s,'\"\n]+)", "not_contains"),
    # "field not contains 'value'"
    (_FIELD + r"\s+not\s+contains?\s+['\"]([^'\"]+)['\"]", "not_contains"),
    (_FIELD + r"\s+not\s+contains?\s+([^\s,'\"\n]+)", "not_contains"),
    # "field not equals 'value'"
    (_FIELD + r"\s+not\s+equals?\s+['\"]([^'\"]+)['\"]", "not_equals"),
    (_FIELD + r"\s+not\s+equals?\s+([^\s,'\"\n]+)", "not_equals"),
    # "field CONTAINS 'value'" / "field contains 'value'"
    (_FIELD + r"(?:\s+that)?\s+CONTAINS\s+['\"]([^'\"]+)['\"]", "contains"),
    (_FIELD + r"\s+contains?\s+['\"]([^'\"]+)['\"]", "contains"),
    (_FIELD + r"\s+contains?\s+([^\s,'\"\n]+)", "contains"),
    # "field equals 'value'" / "field EQUALS 'value'"
    (_FIELD + r"\s+equals?\s+['\"]([^'\"]+)['\"]", "equals"),
    (_FIELD + r"\s+EQUALS\s+['\"]([^'\"]+)['\"]", "equals"),
    (_FIELD + r"\s+equals?\s+([^\s,'\"\n\]]+)", "equals"),
    # greater/less equal (before plain greater/less to avoid premature match)
    (
        _FIELD
        + r"\s+(?:is\s+)?(?:greater\s+(?:than\s+)?or\s+equal\s+to|greater\s+equal(?:\s+to)?|GREATER\s+EQUAL(?:\s+TO)?|>=)\s+['\"]?([^\s,'\"\n\]]+)['\"]?",
        "greater_equal",
    ),
    (
        _FIELD
        + r"\s+(?:is\s+)?(?:less\s+(?:than\s+)?or\s+equal\s+to|less\s+equal(?:\s+to)?|LESS\s+EQUAL(?:\s+TO)?|<=)\s+['\"]?([^\s,'\"\n\]]+)['\"]?",
        "less_equal",
    ),
    # plain greater/less than
    (_FIELD + r"\s+greater\s+than\s+['\"]?([^\s,'\"\n\]]+)['\"]?", "greater_than"),
    (_FIELD + r"\s+less\s+than\s+['\"]?([^\s,'\"\n\]]+)['\"]?", "less_than"),
    (_FIELD + r"\s+BELOW\s+['\"]?([^\s,'\"\n\]]+)['\"]?", "less_than"),
    (_FIELD + r"\s+ABOVE\s+['\"]?([^\s,'\"\n\]]+)['\"]?", "greater_than"),
]

# "is not one of [...]" pattern
_NOT_IN_PAT = re.compile(
    r"([\w_]+(?:\s+[\w_]+)?)\s+is\s+not\s+one\s+of\s+\[([^\]]+)\]",
    re.IGNORECASE,
)

# "is one of [...]" pattern
_IN_PAT = re.compile(
    r"([\w_]+(?:\s+[\w_]+)?)\s+is\s+one\s+of\s+\[([^\]]+)\]",
    re.IGNORECASE,
)


def _spans_overlap(new_start: int, new_end: int, used: list[tuple[int, int]]) -> bool:
    """Check if a new span overlaps with any already-used span."""
    for s, e in used:
        if new_start < e and new_end > s:
            return True
    return False


def parse_constraints(prompt: str) -> list[Constraint]:
    """Parse structured constraints from an IWA task prompt.

    Extracts field-operator-value triples from natural language.
    Supports: equals, not_equals, contains, not_contains, greater_than,
    less_than, greater_equal, less_equal, in, not_in.

    Deduplicates by (field, operator, value) tuple.
    Uses span tracking to prevent overlapping matches (e.g., "not equals"
    should not also produce an "equals" match from the same text region).
    """
    constraints: list[Constraint] = []
    seen: set[tuple] = set()
    used_spans: list[tuple[int, int]] = []

    # Handle "is not one of [...]"
    for m in _NOT_IN_PAT.finditer(prompt):
        if _spans_overlap(m.start(), m.end(), used_spans):
            continue
        field = m.group(1).strip().lower().replace(" ", "_")
        vals = [v.strip().strip("'\"") for v in m.group(2).split(",")]
        key = (field, "not_in", str(vals))
        if key not in seen:
            seen.add(key)
            constraints.append(Constraint(field=field, operator="not_in", value=vals))
            used_spans.append((m.start(), m.end()))

    # Handle "is one of [...]"
    for m in _IN_PAT.finditer(prompt):
        if _spans_overlap(m.start(), m.end(), used_spans):
            continue
        field = m.group(1).strip().lower().replace(" ", "_")
        vals = [v.strip().strip("'\"") for v in m.group(2).split(",")]
        key = (field, "in", str(vals))
        if key not in seen:
            seen.add(key)
            constraints.append(Constraint(field=field, operator="in", value=vals))
            used_spans.append((m.start(), m.end()))

    # Handle basic operator patterns (ordered: most specific first)
    for pattern, op in _PATTERNS:
        for m in re.finditer(pattern, prompt, re.IGNORECASE):
            if _spans_overlap(m.start(), m.end(), used_spans):
                continue
            field = m.group(1).strip().lower().replace(" ", "_")
            value = m.group(2).strip().strip("'\"").rstrip(".,;:")
            key = (field, op, value)
            if key not in seen:
                seen.add(key)
                constraints.append(Constraint(field=field, operator=op, value=value))
                used_spans.append((m.start(), m.end()))

    return constraints


def format_constraints_block(constraints: list[Constraint]) -> str:
    """Format parsed constraints as a structured block for the LLM prompt.

    Returns empty string if no constraints.
    Otherwise returns a multi-line block with a CONSTRAINTS header and
    human-readable descriptions for each constraint.
    """
    if not constraints:
        return ""

    lines = ["CONSTRAINTS (use these to find the RIGHT item and fill forms correctly):"]
    for c in constraints:
        if c.operator == "equals":
            lines.append(f"  [{c.field}] MUST EQUAL '{c.value}' exactly")
        elif c.operator == "not_equals":
            lines.append(f"  [{c.field}] must NOT be '{c.value}' -> choose any other value")
        elif c.operator == "contains":
            lines.append(f"  [{c.field}] MUST CONTAIN '{c.value}'")
        elif c.operator == "not_contains":
            lines.append(f"  [{c.field}] must NOT CONTAIN '{c.value}'")
        elif c.operator == "greater_than":
            lines.append(f"  [{c.field}] must be > {c.value}")
        elif c.operator == "less_than":
            lines.append(f"  [{c.field}] must be < {c.value}")
        elif c.operator == "greater_equal":
            lines.append(f"  [{c.field}] must be >= {c.value}")
        elif c.operator == "less_equal":
            lines.append(f"  [{c.field}] must be <= {c.value}")
        elif c.operator == "not_in":
            lines.append(f"  [{c.field}] must NOT be any of {c.value}")
        elif c.operator == "in":
            lines.append(f"  [{c.field}] must be one of {c.value}")

    return "\n".join(lines)
