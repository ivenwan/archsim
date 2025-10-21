from __future__ import annotations

from typing import Optional, List, Dict, Any

from ..core.resource import Resource
from ..core.databuffer import DataBuffer
from ..core.message import Message


class BufferGenerator(Resource):
    """
    Periodically creates a DataBuffer and transmits it to a specified memory.

    Parameters
    - period: ticks between buffer generations (>=1)
    - buffer_size: bytes per generated buffer
    - target_memory: resource name of destination memory
    - start_tick: first tick to generate
    - total: total number of buffers to generate (None = infinite)
    """

    def __init__(
        self,
        name: str,
        period: int = 10,
        buffer_size: int = 4096,
        target_memory: str = "memory",
        start_tick: int = 0,
        total: Optional[int] = None,
        triggers: Optional[List[Dict[str, Any]]] = None,
        auto_consume_after: Optional[int] = None,
    ) -> None:
        super().__init__(name)
        self.add_port("out", direction="out")
        self.add_port("in", direction="in")  # to receive acks if wired
        self.period = max(1, period)
        self.buffer_size = buffer_size
        self.target_memory = target_memory
        self.start_tick = max(0, start_tick)
        self.total = total
        self._next_tick = self.start_tick
        self._produced = 0
        self.triggers = list(triggers) if triggers else []
        self.auto_consume_after = auto_consume_after
        self._consume_queue: List[tuple[int, str]] = []  # (due_tick, buffer_id)

    def tick(self, sim) -> None:
        # Drain any incoming responses/acks and capture buffer_ids
        inq = self.inbox["in"]
        while inq:
            msg = inq.popleft()
            if self.auto_consume_after is not None and getattr(msg, "kind", None) == "buffer_ack":
                buf_id = (getattr(msg, "payload", {}) or {}).get("buffer_id")
                if buf_id:
                    self._consume_queue.append((sim.ticks + max(0, self.auto_consume_after), str(buf_id)))

        if self.total is not None and self._produced >= self.total:
            return

        if sim.ticks >= self._next_tick:
            # Create and register buffer owned by generator
            buf = DataBuffer(size=self.buffer_size)
            if self.triggers:
                buf.triggers = list(self.triggers)
            sim.buffer_pool.register(buf, owner=self.name)
            sim.buffer_pool.set_state(sim, buf.id, "allocated")
            # Send transfer request to memory
            msg = Message(
                src=self.name,
                dst=self.target_memory,
                size=buf.size,
                kind="buffer_transfer",
                payload={"buffer": buf.to_dict()},
                created_at=sim.ticks,
            )
            self.send("out", msg)
            sim.buffer_pool.set_state(sim, buf.id, "transit")
            self._produced += 1
            self._next_tick += self.period

        # Emit scheduled buffer_consume requests
        while self._consume_queue and self._consume_queue[0][0] <= sim.ticks:
            _, bid = self._consume_queue.pop(0)
            msg = Message(
                src=self.name,
                dst=self.target_memory,
                size=1,
                kind="buffer_consume",
                payload={"buffer_id": bid},
                created_at=sim.ticks,
            )
            self.send("out", msg)
