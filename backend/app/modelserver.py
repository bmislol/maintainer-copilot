"""Model inference server entry point.

Hosts the fine-tuned classifier, NER, and summarization endpoints.
Currently a stub — real model loading lands in Phase 2.1.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Maintainer's Copilot — Model Server",
    version="0.1.0",
    description="Inference server for classifier, NER, and summarizer. Stub.",
)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
