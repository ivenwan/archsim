from __future__ import annotations

from collections import deque
from typing import Deque, List, Tuple, Optional

from ..core.resource import Resource
from ..core.message import Message


class SemaphoreStation(Resource):
    """
    Tracks an array of counting semaphores and processes client operations.

    - count: number of semaphores (default 32), each initialized to 0.

    Supported operations via Message.kind:
    - "sem_signal": increment semaphore i. If any waiters are queued for i, grant
      one waiter immediately (without increasing the counter).
    - "sem_wait": if semaphore i > 0, decrement and grant immediately; otherwise
      enqueue the request until a future signal arrives.

    Message payload requirements:
    - payload["index"]: int semaphore index (0 <= index < count)

    Responses:
    - "sem_granted": sent to waiting or immediate-wait clients when their wait is
      granted. payload: {"index": i, "reply_to": <id>}
    - "sem_ack": optional ack for signal/wait enqueue. payload includes
      {"index": i, "action": "signal"|"wait_enqueued"|"wait_immediate"}
    """

    def __init__(self, name: str, count: int = 32) -> None:
        super().__init__(name)
        if count <= 0:
            raise ValueError("SemaphoreStation.count must be > 0")
        self.count = count
        self.values: List[int] = [0 for _ in range(count)]
        self.waiters: List[Deque[Tuple[str, str]]] = [deque() for _ in range(count)]

        self.add_port("in", direction="in")
        self.add_port("out", direction="out")

    def _validate_index(self, idx: int) -> None:
        if not (0 <= idx < self.count):
            raise IndexError(f"Semaphore index {idx} out of range [0,{self.count})")

    def _grant_waiter(self, idx: int, sim) -> bool:
        q = self.waiters[idx]
        if q:
            dst, reply_to = q.popleft()
            grant = Message(
                src=self.name,
                dst=dst,
                size=1,
                kind="sem_granted",
                payload={"index": idx, "reply_to": reply_to},
                created_at=sim.ticks,
            )
            self.send("out", grant)
            return True
        return False

    def _handle_signal(self, idx: int, req: Message, sim) -> None:
        # If someone is waiting, grant them instead of incrementing
        if not self._grant_waiter(idx, sim):
            self.values[idx] += 1
        # Optional ack back to signaler
        ack = Message(
            src=self.name,
            dst=req.src,
            size=1,
            kind="sem_ack",
            payload={"index": idx, "action": "signal", "value": self.values[idx], "reply_to": req.id},
            created_at=sim.ticks,
        )
        self.send("out", ack)

    def _handle_wait(self, idx: int, req: Message, sim) -> None:
        if self.values[idx] > 0:
            # Consume one unit and grant immediately
            self.values[idx] -= 1
            grant = Message(
                src=self.name,
                dst=req.src,
                size=1,
                kind="sem_granted",
                payload={"index": idx, "reply_to": req.id},
                created_at=sim.ticks,
            )
            self.send("out", grant)
            # Optional ack (immediate)
            ack = Message(
                src=self.name,
                dst=req.src,
                size=1,
                kind="sem_ack",
                payload={"index": idx, "action": "wait_immediate", "value": self.values[idx], "reply_to": req.id},
                created_at=sim.ticks,
            )
            self.send("out", ack)
        else:
            # Enqueue waiter
            self.waiters[idx].append((req.src, req.id))
            # Optional ack (enqueued)
            ack = Message(
                src=self.name,
                dst=req.src,
                size=1,
                kind="sem_ack",
                payload={"index": idx, "action": "wait_enqueued", "value": self.values[idx], "reply_to": req.id},
                created_at=sim.ticks,
            )
            self.send("out", ack)

    def tick(self, sim) -> None:
        inq = self.inbox["in"]
        while inq:
            req = inq.popleft()
            kind = getattr(req, "kind", None)
            payload = getattr(req, "payload", {}) or {}
            idx = int(payload.get("index", -1))
            try:
                self._validate_index(idx)
            except Exception:
                # Invalid index: ignore request
                continue

            if kind == "sem_signal":
                self._handle_signal(idx, req, sim)
            elif kind == "sem_wait":
                self._handle_wait(idx, req, sim)
            else:
                # Unknown op for this station; ignore
                pass

