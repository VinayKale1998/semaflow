from typing import Any, Literal
from pydantic import BaseModel, Field

# All valid measure keys from semantic_layer.yaml measures section.
# Keeping as Literal so OpenAPI (stage 6) generates a proper enum, and so
# the resolver can treat an unknown measure as a hard validation failure
# rather than a runtime KeyError.
MeasureKey = Literal[
    "top_categories_by_revenue",
    "aov_by_state",
    "seller_ratings_by_state",
    "return_rate_by_category",
]


class SQLRequest(BaseModel):
    """Inbound user question with execution constraints."""

    question: str
    max_rows: int = Field(default=1000, ge=1, le=10000)


class ModelSelection(BaseModel):
    """Structured output returned by the text-to-SQL node (Gemini).

    The model never writes SQL. It selects a measure key and annotates it
    with glossary references and free-form filter values; the resolver does
    the actual assembly.
    """

    measure: MeasureKey
    # dot-namespaced glossary keys, e.g. "time_periods.last_quarter", "regions.south"
    glossary_refs: list[str] = Field(default_factory=list)
    # template parameters not covered by glossary, e.g. {"category": "electronics", "top_n": "5"}
    filters: dict[str, str] = Field(default_factory=dict)
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class ResolvedSQL(BaseModel):
    """Deterministic output from the resolver after template substitution."""

    sql: str
    measure: MeasureKey
    # record exactly what was substituted so guardrails and logs can inspect it
    parameters_applied: dict[str, str] = Field(default_factory=dict)


class GuardrailResult(BaseModel):
    """Result of all guardrail checks run against the resolved SQL.

    Individual boolean fields map to each discrete check so failures can be
    reported precisely.  `passed` is True only when all four checks pass.
    """

    passed: bool
    violations: list[str] = Field(default_factory=list)
    is_read_only: bool        # no INSERT/UPDATE/DELETE/DROP/CREATE/TRUNCATE
    schema_valid: bool        # only tables and columns present in the semantic layer
    joins_safe: bool          # no forbidden joins (e.g. fact_order_items -> fact_order_payments)
    row_limit_enforced: bool  # LIMIT clause present and within max_rows


class SQLResponse(BaseModel):
    """Complete pipeline result, from raw question to executed rows.

    Upstream context (request, model_selection, guardrail) is optional because
    executor.execute() constructs a SQLResponse from a ResolvedSQL alone; it
    does not have those objects. run_sql_pipeline() enriches them afterward,
    since it is the step that holds all four. resolved is always present.
    """

    request: SQLRequest | None = None
    model_selection: ModelSelection | None = None
    resolved: ResolvedSQL
    guardrail: GuardrailResult | None = None
    # Execution result, populated by executor.execute().
    rows: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    row_count: int = 0
    # final_sql: the SQL actually executed. ready_to_execute: True once run.
    final_sql: str | None = None
    ready_to_execute: bool = False
