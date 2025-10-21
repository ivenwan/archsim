from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional

from ..core.resource import Resource


class Bus(Resource):
    def __init__(self, name: str, bandwidth: int = 16):
        super().__init__(name)
        self.bandwidth = bandwidth  # bytes per tick from aggregated senders
        self.add_port("out", direction="out")
        self._rr_order: List[str] = []  # round-robin over input ports

    def add_input(self, port: str) -> None:
        if port not in self.inbox:
            self.add_port(port, direction="in")
            self._rr_order.append(port)

    def tick(self, sim) -> None:
        # Ensure rr order up to date for dynamic ports
        for p in self.inbox.keys():
            if p not in self._rr_order:
                self._rr_order.append(p)

        remaining = self.bandwidth
        if not self._rr_order:
            return

        # Round-robin arbitration across inputs, moving whole messages if they fit
        start_idx = getattr(self, "_last_idx", 0) % max(1, len(self._rr_order))
        idx = start_idx
        spins = 0
        moved_any = False
        while remaining > 0 and spins <= len(self._rr_order):
            port = self._rr_order[idx % len(self._rr_order)]
            q = self.inbox.get(port)
            if q and q:
                msg = q[0]
                size = getattr(msg, "size", 1)
                if size <= remaining:
                    q.popleft()
                    self.send("out", msg)
                    remaining -= size
                    moved_any = True
            idx += 1
            if idx - start_idx >= len(self._rr_order):
                spins += 1
                if not moved_any:
                    break
                moved_any = False
        self._last_idx = idx

