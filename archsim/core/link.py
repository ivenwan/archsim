from __future__ import annotations

from collections import deque
from typing import Deque, Optional


class Link:
    def __init__(
        self,
        src,
        src_port: str,
        dst,
        dst_port: str,
        bandwidth: int = 1,  # bytes per tick
        latency: int = 1,  # ticks
        name: Optional[str] = None,
    ) -> None:
        if bandwidth <= 0:
            raise ValueError("Link.bandwidth must be > 0")
        if latency < 0:
            raise ValueError("Link.latency must be >= 0")
        self.src = src
        self.src_port = src_port
        self.dst = dst
        self.dst_port = dst_port
        self.bandwidth = bandwidth
        self.latency = latency
        self.name = name or f"{src.name}:{src_port}->{dst.name}:{dst_port}"

        # Pipeline stages: stage 0 is the stage that accepts from src this tick
        # After tick, data in stage i moves to i+1; stage (latency) delivers
        self.pipeline: list[Deque] = [deque() for _ in range(max(1, latency))]

        # Basic accounting
        self.bytes_moved_this_tick: int = 0
        self.utilization_sum: int = 0
        self.ticks: int = 0

    def tick(self, sim) -> None:
        self.ticks += 1
        self.bytes_moved_this_tick = 0

        # Delivery if latency >= 1
        if self.latency >= 1:
            last = self.pipeline[-1]
            while last:
                msg = last.popleft()
                sim.deliver(self.dst, self.dst_port, msg)
                self.bytes_moved_this_tick += msg.size
                sim.metrics.messages_delivered += 1
                sim.metrics.bytes_transferred += msg.size

            # Shift pipeline forward
            for i in range(len(self.pipeline) - 1, 0, -1):
                prev = self.pipeline[i - 1]
                cur = self.pipeline[i]
                while prev:
                    cur.append(prev.popleft())

            # Now stage 0 is empty and ready to accept
            # Pull from src outbox subject to bandwidth
            capacity = self.bandwidth
            outq = self.src.outbox.get(self.src_port)
            if outq is not None:
                while outq and capacity >= getattr(outq[0], "size", 1):
                    msg = outq.popleft()
                    self.pipeline[0].append(msg)
                    capacity -= getattr(msg, "size", 1)
        else:
            # latency == 0: deliver immediately subject to bandwidth
            capacity = self.bandwidth
            outq = self.src.outbox.get(self.src_port)
            if outq is not None:
                while outq and capacity >= getattr(outq[0], "size", 1):
                    msg = outq.popleft()
                    sim.deliver(self.dst, self.dst_port, msg)
                    capacity -= getattr(msg, "size", 1)
                    self.bytes_moved_this_tick += msg.size
                    sim.metrics.messages_delivered += 1
                    sim.metrics.bytes_transferred += msg.size

        self.utilization_sum += self.bytes_moved_this_tick

    @property
    def utilization(self) -> float:
        if self.ticks == 0:
            return 0.0
        # utilization measured as avg bytes moved / bandwidth per tick
        return min(1.0, (self.utilization_sum / max(1, self.ticks)) / self.bandwidth)

