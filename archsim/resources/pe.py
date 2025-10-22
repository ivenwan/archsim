from __future__ import annotations

import math
import random
from typing import Callable, List, Optional, Tuple, Dict, Any

from ..core.resource import Resource
from ..core.message import Message
from ..core.databuffer import DataBuffer


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

        # Busy/idle accounting
        self._busy_this_tick = False
        self._ticks = 0
        self._busy_ticks = 0

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

    def tick(self, sim) -> None:
        self._busy_this_tick = False
        cmd = None
        if self.mode == "pro":
            cmd = self._pop_command()
        if self.mode == "dummy":
            self._dummy_process(sim)
        else:
            # Pro mode: call process_fn if provided; else do nothing
            if self.process_fn is not None:
                inputs = self._gather_inputs()
                try:
                    outputs = self.process_fn(self, cmd, inputs) or []
                except Exception:
                    outputs = []
                if outputs:
                    self._emit_outputs(sim, outputs)
                    self._busy_this_tick = True

    def finalize_tick(self, sim) -> None:
        self._ticks += 1
        if self._busy_this_tick:
            self._busy_ticks += 1

    @property
    def avg_utilization(self) -> float:
        if self._ticks == 0:
            return 0.0
        return self._busy_ticks / self._ticks

