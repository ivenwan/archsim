from __future__ import annotations

from collections import deque
from typing import Deque, Optional, Tuple
from uuid import uuid4

from .databuffer import DataBuffer


class BaseQueue:
    def __init__(self, parent: str, direction: str, function: str):
        if direction not in ("in", "out"):
            raise ValueError("Queue direction must be 'in' or 'out'")
        self.parent = parent
        self.direction = direction
        self.function = function
        self.uid = f"q-{uuid4().hex[:8]}"
        self.items: Deque = deque()

    @property
    def coordinate(self) -> str:
        return f"{self.parent}:{self.direction}:{self.function}"

    def enqueue(self, item) -> None:
        self.items.append(item)

    def dequeue(self):
        if self.items:
            return self.items.popleft()
        return None

    def peek(self):
        return self.items[0] if self.items else None

    def __len__(self) -> int:
        return len(self.items)


class InputQueue(BaseQueue):
    """Simple input queue wrapper."""

    pass


class OutputQueue(BaseQueue):
    """
    Output queue that can schedule buffer transfers to a destination.
    Items are (DataBuffer, dst_memory, dst_pe, dst_queue).
    """

    def __init__(self, parent: str, function: str):
        super().__init__(parent=parent, direction="out", function=function)
        self._scheduled: set[str] = set()

    def enqueue_transfer(self, buf: DataBuffer, dst_memory: str, dst_pe: Optional[str] = None, dst_queue: str = "in0") -> None:
        self.enqueue((buf, dst_memory, dst_pe, dst_queue))

    def step(self, sim) -> None:
        if not self.items:
            return
        head = self.items[0]
        if not isinstance(head, tuple) or len(head) < 2:
            return
        buf, dst_mem, dst_pe, dst_q = head
        if not isinstance(buf, DataBuffer):
            return
        if buf.id in self._scheduled:
            return
        # Schedule via buffer pool
        sim.buffer_pool.schedule_transfer(sim, buf.id, dst_mem, dst_pe=dst_pe, dst_queue=dst_q)
        self._scheduled.add(buf.id)

