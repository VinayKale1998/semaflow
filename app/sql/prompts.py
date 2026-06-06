import re
from typing import Any

SYSTEM_PROMPT = """You are a semantic SQL selector for SemaFlow, a BI system built on the \
Brazilian Olist e-commerce dataset (2016–2018).

Your job: given a user question, select exactly one measure from the measure menu provided \
in the user message. You never write SQL. The downstream resolver assembles SQL from your selection.

Output field guidance:
- measure: the exact key from the measure menu that best answers the question
- glossary_refs: zero or more "namespace.key" strings (e.g. "time_periods.last_quarter") \
drawn only from the glossary section of the user message
- filters: template parameters not covered by glossary_refs, as string values \
(e.g. {"category": "electronics"} or {"top_n": "5"})
- reasoning: one sentence explaining why this measure was chosen
- confidence: 0.0–1.0, your certainty that this measure answers the question

Rules:
1. Use only measure keys that appear verbatim in the measure menu. Never invent keys.
2. Use only glossary refs that appear in the glossary section. Never invent refs.
3. If no measure fits well, pick the closest one and set confidence accordingly.
4. One response, one measure. Never combine or list multiple measures.
5. All filter values must be strings, including numbers ("top_n": "5" not 5).
"""


def _extract_template_params(sql_template: str) -> list[str]:
    """Return all {placeholder} names found in a SQL template string."""
    return re.findall(r'\{(\w+)\}', sql_template)


def build_user_prompt(question: str, semantic_layer: dict[str, Any]) -> str:
    """Produce the per-request user message sent to the text-to-SQL node.

    Compresses the measure menu and glossary into a compact, model-readable
    form.  The system prompt stays stable; this function carries all the
    request-specific content.
    """
    lines: list[str] = [f"Question: {question}", "", "Measure menu:"]

    for key, measure in semantic_layer.get("measures", {}).items():
        pattern = measure.get("question_pattern", "")
        lines.append(f"  {key}: \"{pattern}\"")
        params = _extract_template_params(measure.get("sql_template", ""))
        if params:
            lines.append(f"    template parameters: {', '.join(params)}")

    lines.extend(["", "Glossary (use 'namespace.key' format in glossary_refs):"])

    glossary = semantic_layer.get("glossary", {})

    if "time_periods" in glossary:
        keys = [k for k in glossary["time_periods"] if k != "dataset_reference_date"]
        lines.append(f"  time_periods: {', '.join(keys)}")

    if "regions" in glossary:
        parts = []
        for name, data in glossary["regions"].items():
            states = "/".join(data.get("states", []))
            parts.append(f"{name} ({states})")
        lines.append(f"  regions: {', '.join(parts)}")

    if "fuzzy_terms" in glossary:
        keys = list(glossary["fuzzy_terms"].keys())
        lines.append(f"  fuzzy_terms: {', '.join(keys)}")

    return "\n".join(lines)
