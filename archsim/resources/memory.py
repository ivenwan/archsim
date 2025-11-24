from __future__ import annotations

from collections import deque
from typing import Deque, List, Tuple, Dict, Optional

from ..core.resource import Resource
from ..core.message import Message
from ..core.databuffer import DataBuffer


class Memory(Resource):
    def __init__(self, name: str, latency: int = 20, max_issue_per_tick: int = 1):
        super().__init__(name)
        self.latency = latency
        self.max_issue_per_tick = max_issue_per_tick
        self.add_port("in", direction="in")
        self.add_port("out", direction="out")
        self._inflight: Deque[Tuple[int, Message]] = deque()
        # Keep last simulator reference for reporting
        self._last_sim = None

    # Buffer APIs
    def allocate_buffer(self, sim, buf: DataBuffer) -> None:
        buf.owner_memory = self.name
        sim.buffer_pool.register(buf, owner=self.name)

    def deallocate_buffer(self, sim, buf_id: str) -> Optional[DataBuffer]:
        owner = sim.buffer_pool.owner(buf_id)
        if owner == self.name:
            return sim.buffer_pool.delete(buf_id)
        # If not owned by this memory, ignore
        return None

    @property
    def total_allocated_bytes(self) -> int:
        sim = self._last_sim
        if sim is None:
            return 0
        return sim.buffer_pool.bytes_owned(self.name)

    def tick(self, sim) -> None:
        # Track last sim for reporting
        self._last_sim = sim

        # Issue new requests up to throughput
        issued = 0
        inq = self.inbox["in"]
        while inq and issued < self.max_issue_per_tick:
            req = inq.popleft()
            kind = getattr(req, "kind", "data")

            # Handle DataBuffer lifecycle operations
            if kind == "buffer_transfer":
                payload = getattr(req, "payload", {}) or {}
                buf_dict = payload.get("buffer")
                if isinstance(buf_dict, DataBuffer):
                    buf = buf_dict
                elif isinstance(buf_dict, dict):
                    buf = DataBuffer.from_dict(buf_dict)
                else:
                    # If no explicit buffer provided, synthesize from message size
                    buf = DataBuffer(size=getattr(req, "size", 1))
                # Register / transfer ownership to this memory
                if sim.buffer_pool.exists(buf.id):
                    sim.buffer_pool.transfer(buf.id, self.name)
                else:
                    self.allocate_buffer(sim, buf)
                # Optional ACK
                ack = Message(
                    src=self.name,
                    dst=req.src,
                    size=1,
                    kind="buffer_ack",
                    payload={"buffer_id": buf.id},
                    created_at=sim.ticks,
                )
                ready_tick = sim.ticks + max(0, self.latency)
                self._inflight.append((ready_tick, ack))
                # Mark responded at enqueue time (delivery will occur later)
                sim.buffer_pool.set_state(sim, buf.id, "responded")
                issued += 1
                continue

            if kind == "buffer_consume":
                payload = getattr(req, "payload", {}) or {}
                buf_id = payload.get("buffer_id")
                if buf_id:
                    self.deallocate_buffer(sim, str(buf_id))
                    sim.buffer_pool.set_state(sim, str(buf_id), "deallocated")
                # Optional ACK to requester
                ack = Message(
                    src=self.name,
                    dst=req.src,
                    size=1,
                    kind="buffer_freed",
                    payload={"buffer_id": buf_id},
                    created_at=sim.ticks,
                )
                ready_tick = sim.ticks + max(0, self.latency)
                self._inflight.append((ready_tick, ack))
                issued += 1
                continue

            # Default behavior: memory request/response
            resp = Message(
                src=self.name,
                dst=req.src,  # return to sender
                size=req.size,
                kind="resp",
                payload={"reply_to": req.id, "kind": req.kind},
                created_at=sim.ticks,
            )
            ready_tick = sim.ticks + max(0, self.latency)
            self._inflight.append((ready_tick, resp))
            issued += 1

        # Emit ready responses
        while self._inflight and self._inflight[0][0] <= sim.ticks:
            _, resp = self._inflight.popleft()
            self.send("out", resp)
