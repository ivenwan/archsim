from __future__ import annotations

from typing import Optional

from ..core.resource import Resource
from ..core.message import Message


class SemaphoreClient(Resource):
    """
    Simple client that waits on a semaphore index and records grants.
    Sends a single sem_wait at start_tick, optionally repeats every period if provided.
    """

    def __init__(self, name: str, station: str, index: int, start_tick: int = 0, period: Optional[int] = None) -> None:
        super().__init__(name)
        self.add_port("out", direction="out")
        self.add_port("in", direction="in")
        self.station = station
        self.index = int(index)
        self.start_tick = max(0, start_tick)
        self.period = period if (period is None or period >= 1) else 1
        self._next = self.start_tick
        self.granted = 0

    def tick(self, sim) -> None:
        # Receive grants
        inq = self.inbox["in"]
        while inq:
            msg = inq.popleft()
            if getattr(msg, "kind", None) == "sem_granted":
                self.granted += 1

        # Emit waits
        if self._next is not None and sim.ticks >= self._next:
            m = Message(
                src=self.name,
                dst=self.station,
                size=1,
                kind="sem_wait",
                payload={"index": self.index},
                created_at=sim.ticks,
            )
            self.send("out", m)
            if self.period is None:
                self._next = None
            else:
                self._next += self.period

