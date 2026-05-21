"""HyDE query transformation — Phase 3.3 (D-019).

Hypothetical Document Embedding (HyDE, Gao et al. 2022):
  1. Ask the LLM to write a hypothetical answer to the query.
  2. Embed the hypothetical answer — its embedding is closer to relevant
     passages than the raw question embedding.
  3. Retrieve using the hypothetical embedding in addition to (not instead
     of) the original query embedding.

This module implements the LLM call only.  The pipeline in pipeline.py
combines original + HyDE embeddings with BM25 via three-stream RRF.

Design: accepts an AsyncAnthropic client as a parameter so the caller
controls client construction (Vault key injection, test injection).
The module does NOT construct the client internally (D-019 rationale).
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert on scikit-learn.  "
    "Write a short passage (3–6 sentences) that would appear in documentation "
    "or a GitHub issue and directly answers the user's question.  "
    "Do not add headings or bullet points — plain prose only."
)


async def hyde_transform(
    query: str,
    client: AsyncAnthropic,
    model: str = "claude-haiku-4-5",
) -> str:
    """Return a hypothetical passage that answers the query.

    Args:
        query: the user's natural-language question.
        client: AsyncAnthropic instance (caller-provided, Vault-keyed).
        model: Claude model to use for HyDE generation.

    Returns:
        A short prose passage suitable for embedding.
    """
    response = await client.messages.create(
        model=model,
        max_tokens=256,
        system=_SYSTEM,
        messages=[{"role": "user", "content": query}],
    )
    text_blocks = [b for b in response.content if isinstance(b, TextBlock)]
    text = text_blocks[0].text if text_blocks else ""
    logger.debug("HyDE passage (%d chars) for query: %.60s", len(text), query)
    return text
