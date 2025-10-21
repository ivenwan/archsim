from __future__ import annotations

from collections import deque
from typing import Deque, List, Tuple

from ..core.resource import Resource
from ..core.message import Message


class Memory(Resource):
    def __init__(self, name: str, latency: int = 20, max_issue_per_tick: int = 1):
        super().__init__(name)
        self.latency = latency
        self.max_issue_per_tick = max_issue_per_tick
        self.add_port("in", direction="in")
        self.add_port("out", direction="out")
        self._inflight: Deque[Tuple[int, Message]] = deque()

    def tick(self, sim) -> None:
        # Issue new requests up to throughput
        issued = 0
        inq = self.inbox["in"]
        while inq and issued < self.max_issue_per_tick:
            req = inq.popleft()
            # Prepare a response message
            resp = Message(
                src=self.name,
                dst=req.src,  # return to sender
                size=req.size,
                kind="resp",
                payload={"reply_to": req.id, "kind": req.kind},
                created_at=sim.ticks,
            )
            ready_tick = sim.ticks + max(0, self.latency)
            self._inflight.append((ready_tick, resp))
            issued += 1

        # Emit ready responses
        while self._inflight and self._inflight[0][0] <= sim.ticks:
            _, resp = self._inflight.popleft()
            self.send("out", resp)

