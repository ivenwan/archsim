from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from uuid import uuid4
import os


class BufferStates:
    ALLOCATED = "allocated"
    TRANSIT = "transit"
    ARRIVED = "arrived"
    RESPONDED = "responded"
    INUSE = "inuse"
    DEALLOCATED = "deallocated"


@dataclass
class DataBuffer:
    """
    Abstract data unit moved between memories over buses/links.

    - size: total bytes to transfer
    - content: backing bytes (optional). Defaults to random bytes of length `size`.
    """

    size: int
    content: Optional[bytes] = None
    id: str = field(default_factory=lambda: f"buf-{uuid4().hex[:8]}")
    state: str = BufferStates.ALLOCATED
    # Optional transition triggers: list of dicts like
    # {"on": "arrived", "action": "signal"|"wait", "station": "sem", "index": 0}
    triggers: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.size <= 0:
            raise ValueError("DataBuffer.size must be > 0")
        if self.content is None:
            # Random bytes; avoid excessive memory for very large sizes by capping generation
            # Users can supply content explicitly for large buffers if needed.
            cap = min(self.size, 1_000_000)  # cap generation to 1MB for safety
            payload = os.urandom(cap)
            if cap < self.size:
                # Pad logically without storing full content
                self.content = payload + bytes(self.size - cap)
            else:
                self.content = payload

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "size": self.size,
            "content": self.content,
            "state": self.state,
            "triggers": list(self.triggers) if self.triggers else [],
        }

    @staticmethod
    def from_dict(d: dict) -> "DataBuffer":
        buf = DataBuffer(
            size=int(d["size"]),
            content=d.get("content"),
            id=d.get("id") or f"buf-{uuid4().hex[:8]}",
        )
        if "state" in d:
            buf.state = str(d["state"])  # trust input
        if "triggers" in d and isinstance(d["triggers"], list):
            buf.triggers = list(d["triggers"])  # shallow copy
        return buf
