from __future__ import annotations

from typing import Optional

from .topology import Topology
from ..metrics import Metrics


class Simulator:
    def __init__(self, topology: Optional[Topology] = None) -> None:
        self.topology = topology or Topology()
        self.ticks = 0
        self.metrics = Metrics()

    def deliver(self, resource, port: str, msg) -> None:
        resource.in_queue(port).append(msg)

    def add_resources(self, *resources) -> None:
        self.topology.add(*resources)

    def tick(self) -> None:
        # First, tick all resources
        for r in list(self.topology.resources.values()):
            r.tick(self)

        # Then, tick all links to move data along
        for link in self.topology.links:
            link.tick(self)

        self.ticks += 1
        self.metrics.ticks = self.ticks

    def run(self, max_ticks: int = 1000, until_quiescent: bool = False) -> None:
        for _ in range(max_ticks):
            self.tick()
            if until_quiescent and self.is_quiescent():
                break

    def is_quiescent(self) -> bool:
        # No messages in any in/out queues and no messages in links
        for r in self.topology.resources.values():
            for q in list(r.inbox.values()) + list(r.outbox.values()):
                if q:
                    return False
        for link in self.topology.links:
            if any(stage for stage in link.pipeline):
                return False
        return True

