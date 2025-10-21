from __future__ import annotations

from typing import List, Optional

from ..core.resource import Resource


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

    def add_input(self, port: str) -> None:
        if port not in self.inbox:
            self.add_port(port, direction="in")
            self._inputs.append(port)

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

        if self.mode == "shared":
            # Round-robin across inputs, forwarding one message at a time
            start = self._rr_index
            idx = self._next_nonempty_from(start)
            visited = 0
            while idx is not None and visited < len(self._inputs):
                port = self._inputs[idx]
                q = self.inbox[port]
                if q:
                    msg = q[0]
                    # Forward whole message
                    self.send("out", q.popleft())
                visited += 1
                next_idx = self._next_nonempty_from(idx + 1)
                if next_idx is None:
                    break
                idx = next_idx
            # Advance RR pointer for next tick
            self._rr_index = (start + 1) % len(self._inputs)

        else:  # scheduled
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
            while q:
                self.send("out", q.popleft())

