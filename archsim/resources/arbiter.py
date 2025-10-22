from __future__ import annotations

from typing import List, Optional

from ..core.resource import Resource
from ..core.channel import Channel
from ..core.message import Message


class Arbiter(Resource):
    """
    Arbiter merges traffic from multiple upstream inputs into a single
    downstream output according to a chosen mode:

    - mode="shared": share downstream capacity among active inputs using
      round-robin across input ports each tick.
    - mode="scheduled": pick one input port with pending data and let it
      use the downstream fully until its queue drains, then switch.

    Notes
    - This component shapes how messages are enqueued toward the downstream
      bus/link. The actual bytes delivered per tick are ultimately limited by
      the downstream link bandwidth.
    - Messages are forwarded whole (no fragmentation). If you need sub-message
      interleaving, use smaller message sizes or add a fragmentation stage.
    """

    def __init__(self, name: str, mode: str = "shared") -> None:
        super().__init__(name)
        if mode not in ("shared", "scheduled"):
            raise ValueError("Arbiter mode must be 'shared' or 'scheduled'")
        self.mode = mode
        self.add_port("out", direction="out")
        self._inputs: List[str] = []
        self._rr_index: int = 0
        self._active_port: Optional[str] = None
        # Scheduling against a downstream channel
        self._downstream: Optional[Channel] = None
        self._available_from: int = 0
        # One outstanding per initiator; track active transfer per port
        self._inflight_by_port: dict[str, Optional[str]] = {}
        # Active transfers for interleaving schedule
        # item: {port, buf_id, total, progressed, start, last_update, per_share_bw, expected}
        self._active: list[dict] = []

    def add_input(self, port: str) -> None:
        if port not in self.inbox:
            self.add_port(port, direction="in")
            self._inputs.append(port)

    def set_downstream_channel(self, channel: Channel) -> None:
        """Inform the arbiter which channel it feeds for scheduling estimates."""
        self._downstream = channel

    def _has_pending(self) -> bool:
        for p in self._inputs:
            if self.inbox.get(p) and len(self.inbox[p]) > 0:
                return True
        return False

    def _next_nonempty_from(self, start: int) -> Optional[int]:
        if not self._inputs:
            return None
        n = len(self._inputs)
        for i in range(n):
            idx = (start + i) % n
            q = self.inbox.get(self._inputs[idx])
            if q and len(q) > 0:
                return idx
        return None

    def tick(self, sim) -> None:
        if not self._inputs:
            return

        # Clean up completed transfers
        now = sim.ticks
        if self._downstream is not None and getattr(self._downstream, "transfer_mode", None) == "interleaving":
            # In interleaving, use expected arrival to drop finished
            self._active = [a for a in self._active if a.get("expected", now + 1) > now]
            # Update inflight map accordingly
            active_ports = {a["port"] for a in self._active}
            for p in self._inputs:
                if self._inflight_by_port.get(p) and p not in active_ports:
                    self._inflight_by_port[p] = None
        else:
            # In blocking, free channel if time has reached available_from
            if self._available_from <= now:
                # No active inflights remain
                for p in self._inputs:
                    self._inflight_by_port[p] = None

        # Decide arbitration + scheduling policy
        channel_mode = None
        if self._downstream is not None:
            channel_mode = self._downstream.transfer_mode
        # Fallback to arbiter.mode legacy mapping
        if channel_mode is None:
            channel_mode = "interleaving" if self.mode == "shared" else "blocking"

        if channel_mode == "interleaving":
            # Round-robin across inputs, forwarding one message at a time
            start = self._rr_index
            idx = self._next_nonempty_from(start)
            visited = 0
            while idx is not None and visited < len(self._inputs):
                port = self._inputs[idx]
                q = self.inbox[port]
                # Allow at most one outstanding per port
                if q and (not self._inflight_by_port.get(port)):
                    msg = q.popleft()
                    # Schedule in interleaving set
                    buf_id = None
                    payload = getattr(msg, "payload", {}) or {}
                    b = payload.get("buffer")
                    if isinstance(b, dict):
                        buf_id = b.get("id")
                    self._inflight_by_port[port] = buf_id or "inflight"
                    # Add active transfer
                    self._active.append({
                        "port": port,
                        "buf_id": buf_id,
                        "total": getattr(msg, "size", 1),
                        "progressed": 0,
                        "start": now,
                        "last_update": now,
                        "per_share_bw": 0,
                        "expected": now,
                    })
                    # Forward message downstream
                    self.send("out", msg)
                    # Recompute expected arrivals for all actives based on shared BW
                    self._recompute_interleaving(sim)
                visited += 1
                next_idx = self._next_nonempty_from(idx + 1)
                if next_idx is None:
                    break
                idx = next_idx
            # Advance RR pointer for next tick
            self._rr_index = (start + 1) % len(self._inputs)
            # Update channel active state
            if self._downstream is not None:
                active_count = len(self._active)
                expected_max = max((a.get("expected", 0) for a in self._active), default=sim.ticks)
                self._downstream.set_active_state(sim.ticks, active_count, expected_max)

        else:  # blocking
            # Keep serving the active port until empty; then pick next non-empty
            if self._active_port is None or not self.inbox.get(self._active_port) or len(self.inbox[self._active_port]) == 0:
                # Choose next non-empty port starting from rr_index
                idx = self._next_nonempty_from(self._rr_index)
                self._active_port = self._inputs[idx] if idx is not None else None
                # Advance rr index for fairness next time we switch
                if idx is not None:
                    self._rr_index = (idx + 1) % len(self._inputs)

            if self._active_port is None:
                return

            q = self.inbox[self._active_port]
            # Drain as many messages as available into outbox this tick
            # In blocking mode, only admit a message if channel is free
            if self._available_from <= now and q:
                msg = q.popleft()
                if isinstance(msg, Message) and getattr(msg, "kind", None) == "buffer_transfer" and self._downstream is not None:
                    size = getattr(msg, "size", 1)
                    start_time = max(now, self._available_from)
                    duration = self._downstream.estimate_ticks(size)
                    arrival = start_time + duration
                    payload = getattr(msg, "payload", {}) or {}
                    buf_dict = payload.get("buffer")
                    buf_id = None
                    if isinstance(buf_dict, dict):
                        buf_id = buf_dict.get("id")
                    if buf_id:
                        sim.buffer_pool.record_expected_arrival(str(buf_id), arrival)
                    self._available_from = arrival
                    # Mark inflight for the active port
                    self._inflight_by_port[self._active_port] = buf_id or "inflight"
                self.send("out", msg)
            # Update channel active state: busy if available_from in future
            if self._downstream is not None:
                active_count = 1 if self._available_from > now else 0
                self._downstream.set_active_state(now, active_count, self._available_from if active_count else None)

    def _recompute_interleaving(self, sim) -> None:
        if not self._downstream or not self._active:
            return
        now = sim.ticks
        n = max(1, len(self._active))
        share_bw = max(1, int(self._downstream.bandwidth / n))
        for a in self._active:
            # Accumulate progress since last update using previous share
            dt = max(0, now - int(a.get("last_update", now)))
            prev_bw = int(a.get("per_share_bw", share_bw)) or share_bw
            a["progressed"] = min(a["total"], int(a.get("progressed", 0)) + dt * prev_bw)
            remaining = max(0, a["total"] - a["progressed"])
            # Remaining latency budget from start
            lat_elapsed = max(0, now - int(a.get("start", now)))
            lat_rem = max(0, int(self._downstream.latency) - lat_elapsed)
            data_ticks = (remaining + share_bw - 1) // share_bw if share_bw > 0 else 0
            expected = now + lat_rem + data_ticks
            a["per_share_bw"] = share_bw
            a["last_update"] = now
            a["expected"] = expected
            buf_id = a.get("buf_id")
            if buf_id:
                sim.buffer_pool.record_expected_arrival(str(buf_id), expected)
