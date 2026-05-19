"""Model inference server entry point.

Hosts the fine-tuned classifier, NER, and summarization endpoints.
Currently a stub — real model loading lands in Phase 2.1.
"""

import logging

from fastapi import FastAPI

from app.core.logging import configure_logging

configure_logging(service_name="modelserver")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Maintainer's Copilot — Model Server",
    version="0.1.0",
    description="Inference server for classifier, NER, and summarizer. Stub.",
)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
