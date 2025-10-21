from __future__ import annotations

from ..core.resource import Resource
from ..core.message import Message
from ..core.databuffer import DataBuffer


class BufferProducer(Resource):
    """
    Produces a single DataBuffer transfer to a target memory at a given tick.
    """

    def __init__(self, name: str, buffer: DataBuffer, target_memory: str = "memory", issue_tick: int = 0):
        super().__init__(name)
        self.add_port("out", direction="out")
        self.buffer = buffer
        self.target_memory = target_memory
        self.issue_tick = max(0, issue_tick)
        self._sent = False

    def tick(self, sim) -> None:
        if not self._sent and sim.ticks >= self.issue_tick:
            # Ensure buffer is registered (owned by the producer initially)
            if not sim.buffer_pool.exists(self.buffer.id):
                sim.buffer_pool.register(self.buffer, owner=self.name)
            sim.buffer_pool.set_state(sim, self.buffer.id, "allocated")
            msg = Message(
                src=self.name,
                dst=self.target_memory,
                size=self.buffer.size,
                kind="buffer_transfer",
                payload={"buffer": self.buffer.to_dict()},
                created_at=sim.ticks,
            )
            self.send("out", msg)
            sim.buffer_pool.set_state(sim, self.buffer.id, "transit")
            self._sent = True


class BufferConsumer(Resource):
    """
    Issues a buffer_consume message to a target memory at a given tick,
    freeing the buffer by id.
    """

    def __init__(self, name: str, buffer_id: str, target_memory: str = "memory", consume_tick: int = 10):
        super().__init__(name)
        self.add_port("out", direction="out")
        self.add_port("in", direction="in")
        self.buffer_id = buffer_id
        self.target_memory = target_memory
        self.consume_tick = max(0, consume_tick)
        self._issued = False

    def tick(self, sim) -> None:
        # Drain any incoming messages (e.g., acks), but logic is minimal here
        inq = self.inbox["in"]
        while inq:
            _ = inq.popleft()

        if not self._issued and sim.ticks >= self.consume_tick:
            msg = Message(
                src=self.name,
                dst=self.target_memory,
                size=1,
                kind="buffer_consume",
                payload={"buffer_id": self.buffer_id},
                created_at=sim.ticks,
            )
            self.send("out", msg)
            self._issued = True
