import re
import logging
from pathlib import Path

import yaml

from .models import GuardrailResult, ResolvedSQL, SQLRequest

logger = logging.getLogger(__name__)

_SEMANTIC_LAYER_PATH = Path(__file__).parent.parent / "semantic" / "semantic_layer.yaml"

_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|TRUNCATE|ALTER|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


def _load_semantic_layer() -> dict:
    with open(_SEMANTIC_LAYER_PATH) as f:
        return yaml.safe_load(f)


_SEMANTIC_LAYER: dict = _load_semantic_layer()


def _check_read_only(sql: str) -> list[str]:
    matches = _WRITE_KEYWORDS.findall(sql)
    if matches:
        return [f"Write operation not allowed: {', '.join(set(m.upper() for m in matches))}"]
    return []


def _check_schema(sql: str) -> list[str]:
    """Check that every table referenced in the SQL exists in allowed_joins."""
    violations = []
    known_tables: set[str] = set()
    for join in _SEMANTIC_LAYER.get("allowed_joins", []):
        known_tables.add(join["from"])
        known_tables.add(join["to"])

    # Also pull tables from terms and measures source_table fields
    for term in _SEMANTIC_LAYER.get("terms", {}).values():
        if "source_table" in term:
            known_tables.add(term["source_table"])

    # Extract table names from FROM and JOIN clauses
    referenced = re.findall(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, re.IGNORECASE
    )
    for table in referenced:
        if table.lower() not in {t.lower() for t in known_tables}:
            violations.append(f"Unknown table referenced: '{table}'")
    return violations


def _check_joins(sql: str, measure: str) -> list[str]:
    """Reject any forbidden join declared in allowed_joins with safe: false."""
    violations = []
    sql_upper = sql.upper()

    for join in _SEMANTIC_LAYER.get("allowed_joins", []):
        if join.get("safe", True):
            continue
        # Check if both tables appear in the SQL together
        from_table = join["from"].upper()
        to_table = join["to"].upper()
        if from_table in sql_upper and to_table in sql_upper:
            note = join.get("note", "forbidden join")
            violations.append(
                f"Forbidden join detected: {join['from']} -> {join['to']}. {note}"
            )
    return violations


def _check_row_limit(sql: str, max_rows: int) -> list[str]:
    match = re.search(r"\bLIMIT\s+(\d+)", sql, re.IGNORECASE)
    if not match:
        return [f"No LIMIT clause found. All queries must be row-limited."]
    limit_value = int(match.group(1))
    if limit_value > max_rows:
        return [f"LIMIT {limit_value} exceeds max_rows={max_rows}."]
    return []


def run(resolved: ResolvedSQL, request: SQLRequest) -> GuardrailResult:
    """Run all guardrail checks against resolved SQL.

    Checks are independent — all run regardless of prior failures so the
    caller gets a complete violation list, not just the first failure.
    """
    sql = resolved.sql
    violations: list[str] = []

    read_only_violations = _check_read_only(sql)
    violations.extend(read_only_violations)
    is_read_only = len(read_only_violations) == 0

    schema_violations = _check_schema(sql)
    violations.extend(schema_violations)
    schema_valid = len(schema_violations) == 0

    join_violations = _check_joins(sql, resolved.measure)
    violations.extend(join_violations)
    joins_safe = len(join_violations) == 0

    limit_violations = _check_row_limit(sql, request.max_rows)
    violations.extend(limit_violations)
    row_limit_enforced = len(limit_violations) == 0

    return GuardrailResult(
        passed=is_read_only and schema_valid and joins_safe and row_limit_enforced,
        violations=violations,
        is_read_only=is_read_only,
        schema_valid=schema_valid,
        joins_safe=joins_safe,
        row_limit_enforced=row_limit_enforced,
    )
