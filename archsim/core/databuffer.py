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


class BufferRoles:
    SOURCE = "source"
    DEST = "destination"


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
    # Ownership and role metadata
    owner_memory: Optional[str] = None
    role: str = BufferRoles.SOURCE
    destination_pe: Optional[str] = None
    destination_queue: Optional[str] = None
    # Inflight accounting
    bytes_received: int = 0
    bytes_sent: int = 0
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
            "owner_memory": self.owner_memory,
            "role": self.role,
            "destination_pe": self.destination_pe,
            "destination_queue": self.destination_queue,
            "bytes_received": self.bytes_received,
            "bytes_sent": self.bytes_sent,
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
        if "owner_memory" in d:
            buf.owner_memory = d.get("owner_memory")
        if "role" in d:
            buf.role = str(d.get("role"))
        if "destination_pe" in d:
            buf.destination_pe = d.get("destination_pe")
        if "destination_queue" in d:
            buf.destination_queue = d.get("destination_queue")
        if "bytes_received" in d:
            buf.bytes_received = int(d.get("bytes_received", 0))
        if "bytes_sent" in d:
            buf.bytes_sent = int(d.get("bytes_sent", 0))
        if "triggers" in d and isinstance(d["triggers"], list):
            buf.triggers = list(d["triggers"])  # shallow copy
        return buf

    @property
    def buffering_size(self) -> int:
        return max(0, self.bytes_received - self.bytes_sent)

    def add_received(self, amount: int) -> None:
        self.bytes_received = min(self.size, max(0, self.bytes_received + amount))

    def add_sent(self, amount: int) -> None:
        self.bytes_sent = min(self.size, max(0, self.bytes_sent + amount))
