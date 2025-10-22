from __future__ import annotations

from typing import Dict, Optional, Set, List, Any

from .databuffer import DataBuffer
from .message import Message


class BufferPool:
    """
    Global buffer pool for tracking all dynamic DataBuffers in the system.

    - Registers buffers and tracks ownership by resource name (e.g., memory id).
    - Supports ownership transfer and deletion.
    - Computes total and per-owner allocated bytes.
    """

    def __init__(self) -> None:
        self._buffers: Dict[str, DataBuffer] = {}
        self._owner_of: Dict[str, Optional[str]] = {}
        self._owned_by: Dict[Optional[str], Set[str]] = {}
        self._triggers: Dict[str, List[Dict[str, Any]]] = {}
        self._expected_arrival: Dict[str, int] = {}

    # Core operations
    def register(self, buffer: DataBuffer, owner: Optional[str] = None) -> DataBuffer:
        if buffer.id not in self._buffers:
            self._buffers[buffer.id] = buffer
        # Assign owner
        self.set_owner(buffer.id, owner)
        return self._buffers[buffer.id]

    def create(self, size: int, content: Optional[bytes] = None, owner: Optional[str] = None) -> DataBuffer:
        buf = DataBuffer(size=size, content=content)
        return self.register(buf, owner=owner)

    def get(self, buffer_id: str) -> Optional[DataBuffer]:
        return self._buffers.get(buffer_id)

    def exists(self, buffer_id: str) -> bool:
        return buffer_id in self._buffers

    def owner(self, buffer_id: str) -> Optional[str]:
        return self._owner_of.get(buffer_id)

    def set_owner(self, buffer_id: str, owner: Optional[str]) -> None:
        prev = self._owner_of.get(buffer_id)
        if prev == owner and buffer_id in self._buffers:
            return
        # Remove from previous owner set
        if prev in self._owned_by:
            self._owned_by[prev].discard(buffer_id)
        # Assign new owner
        self._owner_of[buffer_id] = owner
        self._owned_by.setdefault(owner, set()).add(buffer_id)

    def transfer(self, buffer_id: str, new_owner: Optional[str]) -> None:
        if buffer_id not in self._buffers:
            raise KeyError(f"Unknown buffer id: {buffer_id}")
        self.set_owner(buffer_id, new_owner)

    def delete(self, buffer_id: str) -> Optional[DataBuffer]:
        buf = self._buffers.pop(buffer_id, None)
        if buf is not None:
            owner = self._owner_of.pop(buffer_id, None)
            if owner in self._owned_by:
                self._owned_by[owner].discard(buffer_id)
            # Remove triggers tracking
            self._triggers.pop(buffer_id, None)
            self._expected_arrival.pop(buffer_id, None)
        return buf

    # Accounting
    def bytes_owned(self, owner: Optional[str]) -> int:
        total = 0
        for bid in self._owned_by.get(owner, set()):
            b = self._buffers.get(bid)
            if b is not None:
                total += b.size
        return total

    def total_bytes(self) -> int:
        return sum(b.size for b in self._buffers.values())

    # Triggers and state handling
    def set_triggers(self, buffer_id: str, triggers: List[Dict[str, Any]]) -> None:
        self._triggers[buffer_id] = list(triggers)

    def add_trigger(self, buffer_id: str, trigger: Dict[str, Any]) -> None:
        self._triggers.setdefault(buffer_id, []).append(trigger)

    def set_state(self, sim, buffer_id: str, state: str) -> None:
        buf = self._buffers.get(buffer_id)
        if buf is None:
            return
        buf.state = state
        # Collect triggers from pool and from buffer itself
        trig_list: List[Dict[str, Any]] = []
        if buffer_id in self._triggers:
            trig_list.extend(self._triggers[buffer_id])
        if getattr(buf, "triggers", None):
            trig_list.extend(buf.triggers)
        if not trig_list:
            return
        # Fire matching triggers
        for trig in trig_list:
            try:
                if str(trig.get("on")) != state:
                    continue
                action = str(trig.get("action"))
                station = str(trig.get("station"))
                index = int(trig.get("index"))
            except Exception:
                continue
            # Lookup station resource and deliver a semaphore op
            target = sim.topology.resources.get(station)
            if target is None:
                continue
            kind = "sem_signal" if action == "signal" else "sem_wait"
            msg = Message(
                src="buffer_pool",
                dst=station,
                size=1,
                kind=kind,
                payload={"index": index, "buffer_id": buffer_id, "state": state},
                created_at=sim.ticks,
            )
            sim.deliver(target, "in", msg)

    # Scheduling helpers
    def record_expected_arrival(self, buffer_id: str, tick: int) -> None:
        self._expected_arrival[buffer_id] = int(tick)

    def tick(self, sim) -> None:
        # Transition buffers whose expected arrival is due
        due = [bid for bid, t in list(self._expected_arrival.items()) if t <= sim.ticks]
        for bid in due:
            self.set_state(sim, bid, "arrived")
            self._expected_arrival.pop(bid, None)
