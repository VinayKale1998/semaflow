"""LangSmith tracing for Anthropic clients.

Wraps an Anthropic client so each .messages.create call becomes a child LLM
span in LangSmith (prompt, completion, model, token counts, latency). Without
this, LangGraph only traces the node spans, not the model calls inside them.
"""

import logging
import os
from typing import TypeVar

import anthropic
from langsmith.wrappers import wrap_anthropic

logger = logging.getLogger(__name__)

# wrap_anthropic patches both sync (Anthropic) and async (AsyncAnthropic)
# clients and returns the same type, so callers keep the identical
# .messages.create surface.
ClientT = TypeVar("ClientT", anthropic.Anthropic, anthropic.AsyncAnthropic)


def maybe_trace(client: ClientT) -> ClientT:
    """Return a LangSmith-traced client when tracing is enabled, else the raw one.

    Tracing is enabled only when LANGSMITH_TRACING=true and LANGSMITH_API_KEY
    is set, mirroring the gate in graph.py. Dev without LangSmith uses the
    unwrapped client and behaves identically.
    """
    tracing = os.environ.get("LANGSMITH_TRACING", "").lower() == "true"
    if tracing and os.environ.get("LANGSMITH_API_KEY"):
        logger.debug("Wrapping Anthropic client with LangSmith tracing")
        return wrap_anthropic(client)
    return client
