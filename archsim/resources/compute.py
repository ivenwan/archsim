from __future__ import annotations

from typing import Optional

from ..core.resource import Resource
from ..core.message import Message


class ComputeUnit(Resource):
    def __init__(
        self,
        name: str,
        total_requests: int = 100,
        request_size: int = 64,
        issue_interval: int = 1,
        request_kind: str = "read",
    ) -> None:
        super().__init__(name)
        self.add_port("out", direction="out")
        self.add_port("in", direction="in")
        self.total_requests = total_requests
        self.request_size = request_size
        self.issue_interval = max(1, issue_interval)
        self.request_kind = request_kind
        self._issued = 0
        self._received = 0
        self._last_issue_tick = -10**9

    def tick(self, sim) -> None:
        # Receive any responses
        inq = self.inbox["in"]
        while inq:
            msg = inq.popleft()
            if msg.kind == "resp":
                self._received += 1

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
                self.send("out", req)
                self._issued += 1
                self._last_issue_tick = sim.ticks

    @property
    def progress(self) -> tuple[int, int]:
        return self._issued, self._received

