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

    def __init__(self, name: str, bandwidth: int = 128, latency: int = 5, transfer_mode: str = "interleaving") -> None:
        super().__init__(name)
        if bandwidth <= 0:
            raise ValueError("Channel.bandwidth must be > 0")
        if latency < 0:
            raise ValueError("Channel.latency must be >= 0")
        self.bandwidth = bandwidth
        self.latency = latency
        if transfer_mode not in ("interleaving", "blocking"):
            raise ValueError("Channel.transfer_mode must be 'interleaving' or 'blocking'")
        self.transfer_mode = transfer_mode
        self.add_port("in", direction="in")
        self.add_port("out", direction="out")
        # Occupancy tracking
        self._ticks: int = 0
        self._busy_ticks: int = 0
        self._active_count: int = 0
        self._last_finalized_tick: int = -1
        # Backpressure
        self._backpressured: bool = False

    def estimate_ticks(self, size: int) -> int:
        bw = self.current_bandwidth
        if bw <= 0:
            # Effectively stalled; return a large placeholder
            return 10**9
        data_ticks = math.ceil(max(1, size) / bw)
        return max(0, self.latency) + data_ticks

    @property
    def is_interleaving(self) -> bool:
        return self.transfer_mode == "interleaving"

    @property
    def is_blocking(self) -> bool:
        return self.transfer_mode == "blocking"

    @property
    def current_bandwidth(self) -> int:
        return 0 if self._backpressured else self.bandwidth

    def set_backpressure(self, flag: bool) -> None:
        self._backpressured = bool(flag)

    # Scheduling/occupancy API (called by arbiters)
    def set_active_state(self, now_tick: int, active_count: int, expected_end_tick: int | None = None) -> None:
        # active_count > 0 means the channel is currently in use this tick
        self._active_count = max(0, int(active_count))

    # Pass-through behavior: forward any messages from 'in' to 'out'
    def tick(self, sim) -> None:
        inq = self.inbox.get("in")
        if inq is not None:
            while inq:
                self.send("out", inq.popleft())

    # Called by simulator at end of tick to fold occupancy stats
    def finalize_tick(self, sim) -> None:
        if self._last_finalized_tick == sim.ticks:
            return
        self._ticks += 1
        if self._active_count > 0:
            self._busy_ticks += 1
        self._last_finalized_tick = sim.ticks

    @property
    def avg_occupancy(self) -> float:
        if self._ticks == 0:
            return 0.0
        return self._busy_ticks / self._ticks
