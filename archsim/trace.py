from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TraceOptions:
    every: int = 1              # print every N ticks
    queues: bool = True         # print non-empty queues per resource
    links: bool = True          # print per-link bytes moved and occupancy
    show_empty: bool = False    # include empty queues/links


class ConsoleTracer:
    def __init__(self, options: Optional[TraceOptions] = None) -> None:
        self.opt = options or TraceOptions()

    def on_tick(self, sim) -> None:
        t = sim.ticks
        if self.opt.every <= 0 or (t % self.opt.every) != 0:
            return

        print(f"[tick {t}]")

        if self.opt.queues:
            for name, res in sim.topology.resources.items():
                # Collect non-empty queues (or all if show_empty)
                lines = []
                for port, q in res.inbox.items():
                    if self.opt.show_empty or len(q) > 0:
                        lines.append(f"in:{port}={len(q)}")
                for port, q in res.outbox.items():
                    if self.opt.show_empty or len(q) > 0:
                        lines.append(f"out:{port}={len(q)}")
                if lines:
                    print(f"  res {name}: " + ", ".join(lines))

        if self.opt.links:
            for lk in sim.topology.links:
                occ = sum(len(stage) for stage in getattr(lk, "pipeline", []))
                moved = getattr(lk, "bytes_moved_this_tick", 0)
                if self.opt.show_empty or moved > 0 or occ > 0:
                    print(
                        f"  link {lk.name}: moved={moved}B, occ={occ}, bw={lk.bandwidth}, lat={lk.latency}"
                    )
        # Channels occupancy
        try:
            from .core.channel import Channel  # type: ignore
        except Exception:
            Channel = None  # type: ignore
        if Channel is not None:
            for name, res in sim.topology.resources.items():
                if isinstance(res, Channel):
                    if self.opt.show_empty or res._active_count > 0:
                        print(
                            f"  chan {name}: active={res._active_count}, mode={res.transfer_mode}, avg={res.avg_occupancy:.2f}"
                        )
