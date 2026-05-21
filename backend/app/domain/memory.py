"""Domain models for memory — Phase 4.3."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

MemoryType = Literal["episodic", "semantic", "procedural"]


class MemoryEntry(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    content: str
    memory_type: MemoryType
    created_at: datetime

    model_config = {"from_attributes": True}
