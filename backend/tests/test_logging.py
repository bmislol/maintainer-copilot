"""Smoke test: structured logger emits JSON with required fields."""

from __future__ import annotations

import io
import json
import logging

from app.core.logging import JSONFormatter, request_id_var, trace_id_var


def test_json_formatter_emits_required_fields() -> None:
    """Every log line carries timestamp, level, service, event, request_id, trace_id."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter(service_name="test-service"))

    logger = logging.getLogger("app.test")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    token_req = request_id_var.set("req-123")
    token_trace = trace_id_var.set("trace-abc")
    try:
        logger.info("hello world")
    finally:
        request_id_var.reset(token_req)
        trace_id_var.reset(token_trace)

    line = stream.getvalue().strip()
    payload = json.loads(line)

    assert payload["service"] == "test-service"
    assert payload["level"] == "info"
    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-123"
    assert payload["trace_id"] == "trace-abc"
    assert "timestamp" in payload
