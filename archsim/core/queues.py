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
    If a channel is provided, chunk transmission respects its current bandwidth.
    """

    def __init__(self, parent: str, function: str):
        super().__init__(parent=parent, direction="out", function=function)
        self._scheduled: set[str] = set()
        self._dest_map: dict[str, Optional[str]] = {}

    def enqueue_transfer(self, buf: DataBuffer, dst_memory: str, dst_pe: Optional[str] = None, dst_queue: str = "in0") -> None:
        self.enqueue((buf, dst_memory, dst_pe, dst_queue))

    def step(self, sim, channel=None) -> None:
        if not self.items:
            return
        head = self.items[0]
        if not isinstance(head, tuple) or len(head) < 2:
            return
        buf, dst_mem, dst_pe, dst_q = head
        if not isinstance(buf, DataBuffer):
            return
        # Register destination if not already scheduled
        if buf.id not in self._scheduled:
            dest = sim.buffer_pool.schedule_transfer(sim, buf.id, dst_mem, dst_pe=dst_pe, dst_queue=dst_q)
            self._dest_map[buf.id] = getattr(dest, "id", None) if dest else None
            self._scheduled.add(buf.id)
            # Assume source is fully available to send; mark received
            if buf.bytes_received < buf.size:
                buf.add_received(buf.size - buf.bytes_received)

        # If channel is backpressured or has zero capacity, wait
        capacity = None
        if channel is not None:
            if hasattr(channel, "current_bandwidth"):
                capacity = channel.current_bandwidth
            else:
                capacity = getattr(channel, "bandwidth", None)
            if capacity is not None and capacity <= 0:
                return

        buffering = buf.buffering_size
        if buffering <= 0:
            return
        if capacity is None:
            send_bytes = buffering
        else:
            send_bytes = min(buffering, capacity)

        buf.add_sent(send_bytes)

        # If we've sent the entire buffer, record expected arrival and dequeue
        if buf.bytes_sent >= buf.size:
            dest_id = self._dest_map.get(buf.id)
            if dest_id:
                arrival = sim.ticks + (getattr(channel, "latency", 0) if channel is not None else 0)
                sim.buffer_pool.record_expected_arrival(dest_id, arrival)
            self.items.popleft()
            self._scheduled.discard(buf.id)
            self._dest_map.pop(buf.id, None)
