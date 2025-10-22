from __future__ import annotations

from typing import Optional, List

from ..core.resource import Resource
from ..core.message import Message


class SemaphoreRecorder(Resource):
    """
    Records the ticks when a semaphore is granted. It continuously waits on
    the given semaphore index by re-issuing a wait after each grant.
    """

    def __init__(self, name: str, station: str, index: int, start_tick: int = 0) -> None:
        super().__init__(name)
        self.add_port("out", direction="out")
        self.add_port("in", direction="in")
        self.station = station
        self.index = int(index)
        self.start_tick = max(0, start_tick)
        self._armed = False
        self.grants: List[int] = []

    def _issue_wait(self, sim) -> None:
        m = Message(
            src=self.name,
            dst=self.station,
            size=1,
            kind="sem_wait",
            payload={"index": self.index},
            created_at=sim.ticks,
        )
        self.send("out", m)
        self._armed = True

    def tick(self, sim) -> None:
        # Arm on first eligible tick
        if not self._armed and sim.ticks >= self.start_tick:
            self._issue_wait(sim)

        # Consume incoming messages and record grants
        inq = self.inbox["in"]
        while inq:
            msg = inq.popleft()
            if getattr(msg, "kind", None) == "sem_granted":
                self.grants.append(sim.ticks)
                # Re-arm immediately to catch subsequent signals
                self._issue_wait(sim)

