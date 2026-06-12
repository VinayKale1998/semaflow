import logging
import os
import re
from pathlib import Path

import anthropic
import yaml
from pydantic import ValidationError

from app.llm.tracing import maybe_trace

from .models import ModelSelection, SQLRequest
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

_SEMANTIC_LAYER_PATH = Path(__file__).parent.parent / "semantic" / "semantic_layer.yaml"


def _load_semantic_layer() -> dict:
    with open(_SEMANTIC_LAYER_PATH) as f:
        return yaml.safe_load(f)


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences that some models add despite instructions."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


async def run(request: SQLRequest) -> ModelSelection | None:
    """Call Claude to select a measure for the given SQL request.

    Temporary: using Claude Haiku due to Gemini API geographic restriction
    on free tier. Swap back to Gemini (gemini-2.0-flash) once billing is
    enabled on the Gemini project. The interface is identical.

    Returns None if the response fails Pydantic validation.
    """
    semantic_layer = _load_semantic_layer()
    user_prompt = build_user_prompt(request.question, semantic_layer)

    client = maybe_trace(
        anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    )

    system = (
        SYSTEM_PROMPT
        + "\n\nRespond ONLY with valid JSON. "
        "No markdown, no backticks, no explanation. Raw JSON only."
    )

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = _strip_markdown_fences(response.content[0].text)
        return ModelSelection.model_validate_json(text)

    except ValidationError as exc:
        logger.warning(
            "text-to-sql node: response failed Pydantic validation. "
            "question=%r error=%s",
            request.question,
            exc,
        )
        return None
