import logging
import os
from pathlib import Path

import yaml
from google import genai
from google.genai import types
from pydantic import ValidationError

from .models import ModelSelection, SQLRequest
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

_SEMANTIC_LAYER_PATH = Path(__file__).parent.parent / "semantic" / "semantic_layer.yaml"


def _load_semantic_layer() -> dict:
    with open(_SEMANTIC_LAYER_PATH) as f:
        return yaml.safe_load(f)


async def run(request: SQLRequest) -> ModelSelection | None:
    """Call Gemini to select a measure for the given SQL request.

    Returns None if the model returns a measure key not in the schema
    (hallucination guard).  Confidence is surfaced as-is; the caller decides
    whether to act on low-confidence selections.
    """
    semantic_layer = _load_semantic_layer()
    user_prompt = build_user_prompt(request.question, semantic_layer)

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=[user_prompt],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ModelSelection,
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )
        return ModelSelection.model_validate_json(response.text)

    except ValidationError as exc:
        # Gemini returned JSON that does not match ModelSelection — most likely
        # a measure key not in MeasureKey Literal.  Log and propagate as None
        # so the pipeline can surface a clean "could not classify" error
        # instead of a 500.
        logger.warning(
            "text-to-sql node: Gemini response failed Pydantic validation "
            "(probable hallucinated measure key). question=%r error=%s",
            request.question,
            exc,
        )
        return None
