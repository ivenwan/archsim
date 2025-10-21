from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4


@dataclass
class Message:
    src: str
    dst: str
    size: int = 1  # bytes
    kind: str = "data"  # e.g., 'read', 'write', 'resp', 'data'
    payload: Optional[Any] = None
    created_at: int = 0
    id: str = field(default_factory=lambda: f"msg-{uuid4().hex[:8]}")
    reply_to: Optional[str] = None

    def __post_init__(self) -> None:
        if self.size <= 0:
            raise ValueError("Message.size must be > 0")

