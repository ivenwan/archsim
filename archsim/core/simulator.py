from __future__ import annotations

from typing import Optional

from .topology import Topology
from .buffer_pool import BufferPool
from ..metrics import Metrics


class Simulator:
    def __init__(self, topology: Optional[Topology] = None, tracer: Optional[object] = None) -> None:
        self.topology = topology or Topology()
        self.ticks = 0
        self.metrics = Metrics()
        self.buffer_pool = BufferPool()
        self.topology.simulator = self
        self.tracer = tracer

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
        # Buffer pool time-based updates (e.g., expected arrivals)
        if hasattr(self, "buffer_pool") and self.buffer_pool is not None:
            try:
                self.buffer_pool.tick(self)
            except Exception:
                pass
        # Finalize channel occupancy (if resources expose finalize_tick)
        for r in list(self.topology.resources.values()):
            finalize = getattr(r, "finalize_tick", None)
            if callable(finalize):
                try:
                    finalize(self)
                except Exception:
                    pass
        # Notify tracer after completing the tick
        if self.tracer is not None and hasattr(self.tracer, "on_tick"):
            try:
                self.tracer.on_tick(self)
            except Exception:
                # Tracing should never break simulation
                pass

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
