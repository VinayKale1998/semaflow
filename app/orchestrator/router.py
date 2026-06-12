"""
Stage 5, Piece 1: Query Router.

Classifies an incoming natural-language query into one of three routes:
  - sql:    answerable entirely by querying the Olist database.
  - rag:    about data structure, column meaning, or platform policy.
  - hybrid: needs BOTH a SQL result and an explanation of what it means.

The router only classifies. It does not call the SQL or RAG nodes, and it
does not orchestrate anything. Execution lives in Piece 2 (LangGraph).

Uses Claude Haiku with forced tool use so the model can only return
structured JSON matching RouteDecision. No free-form text parsing.
"""
import logging
import os
from typing import Literal

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from app.llm.tracing import maybe_trace

load_dotenv()

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
You are the query router for a governed analytics system over the Olist
Brazilian e-commerce dataset. Classify each user question into exactly one
route. Use the route_query tool to return your decision.

Routes:

- sql: The question can be answered entirely by querying the database.
  It asks for a number, a ranking, an aggregate, a count, or a filtered
  list of rows. No explanation of meaning is needed.
  Examples: "what was total revenue in 2018", "top 10 sellers by order
  count", "average review score for delivered orders".

- rag: The question is about how the data is structured, what a column
  means, or about platform policy. No aggregation or computation needed.
  Examples: "what does order_status mean", "what is the difference between
  customer_id and customer_unique_id", "what are the seller compliance
  rules".

- hybrid: The question needs BOTH a computed SQL result AND an explanation
  of what it means or how to interpret it. Look for a metric request joined
  to a definitional or explanatory clause ("and what does X mean", "and
  explain why ...").
  Examples: "what is the cancellation rate and what does canceled mean",
  "show me revenue by category and explain why some have no English name".

If you genuinely cannot decide between routes, choose hybrid: it is the
safe default because it runs both paths. Always provide a short reason and
a confidence between 0.0 and 1.0.
"""

_ROUTE_TOOL = {
    "name": "route_query",
    "description": "Record the routing decision for the user's question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "route": {
                "type": "string",
                "enum": ["sql", "rag", "hybrid"],
                "description": "The chosen route.",
            },
            "reason": {
                "type": "string",
                "description": "One short sentence explaining the choice.",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in the decision, 0.0 to 1.0.",
            },
        },
        "required": ["route", "reason", "confidence"],
    },
}


class RouteDecision(BaseModel):
    route: Literal["sql", "rag", "hybrid"]
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class Router:
    def __init__(self) -> None:
        self._client = maybe_trace(
            anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        )

    def classify(self, query: str) -> RouteDecision:
        """Classify a natural-language query into sql, rag, or hybrid."""
        response = self._client.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            tools=[_ROUTE_TOOL],
            tool_choice={"type": "tool", "name": "route_query"},
            messages=[{"role": "user", "content": query}],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "route_query":
                decision = RouteDecision.model_validate(block.input)
                logger.info(
                    "router: query=%r -> route=%s confidence=%.2f reason=%r",
                    query,
                    decision.route,
                    decision.confidence,
                    decision.reason,
                )
                return decision

        # Forced tool_choice should make this unreachable. If the model
        # somehow returns no tool call, default to hybrid (runs both paths).
        logger.warning(
            "router: no tool_use block returned for query=%r, defaulting to hybrid",
            query,
        )
        return RouteDecision(
            route="hybrid",
            reason="Router returned no structured decision; defaulting to hybrid.",
            confidence=0.0,
        )
