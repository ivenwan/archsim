from __future__ import annotations

import math
import random
from typing import Callable, List, Optional, Tuple, Dict, Any, Union

from ..core.resource import Resource
from ..core.message import Message
from ..core.databuffer import DataBuffer
from ..core.queues import InputQueue, OutputQueue


class ProcessingElement(Resource):
    """
    Base processing element (PE) with multiple input and output queues
    and an optional command queue. Each tick, the PE may consume inputs
    and produce outputs via a `process` function.

    Modes
    - dummy: no command required; when idle, greedily pop the heads of
      input queues and combine into an output buffer. Output size is
      computed from the in:out ratio.
    - pro: process uses a command popped from command queue to decide
      how to handle inputs. Provide `process_fn` to customize behavior.

    Busy/idle accounting is tracked for profiling.
    """

    def __init__(
        self,
        name: str,
        in_queues: int = 2,
        out_queues: int = 1,
        mode: str = "dummy",
        in_out_ratio: Tuple[int, int] = (2, 1),
        output_target: Optional[str] = None,
        process_fn: Optional[Callable[["ProcessingElement", Any, List[Message]], List[Message]]] = None,
        backpressure_prob: float = 0.2,
    ) -> None:
        super().__init__(name)
        if in_queues <= 0 or out_queues <= 0:
            raise ValueError("PE requires at least one input and one output queue")
        if mode not in ("dummy", "pro"):
            raise ValueError("PE mode must be 'dummy' or 'pro'")
        self.mode = mode
        self.in_names = [f"in{i}" for i in range(in_queues)]
        self.out_names = [f"out{i}" for i in range(out_queues)]
        for n in self.in_names:
            self.add_port(n, direction="in")
        for n in self.out_names:
            self.add_port(n, direction="out")
        # command queue
        self.add_port("cmd", direction="in")
        self.in_out_ratio = in_out_ratio
        self.output_target = output_target  # e.g., memory name
        self.process_fn = process_fn
        self.backpressure_prob = max(0.0, min(1.0, backpressure_prob))

        # Busy/idle accounting
        self._busy_this_tick = False
        self._ticks = 0
        self._busy_ticks = 0
        # State machine for pro mode
        self.state = "idle"
        self._current_cmd: Optional[Message] = None
        self._current_inputs: List[Dict[str, Any]] = []  # [{buf, remaining}]
        self._consume_rate: int = 0
        self._output_progress: int = 0
        self._expected_output_size: int = 0
        # Queue registrations
        self._input_queues: List[InputQueue] = []
        self._output_queues: List[OutputQueue] = []
        for n in self.in_names:
            iq = InputQueue(parent=self.name, direction="in", function=n)
            iq.items = self.inbox[n]
            self._input_queues.append(iq)
        for n in self.out_names:
            oq = OutputQueue(parent=self.name, function=n)
            oq.items = self.outbox[n]
            self._output_queues.append(oq)
        self._queues_registered = False

    def _pop_command(self):
        q = self.inbox["cmd"]
        if q:
            return q.popleft()
        return None

    def _gather_inputs(self) -> List[Message]:
        gathered: List[Message] = []
        for n in self.in_names:
            q = self.inbox.get(n)
            if q and q:
                gathered.append(q.popleft())
        return gathered

    def _emit_outputs(self, sim, outputs: List[Message]) -> None:
        # For now, emit to out0 only; advanced routing can be added later
        for m in outputs:
            self.send(self.out_names[0], m)

    def _dummy_process(self, sim) -> None:
        inputs = self._gather_inputs()
        if not inputs:
            return
        # Determine total input size by treating messages with buffers specially
        total = 0
        bufs: List[DataBuffer] = []
        for m in inputs:
            if isinstance(m, Message):
                payload = getattr(m, "payload", {}) or {}
                b = payload.get("buffer")
                if isinstance(b, dict):
                    try:
                        size = int(b.get("size", m.size))
                    except Exception:
                        size = m.size
                    total += size
                else:
                    total += getattr(m, "size", 1)
        # Compute output size based on ratio
        in_n, out_n = self.in_out_ratio
        out_size = max(1, math.floor(total * (out_n / max(1, in_n))))
        # Create a new buffer and register
        buf = DataBuffer(size=out_size)
        sim.buffer_pool.register(buf, owner=self.name)
        sim.buffer_pool.set_state(sim, buf.id, "allocated")
        # Emit a transfer if target is provided; otherwise, emit a local message
        dst = self.output_target or "memory"
        msg = Message(
            src=self.name,
            dst=dst,
            size=buf.size,
            kind="buffer_transfer",
            payload={"buffer": buf.to_dict()},
            created_at=sim.ticks,
        )
        self._emit_outputs(sim, [msg])
        sim.buffer_pool.set_state(sim, buf.id, "transit")
        self._busy_this_tick = True

    def _start_command_if_ready(self) -> None:
        # Need a command and at least one item in each input queue
        cmdq = self.inbox["cmd"]
        if not cmdq:
            return
        for n in self.in_names:
            q = self.inbox.get(n)
            if not q or len(q) == 0:
                return
        # Pop command and one buffer from each input
        self._current_cmd = cmdq.popleft()
        self._current_inputs = []
        total_in = 0
        for n in self.in_names:
            buf = self.inbox[n].popleft()
            if isinstance(buf, DataBuffer):
                remaining = buf.size
            elif isinstance(buf, Message):
                remaining = getattr(buf, "size", 0)
            else:
                remaining = getattr(buf, "size", 0)
            self._current_inputs.append({"buf": buf, "remaining": remaining})
            total_in += remaining
        # Rate from command payload or default
        rate =  max(1, int((getattr(self._current_cmd, "payload", {}) or {}).get("rate", 64)))
        self._consume_rate = rate
        in_n, out_n = self.in_out_ratio
        self._expected_output_size = max(1, math.floor(total_in * (out_n / max(1, in_n))))
        self._output_progress = 0
        self.state = "busy"

    def _simulate_backpressure(self) -> bool:
        # Randomly signal backpressure
        if random.random() < self.backpressure_prob:
            return True
        return False

    def _relieve_backpressure(self) -> bool:
        # Randomly relieve backpressure
        return random.random() < 0.5

    def tick(self, sim) -> None:
        if not self._queues_registered and hasattr(sim, "topology"):
            for q in self._input_queues + self._output_queues:
                sim.topology.register_queue(q)
            self._queues_registered = True
        self._busy_this_tick = False
        if self.mode == "dummy":
            self._dummy_process(sim)
        else:
            # Pro mode: simple state machine with random backpressure
            if self.state == "idle":
                self._start_command_if_ready()
            if self.state == "backpressured":
                if self._relieve_backpressure():
                    self.state = "busy"
                else:
                    return
            if self.state == "busy":
                if self._simulate_backpressure():
                    self.state = "backpressured"
                    return
                if not self._current_inputs:
                    self.state = "idle"
                    return
                remaining_budget = self._consume_rate
                consumed_total = 0
                for slot in self._current_inputs:
                    if remaining_budget <= 0:
                        break
                    rem = slot.get("remaining", 0)
                    if rem <= 0:
                        continue
                    take = min(rem, remaining_budget)
                    slot["remaining"] = rem - take
                    remaining_budget -= take
                    consumed_total += take
                self._output_progress += consumed_total
                self._busy_this_tick = consumed_total > 0
                # Check if all inputs consumed
                if all(slot.get("remaining", 0) <= 0 for slot in self._current_inputs):
                    # Build output buffer
                    out_size = max(1, self._expected_output_size)
                    buf = DataBuffer(size=out_size, owner_memory=self.name, role="destination")
                    sim.buffer_pool.register(buf, owner=self.name)
                    sim.buffer_pool.set_state(sim, buf.id, "allocated")
                    dst = self.output_target or "memory"
                    msg = Message(
                        src=self.name,
                        dst=dst,
                        size=buf.size,
                        kind="buffer_transfer",
                        payload={"buffer": buf.to_dict()},
                        created_at=sim.ticks,
                    )
                    self._emit_outputs(sim, [msg])
                    sim.buffer_pool.set_state(sim, buf.id, "transit")
                    # Mark consumed inputs as deallocated
                    for slot in self._current_inputs:
                        b = slot.get("buf")
                        if isinstance(b, DataBuffer):
                            sim.buffer_pool.set_state(sim, b.id, "deallocated")
                            sim.buffer_pool.delete(b.id)
                    self._current_inputs = []
                    self._current_cmd = None
                    self.state = "idle"

    def finalize_tick(self, sim) -> None:
        self._ticks += 1
        if self._busy_this_tick:
            self._busy_ticks += 1

    @property
    def avg_utilization(self) -> float:
        if self._ticks == 0:
            return 0.0
        return self._busy_ticks / self._ticks
