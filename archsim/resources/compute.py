from __future__ import annotations

from typing import Optional, List, Tuple

from ..core.resource import Resource
from ..core.message import Message
from ..core.databuffer import DataBuffer
from .pe import ProcessingElement


class ComputeUnit(ProcessingElement):
    def __init__(
        self,
        name: str,
        total_requests: int = 100,
        request_size: int = 64,
        issue_interval: int = 1,
        request_kind: str = "read",
        # Buffer production options
        produce_buffers: bool = False,
        buffer_size: int = 1024,
        buffer_dest: str = "memory",
        consume_after: Optional[int] = None,  # ticks after issue to request deallocation
    ) -> None:
        # Initialize as a PE with 1 in, 1 out in pro mode to retain original ports
        super().__init__(name, in_queues=1, out_queues=1, mode="pro", output_target="memory")
        # Backward-compatible alias ports 'in'/'out'
        self.inbox["in"] = self.inbox["in0"]
        self.outbox["out"] = self.outbox["out0"]
        self.total_requests = total_requests
        self.request_size = request_size
        self.issue_interval = max(1, issue_interval)
        self.request_kind = request_kind
        self._issued = 0
        self._received = 0
        self._last_issue_tick = -10**9
        self.produce_buffers = produce_buffers
        self.buffer_size = buffer_size
        self.buffer_dest = buffer_dest
        self.consume_after = consume_after
        self._consume_queue: List[Tuple[int, str]] = []  # (due_tick, buffer_id)

    def tick(self, sim) -> None:
        # Receive any responses
        inq = self.inbox["in0"]
        while inq:
            msg = inq.popleft()
            if msg.kind == "resp":
                self._received += 1

        # Optionally issue buffer creations/transfers
        if self.produce_buffers:
            if self._issued < self.total_requests and (sim.ticks - self._last_issue_tick) >= self.issue_interval:
                buf = DataBuffer(size=self.buffer_size)
                # Register ownership with the pool (owned by compute until transferred)
                sim.buffer_pool.register(buf, owner=self.name)
                sim.buffer_pool.set_state(sim, buf.id, "allocated")
                msg = Message(
                    src=self.name,
                    dst=self.buffer_dest,
                    size=buf.size,
                    kind="buffer_transfer",
                    payload={"buffer": buf.to_dict()},
                    created_at=sim.ticks,
                )
                self.send("out0", msg)
                sim.buffer_pool.set_state(sim, buf.id, "transit")
                self._issued += 1
                self._last_issue_tick = sim.ticks
                if self.consume_after is not None:
                    self._consume_queue.append((sim.ticks + max(0, self.consume_after), buf.id))
        else:
            # Issue new request if allowed by interval and quota
            if self._issued < self.total_requests:
                if (sim.ticks - self._last_issue_tick) >= self.issue_interval:
                    req = Message(
                        src=self.name,
                        dst="memory",  # symbolic; route decided by topology
                        size=self.request_size,
                        kind=self.request_kind,
                        created_at=sim.ticks,
                    )
                    self.send("out0", req)
                    self._issued += 1
                    self._last_issue_tick = sim.ticks

        # Emit scheduled buffer consume requests
        if self._consume_queue:
            # Maintain FIFO by due tick
            while self._consume_queue and self._consume_queue[0][0] <= sim.ticks:
                _, bid = self._consume_queue.pop(0)
                msg = Message(
                    src=self.name,
                    dst=self.buffer_dest,
                    size=1,
                    kind="buffer_consume",
                    payload={"buffer_id": bid},
                    created_at=sim.ticks,
                )
                self.send("out0", msg)

    @property
    def progress(self) -> tuple[int, int]:
        return self._issued, self._received
