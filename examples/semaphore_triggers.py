from __future__ import annotations

from archsim.core.simulator import Simulator
from archsim.core.topology import Topology
from archsim.resources.memory import Memory
from archsim.resources.generator import BufferGenerator
from archsim.resources.semaphore import SemaphoreStation
from archsim.resources.semaphore_client import SemaphoreClient


def build(topo: Topology) -> Simulator:
    # Memory and semaphore station
    mem = Memory("memory", latency=5, max_issue_per_tick=4)
    sem = SemaphoreStation("sem", count=8)

    # Generator that attaches triggers to its buffers:
    # - signal sem[0] on arrival
    # - signal sem[1] on deallocation
    gen = BufferGenerator(
        "gen",
        period=20,
        buffer_size=2048,
        target_memory="memory",
        start_tick=0,
        total=3,
        triggers=[
            {"on": "arrived", "action": "signal", "station": "sem", "index": 0},
            {"on": "deallocated", "action": "signal", "station": "sem", "index": 1},
        ],
        auto_consume_after=40,  # will free buffers to fire deallocated trigger
    )

    # Two clients waiting on sem[0] (arrival) and sem[1] (deallocation)
    waiter_arrived = SemaphoreClient("waiter_arrived", station="sem", index=0, start_tick=0)
    waiter_dealloc = SemaphoreClient("waiter_dealloc", station="sem", index=1, start_tick=0)

    topo.add(mem, sem, gen, waiter_arrived, waiter_dealloc)

    # Wire gen <-> memory for buffer transfer + acks
    topo.connect(gen, "out", mem, "in", bandwidth=256, latency=1)
    topo.connect(mem, "out", gen, "in", bandwidth=256, latency=1)

    # Wire semaphore station to clients
    topo.connect(waiter_arrived, "out", sem, "in", bandwidth=1, latency=0)
    topo.connect(waiter_dealloc, "out", sem, "in", bandwidth=1, latency=0)
    topo.connect(sem, "out", waiter_arrived, "in", bandwidth=1, latency=0)
    topo.connect(sem, "out", waiter_dealloc, "in", bandwidth=1, latency=0)

    return Simulator(topo)


if __name__ == "__main__":
    sim = build(Topology())
    # Enable tracing by adjusting CLI flags when running via `python -m archsim`.
    sim.run(max_ticks=200)
    wa = sim.topology.get("waiter_arrived")
    wd = sim.topology.get("waiter_dealloc")
    print({"arrived_grants": wa.granted, "dealloc_grants": wd.granted})

