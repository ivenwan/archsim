from __future__ import annotations

import math
from ..core.resource import Resource


class Channel(Resource):
    """
    Base channel connecting an input to an output with bandwidth and latency.

    - bandwidth: bytes per tick
    - latency: pipeline latency in ticks (propagation)

    Subclasses may implement additional behavior, but this base provides
    helpers to estimate transfer time for a payload of given size.
    """

    def __init__(self, name: str, bandwidth: int = 128, latency: int = 5) -> None:
        super().__init__(name)
        if bandwidth <= 0:
            raise ValueError("Channel.bandwidth must be > 0")
        if latency < 0:
            raise ValueError("Channel.latency must be >= 0")
        self.bandwidth = bandwidth
        self.latency = latency
        self.add_port("in", direction="in")
        self.add_port("out", direction="out")

    def estimate_ticks(self, size: int) -> int:
        data_ticks = math.ceil(max(1, size) / self.bandwidth)
        return max(0, self.latency) + data_ticks

