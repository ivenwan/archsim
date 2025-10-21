from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Iterable, Optional


class Resource:
    def __init__(self, name: str):
        self.name = name
        self.inbox: Dict[str, Deque] = {}
        self.outbox: Dict[str, Deque] = {}

    # Port management
    def add_port(self, port: str, direction: str = "both") -> None:
        if direction in ("in", "both"):
            self.inbox.setdefault(port, deque())
        if direction in ("out", "both"):
            self.outbox.setdefault(port, deque())

    def ports(self) -> Iterable[str]:
        return set(self.inbox.keys()) | set(self.outbox.keys())

    # Messaging helpers
    def recv(self, port: str):
        q = self.inbox.get(port)
        if q and len(q) > 0:
            return q.popleft()
        return None

    def peek_in(self, port: str) -> Optional[object]:
        q = self.inbox.get(port)
        if q and len(q) > 0:
            return q[0]
        return None

    def send(self, port: str, msg) -> None:
        self.outbox.setdefault(port, deque()).append(msg)

    def out_queue(self, port: str) -> Deque:
        return self.outbox.setdefault(port, deque())

    def in_queue(self, port: str) -> Deque:
        return self.inbox.setdefault(port, deque())

    # Default behavior: pass-through from same-named in->out
    def on_receive(self, port: str, msg, sim) -> None:
        if port in self.outbox:
            self.send(port, msg)

    def tick(self, sim) -> None:
        for port, q in list(self.inbox.items()):
            while q:
                msg = q.popleft()
                self.on_receive(port, msg, sim)

