"""Dataset models and loaders for the Stage 6 eval harness.

Two datasets back the scorecard:
  - eval_questions.yaml : labeled natural-language questions (EvalCase)
  - adversarial_sql.yaml: hand-crafted SQL that must trip one guardrail layer
                          (AdversarialCase)

Loading is pure and deterministic. No LLM, no DB. The pydantic models are the
single contract every scorer and runner reads from, so a typo in the YAML fails
loudly at load time rather than silently mis-scoring downstream.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

_DATASETS = Path(__file__).parent / "datasets"

Category = Literal[
    "sql_positive",
    "rag_positive",
    "hybrid_positive",
    "sql_oos",
    "rag_oos",
]

GuardrailLayer = Literal[
    "is_read_only",
    "schema_valid",
    "joins_safe",
    "row_limit_enforced",
]


class EvalCase(BaseModel):
    """One labeled question. Fields are populated only for the dimensions the
    case is meant to exercise; the rest stay at their defaults."""

    id: str
    text: str
    category: Category
    expected_route: Literal["sql", "rag", "hybrid"]

    # SQL / hybrid labels. expected_measure is None for sql_oos (correct refusal).
    expected_measure: str | None = None
    expected_glossary: list[str] = Field(default_factory=list)
    expected_status: str | None = None

    # RAG / hybrid labels.
    expected_sources: list[str] = Field(default_factory=list)

    # Hedge-calibration labels.
    expects_hedge: bool = False
    expects_revision: bool | None = None
    expects_recovery: bool | None = None

    note: str | None = None

    @property
    def has_sql(self) -> bool:
        return self.category in ("sql_positive", "hybrid_positive", "sql_oos")

    @property
    def has_rag(self) -> bool:
        return self.category in ("rag_positive", "hybrid_positive", "rag_oos")


class AdversarialCase(BaseModel):
    """One SQL string that must be rejected by exactly one guardrail layer."""

    id: str
    sql: str
    fails: GuardrailLayer
    reason_fragments: list[str] = Field(default_factory=list)
    note: str | None = None


class AdversarialSet(BaseModel):
    max_rows: int = 1000
    cases: list[AdversarialCase]


def load_eval_cases(path: Path | None = None) -> list[EvalCase]:
    path = path or (_DATASETS / "eval_questions.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = [EvalCase.model_validate(c) for c in raw["cases"]]
    _assert_unique_ids(c.id for c in cases)
    return cases


def load_adversarial_set(path: Path | None = None) -> AdversarialSet:
    path = path or (_DATASETS / "adversarial_sql.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    aset = AdversarialSet.model_validate(raw)
    _assert_unique_ids(c.id for c in aset.cases)
    return aset


def _assert_unique_ids(ids) -> None:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            raise ValueError(f"duplicate case id in dataset: {i!r}")
        seen.add(i)
